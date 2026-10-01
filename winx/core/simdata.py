"""Data used when WinX runs on a non-Windows host (or with ``--simulate``).

The point is not to fake being useful — it is to keep every code path
exercised so the UI, the undo logic and the reporting can be developed and
tested on any machine, and so WinX can be *demonstrated* safely.
"""

from __future__ import annotations

import json
import random

from .config import data_dir

_SIM_SERVICES_FILE = data_dir() / "sim_services.json"

DEFAULT_SERVICES: dict[str, dict[str, str]] = {
    "SysMain": {"start": "auto", "state": "RUNNING", "display": "SysMain"},
    "WSearch": {"start": "delayed-auto", "state": "RUNNING", "display": "Windows Search"},
    "DiagTrack": {"start": "auto", "state": "RUNNING", "display": "Connected User Experiences and Telemetry"},
    "dmwappushservice": {"start": "manual", "state": "STOPPED", "display": "WAP Push Message Routing Service"},
    "Spooler": {"start": "auto", "state": "RUNNING", "display": "Print Spooler"},
    "wuauserv": {"start": "manual", "state": "STOPPED", "display": "Windows Update"},
    "BITS": {"start": "delayed-auto", "state": "RUNNING", "display": "Background Intelligent Transfer Service"},
    "Fax": {"start": "manual", "state": "STOPPED", "display": "Fax"},
    "RetailDemo": {"start": "manual", "state": "STOPPED", "display": "Retail Demo Service"},
    "MapsBroker": {"start": "delayed-auto", "state": "RUNNING", "display": "Downloaded Maps Manager"},
    "lfsvc": {"start": "manual", "state": "STOPPED", "display": "Geolocation Service"},
    "PcaSvc": {"start": "auto", "state": "RUNNING", "display": "Program Compatibility Assistant Service"},
    "WerSvc": {"start": "manual", "state": "STOPPED", "display": "Windows Error Reporting Service"},
    "TabletInputService": {"start": "manual", "state": "STOPPED", "display": "Touch Keyboard and Handwriting Panel Service"},
}


