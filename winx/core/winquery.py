"""Helpers for structured PowerShell queries (CIM/WMI) with graceful fallback."""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from . import platform as pf
from .runner import run_script

_PREFIX = "$ErrorActionPreference='SilentlyContinue'; $ProgressPreference='SilentlyContinue'; "
_JSON_DEPTH = 6


def ps_json(script: str, timeout: int = 180) -> list[dict] | dict | None:
    """Run a PowerShell snippet that ends in ``ConvertTo-Json`` and parse it."""
    full = f"{_PREFIX}{script} | ConvertTo-Json -Depth {_JSON_DEPTH} -Compress"
    rc, out, err = run_script(full, timeout=timeout)
    if rc != 0:
        return None
    text = out.strip()
    if not text:
        return None
    start = min((i for i in (text.find("["), text.find("{")) if i >= 0), default=-1)
    if start > 0:
        text = text[start:]
    try:
        return json.loads(text)
    except Exception:
        try:
            return json.loads(text.encode("utf-8", "ignore").decode("utf-8", "ignore"))
        except Exception:
            return None


def ps_csv(script: str, timeout: int = 180) -> list[dict]:
    """Run a PowerShell snippet that ends in ``ConvertTo-Csv`` and parse rows."""
    full = f"{_PREFIX}{script} | ConvertTo-Csv -NoTypeInformation"
    rc, out, _ = run_script(full, timeout=timeout)
    if rc != 0 or not out.strip():
        return []
    try:
        return list(csv.DictReader(io.StringIO(out[out.find("#TYPE") >= 0 and out.find("\n") + 1 or 0 :])))
    except Exception:
        return []


def text(value: Any, default: str = "") -> str:
    """None-safe string conversion for CIM/PowerShell values.

    A missing property arrives as ``None`` (and an empty collection can arrive
    as ``[None]``), so ``str(value)`` would leak the literal "None" into the
    UI or explode inside a join().
    """
    if value is None:
        return default
    if isinstance(value, (list, tuple)):
        parts = [text(v) for v in value]
        return ", ".join(p for p in parts if p)
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value)


def as_list(data: Any) -> list[dict]:
    if data is None:
        return []
    if isinstance(data, list):
        return [d for d in data if isinstance(d, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def cim(class_name: str, props: list[str] | None = None, where: str = "", timeout: int = 180) -> list[dict]:
    """``Get-CimInstance <class> | Select ...`` as a list of dicts."""
    select = ""
    if props:
        select = " | Select-Object " + ",".join(props)
    where_clause = f" -Filter \"{where}\"" if where else ""
    return as_list(ps_json(f"Get-CimInstance {class_name}{where_clause}{select}", timeout=timeout))


def available() -> bool:
    """True when PowerShell queries can actually return data."""
    if not pf.IS_WINDOWS or pf.simulating():
        return False
    return True
