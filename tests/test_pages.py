from base64 import b64encode
from datetime import datetime, timedelta, timezone
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from app import db as database
from app.main import create_app
from app.models import Page
from app.services.pages import resolve_expiry, slugify


def test_slugify_hyphenates_title():
    assert slugify("Emergency Planner") == "emergency-planner"
    assert slugify("My Travel Checklist") == "my-travel-checklist"
    assert slugify("  Hello---World  ") == "hello-world"


@pytest.fixture
def client(tmp_path, monkeypatch):
    hosted = tmp_path / "hosted"
    hosted.mkdir()
    tls = tmp_path / "tls"
    tls.mkdir()
    monkeypatch.setattr("app.services.pages.HOSTED_DIR", hosted)
    monkeypatch.setattr("app.services.backup.HOSTED_DIR", hosted)
    monkeypatch.setattr("app.services.users.HOSTED_DIR", hosted)
    monkeypatch.setattr("app.services.tls.TLS_DIR", tls)
    monkeypatch.setattr("app.services.backup.TLS_DIR", tls)
    flask_app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test",
            "DATABASE_URL": f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        }
    )
    return flask_app.test_client()


def _login(client):
    return client.post("/login", data={"username": "admin", "password": "admin"}, follow_redirects=True)


def test_login_screen_shows_sign_in(client):
    response = client.get("/login")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Sign in" in html
    assert "Use your FileServe username and password." in html
    assert "admin / admin" in html
    assert "login-shell" in html
    assert "login-card" in html


def test_add_page_uses_full_width_file_picker(client):
    _login(client)
    html = client.get("/admin/add").get_data(as_text=True)
    assert "Tap to choose a file" in html
    assert "file-picker-drop" in html
    assert "Choose File" not in html
    assert "Label" in html
    assert "Short description" in html
    assert "Require a password" in html
    assert "data-slug-field" in html
    assert "Keep until" in html
    assert "Removed manually" in html
    assert "Custom date" in html
    assert ".zip" in html


