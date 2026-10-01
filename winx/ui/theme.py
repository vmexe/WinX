"""Themes: colour palettes and the stylesheet that turns them into a UI."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QColor


@dataclass
class Palette:
    name: str
    window: str
    panel: str
    card: str
    card_alt: str
    border: str
    text: str
    muted: str
    accent: str
    accent_text: str
    success: str
    warning: str
    danger: str
    hover: str
    selection: str
    input_bg: str
    shadow: str

    def q(self, key: str) -> QColor:
        return QColor(getattr(self, key))


DARK = Palette(
    name="dark",
    window="#0b0e14",
    panel="#11151d",
    card="#161b25",
    card_alt="#1c2230",
    border="#232b3a",
    text="#e6edf3",
    muted="#8b98a9",
    accent="#4cc2ff",
    accent_text="#04222e",
    success="#3ecf8e",
    warning="#f5c451",
    danger="#ff6b6b",
    hover="#1e2634",
    selection="#1d3b52",
    input_bg="#0e131b",
    shadow="rgba(0,0,0,0.35)",
)

LIGHT = Palette(
    name="light",
    window="#eef1f6",
    panel="#ffffff",
    card="#ffffff",
    card_alt="#f6f8fb",
    border="#dde3ea",
    text="#1b2430",
    muted="#5c6b7d",
    accent="#0b6fc2",
    accent_text="#ffffff",
    success="#128a5b",
    warning="#b7791f",
    danger="#c92a2a",
    hover="#eef2f7",
    selection="#cfe4fb",
    input_bg="#ffffff",
    shadow="rgba(15,23,42,0.12)",
)

PALETTES = {"dark": DARK, "light": LIGHT}

ACCENTS = {
    "Blue": "#4cc2ff",
    "Teal": "#2dd4bf",
    "Violet": "#a78bfa",
    "Amber": "#f5a524",
    "Green": "#3ecf8e",
    "Rose": "#fb7185",
}


def stylesheet(p: Palette, accent: str | None = None) -> str:
    accent = accent or p.accent
    return f"""
/* ---------- base ---------- */
QWidget {{
    color: {p.text};
    background: transparent;
    font-family: "Segoe UI", "Inter", system-ui, sans-serif;
    font-size: 13px;
    selection-background-color: {p.selection};
    selection-color: {p.text};
}}
QMainWindow, QDialog {{
    background: {p.window};
}}
QToolTip {{
    background: {p.card_alt};
    color: {p.text};
    border: 1px solid {p.border};
    padding: 4px 7px;
    border-radius: 6px;
}}

/* ---------- containers ---------- */
QFrame#Card {{
    background: {p.card};
    border: 1px solid {p.border};
    border-radius: 12px;
}}
QFrame#Card[selected="true"] {{
    border: 1px solid {accent};
    background: {p.card_alt};
}}
QFrame#Panel {{
    background: {p.panel};
    border: 1px solid {p.border};
    border-radius: 12px;
}}
QFrame#NavRail {{
    background: {p.panel};
    border-right: 1px solid {p.border};
}}
QFrame#Separator {{
    background: {p.border};
}}
QFrame#HeroCard {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {accent}, stop:1 {p.card_alt});
    border: 1px solid {p.border};
    border-radius: 14px;
}}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{
    background: transparent; width: 10px; margin: 2px;
}}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{
    background: {p.border}; border-radius: 5px; min-height: 30px;
}}
QScrollBar::handle:horizontal {{
    background: {p.border}; border-radius: 5px; min-width: 30px;
}}
QScrollBar::handle:hover {{ background: {p.muted}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}

/* ---------- buttons ---------- */
QPushButton {{
    background: {p.card_alt};
    border: 1px solid {p.border};
    border-radius: 8px;
    padding: 7px 14px;
    color: {p.text};
}}
QPushButton:hover {{ background: {p.hover}; border-color: {accent}; }}
QPushButton:pressed {{ background: {p.selection}; }}
QPushButton:disabled {{ color: {p.muted}; border-color: {p.border}; background: {p.card}; }}
QPushButton[accent="true"] {{
    background: {accent}; color: {p.accent_text}; border: 1px solid {accent}; font-weight: 600;
}}
QPushButton[accent="true"]:hover {{ background: {accent}; border-color: {p.text}; }}
QPushButton[danger="true"] {{ color: {p.danger}; border-color: {p.danger}; }}
QPushButton[danger="true"]:hover {{ background: {p.danger}; color: #ffffff; }}
QPushButton[flat="true"] {{
    background: transparent; border: none; padding: 6px 8px; color: {p.muted};
}}
QPushButton[flat="true"]:hover {{ color: {accent}; background: {p.hover}; }}
QPushButton#NavButton {{
    background: transparent; border: none; border-radius: 9px;
    padding: 9px 12px; text-align: left; color: {p.text};
}}
QPushButton#NavButton:hover {{ background: {p.hover}; }}
QPushButton#NavButton[selected="true"] {{
    background: {p.card_alt};
    color: {accent};
    font-weight: 600;
    border-left: 3px solid {accent};
    padding-left: 9px;
}}

