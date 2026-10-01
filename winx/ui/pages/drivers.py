"""Drivers page: inventory, problem devices, backups and the driver store."""

from __future__ import annotations

import datetime as dt
import os

from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
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
from ..context import AppContext
from ..icons import icon
from ..widgets import LogConsole, ProgressRow, StatCard
from .base import Page


class DriversPage(Page):
    key = "drivers"
    title = "Drivers"
    subtitle = "Every installed driver, devices that are not working, and a one-click backup before you touch anything."
    icon_name = "chip"

    def __init__(self, ctx: AppContext):
        super().__init__(ctx)
        self._build()

    def _build(self) -> None:
        layout = self.content_layout
        header = QHBoxLayout()
        heading = QLabel("Drivers")
        font = QFont()
        font.setPointSize(18)
        font.setWeight(QFont.Weight.Bold)
        heading.setFont(font)
        header.addWidget(heading)
        header.addStretch(1)
        self.btn_backup = QPushButton(" Back up all drivers")
        self.btn_backup.setIcon(icon("save", self.ctx.accent, 16))
        self.btn_backup.clicked.connect(self._backup)
        self.btn_scan = QPushButton("Rescan hardware")
        self.btn_scan.clicked.connect(self._rescan)
        self.btn_refresh = QPushButton(" Refresh")
        self.btn_refresh.setIcon(icon("refresh", self.ctx.accent, 16))
        self.btn_refresh.clicked.connect(self.refresh)
        header.addWidget(self.btn_backup)
        header.addWidget(self.btn_scan)
        header.addWidget(self.btn_refresh)
        layout.addLayout(header)

        sub = QLabel(self.subtitle)
        sub.setProperty("muted", True)
        sub.setWordWrap(True)
        layout.addWidget(sub)

        stats = QHBoxLayout()
        stats.setSpacing(10)
        self.stat_total = StatCard("Drivers", "—", "", "chip")
        self.stat_problems = StatCard("Problem devices", "—", "", "warning")
        self.stat_unsigned = StatCard("Unsigned", "—", "", "security")
        self.stat_old = StatCard("Older than 2 years", "—", "", "clock")
        stats.addWidget(self.stat_total)
        stats.addWidget(self.stat_problems)
        stats.addWidget(self.stat_unsigned)
        stats.addWidget(self.stat_old)
        layout.addLayout(stats)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)

        # inventory
        tab = QWidget()
        tl = QVBoxLayout(tab)
        bar = QHBoxLayout()
        self.search = QLabel()
        self.chk_problems = QCheckBox("Show only devices with problems")
        self.chk_problems.stateChanged.connect(self._apply_filter)
        self.chk_unsigned = QCheckBox("Show only unsigned drivers")
        self.chk_unsigned.stateChanged.connect(self._apply_filter)
        bar.addWidget(self.chk_problems)
        bar.addWidget(self.chk_unsigned)
        bar.addStretch(1)
        tl.addLayout(bar)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Device", "Provider", "Version", "Date", "Class", "INF", "Status"])
        self.tree.setColumnWidth(0, 280)
        self.tree.setColumnWidth(1, 170)
        self.tree.setColumnWidth(2, 140)
        self.tree.setColumnWidth(3, 100)
        self.tree.setColumnWidth(5, 110)
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setMinimumHeight(260)
        tl.addWidget(self.tree, 1)
        self.tabs.addTab(tab, "Installed drivers")

        # store
        store_tab = QWidget()
        sl = QVBoxLayout(store_tab)
        info = QLabel(
            "The driver store holds every driver package Windows has ever installed. Removing one uninstalls it "
            "from all devices. Back up before you touch this."
        )
        info.setProperty("muted", True)
        info.setWordWrap(True)
        sl.addWidget(info)
        self.store_tree = QTreeWidget()
        self.store_tree.setHeaderLabels(["Published name", "Original name", "Provider", "Class", "Version"])
        self.store_tree.setColumnWidth(0, 160)
        self.store_tree.setColumnWidth(1, 170)
        self.store_tree.setColumnWidth(2, 200)
        self.store_tree.setRootIsDecorated(False)
        self.store_tree.setAlternatingRowColors(True)
        self.store_tree.setMinimumHeight(220)
        sl.addWidget(self.store_tree, 1)
        sbar = QHBoxLayout()
        self.btn_store_refresh = QPushButton("Refresh driver store")
        self.btn_store_refresh.clicked.connect(self._load_store)
        self.btn_store_delete = QPushButton("Remove selected package")
        self.btn_store_delete.setProperty("danger", True)
        self.btn_store_delete.clicked.connect(self._delete_store)
        sbar.addWidget(self.btn_store_refresh)
        sbar.addWidget(self.btn_store_delete)
        sbar.addStretch(1)
        sl.addLayout(sbar)
        self.tabs.addTab(store_tab, "Driver store")

        self.progress = ProgressRow()
        layout.addWidget(self.progress)
        self.console = LogConsole(placeholder="Driver operations are logged here…")
        self.console.setFixedHeight(110)
        layout.addWidget(self.console)

    # -- data ------------------------------------------------------------
    def refresh(self) -> None:
        self.progress.start("Enumerating drivers…")
        worker = submit(self._load)
        worker.signals.progress.connect(lambda d, t, m: self.progress.set(d, t, m or "Enumerating…"))
        worker.signals.result.connect(self._on_loaded)
        worker.signals.error.connect(self._on_error)

    def _load(self, progress=None):
        return drivers.list_drivers(progress=progress)

    def _on_loaded(self, rows) -> None:
        self.rows = rows
        self.tree.clear()
        problems = 0
        unsigned = 0
        old = 0
        cutoff = dt.date.today() - dt.timedelta(days=730)
        for drv in rows:
            item = QTreeWidgetItem(
                [drv.name, drv.provider, drv.version, drv.date, drv.device_class, drv.inf, drv.status]
            )
            if drv.is_problem:
                item.setForeground(6, QColor("#ff6b6b"))
                item.setForeground(0, QColor("#ff6b6b"))
                problems += 1
            if not drv.signed:
                item.setForeground(2, QColor("#f5c451"))
                unsigned += 1
            try:
                if drv.date and dt.date.fromisoformat(drv.date) < cutoff:
                    old += 1
            except ValueError:
                pass
            self.tree.addTopLevelItem(item)

        self.stat_total.set_value(str(len(rows)), "installed drivers")
        self.stat_problems.set_value(str(problems), "not working correctly" if problems else "all devices OK")
        self.stat_unsigned.set_value(str(unsigned), "unsigned packages")
        self.stat_old.set_value(str(old), "consider updating")
        self.progress.stop(f"{len(rows)} drivers, {problems} problem(s)")
        self.status(f"{len(rows)} drivers, {problems} with problems")
        self._apply_filter()

    def _apply_filter(self, *_args) -> None:
        problems_only = self.chk_problems.isChecked()
        unsigned_only = self.chk_unsigned.isChecked()
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            is_problem = item.foreground(6).color() == QColor("#ff6b6b")
            is_unsigned = item.foreground(2).color() == QColor("#f5c451")
            hidden = (problems_only and not is_problem) or (unsigned_only and not is_unsigned)
            item.setHidden(hidden)

    # -- store -----------------------------------------------------------
    def _load_store(self) -> None:
        self.progress.start("Reading driver store…")
        worker = submit(self._store)
        worker.signals.result.connect(self._on_store)
        worker.signals.error.connect(self._on_error)

    def _store(self):
        return drivers.driver_store()

    def _on_store(self, rows) -> None:
        self.progress.stop(f"{len(rows)} packages")
        self.store_tree.clear()
        for drv in rows:
            self.store_tree.addTopLevelItem(
                QTreeWidgetItem([drv.published, drv.original, drv.provider, drv.class_name, drv.version])
            )

    def _delete_store(self) -> None:
        items = self.store_tree.selectedItems()
        if not items:
            return
        published = items[0].text(0)
        answer = QMessageBox.warning(
            self,
            "Remove driver package",
            f"Remove and uninstall {published}?\n\nIf this is your graphics, network or storage driver you could "
            "lose display or connectivity until you reinstall it.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        ok, detail = drivers.remove_store_driver(published)
        self.log((f"Removed {published}" if ok else f"Failed: {detail}"), "ok" if ok else "error")
        self._load_store()

    # -- actions ---------------------------------------------------------
    def _backup(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choose a backup folder", os.path.expanduser("~"))
        if not folder:
            return
        folder = os.path.join(folder, f"DriverBackup-{dt.date.today():%Y%m%d}")
        self.progress.start("Exporting drivers…")
        worker = submit(self._do_backup, folder)
        worker.signals.result.connect(self._on_backup)
        worker.signals.error.connect(self._on_error)

    def _do_backup(self, folder):
        return drivers.backup_drivers(folder)

    def _on_backup(self, payload) -> None:
        ok, detail = payload
        self.progress.stop("done")
        self.log(("Drivers exported" if ok else "Export failed") + f": {detail}", "ok" if ok else "error")
        QMessageBox.information(self, "Driver backup", detail if ok else "Failed: " + detail)

    def _rescan(self) -> None:
        self.progress.start("Scanning for hardware changes…")
        worker = submit(self._do_rescan)
        worker.signals.result.connect(self._on_rescan)
        worker.signals.error.connect(self._on_error)

    def _do_rescan(self):
        return drivers.scan_hardware_changes()

    def _on_rescan(self, payload) -> None:
        ok, detail = payload
        self.progress.stop("done")
        self.log(("Hardware rescan complete" if ok else "Rescan failed") + f": {detail}", "ok" if ok else "error")
        self.refresh()

    def _on_error(self, message: str) -> None:
        self.progress.stop("failed")
        self.log(message, "error")
