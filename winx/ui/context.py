"""Shared application context handed to every page."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..core import platform as pf
from ..core.backup import BackupManager
from ..core.config import Settings
from ..core.engine import Engine


@dataclass
class AppContext:
    """Everything a page needs to talk to the rest of the app."""

    engine: Engine
    settings: Settings
    backups: BackupManager

    #: emit a line into the activity log: ``log(text, level)``
    log: Callable[[str, str], None] = lambda text, level="info": None
    #: show a transient message in the status bar
    status: Callable[[str], None] = lambda text: None
    #: jump to another page by key
    navigate: Callable[[str], None] = lambda key: None
    #: ask the shell to relaunch elevated
    elevate: Callable[[], bool] = lambda: pf.relaunch_as_admin()
    #: mark a page dirty so it reloads next time it is shown
    invalidate: Callable[[str], None] = lambda key: None

    @property
    def is_admin(self) -> bool:
        return pf.is_admin()

    @property
    def simulating(self) -> bool:
        return pf.simulating()
