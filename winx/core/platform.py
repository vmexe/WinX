"""Platform detection, privilege handling and simulation mode."""

from __future__ import annotations

import ctypes
import os
import platform
import subprocess
import sys
from functools import lru_cache

IS_WINDOWS = os.name == "nt"

#: Simulation is the default on non-Windows hosts but can be forced on any
#: platform through the ``--simulate`` flag or the settings page.
FORCED_SIMULATE = "--simulate" in sys.argv
SIMULATING = (not IS_WINDOWS) or FORCED_SIMULATE


def set_simulating(value: bool) -> None:
    """Enable/disable simulation mode at runtime (used by the settings page)."""
    global SIMULATING
    SIMULATING = bool(value) or (not IS_WINDOWS)


def simulating() -> bool:
    return SIMULATING


# --------------------------------------------------------------------------
# privileges
# --------------------------------------------------------------------------
def is_admin() -> bool:
    """True when the process runs with administrator rights."""
    if not IS_WINDOWS:
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def can_elevate() -> bool:
    """True when we are *not* elevated but could be (i.e. running on Windows)."""
    return IS_WINDOWS and not is_admin()


def relaunch_as_admin() -> bool:
    """Relaunch the current process with a UAC prompt.  Returns True on success."""
    if not IS_WINDOWS or is_admin():
        return False
    try:
        params = " ".join(f'"{a}"' for a in sys.argv[1:])
        executable = sys.executable
        if is_frozen():
            executable = sys.executable  # onefile exe: same binary
        rc = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", executable, params, None, 1
        )
        return int(rc) > 32
    except Exception:
        return False


def is_frozen() -> bool:
    """True when running from a PyInstaller/Nuitka bundle."""
    return bool(getattr(sys, "frozen", False))


# --------------------------------------------------------------------------
# host description
# --------------------------------------------------------------------------
@lru_cache(maxsize=1)
def os_display_name() -> str:
    if IS_WINDOWS:
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Windows NT\CurrentVersion",
            ) as key:
                product = winreg.QueryValueEx(key, "ProductName")[0]
                build = winreg.QueryValueEx(key, "CurrentBuildNumber")[0]
                ubr = winreg.QueryValueEx(key, "UBR")[0]
                return f"{product} (build {build}.{ubr})"
        except Exception:
            return f"Windows {platform.release()} ({platform.version()})"
    return f"{platform.system()} {platform.release()} — simulation mode"


@lru_cache(maxsize=1)
def windows_version() -> tuple[int, int, int]:
    """(major, minor, build) of the running Windows, or (0, 0, 0)."""
    if not IS_WINDOWS:
        return (0, 0, 0)
    try:
        v = platform.version().split(".")
        return (int(v[0]), int(v[1]), int(v[2]) if len(v) > 2 else 0)
    except Exception:
        return (0, 0, 0)


@lru_cache(maxsize=1)
def is_windows_11() -> bool:
    return IS_WINDOWS and windows_version()[2] >= 22000


@lru_cache(maxsize=1)
def powershell_exe() -> str:
    """Path to a usable PowerShell host.

    Cached: probing spawns a real PowerShell process (~0.5s), and this is
    called for *every* command we build. Without the cache a single
    ``ps_json()`` costs two process launches instead of one.
    """
    if not IS_WINDOWS:
        return "pwsh"
    for candidate in ("powershell", "pwsh"):
        try:
            subprocess.run(
                [candidate, "-NoProfile", "-Command", "exit"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
                creationflags=_no_window(),
            )
            return candidate
        except Exception:
            continue
    return "powershell"


def _no_window() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if IS_WINDOWS else 0


def no_window_flags() -> int:
    return _no_window()


def startupinfo():
    """A subprocess.STARTUPINFO that hides the console window on Windows."""
    if not IS_WINDOWS:
        return None
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0  # SW_HIDE
    return si


def open_with_shell(path: str) -> bool:
    """Open a file/folder/URL with the default handler."""
    try:
        if IS_WINDOWS:
            os.startfile(path)  # type: ignore[attr-defined]
            return True
        subprocess.run(["xdg-open", path], check=False, timeout=10)
        return True
    except Exception:
        return False


def win_dir() -> str:
    """Value of %SystemRoot% (``C:\\Windows`` normally)."""
    return os.environ.get("SystemRoot", r"C:\Windows") if IS_WINDOWS else "/tmp/winx-sim/Windows"


def program_files() -> str:
    return os.environ.get("ProgramFiles", r"C:\Program Files")


def expand(path: str) -> str:
    """Expand environment variables *and* ``~``, tolerating unknown ones."""
    step1 = os.path.expandvars(path)
    step2 = os.path.expanduser(step1)
    return os.path.expandvars(step2)
