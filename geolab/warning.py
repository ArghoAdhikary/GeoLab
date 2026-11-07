"""Landslide early warning: past rain plus the 7-16 day forecast, turned into a factor of safety and
an alert level for each day.

Rain comes from the free Open-Meteo forecast service (no key): the last ``past_days`` of measured
(model-analysed) rain and the forecast. Two ways to get F for each day:

* **Model** (best): the series goes on the climate boundary of the project's transient seepage
  analysis, which is then solved with the slope analysis below it (as Tools > Rainfall does). This
  needs a transient seepage analysis with a climate boundary.
* **Quick**: the water table rises with the antecedent rain. The rise is the effective rain
  (``antecedent_index``, a decaying sum) divided by the drainable porosity. It is capped at
  ``max_rise`` and re-evaluated on the solved slip surfaces (see whatif.SurfacePool). This is a
  screening estimate.

A rain threshold is also checked: the Chattogram hill threshold of Rahman & Rahman style
cumulative rain (default: 3-day rain above 150 mm, or 1-day above 90 mm). The thresholds can
be edited; there is no national standard yet.

Alert levels: red F < 1.0 (or above both thresholds), orange F < ``orange`` (1.2), yellow F < ``yellow``
(1.3) or above one threshold, green otherwise.
"""
from __future__ import annotations

import datetime as dt
import json
import urllib.parse
import urllib.request

FORECAST = "https://api.open-meteo.com/v1/forecast"
LEVELS = ("green", "yellow", "orange", "red")
DEFAULTS = {"past_days": 14, "forecast_days": 7, "decay": 0.85, "porosity": 0.10, "max_rise": 6.0,
            "infiltration": 0.5, "yellow": 1.3, "orange": 1.2, "red": 1.0,
            "rain_1d": 90.0, "rain_3d": 150.0}


