"""Design code checks: Australian Standards (the default) and the Bangladesh National Building Code 2020.

What is checked
* Slope stability: the factor of safety of every solved slope analysis against the minimum the code (or
  the usual practice under it) asks for, for the design case of the analysis (long term, temporary,
  earthquake, rapid drawdown).
* AS 4678 limit state: c' and tan(phi') multiplied by the soil uncertainty factors and the live load by
  its load factor; the factor of safety of the factored model must be at least 1.0.
* Seismic coefficient: kh from the code's hazard (AS 1170.4: kp Z and the site class; BNBC 2020: the seismic
  zone, site class and importance), for the pseudo-static slope analysis.
* Bearing pressure of footings and liquefaction (see liquefaction.py).

The numbers below are the published values as GeoLab understands them. They are defaults that can be
edited (Design > Design Code Settings): the project specification and the standard itself always govern.
"""
from __future__ import annotations

import math

CODES = {
    "AS": "Australian Standards (AS 4678, AS 1170.4)",
    "BNBC": "Bangladesh National Building Code 2020 (BNBC)",
    "none": "No code (report the factor of safety only)",
}
DEFAULT_CODE = "AS"

CASES = {
    "long_term": "Long term (permanent, drained)",
    "temporary": "Temporary / end of construction",
    "earthquake": "Earthquake (pseudo-static)",
    "drawdown": "Rapid drawdown",
}

# minimum factors of safety for slopes (limit equilibrium, global)
MIN_FOS = {
    "AS": {"long_term": 1.5, "temporary": 1.3, "earthquake": 1.1, "drawdown": 1.3},
    "BNBC": {"long_term": 1.5, "temporary": 1.3, "earthquake": 1.1, "drawdown": 1.3},
    "none": {"long_term": 1.5, "temporary": 1.3, "earthquake": 1.0, "drawdown": 1.2},
}
MIN_FOS_SOURCE = {
    "AS": "Usual Australian practice under AS 4678 / ANCOLD / road-authority specifications",
    "BNBC": "BNBC 2020 Part 6 (soils and foundations) and usual Bangladesh practice",
    "none": "Common practice",
}

# ------------------------------------------------------------------------------------------- AS 4678
# soil uncertainty (strength reduction) factors for c' and tan(phi'), by soil class
AS4678_CLASSES = {
    "I": {"label": "Class I - controlled fill, well investigated", "phi_uc": 0.90, "phi_uphi": 0.95},
    "II": {"label": "Class II - good natural soil / fill with normal investigation", "phi_uc": 0.70,
           "phi_uphi": 0.85},
    "III": {"label": "Class III - poorly known or variable soil", "phi_uc": 0.50, "phi_uphi": 0.75},
}
AS4678_LOAD = {"dead": 1.25, "dead_favourable": 0.8, "live": 1.5}

# ----------------------------------------------------------------------------------------- AS 1170.4
AS1170_Z = {   # hazard factor Z (g) for capital and large cities
    "Adelaide": 0.10, "Brisbane": 0.05, "Canberra": 0.08, "Darwin": 0.09, "Hobart": 0.03,
    "Melbourne": 0.08, "Newcastle": 0.11, "Perth": 0.09, "Sydney": 0.08,
}
AS1170_KP = {  # probability factor kp by annual probability of exceedance
    "1/100": 0.5, "1/200": 0.7, "1/250": 0.75, "1/500": 1.0, "1/800": 1.25, "1/1000": 1.3,
    "1/1500": 1.5, "1/2000": 1.7, "1/2500": 1.8,
}
AS1170_SITE = {  # spectral shape factor at T = 0, Ch(0)
    "Ae": ("Strong rock", 0.8), "Be": ("Rock", 1.0), "Ce": ("Shallow soil", 1.3),
    "De": ("Deep or soft soil", 1.1), "Ee": ("Very soft soil", 1.1),
}
AS1170_KPZ_MIN = 0.08

# ------------------------------------------------------------------------------------------- BNBC 2020
BNBC_ZONES = {1: 0.12, 2: 0.20, 3: 0.28, 4: 0.36}
BNBC_CITIES = {"Dhaka": 2, "Chattogram": 3, "Sylhet": 4, "Rajshahi": 1, "Khulna": 1, "Barishal": 1}
BNBC_SITE = {  # soil factor S
    "SA": ("Rock", 1.0), "SB": ("Very dense soil / soft rock", 1.2), "SC": ("Dense or stiff soil", 1.15),
    "SD": ("Medium dense / firm soil", 1.35), "SE": ("Soft soil layer over stiff", 1.4),
}
BNBC_IMPORTANCE = {"I": 1.0, "II": 1.0, "III": 1.25, "IV": 1.5}

