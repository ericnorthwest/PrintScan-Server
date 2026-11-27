from __future__ import annotations

import re
import subprocess
from typing import Any


_OPTION_PATTERN = re.compile(
    r"^\s+--(?P<name>[a-z][a-z0-9_-]*)(?:\s+(?P<spec>.*))?$",
    re.IGNORECASE,
)
_RANGE_PATTERN = re.compile(
    r"^(?P<minimum>-?\d+(?:\.\d+)?)\.\.(?P<maximum>-?\d+(?:\.\d+)?)(?:[a-zA-Z%]+)?$"
)
_SUPPORTED_OPTIONS = {"mode", "resolution", "source"}


class SaneError(RuntimeError):
    """Raised when SANE cannot discover or operate a scanner."""


def _run(scanimage_bin: str, args: list[str], timeout: int = 20) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            [scanimage_bin, *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise SaneError(
            f"scanimage was not found at {scanimage_bin!r}. "
            "Check PRINTSCAN_SCANIMAGE_BIN and the SANE installation."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise SaneError("SANE did not respond before the timeout.") from exc


def _combined_output(result: subprocess.CompletedProcess[str]) -> str:
    return "\n".join(part for part in (result.stdout, result.stderr) if part)


def _parse_device_line(line: str) -> dict[str, str] | None:
    marker = line.find("device ")
    if marker < 0:
        return None
    tail = line[marker + len("device "):].lstrip()
    if not tail or tail[0] not in ("'", chr(96)):
        return None
    quote = tail[0]
    end = tail.find(quote, 1)
    if end < 0:
        return None
    name = tail[1:end]
    suffix = tail[end + 1:].strip()
    if not suffix.lower().startswith("is a "):
        return None
    return {"name": name, "model": suffix[5:].strip()}


def list_scanners(scanimage_bin: str) -> dict[str, Any]:
    result = _run(scanimage_bin, ["-L"], timeout=20)
    output = _combined_output(result)
    devices: list[dict[str, str]] = []

    for line in output.splitlines():
        device = _parse_device_line(line.strip())
        if device and not any(item["name"] == device["name"] for item in devices):
            devices.append(device)

    note = None
    if not devices:
        note = (
            "SANE не обнаружил сканер. Проверьте PRINTSCAN_SCANIMAGE_BIN, "
            "права пользователя сервиса и доступность USB-устройства."
        )
    if result.returncode != 0 and not output.strip():
        raise SaneError("scanimage не смог обратиться к SANE-бэкендам.")

    return {"scanners": devices, "available": bool(devices), "note": note}


def _parse_option(name: str, spec: str) -> dict[str, Any] | None:
    default_match = re.search(r"\[([^\]]*)\]\s*$", spec)
    default = default_match.group(1).strip() if default_match else None
    value_spec = spec[: default_match.start()].strip() if default_match else spec.strip()
    token = value_spec.split(maxsplit=1)[0] if value_spec else ""

    if not token:
        return None

    if name == "resolution":
        range_match = _RANGE_PATTERN.match(token)
        if range_match:
            minimum = int(float(range_match.group("minimum")))
            maximum = int(float(range_match.group("maximum")))
            step_match = re.search(r"\bin steps of\s+(\d+(?:\.\d+)?)", value_spec, re.IGNORECASE)
            step = max(1, int(float(step_match.group(1)))) if step_match else 1
            parsed_default = int(float(default)) if default and re.fullmatch(r"\d+(?:\.\d+)?", default) else minimum
            return {
                "type": "range",
                "minimum": minimum,
                "maximum": maximum,
                "step": step,
                "default": parsed_default,
            }

        values = [item.rstrip("dpi") for item in token.split("|")]
        if values and all(item.isdigit() for item in values):
            numeric_values = [int(item) for item in values]
            parsed_default = int(default) if default and default.isdigit() else numeric_values[0]
            return {
                "type": "choices",
                "values": numeric_values,
                "default": parsed_default,
            }
        return None

    values = [item for item in token.split("|") if item]
    if not values:
        return None
    if default and default not in values:
        default = values[0]
    return {"type": "choices", "values": values, "default": default or values[0]}


def parse_scanner_options(output: str) -> dict[str, dict[str, Any]]:
    """Extract the standard user-facing options from scanimage help output."""
    options: dict[str, dict[str, Any]] = {}

    for line in output.splitlines():
        match = _OPTION_PATTERN.match(line)
        if not match:
            continue
        name = match.group("name").lower()
        if name not in _SUPPORTED_OPTIONS:
            continue
        parsed = _parse_option(name, match.group("spec") or "")
        if parsed:
            options[name] = parsed

    return options


def get_scanner_options(scanimage_bin: str, device: str) -> dict[str, Any]:
    scanners = list_scanners(scanimage_bin)["scanners"]
    if device not in {item["name"] for item in scanners}:
        raise SaneError("Выбранный сканер больше не обнаруживается SANE.")

    result = _run(scanimage_bin, ["-A", "--device-name", device], timeout=20)
    output = _combined_output(result)
    if result.returncode != 0 and not output.strip():
        raise SaneError("Не удалось получить параметры выбранного сканера.")

    options = parse_scanner_options(output)
    if not options:
        raise SaneError("SANE-бэкенд не сообщил доступные параметры сканирования.")

    return {"device": device, "options": options}


def build_scan_arguments(
    device: str,
    options: dict[str, dict[str, Any]],
    selected: dict[str, Any],
) -> list[str]:
    """Validate UI values against options reported by the selected SANE backend."""
    args = ["--device-name", device, "--format=pnm"]

    for name in ("mode", "resolution", "source"):
        value = selected.get(name)
        if value is None or value == "":
            continue

        spec = options.get(name)
        if spec is None:
            raise SaneError(f"Этот сканер не поддерживает параметр {name}.")

        if spec["type"] == "choices":
            allowed = [str(item) for item in spec["values"]]
            if str(value) not in allowed:
                raise SaneError(f"Недопустимое значение параметра {name}.")
            value = str(value)
        elif name == "resolution" and spec["type"] == "range":
            try:
                numeric_value = int(value)
            except (TypeError, ValueError) as exc:
                raise SaneError("Разрешение должно быть целым числом.") from exc
            minimum = int(spec["minimum"])
            maximum = int(spec["maximum"])
            step = max(1, int(spec["step"]))
            if numeric_value < minimum or numeric_value > maximum:
                raise SaneError("Разрешение находится вне диапазона сканера.")
            if (numeric_value - minimum) % step:
                raise SaneError(f"Разрешение должно изменяться с шагом {step} dpi.")
            value = str(numeric_value)
        else:
            raise SaneError(f"Неподдерживаемый тип параметра {name}.")

        args.extend([f"--{name}", str(value)])

    return args
