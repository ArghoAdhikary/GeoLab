"""Painter-agnostic drawing of a project and its results.

The same code draws the on-screen canvas, PNG exports and PDF pages, so the
printed output always matches what the user sees.
"""
from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF

from ..geometry import GroundProfile, bounds, polygon_area

BC_COLORS = {"head": "#1f5fd1", "pressure_head": "#14a3b8", "flux": "#2e9d3a", "seepage_face": "#e07b00"}
WATER = QColor("#2f6fe0")


class View:
    """World <-> device transform with equal x/y scale and y pointing up."""

    def __init__(self):
        self.cx, self.cy, self.s = 0.0, 0.0, 10.0
        self.rect = QRectF(0, 0, 800, 600)

    def fit(self, b, rect: QRectF, margin=0.08):
        x0, y0, x1, y1 = b
        w, h = max(x1 - x0, 1e-6), max(y1 - y0, 1e-6)
        self.rect = QRectF(rect)
        self.cx, self.cy = 0.5 * (x0 + x1), 0.5 * (y0 + y1)
        self.s = min(rect.width() * (1 - 2 * margin) / w, rect.height() * (1 - 2 * margin) / h)

    def dev(self, x, y) -> QPointF:
        c = self.rect.center()
        return QPointF(c.x() + (x - self.cx) * self.s, c.y() - (y - self.cy) * self.s)

    def world(self, px, py):
        c = self.rect.center()
        return (self.cx + (px - c.x()) / self.s, self.cy - (py - c.y()) / self.s)

    def zoom(self, factor, px=None, py=None):
        if px is not None:
            wx, wy = self.world(px, py)
        self.s *= factor
        if px is not None:
            nx, ny = self.world(px, py)
            self.cx += wx - nx
            self.cy += wy - ny

    def pan(self, dpx, dpy):
        self.cx -= dpx / self.s
        self.cy += dpy / self.s


def colormap(t: float) -> QColor:
    """Blue -> cyan -> green -> yellow -> red."""
    t = min(1.0, max(0.0, t))
    stops = [(0.0, (45, 85, 200)), (0.25, (40, 170, 220)), (0.5, (80, 190, 90)), (0.75, (240, 210, 50)), (1.0, (215, 50, 40))]
    for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
        if t <= t1:
            u = (t - t0) / (t1 - t0)
            return QColor(*[int(a + u * (b - a)) for a, b in zip(c0, c1)])
    return QColor(*stops[-1][1])


def nice_step(span, target=8):
    raw = span / max(target, 1)
    mag = 10 ** math.floor(math.log10(raw)) if raw > 0 else 1
    for m in (1, 2, 5, 10):
        if raw <= m * mag:
            return m * mag
    return 10 * mag


def project_bounds(project):
    b = bounds(project.regions)
    if not project.regions:
        pts = [p for bc in project.boundary_conditions for p in bc.points] + project.piezometric_line
        if pts:
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            return (min(xs), min(ys), max(xs), max(ys))
        return (0, 0, 50, 30)
    return b