def _services() -> dict[str, dict[str, str]]:
    if _SIM_SERVICES_FILE.exists():
        try:
            return json.loads(_SIM_SERVICES_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {k: dict(v) for k, v in DEFAULT_SERVICES.items()}


def _save_services(data: dict) -> None:
    _SIM_SERVICES_FILE.parent.mkdir(parents=True, exist_ok=True)
    _SIM_SERVICES_FILE.write_text(json.dumps(data, indent=1), encoding="utf-8")


def simulated_service(name: str) -> dict:
    data = _services()
    if name in data:
        s = data[name]
        return {"exists": True, "start": s["start"], "state": s["state"], "display": s["display"]}
    return {"exists": False, "start": "", "state": "", "display": name}


def set_simulated_service(name: str, start: str | None = None, state: str | None = None) -> None:
    data = _services()
    entry = data.setdefault(name, {"start": "manual", "state": "STOPPED", "display": name})
    if start:
        entry["start"] = start
    if state:
        entry["state"] = state
    _save_services(data)


def simulated_services() -> list[dict]:
    out = []
    for name, s in _services().items():
        out.append(
            {
                "name": name,
                "display": s["display"],
                "start": s["start"],
                "state": s["state"],
                "account": "LocalSystem" if name in ("SysMain", "Spooler", "BITS") else "LocalService",
                "path": rf"C:\Windows\System32\svchost.exe -k {name.lower()}",
            }
        )
    return sorted(out, key=lambda r: r["display"].lower())


# --------------------------------------------------------------------------
# command transcripts
# --------------------------------------------------------------------------
def _flat(argv: list[str]) -> str:
    return " ".join(argv).lower()


def simulate_run(argv: list[str]) -> tuple[int, str, str]:
    text = _flat(argv)
    if "sfc" in text:
        return (0, "Verification 100% complete.\nWindows Resource Protection did not find any integrity violations.\n", "")
    if "restorehealth" in text:
        return (0, "[====                       ] 20.0%\n[==========================] 100.0%\nThe restore operation completed successfully.\n", "")
    if "scanhealth" in text:
        return (0, "[==========================] 100.0%\nNo component store corruption detected.\n", "")
    if "startcomponentcleanup" in text:
        return (0, "[==========================] 100.0%\nThe operation completed successfully.\n", "")
    if "chkdsk" in text:
        return (0, "Stage 1: Examining basic file system structure ...\nWindows has scanned the file system and found no problems.\n", "")
    if "flushdns" in text:
        return (0, "Successfully flushed the DNS Resolver Cache.\n", "")
    if "winsock reset" in text:
        return (0, "Successfully reset the Winsock Catalog. You must restart the computer.\n", "")
    if "int ip reset" in text:
        return (0, "Resetting Interface Information, OK!\nRestart the computer to complete this action.\n", "")
    if "advfirewall" in text:
        return (0, "Ok.\n", "")
    if "renew" in text or "release" in text:
        return (0, "Windows IP Configuration\nEthernet adapter Ethernet:\n   IPv4 Address. . . . . . . . . . . : 192.168.1.42\n", "")
    if "powercfg" in text and "/list" in text or "powercfg" in text and "list" in text:
        schemes = (
            "Existing Power Schemes (* Active)\n"
            "Power Scheme GUID: 381b4222-f694-41f0-9685-ff5bb260df2e  (Balanced) *\n"
            "Power Scheme GUID: 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c  (High performance)\n"
            "Power Scheme GUID: a1841308-3541-4fab-bc81-f71556f20b4a  (Power saver)\n"
            "Power Scheme GUID: e9a42b02-d5df-448d-aa00-03bd147049be  (Ultimate Performance)\n"
        )
        return (0, schemes, "")
    if "powercfg" in text:
        return (0, "Power configuration updated.\n", "")
    if "checkpoint-computer" in text:
        return (0, "Restore point created: WinX checkpoint.\n", "")
    if "netsh" in text:
        return (0, "Ok.\n", "")
    if "ping" in text:
        return (0, "Reply from 1.1.1.1: bytes=32 time=14ms TTL=57 (4 packets, 0% loss)\nMinimum = 13ms, Maximum = 15ms, Average = 14ms\n", "")
    if "mpcmdrun" in text or "start-mpscan" in text:
        return (0, "Scan starting...\nScan finished.\nScanning Type: Quick\nThreats detected: 0\n", "")
    if "defrag" in text:
        return (0, "The operation completed successfully on (C:).\n", "")
    if "manage-bde" in text:
        return (0, "Conversion Status: Fully Encrypted\nPercentage Encrypted: 100.0%\n", "")
    if "driverquery" in text:
        return (0, "Module Name,Display Name,Driver Type,Link Date\nntoskrnl.exe,NT Kernel & System,Kernel,6/15/2024\n", "")
    if "pnputil" in text:
        return (0, "Driver package exported successfully.\n", "")
    if "get-appxpackage" in text or "get-appxprovisionedpackage" in text:
        return (0, "[]", "")
    if "winget" in text:
        return (0, "No installed package found matching input criteria.\n", "")
    if "wmic" in text or "get-ciminstance" in text:
        return (0, "", "")
    if "convertto-json" in text or "convertto-csv" in text:
        return (0, "[]", "")
    if "reg " in text:
        return (0, "The operation completed successfully.\n", "")
    if "schtasks" in text:
        return (0, "SUCCESS: The parameters of scheduled task have been changed.\n", "")
    if "sc " in text:
        return (0, "[SC] ChangeServiceConfig SUCCESS\n", "")
    if "fsutil" in text:
        return (0, "DisableLastAccess = 1\n", "")
    if "wsreset" in text:
        return (0, "The Store cache was cleared.\n", "")
    if "dism" in text:
        return (0, "The operation completed successfully.\n", "")
    return (0, f"[simulated] {' '.join(argv[:4])}\n", "")


def simulate_transcript(argv: list[str]) -> list[str]:
    rc, out, err = simulate_run(argv)
    text = _flat(argv)
    if "sfc" in text:
        return [
            "Beginning system scan. This process will take some time.",
            "Beginning verification phase of system scan.",
            "Verification 34% complete.",
            "Verification 67% complete.",
            "Verification 100% complete.",
            "Windows Resource Protection did not find any integrity violations.",
        ]
    if "restorehealth" in text:
        return [
            "Deployment Image Servicing and Management tool",
            "[====                       ] 20.0%",
            "[=========                  ] 38.0%",
            "[==============             ] 56.0%",
            "[====================       ] 80.0%",
            "[==========================] 100.0%",
            "The restore operation completed successfully.",
        ]
    if "chkdsk" in text:
        return [
            "Stage 1: Examining basic file system structure ...",
            "  102400 file records processed.",
            "Stage 2: Examining file name linkage ...",
            "Stage 3: Examining security descriptors ...",
            "Windows has scanned the file system and found no problems.",
        ]
    lines = [l for l in (out + err).splitlines() if l.strip()]
    return lines or ["[simulated] done"]


# --------------------------------------------------------------------------
# simulated machine inventory
# --------------------------------------------------------------------------
def simulated_installed_apps() -> list[dict]:
    return [
        {"name": "Microsoft Edge", "version": "128.0.2739.42", "publisher": "Microsoft Corporation", "size_mb": 412, "source": "AppX", "id": "Microsoft.MicrosoftEdge.Stable", "bloat": False},
        {"name": "Candy Crush Saga", "version": "1.1980.3.0", "publisher": "King.com", "size_mb": 268, "source": "AppX", "id": "king.com.CandyCrushSaga", "bloat": True},
        {"name": "TikTok", "version": "3.9.0.0", "publisher": "TikTok Pte. Ltd.", "size_mb": 187, "source": "AppX", "id": "BytedancePte.Ltd.TikTok", "bloat": True},
        {"name": "Spotify Music", "version": "1.245.0.0", "publisher": "Spotify AB", "size_mb": 221, "source": "AppX", "id": "SpotifyAB.SpotifyMusic", "bloat": True},
        {"name": "Xbox Game Bar", "version": "7.124.0.0", "publisher": "Microsoft Corporation", "size_mb": 96, "source": "AppX", "id": "Microsoft.XboxGamingOverlay", "bloat": False},
        {"name": "Your Phone", "version": "1.24022.0.0", "publisher": "Microsoft Corporation", "size_mb": 78, "source": "AppX", "id": "Microsoft.YourPhone", "bloat": False},
        {"name": "News", "version": "11.32.0.0", "publisher": "Microsoft Corporation", "size_mb": 44, "source": "AppX", "id": "Microsoft.BingNews", "bloat": True},
        {"name": "Weather", "version": "11.32.0.0", "publisher": "Microsoft Corporation", "size_mb": 38, "source": "AppX", "id": "Microsoft.BingWeather", "bloat": True},
        {"name": "Get Help", "version": "10.2405.0.0", "publisher": "Microsoft Corporation", "size_mb": 22, "source": "AppX", "id": "Microsoft.GetHelp", "bloat": True},
        {"name": "Tips", "version": "10.3.0.0", "publisher": "Microsoft Corporation", "size_mb": 14, "source": "AppX", "id": "Microsoft.Tips", "bloat": True},
        {"name": "Solitaire Collection", "version": "4.20.0.0", "publisher": "Microsoft Casual Games", "size_mb": 156, "source": "AppX", "id": "Microsoft.SolitaireCollection", "bloat": True},
        {"name": "7-Zip 24.08 (x64)", "version": "24.08", "publisher": "Igor Pavlov", "size_mb": 6, "source": "MSI", "id": "{23170F69-40C1-2702-2408-000001000000}", "bloat": False},
        {"name": "Mozilla Firefox (x64 en-US)", "version": "129.0", "publisher": "Mozilla", "size_mb": 231, "source": "Win32", "id": "Mozilla Firefox 129.0 (x64 en-US)", "bloat": False},
        {"name": "Google Chrome", "version": "128.0.6613.85", "publisher": "Google LLC", "size_mb": 498, "source": "Win32", "id": "Google Chrome", "bloat": False},
        {"name": "Visual Studio Code", "version": "1.92.2", "publisher": "Microsoft Corporation", "size_mb": 402, "source": "Win32", "id": "{EA457B21-A73B-494C-8E9B-9DB1EF0F0D8C}_is1", "bloat": False},
        {"name": "McAfee LiveSafe", "version": "16.0", "publisher": "McAfee, Inc.", "size_mb": 742, "source": "Win32", "id": "{35A3F1A8-2B71-4E17-B1B9-2F0E6B7A1A11}", "bloat": True},
    ]


def simulated_startup_items() -> list[dict]:
    return [
        {"name": "OneDrive", "command": r"C:\Users\demo\AppData\Local\Microsoft\OneDrive\OneDrive.exe /background", "location": r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run", "type": "Registry", "enabled": True, "impact": "Low", "publisher": "Microsoft"},
        {"name": "Steam", "command": r"C:\Program Files (x86)\Steam\steam.exe -silent", "location": r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run", "type": "Registry", "enabled": True, "impact": "Medium", "publisher": "Valve"},
        {"name": "Spotify", "command": r"C:\Users\demo\AppData\Roaming\Spotify\Spotify.exe", "location": r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run", "type": "Registry", "enabled": True, "impact": "Medium", "publisher": "Spotify AB"},
        {"name": "Adobe Acrobat Update", "command": r"C:\Program Files (x86)\Common Files\Adobe\ARM\1.0\AdobeARM.exe", "location": r"HKLM\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run", "type": "Registry", "enabled": True, "impact": "Low", "publisher": "Adobe"},
        {"name": "Discord", "command": r"C:\Users\demo\AppData\Local\Discord\Update.exe --processStart Discord.exe", "location": r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run", "type": "Registry", "enabled": False, "impact": "Medium", "publisher": "Discord"},
        {"name": "Realtek HD Audio Manager", "command": r"C:\Program Files\Realtek\Audio\HDA\RAVBg64.exe", "location": "Startup folder", "type": "Folder", "enabled": True, "impact": "Low", "publisher": "Realtek"},
        {"name": "GoogleUpdateTaskMachineUA", "command": r"C:\Program Files (x86)\Google\Update\GoogleUpdate.exe /ua", "location": "Task Scheduler", "type": "Task", "enabled": True, "impact": "Low", "publisher": "Google"},
        {"name": "Adobe Acrobat Update Task", "command": r"C:\Program Files (x86)\Adobe\Acrobat DC\Acrobat\AdobeARM.exe", "location": "Task Scheduler", "type": "Task", "enabled": True, "impact": "Low", "publisher": "Adobe"},
        {"name": "Microsoft Compatibility Appraiser", "command": r"C:\Windows\System32\CompatTelRunner.exe", "location": "Task Scheduler", "type": "Task", "enabled": True, "impact": "High", "publisher": "Microsoft"},
    ]


def simulated_drivers() -> list[dict]:
    return [
        {"name": "NVIDIA GeForce RTX 4070", "provider": "NVIDIA", "version": "32.0.15.6094", "date": "2024-07-30", "type": "Display", "status": "OK", "inf": "oem12.inf"},
        {"name": "Intel(R) Wi-Fi 6E AX211", "provider": "Intel Corporation", "version": "23.60.2.2", "date": "2024-03-11", "type": "Network", "status": "OK", "inf": "oem31.inf"},
        {"name": "Realtek High Definition Audio", "provider": "Realtek", "version": "6.0.9600.1", "date": "2023-11-02", "type": "Media", "status": "OK", "inf": "oem4.inf"},
        {"name": "Standard SATA AHCI Controller", "provider": "Microsoft", "version": "10.0.22621.1", "date": "2022-05-06", "type": "Storage", "status": "OK", "inf": "msahci.inf"},
        {"name": "USB Mass Storage Device", "provider": "Microsoft", "version": "10.0.22621.1", "date": "2022-05-06", "type": "USB", "status": "Error (Code 43)", "inf": "usbstor.inf"},
        {"name": "AMD Chipset SMBus", "provider": "Advanced Micro Devices", "version": "5.12.0.46", "date": "2021-08-19", "type": "System", "status": "OK", "inf": "oem22.inf"},
    ]


def simulated_event_errors() -> list[dict]:
    return [
        {"time": "2024-08-14 09:12", "source": "DistributedCOM", "id": "10016", "level": "Error", "message": "The application-specific permission settings do not grant Local Activation permission for the COM Server."},
        {"time": "2024-08-14 08:57", "source": "Kernel-Power", "id": "41", "level": "Critical", "message": "The system has rebooted without cleanly shutting down first."},
        {"time": "2024-08-13 22:03", "source": "Service Control Manager", "id": "7000", "level": "Error", "message": "The Fax service failed to start due to the following error: Access is denied."},
        {"time": "2024-08-13 21:44", "source": "disk", "id": "11", "level": "Error", "message": "The driver detected a controller error on \\Device\\Harddisk1\\DR1."},
    ]


def simulated_disks() -> list[dict]:
    return [
        {"drive": "C:", "label": "Windows", "fs": "NTFS", "total": 512 * 1024**3, "free": 87 * 1024**3, "media": "SSD", "health": "Healthy", "smart_ok": True, "temp_c": 39},
        {"drive": "D:", "label": "Data", "fs": "NTFS", "total": 1024 * 1024**3, "free": 402 * 1024**3, "media": "HDD", "health": "Healthy", "smart_ok": True, "temp_c": 34},
    ]


def seeded_registry() -> dict[str, dict[str, dict[str, dict]]]:
    """A handful of realistic starting values so switches are not all 'off'."""
    return {
        "HKCU": {
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\VisualEffects": {
                "VisualFXSetting": {"type": "REG_DWORD", "data": 1}
            },
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize": {
                "EnableTransparency": {"type": "REG_DWORD", "data": 1},
                "AppsUseLightTheme": {"type": "REG_DWORD", "data": 0},
            },
            r"Software\Microsoft\Windows\CurrentVersion\BackgroundAccessApplications": {
                "GlobalUserDisabled": {"type": "REG_DWORD", "data": 0}
            },
            r"Software\Microsoft\Windows\CurrentVersion\AdvertisingInfo": {
                "Enabled": {"type": "REG_DWORD", "data": 1}
            },
            r"Software\Microsoft\Siuf\Rules": {
                "NumberOfSIUFInPeriod": {"type": "REG_DWORD", "data": 0},
                "PeriodInNanoSeconds": {"type": "REG_DWORD", "data": 0},
            },
            r"Software\Microsoft\Windows\CurrentVersion\Search": {
                "BingSearchEnabled": {"type": "REG_DWORD", "data": 1},
                "CortanaConsent": {"type": "REG_DWORD", "data": 1},
            },
            r"Software\Microsoft\GameBar": {"AutoGameModeEnabled": {"type": "REG_DWORD", "data": 0}},
            r"Control Panel\Desktop": {"MenuShowDelay": {"type": "REG_SZ", "data": "400"}},
            r"Software\Microsoft\Windows\CurrentVersion\Privacy": {
                "TailoredExperiencesWithDiagnosticDataEnabled": {"type": "REG_DWORD", "data": 1}
            },
        },
        "HKLM": {
            r"SOFTWARE\Policies\Microsoft\Windows\DataCollection": {"AllowTelemetry": {"type": "REG_DWORD", "data": 1}},
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\DataCollection": {"AllowTelemetry": {"type": "REG_DWORD", "data": 1}},
            r"SOFTWARE\Policies\Microsoft\Windows\System": {"EnableActivityFeed": {"type": "REG_DWORD", "data": 1}},
            r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers": {"HwSchMode": {"type": "REG_DWORD", "data": 1}},
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile": {
                "SystemResponsiveness": {"type": "REG_DWORD", "data": 20},
                "NetworkThrottlingIndex": {"type": "REG_DWORD", "data": 10},
            },
        },
    }


def random_hex(n: int = 8) -> str:  # pragma: no cover - cosmetic
    return "".join(random.choice("0123456789ABCDEF") for _ in range(n))


def mac_address() -> str:
    return ":".join(f"{random.randint(0x00, 0xFF):02X}" for _ in range(6))
