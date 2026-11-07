"""Dialogs of GeoLab 2.12: section from a map, landslide early warning, probabilistic analysis,
foundations and walls, laboratory tests, SWCC estimate, quantities and cost, comparing options,
and a small chart widget used by all of them."""
from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFileDialog, QFormLayout,
                               QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QMessageBox,
                               QPlainTextEdit, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
                               QTabWidget, QVBoxLayout, QWidget)

from .theme import is_dark, ui_font
from .tools import ToolDialog, analysis_combo, num, slope_analyses

LEVEL_COLORS = {"green": "#2e9d4f", "yellow": "#e3b505", "orange": "#e8720c", "red": "#d32f2f"}


# --------------------------------------------------------------------------- chart
class Chart(QWidget):
    """A small chart: line, bar and circle series, linear or log x, optional second y axis."""

    def __init__(self, title="", xlabel="", ylabel="", logx=False, parent=None):
        super().__init__(parent)
        self.title, self.xlabel, self.ylabel, self.logx = title, xlabel, ylabel, logx
        self.series = []        # dict(kind=line|bar|hbar|circle|vline|hline, ...)
        self.y2label = ""
        self.setMinimumHeight(200)

    def clear(self):
        self.series = []
        self.update()

    def line(self, xs, ys, color="#2f6fe0", width=2.0, label="", axis=1, dash=False, points=False):
        self.series.append(dict(kind="line", x=list(xs), y=list(ys), color=color, width=width, label=label,
                                axis=axis, dash=dash, points=points))
        self.update()

    def bars(self, xs, ys, color="#5b9bd5", width=None, label="", axis=1, colors=None):
        self.series.append(dict(kind="bar", x=list(xs), y=list(ys), color=color, w=width, label=label, axis=axis,
                                colors=colors))
        self.update()

    def hbars(self, labels, lows, highs, base, color_lo="#d9534f", color_hi="#5cb85c"):
        self.series.append(dict(kind="hbar", labels=list(labels), lo=list(lows), hi=list(highs), base=base,
                                c1=color_lo, c2=color_hi))
        self.update()

    def circle(self, cx, r, color="#2f6fe0"):
        self.series.append(dict(kind="circle", cx=cx, r=r, color=color, axis=1))
        self.update()

    def vline(self, x, color="#888", label=""):
        self.series.append(dict(kind="vline", x=x, color=color, label=label))
        self.update()

    def hline(self, y, color="#888", label="", axis=1):
        self.series.append(dict(kind="hline", y=y, color=color, label=label, axis=axis))
        self.update()

    # -- drawing --------------------------------------------------------------
    def _range(self, axis):
        xs, ys = [], []
        for s in self.series:
            if s.get("axis", 1) != axis:
                continue
            if s["kind"] in ("line", "bar"):
                xs += [x for x in s["x"] if x is not None]
                ys += [y for y in s["y"] if y is not None and math.isfinite(y)]
                if s["kind"] == "bar":
                    ys.append(0.0)
            elif s["kind"] == "circle":
                xs += [s["cx"] - s["r"], s["cx"] + s["r"]]
                ys += [0.0, s["r"]]
            elif s["kind"] == "hline":
                ys.append(s["y"])
        for s in self.series:
            if s["kind"] == "vline" and axis == 1:
                xs.append(s["x"])
        return xs, ys

    def paintEvent(self, e):
        g = QPainter(self)
        g.setRenderHint(QPainter.Antialiasing)
        dark = is_dark()
        fg = QColor("#d0d0d0" if dark else "#303030")
        grid = QColor("#3a3d42" if dark else "#e3e6ea")
        g.fillRect(self.rect(), QColor("#1e1f22" if dark else "#ffffff"))
        f = ui_font(8.5)
        g.setFont(f)
        W, H = self.width(), self.height()
        has_y2 = any(s.get("axis") == 2 for s in self.series)
        L, R, T, B = 58, 58 if has_y2 else 16, 24 if self.title else 10, 36
        plot = QRectF(L, T, max(10, W - L - R), max(10, H - T - B))
        if self.title:
            bf = ui_font(9.5, True)
            g.setFont(bf)
            g.setPen(fg)
            g.drawText(QRectF(0, 2, W, 20), Qt.AlignCenter, self.title)
            g.setFont(f)
        hb = [s for s in self.series if s["kind"] == "hbar"]
        if hb:
            self._paint_tornado(g, plot, hb[0], fg, grid)
            g.end()
            return
        xs, ys = self._range(1)
        if not xs or not ys:
            g.setPen(fg)
            g.drawText(self.rect(), Qt.AlignCenter, "No data yet")
            g.end()
            return
        tx = (lambda v: math.log10(max(v, 1e-12))) if self.logx else (lambda v: v)
        x0, x1 = min(tx(x) for x in xs), max(tx(x) for x in xs)
        y0, y1 = min(ys), max(ys)
        if any(s["kind"] == "circle" for s in self.series):
            y0 = 0.0
            span = max(x1 - x0, y1 - y0) or 1.0
            # equal scales so Mohr circles look round
            sx = plot.width() / span
            sy = plot.height() / span
            sc = min(sx, sy)
            x1 = x0 + plot.width() / sc
            y1 = y0 + plot.height() / sc
        if x1 == x0:
            x1 = x0 + 1
        if y1 == y0:
            y1 = y0 + 1
        pad = 0.05 * (y1 - y0)
        if not any(s["kind"] == "circle" for s in self.series):
            y1 += pad
            y0 -= pad if y0 != 0 else 0

        def P(x, y, ya=(y0, y1)):
            return QPointF(plot.left() + (tx(x) - x0) / (x1 - x0) * plot.width(),
                           plot.bottom() - (y - ya[0]) / (ya[1] - ya[0]) * plot.height())
        # axes and grid
        g.setPen(QPen(grid, 1))
        for k in range(6):
            yy = plot.top() + k / 5 * plot.height()
            g.drawLine(QPointF(plot.left(), yy), QPointF(plot.right(), yy))
        g.setPen(fg)
        for k in range(6):
            v = y1 - k / 5 * (y1 - y0)
            g.drawText(QRectF(0, plot.top() + k / 5 * plot.height() - 8, L - 6, 16), Qt.AlignRight | Qt.AlignVCenter,
                       _fmt(v))
        for k in range(6):
            v = x0 + k / 5 * (x1 - x0)
            lab = _fmt(10 ** v) if self.logx else _fmt(v)
            g.drawText(QRectF(plot.left() + k / 5 * plot.width() - 40, plot.bottom() + 2, 80, 16), Qt.AlignCenter, lab)
        g.drawText(QRectF(plot.left(), H - 18, plot.width(), 16), Qt.AlignCenter, self.xlabel)
        g.save()
        g.translate(12, plot.center().y())
        g.rotate(-90)
        g.drawText(QRectF(-plot.height() / 2, -8, plot.height(), 16), Qt.AlignCenter, self.ylabel)
        g.restore()
        g.drawRect(plot)
        y2 = None
        if has_y2:
            _, ys2 = self._range(2)
            if ys2:
                a, b = min(ys2), max(ys2)
                if b == a:
                    b = a + 1
                pad2 = 0.08 * (b - a)
                y2 = (a - pad2, b + pad2)
                for k in range(6):
                    v = y2[1] - k / 5 * (y2[1] - y2[0])
                    g.drawText(QRectF(plot.right() + 4, plot.top() + k / 5 * plot.height() - 8, R - 4, 16),
                               Qt.AlignLeft | Qt.AlignVCenter, _fmt(v))
                g.save()
                g.translate(W - 8, plot.center().y())
                g.rotate(90)
                g.drawText(QRectF(-plot.height() / 2, -8, plot.height(), 16), Qt.AlignCenter, self.y2label)
                g.restore()
        g.setClipRect(plot)
        legend = []
        for s in self.series:
            ya = y2 if s.get("axis") == 2 and y2 else (y0, y1)
            col = QColor(s.get("color", "#2f6fe0"))
            if s["kind"] == "bar":
                xsb = s["x"]
                w = s["w"] or ((xsb[1] - xsb[0]) * 0.8 if len(xsb) > 1 else 1.0)
                for i, (x, y) in enumerate(zip(xsb, s["y"])):
                    c = QColor(s["colors"][i]) if s.get("colors") else col
                    a, b = P(x - w / 2, 0, ya), P(x + w / 2, y, ya)
                    g.fillRect(QRectF(a, b).normalized(), c)
            elif s["kind"] == "line":
                pen = QPen(col, s["width"])
                if s["dash"]:
                    pen.setStyle(Qt.DashLine)
                g.setPen(pen)
                pts = [P(x, y, ya) for x, y in zip(s["x"], s["y"]) if y is not None and math.isfinite(y)]
                if len(pts) > 1:
                    g.drawPolyline(QPolygonF(pts))
                if s["points"]:
                    g.setBrush(col)
                    for p in pts:
                        g.drawEllipse(p, 3, 3)
                    g.setBrush(Qt.NoBrush)
            elif s["kind"] == "circle":
                c = P(s["cx"], 0)
                rr = s["r"] / (x1 - x0) * plot.width()
                g.setPen(QPen(col, 1.6))
                path = QPainterPath()
                path.arcMoveTo(QRectF(c.x() - rr, c.y() - rr, 2 * rr, 2 * rr), 0)
                path.arcTo(QRectF(c.x() - rr, c.y() - rr, 2 * rr, 2 * rr), 0, 180)
                g.drawPath(path)
            elif s["kind"] == "vline":
                g.setPen(QPen(col, 1.2, Qt.DashLine))
                a = P(s["x"], y0)
                g.drawLine(QPointF(a.x(), plot.top()), QPointF(a.x(), plot.bottom()))
            elif s["kind"] == "hline":
                g.setPen(QPen(col, 1.2, Qt.DashLine))
                a = P(x0 if not self.logx else 10 ** x0, s["y"], ya)
                g.drawLine(QPointF(plot.left(), a.y()), QPointF(plot.right(), a.y()))
            if s.get("label"):
                legend.append((s["label"], col))
        g.setClipping(False)
        lx = plot.left() + 8
        for text, col in legend:
            g.fillRect(QRectF(lx, plot.top() + 6, 12, 8), col)
            g.setPen(fg)
            g.drawText(QPointF(lx + 16, plot.top() + 14), text)
            lx += 26 + g.fontMetrics().horizontalAdvance(text)
        g.end()

    def _paint_tornado(self, g, plot, s, fg, grid):
        vals = [v for v in s["lo"] + s["hi"] + [s["base"]] if v is not None and math.isfinite(v)]
        if not vals:
            return
        a, b = min(vals), max(vals)
        pad = 0.08 * (b - a or 1)
        a, b = a - pad, b + pad
        n = len(s["labels"])
        left = plot.left() + 150
        width = plot.right() - left

        def X(v):
            return left + (v - a) / (b - a) * width
        rh = min(26.0, plot.height() / max(1, n))
        for i, lab in enumerate(s["labels"]):
            y = plot.top() + i * rh
            g.setPen(fg)
            g.drawText(QRectF(plot.left() - 50, y, 196, rh), Qt.AlignRight | Qt.AlignVCenter, lab[:34])
            for v, c in ((s["lo"][i], s["c1"]), (s["hi"][i], s["c2"])):
                if v is None or not math.isfinite(v):
                    continue
                x0, x1 = sorted((X(s["base"]), X(v)))
                g.fillRect(QRectF(x0, y + 3, max(1.0, x1 - x0), rh - 6), QColor(c))
        g.setPen(QPen(fg, 1.2, Qt.DashLine))
        g.drawLine(QPointF(X(s["base"]), plot.top()), QPointF(X(s["base"]), plot.top() + n * rh))
        g.setPen(fg)
        for k in range(5):
            v = a + k / 4 * (b - a)
            g.drawText(QRectF(X(v) - 30, plot.top() + n * rh + 4, 60, 16), Qt.AlignCenter, _fmt(v))
        g.drawText(QRectF(left, plot.top() + n * rh + 20, width, 16), Qt.AlignCenter,
                   "factor of safety (red: mean - 1 sd, green: mean + 1 sd)")


