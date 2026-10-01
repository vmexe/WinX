"""Small shared widgets.

Deliberately thin: every widget here is a plain Qt class with no stylesheet,
no custom painting and no font of its own, so the app looks like whatever the
platform style says it should look like.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QStyle,
    QWidget,
)

#: status name -> standard pixmap, so rows use the platform's own icons
STATUS_PIXMAP = {
    "ok": QStyle.StandardPixmap.SP_DialogApplyButton,
    "info": QStyle.StandardPixmap.SP_MessageBoxInformation,
    "warn": QStyle.StandardPixmap.SP_MessageBoxWarning,
    "fail": QStyle.StandardPixmap.SP_MessageBoxCritical,
}


def standard_icon(pixmap: QStyle.StandardPixmap):
    """An icon from the current platform style."""
    app = QApplication.instance()
    style = app.style() if app else None
    return style.standardIcon(pixmap) if style else None


def status_icon(status: str):
    return standard_icon(STATUS_PIXMAP.get(status, QStyle.StandardPixmap.SP_MessageBoxInformation))


class ProgressRow(QWidget):
    """A progress bar with a caption and an optional Cancel button."""

    def __init__(self, parent=None, cancellable: bool = False):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setTextVisible(False)
        layout.addWidget(self.bar, 1)

        self.label = QLabel("")
        layout.addWidget(self.label)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setVisible(cancellable)
        self.cancel_button.setEnabled(False)
        layout.addWidget(self.cancel_button)

        self.setVisible(False)

    def start(self, message: str = "Working…") -> None:
        self.setVisible(True)
        self.bar.setVisible(True)
        self.bar.setRange(0, 0)          # busy indicator until the first update
        self.label.setText(message)
        self.cancel_button.setEnabled(True)

    def set(self, done: int, total: int, message: str = "") -> None:
        self.setVisible(True)
        self.bar.setVisible(True)
        if total > 0:
            self.bar.setRange(0, total)
            self.bar.setValue(min(done, total))
        if message:
            self.label.setText(message)

    def stop(self, message: str = "") -> None:
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setVisible(False)
        self.label.setText(message)
        self.cancel_button.setEnabled(False)
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

    def append(self, text: str, level: str = "info") -> None:
        prefix = {"error": "! ", "warn": "! ", "cmd": "> ", "ok": "+ "}.get(level, "")
        for line in str(text).splitlines() or [""]:
            self.appendPlainText(prefix + line)
        self.ensureCursorVisible()
