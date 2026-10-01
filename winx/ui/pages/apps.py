"""Uninstaller: installed programs and Store apps, with bloatware detection."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSlider,
    QTreeWidget,
    QTreeWidgetItem,
)

from ...core.workers import submit
from ...modules import apps
from .. import sysicons
from ..context import AppContext
from ..widgets import LogConsole, ProgressRow
from .base import Page


class AppRow(QTreeWidgetItem):
    """Sorts the size column by megabytes, not by the text '1.2 GB'.

    ``super().__lt__`` is *not* usable here: Qt dispatches ``operator<`` back
    into this override and the recursion crashes the process, so the default
    case compares the cell text itself.
    """

    def __lt__(self, other: QTreeWidgetItem) -> bool:
        tree = self.treeWidget()
        column = tree.sortColumn() if tree is not None else 0
        if column == 3:
            mine = self.data(2, Qt.ItemDataRole.UserRole) or 0
            theirs = other.data(2, Qt.ItemDataRole.UserRole) or 0
            return int(mine) < int(theirs)
        return self.text(column).casefold() < other.text(column).casefold()


class AppsPage(Page):
    key = "apps"
    title = "Uninstaller"
    subtitle = "Everything installed on this PC, including Store apps. Flagged rows are common bloatware."
    #: enumerating the uninstall registry and every Store package is slow
    cache_ttl = 1800.0

    def __init__(self, ctx: AppContext):
        super().__init__(ctx)
        self.entries: list[apps.App] = []
        self.icons = sysicons.IconLoader(self, size=32)

        self.layout_.addLayout(self.cache_row())

        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search by name or publisher…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._apply_filter)
        filters.addWidget(self.search, 1)

        filters.addWidget(QLabel("Show:"))
        self.combo_show = QComboBox()
        for label, value in [
            ("Everything", "all"),
            ("Bloatware only", "bloat"),
            ("Desktop programs", "win32"),
            ("Store apps", "appx"),
            ("Removable only", "removable"),
        ]:
            self.combo_show.addItem(label, value)
        self.combo_show.currentIndexChanged.connect(self._apply_filter)
        filters.addWidget(self.combo_show)

        filters.addWidget(QLabel("Sort by:"))
        self.combo_sort = QComboBox()
        for label, column in [
            ("Name", 0), ("Size", 3), ("Publisher", 2), ("Source", 4)
        ]:
            self.combo_sort.addItem(label, column)
        self.combo_sort.currentIndexChanged.connect(self._apply_sort)
        filters.addWidget(self.combo_sort)
        self.layout_.addLayout(filters)

        size_row = QHBoxLayout()
        size_row.addWidget(QLabel("Hide anything smaller than:"))
        self.slider_size = QSlider(Qt.Orientation.Horizontal)
        self.slider_size.setRange(0, 2000)
        self.slider_size.setSingleStep(10)
        self.slider_size.setPageStep(100)
        self.slider_size.setTickInterval(250)
        self.slider_size.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.slider_size.valueChanged.connect(self._size_changed)
        size_row.addWidget(self.slider_size, 1)
        self.size_label = QLabel("any size")
        self.size_label.setMinimumWidth(80)
        size_row.addWidget(self.size_label)
        self.layout_.addLayout(size_row)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(6)
        self.tree.setHeaderLabels(["Name", "Version", "Publisher", "Size", "Source", "Note"])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setSortingEnabled(True)
        self.tree.setIconSize(QSize(24, 24))
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.itemChanged.connect(lambda *_: self._update_summary())
        self.layout_.addWidget(self.tree, 1)

        self.progress = ProgressRow()
        self.layout_.addWidget(self.progress)

        self.console = LogConsole("Uninstall output appears here.")
        self.console.setMaximumHeight(110)
        self.layout_.addWidget(self.console)

        buttons = QHBoxLayout()
        # the "Refresh" button next to the "Updated …" line is the only one:
        # a second copy down here was just noise
        self.btn_refresh = self.refresh_button
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
        pending: list[QTreeWidgetItem] = []
        for app in entries:
            is_bloat, reason = apps.is_bloat_app(app)
            item = AppRow(
                [app.name, app.version, app.publisher, app.size_text, app.source,
                 reason if is_bloat else ""]
            )
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(0, Qt.CheckState.Unchecked)
            item.setData(0, Qt.ItemDataRole.UserRole, app)
            item.setData(1, Qt.ItemDataRole.UserRole, is_bloat)
            item.setData(2, Qt.ItemDataRole.UserRole, app.size_mb)
            item.setIcon(0, sysicons.generic_app_icon())
            pending.append(item)
            if not app.removable:
                item.setDisabled(True)
                item.setToolTip(0, "This entry cannot be uninstalled from here")
            self.tree.addTopLevelItem(item)
        self.tree.blockSignals(True)
        self.tree.setSortingEnabled(True)
        self.tree.blockSignals(False)
        self.tree.resizeColumnToContents(1)
        self.tree.resizeColumnToContents(3)
        self._apply_sort()
        self._apply_filter()
        self._update_summary()
        self._start_icon_loading(pending)
        self.mark_loaded()

    # -- icons -----------------------------------------------------------
    def _start_icon_loading(self, items: list) -> None:
        self.icons.load(
            (item, getattr(item.data(0, Qt.ItemDataRole.UserRole), "icon_path", ""))
            for item in items
        )

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

    def _size_changed(self, value: int) -> None:
        self.size_label.setText("any size" if not value else f"{value} MB")
        self._apply_filter()

    def _apply_sort(self, *_args) -> None:
        column = self.combo_sort.currentData()
        order = (
            Qt.SortOrder.DescendingOrder if column == 3 else Qt.SortOrder.AscendingOrder
        )
        self.tree.sortItems(int(column), order)

    def _matches(self, row) -> bool:
        needle = self.search.text().strip().lower()
        if needle and needle not in f"{row.text(0)} {row.text(2)}".lower():
            return False
        app = row.data(0, Qt.ItemDataRole.UserRole)
        choice = self.combo_show.currentData()
        if choice == "bloat" and not row.data(1, Qt.ItemDataRole.UserRole):
            return False
        if choice == "appx" and getattr(app, "source", "") != "AppX":
            return False
        if choice == "win32" and getattr(app, "source", "") == "AppX":
            return False
        if choice == "removable" and not getattr(app, "removable", True):
            return False
        minimum = self.slider_size.value()
        if minimum and int(getattr(app, "size_mb", 0) or 0) < minimum:
            return False
        return True

    def _apply_filter(self, *_args) -> None:
        shown = 0
        for row in self._rows():
            visible = self._matches(row)
            row.setHidden(not visible)
            shown += int(visible)
        total = self.tree.topLevelItemCount()
        if total and shown != total:
            self.status(f"Showing {shown} of {total} programs")

    def focus_search(self, text: str) -> None:
        """Used by the global search box."""
        self.search.setText(text)
        self.search.setFocus()

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
        self.force_refresh()

    def _set_busy(self, busy: bool) -> None:
        for button in (self.btn_refresh, self.btn_uninstall, self.btn_select_bloat, self.btn_none):
            button.setEnabled(not busy)
