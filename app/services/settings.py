from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import env
from app.models import Setting, User
from app.services import passwords

DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "admin"

UI_KEYS = (
    "admin_username",
    "admin_password",
    "instance_name",
    "device_hostname",
    "github_repo",
    "https_enabled",
)


def _env_value(key: str) -> str:
    mapping = {
        "admin_username": env.admin_username,
        "admin_password": env.admin_password,
        "instance_name": env.instance_name,
        "device_hostname": env.device_hostname,
        "github_repo": env.github_repo,
    }
    return mapping.get(key, "") or ""


def _default_value(key: str) -> str:
    if key == "admin_username":
        return DEFAULT_ADMIN_USERNAME
    if key == "admin_password":
        return DEFAULT_ADMIN_PASSWORD
    return ""


def get_setting_row(db: Session, key: str) -> Setting | None:
    return db.get(Setting, key)


def get_value(db: Session, key: str) -> str:
    row = get_setting_row(db, key)
    if row is not None and row.value != "":
        return row.value
    env_val = _env_value(key)
    if env_val:
        return env_val
    return _default_value(key)


def get_source(db: Session, key: str) -> str:
    row = get_setting_row(db, key)
    if row is not None and row.value != "":
        return "ui"
    if _env_value(key):
        return "env"
    if _default_value(key):
        return "default"
    return "unset"


def set_value(db: Session, key: str, value: str) -> None:
    row = get_setting_row(db, key)
    now = datetime.now(timezone.utc)
    if row is None:
        db.add(Setting(key=key, value=value, updated_at=now))
    else:
        row.value = value
        row.updated_at = now
    db.commit()


def clear_value(db: Session, key: str) -> None:
    row = get_setting_row(db, key)
    if row is None:
        return
    db.delete(row)
    db.commit()


def get_admin_credentials(db: Session) -> tuple[str, str]:
    return get_value(db, "admin_username"), get_value(db, "admin_password")


def https_enabled(db: Session | None) -> bool:
    if db is None:
        return False
    return get_value(db, "https_enabled") == "1"


def set_https_enabled(db: Session, enabled: bool) -> None:
    if enabled:
        set_value(db, "https_enabled", "1")
    else:
        clear_value(db, "https_enabled")


def using_factory_admin(db: Session) -> bool:
    admin = db.query(User).filter(User.role == "admin").order_by(User.id.asc()).first()
    if admin is not None:
        if admin.username != DEFAULT_ADMIN_USERNAME:
            return False
        return passwords.verify_password(admin.password_hash, DEFAULT_ADMIN_PASSWORD)
    username, password = get_admin_credentials(db)
    if username != DEFAULT_ADMIN_USERNAME:
        return False
    return passwords.verify_password(password, DEFAULT_ADMIN_PASSWORD)
