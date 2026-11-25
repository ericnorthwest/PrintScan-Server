from __future__ import annotations

import argparse
import getpass
import re
import sqlite3

import uvicorn

from .config import Settings
from .database import create_user, init_database
from .security import hash_password


def _create_admin(username: str | None) -> int:
    settings = Settings.from_env()
    init_database(settings.database_path)
    if username is None:
        username = input("Administrator username: ").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{3,64}", username):
        print("Username must be 3-64 characters: letters, digits, dot, dash or underscore.")
        return 2
    password = getpass.getpass("Administrator password (minimum 12 characters): ")
    confirmation = getpass.getpass("Repeat password: ")
    if password != confirmation:
        print("Passwords do not match.")
        return 2
    try:
        create_user(settings.database_path, username, hash_password(password))
    except ValueError as exc:
        print(str(exc))
        return 2
    except sqlite3.IntegrityError:
        print("That username already exists.")
        return 2
    print("Administrator account created.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="printscan")
    commands = parser.add_subparsers(dest="command", required=True)
    admin_parser = commands.add_parser("init-admin", help="Create the first administrator")
    admin_parser.add_argument("username", nargs="?")
    serve_parser = commands.add_parser("serve", help="Start the web application")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8090)
    args = parser.parse_args()
    if args.command == "init-admin":
        raise SystemExit(_create_admin(args.username))
    if args.command == "serve":
        uvicorn.run("printscan_server.main:app", host=args.host, port=args.port,
                    proxy_headers=False, forwarded_allow_ips="")


if __name__ == "__main__":
    main()
