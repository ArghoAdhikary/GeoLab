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
