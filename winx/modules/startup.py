"""Startup program, service and scheduled-task manager.

Slow boots are almost always caused by what runs at logon, not by Windows
itself — this module finds those entries and lets you disable them without
deleting anything (registry values are renamed, not removed).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..core import platform as pf
from ..core import registry, services
from ..core.model import MODERATE, SAFE
from ..core.runner import run_script
from ..core.winquery import as_list, ps_json, text

RUN_KEYS = [
    ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Run"),
    ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\RunOnce"),
    ("HKLM", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"),
    ("HKLM", r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run"),
]

STARTUP_FOLDERS = [
    r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup",
    r"%ProgramData%\Microsoft\Windows\Start Menu\Programs\Startup",
]

DISABLED_PREFIX = "_WinXDisabled_"


@dataclass
class StartupItem:
    name: str
    command: str
    location: str
    type: str  # Registry | Folder | Task
    enabled: bool = True
    impact: str = "Low"
    publisher: str = ""
    hive: str = ""
    path: str = ""
    value_name: str = ""
    task_path: str = ""

    @property
    def full_task_name(self) -> str:
        return f"{self.task_path}{self.name}"

    @property
    def display_location(self) -> str:
        if self.type == "Registry":
            return rf"{self.hive}\{self.path}"
        return self.location


def _impact_for(name: str, command: str) -> str:
    blob = (name + " " + command).lower()
    heavy = ("adobe", "steam", "epic", "teams", "slack", "discord", "onedrive", "dropbox",
             "spotify", "creative cloud", "java", "update", "chrome", "edge", "skype", "zoom")
    if any(w in blob for w in heavy):
        return "Medium"
    if "system32" in blob or "windows" in blob:
        return "Low"
    return "Low"


# --------------------------------------------------------------------------
# enumeration
# --------------------------------------------------------------------------
def _from_registry() -> list[StartupItem]:
    items: list[StartupItem] = []
    for hive, path in RUN_KEYS:
        if not pf.IS_WINDOWS or pf.simulating():
            continue
        values = _read_key_values(hive, path)
        for name, data in values:
            disabled = name.startswith(DISABLED_PREFIX)
            items.append(
                StartupItem(
                    name=name.replace(DISABLED_PREFIX, "") if disabled else name,
                    command=str(data),
                    location=rf"{hive}\{path}",
                    type="Registry",
                    enabled=not disabled,
                    impact=_impact_for(name, str(data)),
                    hive=hive,
                    path=path,
                    value_name=name,
                )
            )
    return items


def _read_key_values(hive: str, path: str):  # pragma: no cover - Windows only
    import winreg

    out = []
    mapping = {
        "HKCU": winreg.HKEY_CURRENT_USER,
        "HKLM": winreg.HKEY_LOCAL_MACHINE,
        "HKU": winreg.HKEY_USERS,
    }
    try:
        with winreg.OpenKey(mapping[hive], path) as key:
            index = 0
            while True:
                try:
                    name, data, _ = winreg.EnumValue(key, index)
                    out.append((name, data))
                    index += 1
                except OSError:
                    break
    except OSError:
        pass
    return out


def _from_folders() -> list[StartupItem]:
    items: list[StartupItem] = []
    for raw in STARTUP_FOLDERS:
        folder = Path(pf.expand(raw))
        if not folder.exists():
            continue
        try:
            entries = sorted(folder.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.name.lower().endswith(".winx-disabled"):
                items.append(
                    StartupItem(
                        name=entry.name.replace(".winx-disabled", ""),
                        command=str(entry),
                        location=str(folder),
                        type="Folder",
                        enabled=False,
                        impact=_impact_for(entry.name, str(entry)),
                    )
                )
            elif entry.suffix.lower() in (".lnk", ".url", ".exe", ".bat", ".cmd"):
                items.append(
                    StartupItem(
                        name=entry.name,
                        command=str(entry),
                        location=str(folder),
                        type="Folder",
                        enabled=True,
                        impact=_impact_for(entry.name, str(entry)),
                    )
                )
    return items


_TASKS_SCRIPT = (
    "Get-ScheduledTask | Where-Object { $_.State -ne 'Disabled' } | ForEach-Object { "
    "$t = $_; $types = @($t.Triggers | ForEach-Object { $_.CimClass.CimClassName }); "
    "if ($types -contains 'MSFT_TaskLogonTrigger' -or $types -contains 'MSFT_TaskBootTrigger') { "
    "$i = $t | Get-ScheduledTaskInfo -ErrorAction SilentlyContinue; "
    "[PSCustomObject]@{ Name=$t.TaskName; Path=$t.TaskPath; State=$t.State; "
    "Command=($t.Actions | ForEach-Object { ($_.Execute + ' ' + $_.Arguments).Trim() }) -join ' | '; "
    "Publisher=$t.Author; LastRun=if($i){$i.LastRunTime}else{$null} } } } "
)


def _from_tasks() -> list[StartupItem]:
    if not pf.IS_WINDOWS or pf.simulating():
        return []
    data = ps_json(_TASKS_SCRIPT + "| Select-Object -First 200", timeout=240)
    items: list[StartupItem] = []
    for row in as_list(data):
        name = text(row.get("Name")).strip()
        if not name:
            continue
        items.append(
            StartupItem(
                name=name,
                command=text(row.get("Command")),
                location="Task Scheduler",
                type="Task",
                enabled=True,
                impact=_impact_for(name, text(row.get("Command"))),
                publisher=text(row.get("Publisher")),
                task_path=text(row.get("Path")) or "\\",
            )
        )
    return items


def enumerate_items(
    progress: Callable[[int, int, str], None] | None = None,
    emit: Callable[[str], None] | None = None,
) -> list[StartupItem]:
    """Collect registry, folder and scheduled-task startup entries."""
    emit = emit or (lambda _m: None)
    if not pf.IS_WINDOWS or pf.simulating():
        from ..core.simdata import simulated_startup_items

        rows = simulated_startup_items()
        items = [
            StartupItem(
                name=r["name"],
                command=r["command"],
                location=r["location"],
                type=r["type"],
                enabled=bool(r["enabled"]),
                impact=r["impact"],
                publisher=r.get("publisher", ""),
            )
            for r in rows
        ]
        if progress:
            progress(1, 1, "loaded demo startup entries")
        return items

    items: list[StartupItem] = []
    steps = 3
    if progress:
        progress(1, steps, "registry Run keys")
    emit("Scanning registry Run keys…")
    items += _from_registry()
    if progress:
        progress(2, steps, "startup folders")
    emit("Scanning Startup folders…")
    items += _from_folders()
    if progress:
        progress(3, steps, "scheduled tasks")
    emit("Scanning scheduled tasks…")
    items += _from_tasks()

    # de-duplicate by (type, name, command)
    seen: set[tuple[str, str, str]] = set()
    unique: list[StartupItem] = []
    for item in items:
        sig = (item.type, item.name.lower(), item.command.lower())
        if sig in seen:
            continue
        seen.add(sig)
        unique.append(item)
    unique.sort(key=lambda i: (not i.enabled, {"High": 0, "Medium": 1, "Low": 2}[i.impact], i.name.lower()))
    return unique


def services_rows() -> list[dict]:
    """Auto-starting services (excluding Microsoft core services)."""
    rows = services.list_services()
    out = []
    for row in rows:
        if row["start"] in ("auto", "delayed-auto"):
            out.append(row)
    return out


# --------------------------------------------------------------------------
# mutations
# --------------------------------------------------------------------------
def set_enabled(item: StartupItem, enabled: bool) -> tuple[bool, str]:
    if item.type == "Registry":
        return _set_registry_enabled(item, enabled)
    if item.type == "Folder":
        return _set_folder_enabled(item, enabled)
    if item.type == "Task":
        verb = "/Enable" if enabled else "/Disable"
        rc, out, err = run_script(f'schtasks /Change /TN "{item.full_task_name}" {verb}', timeout=120)
        ok = rc == 0
        return (ok, "" if ok else (err or out or "schtasks failed").strip())
    return (False, f"unsupported entry type {item.type}")


def _set_registry_enabled(item: StartupItem, enabled: bool) -> tuple[bool, str]:
    if not pf.IS_WINDOWS or pf.simulating():
        return (True, "")
    current = item.value_name
    target = current.replace(DISABLED_PREFIX, "") if enabled else DISABLED_PREFIX + current.replace(DISABLED_PREFIX, "")
    if current == target:
        return (True, "")
    exists, value, _ = registry.get_value(item.hive, item.path, current)
    if not exists:
        return (False, "entry no longer exists")
    ok, err = registry.set_value(item.hive, item.path, target, value)
    if not ok:
        return (False, err)
    ok2, err2 = registry.delete_value(item.hive, item.path, current)
    if ok2:
        item.value_name = target
    return (ok2, err2)


def _set_folder_enabled(item: StartupItem, enabled: bool) -> tuple[bool, str]:
    path = Path(item.command)
    if not path.exists():
        candidate = Path(str(item.command) + ".winx-disabled")
        if candidate.exists():
            path = candidate
        else:
            return (False, "shortcut not found")
    if enabled:
        target = path.with_name(path.name.replace(".winx-disabled", ""))
    else:
        target = path.with_name(path.name + ".winx-disabled")
    try:
        path.rename(target)
        item.command = str(target)
        return (True, "")
    except OSError as exc:
        return (False, str(exc))


def remove(item: StartupItem) -> tuple[bool, str]:
    """Permanently delete a startup entry."""
    if item.type == "Registry":
        return registry.delete_value(item.hive, item.path, item.value_name)
    if item.type == "Folder":
        try:
            Path(item.command).unlink()
            return (True, "")
        except OSError as exc:
            return (False, str(exc))
    if item.type == "Task":
        rc, out, err = run_script(f'schtasks /Delete /TN "{item.full_task_name}" /F', timeout=120)
        return (rc == 0, "" if rc == 0 else (err or out).strip())
    return (False, "unsupported entry type")


def set_service_start(name: str, start: str) -> tuple[bool, str]:
    return services.set_start(name, start)


IMPACT_ORDER = {"High": 0, "Medium": 1, "Low": 2}
RISK_OF_DISABLE = {"High": SAFE, "Medium": SAFE, "Low": MODERATE}
