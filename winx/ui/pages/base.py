"""Base class shared by the content pages."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QTabWidget, QVBoxLayout, QWidget

from ..context import AppContext


class Page(QWidget):
    """Common plumbing: a description line, lazy refresh and page metadata."""

    key = "page"
    title = "Page"
    subtitle = ""

    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self._loaded = False
        self._dirty = True

        self.layout_ = QVBoxLayout(self)
        if self.subtitle:
            caption = QLabel(self.subtitle)
            caption.setWordWrap(True)
            self.layout_.addWidget(caption)

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

    # -- helpers ---------------------------------------------------------
    def log(self, text: str, level: str = "info") -> None:
        self.ctx.log(text, level)

    def status(self, text: str) -> None:
        self.ctx.status(text)

    def on_error(self, message: str) -> None:
        first = (message or "Unknown error").splitlines()[0]
        self.log(first, "error")
        self.status(first)


class TabbedPage(Page):
    """A page made of other pages, one per tab (used by Network and Security)."""

    def __init__(
        self,
        ctx: AppContext,
        key: str,
        title: str,
        subtitle: str,
        tabs: list[tuple[str, Page]],
    ):
        self.key = key
        self.title = title
        self.subtitle = subtitle
        super().__init__(ctx)
        self.sub_pages = [page for _label, page in tabs]

        self.tabs = QTabWidget()
        for label, page in tabs:
            self.tabs.addTab(page, label)
        self.layout_.addWidget(self.tabs, 1)
        self.tabs.currentChanged.connect(self._tab_changed)

    def _tab_changed(self, index: int) -> None:
        page = self.tabs.widget(index)
        if isinstance(page, Page):
            page.on_show()

    def refresh(self) -> None:
        current = self.tabs.currentWidget()
        if isinstance(current, Page):
            current.on_show()
