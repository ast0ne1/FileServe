from __future__ import annotations

import secrets
from urllib.parse import urlparse

from flask import Request, Response, g, redirect, request, session, url_for
from sqlalchemy.orm import Session

from app.config import DATA_DIR, env
from app.models import User
from app.services import settings, users as users_svc

COOKIE_MAX_AGE = 60 * 60 * 24 * 14


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


def request_is_https() -> bool:
    if request.is_secure:
        return True
    if not settings.https_enabled(getattr(g, "db", None)):
        return False
    return (request.headers.get("x-forwarded-proto") or "").lower() == "https"


def is_signed_in() -> bool:
    return bool(session.get("uid"))


def current_user_id() -> int | None:
    raw = session.get("uid")
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def current_role() -> str:
    return str(session.get("role") or "")


def is_admin() -> bool:
    return current_role() == "admin"


def current_user(db: Session | None = None) -> User | None:
    uid = current_user_id()
    if uid is None:
        return None
    session_db = db or getattr(g, "db", None)
    if session_db is None:
        return None
    return users_svc.get_user(session_db, uid)


def attach_session(user: User) -> None:
    session.permanent = True
    session["uid"] = user.id
    session["user"] = user.username
    session["role"] = user.role
    session.modified = True


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


# Back-compat for page Basic auth hashing checks
def password_matches(stored: str, provided: str) -> bool:
    from app.services.passwords import verify_password

    return verify_password(stored, provided)
