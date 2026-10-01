"""Settings, safety switches and the undo history."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
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
from ...core.format import human_size
from ...core.workers import submit
from ..context import AppContext
from ..icons import icon
from ..theme import ACCENTS
from ..widgets import LogConsole, ProgressRow
from .base import Page, section


class SettingsPage(Page):
    key = "settings"
    title = "Settings"
    subtitle = "How WinX behaves, what it backs up, and how to roll anything back."
    icon_name = "settings"

    def __init__(self, ctx: AppContext):
        super().__init__(ctx)
        self._build()

    def _build(self) -> None:
        layout = self.content_layout
        heading = QLabel("Settings")
        f = QFont()
        f.setPointSize(18)
        f.setWeight(QFont.Weight.Bold)
        heading.setFont(f)
        layout.addWidget(heading)

        sub = QLabel(self.subtitle)
        sub.setProperty("muted", True)
        layout.addWidget(sub)

        # ---- appearance -------------------------------------------------
        appearance = section("Appearance", "Applies immediately.")
        row = QHBoxLayout()
        row.setSpacing(8)
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["dark", "light"])
        self.theme_combo.setCurrentText(self.ctx.settings.str("general/theme") or "dark")
        self.theme_combo.currentTextChanged.connect(self._change_theme)
        row.addWidget(QLabel("Theme"))
        row.addWidget(self.theme_combo)
        row.addSpacing(16)
        self.accent_combo = QComboBox()
        self.accent_combo.addItems(list(ACCENTS))
        current = self.ctx.settings.str("general/accent")
        for name, value in ACCENTS.items():
            if value.lower() == (current or "").lower():
                self.accent_combo.setCurrentText(name)
                break
        self.accent_combo.currentTextChanged.connect(self._change_accent)
        row.addWidget(QLabel("Accent"))
        row.addWidget(self.accent_combo)
        row.addStretch(1)
        appearance.addLayout(row)
        layout.addLayout(appearance)

        # ---- safety -----------------------------------------------------
        safety = section("Safety", "These defaults are what every confirmation dialog uses.")
        grid = QVBoxLayout()
        grid.setSpacing(8)

        self.chk_backup = QCheckBox("Back up every change so it can be undone (recommended)")
        self.chk_backup.setChecked(self.ctx.settings.bool("safety/backup_enabled"))
        self.chk_backup.stateChanged.connect(lambda s: self._set("safety/backup_enabled", bool(s)))
        grid.addWidget(self.chk_backup)
        grid.addWidget(
            _note(
                "Before a registry value is written, WinX records what was there (including “nothing”). "
                "Turn this off if you want the smallest possible footprint — you lose one-click undo."
            )
        )

        self.chk_restore = QCheckBox("Also create a Windows System Restore point (administrator)")
        self.chk_restore.setChecked(self.ctx.settings.bool("safety/restore_point"))
        self.chk_restore.stateChanged.connect(lambda s: self._set("safety/restore_point", bool(s)))
        grid.addWidget(self.chk_restore)

        self.chk_confirm = QCheckBox("Ask for confirmation before every single change")
        self.chk_confirm.setChecked(self.ctx.settings.bool("safety/confirm_each"))
        self.chk_confirm.stateChanged.connect(lambda s: self._set("safety/confirm_each", bool(s)))
        grid.addWidget(self.chk_confirm)

        self.chk_risky = QCheckBox("Show advanced/high-impact settings")
        self.chk_risky.setChecked(self.ctx.settings.bool("safety/show_risky"))
        self.chk_risky.stateChanged.connect(lambda s: self._set("safety/show_risky", bool(s)))
        grid.addWidget(self.chk_risky)

        self.chk_simulate = QCheckBox("Simulation mode (show what would happen, change nothing)")
        self.chk_simulate.setChecked(pf.simulating())
        self.chk_simulate.setEnabled(pf.IS_WINDOWS)
        self.chk_simulate.setToolTip("Off-Windows builds always run in simulation mode")
        self.chk_simulate.stateChanged.connect(self._toggle_simulate)
        grid.addWidget(self.chk_simulate)

        safety.addLayout(grid)
        layout.addLayout(safety)

        # ---- history ----------------------------------------------------
        history = section("History & undo", "Every batch of changes WinX applies can be rolled back here.")
        self.history_tree = QTreeWidget()
        self.history_tree.setHeaderLabels(["When", "What", "Changes", "Restore point"])
        self.history_tree.setColumnWidth(0, 160)
        self.history_tree.setColumnWidth(1, 320)
        self.history_tree.setColumnWidth(2, 90)
        self.history_tree.setRootIsDecorated(False)
        self.history_tree.setAlternatingRowColors(True)
        self.history_tree.setMinimumHeight(200)
        self.history_tree.setMaximumHeight(240)
        history.addWidget(self.history_tree)

        hbar = QHBoxLayout()
        hbar.setSpacing(8)
        self.btn_undo = QPushButton(" Undo selected")
        self.btn_undo.setIcon(icon("undo", self.ctx.accent, 16))
        self.btn_undo.clicked.connect(self._undo)
        self.btn_delete = QPushButton("Delete record")
        self.btn_delete.setProperty("danger", True)
        self.btn_delete.clicked.connect(self._delete_backup)
        self.btn_clear = QPushButton("Clear all")
        self.btn_clear.setProperty("danger", True)
        self.btn_clear.clicked.connect(self._clear_backups)
        self.btn_open = QPushButton("Open backup folder")
        self.btn_open.clicked.connect(lambda: pf.open_with_shell(str(backups_dir())))
        hbar.addWidget(self.btn_undo)
        hbar.addWidget(self.btn_delete)
        hbar.addWidget(self.btn_clear)
        hbar.addStretch(1)
        hbar.addWidget(self.btn_open)
        history.addLayout(hbar)
        layout.addLayout(history)

        # ---- system actions ---------------------------------------------
        actions = section("System actions")
        abar = QHBoxLayout()
        abar.setSpacing(8)
        self.btn_restore_point = QPushButton("Create restore point now")
        self.btn_restore_point.clicked.connect(self._restore_point)
        self.btn_explorer = QPushButton("Restart Explorer")
        self.btn_explorer.clicked.connect(self._restart_explorer)
        self.btn_log = QPushButton("Open log file")
        self.btn_log.clicked.connect(lambda: pf.open_with_shell(str(log_file())))
        self.btn_data = QPushButton("Open app data folder")
        self.btn_data.clicked.connect(lambda: pf.open_with_shell(str(data_dir())))
        for b in (self.btn_restore_point, self.btn_explorer, self.btn_log, self.btn_data):
            abar.addWidget(b)
        abar.addStretch(1)
        actions.addLayout(abar)
        layout.addLayout(actions)

        # ---- about ------------------------------------------------------
        about = section("About")
        about_box = QFrame()
        about_box.setObjectName("Card")
        al = QVBoxLayout(about_box)
        al.setContentsMargins(14, 12, 14, 12)
        al.setSpacing(6)
        title = QLabel(f"WinX {__version__}")
        tf = QFont()
        tf.setPointSize(12)
        tf.setWeight(QFont.Weight.Bold)
        title.setFont(tf)
        al.addWidget(title)
        body = QLabel(
            "An all-in-one Windows utility: clean junk, tune performance, harden privacy, and repair "
            "broken system files — with every change previewed, backed up and reversible.\n\n"
            "Built with PySide6. Apache-2.0 licensed."
        )
        body.setWordWrap(True)
        body.setProperty("muted", True)
        al.addWidget(body)
        meta = QLabel(
            f"Python {pf_()} · Qt (PySide6) · mode: {'simulation' if pf.simulating() else 'live'}"
        )
        meta.setProperty("muted", True)
        al.addWidget(meta)
        if not pf.IS_WINDOWS:
            warn = QLabel(
                "You are running WinX outside Windows, so it is in simulation mode: scans and previews are real, "
                "but nothing is executed and the registry is a local sandbox file."
            )
            warn.setWordWrap(True)
            warn.setStyleSheet("color:#f5c451;")
            al.addWidget(warn)
        about.addWidget(about_box)
        layout.addLayout(about)

        self.progress = ProgressRow()
        layout.addWidget(self.progress)
        self.console = LogConsole(placeholder="Undo operations are logged here…")
        self.console.setFixedHeight(120)
        layout.addWidget(self.console)
        layout.addStretch(1)

    # -- callbacks -------------------------------------------------------
    def _set(self, key: str, value) -> None:
        self.ctx.settings.set(key, value)
        self.ctx.settings.sync()
        self.status("Setting saved")

    def _change_theme(self, name: str) -> None:
        self._set("general/theme", name)
        self.ctx.refresh_theme()

    def _change_accent(self, name: str) -> None:
        value = ACCENTS.get(name, "#4cc2ff")
        self._set("general/accent", value)
        self.ctx.refresh_theme()

    def _toggle_simulate(self, state: int) -> None:
        pf.set_simulating(bool(state))
        self.status("Simulation mode " + ("on" if state else "off"))

    def refresh(self) -> None:
        self._reload_history()

    def _reload_history(self) -> None:
        self.history_tree.clear()
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
            if record.simulated:
                item.setText(3, (item.text(3) + " simulated").strip())
            self.history_tree.addTopLevelItem(item)
        total = human_size(self.ctx.backups.total_bytes())
        self.status(f"{self.history_tree.topLevelItemCount()} backup record(s), {total} on disk")

    def _selected_id(self) -> str | None:
        items = self.history_tree.selectedItems()
        if not items:
            return None
        return items[0].data(0, Qt.ItemDataRole.UserRole)

    def _undo(self) -> None:
        backup_id = self._selected_id()
        if not backup_id:
            return
        answer = QMessageBox.question(
            self, "Undo changes", "Restore every value recorded in this backup to its previous state?"
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.progress.start("Undoing…")
        worker = submit(self._do_undo, backup_id)
        worker.signals.result.connect(self._on_undo)
        worker.signals.error.connect(self._on_error)

    def _do_undo(self, backup_id, emit=None):
        return self.ctx.engine.undo(backup_id, emit=emit)

    def _on_undo(self, report) -> None:
        self.progress.stop("undo finished")
        for step in report.steps:
            self.console.append(str(step), "ok" if step.ok else "error")
        self.console.append(report.summary(), "ok" if report.ok else "warn")
        self.status(report.summary())
        self._reload_history()

    def _delete_backup(self) -> None:
        backup_id = self._selected_id()
        if backup_id and self.ctx.backups.delete(backup_id):
            self.status("Backup record deleted")
            self._reload_history()

    def _clear_backups(self) -> None:
        answer = QMessageBox.question(
            self, "Clear history", "Delete every stored backup record? Undo will no longer be possible."
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        count = self.ctx.backups.clear()
        self.status(f"{count} record(s) deleted")
        self._reload_history()

    def _restore_point(self) -> None:
        self.progress.start("Creating restore point…")
        worker = submit(self._do_restore_point)
        worker.signals.result.connect(self._on_restore_point)
        worker.signals.error.connect(self._on_error)

    def _do_restore_point(self):
        from ...core.backup import create_restore_point

        return create_restore_point("WinX manual checkpoint")

    def _on_restore_point(self, payload) -> None:
        ok, detail = payload
        self.progress.stop("done")
        self.console.append(("Restore point created" if ok else "Failed: " + detail), "ok" if ok else "error")

    def _restart_explorer(self) -> None:
        self.ctx.engine.restart_explorer(emit=lambda m: self.console.append(m))
        self.status("Explorer restarted")

    def _on_error(self, message: str) -> None:
        self.progress.stop("failed")
        self.console.append(message, "error")


def _note(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setProperty("muted", True)
    label.setStyleSheet("font-size:11px; padding-left:24px;")
    return label


def pf_() -> str:
    import platform

    return platform.python_version()
