"""Disk health, storage analysis, duplicate and large-file finders."""

from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from ..core import platform as pf
from ..core.format import human_size
from ..core.winquery import as_list, ps_json, text

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover - optional on the dev box
    psutil = None  # type: ignore


@dataclass
class Volume:
    drive: str
    label: str = ""
    fs: str = ""
    total: int = 0
    free: int = 0
    media: str = ""          # SSD | HDD | Removable | Unknown
    health: str = "Unknown"
    smart: str = "Unknown"
    temp_c: int | None = None
    mount: str = ""
    bitlocker: str = ""

    @property
    def used(self) -> int:
        return max(0, self.total - self.free)

    @property
    def used_pct(self) -> int:
        return int(round(100 * self.used / self.total)) if self.total else 0

    @property
    def free_text(self) -> str:
        return human_size(self.free)

    @property
    def total_text(self) -> str:
        return human_size(self.total)


# PowerShell storage queries cost seconds; the answers (which disk is an SSD,
# what the controller reports as health) change essentially never while the app
# is open, so they are cached. Usage figures always come fresh from psutil.
_MEDIA_TTL = 300.0
_media_cache: tuple[float, dict[str, str], dict[str, tuple[str, int | None]]] | None = None


def _media_and_health() -> tuple[dict[str, str], dict[str, tuple[str, int | None]]]:
    """Drive letter -> media type / health, cached for ``_MEDIA_TTL`` seconds."""
    global _media_cache
    now = time.monotonic()
    if _media_cache and now - _media_cache[0] < _MEDIA_TTL:
        return _media_cache[1], _media_cache[2]

    media_by_drive: dict[str, str] = {}
    smart_by_drive: dict[str, tuple[str, int | None]] = {}
    for row in as_list(
        ps_json(
            "Get-PhysicalDisk | Select-Object FriendlyName, MediaType, HealthStatus | "
            "ForEach-Object { $d = $_; $p = Get-Disk | Where-Object { $_.FriendlyName -eq $d.FriendlyName } | "
            "Select-Object -First 1; "
            "Get-Partition -DiskNumber $p.Number -ErrorAction SilentlyContinue | "
            "Select-Object -ExpandProperty DriveLetter | ForEach-Object { "
            "[PSCustomObject]@{ Drive=$_; Media=$d.MediaType; Health=$d.HealthStatus } } }",
            timeout=240,
        )
    ):
        drive = text(row.get("Drive")).strip()
        if drive:
            media_by_drive[drive] = text(row.get("Media"))
            smart_by_drive[drive] = (text(row.get("Health")), None)

    _media_cache = (now, media_by_drive, smart_by_drive)
    return media_by_drive, smart_by_drive


def invalidate_cache() -> None:
    """Drop the cached media/health answers (used by the Disks page refresh)."""
    global _media_cache
    _media_cache = None


def volumes(fast: bool = False) -> list[Volume]:
    """List volumes with usage, media type and health where available.

    ``fast=True`` returns usage only (psutil, microseconds, no subprocess) and
    is what anything on the UI thread must use: the PowerShell storage cmdlets
    take seconds on a cold cache and would freeze the window.
    """
    if not pf.IS_WINDOWS or pf.simulating():
        from ..core.simdata import simulated_disks

        rows = simulated_disks()
        out: list[Volume] = []
        if psutil is not None:
            real = [p for p in psutil.disk_partitions() if p.fstype and "squashfs" not in p.fstype]
            for part in real:
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                except Exception:
                    continue
                out.append(
                    Volume(
                        drive=part.mountpoint,
                        label=part.device.split("/")[-1],
                        fs=part.fstype,
                        total=usage.total,
                        free=usage.free,
                        media="SSD" if "nvme" in part.device else "HDD",
                        health="Healthy",
                        smart="OK",
                        mount=part.mountpoint,
                    )
                )
        if out:
            return out
        return [
            Volume(
                drive=r["drive"], label=r["label"], fs=r["fs"], total=r["total"], free=r["free"],
                media=r["media"], health=r["health"], smart="OK" if r["smart_ok"] else "Warning",
                temp_c=r["temp_c"], mount=r["drive"],
            )
            for r in rows
        ]

    out: list[Volume] = []
    if fast:
        media_by_drive: dict[str, str] = {}
        smart_by_drive: dict[str, tuple[str, int | None]] = {}
    else:
        media_by_drive, smart_by_drive = _media_and_health()

    if psutil is not None:
        for part in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(part.mountpoint)
            except Exception:
                continue
            drive = part.mountpoint[:2].upper()
            out.append(
                Volume(
                    drive=drive,
                    label=_volume_label(drive),
                    fs=part.fstype,
                    total=usage.total,
                    free=usage.free,
                    media=media_by_drive.get(drive[0], ""),
                    health=smart_by_drive.get(drive[0], ("", None))[0] or "",
                    smart=smart_by_drive.get(drive[0], ("", None))[0] or "Unknown",
                    mount=part.mountpoint,
                )
            )
    return out


