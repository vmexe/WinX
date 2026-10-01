"""Disks: volumes, drive health and storage analysis."""

from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core import platform as pf
from ...core.format import human_size
from ...core.workers import submit
from ...modules import disks
from ..context import AppContext
from ..widgets import ProgressRow
from .base import Page


class DisksPage(Page):
    key = "disks"
    title = "Disks"
    subtitle = "Drive health, and where your space has gone."

    def __init__(self, ctx: AppContext):
        super().__init__(ctx)
        self.volumes: list[disks.Volume] = []
        self._worker = None

        self.tabs = QTabWidget()
        self.layout_.addWidget(self.tabs, 1)
        self.tabs.addTab(self._build_volumes(), "Volumes")
        self.tabs.addTab(self._build_health(), "Drive health")
        self.tabs.addTab(self._build_analysis(), "Storage analysis")

        self.progress = ProgressRow(cancellable=True)
        self.progress.cancel_button.clicked.connect(self._cancel)
        self.layout_.addWidget(self.progress)

    # -- tabs ------------------------------------------------------------
    def _build_volumes(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.volumes_tree = QTreeWidget()
        self.volumes_tree.setColumnCount(8)
        self.volumes_tree.setHeaderLabels(
            ["Drive", "Label", "File system", "Media", "Health", "Capacity", "Free", "Used"]
        )
        self.volumes_tree.setRootIsDecorated(False)
        self.volumes_tree.setAlternatingRowColors(True)
        self.volumes_tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.volumes_tree, 1)

        buttons = QHBoxLayout()
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.clicked.connect(self.refresh)
        buttons.addWidget(self.btn_refresh)
        self.btn_optimise = QPushButton("Optimise drive")
        self.btn_optimise.clicked.connect(self._optimise)
        buttons.addWidget(self.btn_optimise)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        return page

    def _build_health(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.health_tree = QTreeWidget()
        self.health_tree.setColumnCount(7)
        self.health_tree.setHeaderLabels(
            ["Disk", "Media", "Health", "Power-on hours", "Read errors", "Write errors", "Temperature"]
        )
        self.health_tree.setRootIsDecorated(False)
        self.health_tree.setAlternatingRowColors(True)
        self.health_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.health_tree, 1)
        return page

    def _build_analysis(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Folder:"))
        self.root_combo = QComboBox()
        self.root_combo.setEditable(True)
        self.root_combo.setMinimumWidth(260)
        controls.addWidget(self.root_combo, 1)
        self.btn_browse = QPushButton("Browse…")
        self.btn_browse.clicked.connect(self._browse)
        controls.addWidget(self.btn_browse)

        controls.addWidget(QLabel("Minimum size (MB):"))
        self.min_size = QSpinBox()
        self.min_size.setRange(1, 100000)
        self.min_size.setValue(50)
        controls.addWidget(self.min_size)
        layout.addLayout(controls)

        self.analysis_tree = QTreeWidget()
        self.analysis_tree.setColumnCount(3)
        self.analysis_tree.setHeaderLabels(["Path", "Size", "Files"])
        self.analysis_tree.setAlternatingRowColors(True)
        self.analysis_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.analysis_tree.itemActivated.connect(self._open_selected)
        layout.addWidget(self.analysis_tree, 1)

        buttons = QHBoxLayout()
        self.btn_folders = QPushButton("Folder sizes")
        self.btn_folders.clicked.connect(self._folder_sizes)
        buttons.addWidget(self.btn_folders)
        self.btn_large = QPushButton("Largest files")
        self.btn_large.clicked.connect(self._largest_files)
        buttons.addWidget(self.btn_large)
        self.btn_dups = QPushButton("Find duplicates")
        self.btn_dups.clicked.connect(self._duplicates)
        buttons.addWidget(self.btn_dups)
        buttons.addStretch(1)
        self.btn_open = QPushButton("Open location")
        self.btn_open.clicked.connect(self._open_selected)
        buttons.addWidget(self.btn_open)
        layout.addLayout(buttons)
        return page

    # -- data ------------------------------------------------------------
    def refresh(self) -> None:
        self.btn_refresh.setEnabled(False)
        self.progress.start("Reading drives…")
        worker = submit(self._load)
        worker.signals.result.connect(self._on_loaded)
        worker.signals.error.connect(self._on_failed)

    def _load(self):
        # An explicit visit to this page is the one place that wants live
        # media/health data rather than the cached answer.
        disks.invalidate_cache()
        return (disks.volumes(), disks.smart_report())

    def _on_loaded(self, payload) -> None:
        self.btn_refresh.setEnabled(True)
        volumes, smart = payload
        self.volumes = volumes
        self.progress.stop("")

        self.volumes_tree.clear()
        for vol in volumes:
            item = QTreeWidgetItem(
                [
                    vol.drive,
                    vol.label,
                    vol.fs,
                    vol.media,
                    vol.health,
                    vol.total_text,
                    vol.free_text,
                    f"{vol.used_pct}%",
                ]
            )
            item.setData(0, Qt.ItemDataRole.UserRole, vol)
            self.volumes_tree.addTopLevelItem(item)
        self.volumes_tree.resizeColumnToContents(0)

        self.health_tree.clear()
        for row in smart:
            self.health_tree.addTopLevelItem(
                QTreeWidgetItem(
                    [
                        str(row.get("disk", "")),
                        str(row.get("model", "")),
                        str(row.get("health", "")),
                        str(row.get("power_hours") or "—"),
                        str(row.get("read_errors") if row.get("read_errors") is not None else "—"),
                        str(row.get("write_errors") if row.get("write_errors") is not None else "—"),
                        f"{row.get('temp_c')} °C" if row.get("temp_c") else "—",
                    ]
                )
            )

        current = self.root_combo.currentText()
        self.root_combo.clear()
        self.root_combo.addItems([v.mount or v.drive for v in volumes] or [os.path.expanduser("~")])
        if current:
            self.root_combo.setEditText(current)
        self.status(f"{len(volumes)} volume(s)")

    def _on_failed(self, message: str) -> None:
        self.btn_refresh.setEnabled(True)
        self._set_busy(False)
        self.progress.stop("Failed")
        self.on_error(message)

    # -- analysis --------------------------------------------------------
    def _root(self) -> str:
        return self.root_combo.currentText().strip() or os.path.expanduser("~")

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choose a folder to analyse", self._root())
        if folder:
            self.root_combo.setEditText(folder)

    def _start(self, fn, *args, message: str = "Working…"):
        self._set_busy(True)
        self.progress.start(message)
        self.analysis_tree.clear()
        self._worker = submit(fn, *args)
        self._worker.signals.progress.connect(lambda d, t, m: self.progress.set(d, t, m))
        self._worker.signals.error.connect(self._on_failed)
        return self._worker

    def _folder_sizes(self) -> None:
        worker = self._start(self._do_folders, self._root(), message="Measuring folders…")
        worker.signals.result.connect(self._show_entries)

    def _do_folders(self, root, progress=None, is_cancelled=None):
        return disks.folder_sizes(root, depth=2, progress=progress, is_cancelled=is_cancelled)

    def _largest_files(self) -> None:
        worker = self._start(
            self._do_largest, self._root(), self.min_size.value(), message="Looking for large files…"
        )
        worker.signals.result.connect(self._show_entries)

    def _do_largest(self, root, min_mb, progress=None, is_cancelled=None):
        return disks.largest_files(
            root, top_n=200, min_size=min_mb * 1024 * 1024, progress=progress, is_cancelled=is_cancelled
        )

    def _duplicates(self) -> None:
        worker = self._start(
            self._do_dups, [self._root()], self.min_size.value(), message="Comparing files…"
        )
        worker.signals.result.connect(self._show_duplicates)

    def _do_dups(self, roots, min_mb, progress=None, is_cancelled=None):
        return disks.find_duplicates(
            roots, min_size=min_mb * 1024 * 1024, progress=progress, is_cancelled=is_cancelled
        )

    def _show_entries(self, entries: list) -> None:
        self._set_busy(False)
        self.analysis_tree.clear()
        for entry in entries:
            item = QTreeWidgetItem([entry.path, entry.size_text, str(entry.files or "")])
            item.setData(0, Qt.ItemDataRole.UserRole, entry.path)
            self.analysis_tree.addTopLevelItem(item)
        total = sum(e.size for e in entries)
        self.progress.stop(f"{len(entries)} results — {human_size(total)}")

    def _show_duplicates(self, groups: list) -> None:
        self._set_busy(False)
        self.analysis_tree.clear()
        wasted = 0
        for group in groups:
            parent = QTreeWidgetItem(
                [f"{len(group.paths)} copies", human_size(group.size), group.wasted_text]
            )
            for path in group.paths:
                child = QTreeWidgetItem([path, "", ""])
                child.setData(0, Qt.ItemDataRole.UserRole, path)
                parent.addChild(child)
            self.analysis_tree.addTopLevelItem(parent)
            wasted += group.wasted
        self.analysis_tree.expandAll()
        self.progress.stop(f"{len(groups)} duplicate group(s) — {human_size(wasted)} wasted")

    def _open_selected(self, *_args) -> None:
        item = self.analysis_tree.currentItem()
        path = item.data(0, Qt.ItemDataRole.UserRole) if item else None
        if not path:
            return
        folder = path if os.path.isdir(path) else os.path.dirname(path)
        if not pf.open_with_shell(folder):
            QMessageBox.information(self, "Could not open", folder)

    # -- volume actions --------------------------------------------------
    def _optimise(self) -> None:
        item = self.volumes_tree.currentItem()
        vol = item.data(0, Qt.ItemDataRole.UserRole) if item else None
        if vol is None:
            QMessageBox.information(self, "No drive selected", "Pick a drive in the list first.")
            return
        is_ssd = "ssd" in (vol.media or "").lower()
        verb = "Run TRIM on" if is_ssd else "Defragment"
        answer = QMessageBox.question(
            self,
            "Optimise drive",
            f"{verb} {vol.drive}?\n\nThis can take a while and runs in the background.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.progress.start(f"Optimising {vol.drive}…")
        worker = submit(disks.optimize, vol.drive, is_ssd)
        worker.signals.result.connect(self._on_optimised)
        worker.signals.error.connect(self._on_failed)

    def _on_optimised(self, payload) -> None:
        ok, detail = payload
        self.progress.stop("Optimisation finished" if ok else "Optimisation failed")
        self.log(detail or ("Drive optimised" if ok else "Drive optimisation failed"), "ok" if ok else "error")

    # -- plumbing --------------------------------------------------------
    def _cancel(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            self.progress.stop("Cancelled")
            self._set_busy(False)

    def _set_busy(self, busy: bool) -> None:
        for button in (self.btn_folders, self.btn_large, self.btn_dups, self.btn_browse):
            button.setEnabled(not busy)
