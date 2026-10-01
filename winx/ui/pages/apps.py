"""Uninstaller: installed programs and Store apps, with bloatware detection."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
)

from ...core.workers import submit
from ...modules import apps
from ..context import AppContext
from ..widgets import LogConsole, ProgressRow
from .base import Page


class AppsPage(Page):
    key = "apps"
    title = "Uninstaller"
    subtitle = "Everything installed on this PC, including Store apps. Flagged rows are common bloatware."

    def __init__(self, ctx: AppContext):
        super().__init__(ctx)
        self.entries: list[apps.App] = []

        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search by name or publisher…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._apply_filter)
        filters.addWidget(self.search, 1)

        self.only_bloat = QCheckBox("Only bloatware")
        self.only_bloat.toggled.connect(self._apply_filter)
        filters.addWidget(self.only_bloat)
        self.layout_.addLayout(filters)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(6)
        self.tree.setHeaderLabels(["Name", "Version", "Publisher", "Size", "Source", "Note"])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setSortingEnabled(True)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.itemChanged.connect(lambda *_: self._update_summary())
        self.layout_.addWidget(self.tree, 1)

        self.progress = ProgressRow()
        self.layout_.addWidget(self.progress)

        self.console = LogConsole("Uninstall output appears here.")
        self.console.setMaximumHeight(110)
        self.layout_.addWidget(self.console)

        buttons = QHBoxLayout()
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.clicked.connect(self.refresh)
        buttons.addWidget(self.btn_refresh)

        self.btn_select_bloat = QPushButton("Select bloatware")
        self.btn_select_bloat.clicked.connect(self._select_bloat)
        buttons.addWidget(self.btn_select_bloat)

        self.btn_none = QPushButton("Select none")
        self.btn_none.clicked.connect(lambda: self._set_all(False))
        buttons.addWidget(self.btn_none)

        buttons.addStretch(1)
        self.summary = QLabel("0 selected")
        buttons.addWidget(self.summary)

        self.btn_uninstall = QPushButton("Uninstall selected")
        self.btn_uninstall.clicked.connect(self._uninstall)
        buttons.addWidget(self.btn_uninstall)
        self.layout_.addLayout(buttons)

    # -- data ------------------------------------------------------------
    def refresh(self) -> None:
        self._set_busy(True)
        self.progress.start("Reading installed programs…")
        worker = submit(self._load)
        worker.signals.progress.connect(lambda d, t, m: self.progress.set(d, t, m))
        worker.signals.result.connect(self._on_loaded)
        worker.signals.error.connect(self._on_failed)

    def _load(self, progress=None):
        return apps.installed_apps(progress=progress)

    def _on_loaded(self, entries: list) -> None:
        self._set_busy(False)
        self.entries = entries
        bloat = sum(1 for a in entries if apps.is_bloat_app(a)[0])
        self.progress.stop(f"{len(entries)} programs, {bloat} flagged as bloatware")

        self.tree.setSortingEnabled(False)
        self.tree.blockSignals(True)
        self.tree.clear()
        for app in entries:
            is_bloat, reason = apps.is_bloat_app(app)
            item = QTreeWidgetItem(
                [app.name, app.version, app.publisher, app.size_text, app.source,
                 reason if is_bloat else ""]
            )
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(0, Qt.CheckState.Unchecked)
            item.setData(0, Qt.ItemDataRole.UserRole, app)
            item.setData(1, Qt.ItemDataRole.UserRole, is_bloat)
            if not app.removable:
                item.setDisabled(True)
                item.setToolTip(0, "This entry cannot be uninstalled from here")
            self.tree.addTopLevelItem(item)
        self.tree.blockSignals(True)
        self.tree.setSortingEnabled(True)
        self.tree.blockSignals(False)
        self.tree.resizeColumnToContents(1)
        self.tree.resizeColumnToContents(3)
        self._apply_filter()
        self._update_summary()

    def _on_failed(self, message: str) -> None:
        self._set_busy(False)
        self.progress.stop("Could not list installed programs")
        self.on_error(message)

    # -- selection -------------------------------------------------------
    def _rows(self):
        for i in range(self.tree.topLevelItemCount()):
            yield self.tree.topLevelItem(i)

    def _selected_apps(self) -> list[apps.App]:
        return [
            row.data(0, Qt.ItemDataRole.UserRole)
            for row in self._rows()
            if row.checkState(0) == Qt.CheckState.Checked
        ]

    def _set_all(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for row in self._rows():
            if not row.isHidden() and not row.isDisabled():
                row.setCheckState(0, state)

    def _select_bloat(self) -> None:
        for row in self._rows():
            is_bloat = bool(row.data(1, Qt.ItemDataRole.UserRole))
            row.setCheckState(
                0, Qt.CheckState.Checked if is_bloat and not row.isDisabled() else Qt.CheckState.Unchecked
            )

    def _update_summary(self) -> None:
        self.summary.setText(f"{len(self._selected_apps())} selected")

    def _apply_filter(self, *_args) -> None:
        needle = self.search.text().strip().lower()
        bloat_only = self.only_bloat.isChecked()
        for row in self._rows():
            text = f"{row.text(0)} {row.text(2)}".lower()
            visible = (not needle or needle in text) and (
                not bloat_only or bool(row.data(1, Qt.ItemDataRole.UserRole))
            )
            row.setHidden(not visible)

    # -- uninstall -------------------------------------------------------
    def _uninstall(self) -> None:
        selected = self._selected_apps()
        if not selected:
            QMessageBox.information(self, "Nothing selected", "Tick the programs you want to remove.")
            return
        names = "\n".join(f"  • {a.name}" for a in selected[:12])
        more = f"\n  … and {len(selected) - 12} more" if len(selected) > 12 else ""
        answer = QMessageBox.question(
            self,
            "Uninstall programs",
            f"Uninstall {len(selected)} program(s)?\n\n{names}{more}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self._set_busy(True)
        self.progress.start("Uninstalling…")
        worker = submit(self._do_uninstall, selected)
        worker.signals.message.connect(lambda m: self.console.append(m))
        worker.signals.result.connect(self._on_uninstalled)
        worker.signals.error.connect(self._on_failed)

    def _do_uninstall(self, selected, emit=None):
        return apps.uninstall_many(selected, emit=emit)

    def _on_uninstalled(self, payload) -> None:
        self._set_busy(False)
        done, failed = payload
        message = f"Uninstalled {done} program(s)" + (f", {failed} failed" if failed else "")
        self.progress.stop(message)
        self.log(message, "ok" if not failed else "warn")
        self.status(message)
        self.refresh()

    def _set_busy(self, busy: bool) -> None:
        for button in (self.btn_refresh, self.btn_uninstall, self.btn_select_bloat, self.btn_none):
            button.setEnabled(not busy)