def _fmt(v):
    if v == 0:
        return "0"
    a = abs(v)
    if a >= 1e5 or a < 1e-2:
        return f"{v:.1e}"
    if a >= 100:
        return f"{v:.0f}"
    if a >= 10:
        return f"{v:.1f}"
    return f"{v:.2f}"


def _float(edit, default=0.0):
    try:
        return float(edit.text().replace(",", "."))
    except ValueError:
        return default


# --------------------------------------------------------------------------- map
class MapWidget(QWidget):
    """OpenStreetMap tiles. Drag to move, wheel to zoom, click to place point A, then B."""
    picked = Signal(int, float, float)     # 0 = A, 1 = B

    TILE = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
    # layer -> (label, tile address, attribution, highest zoom)
    LAYERS = {
        "osm": ("Street map", "https://tile.openstreetmap.org/{z}/{x}/{y}.png", "© OpenStreetMap contributors", 18),
        "satellite": ("Satellite", "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
                      "Imagery © Esri, Maxar, Earthstar Geographics", 18),
        "topo": ("Topographic (contours)", "https://tile.opentopomap.org/{z}/{x}/{y}.png",
                 "© OpenTopoMap (CC-BY-SA), © OpenStreetMap contributors", 17),
        "hillshade": ("Hillshade (terrain relief)",
                      "https://server.arcgisonline.com/ArcGIS/rest/services/Elevation/World_Hillshade/MapServer/tile/{z}/{y}/{x}",
                      "Hillshade © Esri", 16),
    }
    layer = "osm"
    ATTRIB = "© OpenStreetMap contributors"

    def set_layer(self, key):
        if key not in self.LAYERS:
            return
        self.layer = key
        _, self.TILE, self.ATTRIB, zmax = self.LAYERS[key]
        self.zoom = min(self.zoom, zmax)
        self.tiles.clear()
        self.pending.clear()
        self.update()

    def __init__(self, lat=22.36, lon=91.80, zoom=12, parent=None):
        super().__init__(parent)
        from PySide6.QtNetwork import QNetworkAccessManager
        self.lat, self.lon, self.zoom = lat, lon, zoom
        self.tiles = {}
        self.pending = set()
        self.points = [None, None]
        self.next_pt = 0
        self.net = QNetworkAccessManager(self)
        self.net.finished.connect(self._got)
        self._drag = None
        self._moved = False
        self.setMinimumSize(360, 300)
        self.setCursor(Qt.CrossCursor)
        self.setToolTip("Drag to move, mouse wheel to zoom, click to place A then B")

    @staticmethod
    def project(lat, lon, z):
        n = 2 ** z * 256
        x = (lon + 180) / 360 * n
        s = math.sin(math.radians(max(-85.05, min(85.05, lat))))
        y = (0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * n
        return x, y

    @staticmethod
    def unproject(x, y, z):
        n = 2 ** z * 256
        lon = x / n * 360 - 180
        lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
        return lat, lon

    def set_center(self, lat, lon, zoom=None):
        self.lat, self.lon = lat, lon
        if zoom is not None:
            self.zoom = zoom
        self.update()

    def _fetch(self, z, x, y):
        from PySide6.QtCore import QUrl
        from PySide6.QtNetwork import QNetworkRequest
        key = (z, x, y)
        if key in self.pending or key in self.tiles:
            return
        from .. import net
        if net.OFFLINE:
            return
        self.pending.add(key)
        req = QNetworkRequest(QUrl(self.TILE.format(z=z, x=x, y=y)))
        req.setRawHeader(b"User-Agent", b"GeoLab (geotechnical software; section picker)")
        reply = self.net.get(req)
        reply.setProperty("tile", f"{z}/{x}/{y}")

    def _got(self, reply):
        from PySide6.QtGui import QPixmap
        try:
            z, x, y = (int(v) for v in str(reply.property("tile")).split("/"))
        except ValueError:
            reply.deleteLater()
            return
        self.pending.discard((z, x, y))
        pm = QPixmap()
        if pm.loadFromData(bytes(reply.readAll())):
            self.tiles[(z, x, y)] = pm
            if len(self.tiles) > 400:
                for k in list(self.tiles)[:100]:
                    self.tiles.pop(k, None)
            self.update()
        reply.deleteLater()

    def paintEvent(self, e):
        g = QPainter(self)
        g.fillRect(self.rect(), QColor("#e8e4da"))
        cx, cy = self.project(self.lat, self.lon, self.zoom)
        ox, oy = cx - self.width() / 2, cy - self.height() / 2
        n = 2 ** self.zoom
        for tx in range(int(ox // 256), int((ox + self.width()) // 256) + 1):
            for ty in range(int(oy // 256), int((oy + self.height()) // 256) + 1):
                if not (0 <= ty < n):
                    continue
                key = (self.zoom, tx % n, ty)
                pm = self.tiles.get(key)
                if pm is None:
                    self._fetch(*key)
                else:
                    g.drawPixmap(int(tx * 256 - ox), int(ty * 256 - oy), pm)
        g.setRenderHint(QPainter.Antialiasing)
        pts = []
        for i, p in enumerate(self.points):
            if p is None:
                continue
            x, y = self.project(p[0], p[1], self.zoom)
            q = QPointF(x - ox, y - oy)
            pts.append(q)
            g.setPen(QPen(QColor("white"), 2))
            g.setBrush(QColor("#d32f2f" if i == 0 else "#1565c0"))
            g.drawEllipse(q, 8, 8)
            g.setPen(QColor("white"))
            g.setFont(ui_font(8, True))
            g.drawText(QRectF(q.x() - 8, q.y() - 8, 16, 16), Qt.AlignCenter, "AB"[i])
        if len(pts) == 2:
            g.setPen(QPen(QColor("#d32f2f"), 2.5, Qt.DashLine))
            g.drawLine(pts[0], pts[1])
        g.setPen(QColor("#333"))
        g.setFont(ui_font(7.5))
        from .. import net
        text = "Offline mode: no map" if net.OFFLINE else self.ATTRIB
        tw = g.fontMetrics().horizontalAdvance(text) + 10
        g.fillRect(QRectF(self.width() - tw, self.height() - 16, tw, 16), QColor(255, 255, 255, 200))
        g.drawText(QRectF(self.width() - tw + 2, self.height() - 16, tw - 4, 16), Qt.AlignRight | Qt.AlignVCenter,
                   text)
        g.end()

    def mousePressEvent(self, e):
        self._drag = e.position()
        self._moved = False

    def mouseMoveEvent(self, e):
        if self._drag is None:
            return
        d = e.position() - self._drag
        if abs(d.x()) + abs(d.y()) > 3:
            self._moved = True
            cx, cy = self.project(self.lat, self.lon, self.zoom)
            self.lat, self.lon = self.unproject(cx - d.x(), cy - d.y(), self.zoom)
            self._drag = e.position()
            self.update()

    def mouseReleaseEvent(self, e):
        if not self._moved and e.button() == Qt.LeftButton:
            cx, cy = self.project(self.lat, self.lon, self.zoom)
            x = cx - self.width() / 2 + e.position().x()
            y = cy - self.height() / 2 + e.position().y()
            lat, lon = self.unproject(x, y, self.zoom)
            i = self.next_pt
            self.points[i] = (lat, lon)
            self.next_pt = 1 - i
            self.picked.emit(i, lat, lon)
            self.update()
        self._drag = None

    def wheelEvent(self, e):
        z = self.zoom + (1 if e.angleDelta().y() > 0 else -1)
        self.zoom = max(3, min(self.LAYERS[self.layer][3], z))
        self.update()


class MapSectionDialog(QDialog):
    """Pick two points on a map; GeoLab gets the ground levels and builds a slope model."""

    def __init__(self, main):
        super().__init__(main)
        from .. import rainfall, terrain
        self.main, self.terrain = main, terrain
        self.setWindowTitle("Cross-Section from a Map")
        self.resize(1000, 760)
        self.profile = None
        v = QVBoxLayout(self)
        intro = QLabel("Click point <b>A</b> (top of the hill) and point <b>B</b> (the toe) on the map, or type "
                       "their coordinates. GeoLab gets the ground levels along the line (Copernicus 90 m DEM "
                       "through Open-Meteo, only the coordinates are sent) and builds the slope model with your "
                       "soil layers. A 90 m DEM does not see small cuttings: check against a survey.")
        intro.setWordWrap(True)
        v.addWidget(intro)
        top = QHBoxLayout()
        self.map = MapWidget()
        self.map.picked.connect(self._picked)
        top.addWidget(self.map, 3)
        side = QVBoxLayout()
        f = QFormLayout()
        self.place = QComboBox()
        for name, (la, lo) in rainfall.PLACES.items():
            self.place.addItem(name, (la, lo))
        self.place.currentIndexChanged.connect(lambda *_: self.map.set_center(*self.place.currentData(), zoom=13))
        f.addRow("Go to", self.place)
        self.layer = QComboBox()
        for k, (lab, *_r) in MapWidget.LAYERS.items():
            self.layer.addItem(lab, k)
        self.layer.currentIndexChanged.connect(lambda *_: self.map.set_layer(self.layer.currentData()))
        f.addRow("Map", self.layer)
        self.a_lat, self.a_lon, self.b_lat, self.b_lon = (QLineEdit() for _ in range(4))
        for w_ in (self.a_lat, self.a_lon, self.b_lat, self.b_lon):
            w_.setPlaceholderText("decimal degrees")
        f.addRow("A latitude", self.a_lat)
        f.addRow("A longitude", self.a_lon)
        f.addRow("B latitude", self.b_lat)
        f.addRow("B longitude", self.b_lon)
        self.n = QSpinBox()
        self.n.setRange(10, 300)
        self.n.setValue(60)
        f.addRow("Points along the line", self.n)
        self.water = QDoubleSpinBox()
        self.water.setRange(-1, 100)
        self.water.setValue(3.0)
        self.water.setSpecialValueText("no water table")
        self.water.setSuffix(" m below ground")
        f.addRow("Water table", self.water)
        side.addLayout(f)
        self.layers = QTableWidget(3, 5)
        self.layers.setHorizontalHeaderLabels(["Layer", "Thick. m", "c' kPa", "phi'", "gamma"])
        for r, row in enumerate(terrain.DEFAULT_LAYERS):
            for c, val in enumerate(row[:5]):
                self.layers.setItem(r, c, QTableWidgetItem(str(val)))
        self.layers.setToolTip("Thickness 0 = down to the bottom of the model")
        side.addWidget(QLabel("Soil layers below the ground (thickness 0 = to the bottom):"))
        side.addWidget(self.layers)
        row = QHBoxLayout()
        self.get_btn = QPushButton("Get Ground Levels")
        self.get_btn.clicked.connect(self.get_levels)
        self.make_btn = QPushButton("Make the Model")
        self.make_btn.setEnabled(False)
        self.make_btn.clicked.connect(self.make_model)
        row.addWidget(self.get_btn)
        row.addWidget(self.make_btn)
        side.addLayout(row)
        top.addLayout(side, 2)
        v.addLayout(top, 3)
        self.chart = Chart("Ground profile A to B", "distance from A (m)", "level (m)")
        v.addWidget(self.chart, 2)
        self.info = QLabel("")
        v.addWidget(self.info)
        self.project = None

    def _picked(self, i, lat, lon):
        a, b = ((self.a_lat, self.a_lon), (self.b_lat, self.b_lon))[i]
        a.setText(f"{lat:.6f}")
        b.setText(f"{lon:.6f}")

    def points(self):
        try:
            A = (float(self.a_lat.text()), float(self.a_lon.text()))
            B = (float(self.b_lat.text()), float(self.b_lon.text()))
        except ValueError:
            raise ValueError("Give both points: click A and B on the map or type the coordinates.") from None
        return A, B

    def get_levels(self, opener=None):
        try:
            A, B = self.points()
            self.profile = self.terrain.profile(A, B, self.n.value(), opener=opener)
        except ValueError as e:
            QMessageBox.warning(self, "Cross-section", str(e))
            return None
        pr = self.profile
        self.chart.clear()
        self.chart.line(pr["x"], pr["z"], "#8d6e3f", 2.2, "ground")
        st = self.terrain.steepest(pr)
        self.info.setText(f"Length {pr['length']:.0f} m, relief {st['relief']:.1f} m, steepest {st['angle']:.0f} deg "
                          f"at {st['at']:.0f} m from A.")
        self.make_btn.setEnabled(True)
        return pr

    def layer_rows(self):
        out = []
        cols = ["#d9c49c", "#b9a37a", "#8f8f8f", "#a7c49b", "#c9a28a"]
        for r in range(self.layers.rowCount()):
            cells = [self.layers.item(r, c).text() if self.layers.item(r, c) else "" for c in range(5)]
            if not cells[0].strip():
                continue
            try:
                t, c, p, g = (float(x) for x in cells[1:5])
            except ValueError:
                raise ValueError(f"Layer '{cells[0]}': type numbers for thickness, c', phi' and gamma.") from None
            out.append((cells[0], t, c, p, g, cols[r % len(cols)]))
        if not out:
            raise ValueError("Enter at least one soil layer.")
        return out

    def make_model(self):
        if self.profile is None:
            return None
        try:
            wd = None if self.water.value() < 0 else self.water.value()
            p = self.terrain.build_model(self.profile, self.layer_rows(), water_depth=wd)
        except ValueError as e:
            QMessageBox.warning(self, "Cross-section", str(e))
            return None
        self.project = p
        if self.main.maybe_save():
            self.main.set_project(p, dirty=True)
            self.main.log_msg("Built the model from the map section. Check the layers and press Solve (F5).")
            self.accept()
        return p


# --------------------------------------------------------------------------- early warning
class WarningDialog(ToolDialog):
    def __init__(self, main):
        from .. import rainfall, warning
        super().__init__(main, "Landslide Early Warning",
                         "Gets the last days of rain and the forecast for the place (Open-Meteo, only the "
                         "coordinates are sent) and works out the factor of safety and an alert level for each "
                         "day. <b>Model</b> uses your transient seepage and slope analyses (best). <b>Quick</b> "
                         "raises the water table with the antecedent rain and checks the solved slip surfaces. "
                         "The rain thresholds are editable starting values, not a national standard.",
                         "Check Now")
        self.W = warning
        self.place = QComboBox()
        for name, ll in rainfall.PLACES.items():
            self.place.addItem(name, ll)
        self.place.addItem("Other (type below)", None)
        self.lat, self.lon = QLineEdit("22.3569"), QLineEdit("91.7832")
        self.place.currentIndexChanged.connect(self._place)
        self.form.addRow("Place", self.place)
        row = QHBoxLayout()
        row.addWidget(self.lat)
        row.addWidget(self.lon)
        self.form.addRow("Latitude, longitude", row)
        self.past = QSpinBox()
        self.past.setRange(1, 90)
        self.past.setValue(14)
        self.fut = QSpinBox()
        self.fut.setRange(1, 16)
        self.fut.setValue(7)
        r2 = QHBoxLayout()
        r2.addWidget(QLabel("days back"))
        r2.addWidget(self.past)
        r2.addWidget(QLabel("days ahead"))
        r2.addWidget(self.fut)
        self.form.addRow("Period", r2)
        self.method = QComboBox()
        self.method.addItem("Quick (water table rises with the rain)", "quick")
        self.method.addItem("Model (transient seepage + slope)", "model")
        self.form.addRow("Method", self.method)
        r3 = QHBoxLayout()
        self.t1 = num(90, 1, 1000, 0, 5, "mm")
        self.t3 = num(150, 1, 3000, 0, 5, "mm")
        self.f_or = num(1.2, 0.5, 3, 2, 0.05)
        self.f_ye = num(1.3, 0.5, 3, 2, 0.05)
        for lab, w_ in (("1-day", self.t1), ("3-day", self.t3), ("orange F <", self.f_or), ("yellow F <", self.f_ye)):
            r3.addWidget(QLabel(lab))
            r3.addWidget(w_)
        self.form.addRow("Alerts", r3)
        self.watch = QCheckBox("Check again every 6 hours while GeoLab is open, and tell me if it gets worse")
        self.form.addRow(self.watch)
        self.banner = QLabel("")
        self.banner.setAlignment(Qt.AlignCenter)
        self.banner.setMinimumHeight(34)
        self.v.insertWidget(3, self.banner)
        self.chart = Chart("Rain and factor of safety", "day", "rain (mm/day)")
        self.chart.y2label = "factor of safety"
        self.v.insertWidget(4, self.chart, 2)
        self.series = None

    def _place(self, *_):
        ll = self.place.currentData()
        if ll:
            self.lat.setText(f"{ll[0]:.4f}")
            self.lon.setText(f"{ll[1]:.4f}")

    def settings(self):
        return {"rain_1d": self.t1.value(), "rain_3d": self.t3.value(), "orange": self.f_or.value(),
                "yellow": self.f_ye.value()}

    def run(self, opener=None, wait=False):
        lat, lon = _float(self.lat, 999), _float(self.lon, 999)
        main = self.main
        method = self.method.currentData()
        past, fut, st = self.past.value(), self.fut.value(), self.settings()
        p = main.project

        def job(progress=None, cancelled=None):
            series = self.W.fetch_forecast(lat, lon, past, fut, opener=opener)
            if method == "model":
                return self.W.model_assessment(p, series, st, progress), series
            pool = None
            sl = [a for a in p.analyses if a.kind == "slope" and a.results and a.results.get("critical")
                  and a.method != "finite_element"]
            if sl and p.piezometric_line:
                from ..whatif import SurfacePool
                pool = SurfacePool(p, sl[0], n=15)
            return self.W.quick_assessment(series, pool, st), series
        if wait:
            return self._show(job())
        self.start(job, self._show)
        return None

    def _show(self, out):
        res, series = out
        self.result = res
        place = self.place.currentText() if self.place.currentData() else f"{self.lat.text()}, {self.lon.text()}"
        self.out.setPlainText(self.W.text_report(res, place))
        lvl = res["level"]
        self.banner.setText(f"Alert for the coming days: {lvl.upper()}"
                            + (f"   (minimum F {res['min_fos']:.2f})" if res.get("min_fos") not in (None, math.inf) else ""))
        self.banner.setStyleSheet(f"background:{LEVEL_COLORS[lvl]}; color:white; font-weight:bold; font-size:12pt;"
                                  " border-radius:6px;")
        days = res["days"]
        xs = list(range(len(days)))
        self.chart.clear()
        self.chart.bars(xs, [d["rain"] for d in days], colors=["#5b9bd5" if not d["forecast"] else "#9ec5ea"
                                                               for d in days], label="rain (light = forecast)")
        fos = [d["fos"] if d["fos"] is not None and math.isfinite(d["fos"]) else None for d in days]
        if any(f is not None for f in fos):
            self.chart.line(xs, fos, "#d32f2f", 2.2, "F", axis=2, points=True)
        self.chart.xlabel = f"day ({days[0]['date']} to {days[-1]['date']})"
        self.main.last_warning = {"result": res, "place": place, "level": lvl}
        if self.watch.isChecked():
            self.main.start_warning_watch(self)
        return res


# --------------------------------------------------------------------------- probabilistic
class ReliabilityDialog(ToolDialog):
    def __init__(self, main):
        from .. import reliability
        super().__init__(main, "Probabilistic Analysis and Sensitivity",
                         "Monte Carlo on the lowest slip surfaces of the solved analysis: c', phi' and unit weight "
                         "of every material vary around their values (their standard deviation, or the COV below). "
                         "Gives the probability of failure, the reliability index, a histogram of F and a tornado "
                         "chart of which parameter matters most.", "Run")
        self.R = reliability
        self.analysis = analysis_combo(slope_analyses(main.project, solved_only=True), main.current_analysis())
        self.form.addRow("Analysis", self.analysis)
        self.n = QSpinBox()
        self.n.setRange(20, 5000)
        self.n.setValue(200)
        self.form.addRow("Trials", self.n)
        row = QHBoxLayout()
        self.cov_c = num(30, 0, 100, 0, 5, "%")
        self.cov_p = num(10, 0, 50, 0, 1, "%")
        self.cov_g = num(5, 0, 30, 0, 1, "%")
        for lab, w_ in (("c'", self.cov_c), ("tan phi'/phi'", self.cov_p), ("unit weight", self.cov_g)):
            row.addWidget(QLabel(lab))
            row.addWidget(w_)
        self.form.addRow("COV (when no sd is set)", row)
        self.water_sd = num(0, 0, 20, 2, 0.1, "m")
        self.form.addRow("Water table sd", self.water_sd)
        charts = QHBoxLayout()
        self.hist = Chart("Histogram of F", "factor of safety", "trials")
        self.torn = Chart("Sensitivity (tornado)")
        charts.addWidget(self.hist)
        charts.addWidget(self.torn)
        self.v.insertLayout(3, charts, 2)
        self.keep = self.add_button("Put in the Design Report", self._keep)

    def run(self, wait=False):
        p = self.main.project
        a = p.analysis(self.analysis.currentData())
        if a is None:
            return None
        n = self.n.value()
        cov = {"cohesion": self.cov_c.value() / 100, "phi": self.cov_p.value() / 100,
               "unit_weight": self.cov_g.value() / 100}
        wsd = self.water_sd.value()

        def job(progress=None, cancelled=None):
            from ..whatif import SurfacePool
            pool = SurfacePool(p, a, n=12)
            vs = self.R.variables(p, a, cov, wsd)
            if not vs:
                raise ValueError("No random variables: give the materials a standard deviation or a COV.")
            res = self.R.run(pool, vs, n, progress=progress, cancelled=cancelled)
            torn = self.R.tornado(pool, vs)
            return res, torn, vs
        if wait:
            return self._show(job())
        self.start(job, self._show)
        return None

    def _show(self, out):
        res, torn, vs = out
        self.result = out
        self.out.setPlainText(self.R.text_report(res, torn, vs))
        self.hist.clear()
        if res.get("n", 0) > 1:
            e = res["edges"]
            mids = [(e[i] + e[i + 1]) / 2 for i in range(len(e) - 1)]
            self.hist.bars(mids, res["histogram"], colors=["#d9534f" if m < 1 else "#5b9bd5" for m in mids])
            self.hist.vline(1.0, "#d32f2f")
        self.torn.clear()
        if torn and res.get("base"):
            self.torn.hbars([t["label"] for t in torn], [t["low"] for t in torn], [t["high"] for t in torn],
                            res["base"])
        self.keep.setEnabled(res.get("n", 0) > 1)
        return out

    def _keep(self):
        a = self.main.project.analysis(self.analysis.currentData())
        res = self.result[0]
        if a is not None and a.results is not None:
            a.results["probability"] = {"n": res["n"], "mean": res["mean"], "sd": res["sd"], "pf": res["pf"],
                                        "reliability_index": res.get("beta"), "min": res["min"], "max": res["max"],
                                        "histogram": res["histogram"], "hist_edges": res["edges"],
                                        "method": "Monte Carlo on the lowest slip surfaces"}
            self.main.dirty = True
            self.main.refresh_all()
            self.main.log_msg(f"Probability of failure {100 * res['pf']:.2f} % kept for '{a.name}'.")


# --------------------------------------------------------------------------- foundations and walls
def _form_values(widgets):
    return {k: w.value() for k, w in widgets.items()}


class FoundationDialog(QDialog):
    def __init__(self, main):
        super().__init__(main)
        from .. import foundations
        self.F, self.main = foundations, main
        self.setWindowTitle("Foundations and Retaining Walls")
        self.resize(820, 680)
        v = QVBoxLayout(self)
        self.tabs = QTabWidget()
        v.addWidget(self.tabs, 1)
        self.out = QPlainTextEdit()
        self.out.setReadOnly(True)
        self.out.setFont(QFont("Consolas", 9))
        v.addWidget(self.out, 1)
        self.bw = self._tab("Bearing capacity", [
            ("B", "Width B (m)", 2.0, 0.1, 100), ("L", "Length L (m, 0 = strip)", 0.0, 0, 1000),
            ("D", "Depth D (m)", 1.0, 0, 50), ("c", "c' or Su (kPa)", 0.0, 0, 2000),
            ("phi", "phi' (deg)", 30.0, 0, 50), ("gamma", "Unit weight (kN/m3)", 18.0, 5, 30),
            ("water", "Water table depth (m, -1 = deep)", -1.0, -1, 100), ("q", "Applied pressure (kPa)", 150.0, 0, 1e5),
            ("H", "Horizontal load (kN or kN/m)", 0.0, 0, 1e6), ("V", "Vertical load (kN or kN/m)", 0.0, 0, 1e7)],
            self.run_bearing, extra=self._bearing_extra)
        self.ww = self._tab("Retaining wall", [
            ("H", "Total height H (m)", 5.0, 0.5, 30), ("base", "Base width (m)", 3.5, 0.5, 30),
            ("toe", "Toe length (m)", 0.8, 0, 10), ("stem_top", "Stem top thickness (m)", 0.3, 0.1, 5),
            ("stem_bottom", "Stem bottom thickness (m)", 0.5, 0.1, 5), ("base_t", "Base thickness (m)", 0.5, 0.1, 5),
            ("back_phi", "Backfill phi' (deg)", 30.0, 0, 50), ("back_gamma", "Backfill unit weight", 18.0, 5, 30),
            ("back_c", "Backfill c' (kPa)", 0.0, 0, 100), ("surcharge", "Surcharge (kPa)", 10.0, 0, 500),
            ("water_h", "Water height behind (m)", 0.0, 0, 30), ("beta", "Backfill slope (deg)", 0.0, 0, 40),
            ("found_phi", "Foundation phi' (deg)", 30.0, 0, 50), ("found_c", "Foundation c' (kPa)", 0.0, 0, 500),
            ("found_gamma", "Foundation unit weight", 19.0, 5, 30), ("Df", "Toe embedment (m)", 0.5, 0, 10)],
            self.run_wall, extra=self._wall_extra)
        self.sw = self._tab("Cantilever sheet pile", [
            ("H", "Retained height (m)", 4.0, 0.5, 15), ("phi", "phi' of the sand (deg)", 32.0, 20, 45),
            ("gamma", "Unit weight", 18.0, 10, 25), ("surcharge", "Surcharge (kPa)", 0.0, 0, 200),
            ("factor", "Increase on the embedment", 1.2, 1.0, 2.0)], self.run_pile)
        self.stw = self._tab("Settlement", [
            ("B", "Width B (m)", 2.0, 0.1, 100), ("L", "Length L (m, 0 = strip)", 2.0, 0, 1000),
            ("D", "Depth D (m)", 1.0, 0, 50), ("q", "Net pressure (kPa)", 100.0, 0, 5000),
            ("water", "Water table depth (m)", 2.0, 0, 100)], self.run_settle, extra=self._settle_extra)

    def _tab(self, title, fields, slot, extra=None):
        w = QWidget()
        lay = QVBoxLayout(w)
        g = QGridLayout()
        widgets = {}
        for i, (key, label, val, lo, hi) in enumerate(fields):
            sp = QDoubleSpinBox()
            sp.setRange(lo, hi)
            sp.setDecimals(2)
            sp.setValue(val)
            widgets[key] = sp
            g.addWidget(QLabel(label), i // 2, (i % 2) * 2)
            g.addWidget(sp, i // 2, (i % 2) * 2 + 1)
        lay.addLayout(g)
        if extra:
            extra(lay, widgets)
        b = QPushButton("Calculate")
        b.clicked.connect(slot)
        lay.addWidget(b)
        lay.addStretch(1)
        self.tabs.addTab(w, title)
        return widgets

    def _bearing_extra(self, lay, w):
        row = QHBoxLayout()
        self.b_method = QComboBox()
        for m in ("vesic", "hansen", "meyerhof"):
            self.b_method.addItem(m.title(), m)
        self.b_undr = QCheckBox("Undrained (phi = 0, c = Su)")
        row.addWidget(QLabel("Factors"))
        row.addWidget(self.b_method)
        row.addWidget(self.b_undr)
        row.addStretch(1)
        lay.addLayout(row)

    def _wall_extra(self, lay, w):
        row = QHBoxLayout()
        self.w_method = QComboBox()
        self.w_method.addItem("Rankine", "rankine")
        self.w_method.addItem("Coulomb", "coulomb")
        self.w_passive = QCheckBox("Count passive resistance at the toe")
        row.addWidget(QLabel("Earth pressure"))
        row.addWidget(self.w_method)
        row.addWidget(self.w_passive)
        row.addStretch(1)
        lay.addLayout(row)

    def _settle_extra(self, lay, w):
        lay.addWidget(QLabel("Layers below the footing base: thickness, unit weight, E (kPa), nu, kind "
                             "(sand/clay), Cc, Cr, e0, preconsolidation (kPa, 0 = normally consolidated)"))
        self.s_layers = QPlainTextEdit("2, 18, 20000, 0.3, sand\n4, 17, 5000, 0.35, clay, 0.30, 0.05, 1.0, 0")
        self.s_layers.setMaximumHeight(80)
        lay.addWidget(self.s_layers)

    def run_bearing(self):
        v = _form_values(self.bw)
        wd = None if v["water"] < 0 else v["water"]
        r = self.F.bearing(v["B"], v["L"], v["D"], v["c"], v["phi"], v["gamma"], wd, v["H"], v["V"] or None,
                           self.b_method.currentData(), self.b_undr.isChecked())
        chk = self.F.bearing_check(self.main.project, r, v["q"])
        t = r["terms"]
        self.out.setPlainText(
            f"{'Strip' if r['strip'] else 'Rectangular'} footing B = {v['B']:g} m"
            + ("" if r["strip"] else f" x L = {r['L']:g} m") + f", D = {v['D']:g} m ({r['method'].title()} factors)\n"
            f"Nc = {r['Nc']:.2f}   Nq = {r['Nq']:.2f}   Ngamma = {r['Ngamma']:.2f}\n"
            f"Cohesion term {t['c']:.1f} + overburden term {t['q']:.1f} + width term {t['gamma']:.1f}\n"
            f"Ultimate bearing pressure qu = {r['qu']:.1f} kPa   (net {r['net']:.1f} kPa)\n\n"
            f"Design code check ({chk['code']}): {chk['text']}  ->  {'PASS' if chk['pass'] else 'FAIL'}")
        return r

    def run_wall(self):
        v = _form_values(self.ww)
        try:
            r = self.F.retaining_wall(method=self.w_method.currentData(), passive=self.w_passive.isChecked(), **v)
        except ValueError as e:
            self.out.setPlainText(str(e))
            return None
        self.out.setPlainText(self.F.wall_report(r))
        return r

    def run_pile(self):
        v = _form_values(self.sw)
        try:
            r = self.F.sheet_pile_cantilever(v["H"], v["phi"], v["gamma"], v["surcharge"], v["factor"])
        except ValueError as e:
            self.out.setPlainText(str(e))
            return None
        self.out.setPlainText(
            f"Ka = {r['Ka']:.3f}   Kp = {r['Kp']:.3f}\n"
            f"Embedment for equilibrium d0 = {r['d0']:.2f} m; design embedment = {r['embedment']:.2f} m\n"
            f"Total pile length = {r['total_length']:.2f} m\n"
            f"Maximum bending moment = {r['M_max']:.1f} kNm/m at {r['zero_shear_depth']:.2f} m below dredge level\n"
            "Simplified free-earth method for a cantilever wall in dry sand; check with a full analysis "
            "(Define > Structures and a stress analysis) for design.")
        return r

    def run_settle(self):
        v = _form_values(self.stw)
        layers = []
        for line in self.s_layers.toPlainText().splitlines():
            parts = [p.strip() for p in line.split(",") if p.strip()]
            if len(parts) < 5:
                continue
            try:
                d = {"thickness": float(parts[0]), "gamma": float(parts[1]), "E": float(parts[2]),
                     "nu": float(parts[3]), "kind": parts[4].lower()}
                if len(parts) >= 8:
                    d.update(Cc=float(parts[5]), Cr=float(parts[6]), e0=float(parts[7]))
                if len(parts) >= 9:
                    d["sigma_p"] = float(parts[8])
            except ValueError:
                self.out.setPlainText(f"Could not read the layer line: {line}")
                return None
            layers.append(d)
        if not layers:
            self.out.setPlainText("Enter at least one layer.")
            return None
        r = self.F.settlement(v["q"], v["B"], v["L"] or None, v["D"], layers, water_depth=v["water"])
        self.out.setPlainText(
            f"Immediate settlement {1000 * r['immediate']:.1f} mm\n"
            f"Consolidation settlement {1000 * r['consolidation']:.1f} mm\n"
            f"Total {1000 * r['total']:.1f} mm\n\n"
            f"{'z (m)':>8}{'sigma_v0':>10}{'d_sigma':>10}{'imm mm':>9}{'cons mm':>9}\n"
            + "\n".join(f"{x['z']:8.2f}{x['sigma_v']:10.1f}{x['d_sigma']:10.1f}{1000 * x['immediate']:9.2f}"
                        f"{1000 * x['consolidation']:9.2f}" for x in r["rows"]))
        return r


# --------------------------------------------------------------------------- lab tests
class LabTestDialog(QDialog):
    def __init__(self, main):
        super().__init__(main)
        from .. import labtest
        self.L, self.main = labtest, main
        self.setWindowTitle("Strength from Laboratory Tests")
        self.resize(900, 640)
        v = QVBoxLayout(self)
        top = QHBoxLayout()
        left = QVBoxLayout()
        f = QFormLayout()
        self.kind = QComboBox()
        self.kind.addItem("Triaxial CD / CU with pore pressure (effective)", "triaxial")
        self.kind.addItem("Triaxial, total stresses", "triaxial_total")
        self.kind.addItem("Triaxial UU (undrained strength Su)", "uu")
        self.kind.addItem("Direct shear", "direct_shear")
        self.kind.currentIndexChanged.connect(self._hint)
        f.addRow("Test", self.kind)
        self.c0 = QCheckBox("Force c' = 0")
        f.addRow(self.c0)
        left.addLayout(f)
        self.hint = QLabel()
        left.addWidget(self.hint)
        self.data = QPlainTextEdit("100, 300, 0\n200, 560, 0\n300, 820, 0")
        left.addWidget(self.data, 1)
        row = QHBoxLayout()
        fit = QPushButton("Fit")
        fit.clicked.connect(self.fit)
        row.addWidget(fit)
        self.mat = QComboBox()
        for m in main.project.materials:
            self.mat.addItem(m.name, m.id)
        self.use = QPushButton("Use for Material")
        self.use.setEnabled(False)
        self.use.clicked.connect(self.apply)
        row.addWidget(self.mat)
        row.addWidget(self.use)
        left.addLayout(row)
        top.addLayout(left, 2)
        self.chart = Chart("Mohr circles and failure line", "normal stress (kPa)", "shear stress (kPa)")
        top.addWidget(self.chart, 3)
        v.addLayout(top, 3)
        self.out = QPlainTextEdit()
        self.out.setReadOnly(True)
        self.out.setFont(QFont("Consolas", 9))
        v.addWidget(self.out, 1)
        self.res = None
        self._hint()

    def _hint(self, *_):
        k = self.kind.currentData()
        self.hint.setText("One specimen per line: normal stress, shear stress at failure (kPa)" if k == "direct_shear"
                          else "One specimen per line: sigma3, sigma1 at failure [, pore pressure u] (kPa)")

    def fit(self):
        k = self.kind.currentData()
        rows = self.L.parse(self.data.toPlainText(), "direct_shear" if k == "direct_shear" else "triaxial")
        try:
            if k == "direct_shear":
                r = self.L.direct_shear(rows, self.c0.isChecked())
            elif k == "uu":
                r = self.L.unconsolidated_undrained(rows)
            else:
                r = self.L.triaxial(rows, effective=(k == "triaxial"), force_c0=self.c0.isChecked())
        except ValueError as e:
            self.out.setPlainText(str(e))
            return None
        self.res = r
        self.out.setPlainText(self.L.text_report(r))
        self.chart.clear()
        if r["kind"] == "triaxial":
            for c in r["circles"]:
                self.chart.circle(c["centre"], c["radius"], "#2f6fe0")
            smax = max(c["sigma1"] for c in r["circles"])
            self.chart.line([0, smax], [r["c"], r["c"] + smax * math.tan(math.radians(r["phi"]))], "#d32f2f", 2,
                            f"c' {r['c']:.1f}, phi' {r['phi']:.1f}")
        elif r["kind"] == "direct_shear":
            xs = [p[0] for p in r["points"]]
            ys = [p[1] for p in r["points"]]
            self.chart.line(xs, ys, "#2f6fe0", 0.01, points=True)
            self.chart.line([0, max(xs)], [r["c"], r["c"] + max(xs) * math.tan(math.radians(r["phi"]))], "#d32f2f", 2,
                            f"c' {r['c']:.1f}, phi' {r['phi']:.1f}")
        else:
            for x in rows:
                s1 = x["sigma1"]
                self.chart.circle((s1 + x["sigma3"]) / 2, (s1 - x["sigma3"]) / 2)
            self.chart.hline(r["su"], "#d32f2f", f"Su {r['su']:.1f}")
        self.use.setEnabled(True)
        return r

    def apply(self):
        m = self.main.project.material(self.mat.currentData())
        if m is None or self.res is None:
            return
        self.main.before_change()
        if self.res["kind"] == "uu":
            m.cohesion, m.phi = round(self.res["su"], 2), 0.0
        else:
            m.cohesion, m.phi = round(self.res["c"], 2), round(self.res["phi"], 2)
        self.main.after_change(f"Strength of {m.name} from the lab tests")


# --------------------------------------------------------------------------- SWCC estimate
class SwccDialog(QDialog):
    def __init__(self, main):
        super().__init__(main)
        from .. import swcc
        self.S, self.main = swcc, main
        self.setWindowTitle("Estimate SWCC and k from Grain Size")
        self.resize(820, 560)
        v = QVBoxLayout(self)
        intro = QLabel("Sands and gravels: the Modified Kovacs model from D10, D60 and the void ratio, and "
                       "k from Chapuis (2004). Silts and clays: the average curve of the soil type (Carsel & "
                       "Parrish 1988) from the USCS symbol or the liquid limit. These are estimates: use tests "
                       "when you have them.")
        intro.setWordWrap(True)
        v.addWidget(intro)
        top = QHBoxLayout()
        f = QFormLayout()
        self.mat = QComboBox()
        for m in main.project.materials:
            self.mat.addItem(m.name, m.id)
        f.addRow("Material", self.mat)
        self.d10 = num(0.1, 0.0, 50, 4, 0.01, "mm")
        self.d60 = num(0.3, 0.0, 100, 4, 0.05, "mm")
        self.e = num(0.6, 0.1, 5, 3, 0.05)
        self.wl = num(0, 0, 300, 0, 1, "%")
        self.wl.setSpecialValueText("none (sand)")
        self.uscs = QComboBox()
        self.uscs.addItem("(from D10 / liquid limit)", "")
        for k in self.S.USCS_TEXTURE:
            self.uscs.addItem(k, k)
        for lab, w_ in (("D10", self.d10), ("D60", self.d60), ("Void ratio e", self.e), ("Liquid limit", self.wl),
                        ("USCS symbol", self.uscs)):
            f.addRow(lab, w_)
        b = QPushButton("Estimate")
        b.clicked.connect(self.estimate)
        f.addRow(b)
        self.use = QPushButton("Use for Material")
        self.use.setEnabled(False)
        self.use.clicked.connect(self.apply)
        f.addRow(self.use)
        top.addLayout(f, 2)
        self.chart = Chart("Soil-water characteristic curve", "suction (kPa)", "volumetric water content",
                           logx=True)
        top.addWidget(self.chart, 3)
        v.addLayout(top, 3)
        self.out = QLabel("")
        self.out.setWordWrap(True)
        v.addWidget(self.out)
        self.res = None

    def estimate(self):
        wl = self.wl.value() or None
        r = self.S.estimate(self.d10.value(), self.d60.value(), self.e.value(), wl, self.uscs.currentData() or None)
        self.res = r
        self.chart.clear()
        self.chart.line(r["suction"], r["theta"], "#2f6fe0", 2.2, "estimate")
        self.out.setText(f"{r['method']}: theta_s {r['theta_s']:.3f}, theta_r {r['theta_r']:.3f}, van Genuchten "
                         f"alpha {r['vg_alpha']:.3g} 1/m, n {r['vg_n']:.3f}; k_sat {r['k_sat']:.2e} m/s; "
                         f"air entry about {r['air_entry_kpa']:.1f} kPa")
        self.use.setEnabled(True)
        return r

    def apply(self):
        m = self.main.project.material(self.mat.currentData())
        if m is None or self.res is None:
            return
        self.main.before_change()
        self.S.apply(m, self.res)
        self.main.after_change(f"Hydraulic properties of {m.name} estimated from the grain size")


# --------------------------------------------------------------------------- quantities and comparing options
class QuantitiesDialog(QDialog):
    def __init__(self, main):
        super().__init__(main)
        from .. import quantities
        self.Q, self.main = quantities, main
        self.setWindowTitle("Quantities and Cost")
        self.resize(760, 600)
        v = QVBoxLayout(self)
        f = QFormLayout()
        self.length = num(1.0, 0.1, 1e5, 1, 10, "m")
        f.addRow("Length of slope / embankment", self.length)
        self.cur = QLineEdit("BDT")
        f.addRow("Currency", self.cur)
        self.rates = {}
        row = QHBoxLayout()
        for key, label, val in (("cut", "cut /m3", 450), ("fill", "fill /m3", 650),
                                ("reinforcement", "reinforcement /m", 2500), ("structure", "wall, pile /m", 18000)):
            w_ = num(val, 0, 1e8, 0, 50)
            self.rates[key] = w_
            row.addWidget(QLabel(label))
            row.addWidget(w_)
        f.addRow("Rates", row)
        er = QHBoxLayout()
        self.existing = QLineEdit()
        self.existing.setPlaceholderText("optional: the project file of the existing ground, for cut and fill")
        br = QPushButton("Browse...")
        br.clicked.connect(self._browse)
        er.addWidget(self.existing, 1)
        er.addWidget(br)
        f.addRow("Existing ground", er)
        v.addLayout(f)
        b = QPushButton("Calculate")
        b.clicked.connect(self.calculate)
        v.addWidget(b)
        self.out = QPlainTextEdit()
        self.out.setReadOnly(True)
        self.out.setFont(QFont("Consolas", 9))
        v.addWidget(self.out, 1)

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Existing Ground", self.main.last_dir(),
                                              "GeoLab or GeoStudio project (*.slab *.gsz)")
        if path:
            self.existing.setText(path)

    def rate_dict(self):
        return {"currency": self.cur.text().strip() or "BDT", **{k: w.value() for k, w in self.rates.items()}}

    def calculate(self):
        ex = None
        if self.existing.text().strip():
            from ..fileio import load_project
            try:
                ex = load_project(self.existing.text().strip())
            except Exception as e:                      # noqa: BLE001
                self.out.setPlainText(f"Could not open the existing ground: {e}")
                return None
        try:
            q = self.Q.quantities(self.main.project, self.length.value(), ex)
        except ValueError as e:
            self.out.setPlainText(str(e))
            return None
        c = self.Q.cost(q, self.rate_dict())
        self.out.setPlainText(self.Q.text_quantities(q, c))
        return q, c


class CompareDialog(QDialog):
    def __init__(self, main):
        super().__init__(main)
        from .. import quantities
        self.Q, self.main = quantities, main
        self.setWindowTitle("Compare Design Options")
        self.resize(900, 560)
        v = QVBoxLayout(self)
        intro = QLabel("Put several designs side by side: the open project and any saved project files. Each "
                       "slope analysis gives a row with F, the code minimum, pass or fail, the probability of "
                       "failure (if run) and the cost (rates from Tools > Quantities and Cost).")
        intro.setWordWrap(True)
        v.addWidget(intro)
        row = QHBoxLayout()
        self.files = QListWidget()
        row.addWidget(self.files, 1)
        col = QVBoxLayout()
        add = QPushButton("Add Project Files...")
        add.clicked.connect(self.add_files)
        rem = QPushButton("Remove")
        rem.clicked.connect(lambda: self.files.takeItem(self.files.currentRow()))
        self.solve = QCheckBox("Solve the options that are not solved")
        self.solve.setChecked(True)
        go = QPushButton("Compare")
        go.clicked.connect(self.compare)
        for w_ in (add, rem, self.solve, go):
            col.addWidget(w_)
        col.addStretch(1)
        row.addLayout(col)
        v.addLayout(row, 1)
        self.out = QPlainTextEdit()
        self.out.setReadOnly(True)
        self.out.setFont(QFont("Consolas", 9))
        v.addWidget(self.out, 2)
        self.extra = []

    def add_files(self, paths=None):
        if not paths:
            paths, _ = QFileDialog.getOpenFileNames(self, "Design Options", self.main.last_dir(),
                                                    "GeoLab or GeoStudio project (*.slab *.gsz)")
        for p in paths or []:
            self.files.addItem(p)

    def options(self):
        from ..fileio import load_project
        opts = [(f"{self.main.project.title or 'Open project'} (open)", self.main.project)]
        for i in range(self.files.count()):
            path = self.files.item(i).text()
            opts.append((Path(path).stem, load_project(path)))
        return opts

    def compare(self):
        try:
            opts = self.options()
        except Exception as e:                          # noqa: BLE001
            self.out.setPlainText(f"Could not open a file: {e}")
            return None
        if self.solve.isChecked():
            from ..solver import solve_all
            for name, p in opts[1:]:
                if any(a.kind == "slope" and not a.results for a in p.analyses):
                    solve_all(p)
        rows = self.Q.compare(opts)
        self.out.setPlainText(self.Q.text_compare(rows))
        return rows
