"""Probabilistic slope stability on several slip surfaces, with sensitivity.

The analysis settings already have a Monte Carlo option that varies the strength on the critical slip
surface only. Here each trial is checked on a pool of slip surfaces (the lowest ones of the search),
so a different surface can become critical when the strength changes. That is closer to a full
probabilistic search, and it is much faster than searching again for every trial.

Random variables: c', phi' and unit weight of each material (normal, lognormal or uniform), and
optionally the water table level. The mean is the material's value; the spread is the material's
standard deviation, or a coefficient of variation (COV) when no standard deviation is set. Typical
COVs: c' 20-40 %, tan phi' 5-15 %, unit weight 3-7 %.

Results: probability of failure Pf = P(F < 1), the mean and standard deviation of F, and two
reliability indices: normal beta = (mean - 1) / sd, and lognormal beta. Also a histogram, and a
tornado chart of how far F moves when each variable goes to its mean +/- one standard deviation.
"""
from __future__ import annotations

import math

import numpy as np

DEFAULT_COV = {"cohesion": 0.30, "phi": 0.10, "unit_weight": 0.05}
LABEL = {"cohesion": "c'", "phi": "phi'", "unit_weight": "unit weight"}


def variables(project, analysis=None, cov=None, water_sd: float = 0.0, materials=None):
    """The random variables: [{"key", "label", "mean", "sd", "dist"}]. ``materials`` limits them to some ids."""
    cov = {**DEFAULT_COV, **(cov or {})}
    out = []
    for m in project.materials:
        if materials is not None and m.id not in materials:
            continue
        for prop in ("cohesion", "phi", "unit_weight"):
            mean = float(getattr(m, prop))
            sd = float(getattr(m, prop + "_sd", 0.0) or 0.0)
            if sd <= 0:
                sd = abs(mean) * cov[prop]
            if mean <= 0 and prop != "cohesion":
                continue
            if sd <= 0:
                continue
            out.append({"key": f"m{m.id}.{prop}", "label": f"{m.name}: {LABEL[prop]}", "mean": mean, "sd": sd,
                        "dist": m.distribution or "normal"})
    if water_sd > 0 and project.piezometric_line:
        out.append({"key": "water_dy", "label": "Water table level", "mean": 0.0, "sd": float(water_sd),
                    "dist": "normal"})
    return out


def sample(rng, v):
    mu, sd, dist = v["mean"], v["sd"], v["dist"]
    if dist == "lognormal" and mu > 0:
        s2 = math.log(1 + (sd / mu) ** 2)
        x = rng.lognormal(math.log(mu) - s2 / 2, math.sqrt(s2))
    elif dist == "uniform":
        h = sd * math.sqrt(3)
        x = rng.uniform(mu - h, mu + h)
    else:
        x = rng.normal(mu, sd)
    if v["key"].endswith(".phi"):
        x = min(max(x, 0.0), 89.0)
    elif v["key"].endswith(".cohesion"):
        x = max(x, 0.0)
    elif v["key"].endswith(".unit_weight"):
        x = max(x, 0.1)
    return float(x)


def run(pool, vars_, n: int = 200, seed: int = 1, progress=None, cancelled=None) -> dict:
    """Monte Carlo with ``n`` trials on a whatif.SurfacePool."""
    rng = np.random.default_rng(seed)
    fs = []
    for i in range(int(n)):
        if cancelled and cancelled():
            break
        ch = {v["key"]: sample(rng, v) for v in vars_}
        F = pool.fos(ch)
        if math.isfinite(F):
            fs.append(F)
        if progress and (i % 5 == 0 or i == n - 1):
            progress(int(100 * (i + 1) / n))
    return stats(fs, pool.base_fos)


