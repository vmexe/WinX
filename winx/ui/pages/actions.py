"""Pages that run one-shot tasks (repair, network fixes, scans, tools)."""

from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...core.model import ActionDef
from ...core.workers import submit
from ...modules import actions_data
from ..context import AppContext
from ..icons import icon
from ..widgets import EmptyState, LogConsole, ProgressRow, SearchField
from .base import ActionCard, Page


class ActionsPage(Page):
    """A list of runnable tasks with live output."""

    def __init__(
        self,
        ctx: AppContext,
        group: str,
        key: str,
        title: str,
        subtitle: str,
        icon_name: str,
        with_console: bool = True,
    ):
        self.group = group
        self.key = key
        self.title = title
        self.subtitle = subtitle
        self.icon_name = icon_name
        self.with_console = with_console
        super().__init__(ctx)

        self.actions = actions_data.by_group(group)
        self.cards: dict[str, ActionCard] = {}
        self._worker = None
        self._current: ActionDef | None = None
        self._build()

    # -- ui --------------------------------------------------------------
    def _build(self) -> None:
        layout = self.content_layout

        header = QHBoxLayout()
        heading = QLabel(self.title)
        font = QFont()
        font.setPointSize(18)
        font.setWeight(QFont.Weight.Bold)
        heading.setFont(font)
        header.addWidget(heading)
        header.addStretch(1)
        layout.addLayout(header)

        sub = QLabel(self.subtitle)
        sub.setWordWrap(True)
        sub.setProperty("muted", True)
        layout.addWidget(sub)

        if self.group in ("repair", "network", "security"):
            warn = QLabel(
                "These tasks change system configuration. WinX streams exactly what it runs "
                "into the log below — nothing is hidden."
            )
            warn.setWordWrap(True)
            warn.setProperty("muted", True)
            layout.addWidget(warn)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.search = SearchField("Search tasks…")
        self.search.textChanged.connect(self._apply_filter)
        toolbar.addWidget(self.search)
        toolbar.addStretch(1)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setProperty("danger", True)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel)
        toolbar.addWidget(self.cancel_btn)
        layout.addLayout(toolbar)

        self.list_widget = QWidget()
        self.list_layout = QVBoxLayout(self.list_widget)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(8)
        layout.addWidget(self.list_widget, 1)

        self.empty = EmptyState("No matching tasks", "Try another search term.")
        self.empty.hide()
        layout.addWidget(self.empty)

        self.progress = ProgressRow()
        layout.addWidget(self.progress)

        if self.with_console:
            self.console = LogConsole(placeholder="Task output appears here…")
            self.console.setMinimumHeight(150)
            layout.addWidget(self.console, 0)
            self.console.setFixedHeight(190)

        for action in self.actions:
            card = ActionCard(action, self.ctx.accent, self)
            card.runRequested.connect(self._run)
            card.preview_btn.clicked.connect(lambda _c=False, a=action: self._preview(a))
            self.cards[action.key] = card
            self.list_layout.addWidget(card)
        self.list_layout.addStretch(1)

    # -- running ---------------------------------------------------------
    def _run(self, action: ActionDef) -> None:
        if self._worker is not None:
            self.status("Another task is still running")
            return
        if action.admin and not self.ctx.is_admin and not self.ctx.simulating:
            answer = QMessageBox.question(
                self,
                "Administrator rights needed",
                f"“{action.name}” needs administrator rights.\n\n"
                "WinX can relaunch itself elevated. Continue?",
            )
            if answer == QMessageBox.StandardButton.Yes:
                self.ctx.elevate()
            return

        if action.risk != "safe":
            answer = QMessageBox.question(
                self,
                "Confirm",
                f"{action.name}\n\n{action.note or action.description}",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        self._current = action
        self._set_busy(True)
        self.progress.start(f"Running {action.name}…")
        self.cancel_btn.setEnabled(True)
        self.log(f"=== {action.name} ===", "cmd")
        self._worker = submit(self._execute, action)
        self._worker.signals.message.connect(lambda m: self._log_line(m))
        self._worker.signals.progress.connect(lambda d, t: self.progress.set(d, t, f"{action.name}: step {d}/{t}"))
        self._worker.signals.result.connect(self._on_finished)
        self._worker.signals.error.connect(self._on_error)

    def _execute(self, action: ActionDef, emit=None, progress=None, is_cancelled=None):
        return self.ctx.engine.run_action(action, emit=emit, progress=progress, cancel=is_cancelled)

    def _on_finished(self, report) -> None:
        self._set_busy(False)
        self._worker = None
        self.progress.stop("done")
        self.log(report.summary(), "ok" if report.ok else "warn")
        for step in report.steps:
            if not step.ok:
                self.log(str(step), "error")
        self.status(report.summary())
        if self._current and self._current.restart == "pc":
            QMessageBox.information(
                self, "Restart required", f"{self._current.name} finished. Restart the PC to complete it."
            )

    def _on_error(self, message: str) -> None:
        self._set_busy(False)
        self._worker = None
        self.progress.stop("failed")
        self.log(message, "error")
        QMessageBox.critical(self, "Task failed", message.splitlines()[0] if message else "Unknown error")

    def _cancel(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            self.log("Cancelling…", "warn")
            self.cancel_btn.setEnabled(False)

    def _set_busy(self, busy: bool) -> None:
        current = self._current
        for key, card in self.cards.items():
            card.set_busy(busy, running=bool(current) and current.key == key)
        if not busy:
            self.cancel_btn.setEnabled(False)
            self._current = None

    def _preview(self, action: ActionDef) -> None:
        from .tweaks import _show_preview

        lines = [action.name, action.description, ""]
        lines += ["   " + line for line in self.ctx.engine.preview_action(action)]
        if action.note:
            lines += ["", "Note: " + action.note]
        _show_preview(self, f"Preview — {action.name}", "\n".join(lines))

    def _log_line(self, text: str) -> None:
        level = "info"
        low = text.lower()
        if low.startswith(">"):
            level = "cmd"
        elif "error" in low or "failed" in low or low.strip().startswith("!"):
            level = "error"
        elif "success" in low or "complete" in low or "ok" == low.strip():
            level = "ok"
        self.log(text, level)

    def _apply_filter(self, *_args) -> None:
        needle = self.search.text().strip().lower()
        visible = 0
        for action in self.actions:
            card = self.cards[action.key]
            show = (
                not needle
                or needle in action.name.lower()
                or needle in action.description.lower()
            )
            card.setVisible(show)
            visible += 1 if show else 0
        self.empty.setVisible(visible == 0)


class ToolsPage(Page):
    """Grid of shortcuts into the classic Windows applets."""

    key = "tools"
    title = "Tools"
    subtitle = "One click away from the Windows applets you actually need."
    icon_name = "tools"

    def __init__(self, ctx: AppContext):
        super().__init__(ctx)
        self.actions = actions_data.by_group("tools")
        self._worker = None

        layout = self.content_layout
        heading = QLabel("Tools")
        font = QFont()
        font.setPointSize(18)
        font.setWeight(QFont.Weight.Bold)
        heading.setFont(font)
        layout.addWidget(heading)
        sub = QLabel(self.subtitle)
        sub.setProperty("muted", True)
        layout.addWidget(sub)

        grid = QGridLayout()
        grid.setSpacing(10)
        columns = 4
        for index, action in enumerate(self.actions):
            button = QPushButton(action.name)
            button.setMinimumHeight(62)
            button.setIcon(icon(_icon_for_tool(action), self.ctx.accent, 22))
            button.setIconSize(QSize(22, 22))
            button.setToolTip(action.description)
            button.clicked.connect(lambda _c=False, a=action: self._launch(a))
            grid.addWidget(button, index // columns, index % columns)
        layout.addLayout(grid)

        self.console = LogConsole(placeholder="Launched tools appear here…")
        self.console.setFixedHeight(140)
        layout.addWidget(self.console)
        layout.addStretch(1)

    def _launch(self, action: ActionDef) -> None:
        self.log(f"Launching {action.name}…", "cmd")
        worker = submit(self._execute, action)
        worker.signals.message.connect(lambda m: self.console.append(m))
        worker.signals.result.connect(self._done)

    def _execute(self, action: ActionDef, emit=None, progress=None):
        return self.ctx.engine.run_action(action, emit=emit, progress=progress)

    def _done(self, report) -> None:
        for step in report.steps:
            level = "ok" if step.ok else "error"
            self.console.append(str(step), level)
        self.status(report.summary())


def _icon_for_tool(action: ActionDef) -> str:
    mapping = {
        "tool_services": "sliders",
        "tool_devmgmt": "chip",
        "tool_diskmgmt": "drive",
        "tool_msconfig": "gear",
        "tool_taskschd": "clock",
        "tool_eventvwr": "terminal",
        "tool_msinfo32": "monitor",
        "tool_resmon": "bolt",
        "tool_optionalfeatures": "grid",
        "tool_rstrui": "undo",
        "tool_dxdiag": "monitor",
        "tool_sysdm": "gear",
        "tool_appwiz": "box",
        "tool_firewall_cpl": "verified",
        "tool_ncpa": "globe",
        "tool_powercfg_cpl": "bolt",
    }
    return mapping.get(action.key, "toolbox")


def make_actions_page(group: str, key: str, title: str, subtitle: str, icon_name: str, with_console: bool = True):
    def factory(ctx: AppContext) -> ActionsPage:
        return ActionsPage(ctx, group, key, title, subtitle, icon_name, with_console)

    return factory
