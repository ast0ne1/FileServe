from __future__ import annotations

import logging
from datetime import timedelta
from functools import wraps
from io import BytesIO

from flask import (
    Flask,
    Response,
    abort,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    send_from_directory,
    url_for,
)
from werkzeug.security import generate_password_hash

from app import __author__, __version__
from app.auth import (
    attach_session,
    clear_session,
    credentials_match,
    is_signed_in,
    login_redirect,
    safe_next,
    session_secret,
    wants_json,
)
from app.config import BACKUPS_DIR, DATA_DIR, HOSTED_DIR, UPDATES_DIR, env
from app.db import init_db
from app import db as database
from app.services import backup, hostname, pages as pages_svc, qrcode, settings, update

logging.basicConfig(level=logging.INFO)

SETTINGS_TABS = (
    ("device", "Device"),
    ("backup", "Backup/Restore"),
    ("update", "Update"),
    ("about", "About"),
)
SETTINGS_LEDES = {
    "device": "Appearance, admin login, hostname, and instance name.",
    "backup": "Download or restore a zip of your pages and settings. Roll back the last app install here.",
    "update": "Check GitHub Releases and install a newer zip.",
    "about": "What FileServe is and which version this copy is running.",
}
SETTINGS_SAVE_TABS = {"device", "update"}
TAB_KEYS = {key for key, _label in SETTINGS_TABS}


def normalize_settings_tab(value: str | None) -> str:
    tab = (value or "device").strip().lower()
    return tab if tab in TAB_KEYS else "device"


def settings_path(tab: str = "device") -> str:
    return url_for("settings_page", tab=normalize_settings_tab(tab))


