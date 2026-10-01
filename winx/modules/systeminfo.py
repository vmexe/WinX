"""Hardware/OS inventory and the health check engine."""

from __future__ import annotations

import datetime as dt
import os
import platform
import socket
from typing import Callable

from ..core import platform as pf
from ..core import registry
from ..core.format import human_duration, human_size
from ..core.winquery import as_list, ps_json

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover
    psutil = None  # type: ignore


# --------------------------------------------------------------------------
# inventory
# --------------------------------------------------------------------------
def snapshot(progress: Callable[[int, int, str], None] | None = None) -> dict:
    """Everything the System Information page shows, in one dict."""
    info: dict = {
        "os": pf.os_display_name(),
        "computer": socket.gethostname(),
        "user": _username(),
        "boot_time": 0.0,
        "cpu": {},
        "memory": {},
        "gpu": [],
        "motherboard": {},
        "disks": [],
        "network": [],
        "battery": {},
        "monitors": [],
        "activation": "Unknown",
    }

    if psutil is not None:
        try:
            info["boot_time"] = float(psutil.boot_time())
        except Exception:
            info["boot_time"] = 0.0
        try:
            freq = psutil.cpu_freq()
            info["cpu"] = {
                "name": platform.processor() or _cpu_name(),
                "cores": psutil.cpu_count(logical=False) or 0,
                "threads": psutil.cpu_count(logical=True) or 0,
                "freq_max": round(freq.max / 1000, 2) if freq and freq.max else 0,
                "freq_cur": round(freq.current / 1000, 2) if freq and freq.current else 0,
            }
        except Exception:
            info["cpu"] = {}
        try:
            vm = psutil.virtual_memory()
            info["memory"] = {
                "total": vm.total,
                "available": vm.available,
                "used": vm.used,
                "percent": vm.percent,
            }
        except Exception:
            info["memory"] = {}
        try:
            info["battery"] = _battery()
        except Exception:
            info["battery"] = {}

    if not pf.IS_WINDOWS or pf.simulating():
        info.setdefault("cpu", {})
        if not info["cpu"]:
            info["cpu"] = {"name": _cpu_name(), "cores": 8, "threads": 16, "freq_max": 4.7, "freq_cur": 3.2}
        if not info["memory"]:
            info["memory"] = {"total": 32 * 1024**3, "available": 12 * 1024**3, "used": 20 * 1024**3, "percent": 62}
        info["gpu"] = [
            {"name": "NVIDIA GeForce RTX 4070", "driver": "32.0.15.6094", "memory": "12 GB", "resolution": "2560x1440@165Hz"}
        ]
        info["motherboard"] = {"manufacturer": "ASUSTeK COMPUTER INC.", "product": "ROG STRIX B650E-F", "bios": "3.10 (2024-07-02)", "serial": "SIM-SERIAL-0001"}
        info["network"] = [
            {"name": "Intel(R) Wi-Fi 6E AX211", "type": "Wireless", "ip": "192.168.1.42", "mac": "A4:5E:60:9F:11:2C", "speed": "1201 Mbps"},
            {"name": "Realtek PCIe GbE Family Controller", "type": "Ethernet", "ip": "—", "mac": "B0:25:AA:12:34:56", "speed": "1 Gbps"},
        ]
        info["monitors"] = [{"name": "DELL S2721DGF", "resolution": "2560x1440", "refresh": "165 Hz"}]
        info["activation"] = "Licensed (simulated)"
        info["battery"] = info.get("battery") or {"present": False}
        return info

    if progress:
        progress(1, 5, "processor")
    for row in as_list(ps_json("Get-CimInstance Win32_Processor | Select-Object Name, NumberOfCores, NumberOfLogicalProcessors, MaxClockSpeed", timeout=180)):
        info["cpu"] = {
            "name": str(row.get("Name", "")).strip(),
            "cores": row.get("NumberOfCores") or 0,
            "threads": row.get("NumberOfLogicalProcessors") or 0,
            "freq_max": round((row.get("MaxClockSpeed") or 0) / 1000, 2),
            "freq_cur": info["cpu"].get("freq_cur", 0),
        }
        break

    if progress:
        progress(2, 5, "graphics")
    info["gpu"] = [
        {
            "name": str(r.get("Name", "")).strip(),
            "driver": str(r.get("DriverVersion", "") or ""),
            "memory": _gpu_memory(r.get("AdapterRAM")),
            "resolution": f"{r.get('CurrentHorizontalResolution','')}x{r.get('CurrentVerticalResolution','')}"
            if r.get("CurrentHorizontalResolution")
            else "",
            "refresh": f"{r.get('CurrentRefreshRate','')} Hz" if r.get("CurrentRefreshRate") else "",
        }
        for r in as_list(
            ps_json(
                "Get-CimInstance Win32_VideoController | Select-Object Name, DriverVersion, AdapterRAM, "
                "CurrentHorizontalResolution, CurrentVerticalResolution, CurrentRefreshRate",
                timeout=180,
            )
        )
    ]

    if progress:
        progress(3, 5, "motherboard & bios")
    for row in as_list(ps_json("Get-CimInstance Win32_BaseBoard | Select-Object Manufacturer, Product, SerialNumber", timeout=180)):
        info["motherboard"] = {
            "manufacturer": str(row.get("Manufacturer", "") or "").strip(),
            "product": str(row.get("Product", "") or "").strip(),
            "serial": str(row.get("SerialNumber", "") or "").strip(),
        }
        break
    for row in as_list(ps_json("Get-CimInstance Win32_BIOS | Select-Object SMBIOSBIOSVersion, ReleaseDate", timeout=180)):
        info["motherboard"]["bios"] = f"{row.get('SMBIOSBIOSVersion','')} ({_parse_cim_date(row.get('ReleaseDate'))})".strip()
        break

    if progress:
        progress(4, 5, "network adapters")
    info["network"] = [
        {
            "name": str(r.get("name", "")),
            "type": "Wireless" if "wi-fi" in str(r.get("name", "")).lower() or "wireless" in str(r.get("name", "")).lower() else "Ethernet",
            "ip": ", ".join(r.get("ip") or []) if isinstance(r.get("ip"), list) else str(r.get("ip") or ""),
            "mac": str(r.get("mac") or ""),
            "speed": str(r.get("speed") or ""),
        }
        for r in as_list(
            ps_json(
                "Get-NetAdapter -ErrorAction SilentlyContinue | Where-Object Status -eq 'Up' | ForEach-Object { "
                "$a = $_; $ip = (Get-NetIPAddress -InterfaceIndex $a.InterfaceIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue).IPAddress; "
                "[PSCustomObject]@{ name=$a.Name; mac=$a.MacAddress; speed=$a.LinkSpeed; ip=@($ip) } }",
                timeout=180,
            )
        )
    ]

    if progress:
        progress(5, 5, "activation")
    rc, out, _ = _slmgr()
    info["activation"] = out.strip()[:120] or "Unknown"
    return info