# bearing capacity: factor on the ultimate capacity
BEARING = {"AS": {"kind": "phi_g", "value": 0.5, "label": "Geotechnical reduction factor phi_g"},
           "BNBC": {"kind": "fos", "value": 3.0, "label": "Factor of safety on ultimate bearing"},
           "none": {"kind": "fos", "value": 3.0, "label": "Factor of safety on ultimate bearing"}}

DEFAULT_SETTINGS = {
    "AS": {"soil_class": "II", "city": "Sydney", "Z": 0.08, "probability": "1/500", "site": "De",
           "kh_fraction": 0.5, "case": "auto"},
    "BNBC": {"city": "Dhaka", "zone": 2, "site": "SD", "importance": "II", "kh_fraction": 0.5, "case": "auto"},
    "none": {"case": "auto"},
}


def code_of(project) -> str:
    c = getattr(project, "design_code", "") or DEFAULT_CODE
    return c if c in CODES else DEFAULT_CODE


def settings_of(project) -> dict:
    code = code_of(project)
    s = dict(DEFAULT_SETTINGS.get(code, {}))
    s.update((getattr(project, "code_settings", {}) or {}).get(code, {}))
    return s


def seismic(code: str, s: dict) -> dict:
    """Peak ground acceleration and pseudo-static kh for the code settings."""
    if code == "AS":
        Z = float(s.get("Z") or AS1170_Z.get(s.get("city"), 0.08))
        kp = AS1170_KP.get(s.get("probability", "1/500"), 1.0)
        kpz = max(kp * Z, AS1170_KPZ_MIN)
        site, ch0 = AS1170_SITE.get(s.get("site", "De"), ("", 1.0))
        pga = kpz * ch0
        frac = float(s.get("kh_fraction", 0.5))
        return {"pga": pga, "kh": frac * pga,
                "text": f"AS 1170.4: kp = {kp:g}, Z = {Z:g} g, kpZ = {kpz:.3f} (not less than {AS1170_KPZ_MIN}), "
                        f"site class {s.get('site', 'De')} ({site}) Ch(0) = {ch0:g}: PGA = {pga:.3f} g; "
                        f"kh = {frac:g} x PGA = {frac * pga:.3f}"}
    if code == "BNBC":
        zone = int(s.get("zone") or BNBC_CITIES.get(s.get("city"), 2))
        Z = BNBC_ZONES.get(zone, 0.20)
        site, S = BNBC_SITE.get(s.get("site", "SD"), ("", 1.0))
        I = BNBC_IMPORTANCE.get(s.get("importance", "II"), 1.0)
        pga = 2.0 / 3.0 * Z * I * S
        frac = float(s.get("kh_fraction", 0.5))
        return {"pga": pga, "kh": frac * pga,
                "text": f"BNBC 2020: seismic zone {zone}, Z = {Z:g} g, site class {s.get('site', 'SD')} ({site}) "
                        f"S = {S:g}, importance I = {I:g}: design PGA = 2/3 Z I S = {pga:.3f} g; "
                        f"kh = {frac:g} x PGA = {frac * pga:.3f}"}
    return {"pga": 0.0, "kh": 0.0, "text": "No code selected: enter kh yourself."}


def design_case(analysis, setting: str = "auto") -> str:
    if setting and setting != "auto":
        return setting
    if getattr(analysis, "rapid_drawdown", False) or "drawdown" in analysis.name.lower():
        return "drawdown"
    if abs(analysis.kh) > 0 or abs(analysis.kv) > 0:
        return "earthquake"
    text = (analysis.name + " " + analysis.description).lower()
    if any(w in text for w in ("temporary", "construction", "short term", "short-term", "undrained")):
        return "temporary"
    return "long_term"


def required_fos(code: str, case: str, s: dict | None = None) -> float:
    s = s or {}
    if f"min_{case}" in s:
        return float(s[f"min_{case}"])
    return MIN_FOS.get(code, MIN_FOS["none"])[case]


