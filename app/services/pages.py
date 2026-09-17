import calendar
import re
import shutil
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from html import escape
from io import BytesIO
from pathlib import Path

import mammoth
from sqlalchemy.orm import Session
from werkzeug.datastructures import FileStorage

from app.auth import password_matches
from app.config import HOSTED_DIR
from app.models import Page, User, utcnow
from app.services import passwords

RESERVED_SLUGS = {
    "login",
    "logout",
    "admin",
    "static",
    "hosted",
    "settings",
    "browse",
    "u",
    "manifest.webmanifest",
    "favicon.ico",
}

ALLOWED_SUFFIXES = {".html", ".pdf", ".docx"}
STORED_HTML = "index.html"
STORED_PDF = "file.pdf"
STORED_DOCX = "file.docx"
STORED_PREVIEW = "preview.html"
PUBLIC_FILES = {"html": STORED_HTML, "pdf": STORED_PDF, "docx": STORED_PREVIEW}
SOURCE_FILES = {"html": STORED_HTML, "pdf": STORED_PDF, "docx": STORED_DOCX}
MAX_DESCRIPTION = 280
MIME_TYPES = {
    "html": "text/html; charset=utf-8",
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
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


def page_dir_for(owner: User | None, slug: str) -> Path:
    HOSTED_DIR.mkdir(parents=True, exist_ok=True)
    if owner is None or owner.is_admin:
        return HOSTED_DIR / slug
    folder = HOSTED_DIR / "u" / owner.username / slug
    folder.parent.mkdir(parents=True, exist_ok=True)
    return folder


def page_dir(page: Page) -> Path:
    return page_dir_for(page.owner, page.slug)


def get_root_by_slug(db: Session, slug: str) -> Page | None:
    return (
        db.query(Page)
        .join(User, Page.user_id == User.id)
        .filter(Page.slug == slug, User.role == "admin")
        .one_or_none()
    )


def get_user_page(db: Session, username: str, slug: str) -> Page | None:
    return (
        db.query(Page)
        .join(User, Page.user_id == User.id)
        .filter(User.username == username.lower(), User.role == "user", Page.slug == slug)
        .one_or_none()
    )


def get_by_slug(db: Session, slug: str) -> Page | None:
    """Backward-compatible alias for root (admin) pages."""
    return get_root_by_slug(db, slug)


def list_pages(db: Session, *, viewer: User, owner_id: int | None = None) -> list[Page]:
    query = db.query(Page).join(User, Page.user_id == User.id)
    if viewer.is_admin:
        if owner_id is not None:
            query = query.filter(Page.user_id == owner_id)
    else:
        query = query.filter(Page.user_id == viewer.id)
    return query.order_by(Page.created_at.desc()).all()


def list_public_pages(db: Session) -> list[Page]:
    pages = (
        db.query(Page)
        .filter(Page.enabled.is_(True))
        .order_by(Page.title.asc())
        .all()
    )
    return [page for page in pages if not is_expired(page)]


def get_page(db: Session, page_id: int) -> Page | None:
    return db.get(Page, page_id)


def can_manage(viewer: User, page: Page) -> bool:
    if viewer.is_admin:
        return True
    return page.user_id == viewer.id


def public_filename(page: Page) -> str:
    return PUBLIC_FILES.get(page.page_type, STORED_HTML)


def source_filename(page: Page) -> str:
    return SOURCE_FILES.get(page.page_type, STORED_HTML)


def public_file_path(page: Page) -> Path:
    return page_dir(page) / public_filename(page)


def source_path(page: Page) -> Path:
    return page_dir(page) / source_filename(page)


def download_name(page: Page) -> str:
    name = Path(page.filename or "").name
    if name:
        return name
    return source_filename(page)


def public_mimetype(page: Page) -> str:
    if page.page_type == "docx":
        return "text/html; charset=utf-8"
    return MIME_TYPES.get(page.page_type, "application/octet-stream")


def source_mimetype(page: Page) -> str:
    return MIME_TYPES.get(page.page_type, "application/octet-stream")


def _clean_description(value: str) -> str:
    text = (value or "").strip()
    if len(text) > MAX_DESCRIPTION:
        raise ValueError(f"Description must be {MAX_DESCRIPTION} characters or fewer.")
    return text


def _original_name(upload: FileStorage) -> str:
    return Path((upload.filename or "").strip()).name


@dataclass
class PreparedUpload:
    filename: str
    page_type: str
    source_name: str
    source_bytes: bytes
    preview_html: str | None = None


def _docx_preview(data: bytes, title: str) -> str:
    try:
        result = mammoth.convert_to_html(BytesIO(data), convert_image=mammoth.images.data_uri)
    except Exception as exc:  # noqa: BLE001
        raise ValueError("That Word file could not be opened. Try exporting it as PDF.") from exc
    body = (result.value or "").strip()
    if not body:
        raise ValueError("That Word file has no readable text. Try exporting it as PDF.")
    safe_title = escape(title or "Document")
    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8"/>\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1"/>\n'
        f"<title>{safe_title}</title>\n"
        "<style>\n"
        "body{font-family:Georgia,serif;max-width:42rem;margin:2rem auto;padding:0 1rem;"
        "line-height:1.5;color:#1c1814;}\n"
        "img{max-width:100%;height:auto;}\n"
        "</style>\n"
        "</head>\n"
        f"<body>\n{body}\n</body>\n"
        "</html>\n"
    )


