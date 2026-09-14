# Changelog

Current version is **0.0.0.2**. New work is appended under that version until you ask to bump it.

## 0.0.0.2 — 2026-09-14

### Added
- QR code on each Hosted Pages card for the public LAN URL
- Optional username and password per page; pages stay public unless you turn that on
- Card label and custom public path, with an edit modal on each card after setup
- Optional expiry of 1 week, 1 month, 3 months, 6 months, or a custom date; default is keep until removed
- Full-width tap target on Add Page for choosing the HTML file

### Changed
- Default port is 8081 so FileServe can run beside NewsCast on 8080
- Phone layout: stacked page actions, QR above the URL, stretched Open button, and safe-area padding
- QR codes are PNG with a quiet zone, sized to stay inside the card frame

### Fixed
- Path field keeps the leading slash inside the same input
- QR codes were clipped by the rounded frame on cards

## 0.0.0.1

- First version: login, hosted HTML pages, add/delete, NewsCast-style themes and settings
- GitHub Release check/install/rollback and backup/restore of pages plus settings
