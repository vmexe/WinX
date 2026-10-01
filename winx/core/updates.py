"""In-app update check and self-update.

WinX ships as a single ``WinX.exe``, so updating is: ask GitHub for the latest
release, download the new executable next to the running one, then hand over to
a tiny batch script that waits for this process to exit, swaps the files and
starts the new build. Nothing is replaced while it is running, and the old
executable is kept as ``WinX.exe.old`` until the next successful update.

Everything here is network/disk work: call it from a worker thread.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable

from . import platform as pf

API_LATEST = "https://api.github.com/repos/vmexe/WinX/releases/latest"
RELEASES_PAGE = "https://github.com/vmexe/WinX/releases/latest"
USER_AGENT = "WinX-updater"
ASSET_NAME = "WinX.exe"


@dataclass
class UpdateInfo:
    """What the server says the newest release is."""

    version: str = ""
    url: str = ""                 # direct download for WinX.exe
    page: str = RELEASES_PAGE
    notes: str = ""
    available: bool = False
    error: str = ""

    @property
    def can_self_update(self) -> bool:
        return bool(self.available and self.url and pf.is_frozen() and pf.IS_WINDOWS)


def parse_version(raw: str) -> tuple[int, ...]:
    """``v1.2.3`` -> ``(1, 2, 3)``; unparsable parts become 0."""
    numbers = re.findall(r"\d+", str(raw or ""))
    return tuple(int(n) for n in numbers[:4]) or (0,)


def is_newer(candidate: str, current: str) -> bool:
    a, b = parse_version(candidate), parse_version(current)
    length = max(len(a), len(b))
    a = a + (0,) * (length - len(a))
    b = b + (0,) * (length - len(b))
    return a > b


def check(current_version: str, timeout: int = 15) -> UpdateInfo:
    """Ask GitHub for the latest release. Never raises."""
    request = urllib.request.Request(
        API_LATEST, headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        return UpdateInfo(error=str(exc))

    tag = str(payload.get("tag_name") or "").strip()
    if not tag:
        return UpdateInfo(error="the release feed had no tag")

    url = ""
    for asset in payload.get("assets") or []:
        if str(asset.get("name", "")).lower() == ASSET_NAME.lower():
            url = str(asset.get("browser_download_url") or "")
            break

    return UpdateInfo(
        version=tag.lstrip("vV"),
        url=url,
        page=str(payload.get("html_url") or RELEASES_PAGE),
        notes=str(payload.get("body") or "").strip(),
        available=is_newer(tag, current_version),
    )


def download(
    info: UpdateInfo,
    progress: Callable[[int, int, str], None] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
) -> tuple[bool, str]:
    """Fetch the new executable into a temp file. Returns ``(ok, path or error)``."""
    if not info.url:
        return (False, "this release has no downloadable WinX.exe")

    progress = progress or (lambda *_a: None)
    request = urllib.request.Request(info.url, headers={"User-Agent": USER_AGENT})
    target = os.path.join(tempfile.gettempdir(), f"WinX-{info.version}.exe")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            total = int(response.headers.get("Content-Length") or 0)
            done = 0
            with open(target, "wb") as handle:
                while True:
                    if is_cancelled is not None and is_cancelled():
                        return (False, "cancelled")
                    chunk = response.read(256 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)
                    done += len(chunk)
                    progress(done, total or done, f"downloading {done // 1048576} MB")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return (False, str(exc))

    if os.path.getsize(target) < 1024 * 1024:
        return (False, "the download looks truncated")
    return (True, target)


def apply_update(new_exe: str) -> tuple[bool, str]:
    """Swap the running executable for ``new_exe`` and restart.

    Returns ``(True, "")`` when the hand-off script was launched — the caller
    should then close the application immediately.
    """
    if not pf.is_frozen():
        return (False, "self-update only works on the packaged WinX.exe")
    if not os.path.isfile(new_exe):
        return (False, "the downloaded file disappeared")

    current = os.path.abspath(sys.executable)
    script = os.path.join(tempfile.gettempdir(), "winx-update.cmd")
    body = f"""@echo off
setlocal
set "target={current}"
set "source={new_exe}"
rem wait for WinX to exit (up to ~30s)
for /l %%i in (1,1,60) do (
    >nul 2>nul (call :try_move && goto started)
    timeout /t 1 /nobreak >nul
)
goto :eof
:try_move
move /y "%target%" "%target%.old" || exit /b 1
move /y "%source%" "%target%" || (move /y "%target%.old" "%target%" & exit /b 1)
exit /b 0
:started
start "" "%target%"
del "%target%.old" >nul 2>nul
del "%~f0" >nul 2>nul
"""
    try:
        with open(script, "w", encoding="ascii", errors="ignore") as handle:
            handle.write(body)
        subprocess.Popen(
            ["cmd.exe", "/c", script],
            creationflags=pf.no_window_flags() | getattr(subprocess, "DETACHED_PROCESS", 0),
            close_fds=True,
        )
    except OSError as exc:
        return (False, str(exc))
    return (True, "")
