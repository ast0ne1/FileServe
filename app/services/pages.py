import calendar
import re
import shutil
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.orm import Session
from werkzeug.datastructures import FileStorage
from werkzeug.security import generate_password_hash

from app.auth import password_matches
from app.config import HOSTED_DIR
from app.models import Page, utcnow

RESERVED_SLUGS = {
    "login",
    "logout",
    "admin",
    "static",
    "hosted",
    "settings",
    "manifest.webmanifest",
    "favicon.ico",
}

SLUG_RE = re.compile(r"[^a-z0-9]+")
MIN_PAGE_PASSWORD = 4
EXPIRY_MODES = ("none", "week", "month", "3months", "6months", "custom")


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def add_calendar_months(moment: datetime, months: int) -> datetime:
    month_index = moment.month - 1 + months
    year = moment.year + month_index // 12
    month = month_index % 12 + 1
    day = min(moment.day, calendar.monthrange(year, month)[1])
    return moment.replace(year=year, month=month, day=day)


def resolve_expiry(mode: str, custom_date: str = "", *, now: datetime | None = None) -> datetime | None:
    chosen = (mode or "none").strip().lower()
    if chosen in {"", "none", "keep"}:
        return None
    moment = now or utcnow()
    if chosen == "week":
        return moment + timedelta(days=7)
    if chosen == "month":
        return add_calendar_months(moment, 1)
    if chosen == "3months":
        return add_calendar_months(moment, 3)
    if chosen == "6months":
        return add_calendar_months(moment, 6)
    if chosen != "custom":
        raise ValueError("Choose a valid expiry.")
    raw = (custom_date or "").strip()
    if not raw:
        raise ValueError("Choose an expiry date.")
    try:
        day = date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError("Expiry date must be a valid date.") from exc
    end = datetime(day.year, day.month, day.day, 23, 59, 59, tzinfo=timezone.utc)
    if end <= moment:
        raise ValueError("Expiry must be in the future.")
    return end


def is_expired(page: Page, *, now: datetime | None = None) -> bool:
    if page.expires_at is None:
        return False
    return as_utc(page.expires_at) <= (now or utcnow())


def slugify(title: str) -> str:
    text = unicodedata.normalize("NFKD", title or "").encode("ascii", "ignore").decode("ascii")
    text = text.lower().replace("/", " ")
    text = SLUG_RE.sub("-", text).strip("-")
    return text


def page_dir(slug: str) -> Path:
    HOSTED_DIR.mkdir(parents=True, exist_ok=True)
    return HOSTED_DIR / slug


def get_by_slug(db: Session, slug: str) -> Page | None:
    return db.query(Page).filter(Page.slug == slug).one_or_none()


def list_pages(db: Session) -> list[Page]:
    return db.query(Page).order_by(Page.created_at.desc()).all()


def resolve_slug(label: str, requested: str = "") -> str:
    slug = slugify(requested) or slugify(label)
    if not slug:
        raise ValueError("The path needs at least one letter or number.")
    if slug in RESERVED_SLUGS:
        raise ValueError("That URL is reserved by FileServe. Choose a different path.")
    return slug


def _slug_taken(db: Session, slug: str, *, ignore_id: int | None = None) -> bool:
    existing = get_by_slug(db, slug)
    if existing is not None and existing.id != ignore_id:
        return True
    folder = page_dir(slug)
    if ignore_id is not None:
        current = db.get(Page, ignore_id)
        if current is not None and current.slug == slug:
            return False
    return folder.exists() and (existing is None or existing.id != ignore_id)


def _apply_auth(page: Page, *, protect: bool, username: str, password: str, keep_password: bool) -> None:
    if not protect:
        page.auth_username = ""
        page.auth_password_hash = ""
        return
    clean_user = (username or "").strip()
    if not clean_user:
        raise ValueError("Enter a username for this page.")
    if password:
        if len(password) < MIN_PAGE_PASSWORD:
            raise ValueError(f"Page password must be at least {MIN_PAGE_PASSWORD} characters.")
        page.auth_password_hash = generate_password_hash(password)
    elif not keep_password or not page.auth_password_hash:
        raise ValueError("Enter a password for this page.")
    page.auth_username = clean_user


