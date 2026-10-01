"""Small shared widgets.

Deliberately thin: every widget here is a plain Qt class with no stylesheet,
no custom painting and no font of its own, so the app looks like whatever the
platform style says it should look like.
"""

from __future__ import annotations

import time

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QWidget,
)

from ..core.format import human_duration
from .sysicons import STATUS_PIXMAP, standard_icon, status_icon

#: re-exported so existing imports keep working; the icons themselves come
#: from the platform style (see :mod:`winx.ui.sysicons`)
__all__ = ["STATUS_PIXMAP", "standard_icon", "status_icon", "ProgressRow", "LogConsole"]


class ProgressRow(QWidget):
    """A progress bar with a caption and an optional Cancel button."""

    def __init__(self, parent=None, cancellable: bool = False):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(10)

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setTextVisible(True)        # the native bar draws its own %
        self.bar.setFormat("")
        layout.addWidget(self.bar, 1)

        self.label = QLabel("")
        self.label.setMinimumWidth(160)
        layout.addWidget(self.label)

        self._started = 0.0

        self._cancellable = cancellable
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setVisible(False)   # only while something is running
        self.cancel_button.setEnabled(False)
        layout.addWidget(self.cancel_button)

        self.setVisible(False)

    def start(self, message: str = "Working…") -> None:
        self.setVisible(True)
        self.bar.setVisible(True)
        self.bar.setRange(0, 0)          # busy indicator until the first update
        self.bar.setFormat("")
        self.label.setText(message)
        self.cancel_button.setVisible(self._cancellable)
        self.cancel_button.setEnabled(self._cancellable)
        self._started = time.monotonic()

    def set(self, done: int, total: int, message: str = "") -> None:
        """Update the bar. Shows a real percentage and an estimate when it can."""
        self.setVisible(True)
        self.bar.setVisible(True)
        if total > 0:
            self.bar.setRange(0, total)
            self.bar.setValue(min(done, total))
            self.bar.setFormat(f"%p%  ({min(done, total)} of {total})")
            remaining = self._eta(done, total)
            if remaining:
                self.bar.setFormat(f"%p%  ({min(done, total)} of {total}) · {remaining} left")
        if message:
            self.label.setText(message)

    def _eta(self, done: int, total: int) -> str:
        """A rough "time left", only once there is enough to extrapolate from."""
        if not self._started or done <= 0 or total <= 0 or done >= total:
            return ""
        elapsed = time.monotonic() - self._started
        if elapsed < 3:
            return ""
        remaining = elapsed / done * (total - done)
        if remaining < 2:
            return ""
        return human_duration(remaining)

    def stop(self, message: str = "") -> None:
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setFormat("")
        self._started = 0.0
        self.bar.setVisible(False)
        self.label.setText(message)
        self.cancel_button.setEnabled(False)
        self.cancel_button.setVisible(False)
        self.setVisible(bool(message))


class LogConsole(QPlainTextEdit):
    """Read-only output view used by the long-running pages."""

    def __init__(self, placeholder: str = "", parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setPlaceholderText(placeholder)
        self.setMaximumBlockCount(5000)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.DefaultContextMenu)
        self._extra_actions = [self._action("Save output…", self.save_to_file),
                               self._action("Clear output", self.clear)]

    def _action(self, text: str, slot) -> QAction:
        action = QAction(text, self)
        action.triggered.connect(slot)
        return action

    def contextMenuEvent(self, event) -> None:  # noqa: N802 - Qt naming
        """The standard menu, plus Save and Clear."""
        menu = self.createStandardContextMenu()
        menu.addSeparator()
        for action in self._extra_actions:
            menu.addAction(action)
        menu.exec(event.globalPos())

    def save_to_file(self) -> None:
        path, _filter = QFileDialog.getSaveFileName(
            self, "Save output", "winx-output.txt", "Text files (*.txt);;All files (*)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(self.toPlainText())
        except OSError as exc:
            QMessageBox.warning(self, "Save output", f"Could not write the file:\n\n{exc}")

    def append(self, text: str, level: str = "info") -> None:
        """Add lines without stealing a selection or the scroll position.

        Output arrives while the user may be reading or copying it; scrolling
        is only forced when the view was already parked at the bottom.
        """
        prefix = {"error": "! ", "warn": "! ", "cmd": "> ", "ok": "+ "}.get(level, "")
        scrollbar = self.verticalScrollBar()
        at_bottom = scrollbar.value() >= scrollbar.maximum() - 2
        had_selection = self.textCursor().hasSelection()

        cursor = self.textCursor()
        saved = (cursor.selectionStart(), cursor.selectionEnd())
        for line in str(text).splitlines() or [""]:
            self.appendPlainText(prefix + line)

        if had_selection:
            restored = self.textCursor()
            restored.setPosition(saved[0])
            restored.setPosition(saved[1], restored.MoveMode.KeepAnchor)
            self.setTextCursor(restored)
        if at_bottom:
            scrollbar.setValue(scrollbar.maximum())
        else:                                   # leave the user where they were
            scrollbar.setValue(scrollbar.value())
