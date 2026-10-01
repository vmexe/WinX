"""Reusable widgets: switches, cards, badges, log console, progress rows."""

from __future__ import annotations

from typing import Iterable

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
)
from PySide6.QtGui import QColor, QFont, QPainter, QTextCursor
from PySide6.QtWidgets import (
    QAbstractButton,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .theme import Palette


# --------------------------------------------------------------------------
# switch
# --------------------------------------------------------------------------
class ToggleSwitch(QAbstractButton):
    """An animated on/off switch with an optional 'partially applied' look."""

    def __init__(self, parent=None, checked: bool = False):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self._offset = 1.0 if checked else 0.0
        self._partial = False
        self._anim = QPropertyAnimation(self, b"offset", self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.toggled.connect(lambda _c: self._animate())

    # -- geometry --------------------------------------------------------
    def sizeHint(self) -> QSize:
        return QSize(46, 26)

    def minimumSizeHint(self) -> QSize:
        return QSize(46, 26)

    # -- state -----------------------------------------------------------
    def isPartial(self) -> bool:
        return self._partial

    def setPartial(self, value: bool) -> None:
        self._partial = bool(value)
        self.update()

    # -- animation -------------------------------------------------------
    def get_offset(self) -> float:
        return self._offset

    def set_offset(self, value: float) -> None:
        self._offset = float(value)
        self.update()

    offset = Property(float, get_offset, set_offset)

    def _animate(self) -> None:
        target = 1.0 if self.isChecked() else 0.0
        if self._partial:
            target = 0.5
        self._anim.stop()
        self._anim.setStartValue(self._offset)
        self._anim.setEndValue(target)
        self._anim.start()

    # -- painting --------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        palette = self._palette()
        w, h = self.width(), self.height()
        margin = 3
        radius = h / 2.0

        on = self.isChecked() or self._partial
        track_color = QColor(palette.accent if self.isChecked() else (palette.warning if self._partial else palette.border))
        if self._partial:
            track_color = QColor(palette.warning)
        if not on:
            track_color = QColor(palette.border)
        if not self.isEnabled():
            track_color = QColor(palette.border)
            track_color.setAlpha(120)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(track_color)
        painter.drawRoundedRect(QRectF(0, 0, w, h), radius, radius)

        knob_d = h - 2 * margin
        travel = w - 2 * margin - knob_d
        x = margin + travel * self._offset
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(QRectF(x, margin, knob_d, knob_d))
        painter.end()

    def _palette(self) -> Palette:
        window = self.window()
        return getattr(window, "palette_colors", None) or _FALLBACK

    def setCheckedSilent(self, value: bool) -> None:
        self.blockSignals(True)
        self.setChecked(value)
        self.blockSignals(False)
        self._offset = 1.0 if value else 0.0
        self.update()


from .theme import DARK as _FALLBACK  # noqa: E402  (used above at runtime)


# --------------------------------------------------------------------------
# structural widgets
# --------------------------------------------------------------------------
class Card(QFrame):
    """A titled row with a control on the right (switch, button, value…)."""

    def __init__(
        self,
        title: str,
        description: str = "",
        control: QWidget | None = None,
        icon: str | None = None,
        parent=None,
        accent: str | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("Card")
        self._selected = False
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(14)

        if icon:
            from .icons import icon as make_icon

            lbl = QLabel()
            lbl.setPixmap(make_icon(icon, accent or "#4cc2ff", 22).pixmap(22, 22))
            lbl.setFixedWidth(26)
            layout.addWidget(lbl, 0, Qt.AlignmentFlag.AlignTop)

        text = QVBoxLayout()
        text.setSpacing(3)
        self.title_label = QLabel(title)
        self.title_label.setWordWrap(True)
        font = QFont()
        font.setPointSize(10)
        font.setWeight(QFont.Weight.DemiBold)
        self.title_label.setFont(font)
        text.addWidget(self.title_label)
        self.description_label = QLabel(description)
        self.description_label.setWordWrap(True)
        self.description_label.setProperty("muted", True)
        self.description_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        text.addWidget(self.description_label)
        self.badges = QHBoxLayout()
        self.badges.setSpacing(6)
        text.addLayout(self.badges)
        layout.addLayout(text, 1)

        if control is not None:
            layout.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)
            self.control = control

    def add_badge(self, text: str, color: str | None = None) -> None:
        self.badges.addWidget(Badge(text, color))

    def set_selected(self, value: bool) -> None:
        self._selected = value
        self.setProperty("selected", "true" if value else "false")
        self.style().polish(self)


class Badge(QLabel):
    """A small coloured pill."""

    def __init__(self, text: str, color: str | None = None, parent=None):
        super().__init__(text, parent)
        color = color or "#8b98a9"
        self.setStyleSheet(
            f"color: {color}; border: 1px solid {color}55; background: {color}18;"
            f" border-radius: 8px; padding: 1px 7px; font-size: 11px;"
        )
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)


class StatCard(QFrame):
    """Dashboard metric tile."""

    def __init__(self, label: str, value: str = "—", sub: str = "", icon: str | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setMinimumHeight(96)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(2)

        top = QHBoxLayout()
        self.label = QLabel(label.upper())
        self.label.setProperty("muted", True)
        font = QFont()
        font.setPointSize(8)
        font.setWeight(QFont.Weight.Bold)
        self.label.setFont(font)
        top.addWidget(self.label)
        top.addStretch(1)
        if icon:
            from .icons import icon as make_icon

            ic = QLabel()
            ic.setPixmap(make_icon(icon, "#4cc2ff", 18).pixmap(18, 18))
            top.addWidget(ic)
        layout.addLayout(top)

        self.value_label = QLabel(value)
        vfont = QFont()
        vfont.setPointSize(17)
        vfont.setWeight(QFont.Weight.DemiBold)
        self.value_label.setFont(vfont)
        layout.addWidget(self.value_label)

        self.sub_label = QLabel(sub)
        self.sub_label.setProperty("muted", True)
        layout.addWidget(self.sub_label)
        layout.addStretch(1)

        self.bar = QProgressBar()
        self.bar.setFixedHeight(6)
        self.bar.setTextVisible(False)
        self.bar.hide()
        layout.addWidget(self.bar)

    def set_value(self, value: str, sub: str = "", percent: int | None = None) -> None:
        self.value_label.setText(value)
        if sub:
            self.sub_label.setText(sub)
        if percent is None:
            self.bar.hide()
        else:
            self.bar.show()
            self.bar.setValue(max(0, min(100, int(percent))))


class SectionTitle(QLabel):
    def __init__(self, text: str, sub: str = "", parent=None):
        super().__init__(text, parent)
        font = QFont()
        font.setPointSize(13)
        font.setWeight(QFont.Weight.DemiBold)
        self.setFont(font)
        self.setContentsMargins(0, 6, 0, 2)
        self._sub = sub


class PageHeader(QWidget):
    """Title + subtitle + optional action buttons."""

    def __init__(self, title: str, subtitle: str = "", actions: Iterable[QWidget] = (), parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 10)
        left = QVBoxLayout()
        left.setSpacing(2)
        self.title = QLabel(title)
        font = QFont()
        font.setPointSize(18)
        font.setWeight(QFont.Weight.Bold)
        self.title.setFont(font)
        left.addWidget(self.title)
        if subtitle:
            self.subtitle = QLabel(subtitle)
            self.subtitle.setProperty("muted", True)
            self.subtitle.setWordWrap(True)
            left.addWidget(self.subtitle)
        layout.addLayout(left, 1)
        for action in actions:
            layout.addWidget(action, 0, Qt.AlignmentFlag.AlignTop)


class LogConsole(QFrame):
    """Monospaced output console with level colours and a small toolbar."""

    LEVEL_COLORS = {
        "info": None,
        "ok": "#3ecf8e",
        "warn": "#f5c451",
        "error": "#ff6b6b",
        "cmd": "#4cc2ff",
        "muted": "#8b98a9",
    }

    def __init__(self, parent=None, placeholder: str = "Output appears here…"):
        super().__init__(parent)
        self.setObjectName("Panel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        bar = QHBoxLayout()
        self.title = QLabel("Activity log")
        self.title.setProperty("muted", True)
        bar.addWidget(self.title)
        bar.addStretch(1)
        self.btn_clear = QPushButton("Clear")
        self.btn_clear.setProperty("flat", True)
        self.btn_clear.clicked.connect(self.clear)
        self.btn_save = QPushButton("Save…")
        self.btn_save.setProperty("flat", True)
        self.btn_save.clicked.connect(self.save_to_file)
        bar.addWidget(self.btn_clear)
        bar.addWidget(self.btn_save)
        layout.addLayout(bar)

        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setPlaceholderText(placeholder)
        self.view.setMaximumBlockCount(5000)
        font = QFont("Cascadia Mono", 9)
        font.setStyleHint(QFont.StyleHint.Monospace)
        if not font.exactMatch():
            font = QFont("Consolas", 9)
        self.view.setFont(font)
        layout.addWidget(self.view, 1)

    def append(self, text: str, level: str = "info") -> None:
        color = self.LEVEL_COLORS.get(level)
        line = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        html = f'<span style="color:{color}">{line}</span>' if color else f"<span>{line}</span>"
        self.view.appendHtml(html)
        self.view.moveCursor(QTextCursor.MoveOperation.End)

    def clear(self) -> None:
        self.view.clear()

    def save_to_file(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save log", "winx-log.txt", "Text files (*.txt *.log)")
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self.view.toPlainText())


class ProgressRow(QWidget):
    """Label + bar + status line that can be shown/hidden as a unit."""

    def __init__(self, parent=None, label: str = ""):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.label = QLabel(label)
        self.label.setProperty("muted", True)
        layout.addWidget(self.label)
        self.bar = QProgressBar()
        self.bar.setFixedHeight(8)
        self.bar.setTextVisible(False)
        layout.addWidget(self.bar)
        self.hide()

    def set(self, done: int, total: int, text: str = "") -> None:
        if text:
            self.label.setText(text)
        if total > 0:
            self.bar.setMaximum(total)
            self.bar.setValue(min(done, total))
        else:
            self.bar.setMaximum(0)
            self.bar.setValue(0)

    def start(self, text: str = "") -> None:
        if text:
            self.label.setText(text)
        self.bar.setValue(0)
        self.show()

    def stop(self, text: str = "") -> None:
        if text:
            self.label.setText(text)
        self.hide()


class SearchField(QLineEdit):
    def __init__(self, placeholder: str = "Search…", parent=None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setClearButtonEnabled(True)
        self.setMinimumWidth(220)


class EmptyState(QFrame):
    def __init__(self, text: str, hint: str = "", parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(6)
        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = QFont()
        font.setPointSize(11)
        font.setWeight(QFont.Weight.DemiBold)
        lbl.setFont(font)
        layout.addWidget(lbl)
        if hint:
            sub = QLabel(hint)
            sub.setProperty("muted", True)
            sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
            sub.setWordWrap(True)
            layout.addWidget(sub)
        self.setMinimumHeight(120)


def hline() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setObjectName("Separator")
    line.setFixedHeight(1)
    return line


def scrollable(widget: QWidget):
    from PySide6.QtWidgets import QScrollArea

    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    area.setWidget(widget)
    return area
