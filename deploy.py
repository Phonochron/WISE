"""Start the single-instance WISE AI service on Railway."""

import os
import re
from pathlib import Path
from typing import MutableMapping

from werkzeug.security import generate_password_hash

from wise_ai.data_store import count_users, get_user_by_name, save_user


def prepare_deployment(environ: MutableMapping[str, str]) -> int:
    """Validate runtime settings and bootstrap one admin on the mounted volume."""
    port_text = environ.get("PORT", "")
    try:
        port = int(port_text)
    except ValueError as exc:
        raise RuntimeError("Railway must provide a valid PORT") from exc
    if not 1 <= port <= 65535:
        raise RuntimeError("Railway PORT must be between 1 and 65535")

    mount_text = environ.get("RAILWAY_VOLUME_MOUNT_PATH", "")
    mount = Path(mount_text) if mount_text else None
    if mount is None or not mount.is_absolute() or not mount.is_dir():
        raise RuntimeError("Attach a persistent Railway volume before starting WISE AI")
    if environ.get("WISE_AUTH_REQUIRED", "").lower() != "true":
        raise RuntimeError("Set WISE_AUTH_REQUIRED=true")
    if environ.get("WISE_SECURE_COOKIES", "").lower() != "true":
        raise RuntimeError("Set WISE_SECURE_COOKIES=true for the HTTPS domain")
    if len(environ.get("WISE_SECRET_KEY", "")) < 32:
        raise RuntimeError("Set a persistent WISE_SECRET_KEY with at least 32 characters")
    if environ.get("WISE_DEBUG", "false").lower() not in {"false", "0"}:
        raise RuntimeError("Disable WISE_DEBUG for deployment")

    database = mount / "wise.db"
    environ["WISE_DATABASE_PATH"] = str(database)
    if count_users(database, "admin") == 0:
        username = environ.get("WISE_BOOTSTRAP_ADMIN_USERNAME", "admin").strip()
        password = environ.get("WISE_BOOTSTRAP_ADMIN_PASSWORD", "")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{3,80}", username):
            raise RuntimeError("Set a valid WISE_BOOTSTRAP_ADMIN_USERNAME")
        if not 12 <= len(password) <= 1024:
            raise RuntimeError("Set WISE_BOOTSTRAP_ADMIN_PASSWORD (12-1024 characters) for the first deploy")
        if get_user_by_name(database, username) is not None:
            raise RuntimeError("Bootstrap username already belongs to another account")
        save_user(database, username, generate_password_hash(password), "admin", None)
    environ.pop("WISE_BOOTSTRAP_ADMIN_PASSWORD", None)
    return port


def main() -> None:
    port = prepare_deployment(os.environ)
    os.execvp("gunicorn", [
        "gunicorn", "--bind", f"0.0.0.0:{port}", "--workers", "1", "--threads", "4",
        "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-",
        "app:app",
    ])


if __name__ == "__main__":
    main()