def _relocate(old_slug: str, new_slug: str) -> None:
    if old_slug == new_slug:
        return
    source = page_dir(old_slug)
    dest = page_dir(new_slug)
    if dest.exists():
        raise ValueError("That URL is already in use.")
    if source.exists():
        source.rename(dest)


def create_page(
    db: Session,
    title: str,
    upload: FileStorage,
    *,
    slug: str = "",
    protect: bool = False,
    username: str = "",
    password: str = "",
    expires_at: datetime | None = None,
) -> Page:
    clean_title = (title or "").strip()
    if not clean_title:
        raise ValueError("Enter a label.")
    filename = (upload.filename or "").strip()
    if not filename:
        raise ValueError("Choose an HTML file.")
    suffix = Path(filename).suffix.lower()
    if suffix != ".html":
        raise ValueError("Only .html files can be hosted.")
    clean_slug = resolve_slug(clean_title, slug)
    if _slug_taken(db, clean_slug):
        raise ValueError("That URL is already in use.")
    folder = page_dir(clean_slug)
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / "index.html"
    upload.save(dest)
    page = Page(
        title=clean_title,
        slug=clean_slug,
        filename=filename,
        page_type="html",
        expires_at=expires_at,
        enabled=True,
    )
    try:
        _apply_auth(page, protect=protect, username=username, password=password, keep_password=False)
        db.add(page)
        db.commit()
        db.refresh(page)
    except Exception:
        db.rollback()
        if folder.exists():
            shutil.rmtree(folder, ignore_errors=True)
        raise
    return page


def update_page(
    db: Session,
    page_id: int,
    *,
    title: str,
    slug: str = "",
    protect: bool = False,
    username: str = "",
    password: str = "",
    expires_at: datetime | None = None,
) -> Page:
    page = db.get(Page, page_id)
    if page is None:
        raise ValueError("That page is already gone.")
    clean_title = (title or "").strip()
    if not clean_title:
        raise ValueError("Enter a label.")
    clean_slug = resolve_slug(clean_title, slug)
    if _slug_taken(db, clean_slug, ignore_id=page.id):
        raise ValueError("That URL is already in use.")
    old_slug = page.slug
    relocated = False
    try:
        _apply_auth(
            page,
            protect=protect,
            username=username,
            password=password,
            keep_password=page.is_protected,
        )
        page.title = clean_title
        page.expires_at = expires_at
        if clean_slug != old_slug:
            _relocate(old_slug, clean_slug)
            relocated = True
            page.slug = clean_slug
        db.commit()
        db.refresh(page)
    except Exception:
        db.rollback()
        if relocated:
            try:
                _relocate(clean_slug, old_slug)
            except ValueError:
                pass
        raise
    return page


def toggle_page(db: Session, page_id: int) -> Page:
    page = db.get(Page, page_id)
    if page is None:
        raise ValueError("That page is already gone.")
    page.enabled = not bool(page.enabled)
    db.commit()
    db.refresh(page)
    return page


def delete_page(db: Session, page_id: int) -> Page:
    page = db.get(Page, page_id)
    if page is None:
        raise ValueError("That page is already gone.")
    folder = page_dir(page.slug)
    db.delete(page)
    db.commit()
    if folder.exists():
        shutil.rmtree(folder, ignore_errors=True)
    return page


def purge_expired(db: Session) -> list[str]:
    now = utcnow()
    expired = [page for page in db.query(Page).filter(Page.expires_at.isnot(None)).all() if is_expired(page, now=now)]
    removed = []
    for page in expired:
        folder = page_dir(page.slug)
        removed.append(page.slug)
        db.delete(page)
        if folder.exists():
            shutil.rmtree(folder, ignore_errors=True)
    if expired:
        db.commit()
    return removed


def credentials_allowed(page: Page, username: str, password: str) -> bool:
    if not page.is_protected:
        return True
    return bool(username) and username == page.auth_username and password_matches(page.auth_password_hash, password)