def stats(fs, base=None) -> dict:
    fs = np.asarray(fs, dtype=float)
    if len(fs) < 2:
        return {"n": int(len(fs))}
    mean, sd = float(fs.mean()), float(fs.std(ddof=1))
    beta = (mean - 1.0) / sd if sd > 0 else None
    beta_ln = None
    if sd > 0 and mean > 0:
        cv = sd / mean
        beta_ln = math.log(mean / math.sqrt(1 + cv * cv)) / math.sqrt(math.log(1 + cv * cv))
    hist, edges = np.histogram(fs, bins=24)
    return {"n": int(len(fs)), "base": base, "mean": mean, "sd": sd, "min": float(fs.min()), "max": float(fs.max()),
            "pf": float((fs < 1.0).mean()), "beta": beta, "beta_lognormal": beta_ln,
            "p5": float(np.percentile(fs, 5)), "p95": float(np.percentile(fs, 95)),
            "histogram": hist.tolist(), "edges": edges.tolist(), "values": fs.tolist()}


def tornado(pool, vars_, progress=None) -> list[dict]:
    """F at mean - sd and mean + sd of each variable, the others at their means; widest swing first."""
    out = []
    for i, v in enumerate(vars_):
        lo = dict(v, dist="normal")
        a = {v["key"]: _clamp(v, v["mean"] - v["sd"])}
        b = {v["key"]: _clamp(v, v["mean"] + v["sd"])}
        f_lo, f_hi = pool.fos(a), pool.fos(b)
        out.append({"key": v["key"], "label": lo["label"], "low": f_lo, "high": f_hi,
                    "swing": abs(f_hi - f_lo) if math.isfinite(f_hi) and math.isfinite(f_lo) else 0.0})
        if progress:
            progress(int(100 * (i + 1) / max(1, len(vars_))))
    out.sort(key=lambda r: -r["swing"])
    return out


def _clamp(v, x):
    k = v["key"]
    if k.endswith(".phi"):
        return min(max(x, 0.0), 89.0)
    if k.endswith(".cohesion"):
        return max(x, 0.0)
    if k.endswith(".unit_weight"):
        return max(x, 0.1)
    return x


USACE = [(5.0, "high"), (4.0, "good"), (3.0, "above average"), (2.5, "below average"), (2.0, "poor"),
         (1.5, "unsatisfactory"), (-1e9, "hazardous")]


def usace(beta: float) -> str:
    return next(name for b, name in USACE if beta >= b)


def text_report(res: dict, torn=None, vars_=None) -> str:
    if res.get("n", 0) < 2:
        return "Too few valid trials."
    lines = ["Probabilistic slope stability (Monte Carlo on the lowest slip surfaces)",
             f"Trials: {res['n']}    F of the mean values: {res['base']:.3f}" if res.get("base") else
             f"Trials: {res['n']}",
             f"Mean F {res['mean']:.3f}   standard deviation {res['sd']:.3f}   range {res['min']:.3f} - {res['max']:.3f}",
             f"5 % / 95 % values: {res['p5']:.3f} / {res['p95']:.3f}",
             f"Probability of failure Pf = P(F < 1) = {100 * res['pf']:.2f} %",
             "Reliability index beta: "
             + (f"{res['beta']:.2f} (normal)" if res.get("beta") is not None else "-")
             + (f", {res['beta_lognormal']:.2f} (lognormal)" if res.get("beta_lognormal") is not None else "")]
    b = res.get("beta")
    if b is not None:
        lines.append(f"Performance level (US Army Corps of Engineers 1997): {usace(b)}")
    if vars_:
        lines += ["", "Random variables:"]
        lines += [f"  {v['label']:<40} mean {v['mean']:9.3f}  sd {v['sd']:8.3f}  {v['dist']}" for v in vars_]
    if torn:
        lines += ["", "Sensitivity (F at mean - 1 sd / mean + 1 sd):"]
        lines += [f"  {t['label']:<40} {t['low']:7.3f} / {t['high']:7.3f}   swing {t['swing']:.3f}" for t in torn]
    return "\n".join(lines)
