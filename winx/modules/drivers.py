"""Driver inventory, problem-device detection and driver-store maintenance."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from ..core import platform as pf
from ..core.runner import run_script
from ..core.winquery import as_list, ps_json

DRIVERS_SCRIPT = (
    "Get-CimInstance Win32_PnPSignedDriver -ErrorAction SilentlyContinue | "
    "Where-Object { $_.DeviceName -and $_.DriverVersion } | "
    "Select-Object DeviceName, DriverVersion, DriverDate, Manufacturer, InfName, "
    "DeviceClass, IsSigned | Sort-Object DeviceName"
)

PROBLEM_SCRIPT = (
    "Get-PnpDevice -ErrorAction SilentlyContinue | Where-Object { $_.Status -ne 'OK' } | "
    "Select-Object FriendlyName, Status, Class, InstanceId, Problem"
)


@dataclass
class Driver:
    name: str = ""
    version: str = ""
    date: str = ""
    provider: str = ""
    inf: str = ""
    device_class: str = ""
    signed: bool = True
    status: str = "OK"

    @property
    def is_problem(self) -> bool:
        return self.status.upper() not in ("OK", "")


def _parse_driver_date(raw) -> str:
    s = str(raw or "")
    m = re.match(r"^(\d{4})(\d{2})(\d{2})", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return s[:10]


def list_drivers(progress: Callable[[int, int, str], None] | None = None) -> list[Driver]:
    if not pf.IS_WINDOWS or pf.simulating():
        from ..core.simdata import simulated_drivers

        rows = simulated_drivers()
        if progress:
            progress(1, 1, "loaded demo driver list")
        return [
            Driver(
                name=r["name"], version=r["version"], date=r["date"], provider=r["provider"],
                inf=r["inf"], device_class=r["type"], status=r["status"],
            )
            for r in rows
        ]

    if progress:
        progress(1, 2, "enumerating signed drivers")
    out: list[Driver] = []
    for row in as_list(ps_json(DRIVERS_SCRIPT, timeout=420)):
        out.append(
            Driver(
                name=str(row.get("DeviceName", "") or ""),
                version=str(row.get("DriverVersion", "") or ""),
                date=_parse_driver_date(row.get("DriverDate")),
                provider=str(row.get("Manufacturer", "") or ""),
                inf=str(row.get("InfName", "") or ""),
                device_class=str(row.get("DeviceClass", "") or ""),
                signed=bool(row.get("IsSigned", True)),
            )
        )
    if progress:
        progress(2, 2, "checking device status")
    problems = {p["name"].lower(): p["status"] for p in problem_devices()}
    for drv in out:
        if drv.name.lower() in problems:
            drv.status = problems[drv.name.lower()]
    return out


def problem_devices() -> list[dict]:
    """Devices that Windows reports as not working."""
    if not pf.IS_WINDOWS or pf.simulating():
        from ..core.simdata import simulated_drivers

        return [
            {"name": d["name"], "status": d["status"], "class": d["type"], "instance": "", "problem": ""}
            for d in simulated_drivers()
            if d["status"] != "OK"
        ]
    rows = []
    for row in as_list(ps_json(PROBLEM_SCRIPT, timeout=240)):
        rows.append(
            {
                "name": str(row.get("FriendlyName", "") or ""),
                "status": str(row.get("Status", "") or ""),
                "class": str(row.get("Class", "") or ""),
                "instance": str(row.get("InstanceId", "") or ""),
                "problem": str(row.get("Problem", "") or ""),
            }
        )
    return rows


def backup_drivers(dest: str) -> tuple[bool, str]:
    """``pnputil /export-driver * <dest>`` — a lifesaver before a reinstall."""
    if not pf.IS_WINDOWS or pf.simulating():
        return (True, f"simulated: drivers exported to {dest}")
    rc, out, err = run_script(f"pnputil /export-driver * '{dest}'", timeout=1800)
    return (rc == 0, (out or err).strip()[:2000] or "exported")


def scan_hardware_changes() -> tuple[bool, str]:
    if not pf.IS_WINDOWS or pf.simulating():
        return (True, "simulated: hardware rescanned")
    rc, out, err = run_script("pnputil /scan-devices", timeout=600)
    return (rc == 0, (out or err).strip()[:1000] or "scan complete")


@dataclass
class StoreDriver:
    published: str  # oem12.inf
    original: str
    provider: str = ""
    class_name: str = ""
    version: str = ""
    date: str = ""


def driver_store() -> list[StoreDriver]:
    """Third-party packages sitting in the driver store."""
    if not pf.IS_WINDOWS or pf.simulating():
        from ..core.simdata import simulated_drivers

        return [
            StoreDriver(
                published=d["inf"], original=d["inf"].replace("oem", "drv"),
                provider=d["provider"], class_name=d["type"], version=d["version"], date=d["date"],
            )
            for d in simulated_drivers()
        ]
    rc, out, _ = run_script("pnputil /enum-drivers", timeout=300)
    entries: list[StoreDriver] = []
    current: dict[str, str] = {}
    for line in out.splitlines():
        line = line.strip()
        if re.match(r"^Published Name\s*:", line, re.I):
            if current:
                entries.append(_store_from_dict(current))
            current = {"published": line.split(":", 1)[1].strip()}
        elif ":" in line and current:
            key, _, value = line.partition(":")
            current[key.strip().lower()] = value.strip()
    if current:
        entries.append(_store_from_dict(current))
    return entries


def _store_from_dict(data: dict[str, str]) -> StoreDriver:
    return StoreDriver(
        published=data.get("published", ""),
        original=data.get("original name", ""),
        provider=data.get("provider name", ""),
        class_name=data.get("class name", ""),
        version=data.get("driver version", ""),
        date=data.get("driver date", ""),
    )


def remove_store_driver(published: str) -> tuple[bool, str]:
    """Remove and uninstall a driver package (advanced)."""
    if not pf.IS_WINDOWS or pf.simulating():
        return (True, f"simulated: removed {published}")
    rc, out, err = run_script(
        f"pnputil /delete-driver {published} /uninstall /force", timeout=900
    )
    return (rc == 0, (out or err).strip()[:1000] or "removed")
