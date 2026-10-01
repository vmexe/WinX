"""Drivers: what is installed, what is broken, and the driver store."""

from __future__ import annotations

import os

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core.workers import submit
from ...modules import drivers
from .. import sysicons
from ..context import AppContext
from ..widgets import ProgressRow
from .base import Page


class DriversPage(Page):
    key = "drivers"
    title = "Drivers"
    subtitle = "Installed drivers, devices reporting problems, and third-party packages in the driver store."
    cache_ttl = 1800.0

    def __init__(self, ctx: AppContext):
        super().__init__(ctx)

        self.layout_.addLayout(self.cache_row())

        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search drivers…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._apply_filter)
        filters.addWidget(self.search, 1)

        filters.addWidget(QLabel("Show:"))
        self.combo_show = QComboBox()
        for label, value in [
            ("Everything", "all"),
            ("Problem devices", "problem"),
            ("Unsigned drivers", "unsigned"),
            ("Third-party only", "thirdparty"),
        ]:
            self.combo_show.addItem(label, value)
        self.combo_show.currentIndexChanged.connect(self._apply_filter)
        filters.addWidget(self.combo_show)

        filters.addWidget(QLabel("Class:"))
        self.combo_class = QComboBox()
        self.combo_class.addItem("All classes", "")
        self.combo_class.currentIndexChanged.connect(self._apply_filter)
        filters.addWidget(self.combo_class)
        self.layout_.addLayout(filters)

        self.tabs = QTabWidget()
        self.layout_.addWidget(self.tabs, 1)

        installed = QWidget()
        installed_layout = QVBoxLayout(installed)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(6)
        self.tree.setHeaderLabels(["Device", "Class", "Provider", "Version", "Date", "Status"])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setSortingEnabled(True)
        self.tree.setIconSize(QSize(20, 20))
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        installed_layout.addWidget(self.tree, 1)
        self.tabs.addTab(installed, "Installed drivers")

        store = QWidget()
        store_layout = QVBoxLayout(store)
        self.store_tree = QTreeWidget()
        self.store_tree.setColumnCount(6)
        self.store_tree.setHeaderLabels(
            ["Published name", "Original name", "Provider", "Class", "Version", "Date"]
        )
        self.store_tree.setRootIsDecorated(False)
        self.store_tree.setAlternatingRowColors(True)
        self.store_tree.setSortingEnabled(True)
        self.store_tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        store_layout.addWidget(self.store_tree, 1)

        store_buttons = QHBoxLayout()
        self.btn_remove = QPushButton("Remove package…")
        self.btn_remove.clicked.connect(self._remove_store_driver)
        store_buttons.addWidget(self.btn_remove)
        store_buttons.addStretch(1)
        store_layout.addLayout(store_buttons)
        self.tabs.addTab(store, "Driver store")

        self.progress = ProgressRow()
        self.layout_.addWidget(self.progress)

        buttons = QHBoxLayout()
        # the "Refresh" button next to the "Updated …" line is the only one:
        # a second copy down here was just noise
        self.btn_refresh = self.refresh_button
        self.btn_backup = QPushButton("Back up all drivers…")
        self.btn_backup.clicked.connect(self._backup)
        buttons.addWidget(self.btn_backup)
        self.btn_scan = QPushButton("Scan for hardware changes")
        self.btn_scan.clicked.connect(self._scan_hardware)
        buttons.addWidget(self.btn_scan)
        buttons.addStretch(1)
        self.layout_.addLayout(buttons)

    # -- data ------------------------------------------------------------
    def refresh(self) -> None:
        self.btn_refresh.setEnabled(False)
        self.progress.start("Reading drivers…")
        worker = submit(self._load)
        worker.signals.progress.connect(lambda d, t, m: self.progress.set(d, t, m))
        worker.signals.result.connect(self._on_loaded)
        worker.signals.error.connect(self._on_failed)

    def _load(self, progress=None):
        return (drivers.list_drivers(progress=progress), drivers.driver_store())

    def _on_loaded(self, payload) -> None:
        self.btn_refresh.setEnabled(True)
        installed, store = payload
        self.progress.stop(f"{len(installed)} drivers, {len(store)} third-party packages")

        self.tree.setSortingEnabled(False)
        self.tree.clear()
        classes = sorted({d.device_class for d in installed if d.device_class})
        for driver in installed:
            item = QTreeWidgetItem(
                [driver.name, driver.device_class, driver.provider, driver.version, driver.date, driver.status]
            )
            item.setData(0, Qt.ItemDataRole.UserRole, driver.is_problem)
            item.setData(1, Qt.ItemDataRole.UserRole, driver.signed)
            item.setData(2, Qt.ItemDataRole.UserRole, driver)
            # the shell has no icon for a driver, so use the platform's own
            # status icons instead of drawing anything ourselves
            if driver.is_problem:
                item.setIcon(0, sysicons.status_icon("warn"))
            elif not driver.signed:
                item.setIcon(0, sysicons.status_icon("info"))
            else:
                item.setIcon(0, sysicons.status_icon("ok"))
            if not driver.signed:
                item.setToolTip(0, "Unsigned driver")
            self.tree.addTopLevelItem(item)
        self._fill_classes(classes)
        self.tree.setSortingEnabled(True)
        self.tree.resizeColumnToContents(1)

        self.store_tree.setSortingEnabled(False)
        self.store_tree.clear()
        for pkg in store:
            item = QTreeWidgetItem(
                [pkg.published, pkg.original, pkg.provider, pkg.class_name, pkg.version, pkg.date]
            )
            item.setData(0, Qt.ItemDataRole.UserRole, pkg.published)
            self.store_tree.addTopLevelItem(item)
        self.store_tree.setSortingEnabled(True)
        self.store_tree.resizeColumnToContents(0)
        for pkg_row in range(self.store_tree.topLevelItemCount()):
            self.store_tree.topLevelItem(pkg_row).setIcon(0, sysicons.generic_app_icon())

        self._apply_filter()
        self.mark_loaded()

    def _on_failed(self, message: str) -> None:
        self.btn_refresh.setEnabled(True)
        self.progress.stop("Could not read drivers")
        self.on_error(message)

    def _fill_classes(self, classes: list[str]) -> None:
        current = self.combo_class.currentData()
        self.combo_class.blockSignals(True)
        self.combo_class.clear()
        self.combo_class.addItem("All classes", "")
        for name in classes:
            self.combo_class.addItem(name, name)
        index = self.combo_class.findData(current)
        self.combo_class.setCurrentIndex(index if index >= 0 else 0)
        self.combo_class.blockSignals(False)

    def _apply_filter(self, *_args) -> None:
        needle = self.search.text().strip().lower()
        choice = self.combo_show.currentData()
        wanted_class = self.combo_class.currentData()
        for i in range(self.tree.topLevelItemCount()):
            row = self.tree.topLevelItem(i)
            text = " ".join(row.text(c) for c in range(row.columnCount())).lower()
            visible = not needle or needle in text
            if visible and wanted_class:
                visible = row.text(1) == wanted_class
            if visible and choice == "problem":
                visible = bool(row.data(0, Qt.ItemDataRole.UserRole))
            if visible and choice == "unsigned":
                visible = not bool(row.data(1, Qt.ItemDataRole.UserRole))
            if visible and choice == "thirdparty":
                visible = "microsoft" not in row.text(2).lower()
            row.setHidden(not visible)

    def focus_search(self, text: str) -> None:
        self.search.setText(text)
        self.search.setFocus()

    # -- actions ---------------------------------------------------------
    def _backup(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Choose a folder for the driver backup", os.path.expanduser("~")
        )
        if not folder:
            return
        self.progress.start("Backing up drivers…")
        worker = submit(drivers.backup_drivers, folder)
        worker.signals.result.connect(lambda payload: self._on_simple(payload, "Driver backup"))
        worker.signals.error.connect(self._on_failed)

    def _scan_hardware(self) -> None:
        self.progress.start("Scanning for hardware changes…")
        worker = submit(drivers.scan_hardware_changes)
        worker.signals.result.connect(lambda payload: self._on_simple(payload, "Hardware scan"))
        worker.signals.error.connect(self._on_failed)

    def _remove_store_driver(self) -> None:
        item = self.store_tree.currentItem()
        published = item.data(0, Qt.ItemDataRole.UserRole) if item else None
        if not published:
            QMessageBox.information(self, "No package selected", "Pick a package in the list first.")
            return
        answer = QMessageBox.question(
            self,
            "Remove driver package",
            f"Remove {published} from the driver store?\n\n"
            "Windows will fall back to another driver for that device.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        ok, detail = drivers.remove_store_driver(published)
        self._on_simple((ok, detail), "Remove package")
        if ok:
            self.refresh()

    def _on_simple(self, payload, title: str) -> None:
        ok, detail = payload
        message = f"{title}: {detail}" if detail else f"{title} {'finished' if ok else 'failed'}"
        self.progress.stop(message)
        self.log(message, "ok" if ok else "error")
        self.status(message)
