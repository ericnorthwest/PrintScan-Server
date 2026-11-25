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
    spool_dir: Path
    allowed_hosts: list[str]
    cookie_secure: bool
    session_ttl_seconds: int
    max_upload_bytes: int
    lp_bin: str
    lpstat_bin: str
    scanimage_bin: str

    @classmethod
    def from_env(cls) -> "Settings":
        data_dir = Path(os.getenv("PRINTSCAN_DATA_DIR", "./var")).expanduser()
        database_path = Path(os.getenv("PRINTSCAN_DATABASE_PATH", str(data_dir / "printscan.sqlite3"))).expanduser()
        spool_dir = Path(os.getenv("PRINTSCAN_SPOOL_DIR", str(data_dir / "spool"))).expanduser()
        hosts_value = os.getenv("PRINTSCAN_ALLOWED_HOSTS", "localhost,127.0.0.1,::1")
        allowed_hosts = [item.strip() for item in hosts_value.split(",") if item.strip()]
        if not allowed_hosts:
            allowed_hosts = ["localhost", "127.0.0.1", "::1"]
        session_ttl = int(os.getenv("PRINTSCAN_SESSION_TTL", "43200"))
        max_upload = int(os.getenv("PRINTSCAN_MAX_UPLOAD_BYTES", str(32 * 1024 * 1024)))
        if session_ttl < 300:
            raise ValueError("PRINTSCAN_SESSION_TTL must be at least 300 seconds")
        if not 1024 * 1024 <= max_upload <= 512 * 1024 * 1024:
            raise ValueError("PRINTSCAN_MAX_UPLOAD_BYTES must be between 1 and 512 MiB")
        return cls(
            data_dir=data_dir,
            database_path=database_path,
            spool_dir=spool_dir,
            allowed_hosts=allowed_hosts,
            cookie_secure=_as_bool(os.getenv("PRINTSCAN_COOKIE_SECURE")),
            session_ttl_seconds=session_ttl,
            max_upload_bytes=max_upload,
            lp_bin=os.getenv("PRINTSCAN_LP_BIN", "lp"),
            lpstat_bin=os.getenv("PRINTSCAN_LPSTAT_BIN", "lpstat"),
            scanimage_bin=os.getenv("PRINTSCAN_SCANIMAGE_BIN", "scanimage"),
        )
