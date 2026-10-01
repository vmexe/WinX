"""The main window: a standard navigation list, page stack and activity log."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QDockWidget,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QSplitter,
    QStackedWidget,
    QStyle,
    QWidget,
)

from .. import __version__
from ..core import platform as pf
from .context import AppContext
from .pages.actions import ActionsPage, ToolsPage
from .pages.apps import AppsPage
from .pages.base import Page, TabbedPage
from .pages.cleaner import CleanerPage
from .pages.dashboard import DashboardPage
from .pages.disks import DisksPage
from .pages.drivers import DriversPage
from .pages.settings import SettingsPage
from .pages.startup import StartupPage
from .pages.systeminfo import SystemInfoPage
from .pages.tweaks import TweaksPage
from .widgets import LogConsole

#: (key, label) in navigation order; "" starts a new section
NAV_ITEMS: list[tuple[str, str]] = [
    ("", "Overview"),
    ("dashboard", "Dashboard"),
    ("systeminfo", "System"),
    ("", "Clean up"),
    ("cleaner", "Cleaner"),
    ("apps", "Uninstaller"),
    ("disks", "Disks"),
    ("", "Speed"),
    ("performance", "Performance"),
    ("gaming", "Gaming"),
    ("startup", "Startup"),
    ("", "Repair"),
    ("repair", "Repair"),
    ("network", "Network"),
    ("drivers", "Drivers"),
    ("", "Privacy and security"),
    ("privacy", "Privacy"),
    ("security", "Security"),
    ("", "Other"),
    ("interface", "Interface"),
    ("tools", "Tools"),
    ("settings", "Settings"),
]


class MainWindow(QMainWindow):
    """Hosts every page and owns the global activity log."""

    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self.pages: dict[str, QWidget] = {}
        self._current = "dashboard"

        self.setWindowTitle(f"WinX {__version__}")
        self.resize(1100, 760)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.nav = QListWidget()
        self.nav.setMaximumWidth(220)
        self.nav.setMinimumWidth(150)
        for key, label in NAV_ITEMS:
            item = QListWidgetItem(label)
            if not key:
                item.setFlags(Qt.ItemFlag.NoItemFlags)   # section heading
            else:
                item.setData(Qt.ItemDataRole.UserRole, key)
            self.nav.addItem(item)
        self.nav.currentItemChanged.connect(self._nav_changed)
        splitter.addWidget(self.nav)

        # Pages are built on first visit. Constructing all fifteen up front
        # (85 tweak rows, 59 action cards, …) cost seconds of frozen window
        # before anything appeared.
        self.stack = QStackedWidget()
        splitter.addWidget(self.stack)
        splitter.setStretchFactor(1, 1)
        self.setCentralWidget(splitter)

        self._build_log_dock()
        self._build_menus()
        self._build_status_bar()
        self._goto("dashboard")

    # ------------------------------------------------------------------
    def _build_log_dock(self) -> None:
        self.log_console = LogConsole("Every command and result appears here.")
        self.log_dock = QDockWidget("Activity log", self)
        self.log_dock.setObjectName("ActivityLog")
        self.log_dock.setWidget(self.log_console)
        self.log_dock.setAllowedAreas(
            Qt.DockWidgetArea.BottomDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.log_dock)
        self.resizeDocks([self.log_dock], [150], Qt.Orientation.Vertical)

    def _build_menus(self) -> None:
        style = self.style()
        menu = self.menuBar()

        file_menu = menu.addMenu("&File")
        refresh = QAction(
            style.standardIcon(QStyle.StandardPixmap.SP_BrowserReload), "&Refresh page", self
        )
        refresh.setShortcut(QKeySequence.StandardKey.Refresh)
        refresh.triggered.connect(self._refresh_current)
        file_menu.addAction(refresh)

        if pf.IS_WINDOWS and not pf.is_admin():
            elevate = QAction(
                style.standardIcon(QStyle.StandardPixmap.SP_DialogOkButton),
                "Restart as &administrator",
                self,
            )
            elevate.triggered.connect(self._elevate)
            file_menu.addAction(elevate)

        file_menu.addSeparator()
        quit_action = QAction("E&xit", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        view_menu = menu.addMenu("&View")
        toggle_log = self.log_dock.toggleViewAction()
        toggle_log.setText("&Activity log")
        view_menu.addAction(toggle_log)

        help_menu = menu.addMenu("&Help")
        about = QAction("&About WinX", self)
        about.triggered.connect(self._about)
        help_menu.addAction(about)

    def _build_status_bar(self) -> None:
        self.status_label = QLabel("Ready")
        self.statusBar().addWidget(self.status_label, 1)

        bits = []
        if pf.simulating():
            bits.append("Simulation mode")
        if pf.IS_WINDOWS:
            bits.append("Administrator" if pf.is_admin() else "Standard user")
        bits.append(pf.os_display_name())
        self.statusBar().addPermanentWidget(QLabel(" · ".join(bits)))

    # ------------------------------------------------------------------
    # navigation
    # ------------------------------------------------------------------
    def has_page(self, key: str) -> bool:
        """True for a known page, built or not."""
        return key in PAGE_FACTORIES

    def page(self, key: str) -> QWidget | None:
        """The page for ``key``, constructing it on first use."""
        page = self.pages.get(key)
        if page is not None:
            return page
        factory = PAGE_FACTORIES.get(key)
        if factory is None:
            return None
        page = factory(self.ctx)
        page.setObjectName("page_" + key)
        self.pages[key] = page
        self.stack.addWidget(page)
        return page

    def _nav_changed(self, current: QListWidgetItem | None, _previous) -> None:
        key = current.data(Qt.ItemDataRole.UserRole) if current else None
        if key:
            self._goto(key)

    def _goto(self, key: str) -> None:
        page = self.page(key)
        if page is None:
            return
        self._current = key
        self.stack.setCurrentWidget(page)
        self._select_nav(key)
        if hasattr(page, "on_show"):
            QTimer.singleShot(0, page.on_show)
        self.status(getattr(page, "title", key))
        self.ctx.settings.set("ui/last_page", key)

    def _select_nav(self, key: str) -> None:
        for i in range(self.nav.count()):
            item = self.nav.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == key:
                if self.nav.currentItem() is not item:
                    self.nav.blockSignals(True)
                    self.nav.setCurrentItem(item)
                    self.nav.blockSignals(False)
                return

    def _refresh_current(self) -> None:
        page = self.pages.get(self._current)
        if isinstance(page, Page):
            page.invalidate()
            page.on_show()

    def _elevate(self) -> None:
        if self.ctx.elevate():
            self.status("Relaunching with administrator rights…")
            QTimer.singleShot(1500, self.close)

    def _about(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.about(
            self,
            "About WinX",
            f"<b>WinX {__version__}</b><br><br>"
            "Cleans, tunes, repairs and reports on a Windows PC.<br>"
            "Every change is previewed, backed up and reversible.<br><br>"
            f"{pf.os_display_name()}",
        )

    # ------------------------------------------------------------------
    def log(self, text: str, level: str = "info") -> None:
        self.log_console.append(text, level)

    def status(self, text: str) -> None:
        self.status_label.setText(text)


# --------------------------------------------------------------------------
# page registry
# --------------------------------------------------------------------------
def _performance(ctx: AppContext) -> TweaksPage:
    return TweaksPage(
        ctx,
        category="performance",
        key="performance",
        title="Performance",
        subtitle="Speed up boot, the desktop and background resource use. Every change is reversible.",
    )


def _gaming(ctx: AppContext) -> TweaksPage:
    return TweaksPage(
        ctx,
        category="gaming",
        key="gaming",
        title="Gaming",
        subtitle="Stop Windows recording, throttling and interrupting your games.",
    )


def _privacy(ctx: AppContext) -> TweaksPage:
    return TweaksPage(
        ctx,
        category="privacy",
        key="privacy",
        title="Privacy",
        subtitle="Turn off telemetry, ad tracking and the assistant features that phone home.",
    )


def _interface(ctx: AppContext) -> TweaksPage:
    return TweaksPage(
        ctx,
        category="interface",
        key="interface",
        title="Interface",
        subtitle="Make Explorer, the taskbar and the Start menu behave the way you want.",
    )


def _repair(ctx: AppContext) -> ActionsPage:
    return ActionsPage(
        ctx,
        group="repair",
        key="repair",
        title="Repair",
        subtitle="Fix corrupted system files, a broken Windows image, failing updates and stuck search or icons.",
    )


def _network(ctx: AppContext) -> TabbedPage:
    return TabbedPage(
        ctx,
        key="network",
        title="Network",
        subtitle="Fix a broken connection, or tune the TCP/IP stack for lower latency.",
        tabs=[
            (
                "Repairs",
                ActionsPage(
                    ctx,
                    group="network",
                    key="network_actions",
                    title="Network repairs",
                    subtitle="Work through these in order when the internet misbehaves.",
                ),
            ),
            (
                "Tweaks",
                TweaksPage(
                    ctx,
                    category="network",
                    key="network_tweaks",
                    title="Network tweaks",
                    subtitle="Lower latency and remove legacy protocols.",
                ),
            ),
        ],
    )


def _security(ctx: AppContext) -> TabbedPage:
    return TabbedPage(
        ctx,
        key="security",
        title="Security",
        subtitle="Scan for malware, then harden the settings that matter.",
        tabs=[
            (
                "Scans and tools",
                ActionsPage(
                    ctx,
                    group="security",
                    key="security_actions",
                    title="Security tasks",
                    subtitle="Defender scans, firewall, encryption and activation status.",
                ),
            ),
            (
                "Hardening",
                TweaksPage(
                    ctx,
                    category="security",
                    key="security_tweaks",
                    title="Hardening",
                    subtitle="Close the doors that malware and attackers use most often on a home PC.",
                ),
            ),
        ],
    )


PAGE_FACTORIES = {
    "dashboard": DashboardPage,
    "systeminfo": SystemInfoPage,
    "cleaner": CleanerPage,
    "apps": AppsPage,
    "disks": DisksPage,
    "performance": _performance,
    "gaming": _gaming,
    "startup": StartupPage,
    "repair": _repair,
    "network": _network,
    "drivers": DriversPage,
    "privacy": _privacy,
    "security": _security,
    "interface": _interface,
    "tools": ToolsPage,
    "settings": SettingsPage,
}
