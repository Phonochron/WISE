"""Run WISE AI behind an HTTPS reverse proxy with operational safeguards."""

import os

from waitress import serve

from app import app
from wise_ai.config import get_server_config
from wise_ai.data_store import count_users


def main() -> None:
    if not app.config["AUTH_REQUIRED"]:
        raise RuntimeError("Set WISE_AUTH_REQUIRED=true before starting the operational server")
    if len(os.getenv("WISE_SECRET_KEY", "")) < 32:
        raise RuntimeError("Set a persistent WISE_SECRET_KEY with at least 32 characters")
    if not app.config["SESSION_COOKIE_SECURE"]:
        raise RuntimeError("Set WISE_SECURE_COOKIES=true and serve clients over HTTPS")
    if count_users(app.config["DATABASE_PATH"], "admin") == 0:
        raise RuntimeError("Create an admin account with manage_users.py first")
    config = get_server_config()
    if config["debug"]:
        raise RuntimeError("Disable WISE_DEBUG for the operational server")
    if config["host"] not in {"127.0.0.1", "::1", "localhost"}:
        raise RuntimeError("Bind Waitress to loopback and expose it through an HTTPS reverse proxy")
    serve(app, host=config["host"], port=config["port"], max_request_body_size=12 * 1024 * 1024)


if __name__ == "__main__":
    main()
