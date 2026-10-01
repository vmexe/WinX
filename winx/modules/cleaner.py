"""Junk-file detection and cleaning.

Cleaning is deliberately conservative:

* only well-known cache/temp/log locations are scanned,
* files that are locked by a running process are skipped, not forced,
* nothing outside the target list is ever touched,
* the scan runs incrementally so the UI can show progress and be cancelled.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from ..core import platform as pf
from ..core.format import human_size
from ..core.model import MODERATE, RISKY, SAFE, Command

# --------------------------------------------------------------------------
# target catalogue
# --------------------------------------------------------------------------


@dataclass
class CleanTarget:
    key: str
    name: str
    description: str
    paths: list[str] = field(default_factory=list)
    risk: str = SAFE
    admin: bool = False
    #: when set, cleaning runs this command instead of deleting files
    special: Command | None = None
    #: optional glob patterns (matched against the file name, lowercased)
    patterns: tuple[str, ...] = ()
    #: only remove entries older than N days (0 = any age)
    older_than_days: int = 0
    group: str = "Windows"

    def resolved_paths(self) -> list[Path]:
        out: list[Path] = []
        for raw in self.paths:
            expanded = pf.expand(raw)
            try:
                p = Path(expanded)
            except Exception:
                continue
            out.append(p)
        return out


def _browser_targets() -> list[CleanTarget]:
    local = "%LOCALAPPDATA%"
    roaming = "%APPDATA%"
    return [
        CleanTarget(
            key="chrome_cache",
            name="Google Chrome cache",
            description="Cached images, scripts and GPU shader caches.",
            paths=[
                rf"{local}\Google\Chrome\User Data\Default\Cache",
                rf"{local}\Google\Chrome\User Data\Default\Code Cache",
                rf"{local}\Google\Chrome\User Data\Default\GPUCache",
                rf"{local}\Google\Chrome\User Data\ShaderCache",
            ],
            group="Browsers",
        ),
        CleanTarget(
            key="edge_cache",
            name="Microsoft Edge cache",
            description="Chromium cache, code cache and GPU cache for Edge.",
            paths=[
                rf"{local}\Microsoft\Edge\User Data\Default\Cache",
                rf"{local}\Microsoft\Edge\User Data\Default\Code Cache",
                rf"{local}\Microsoft\Edge\User Data\Default\GPUCache",
            ],
            group="Browsers",
        ),
        CleanTarget(
            key="firefox_cache",
            name="Mozilla Firefox cache",
            description="Offline cache and startup cache for Firefox profiles.",
            paths=[rf"{local}\Mozilla\Firefox\Profiles"],
            patterns=("cache2", "startupCache"),
            group="Browsers",
        ),
        CleanTarget(
            key="brave_cache",
            name="Brave cache",
            description="Chromium cache folders used by Brave.",
            paths=[
                rf"{local}\BraveSoftware\Brave-Browser\User Data\Default\Cache",
                rf"{local}\BraveSoftware\Brave-Browser\User Data\Default\Code Cache",
            ],
            group="Browsers",
        ),
        CleanTarget(
            key="opera_cache",
            name="Opera / Vivaldi cache",
            description="Chromium cache folders used by Opera and Vivaldi.",
            paths=[
                rf"{roaming}\Opera Software\Opera Stable\Cache",
                rf"{local}\Vivaldi\User Data\Default\Cache",
            ],
            group="Browsers",
        ),
    ]


def _windows_targets() -> list[CleanTarget]:
    win = "%SystemRoot%"
    local = "%LOCALAPPDATA%"
    return [
        CleanTarget(
            key="user_temp",
            name="User temp files",
            description="%TEMP% — installers, crash leftovers and temp scratch data.",
            paths=["%TEMP%"],
        ),
        CleanTarget(
            key="windows_temp",
            name="Windows temp files",
            description="C:\\Windows\\Temp — system-wide temporary files.",
            paths=[rf"{win}\Temp"],
            admin=True,
        ),
        CleanTarget(
            key="prefetch",
            name="Prefetch files",
            description="Application prefetch data. Windows rebuilds it automatically.",
            paths=[rf"{win}\Prefetch"],
            risk=MODERATE,
            admin=True,
        ),
        CleanTarget(
            key="windows_update_cache",
            name="Windows Update cache",
            description="Downloaded updates in SoftwareDistribution\\Download.",
            paths=[rf"{win}\SoftwareDistribution\Download"],
            admin=True,
            risk=MODERATE,
        ),
        CleanTarget(
            key="delivery_optimization",
            name="Delivery Optimisation cache",
            description="Peer-to-peer update cache used to share updates on the LAN.",
            paths=[
                rf"{win}\SoftwareDistribution\DeliveryOptimization",
                rf"{win}\ServiceProfiles\NetworkService\AppData\Local\Microsoft\Windows\DeliveryOptimization",
            ],
            admin=True,
        ),
        CleanTarget(
            key="thumbnail_cache",
            name="Thumbnail & icon cache",
            description="Explorer thumbcache_*.db files. Rebuilt on demand.",
            paths=[rf"{local}\Microsoft\Windows\Explorer"],
            patterns=("thumbcache_*.db", "iconcache_*.db"),
        ),
        CleanTarget(
            key="font_cache",
            name="Font cache",
            description="Cached font data used by the font cache service.",
            paths=[rf"{win}\ServiceProfiles\LocalService\AppData\Local\FontCache"],
            admin=True,
        ),
        CleanTarget(
            key="error_reports",
            name="Windows error reports",
            description="WER report queue and archived crash reports.",
            paths=[rf"{local}\Microsoft\Windows\WER"],
        ),
        CleanTarget(
            key="crash_dumps",
            name="Crash dumps & minidumps",
            description="Kernel and user-mode memory dumps from previous crashes.",
            paths=[rf"{local}\CrashDumps", rf"{win}\Minidump", rf"{win}\MEMORY.DMP"],
            risk=MODERATE,
            admin=True,
        ),
        CleanTarget(
            key="windows_logs",
            name="Windows log files",
            description="CBS, DISM and setup logs (keeps the last 7 days).",
            paths=[rf"{win}\Logs\CBS", rf"{win}\Logs\DISM", rf"{win}\Panther"],
            patterns=("*.log", "*.cab", "*.etl"),
            admin=True,
            older_than_days=7,
        ),
        CleanTarget(
            key="defender_history",
            name="Defender scan history",
            description="Old Defender scan history and support logs.",
            paths=[r"%ProgramData%\Microsoft\Windows Defender\Scans\History"],
            admin=True,
        ),
        CleanTarget(
            key="recycle_bin",
            name="Recycle Bin",
            description="Empties the Recycle Bin on all drives.",
            special=Command(
                kind="powershell",
                script=(
                    "$ErrorActionPreference='SilentlyContinue'; "
                    "Clear-RecycleBin -DriveLetter (Get-PSDrive -PSProvider FileSystem | "
                    "Select-Object -ExpandProperty Name) -Force -ErrorAction SilentlyContinue; "
                    "'Recycle Bin emptied'"
                ),
                label="Clear-RecycleBin (all drives)",
                timeout=300,
            ),
        ),
        CleanTarget(
            key="windows_old",
            name="Previous Windows installation",
            description="Windows.old and upgrade leftovers. Removing this stops 'go back'.",
            paths=[r"C:\Windows.old", r"C:\$WINDOWS.~BT", r"C:\$WINDOWS.~WS"],
            risk=RISKY,
            admin=True,
        ),
        CleanTarget(
            key="shader_cache",
            name="Shader caches",
            description="DirectX, NVIDIA and AMD shader caches (rebuilt on demand).",
            paths=[
                rf"{local}\D3DSCache",
                rf"{local}\NVIDIA\DXCache",
                rf"{local}\NVIDIA\GLCache",
                rf"{local}\AMD\DxCache",
            ],
        ),
        CleanTarget(
            key="iis_logs",
            name="IIS / web server logs",
            description="Request logs kept by the local IIS instance, if present.",
            paths=[r"C:\inetpub\logs\LogFiles"],
            admin=True,
        ),
    ]


def _dev_targets() -> list[CleanTarget]:
    local = "%LOCALAPPDATA%"
    roaming = "%APPDATA%"
    return [
        CleanTarget(
            key="npm_cache",
            name="npm / yarn / pnpm caches",
            description="Node package manager download caches.",
            paths=[
                rf"{roaming}\npm-cache",
                rf"{local}\Yarn\Cache",
                rf"{local}\pnpm-store",
            ],
            group="Developer",
        ),
        CleanTarget(
            key="pip_cache",
            name="Python pip cache",
            description="Downloaded wheels kept by pip.",
            paths=[rf"{local}\pip\cache"],
            group="Developer",
        ),
        CleanTarget(
            key="nuget_cache",
            name="NuGet & MSBuild caches",
            description="NuGet package cache and temporary build output.",
            paths=[r"%USERPROFILE%\.nuget\packages", rf"{local}\NuGet\Cache"],
            group="Developer",
        ),
        CleanTarget(
            key="vs_temp",
            name="Visual Studio caches",
            description="Component model cache and temporary build files.",
            paths=[
                rf"{local}\Microsoft\VisualStudio",
                rf"{local}\Microsoft\VSCommon",
            ],
            patterns=("*.tmp", "*.log", "Cache*"),
            group="Developer",
        ),
        CleanTarget(
            key="chocolatey",
            name="Chocolatey / WinGet temp",
            description="Package manager download leftovers.",
            paths=[rf"{local}\Temp\chocolatey", rf"{local}\Temp\WinGet"],
            group="Developer",
        ),
    ]


def _app_targets() -> list[CleanTarget]:
    roaming = "%APPDATA%"
    local = "%LOCALAPPDATA%"
    return [
        CleanTarget(
            key="discord_cache",
            name="Discord / Slack / Teams cache",
            description="Chat app media caches — safe to clear, they re-download.",
            paths=[
                rf"{roaming}\discord\Cache",
                rf"{roaming}\discord\Code Cache",
                rf"{roaming}\Slack\Cache",
                rf"{roaming}\Microsoft\Teams\Cache",
            ],
            group="Apps",
        ),
        CleanTarget(
            key="spotify_cache",
            name="Spotify / media caches",
            description="Offline media storage and playback caches.",
            paths=[rf"{local}\Spotify\Storage", rf"{local}\Spotify\Data"],
            group="Apps",
        ),
        CleanTarget(
            key="steam_shader",
            name="Steam shader & download caches",
            description="Steam's shader pre-cache and download cache.",
            paths=[r"%ProgramFiles(x86)%\Steam\steamapps\shadercache", r"%ProgramFiles(x86)%\Steam\steamapps\downloading"],
            group="Apps",
        ),
        CleanTarget(
            key="office_cache",
            name="Microsoft Office cache",
            description="Office document cache and unsaved file recovery data older than 30 days.",
            paths=[rf"{local}\Microsoft\Office\16.0\OfficeFileCache"],
            older_than_days=30,
            group="Apps",
        ),
    ]


_DEMO_TARGETS = [
    CleanTarget(
        key="demo_cache",
        name="User cache (demo target)",
        description="Shown because WinX is running outside Windows — real junk directories.",
        paths=["~/.cache", "~/.local/share/Trash", "/tmp/winx-demo-junk"],
        group="Demo",
    ),
]


def all_targets() -> list[CleanTarget]:
    targets = [*_windows_targets(), *_browser_targets(), *_app_targets(), *_dev_targets()]
    if not pf.IS_WINDOWS or pf.simulating():
        targets = [*_DEMO_TARGETS, *targets]
    return targets


def target_by_key(key: str) -> CleanTarget | None:
    for t in all_targets():
        if t.key == key:
            return t
    return None


# --------------------------------------------------------------------------
# results
# --------------------------------------------------------------------------
@dataclass
class ScanResult:
    key: str
    name: str
    description: str
    group: str
    risk: str
    admin: bool
    size: int = 0
    files: int = 0
    dirs: int = 0
    error: str = ""
    #: True when the size cannot be measured (command based target)
    unmeasured: bool = False

    @property
    def size_text(self) -> str:
        return "—" if self.unmeasured else human_size(self.size)


def _match(name: str, patterns: tuple[str, ...]) -> bool:
    if not patterns:
        return True
    low = name.lower()
    for pat in patterns:
        pat = pat.lower()
        if pat.startswith("*") and low.endswith(pat[1:]):
            return True
        if pat.endswith("*") and low.startswith(pat[:-1]):
            return True
        if pat == low:
            return True
    return False


def _scan_path(root: Path, target: CleanTarget, result: ScanResult, is_cancelled) -> None:
    if not root.exists():
        return
    import time

    cutoff = None
    if target.older_than_days:
        cutoff = time.time() - target.older_than_days * 86400

    if root.is_file():
        try:
            st = root.stat()
            result.files += 1
            result.size += st.st_size
        except OSError:
            pass
        return

    def _walk(path: Path) -> None:
        if is_cancelled and is_cancelled():
            return
        try:
            with os.scandir(path) as it:
                entries = list(it)
        except (PermissionError, OSError):
            result.dirs += 1
            return
        for entry in entries:
            if is_cancelled and is_cancelled():
                return
            try:
                if entry.is_dir(follow_symlinks=False):
                    result.dirs += 1
                    _walk(Path(entry.path))
                else:
                    if not _match(entry.name, target.patterns):
                        continue
                    st = entry.stat(follow_symlinks=False)
                    if cutoff is not None and st.st_mtime > cutoff:
                        continue
                    result.files += 1
                    result.size += st.st_size
            except (PermissionError, OSError, FileNotFoundError):
                continue

    _walk(root)


def scan(
    targets: Iterable[CleanTarget] | None = None,
    progress: Callable[[int, int, str], None] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
) -> list[ScanResult]:
    """Measure every target; safe, read-only and cancellable."""
    targets = list(targets if targets is not None else all_targets())
    results: list[ScanResult] = []
    total = max(len(targets), 1)
    for i, target in enumerate(targets, 1):
        if is_cancelled and is_cancelled():
            break
        if progress:
            progress(i, total, target.name)
        res = ScanResult(
            key=target.key,
            name=target.name,
            description=target.description,
            group=target.group,
            risk=target.risk,
            admin=target.admin,
        )
        if target.special is not None:
            res.unmeasured = True
            results.append(res)
            continue
        try:
            for p in target.resolved_paths():
                _scan_path(p, target, res, is_cancelled)
        except Exception as exc:  # noqa: BLE001 - a bad target must not kill the scan
            res.error = str(exc)
        results.append(res)
    return results


@dataclass
class CleanOutcome:
    key: str
    name: str
    freed: int = 0
    files: int = 0
    dirs: int = 0
    skipped: int = 0
    error: str = ""
    ok: bool = True

    @property
    def freed_text(self) -> str:
        return human_size(self.freed)


def clean(
    targets: Iterable[CleanTarget],
    progress: Callable[[int, int, str], None] | None = None,
    emit: Callable[[str], None] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
) -> list[CleanOutcome]:
    """Delete the contents of the given targets.  Never forces locked files."""
    emit = emit or (lambda _m: None)
    targets = list(targets)
    outcomes: list[CleanOutcome] = []
    total = max(len(targets), 1)

    for i, target in enumerate(targets, 1):
        if is_cancelled and is_cancelled():
            break
        if progress:
            progress(i, total, target.name)
        outcome = CleanOutcome(key=target.key, name=target.name)

        if target.special is not None:
            from ..core.runner import run_stream

            emit(f"> {target.special.display()}")
            rc, err = run_stream(target.special, on_line=lambda line: emit("  " + line))
            outcome.ok = rc == 0
            outcome.error = "" if rc == 0 else (err or f"exit code {rc}")
            outcomes.append(outcome)
            continue

        import time

        cutoff = time.time() - target.older_than_days * 86400 if target.older_than_days else None

        for root in target.resolved_paths():
            if is_cancelled and is_cancelled():
                break
            if not root.exists():
                continue
            emit(f"> {root}")

            if root.is_file():
                try:
                    freed = root.stat().st_size
                    root.unlink()
                    outcome.freed += freed
                    outcome.files += 1
                except OSError as exc:
                    outcome.skipped += 1
                    outcome.error = outcome.error or str(exc)
                continue

            # files first, then prune empty directories bottom-up
            for dirpath, dirnames, filenames in os.walk(root, topdown=False):
                if is_cancelled and is_cancelled():
                    break
                for name in filenames:
                    if not _match(name, target.patterns):
                        continue
                    path = Path(dirpath) / name
                    try:
                        st = path.stat()
                        if cutoff is not None and st.st_mtime > cutoff:
                            continue
                        path.unlink()
                        outcome.freed += st.st_size
                        outcome.files += 1
                    except (PermissionError, OSError, FileNotFoundError):
                        outcome.skipped += 1
                for name in dirnames:
                    path = Path(dirpath) / name
                    try:
                        next(path.iterdir())
                    except StopIteration:
                        try:
                            path.rmdir()
                            outcome.dirs += 1
                        except OSError:
                            pass
                    except (PermissionError, OSError):
                        outcome.skipped += 1
        outcomes.append(outcome)
        emit(
            f"  {target.name}: freed {human_size(outcome.freed)}, "
            f"{outcome.files} file(s), {outcome.skipped} skipped"
        )
    return outcomes
