from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import HOSTED_DIR
from app.models import Page, User
from app.services import passwords, settings

logger = logging.getLogger("fileserve.users")

USERNAME_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,30}[a-z0-9])?$")
RESERVED_USERNAMES = {
    "login",
    "logout",
    "static",
    "hosted",
    "settings",
    "browse",
    "u",
    "users",
}


def validate_username(username: str) -> str:
    name = (username or "").strip().lower()
    if not name:
        raise ValueError("Enter a username.")
    if name in RESERVED_USERNAMES:
        raise ValueError("That username is reserved.")
    if not USERNAME_RE.fullmatch(name):
        raise ValueError("Username must be letters, digits, or hyphens.")
    return name


def ensure_admin_user(db: Session | None = None) -> User:
    from app import db as database

    own = db is None
    session = db or database.SessionLocal()
    try:
        existing = session.query(User).order_by(User.id.asc()).first()
        if existing is not None:
            return existing
        username, password = settings.get_admin_credentials(session)
        username = (username or settings.DEFAULT_ADMIN_USERNAME).strip() or settings.DEFAULT_ADMIN_USERNAME
        username = username.lower()
        raw = password or settings.DEFAULT_ADMIN_PASSWORD
        hashed = raw if passwords.is_hashed(raw) else passwords.hash_password(raw)
        if not passwords.is_hashed(raw):
            settings.set_value(session, "admin_password", hashed)
        if settings.get_value(session, "admin_username") != username:
            settings.set_value(session, "admin_username", username)
        user = User(username=username, password_hash=hashed, role="admin", active=True)
        session.add(user)
        session.commit()
        session.refresh(user)
        logger.info("Created household admin user id=%s username=%s", user.id, user.username)
        return user
    finally:
        if own:
            session.close()


def list_users(db: Session) -> list[User]:
    return db.query(User).order_by(User.role.desc(), User.username.asc()).all()


def get_user(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def get_by_username(db: Session, username: str) -> User | None:
    name = (username or "").strip().lower()
    if not name:
        return None
    return db.query(User).filter(User.username == name).one_or_none()


def create_user(db: Session, *, username: str, password: str, role: str = "user") -> User:
    name = validate_username(username)
    if get_by_username(db, name) is not None:
        raise ValueError("That username is already taken.")
    if len(password or "") < 4:
        raise ValueError("Password must be at least 4 characters.")
    if role == "admin":
        raise ValueError("Extra admin accounts are not supported. Create a regular user.")
    user = User(username=name, password_hash=passwords.hash_password(password), role="user", active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    (HOSTED_DIR / "u" / name).mkdir(parents=True, exist_ok=True)
    return user


def update_user(
    db: Session,
    user: User,
    *,
    active: bool | None = None,
    new_password: str | None = None,
) -> User:
    if user.role == "admin" and active is False:
        other = (
            db.query(User)
            .filter(User.role == "admin", User.active.is_(True), User.id != user.id)
            .count()
        )
        if other == 0:
            raise ValueError("Keep at least one active admin account.")
    if active is not None:
        user.active = bool(active)
    if new_password:
        if len(new_password) < 4:
            raise ValueError("Password must be at least 4 characters.")
        user.password_hash = passwords.hash_password(new_password)
        if user.role == "admin":
            settings.set_value(db, "admin_password", user.password_hash)
            settings.set_value(db, "admin_username", user.username)
    db.commit()
    db.refresh(user)
    return user


def delete_user(db: Session, user: User) -> None:
    if user.role == "admin":
        raise ValueError("The household admin account cannot be removed.")
    pages = db.query(Page).filter(Page.user_id == user.id).all()
    for page in pages:
        folder = HOSTED_DIR / "u" / user.username / page.slug
        db.delete(page)
        if folder.exists():
            shutil.rmtree(folder, ignore_errors=True)
    folder_root = HOSTED_DIR / "u" / user.username
    db.delete(user)
    db.commit()
    if folder_root.exists():
        shutil.rmtree(folder_root, ignore_errors=True)


def authenticate(db: Session, username: str, password: str) -> User | None:
    user = get_by_username(db, username)
    if user is None or not user.active:
        return None
    if not passwords.verify_password(user.password_hash, password):
        return None
    if passwords.needs_rehash(user.password_hash):
        user.password_hash = passwords.hash_password(password)
        if user.role == "admin":
            settings.set_value(db, "admin_password", user.password_hash)
        else:
            db.commit()
    return user


def migrate_multi_user() -> None:
    """Create users table, bootstrap admin, and attach existing pages to the admin."""
    from app import db as database

    if database.engine is None:
        return
    ensure_admin_user()
    db = database.SessionLocal()
    try:
        admin = db.query(User).filter(User.role == "admin").order_by(User.id.asc()).first()
        if admin is None:
            admin = ensure_admin_user(db)
        cols = {row[1] for row in db.execute(text("PRAGMA table_info(pages)")).fetchall()}
        if "user_id" not in cols:
            db.execute(text("ALTER TABLE pages ADD COLUMN user_id INTEGER"))
            db.commit()
        db.execute(text("UPDATE pages SET user_id = :uid WHERE user_id IS NULL"), {"uid": admin.id})
        db.commit()
        # Unique slug within owner: drop old global unique if needed is handled by app logic
        HOSTED_DIR.mkdir(parents=True, exist_ok=True)
        (HOSTED_DIR / "u").mkdir(parents=True, exist_ok=True)
    finally:
        db.close()