def fetch_forecast(lat, lon, past_days=14, forecast_days=7, timeout=30.0, opener=None) -> dict:
    """Daily rain and ET0 (mm/day): ``past_days`` back and ``forecast_days`` ahead."""
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("Latitude must be -90..90 and longitude -180..180.")
    q = urllib.parse.urlencode({"latitude": f"{lat:.4f}", "longitude": f"{lon:.4f}",
                                "daily": "precipitation_sum,et0_fao_evapotranspiration",
                                "past_days": int(past_days), "forecast_days": int(forecast_days),
                                "timezone": "auto"})
    req = urllib.request.Request(f"{FORECAST}?{q}", headers={"User-Agent": "GeoLab"})
    try:
        with (opener or urllib.request.urlopen)(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:                       # noqa: BLE001
        raise ValueError(f"Could not get the forecast from Open-Meteo: {e}") from e
    if data.get("error"):
        raise ValueError(f"Open-Meteo: {data.get('reason', 'error')}")
    d = data.get("daily") or {}
    days = d.get("time") or []
    if not days:
        raise ValueError("Open-Meteo returned no days.")
    rain = [float(v or 0.0) for v in d.get("precipitation_sum", [])]
    et0 = [float(v or 0.0) for v in d.get("et0_fao_evapotranspiration", [])] or [0.0] * len(rain)
    today = dt.date.today().isoformat()
    return {"dates": days, "rain": rain, "et0": et0, "today": today,
            "first_forecast": next((i for i, x in enumerate(days) if x >= today), len(days)),
            "lat": lat, "lon": lon, "source": "Open-Meteo forecast"}


def antecedent(rain, decay=0.85):
    """Antecedent precipitation index for each day: API_t = decay * API_(t-1) + rain_t."""
    out, a = [], 0.0
    for r in rain:
        a = decay * a + float(r)
        out.append(a)
    return out


def rolling(rain, n):
    return [sum(rain[max(0, i - n + 1):i + 1]) for i in range(len(rain))]


def level_of(fos, r1, r3, s) -> str:
    over = int(r1 >= s["rain_1d"]) + int(r3 >= s["rain_3d"])
    lvl = 0
    if fos is not None:
        if fos < s["red"]:
            lvl = 3
        elif fos < s["orange"]:
            lvl = 2
        elif fos < s["yellow"]:
            lvl = 1
    lvl = max(lvl, {0: 0, 1: 1, 2: 3}[over])
    return LEVELS[lvl]


def quick_assessment(series: dict, pool=None, settings: dict | None = None) -> dict:
    """F and the alert level for each day by the quick (water table rise) method.

    ``pool`` is a whatif.SurfacePool of the solved slope (None: rain thresholds only)."""
    s = {**DEFAULTS, **(settings or {})}
    rain = series["rain"]
    api = antecedent(rain, s["decay"])
    r1, r3 = rain, rolling(rain, 3)
    rises = [min(s["max_rise"], s["infiltration"] * a / 1000.0 / max(1e-3, s["porosity"])) for a in api]
    cache = {}
    days = []
    for i, d in enumerate(series["dates"]):
        rise = round(rises[i], 2)
        fos = None
        if pool is not None:
            if rise not in cache:
                cache[rise] = pool.fos({"water_dy": rise})
            fos = cache[rise]
        days.append({"date": d, "rain": rain[i], "rain_3d": r3[i], "api": api[i], "rise": rise, "fos": fos,
                     "forecast": i >= series.get("first_forecast", len(rain)),
                     "level": level_of(fos, r1[i], r3[i], s)})
    return summarize(days, "quick (water table rises with antecedent rain)")


def model_assessment(project, series: dict, settings: dict | None = None, progress=None) -> dict:
    """F for each day from the project's own transient seepage with the rain applied: the seepage is solved
    once, then the slip surfaces of the slope analysis are checked with the pore pressures of each day."""
    import copy

    import numpy as np

    from . import rainfall
    from .solver import solve
    from .whatif import SurfacePool
    s = {**DEFAULTS, **(settings or {})}
    p = copy.deepcopy(project)
    rs = {"dates": series["dates"], "rain": series["rain"], "et0": series["et0"],
          "source": series.get("source", "forecast")}
    rainfall.apply_to_project(p, rs)
    slope = next((a for a in p.analyses if a.kind == "slope" and a.pwp == "seepage"), None)
    if slope is None:
        raise ValueError("The model needs a slope analysis that takes its pore pressures from the seepage "
                         "analysis (as in the rainfall example).")
    from .solver import ancestor
    seep = ancestor(p, slope, "seepage")
    sres = solve(p, seep)
    solve(p, slope)
    pool = SurfacePool(p, slope, n=15)
    times = np.array(sres.get("times") or [])
    hist = sres.get("head_history") or []
    ys = np.array(sres["nodes"])[:, 1]
    rain, r3 = series["rain"], rolling(series["rain"], 3)
    days = []
    for i, d in enumerate(series["dates"]):
        fos = None
        if len(times):
            k = int(np.argmin(np.abs(times - (i + 1) * 86400.0)))
            h = np.array(hist[k])
            pool.seep = dict(sres, head=h.tolist(), pressure_head=(h - ys).tolist())
            fos = pool.evaluate(project=p, analysis=slope)[0]
        if progress:
            progress(int(100 * (i + 1) / len(series["dates"])))
        days.append({"date": d, "rain": rain[i], "rain_3d": r3[i], "fos": fos,
                     "forecast": i >= series.get("first_forecast", len(rain)),
                     "level": level_of(fos, rain[i], r3[i], s)})
    return summarize(days, "model (transient seepage with the rain, then slope stability)")


def summarize(days, method) -> dict:
    worst = max(days, key=lambda d: LEVELS.index(d["level"])) if days else None
    fut = [d for d in days if d["forecast"]]
    worst_f = max(fut, key=lambda d: LEVELS.index(d["level"])) if fut else worst
    fmin = min((d["fos"] for d in days if d["fos"] is not None), default=None)
    return {"days": days, "method": method, "level": worst_f["level"] if worst_f else "green",
            "worst_day": worst_f["date"] if worst_f else None, "min_fos": fmin,
            "total_rain": sum(d["rain"] for d in days),
            "forecast_rain": sum(d["rain"] for d in fut)}


def text_report(res: dict, place: str = "") -> str:
    lines = [f"Landslide early warning {place}".rstrip(), f"Method: {res['method']}",
             f"Alert for the forecast days: {res['level'].upper()}"
             + (f" (worst on {res['worst_day']})" if res.get("worst_day") else ""),
             f"Rain in the period: {res['total_rain']:.0f} mm, of which forecast {res['forecast_rain']:.0f} mm", "",
             f"{'Date':<12}{'Rain':>8}{'3-day':>8}{'F':>8}  Level"]
    for d in res["days"]:
        f = f"{d['fos']:.3f}" if d["fos"] is not None and d["fos"] != float("inf") else "-"
        lines.append(f"{d['date']:<12}{d['rain']:8.1f}{d['rain_3d']:8.1f}{f:>8}  {d['level']}"
                     + ("  (forecast)" if d["forecast"] else ""))
    return "\n".join(lines)
