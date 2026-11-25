from __future__ import annotations

import re

from .cups import IntegrationUnavailable, _run

_DEVICE_PATTERN = re.compile(r"device ['\x60](.+?)['\x60'] is a (.+)", re.IGNORECASE)


def list_scanners(scanimage_bin: str) -> dict:
    result = _run(scanimage_bin, ["-L"], timeout=15)
    output = "\n".join(part for part in (result.stdout, result.stderr) if part)
    devices = []
    for line in output.splitlines():
        match = _DEVICE_PATTERN.search(line.strip())
        if match:
            devices.append({"name": match.group(1), "model": match.group(2)})
    note = None
    if not devices:
        note = (
            "No SANE devices were reported. The Samsung SCX-4100 needs the patched "
            "SANE backend and a future USB broker to temporarily release the usblp "
            "interface before scanning."
        )
    if result.returncode != 0 and not output.strip():
        raise IntegrationUnavailable("scanimage could not query SANE backends")
    return {"scanners": devices, "available": bool(devices), "note": note}
