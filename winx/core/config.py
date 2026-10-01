"""Application paths and persisted settings."""

from __future__ import annotations

import json
import os
from pathlib import Path

from PySide6.QtCore import QSettings

from . import platform as pf

APP_NAME = "WinX"
ORG_NAME = "vmexe"
VERSION = "1.0.0"


def _base_dir() -> Path:
    """Directory for logs, backups and the simulated registry."""
    if pf.IS_WINDOWS:
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return root / APP_NAME


def data_dir() -> Path:
    p = _base_dir()
    p.mkdir(parents=True, exist_ok=True)
    return p


def backups_dir() -> Path:
    p = data_dir() / "backups"
    p.mkdir(parents=True, exist_ok=True)
    return p


def logs_dir() -> Path:
    p = data_dir() / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def log_file() -> Path:
    return logs_dir() / "winx.log"


def resource_path(*parts: str) -> Path:
    """Absolute path to a bundled resource (works inside a onefile exe)."""
    import sys

    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return base.joinpath(*parts)


# --------------------------------------------------------------------------
# settings
# --------------------------------------------------------------------------
DEFAULTS = {
    "general/theme": "dark",               # dark | light | system
    "general/accent": "#4cc2ff",
    "general/close_to_tray": False,
    "general/check_updates": True,
    "safety/backup_enabled": True,         # export changed keys before writing
    "safety/restore_point": False,         # Checkpoint-Computer (admin only)
    "safety/confirm_each": False,          # confirm every single change
    "safety/simulate": False,              # dry-run
    "safety/show_risky": True,
    "cleaner/selected": "",
    "ui/last_page": "dashboard",
    "ui/window_geometry": "",
}


class Settings:
    """Thin typed wrapper over :class:`QSettings`."""

    def __init__(self) -> None:
        self._qs = QSettings(ORG_NAME, APP_NAME)

    # -- generic ---------------------------------------------------------
    def value(self, key: str, default=None):
        if key in DEFAULTS and default is None:
            default = DEFAULTS[key]
        return self._qs.value(key, default)

    def set(self, key: str, value) -> None:
        self._qs.setValue(key, value)

    def sync(self) -> None:
        self._qs.sync()

    # -- typed helpers ---------------------------------------------------
    def bool(self, key: str) -> bool:
        v = self.value(key)
        if isinstance(v, bool):
            return v
        return str(v).lower() in ("1", "true", "yes", "on")

    def str(self, key: str) -> str:
        return str(self.value(key, DEFAULTS.get(key, "")) or "")

    def json(self, key: str, default=None):
        raw = self.value(key, "")
        if not raw:
            return default
        try:
            return json.loads(str(raw))
        except Exception:
            return default

    def set_json(self, key: str, value) -> None:
        self.set(key, json.dumps(value))


_settings: Settings | None = None


def settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
