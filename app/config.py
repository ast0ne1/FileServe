import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
HOSTED_DIR = DATA_DIR / "hosted"
BACKUPS_DIR = DATA_DIR / "backups"
UPDATES_DIR = DATA_DIR / "updates"

load_dotenv(ROOT_DIR / ".env")


def _env(key: str, default: str = "") -> str:
    value = os.getenv(key)
    return default if value is None else value


class EnvSettings:
    host: str
    port: int
    database_url: str
    public_base_url: str
    device_hostname: str
    admin_username: str
    admin_password: str
    session_secret: str
    instance_name: str
    github_repo: str

    def __init__(self) -> None:
        self.host = _env("HOST", "0.0.0.0")
        self.port = int(_env("PORT", "8081") or "8081")
        self.database_url = _env("DATABASE_URL", "sqlite:///./data/fileserve.db")
        self.public_base_url = _env("PUBLIC_BASE_URL", "http://127.0.0.1:8081")
        self.device_hostname = _env("DEVICE_HOSTNAME", "")
        self.admin_username = _env("ADMIN_USERNAME", "admin")
        self.admin_password = _env("ADMIN_PASSWORD", "admin")
        self.session_secret = _env("SESSION_SECRET", "")
        self.instance_name = _env("INSTANCE_NAME", "")
        self.github_repo = _env("GITHUB_REPO", "")


env = EnvSettings()