def test_admin_requires_login(client):
    response = client.get("/admin", follow_redirects=False)
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_upload_serves_public_html_and_rejects_duplicate(client):
    _login(client)
    html = b"<html><body>Planner</body></html>"
    created = client.post(
        "/admin/add",
        data={"title": "Emergency Planner", "file": (BytesIO(html), "ignored-name.html")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert created.status_code == 200
    public = client.get("/emergency-planner")
    assert public.status_code == 200
    assert public.data == html

    duplicate = client.post(
        "/admin/add",
        data={"title": "Emergency Planner", "file": (BytesIO(html), "other.html")},
        content_type="multipart/form-data",
        headers={"Accept": "application/json", "X-Requested-With": "fetch"},
    )
    assert duplicate.status_code == 400
    assert b"already in use" in duplicate.data


def test_delete_removes_page(client):
    _login(client)
    client.post(
        "/admin/add",
        data={"title": "Travel Planner", "file": (BytesIO(b"<html></html>"), "a.html")},
        content_type="multipart/form-data",
    )
    listed = client.get("/admin")
    html = listed.get_data(as_text=True)
    assert "Travel Planner" in html
    assert "qr-frame" in html
    assert "qr-image" in html
    assert "data:image/png" in html
    assert "Scan to open this page" in html
    assert "/travel-planner" in html
    assert "<svg" in html
    assert "data-edit-page" in html
    deleted = client.post(
        "/admin/delete/1",
        headers={"Accept": "application/json", "X-Requested-With": "fetch"},
    )
    assert deleted.status_code == 200
    assert client.get("/travel-planner").status_code == 404


def _basic(user, password):
    token = b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def test_custom_path_and_page_password(client):
    _login(client)
    html = b"<html><body>Kit</body></html>"
    created = client.post(
        "/admin/add",
        data={
            "label": "Home Kit",
            "slug": "family-kit",
            "protect": "1",
            "page_username": "kit",
            "page_password": "secret1",
            "file": (BytesIO(html), "kit.html"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert created.status_code == 200
    listed = created.get_data(as_text=True)
    assert "Protected" in listed
    assert "/family-kit" in listed
    as_admin = client.get("/family-kit")
    assert as_admin.status_code == 200
    assert as_admin.data == html

    client.post("/logout")
    locked = client.get("/family-kit")
    assert locked.status_code == 401
    assert "Basic" in locked.headers.get("WWW-Authenticate", "")
    wrong = client.get("/family-kit", headers=_basic("kit", "nope"))
    assert wrong.status_code == 401
    opened = client.get("/family-kit", headers=_basic("kit", "secret1"))
    assert opened.status_code == 200
    assert opened.data == html


def test_edit_page_updates_label_path_and_clears_password(client):
    _login(client)
    client.post(
        "/admin/add",
        data={
            "label": "Old Label",
            "slug": "old-path",
            "protect": "1",
            "page_username": "guest",
            "page_password": "secret1",
            "file": (BytesIO(b"<html>ok</html>"), "a.html"),
        },
        content_type="multipart/form-data",
    )
    updated = client.post(
        "/admin/edit/1",
        data={"label": "New Label", "slug": "new-path"},
        headers={"Accept": "application/json", "X-Requested-With": "fetch"},
    )
    assert updated.status_code == 200
    listed = client.get("/admin").get_data(as_text=True)
    assert "New Label" in listed
    assert "/new-path" in listed
    assert "Protected" not in listed
    assert client.get("/old-path").status_code == 404
    client.post("/logout")
    public = client.get("/new-path")
    assert public.status_code == 200
    assert public.data == b"<html>ok</html>"


def test_resolve_expiry_presets():
    now = datetime(2026, 1, 31, 12, 0, tzinfo=timezone.utc)
    assert resolve_expiry("none", now=now) is None
    assert resolve_expiry("week", now=now) == now + timedelta(days=7)
    assert resolve_expiry("month", now=now) == datetime(2026, 2, 28, 12, 0, tzinfo=timezone.utc)
    custom = resolve_expiry("custom", "2026-03-15", now=now)
    assert custom == datetime(2026, 3, 15, 23, 59, 59, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="future"):
        resolve_expiry("custom", "2020-01-01", now=now)


def test_page_expiry_and_purge(client):
    _login(client)
    created = client.post(
        "/admin/add",
        data={
            "label": "Temp Note",
            "slug": "temp-note",
            "expiry": "week",
            "file": (BytesIO(b"<html>n</html>"), "a.html"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    html = created.get_data(as_text=True)
    assert "Until" in html
    assert "temp-note" in html

    db = database.SessionLocal()
    try:
        page = db.query(Page).one()
        page.expires_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
        db.commit()
    finally:
        db.close()

    listed = client.get("/admin").get_data(as_text=True)
    assert "Temp Note" not in listed
    assert client.get("/temp-note").status_code == 404


def test_disable_hides_page_without_deleting(client):
    _login(client)
    html = b"<html><body>Stay</body></html>"
    client.post(
        "/admin/add",
        data={"label": "Stay Put", "slug": "stay-put", "file": (BytesIO(html), "a.html")},
        content_type="multipart/form-data",
    )
    listed = client.get("/admin").get_data(as_text=True)
    assert "toggle" in listed
    assert "Enabled" in listed
    off = client.post(
        "/admin/toggle/1",
        headers={"Accept": "application/json", "X-Requested-With": "fetch"},
    )
    assert off.status_code == 200
    assert b"Disabled Stay Put" in off.data
    dimmed = client.get("/admin").get_data(as_text=True)
    assert "is-off" in dimmed
    assert "Stay Put" in dimmed
    preview = client.get("/stay-put")
    assert preview.status_code == 200
    assert preview.data == html
    client.post("/logout")
    assert client.get("/stay-put").status_code == 404
    _login(client)
    on = client.post(
        "/admin/toggle/1",
        headers={"Accept": "application/json", "X-Requested-With": "fetch"},
    )
    assert on.status_code == 200
    client.post("/logout")
    public = client.get("/stay-put")
    assert public.status_code == 200
    assert public.data == html


MINIMAL_PDF = b"%PDF-1.1\n1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\ntrailer<< /Root 1 0 R >>\n%%EOF\n"


def _docx_bytes(text: str) -> bytes:
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/>'
        "</Relationships>"
    )
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("word/document.xml", document_xml)
    return buffer.getvalue()


def test_replace_file_keeps_slug_and_password(client):
    _login(client)
    first = b"<html><body>One</body></html>"
    second = b"<html><body>Two</body></html>"
    client.post(
        "/admin/add",
        data={
            "label": "Keep Path",
            "slug": "keep-path",
            "protect": "1",
            "page_username": "kit",
            "page_password": "secret1",
            "file": (BytesIO(first), "one.html"),
        },
        content_type="multipart/form-data",
    )
    updated = client.post(
        "/admin/edit/1",
        data={
            "label": "Keep Path",
            "slug": "keep-path",
            "protect": "1",
            "page_username": "kit",
            "file": (BytesIO(second), "two.html"),
        },
        content_type="multipart/form-data",
        headers={"Accept": "application/json", "X-Requested-With": "fetch"},
    )
    assert updated.status_code == 200
    client.post("/logout")
    locked = client.get("/keep-path")
    assert locked.status_code == 401
    opened = client.get("/keep-path", headers=_basic("kit", "secret1"))
    assert opened.status_code == 200
    assert opened.data == second


def test_pdf_and_docx_hosting_and_rejected_types(client):
    _login(client)
    pdf = client.post(
        "/admin/add",
        data={"label": "Guide", "slug": "guide", "file": (BytesIO(MINIMAL_PDF), "guide.pdf")},
        content_type="multipart/form-data",
        headers={"Accept": "application/json", "X-Requested-With": "fetch"},
    )
    assert pdf.status_code == 200
    public_pdf = client.get("/guide")
    assert public_pdf.status_code == 200
    assert public_pdf.mimetype == "application/pdf"
    assert "inline" in (public_pdf.headers.get("Content-Disposition") or "").lower()
    assert public_pdf.data == MINIMAL_PDF

    docx = _docx_bytes("Readable paragraph")
    word = client.post(
        "/admin/add",
        data={"label": "Notes", "slug": "notes", "file": (BytesIO(docx), "notes.docx")},
        content_type="multipart/form-data",
        headers={"Accept": "application/json", "X-Requested-With": "fetch"},
    )
    assert word.status_code == 200
    public_word = client.get("/notes")
    assert public_word.status_code == 200
    assert "html" in public_word.mimetype
    assert "Readable paragraph" in public_word.get_data(as_text=True)
    downloaded = client.get("/admin/download/2")
    assert downloaded.status_code == 200
    assert downloaded.data == docx
    assert "notes.docx" in (downloaded.headers.get("Content-Disposition") or "")

    rejected_zip = client.post(
        "/admin/add",
        data={"label": "Bundle", "file": (BytesIO(b"PK\x03\x04not-a-zip"), "site.zip")},
        content_type="multipart/form-data",
        headers={"Accept": "application/json", "X-Requested-With": "fetch"},
    )
    assert rejected_zip.status_code == 400
    rejected_doc = client.post(
        "/admin/add",
        data={"label": "Old Word", "file": (BytesIO(b"DOC"), "old.doc")},
        content_type="multipart/form-data",
        headers={"Accept": "application/json", "X-Requested-With": "fetch"},
    )
    assert rejected_doc.status_code == 400


def _site_zip_bytes(*, nested_root: str | None = None) -> bytes:
    buffer = BytesIO()
    prefix = f"{nested_root}/" if nested_root else ""
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr(f"{prefix}index.html", b"<html><body><script src='js/app.js'></script></body></html>")
        archive.writestr(f"{prefix}js/app.js", b"window.__fileserve=1;")
        archive.writestr(f"{prefix}assets/note.txt", b"hello")
    buffer.seek(0)
    return buffer.read()


def test_zip_site_serves_assets_as_one_page_and_deletes_folder(client):
    from app.services import pages as pages_svc

    _login(client)
    created = client.post(
        "/admin/add",
        data={
            "label": "Mini Game",
            "slug": "mini-game",
            "file": (BytesIO(_site_zip_bytes(nested_root="GameFolder")), "mini-game.zip"),
        },
        content_type="multipart/form-data",
        headers={"Accept": "application/json", "X-Requested-With": "fetch"},
    )
    assert created.status_code == 200
    listed = client.get("/admin").get_data(as_text=True)
    assert "Mini Game" in listed
    assert "Site" in listed
    assert listed.count("data-page-card") == 1

    bare = client.get("/mini-game", follow_redirects=False)
    assert bare.status_code == 302
    assert bare.headers["Location"].endswith("/mini-game/")

    index = client.get("/mini-game/")
    assert index.status_code == 200
    assert b"js/app.js" in index.data
    script = client.get("/mini-game/js/app.js")
    assert script.status_code == 200
    assert script.data == b"window.__fileserve=1;"
    note = client.get("/mini-game/assets/note.txt")
    assert note.status_code == 200
    assert note.data == b"hello"

    after_assets = client.get("/admin").get_data(as_text=True)
    assert "Opened 1 time" in after_assets

    downloaded = client.get("/admin/download/1")
    assert downloaded.status_code == 200
    assert downloaded.mimetype == "application/zip"
    with ZipFile(BytesIO(downloaded.data)) as archive:
        names = set(archive.namelist())
    assert "index.html" in names
    assert "js/app.js" in names

    site_dir = pages_svc.HOSTED_DIR / "mini-game"
    assert site_dir.is_dir()
    removed = client.post("/admin/delete/1", headers={"Accept": "application/json", "X-Requested-With": "fetch"})
    assert removed.status_code == 200
    assert not site_dir.exists()
    assert client.get("/mini-game/").status_code == 404
    assert "data-page-card" not in client.get("/admin").get_data(as_text=True)


def test_description_browse_and_open_count(client):
    _login(client)
    created = client.post(
        "/admin/add",
        data={
            "label": "Family Kit",
            "slug": "family-kit",
            "description": "Kitchen folder",
            "file": (BytesIO(b"<html>kit</html>"), "a.html"),
        },
        content_type="multipart/form-data",
        headers={"Accept": "application/json", "X-Requested-With": "fetch"},
    )
    assert created.status_code == 200
    listed = client.get("/admin").get_data(as_text=True)
    assert "Kitchen folder" in listed
    assert "data-page-search" in listed
    assert "Copy URL" in listed
    assert "Download QR" in listed
    assert "Print QR" in listed
    assert "title=\"Copy URL\"" in listed
    assert "title=\"Download file\"" in listed
    assert "title=\"Download QR\"" in listed
    assert "title=\"Print QR\"" in listed
    db = database.SessionLocal()
    try:
        page = db.query(Page).one()
        assert page.open_count == 0
        assert page.description == "Kitchen folder"
    finally:
        db.close()
    browse = client.get("/browse")
    assert browse.status_code == 200
    browse_html = browse.get_data(as_text=True)
    assert "Family Kit" in browse_html
    assert "Kitchen folder" in browse_html
    db = database.SessionLocal()
    try:
        assert db.query(Page).one().open_count == 0
    finally:
        db.close()
    assert client.get("/family-kit").status_code == 200
    assert client.get("/family-kit").status_code == 200
    db = database.SessionLocal()
    try:
        page = db.query(Page).one()
        assert page.open_count == 2
        assert page.last_opened_at is not None
    finally:
        db.close()
    downloaded = client.get("/admin/download/1")
    assert downloaded.status_code == 200
    assert downloaded.data == b"<html>kit</html>"
    db = database.SessionLocal()
    try:
        assert db.query(Page).one().open_count == 2
    finally:
        db.close()
    client.post("/admin/toggle/1", headers={"Accept": "application/json", "X-Requested-With": "fetch"})
    client.post("/logout")
    hidden = client.get("/browse").get_data(as_text=True)
    assert "Family Kit" not in hidden


def test_password_reveal_is_once_only(client):
    _login(client)
    created = client.post(
        "/admin/add",
        data={
            "label": "Secret Note",
            "slug": "secret-note",
            "protect": "1",
            "page_username": "guest",
            "page_password": "secret1",
            "file": (BytesIO(b"<html>s</html>"), "a.html"),
        },
        content_type="multipart/form-data",
        headers={"Accept": "application/json", "X-Requested-With": "fetch"},
    )
    assert created.status_code == 200
    payload = created.get_json()
    assert payload["reveal"]["username"] == "guest"
    assert payload["reveal"]["password"] == "secret1"
    first = client.get("/admin").get_data(as_text=True)
    assert "Save this password" in first
    assert "secret1" in first
    second = client.get("/admin").get_data(as_text=True)
    assert "Save this password" not in second
    assert "secret1" not in second


def test_qr_download_and_print_require_login(client):
    _login(client)
    client.post(
        "/admin/add",
        data={"label": "Poster", "slug": "poster", "file": (BytesIO(b"<html>p</html>"), "a.html")},
        content_type="multipart/form-data",
    )
    png = client.get("/admin/qr/1.png")
    assert png.status_code == 200
    assert png.mimetype == "image/png"
    assert png.data[:8] == b"\x89PNG\r\n\x1a\n"
    printed = client.get("/admin/qr/1/print")
    assert printed.status_code == 200
    assert "Print QR" in printed.get_data(as_text=True)
    client.post("/logout")
    assert client.get("/admin/qr/1.png", follow_redirects=False).status_code == 302
    assert client.get("/admin/download/1", follow_redirects=False).status_code == 302


def _login_as(client, username: str, password: str):
    client.post("/logout")
    return client.post("/login", data={"username": username, "password": password}, follow_redirects=True)


def test_household_user_pages_use_user_path_and_own_scope(client):
    _login(client)
    created = client.post(
        "/admin/settings/users",
        data={"username": "alex", "password": "alexpass"},
        headers={"Accept": "application/json", "X-Requested-With": "fetch"},
    )
    assert created.status_code == 200
    assert created.get_json()["ok"] is True

    admin_page = client.post(
        "/admin/add",
        data={"label": "Admin Note", "slug": "shared-slug", "file": (BytesIO(b"<html>admin</html>"), "a.html")},
        content_type="multipart/form-data",
        headers={"Accept": "application/json", "X-Requested-With": "fetch"},
    )
    assert admin_page.status_code == 200

    _login_as(client, "alex", "alexpass")
    user_page = client.post(
        "/admin/add",
        data={"label": "Alex Note", "slug": "shared-slug", "file": (BytesIO(b"<html>alex</html>"), "a.html")},
        content_type="multipart/form-data",
        headers={"Accept": "application/json", "X-Requested-With": "fetch"},
    )
    assert user_page.status_code == 200

    admin_public = client.get("/shared-slug")
    assert admin_public.status_code == 200
    assert admin_public.data == b"<html>admin</html>"

    user_public = client.get("/u/alex/shared-slug")
    assert user_public.status_code == 200
    assert user_public.data == b"<html>alex</html>"

    pages_html = client.get("/admin").get_data(as_text=True)
    assert "/u/alex/shared-slug" in pages_html
    assert "Admin Note" not in pages_html

    settings_html = client.get("/admin/settings").get_data(as_text=True)
    assert 'data-settings-tab="users"' not in settings_html
    assert "Use HTTPS" not in settings_html
    assert "Backup/Restore" not in settings_html

    _login_as(client, "admin", "admin")
    admin_pages = client.get("/admin").get_data(as_text=True)
    assert "Alex Note" in admin_pages
    assert "alex" in admin_pages
    filtered = client.get("/admin?user=alex").get_data(as_text=True)
    assert "Alex Note" in filtered
    assert "Admin Note" not in filtered
    users_tab = client.get("/admin/settings?tab=users").get_data(as_text=True)
    assert "Create user" in users_tab
    assert "alex" in users_tab


def test_non_admin_cannot_manage_other_pages(client):
    _login(client)
    client.post("/admin/settings/users", data={"username": "blake", "password": "blakepass"})
    client.post(
        "/admin/add",
        data={"label": "Admin Only", "slug": "admin-only", "file": (BytesIO(b"<html>a</html>"), "a.html")},
        content_type="multipart/form-data",
    )
    _login_as(client, "blake", "blakepass")
    denied = client.post("/admin/delete/1", headers={"Accept": "application/json", "X-Requested-With": "fetch"})
    assert denied.status_code == 400
    assert b"cannot delete" in denied.data