def _username() -> str:
    return os.environ.get("USERNAME") or os.environ.get("USER") or "unknown"


def _cpu_name() -> str:
    return platform.processor() or platform.machine() or "Unknown CPU"


def _gpu_memory(raw) -> str:
    try:
        value = int(raw)
        if value > 0:
            return human_size(value)
    except (TypeError, ValueError):
        pass
    return ""


def _parse_cim_date(raw) -> str:
    s = str(raw or "")
    return s[:10] if len(s) >= 10 else s


def _slmgr():  # pragma: no cover - Windows only
    from ..core.runner import run_sync

    return run_sync(["cscript", "//nologo", r"C:\Windows\System32\slmgr.vbs", "/xpr"], timeout=120)


def _battery() -> dict:
    if psutil is None:
        return {"present": False}
    try:
        bat = psutil.sensors_battery()
    except Exception:
        return {"present": False}
    if not bat:
        return {"present": False}
    return {
        "present": True,
        "percent": round(bat.percent, 1),
        "plugged": bool(bat.power_plugged),
        "remaining": human_duration(bat.secsleft) if bat.secsleft and bat.secsleft > 0 else "—",
        "wear": "",
    }


def live_stats() -> dict:
    """Cheap stats polled every second by the dashboard."""
    out = {"cpu": 0.0, "ram": 0.0, "disk_read": 0, "disk_write": 0, "net_sent": 0, "net_recv": 0, "procs": 0}
    if psutil is None:
        return out
    try:
        out["cpu"] = psutil.cpu_percent(interval=None)
        out["ram"] = psutil.virtual_memory().percent
        io = psutil.disk_io_counters()
        if io:
            out["disk_read"] = io.read_bytes
            out["disk_write"] = io.write_bytes
        net = psutil.net_io_counters()
        if net:
            out["net_sent"] = net.bytes_sent
            out["net_recv"] = net.bytes_recv
        out["procs"] = len(psutil.pids())
    except Exception:
        pass
    return out


