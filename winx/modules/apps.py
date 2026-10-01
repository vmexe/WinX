"""Installed-app inventory, bloatware removal and the advanced uninstaller."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from ..core import platform as pf
from ..core.format import human_size
from ..core.runner import run_script
from ..core.winquery import as_list, ps_json

UNINSTALL_SCRIPT = (
    "$paths = @('HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*',"
    "'HKLM:\\SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*',"
    "'HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*'); "
    "Get-ItemProperty $paths -ErrorAction SilentlyContinue | "
    "Where-Object { $_.DisplayName -and ($_.SystemComponent -ne 1) -and ($_.ParentKeyName -eq $null) } | "
    "Select-Object DisplayName, DisplayVersion, Publisher, InstallDate, EstimatedSize, "
    "UninstallString, QuietUninstallString, PSPath | Sort-Object DisplayName"
)

APPX_SCRIPT = (
    "Get-AppxPackage -ErrorAction SilentlyContinue | "
    "Select-Object Name, PackageFullName, Version, Publisher, InstallLocation, IsFramework, NonRemovable | "
    "Where-Object { -not $_.IsFramework } | Sort-Object Name"
)


@dataclass
class App:
    name: str
    version: str = ""
    publisher: str = ""
    installed: str = ""
    size_mb: int = 0
    source: str = "Win32"  # Win32 | MSI | AppX | Store
    uninstall_id: str = ""
    uninstall_string: str = ""
    quiet_string: str = ""
    removable: bool = True

    @property
    def size_text(self) -> str:
        return human_size(self.size_mb * 1024 * 1024) if self.size_mb else "—"


# --------------------------------------------------------------------------
# bloatware knowledge base
# --------------------------------------------------------------------------
BLOAT_PATTERNS: list[tuple[str, str, str]] = [
    # (friendly name, AppX name regex, reason)
    ("3D Builder", r"^Microsoft\.3DBuilder$", "Rarely used 3D app"),
    ("3D Viewer", r"^Microsoft\.Microsoft3DViewer$", "Replaced by built-in viewer"),
    ("Alarms & Clock", r"^Microsoft\.WindowsAlarms$", "Duplicate of phone alarms"),
    ("Bing News", r"^Microsoft\.BingNews$", "Ad-driven news feed"),
    ("Bing Weather", r"^Microsoft\.BingWeather$", "Live tile weather"),
    ("Candy Crush Saga", r"^king\.com\.CandyCrush", "Pre-installed game"),
    ("Candy Crush Friends", r"^king\.com\.CandyCrushFriends", "Pre-installed game"),
    ("Clipchamp", r"^Clipchamp\.Clipchamp$", "Video editor trial"),
    ("Dev Home", r"^Microsoft\.DevHome$", "Developer dashboard"),
    ("Disney+", r"^Disney", "Streaming trial"),
    ("Dolby Access", r"^DolbyLaboratories", "Audio app, driver not affected"),
    ("Facebook", r"^Facebook", "Social app"),
    ("Feedback Hub", r"^Microsoft\.WindowsFeedbackHub$", "Telemetry-adjacent"),
    ("Get Help", r"^Microsoft\.GetHelp$", "Rarely used support app"),
    ("Get Started / Tips", r"^Microsoft\.Tips$", "Onboarding tips"),
    ("Groove Music", r"^Microsoft\.ZuneMusic$", "Superseded by Media Player"),
    ("Instagram", r"^Instagram", "Social app"),
    ("Mail & Calendar", r"^microsoft\.windowscommunicationsapps$", "Built-in mail client"),
    ("Maps", r"^Microsoft\.WindowsMaps$", "Offline maps, large download"),
    ("Messenger", r"^FacebookMessenger", "Social app"),
    ("Microsoft 365 hub", r"^Microsoft\.MicrosoftOfficeHub$", "Office upsell shortcut"),
    ("Mixed Reality Portal", r"^Microsoft\.MixedReality", "VR portal"),
    ("Movies & TV", r"^Microsoft\.ZuneVideo$", "Rarely used player"),
    ("Netflix", r"^Netflix", "Streaming trial"),
    ("News", r"^Microsoft\.News$", "Ad-driven news feed"),
    ("Office hub", r"^Microsoft\.Office", "Office upsell (check before removing)"),
    ("OneNote", r"^Microsoft\.Office\.OneNote$", "Note taking app"),
    ("Paint 3D", r"^Microsoft\.MSPaint$", "Legacy 3D paint"),
    ("People", r"^Microsoft\.People$", "Contact aggregator"),
    ("Phone Link", r"^Microsoft\.YourPhone$", "Phone mirroring"),
    ("Power Automate Desktop", r"^Microsoft\.PowerAutomateDesktop$", "Automation client"),
    ("Prime Video", r"^AmazonVideo", "Streaming trial"),
    ("Quick Assist", r"^Microsoft\.QuickAssist$", "Remote help"),
    ("Skype", r"^Microsoft\.SkypeApp$", "Superseded by Teams"),
    ("Solitaire Collection", r"^Microsoft\.SolitaireCollection$", "Ad-supported games"),
    ("Spotify", r"^SpotifyAB", "Pre-installed music app"),
    ("Sticky Notes", r"^Microsoft\.MicrosoftStickyNotes$", "Notes app"),
    ("Teams (consumer)", r"^MicrosoftTeams$", "Consumer chat"),
    ("TikTok", r"^BytedancePte", "Pre-installed social app"),
    ("To Do", r"^Microsoft\.Todos$", "Task app"),
    ("Twitter / X", r"^Twitter|^XCorp", "Social app"),
    ("Voice Recorder", r"^Microsoft\.WindowsSoundRecorder$", "Audio recorder"),
    ("Weather", r"^Microsoft\.BingWeather$", "Live tile weather"),
    ("Web Media Extensions", r"^Microsoft\.WebMediaExtensions$", "Codec pack"),
    ("Windows Phone companion", r"^Microsoft\.CommsPhone$", "Legacy companion"),
    ("Xbox extras", r"^Microsoft\.Xbox(?!GamingOverlay|GameOverlay)", "Xbox companion apps"),
    ("Xbox Game Bar", r"^Microsoft\.XboxGamingOverlay$", "Overlay (turn off instead)"),
    ("Your Phone", r"^Microsoft\.YourPhone$", "Phone mirroring"),
]


def is_bloat(name: str) -> tuple[bool, str]:
    """Match a display name *or* a package identifier against the bloat list."""
    for friendly, pattern, reason in BLOAT_PATTERNS:
        if re.search(pattern, name, re.I):
            return (True, reason)
    return (False, "")


def is_bloat_app(app: "App") -> tuple[bool, str]:
    """Bloat check for a whole :class:`App` (checks name and package id)."""
    ok, reason = is_bloat(app.name)
    if ok:
        return (ok, reason)
    if app.uninstall_id:
        return is_bloat(app.uninstall_id)
    return (False, "")


# --------------------------------------------------------------------------
# inventory
# --------------------------------------------------------------------------
def installed_apps(progress: Callable[[int, int, str], None] | None = None) -> list[App]:
    if not pf.IS_WINDOWS or pf.simulating():
        from ..core.simdata import simulated_installed_apps

        rows = simulated_installed_apps()
        if progress:
            progress(1, 1, "loaded demo app list")
        return [
            App(
                name=r["name"],
                version=r["version"],
                publisher=r["publisher"],
                size_mb=r["size_mb"],
                source=r["source"],
                uninstall_id=r["id"],
                uninstall_string=_sim_uninstall_string(r),
            )
            for r in rows
        ]

    apps: list[App] = []
    if progress:
        progress(1, 2, "reading uninstall registry keys")
    for row in as_list(ps_json(UNINSTALL_SCRIPT, timeout=300)):
        name = str(row.get("DisplayName", "")).strip()
        if not name:
            continue
        size = row.get("EstimatedSize")
        try:
            size_mb = int(size) // 1024 if size else 0
        except (TypeError, ValueError):
            size_mb = 0
        ps_path = str(row.get("PSPath", "") or "")
        key_id = ps_path.split("Uninstall\\")[-1] if "Uninstall\\" in ps_path else name
        apps.append(
            App(
                name=name,
                version=str(row.get("DisplayVersion", "") or ""),
                publisher=str(row.get("Publisher", "") or ""),
                installed=_fmt_date(row.get("InstallDate")),
                size_mb=size_mb,
                source="MSI" if "MsiExec" in str(row.get("UninstallString", "")) else "Win32",
                uninstall_id=key_id,
                uninstall_string=str(row.get("UninstallString", "") or ""),
                quiet_string=str(row.get("QuietUninstallString", "") or ""),
            )
        )

    if progress:
        progress(2, 2, "enumerating Store apps")
    for row in as_list(ps_json(APPX_SCRIPT, timeout=300)):
        name = str(row.get("Name", "")).strip()
        if not name:
            continue
        apps.append(
            App(
                name=name,
                version=str(row.get("Version", "") or ""),
                publisher=str(row.get("Publisher", "") or ""),
                size_mb=0,
                source="AppX",
                uninstall_id=str(row.get("PackageFullName", "") or ""),
                uninstall_string=f"Remove-AppxPackage '{row.get('PackageFullName','')}'",
                removable=not bool(row.get("NonRemovable")),
            )
        )

    apps.sort(key=lambda a: a.name.lower())
    return apps


def _fmt_date(raw) -> str:
    s = str(raw or "")
    if len(s) == 8 and s.isdigit():
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
    return s


def _sim_uninstall_string(row: dict) -> str:
    if row["source"] == "AppX":
        return f"Remove-AppxPackage '{row['id']}'"
    if row["source"] == "MSI":
        return f"msiexec /X{row['id']} /qn"
    return f'"{row["name"]} uninstaller"'


# --------------------------------------------------------------------------
# removal
# --------------------------------------------------------------------------
def uninstall_command(app: App) -> str:
    """A PowerShell one-liner that removes ``app`` as unattended as possible."""
    if app.source == "AppX":
        return (
            f"Get-AppxPackage -Name '{app.name}' -AllUsers -ErrorAction SilentlyContinue | "
            "Remove-AppxPackage -ErrorAction SilentlyContinue; "
            f"Get-AppxProvisionedPackage -Online | Where-Object DisplayName -eq '{app.name}' | "
            "Remove-AppxProvisionedPackage -Online -AllUsers -ErrorAction SilentlyContinue"
        )
    quiet = app.quiet_string or app.uninstall_string
    if re.match(r"^\s*msiexec", quiet or "", re.I):
        match = re.search(r"\{[0-9A-Fa-f-]+\}", quiet or "")
        if match:
            return f"Start-Process msiexec -ArgumentList '/X{match.group(0)}','/qn','/norestart' -Wait"
    if app.uninstall_id and re.match(r"^\{[0-9A-Fa-f-]+\}$", app.uninstall_id):
        return f"Start-Process msiexec -ArgumentList '/X{app.uninstall_id}','/qn','/norestart' -Wait"
    base = quiet or app.uninstall_string
    if base:
        escaped = base.replace('"', '\\"')
        return f'Start-Process cmd -ArgumentList "/c {escaped}" -Wait -ErrorAction SilentlyContinue'
    return f"winget uninstall --name '{app.name}' --accept-source-agreements"


def uninstall(app: App, remove_provisioned: bool = True) -> tuple[bool, str]:
    """Uninstall an app.  Returns ``(ok, output)``."""
    script = uninstall_command(app)
    rc, out, err = run_script(script, timeout=1800)
    text = (out or "") + (err or "")
    ok = rc == 0 and "error" not in text.lower()
    return (ok, text.strip()[:2000] or ("done" if ok else "failed"))


def uninstall_many(apps: list[App], emit: Callable[[str], None] | None = None) -> tuple[int, int]:
    emit = emit or (lambda _m: None)
    ok_count = 0
    for app in apps:
        emit(f"Removing {app.name}…")
        ok, detail = uninstall(app)
        emit("  ok" if ok else f"  failed: {detail[:200]}")
        ok_count += 1 if ok else 0
    return (ok_count, len(apps))


def winget_available() -> bool:
    if not pf.IS_WINDOWS or pf.simulating():
        return False
    rc, out, _ = run_script("(Get-Command winget -ErrorAction SilentlyContinue) -ne $null", timeout=60)
    return rc == 0 and "True" in out


def repair_store_apps() -> tuple[bool, str]:
    from .actions_data import action_by_key

    return (True, "use the Repair page") if action_by_key else (False, "")
