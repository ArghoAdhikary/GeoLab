"""Parametric study: change one or two values over a range, find F for each, and see where F crosses the
target. Uses the slip surfaces kept by the solved slope analysis (whatif.SurfacePool), so one hundred runs
take seconds; `confirm=True` runs the full slip-surface search for every point instead.
"""
from __future__ import annotations

import math

from .whatif import CHANGES, MAT_PROPS


def parameters(project) -> dict:
    """key -> label of everything that can be varied."""
    out = dict(CHANGES)
    for m in project.materials:
        for prop, lab in MAT_PROPS.items():
            out[f"m{m.id}.{prop}"] = f"{m.name}: {lab}"
    return out


def current_value(project, analysis, key: str) -> float:
    if key == "water_dy":
        return 0.0
    if key in ("ru", "kh", "kv"):
        return float(getattr(analysis, key))
    if key.endswith("_factor"):
        return 1.0
    if key.startswith("m") and "." in key:
        mid, prop = key[1:].split(".", 1)
        return float(getattr(project.material(int(mid)), prop))
    return 0.0


def default_range(project, analysis, key: str) -> tuple[float, float]:
    v = current_value(project, analysis, key)
    if key == "water_dy":
        return -5.0, 5.0
    if key in ("kh", "kv"):
        return 0.0, 0.3
    if key == "ru":
        return 0.0, 0.6
    if key.endswith("_factor"):
        return 0.5, 1.5
    if key.endswith(".phi"):
        return max(0.0, v - 10), v + 10
    if key.endswith(".unit_weight"):
        return max(1.0, v - 3), v + 3
    return 0.0, max(2 * v, 10.0)


def values(lo: float, hi: float, n: int) -> list[float]:
    n = max(2, int(n))
    return [lo + (hi - lo) * i / (n - 1) for i in range(n)]


def run(pool, key: str, xs: list[float], key2: str | None = None, ys: list[float] | None = None,
        confirm: bool = False, progress=None, cancelled=None) -> dict:
    """F for every x (and every y of the second parameter). F[j][i] is at xs[i], ys[j]."""
    ys = list(ys) if key2 else [None]
    total = len(xs) * len(ys)
    F, k = [], 0
    for y in ys:
        row = []
        for x in xs:
            if cancelled and cancelled():
                raise InterruptedError("Stopped.")
            ch = {key: x}
            if key2:
                ch[key2] = y
            if confirm:
                from .whatif import confirm as full
                r = full(pool.project, pool.analysis, ch)
                f = float(r["critical"]["fos"]) if r.get("critical") else math.inf
            else:
                f = pool.fos(ch)
            row.append(f)
            k += 1
            if progress:
                progress(100 * k / total)
        F.append(row)
    return {"key": key, "key2": key2, "xs": list(xs), "ys": ys if key2 else [], "F": F,
            "base": pool.base_fos}


def crossing(xs, fs, target: float = 1.0):
    """First x where F passes the target (linear interpolation), or None."""
    for i in range(len(xs) - 1):
        a, b = fs[i], fs[i + 1]
        if not (math.isfinite(a) and math.isfinite(b)):
            continue
        if (a - target) * (b - target) <= 0 and a != b:
            return xs[i] + (target - a) * (xs[i + 1] - xs[i]) / (b - a)
    return None


def rows(res: dict, labels: dict | None = None) -> list[list]:
    labels = labels or {}
    k1 = labels.get(res["key"], res["key"])
    if not res["key2"]:
        return [[k1, "F"]] + [[x, f] for x, f in zip(res["xs"], res["F"][0])]
    k2 = labels.get(res["key2"], res["key2"])
    out = [[f"{k2} \\ {k1}"] + list(res["xs"])]
    for y, r in zip(res["ys"], res["F"]):
        out.append([y] + list(r))
    return out


def text_report(res: dict, labels: dict | None = None, target: float = 1.5) -> str:
    labels = labels or {}
    k1 = labels.get(res["key"], res["key"])
    L = [f"Parametric study: {k1}" + (f" and {labels.get(res['key2'], res['key2'])}" if res["key2"] else ""),
         "=" * 72, f"Factor of safety of the solved model: {res['base']:.3f}", ""]

    def f(v):
        return f"{v:9.3f}" if math.isfinite(v) else "      inf"
    if not res["key2"]:
        L.append(f"{'value':>12}  {'F':>9}")
        for x, v in zip(res["xs"], res["F"][0]):
            L.append(f"{x:12.4g}  {f(v)}")
        for t in sorted({1.0, target}):
            c = crossing(res["xs"], res["F"][0], t)
            L.append(f"F = {t:g} at {k1} = {c:.4g}" if c is not None else f"F does not cross {t:g} in this range")
    else:
        L.append(f"{'':>12}" + "".join(f"{x:>9.3g}" for x in res["xs"]))
        for y, r in zip(res["ys"], res["F"]):
            L.append(f"{y:12.4g}" + "".join(f(v) for v in r))
        L.append("")
        L.append(f"Rows: {labels.get(res['key2'], res['key2'])}; columns: {k1}.")
    return "\n".join(L)
