"""3D view of an extruded model: the section at both ends, the critical ellipsoid of a 3D slope
analysis, and the water table and wells of a 3D seepage analysis. Drawn with QPainter in a
rotatable oblique projection (no OpenGL needed)."""
from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import (QDialog, QDoubleSpinBox, QHBoxLayout, QInputDialog, QLabel, QMessageBox, QPushButton,
                               QSlider, QVBoxLayout, QWidget)


def has_3d(res) -> bool:
    return bool(res) and bool(res.get("three_d")) and "error" not in (res.get("three_d") or {})


class View3D(QWidget):
    def __init__(self, project, analysis, parent=None):
        super().__init__(parent)
        self.p, self.a = project, analysis
        self.yaw, self.pitch = 35.0, 25.0
        self.setMinimumSize(640, 420)
        self._drag = None

    # projection: x right, y up, z into the screen, turned by yaw (about y) and pitch (about x)
    def _proj(self, x, y, z):
        cy, sy = math.cos(math.radians(self.yaw)), math.sin(math.radians(self.yaw))
        cp, sp = math.cos(math.radians(self.pitch)), math.sin(math.radians(self.pitch))
        X = x * cy + z * sy
        Z = -x * sy + z * cy
        Y = y * cp + Z * sp
        return X, Y

    def _frame(self):
        xs = [q[0] for r in self.p.regions for q in r.points]
        ys = [q[1] for r in self.p.regions for q in r.points]
        W = float(self.a.width3d)
        pts = [self._proj(x, y, z) for x in (min(xs), max(xs)) for y in (min(ys), max(ys)) for z in (0, W)]
        X = [q[0] for q in pts]; Y = [q[1] for q in pts]
        sx = (self.width() - 40) / max(max(X) - min(X), 1e-9)
        sy = (self.height() - 40) / max(max(Y) - min(Y), 1e-9)
        s = min(sx, sy)
        ox = 20 - min(X) * s + 0.5 * (self.width() - 40 - (max(X) - min(X)) * s)
        oy = self.height() - 20 + min(Y) * s - 0.5 * (self.height() - 40 - (max(Y) - min(Y)) * s)
        return lambda x, y, z: QPointF(ox + self._proj(x, y, z)[0] * s, oy - self._proj(x, y, z)[1] * s)

    def paintEvent(self, _e):
        g = QPainter(self)
        g.setRenderHint(QPainter.Antialiasing)
        pal = self.palette()
        g.fillRect(self.rect(), pal.base())
        if not self.p.regions:
            return
        P = self._frame()
        W = float(self.a.width3d)
        mats = {m.id: m for m in self.p.materials}
        # end faces and the outline of each region
        for z, alpha in ((W, 90), (0.0, 170)):
            for r in self.p.regions:
                m = mats.get(r.material_id)
                col = QColor(m.color if m else "#cccccc")
                col.setAlpha(alpha)
                g.setBrush(col)
                g.setPen(QPen(QColor(80, 80, 80), 1))
                g.drawPolygon(QPolygonF([P(x, y, z) for x, y in r.points]))
        g.setPen(QPen(QColor(110, 110, 110), 1))
        seen = set()
        for r in self.p.regions:
            for x, y in r.points:
                k = (round(x, 6), round(y, 6))
                if k not in seen:
                    seen.add(k)
                    g.drawLine(P(x, y, 0.0), P(x, y, W))
        res = self.a.results or {}
        t = res.get("three_d") or {}
        if res.get("type") == "slope" and "fos" in t:
            self._draw_ellipsoid(g, P, t)
        elif res.get("type") == "seepage" and t.get("z"):
            self._draw_seepage(g, P, res, t)
        g.setPen(pal.text().color())
        g.drawText(10, 18, "Drag to turn the view.  z runs into the page (0 at the front).")

    def _draw_ellipsoid(self, g, P, t):
        from ..geometry import GroundProfile
        gp = GroundProfile(self.p.regions)
        xc, yc, R, b, zc = t["xc"], t["yc"], t["R"], 0.5 * t["length"], t["zc"]
        g.setPen(QPen(QColor(200, 30, 30), 1.6))
        for z, Rz in t.get("strips", []):
            xs = np.linspace(xc - Rz, xc + Rz, 80)
            ys = yc - np.sqrt(np.maximum(Rz * Rz - (xs - xc) ** 2, 0.0))
            yg = gp.ground(xs)
            path = QPainterPath()
            started = False
            for x, y, top in zip(xs, ys, yg):
                if y <= top + 1e-9 and gp.xmin <= x <= gp.xmax:
                    q = P(x, y, z)
                    path.lineTo(q) if started else path.moveTo(q)
                    started = True
                else:
                    started = False
            g.drawPath(path)
        g.setPen(QPen(QColor(200, 30, 30), 1, Qt.DashLine))
        for zz in (max(0.0, zc - b), min(t["width"], zc + b)):
            g.drawLine(P(gp.xmin, gp.ground(gp.xmin), zz), P(gp.xmax, gp.ground(gp.xmax), zz))
        g.setPen(self.palette().text().color())
        g.drawText(10, 36, f"F (3D) = {t['fos']:.3f}    F (2D) = {t['fos_2d']:.3f}    slide length "
                           f"{t['length']:.1f}, centre z = {t['zc']:.1f}")

    def _draw_seepage(self, g, P, res, t):
        zs = t["z"]
        nn2 = t["nn2"]
        nodes = np.asarray(res["nodes"])
        tris = np.asarray(res["tris"])
        from ..seep import phreatic_segments
        hp = np.asarray(t["pressure_head"]).reshape(len(zs), nn2)
        g.setPen(QPen(QColor(30, 90, 220), 1.4))
        step = max(1, len(zs) // 8)
        for k in list(range(0, len(zs), step)) + [len(zs) - 1]:
            for x1, y1, x2, y2 in phreatic_segments(nodes, tris, hp[k]):
                g.drawLine(P(x1, y1, zs[k]), P(x2, y2, zs[k]))
        g.setPen(QPen(QColor(0, 140, 200), 3))
        for w in self.a.wells or []:
            x, z, yt, yb = (list(w) + [0, 0, 0, 0])[:4]
            g.drawLine(P(x, yt, z), P(x, yb, z))
        g.setPen(self.palette().text().color())
        g.drawText(10, 36, "Blue: water table at sections across the width; thick lines: wells")

    def mousePressEvent(self, e):
        self._drag = (e.position().x(), e.position().y(), self.yaw, self.pitch)

    def mouseMoveEvent(self, e):
        if self._drag:
            x0, y0, yaw, pitch = self._drag
            self.yaw = yaw + 0.4 * (e.position().x() - x0)
            self.pitch = max(-80.0, min(80.0, pitch - 0.4 * (e.position().y() - y0)))
            self.update()

    def mouseReleaseEvent(self, _e):
        self._drag = None


class View3DDialog(QDialog):
    def __init__(self, main, analysis):
        super().__init__(main)
        self.setWindowTitle(f"3D View - {analysis.name}")
        self.resize(900, 620)
        v = QVBoxLayout(self)
        self.view = View3D(main.project, analysis, self)
        v.addWidget(self.view, 1)
        h = QHBoxLayout()
        h.addWidget(QLabel("Turn:"))
        sl = QSlider(Qt.Horizontal)
        sl.setRange(-90, 90)
        sl.setValue(int(self.view.yaw))
        sl.valueChanged.connect(lambda val: (setattr(self.view, "yaw", float(val)), self.view.update()))
        h.addWidget(sl, 1)
        b = QPushButton("Close")
        b.clicked.connect(self.accept)
        h.addWidget(b)
        v.addLayout(h)


def show_3d(main):
    a = main.current_analysis()
    if a is None or not getattr(a, "three_d", False):
        QMessageBox.information(main, "3D View", "Select a 3D slope or seepage analysis (Analysis Settings > 3D).")
        return None
    d = View3DDialog(main, a)
    d.show()
    return d


def choose_section(main, z=None):
    """Show another section z of a solved 3D seepage analysis in the drawing."""
    a = main.current_analysis()
    r = a.results if a else None
    if not (r and r.get("type") == "seepage" and r.get("three_d")):
        QMessageBox.information(main, "3D Section", "Select a solved 3D seepage analysis first.")
        return None
    W = r["three_d"]["width"]
    if z is None:
        z, ok = QInputDialog.getDouble(main, "3D Section", f"Section z (0 to {W:g} {main.project.unit('length')}):",
                                       float(r.get("slice_z", 0.5 * W)), 0.0, W, 3)
        if not ok:
            return None
    from ..seep3d import slice_results
    a.results = slice_results(r, z)
    a.slice_z = float(z)
    main.refresh_props()
    main.canvas.update()
    return z
