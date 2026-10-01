"""Tweaks: reversible settings, shown as a checkable list."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from ...core.engine import OFF, ON
from ...core.model import MODERATE, RISK_LABEL, RISKY, SAFE, TweakDef
from ...core.workers import submit
from ...modules import tweaks_data
from ..context import AppContext
from ..widgets import ProgressRow
from .base import Page

STATE_TEXT = {ON: "On", OFF: "Off"}

#: risk -> the heading its tweaks are grouped under
GROUP_TITLE = {
    SAFE: "Recommended",
    MODERATE: "Moderate",
    RISKY: "Advanced",
}


class TweaksPage(Page):
    """A checkable list of tweaks for one category."""

    def __init__(
        self,
        ctx: AppContext,
        category: str,
        key: str,
        title: str,
        subtitle: str,
    ):
        self.key = key
        self.title = title
        self.subtitle = subtitle
        super().__init__(ctx)

        self.category = category
        self.tweaks: list[TweakDef] = tweaks_data.by_category(category)
        self.states: dict[str, str] = {}
        self.items: dict[str, QTreeWidgetItem] = {}
        self.groups: dict[str, QTreeWidgetItem] = {}

        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search these tweaks…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._apply_filter)
        filters.addWidget(self.search, 1)
        filters.addWidget(QLabel("Risk:"))
        self.combo_risk = QComboBox()
        for label, value in [
            ("Recommended only", "safe"),
            ("Recommended and moderate", "moderate"),
            ("Everything, including advanced", "all"),
        ]:
            self.combo_risk.addItem(label, value)
        self.combo_risk.setCurrentIndex(
            2 if self.ctx.settings.bool("safety/show_risky") else 1
        )
        self.combo_risk.currentIndexChanged.connect(self._apply_filter)
        filters.addWidget(self.combo_risk)

        filters.addWidget(QLabel("State:"))
        self.combo_state = QComboBox()
        for label, value in [("Any", "any"), ("On", ON), ("Off", OFF)]:
            self.combo_state.addItem(label, value)
        self.combo_state.currentIndexChanged.connect(self._apply_filter)
        filters.addWidget(self.combo_state)
        self.layout_.addLayout(filters)
        self.layout_.addLayout(self.cache_row("Re-read current state"))

        self.tree = QTreeWidget()
        self.tree.setColumnCount(4)
        self.tree.setHeaderLabels(["Tweak", "Current", "Risk", "Needs"])
        self.tree.setRootIsDecorated(True)
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.itemChanged.connect(self._item_changed)
        self.tree.currentItemChanged.connect(self._show_description)
        self.layout_.addWidget(self.tree, 1)

        self.description = QLabel("")
        self.description.setWordWrap(True)
        self.layout_.addWidget(self.description)

        self.progress = ProgressRow()
        self.layout_.addWidget(self.progress)

        buttons = QHBoxLayout()
        # the Refresh button sits next to the "Updated …" line above
        self.btn_reload = self.refresh_button
        self.btn_safe = QPushButton("Select recommended")
        self.btn_safe.clicked.connect(self._select_safe)
        buttons.addWidget(self.btn_safe)
        self.btn_reset = QPushButton("Discard changes")
        self.btn_reset.clicked.connect(self._reset_pending)
        buttons.addWidget(self.btn_reset)
        buttons.addStretch(1)

        self.backup_box = QCheckBox("Back up before applying")
        self.backup_box.setChecked(self.ctx.settings.bool("safety/backup_enabled"))
        buttons.addWidget(self.backup_box)
        self.btn_preview = QPushButton("Preview")
        self.btn_preview.clicked.connect(self._preview)
        buttons.addWidget(self.btn_preview)
        self.btn_apply = QPushButton("Apply")
        self.btn_apply.setDefault(True)
        self.btn_apply.clicked.connect(self._apply)
        buttons.addWidget(self.btn_apply)
        self.layout_.addLayout(buttons)

        self._populate()
        self._update_buttons()

    # -- tree ------------------------------------------------------------
    def _populate(self) -> None:
        """Build the list, grouped by risk so the page reads as three short
        sections rather than one thirty-row wall."""
        self.tree.blockSignals(True)
        self.tree.clear()
        self.items.clear()
        self.groups.clear()

        for risk in (SAFE, MODERATE, RISKY):
            tweaks = [t for t in self.tweaks if t.risk == risk]
            if not tweaks:
                continue
            heading = QTreeWidgetItem([GROUP_TITLE.get(risk, risk), "", "", ""])
            font = heading.font(0)
            font.setBold(True)
            heading.setFont(0, font)
            heading.setFirstColumnSpanned(True)
            heading.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.tree.addTopLevelItem(heading)
            self.groups[risk] = heading

            for tweak in tweaks:
                needs = []
                if tweak.admin:
                    needs.append("administrator")
                if tweak.restart == "explorer":
                    needs.append("Explorer restart")
                elif tweak.restart == "pc":
                    needs.append("reboot")
                item = QTreeWidgetItem(
                    [tweak.name, "…", RISK_LABEL.get(tweak.risk, tweak.risk), ", ".join(needs)]
                )
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(0, Qt.CheckState.Unchecked)
                item.setData(0, Qt.ItemDataRole.UserRole, tweak)
                item.setToolTip(0, tweak.description)
                heading.addChild(item)
                self.items[tweak.key] = item
            heading.setExpanded(risk != RISKY)

        self.tree.blockSignals(False)
        self.tree.resizeColumnToContents(1)
        self.tree.resizeColumnToContents(2)
        self._apply_filter()

    def refresh(self) -> None:
        self.btn_reload.setEnabled(False)
        self.progress.start("Reading the current settings…")
        worker = submit(self._load_states)
        worker.signals.result.connect(self._on_states)
        worker.signals.error.connect(self._on_failed)

    def _load_states(self):
        return self.ctx.engine.states(self.tweaks)

    def _on_states(self, states: dict) -> None:
        self.btn_reload.setEnabled(True)
        self.states = states
        self.progress.stop("")
        self.tree.blockSignals(True)
        for key, item in self.items.items():
            state = states.get(key, "unknown")
            item.setText(1, STATE_TEXT.get(state, "Unknown"))
            item.setCheckState(
                0, Qt.CheckState.Checked if state == ON else Qt.CheckState.Unchecked
            )
            item.setDisabled(False)
        self.tree.blockSignals(False)
        for column in (1, 2, 3):
            self.tree.resizeColumnToContents(column)
        self._update_buttons()
        self._apply_filter()
        self.status(f"{len(states)} settings read")
        self.mark_loaded()

    def _on_failed(self, message: str) -> None:
        self.btn_reload.setEnabled(True)
        self.progress.stop("Failed")
        self.on_error(message)

    # -- pending changes -------------------------------------------------
    def _pending(self) -> list[tuple[TweakDef, bool]]:
        out: list[tuple[TweakDef, bool]] = []
        for key, item in self.items.items():
            tweak = item.data(0, Qt.ItemDataRole.UserRole)
            desired = item.checkState(0) == Qt.CheckState.Checked
            current = self.states.get(key)
            if current is None:
                continue
            if (current == ON) != desired:
                out.append((tweak, desired))
        return out

    def _item_changed(self, *_args) -> None:
        self._update_buttons()

    def _update_buttons(self) -> None:
        pending = self._pending()
        self.btn_apply.setEnabled(bool(pending))
        self.btn_preview.setEnabled(bool(pending))
        self.btn_reset.setEnabled(bool(pending))
        self.btn_apply.setText(f"Apply {len(pending)} change(s)" if pending else "Apply")

    def _reset_pending(self) -> None:
        self.tree.blockSignals(True)
        for key, item in self.items.items():
            state = self.states.get(key)
            item.setCheckState(0, Qt.CheckState.Checked if state == ON else Qt.CheckState.Unchecked)
        self.tree.blockSignals(False)
        self._update_buttons()

    def _select_safe(self) -> None:
        self.tree.blockSignals(True)
        for item in self.items.values():
            tweak = item.data(0, Qt.ItemDataRole.UserRole)
            if tweak.risk == SAFE and not item.isHidden():
                item.setCheckState(0, Qt.CheckState.Checked)
        self.tree.blockSignals(False)
        self._update_buttons()

    def _show_description(self, current, _previous) -> None:
        tweak = current.data(0, Qt.ItemDataRole.UserRole) if current else None
        self.description.setText(tweak.description if tweak else "")

    def _apply_filter(self, *_args) -> None:
        needle = self.search.text().strip().lower()
        risk_choice = self.combo_risk.currentData()
        state_choice = self.combo_state.currentData()
        for key, item in self.items.items():
            tweak = item.data(0, Qt.ItemDataRole.UserRole)
            haystack = f"{tweak.name} {tweak.description} {' '.join(tweak.tags)}".lower()
            visible = not needle or needle in haystack
            if visible and risk_choice == "safe":
                visible = tweak.risk == SAFE
            elif visible and risk_choice == "moderate":
                visible = tweak.risk != RISKY
            if visible and state_choice != "any":
                visible = self.states.get(key) == state_choice
            item.setHidden(not visible)

        # fold away a whole section when nothing in it matches
        for risk, heading in self.groups.items():
            shown = sum(
                1 for i in range(heading.childCount()) if not heading.child(i).isHidden()
            )
            heading.setHidden(shown == 0)
            heading.setText(0, f"{GROUP_TITLE.get(risk, risk)}  ({shown})")
            if shown and needle:
                heading.setExpanded(True)

    def focus_search(self, text: str) -> None:
        """Entry point for the global search box."""
        self.search.setText(text)
        self.search.setFocus()

    # -- apply -----------------------------------------------------------
    def _preview(self) -> None:
        lines: list[str] = []
        for tweak, enable in self._pending():
            lines.append(f"{tweak.name} → {'on' if enable else 'off'}")
            lines += ["    " + line for line in self.ctx.engine.preview_tweak(tweak, enable)]
            lines.append("")
        _show_text(self, "Preview", "\n".join(lines) or "Nothing to do.")

    def _apply(self) -> None:
        pending = self._pending()
        if not pending:
            return
        risky = [t for t, _on in pending if t.risk == RISKY]
        if risky:
            answer = QMessageBox.question(
                self,
                "Advanced changes",
                f"{len(risky)} of these are advanced changes:\n\n"
                + "\n".join(f"  • {t.name}" for t in risky[:8])
                + "\n\nApply anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        self.btn_apply.setEnabled(False)
        self.progress.start("Applying…")
        worker = submit(
            self._do_apply,
            pending,
            self.backup_box.isChecked(),
            self.ctx.settings.bool("safety/restore_point"),
        )
        worker.signals.progress.connect(lambda d, t, m: self.progress.set(d, t, m or "Applying…"))
        worker.signals.message.connect(lambda m: self.log(m))
        worker.signals.result.connect(self._on_applied)
        worker.signals.error.connect(self._on_failed)

    def _do_apply(self, items, backup, restore_point, emit=None, progress=None):
        return self.ctx.engine.apply_tweaks(
            items, backup=backup, restore_point=restore_point, emit=emit, progress=progress
        )

    def _on_applied(self, report) -> None:
        self.progress.stop(report.summary())
        self.log(report.summary(), "ok" if report.ok else "error")
        self.status(report.summary())
        if report.ok:
            QMessageBox.information(self, "Applied", report.summary())
        else:
            detail = "\n".join(str(step) for step in report.failed[:10])
            QMessageBox.warning(self, "Finished with problems", f"{report.summary()}\n\n{detail}")
        self.refresh()


def _show_text(parent, title: str, text: str) -> None:
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    dialog.resize(680, 460)
    layout = QVBoxLayout(dialog)
    view = QPlainTextEdit(text)
    view.setReadOnly(True)
    layout.addWidget(view)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    buttons.rejected.connect(dialog.reject)
    buttons.accepted.connect(dialog.accept)
    layout.addWidget(buttons)
    dialog.exec()


def make_tweaks_page(category: str, key: str, title: str, subtitle: str):
    def factory(ctx: AppContext) -> TweaksPage:
        return TweaksPage(ctx, category=category, key=key, title=title, subtitle=subtitle)

    return factory
