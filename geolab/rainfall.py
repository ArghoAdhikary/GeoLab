"""Real rainfall for a site: daily rain and evaporation (FAO reference ET0) from the Open-Meteo historical
weather archive (free, no key; https://open-meteo.com), or from a CSV file, or a design storm. The series
becomes the climate boundary of a transient seepage analysis, so the slope can be checked through a real
wet season (landslide early warning, e.g. the Chattogram hills in the monsoon).

Only the latitude, longitude and dates the user enters are sent to Open-Meteo.
"""
from __future__ import annotations

import datetime as dt
import json
import urllib.parse
import urllib.request

from .borehole import read_table

ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
DAY = 86400.0
MM_PER_DAY = 1.0 / 1000.0 / DAY     # mm/day -> m/s

PLACES = {   # a few places to start from
    "Chattogram (Bangladesh)": (22.3569, 91.7832),
    "Rangamati (Bangladesh)": (22.6533, 92.1789),
    "Cox's Bazar (Bangladesh)": (21.4272, 92.0058),
    "Sylhet (Bangladesh)": (24.8949, 91.8687),
    "Dhaka (Bangladesh)": (23.8103, 90.4125),
    "Sydney (Australia)": (-33.8688, 151.2093),
    "Brisbane (Australia)": (-27.4698, 153.0251),
    "Melbourne (Australia)": (-37.8136, 144.9631),
    "Cairns (Australia)": (-16.9186, 145.7781),
}


def fetch_open_meteo(lat: float, lon: float, start: str, end: str, timeout: float = 30.0, opener=None) -> dict:
    """Daily rainfall and ET0 (mm/day) between two dates (YYYY-MM-DD)."""
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("Latitude must be -90..90 and longitude -180..180.")
    d0, d1 = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    if d1 < d0:
        raise ValueError("The end date is before the start date.")
    if (d1 - d0).days > 3 * 366:
        raise ValueError("Ask for three years at most.")
    q = urllib.parse.urlencode({"latitude": f"{lat:.4f}", "longitude": f"{lon:.4f}", "start_date": start,
                                "end_date": end, "daily": "precipitation_sum,et0_fao_evapotranspiration",
                                "timezone": "auto"})
    req = urllib.request.Request(f"{ARCHIVE}?{q}", headers={"User-Agent": "GeoLab"})
    try:
        with (opener or urllib.request.urlopen)(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:                       # noqa: BLE001
        raise ValueError(f"Could not get the weather data from Open-Meteo: {e}") from e
    if data.get("error"):
        raise ValueError(f"Open-Meteo: {data.get('reason', 'error')}")
    d = data.get("daily") or {}
    days = d.get("time") or []
    rain = [float(v or 0.0) for v in d.get("precipitation_sum", [])]
    et0 = [float(v or 0.0) for v in d.get("et0_fao_evapotranspiration", [])]
    if not days:
        raise ValueError("Open-Meteo returned no days for that period.")
    return {"dates": days, "rain": rain, "et0": et0 or [0.0] * len(rain),
            "source": f"Open-Meteo archive, {lat:.3f}, {lon:.3f}"}


def from_csv(path_or_text) -> dict:
    """date (or day number), rain (mm/day), and optionally et0 / evaporation (mm/day)."""
    rows = read_table(path_or_text)
    head = [h.strip().lower() for h in rows[0]]

    def col(*names):
        return next((i for i, h in enumerate(head) if any(h.startswith(n) for n in names)), None)
    ir, ie, idt = col("rain", "precip", "p"), col("et0", "evap", "pet", "e"), col("date", "day", "time", "t")
    if ir is None:
        raise ValueError("The file needs a 'rain' column in mm/day.")
    dates, rain, et0 = [], [], []
    for r in rows[1:]:
        try:
            rain.append(float(r[ir]))
        except (ValueError, IndexError):
            continue
        et0.append(float(r[ie]) if ie is not None and ie < len(r) and r[ie].strip() else 0.0)
        dates.append(r[idt] if idt is not None and idt < len(r) else str(len(dates) + 1))
    if not rain:
        raise ValueError("No rainfall values were found.")
    return {"dates": dates, "rain": rain, "et0": et0, "source": "CSV file"}


def design_storm(total_mm: float, days: int, dry_days: int = 10, et0: float = 3.0) -> dict:
    """Rain spread evenly over `days`, then `dry_days` without rain."""
    n = days + dry_days
    rain = [total_mm / days] * days + [0.0] * dry_days
    return {"dates": [str(i + 1) for i in range(n)], "rain": rain, "et0": [et0] * n,
            "source": f"Design storm: {total_mm:g} mm in {days} days"}


def stats(series: dict) -> dict:
    r = series["rain"]
    best5 = max((sum(r[i:i + 5]) for i in range(max(1, len(r) - 4))), default=0.0)
    i_max = max(range(len(r)), key=lambda i: r[i]) if r else 0
    return {"days": len(r), "total": sum(r), "max_day": max(r) if r else 0.0,
            "max_day_date": series["dates"][i_max] if r else "", "max_5day": best5,
            "et0_total": sum(series["et0"])}


def to_functions(series: dict, units: str = "metric"):
    """(rain fn, evaporation fn) as [[time s, flux per second], ...] steps (one value per day)."""
    f = MM_PER_DAY if units == "metric" else MM_PER_DAY * 3.2808
    rain, evap = [], []
    for i, (r, e) in enumerate(zip(series["rain"], series["et0"])):
        t0, t1 = i * DAY, (i + 1) * DAY - 1.0
        rain += [[t0, r * f], [t1, r * f]]
        evap += [[t0, e * f], [t1, e * f]]
    return rain, evap


def apply_to_project(project, series: dict, seep_analysis=None, steps_per_day: float = 1.0) -> str:
    """Put the series on the climate boundary (one is made along the ground if none exists) and set the
    transient seepage analysis to run over the whole period."""
    from .geometry import GroundProfile
    seeps = [a for a in project.analyses if a.kind == "seepage"]
    a = seep_analysis or next((x for x in seeps if x.transient), seeps[0] if seeps else None)
    if a is None:
        raise ValueError("The model has no seepage analysis. Start from the rainfall example "
                         "(File > Open Example) or add a transient seepage analysis.")
    rain, evap = to_functions(series, project.units)
    bc = next((b for b in project.boundary_conditions if b.type == "climate"), None)
    if bc is None:
        gp = GroundProfile(project.regions)
        xs = sorted({p[0] for r in project.regions for p in r.points})
        pts = [(x, float(gp.ground(x))) for x in xs]
        bc = project.add_bc("Weather", "climate", 0.0, pts, humidity=0.7)
    bc.fn, bc.fn2 = rain, evap
    bc.value, bc.value2 = 0.0, 0.0
    n_days = len(series["rain"])
    a.transient = True
    a.duration = n_days * DAY
    a.n_steps = max(10, int(round(n_days * steps_per_day)))
    a.step_growth = 1.0
    if a.initial == "parent" and project.analysis(a.parent_id) is None:
        a.initial = "water_table"
    project.clear_results()
    s = stats(series)
    return (f"{series['source']}: {s['days']} days, {s['total']:.0f} mm of rain (wettest day {s['max_day']:.0f} mm "
            f"on {s['max_day_date']}, wettest 5 days {s['max_5day']:.0f} mm) on '{bc.name}', analysis '{a.name}' "
            f"runs {n_days} days.")
