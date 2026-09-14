import secrets
from urllib.parse import urlparse

from flask import Request, Response, redirect, request, session, url_for
from sqlalchemy.orm import Session
from werkzeug.security import check_password_hash

from app.config import DATA_DIR, env
from app.services import settings

COOKIE_NAME = "fileserve"
COOKIE_MAX_AGE = 60 * 60 * 24 * 14
HASH_PREFIXES = ("pbkdf2:", "scrypt:", "argon2:")


def _equal(left: str, right: str) -> bool:
    return secrets.compare_digest(left.encode("utf-8"), right.encode("utf-8")) if len(left) == len(right) else False


def session_secret() -> str:
    if env.session_secret.strip():
        return env.session_secret.strip()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / "session.secret"
    if path.exists():
        stored = path.read_text(encoding="utf-8").strip()
        if stored:
            return stored
    value = secrets.token_hex(32)
    path.write_text(value, encoding="utf-8")
    return value


def password_matches(stored: str, provided: str) -> bool:
    if stored.startswith(HASH_PREFIXES):
        return check_password_hash(stored, provided)
    return _equal(stored, provided)


def credentials_match(db: Session, username: str, password: str) -> bool:
    expected_user, expected_pass = settings.get_admin_credentials(db)
    return _equal(username, expected_user) and password_matches(expected_pass, password)


def is_signed_in() -> bool:
    return bool(session.get("user"))


def current_user() -> str | None:
    user = session.get("user")
    return str(user) if user else None


def attach_session(username: str) -> None:
    session.permanent = True
    session["user"] = username


def clear_session() -> None:
    session.clear()


def safe_next(value: str | None) -> str:
    if not value:
        return url_for("pages_list")
    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc or not value.startswith("/") or value.startswith("//"):
        return url_for("pages_list")
    return value


def wants_json(req: Request | None = None) -> bool:
    req = req or request
    accept = req.headers.get("accept", "")
    return "application/json" in accept or req.headers.get("x-requested-with") == "fetch"


def login_redirect() -> Response:
    nxt = request.full_path
    if nxt.endswith("?"):
        nxt = request.path
    return redirect(url_for("login", next=nxt))
