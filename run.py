from __future__ import annotations

import os
import sys


def main() -> None:
    from app.serve import main as serve_main

    serve_main()


if __name__ == "__main__":
    # Keep old entrypoints working: prefer the TLS-aware serve module.
    if os.environ.get("FILESERVE_LEGACY_SERVER") == "1":
        from app.config import env
        from app.main import app

        if os.name == "nt":
            from waitress import serve

            print(f"FileServe at http://127.0.0.1:{env.port}")
            serve(app, host=env.host, port=env.port)
            raise SystemExit(0)
        os.execvp(
            sys.executable,
            [sys.executable, "-m", "gunicorn", "-b", f"{env.host}:{env.port}", "app.main:app"],
        )
    main()
