"""Generic page that renders a category of tweaks as switchable cards."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...core.engine import OFF, ON, PARTIAL, UNKNOWN, Engine
from ...core.model import RISK_COLOR, RISK_LABEL, SAFE, TweakDef
from ...core.workers import submit
from ...modules import tweaks_data
from ..context import AppContext
from ..icons import icon
from ..widgets import Card, EmptyState, ProgressRow, SearchField, ToggleSwitch
from .base import Page, PendingBar


class TweakCard(Card):
    """One tweak, one switch (or Apply/Restore for command-only tweaks)."""

    toggled = Signal(object, bool)

    def __init__(self, tweak: TweakDef, accent: str = "#4cc2ff", parent=None):
        self.tweak = tweak
        control = QWidget(parent)
        cl = QHBoxLayout(control)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(8)

        if tweak.is_checkable:
            self.switch = ToggleSwitch(control)
            self.switch.clicked.connect(lambda checked: self.toggled.emit(self.tweak, checked))
            cl.addWidget(self.switch)
            self.apply_btn = None
        else:
            self.switch = None
            self.apply_btn = QPushButton("Apply", control)
            self.apply_btn.setFixedWidth(84)
            self.apply_btn.clicked.connect(lambda: self.toggled.emit(self.tweak, True))
            self.restore_btn = QPushButton("Restore", control)
            self.restore_btn.setFixedWidth(84)
            self.restore_btn.clicked.connect(lambda: self.toggled.emit(self.tweak, False))
            cl.addWidget(self.apply_btn)
            cl.addWidget(self.restore_btn)

        super().__init__(
            title=tweak.name,
            description=tweak.description,
            control=control,
            icon=_tweak_icon(tweak),
            parent=parent,
            accent=accent,
        )
        if tweak.admin:
            self.add_badge("Admin", "#f5c451")
        if tweak.risk != SAFE:
            self.add_badge(RISK_LABEL[tweak.risk], RISK_COLOR[tweak.risk])
        if tweak.restart == "pc":
            self.add_badge("Needs reboot", "#8b98a9")
        elif tweak.restart == "explorer":
            self.add_badge("Restarts Explorer", "#8b98a9")

    # -- state -----------------------------------------------------------
    def set_state(self, state: str) -> None:
        if self.switch is None:
            return
        if state == ON:
            self.switch.blockSignals(True)
            self.switch.setChecked(True)
            self.switch.blockSignals(False)
            self.switch.set_offset(1.0)
            self.switch.setPartial(False)
        elif state == PARTIAL:
            self.switch.blockSignals(True)
            self.switch.setChecked(False)
            self.switch.blockSignals(False)
            self.switch.set_offset(0.5)
            self.switch.setPartial(True)
        else:
            self.switch.blockSignals(True)
            self.switch.setChecked(False)
            self.switch.blockSignals(False)
            self.switch.set_offset(0.0)
            self.switch.setPartial(False)
        self.switch.update()

    def set_pending(self, pending: bool, desired: bool) -> None:
        self.set_selected(pending)
        if self.switch is not None and pending:
            self.switch.blockSignals(True)
            self.switch.setChecked(desired)
            self.switch.blockSignals(False)
            self.switch.set_offset(1.0 if desired else 0.0)
            self.switch.setPartial(False)
            self.switch.update()

    def matches(self, needle: str) -> bool:
        if not needle:
            return True
        blob = f"{self.tweak.name} {self.tweak.description} {self.tweak.key}".lower()
        return needle in blob


def _tweak_icon(tweak: TweakDef) -> str:
    if tweak.category == "privacy":
        return "eye"
    if tweak.category == "security":
        return "security"
    if tweak.category == "network":
        return "globe"
    if tweak.category == "interface":
        return "sliders"
    if tweak.category == "gaming":
        return "gamepad"
    if "power" in tweak.tags:
        return "performance"
    return "bolt"


class TweaksPage(Page):
    """Renders ``tweaks_data.by_category(category)`` with pending-apply UX."""

    def __init__(
        self,
        ctx: AppContext,
        category: str,
        key: str,
        title: str,
        subtitle: str,
        icon_name: str,
    ):
        self.category = category
        self.key = key
        self.title = title
        self.subtitle = subtitle
        self.icon_name = icon_name
        super().__init__(ctx)

        self.tweaks = tweaks_data.by_category(category)
        self.cards: dict[str, TweakCard] = {}
        self.states: dict[str, str] = {}
        self.pending: dict[str, bool] = {}
        self._busy = False

        self._build()

    # -- ui --------------------------------------------------------------
    def _build(self) -> None:
        layout = self.content_layout

        header = QHBoxLayout()
        self.heading = QLabel(self.title)
        from PySide6.QtGui import QFont

        font = QFont()
        font.setPointSize(18)
        font.setWeight(QFont.Weight.Bold)
        self.heading.setFont(font)
        header.addWidget(self.heading)
        header.addStretch(1)
        self.btn_reload = QPushButton(" Refresh")
        self.btn_reload.setIcon(icon("refresh", self.ctx.accent, 16))
        self.btn_reload.clicked.connect(self.refresh)
        self.btn_reload.setToolTip("Re-read the current state from Windows")
        header.addWidget(self.btn_reload)
        layout.addLayout(header)

        sub = QLabel(self.subtitle)
        sub.setWordWrap(True)
        sub.setProperty("muted", True)
        layout.addWidget(sub)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.search = SearchField(f"Search {self.title.lower()}…")
        self.search.textChanged.connect(self._apply_filter)
        toolbar.addWidget(self.search)

        self.filter = QComboBox()
        self.filter.addItems(["All", "Not applied", "Applied", "Pending"])
        self.filter.currentTextChanged.connect(self._apply_filter)
        toolbar.addWidget(self.filter)

        self.chk_hide_risky = QCheckBox("Hide advanced")
        self.chk_hide_risky.setChecked(not self.ctx.settings.bool("safety/show_risky"))
        self.chk_hide_risky.stateChanged.connect(self._apply_filter)
        toolbar.addWidget(self.chk_hide_risky)

        toolbar.addStretch(1)
        self.btn_select_safe = QPushButton("Select all safe")
        self.btn_select_safe.clicked.connect(self._select_safe)
        toolbar.addWidget(self.btn_select_safe)
        layout.addLayout(toolbar)

        self.list_widget = QWidget()
        self.list_layout = QVBoxLayout(self.list_widget)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(8)
        layout.addWidget(self.list_widget, 1)

        self.empty = EmptyState("No matching settings", "Try a different search term.")
        self.empty.hide()
        layout.addWidget(self.empty)

        self.progress = ProgressRow()
        layout.addWidget(self.progress)

        self.pending_bar = PendingBar(default_backup=self.ctx.settings.bool("safety/backup_enabled"))
        self.pending_bar.applyClicked.connect(self._apply_pending)
        self.pending_bar.previewClicked.connect(self._preview_pending)
        self.pending_bar.resetClicked.connect(self._reset_pending)
        layout.addWidget(self.pending_bar)

        for tweak in self.tweaks:
            card = TweakCard(tweak, self.ctx.accent, self)
            card.toggled.connect(self._on_toggled)
            self.cards[tweak.key] = card
            self.list_layout.addWidget(card)
        self.list_layout.addStretch(1)

    # -- data ------------------------------------------------------------
    def refresh(self) -> None:
        self.progress.start("Reading current state…")
        worker = submit(self._load_states)
        worker.signals.result.connect(self._on_states)
        worker.signals.error.connect(self._on_error)

    def _load_states(self):
        engine = Engine()
        return engine.states(self.tweaks)

    def _on_states(self, states: dict) -> None:
        self.states = states
        for key, card in self.cards.items():
            card.set_state(states.get(key, UNKNOWN))
        self.progress.stop(f"{len(states)} settings checked")
        self._apply_filter()
        self.status(f"{self.title}: state refreshed")

    def _on_error(self, message: str) -> None:
        self.progress.stop("failed")
        self.log(message, "error")

    # -- pending ---------------------------------------------------------
    def _on_toggled(self, tweak: TweakDef, checked: bool) -> None:
        if self._busy:
            return
        current = self.states.get(tweak.key, OFF)
        already_on = current == ON
        if not tweak.is_checkable:
            self._run_single(tweak, checked)
            return
        if checked == already_on:
            self.pending.pop(tweak.key, None)
        else:
            self.pending[tweak.key] = checked
        self._update_pending_ui()

    def _update_pending_ui(self) -> None:
        for key, card in self.cards.items():
            if key in self.pending:
                card.set_pending(True, self.pending[key])
            else:
                card.set_pending(False, False)
                if key in self.states:
                    card.set_state(self.states[key])
        self.pending_bar.set_count(len(self.pending))

    def _reset_pending(self) -> None:
        self.pending.clear()
        self._update_pending_ui()

    def _select_safe(self) -> None:
        for tweak in self.tweaks:
            if not tweak.is_checkable or tweak.risk != SAFE:
                continue
            if tweak.admin and not self.ctx.is_admin and self.ctx.simulating is False:
                continue
            if self.states.get(tweak.key, OFF) != ON:
                self.pending[tweak.key] = True
        self._update_pending_ui()

    def _preview_pending(self) -> None:
        items = [(tweaks_data.by_key(k), v) for k, v in self.pending.items()]
        lines: list[str] = []
        for tweak, enable in items:
            if tweak is None:
                continue
            lines.append(f"# {tweak.name}  ({'ON' if enable else 'OFF'})")
            lines += ["   " + line for line in self.ctx.engine.preview_tweak(tweak, enable)]
            lines.append("")
        _show_preview(self, f"Preview — {len(items)} change(s)", "\n".join(lines) or "Nothing to do")

    def _apply_pending(self, backup: bool) -> None:
        if not self.pending:
            return
        items = [(tweaks_data.by_key(k), v) for k, v in self.pending.items()]
        items = [(t, v) for t, v in items if t is not None]
        if not items:
            return

        risky = [t.name for t, v in items if t.risk != SAFE]
        if risky and self.ctx.settings.bool("safety/confirm_each") is False:
            answer = QMessageBox.question(
                self,
                "Confirm advanced changes",
                "These changes can alter how Windows behaves:\n\n • "
                + "\n • ".join(risky[:12])
                + ("\n …" if len(risky) > 12 else "")
                + "\n\nThey are still reversible — continue?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        self._busy = True
        self.progress.start(f"Applying {len(items)} change(s)…")
        restore_point = self.ctx.settings.bool("safety/restore_point")
        worker = submit(
            self._do_apply, items, backup, restore_point
        )
        worker.signals.message.connect(lambda m: self.log(m, "info"))
        worker.signals.progress.connect(lambda d, t: self.progress.set(d, t))
        worker.signals.result.connect(self._on_applied)
        worker.signals.error.connect(self._on_error)

    def _do_apply(self, items, backup, restore_point, emit=None, progress=None):
        return self.ctx.engine.apply_tweaks(
            items, backup=backup, restore_point=restore_point, emit=emit, progress=progress
        )

    def _on_applied(self, report) -> None:
        self._busy = False
        self.progress.stop("done")
        self.log(report.summary(), "ok" if report.ok else "warn")
        for step in report.steps:
            if not step.ok:
                self.log(str(step), "error")
        self.pending.clear()
        self._update_pending_ui()
        self.refresh()
        self.status(report.summary())
        if report.ok:
            QMessageBox.information(self, "Applied", report.summary())
        else:
            QMessageBox.warning(self, "Finished with problems", report.summary())

    def _run_single(self, tweak: TweakDef, enable: bool) -> None:
        self._busy = True
        self.progress.start(f"{'Applying' if enable else 'Restoring'}: {tweak.name}")
        worker = submit(
            self.ctx.engine.apply_tweaks,
            [(tweak, enable)],
            self.ctx.settings.bool("safety/backup_enabled"),
            False,
        )
        worker.signals.message.connect(lambda m: self.log(m, "info"))
        worker.signals.result.connect(self._on_applied)
        worker.signals.error.connect(self._on_error)

    # -- filtering -------------------------------------------------------
    def _apply_filter(self, *_args) -> None:
        needle = self.search.text().strip().lower()
        mode = self.filter.currentText()
        hide_risky = self.chk_hide_risky.isChecked()
        visible = 0
        for tweak in self.tweaks:
            card = self.cards[tweak.key]
            show = card.matches(needle)
            if show and hide_risky and tweak.risk != SAFE:
                show = False
            if show and mode == "Not applied":
                show = self.states.get(tweak.key, OFF) != ON and tweak.key not in self.pending
            elif show and mode == "Applied":
                show = self.states.get(tweak.key, OFF) == ON
            elif show and mode == "Pending":
                show = tweak.key in self.pending
            card.setVisible(show)
            visible += 1 if show else 0
        self.empty.setVisible(visible == 0)


def _show_preview(parent, title: str, text: str) -> None:
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    dialog.resize(720, 460)
    layout = QVBoxLayout(dialog)
    view = QPlainTextEdit()
    view.setReadOnly(True)
    view.setPlainText(text)
    from PySide6.QtGui import QFont

    font = QFont("Consolas", 10)
    view.setFont(font)
    layout.addWidget(view, 1)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    buttons.rejected.connect(dialog.reject)
    buttons.accepted.connect(dialog.accept)
    layout.addWidget(buttons)
    dialog.exec()


def make_tweaks_page(category: str, key: str, title: str, subtitle: str, icon_name: str):
    def factory(ctx: AppContext) -> TweaksPage:
        return TweaksPage(ctx, category, key, title, subtitle, icon_name)

    return factory
