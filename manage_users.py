"""Create or update a WISE AI account without putting its password in shell history."""

import argparse
import getpass
import os
import secrets
from pathlib import Path

from werkzeug.security import generate_password_hash

from wise_ai.data_store import save_user


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or update a WISE AI account")
    parser.add_argument("username")
    parser.add_argument("--role", choices=("admin", "branch"), required=True)
    parser.add_argument("--branch", help="Exact Branch value for a branch account")
    parser.add_argument("--generate-password", action="store_true", help="Generate and display an initial random password")
    args = parser.parse_args()
    username = args.username.strip()
    branch = args.branch.strip() if args.branch else None
    if not username or len(username) > 80:
        parser.error("username must contain 1-80 characters")
    if args.role == "branch" and (not branch or len(branch) > 120):
        parser.error("branch account requires --branch (1-120 characters)")
    if args.role == "admin" and branch:
        parser.error("admin account must not specify --branch")
    if args.generate_password:
        password = secrets.token_urlsafe(24)
    else:
        password = getpass.getpass("Password (at least 12 characters): ")
        confirmation = getpass.getpass("Confirm password: ")
        if len(password) < 12 or password != confirmation:
            parser.error("password must be at least 12 characters and match confirmation")
    database = os.getenv("WISE_DATABASE_PATH", str(Path(__file__).resolve().parent / "instance" / "wise.db"))
    save_user(database, username, generate_password_hash(password), args.role, branch)
    print(f"Account {username} saved as {args.role}.")
    if args.generate_password:
        print(f"Initial password: {password}")


if __name__ == "__main__":
    main()
