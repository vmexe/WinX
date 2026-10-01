"""Light / dark selection using Qt's own colour-scheme support.

WinX never ships a stylesheet or a hand-made palette: asking Qt for a colour
scheme makes the *platform* style redraw itself the way Windows would, so the
app still looks like a stock Windows application in either mode.
``Qt.ColorScheme`` arrived in Qt 6.5; on anything older the preference is
remembered but the system setting wins.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import QApplication

SETTING_KEY = "ui/color_scheme"
SCALE_KEY = "ui/scale"

#: percent of the system font size; 100 = exactly what Windows asked for
MIN_SCALE, MAX_SCALE, DEFAULT_SCALE = 80, 180, 100

#: stored value -> label shown in Settings
CHOICES = [
    ("system", "Follow Windows"),
    ("light", "Light"),
    ("dark", "Dark"),
]


#: the value most recently requested, so a probe can put it back
_requested = "system"
_supported: bool | None = None


def _scheme_for(value: str):
    return {
        "light": Qt.ColorScheme.Light,
        "dark": Qt.ColorScheme.Dark,
    }.get((value or "").lower(), Qt.ColorScheme.Unknown)


def has_api() -> bool:
    hints = QGuiApplication.styleHints()
    return hasattr(Qt, "ColorScheme") and hasattr(hints, "setColorScheme")


def supported() -> bool:
    """True when this Qt build *actually* honours a requested colour scheme.

    The API exists from Qt 6.8, but some platform plugins ignore it (the
    offscreen one used by the tests does), so the answer is probed once and
    cached instead of guessed from the version.
    """
    global _supported
    if _supported is not None:
        return _supported
    if not has_api():
        _supported = False
        return False
    hints = QGuiApplication.styleHints()
    try:
        hints.setColorScheme(Qt.ColorScheme.Dark)
        _supported = hints.colorScheme() == Qt.ColorScheme.Dark
    except (RuntimeError, TypeError):
        _supported = False
    finally:
        try:
            hints.setColorScheme(_scheme_for(_requested))
        except (RuntimeError, TypeError):
            pass
    return _supported


def apply(value: str) -> bool:
    """Switch the application to ``system``/``light``/``dark``."""
    global _requested
    _requested = (value or "system").lower()
    if not has_api():
        return False
    QGuiApplication.styleHints().setColorScheme(_scheme_for(_requested))
    return supported()


def current(settings) -> str:
    value = settings.str(SETTING_KEY) or "system"
    return value if value in {key for key, _label in CHOICES} else "system"


def apply_saved(settings) -> None:
    apply(current(settings))


# --------------------------------------------------------------------------
# interface size
# --------------------------------------------------------------------------
_base_font: QFont | None = None


def base_font() -> QFont:
    """The font the system gave us, captured before anything scales it."""
    global _base_font
    if _base_font is None:
        app = QApplication.instance()
        _base_font = QFont(app.font()) if app else QFont()
    return QFont(_base_font)


def clamp_scale(percent) -> int:
    try:
        value = int(round(float(percent)))
    except (TypeError, ValueError):
        return DEFAULT_SCALE
    return max(MIN_SCALE, min(MAX_SCALE, value))


def apply_scale(percent) -> int:
    """Scale the whole interface by resizing the *system* font.

    Qt lays every native widget out from the application font, so changing its
    size grows buttons, rows and spacing together — no custom font is
    introduced and no stylesheet is involved.
    """
    app = QApplication.instance()
    value = clamp_scale(percent)
    if app is None:
        return value
    font = base_font()
    points = font.pointSizeF()
    if points <= 0:                      # font defined in pixels
        pixels = font.pixelSize() if font.pixelSize() > 0 else 12
        font.setPixelSize(max(8, round(pixels * value / 100)))
    else:
        font.setPointSizeF(max(6.0, points * value / 100))
    app.setFont(font)
    return value


def current_scale(settings) -> int:
    return clamp_scale(settings.value(SCALE_KEY, DEFAULT_SCALE))


def apply_saved_scale(settings) -> int:
    return apply_scale(current_scale(settings))
