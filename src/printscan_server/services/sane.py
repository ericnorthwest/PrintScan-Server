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
            "No SANE devices are visible to the PrintScan service. Check that "
            "PRINTSCAN_SCANIMAGE_BIN and SANE_CONFIG_DIR point to the intended "
            "SANE installation and that the service account can access the scanner. "
            "The Samsung SCX-4100 also needs the USB broker to release usblp "
            "temporarily before scanning."
        )
    if result.returncode != 0 and not output.strip():
        raise IntegrationUnavailable("scanimage could not query SANE backends")
    return {"scanners": devices, "available": bool(devices), "note": note}
