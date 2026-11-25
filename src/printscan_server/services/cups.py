from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass


class IntegrationUnavailable(RuntimeError):
    pass


@dataclass
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


def _run(binary: str, args: list[str], timeout: int = 10) -> CommandResult:
    try:
        process = subprocess.run(
            [binary, *args], check=False, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise IntegrationUnavailable(f"Required executable not found: {binary}") from exc
    except subprocess.TimeoutExpired as exc:
        raise IntegrationUnavailable(f"Command timed out: {binary}") from exc
    return CommandResult(process.returncode, process.stdout, process.stderr)


def list_printers(lpstat_bin: str) -> dict:
    result = _run(lpstat_bin, ["-p"])
    if result.returncode != 0:
        raise IntegrationUnavailable(result.stderr.strip() or "lpstat failed")
    printers = []
    for line in result.stdout.splitlines():
        match = re.match(r"^printer ([A-Za-z0-9_.-]{1,127}) (.+)$", line.strip())
        if match:
            printers.append({"name": match.group(1), "state": match.group(2)})
    default_result = _run(lpstat_bin, ["-d"])
    default_printer = None
    if default_result.returncode == 0:
        match = re.search(r"system default destination:\s*([A-Za-z0-9_.-]{1,127})",
                          default_result.stdout, re.IGNORECASE)
        if match:
            default_printer = match.group(1)
    return {"printers": printers, "default_printer": default_printer}


def submit_print(lp_bin: str, printer: str, title: str, document_path: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,127}", printer):
        raise ValueError("Invalid printer name")
    result = _run(lp_bin, ["-d", printer, "-t", title[:120], document_path], timeout=30)
    if result.returncode != 0:
        raise IntegrationUnavailable(result.stderr.strip() or "CUPS rejected the job")
    return result.stdout.strip() or "submitted"
