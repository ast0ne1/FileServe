import re
import shutil
import unicodedata
from pathlib import Path

from sqlalchemy.orm import Session
from werkzeug.datastructures import FileStorage

from app.config import HOSTED_DIR
from app.models import Page

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


def slugify(title: str) -> str:
    text = unicodedata.normalize("NFKD", title or "").encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = SLUG_RE.sub("-", text).strip("-")
    return text


def page_dir(slug: str) -> Path:
    HOSTED_DIR.mkdir(parents=True, exist_ok=True)
    return HOSTED_DIR / slug


def get_by_slug(db: Session, slug: str) -> Page | None:
    return db.query(Page).filter(Page.slug == slug).one_or_none()


def list_pages(db: Session) -> list[Page]:
    return db.query(Page).order_by(Page.created_at.desc()).all()


def create_page(db: Session, title: str, upload: FileStorage) -> Page:
    clean_title = (title or "").strip()
    if not clean_title:
        raise ValueError("Enter a title.")
    filename = (upload.filename or "").strip()
    if not filename:
        raise ValueError("Choose an HTML file.")
    suffix = Path(filename).suffix.lower()
    if suffix != ".html":
        raise ValueError("Only .html files can be hosted.")
    slug = slugify(clean_title)
    if not slug:
        raise ValueError("The title needs at least one letter or number for a URL.")
    if slug in RESERVED_SLUGS:
        raise ValueError("That URL is reserved by FileServe. Choose a different title.")
    if get_by_slug(db, slug):
        raise ValueError("That URL is already in use.")
    folder = page_dir(slug)
    if folder.exists():
        raise ValueError("That URL is already in use.")
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / "index.html"
    upload.save(dest)
    page = Page(title=clean_title, slug=slug, filename=filename, page_type="html")
    db.add(page)
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
