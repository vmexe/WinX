"""Settings: safety options, backup history and application folders."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from ... import __version__
from ...core import platform as pf
from ...core.config import backups_dir, data_dir, log_file
from ...core.workers import submit
from ..context import AppContext
from .base import Page


class SettingsPage(Page):
    key = "settings"
    title = "Settings"
    subtitle = "How WinX behaves when it changes something, and what it has changed so far."

    def __init__(self, ctx: AppContext):
        super().__init__(ctx)

        safety = QGroupBox("Safety")
        safety_layout = QVBoxLayout(safety)
        self.chk_backup = self._option(
            safety_layout,
            "safety/backup_enabled",
            "Back up the previous value before changing anything",
            "Backups are listed below and can be undone individually.",
        )
        self.chk_restore = self._option(
            safety_layout,
            "safety/restore_point",
            "Also create a Windows restore point before applying tweaks",
            "Needs administrator rights; adds a minute or so to each apply.",
        )
        self.chk_risky = self._option(
            safety_layout,
            "safety/show_risky",
            "Show advanced changes in the tweak lists",
            "",
        )
        self.chk_simulate = self._option(
            safety_layout,
            "safety/simulate",
            "Simulation mode — describe changes but never make them",
            "Takes effect the next time WinX starts.",
        )
        self.layout_.addWidget(safety)

        history = QGroupBox("History")
        history_layout = QVBoxLayout(history)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(4)
        self.tree.setHeaderLabels(["When", "Change", "Entries", "Restore point"])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        history_layout.addWidget(self.tree, 1)

        history_buttons = QHBoxLayout()
        self.btn_undo = QPushButton("Undo selected")
        self.btn_undo.clicked.connect(self._undo)
        history_buttons.addWidget(self.btn_undo)
        self.btn_delete = QPushButton("Delete record")
        self.btn_delete.clicked.connect(self._delete)
        history_buttons.addWidget(self.btn_delete)
        self.btn_clear = QPushButton("Clear history")
        self.btn_clear.clicked.connect(self._clear)
        history_buttons.addWidget(self.btn_clear)
        history_buttons.addStretch(1)
        self.btn_reload = QPushButton("Refresh")
        self.btn_reload.clicked.connect(self.refresh)
        history_buttons.addWidget(self.btn_reload)
        history_layout.addLayout(history_buttons)
        self.layout_.addWidget(history, 1)

        folders = QGroupBox("Folders")
        folders_layout = QVBoxLayout(folders)
        folders_layout.addWidget(self._path_row("Application data", str(data_dir())))
        folders_layout.addWidget(self._path_row("Backups", str(backups_dir())))
        folders_layout.addWidget(self._path_row("Log file", str(log_file())))
        self.layout_.addWidget(folders)

        about = QLabel(
            f"WinX {__version__} · {pf.os_display_name()} · "
            + ("administrator" if pf.is_admin() else "standard user")
        )
        about.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.layout_.addWidget(about)

    # -- helpers ---------------------------------------------------------
    def _option(self, layout, key: str, label: str, hint: str) -> QCheckBox:
        box = QCheckBox(label)
        box.setChecked(self.ctx.settings.bool(key))
        box.toggled.connect(lambda checked, k=key: self.ctx.settings.set(k, bool(checked)))
        layout.addWidget(box)
        if hint:
            note = QLabel(hint)
            note.setWordWrap(True)
            note.setEnabled(False)
            layout.addWidget(note)
        return box

    def _path_row(self, label: str, path: str):
        from PySide6.QtWidgets import QWidget

        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        caption = QLabel(f"{label}:")
        layout.addWidget(caption)
        value = QLabel(path)
        value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(value, 1)
        button = QPushButton("Open")
        button.clicked.connect(lambda _checked=False, p=path: pf.open_with_shell(p))
        layout.addWidget(button)
        return row

    # -- history ---------------------------------------------------------
    def refresh(self) -> None:
        self.tree.clear()
        for record in self.ctx.backups.all():
            item = QTreeWidgetItem(
                [
                    record.created_str,
                    record.label,
                    str(record.size),
                    "yes" if record.restore_point else "",
                ]
            )
            item.setData(0, Qt.ItemDataRole.UserRole, record.id)
            self.tree.addTopLevelItem(item)
        self.tree.resizeColumnToContents(0)
        has_records = self.tree.topLevelItemCount() > 0
        for button in (self.btn_undo, self.btn_delete, self.btn_clear):
            button.setEnabled(has_records)

    def _selected_id(self) -> str | None:
        item = self.tree.currentItem()
        return item.data(0, Qt.ItemDataRole.UserRole) if item else None

    def _undo(self) -> None:
        backup_id = self._selected_id()
        if not backup_id:
            QMessageBox.information(self, "Nothing selected", "Pick a record to undo.")
            return
        answer = QMessageBox.question(
            self,
            "Undo change",
            "Restore the previous values recorded in this backup?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        worker = submit(self.ctx.engine.undo, backup_id)
        worker.signals.message.connect(lambda m: self.log(m))
        worker.signals.result.connect(self._on_undone)
        worker.signals.error.connect(self.on_error)

    def _on_undone(self, report) -> None:
        self.log(report.summary(), "ok" if report.ok else "error")
        self.status(report.summary())
        QMessageBox.information(self, "Undo", report.summary())
        self.refresh()

    def _delete(self) -> None:
        backup_id = self._selected_id()
        if backup_id and self.ctx.backups.delete(backup_id):
            self.status("Backup record deleted")
            self.refresh()

    def _clear(self) -> None:
        answer = QMessageBox.question(
            self,
            "Clear history",
            "Delete every backup record?\n\nChanges already applied stay applied — you just lose the ability to undo them from here.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        removed = self.ctx.backups.clear()
        self.status(f"{removed} record(s) deleted")
        self.refresh()
