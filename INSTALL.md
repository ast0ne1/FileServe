# Install FileServe on a Raspberry Pi

This is for a Pi 4 (or similar) on your home network. You copy the project from a Windows PC, run one install script, then browse to the Pi.

## On the Windows PC

1. Open the FileServe folder.
2. Double-click `deploy\export-pi.bat`.
3. Copy the `dist\FileServe-pi` folder onto a USB stick (or SCP / shared drive).

You do not need `.venv`, `data`, or tests on the Pi.

## On the Pi

1. Copy `FileServe-pi` somewhere convenient, for example `/home/pi/FileServe-pi`.
2. Open a terminal in that folder.
3. Run:

```bash
sudo ./deploy/install.sh --hostname fileserve
```

The script installs Python, Avahi (for `.local` names), a venv, and a systemd service at `/opt/fileserve`. `--hostname` sets the Pi name so you can open `http://fileserve.local:8081`. Omit the flag to keep the current hostname.

It writes a first-run `.env` if none exists. An existing `.env` and `data/` folder are left alone if you run install again.

## First login

Open `http://fileserve.local:8081` or `http://<pi-ip>:8081`.

Sign in with **admin** / **admin**, then change the password on **Settings → General**. Add household users on **Settings → Users** when you want separate page libraries.

To turn on HTTPS later: enable **Use HTTPS** on General, download the root CA and trust it on each phone or PC, then restart from the prompt on that tab.

## Updates

After the project is on GitHub with a Release, use **Settings → Update**: set the repository (`owner/FileServe`), tap **Check for updates**, then **Install**. That backs up your data first and does not overwrite `.env` or the `data` folder.

**Download backup** and **Roll back last app** are on the Backup/Restore tab.

## Manual run (without systemd)

```bash
cd /opt/fileserve
sudo -u fileserve /opt/fileserve/.venv/bin/python run.py
```
