from io import BytesIO

import pytest

from app.main import create_app
from app.services.pages import slugify


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


def test_login_screen_looks_like_newscast(client):
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
    assert b"Travel Planner" in listed.data
    deleted = client.post(
        "/admin/delete/1",
        headers={"Accept": "application/json", "X-Requested-With": "fetch"},
    )
    assert deleted.status_code == 200
    assert client.get("/travel-planner").status_code == 404
