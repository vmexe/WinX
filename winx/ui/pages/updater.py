"""Updater: one page that updates programs, Store apps and Windows itself."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core import platform as pf
from ...core.format import human_size
from ...core.workers import submit
from ...modules import updater
from .. import sysicons
from ..context import AppContext
from ..widgets import LogConsole, ProgressRow
from .base import Page

GROUP_LABEL = {
    "windows": "Windows updates",
    "winget": "Program updates",
    "store": "Store apps",
}


class UpdaterPage(Page):
    key = "updater"
    title = "Updater"
    subtitle = (
        "Everything that can be brought up to date, in one place: Windows itself, "
        "the programs winget knows about, and Microsoft Store apps."
    )

    #: checking asks winget and Windows Update, which take a while
    cache_ttl = 1800.0

    def __init__(self, ctx: AppContext):
        super().__init__(ctx)
        self.updates: list[updater.Update] = []

        self.layout_.addLayout(self.cache_row("Check for updates"))

        self.summary_box = QGroupBox("Summary")
        summary_layout = QHBoxLayout(self.summary_box)
        summary_layout.setSpacing(24)
        self.lbl_windows = self._summary_label(summary_layout, "Windows")
        self.lbl_programs = self._summary_label(summary_layout, "Programs")
        self.lbl_download = self._summary_label(summary_layout, "To download")
        summary_layout.addStretch(1)
        self.layout_.addWidget(self.summary_box)

        filters = QHBoxLayout()
        filters.addWidget(QLabel("Show:"))
        self.combo_show = QComboBox()
        for label, value in [
            ("Everything", "all"),
            ("Windows only", "windows"),
            ("Programs only", "winget"),
        ]:
            self.combo_show.addItem(label, value)
        self.combo_show.currentIndexChanged.connect(self._apply_filter)
        filters.addWidget(self.combo_show)
        filters.addStretch(1)
        self.btn_all = QPushButton("Select all")
        self.btn_all.clicked.connect(lambda: self._set_all(True))
        filters.addWidget(self.btn_all)
        self.btn_none = QPushButton("Select none")
        self.btn_none.clicked.connect(lambda: self._set_all(False))
        filters.addWidget(self.btn_none)
        self.layout_.addLayout(filters)

        self.tabs = QTabWidget()
        self.layout_.addWidget(self.tabs, 1)

        available = QWidget()
        available_layout = QVBoxLayout(available)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(4)
        self.tree.setHeaderLabels(["Name", "Version", "Download", "Note"])
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setIconSize(QSize(22, 22))
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.itemChanged.connect(lambda *_: self._update_buttons())
        available_layout.addWidget(self.tree, 1)
        self.tabs.addTab(available, "Available updates")

        history = QWidget()
        history_layout = QVBoxLayout(history)
        self.history_tree = QTreeWidget()
        self.history_tree.setColumnCount(3)
        self.history_tree.setHeaderLabels(["Installed", "Update", "Result"])
        self.history_tree.setRootIsDecorated(False)
        self.history_tree.setAlternatingRowColors(True)
        self.history_tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        history_layout.addWidget(self.history_tree, 1)
        self.tabs.addTab(history, "Recently installed")

        self.progress = ProgressRow(cancellable=True)
        self.progress.cancel_button.clicked.connect(self._cancel)
        self.layout_.addWidget(self.progress)

        self.console = LogConsole("Update output appears here.")
        self.console.setMaximumHeight(130)
        self.layout_.addWidget(self.console)

        buttons = QHBoxLayout()
        self.btn_update = QPushButton("Update selected")
        self.btn_update.setDefault(True)
        self.btn_update.setEnabled(False)
        self.btn_update.clicked.connect(self._update_selected)
        buttons.addWidget(self.btn_update)

        self.btn_store = QPushButton("Check the Microsoft Store")
        self.btn_store.clicked.connect(self._store_scan)
        buttons.addWidget(self.btn_store)

        self.btn_settings = QPushButton("Open Windows Update")
        self.btn_settings.clicked.connect(
            lambda: pf.open_with_shell("ms-settings:windowsupdate")
        )
        buttons.addWidget(self.btn_settings)
        buttons.addStretch(1)

        self.btn_winx = QPushButton("Check for a new WinX")
        self.btn_winx.clicked.connect(self._check_winx)
        buttons.addWidget(self.btn_winx)
        self.layout_.addLayout(buttons)

        self._worker = None

    # -- helpers ---------------------------------------------------------
    def _summary_label(self, layout, caption: str) -> QLabel:
        box = QVBoxLayout()
        value = QLabel("—")
        font = value.font()
        font.setPointSizeF(font.pointSizeF() * 1.6)
        value.setFont(font)
        title = QLabel(caption)
        title.setEnabled(False)
        box.addWidget(value)
        box.addWidget(title)
        layout.addLayout(box)
        return value

    # -- data ------------------------------------------------------------
    def refresh(self) -> None:
        self._set_busy(True)
        self.progress.start("Checking for updates…")
        worker = submit(self._load)
        worker.signals.progress.connect(lambda d, t, m: self.progress.set(d, t, m))
        worker.signals.result.connect(self._on_loaded)
        worker.signals.error.connect(self._on_failed)

    def _load(self, progress=None):
        return (updater.all_updates(progress=progress), updater.windows_update_history())

    def _on_loaded(self, payload) -> None:
        self._set_busy(False)
        updates, history = payload
        self.updates = updates

        windows = [u for u in updates if u.source == "windows"]
        programs = [u for u in updates if u.source != "windows"]
        total_bytes = sum(u.size for u in updates)
        self.lbl_windows.setText(str(len(windows)))
        self.lbl_programs.setText(str(len(programs)))
        self.lbl_download.setText(human_size(total_bytes) if total_bytes else "—")

        self.tree.blockSignals(True)
        self.tree.clear()
        for source in ("windows", "winget", "store"):
            rows = [u for u in updates if u.source == source]
            if not rows:
                continue
            heading = QTreeWidgetItem([f"{GROUP_LABEL[source]}  ({len(rows)})", "", "", ""])
            font = heading.font(0)
            font.setBold(True)
            heading.setFont(0, font)
            heading.setFlags(Qt.ItemFlag.ItemIsEnabled)
            heading.setFirstColumnSpanned(True)
            self.tree.addTopLevelItem(heading)
            for update in rows:
                item = QTreeWidgetItem(
                    [
                        update.name,
                        update.version_text,
                        human_size(update.size) if update.size else "",
                        self._note_for(update),
                    ]
                )
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(0, Qt.CheckState.Checked)
                item.setData(0, Qt.ItemDataRole.UserRole, update)
                icon = sysicons.file_icon(update.icon_path) if update.icon_path else None
                item.setIcon(
                    0,
                    icon
                    if icon is not None and not icon.isNull()
                    else sysicons.page_icon("updater" if source == "windows" else "apps"),
                )
                heading.addChild(item)
            heading.setExpanded(True)
        self.tree.blockSignals(False)
        self.tree.resizeColumnToContents(1)
        self.tree.resizeColumnToContents(2)

        self.history_tree.clear()
        for row in history:
            self.history_tree.addTopLevelItem(
                QTreeWidgetItem([row.get("date", ""), row.get("title", ""), row.get("result", "")])
            )
        self.history_tree.resizeColumnToContents(0)

        count = len(updates)
        message = "Everything is up to date" if not count else f"{count} update(s) available"
        self.progress.stop(message)
        self.status(message)
        self._apply_filter()
        self._update_buttons()
        self.mark_loaded()

    def _note_for(self, update: updater.Update) -> str:
        bits = [b for b in (update.note,) if b]
        if update.needs_reboot:
            bits.append("needs a restart")
        if update.needs_admin and not self.ctx.is_admin:
            bits.append("needs administrator")
        return " · ".join(bits)

    def _on_failed(self, message: str) -> None:
        self._set_busy(False)
        self.progress.stop("Could not check for updates")
        self.on_error(message)

    # -- selection -------------------------------------------------------
    def _rows(self):
        for i in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(i)
            for j in range(group.childCount()):
                yield group.child(j)

    def _selected(self) -> list[updater.Update]:
        return [
            row.data(0, Qt.ItemDataRole.UserRole)
            for row in self._rows()
            if row.checkState(0) == Qt.CheckState.Checked and not row.isHidden()
        ]

    def _set_all(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        self.tree.blockSignals(True)
        for row in self._rows():
            if not row.isHidden():
                row.setCheckState(0, state)
        self.tree.blockSignals(False)
        self._update_buttons()

    def _apply_filter(self, *_args) -> None:
        choice = self.combo_show.currentData()
        for i in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(i)
            shown = 0
            for j in range(group.childCount()):
                row = group.child(j)
                update = row.data(0, Qt.ItemDataRole.UserRole)
                visible = choice == "all" or update.source == choice
                row.setHidden(not visible)
                shown += int(visible)
            group.setHidden(shown == 0)
        self._update_buttons()

    def _update_buttons(self) -> None:
        selected = self._selected()
        self.btn_update.setEnabled(bool(selected))
        self.btn_update.setText(
            f"Update {len(selected)} item(s)" if selected else "Update selected"
        )

    # -- actions ---------------------------------------------------------
    def _update_selected(self) -> None:
        selected = self._selected()
        if not selected:
            return
        windows = [u for u in selected if u.source == "windows"]
        programs = [u for u in selected if u.source == "winget"]

        if windows and not self.ctx.is_admin and not self.ctx.simulating:
            answer = QMessageBox.question(
                self,
                "Administrator required",
                "Installing Windows updates needs administrator rights.\n\n"
                "Restart WinX as administrator now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if answer == QMessageBox.StandardButton.Yes:
                self.ctx.elevate()
            return

        names = "\n".join(f"  • {u.name}" for u in selected[:10])
        more = f"\n  … and {len(selected) - 10} more" if len(selected) > 10 else ""
        answer = QMessageBox.question(
            self,
            "Install updates",
            f"Install {len(selected)} update(s)?\n\n{names}{more}\n\n"
            "Windows updates can restart your PC when they finish.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self._set_busy(True)
        self.progress.start("Installing updates…")
        self._worker = submit(self._install, programs, bool(windows))
        self._worker.signals.message.connect(self.console.append)
        self._worker.signals.progress.connect(lambda d, t, m: self.progress.set(d, t, m))
        self._worker.signals.result.connect(self._on_installed)
        self._worker.signals.error.connect(self._on_failed)

    def _install(self, programs, do_windows, emit=None, progress=None, cancel=None):
        emit = emit or (lambda _line: None)
        progress = progress or (lambda *_a: None)
        done, failed = 0, 0
        total = len(programs) + (1 if do_windows else 0)
        step = 0

        for update in programs:
            if cancel is not None and cancel():
                break
            step += 1
            progress(step, total, f"updating {update.name}")
            emit(f"--- {update.name} ({update.identifier})")
            ok, detail = updater.upgrade_app(update.identifier, emit=emit, cancel=cancel)
            emit(detail)
            done += int(ok)
            failed += int(not ok)

        if do_windows and not (cancel is not None and cancel()):
            step += 1
            progress(step, total, "installing Windows updates")
            ok, detail = updater.install_windows_updates(emit=emit, progress=progress, cancel=cancel)
            emit(detail)
            done += int(ok)
            failed += int(not ok)

        return (done, failed)

    def _on_installed(self, payload) -> None:
        self._set_busy(False)
        done, failed = payload
        message = f"{done} update(s) finished" + (f", {failed} failed" if failed else "")
        self.progress.stop(message)
        self.log(message, "ok" if not failed else "warn")
        self.status(message)
        self.force_refresh()

    def _store_scan(self) -> None:
        self.progress.start("Asking the Microsoft Store to check for app updates…")
        worker = submit(updater.store_scan)
        worker.signals.message.connect(self.console.append)
        worker.signals.result.connect(self._on_store)
        worker.signals.error.connect(self._on_failed)

    def _on_store(self, payload) -> None:
        ok, detail = payload
        self.progress.stop(f"Microsoft Store: {detail}")
        self.log(f"Microsoft Store: {detail}", "ok" if ok else "warn")

    def _check_winx(self) -> None:
        window = self.window()
        if hasattr(window, "check_for_updates"):
            window.check_for_updates(quiet=False)

    def _cancel(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            self.progress.stop("Cancelled")
            self._set_busy(False)

    def _set_busy(self, busy: bool) -> None:
        for button in (self.btn_update, self.btn_store, self.btn_settings, self.btn_winx):
            button.setEnabled(not busy)
        if not busy:
            self._update_buttons()
