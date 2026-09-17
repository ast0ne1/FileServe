# FileServe

A small Flask host for household files. Upload HTML, PDF, or Word, get a friendly URL on your LAN, and manage everything from a phone-friendly UI.

Current version is **0.0.0.4**.

It runs the same way on Windows and Raspberry Pi OS. Hosted HTML is served as uploaded — no FileServe chrome, no rewriting. PDFs open in the browser. Word (`.docx`) is shown as a readable preview.

Default login: **admin** / **admin**. Change it on Settings after first launch. Passwords are hashed with argon2id. Add household users under **Settings → Users**; their pages live at `/u/username/slug` while admin pages stay at `/slug`.

<p align="center">
  <img src="docs/screenshots/login.png?v=0.0.0.4" alt="FileServe sign-in screen on a phone" width="280" />
</p>

## What it does

- Hosts one HTML, PDF, or Word file per public path (`/emergency-planner` for admin, `/u/alex/…` for users)
- Optional username and password per page; pages stay public unless you turn that on
- Optional expiry (1 week, 1 month, 3 months, 6 months, or a custom date); default is keep until removed
- Disable a page to hide the public URL without deleting its files
- Replace the hosted file later without changing the URL
- Lists, opens, edits, downloads, and deletes pages from an authenticated dashboard
- Card label, description, and path are set on Add and can be changed later; the path defaults from the label
- Public `/browse` listing of enabled, non-expired titles (all household members)
- Light / Dark / Auto plus colour palettes (Default, Ocean, Forest, Slate)
- Optional household accounts with separate page libraries and storage under `data/hosted/u/<username>/`
- Opt-in LAN HTTPS with an in-app local CA on the same port as HTTP; download the root CA and trust it on each device before restarting
- Backup and restore of the database, hosted files, TLS certificates, and `.env`
- In-app GitHub Release check, install, and rollback

## Web UI

| Tab | What it is for |
| --- | --- |
| **Pages** | Hosted labels and paths, QR codes, search/sort, Enable/Disable, Open, Edit, copy/download/print actions, and Remove. Admins see an owner chip and can filter by user. |
| **Add** | Label, optional description and path, optional page login, optional expiry, plus `.html`, `.pdf`, or `.docx` file |
| **Settings** | Device (appearance, your password, hostname, HTTPS, instance name), Users (admin), Backup/Restore (admin), Update (admin), About. Non-admins only see Device and About. |

<p align="center">
  <img src="docs/screenshots/pages.png?v=0.0.0.4" alt="Hosted Pages" width="280" />
  <img src="docs/screenshots/add.png?v=0.0.0.4" alt="Add Page" width="280" />
  <img src="docs/screenshots/settings.png?v=0.0.0.4" alt="Settings" width="280" />
</p>

Public URLs such as `http://<pi-ip>:8081/emergency-planner` do not require a FileServe login unless you protect that page. Live titles are listed at `/browse`. FileServe defaults to port **8081**.

| Path | Who it belongs to |
| --- | --- |
| `/slug` | Admin (household root) pages |
| `/u/<username>/slug` | That household user’s pages |
| `/browse` | Public list of enabled, non-expired titles from everyone |

## Household accounts

Admin creates people under **Settings → Users**. Each person gets their own hosted pages, QR codes, and file storage. They use the same Pages and Add tabs as admin, but only see their own cards (no user filter).

- **URLs** — admin keeps short paths (`/family-kit`). Users get `/u/<username>/family-kit`.
- **Settings** — non-admins can change appearance and their own password. Hostname, HTTPS, Users, Backup/Restore, and Update stay admin-only.
- **Admin oversight** — on Pages, filter by user, see an owner chip on each card, and enable/edit/delete any page.
- **Removing a user** — deletes their account and all of their hosted pages from disk.

## HTTPS

On **Settings → Device**, turn on **Use HTTPS**. FileServe creates a local root CA and server certificate under `data/tls/`.

1. Download the root CA and trust it on each phone or PC (required once per device).
2. Use **Restart to enable HTTPS** when prompted. The app keeps the same port; open `https://…`, not `http://`.
3. Turning HTTPS off schedules a restart back to plain HTTP.
4. Share URLs and QR codes use `https://` while HTTPS is enabled. Backups include the TLS folder.

## Windows development

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Double-click `run-local.bat` (or run `python run.py`). Open http://127.0.0.1:8081 and sign in with `admin` / `admin`.

uvicorn serves the app (HTTP or HTTPS). Set `FILESERVE_LEGACY_SERVER=1` to use Waitress on Windows or Gunicorn on the Pi instead (HTTP only).

## Raspberry Pi OS

Step-by-step: **[INSTALL.md](INSTALL.md)**.

On the PC, double-click `deploy\export-pi.bat`. It writes `dist\FileServe-pi`. Copy that onto the Pi, then:

```bash
cd /path/to/FileServe-pi
sudo ./deploy/install.sh --hostname fileserve
```

Open `http://fileserve.local:8081` (or `http://<pi-ip>:8081`), sign in with `admin` / `admin`, then change the password on Settings. Add household users and optional HTTPS from Settings when you are ready.

After you publish GitHub Releases, Settings can check and install that update in place. It backs up data first and does not overwrite `.env` or the `data` folder.

## Configuration

| Variable | Default | Notes |
| --- | --- | --- |
| `HOST` | `0.0.0.0` | Bind address so other devices on the LAN can connect |
| `PORT` | `8081` | HTTP or HTTPS port (same port either way) |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | `admin` / `admin` | Factory login; Settings can change the admin password |
| `GITHUB_REPO` | empty | `owner/FileServe` for in-app release checks |
| `DEVICE_HOSTNAME` | empty | Optional `.local` name on a Pi |
| `INSTANCE_NAME` | empty | Label for this copy (Home, Work) |
| `PUBLIC_BASE_URL` | `http://127.0.0.1:8081` | Used for share/QR URLs when no hostname is set; becomes `https://…` when Use HTTPS is on |

UI-saved Settings win over environment variables.
