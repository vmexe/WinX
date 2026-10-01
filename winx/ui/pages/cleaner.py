"""Junk cleaner page: scan → review → clean."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
)

from ...core.format import human_size
from ...core.model import MODERATE, RISKY, SAFE
from ...core.workers import submit
from ...modules import cleaner
from ..context import AppContext
from ..icons import icon
from ..widgets import LogConsole, ProgressRow, StatCard
from .base import Page

GROUP_ORDER = ["Windows", "Browsers", "Apps", "Developer", "Demo"]

_RISK_COLOR = {SAFE: "#3ecf8e", MODERATE: "#f5c451", RISKY: "#ff6b6b"}


class CleanerPage(Page):
    key = "cleaner"
    title = "Cleaner"
    subtitle = "Find and remove temporary files, caches and leftovers from well-known locations only."
    icon_name = "trash"

    def __init__(self, ctx: AppContext):
        super().__init__(ctx)
        self.results: list[cleaner.ScanResult] = []
        self._worker = None
        self._targets = cleaner.all_targets()
        self._build()

    # -- ui --------------------------------------------------------------
    def _build(self) -> None:
        layout = self.content_layout

        header = QHBoxLayout()
        heading = QLabel("Cleaner")
        font = QFont()
        font.setPointSize(18)
        font.setWeight(QFont.Weight.Bold)
        heading.setFont(font)
        header.addWidget(heading)
        header.addStretch(1)
        self.btn_scan = QPushButton(" Scan")
        self.btn_scan.setIcon(icon("refresh", self.ctx.accent, 16))
        self.btn_scan.setProperty("accent", True)
        self.btn_scan.clicked.connect(self.refresh)
        header.addWidget(self.btn_scan)
        self.btn_clean = QPushButton(" Clean selected")
        self.btn_clean.setIcon(icon("trash", self.ctx.accent, 16))
        self.btn_clean.setEnabled(False)
        self.btn_clean.clicked.connect(self._clean)
        header.addWidget(self.btn_clean)
        layout.addLayout(header)

        sub = QLabel(self.subtitle)
        sub.setProperty("muted", True)
        sub.setWordWrap(True)
        layout.addWidget(sub)

        cards = QHBoxLayout()
        cards.setSpacing(10)
        self.stat_junk = StatCard("Removable junk", "—", "Run a scan to measure", "trash")
        self.stat_files = StatCard("Files", "—", "", "folder")
        self.stat_freed = StatCard("Freed this session", "0 B", "", "spark")
        cards.addWidget(self.stat_junk)
        cards.addWidget(self.stat_files)
        cards.addWidget(self.stat_freed)
        layout.addLayout(cards)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.btn_all = QPushButton("Select all")
        self.btn_all.clicked.connect(lambda: self._select(True, only_safe=False))
        self.btn_safe = QPushButton("Select safe only")
        self.btn_safe.clicked.connect(lambda: self._select(True, only_safe=True))
        self.btn_none = QPushButton("Select none")
        self.btn_none.clicked.connect(lambda: self._select(False))
        self.chk_admin = QCheckBox("Include items that need administrator rights")
        self.chk_admin.setChecked(True)
        self.chk_admin.stateChanged.connect(self._update_selection_state)
        toolbar.addWidget(self.btn_all)
        toolbar.addWidget(self.btn_safe)
        toolbar.addWidget(self.btn_none)
        toolbar.addStretch(1)
        toolbar.addWidget(self.chk_admin)
        layout.addLayout(toolbar)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Target", "Size", "Files", "Type"])
        self.tree.setRootIsDecorated(True)
        self.tree.setAlternatingRowColors(True)
        self.tree.setColumnWidth(0, 380)
        self.tree.setColumnWidth(1, 110)
        self.tree.setColumnWidth(2, 80)
        self.tree.setMinimumHeight(260)
        self.tree.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.tree, 1)

        self.progress = ProgressRow()
        layout.addWidget(self.progress)

        self.console = LogConsole(placeholder="Scan and clean output appears here…")
        self.console.setFixedHeight(150)
        layout.addWidget(self.console)

        self._freed = 0

    # -- data ------------------------------------------------------------
    def refresh(self) -> None:
        self.btn_scan.setEnabled(False)
        self.btn_clean.setEnabled(False)
        self.progress.start("Scanning…")
        self._worker = submit(self._scan)
        self._worker.signals.progress.connect(lambda d, t, m: self.progress.set(d, t, m or "Scanning…"))
        self._worker.signals.result.connect(self._on_scan_done)
        self._worker.signals.error.connect(self._on_error)

    def _scan(self, progress=None, is_cancelled=None):
        return cleaner.scan(progress=progress, is_cancelled=is_cancelled)

    def _on_scan_done(self, results) -> None:
        self.btn_scan.setEnabled(True)
        self.progress.stop(f"Scan complete — {len(results)} locations")
        self.results = results
        self._populate()
        total = sum(r.size for r in results if not r.unmeasured)
        files = sum(r.files for r in results)
        self.stat_junk.set_value(human_size(total), f"{len(results)} locations checked")
        self.stat_files.set_value(f"{files:,}", "candidate files")
        self.log(f"Scan finished: {human_size(total)} removable across {files:,} files", "ok")
        self.status(f"Scan complete: {human_size(total)} of junk found")
        self._update_selection_state()

    def _on_error(self, message: str) -> None:
        self.btn_scan.setEnabled(True)
        self.progress.stop("scan failed")
        self.log(message, "error")

    # -- tree ------------------------------------------------------------
    def _populate(self) -> None:
        self.tree.blockSignals(True)
        self.tree.clear()
        groups: dict[str, list[cleaner.ScanResult]] = {}
        for result in self.results:
            groups.setdefault(result.group, []).append(result)

        ordered = [g for g in GROUP_ORDER if g in groups] + [g for g in sorted(groups) if g not in GROUP_ORDER]
        for group in ordered:
            rows = groups[group]
            total = sum(r.size for r in rows if not r.unmeasured)
            parent = QTreeWidgetItem([group, human_size(total), "", f"{len(rows)} items"])
            parent.setFlags(parent.flags() | Qt.ItemFlag.ItemIsAutoTristate | Qt.ItemFlag.ItemIsUserCheckable)
            parent.setCheckState(0, Qt.CheckState.Unchecked)
            font = parent.font(0)
            font.setWeight(QFont.Weight.DemiBold)
            parent.setFont(0, font)
            self.tree.addTopLevelItem(parent)
            for result in sorted(rows, key=lambda r: r.size, reverse=True):
                child = QTreeWidgetItem(
                    [
                        result.name,
                        result.size_text,
                        f"{result.files:,}" if result.files else "—",
                        "command" if result.unmeasured else result.group,
                    ]
                )
                child.setData(0, Qt.ItemDataRole.UserRole, result.key)
                child.setFlags(child.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                child.setCheckState(0, Qt.CheckState.Unchecked)
                child.setToolTip(0, result.description)
                if result.risk != SAFE:
                    child.setForeground(0, _QColor(_RISK_COLOR[result.risk]))
                if result.admin:
                    child.setText(3, (child.text(3) + " • admin").strip())
                parent.addChild(child)
            parent.setExpanded(True)
        self.tree.blockSignals(False)

    def _select(self, state: bool, only_safe: bool = False) -> None:
        self.tree.blockSignals(True)
        for i in range(self.tree.topLevelItemCount()):
            parent = self.tree.topLevelItem(i)
            for j in range(parent.childCount()):
                child = parent.child(j)
                key = child.data(0, Qt.ItemDataRole.UserRole)
                result = self._result_for(key)
                if result is None:
                    continue
                if only_safe and result.risk != SAFE:
                    child.setCheckState(0, Qt.CheckState.Unchecked)
                    continue
                if state and result.admin and not self.chk_admin.isChecked():
                    child.setCheckState(0, Qt.CheckState.Unchecked)
                    continue
                child.setCheckState(0, Qt.CheckState.Checked if state else Qt.CheckState.Unchecked)
        self.tree.blockSignals(False)
        self._update_selection_state()

    def _on_item_changed(self, item, column: int) -> None:
        if column != 0:
            return
        self._update_selection_state()

    def _result_for(self, key: str):
        for r in self.results:
            if r.key == key:
                return r
        return None

    def _selected_keys(self) -> list[str]:
        keys: list[str] = []
        for i in range(self.tree.topLevelItemCount()):
            parent = self.tree.topLevelItem(i)
            for j in range(parent.childCount()):
                child = parent.child(j)
                if child.checkState(0) == Qt.CheckState.Checked:
                    key = child.data(0, Qt.ItemDataRole.UserRole)
                    if key:
                        keys.append(key)
        return keys

    def _selected_total(self) -> int:
        total = 0
        for key in self._selected_keys():
            result = self._result_for(key)
            if result and not result.unmeasured:
                total += result.size
        return total

    def _update_selection_state(self, *_args) -> None:
        keys = self._selected_keys()
        total = self._selected_total()
        self.btn_clean.setEnabled(bool(keys))
        if keys:
            self.btn_clean.setText(f" Clean {len(keys)} item(s) — {human_size(total)}")
        else:
            self.btn_clean.setText(" Clean selected")

    # -- cleaning --------------------------------------------------------
    def _clean(self) -> None:
        keys = self._selected_keys()
        if not keys:
            return
        targets = [t for t in self._targets if t.key in keys]
        risky = [t.name for t in targets if t.risk != SAFE]
        message = (
            f"This will permanently delete {self._selected_total() and human_size(self._selected_total()) or 'the selected files'}\n"
            f"across {len(targets)} location(s).\n\nFiles in use are skipped, never forced."
        )
        if risky:
            message += "\n\nAdvanced targets included:\n • " + "\n • ".join(risky)
        answer = QMessageBox.question(self, "Confirm cleanup", message)
        if answer != QMessageBox.StandardButton.Yes:
            return

        backup = self.ctx.settings.bool("safety/backup_enabled")
        if backup:
            self.log("Backups are not created for file deletion — cleaning is not reversible.", "warn")

        self.btn_clean.setEnabled(False)
        self.btn_scan.setEnabled(False)
        self.progress.start("Cleaning…")
        worker = submit(self._do_clean, targets)
        worker.signals.progress.connect(lambda d, t, m: self.progress.set(d, t, m or "Cleaning…"))
        worker.signals.message.connect(lambda m: self.log(m))
        worker.signals.result.connect(self._on_clean_done)
        worker.signals.error.connect(self._on_error)

    def _do_clean(self, targets, progress=None, emit=None, is_cancelled=None):
        return cleaner.clean(targets, progress=progress, emit=emit, is_cancelled=is_cancelled)

    def _on_clean_done(self, outcomes) -> None:
        self.progress.stop("Cleaning finished")
        self.btn_scan.setEnabled(True)
        freed = sum(o.freed for o in outcomes)
        files = sum(o.files for o in outcomes)
        skipped = sum(o.skipped for o in outcomes)
        self._freed += freed
        self.stat_freed.set_value(human_size(self._freed), f"{files:,} files deleted, {skipped} skipped")
        self.log(f"Freed {human_size(freed)} ({files:,} files, {skipped} skipped)", "ok")
        for outcome in outcomes:
            if outcome.error and outcome.skipped:
                self.log(f"{outcome.name}: {outcome.skipped} file(s) skipped — {outcome.error}", "warn")
        self.status(f"Freed {human_size(freed)}")
        QMessageBox.information(
            self, "Cleanup complete", f"Freed {human_size(freed)}\n{files:,} files deleted\n{skipped} skipped (in use)"
        )
        self.refresh()


def _QColor(value: str):  # local import shim to keep the module import-light
    from PySide6.QtGui import QColor

    return QColor(value)
