"""Registry access with an offline (simulated) fallback.

On Windows this talks to ``winreg``.  Everywhere else the same API is backed
by a JSON file so the UI can be exercised without a Windows box.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from .config import data_dir
from . import platform as pf

if pf.IS_WINDOWS:  # pragma: no cover - only on Windows
    import winreg  # type: ignore
else:  # pragma: no cover - only off Windows
    winreg = None  # type: ignore

HIVES = {
    "HKCU": "HKEY_CURRENT_USER",
    "HKLM": "HKEY_LOCAL_MACHINE",
    "HKU": "HKEY_USERS",
    "HKCR": "HKEY_CLASSES_ROOT",
    "HKCC": "HKEY_CURRENT_CONFIG",
}

_SIM_FILE = data_dir() / "sim_registry.json"


# --------------------------------------------------------------------------
# simulated hive
# --------------------------------------------------------------------------
class _SimHive:
    """A tiny JSON backed stand-in for the registry."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.data: dict[str, dict[str, dict[str, Any]]] = {}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                self.data = {}

    def save(self) -> None:
        self.path.write_text(json.dumps(self.data, indent=1), encoding="utf-8")

    @staticmethod
    def _norm(path: str) -> str:
        return path.replace("/", "\\").rstrip("\\")

    def get(self, hive: str, path: str, name: str):
        return self.data.get(hive, {}).get(self._norm(path), {}).get(name)

    def set(self, hive: str, path: str, name: str, record: dict) -> None:
        self.data.setdefault(hive, {}).setdefault(self._norm(path), {})[name] = record
        self.save()

    def delete(self, hive: str, path: str, name: str) -> None:
        bucket = self.data.get(hive, {}).get(self._norm(path), {})
        if name in bucket:
            del bucket[name]
            self.save()


_sim: _SimHive | None = None


def sim_hive() -> _SimHive:
    global _sim
    if _sim is None:
        _sim = _SimHive(_SIM_FILE)
    return _sim


def seed_simulation(defaults: dict[str, dict[str, dict[str, Any]]]) -> None:
    """Pre-populate the simulated registry (used for demos/screenshots)."""
    hive = sim_hive()
    changed = False
    for h, paths in defaults.items():
        for path, values in paths.items():
            for name, rec in values.items():
                if hive.get(h, path, name) is None:
                    hive.set(h, path, name, rec)
                    changed = True
    if changed:
        hive.save()


# --------------------------------------------------------------------------
# value typing
# --------------------------------------------------------------------------
def infer_type(value: Any) -> str:
    if isinstance(value, bool):
        return "REG_DWORD"
    if isinstance(value, int):
        return "REG_DWORD"
    if isinstance(value, bytes):
        return "REG_BINARY"
    if isinstance(value, (list, tuple)):
        return "REG_MULTI_SZ"
    if isinstance(value, str) and "%" in value:
        return "REG_EXPAND_SZ"
    return "REG_SZ"


def normalise(value: Any) -> Any:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value]
    return value


# --------------------------------------------------------------------------
# public API
# --------------------------------------------------------------------------
def get_value(hive: str, path: str, name: str) -> tuple[bool, Any, str]:
    """Return ``(exists, value, type_name)``."""
    if not pf.IS_WINDOWS or pf.simulating():
        rec = sim_hive().get(hive, path, name)
        if rec is None:
            return (False, None, "")
        return (True, rec.get("data"), rec.get("type", "REG_SZ"))
    try:  # pragma: no cover - Windows only
        root = getattr(winreg, HIVES[hive])
        with winreg.OpenKey(root, path) as key:
            data, rtype = winreg.QueryValueEx(key, name)
            return (True, data, _type_name(rtype))
    except FileNotFoundError:
        return (False, None, "")
    except Exception:
        return (False, None, "")


def set_value(hive: str, path: str, name: str, value: Any, vtype: str = "auto") -> tuple[bool, str]:
    if vtype == "auto":
        vtype = infer_type(value)
    value = normalise(value)
    if not pf.IS_WINDOWS or pf.simulating():
        sim_hive().set(hive, path, name, {"type": vtype, "data": value})
        return (True, "")
    try:  # pragma: no cover - Windows only
        root = getattr(winreg, HIVES[hive])
        with winreg.CreateKeyEx(root, path, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, name, 0, _reg_type(vtype), value)
        return (True, "")
    except PermissionError as exc:  # needs elevation
        return (False, f"access denied: {exc}")
    except OSError as exc:
        return (False, str(exc))


def delete_value(hive: str, path: str, name: str) -> tuple[bool, str]:
    if not pf.IS_WINDOWS or pf.simulating():
        sim_hive().delete(hive, path, name)
        return (True, "")
    try:  # pragma: no cover - Windows only
        root = getattr(winreg, HIVES[hive])
        with winreg.OpenKey(root, path, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, name)
        return (True, "")
    except FileNotFoundError:
        return (True, "")
    except PermissionError as exc:
        return (False, f"access denied: {exc}")
    except OSError as exc:
        return (False, str(exc))


def export_key(hive: str, path: str, dest: Path) -> tuple[bool, str]:
    """``reg export`` a whole key to ``dest`` (used for backups)."""
    if not pf.IS_WINDOWS or pf.simulating():
        snapshot: dict[str, dict[str, Any]] = {}
        root = sim_hive().data.get(hive, {})
        prefix = path.replace("/", "\\").rstrip("\\")
        for full, values in root.items():
            if full == prefix or full.startswith(prefix + "\\"):
                snapshot[full] = values
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps({"__sim__": True, "hive": hive, "keys": snapshot}, indent=1), encoding="utf-8")
        return (True, "")
    try:  # pragma: no cover - Windows only
        dest.parent.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(
            ["reg", "export", rf"{hive}\{path}", str(dest), "/y"],
            capture_output=True,
            text=True,
            timeout=120,
            creationflags=pf.no_window_flags(),
            startupinfo=pf.startupinfo(),
        )
        if proc.returncode == 0:
            return (True, "")
        return (False, (proc.stderr or proc.stdout or "reg export failed").strip())
    except Exception as exc:
        return (False, str(exc))


if winreg is not None:  # pragma: no cover - Windows only
    _TYPE_NAMES = {
        winreg.REG_SZ: "REG_SZ",
        winreg.REG_EXPAND_SZ: "REG_EXPAND_SZ",
        winreg.REG_DWORD: "REG_DWORD",
        winreg.REG_QWORD: "REG_QWORD",
        winreg.REG_BINARY: "REG_BINARY",
        winreg.REG_MULTI_SZ: "REG_MULTI_SZ",
    }

    def _type_name(rtype: int) -> str:
        return _TYPE_NAMES.get(rtype, str(rtype))

    def _reg_type(name: str) -> int:
        return {
            "REG_SZ": winreg.REG_SZ,
            "REG_EXPAND_SZ": winreg.REG_EXPAND_SZ,
            "REG_DWORD": winreg.REG_DWORD,
            "REG_QWORD": winreg.REG_QWORD,
            "REG_BINARY": winreg.REG_BINARY,
            "REG_MULTI_SZ": winreg.REG_MULTI_SZ,
        }.get(name, winreg.REG_SZ)

else:

    def _type_name(rtype: int) -> str:
        return str(rtype)

    def _reg_type(name: str) -> int:
        return 0
