from __future__ import annotations

import json
import shutil
import sqlite3
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from sqlalchemy import text

from app import __version__
from app.config import BACKUPS_DIR, DATA_DIR, HOSTED_DIR, ROOT_DIR, TLS_DIR
from app import db as database

FORMAT = "fileserve-backup"
FORMAT_VERSION = 1
DB_NAME = "fileserve.db"


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _db_path() -> Path:
    return DATA_DIR / DB_NAME


def _checkpoint_db() -> Path | None:
    db_path = _db_path()
    if not db_path.exists():
        return None
    try:
        if database.engine is not None:
            with database.engine.begin() as conn:
                conn.execute(text("PRAGMA wal_checkpoint(TRUNCATE)"))
    except Exception:
        raw = sqlite3.connect(db_path)
        try:
            raw.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            raw.close()
    return db_path


def write_backup(dest: Path | None = None) -> Path:
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    dest = dest or (BACKUPS_DIR / f"fileserve-backup-{_timestamp()}.zip")
    dest.parent.mkdir(parents=True, exist_ok=True)
    db_path = _checkpoint_db()
    manifest = {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "app_version": __version__,
    }
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, indent=2))
        if db_path and db_path.exists():
            archive.write(db_path, DB_NAME)
        env_path = ROOT_DIR / ".env"
        if env_path.exists():
            archive.write(env_path, ".env")
        if HOSTED_DIR.exists():
            for path in HOSTED_DIR.rglob("*"):
                if path.is_file():
                    archive.write(path, Path("hosted") / path.relative_to(HOSTED_DIR))
        if TLS_DIR.exists():
            for path in TLS_DIR.rglob("*"):
                if path.is_file():
                    archive.write(path, Path("tls") / path.relative_to(TLS_DIR))
    return dest


def backup_bytes() -> bytes:
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    temp = BACKUPS_DIR / f".tmp-{_timestamp()}.zip"
    try:
        write_backup(temp)
        return temp.read_bytes()
    finally:
        if temp.exists():
            temp.unlink()


def latest_backup() -> Path | None:
    if not BACKUPS_DIR.exists():
        return None
    zips = sorted(BACKUPS_DIR.glob("fileserve-backup-*.zip"), key=lambda path: path.stat().st_mtime)
    return zips[-1] if zips else None


def restore_backup(payload: bytes | Path) -> None:
    raw = payload.read_bytes() if isinstance(payload, Path) else payload
    with zipfile.ZipFile(BytesIO(raw)) as archive:
        names = set(archive.namelist())
        if "manifest.json" in names:
            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
            if manifest.get("format") and manifest.get("format") != FORMAT:
                raise ValueError("That file is not a FileServe backup.")
        if DB_NAME not in names:
            raise ValueError("Backup is missing the database.")
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        HOSTED_DIR.mkdir(parents=True, exist_ok=True)
        try:
            if database.engine is not None:
                database.engine.dispose()
        except Exception:
            pass
        db_path = _db_path()
        db_path.write_bytes(archive.read(DB_NAME))
        for stale in (DATA_DIR / f"{DB_NAME}-wal", DATA_DIR / f"{DB_NAME}-shm"):
            if stale.exists():
                stale.unlink()
        if ".env" in names:
            (ROOT_DIR / ".env").write_bytes(archive.read(".env"))
        if HOSTED_DIR.exists():
            for child in HOSTED_DIR.iterdir():
                if child.name == ".gitkeep":
                    continue
                if child.is_file():
                    child.unlink()
                elif child.is_dir():
                    shutil.rmtree(child)
        for name in names:
            if not name.startswith("hosted/") or name.endswith("/"):
                continue
            target = HOSTED_DIR / name[len("hosted/") :]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(name))
        if any(name.startswith("tls/") for name in names):
            TLS_DIR.mkdir(parents=True, exist_ok=True)
            for child in TLS_DIR.iterdir():
                if child.is_file():
                    child.unlink()
                elif child.is_dir():
                    shutil.rmtree(child)
            for name in names:
                if not name.startswith("tls/") or name.endswith("/"):
                    continue
                target = TLS_DIR / name[len("tls/") :]
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(name))
