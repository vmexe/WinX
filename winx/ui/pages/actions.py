"""One-shot tasks: repairs, network fixes, security scans and tools."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
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

from ...core.model import ActionDef, RISK_LABEL, RISKY, SAFE
from ...core.workers import submit
from ...modules import actions_data
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
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        self.tree.header().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.tree.itemActivated.connect(lambda *_: self._run())
        self.tree.currentItemChanged.connect(self._selection_changed)
        self.layout_.addWidget(self.tree, 1)

        for action in self.actions:
            item = QTreeWidgetItem(
                [
                    action.name,
                    RISK_LABEL.get(action.risk, action.risk),
                    "Administrator" if action.admin else "",
                    action.description,
                ]
            )
            item.setData(0, Qt.ItemDataRole.UserRole, action)
            item.setToolTip(3, action.description)
            self.tree.addTopLevelItem(item)
        self.tree.resizeColumnToContents(0)
        self.tree.resizeColumnToContents(1)

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

        if self.tree.topLevelItemCount():
            self.tree.setCurrentItem(self.tree.topLevelItem(0))

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
        for i in range(self.tree.topLevelItemCount()):
            row = self.tree.topLevelItem(i)
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
