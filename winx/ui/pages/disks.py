"""Disks page: volumes, health, storage analysis and duplicate files."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
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
from ..icons import icon
from ..widgets import Badge, LogConsole, ProgressRow, StatCard
from .base import Page


class DisksPage(Page):
    key = "disks"
    title = "Disks"
    subtitle = "Free space, drive health, and what is actually eating your disk."
    icon_name = "drive"

    def __init__(self, ctx: AppContext):
        super().__init__(ctx)
        self._worker = None
        self.volumes: list[disks.Volume] = []
        self._build()

    def _build(self) -> None:
        layout = self.content_layout

        header = QHBoxLayout()
        heading = QLabel("Disks")
        font = QFont()
        font.setPointSize(18)
        font.setWeight(QFont.Weight.Bold)
        heading.setFont(font)
        header.addWidget(heading)
        header.addStretch(1)
        self.btn_refresh = QPushButton(" Refresh")
        self.btn_refresh.setIcon(icon("refresh", self.ctx.accent, 16))
        self.btn_refresh.clicked.connect(self.refresh)
        header.addWidget(self.btn_refresh)
        layout.addLayout(header)

        sub = QLabel(self.subtitle)
        sub.setProperty("muted", True)
        layout.addWidget(sub)

        self.volumes_row = QHBoxLayout()
        self.volumes_row.setSpacing(10)
        layout.addLayout(self.volumes_row)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)

        # folders tab
        folders = QWidget()
        fl = QVBoxLayout(folders)
        bar = QHBoxLayout()
        self.drive_combo = QComboBox()
        self.drive_combo.setMinimumWidth(180)
        self.drive_combo.currentTextChanged.connect(self._populate_drives_dependent)
        bar.addWidget(QLabel("Drive:"))
        bar.addWidget(self.drive_combo)
        self.btn_folders = QPushButton("Analyse folders")
        self.btn_folders.clicked.connect(self._analyse_folders)
        self.btn_large = QPushButton("Find large files")
        self.btn_large.clicked.connect(self._find_large)
        self.min_size = QSpinBox()
        self.min_size.setRange(1, 10000)
        self.min_size.setValue(100)
        self.min_size.setSuffix(" MB")
        self.min_size.setFixedWidth(110)
        bar.addWidget(self.btn_folders)
        bar.addWidget(self.btn_large)
        bar.addWidget(QLabel("Larger than"))
        bar.addWidget(self.min_size)
        bar.addStretch(1)
        fl.addLayout(bar)
        self.folders_tree = QTreeWidget()
        self.folders_tree.setHeaderLabels(["Path", "Size", "Files"])
        self.folders_tree.setColumnWidth(0, 620)
        self.folders_tree.setColumnWidth(1, 110)
        self.folders_tree.setRootIsDecorated(False)
        self.folders_tree.setAlternatingRowColors(True)
        self.folders_tree.setMinimumHeight(240)
        fl.addWidget(self.folders_tree, 1)
        actions = QHBoxLayout()
        self.btn_open = QPushButton("Open location")
        self.btn_open.clicked.connect(self._open_selected)
        self.btn_delete_file = QPushButton("Delete selected file")
        self.btn_delete_file.setProperty("danger", True)
        self.btn_delete_file.clicked.connect(self._delete_selected)
        actions.addWidget(self.btn_open)
        actions.addWidget(self.btn_delete_file)
        actions.addStretch(1)
        fl.addLayout(actions)
        self.tabs.addTab(folders, "Storage analysis")

        # duplicates tab
        dups = QWidget()
        dl = QVBoxLayout(dups)
        dbar = QHBoxLayout()
        self.btn_dups = QPushButton("Find duplicate files")
        self.btn_dups.clicked.connect(self._find_duplicates)
        self.dup_min = QSpinBox()
        self.dup_min.setRange(1, 5000)
        self.dup_min.setValue(5)
        self.dup_min.setSuffix(" MB")
        self.dup_min.setFixedWidth(110)
        dbar.addWidget(self.btn_dups)
        dbar.addWidget(QLabel("Minimum size"))
        dbar.addWidget(self.dup_min)
        dbar.addStretch(1)
        dl.addLayout(dbar)
        self.dups_tree = QTreeWidget()
        self.dups_tree.setHeaderLabels(["Group / File", "Size", "Reclaimable"])
        self.dups_tree.setColumnWidth(0, 620)
        self.dups_tree.setColumnWidth(1, 110)
        self.dups_tree.setAlternatingRowColors(True)
        self.dups_tree.setMinimumHeight(240)
        dl.addWidget(self.dups_tree, 1)
        self.tabs.addTab(dups, "Duplicates")

        # health tab
        health = QWidget()
        hl = QVBoxLayout(health)
        self.health_tree = QTreeWidget()
        self.health_tree.setHeaderLabels(["Disk", "Type", "Health", "Power-on hours", "Read errors", "Temp"])
        self.health_tree.setColumnWidth(0, 260)
        self.health_tree.setRootIsDecorated(False)
        self.health_tree.setAlternatingRowColors(True)
        hl.addWidget(self.health_tree, 1)
        self.tabs.addTab(health, "Health")

        self.progress = ProgressRow()
        layout.addWidget(self.progress)
        self.console = LogConsole(placeholder="Disk analysis output…")
        self.console.setFixedHeight(110)
        layout.addWidget(self.console)

    # -- data ------------------------------------------------------------
    def refresh(self) -> None:
        worker = submit(self._load)
        worker.signals.result.connect(self._on_loaded)
        worker.signals.error.connect(self._on_error)

    def _load(self):
        return (disks.volumes(), disks.smart_report())

    def _on_loaded(self, payload) -> None:
        volumes, smart = payload
        self.volumes = volumes
        self._populate_volumes()
        self._populate_health(smart)
        self.drive_combo.blockSignals(True)
        self.drive_combo.clear()
        for v in volumes:
            self.drive_combo.addItem(f"{v.drive}  {v.label}".strip(), v.mount)
        self.drive_combo.blockSignals(False)
        self.status(f"{len(volumes)} volume(s) detected")

    def _populate_volumes(self) -> None:
        while self.volumes_row.count():
            item = self.volumes_row.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        for vol in self.volumes:
            card = StatCard(
                f"{vol.drive} {vol.label}".strip(),
                vol.free_text + " free",
                f"{vol.total_text} total · {vol.used_pct}% used · {vol.media or vol.fs}".strip(" ·"),
                "drive",
            )
            card.bar.show()
            card.bar.setValue(vol.used_pct)
            if vol.used_pct >= 90:
                card.bar.setStyleSheet("QProgressBar::chunk { background: #ff6b6b; }")
            elif vol.used_pct >= 75:
                card.bar.setStyleSheet("QProgressBar::chunk { background: #f5c451; }")

            buttons = QHBoxLayout()
            btn_opt = QPushButton("Optimise")
            btn_opt.clicked.connect(lambda _c=False, v=vol: self._optimise(v))
            buttons.addWidget(btn_opt)
            card.layout().addLayout(buttons)

            if vol.smart and vol.smart.lower() not in ("ok", "healthy", ""):
                card.layout().addWidget(Badge(vol.smart, "#ff6b6b"))
            self.volumes_row.addWidget(card)

    def _populate_health(self, rows) -> None:
        self.health_tree.clear()
        for row in rows:
            item = QTreeWidgetItem(
                [
                    str(row.get("disk", "")),
                    str(row.get("model", "")),
                    str(row.get("health", "")),
                    str(row.get("power_hours", "") or "—"),
                    str(row.get("read_errors", "") or "—"),
                    f"{row['temp_c']}°C" if row.get("temp_c") else "—",
                ]
            )
            health = str(row.get("health", "")).lower()
            if health and health not in ("healthy", "ok"):
                item.setForeground(2, _color("#ff6b6b"))
            self.health_tree.addTopLevelItem(item)

    def _populate_drives_dependent(self, *_args) -> None:
        pass

    # -- analysis --------------------------------------------------------
    def _current_root(self) -> str:
        return self.drive_combo.currentData() or (self.volumes[0].mount if self.volumes else "/")

    def _analyse_folders(self) -> None:
        self.folders_tree.clear()
        self.progress.start("Measuring folders…")
        root = self._current_root()
        worker = submit(self._folders, root)
        worker.signals.progress.connect(lambda d, t, m: self.progress.set(d, t, m or "Measuring…"))
        worker.signals.result.connect(self._on_folders)
        worker.signals.error.connect(self._on_error)

    def _folders(self, root, progress=None, is_cancelled=None):
        return disks.folder_sizes(root, depth=2, progress=progress, is_cancelled=is_cancelled)

    def _on_folders(self, entries) -> None:
        self.progress.stop(f"{len(entries)} folders measured")
        self.folders_tree.clear()
        for entry in entries[:200]:
            item = QTreeWidgetItem([entry.path, entry.size_text, f"{entry.files:,}"])
            item.setData(0, Qt.ItemDataRole.UserRole, entry.path)
            self.folders_tree.addTopLevelItem(item)
        self.log(f"Folder analysis: {len(entries)} folders, largest {entries[0].size_text if entries else '—'}", "ok")

    def _find_large(self) -> None:
        self.folders_tree.clear()
        self.progress.start("Searching for large files…")
        root = self._current_root()
        min_size = self.min_size.value() * 1024 * 1024
        worker = submit(self._large, root, min_size)
        worker.signals.progress.connect(lambda d, _t, m: self.progress.set(d, 0, m or "Scanning…"))
        worker.signals.result.connect(self._on_folders)
        worker.signals.error.connect(self._on_error)

    def _large(self, root, min_size, progress=None, is_cancelled=None):
        return disks.largest_files(root, top_n=200, min_size=min_size, progress=progress, is_cancelled=is_cancelled)

    def _find_duplicates(self) -> None:
        self.dups_tree.clear()
        self.progress.start("Hashing files…")
        roots = [v.mount for v in self.volumes] or [self._current_root()]
        min_size = self.dup_min.value() * 1024 * 1024
        worker = submit(self._dups, roots, min_size)
        worker.signals.progress.connect(lambda d, t, m: self.progress.set(d, t, m or "Comparing…"))
        worker.signals.result.connect(self._on_dups)
        worker.signals.error.connect(self._on_error)

    def _dups(self, roots, min_size, progress=None, is_cancelled=None):
        return disks.find_duplicates(roots, min_size=min_size, progress=progress, is_cancelled=is_cancelled)

    def _on_dups(self, groups) -> None:
        self.progress.stop(f"{len(groups)} duplicate group(s)")
        wasted = sum(g.wasted for g in groups)
        for group in groups[:150]:
            parent = QTreeWidgetItem([f"{len(group.paths)} identical files", human_size(group.size), group.wasted_text])
            self.dups_tree.addTopLevelItem(parent)
            for path in group.paths:
                child = QTreeWidgetItem([path, human_size(group.size), ""])
                child.setData(0, Qt.ItemDataRole.UserRole, path)
                parent.addChild(child)
            parent.setExpanded(False)
        self.log(f"Found {len(groups)} duplicate groups ({human_size(wasted)} reclaimable)", "ok")
        self.status(f"{human_size(wasted)} reclaimable in duplicates")

    # -- actions ---------------------------------------------------------
    def _selected_path(self) -> str | None:
        tree = self.folders_tree if self.tabs.currentIndex() == 0 else self.dups_tree
        items = tree.selectedItems()
        if not items:
            return None
        return items[0].data(0, Qt.ItemDataRole.UserRole)

    def _open_selected(self) -> None:
        path = self._selected_path()
        if not path:
            return
        import os

        folder = path if os.path.isdir(path) else os.path.dirname(path)
        pf.open_with_shell(folder)

    def _delete_selected(self) -> None:
        path = self._selected_path()
        if not path:
            return
        import os

        if os.path.isdir(path):
            QMessageBox.information(self, "Not a file", "Select an individual file to delete.")
            return
        answer = QMessageBox.question(self, "Delete file", f"Permanently delete?\n\n{path}")
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            os.remove(path)
            self.log(f"Deleted {path}", "warn")
            self.status("File deleted")
        except OSError as exc:
            QMessageBox.warning(self, "Could not delete", str(exc))

    def _optimise(self, vol: disks.Volume) -> None:
        is_ssd = str(vol.media).upper() == "SSD"
        answer = QMessageBox.question(
            self,
            "Optimise drive",
            f"{'TRIM' if is_ssd else 'Defragment'} {vol.drive}?\n\n"
            "This can take a while on large mechanical drives.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.progress.start(f"Optimising {vol.drive}…")
        worker = submit(self._do_optimise, vol.drive, is_ssd)
        worker.signals.result.connect(self._on_optimise)
        worker.signals.error.connect(self._on_error)

    def _do_optimise(self, drive, is_ssd):
        return disks.optimize(drive, is_ssd)

    def _on_optimise(self, payload) -> None:
        ok, detail = payload
        self.progress.stop("done")
        self.log(("Drive optimised" if ok else "Optimisation failed") + (f": {detail}" if detail else ""),
                 "ok" if ok else "error")

    def _on_error(self, message: str) -> None:
        self.progress.stop("failed")
        self.log(message, "error")


def _color(value: str):
    from PySide6.QtGui import QColor

    return QColor(value)
