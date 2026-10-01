"""Application bootstrap: settings, theme, logging, single instance, main loop."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from . import __app_name__, __version__
from .core.config import Settings, log_file
from .core import platform as pf
from .core.backup import BackupManager
from .core.console import ensure_utf8_console
from .core.engine import Engine
from .ui.context import AppContext
from .ui.theme import apply_theme


def setup_logging() -> logging.Logger:
    logger = logging.getLogger("winx")
    logger.setLevel(logging.DEBUG)
    if not logger.handlers:
        handler = RotatingFileHandler(
            log_file(), maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s"))
        logger.addHandler(handler)
    return logger


def build_application(argv: list[str]) -> QApplication:
    if hasattr(Qt, "AA_EnableHighDpiScaling"):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, "AA_UseHighDpiPixmaps"):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(argv)
    app.setApplicationName(__app_name__)
    app.setApplicationDisplayName(__app_name__)
    app.setOrganizationName("vmexe")
    app.setApplicationVersion(__version__)
    app.setStyle("Fusion")
    return app


def single_instance_guard(app_name: str = __app_name__) -> bool:
    """Return True if this is the only running instance."""
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtNetwork import QLocalServer, QLocalSocket

    socket = QLocalSocket()
    socket.connectToServer(app_name)
    if socket.waitForConnected(300):
        socket.close()
        return False
    server = QLocalServer()
    QLocalServer.removeServer(app_name)
    server.listen(app_name)
    # keep references alive for the lifetime of the process
    QCoreApplication.instance().setProperty("winx_instance_server", server)
    return True


class WinX:
    """Wires the core objects together and owns the main window."""

    def __init__(self, argv: list[str] | None = None):
        self.argv = list(argv if argv is not None else sys.argv)
        self.logger = setup_logging()
        self.app = build_application(self.argv)
        self.settings = Settings()
        self.engine = Engine()
        self.backups = BackupManager()
        self._apply_theme()

        self.window = None
        self.ctx = AppContext(
            engine=self.engine,
            settings=self.settings,
            backups=self.backups,
            palette=self.palette,
            log=self._log,
            status=self._status,
            navigate=self._navigate,
            elevate=pf.relaunch_as_admin,
            refresh_theme=self._apply_theme_refresh,
        )

    # -- theme -----------------------------------------------------------
    def _apply_theme(self) -> None:
        theme = (self.settings.str("general/theme") or "dark").lower()
        accent = self.settings.str("general/accent") or None
        self.palette = apply_theme(self.app, theme, accent)

    def _apply_theme_refresh(self) -> None:
        self._apply_theme()
        if self.window:
            self.window.setStyleSheet("")
            self.window.status(f"Theme: {self.palette.name}")

    # -- plumbing --------------------------------------------------------
    def _log(self, text: str, level: str = "info") -> None:
        if self.window is not None:
            self.window.log(text, level)
        self.logger.info(text) if level != "error" else self.logger.error(text)

    def _status(self, text: str) -> None:
        if self.window is not None:
            self.window.status(text)

    def _navigate(self, key: str) -> None:
        if self.window is not None:
            self.window._goto(key)

    # -- lifecycle -------------------------------------------------------
    def show(self) -> None:
        from .core.simdata import seeded_registry
        from .core.registry import seed_simulation

        if pf.simulating():
            seed_simulation(seeded_registry())

        from .ui.main_window import MainWindow

        self.window = MainWindow(self.ctx)
        self.window.themeChanged.connect(lambda: None)
        last = self.settings.str("ui/last_page")
        if last and self.window.has_page(last):
            self.window._goto(last)
        self.window.show()

    def exec(self) -> int:
        return self.app.exec()


def run(argv: list[str] | None = None) -> int:
    """Entry point used by ``python -m winx`` and ``main.py``."""
    ensure_utf8_console()
    argv = list(argv if argv is not None else sys.argv)
    if "--version" in argv:
        print(f"WinX {__version__}")
        return 0

    app = WinX(argv)
    if "--no-single-instance" not in argv and not single_instance_guard():
        print("WinX is already running.")
        return 0
    app.show()
    return app.exec()