def check_slope(project, analysis, factored: bool = True) -> dict:
    """Check one solved slope analysis against the selected code."""
    code = code_of(project)
    s = settings_of(project)
    r = analysis.results
    if not r or not r.get("critical"):
        raise ValueError(f"Solve '{analysis.name}' first.")
    F = float(r["critical"]["fos"])
    case = design_case(analysis, s.get("case", "auto"))
    need = required_fos(code, case, s)
    out = {"analysis": analysis.name, "code": code, "case": case, "case_label": CASES[case], "fos": F,
           "required": need, "pass": F >= need - 1e-9, "source": MIN_FOS_SOURCE[code], "rows": []}
    out["rows"].append({"check": f"Factor of safety, {CASES[case].lower()}", "value": F, "limit": f">= {need:g}",
                        "pass": out["pass"]})
    if code == "AS" and factored and case != "drawdown":
        cl = AS4678_CLASSES.get(s.get("soil_class", "II"), AS4678_CLASSES["II"])
        phi_uc = float(s.get("phi_uc", cl["phi_uc"]))
        phi_uphi = float(s.get("phi_uphi", cl["phi_uphi"]))
        lf = float(s.get("live_factor", AS4678_LOAD["live"]))
        try:
            from .whatif import SurfacePool
            pool = SurfacePool(project, analysis)
            Ff = pool.fos({"c_factor": phi_uc, "tanphi_factor": phi_uphi, "load_factor": lf})
            out["factored_fos"] = Ff
            out["rows"].append({"check": f"AS 4678 limit state: c' x {phi_uc:g}, tan phi' x {phi_uphi:g}, "
                                         f"live load x {lf:g}", "value": Ff, "limit": ">= 1.0",
                                "pass": Ff >= 1.0 - 1e-9})
        except ValueError as e:
            out["rows"].append({"check": "AS 4678 limit state", "value": None, "limit": ">= 1.0", "pass": None,
                                "note": str(e)})
    if case == "earthquake" and code != "none":
        sz = seismic(code, s)
        used = abs(analysis.kh)
        ok = used >= sz["kh"] - 1e-6
        out["rows"].append({"check": f"Seismic coefficient used (kh = {used:.3f})", "value": used,
                            "limit": f">= {sz['kh']:.3f}", "pass": ok, "note": sz["text"]})
    out["pass_all"] = all(row["pass"] is not False for row in out["rows"])
    return out


def check_bearing(project, analysis, q_applied: float, q_ultimate: float) -> dict:
    code = code_of(project)
    b = dict(BEARING[code])
    s = settings_of(project)
    if "bearing_value" in s:
        b["value"] = float(s["bearing_value"])
    if b["kind"] == "phi_g":
        cap = b["value"] * q_ultimate
        ok = q_applied <= cap
        text = f"{b['label']} = {b['value']:g}: design capacity {cap:.1f} >= applied {q_applied:.1f}"
    else:
        cap = q_ultimate / b["value"]
        ok = q_applied <= cap
        text = f"{b['label']} = {b['value']:g}: allowable {cap:.1f} >= applied {q_applied:.1f}"
    return {"code": code, "applied": q_applied, "ultimate": q_ultimate, "capacity": cap, "pass": ok, "text": text}


def check_project(project) -> list[dict]:
    """Check every solved slope analysis. Analyses that are not solved are listed with a note."""
    out = []
    for a in project.analyses:
        if a.kind != "slope":
            continue
        if not a.results or not a.results.get("critical"):
            out.append({"analysis": a.name, "error": "not solved"})
            continue
        try:
            out.append(check_slope(project, a))
        except ValueError as e:
            out.append({"analysis": a.name, "error": str(e)})
    return out


def summary_text(project, checks: list[dict] | None = None) -> str:
    code = code_of(project)
    checks = check_project(project) if checks is None else checks
    L = [f"Design code: {CODES[code]}", ""]
    for c in checks:
        if "error" in c:
            L.append(f"{c['analysis']}: {c['error']}")
            continue
        L.append(f"{c['analysis']}  [{c['case_label']}]  -  {'PASS' if c['pass_all'] else 'FAIL'}")
        for row in c["rows"]:
            v = "-" if row["value"] is None else f"{row['value']:.3f}"
            mark = {True: "pass", False: "FAIL", None: "n/a"}[row["pass"]]
            L.append(f"   {row['check']}: {v} (needs {row['limit']})  {mark}")
            if row.get("note"):
                L.append(f"      {row['note']}")
        L.append("")
    L.append(f"Minimum factors of safety: {MIN_FOS_SOURCE[code]}. The project specification and the standard "
             "itself govern; edit the values in Design > Design Code Settings.")
    return "\n".join(L)


def fmt_pct(x):
    return f"{100 * x:.1f} %" if x is not None and math.isfinite(x) else "-"