/* ---------- inputs ---------- */
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {p.input_bg};
    border: 1px solid {p.border};
    border-radius: 8px;
    padding: 6px 10px;
    color: {p.text};
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{
    border-color: {accent};
}}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox QAbstractItemView {{
    background: {p.card}; border: 1px solid {p.border};
    selection-background-color: {p.selection};
}}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{
    width: 17px; height: 17px; border-radius: 4px;
    border: 1px solid {p.border}; background: {p.input_bg};
}}
QCheckBox::indicator:hover {{ border-color: {accent}; }}
QCheckBox::indicator:checked {{
    background: {accent}; border-color: {accent};
    image: none;
}}
QCheckBox::indicator:indeterminate {{ background: {p.warning}; border-color: {p.warning}; }}
QRadioButton::indicator {{ width: 16px; height: 16px; border-radius: 8px;
    border: 1px solid {p.border}; background: {p.input_bg}; }}
QRadioButton::indicator:checked {{ background: {accent}; border-color: {accent}; }}

/* ---------- data views ---------- */
QTreeWidget, QTableWidget, QListWidget {{
    background: {p.card};
    border: 1px solid {p.border};
    border-radius: 10px;
    gridline-color: {p.border};
    alternate-background-color: {p.card_alt};
}}
QHeaderView::section {{
    background: {p.card_alt};
    color: {p.muted};
    border: none;
    border-bottom: 1px solid {p.border};
    padding: 7px 10px;
    font-weight: 600;
}}
QTreeWidget::item, QTableWidget::item {{ padding: 5px 4px; }}
QTreeWidget::item:selected, QTableWidget::item:selected {{
    background: {p.selection}; color: {p.text};
}}
QTreeWidget::item:hover, QTableWidget::item:hover {{ background: {p.hover}; }}

/* ---------- progress & tabs ---------- */
QProgressBar {{
    background: {p.input_bg};
    border: 1px solid {p.border};
    border-radius: 6px;
    height: 10px;
    text-align: center;
    color: {p.muted};
}}
QProgressBar::chunk {{ background: {accent}; border-radius: 5px; }}
QTabWidget::pane {{ border: 1px solid {p.border}; border-radius: 10px; background: {p.card}; }}
QTabBar::tab {{
    background: transparent; padding: 8px 16px; border-radius: 8px; color: {p.muted};
}}
QTabBar::tab:selected {{ background: {p.card_alt}; color: {p.text}; font-weight: 600; }}
QTabBar::tab:hover {{ color: {accent}; }}

QLabel[heading="true"] {{ font-size: 20px; font-weight: 700; }}
QLabel[sub="true"] {{ color: {p.muted}; }}
QLabel[muted="true"] {{ color: {p.muted}; }}
QLabel[success="true"] {{ color: {p.success}; }}
QLabel[warning="true"] {{ color: {p.warning}; }}
QLabel[danger="true"] {{ color: {p.danger}; }}
QLabel[accent="true"] {{ color: {accent}; }}
QStatusBar {{ background: {p.panel}; border-top: 1px solid {p.border}; color: {p.muted}; }}
QSplitter::handle {{ background: {p.border}; }}
""".replace("{p.muted)", str(p.muted))


def apply_theme(app, name: str = "dark", accent: str | None = None) -> Palette:
    """Install the stylesheet on ``app`` and return the palette in use."""
    palette = PALETTES.get(name, DARK)
    app.setStyleSheet(stylesheet(palette, accent))
    return palette