def prepare_upload(upload: FileStorage, title: str) -> PreparedUpload:
    filename = _original_name(upload)
    if not filename:
        raise ValueError("Choose an HTML, PDF, or Word file.")
    suffix = Path(filename).suffix.lower()
    if suffix == ".doc":
        raise ValueError("Legacy .doc files cannot be opened in the browser. Save as .docx or upload a PDF.")
    if suffix not in ALLOWED_SUFFIXES:
        raise ValueError("Host an .html, .pdf, or .docx file.")
    data = upload.read()
    if not data:
        raise ValueError("That file is empty.")
    if suffix == ".html":
        return PreparedUpload(filename=filename, page_type="html", source_name=STORED_HTML, source_bytes=data)
    if suffix == ".pdf":
        return PreparedUpload(filename=filename, page_type="pdf", source_name=STORED_PDF, source_bytes=data)
    preview = _docx_preview(data, title)
    return PreparedUpload(
        filename=filename,
        page_type="docx",
        source_name=STORED_DOCX,
        source_bytes=data,
        preview_html=preview,
    )


def _clear_folder(folder: Path) -> None:
    if not folder.exists():
        return
    for child in folder.iterdir():
        if child.is_file():
            child.unlink()
        elif child.is_dir():
            shutil.rmtree(child, ignore_errors=True)


def write_upload(folder: Path, prepared: PreparedUpload) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    _clear_folder(folder)
    (folder / prepared.source_name).write_bytes(prepared.source_bytes)
    if prepared.preview_html is not None:
        (folder / STORED_PREVIEW).write_text(prepared.preview_html, encoding="utf-8")


def resolve_slug(label: str, requested: str = "") -> str:
    slug = slugify(requested) or slugify(label)
    if not slug:
        raise ValueError("The path needs at least one letter or number.")
    if slug in RESERVED_SLUGS:
        raise ValueError("That URL is reserved by FileServe. Choose a different path.")
    return slug


def _slug_taken(db: Session, owner: User, slug: str, *, ignore_id: int | None = None) -> bool:
    query = db.query(Page).filter(Page.user_id == owner.id, Page.slug == slug)
    if ignore_id is not None:
        query = query.filter(Page.id != ignore_id)
    if query.one_or_none() is not None:
        return True
    folder = page_dir_for(owner, slug)
    if ignore_id is not None:
        current = db.get(Page, ignore_id)
        if current is not None and current.user_id == owner.id and current.slug == slug:
            return False
    return folder.exists()


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
        page.auth_password_hash = passwords.hash_password(password)
    elif not keep_password or not page.auth_password_hash:
        raise ValueError("Enter a password for this page.")
    page.auth_username = clean_user


