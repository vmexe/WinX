"""Startup manager: logon programs, startup folders, scheduled tasks, services."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
    QVBoxLayout,
)

from ...core.workers import submit
from ...modules import startup
from ..context import AppContext
from ..widgets import ProgressRow
from .base import Page

SERVICE_STARTS = ["auto", "delayed-auto", "demand", "disabled"]


class StartupPage(Page):
    key = "startup"
    title = "Startup"
    subtitle = "Programs and services that launch themselves when Windows starts."

    def __init__(self, ctx: AppContext):
        super().__init__(ctx)
        self.items: list[startup.StartupItem] = []

        self.tabs = QTabWidget()
        self.layout_.addWidget(self.tabs, 1)

        # -- startup entries ---------------------------------------------
        entries = QWidget()
        entries_layout = QVBoxLayout(entries)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(5)
        self.tree.setHeaderLabels(["Program", "Status", "Impact", "Type", "Location"])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setSortingEnabled(True)
        self.tree.header().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.tree.currentItemChanged.connect(self._show_command)
        entries_layout.addWidget(self.tree, 1)

        self.command_label = QLabel("")
        self.command_label.setWordWrap(True)
        self.command_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        entries_layout.addWidget(self.command_label)

        entry_buttons = QHBoxLayout()
        self.btn_disable = QPushButton("Disable")
        self.btn_disable.clicked.connect(lambda: self._set_enabled(False))
        entry_buttons.addWidget(self.btn_disable)
        self.btn_enable = QPushButton("Enable")
        self.btn_enable.clicked.connect(lambda: self._set_enabled(True))
        entry_buttons.addWidget(self.btn_enable)
        self.btn_remove = QPushButton("Remove…")
        self.btn_remove.clicked.connect(self._remove)
        entry_buttons.addWidget(self.btn_remove)
        entry_buttons.addStretch(1)
        entries_layout.addLayout(entry_buttons)
        self.tabs.addTab(entries, "Startup programs")

        # -- services -----------------------------------------------------
        services = QWidget()
        services_layout = QVBoxLayout(services)
        self.services_tree = QTreeWidget()
        self.services_tree.setColumnCount(4)
        self.services_tree.setHeaderLabels(["Service", "Display name", "Start", "State"])
        self.services_tree.setRootIsDecorated(False)
        self.services_tree.setAlternatingRowColors(True)
        self.services_tree.setUniformRowHeights(True)
        self.services_tree.setSortingEnabled(True)
        self.services_tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        services_layout.addWidget(self.services_tree, 1)

        service_buttons = QHBoxLayout()
        self.btn_start_type = QPushButton("Change start type…")
        self.btn_start_type.clicked.connect(self._change_start_type)
        service_buttons.addWidget(self.btn_start_type)
        service_buttons.addStretch(1)
        services_layout.addLayout(service_buttons)
        self.tabs.addTab(services, "Auto-start services")

        self.progress = ProgressRow()
        self.layout_.addWidget(self.progress)

        footer = QHBoxLayout()
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.clicked.connect(self.refresh)
        footer.addWidget(self.btn_refresh)
        footer.addStretch(1)
        self.summary = QLabel("")
        footer.addWidget(self.summary)
        self.layout_.addLayout(footer)

    # -- data ------------------------------------------------------------
    def refresh(self) -> None:
        self.btn_refresh.setEnabled(False)
        self.progress.start("Reading startup entries…")
        worker = submit(self._load)
        worker.signals.progress.connect(lambda d, t, m: self.progress.set(d, t, m))
        worker.signals.message.connect(lambda m: self.log(m))
        worker.signals.result.connect(self._on_loaded)
        worker.signals.error.connect(self._on_failed)

    def _load(self, progress=None, emit=None):
        items = startup.enumerate_items(progress=progress, emit=emit)
        return (items, startup.services_rows())

    def _on_loaded(self, payload) -> None:
        self.btn_refresh.setEnabled(True)
        items, services_rows = payload
        self.items = items

        self.tree.setSortingEnabled(False)
        self.tree.clear()
        for item in items:
            row = QTreeWidgetItem(
                [
                    item.name,
                    "Enabled" if item.enabled else "Disabled",
                    item.impact,
                    item.type,
                    item.display_location,
                ]
            )
            row.setData(0, Qt.ItemDataRole.UserRole, item)
            self.tree.addTopLevelItem(row)
        self.tree.setSortingEnabled(True)
        self.tree.resizeColumnToContents(0)

        self.services_tree.setSortingEnabled(False)
        self.services_tree.clear()
        for row in services_rows:
            node = QTreeWidgetItem(
                [row.get("name", ""), row.get("display", ""), row.get("start", ""), row.get("state", "")]
            )
            node.setData(0, Qt.ItemDataRole.UserRole, row.get("name", ""))
            self.services_tree.addTopLevelItem(node)
        self.services_tree.setSortingEnabled(True)
        self.services_tree.resizeColumnToContents(0)

        enabled = sum(1 for i in items if i.enabled)
        self.summary.setText(
            f"{enabled} of {len(items)} entries enabled · {len(services_rows)} services start automatically"
        )
        self.progress.stop("")
        self.status("Startup list updated")

    def _on_failed(self, message: str) -> None:
        self.btn_refresh.setEnabled(True)
        self.progress.stop("Could not read startup entries")
        self.on_error(message)

    # -- actions ---------------------------------------------------------
    def _current(self) -> startup.StartupItem | None:
        row = self.tree.currentItem()
        return row.data(0, Qt.ItemDataRole.UserRole) if row else None

    def _show_command(self, current, _previous) -> None:
        item = current.data(0, Qt.ItemDataRole.UserRole) if current else None
        self.command_label.setText(item.command if item else "")

    def _set_enabled(self, enabled: bool) -> None:
        item = self._current()
        if item is None:
            return
        ok, error = startup.set_enabled(item, enabled)
        verb = "enabled" if enabled else "disabled"
        if ok:
            self.log(f"{item.name} {verb}", "ok")
            self.status(f"{item.name} {verb}")
            self.refresh()
        else:
            QMessageBox.warning(self, "Could not change the entry", error or "Unknown error")

    def _remove(self) -> None:
        item = self._current()
        if item is None:
            return
        answer = QMessageBox.question(
            self,
            "Remove startup entry",
            f"Permanently remove “{item.name}” from startup?\n\nThis does not uninstall the program.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        ok, error = startup.remove(item)
        if ok:
            self.log(f"{item.name} removed from startup", "ok")
            self.refresh()
        else:
            QMessageBox.warning(self, "Could not remove the entry", error or "Unknown error")

    def _change_start_type(self) -> None:
        row = self.services_tree.currentItem()
        if row is None:
            return
        name = row.data(0, Qt.ItemDataRole.UserRole)
        current = row.text(2)
        index = SERVICE_STARTS.index(current) if current in SERVICE_STARTS else 0
        choice, ok = QInputDialog.getItem(
            self, "Change start type", f"Start type for {name}:", SERVICE_STARTS, index, False
        )
        if not ok:
            return
        done, error = startup.set_service_start(name, choice)
        if done:
            self.log(f"{name} set to {choice}", "ok")
            self.refresh()
        else:
            QMessageBox.warning(self, "Could not change the service", error or "Unknown error")
