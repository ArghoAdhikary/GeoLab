"""Small painted icons for the analysis kinds (no image files needed)."""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF

KIND_COLORS = {"slope": "#2e8b57", "seepage": "#2f6fd6", "stress": "#d4a017", "dynamic": "#c0392b",
               "thermal": "#e67e22", "transport": "#8e44ad", "air": "#6c7a89"}

_cache: dict = {}


def _poly(*pts):
    return QPolygonF([QPointF(x, y) for x, y in pts])


def _paint(p: QPainter, kind: str, s: float):
    c = QColor(KIND_COLORS.get(kind, "#555555"))
    dark = c.darker(140)
    p.setPen(QPen(dark, max(1.0, s / 24)))
    p.setBrush(QBrush(c))
    if kind == "slope":
        p.setBrush(QBrush(c.lighter(150)))
        p.drawPolygon(_poly((0.08 * s, 0.9 * s), (0.92 * s, 0.9 * s), (0.92 * s, 0.25 * s), (0.6 * s, 0.25 * s)))
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(dark, s / 12))
        p.drawArc(QRectF(0.3 * s, -0.25 * s, 0.75 * s, 1.05 * s), 200 * 16, 95 * 16)
    elif kind == "seepage":
        path = QPainterPath(QPointF(0.5 * s, 0.08 * s))
        path.cubicTo(0.5 * s, 0.08 * s, 0.15 * s, 0.5 * s, 0.2 * s, 0.65 * s)
        path.arcTo(QRectF(0.2 * s, 0.35 * s, 0.6 * s, 0.6 * s), 180, 180)
        path.cubicTo(0.85 * s, 0.5 * s, 0.5 * s, 0.08 * s, 0.5 * s, 0.08 * s)
        p.drawPath(path)
    elif kind == "stress":
        p.setBrush(QBrush(c.lighter(130)))
        p.drawRect(QRectF(0.2 * s, 0.55 * s, 0.6 * s, 0.35 * s))
        p.setBrush(QBrush(dark))
        for x in (0.32, 0.5, 0.68):
            p.drawPolygon(_poly(((x - 0.08) * s, 0.3 * s), ((x + 0.08) * s, 0.3 * s), (x * s, 0.48 * s)))
            p.drawRect(QRectF((x - 0.025) * s, 0.08 * s, 0.05 * s, 0.24 * s))
    elif kind == "dynamic":
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(c, s / 11))
        path = QPainterPath(QPointF(0.05 * s, 0.5 * s))
        for i in range(1, 41):
            t = i / 40
            path.lineTo(QPointF((0.05 + 0.9 * t) * s, (0.5 - 0.38 * math.sin(t * 6 * math.pi) * math.exp(-2.2 * t)) * s))
        p.drawPath(path)
    elif kind == "thermal":
        p.setBrush(QBrush(QColor("#ffffff")))
        p.drawRoundedRect(QRectF(0.4 * s, 0.06 * s, 0.2 * s, 0.6 * s), 0.1 * s, 0.1 * s)
        p.setBrush(QBrush(c))
        p.drawEllipse(QRectF(0.3 * s, 0.6 * s, 0.4 * s, 0.34 * s))
        p.drawRect(QRectF(0.46 * s, 0.3 * s, 0.08 * s, 0.35 * s))
    elif kind == "transport":
        for (x, y, r) in ((0.3, 0.35, 0.16), (0.62, 0.3, 0.12), (0.55, 0.65, 0.2), (0.25, 0.72, 0.1)):
            col = QColor(c)
            col.setAlphaF(0.55 + r)
            p.setBrush(QBrush(col))
            p.drawEllipse(QPointF(x * s, y * s), r * s, r * s)
    else:  # air
        p.setBrush(Qt.NoBrush)
        pen = QPen(c, s / 12)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        for y, w in ((0.3, 0.7), (0.5, 0.85), (0.7, 0.6)):
            path = QPainterPath(QPointF(0.08 * s, y * s))
            path.lineTo(QPointF(w * s, y * s))
            path.arcTo(QRectF((w - 0.08) * s, (y - 0.16) * s, 0.16 * s, 0.16 * s), 270, 270)
            p.drawPath(path)


def kind_pixmap(kind: str, size: int = 32) -> QPixmap:
    key = (kind, size)
    if key not in _cache:
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        _paint(p, kind, float(size))
        p.end()
        _cache[key] = pm
    return _cache[key]


