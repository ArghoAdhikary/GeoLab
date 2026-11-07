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

BC_COLORS = {"head": "#1f5fd1", "pressure_head": "#14a3b8", "flux": "#2e9d3a", "seepage_face": "#e07b00",
             "nodal_flux": "#2e9d3a", "infiltration": "#2aa198", "free_drainage": "#6c71c4", "climate": "#0a8f3c",
             "fixed_x": "#555555", "fixed_y": "#555555", "fixed_xy": "#222222", "pressure": "#b0306a",
             "shear": "#b0306a", "force_x": "#b0306a", "force_y": "#b0306a", "displacement_y": "#d33682",
             "temperature": "#d1401f", "heat_flux": "#e07b00", "convective": "#cb4b16",
             "concentration": "#6b0080", "mass_flux": "#8e44ad", "free_exit": "#9b59b6",
             "air_pressure": "#268bd2", "air_flux": "#2aa198"}

# contour fields per result type: key -> (label, unit key, per element)
FIELDS = {
    "seepage": {"head": ("Total head", "length", False), "pressure_head": ("Pressure head", "length", False),
                "pore_pressure": ("Pore-water pressure", "pressure", False),
                "water_content": ("Volumetric water content", "", False)},
    "stress": {"sy": ("Vertical total stress", "pressure", False), "sx": ("Horizontal total stress", "pressure", False),
               "txy": ("Shear stress", "pressure", False), "sy_eff": ("Vertical effective stress", "pressure", False),
               "sx_eff": ("Horizontal effective stress", "pressure", False),
               "pwp": ("Pore-water pressure", "pressure", False),
               "s1": ("Major principal stress", "pressure", False), "s3": ("Minor principal stress", "pressure", False),
               "q": ("Deviatoric stress", "pressure", False), "displacement": ("Displacement", "length", False),
               "dx": ("x-displacement", "length", False), "dy": ("y-displacement", "length", False),
               "excess_pwp": ("Excess pore pressure", "pressure", False)},
    "dynamic": {"max_acceleration": ("Peak horizontal acceleration (g)", "", False),
                "max_displacement": ("Peak relative displacement", "length", False),
                "G_ratio": ("G / Gmax", "", True), "damping": ("Damping ratio", "", True),
                "max_shear_strain": ("Peak shear strain", "", True)},
    "thermal": {"temperature": ("Temperature", "temperature", False),
                "frozen_fraction": ("Frozen fraction", "", False)},
    "transport": {"concentration": ("Concentration", "concentration", False)},
    "air": {"air_pressure": ("Air pressure", "pressure", False)},
}
HISTORY = {("thermal", "temperature"): "temperature_history",
           ("transport", "concentration"): "concentration_history", ("air", "air_pressure"): "pressure_history",
           ("stress", "excess_pwp"): "excess_history"}
VECTORS = {"seepage": ("vx", "vy"), "thermal": ("qx", "qy"), "air": ("vx", "vy")}


def default_field(res):
    return next(iter(FIELDS[res["type"]]))


def available_fields(res):
    """Contour fields present in a result dict: [(key, label)]."""
    if not res or res.get("type") not in FIELDS:
        return []
    return [(k, spec[0]) for k, spec in FIELDS[res["type"]].items() if k == "displacement" and "dx" in res or k in res]