class Renderer:
    def __init__(self, project, analysis, view: View, painter: QPainter, *, mode="define", opts=None):
        self.p = project
        self.a = analysis
        self.v = view
        self.g = painter
        self.mode = mode
        self.o = {"grid": False, "axes": True, "slices": True, "trials": True, "mesh": False,
                  "vectors": True, "labels": True, "contour": "head", "selected_region": None,
                  "screen": True}
        if opts:
            self.o.update(opts)
        self.fs = 1.0 if self.o["screen"] else 0.6   # font scale for print

    # -- helpers ---------------------------------------------------------
    def pen(self, color, w=1.0, style=Qt.SolidLine):
        p = QPen(QColor(color), w)
        p.setStyle(style)
        p.setCosmetic(True)
        return p

    def font(self, size, bold=False):
        f = QFont("Segoe UI")
        f.setPointSizeF(size * self.fs)
        f.setBold(bold)
        return f

    def poly(self, pts) -> QPolygonF:
        return QPolygonF([self.v.dev(x, y) for x, y in pts])

    # -- main entry ------------------------------------------------------
    def draw(self):
        g = self.g
        g.setRenderHint(QPainter.Antialiasing, True)
        g.fillRect(self.v.rect, QColor("white"))
        if self.o["grid"]:
            self.draw_grid()
        res = self.a.results if self.a else None
        seep_res = res if (res and res.get("type") == "seepage") else None
        if self.mode == "results" and seep_res:
            self.draw_regions(fill=False)
            self.draw_seepage(seep_res)
        else:
            self.draw_regions(fill=True)
        if self.o["axes"]:
            self.draw_axes()
        self.draw_water_and_loads()
        if self.a is None or self.a.kind == "seepage" or self.mode == "define":
            self.draw_bcs()
        if self.a and self.a.kind == "slope":
            if self.mode == "results" and res and res.get("type") == "slope":
                self.draw_slope_results(res)
            else:
                self.draw_search()
        self.draw_sketch()

    def draw_grid(self):
        g, v = self.g, self.v
        r = v.rect
        x0, y1 = v.world(r.left(), r.top())
        x1, y0 = v.world(r.right(), r.bottom())
        step = self.o.get("grid_spacing", 1.0)
        while step * v.s < 8:
            step *= 2
        g.setPen(self.pen("#c9cfd8", 1.5))
        xs = np.arange(math.floor(x0 / step) * step, x1 + step, step)
        ys = np.arange(math.floor(y0 / step) * step, y1 + step, step)
        for x in xs:
            for y in ys:
                g.drawPoint(v.dev(x, y))

    def draw_regions(self, fill=True):
        g = self.g
        for r in self.p.regions:
            if len(r.points) < 2:
                continue
            m = self.p.material(r.material_id)
            col = QColor(m.color) if m else QColor("#ffffff")
            if not fill:
                col.setAlpha(0)
            g.setBrush(QBrush(col))
            sel = self.o["selected_region"] == r.id
            g.setPen(self.pen("#d01f1f" if sel else "#202020", 2.2 if sel else 1.2))
            g.drawPolygon(self.poly(r.points))
            if self.mode == "define" and self.o["screen"]:
                g.setBrush(QColor("#202020"))
                for x, y in r.points:
                    d = self.v.dev(x, y)
                    g.drawRect(QRectF(d.x() - 2.5, d.y() - 2.5, 5, 5))
            if self.o["labels"] and m and fill and abs(polygon_area(r.points)) * self.v.s ** 2 > 600:
                cx = sum(p[0] for p in r.points) / len(r.points)
                cy = sum(p[1] for p in r.points) / len(r.points)
                g.setPen(QColor("#303030"))
                g.setFont(self.font(9))
                d = self.v.dev(cx, cy)
                g.drawText(QRectF(d.x() - 80, d.y() - 10, 160, 20), Qt.AlignCenter, m.name)

    def draw_axes(self):
        if not self.p.regions:
            return
        g, v = self.g, self.v
        x0, y0, x1, y1 = project_bounds(self.p)
        g.setPen(self.pen("#404040", 1))
        g.setFont(self.font(8))
        step = nice_step(x1 - x0)
        off = 18 / v.s if self.o["screen"] else 14 / v.s
        base = v.dev(x0, y0 - off)
        g.drawLine(base, v.dev(x1, y0 - off))
        x = math.ceil(x0 / step) * step
        while x <= x1 + 1e-9:
            d = v.dev(x, y0 - off)
            g.drawLine(d, QPointF(d.x(), d.y() + 4))
            g.drawText(QRectF(d.x() - 30, d.y() + 4, 60, 14), Qt.AlignHCenter | Qt.AlignTop, f"{x:g}")
            x += step
        step = nice_step(y1 - y0, 5)
        g.drawLine(v.dev(x0 - off, y0), v.dev(x0 - off, y1))
        y = math.ceil(y0 / step) * step
        while y <= y1 + 1e-9:
            d = v.dev(x0 - off, y)
            g.drawLine(d, QPointF(d.x() - 4, d.y()))
            g.drawText(QRectF(d.x() - 50, d.y() - 7, 44, 14), Qt.AlignRight | Qt.AlignVCenter, f"{y:g}")
            y += step
        u = self.p.unit("length")
        d = v.dev(0.5 * (x0 + x1), y0 - off)
        g.drawText(QRectF(d.x() - 60, d.y() + 16, 120, 14), Qt.AlignCenter, f"Distance ({u})")

    def draw_water_and_loads(self):
        g, v = self.g, self.v
        line = self.p.piezometric_line
        show_piezo = (self.a is None or self.a.kind == "slope" and self.a.pwp == "piezometric"
                      or self.mode == "define")
        if len(line) >= 2 and show_piezo:
            g.setPen(self.pen(WATER, 2, Qt.DashLine))
            pts = sorted(line)
            g.drawPolyline(self.poly(pts))
            # water table marker
            mx = pts[len(pts) // 2] if len(pts) > 2 else [0.5 * (pts[0][0] + pts[1][0]), 0.5 * (pts[0][1] + pts[1][1])]
            d = v.dev(*mx)
            tri = QPolygonF([QPointF(d.x() - 6, d.y() - 10), QPointF(d.x() + 6, d.y() - 10), QPointF(d.x(), d.y() - 2)])
            g.setBrush(WATER)
            g.setPen(self.pen(WATER, 1))
            g.drawPolygon(tri)
        if self.p.regions and (self.p.surcharges or self.p.point_loads):
            gp = GroundProfile(self.p.regions, samples=300)
            g.setPen(self.pen("#7a1fa2", 1.4))
            g.setBrush(QColor("#7a1fa2"))
            for s in self.p.surcharges:
                a, b = sorted((s.x1, s.x2))
                n = max(2, int((b - a) * v.s / 18))
                xs = np.linspace(a, b, n)
                tops = []
                for x in xs:
                    yg = float(gp.ground(x))
                    p0 = v.dev(x, yg)
                    p1 = QPointF(p0.x(), p0.y() - 22)
                    self.arrow(p1, p0)
                    tops.append(p1)
                g.drawLine(tops[0], tops[-1])
                g.setFont(self.font(8))
                g.drawText(QRectF(tops[0].x(), tops[0].y() - 16, max(60.0, tops[-1].x() - tops[0].x()), 14),
                           Qt.AlignCenter, f"{s.q:g} {self.p.unit('pressure')}")
            for pl in self.p.point_loads:
                yg = float(gp.ground(pl.x))
                p0 = v.dev(pl.x, yg)
                self.arrow(QPointF(p0.x(), p0.y() - 34), p0)
                g.setFont(self.font(8))
                g.drawText(QRectF(p0.x() - 40, p0.y() - 50, 80, 14), Qt.AlignCenter, f"{pl.fy:g} {self.p.unit('force')}")

    def arrow(self, a: QPointF, b: QPointF, head=6):
        g = self.g
        g.drawLine(a, b)
        ang = math.atan2(b.y() - a.y(), b.x() - a.x())
        p1 = QPointF(b.x() - head * math.cos(ang - 0.4), b.y() - head * math.sin(ang - 0.4))
        p2 = QPointF(b.x() - head * math.cos(ang + 0.4), b.y() - head * math.sin(ang + 0.4))
        g.drawPolygon(QPolygonF([b, p1, p2]))

    def draw_bcs(self):
        g = self.g
        for bc in self.p.boundary_conditions:
            if len(bc.points) < 1:
                continue
            col = BC_COLORS.get(bc.type, "#000")
            g.setPen(self.pen(col, 4))
            if len(bc.points) == 1:
                g.drawPoint(self.v.dev(*bc.points[0]))
            else:
                g.drawPolyline(self.poly(bc.points))
            if self.o["labels"]:
                g.setFont(self.font(8))
                g.setPen(QColor(col))
                d = self.v.dev(*bc.points[0])
                g.drawText(QPointF(d.x() + 5, d.y() - 5), bc.name)

    def draw_search(self):
        if not self.p.regions:
            return
        st = self.a.search
        g, v = self.g, self.v
        if st.mode == "entry_exit" and (st.entry_x1 != st.entry_x2 or st.exit_x1 != st.exit_x2):
            gp = GroundProfile(self.p.regions, samples=400)
            for (x1, x2), label in (((st.entry_x1, st.entry_x2), "Entry"), ((st.exit_x1, st.exit_x2), "Exit")):
                xs = np.linspace(x1, x2, 40)
                pts = [(x, float(gp.ground(x))) for x in xs]
                g.setPen(self.pen("#d01f1f", 5))
                g.drawPolyline(self.poly(pts))
                g.setFont(self.font(9, True))
                g.setPen(QColor("#d01f1f"))
                d = v.dev(*pts[len(pts) // 2])
                g.drawText(QRectF(d.x() - 40, d.y() - 26, 80, 16), Qt.AlignCenter, label)
        elif st.mode == "grid_radius" and st.grid_x1 != st.grid_x2:
            g.setPen(self.pen("#d01f1f", 1.2, Qt.DashLine))
            g.setBrush(Qt.NoBrush)
            a, b = v.dev(st.grid_x1, st.grid_y1), v.dev(st.grid_x2, st.grid_y2)
            g.drawRect(QRectF(a, b).normalized())
            g.setPen(self.pen("#d01f1f", 3))
            for x in np.linspace(st.grid_x1, st.grid_x2, max(1, st.grid_nx)):
                for y in np.linspace(st.grid_y1, st.grid_y2, max(1, st.grid_ny)):
                    g.drawPoint(v.dev(x, y))
        elif st.mode == "fully_specified":
            g.setPen(self.pen("#d01f1f", 1.5, Qt.DashLine))
            g.setBrush(Qt.NoBrush)
            for xc, yc, R in (c[:3] for c in st.circles):
                c = v.dev(xc, yc)
                g.drawEllipse(c, R * v.s, R * v.s)
            for pl in st.polylines:
                g.drawPolyline(self.poly(pl))

    def _surface_pts(self, surface, gp, x_range=None):
        if surface["type"] == "circle":
            xc, yc, R = surface["xc"], surface["yc"], surface["R"]
            lo, hi = x_range if x_range else (xc - R, xc + R)
            xs = np.linspace(lo, hi, 80)
            ys = yc - np.sqrt(np.clip(R * R - (xs - xc) ** 2, 0, None))
            return list(zip(xs, ys))
        return surface["points"]

    def draw_slope_results(self, res):
        g, v = self.g, self.v
        crit = res.get("critical")
        if not crit:
            self.draw_message(res.get("message", "No valid slip surface"))
            return
        gp = GroundProfile(self.p.regions, samples=600)
        from ..slope import find_extent
        if self.o["trials"] and res.get("trials"):
            trials = res["trials"][:120]
            fmin, fmax = trials[0]["fos"], trials[-1]["fos"]
            for t in reversed(trials[1:]):
                ext = find_extent(gp, t["surface"], samples=200)
                if not ext:
                    continue
                u = (t["fos"] - fmin) / (fmax - fmin) if fmax > fmin else 0
                c = colormap(0.35 + 0.65 * u)
                c.setAlpha(110)
                g.setPen(self.pen(c, 1))
                g.drawPolyline(self.poly(self._surface_pts(t["surface"], gp, ext[:2])))
        sx = crit["slice_x"]
        surf = crit["surface"]
        pts = self._surface_pts(surf, gp, (sx[0], sx[-1]))
        top = [(x, float(gp.ground(x))) for x in np.linspace(sx[-1], sx[0], 120)]
        path = QPainterPath()
        path.addPolygon(self.poly(pts + top))
        fill = QColor("#ffd24d")
        fill.setAlpha(120)
        g.fillPath(path, fill)
        if self.o["slices"]:
            g.setPen(self.pen("#5a4a10", 0.8))
            for x in sx[1:-1]:
                if surf["type"] == "circle":
                    yb = surf["yc"] - math.sqrt(max(surf["R"] ** 2 - (x - surf["xc"]) ** 2, 0))
                else:
                    pl = sorted(surf["points"])
                    yb = float(np.interp(x, [p[0] for p in pl], [p[1] for p in pl]))
                g.drawLine(v.dev(x, yb), v.dev(x, float(gp.ground(x))))
        g.setPen(self.pen("#c01010", 2.6))
        g.drawPolyline(self.poly(pts))
        mx = 0.5 * (sx[0] + sx[-1])
        anchor = v.dev(mx, float(gp.ground(mx)))
        if surf["type"] == "circle":
            c = v.dev(surf["xc"], surf["yc"])
            if v.rect.adjusted(-20, -20, 20, 20).contains(c):
                g.setPen(self.pen("#c01010", 1, Qt.DotLine))
                g.drawLine(c, v.dev(*pts[0]))
                g.drawLine(c, v.dev(*pts[-1]))
                g.setBrush(QColor("#c01010"))
                g.drawEllipse(c, 3, 3)
                if c.y() < anchor.y() - 40:
                    anchor = QPointF(c.x(), c.y())
        g.setFont(self.font(18, True))
        g.setPen(QColor("#111111"))
        g.drawText(QRectF(anchor.x() - 80, anchor.y() - 40, 160, 32), Qt.AlignCenter, f"{crit['fos']:.3f}")

    def draw_message(self, text):
        self.g.setPen(QColor("#a00000"))
        self.g.setFont(self.font(11, True))
        r = self.v.rect
        self.g.drawText(QRectF(r.left(), r.top() + 10, r.width(), 30), Qt.AlignCenter, text)

    def draw_seepage(self, res):
        g, v = self.g, self.v
        nodes = np.asarray(res["nodes"])
        tris = np.asarray(res["tris"])
        field = np.asarray(res["head"] if self.o["contour"] == "head" else res["pressure_head"])
        lo, hi = float(field.min()), float(field.max())
        span = hi - lo if hi > lo else 1.0
        dev = [v.dev(x, y) for x, y in nodes]
        if self.o["mesh"]:
            g.setPen(self.pen(QColor(0, 0, 0, 70), 0.6))
        else:
            g.setPen(Qt.NoPen)
        vals = field[tris].mean(axis=1)
        for t, val in zip(tris, vals):
            g.setBrush(colormap((val - lo) / span))
            g.drawPolygon(QPolygonF([dev[t[0]], dev[t[1]], dev[t[2]]]))
        # contour lines
        from ..seep import contour_segments
        g.setPen(self.pen(QColor(30, 30, 30, 140), 0.8))
        step = nice_step(span, 10)
        level = math.ceil(lo / step) * step
        while level < hi:
            for x1, y1, x2, y2 in contour_segments(nodes, tris, field, level):
                g.drawLine(v.dev(x1, y1), v.dev(x2, y2))
            level += step
        g.setPen(self.pen(WATER, 2.6))
        for x1, y1, x2, y2 in res["phreatic"]:
            g.drawLine(v.dev(x1, y1), v.dev(x2, y2))
        if self.o["vectors"]:
            vx, vy = np.asarray(res["vx"]), np.asarray(res["vy"])
            mag = np.hypot(vx, vy)
            vmax = mag.max() if mag.max() > 0 else 1
            cent = nodes[tris].mean(axis=1)
            stride = max(1, len(tris) // 350)
            g.setPen(self.pen("#101010", 1))
            g.setBrush(QColor("#101010"))
            for i in range(0, len(tris), stride):
                if mag[i] < 0.02 * vmax:
                    continue
                L = 6 + 16 * math.sqrt(mag[i] / vmax)
                a = v.dev(*cent[i])
                d = QPointF(vx[i] / mag[i] * L, -vy[i] / mag[i] * L)
                self.arrow(a, a + d, 4)
        self.draw_colorbar(lo, hi, "Total head" if self.o["contour"] == "head" else "Pressure head")

    def draw_colorbar(self, lo, hi, label):
        g = self.g
        r = self.v.rect
        x, y, w, h = r.right() - 46, r.top() + 30, 14, min(220.0, r.height() * 0.5)
        for i in range(int(h)):
            g.setPen(colormap(1 - i / h))
            g.drawLine(QPointF(x, y + i), QPointF(x + w, y + i))
        g.setPen(self.pen("#202020", 1))
        g.setBrush(Qt.NoBrush)
        g.drawRect(QRectF(x, y, w, h))
        g.setFont(self.font(8))
        u = self.p.unit("length")
        g.drawText(QRectF(x - 100, y - 22, 140, 16), Qt.AlignRight, f"{label} ({u})")
        for k in range(5):
            val = hi - k * (hi - lo) / 4
            g.drawText(QRectF(x - 60, y + k * h / 4 - 7, 56, 14), Qt.AlignRight | Qt.AlignVCenter, f"{val:.2f}")

    def draw_sketch(self):
        g = self.g
        g.setPen(QColor("#101010"))
        for t in self.p.sketch_texts:
            g.setFont(self.font(t.size))
            g.drawText(self.v.dev(t.x, t.y), t.text)
