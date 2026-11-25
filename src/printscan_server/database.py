from __future__ import annotations

import hashlib
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


@contextmanager
def connection(database_path: Path) -> Iterator[sqlite3.Connection]:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(database_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_database(database_path: Path) -> None:
    with connection(database_path) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'admin',
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                csrf_token TEXT NOT NULL,
                expires_at INTEGER NOT NULL,
                created_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_sessions_expiry ON sessions(expires_at);
            CREATE TABLE IF NOT EXISTS auth_failures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                remote_addr TEXT NOT NULL,
                attempted_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_auth_failures_ip_time
                ON auth_failures(remote_addr, attempted_at);
        """)


def create_user(database_path: Path, username: str, password_hash: str) -> None:
    with connection(database_path) as conn:
        conn.execute(
            "INSERT INTO users(username, password_hash, role, created_at) VALUES (?, ?, 'admin', ?)",
            (username, password_hash, int(time.time())),
        )


def get_user(database_path: Path, username: str) -> dict | None:
    with connection(database_path) as conn:
        row = conn.execute(
            "SELECT id, username, password_hash, role FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        return dict(row) if row else None


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(database_path: Path, user_id: int, ttl_seconds: int) -> tuple[str, str, int]:
    token = secrets.token_urlsafe(40)
    csrf_token = secrets.token_urlsafe(32)
    now = int(time.time())
    expires_at = now + ttl_seconds
    with connection(database_path) as conn:
        conn.execute(
            "INSERT INTO sessions(token_hash, user_id, csrf_token, expires_at, created_at) VALUES (?, ?, ?, ?, ?)",
            (token_digest(token), user_id, csrf_token, expires_at, now),
        )
        conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
    return token, csrf_token, expires_at


def get_session(database_path: Path, token: str) -> dict | None:
    digest = token_digest(token)
    now = int(time.time())
    with connection(database_path) as conn:
        row = conn.execute("""
            SELECT sessions.token_hash, sessions.csrf_token, sessions.expires_at,
                   users.id AS user_id, users.username, users.role
            FROM sessions JOIN users ON users.id = sessions.user_id
            WHERE sessions.token_hash = ?
        """, (digest,)).fetchone()
        if row is None:
            return None
        if row["expires_at"] <= now:
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (digest,))
            return None
        return dict(row)


def delete_session(database_path: Path, token_hash: str) -> None:
    with connection(database_path) as conn:
        conn.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))


def is_rate_limited(database_path: Path, remote_addr: str) -> bool:
    cutoff = int(time.time()) - 900
    with connection(database_path) as conn:
        conn.execute("DELETE FROM auth_failures WHERE attempted_at < ?", (cutoff,))
        row = conn.execute(
            "SELECT COUNT(*) AS total FROM auth_failures WHERE remote_addr = ? AND attempted_at >= ?",
            (remote_addr, cutoff),
        ).fetchone()
        return int(row["total"]) >= 10


def record_login_failure(database_path: Path, remote_addr: str) -> None:
    with connection(database_path) as conn:
        conn.execute("INSERT INTO auth_failures(remote_addr, attempted_at) VALUES (?, ?)",
                     (remote_addr, int(time.time())))


def clear_login_failures(database_path: Path, remote_addr: str) -> None:
    with connection(database_path) as conn:
        conn.execute("DELETE FROM auth_failures WHERE remote_addr = ?", (remote_addr,))