def result_times(res):
    """Saved times of a transient result (empty for steady)."""
    return list(res.get("times") or []) if res else []
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
                  "screen": True, "dark": False}
        if opts:
            self.o.update(opts)
        self.fs = 1.0 if self.o["screen"] else 0.6   # font scale for print
        from .theme import CANVAS
        if self.o["screen"]:                         # night colours and the user's colours on screen only
            from .appearance import canvas_colors
            self.c = canvas_colors(bool(self.o["dark"]))
        else:
            self.c = CANVAS[False]

    # -- helpers ---------------------------------------------------------
    def pen(self, color, w=1.0, style=Qt.SolidLine):
        p = QPen(QColor(color), w)
        p.setStyle(style)
        p.setCosmetic(True)
        return p

    def font(self, size, bold=False):
        f = QFont("Segoe UI")
        if self.o["screen"]:
            from .appearance import font as user_font
            uf = user_font("canvas")
            if uf is not None:
                f.setFamily(uf.family())
        f.setPointSizeF(size * self.fs)
        f.setBold(bold)
        return f

    def poly(self, pts) -> QPolygonF:
        return QPolygonF([self.v.dev(x, y) for x, y in pts])

    # -- main entry ------------------------------------------------------
    def draw(self):
        g = self.g
        g.setRenderHint(QPainter.Antialiasing, True)
        g.fillRect(self.v.rect, QColor(self.c["background"]))
        if self.o["grid"]:
            self.draw_grid()
        res = self.a.results if self.a else None
        field_res = res if (res and res.get("type") in FIELDS) else None
        if self.mode == "results" and field_res:
            self.draw_regions(fill=False)
            self.draw_field(field_res)
        else:
            self.draw_regions(fill=True)
        if self.o["axes"]:
            self.draw_axes()
        self.draw_water_and_loads()
        if self.mode == "define" or (self.a is not None and self.a.kind != "slope"):
            self.draw_bcs()
        self.draw_reinforcement()
        self.draw_structures(res if self.mode == "results" and res and res.get("type") == "stress" else None)
        self.draw_flux_sections(field_res if self.mode == "results" else None)
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
        g.setPen(self.pen(self.c["grid"], 1.5))
        xs = np.arange(math.floor(x0 / step) * step, x1 + step, step)
        ys = np.arange(math.floor(y0 / step) * step, y1 + step, step)
        for x in xs:
            for y in ys:
                g.drawPoint(v.dev(x, y))

    def draw_regions(self, fill=True):
        g = self.g
        off = set(getattr(self.a, "inactive_regions", None) or []) if self.a is not None and self.a.kind == "stress" else set()
        for r in self.p.regions:
            if len(r.points) < 2:
                continue
            m = self.p.material(r.material_id)
            col = QColor(m.color) if m else QColor("#ffffff")
            if not fill:
                col.setAlpha(0)
            if r.id in off:
                g.setBrush(QBrush(QColor(self.c["outline"]), Qt.BDiagPattern))
                g.setPen(self.pen(self.c["outline"], 1.0, Qt.DashLine))
                g.drawPolygon(self.poly(r.points))
                if self.o["labels"] and abs(polygon_area(r.points)) * self.v.s ** 2 > 600:
                    cx = sum(p[0] for p in r.points) / len(r.points)
                    cy = sum(p[1] for p in r.points) / len(r.points)
                    g.setPen(QColor(self.c["text"]))
                    g.setFont(self.font(9))
                    d = self.v.dev(cx, cy)
                    g.drawText(QRectF(d.x() - 90, d.y() - 10, 180, 20), Qt.AlignCenter, "not in this stage")
                continue
            g.setBrush(QBrush(col))
            sel = self.o["selected_region"] == r.id
            g.setPen(self.pen("#d01f1f" if sel else self.c["outline"], 2.2 if sel else 1.2))
            g.drawPolygon(self.poly(r.points))
            if self.mode == "define" and self.o["screen"]:
                g.setBrush(QColor(self.c["outline"]))
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
        g.setPen(self.pen(self.c["axis"], 1))
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
        elif st.mode in ("grid_radius", "grid_tangent") and st.grid_x1 != st.grid_x2:
            g.setPen(self.pen("#d01f1f", 1.2, Qt.DashLine))
            g.setBrush(Qt.NoBrush)
            a, b = v.dev(st.grid_x1, st.grid_y1), v.dev(st.grid_x2, st.grid_y2)
            g.drawRect(QRectF(a, b).normalized())
            g.setPen(self.pen("#d01f1f", 3))
            for x in np.linspace(st.grid_x1, st.grid_x2, max(1, st.grid_nx)):
                for y in np.linspace(st.grid_y1, st.grid_y2, max(1, st.grid_ny)):
                    g.drawPoint(v.dev(x, y))
            if st.mode == "grid_tangent":
                x0, _, x1, _ = project_bounds(self.p)
                g.setPen(self.pen("#d01f1f", 1, Qt.DotLine))
                for y in np.linspace(st.tangent_y1, st.tangent_y2, max(1, st.n_tangent)):
                    g.drawLine(v.dev(x0, y), v.dev(x1, y))
        elif st.mode == "block":
            g.setBrush(Qt.NoBrush)
            for rect, label in ((st.block_left, "Left block"), (st.block_right, "Right block")):
                if rect[0] == rect[2] and rect[1] == rect[3]:
                    continue
                a, b = v.dev(rect[0], rect[1]), v.dev(rect[2], rect[3])
                g.setPen(self.pen("#d01f1f", 1.2, Qt.DashLine))
                g.drawRect(QRectF(a, b).normalized())
                g.setPen(self.pen("#d01f1f", 3))
                for x in np.linspace(rect[0], rect[2], max(1, st.block_n)):
                    for y in np.linspace(rect[1], rect[3], max(1, st.block_n)):
                        g.drawPoint(v.dev(x, y))
                g.setFont(self.font(8, True))
                g.drawText(QRectF(a, b).normalized().topLeft() + QPointF(0, -4), label)
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
        dd = res.get("drawdown")
        if dd and len(dd.get("line_after", [])) >= 2:
            g.setPen(self.pen("#5aa9ff", 1.6, Qt.DashDotLine))
            g.drawPolyline(self.poly(dd["line_after"]))
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
        g.setPen(QColor(self.c["axis"] if self.c["background"] != "#ffffff" else "#111111"))
        g.drawText(QRectF(anchor.x() - 80, anchor.y() - 40, 160, 32), Qt.AlignCenter, f"{crit['fos']:.3f}")

    def draw_message(self, text):
        self.g.setPen(QColor("#ff7070" if self.c["background"] != "#ffffff" else "#a00000"))
        self.g.setFont(self.font(11, True))
        r = self.v.rect
        self.g.drawText(QRectF(r.left(), r.top() + 10, r.width(), 30), Qt.AlignCenter, text)

    def field_values(self, res):
        """(values, per_element, label, unit) of the selected contour field and time step."""
        spec = FIELDS[res["type"]]
        key = self.o.get("contour")
        if key not in spec or (key != "displacement" and key not in res):
            key = default_field(res)
        label, unit_key, per_elem = spec[key]
        idx = self.o.get("time_index")
        y = np.asarray(res["nodes"], float)[:, 1]
        heads = res.get("head_history") if res["type"] == "seepage" else None
        if key == "displacement":
            vals = np.hypot(res["dx"], res["dy"])
        elif heads and idx is not None and 0 <= idx < len(heads) and key in ("head", "pressure_head", "pore_pressure"):
            h = np.asarray(heads[idx], float)
            vals = {"head": h, "pressure_head": h - y, "pore_pressure": (h - y) * self.p.gamma_w}[key]
        else:
            hist = res.get(HISTORY.get((res["type"], key), ""))
            if hist and idx is not None and 0 <= idx < len(hist):
                vals = np.asarray(hist[idx], float)
            else:
                vals = np.asarray(res[key], float)
        return vals, per_elem, label, (self.p.unit(unit_key) if unit_key else "")

    def draw_field(self, res):
        g, v = self.g, self.v
        nodes = np.asarray(res["nodes"], float)
        tris = np.asarray(res["tris"], int)
        field, per_elem, label, unit = self.field_values(res)
        if res["type"] == "stress" and self.o.get("deformed"):
            disp = np.column_stack([res["dx"], res["dy"]])
            dmax = float(np.abs(disp).max())
            if dmax > 0:
                x0, y0, x1, y1 = project_bounds(self.p)
                nodes = nodes + disp * (0.06 * max(x1 - x0, y1 - y0) / dmax) * self.o.get("exaggeration", 1.0)
        finite = field[np.isfinite(field)]
        lo, hi = (float(finite.min()), float(finite.max())) if len(finite) else (0.0, 1.0)
        span = hi - lo if hi > lo else 1.0
        dev = [v.dev(x, y) for x, y in nodes]
        g.setPen(self.pen(QColor(0, 0, 0, 70), 0.6) if self.o["mesh"] else Qt.NoPen)
        vals = field if per_elem else field[tris].mean(axis=1)
        inactive = res.get("inactive") or [False] * len(tris)
        for t, val, off in zip(tris, vals, inactive):
            if off:
                continue
            g.setBrush(colormap((val - lo) / span) if np.isfinite(val) else QColor("#dddddd"))
            g.drawPolygon(QPolygonF([dev[t[0]], dev[t[1]], dev[t[2]]]))
        if not per_elem and hi > lo:
            from ..seep import contour_segments
            g.setPen(self.pen(QColor(30, 30, 30, 140), 0.8))
            step = nice_step(span, 10)
            level = math.ceil(lo / step) * step
            while level < hi:
                for x1, y1, x2, y2 in contour_segments(nodes, tris, field, level):
                    g.drawLine(v.dev(x1, y1), v.dev(x2, y2))
                level += step
        if res["type"] == "seepage":
            from ..seep import phreatic_segments
            idx = self.o.get("time_index")
            heads = res.get("head_history")
            if heads and idx is not None and 0 <= idx < len(heads):
                ph = phreatic_segments(nodes, tris, np.asarray(heads[idx]) - nodes[:, 1])
            else:
                ph = res["phreatic"]
            g.setPen(self.pen(WATER, 2.6))
            for x1, y1, x2, y2 in ph:
                g.drawLine(v.dev(x1, y1), v.dev(x2, y2))
        if res["type"] == "stress" and self.o.get("yield", True) and any(res.get("yielded", [])):
            g.setPen(Qt.NoPen)
            g.setBrush(QColor(220, 0, 160, 120))
            for t, yl in zip(tris, res["yielded"]):
                if yl:
                    g.drawPolygon(QPolygonF([dev[t[0]], dev[t[1]], dev[t[2]]]))
        vec = VECTORS.get(res["type"])
        if self.o["vectors"] and vec and res.get(vec[0]):
            vx, vy = np.asarray(res[vec[0]]), np.asarray(res[vec[1]])
            mag = np.hypot(vx, vy)
            vmax = mag.max() if mag.size and mag.max() > 0 else 1
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
        if res["type"] == "transport":
            for prt in res.get("particles", []):
                g.setPen(self.pen("#6b0080", 1.8))
                g.drawPolyline(self.poly(prt["path"]))
                g.setBrush(QColor("#6b0080"))
                g.drawEllipse(v.dev(*prt["start"]), 3, 3)
        self.draw_colorbar(lo, hi, label, unit)

    def draw_reinforcement(self):
        g = self.g
        for r in getattr(self.p, "reinforcements", []):
            a, b = self.v.dev(r.x1, r.y1), self.v.dev(r.x2, r.y2)
            g.setPen(self.pen("#7a4b00", 2.6))
            g.drawLine(a, b)
            if r.type == "anchor" and r.bond_length > 0:
                L = math.hypot(r.x2 - r.x1, r.y2 - r.y1)
                if L > 0:
                    t = max(0.0, 1 - r.bond_length / L)
                    c = self.v.dev(r.x1 + t * (r.x2 - r.x1), r.y1 + t * (r.y2 - r.y1))
                    g.setPen(self.pen("#7a4b00", 6))
                    g.drawLine(c, b)
            g.setBrush(QColor("#7a4b00"))
            g.setPen(self.pen("#7a4b00", 1))
            g.drawRect(QRectF(a.x() - 3, a.y() - 3, 6, 6))

    def draw_structures(self, res):
        """Walls, anchors and geogrids; in the results, their largest axial force and bending moment."""
        g = self.g
        aid = getattr(self.a, "id", None)
        colors = {"beam": "#2d3a8c", "anchor": "#a23b1f", "geogrid": "#1f7a4d"}
        forces = {s["id"]: s for s in (res or {}).get("structures", []) or []}
        for st in getattr(self.p, "structures", []) or []:
            if len(st.points) < 2:
                continue
            present = not st.analyses or aid in st.analyses
            col = QColor(colors.get(st.type, "#333333"))
            if not present:
                col.setAlpha(70)
            width = 3.6 if st.type == "beam" else 2.4
            style = Qt.DashLine if st.type == "geogrid" else Qt.SolidLine
            g.setPen(self.pen(col, width, style))
            g.drawPolyline(self.poly(st.points))
            if st.type == "anchor":
                g.setBrush(col)
                d = self.v.dev(*st.points[0])
                g.drawRect(QRectF(d.x() - 3.5, d.y() - 3.5, 7, 7))
            if self.o["labels"]:
                g.setFont(self.font(8, True))
                d = self.v.dev(*st.points[-1])
                txt = st.name
                f = forces.get(st.id)
                if f:
                    u = self.p.unit("force")
                    txt += f": N = {f['max_N']:.3g} {u}/{self.p.unit('length')}"
                    if st.type == "beam":
                        txt += f", M = {f['max_M']:.3g} {u}.{self.p.unit('length')}/{self.p.unit('length')}"
                elif not present:
                    txt += " (not in this stage)"
                g.setPen(col)
                g.drawText(QPointF(d.x() + 5, d.y() + 12), txt)

    def draw_flux_sections(self, res):
        g = self.g
        values = (res or {}).get("flux_sections", {})
        for f in getattr(self.p, "flux_sections", []):
            if len(f.points) < 2:
                continue
            g.setPen(self.pen("#00897b", 2, Qt.DashDotLine))
            g.drawPolyline(self.poly(f.points))
            if self.o["labels"]:
                g.setFont(self.font(8, True))
                d = self.v.dev(*f.points[-1])
                txt = f.name if f.name not in values else f"{f.name}: {values[f.name]:.3g} {self.p.unit('flux')}"
                g.drawText(QPointF(d.x() + 4, d.y() - 4), txt)

    def draw_colorbar(self, lo, hi, label, unit=""):
        g = self.g
        r = self.v.rect
        x, y, w, h = r.right() - 46, r.top() + 30, 14, min(220.0, r.height() * 0.5)
        for i in range(int(h)):
            g.setPen(colormap(1 - i / h))
            g.drawLine(QPointF(x, y + i), QPointF(x + w, y + i))
        g.setPen(self.pen(self.c["axis"], 1))
        g.setBrush(Qt.NoBrush)
        g.drawRect(QRectF(x, y, w, h))
        g.setFont(self.font(8))
        g.drawText(QRectF(x - 200, y - 22, 240, 16), Qt.AlignRight, f"{label} ({unit})" if unit else label)
        for k in range(5):
            val = hi - k * (hi - lo) / 4
            g.drawText(QRectF(x - 80, y + k * h / 4 - 7, 76, 14), Qt.AlignRight | Qt.AlignVCenter, f"{val:.4g}")

    def draw_sketch(self):
        g = self.g
        g.setPen(QColor(self.c["axis"]))
        for t in self.p.sketch_texts:
            g.setFont(self.font(t.size))
            g.drawText(self.v.dev(t.x, t.y), t.text)