def _volume_label(drive: str) -> str:  # pragma: no cover - Windows only
    """Volume label via the Win32 API.

    This used to shell out to ``Get-Volume`` once per drive — about a second
    each, on a code path the dashboard hit every two seconds. GetVolumeInfo is
    a single syscall.
    """
    import ctypes

    buf = ctypes.create_unicode_buffer(261)
    try:
        ok = ctypes.windll.kernel32.GetVolumeInformationW(
            ctypes.c_wchar_p(f"{drive[0]}:\\"),
            buf,
            ctypes.sizeof(buf) // ctypes.sizeof(ctypes.c_wchar),
            None,
            None,
            None,
            None,
            0,
        )
    except Exception:
        return ""
    return buf.value if ok else ""


def smart_report() -> list[dict]:
    """Per-disk SMART / reliability counters."""
    if not pf.IS_WINDOWS or pf.simulating():
        from ..core.simdata import simulated_disks

        return [
            {"disk": r["drive"], "model": f"Simulated {r['media']} {r['total'] // (1024**3)}GB",
             "health": r["health"], "power_hours": 4210, "read_errors": 0, "write_errors": 0, "temp_c": r["temp_c"]}
            for r in simulated_disks()
        ]
    rows = as_list(
        ps_json(
            "Get-PhysicalDisk | ForEach-Object { $c = $_ | Get-StorageReliabilityCounter -ErrorAction SilentlyContinue; "
            "[PSCustomObject]@{ Disk=$_.FriendlyName; Media=$_.MediaType; Health=$_.HealthStatus; "
            "Hours=$c.PowerOnHours; Read=$c.ReadErrorsTotal; Write=$c.WriteErrorsTotal; Temp=$c.Temperature } }",
            timeout=240,
        )
    )
    out = []
    for row in rows:
        out.append(
            {
                "disk": text(row.get("Disk")),
                "model": text(row.get("Media")),
                "health": text(row.get("Health")),
                "power_hours": row.get("Hours"),
                "read_errors": row.get("Read"),
                "write_errors": row.get("Write"),
                "temp_c": row.get("Temp"),
            }
        )
    return out


# --------------------------------------------------------------------------
# storage analysis
# --------------------------------------------------------------------------
@dataclass
class BigEntry:
    path: str
    size: int
    is_dir: bool = False
    files: int = 0

    @property
    def size_text(self) -> str:
        return human_size(self.size)


def largest_files(
    root: str,
    top_n: int = 100,
    min_size: int = 50 * 1024 * 1024,
    progress: Callable[[int, int, str], None] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
) -> list[BigEntry]:
    """Find the biggest individual files under ``root``."""
    entries: list[BigEntry] = []
    scanned = 0
    root_path = Path(root)
    if not root_path.exists():
        return entries
    for dirpath, dirnames, filenames in os.walk(root_path):
        if is_cancelled and is_cancelled():
            break
        dirnames[:] = [d for d in dirnames if not _skip_dir(Path(dirpath) / d)]
        for name in filenames:
            if is_cancelled and is_cancelled():
                break
            path = Path(dirpath) / name
            try:
                size = path.stat().st_size
            except OSError:
                continue
            scanned += 1
            if progress and scanned % 500 == 0:
                progress(scanned, 0, str(path.parent))
            if size >= min_size:
                entries.append(BigEntry(str(path), size))
    entries.sort(key=lambda e: e.size, reverse=True)
    return entries[:top_n]


