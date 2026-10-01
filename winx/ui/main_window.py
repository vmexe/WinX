"""The main window: a standard navigation list, page stack and activity log."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import (
    QCompleter,
    QDockWidget,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QStyle,
    QToolBar,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
)

from .. import __version__
from ..core import platform as pf
from ..core.workers import submit
from . import appearance, sysicons
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

#: navigation groups: (group label, [(page key, label), …]).
#: Groups are real, collapsible headings — never disabled list rows.
NAV_GROUPS: list[tuple[str, list[tuple[str, str]]]] = [
    ("Overview", [
        ("dashboard", "Dashboard"),
        ("systeminfo", "System"),
    ]),
    ("Clean up", [
        ("cleaner", "Cleaner"),
        ("apps", "Uninstaller"),
        ("disks", "Disks"),
    ]),
    ("Speed", [
        ("performance", "Performance"),
        ("gaming", "Gaming"),
        ("startup", "Startup"),
    ]),
    ("Repair", [
        ("repair", "Repair"),
        ("network", "Network"),
        ("drivers", "Drivers"),
    ]),
    ("Privacy and security", [
        ("privacy", "Privacy"),
        ("security", "Security"),
    ]),
    ("Other", [
        ("interface", "Interface"),
        ("tools", "Tools"),
        ("settings", "Settings"),
    ]),
]

#: flat (key, label) view of the navigation, kept for the search index
NAV_ITEMS: list[tuple[str, str]] = [
    item for _group, items in NAV_GROUPS for item in items
]

#: tweak category / action group -> the page that shows it
TWEAK_PAGE = {
    "performance": "performance",
    "gaming": "gaming",
    "privacy": "privacy",
    "security": "security",
    "network": "network",
    "interface": "interface",
}
ACTION_PAGE = {
    "repair": "repair",
    "network": "network",
    "security": "security",
    "tools": "tools",
    "maintenance": "tools",
}


def search_index() -> list[tuple[str, str, str]]:
    """Everything the toolbar search can jump to: ``(label, page key, term)``.

    Pages, tweaks and tasks all end up in one list so a user who types
    "telemetry" or "defragment" lands on the right page with the page's own
    filter already applied.
    """
    from ..modules import actions_data, tweaks_data

    entries: list[tuple[str, str, str]] = []
    for key, label in NAV_ITEMS:
        entries.append((label, key, ""))
    for tweak in tweaks_data.ALL_TWEAKS:
        page = TWEAK_PAGE.get(tweak.category)
        if page:
            entries.append((f"{tweak.name} — {label_for(page)}", page, tweak.name))
    for action in actions_data.ALL_ACTIONS:
        page = ACTION_PAGE.get(action.group)
        if page:
            entries.append((f"{action.name} — {label_for(page)}", page, action.name))
    return entries


def label_for(key: str) -> str:
    for page_key, label in NAV_ITEMS:
        if page_key == key:
            return label
    return key


class MainWindow(QMainWindow):
    """Hosts every page and owns the global activity log."""

    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self.pages: dict[str, QWidget] = {}
        self._current = "dashboard"

        self.setWindowTitle(f"WinX {__version__}")
        self.setMinimumSize(1100, 720)
        self.resize(1500, 950)
        self._restore_geometry()

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter = splitter

        self.nav = self._build_nav()
        splitter.addWidget(self.nav)

        # Pages are built on first visit. Constructing all fifteen up front
        # (85 tweak rows, 59 action cards, …) cost seconds of frozen window
        # before anything appeared.
        self.stack = QStackedWidget()
        splitter.addWidget(self.stack)
        splitter.setStretchFactor(1, 1)
        self.setCentralWidget(splitter)

        self._build_log_dock()
        self._build_toolbar()
        self._build_menus()
        self._build_status_bar()
        self._goto("dashboard")

        self._cache_timer = QTimer(self)
        self._cache_timer.setInterval(30_000)
        self._cache_timer.timeout.connect(self._tick_cache_label)
        self._cache_timer.start()

        if self.ctx.settings.bool("general/check_updates") and not pf.simulating():
            QTimer.singleShot(4000, lambda: self.check_for_updates(quiet=True))

    # ------------------------------------------------------------------
    def _build_nav(self) -> QTreeWidget:
        """A collapsible tree instead of a list with dead, greyed-out rows."""
        nav = QTreeWidget()
        nav.setHeaderHidden(True)
        nav.setRootIsDecorated(True)
        nav.setUniformRowHeights(True)
        nav.setIndentation(14)
        nav.setIconSize(QSize(20, 20))
        nav.setMaximumWidth(300)
        nav.setMinimumWidth(190)
        nav.setExpandsOnDoubleClick(False)

        for group_label, items in NAV_GROUPS:
            group = QTreeWidgetItem([group_label])
            group.setFirstColumnSpanned(True)
            font = group.font(0)
            font.setBold(True)
            group.setFont(0, font)
            nav.addTopLevelItem(group)
            for key, label in items:
                child = QTreeWidgetItem([label])
                child.setData(0, Qt.ItemDataRole.UserRole, key)
                child.setIcon(0, sysicons.page_icon(key))
                group.addChild(child)
            group.setExpanded(True)

        nav.currentItemChanged.connect(self._nav_changed)
        nav.itemClicked.connect(self._nav_clicked)
        return nav

    def _build_toolbar(self) -> None:
        """One toolbar: refresh, and a search box that finds anything."""
        style = self.style()
        bar = QToolBar("Main", self)
        bar.setObjectName("MainToolBar")
        bar.setMovable(False)
        bar.setIconSize(QSize(20, 20))
        bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.addToolBar(bar)

        refresh = QAction(
            style.standardIcon(QStyle.StandardPixmap.SP_BrowserReload), "Refresh", self
        )
        refresh.setToolTip("Read this page's data again (F5)")
        refresh.triggered.connect(self._refresh_current)
        bar.addAction(refresh)

        spacer = QWidget()
        spacer.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        bar.addWidget(spacer)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search WinX — pages, tweaks and tasks (Ctrl+F)")
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(360)
        self.search.setMaximumWidth(520)

        self._search_entries = search_index()
        completer = QCompleter([label for label, _key, _term in self._search_entries], self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        completer.setMaxVisibleItems(12)
        completer.activated.connect(self._search_chosen)
        self.search.setCompleter(completer)
        self.search.returnPressed.connect(lambda: self._search_chosen(self.search.text()))
        bar.addWidget(self.search)

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

        find = QAction("&Find anything", self)
        find.setShortcut(QKeySequence.StandardKey.Find)
        find.triggered.connect(self.focus_search)
        view_menu.addAction(find)

        view_menu.addSeparator()
        appearance_menu = view_menu.addMenu("&Appearance")
        group = QActionGroup(self)
        group.setExclusive(True)
        saved = appearance.current(self.ctx.settings)
        for value, label in appearance.CHOICES:
            action = QAction(label, self, checkable=True)
            action.setChecked(value == saved)
            action.setEnabled(appearance.supported() or value == "system")
            action.triggered.connect(lambda _checked=False, v=value: self.set_color_scheme(v))
            group.addAction(action)
            appearance_menu.addAction(action)
        self.appearance_actions = {
            value: action for (value, _label), action in zip(appearance.CHOICES, group.actions())
        }

        help_menu = menu.addMenu("&Help")
        updates = QAction("Check for &updates…", self)
        updates.triggered.connect(lambda: self.check_for_updates(quiet=False))
        help_menu.addAction(updates)
        help_menu.addSeparator()
        about = QAction("&About WinX", self)
        about.triggered.connect(self._about)
        help_menu.addAction(about)

    # ------------------------------------------------------------------
    def set_color_scheme(self, value: str) -> None:
        """Light / dark / follow Windows, applied immediately."""
        self.ctx.settings.set(appearance.SETTING_KEY, value)
        if appearance.apply(value):
            self.status(f"Appearance: {dict(appearance.CHOICES).get(value, value)}")
        else:
            self.status("This Qt build follows the Windows light/dark setting")
        action = getattr(self, "appearance_actions", {}).get(value)
        if action is not None and not action.isChecked():
            action.setChecked(True)
        settings_page = self.pages.get("settings")
        if settings_page is not None and hasattr(settings_page, "sync_appearance"):
            settings_page.sync_appearance(value)

    # ------------------------------------------------------------------
    # updates
    # ------------------------------------------------------------------
    def check_for_updates(self, quiet: bool = False) -> None:
        from ..core import updates

        if not quiet:
            self.status("Checking for updates…")
        worker = submit(updates.check, __version__)
        worker.signals.result.connect(lambda info: self._on_update_info(info, quiet))
        worker.signals.error.connect(
            lambda message: None if quiet else self.on_update_error(message)
        )

    def on_update_error(self, message: str) -> None:
        self.status(f"Update check failed: {message}")
        self.log(f"Update check failed: {message}", "warn")

    def _on_update_info(self, info, quiet: bool) -> None:
        if info.error:
            if not quiet:
                self.on_update_error(info.error)
            return
        if not info.available:
            self.status(f"WinX {__version__} is up to date")
            if not quiet:
                QMessageBox.information(
                    self, "No update", f"WinX {__version__} is the latest version."
                )
            return

        self.log(f"WinX {info.version} is available", "info")
        self.status(f"WinX {info.version} is available")
        notes = (info.notes or "").strip().splitlines()[:8]
        detail = "\n".join(notes)
        box = QMessageBox(self)
        box.setWindowTitle("Update available")
        box.setIcon(QMessageBox.Icon.Information)
        box.setText(f"WinX {info.version} is available (you have {__version__}).")
        if detail:
            box.setInformativeText(detail)
        if info.can_self_update:
            install = box.addButton("Download and install", QMessageBox.ButtonRole.AcceptRole)
        else:
            install = None
            box.addButton("Open the download page", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Later", QMessageBox.ButtonRole.RejectRole)
        box.exec()

        clicked = box.clickedButton()
        if clicked is None or box.buttonRole(clicked) != QMessageBox.ButtonRole.AcceptRole:
            return
        if install is not None and clicked is install:
            self._download_update(info)
        else:
            pf.open_with_shell(info.page)

    def _download_update(self, info) -> None:
        from ..core import updates

        self.status(f"Downloading WinX {info.version}…")
        worker = submit(updates.download, info)
        worker.signals.progress.connect(lambda d, t, m: self.status(f"Update: {m}"))
        worker.signals.result.connect(lambda payload: self._on_update_downloaded(payload, info))
        worker.signals.error.connect(self.on_update_error)

    def _on_update_downloaded(self, payload, info) -> None:
        from ..core import updates

        ok, detail = payload
        if not ok:
            self.on_update_error(detail)
            return
        answer = QMessageBox.question(
            self,
            "Install update",
            f"WinX {info.version} has been downloaded.\n\n"
            "WinX will close, swap in the new version and start again. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer != QMessageBox.StandardButton.Yes:
            self.status(f"Update saved to {detail}")
            return
        started, error = updates.apply_update(detail)
        if not started:
            self.on_update_error(error)
            QMessageBox.warning(self, "Update", f"Could not install the update:\n\n{error}")
            return
        self.status("Restarting into the new version…")
        QTimer.singleShot(400, self.close)

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

    def _nav_changed(self, current: QTreeWidgetItem | None, _previous) -> None:
        key = current.data(0, Qt.ItemDataRole.UserRole) if current else None
        if key:
            self._goto(key)

    def _nav_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        """Clicking a group heading folds it away instead of doing nothing."""
        if item.data(0, Qt.ItemDataRole.UserRole):
            return
        item.setExpanded(not item.isExpanded())

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
        for i in range(self.nav.topLevelItemCount()):
            group = self.nav.topLevelItem(i)
            for j in range(group.childCount()):
                item = group.child(j)
                if item.data(0, Qt.ItemDataRole.UserRole) == key:
                    if self.nav.currentItem() is not item:
                        self.nav.blockSignals(True)
                        group.setExpanded(True)
                        self.nav.setCurrentItem(item)
                        self.nav.blockSignals(False)
                    return

    # ------------------------------------------------------------------
    # search
    # ------------------------------------------------------------------
    def _search_chosen(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        lowered = text.lower()
        match = None
        for label, key, term in self._search_entries:
            if label.lower() == lowered:
                match = (key, term)
                break
        if match is None:                      # free text: best substring hit
            for label, key, term in self._search_entries:
                if lowered in label.lower():
                    match = (key, term)
                    break
        if match is None:
            self.status(f"Nothing in WinX matches “{text}”")
            return

        key, term = match
        self._goto(key)
        page = self.pages.get(key)
        if term and hasattr(page, "focus_search"):
            page.focus_search(term)
        self.search.clear()

    def focus_search(self) -> None:
        self.search.setFocus()
        self.search.selectAll()

    def _tick_cache_label(self) -> None:
        page = self.pages.get(self._current)
        if isinstance(page, Page):
            page.update_cache_label()

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
    def _restore_geometry(self) -> None:
        saved = self.ctx.settings.value("ui/window_geometry", "")
        if isinstance(saved, (bytes, bytearray)) and saved:
            self.restoreGeometry(saved)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self.ctx.settings.set("ui/window_geometry", self.saveGeometry())
        super().closeEvent(event)

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