def kind_icon(kind: str) -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48):
        icon.addPixmap(kind_pixmap(kind, size))
    return icon


# ---------------------------------------------------------------------------
# tool icons (drawing and view tools)
# ---------------------------------------------------------------------------
_INK = {"color": "#2b2b2b"}


def set_dark_icons(dark: bool):
    """Tool icons are drawn with dark lines by day and light lines at night."""
    _INK["color"] = "#dadde2" if dark else "#2b2b2b"


def _tool(p: QPainter, name: str, s: float):
    ink = QColor(_INK["color"])
    pen = QPen(ink, max(1.0, s / 16))
    pen.setJoinStyle(Qt.RoundJoin)
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)

    def P(*pts):
        return _poly(*[(x * s, y * s) for x, y in pts])
    if name == "select":
        p.setBrush(QBrush(QColor("#ffffff")))
        p.drawPolygon(P((0.3, 0.12), (0.3, 0.8), (0.45, 0.65), (0.57, 0.9), (0.66, 0.86), (0.54, 0.6), (0.74, 0.6)))
    elif name == "region":
        p.setBrush(QBrush(QColor("#f3d98b")))
        p.drawPolygon(P((0.1, 0.85), (0.9, 0.85), (0.9, 0.35), (0.55, 0.35), (0.3, 0.6), (0.1, 0.6)))
        p.setBrush(QBrush(ink))
        for x, y in ((0.1, 0.85), (0.9, 0.85), (0.9, 0.35), (0.55, 0.35), (0.3, 0.6), (0.1, 0.6)):
            p.drawEllipse(QPointF(x * s, y * s), s / 20, s / 20)
    elif name == "assign":
        for (x, y, c) in ((0.1, 0.15, "#e9c46a"), (0.5, 0.15, "#90be6d"), (0.1, 0.55, "#f4a261"), (0.5, 0.55, "#8ecae6")):
            p.setBrush(QBrush(QColor(c)))
            p.drawRect(QRectF(x * s, y * s, 0.36 * s, 0.32 * s))
    elif name == "piezo":
        p.setBrush(QBrush(QColor("#f3d98b")))
        p.setPen(QPen(ink, s / 20))
        p.drawPolygon(P((0.05, 0.9), (0.95, 0.9), (0.95, 0.3), (0.6, 0.3), (0.3, 0.6), (0.05, 0.6)))
        dash = QPen(QColor("#1f5fd6"), s / 11)
        dash.setStyle(Qt.DashLine)
        p.setPen(dash)
        p.drawLine(QPointF(0.05 * s, 0.75 * s), QPointF(0.95 * s, 0.5 * s))
        p.setPen(QPen(QColor("#1f5fd6"), s / 16))
        p.setBrush(QBrush(QColor("#1f5fd6")))
        p.drawPolygon(P((0.72, 0.3), (0.86, 0.3), (0.79, 0.42)))
    elif name == "bc":
        p.setBrush(QBrush(QColor("#c0392b")))
        p.setPen(QPen(QColor("#7b241c"), s / 20))
        for x in (0.25, 0.55, 0.85):
            p.drawPolygon(P((x - 0.12, 0.62), (x + 0.12, 0.62), (x, 0.38)))
        p.setPen(QPen(ink, s / 14))
        p.drawLine(QPointF(0.08 * s, 0.75 * s), QPointF(0.95 * s, 0.75 * s))
    elif name == "point_load":
        p.setPen(QPen(QColor("#b03a2e"), s / 9))
        p.drawLine(QPointF(0.5 * s, 0.08 * s), QPointF(0.5 * s, 0.62 * s))
        p.setBrush(QBrush(QColor("#b03a2e")))
        p.drawPolygon(P((0.35, 0.55), (0.65, 0.55), (0.5, 0.78)))
        p.setPen(QPen(ink, s / 14))
        p.drawLine(QPointF(0.1 * s, 0.85 * s), QPointF(0.9 * s, 0.85 * s))
    elif name == "surcharge":
        p.setPen(QPen(QColor("#b03a2e"), s / 14))
        p.setBrush(QBrush(QColor("#b03a2e")))
        p.drawLine(QPointF(0.12 * s, 0.15 * s), QPointF(0.88 * s, 0.15 * s))
        for x in (0.2, 0.4, 0.6, 0.8):
            p.drawLine(QPointF(x * s, 0.15 * s), QPointF(x * s, 0.6 * s))
            p.drawPolygon(P((x - 0.07, 0.58), (x + 0.07, 0.58), (x, 0.72)))
        p.setPen(QPen(ink, s / 14))
        p.drawLine(QPointF(0.05 * s, 0.85 * s), QPointF(0.95 * s, 0.85 * s))
    elif name == "entry_exit":
        p.setPen(QPen(ink, s / 16))
        path = QPainterPath(QPointF(0.03 * s, 0.82 * s))
        for x, y in ((0.3, 0.82), (0.6, 0.35), (0.97, 0.35)):
            path.lineTo(QPointF(x * s, y * s))
        p.drawPath(path)
        red = QPen(QColor("#d6223a"), s / 9)
        red.setCapStyle(Qt.FlatCap)
        p.setPen(red)
        p.drawLine(QPointF(0.05 * s, 0.82 * s), QPointF(0.28 * s, 0.82 * s))
        p.drawLine(QPointF(0.66 * s, 0.35 * s), QPointF(0.95 * s, 0.35 * s))
        arc = QPen(QColor("#2e8b57"), s / 14)
        p.setPen(arc)
        p.drawArc(QRectF(0.12 * s, -0.55 * s, 0.75 * s, 1.37 * s), 205 * 16, 110 * 16)
    elif name == "grid":
        p.setBrush(QBrush(ink))
        for i in range(4):
            for j in range(3):
                p.drawEllipse(QPointF((0.2 + 0.2 * i) * s, (0.15 + 0.17 * j) * s), s / 26, s / 26)
        p.setPen(QPen(QColor("#2e8b57"), s / 14))
        p.setBrush(Qt.NoBrush)
        p.drawArc(QRectF(0.1 * s, -0.1 * s, 0.8 * s, 1.0 * s), 220 * 16, 100 * 16)
    elif name == "reinforcement":
        p.setBrush(QBrush(QColor("#f3d98b")))
        p.drawPolygon(P((0.05, 0.9), (0.95, 0.9), (0.95, 0.15), (0.5, 0.15), (0.05, 0.75)))
        p.setPen(QPen(QColor("#555555"), s / 10))
        p.drawLine(QPointF(0.3 * s, 0.5 * s), QPointF(0.92 * s, 0.62 * s))
        p.drawLine(QPointF(0.3 * s, 0.68 * s), QPointF(0.92 * s, 0.8 * s))
    elif name == "flux_section":
        p.setPen(QPen(QColor("#1f5fd6"), s / 12))
        p.drawLine(QPointF(0.5 * s, 0.08 * s), QPointF(0.5 * s, 0.92 * s))
        p.setPen(QPen(ink, s / 16))
        for y in (0.3, 0.55, 0.8):
            p.drawLine(QPointF(0.15 * s, y * s), QPointF(0.85 * s, y * s))
            p.drawLine(QPointF(0.85 * s, y * s), QPointF(0.75 * s, (y - 0.07) * s))
            p.drawLine(QPointF(0.85 * s, y * s), QPointF(0.75 * s, (y + 0.07) * s))
    elif name == "text":
        f = p.font()
        f.setPixelSize(int(s * 0.8))
        f.setBold(True)
        f.setFamily("Times New Roman")
        p.setFont(f)
        p.drawText(QRectF(0, 0, s, s), Qt.AlignCenter, "A")
    elif name == "pan":
        p.setPen(QPen(ink, s / 12))
        c = 0.5 * s
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            tip = QPointF(c + dx * 0.42 * s, c + dy * 0.42 * s)
            p.drawLine(QPointF(c, c), tip)
            p.drawLine(tip, QPointF(tip.x() - dx * 0.12 * s - dy * 0.1 * s, tip.y() - dy * 0.12 * s - dx * 0.1 * s))
            p.drawLine(tip, QPointF(tip.x() - dx * 0.12 * s + dy * 0.1 * s, tip.y() - dy * 0.12 * s + dx * 0.1 * s))
    elif name in ("define", "results", "layout"):
        if name == "define":
            p.drawEllipse(QRectF(0.12 * s, 0.12 * s, 0.76 * s, 0.76 * s))
            p.setPen(QPen(QColor("#1f5fd6"), s / 9))
            p.drawLine(QPointF(0.32 * s, 0.68 * s), QPointF(0.72 * s, 0.28 * s))
        elif name == "results":
            dash = QPen(ink, s / 14)
            dash.setStyle(Qt.DotLine)
            p.setPen(dash)
            p.drawEllipse(QRectF(0.12 * s, 0.12 * s, 0.76 * s, 0.76 * s))
        else:
            p.drawRect(QRectF(0.12 * s, 0.15 * s, 0.76 * s, 0.7 * s))
            p.drawLine(QPointF(0.12 * s, 0.35 * s), QPointF(0.88 * s, 0.35 * s))
            p.drawLine(QPointF(0.45 * s, 0.35 * s), QPointF(0.45 * s, 0.85 * s))
    elif name in ("zoom_in", "zoom_out"):
        p.setPen(QPen(ink, s / 11))
        p.drawEllipse(QRectF(0.1 * s, 0.1 * s, 0.56 * s, 0.56 * s))
        p.drawLine(QPointF(0.6 * s, 0.6 * s), QPointF(0.9 * s, 0.9 * s))
        p.setPen(QPen(ink, s / 14))
        p.drawLine(QPointF(0.24 * s, 0.38 * s), QPointF(0.52 * s, 0.38 * s))
        if name == "zoom_in":
            p.drawLine(QPointF(0.38 * s, 0.24 * s), QPointF(0.38 * s, 0.52 * s))
    elif name == "print":
        p.setBrush(QBrush(QColor("#ffffff")))
        p.drawRect(QRectF(0.28 * s, 0.08 * s, 0.44 * s, 0.3 * s))
        p.setBrush(QBrush(QColor("#9aa5b1")))
        p.drawRoundedRect(QRectF(0.08 * s, 0.36 * s, 0.84 * s, 0.36 * s), 0.06 * s, 0.06 * s)
        p.setBrush(QBrush(QColor("#ffffff")))
        p.drawRect(QRectF(0.28 * s, 0.6 * s, 0.44 * s, 0.32 * s))
    elif name == "copy":
        p.setBrush(QBrush(QColor("#ffffff")))
        p.drawRect(QRectF(0.12 * s, 0.1 * s, 0.5 * s, 0.6 * s))
        p.drawRect(QRectF(0.38 * s, 0.3 * s, 0.5 * s, 0.6 * s))
    elif name == "grid_toggle":
        p.setBrush(QBrush(ink))
        for i in range(4):
            for j in range(4):
                p.drawEllipse(QPointF((0.17 + 0.22 * i) * s, (0.17 + 0.22 * j) * s), s / 22, s / 22)
    elif name == "snap":
        p.setBrush(QBrush(ink))
        for i in range(3):
            for j in range(3):
                p.drawEllipse(QPointF((0.2 + 0.3 * i) * s, (0.2 + 0.3 * j) * s), s / 24, s / 24)
        p.setPen(QPen(QColor("#d6223a"), s / 10))
        p.drawLine(QPointF(0.5 * s, 0.32 * s), QPointF(0.5 * s, 0.68 * s))
        p.drawLine(QPointF(0.32 * s, 0.5 * s), QPointF(0.68 * s, 0.5 * s))
    elif name == "materials":
        p.setBrush(QBrush(QColor("#e9c46a")))
        p.drawRect(QRectF(0.1 * s, 0.1 * s, 0.8 * s, 0.38 * s))
        p.setBrush(QBrush(QColor("#90be6d")))
        p.drawRect(QRectF(0.1 * s, 0.52 * s, 0.8 * s, 0.38 * s))
    elif name == "analyses":
        p.setBrush(QBrush(QColor("#ffffff")))
        p.drawRect(QRectF(0.15 * s, 0.08 * s, 0.7 * s, 0.84 * s))
        for y in (0.3, 0.5, 0.7):
            p.drawLine(QPointF(0.3 * s, y * s), QPointF(0.7 * s, y * s))


def tool_icon(name: str) -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32):
        key = ("tool", name, size, _INK["color"])
        if key not in _cache:
            pm = QPixmap(size, size)
            pm.fill(Qt.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.Antialiasing)
            _tool(p, name, float(size))
            p.end()
            _cache[key] = pm
        icon.addPixmap(_cache[key])
    return icon
