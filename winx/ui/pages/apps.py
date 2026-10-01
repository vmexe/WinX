"""Uninstaller / bloatware remover page."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
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
from ...core.workers import submit
from ...modules import apps
from ..context import AppContext
from ..icons import icon
from ..widgets import LogConsole, ProgressRow, SearchField, StatCard
from .base import Page


class AppsPage(Page):
    key = "apps"
    title = "Uninstaller"
    subtitle = "Remove pre-installed bloatware and ordinary programs — including Store apps Programs & Features hides."
    icon_name = "box"

    def __init__(self, ctx: AppContext):
        super().__init__(ctx)
        self.entries: list[apps.App] = []
        self._build()

    def _build(self) -> None:
        layout = self.content_layout

        header = QHBoxLayout()
        heading = QLabel("Uninstaller")
        font = QFont()
        font.setPointSize(18)
        font.setWeight(QFont.Weight.Bold)
        heading.setFont(font)
        header.addWidget(heading)
        header.addStretch(1)
        self.btn_refresh = QPushButton(" Refresh list")
        self.btn_refresh.setIcon(icon("refresh", self.ctx.accent, 16))
        self.btn_refresh.clicked.connect(self.refresh)
        header.addWidget(self.btn_refresh)
        layout.addLayout(header)

        sub = QLabel(self.subtitle)
        sub.setProperty("muted", True)
        sub.setWordWrap(True)
        layout.addWidget(sub)

        stats = QHBoxLayout()
        stats.setSpacing(10)
        self.stat_total = StatCard("Installed", "—", "", "box")
        self.stat_bloat = StatCard("Bloatware found", "—", "", "warning")
        self.stat_size = StatCard("Total size", "—", "where reported", "drive")
        stats.addWidget(self.stat_total)
        stats.addWidget(self.stat_bloat)
        stats.addWidget(self.stat_size)
        layout.addLayout(stats)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.search = SearchField("Search applications…")
        self.search.textChanged.connect(self._apply_filter)
        toolbar.addWidget(self.search)
        self.chk_bloat = QCheckBox("Show only suggested removals")
        self.chk_bloat.stateChanged.connect(self._apply_filter)
        toolbar.addWidget(self.chk_bloat)
        toolbar.addStretch(1)
        self.btn_select_bloat = QPushButton("Select suggested")
        self.btn_select_bloat.clicked.connect(self._select_bloat)
        self.btn_uninstall = QPushButton(" Uninstall selected")
        self.btn_uninstall.setIcon(icon("trash", self.ctx.accent, 16))
        self.btn_uninstall.setProperty("danger", True)
        self.btn_uninstall.clicked.connect(self._uninstall)
        toolbar.addWidget(self.btn_select_bloat)
        toolbar.addWidget(self.btn_uninstall)
        layout.addLayout(toolbar)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Application", "Version", "Publisher", "Size", "Source", "Installed"])
        self.tree.setAlternatingRowColors(True)
        self.tree.setColumnWidth(0, 300)
        self.tree.setColumnWidth(1, 110)
        self.tree.setColumnWidth(2, 190)
        self.tree.setColumnWidth(3, 80)
        self.tree.setColumnWidth(4, 70)
        self.tree.setMinimumHeight(280)
        self.tree.setRootIsDecorated(False)
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        layout.addWidget(self.tree, 1)

        self.progress = ProgressRow()
        layout.addWidget(self.progress)

        self.console = LogConsole(placeholder="Uninstall output appears here…")
        self.console.setFixedHeight(150)
        layout.addWidget(self.console)

    # -- data ------------------------------------------------------------
    def refresh(self) -> None:
        self.progress.start("Reading installed applications…")
        worker = submit(self._load)
        worker.signals.progress.connect(lambda d, t, m: self.progress.set(d, t, m or "Loading…"))
        worker.signals.result.connect(self._on_loaded)
        worker.signals.error.connect(self._on_error)

    def _load(self, progress=None):
        return apps.installed_apps(progress=progress)

    def _on_loaded(self, entries) -> None:
        self.entries = entries
        self._populate()
        bloat = [a for a in entries if apps.is_bloat_app(a)[0]]
        total_bytes = sum(a.size_mb for a in entries) * 1024 * 1024
        self.stat_total.set_value(str(len(entries)), f"{len(entries)} apps detected")
        self.stat_bloat.set_value(str(len(bloat)), "suggested for removal")
        self.stat_size.set_value(human_size(total_bytes), "reported by installers")
        self.progress.stop(f"{len(entries)} applications")
        self.status(f"{len(entries)} applications, {len(bloat)} suggested removals")

    def _populate(self) -> None:
        self.tree.clear()
        for app in self.entries:
            is_bloat, reason = apps.is_bloat_app(app)
            row = QTreeWidgetItem(
                [
                    app.name + ("  • suggested" if is_bloat else ""),
                    app.version,
                    app.publisher,
                    app.size_text,
                    app.source,
                    app.installed,
                ]
            )
            row.setData(0, Qt.ItemDataRole.UserRole, app.name)
            row.setFlags(row.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            row.setCheckState(0, Qt.CheckState.Unchecked)
            if is_bloat:
                row.setForeground(0, QColor("#f5c451"))
                row.setToolTip(0, reason)
            if not app.removable:
                row.setText(4, app.source + " (protected)")
            self.tree.addTopLevelItem(row)

    def _apply_filter(self, *_args) -> None:
        needle = self.search.text().strip().lower()
        only_bloat = self.chk_bloat.isChecked()
        for i in range(self.tree.topLevelItemCount()):
            row = self.tree.topLevelItem(i)
            name = (row.data(0, Qt.ItemDataRole.UserRole) or "").lower()
            is_bloat = apps.is_bloat(row.data(0, Qt.ItemDataRole.UserRole) or "")[0]
            show = (not needle or needle in name or needle in row.text(2).lower())
            if show and only_bloat and not is_bloat:
                show = False
            row.setHidden(not show)

    def _selected_apps(self) -> list[apps.App]:
        names = set()
        for i in range(self.tree.topLevelItemCount()):
            row = self.tree.topLevelItem(i)
            if row.checkState(0) == Qt.CheckState.Checked:
                names.add(row.data(0, Qt.ItemDataRole.UserRole))
        return [a for a in self.entries if a.name in names]

    def _select_bloat(self) -> None:
        for i in range(self.tree.topLevelItemCount()):
            row = self.tree.topLevelItem(i)
            name = row.data(0, Qt.ItemDataRole.UserRole)
            if apps.is_bloat(name or "")[0]:
                row.setCheckState(0, Qt.CheckState.Checked)

    def _uninstall(self) -> None:
        selected = self._selected_apps()
        if not selected:
            return
        answer = QMessageBox.question(
            self,
            "Confirm uninstall",
            f"Remove {len(selected)} application(s)?\n\n"
            + "\n".join(f" • {a.name}" for a in selected[:12])
            + ("\n …" if len(selected) > 12 else "")
            + "\n\nStore apps are removed for all users where possible. This cannot be undone.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self.btn_uninstall.setEnabled(False)
        self.progress.start(f"Removing {len(selected)} application(s)…")
        worker = submit(self._do_uninstall, selected)
        worker.signals.message.connect(lambda m: self.log(m))
        worker.signals.result.connect(self._on_uninstall_done)
        worker.signals.error.connect(self._on_error)

    def _do_uninstall(self, selected, emit=None):
        return apps.uninstall_many(selected, emit=emit)

    def _on_uninstall_done(self, payload) -> None:
        ok_count, total = payload
        self.btn_uninstall.setEnabled(True)
        self.progress.stop("uninstall finished")
        self.log(f"Removed {ok_count}/{total} application(s)", "ok" if ok_count == total else "warn")
        self.status(f"Removed {ok_count}/{total}")
        self.refresh()

    def _on_error(self, message: str) -> None:
        self.btn_uninstall.setEnabled(True)
        self.progress.stop("failed")
        self.log(message, "error")