def folder_sizes(
    root: str,
    depth: int = 2,
    progress: Callable[[int, int, str], None] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
) -> list[BigEntry]:
    """Size of every directory ``depth`` levels below ``root``."""
    root_path = Path(root)
    results: list[BigEntry] = []
    if not root_path.exists():
        return results
    targets: list[Path] = [root_path]
    for _ in range(depth):
        nxt: list[Path] = []
        for t in targets:
            try:
                nxt += [p for p in t.iterdir() if p.is_dir() and not _skip_dir(p)]
            except OSError:
                continue
        targets = nxt
    total = max(len(targets), 1)
    for i, target in enumerate(targets, 1):
        if is_cancelled and is_cancelled():
            break
        if progress:
            progress(i, total, str(target))
        size, count = _dir_size(target, is_cancelled)
        results.append(BigEntry(str(target), size, True, count))
    results.sort(key=lambda e: e.size, reverse=True)
    return results


def _dir_size(path: Path, is_cancelled: Callable[[], bool] | None = None) -> tuple[int, int]:
    total = 0
    files = 0
    for dirpath, dirnames, filenames in os.walk(path):
        if is_cancelled and is_cancelled():
            break
        dirnames[:] = [d for d in dirnames if not _skip_dir(Path(dirpath) / d)]
        for name in filenames:
            try:
                total += (Path(dirpath) / name).stat().st_size
                files += 1
            except OSError:
                continue
    return (total, files)


def _skip_dir(path: Path) -> bool:
    name = path.name.lower()
    if name in {"$recycle.bin", "system volume information", "node_modules", ".git", "__pycache__"}:
        return True
    return name.startswith("winsxs")


def _hash_head(path: Path, chunk: int = 128 * 1024) -> str | None:
    try:
        with path.open("rb") as fh:
            return hashlib.md5(fh.read(chunk)).hexdigest()
    except OSError:
        return None


@dataclass
class DuplicateGroup:
    size: int
    digest: str
    paths: list[str] = field(default_factory=list)

    @property
    def wasted(self) -> int:
        return self.size * max(0, len(self.paths) - 1)

    @property
    def wasted_text(self) -> str:
        return human_size(self.wasted)


def find_duplicates(
    roots: Iterable[str],
    min_size: int = 1024 * 1024,
    progress: Callable[[int, int, str], None] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
) -> list[DuplicateGroup]:
    """Group identical files (size + partial MD5 + full MD5 confirmation)."""
    by_size: dict[int, list[Path]] = {}
    scanned = 0
    for root in roots:
        root_path = Path(root)
        if not root_path.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(root_path):
            if is_cancelled and is_cancelled():
                return []
            dirnames[:] = [d for d in dirnames if not _skip_dir(Path(dirpath) / d)]
            for name in filenames:
                path = Path(dirpath) / name
                try:
                    size = path.stat().st_size
                except OSError:
                    continue
                scanned += 1
                if progress and scanned % 300 == 0:
                    progress(scanned, 0, str(path.parent))
                if size >= min_size:
                    by_size.setdefault(size, []).append(path)

    groups: list[DuplicateGroup] = []
    candidates = [paths for paths in by_size.values() if len(paths) > 1]
    total = max(len(candidates), 1)
    for i, paths in enumerate(candidates, 1):
        if is_cancelled and is_cancelled():
            break
        if progress:
            progress(i, total, f"comparing {len(paths)} files")
        buckets: dict[str, list[Path]] = {}
        for path in paths:
            head = _hash_head(path)
            if head:
                buckets.setdefault(head, []).append(path)
        for digest, bucket in buckets.items():
            if len(bucket) < 2:
                continue
            full: dict[str, list[Path]] = {}
            for path in bucket:
                try:
                    h = hashlib.md5(path.read_bytes()).hexdigest()
                except OSError:
                    continue
                full.setdefault(h, []).append(path)
            for h, bucket2 in full.items():
                if len(bucket2) > 1:
                    groups.append(
                        DuplicateGroup(
                            size=bucket2[0].stat().st_size,
                            digest=h,
                            paths=sorted(str(p) for p in bucket2),
                        )
                    )
    groups.sort(key=lambda g: g.wasted, reverse=True)
    return groups


def optimize(drive: str, is_ssd: bool = True) -> tuple[bool, str]:
    """TRIM (SSD) or defrag (HDD) a single volume."""
    from ..core.runner import run_script

    letter = drive[0].upper()
    verb = "-ReTrim" if is_ssd else "-Defrag"
    rc, out, err = run_script(
        f"Optimize-Volume -DriveLetter {letter} {verb} -Verbose -ErrorAction Stop", timeout=3600
    )
    return (rc == 0, (out or err).strip()[:2000])


def boot_time() -> float:
    if psutil is not None:
        try:
            return float(psutil.boot_time())
        except Exception:
            pass
    return time.time() - 3600