def _relocate(owner: User, old_slug: str, new_slug: str) -> None:
    if old_slug == new_slug:
        return
    source = page_dir_for(owner, old_slug)
    dest = page_dir_for(owner, new_slug)
    if dest.exists():
        raise ValueError("That URL is already in use.")
    if source.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        source.rename(dest)


def create_page(
    db: Session,
    title: str,
    upload: FileStorage,
    *,
    owner: User,
    slug: str = "",
    protect: bool = False,
    username: str = "",
    password: str = "",
    expires_at: datetime | None = None,
    description: str = "",
) -> Page:
    clean_title = (title or "").strip()
    if not clean_title:
        raise ValueError("Enter a label.")
    clean_description = _clean_description(description)
    prepared = prepare_upload(upload, clean_title)
    clean_slug = resolve_slug(clean_title, slug)
    if _slug_taken(db, owner, clean_slug):
        raise ValueError("That URL is already in use.")
    folder = page_dir_for(owner, clean_slug)
    write_upload(folder, prepared)
    page = Page(
        title=clean_title,
        slug=clean_slug,
        filename=prepared.filename,
        page_type=prepared.page_type,
        description=clean_description,
        expires_at=expires_at,
        enabled=True,
        user_id=owner.id,
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
    viewer: User,
    title: str,
    slug: str = "",
    protect: bool = False,
    username: str = "",
    password: str = "",
    expires_at: datetime | None = None,
    description: str = "",
    upload: FileStorage | None = None,
) -> Page:
    page = db.get(Page, page_id)
    if page is None:
        raise ValueError("That page is already gone.")
    if not can_manage(viewer, page):
        raise ValueError("You cannot edit that page.")
    owner = page.owner
    if owner is None:
        raise ValueError("That page has no owner.")
    clean_title = (title or "").strip()
    if not clean_title:
        raise ValueError("Enter a label.")
    clean_description = _clean_description(description)
    clean_slug = resolve_slug(clean_title, slug)
    if _slug_taken(db, owner, clean_slug, ignore_id=page.id):
        raise ValueError("That URL is already in use.")
    prepared = None
    if upload is not None and _original_name(upload):
        prepared = prepare_upload(upload, clean_title)
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
        page.description = clean_description
        page.expires_at = expires_at
        if clean_slug != old_slug:
            _relocate(owner, old_slug, clean_slug)
            relocated = True
            page.slug = clean_slug
        if prepared is not None:
            write_upload(page_dir(page), prepared)
            page.filename = prepared.filename
            page.page_type = prepared.page_type
        db.commit()
        db.refresh(page)
    except Exception:
        db.rollback()
        if relocated:
            try:
                _relocate(owner, clean_slug, old_slug)
            except ValueError:
                pass
        raise
    return page


def record_open(db: Session, page: Page) -> None:
    page.open_count = int(page.open_count or 0) + 1
    page.last_opened_at = utcnow()
    db.commit()


def toggle_page(db: Session, page_id: int, *, viewer: User) -> Page:
    page = db.get(Page, page_id)
    if page is None:
        raise ValueError("That page is already gone.")
    if not can_manage(viewer, page):
        raise ValueError("You cannot change that page.")
    page.enabled = not bool(page.enabled)
    db.commit()
    db.refresh(page)
    return page


def delete_page(db: Session, page_id: int, *, viewer: User) -> Page:
    page = db.get(Page, page_id)
    if page is None:
        raise ValueError("That page is already gone.")
    if not can_manage(viewer, page):
        raise ValueError("You cannot delete that page.")
    folder = page_dir(page)
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
        folder = page_dir(page)
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
