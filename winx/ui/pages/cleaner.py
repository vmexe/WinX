"""Cleaner: measure and remove junk files from a fixed list of locations."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
)

from ...core.format import human_size
from ...core.model import RISK_LABEL
from ...core.workers import submit
from ...modules import cleaner
from ..context import AppContext
from ..widgets import LogConsole, ProgressRow
from .base import Page


class CleanerPage(Page):
    key = "cleaner"
    title = "Cleaner"
    subtitle = (
        "Only the locations listed below are touched, and locked files are skipped rather "
        "than forced. Scan first to see what can be removed."
    )

    def __init__(self, ctx: AppContext):
        super().__init__(ctx)
        self.targets = cleaner.all_targets()
        self.results: dict[str, cleaner.ScanResult] = {}
        self._worker = None

        self.tree = QTreeWidget()
        self.tree.setColumnCount(4)
        self.tree.setHeaderLabels(["Location", "Size", "Files", "Risk"])
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.itemChanged.connect(self._item_changed)
        self.tree.currentItemChanged.connect(self._show_description)
        self.layout_.addWidget(self.tree, 1)

        self.description = QLabel("")
        self.description.setWordWrap(True)
        self.layout_.addWidget(self.description)

        self.progress = ProgressRow(cancellable=True)
        self.progress.cancel_button.clicked.connect(self._cancel)
        self.layout_.addWidget(self.progress)

        self.console = LogConsole("Cleaner output appears here.")
        self.console.setMaximumHeight(120)
        self.layout_.addWidget(self.console)

        buttons = QHBoxLayout()
        self.btn_scan = QPushButton("Scan")
        self.btn_scan.clicked.connect(self.refresh)
        buttons.addWidget(self.btn_scan)

        self.btn_safe = QPushButton("Select safe items")
        self.btn_safe.clicked.connect(self._select_safe)
        buttons.addWidget(self.btn_safe)

        self.btn_none = QPushButton("Select none")
        self.btn_none.clicked.connect(lambda: self._set_all(False))
        buttons.addWidget(self.btn_none)

        buttons.addStretch(1)
        self.summary = QLabel("Not scanned yet")
        buttons.addWidget(self.summary)

        self.btn_clean = QPushButton("Clean selected")
        self.btn_clean.setDefault(True)
        self.btn_clean.clicked.connect(self._clean)
        buttons.addWidget(self.btn_clean)
        self.layout_.addLayout(buttons)

        self._populate()

    # -- tree ------------------------------------------------------------
    def _populate(self) -> None:
        self.tree.blockSignals(True)
        self.tree.clear()
        remembered = set((self.ctx.settings.str("cleaner/selected") or "").split(","))
        groups: dict[str, QTreeWidgetItem] = {}
        for target in self.targets:
            parent = groups.get(target.group)
            if parent is None:
                parent = QTreeWidgetItem([target.group, "", "", ""])
                parent.setFlags(parent.flags() | Qt.ItemFlag.ItemIsAutoTristate | Qt.ItemFlag.ItemIsUserCheckable)
                parent.setCheckState(0, Qt.CheckState.Unchecked)
                self.tree.addTopLevelItem(parent)
                groups[target.group] = parent
            item = QTreeWidgetItem([target.name, "—", "", RISK_LABEL.get(target.risk, target.risk)])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            checked = target.key in remembered
            item.setCheckState(0, Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
            item.setData(0, Qt.ItemDataRole.UserRole, target.key)
            if target.admin:
                item.setToolTip(0, "Needs administrator rights")
            item.setToolTip(1, target.description)
            parent.addChild(item)
        self.tree.expandAll()
        self.tree.blockSignals(False)
        self.tree.resizeColumnToContents(1)

    def _items(self):
        for i in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(i)
            for j in range(group.childCount()):
                yield group.child(j)

    def _selected_targets(self) -> list[cleaner.CleanTarget]:
        keys = {
            item.data(0, Qt.ItemDataRole.UserRole)
            for item in self._items()
            if item.checkState(0) == Qt.CheckState.Checked
        }
        return [t for t in self.targets if t.key in keys]

    def _set_all(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for item in self._items():
            item.setCheckState(0, state)

    def _select_safe(self) -> None:
        for item in self._items():
            key = item.data(0, Qt.ItemDataRole.UserRole)
            target = cleaner.target_by_key(key)
            safe = target is not None and target.risk == "safe" and not target.admin
            item.setCheckState(0, Qt.CheckState.Checked if safe else Qt.CheckState.Unchecked)

    def _item_changed(self, *_args) -> None:
        self._update_summary()
        keys = [t.key for t in self._selected_targets()]
        self.ctx.settings.set("cleaner/selected", ",".join(keys))

    def _show_description(self, current, _previous) -> None:
        key = current.data(0, Qt.ItemDataRole.UserRole) if current else None
        target = cleaner.target_by_key(key) if key else None
        if target is None:
            self.description.setText("")
            return
        paths = ", ".join(str(p) for p in target.resolved_paths()[:3])
        self.description.setText(f"{target.description}  —  {paths}")

    def _update_summary(self) -> None:
        selected = self._selected_targets()
        total = sum(
            self.results[t.key].size
            for t in selected
            if t.key in self.results and not self.results[t.key].unmeasured
        )
        self.summary.setText(f"{len(selected)} selected · {human_size(total)}")

    # -- scan ------------------------------------------------------------
    def refresh(self) -> None:
        self._set_busy(True)
        self.progress.start("Scanning…")
        self._worker = submit(self._scan)
        self._worker.signals.progress.connect(lambda d, t, m: self.progress.set(d, t, m))
        self._worker.signals.result.connect(self._on_scanned)
        self._worker.signals.error.connect(self._on_failed)

    def _scan(self, progress=None, is_cancelled=None):
        return cleaner.scan(progress=progress, is_cancelled=is_cancelled)

    def _on_scanned(self, results: list) -> None:
        self._set_busy(False)
        self.results = {r.key: r for r in results}
        total = 0
        for item in self._items():
            result = self.results.get(item.data(0, Qt.ItemDataRole.UserRole))
            if result is None:
                continue
            item.setText(1, result.size_text)
            item.setText(2, "" if result.unmeasured else str(result.files))
            if result.error:
                item.setToolTip(1, result.error)
            if not result.unmeasured:
                total += result.size
        self.tree.resizeColumnToContents(1)
        self.progress.stop(f"Scan complete — {human_size(total)} removable")
        self._update_summary()
        self.status(f"Scan complete: {human_size(total)} can be removed")

    # -- clean -----------------------------------------------------------
    def _clean(self) -> None:
        targets = self._selected_targets()
        if not targets:
            QMessageBox.information(self, "Nothing selected", "Tick the locations you want cleaned.")
            return
        estimate = sum(
            self.results[t.key].size
            for t in targets
            if t.key in self.results and not self.results[t.key].unmeasured
        )
        answer = QMessageBox.question(
            self,
            "Clean selected locations",
            f"Delete the contents of {len(targets)} location(s)?\n\n"
            f"About {human_size(estimate)} will be freed. Files in use are skipped.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self._set_busy(True)
        self.progress.start("Cleaning…")
        self._worker = submit(self._do_clean, targets)
        self._worker.signals.progress.connect(lambda d, t, m: self.progress.set(d, t, m))
        self._worker.signals.message.connect(lambda m: self.console.append(m))
        self._worker.signals.result.connect(self._on_cleaned)
        self._worker.signals.error.connect(self._on_failed)

    def _do_clean(self, targets, progress=None, emit=None, is_cancelled=None):
        return cleaner.clean(targets, progress=progress, emit=emit, is_cancelled=is_cancelled)

    def _on_cleaned(self, outcomes: list) -> None:
        self._set_busy(False)
        freed = sum(o.freed for o in outcomes)
        files = sum(o.files for o in outcomes)
        skipped = sum(o.skipped for o in outcomes)
        message = f"Freed {human_size(freed)} from {files} files"
        if skipped:
            message += f" ({skipped} in use, skipped)"
        self.progress.stop(message)
        self.console.append(message, "ok")
        self.log(message, "ok")
        self.status(message)
        self.refresh()

    # -- plumbing --------------------------------------------------------
    def _cancel(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            self.progress.stop("Cancelled")
            self._set_busy(False)

    def _set_busy(self, busy: bool) -> None:
        for button in (self.btn_scan, self.btn_clean, self.btn_safe, self.btn_none):
            button.setEnabled(not busy)

    def _on_failed(self, message: str) -> None:
        self._set_busy(False)
        self.progress.stop("Failed")
        self.console.append(message, "error")
        self.on_error(message)
