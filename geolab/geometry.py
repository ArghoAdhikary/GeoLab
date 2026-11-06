"""2D geometry helpers used by the editor and the solvers."""
from __future__ import annotations

import math

import numpy as np


def polygon_area(pts) -> float:
    """Signed area (positive when counter-clockwise)."""
    a = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        a += x1 * y2 - x2 * y1
    return 0.5 * a


def point_in_polygon(x: float, y: float, pts) -> bool:
    inside = False
    n = len(pts)
    j = n - 1
    for i in range(n):
        xi, yi = pts[i]
        xj, yj = pts[j]
        if (yi > y) != (yj > y):
            xint = xi + (y - yi) * (xj - xi) / (yj - yi)
            if x < xint:
                inside = not inside
        j = i
    return inside


def vertical_intervals(pts, x: float) -> list[tuple[float, float]]:
    """Intervals (y_low, y_high) where the vertical line at x lies inside the polygon."""
    ys = []
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        if x1 == x2:
            continue
        if (x1 <= x < x2) or (x2 <= x < x1):
            t = (x - x1) / (x2 - x1)
            ys.append(y1 + t * (y2 - y1))
    ys.sort()
    return [(ys[i], ys[i + 1]) for i in range(0, len(ys) - 1, 2)]


def bounds(regions) -> tuple[float, float, float, float]:
    xs = [p[0] for r in regions for p in r.points]
    ys = [p[1] for r in regions for p in r.points]
    if not xs:
        return (0.0, 0.0, 10.0, 10.0)
    return (min(xs), min(ys), max(xs), max(ys))


class GroundProfile:
    """Upper (ground) and lower envelopes of all regions, sampled for fast lookup."""

    def __init__(self, regions, samples: int = 2000):
        self.regions = regions
        xmin, ymin, xmax, ymax = bounds(regions)
        self.xmin, self.xmax = xmin, xmax
        self.ymin, self.ymax = ymin, ymax
        # exact breakpoints plus uniform samples so linear interpolation is exact at vertices
        xs = set(np.linspace(xmin, xmax, samples).tolist())
        for r in regions:
            for p in r.points:
                xs.add(p[0])
        xs = np.array(sorted(xs))
        top = np.full(len(xs), np.nan)
        bot = np.full(len(xs), np.nan)
        eps = 1e-9 * max(1.0, xmax - xmin)
        for i, x in enumerate(xs):
            xq = min(max(x, xmin + eps), xmax - eps)
            hi, lo = -math.inf, math.inf
            for r in regions:
                for a, b in vertical_intervals(r.points, xq):
                    hi = max(hi, b)
                    lo = min(lo, a)
            if hi > -math.inf:
                top[i], bot[i] = hi, lo
        ok = ~np.isnan(top)
        self.xs, self.top, self.bot = xs[ok], top[ok], bot[ok]

    def ground(self, x):
        return np.interp(x, self.xs, self.top)

    def bottom(self, x):
        return np.interp(x, self.xs, self.bot)

    def contains_x(self, x) -> bool:
        return self.xmin <= x <= self.xmax


def polyline_y(points, x):
    """Interpolate a polyline y(x); flat extrapolation beyond the ends."""
    if not points:
        return None
    pts = sorted(points, key=lambda p: p[0])
    xs = np.array([p[0] for p in pts])
    ys = np.array([p[1] for p in pts])
    return np.interp(x, xs, ys)


def dist_point_segment(px, py, x1, y1, x2, y2) -> float:
    dx, dy = x2 - x1, y2 - y1
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / L2))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def dist_point_polyline(px, py, pts) -> float:
    if len(pts) == 1:
        return math.hypot(px - pts[0][0], py - pts[0][1])
    return min(dist_point_segment(px, py, *pts[i], *pts[i + 1]) for i in range(len(pts) - 1))


def segments_intersect(p1, p2, p3, p4) -> bool:
    """Proper intersection of segments p1p2 and p3p4 (touching endpoints does not count)."""
    def orient(a, b, c):
        v = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        return 0 if abs(v) < 1e-12 else (1 if v > 0 else -1)
    o1, o2 = orient(p1, p2, p3), orient(p1, p2, p4)
    o3, o4 = orient(p3, p4, p1), orient(p3, p4, p2)
    return o1 * o2 < 0 and o3 * o4 < 0


def is_simple_polygon(pts) -> bool:
    n = len(pts)
    if n < 3:
        return False
    for i in range(n):
        a1, a2 = pts[i], pts[(i + 1) % n]
        for j in range(i + 1, n):
            if abs(i - j) <= 1 or (i == 0 and j == n - 1):
                continue
            if segments_intersect(a1, a2, pts[j], pts[(j + 1) % n]):
                return False
    return True


def validate_geometry(project) -> list[str]:
    """Return a list of human-readable problems (empty when the geometry is usable)."""
    problems = []
    if not project.regions:
        problems.append("No regions are defined. Draw at least one region.")
    for r in project.regions:
        if len(r.points) < 3:
            problems.append(f"Region {r.id} has fewer than 3 points.")
            continue
        if abs(polygon_area(r.points)) < 1e-9:
            problems.append(f"Region {r.id} has zero area.")
        if not is_simple_polygon(r.points):
            problems.append(f"Region {r.id} edges cross each other.")
        if project.material(r.material_id) is None:
            problems.append(f"Region {r.id} has no material assigned.")
    return problems


def auto_entry_exit(project):
    """Pick sensible entry/exit ranges from the ground profile. Returns (entry, exit) x-ranges."""
    gp = GroundProfile(project.regions, samples=400)
    xs, ys = gp.xs, gp.top
    ytop, ybot = ys.max(), ys.min()
    H = max(ytop - ybot, 1e-6)
    lo_mask = ys <= ybot + 0.1 * H
    hi_mask = ys >= ytop - 0.1 * H
    x_lo, x_hi = xs[lo_mask], xs[hi_mask]
    span = gp.xmax - gp.xmin
    if x_lo.mean() < x_hi.mean():          # slope rises to the right: toe on the left
        x_toe, x_crest = x_lo.max(), x_hi.min()
        w = max(x_crest - x_toe, 0.05 * span)
        exit_r = (max(gp.xmin, x_toe - 0.5 * w), x_toe + 0.2 * w)
        entry_r = (x_crest - 0.2 * w, min(gp.xmax, x_crest + 1.0 * w))
    else:                                    # slope descends to the right: toe on the right
        x_toe, x_crest = x_lo.min(), x_hi.max()
        w = max(x_toe - x_crest, 0.05 * span)
        exit_r = (x_toe - 0.2 * w, min(gp.xmax, x_toe + 0.5 * w))
        entry_r = (max(gp.xmin, x_crest - 1.0 * w), x_crest + 0.2 * w)
    return entry_r, exit_r
