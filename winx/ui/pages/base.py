"""Base class and shared building blocks for the content pages."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ...core.model import RISK_COLOR, RISK_LABEL, ActionDef
from ..context import AppContext
from ..icons import icon


class Page(QWidget):
    """Common plumbing: header, scroll area, lazy refresh, busy state."""

    key = "page"
    title = "Page"
    subtitle = ""
    icon_name = "dashboard"

    refreshed = Signal()

    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self._loaded = False
        self._dirty = True

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(26, 22, 26, 26)
        self.content_layout.setSpacing(10)

        # long pages (85 tweaks, hundreds of drivers) must scroll, not squash
        from PySide6.QtWidgets import QScrollArea

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setWidget(self.content)
        outer.addWidget(self.scroll_area, 1)

    # -- lifecycle -------------------------------------------------------
    def on_show(self) -> None:
        """Called by the main window each time the page becomes visible."""
        if self._dirty or not self._loaded:
            self._dirty = False
            self._loaded = True
            self.refresh()

    def invalidate(self) -> None:
        self._dirty = True

    def refresh(self) -> None:  # pragma: no cover - overridden
        pass

    def log(self, text: str, level: str = "info") -> None:
        self.ctx.log(f"[{self.title}] {text}" if level == "cmd" else text, level)

    def status(self, text: str) -> None:
        self.ctx.status(text)


class ActionCard(QFrame):
    """A one-shot task: title, description, badges and a Run button."""

    runRequested = Signal(object)

    def __init__(self, action: ActionDef, accent: str = "#4cc2ff", parent=None):
        super().__init__(parent)
        self.action = action
        self.setObjectName("Card")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(14)

        lbl = QLabel()
        lbl.setPixmap(icon(_icon_for(action), accent, 24).pixmap(24, 24))
        lbl.setFixedWidth(28)
        layout.addWidget(lbl, 0, Qt.AlignmentFlag.AlignTop)

        text = QVBoxLayout()
        text.setSpacing(4)
        self.title_label = QLabel(action.name)
        font = QFont()
        font.setPointSize(10)
        font.setWeight(QFont.Weight.DemiBold)
        self.title_label.setFont(font)
        text.addWidget(self.title_label)

        self.description_label = QLabel(action.description)
        self.description_label.setWordWrap(True)
        self.description_label.setProperty("muted", True)
        text.addWidget(self.description_label)

        badges = QHBoxLayout()
        badges.setSpacing(6)
        if action.admin:
            badges.addWidget(_badge("Administrator", "#f5c451"))
        if action.risk != "safe":
            badges.addWidget(_badge(RISK_LABEL[action.risk], RISK_COLOR[action.risk]))
        if action.eta:
            badges.addWidget(_badge(_eta_text(action.eta), "#8b98a9"))
        badges.addStretch(1)
        text.addLayout(badges)

        if action.note:
            note = QLabel(action.note)
            note.setWordWrap(True)
            note.setStyleSheet("color:#f5c451; font-size:11px;")
            text.addWidget(note)

        layout.addLayout(text, 1)

        right = QVBoxLayout()
        right.setSpacing(4)
        self.button = QPushButton("Run")
        self.button.setObjectName("runButton")
        self.button.setProperty("accent", True)
        self.button.setFixedWidth(110)
        self.button.clicked.connect(lambda: self.runRequested.emit(self.action))
        right.addWidget(self.button)
        self.preview_btn = QPushButton("Preview")
        self.preview_btn.setProperty("flat", True)
        self.preview_btn.setFixedWidth(110)
        right.addWidget(self.preview_btn)
        right.addStretch(1)
        layout.addLayout(right)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_busy(self, busy: bool, running: bool = False) -> None:
        self.button.setEnabled(not busy or running)
        self.preview_btn.setEnabled(not busy)


class PendingBar(QFrame):
    """Bottom bar that shows queued changes and applies them."""

    applyClicked = Signal(bool)   # backup enabled
    previewClicked = Signal()
    resetClicked = Signal()

    def __init__(self, parent=None, default_backup: bool = True):
        super().__init__(parent)
        self.setObjectName("Panel")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)

        self.label = QLabel("No pending changes")
        layout.addWidget(self.label)
        layout.addStretch(1)

        self.backup = QPushButton()
        self.backup.setCheckable(True)
        self.backup.setChecked(default_backup)
        self.backup.setText("Back up (undoable)")
        self.backup.setToolTip("Record the old values so these changes can be undone from History")
        layout.addWidget(self.backup)

        self.preview_btn = QPushButton("Preview")
        self.preview_btn.clicked.connect(self.previewClicked.emit)
        layout.addWidget(self.preview_btn)

        self.reset_btn = QPushButton("Reset")
        self.reset_btn.clicked.connect(self.resetClicked.emit)
        layout.addWidget(self.reset_btn)

        self.apply_btn = QPushButton("Apply")
        self.apply_btn.setProperty("accent", True)
        self.apply_btn.clicked.connect(lambda: self.applyClicked.emit(self.backup.isChecked()))
        layout.addWidget(self.apply_btn)

        self.setVisible(False)

    def set_count(self, count: int) -> None:
        if count <= 0:
            self.label.setText("No pending changes")
            self.apply_btn.setEnabled(False)
            self.reset_btn.setEnabled(False)
            self.preview_btn.setEnabled(False)
            self.setVisible(False)
        else:
            self.label.setText(f"{count} change{'s' if count != 1 else ''} ready to apply")
            self.apply_btn.setEnabled(True)
            self.reset_btn.setEnabled(True)
            self.preview_btn.setEnabled(True)
            self.setVisible(True)


def _badge(text: str, color: str) -> QLabel:
    from ..widgets import Badge

    return Badge(text, color)


def _eta_text(seconds: int) -> str:
    if seconds < 60:
        return f"~{seconds}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"~{minutes} min"
    return f"~{minutes // 60}h{minutes % 60:02d}"


def _icon_for(action: ActionDef) -> str:
    group_icons = {
        "repair": "wrench",
        "network": "globe",
        "security": "shield" if action.key.startswith("sec_firewall") else "security",
        "maintenance": "toolbox",
        "tools": "toolbox",
    }
    if action.key.startswith("sec_defender"):
        return "verified"
    return group_icons.get(action.group, "spark")


def section(title: str, sub: str = "") -> QVBoxLayout:
    """A titled block: returns a layout you can add cards to."""
    box = QVBoxLayout()
    box.setSpacing(8)
    label = QLabel(title)
    font = QFont()
    font.setPointSize(12)
    font.setWeight(QFont.Weight.DemiBold)
    label.setFont(font)
    box.addWidget(label)
    if sub:
        sub_lbl = QLabel(sub)
        sub_lbl.setProperty("muted", True)
        sub_lbl.setWordWrap(True)
        box.addWidget(sub_lbl)
    return box


class TabbedPage(Page):
    """A page made of other pages, one per tab (used by Network and Security)."""

    def __init__(
        self,
        ctx: AppContext,
        key: str,
        title: str,
        subtitle: str,
        icon_name: str,
        tabs: list[tuple[str, Page]],
    ):
        self.key = key
        self.title = title
        self.subtitle = subtitle
        self.icon_name = icon_name
        super().__init__(ctx)
        self.sub_pages = [page for _label, page in tabs]

        from PySide6.QtWidgets import QTabWidget

        heading = QLabel(title)
        font = QFont()
        font.setPointSize(18)
        font.setWeight(QFont.Weight.Bold)
        heading.setFont(font)
        self.content_layout.addWidget(heading)
        if subtitle:
            sub = QLabel(subtitle)
            sub.setProperty("muted", True)
            sub.setWordWrap(True)
            self.content_layout.addWidget(sub)

        widget = QTabWidget()
        for label, page in tabs:
            host = QWidget()
            layout = QVBoxLayout(host)
            layout.setContentsMargins(8, 10, 8, 8)
            layout.addWidget(page.content, 1)
            widget.addTab(host, label)
        self.content_layout.addWidget(widget, 1)

    def refresh(self) -> None:
        for page in self.sub_pages:
            page.on_show()

    def on_show(self) -> None:
        if self._dirty or not self._loaded:
            self._dirty = False
            self._loaded = True
            for page in self.sub_pages:
                page.on_show()
