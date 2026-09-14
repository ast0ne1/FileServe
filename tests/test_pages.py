from base64 import b64encode
from datetime import datetime, timedelta, timezone
from io import BytesIO

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
    monkeypatch.setattr("app.services.pages.HOSTED_DIR", hosted)
    monkeypatch.setattr("app.services.backup.HOSTED_DIR", hosted)
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
    assert "Use your FileServe admin username and password." in html
    assert "admin / admin" in html
    assert "login-shell" in html
    assert "login-card" in html


def test_add_page_uses_full_width_file_picker(client):
    _login(client)
    html = client.get("/admin/add").get_data(as_text=True)
    assert "Tap to choose an HTML file" in html
    assert "file-picker-drop" in html
    assert "Choose File" not in html
    assert "Label" in html
    assert "Require a password" in html
    assert "data-slug-field" in html
    assert "Keep until" in html
    assert "Removed manually" in html
    assert "Custom date" in html


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
