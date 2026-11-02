"""Interactive drawing canvas."""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ..geometry import point_in_polygon
from ..model import PointLoad, Surcharge
from .render import Renderer, View, project_bounds

MODE_HINTS = {
    "select": "Select: click a region to select it, drag a point to move it. Delete removes the selected region.",
    "region": "Draw Regions: click to add points; click the first point, press Enter or right-click to close.",
    "assign": "Draw Materials: click a region to assign the current material.",
    "piezo": "Draw Piezometric Line: click points left to right; press Enter or right-click to finish.",
    "bc": "Draw Boundary Conditions: click points along a region edge; press Enter or right-click to finish.",
    "point_load": "Draw Point Loads: click on the ground surface to place a load.",
    "surcharge": "Draw Surcharge Loads: click the start and end of the loaded length.",
    "entry_exit": "Draw Slip Surface Entry and Exit: click the 2 ends of the entry range, then the 2 ends of the exit range.",
    "grid": "Draw Slip Surface Grid: click two opposite corners of the grid of centres.",
    "reinforcement": "Draw Reinforcement: click the head (at the slope face), then the far end inside the slope.",
    "flux_section": "Draw Flux Section: click points across the flow; press Enter or right-click to finish.",
    "text": "Sketch Text: click where the text goes.",
    "pan": "Pan: drag to move the view. Mouse wheel zooms.",
}


