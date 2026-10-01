"""Vector icons drawn at runtime — no binary assets to ship or lose.

Each icon is painted with QPainter on a transparent pixmap, so it scales to any
size and picks up the current theme colour automatically.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap


def _pen(color: QColor, width: float, cap=Qt.PenCapStyle.RoundCap):
    pen = QPen(color)
    pen.setWidthF(width)
    pen.setCapStyle(cap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def _setup(painter: QPainter, size: int, color: str, width_ratio: float = 0.085) -> float:
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    w = max(1.4, size * width_ratio)
    painter.setPen(_pen(QColor(color), w))
    painter.setBrush(QBrush())
    return w


# --------------------------------------------------------------------------
# individual glyphs (all drawn in a 24x24 coordinate space)
# --------------------------------------------------------------------------
def _grid(p: QPainter, s: float) -> None:
    for x, y in ((3, 3), (13, 3), (3, 13), (13, 13)):
        p.drawRoundedRect(QRectF(x * s, y * s, 8 * s, 8 * s), 1.8 * s, 1.8 * s)


def _bolt(p: QPainter, s: float) -> None:
    path = QPainterPath()
    path.moveTo(13 * s, 2 * s)
    path.lineTo(5 * s, 13.5 * s)
    path.lineTo(10.5 * s, 13.5 * s)
    path.lineTo(9 * s, 22 * s)
    path.lineTo(19 * s, 10 * s)
    path.lineTo(13.5 * s, 10 * s)
    path.closeSubpath()
    p.drawPath(path)


def _trash(p: QPainter, s: float) -> None:
    p.drawLine(QPointF(4 * s, 7 * s), QPointF(20 * s, 7 * s))
    p.drawLine(QPointF(10 * s, 4 * s), QPointF(14 * s, 4 * s))
    p.drawRoundedRect(QRectF(6 * s, 7 * s, 12 * s, 13 * s), 2 * s, 2 * s)
    p.drawLine(QPointF(10 * s, 11 * s), QPointF(10 * s, 17 * s))
    p.drawLine(QPointF(14 * s, 11 * s), QPointF(14 * s, 17 * s))


def _power(p: QPainter, s: float) -> None:
    rect = QRectF(4 * s, 4 * s, 16 * s, 16 * s)
    p.drawArc(rect, int(38 * 16), int(284 * 16))
    p.drawLine(QPointF(12 * s, 2.5 * s), QPointF(12 * s, 10 * s))


def _wrench(p: QPainter, s: float) -> None:
    p.drawArc(QRectF(13 * s, 2.5 * s, 8 * s, 8 * s), int(200 * 16), int(260 * 16))
    p.drawLine(QPointF(18.4 * s, 8.4 * s), QPointF(7 * s, 19.8 * s))
    p.drawLine(QPointF(4.6 * s, 17.4 * s), QPointF(9.4 * s, 22.2 * s))
    p.drawLine(QPointF(7 * s, 19.8 * s), QPointF(4.6 * s, 17.4 * s))


def _globe(p: QPainter, s: float) -> None:
    p.drawEllipse(QRectF(3 * s, 3 * s, 18 * s, 18 * s))
    p.drawLine(QPointF(3 * s, 12 * s), QPointF(21 * s, 12 * s))
    p.drawEllipse(QRectF(8 * s, 3 * s, 8 * s, 18 * s))


def _eye(p: QPainter, s: float) -> None:
    rect = QRectF(2.5 * s, 6 * s, 19 * s, 12 * s)
    p.drawArc(rect, int(30 * 16), int(120 * 16))
    p.drawArc(rect, int(210 * 16), int(120 * 16))
    p.drawEllipse(QRectF(9.5 * s, 9.5 * s, 5 * s, 5 * s))


def _shield(p: QPainter, s: float, check: bool = False) -> None:
    path = QPainterPath()
    path.moveTo(12 * s, 2.5 * s)
    path.lineTo(20.5 * s, 5.5 * s)
    path.lineTo(20.5 * s, 11.5 * s)
    path.quadTo(20.5 * s, 18 * s, 12 * s, 21.5 * s)
    path.quadTo(3.5 * s, 18 * s, 3.5 * s, 11.5 * s)
    path.lineTo(3.5 * s, 5.5 * s)
    path.closeSubpath()
    p.drawPath(path)
    if check:
        p.drawLine(QPointF(8.5 * s, 11.5 * s), QPointF(11 * s, 14.5 * s))
        p.drawLine(QPointF(11 * s, 14.5 * s), QPointF(16 * s, 8.5 * s))


def _sliders(p: QPainter, s: float) -> None:
    for y in (7, 12, 17):
        p.drawLine(QPointF(3 * s, y * s), QPointF(21 * s, y * s))
    for y, x in ((7, 15), (12, 9), (17, 16)):
        p.drawEllipse(QRectF((x - 2.2) * s, (y - 2.2) * s, 4.4 * s, 4.4 * s))


def _gamepad(p: QPainter, s: float) -> None:
    p.drawRoundedRect(QRectF(2.5 * s, 7 * s, 19 * s, 10.5 * s), 4 * s, 4 * s)
    p.drawLine(QPointF(7 * s, 10 * s), QPointF(7 * s, 14.5 * s))
    p.drawLine(QPointF(4.8 * s, 12.2 * s), QPointF(9.2 * s, 12.2 * s))
    p.drawEllipse(QRectF(14.5 * s, 11 * s, 2.6 * s, 2.6 * s))
    p.drawEllipse(QRectF(18 * s, 9.5 * s, 2.6 * s, 2.6 * s))


def _box(p: QPainter, s: float) -> None:
    p.drawLine(QPointF(3.5 * s, 7 * s), QPointF(20.5 * s, 7 * s))
    p.drawLine(QPointF(9 * s, 3.5 * s), QPointF(15 * s, 3.5 * s))
    p.drawRoundedRect(QRectF(5 * s, 7 * s, 14 * s, 13.5 * s), 2 * s, 2 * s)
    p.drawLine(QPointF(12 * s, 10.5 * s), QPointF(12 * s, 17 * s))
    p.drawLine(QPointF(9.5 * s, 13 * s), QPointF(12 * s, 10.5 * s))
    p.drawLine(QPointF(14.5 * s, 13 * s), QPointF(12 * s, 10.5 * s))


def _chip(p: QPainter, s: float) -> None:
    p.drawRoundedRect(QRectF(6 * s, 6 * s, 12 * s, 12 * s), 2.5 * s, 2.5 * s)
    p.drawRoundedRect(QRectF(10 * s, 10 * s, 4 * s, 4 * s), 1 * s, 1 * s)
    for i in (9, 12.5, 16):
        p.drawLine(QPointF(i * s, 3 * s), QPointF(i * s, 6 * s))
        p.drawLine(QPointF(i * s, 18 * s), QPointF(i * s, 21 * s))
        p.drawLine(QPointF(3 * s, i * s), QPointF(6 * s, i * s))
        p.drawLine(QPointF(18 * s, i * s), QPointF(21 * s, i * s))


def _drive(p: QPainter, s: float) -> None:
    p.drawEllipse(QRectF(3 * s, 6 * s, 18 * s, 6 * s))
    p.drawLine(QPointF(3 * s, 9 * s), QPointF(3 * s, 16 * s))
    p.drawArc(QRectF(3 * s, 13 * s, 18 * s, 6 * s), int(180 * 16), int(180 * 16))
    p.drawEllipse(QRectF(6 * s, 8.2 * s, 2 * s, 2 * s))


def _monitor(p: QPainter, s: float) -> None:
    p.drawRoundedRect(QRectF(3 * s, 4 * s, 18 * s, 13 * s), 2 * s, 2 * s)
    p.drawLine(QPointF(12 * s, 17 * s), QPointF(12 * s, 20.5 * s))
    p.drawLine(QPointF(8 * s, 20.5 * s), QPointF(16 * s, 20.5 * s))
    p.drawLine(QPointF(7 * s, 13 * s), QPointF(7 * s, 10 * s))
    p.drawLine(QPointF(11 * s, 13 * s), QPointF(11 * s, 7.5 * s))
    p.drawLine(QPointF(15 * s, 13 * s), QPointF(15 * s, 9 * s))


def _toolbox(p: QPainter, s: float) -> None:
    p.drawRoundedRect(QRectF(3 * s, 6.5 * s, 18 * s, 12 * s), 2.5 * s, 2.5 * s)
    p.drawRoundedRect(QRectF(7 * s, 3.5 * s, 10 * s, 5 * s), 1.5 * s, 1.5 * s)
    p.drawLine(QPointF(3 * s, 11.5 * s), QPointF(21 * s, 11.5 * s))
    p.drawRoundedRect(QRectF(9 * s, 13.5 * s, 6 * s, 3.5 * s), 1 * s, 1 * s)


def _gear(p: QPainter, s: float) -> None:
    p.drawEllipse(QRectF(8.5 * s, 8.5 * s, 7 * s, 7 * s))
    import math

    for i in range(8):
        angle = math.radians(i * 45)
        inner = 6.6
        outer = 10.6
        p.drawLine(
            QPointF(12 * s + math.cos(angle) * inner * s, 12 * s + math.sin(angle) * inner * s),
            QPointF(12 * s + math.cos(angle) * outer * s, 12 * s + math.sin(angle) * outer * s),
        )


def _search(p: QPainter, s: float) -> None:
    p.drawEllipse(QRectF(4 * s, 4 * s, 11 * s, 11 * s))
    p.drawLine(QPointF(12.2 * s, 12.2 * s), QPointF(20 * s, 20 * s))


def _refresh(p: QPainter, s: float) -> None:
    rect = QRectF(4 * s, 4 * s, 16 * s, 16 * s)
    p.drawArc(rect, int(35 * 16), int(290 * 16))
    p.drawLine(QPointF(20 * s, 4 * s), QPointF(20 * s, 10 * s))
    p.drawLine(QPointF(20 * s, 4 * s), QPointF(14.5 * s, 4 * s))


def _play(p: QPainter, s: float) -> None:
    path = QPainterPath()
    path.moveTo(7 * s, 4 * s)
    path.lineTo(19 * s, 12 * s)
    path.lineTo(7 * s, 20 * s)
    path.closeSubpath()
    p.drawPath(path)


def _stop(p: QPainter, s: float) -> None:
    p.drawRoundedRect(QRectF(6 * s, 6 * s, 12 * s, 12 * s), 2 * s, 2 * s)


def _check(p: QPainter, s: float) -> None:
    p.drawLine(QPointF(4.5 * s, 12.5 * s), QPointF(9.5 * s, 17.5 * s))
    p.drawLine(QPointF(9.5 * s, 17.5 * s), QPointF(19.5 * s, 6.5 * s))


def _warning(p: QPainter, s: float) -> None:
    path = QPainterPath()
    path.moveTo(12 * s, 3 * s)
    path.lineTo(22 * s, 20 * s)
    path.lineTo(2 * s, 20 * s)
    path.closeSubpath()
    p.drawPath(path)
    p.drawLine(QPointF(12 * s, 9 * s), QPointF(12 * s, 14 * s))
    p.drawEllipse(QRectF(11.2 * s, 16 * s, 1.6 * s, 1.6 * s))


def _undo(p: QPainter, s: float) -> None:
    p.drawArc(QRectF(4 * s, 4 * s, 16 * s, 12 * s), int(0 * 16), int(180 * 16))
    p.drawLine(QPointF(4 * s, 10 * s), QPointF(9 * s, 10 * s))
    p.drawLine(QPointF(4 * s, 10 * s), QPointF(7 * s, 6.5 * s))
    p.drawLine(QPointF(4 * s, 10 * s), QPointF(7 * s, 13.5 * s))
    p.drawLine(QPointF(12 * s, 16 * s), QPointF(12 * s, 21 * s))
    p.drawLine(QPointF(12 * s, 21 * s), QPointF(20 * s, 21 * s))


def _folder(p: QPainter, s: float) -> None:
    path = QPainterPath()
    path.moveTo(3 * s, 6 * s)
    path.lineTo(9 * s, 6 * s)
    path.lineTo(11 * s, 8.5 * s)
    path.lineTo(21 * s, 8.5 * s)
    path.lineTo(21 * s, 19 * s)
    path.lineTo(3 * s, 19 * s)
    path.closeSubpath()
    p.drawPath(path)


def _terminal(p: QPainter, s: float) -> None:
    p.drawRoundedRect(QRectF(2.5 * s, 4 * s, 19 * s, 16 * s), 2.5 * s, 2.5 * s)
    p.drawLine(QPointF(6 * s, 10 * s), QPointF(10 * s, 12.5 * s))
    p.drawLine(QPointF(10 * s, 12.5 * s), QPointF(6 * s, 15 * s))
    p.drawLine(QPointF(12.5 * s, 15.5 * s), QPointF(17.5 * s, 15.5 * s))


def _spark(p: QPainter, s: float) -> None:
    path = QPainterPath()
    path.moveTo(12 * s, 2.5 * s)
    path.quadTo(13.5 * s, 9 * s, 19 * s, 10.5 * s)
    path.quadTo(13.5 * s, 12.5 * s, 12 * s, 21.5 * s)
    path.quadTo(10.5 * s, 12.5 * s, 5 * s, 10.5 * s)
    path.quadTo(10.5 * s, 9 * s, 12 * s, 2.5 * s)
    path.closeSubpath()
    p.drawPath(path)


def _heart(p: QPainter, s: float) -> None:
    path = QPainterPath()
    path.moveTo(12 * s, 20 * s)
    path.quadTo(3 * s, 14 * s, 3 * s, 8.5 * s)
    path.quadTo(3 * s, 4.5 * s, 7 * s, 4.5 * s)
    path.quadTo(10 * s, 4.5 * s, 12 * s, 7.5 * s)
    path.quadTo(14 * s, 4.5 * s, 17 * s, 4.5 * s)
    path.quadTo(21 * s, 4.5 * s, 21 * s, 8.5 * s)
    path.quadTo(21 * s, 14 * s, 12 * s, 20 * s)
    path.closeSubpath()
    p.drawPath(path)


def _clock(p: QPainter, s: float) -> None:
    p.drawEllipse(QRectF(3.5 * s, 3.5 * s, 17 * s, 17 * s))
    p.drawLine(QPointF(12 * s, 7 * s), QPointF(12 * s, 12.5 * s))
    p.drawLine(QPointF(12 * s, 12.5 * s), QPointF(16 * s, 14.5 * s))


def _floppy(p: QPainter, s: float) -> None:
    p.drawRoundedRect(QRectF(3.5 * s, 4 * s, 17 * s, 16 * s), 2 * s, 2 * s)
    p.drawRoundedRect(QRectF(8 * s, 4 * s, 8 * s, 6 * s), 1 * s, 1 * s)
    p.drawRoundedRect(QRectF(7.5 * s, 13 * s, 9 * s, 7 * s), 1 * s, 1 * s)


GLYPHS: dict[str, Callable[[QPainter, float], None]] = {
    "dashboard": _grid,
    "performance": _bolt,
    "cleaner": _trash,
    "startup": _power,
    "repair": _wrench,
    "network": _globe,
    "privacy": _eye,
    "security": lambda p, s: _shield(p, s, check=False),
    "verified": lambda p, s: _shield(p, s, check=True),
    "interface": _sliders,
    "gaming": _gamepad,
    "apps": _box,
    "drivers": _chip,
    "disks": _drive,
    "systeminfo": _monitor,
    "tools": _toolbox,
    "settings": _gear,
    "search": _search,
    "refresh": _refresh,
    "play": _play,
    "stop": _stop,
    "check": _check,
    "warning": _warning,
    "undo": _undo,
    "folder": _folder,
    "terminal": _terminal,
    "spark": _spark,
    "heart": _heart,
    "clock": _clock,
    "save": _floppy,
}

_cache: dict[tuple[str, str, int], QIcon] = {}


def icon(name: str, color: str = "#4cc2ff", size: int = 64) -> QIcon:
    """Return a themed :class:`QIcon` for ``name`` (cached)."""
    key = (name, color, size)
    if key in _cache:
        return _cache[key]

    glyph = GLYPHS.get(name, _grid)
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    scale = size / 24.0
    _setup(painter, size, color)
    glyph(painter, scale)
    painter.end()
    result = QIcon(pixmap)
    _cache[key] = result
    return result


def pixmap(name: str, color: str = "#4cc2ff", size: int = 24) -> QPixmap:
    return icon(name, color, size).pixmap(size, size)
