from __future__ import annotations

import os
import sys

from app.config import env
from app.main import app


def main() -> None:
    host = env.host
    port = env.port
    if os.name == "nt":
        from waitress import serve

        print(f"FileServe at http://127.0.0.1:{port}")
        serve(app, host=host, port=port)
        return
    os.execvp(
        sys.executable,
        [sys.executable, "-m", "gunicorn", "-b", f"{host}:{port}", "app.main:app"],
    )


if __name__ == "__main__":
    main()