def create_app(config: dict | None = None) -> Flask:
    extra = config or {}
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    HOSTED_DIR.mkdir(parents=True, exist_ok=True)
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    UPDATES_DIR.mkdir(parents=True, exist_ok=True)
    init_db(extra.get("DATABASE_URL"))

    app = Flask(__name__)
    app.config["SECRET_KEY"] = extra.get("SECRET_KEY") or session_secret()
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=14)
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
    if extra.get("TESTING"):
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False

    @app.before_request
    def _open_db():
        if database.SessionLocal is None:
            init_db()
        g.db = database.SessionLocal()
        pages_svc.purge_expired(g.db)

    @app.teardown_request
    def _close_db(_exc):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    @app.context_processor
    def _inject():
        db = getattr(g, "db", None)
        page_count = 0
        factory = False
        home = "FileServe"
        if db is not None:
            page_count = len(pages_svc.list_pages(db))
            factory = settings.using_factory_admin(db)
            home = hostname.homescreen_name(db)
        return {
            "app_version": __version__,
            "app_author": __author__,
            "app_port": env.port,
            "using_factory_admin": factory,
            "homescreen_name": home,
            "page_count": page_count,
            "settings_tabs": SETTINGS_TABS,
            "settings_ledes": SETTINGS_LEDES,
            "settings_save_tabs": SETTINGS_SAVE_TABS,
        }

    def login_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if is_signed_in():
                return view(*args, **kwargs)
            if wants_json():
                return jsonify({"ok": False, "message": "Not signed in"}), 401
            return login_redirect()

        return wrapped

    def json_or_redirect(message: str, location: str, *, error: bool = False, status: int = 200, **extra):
        if wants_json():
            payload = {"ok": not error, "message": message, **extra}
            return jsonify(payload), (400 if error else status)
        if error:
            flash(message, "error")
        else:
            flash(message, "ok")
        return redirect(location)

    @app.get("/")
    def home():
        if is_signed_in():
            return redirect(url_for("pages_list"))
        return redirect(url_for("login"))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        nxt = safe_next(request.values.get("next"))
        if is_signed_in() and request.method == "GET":
            return redirect(nxt)
        error = None
        username = request.form.get("username", "")
        if request.method == "POST":
            username = (request.form.get("username") or "").strip()
            password = request.form.get("password") or ""
            if credentials_match(g.db, username, password):
                attach_session(username)
                if wants_json():
                    return jsonify({"ok": True, "message": "Signed in."})
                return redirect(nxt)
            error = "Username or password is incorrect."
            if wants_json():
                return jsonify({"ok": False, "message": error}), 400
        return render_template("login.html", error=error, username=username, next=nxt)

    @app.post("/logout")
    def logout():
        clear_session()
        if wants_json():
            return jsonify({"ok": True, "message": "Signed out.", "reauth": True})
        return redirect(url_for("login"))

    def _page_form():
        label = (request.form.get("label") or request.form.get("title") or "").strip()
        slug = (request.form.get("slug") or "").strip()
        protect = request.form.get("protect") == "1"
        username = (request.form.get("page_username") or "").strip()
        password = request.form.get("page_password") or ""
        expiry_mode = (request.form.get("expiry") or "none").strip().lower()
        expiry_date = (request.form.get("expiry_date") or "").strip()
        return label, slug, protect, username, password, expiry_mode, expiry_date

    def _page_unauthorized():
        return Response("Authentication required.\n", 401, {"WWW-Authenticate": 'Basic realm="FileServe page"'})

    @app.get("/admin")
    @login_required
    def pages_list():
        share_url = hostname.get_share_url(g.db)
        items = [
            {
                "page": page,
                "url": qrcode.page_url(share_url, page.slug),
                "qr_png": qrcode.png_data_uri(qrcode.page_url(share_url, page.slug)),
            }
            for page in pages_svc.list_pages(g.db)
        ]
        return render_template("pages.html", pages=items, active="pages", share_url=share_url)

    @app.route("/admin/add", methods=["GET", "POST"])
    @login_required
    def add_page():
        error = None
        label = request.form.get("label") or request.form.get("title") or ""
        slug = request.form.get("slug") or ""
        protect = request.form.get("protect") == "1"
        page_username = request.form.get("page_username") or ""
        expiry_mode = (request.form.get("expiry") or "none").strip().lower()
        expiry_date = (request.form.get("expiry_date") or "").strip()
        if request.method == "POST":
            label, slug, protect, page_username, password, expiry_mode, expiry_date = _page_form()
            upload = request.files.get("file")
            try:
                if upload is None:
                    raise ValueError("Choose an HTML file.")
                page = pages_svc.create_page(
                    g.db,
                    label,
                    upload,
                    slug=slug,
                    protect=protect,
                    username=page_username,
                    password=password,
                    expires_at=pages_svc.resolve_expiry(expiry_mode, expiry_date),
                )
                return json_or_redirect(f"Hosted {page.title}.", url_for("pages_list"))
            except ValueError as exc:
                error = str(exc)
                if wants_json():
                    return jsonify({"ok": False, "message": error}), 400
        return render_template(
            "add.html",
            active="add",
            error=error,
            label=label,
            slug=slug,
            protected=protect,
            page_username=page_username,
            expiry_mode=expiry_mode,
            expiry_date=expiry_date,
        )

    @app.post("/admin/edit/<int:page_id>")
    @login_required
    def edit_page(page_id: int):
        label, slug, protect, page_username, password, expiry_mode, expiry_date = _page_form()
        try:
            page = pages_svc.update_page(
                g.db,
                page_id,
                title=label,
                slug=slug,
                protect=protect,
                username=page_username,
                password=password,
                expires_at=pages_svc.resolve_expiry(expiry_mode, expiry_date),
            )
        except ValueError as exc:
            return json_or_redirect(str(exc), url_for("pages_list"), error=True)
        return json_or_redirect(f"Updated {page.title}.", url_for("pages_list"))

    @app.post("/admin/delete/<int:page_id>")
    @login_required
    def delete_page(page_id: int):
        try:
            page = pages_svc.delete_page(g.db, page_id)
        except ValueError as exc:
            return json_or_redirect(str(exc), url_for("pages_list"), error=True)
        return json_or_redirect(f"Removed {page.title}.", url_for("pages_list"))

    @app.get("/admin/settings")
    @login_required
    def settings_page():
        tab = normalize_settings_tab(request.args.get("tab"))
        latest = backup.latest_backup()
        return render_template(
            "settings.html",
            active="settings",
            settings_tab=tab,
            settings_lede=SETTINGS_LEDES[tab],
            admin_username=settings.get_value(g.db, "admin_username"),
            instance_name=settings.get_value(g.db, "instance_name"),
            device_hostname=settings.get_value(g.db, "device_hostname"),
            github_repo=update.repo_from_db(g.db),
            update_check=update.last_check(g.db),
            latest_backup=latest,
            share_url=hostname.get_share_url(g.db),
        )

    @app.post("/admin/settings")
    @login_required
    def save_settings():
        tab = normalize_settings_tab(request.form.get("settings_tab"))
        reauth = False
        current_user, current_pass = settings.get_admin_credentials(g.db)
        admin_username = (request.form.get("admin_username") or "").strip()
        current_password = request.form.get("current_password") or ""
        new_password = request.form.get("new_password") or ""
        new_password_confirm = request.form.get("new_password_confirm") or ""
        changing_password = bool(new_password.strip())
        changing_username = bool(admin_username) and admin_username != current_user

        def fail(message: str):
            if wants_json():
                return jsonify({"ok": False, "message": message}), 400
            flash(message, "error")
            return redirect(settings_path(tab))

        if changing_password or changing_username:
            from app.auth import password_matches

            if not password_matches(current_pass, current_password):
                return fail("Current password is incorrect.")
            if changing_password:
                if new_password != new_password_confirm:
                    return fail("New passwords do not match.")
                if len(new_password) < 4:
                    return fail("New password must be at least 4 characters.")
                settings.set_value(g.db, "admin_password", generate_password_hash(new_password))
                reauth = True
            if changing_username:
                settings.set_value(g.db, "admin_username", admin_username)
                reauth = True

        instance_name = (request.form.get("instance_name") or "").strip()
        if instance_name:
            settings.set_value(g.db, "instance_name", instance_name[:80])
        else:
            settings.clear_value(g.db, "instance_name")

        wanted_host = hostname.normalize_hostname(request.form.get("device_hostname") or "")
        if wanted_host:
            if not hostname.valid_hostname(wanted_host):
                return fail("Hostname must be letters, digits, or hyphens.")
            settings.set_value(g.db, "device_hostname", wanted_host)
            hostname.apply_os_hostname(wanted_host)
        else:
            settings.clear_value(g.db, "device_hostname")

        github_repo = request.form.get("github_repo") or ""
        repo = update.normalize_repo(github_repo)
        if github_repo.strip() and not repo:
            return fail("GitHub repository must look like owner/FileServe.")
        if repo:
            settings.set_value(g.db, "github_repo", repo)
        else:
            settings.clear_value(g.db, "github_repo")

        extra = {"reauth": reauth}
        if wants_json():
            if reauth:
                clear_session()
            return jsonify({"ok": True, "message": "Settings saved.", **extra})
        response = redirect(url_for("login") if reauth else settings_path(tab))
        if reauth:
            clear_session()
        else:
            flash("Settings saved.", "ok")
        return response

    @app.get("/admin/settings/backup")
    @login_required
    def download_backup():
        buffer = BytesIO(backup.backup_bytes())
        buffer.seek(0)
        return send_file(
            buffer,
            as_attachment=True,
            download_name="fileserve-backup.zip",
            mimetype="application/zip",
        )

    @app.post("/admin/settings/backup/restore")
    @login_required
    def restore_backup():
        upload = request.files.get("file")
        if upload is None or not upload.filename:
            return json_or_redirect("Choose a backup zip.", settings_path("backup"), error=True)
        try:
            backup.restore_backup(upload.read())
        except ValueError as exc:
            return json_or_redirect(str(exc), settings_path("backup"), error=True)
        except Exception as exc:  # noqa: BLE001
            logging.getLogger("fileserve").exception("restore failed")
            return json_or_redirect(f"Could not restore the backup: {exc}", settings_path("backup"), error=True)
        clear_session()
        return json_or_redirect(
            "Backup restored. Sign in again if your password changed.",
            url_for("login"),
            reauth=True,
        )

    @app.post("/admin/settings/updates/check")
    @login_required
    def check_updates():
        result = update.check_latest(g.db)
        message = result.get("message") or "Checked GitHub."
        if wants_json():
            return jsonify({"ok": bool(result.get("ok")), "message": message})
        flash(message, "ok" if result.get("ok") else "error")
        return redirect(settings_path("update"))

    @app.post("/admin/settings/updates/install")
    @login_required
    def install_update():
        try:
            result = update.install_latest(g.db)
        except ValueError as exc:
            return json_or_redirect(str(exc), settings_path("update"), error=True)
        except Exception as exc:  # noqa: BLE001
            logging.getLogger("fileserve").exception("update install failed")
            return json_or_redirect(f"Could not install the update: {exc}", settings_path("update"), error=True)
        update.schedule_restart()
        return json_or_redirect(result.get("message") or "Installed. Restarting…", settings_path("update"))

    @app.post("/admin/settings/updates/rollback")
    @login_required
    def rollback_update():
        try:
            update.rollback_code()
        except ValueError as exc:
            return json_or_redirect(str(exc), settings_path("backup"), error=True)
        except Exception as exc:  # noqa: BLE001
            logging.getLogger("fileserve").exception("update rollback failed")
            return json_or_redirect(f"Could not roll back: {exc}", settings_path("backup"), error=True)
        update.schedule_restart()
        return json_or_redirect("Rolled back. Restarting…", settings_path("backup"))

    @app.get("/manifest.webmanifest")
    def manifest():
        db = g.db
        name = hostname.homescreen_name(db) if db is not None else "FileServe"
        return jsonify(
            {
                "name": name,
                "short_name": name,
                "start_url": "/",
                "display": "standalone",
                "background_color": "#f3eee4",
                "theme_color": "#f3eee4",
                "icons": [{"src": "/static/icons/apple-touch-icon.svg", "sizes": "180x180", "type": "image/svg+xml"}],
            }
        )

    @app.get("/<slug>")
    def public_page(slug: str):
        page = pages_svc.get_by_slug(g.db, slug)
        if page is None:
            abort(404)
        folder = pages_svc.page_dir(slug)
        index = folder / "index.html"
        if not index.is_file():
            abort(404)
        if page.is_protected and not is_signed_in():
            auth = request.authorization
            username = auth.username if auth else ""
            password = auth.password if auth else ""
            if not pages_svc.credentials_allowed(page, username, password):
                return _page_unauthorized()
        return send_from_directory(folder, "index.html")

    @app.get("/<slug>/")
    def public_page_slash(slug: str):
        return public_page(slug)

    return app


app = create_app()
