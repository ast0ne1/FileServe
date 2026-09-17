from __future__ import annotations

import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from werkzeug.security import check_password_hash

_hasher = PasswordHasher()
WERKZEUG_PREFIXES = ("pbkdf2:", "scrypt:", "argon2:")


def is_argon2(value: str | None) -> bool:
    return (value or "").strip().startswith("$argon2")


def is_hashed(value: str | None) -> bool:
    raw = (value or "").strip()
    return is_argon2(raw) or raw.startswith(WERKZEUG_PREFIXES)


def hash_password(password: str) -> str:
    return _hasher.hash(password or "")


def secrets_compare(left: str, right: str) -> bool:
    return secrets.compare_digest(left.encode("utf-8"), right.encode("utf-8")) if len(left) == len(right) else False


def verify_password(stored: str, password: str) -> bool:
    raw = (stored or "").strip()
    if not raw:
        return False
    if is_argon2(raw):
        try:
            return _hasher.verify(raw, password or "")
        except (VerifyMismatchError, InvalidHashError):
            return False
    if raw.startswith(WERKZEUG_PREFIXES):
        return check_password_hash(raw, password or "")
    return secrets_compare(raw, password or "")


def needs_rehash(stored: str) -> bool:
    raw = (stored or "").strip()
    if not is_argon2(raw):
        return True
    try:
        return _hasher.check_needs_rehash(raw)
    except Exception:  # noqa: BLE001
        return True
