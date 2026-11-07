"""A cross-section from a map: ground levels along a line between two points.

Ground levels come from the Copernicus 90 m digital elevation model through the free Open-Meteo
elevation service (no key; https://open-meteo.com/en/docs/elevation-api). Only the coordinates
of the points along the line are sent. The section can be turned into a slope model with soil
layers that follow the ground at chosen depths.

A 90 m DEM smooths small features: cuttings, retaining walls and slopes shorter than about
100 m are not seen. Use a survey for design; this is for first checks and for finding the
steepest line of a hill.
"""
from __future__ import annotations

import json
import math
import urllib.parse
import urllib.request

ELEVATION = "https://api.open-meteo.com/v1/elevation"
R_EARTH = 6371008.8


def haversine(lat1, lon1, lat2, lon2) -> float:
    """Distance in metres between two points on the earth."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R_EARTH * math.asin(min(1.0, math.sqrt(a)))


def line_points(a, b, n: int):
    """n points (lat, lon) evenly along the great-circle line a -> b, and their distances from a."""
    n = max(2, int(n))
    total = haversine(a[0], a[1], b[0], b[1])
    pts = [(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t) for t in (i / (n - 1) for i in range(n))]
    return pts, [total * i / (n - 1) for i in range(n)]


def fetch_elevations(points, timeout: float = 30.0, opener=None) -> list[float]:
    """Ground levels (m above sea level) of up to a few hundred (lat, lon) points."""
    out = []
    for k in range(0, len(points), 100):           # the service takes 100 points per request
        chunk = points[k:k + 100]
        q = urllib.parse.urlencode({"latitude": ",".join(f"{p[0]:.5f}" for p in chunk),
                                    "longitude": ",".join(f"{p[1]:.5f}" for p in chunk)})
        req = urllib.request.Request(f"{ELEVATION}?{q}", headers={"User-Agent": "GeoLab"})
        if opener is None:
            from .net import check
            check("Getting ground levels")
        try:
            with (opener or urllib.request.urlopen)(req, timeout=timeout) as r:
                data = json.loads(r.read().decode("utf-8"))
        except Exception as e:                       # noqa: BLE001
            raise ValueError(f"Could not get the ground levels from Open-Meteo: {e}") from e
        if data.get("error"):
            raise ValueError(f"Open-Meteo: {data.get('reason', 'error')}")
        el = data.get("elevation") or []
        if len(el) != len(chunk):
            raise ValueError("Open-Meteo returned the wrong number of ground levels.")
        out += [float(v) for v in el]
    return out


def profile(a, b, n: int = 60, opener=None) -> dict:
    """Ground profile along a -> b: {"x": distances (m), "z": levels (m), "points": [(lat, lon)], "length"}."""
    if a == b:
        raise ValueError("Pick two different points.")
    pts, xs = line_points(a, b, n)
    if xs[-1] > 20000:
        raise ValueError("Keep the section shorter than 20 km.")
    zs = fetch_elevations(pts, opener=opener)
    return {"x": xs, "z": zs, "points": pts, "length": xs[-1], "a": list(a), "b": list(b)}


def smooth(z, passes: int = 1):
    z = list(z)
    for _ in range(passes):
        z = [z[0]] + [(z[i - 1] + 2 * z[i] + z[i + 1]) / 4 for i in range(1, len(z) - 1)] + [z[-1]]
    return z


DEFAULT_LAYERS = [   # name, thickness below the ground (m; 0 = to the bottom), c', phi', unit weight, colour
    ("Residual soil (silty clay)", 4.0, 8.0, 26.0, 18.5, "#d9c49c"),
    ("Weathered rock (dense sandy silt)", 8.0, 15.0, 34.0, 20.0, "#b9a37a"),
    ("Rock", 0.0, 100.0, 40.0, 23.0, "#8f8f8f"),
]


def build_model(prof: dict, layers=None, water_depth: float | None = 3.0, base_depth: float = 15.0,
                smooth_passes: int = 1, title: str = "Section from map"):
    """A slope stability model of the section: soil layers that follow the ground surface, a water table
    ``water_depth`` below the ground (None = no water), and an entry-exit slip search on the steepest part."""
    from .model import Analysis, Material, Region, new_project  # noqa: F401
    layers = list(layers or DEFAULT_LAYERS)
    x = [float(v) for v in prof["x"]]
    z = smooth(prof["z"], smooth_passes)
    z0 = min(z) - base_depth
    p = new_project("metric", "slope")
    p.title = title
    p.description = (f"Ground levels from the Copernicus 90 m DEM (Open-Meteo) between "
                     f"{prof['a'][0]:.5f}, {prof['a'][1]:.5f} and {prof['b'][0]:.5f}, {prof['b'][1]:.5f}. "
                     "Check against a survey.")
    p.materials = []
    p.regions = []
    top = [(xi, zi) for xi, zi in zip(x, z)]
    depth_done = 0.0
    for i, (name, t, c, phi, g, col) in enumerate(layers):
        mid = i + 1
        p.materials.append(Material(id=mid, name=name, color=col, cohesion=float(c), phi=float(phi),
                                    unit_weight=float(g)))
        last = (t <= 0) or i == len(layers) - 1
        if last:
            bottom = [(xi, z0) for xi in x]
        else:
            depth_done += float(t)
            bottom = [(xi, max(z0 + 0.5, zi - depth_done)) for xi, zi in zip(x, z)]
        pts = top + list(reversed(bottom))
        p.regions.append(Region(id=mid, points=[[round(a, 3), round(b, 3)] for a, b in pts], material_id=mid))
        if last:
            break
        top = bottom
    if water_depth is not None:
        p.piezometric_line = [[round(xi, 3), round(zi - float(water_depth), 3)] for xi, zi in zip(x, z)]
    a = p.analyses[0] if p.analyses else Analysis(id=1, name="Slope stability")
    a.name = "Slope stability (section from map)"
    if water_depth is not None:
        a.pwp = "piezometric"
    from .geometry import auto_entry_exit
    (e1, e2), (x1, x2) = auto_entry_exit(p)
    a.search.mode = "entry_exit"
    a.search.entry_x1, a.search.entry_x2 = float(e1), float(e2)
    a.search.exit_x1, a.search.exit_x2 = float(x1), float(x2)
    if not p.analyses:
        p.analyses = [a]
    return p


def steepest(prof: dict) -> dict:
    x, z = prof["x"], prof["z"]
    best = max(range(1, len(x)), key=lambda i: abs(z[i] - z[i - 1]) / max(1e-6, x[i] - x[i - 1]))
    g = abs(z[best] - z[best - 1]) / max(1e-6, x[best] - x[best - 1])
    return {"at": 0.5 * (x[best] + x[best - 1]), "grade": g, "angle": math.degrees(math.atan(g)),
            "relief": max(z) - min(z)}