# --------------------------------------------------------------------------
# health checks
# --------------------------------------------------------------------------
def health_checks(
    junk_bytes: int | None = None,
    startup_count: int | None = None,
    emit: Callable[[str], None] | None = None,
) -> list[dict]:
    """A prioritised list of things that are wrong (or worth doing).

    Each row: ``{name, status, detail, fix}`` where ``status`` is
    ``fail | warn | ok | info`` and ``fix`` is an optional
    ``(label, page_key)`` pair.
    """
    emit = emit or (lambda _m: None)
    checks: list[dict] = []

    # --- disk space -----------------------------------------------------
    try:
        from . import disks as disks_mod

        vols = disks_mod.volumes()
        system = vols[0] if vols else None
        if system and system.total:
            pct = system.used_pct
            if pct >= 95:
                checks.append({"name": "System drive space", "status": "fail",
                               "detail": f"{system.drive} is {pct}% full ({system.free_text} left)",
                               "fix": ("Clean junk", "cleaner")})
            elif pct >= 85:
                checks.append({"name": "System drive space", "status": "warn",
                               "detail": f"{system.drive} is {pct}% full ({system.free_text} left)",
                               "fix": ("Analyse storage", "disks")})
            else:
                checks.append({"name": "System drive space", "status": "ok",
                               "detail": f"{system.free_text} free of {system.total_text}"})
    except Exception as exc:
        emit(f"disk check failed: {exc}")

    # --- SMART ----------------------------------------------------------
    try:
        from . import disks as disks_mod

        for row in disks_mod.smart_report():
            health = str(row.get("health", "")).lower()
            if health and health not in ("healthy", "ok"):
                checks.append({"name": f"Disk health ({row.get('disk','')})", "status": "fail",
                               "detail": f"{health.title()} — back up your data now", "fix": ("Check disks", "disks")})
    except Exception:
        pass

    # --- memory / cpu ---------------------------------------------------
    if psutil is not None:
        try:
            ram = psutil.virtual_memory().percent
            if ram >= 90:
                checks.append({"name": "Memory pressure", "status": "warn",
                               "detail": f"RAM is {ram:.0f}% used", "fix": ("Startup apps", "startup")})
            elif ram < 90:
                checks.append({"name": "Memory pressure", "status": "ok", "detail": f"RAM {ram:.0f}% used"})
        except Exception:
            pass
        try:
            cpu = psutil.cpu_percent(interval=0.4)
            if cpu >= 90:
                checks.append({"name": "CPU load", "status": "warn", "detail": f"CPU is {cpu:.0f}% busy"})
        except Exception:
            pass
        try:
            boot = dt.datetime.fromtimestamp(psutil.boot_time())
            days = (dt.datetime.now() - boot).days
            if days >= 14:
                checks.append({"name": "Uptime", "status": "info",
                               "detail": f"Not restarted for {days} days — a reboot clears leaks"})
            else:
                checks.append({"name": "Uptime", "status": "ok", "detail": human_duration((dt.datetime.now() - boot).total_seconds())})
        except Exception:
            pass

    # --- junk -----------------------------------------------------------
    if junk_bytes is not None:
        if junk_bytes >= 2 * 1024**3:
            checks.append({"name": "Junk files", "status": "warn",
                           "detail": f"{human_size(junk_bytes)} of removable junk found", "fix": ("Clean now", "cleaner")})
        elif junk_bytes > 0:
            checks.append({"name": "Junk files", "status": "info",
                           "detail": f"{human_size(junk_bytes)} of removable junk", "fix": ("Review", "cleaner")})

    # --- startup --------------------------------------------------------
    if startup_count is not None:
        if startup_count >= 12:
            checks.append({"name": "Startup programs", "status": "warn",
                           "detail": f"{startup_count} programs start with Windows", "fix": ("Trim startup", "startup")})
        else:
            checks.append({"name": "Startup programs", "status": "ok", "detail": f"{startup_count} startup entries"})

    # --- pending reboot --------------------------------------------------
    if _reboot_pending():
        checks.append({"name": "Pending reboot", "status": "warn",
                       "detail": "Windows has a restart queued (updates or a repair task)", "fix": None})

    # --- telemetry / privacy --------------------------------------------
    from ..core.engine import Engine
    from .tweaks_data import by_key

    engine = Engine()
    for key, label, page in (
        ("priv_telemetry_off", "Telemetry", "privacy"),
        ("sec_smartscreen_on", "SmartScreen", "security"),
        ("sec_rdp_off", "Remote Desktop", "security"),
    ):
        tweak = by_key(key)
        if tweak is None:
            continue
        state = engine.tweak_state(tweak)
        if state == "on":
            checks.append({"name": label, "status": "ok", "detail": f"{tweak.name} — applied"})
        elif state == "partial":
            checks.append({"name": label, "status": "warn", "detail": f"{tweak.name} — partially applied", "fix": ("Review", page)})
        else:
            checks.append({"name": label, "status": "info", "detail": f"{tweak.name} — not applied", "fix": ("Apply", page)})

    # --- Windows only probes ---------------------------------------------
    if pf.IS_WINDOWS and not pf.simulating():
        checks += _windows_health_probes(emit)

    order = {"fail": 0, "warn": 1, "info": 2, "ok": 3}
    checks.sort(key=lambda c: order.get(c["status"], 9))
    return checks


