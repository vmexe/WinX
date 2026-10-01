"""One place to update everything: installed programs, Store apps, Windows.

Three independent sources, each optional and each failing quietly:

* **winget** (`winget upgrade`) covers desktop programs and anything the
  Microsoft Store manages through the package manager.
* **Microsoft Store** updates are triggered through the Store's own update
  scan, because that is the only supported way to do it.
* **Windows Update** is read through the Windows Update COM API from
  PowerShell — no third-party module required — and installed with the same
  API when WinX is running elevated.

Everything here shells out, so call it from a worker thread.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

from ..core import platform as pf
from ..core.runner import run_script, run_stream
from ..core.winquery import as_list, ps_json, text

#: Windows Update, read through the COM API that the Settings app uses
WU_SEARCH = (
    "$s = New-Object -ComObject Microsoft.Update.Session; "
    "$sr = $s.CreateUpdateSearcher(); "
    "$r = $sr.Search('IsInstalled=0 and IsHidden=0'); "
    "$r.Updates | ForEach-Object { [pscustomobject]@{ "
    "Title=$_.Title; "
    "KB=($_.KBArticleIDs -join ','); "
    "Size=$_.MaxDownloadSize; "
    "Severity=$_.MsrcSeverity; "
    "Mandatory=$_.IsMandatory; "
    "RebootRequired=$_.InstallationBehavior.RebootBehavior } }"
)

WU_HISTORY = (
    "$s = New-Object -ComObject Microsoft.Update.Session; "
    "$sr = $s.CreateUpdateSearcher(); "
    "$count = $sr.GetTotalHistoryCount(); "
    "if ($count -gt 0) { $sr.QueryHistory(0, [Math]::Min($count, 25)) | "
    "ForEach-Object { [pscustomobject]@{ Title=$_.Title; Date=$_.Date; "
    "Result=$_.ResultCode } } }"
)

STORE_SCAN = (
    "Get-CimInstance -Namespace 'Root\\cimv2\\mdm\\dmmap' "
    "-ClassName 'MDM_EnterpriseModernAppManagement_AppManagement01' | "
    "Invoke-CimMethod -MethodName UpdateScanMethod"
)

RESULT_TEXT = {0: "not started", 1: "in progress", 2: "succeeded", 3: "succeeded with errors",
               4: "failed", 5: "cancelled"}


@dataclass
class Update:
    """One updatable thing, whatever its source."""

    name: str
    current: str = ""
    available: str = ""
    source: str = "winget"          # winget | store | windows
    identifier: str = ""
    size: int = 0
    note: str = ""
    needs_reboot: bool = False
    needs_admin: bool = False
    icon_path: str = ""
    tags: list[str] = field(default_factory=list)

    @property
    def version_text(self) -> str:
        if self.current and self.available:
            return f"{self.current} → {self.available}"
        return self.available or self.current or ""

    @property
    def source_text(self) -> str:
        return {"winget": "Program", "store": "Store app", "windows": "Windows"}.get(
            self.source, self.source
        )


# --------------------------------------------------------------------------
# winget
# --------------------------------------------------------------------------
def winget_available() -> bool:
    if not pf.IS_WINDOWS or pf.simulating():
        return False
    rc, out, _err = run_script(
        "(Get-Command winget -ErrorAction SilentlyContinue) -ne $null", timeout=60
    )
    return rc == 0 and "True" in out


def _parse_winget_table(output: str) -> list[Update]:
    """Parse ``winget upgrade``'s fixed-width table.

    winget has no stable machine-readable output for *upgrade*, so the column
    positions in the header row are used instead of splitting on whitespace —
    program names contain spaces and so do some versions.
    """
    lines = [line.rstrip() for line in (output or "").splitlines()]
    header_index = next(
        (
            i
            for i, line in enumerate(lines)
            if re.match(r"^\s*Name\s+Id\s+Version\s+Available", line)
        ),
        -1,
    )
    if header_index < 0:
        return []

    header = lines[header_index]
    columns = {}
    for field_name in ("Name", "Id", "Version", "Available", "Source"):
        found = header.find(field_name)
        if found >= 0:
            columns[field_name] = found
    order = sorted(columns.items(), key=lambda kv: kv[1])

    updates: list[Update] = []
    for line in lines[header_index + 1 :]:
        if not line.strip() or set(line.strip()) <= {"-"}:
            continue
        if re.match(r"^\s*\d+\s+upgrades? available", line, re.IGNORECASE):
            continue
        values = {}
        for position, (field_name, start) in enumerate(order):
            end = order[position + 1][1] if position + 1 < len(order) else len(line)
            values[field_name] = line[start:end].strip()
        name = values.get("Name", "")
        identifier = values.get("Id", "")
        if not name or not identifier or name == "Name":
            continue
        updates.append(
            Update(
                name=name,
                current=values.get("Version", ""),
                available=values.get("Available", ""),
                source="winget",
                identifier=identifier,
                note=values.get("Source", ""),
            )
        )
    return updates


def winget_upgrades(progress: Callable[..., None] | None = None) -> list[Update]:
    """Programs winget can update."""
    if progress:
        progress(1, 3, "asking winget what is out of date")
    if not pf.IS_WINDOWS or pf.simulating():
        from ..core.simdata import simulated_updates

        return [Update(**row) for row in simulated_updates() if row["source"] == "winget"]
    if not winget_available():
        return []
    rc, out, _err = run_script(
        "winget upgrade --include-unknown --accept-source-agreements", timeout=240
    )
    if rc != 0 and not out:
        return []
    return _parse_winget_table(out)


def upgrade_app(
    identifier: str,
    emit: Callable[[str], None] | None = None,
    cancel: Callable[[], bool] | None = None,
) -> tuple[bool, str]:
    """Update one program through winget, streaming its output."""
    emit = emit or (lambda _line: None)
    if not pf.IS_WINDOWS or pf.simulating():
        emit(f"Would run: winget upgrade --id {identifier}")
        return (True, "simulated")
    argv = [
        "winget", "upgrade", "--id", identifier, "--silent",
        "--accept-package-agreements", "--accept-source-agreements",
        "--disable-interactivity",
    ]
    rc, detail = run_stream(argv, on_line=emit, timeout=3600, cancel=cancel)
    return (rc == 0, detail or ("updated" if rc == 0 else f"winget exited with {rc}"))


# --------------------------------------------------------------------------
# Microsoft Store
# --------------------------------------------------------------------------
def store_scan(emit: Callable[[str], None] | None = None) -> tuple[bool, str]:
    """Ask the Store to look for app updates and install them."""
    emit = emit or (lambda _line: None)
    if not pf.IS_WINDOWS or pf.simulating():
        emit("Would ask the Microsoft Store to check for app updates")
        return (True, "simulated")
    rc, _out, err = run_script(STORE_SCAN, timeout=180)
    if rc == 0:
        return (True, "the Store is downloading any app updates in the background")
    return (False, err.strip() or "the Store update scan is not available on this edition")


# --------------------------------------------------------------------------
# Windows Update
# --------------------------------------------------------------------------
def windows_updates(progress: Callable[..., None] | None = None) -> list[Update]:
    """Updates Windows itself is offering."""
    if progress:
        progress(2, 3, "asking Windows Update")
    if not pf.IS_WINDOWS or pf.simulating():
        from ..core.simdata import simulated_updates

        return [Update(**row) for row in simulated_updates() if row["source"] == "windows"]

    rows = as_list(ps_json(WU_SEARCH, timeout=300))
    updates: list[Update] = []
    for row in rows:
        title = text(row.get("Title")).strip()
        if not title:
            continue
        try:
            size = int(row.get("Size") or 0)
        except (TypeError, ValueError):
            size = 0
        kb = text(row.get("KB")).strip()
        updates.append(
            Update(
                name=title,
                available=f"KB{kb}" if kb and not kb.startswith("KB") else kb,
                source="windows",
                identifier=kb or title,
                size=size,
                note=text(row.get("Severity")),
                needs_reboot=str(row.get("RebootRequired")) not in ("0", "", "None"),
                needs_admin=True,
            )
        )
    return updates


def windows_update_history() -> list[dict]:
    """What Windows Update has installed recently."""
    if not pf.IS_WINDOWS or pf.simulating():
        from ..core.simdata import simulated_update_history

        return simulated_update_history()
    rows = as_list(ps_json(WU_HISTORY, timeout=180))
    history = []
    for row in rows:
        history.append(
            {
                "title": text(row.get("Title")),
                "date": text(row.get("Date"))[:19].replace("T", " "),
                "result": RESULT_TEXT.get(_as_int(row.get("Result")), "unknown"),
            }
        )
    return history


def install_windows_updates(
    emit: Callable[[str], None] | None = None,
    progress: Callable[..., None] | None = None,
    cancel: Callable[[], bool] | None = None,
) -> tuple[bool, str]:
    """Download and install everything Windows Update is offering.

    Needs administrator rights; without them the call is refused up front
    rather than failing halfway through.
    """
    emit = emit or (lambda _line: None)
    if not pf.IS_WINDOWS or pf.simulating():
        emit("Would download and install the pending Windows updates")
        return (True, "simulated")
    if not pf.is_admin():
        return (False, "installing Windows updates needs administrator rights")

    script = (
        "$s = New-Object -ComObject Microsoft.Update.Session; "
        "$sr = $s.CreateUpdateSearcher(); "
        "$r = $sr.Search('IsInstalled=0 and IsHidden=0'); "
        "if ($r.Updates.Count -eq 0) { 'nothing to install'; exit 0 }; "
        "$dl = $s.CreateUpdateDownloader(); $dl.Updates = $r.Updates; "
        "Write-Output 'downloading...'; $null = $dl.Download(); "
        "$inst = $s.CreateUpdateInstaller(); $inst.Updates = $r.Updates; "
        "Write-Output 'installing...'; $res = $inst.Install(); "
        "Write-Output ('result: ' + $res.ResultCode + ' reboot: ' + $res.RebootRequired)"
    )
    if progress:
        progress(0, 0, "Windows Update is working…")
    rc, out, err = run_script(script, timeout=7200)
    for line in (out or "").splitlines():
        if line.strip():
            emit(line.strip())
    if rc != 0:
        return (False, err.strip() or "Windows Update failed")
    return (True, (out or "").strip().splitlines()[-1] if out.strip() else "finished")


def all_updates(progress: Callable[..., None] | None = None) -> list[Update]:
    """Everything that can be updated, from every source."""
    updates: list[Update] = []
    try:
        updates.extend(winget_upgrades(progress=progress))
    except Exception:  # noqa: BLE001 - one broken source must not hide the others
        pass
    try:
        updates.extend(windows_updates(progress=progress))
    except Exception:  # noqa: BLE001
        pass
    if progress:
        progress(3, 3, "done")
    updates.sort(key=lambda u: (u.source != "windows", u.name.lower()))
    return updates


def _as_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1
