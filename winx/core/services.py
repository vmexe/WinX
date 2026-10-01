"""Query and control Windows services (``sc`` / PowerShell, simulated elsewhere)."""

from __future__ import annotations

import re
from functools import lru_cache

from . import platform as pf
from .runner import run_sync

#: Windows accepts these values for ``sc config <name> start= <value>``
SC_START_VALUES = ("boot", "system", "auto", "demand", "disabled", "delayed-auto")

_START_MAP = {
    # sc qc tokens (START_TYPE : 2 AUTO_START)
    "auto_start": "auto",
    "demand_start": "demand",
    "boot_start": "boot",
    "system_start": "system",
    # PowerShell StartMode values (Auto, Manual, Disabled, AutoDelayedStart)
    "auto": "auto",
    "automatic": "auto",
    "manual": "demand",
    "demand": "demand",
    "disabled": "disabled",
    "autodelayedstart": "delayed-auto",
    "automatic-delayed": "delayed-auto",
    "delayed-auto": "delayed-auto",
    "delayedauto": "delayed-auto",
    "boot": "boot",
    "system": "system",
}


def normalise_start(value: str) -> str:
    """Normalise any start-type spelling to a canonical token.

    Handles both `sc qc` (``AUTO_START``) and PowerShell/CIM (``Auto``,
    ``Manual``) spellings; a delayed auto-start is reported as
    ``delayed-auto``.
    """
    v = (value or "").strip().lower()
    if not v:
        return ""
    if "delayed" in v:
        return "delayed-auto"
    v = v.replace(" ", "-").replace("_", "-")
    v = v.replace("-start", "")
    return _START_MAP.get(v, v)


@lru_cache(maxsize=512)
def query(name: str) -> dict:
    """Return ``{"exists": bool, "start": str, "state": str, "display": str}``."""
    if not pf.IS_WINDOWS or pf.simulating():
        from .simdata import simulated_service

        return simulated_service(name)
    rc, out, _ = run_sync(  # pragma: no cover - Windows only
        ["sc", "qc", name], timeout=30
    )
    if rc != 0 or "FAILED" in out.upper():
        return {"exists": False, "start": "", "state": "", "display": name}
    start = ""
    display = name
    m = re.search(r"START_TYPE\s*:\s*(.+)", out, re.I)
    if m:
        # e.g. "2   AUTO_START" or "2   AUTO_START (DELAYED)"
        start = normalise_start(m.group(1))
    m = re.search(r"DISPLAY_NAME\s*:\s*(.+)", out, re.I)
    if m:
        display = m.group(1).strip()
    state = state_of(name)
    return {"exists": True, "start": start, "state": state, "display": display}


def state_of(name: str) -> str:
    if not pf.IS_WINDOWS or pf.simulating():
        from .simdata import simulated_service

        return simulated_service(name)["state"]
    rc, out, _ = run_sync(["sc", "query", name], timeout=30)  # pragma: no cover
    if rc != 0:
        return ""
    m = re.search(r"STATE\s*:\s*\d+\s+(\S+)", out, re.I)
    return (m.group(1).upper() if m else "")


def set_start(name: str, start: str) -> tuple[bool, str]:
    """Change a service start-up type."""
    start = normalise_start(start)
    if not pf.IS_WINDOWS or pf.simulating():
        from .simdata import set_simulated_service

        set_simulated_service(name, start=start)
        query.cache_clear()
        return (True, "")
    rc, out, err = run_sync(  # pragma: no cover - Windows only
        ["sc", "config", name, f"start={start}"], timeout=60
    )
    if rc == 0 and "FAILED" not in out.upper():
        query.cache_clear()
        return (True, "")
    return (False, (err or out or "sc config failed").strip())


def control(name: str, action: str) -> tuple[bool, str]:
    """``start`` / ``stop`` a service."""
    if not pf.IS_WINDOWS or pf.simulating():
        from .simdata import set_simulated_service

        set_simulated_service(name, state="RUNNING" if action == "start" else "STOPPED")
        query.cache_clear()
        return (True, "")
    rc, out, err = run_sync(["sc", action, name], timeout=120)  # pragma: no cover
    ok = rc == 0 or "FAILED 1062" in out  # 1062 = already started
    return (ok, "" if ok else (err or out).strip())


def list_services(include_windows: bool = False) -> list[dict]:
    """All services with their start type — used by the startup manager."""
    if not pf.IS_WINDOWS or pf.simulating():
        from .simdata import simulated_services

        return simulated_services()
    ps = (  # pragma: no cover - Windows only
        "Get-CimInstance Win32_Service | "
        "Select-Object Name,DisplayName,StartMode,State,StartName,PathName | "
        "ConvertTo-Json -Depth 2"
    )
    rc, out, err = run_sync(
        [pf.powershell_exe(), "-NoProfile", "-Command", ps], timeout=120, kind="raw"
    )
    if rc != 0:
        return []
    import json

    try:
        data = json.loads(out)
    except Exception:
        return []
    if isinstance(data, dict):
        data = [data]
    rows = []
    for item in data:
        rows.append(
            {
                "name": item.get("Name", ""),
                "display": item.get("DisplayName", "") or item.get("Name", ""),
                "start": normalise_start(item.get("StartMode", "")),
                "state": (item.get("State", "") or "").upper(),
                "account": item.get("StartName", ""),
                "path": item.get("PathName", "") or "",
            }
        )
    return rows
