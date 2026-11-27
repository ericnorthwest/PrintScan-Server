from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    database_path: Path
    scan_dir: Path
    allowed_hosts: list[str]
    cookie_secure: bool
    session_ttl_seconds: int
    scanimage_bin: str
    max_scan_bytes: int

    @classmethod
    def from_env(cls) -> "Settings":
        data_dir = Path(os.getenv("PRINTSCAN_DATA_DIR", "./var")).expanduser()
        database_path = Path(
            os.getenv("PRINTSCAN_DATABASE_PATH", str(data_dir / "printscan.sqlite3"))
        ).expanduser()
        scan_dir = Path(os.getenv("PRINTSCAN_SCAN_DIR", str(data_dir / "scans"))).expanduser()
        hosts_value = os.getenv("PRINTSCAN_ALLOWED_HOSTS", "localhost,127.0.0.1,::1")
        allowed_hosts = [item.strip() for item in hosts_value.split(",") if item.strip()]
        if not allowed_hosts:
            allowed_hosts = ["localhost", "127.0.0.1", "::1"]

        session_ttl = int(os.getenv("PRINTSCAN_SESSION_TTL", "43200"))
        max_scan_bytes = int(os.getenv("PRINTSCAN_MAX_SCAN_BYTES", str(256 * 1024 * 1024)))
        if session_ttl < 300:
            raise ValueError("PRINTSCAN_SESSION_TTL must be at least 300 seconds")
        if not 1024 * 1024 <= max_scan_bytes <= 1024 * 1024 * 1024:
            raise ValueError("PRINTSCAN_MAX_SCAN_BYTES must be between 1 MiB and 1 GiB")

        return cls(
            data_dir=data_dir,
            database_path=database_path,
            scan_dir=scan_dir,
            allowed_hosts=allowed_hosts,
            cookie_secure=_as_bool(os.getenv("PRINTSCAN_COOKIE_SECURE")),
            session_ttl_seconds=session_ttl,
            scanimage_bin=os.getenv("PRINTSCAN_SCANIMAGE_BIN", "scanimage"),
            max_scan_bytes=max_scan_bytes,
        )