def _reboot_pending() -> bool:
    for hive, path, name in (
        ("HKLM", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing", "RebootPending"),
        ("HKLM", r"SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update", "RebootRequired"),
        ("HKLM", r"SYSTEM\CurrentControlSet\Control\Session Manager", "PendingFileRenameOperations"),
    ):
        exists, _value, _t = registry.get_value(hive, path, name)
        if exists:
            return True
    return False


def _windows_health_probes(emit) -> list[dict]:  # pragma: no cover - Windows only
    out: list[dict] = []
    rows = as_list(
        ps_json(
            "Get-MpComputerStatus | Select-Object AntivirusEnabled, RealTimeProtectionEnabled, "
            "AntivirusSignatureAge, QuickScanAge, FullScanAge",
            timeout=180,
        )
    )
    if rows:
        row = rows[0]
        av = bool(row.get("AntivirusEnabled"))
        rt = bool(row.get("RealTimeProtectionEnabled"))
        if av and rt:
            out.append({"name": "Antivirus", "status": "ok", "detail": "Defender is on with real-time protection"})
        else:
            out.append({"name": "Antivirus", "status": "fail",
                        "detail": "Real-time protection is off", "fix": ("Security page", "security")})
        try:
            sig_age = int(row.get("AntivirusSignatureAge") or 0)
            if sig_age > 7:
                out.append({"name": "Virus definitions", "status": "warn",
                            "detail": f"Signatures are {sig_age} days old", "fix": ("Security page", "security")})
        except (TypeError, ValueError):
            pass

    profiles = as_list(ps_json("Get-NetFirewallProfile | Select-Object Name, Enabled", timeout=180))
    if profiles:
        disabled = [str(p.get("Name")) for p in profiles if not p.get("Enabled")]
        if disabled:
            out.append({"name": "Firewall", "status": "warn", "detail": f"Disabled for: {', '.join(disabled)}",
                        "fix": ("Turn firewall on", "security")})
        else:
            out.append({"name": "Firewall", "status": "ok", "detail": "On for all profiles"})
    return out
