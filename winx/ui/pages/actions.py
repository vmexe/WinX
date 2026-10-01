"""One-shot tasks: repairs, network fixes, security scans and tools."""

from __future__ import annotations

import os
import re

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QStyle,
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

from ...core.model import ActionDef, RISK_LABEL, RISKY, SAFE
from ...core import platform as pf
from ...core.workers import submit
from ...modules import actions_data
from .. import sysicons
from ..context import AppContext
from ..widgets import LogConsole, ProgressRow
from .base import Page


class ActionsPage(Page):
    """A list of tasks with live output."""

    def __init__(
        self,
        ctx: AppContext,
        group: str,
        key: str,
        title: str,
        subtitle: str,
        groups: list[str] | None = None,
        with_console: bool = True,
    ):
        self.key = key
        self.title = title
        self.subtitle = subtitle
        super().__init__(ctx)

        self.groups = groups or [group]
        self.actions: list[ActionDef] = [
            action for name in self.groups for action in actions_data.by_group(name)
        ]
        self._worker = None

        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search tasks…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._apply_filter)
        filters.addWidget(self.search, 1)

        filters.addWidget(QLabel("Risk:"))
        self.combo_risk = QComboBox()
        for label, value in [
            ("Any", "any"),
            ("Safe only", "safe"),
            ("Hide advanced", "nonrisky"),
        ]:
            self.combo_risk.addItem(label, value)
        self.combo_risk.currentIndexChanged.connect(self._apply_filter)
        filters.addWidget(self.combo_risk)

        if len(self.groups) > 1:
            filters.addWidget(QLabel("Group:"))
            self.combo_group = QComboBox()
            self.combo_group.addItem("All groups", "")
            for name in self.groups:
                self.combo_group.addItem(name.capitalize(), name)
            self.combo_group.currentIndexChanged.connect(self._apply_filter)
            filters.addWidget(self.combo_group)
        else:
            self.combo_group = None
        self.layout_.addLayout(filters)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(4)
        self.tree.setHeaderLabels(["Task", "Risk", "Needs", "About"])
        self.tree.setRootIsDecorated(True)
        self.tree.setIconSize(QSize(20, 20))
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        self.tree.header().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.tree.itemActivated.connect(lambda *_: self._run())
        self.tree.currentItemChanged.connect(self._selection_changed)
        self.layout_.addWidget(self.tree, 1)

        self._fill_tree()

        self.note = QLabel("")
        self.note.setWordWrap(True)
        self.layout_.addWidget(self.note)

        self.progress = ProgressRow(cancellable=True)
        self.progress.cancel_button.clicked.connect(self._cancel)
        self.layout_.addWidget(self.progress)

        self.console = None
        if with_console:
            self.console = LogConsole("Task output appears here.")
            self.layout_.addWidget(self.console, 1)

        buttons = QHBoxLayout()
        self.btn_run = QPushButton("Run task")
        self.btn_run.setDefault(True)
        self.btn_run.clicked.connect(self._run)
        buttons.addWidget(self.btn_run)
        self.btn_preview = QPushButton("Preview commands")
        self.btn_preview.clicked.connect(self._preview)
        buttons.addWidget(self.btn_preview)
        buttons.addStretch(1)
        if self.console is not None:
            self.btn_clear = QPushButton("Clear output")
            self.btn_clear.clicked.connect(self.console.clear)
            buttons.addWidget(self.btn_clear)
        self.layout_.addLayout(buttons)

        first = next(iter(self._rows()), None)
        if first is not None:
            self.tree.setCurrentItem(first[1])

    # -- tree -------------------------------------------------------------
    def _heading_for(self, action: ActionDef) -> str:
        """Tasks read better in short, labelled sections than as one long list."""
        if len(self.groups) > 1:
            return action.group.capitalize()
        return {SAFE: "Safe to run", RISKY: "Advanced — read first"}.get(
            action.risk, "Needs a little care"
        )

    RISK_ORDER = ["Safe to run", "Needs a little care", "Advanced — read first"]

    def _fill_tree(self) -> None:
        self.tree.clear()
        self._headings: dict[str, QTreeWidgetItem] = {}
        order = (
            [name.capitalize() for name in self.groups]
            if len(self.groups) > 1
            else self.RISK_ORDER
        )
        actions = sorted(
            self.actions,
            key=lambda a: order.index(self._heading_for(a))
            if self._heading_for(a) in order
            else len(order),
        )
        for action in actions:
            heading = self._heading_for(action)
            parent = self._headings.get(heading)
            if parent is None:
                parent = QTreeWidgetItem([heading, "", "", ""])
                font = parent.font(0)
                font.setBold(True)
                parent.setFont(0, font)
                parent.setFlags(Qt.ItemFlag.ItemIsEnabled)
                self.tree.addTopLevelItem(parent)
                self._headings[heading] = parent
            item = QTreeWidgetItem(
                [
                    action.name,
                    RISK_LABEL.get(action.risk, action.risk),
                    "Administrator" if action.admin else "",
                    action.description,
                ]
            )
            item.setIcon(0, _action_icon(action))
            item.setData(0, Qt.ItemDataRole.UserRole, action)
            item.setToolTip(3, action.description)
            parent.addChild(item)
        self.tree.expandAll()
        self.tree.resizeColumnToContents(0)
        self.tree.resizeColumnToContents(1)
        self.tree.resizeColumnToContents(2)

    def _rows(self):
        for i in range(self.tree.topLevelItemCount()):
            parent = self.tree.topLevelItem(i)
            for j in range(parent.childCount()):
                yield parent, parent.child(j)

    # -- helpers ---------------------------------------------------------
    def _current(self) -> ActionDef | None:
        item = self.tree.currentItem()
        return item.data(0, Qt.ItemDataRole.UserRole) if item else None

    def _selection_changed(self, current, _previous) -> None:
        action = current.data(0, Qt.ItemDataRole.UserRole) if current else None
        if action is None:
            self.note.setText("")
            return
        bits = [action.description]
        if action.note:
            bits.append(action.note)
        if action.eta:
            bits.append(f"Typically takes about {action.eta}s.")
        self.note.setText("  ".join(bits))

    def _apply_filter(self, *_args) -> None:
        needle = self.search.text().strip().lower()
        risk_choice = self.combo_risk.currentData()
        group_choice = self.combo_group.currentData() if self.combo_group else ""
        shown: dict[QTreeWidgetItem, int] = {}
        for parent, row in self._rows():
            action = row.data(0, Qt.ItemDataRole.UserRole)
            text = f"{row.text(0)} {row.text(3)}".lower()
            visible = not needle or needle in text
            if visible and risk_choice == "safe":
                visible = action.risk == SAFE
            elif visible and risk_choice == "nonrisky":
                visible = action.risk != RISKY
            if visible and group_choice:
                visible = action.group == group_choice
            row.setHidden(not visible)
            shown[parent] = shown.get(parent, 0) + (1 if visible else 0)
        for parent, count in shown.items():
            parent.setHidden(count == 0)
            if count:
                parent.setExpanded(True)

    def focus_search(self, text: str) -> None:
        """Entry point for the global search box."""
        self.search.setText(text)
        self.search.setFocus()

    # -- run -------------------------------------------------------------
    def _run(self) -> None:
        action = self._current()
        if action is None:
            return
        if action.admin and not self.ctx.is_admin and not self.ctx.simulating:
            answer = QMessageBox.question(
                self,
                "Administrator required",
                f"“{action.name}” needs administrator rights.\n\nRestart WinX as administrator now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if answer == QMessageBox.StandardButton.Yes:
                self.ctx.elevate()
            return
        if action.risk == RISKY:
            answer = QMessageBox.question(
                self,
                "Confirm task",
                f"“{action.name}” can change how Windows behaves.\n\n{action.description}\n\nRun it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        self._set_busy(True)
        self.progress.start(f"Running {action.name}…")
        if self.console is not None:
            self.console.append(f"{action.name}", "cmd")
        self._worker = submit(self._execute, action)
        self._worker.signals.progress.connect(lambda d, t, m: self.progress.set(d, t, m or action.name))
        self._worker.signals.message.connect(self._on_line)
        self._worker.signals.result.connect(self._on_finished)
        self._worker.signals.error.connect(self._on_failed)

    def _execute(self, action: ActionDef, emit=None, progress=None, cancel=None):
        return self.ctx.engine.run_action(action, emit=emit, progress=progress, cancel=cancel)

    def _on_line(self, text: str) -> None:
        if self.console is not None:
            self.console.append(text)
        else:
            self.log(text)

    def _on_finished(self, report) -> None:
        self._set_busy(False)
        self.progress.stop(report.summary())
        self.log(report.summary(), "ok" if report.ok else "error")
        self.status(report.summary())
        if not report.ok:
            detail = "\n".join(str(step) for step in report.failed[:10])
            QMessageBox.warning(self, "Finished with problems", f"{report.summary()}\n\n{detail}")

    def _on_failed(self, message: str) -> None:
        self._set_busy(False)
        self.progress.stop("Task failed")
        if self.console is not None:
            self.console.append(message, "error")
        self.on_error(message)

    def _cancel(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            self.progress.stop("Cancelled")
            self._set_busy(False)

    def _set_busy(self, busy: bool) -> None:
        self.btn_run.setEnabled(not busy)
        self.btn_preview.setEnabled(not busy)
        self.tree.setEnabled(not busy)

    def _preview(self) -> None:
        action = self._current()
        if action is None:
            return
        lines = [action.name, ""] + list(self.ctx.engine.preview_action(action))
        dialog = QDialog(self)
        dialog.setWindowTitle("Preview")
        dialog.resize(680, 420)
        layout = QVBoxLayout(dialog)
        view = QPlainTextEdit("\n".join(lines))
        view.setReadOnly(True)
        layout.addWidget(view)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        buttons.accepted.connect(dialog.accept)
        layout.addWidget(buttons)
        dialog.exec()


class ToolsPage(ActionsPage):
    """Shortcuts to the built-in Windows tools, plus maintenance tasks."""

    def __init__(self, ctx: AppContext):
        super().__init__(
            ctx,
            group="tools",
            key="tools",
            title="Tools",
            subtitle="Launch the built-in Windows consoles, and run routine maintenance.",
            groups=["tools", "maintenance"],
            with_console=True,
        )


def make_actions_page(group: str, key: str, title: str, subtitle: str, with_console: bool = True):
    def factory(ctx: AppContext) -> ActionsPage:
        return ActionsPage(
            ctx, group=group, key=key, title=title, subtitle=subtitle, with_console=with_console
        )

    return factory


_PROGRAM = re.compile(r"\b([A-Za-z0-9_.-]+\.(?:msc|cpl|exe))\b")


def _action_icon(action: ActionDef):
    """Windows' own icon for the console a task opens, or a neutral one."""
    if pf.IS_WINDOWS:
        text = " ".join(step.display() for step in action.steps if hasattr(step, "display"))
        match = _PROGRAM.search(f"{action.description} {text}")
        if match:
            candidate = os.path.join(pf.win_dir(), "System32", match.group(1))
            if os.path.exists(candidate):
                icon = sysicons.file_icon(candidate, 24)
                if not icon.isNull():
                    return icon
    return sysicons.standard_icon(QStyle.StandardPixmap.SP_CommandLink)
