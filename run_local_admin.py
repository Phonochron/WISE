"""Run the local WISE AI site with login enabled on loopback only."""

import os
import secrets
from pathlib import Path

from wise_ai.config import BASE_DIR, get_server_config
from wise_ai.data_store import count_users


def _local_secret() -> str:
    path = BASE_DIR / "instance" / "local_session_secret"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        try:
            with path.open("x", encoding="utf-8") as handle:
                handle.write(secrets.token_urlsafe(48))
        except FileExistsError:
            pass
    secret = path.read_text(encoding="utf-8").strip()
    if len(secret) < 32:
        raise RuntimeError("Local session secret must have at least 32 characters")
    return secret


def main() -> None:
    database = os.getenv("WISE_DATABASE_PATH", str(BASE_DIR / "instance" / "wise.db"))
    if count_users(database, "admin") == 0:
        raise RuntimeError("Create an admin account first: python manage_users.py admin --role admin")
    os.environ["WISE_AUTH_REQUIRED"] = "true"
    os.environ["WISE_SECRET_KEY"] = os.getenv("WISE_SECRET_KEY") or _local_secret()
    os.environ["WISE_SECURE_COOKIES"] = "false"
    os.environ["WISE_DEBUG"] = "false"
    from app import app

    config = get_server_config()
    app.run(host="127.0.0.1", port=config["port"], debug=False)


if __name__ == "__main__":
    main()
