"""Startup manager page: logon programs, startup folders, tasks and services."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core.workers import submit
from ...modules import startup
from ..context import AppContext
from ..icons import icon
from ..widgets import LogConsole, ProgressRow, StatCard
from .base import Page

_IMPACT_COLOR = {"High": "#ff6b6b", "Medium": "#f5c451", "Low": "#3ecf8e"}


class StartupPage(Page):
    key = "startup"
    title = "Startup"
    subtitle = "Everything that launches when Windows starts. Disabling an entry is reversible — deleting is not."
    icon_name = "power"

    def __init__(self, ctx: AppContext):
        super().__init__(ctx)
        self.items: list[startup.StartupItem] = []
        self._build()

    def _build(self) -> None:
        layout = self.content_layout
        header = QHBoxLayout()
        heading = QLabel("Startup")
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
        sub.setWordWrap(True)
        layout.addWidget(sub)

        stats = QHBoxLayout()
        stats.setSpacing(10)
        self.stat_total = StatCard("Startup entries", "—", "", "power")
        self.stat_enabled = StatCard("Enabled", "—", "", "check")
        self.stat_heavy = StatCard("High impact", "—", "", "warning")
        self.stat_services = StatCard("Auto services", "—", "", "sliders")
        stats.addWidget(self.stat_total)
        stats.addWidget(self.stat_enabled)
        stats.addWidget(self.stat_heavy)
        stats.addWidget(self.stat_services)
        layout.addLayout(stats)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)

        # --- tab 1: logon entries ---------------------------------------
        tab = QWidget()
        tl = QVBoxLayout(tab)
        tl.setSpacing(8)

        bar = QHBoxLayout()
        self.btn_disable = QPushButton("Disable selected")
        self.btn_enable = QPushButton("Enable selected")
        self.btn_delete = QPushButton("Delete selected")
        self.btn_delete.setProperty("danger", True)
        self.btn_disable.clicked.connect(lambda: self._set_enabled(False))
        self.btn_enable.clicked.connect(lambda: self._set_enabled(True))
        self.btn_delete.clicked.connect(self._delete_selected)
        bar.addWidget(self.btn_disable)
        bar.addWidget(self.btn_enable)
        bar.addWidget(self.btn_delete)
        bar.addStretch(1)
        tl.addLayout(bar)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Name", "Type", "Location", "Impact", "Command"])
        self.tree.setAlternatingRowColors(True)
        self.tree.setColumnWidth(0, 210)
        self.tree.setColumnWidth(1, 90)
        self.tree.setColumnWidth(2, 230)
        self.tree.setColumnWidth(3, 80)
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.tree.setRootIsDecorated(False)
        self.tree.setMinimumHeight(240)
        tl.addWidget(self.tree, 1)
        self.tabs.addTab(tab, "Startup programs")

        # --- tab 2: services --------------------------------------------
        services_tab = QWidget()
        sl = QVBoxLayout(services_tab)
        sl.setSpacing(8)
        info = QLabel(
            "Services that start automatically with Windows. Set one to Manual if you do not need it — "
            "Disabled should be reserved for things you are sure about."
        )
        info.setProperty("muted", True)
        info.setWordWrap(True)
        sl.addWidget(info)

        self.services_tree = QTreeWidget()
        self.services_tree.setHeaderLabels(["Service", "Description", "Status", "Start type", "Change to"])
        self.services_tree.setAlternatingRowColors(True)
        self.services_tree.setColumnWidth(0, 230)
        self.services_tree.setColumnWidth(1, 200)
        self.services_tree.setColumnWidth(2, 90)
        self.services_tree.setColumnWidth(3, 110)
        self.services_tree.setRootIsDecorated(False)
        self.services_tree.setMinimumHeight(240)
        sl.addWidget(self.services_tree, 1)
        self.tabs.addTab(services_tab, "Services")

        self.progress = ProgressRow()
        layout.addWidget(self.progress)

        self.console = LogConsole(placeholder="Startup changes are logged here…")
        self.console.setFixedHeight(120)
        layout.addWidget(self.console)

    # -- data ------------------------------------------------------------
    def refresh(self) -> None:
        self.progress.start("Enumerating startup entries…")
        worker = submit(self._load)
        worker.signals.progress.connect(lambda d, t, m: self.progress.set(d, t, m or "Scanning…"))
        worker.signals.result.connect(self._on_loaded)
        worker.signals.error.connect(self._on_error)

    def _load(self, progress=None, emit=None):
        items = startup.enumerate_items(progress=progress, emit=emit)
        return (items, startup.services_rows())

    def _on_loaded(self, payload) -> None:
        items, services_rows = payload
        self.items = items
        self._populate(items)
        self._populate_services(services_rows)
        enabled = sum(1 for i in items if i.enabled)
        heavy = sum(1 for i in items if i.enabled and i.impact == "High")
        self.stat_total.set_value(str(len(items)), f"{len(items)} entries found")
        self.stat_enabled.set_value(str(enabled), f"{enabled} launch at logon")
        self.stat_heavy.set_value(str(heavy), "worth reviewing" if heavy else "nothing heavy")
        self.stat_services.set_value(str(len(services_rows)), "start automatically")
        self.progress.stop("Startup scan complete")
        self.status(f"{len(items)} startup entries, {enabled} enabled")

    def _populate(self, items) -> None:
        self.tree.clear()
        for item in items:
            row = QTreeWidgetItem([item.name, item.type, item.display_location, item.impact, item.command])
            row.setData(0, Qt.ItemDataRole.UserRole, item.name + "|" + item.type)
            row.setToolTip(4, item.command)
            row.setToolTip(2, item.display_location)
            if not item.enabled:
                for col in range(5):
                    row.setForeground(col, QColor("#8b98a9"))
                row.setText(3, "—")
            else:
                row.setForeground(3, QColor(_IMPACT_COLOR.get(item.impact, "#8b98a9")))
            self.tree.addTopLevelItem(row)

    def _populate_services(self, rows) -> None:
        self.services_tree.clear()
        for row in rows:
            item = QTreeWidgetItem(
                [row["name"], row["display"], row["state"].title(), row["start"], ""]
            )
            self.services_tree.addTopLevelItem(item)
            combo = QComboBox()
            combo.addItems(["(unchanged)", "Automatic", "Automatic (Delayed)", "Manual", "Disabled"])
            combo.setFixedWidth(170)
            combo.setProperty("service", row["name"])
            combo.currentTextChanged.connect(lambda text, c=combo: self._change_service(c, text))
            self.services_tree.setItemWidget(item, 4, combo)

    def _change_service(self, combo: QComboBox, text: str) -> None:
        mapping = {
            "Automatic": "auto",
            "Automatic (Delayed)": "delayed-auto",
            "Manual": "demand",
            "Disabled": "disabled",
        }
        if text not in mapping:
            return
        name = combo.property("service")
        answer = QMessageBox.question(
            self,
            "Change service",
            f"Set “{name}” start type to “{text}”?\n\nThe previous setting is stored so you can change it back.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            combo.setCurrentIndex(0)
            return
        ok, err = startup.set_service_start(name, mapping[text])
        if ok:
            self.log(f"Service {name} → {text}", "ok")
            self.status(f"{name} set to {text}")
        else:
            self.log(f"Service {name}: {err}", "error")
            QMessageBox.warning(self, "Could not change service", err or "Unknown error")
        combo.setCurrentIndex(0)
        self.refresh()

    # -- actions ---------------------------------------------------------
    def _selected_items(self):
        names = []
        for row in self.tree.selectedItems():
            key = row.data(0, Qt.ItemDataRole.UserRole)
            if key:
                names.append(key)
        out = []
        for item in self.items:
            if (item.name + "|" + item.type) in names:
                out.append(item)
        return out

    def _set_enabled(self, enabled: bool) -> None:
        items = self._selected_items()
        if not items:
            return
        verb = "Enable" if enabled else "Disable"
        answer = QMessageBox.question(
            self,
            f"{verb} startup entries",
            f"{verb} {len(items)} entr{'y' if len(items) == 1 else 'ies'}?\n\n"
            + "\n".join(f" • {i.name}" for i in items[:10])
            + ("\n …" if len(items) > 10 else "")
            + ("\n\nDisabled entries are renamed, not deleted, so they can be restored." if not enabled else ""),
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        ok_count = 0
        for item in items:
            ok, err = startup.set_enabled(item, enabled)
            if ok:
                ok_count += 1
                self.log(f"{verb}d: {item.name}", "ok")
            else:
                self.log(f"{verb} failed for {item.name}: {err}", "error")
        self.status(f"{ok_count}/{len(items)} entries {verb.lower()}d")
        self.refresh()

    def _delete_selected(self) -> None:
        items = self._selected_items()
        if not items:
            return
        answer = QMessageBox.question(
            self,
            "Delete startup entries",
            f"Permanently remove {len(items)} entr{'y' if len(items) == 1 else 'ies'}?\n\n"
            + "\n".join(f" • {i.name}" for i in items[:10])
            + "\n\nThis cannot be undone with WinX. Consider disabling instead.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        removed = 0
        for item in items:
            ok, err = startup.remove(item)
            if ok:
                removed += 1
                self.log(f"Removed: {item.name}", "warn")
            else:
                self.log(f"Remove failed for {item.name}: {err}", "error")
        self.status(f"Removed {removed} entries")
        self.refresh()

    def _on_error(self, message: str) -> None:
        self.progress.stop("failed")
        self.log(message, "error")
