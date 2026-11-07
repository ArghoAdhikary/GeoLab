"""Monitoring data beside the model: piezometers, settlement plates, inclinometers / survey points.

A CSV with one reading per row:  instrument, kind, x, y, time, value
  kind: head | pore_pressure | settlement | displacement_x | displacement_y
  time: seconds, or with a unit: "12 d", "3 h" (blank = steady state / end of the analysis)
The readings are stored in the project and compared with the selected analysis: computed value at the
same place and time, difference, and the root-mean-square error.
"""
from __future__ import annotations

import math
import re

import numpy as np

from .borehole import read_table

KINDS = {
    "head": ("Total head (piezometer)", "length"),
    "pore_pressure": ("Pore-water pressure (piezometer)", "pressure"),
    "settlement": ("Settlement (down +)", "length"),
    "displacement_x": ("Horizontal displacement (inclinometer, survey)", "length"),
    "displacement_y": ("Vertical displacement (up +)", "length"),
}
_TIME_UNITS = {"s": 1, "sec": 1, "min": 60, "h": 3600, "hr": 3600, "d": 86400, "day": 86400, "days": 86400,
               "w": 604800, "wk": 604800, "mo": 2629800, "month": 2629800, "y": 31557600, "yr": 31557600}


def parse_time(v):
    if v is None:
        return None
    s = str(v).strip().lower()
    if not s:
        return None
    m = re.match(r"^([-+0-9.eE]+)\s*([a-z]*)$", s)
    if not m:
        raise ValueError(f"Cannot read the time '{v}'.")
    return float(m.group(1)) * _TIME_UNITS.get(m.group(2) or "s", 1)


def parse(path_or_text) -> list[dict]:
    rows = read_table(path_or_text)
    head = [h.strip().lower() for h in rows[0]]

    def col(*names):
        return next((i for i, h in enumerate(head) if any(h.startswith(n) for n in names)), None)
    ii, ik, ix, iy, it, iv = (col("instr", "name", "id"), col("kind", "type"), col("x"), col("y", "elev"),
                              col("time", "t", "date"), col("value", "reading", "v"))
    if None in (ix, iy, iv):
        raise ValueError("The file needs the columns x, y and value (and instrument, kind, time).")
    out = []
    for r in rows[1:]:
        try:
            kind = (r[ik].strip().lower() if ik is not None else "head") or "head"
            if kind not in KINDS:
                raise ValueError(f"Unknown kind '{kind}' (use {', '.join(KINDS)}).")
            out.append({"instrument": r[ii].strip() if ii is not None else f"P{len(out) + 1}", "kind": kind,
                        "x": float(r[ix]), "y": float(r[iy]), "value": float(r[iv]),
                        "time": parse_time(r[it]) if it is not None and it < len(r) else None})
        except (IndexError, ValueError) as e:
            if "Unknown kind" in str(e):
                raise
            continue
    if not out:
        raise ValueError("No readings were found.")
    return out


def _at_time(times, hist, t):
    ts = np.asarray(times, float)
    if t is None or len(ts) == 0:
        return np.asarray(hist[-1], float)
    i = int(np.searchsorted(ts, t))
    if i <= 0:
        return np.asarray(hist[0], float)
    if i >= len(ts):
        return np.asarray(hist[-1], float)
    w = (t - ts[i - 1]) / max(ts[i] - ts[i - 1], 1e-30)
    return (1 - w) * np.asarray(hist[i - 1], float) + w * np.asarray(hist[i], float)


def computed(results: dict, obs: dict, gamma_w: float):
    """Computed value for one reading, or None when the analysis does not give that quantity."""
    from .fe import interpolator
    k, t = obs["kind"], obs.get("time")
    typ = results.get("type")
    if typ == "seepage" and k in ("head", "pore_pressure"):
        h = _at_time(results.get("times", []), results.get("head_history", [results["head"]]), t) \
            if results.get("times") else np.asarray(results["head"], float)
        v = interpolator(results["nodes"], h)(obs["x"], obs["y"])[0]
        return float(v if k == "head" else (v - obs["y"]) * gamma_w)
    if typ == "stress":
        if k == "pore_pressure" and "pwp" in results:
            return float(interpolator(results["nodes"], results["pwp"])(obs["x"], obs["y"])[0])
        if k in ("settlement", "displacement_y"):
            if results.get("dy_history") and t is not None:
                dy = _at_time(results["times"], results["dy_history"], t)
            else:
                dy = np.asarray(results["dy"], float)
            v = float(interpolator(results["nodes"], dy)(obs["x"], obs["y"])[0])
            return -v if k == "settlement" else v
        if k == "displacement_x":
            return float(interpolator(results["nodes"], results["dx"])(obs["x"], obs["y"])[0])
    return None


def compare(project, analysis, observations=None) -> dict:
    obs = project.observations if observations is None else observations
    r = analysis.results
    if not r:
        raise ValueError(f"Solve '{analysis.name}' first.")
    rows = []
    for o in obs:
        c = computed(r, o, project.gamma_w)
        rows.append(dict(o, computed=c, diff=None if c is None else c - o["value"]))
    used = [x for x in rows if x["diff"] is not None]
    by_kind = {}
    for x in used:
        by_kind.setdefault(x["kind"], []).append(x["diff"])
    rms = {k: math.sqrt(sum(d * d for d in v) / len(v)) for k, v in by_kind.items()}
    return {"analysis": analysis.name, "rows": rows, "rms": rms, "n_used": len(used), "n": len(rows)}


def text_report(project, res: dict) -> str:
    L = [f"Monitoring compared with '{res['analysis']}'", ""]
    L.append(f"{'Instrument':<12}{'Kind':<16}{'x':>8}{'y':>8}{'time':>10}{'measured':>11}{'computed':>11}{'diff':>9}")
    for r in res["rows"]:
        t = "-" if r.get("time") is None else f"{r['time'] / 86400:.2f} d"
        c = "-" if r["computed"] is None else f"{r['computed']:.4g}"
        d = "-" if r["diff"] is None else f"{r['diff']:+.3g}"
        L.append(f"{r['instrument'][:11]:<12}{r['kind'][:15]:<16}{r['x']:>8.2f}{r['y']:>8.2f}{t:>10}"
                 f"{r['value']:>11.4g}{c:>11}{d:>9}")
    L.append("")
    for k, v in res["rms"].items():
        unit = project.unit(KINDS[k][1])
        L.append(f"RMS error, {KINDS[k][0].lower()}: {v:.3g} {unit}")
    skipped = res["n"] - res["n_used"]
    if skipped:
        L.append(f"{skipped} reading(s) not compared: this analysis does not compute that quantity.")
    return "\n".join(L)


SAMPLE = """instrument,kind,x,y,time,value
P1,head,30,2,,8.7
P2,head,45,2,,6.9
P3,head,55,1,,5.6
"""
