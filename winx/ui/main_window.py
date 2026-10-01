"""The main window: navigation rail, page stack, status bar and activity log."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from ..core import platform as pf
from .context import AppContext
from .icons import icon
from .pages.actions import ActionsPage, ToolsPage
from .pages.apps import AppsPage
from .pages.base import TabbedPage
from .pages.cleaner import CleanerPage
from .pages.dashboard import DashboardPage
from .pages.disks import DisksPage
from .pages.drivers import DriversPage
from .pages.settings import SettingsPage
from .pages.startup import StartupPage
from .pages.systeminfo import SystemInfoPage
from .pages.tweaks import TweaksPage
from .widgets import LogConsole, SearchField

NAV_GROUPS = [
    (
        "Overview",
        [("dashboard", "Dashboard", "dashboard"), ("systeminfo", "System", "monitor")],
    ),
    (
        "Cleanup",
        [("cleaner", "Cleaner", "trash"), ("apps", "Uninstaller", "box"), ("disks", "Disks", "drive")],
    ),
    (
        "Speed",
        [
            ("performance", "Performance", "bolt"),
            ("gaming", "Gaming", "gamepad"),
            ("startup", "Startup", "power"),
        ],
    ),
    (
        "Repair",
        [
            ("repair", "Repair", "wrench"),
            ("network", "Network", "globe"),
            ("drivers", "Drivers", "chip"),
        ],
    ),
    (
        "Privacy & security",
        [("privacy", "Privacy", "eye"), ("security", "Security", "security")],
    ),
    (
        "Look & tools",
        [("interface", "Interface", "sliders"), ("tools", "Tools", "toolbox")],
    ),
    ("", [("settings", "Settings", "settings")]),
]


class MainWindow(QMainWindow):
    """Hosts every page and owns the global activity log."""

    #: emitted when the theme changes so pages can repaint custom widgets
    themeChanged = Signal()

    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self.pages: dict[str, QWidget] = {}
        self.nav_buttons: dict[str, QPushButton] = {}
        self._current = "dashboard"

        self.setWindowTitle(f"WinX {__version__}")
        self.resize(1280, 860)
        self.setMinimumSize(1040, 700)

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_nav())
        root.addWidget(self._build_content(), 1)

        self._build_status_bar()
        self._goto("dashboard")

    # ------------------------------------------------------------------
    # navigation rail
    # ------------------------------------------------------------------
    def _build_nav(self) -> QFrame:
        rail = QFrame()
        rail.setObjectName("NavRail")
        rail.setFixedWidth(238)
        layout = QVBoxLayout(rail)
        layout.setContentsMargins(12, 16, 12, 12)
        layout.setSpacing(6)

        brand = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(icon("spark", self.ctx.accent, 30).pixmap(30, 30))
        brand.addWidget(logo)
        title = QLabel("WinX")
        font = QFont()
        font.setPointSize(16)
        font.setWeight(QFont.Weight.Bold)
        title.setFont(font)
        brand.addWidget(title)
        brand.addStretch(1)
        version = QLabel(f"v{__version__}")
        version.setProperty("muted", True)
        brand.addWidget(version, 0, Qt.AlignmentFlag.AlignBottom)
        layout.addLayout(brand)

        self.nav_search = SearchField("Filter menu…")
        self.nav_search.textChanged.connect(self._filter_nav)
        layout.addWidget(self.nav_search)
        layout.addSpacing(4)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        self.nav_layout = QVBoxLayout(inner)
        self.nav_layout.setContentsMargins(0, 0, 0, 0)
        self.nav_layout.setSpacing(2)

        self.nav_groups: list[tuple[QLabel, list[QPushButton]]] = []
        for group_name, entries in NAV_GROUPS:
            if group_name:
                label = QLabel(group_name.upper())
                gf = QFont()
                gf.setPointSize(8)
                gf.setWeight(QFont.Weight.Bold)
                label.setFont(gf)
                label.setProperty("muted", True)
                label.setContentsMargins(8, 10, 0, 2)
                self.nav_layout.addWidget(label)
            buttons = []
            for key, text, icon_name in entries:
                button = QPushButton(f"  {text}")
                button.setObjectName("NavButton")
                button.setIcon(icon(icon_name, self.ctx.accent, 18))
                button.clicked.connect(lambda _c=False, k=key: self._goto(k))
                button.setCursor(Qt.CursorShape.PointingHandCursor)
                self.nav_buttons[key] = button
                self.nav_layout.addWidget(button)
                buttons.append(button)
            self.nav_groups.append((label if group_name else QLabel(), buttons))
        self.nav_layout.addStretch(1)
        scroll.setWidget(inner)
        layout.addWidget(scroll, 1)

        self.admin_button = QPushButton("Run as Administrator")
        self.admin_button.setObjectName("NavButton")
        self.admin_button.setIcon(icon("verified", "#f5c451", 18))
        self.admin_button.clicked.connect(self._elevate)
        if pf.is_admin() or not pf.IS_WINDOWS:
            self.admin_button.setVisible(False)
        layout.addWidget(self.admin_button)

        self.log_button = QPushButton("Activity log")
        self.log_button.setObjectName("NavButton")
        self.log_button.setIcon(icon("terminal", self.ctx.accent, 18))
        self.log_button.setCheckable(True)
        self.log_button.setChecked(True)
        self.log_button.clicked.connect(self._toggle_log)
        layout.addWidget(self.log_button)
        return rail

    def _build_content(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.stack = QStackedWidget()
        for key, factory in PAGE_FACTORIES.items():
            page = factory(self.ctx)
            page.setObjectName("page_" + key)
            self.pages[key] = page
            self.stack.addWidget(page)
        layout.addWidget(self.stack, 1)

        self.log_console = LogConsole(placeholder="WinX activity log — every command and result appears here.")
        self.log_console.setFixedHeight(180)
        layout.addWidget(self.log_console)
        return container

    # ------------------------------------------------------------------
    def _build_status_bar(self) -> None:
        bar = self.statusBar()
        bar.setContentsMargins(10, 0, 10, 0)
        self.status_label = QLabel("Ready")
        bar.addWidget(self.status_label, 1)

        if pf.simulating():
            self._badge(bar, "SIMULATION", "#f5c451")
        if pf.IS_WINDOWS and pf.is_admin():
            self._badge(bar, "ADMINISTRATOR", "#3ecf8e")
        elif pf.IS_WINDOWS:
            self._badge(bar, "STANDARD USER", "#8b98a9")
        self._badge(bar, pf.os_display_name()[:48], "#8b98a9")

    def _badge(self, bar, text: str, color: str) -> None:
        from .widgets import Badge

        bar.addPermanentWidget(Badge(text, color))

    # ------------------------------------------------------------------
    # navigation
    # ------------------------------------------------------------------
    def _goto(self, key: str) -> None:
        page = self.pages.get(key)
        if page is None:
            return
        self._current = key
        self.stack.setCurrentWidget(page)
        for page_key, button in self.nav_buttons.items():
            selected = page_key == key
            button.setProperty("selected", "true" if selected else "false")
            button.style().polish(button)
        if hasattr(page, "on_show"):
            QTimer.singleShot(0, page.on_show)
        self.status(f"{getattr(page, 'title', key)}")
        self.ctx.settings.set("ui/last_page", key)

    def _filter_nav(self, text: str) -> None:
        needle = text.strip().lower()
        for label, buttons in self.nav_groups:
            visible = 0
            for button in buttons:
                show = not needle or needle in button.text().lower()
                button.setVisible(show)
                visible += 1 if show else 0
            label.setVisible(visible > 0 or not needle)

    def _toggle_log(self, checked: bool) -> None:
        self.log_console.setVisible(checked)

    def _elevate(self) -> None:
        if self.ctx.elevate():
            self.status("Relaunching with administrator rights…")
            QTimer.singleShot(1500, self.close)

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
        subtitle="Speed up boot times, the desktop and background resource use. Switch on what you want, then Apply — every change is reversible.",
        icon_name="bolt",
    )


def _gaming(ctx: AppContext) -> TweaksPage:
    return TweaksPage(
        ctx,
        category="gaming",
        key="gaming",
        title="Gaming",
        subtitle="Stop Windows recording, throttling and interrupting your games.",
        icon_name="gamepad",
    )


def _privacy(ctx: AppContext) -> TweaksPage:
    return TweaksPage(
        ctx,
        category="privacy",
        key="privacy",
        title="Privacy",
        subtitle="Turn off telemetry, ad tracking and the assistant features that phone home.",
        icon_name="eye",
    )


def _interface(ctx: AppContext) -> TweaksPage:
    return TweaksPage(
        ctx,
        category="interface",
        key="interface",
        title="Interface",
        subtitle="Make Explorer, the taskbar and the Start menu behave the way you want.",
        icon_name="sliders",
    )


def _network(ctx: AppContext) -> TabbedPage:
    return TabbedPage(
        ctx,
        key="network",
        title="Network",
        subtitle="Fix a broken connection, or tune the TCP/IP stack for lower latency.",
        icon_name="globe",
        tabs=[
            (
                "Repairs",
                ActionsPage(
                    ctx,
                    group="network",
                    key="network_actions",
                    title="Network repairs",
                    subtitle="Work through these in order when the internet misbehaves.",
                    icon_name="globe",
                ),
            ),
            (
                "Tweaks",
                TweaksPage(
                    ctx,
                    category="network",
                    key="network_tweaks",
                    title="Network tweaks",
                    subtitle="Lower latency and remove legacy protocols. Only change these if you know why.",
                    icon_name="globe",
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
        icon_name="security",
        tabs=[
            (
                "Scans & tools",
                ActionsPage(
                    ctx,
                    group="security",
                    key="security_actions",
                    title="Security tasks",
                    subtitle="Defender scans, firewall, encryption and activation status.",
                    icon_name="security",
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
                    icon_name="security",
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
    "repair": lambda ctx: ActionsPage(
        ctx,
        group="repair",
        key="repair",
        title="Repair",
        subtitle="Fix corrupted system files, a broken Windows image, failing updates and stuck search or icons.",
        icon_name="wrench",
    ),
    "network": _network,
    "drivers": DriversPage,
    "privacy": _privacy,
    "security": _security,
    "interface": _interface,
    "tools": ToolsPage,
    "settings": SettingsPage,
}