class Canvas(QWidget):
    status = Signal(str)
    coords = Signal(float, float)

    def __init__(self, host):
        super().__init__()
        self.host = host
        self.view = View()
        self.mode = "select"
        self.temp: list[list[float]] = []
        self.cursor_w = None
        self.selected_region = None
        self.drag = None
        self.pan_from = None
        self.fitted = False
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumSize(400, 300)

    # -- view ------------------------------------------------------------
    def zoom_fit(self):
        self.view.fit(project_bounds(self.host.project), QRectF(self.rect()))
        self.fitted = True
        self.update()

    def resizeEvent(self, e):
        if not self.fitted:
            self.zoom_fit()
        else:
            self.view.rect = QRectF(self.rect())
        super().resizeEvent(e)

    def set_mode(self, mode):
        self.mode = mode
        self.temp = []
        self.setCursor(Qt.OpenHandCursor if mode == "pan" else Qt.CrossCursor if mode != "select" else Qt.ArrowCursor)
        self.status.emit(MODE_HINTS.get(mode, ""))
        self.update()

    # -- painting --------------------------------------------------------
    def paintEvent(self, e):
        g = QPainter(self)
        self.view.rect = QRectF(self.rect())
        h = self.host
        opts = dict(h.opts)
        opts["selected_region"] = self.selected_region
        opts["grid_spacing"] = h.project.grid_spacing
        Renderer(h.project, h.current_analysis(), self.view, g, mode=h.view_mode, opts=opts).draw()
        if self.temp:
            pen = QPen(QColor("#d01f1f"), 1.6)
            pen.setCosmetic(True)
            g.setPen(pen)
            pts = [self.view.dev(x, y) for x, y in self.temp]
            for i in range(len(pts) - 1):
                g.drawLine(pts[i], pts[i + 1])
            if self.cursor_w and self.mode in ("region", "piezo", "bc", "flux_section", "reinforcement"):
                g.setPen(QPen(QColor("#d01f1f"), 1, Qt.DashLine))
                g.drawLine(pts[-1], self.view.dev(*self.cursor_w))
            g.setBrush(QColor("#d01f1f"))
            for p in pts:
                g.drawEllipse(p, 3.5, 3.5)
        if self.cursor_w and self.mode not in ("select", "pan"):
            d = self.view.dev(*self.cursor_w)
            g.setPen(QPen(QColor("#0a6ad1"), 1))
            g.setBrush(Qt.NoBrush)
            g.drawRect(QRectF(d.x() - 5, d.y() - 5, 10, 10))
        g.end()

    # -- snapping --------------------------------------------------------
    def snap(self, px, py):
        best, bd = None, 10.0
        for r in self.host.project.regions:
            for x, y in r.points:
                d = self.view.dev(x, y)
                dist = math.hypot(d.x() - px, d.y() - py)
                if dist < bd:
                    best, bd = [x, y], dist
        for x, y in self.temp:
            d = self.view.dev(x, y)
            dist = math.hypot(d.x() - px, d.y() - py)
            if dist < bd:
                best, bd = [x, y], dist
        if best:
            return best
        x, y = self.view.world(px, py)
        if self.host.opts.get("snap", True):
            s = self.host.project.grid_spacing
            x, y = round(x / s) * s, round(y / s) * s
        return [round(x, 6), round(y, 6)]

    def region_at(self, x, y):
        for r in reversed(self.host.project.regions):
            if point_in_polygon(x, y, r.points):
                return r
        return None

    # -- mouse -----------------------------------------------------------
    def mousePressEvent(self, e):
        px, py = e.position().x(), e.position().y()
        if e.button() == Qt.MiddleButton or (e.button() == Qt.LeftButton and self.mode == "pan"):
            self.pan_from = (px, py)
            self.setCursor(Qt.ClosedHandCursor)
            return
        if e.button() == Qt.RightButton:
            self.finish()
            return
        if e.button() != Qt.LeftButton:
            return
        h = self.host
        if h.view_mode == "results":
            h.show_result_info(*self.view.world(px, py))
            return
        w = self.snap(px, py)
        if self.mode == "select":
            hits = []
            for r in h.project.regions:
                for i, (x, y) in enumerate(r.points):
                    d = self.view.dev(x, y)
                    if math.hypot(d.x() - px, d.y() - py) < 7:
                        hits.append((r, i))
            if hits:
                h.before_change()
                self.drag = hits
                return
            r = self.region_at(*self.view.world(px, py))
            self.selected_region = r.id if r else None
            h.region_selected(r)
            self.update()
        elif self.mode == "region":
            if len(self.temp) >= 3 and w == self.temp[0]:
                self.finish()
            elif not self.temp or w != self.temp[-1]:
                self.temp.append(w)
        elif self.mode in ("piezo", "bc", "flux_section"):
            if not self.temp or w != self.temp[-1]:
                self.temp.append(w)
        elif self.mode == "reinforcement":
            if not self.temp or w != self.temp[-1]:
                self.temp.append(w)
            if len(self.temp) == 2:
                (x1, y1), (x2, y2) = self.temp
                self.temp = []
                h.add_reinforcement(x1, y1, x2, y2)
        elif self.mode == "assign":
            r = self.region_at(*self.view.world(px, py))
            if r and h.current_material_id is not None:
                h.before_change()
                r.material_id = h.current_material_id
                h.after_change("Assign material")
        elif self.mode == "point_load":
            h.before_change()
            fy, fx = h.load_params()
            h.project.point_loads.append(PointLoad(x=w[0], fy=fy, fx=fx))
            h.after_change("Add point load")
        elif self.mode == "surcharge":
            self.temp.append(w)
            if len(self.temp) == 2:
                h.before_change()
                q = h.surcharge_value()
                h.project.surcharges.append(Surcharge(self.temp[0][0], self.temp[1][0], q))
                self.temp = []
                h.after_change("Add surcharge")
        elif self.mode == "entry_exit":
            self.temp.append(w)
            if len(self.temp) == 4:
                a = h.current_analysis()
                if a and a.kind == "slope":
                    h.before_change()
                    s = a.search
                    s.mode = "entry_exit"
                    s.entry_x1, s.entry_x2 = sorted((self.temp[0][0], self.temp[1][0]))
                    s.exit_x1, s.exit_x2 = sorted((self.temp[2][0], self.temp[3][0]))
                    h.after_change("Set entry and exit")
                self.temp = []
        elif self.mode == "grid":
            self.temp.append(w)
            if len(self.temp) == 2:
                a = h.current_analysis()
                if a and a.kind == "slope":
                    h.before_change()
                    s = a.search
                    s.mode = "grid_radius"
                    s.grid_x1, s.grid_x2 = sorted((self.temp[0][0], self.temp[1][0]))
                    s.grid_y1, s.grid_y2 = sorted((self.temp[0][1], self.temp[1][1]))
                    h.after_change("Set slip grid")
                self.temp = []
        elif self.mode == "text":
            h.add_text(*w)
        self.update()

    def mouseMoveEvent(self, e):
        px, py = e.position().x(), e.position().y()
        if self.pan_from:
            self.view.pan(px - self.pan_from[0], py - self.pan_from[1])
            self.pan_from = (px, py)
            self.update()
            return
        w = self.snap(px, py) if self.mode not in ("select", "pan") else list(self.view.world(px, py))
        self.cursor_w = w
        self.coords.emit(*w)
        if self.drag:
            x, y = self.view.world(px, py)
            if self.host.opts.get("snap", True):
                s = self.host.project.grid_spacing
                x, y = round(round(x / s) * s, 6), round(round(y / s) * s, 6)
            for r, i in self.drag:
                r.points[i] = [x, y]
        self.update()

    def mouseReleaseEvent(self, e):
        if self.pan_from:
            self.pan_from = None
            cursors = {"pan": Qt.OpenHandCursor, "select": Qt.ArrowCursor}
            self.setCursor(cursors.get(self.mode, Qt.CrossCursor))
            return
        if self.drag:
            self.drag = None
            self.host.after_change("Move point")

    def wheelEvent(self, e):
        f = 1.15 if e.angleDelta().y() > 0 else 1 / 1.15
        self.view.zoom(f, e.position().x(), e.position().y())
        self.update()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.finish()
        elif e.key() == Qt.Key_Escape:
            self.temp = []
            self.update()
        elif e.key() == Qt.Key_Delete and self.mode == "select" and self.selected_region is not None:
            self.host.delete_region(self.selected_region)
            self.selected_region = None
        else:
            super().keyPressEvent(e)

    def finish(self):
        h = self.host
        pts = self.temp
        self.temp = []
        if self.mode == "region" and len(pts) >= 3:
            h.add_region(pts)
        elif self.mode == "piezo" and len(pts) >= 2:
            h.before_change()
            h.project.piezometric_line = sorted(pts)
            for a in h.project.analyses:
                if a.kind == "slope" and a.pwp == "none":
                    a.pwp = "piezometric"
            h.after_change("Draw piezometric line")
        elif self.mode == "bc" and len(pts) >= 2:
            h.add_bc(pts)
        elif self.mode == "flux_section" and len(pts) >= 2:
            h.add_flux_section(pts)
        self.update()
