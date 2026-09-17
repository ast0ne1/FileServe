# Changelog

Current version is **0.0.0.4**. New work is appended under that version until you ask to bump it.

## 0.0.0.4 — 2026-09-17

### Added
- Multi-user household accounts: admin pages stay at `/slug`, user pages at `/u/username/slug`
- Settings → Users for creating accounts, resetting passwords, and removing users
- Optional LAN HTTPS with a local root CA, deferred restart, and CA download

### Changed
- Non-admin users see full Pages for their own files only, and Settings limited to Device and About
- Default serve path uses uvicorn (TLS-capable); Waitress remains available via `FILESERVE_LEGACY_SERVER=1`

## 0.0.0.3 — 2026-09-14

### Added
- Host HTML, PDF, and Word (`.docx`); PDFs open in the browser, Word is shown as a readable preview
- Replace the hosted file on an existing page without deleting the URL or settings
- Optional short description on add and edit, shown on the card and public listing
- Public `/browse` listing of enabled, non-expired titles
- Copy URL and copy username on each card; copy password once when it is set
- Download the original hosted file from the card
- Download and print QR codes
- Search and sort on Hosted Pages, plus open count and last opened

### Changed
- Hosted Pages cards group URL/file and QR actions as icon buttons on desktop and phone
- Add Page accepts `.html`, `.pdf`, or `.docx`

### Fixed
- Copy URL/username/password works on plain HTTP LAN addresses, not only localhost

## 0.0.0.2 — 2026-09-14

### Added
- QR code on each Hosted Pages card for the public LAN URL
- Optional username and password per page; pages stay public unless you turn that on
- Card label and custom public path, with an edit modal on each card after setup
- Optional expiry of 1 week, 1 month, 3 months, 6 months, or a custom date; default is keep until removed
- Enable/disable a page to hide the public URL without deleting files
- Full-width tap target on Add Page for choosing the HTML file

### Changed
- Default port is 8081
- Phone layout: stacked page actions, QR above the URL, stretched Open button, and safe-area padding
- QR codes are PNG with a quiet zone, sized to stay inside the card frame

### Fixed
- Path field keeps the leading slash inside the same input
- QR codes were clipped by the rounded frame on cards

## 0.0.0.1

- First version: login, hosted HTML pages, add/delete, themes and settings
- GitHub Release check/install/rollback and backup/restore of pages plus settings
