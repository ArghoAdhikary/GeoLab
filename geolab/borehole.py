"""Borehole and CPT logs: read them from CSV or Excel, estimate soil parameters from SPT N or the cone
(published correlations), and build the cross-section (layers interpolated between the holes).

Borehole log (one row per layer):   hole, x, ground, top, bottom, soil, N, fc, pi, gamma
CPT log (one row per reading):      hole, x, ground, depth, qc, fs, u2
'top', 'bottom' and 'depth' are depths below the ground at the hole; 'ground' is the collar elevation and
'x' the position along the section. 'soil' is a name or a USCS group symbol (AS 1726 / ASTM D2487), e.g.
"Soft clay", "CH", "SM". Column names are matched loosely (case, spaces, units in brackets ignored).
"""
from __future__ import annotations

import csv
import io
import math
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from .liquefaction import GAMMA_W, PA

ALIASES = {
    "hole": ("hole", "borehole", "bh", "id", "name", "cpt", "test"),
    "x": ("x", "chainage", "offset", "distance", "station"),
    "ground": ("ground", "rl", "elevation", "collar", "groundlevel", "gl", "z", "surface"),
    "top": ("top", "from", "depthfrom", "topdepth"),
    "bottom": ("bottom", "to", "depthto", "bottomdepth", "base"),
    "depth": ("depth", "d"),
    "soil": ("soil", "description", "material", "uscs", "layer", "unit", "lithology", "stratum"),
    "N": ("n", "spt", "sptn", "nvalue", "blows", "n60"),
    "fc": ("fc", "fines", "finescontent", "fines%"),
    "pi": ("pi", "plasticityindex", "ip"),
    "gamma": ("gamma", "unitweight", "gammabulk", "bulkunitweight"),
    "qc": ("qc", "qt", "coneresistance"),
    "fs": ("fs", "sleevefriction", "friction"),
    "u2": ("u2", "u", "porepressure"),
}


def _key(name: str) -> str:
    name = re.sub(r"[\(\[].*?[\)\]]", "", name or "")
    return re.sub(r"[^a-z0-9%]", "", name.lower())


def _map_columns(header):
    out = {}
    for i, h in enumerate(header):
        k = _key(h)
        for field, names in ALIASES.items():
            if k in names and field not in out:
                out[field] = i
                break
    return out


def read_xlsx(path) -> list[list[str]]:
    """Rows of the first worksheet of an .xlsx file (values as text), without extra libraries."""
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(path) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", ns):
                shared.append("".join(t.text or "" for t in si.iter(f"{{{ns['m']}}}t")))
        sheets = sorted(n for n in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml$", n))
        if not sheets:
            raise ValueError("The Excel file has no worksheet.")
        root = ET.fromstring(z.read(sheets[0]))
    rows = []
    for row in root.iter(f"{{{ns['m']}}}row"):
        cells = {}
        for c in row.findall("m:c", ns):
            ref = c.get("r", "")
            col = 0
            for ch in re.match(r"[A-Z]+", ref).group(0) if ref else "A":
                col = col * 26 + ord(ch) - 64
            v = c.find("m:v", ns)
            t = c.get("t")
            if t == "s" and v is not None:
                val = shared[int(v.text)]
            elif t == "inlineStr":
                val = "".join(x.text or "" for x in c.iter(f"{{{ns['m']}}}t"))
            else:
                val = v.text if v is not None else ""
            cells[col - 1] = val
        if cells:
            rows.append([cells.get(i, "") for i in range(max(cells) + 1)])
    return rows


def read_table(path_or_text) -> list[list[str]]:
    p = Path(path_or_text) if not (isinstance(path_or_text, str) and "\n" in path_or_text) else None
    if p is not None and p.suffix.lower() in (".xlsx", ".xlsm"):
        return read_xlsx(p)
    text = p.read_text(encoding="utf-8-sig") if p is not None else path_or_text
    dialect = csv.Sniffer().sniff(text[:2000], delimiters=",;\t") if text.strip() else csv.excel
    return [r for r in csv.reader(io.StringIO(text), dialect) if any(c.strip() for c in r)]


def _num(v, default=None):
    try:
        f = float(str(v).strip().replace(",", "."))
        return f if math.isfinite(f) else default
    except (TypeError, ValueError):
        return default


def parse_logs(path_or_text) -> list[dict]:
    """Boreholes: [{"hole", "x", "ground", "kind": "borehole"|"cpt", "layers": [...] | "readings": [...]}]."""
    rows = read_table(path_or_text)
    if len(rows) < 2:
        raise ValueError("The file has no data rows.")
    cols = _map_columns(rows[0])
    is_cpt = "qc" in cols and "depth" in cols
    need = ("depth", "qc") if is_cpt else ("top", "bottom", "soil")
    missing = [n for n in need if n not in cols]
    if missing:
        raise ValueError("Missing column(s): " + ", ".join(missing) + ". A borehole log needs hole, x, ground, "
                         "top, bottom, soil (and N); a CPT log needs hole, x, ground, depth, qc, fs.")
    holes: dict[str, dict] = {}
    for r in rows[1:]:
        def g(name, default=None):
            i = cols.get(name)
            return r[i] if i is not None and i < len(r) else default
        name = str(g("hole", "BH1") or "BH1").strip() or "BH1"
        h = holes.setdefault(name, {"hole": name, "x": _num(g("x"), 0.0) or 0.0,
                                    "ground": _num(g("ground"), 0.0) or 0.0,
                                    "kind": "cpt" if is_cpt else "borehole", "layers": [], "readings": []})
        if is_cpt:
            qc = _num(g("qc"))
            d = _num(g("depth"))
            if qc is None or d is None:
                continue
            h["readings"].append({"depth": d, "qc": qc, "fs": _num(g("fs"), 0.0), "u2": _num(g("u2"), 0.0)})
        else:
            top, bot = _num(g("top")), _num(g("bottom"))
            if top is None or bot is None or bot <= top:
                continue
            h["layers"].append({"top": top, "bottom": bot, "soil": str(g("soil", "") or "Soil").strip(),
                                "N": _num(g("N")), "fc": _num(g("fc")), "pi": _num(g("pi")),
                                "gamma": _num(g("gamma"))})
    out = [h for h in holes.values() if h["layers"] or h["readings"]]
    if is_cpt:
        for h in out:
            h["readings"].sort(key=lambda t: t["depth"])
            qs = sorted(t["qc"] for t in h["readings"])
            if qs and qs[len(qs) // 2] < 100:          # cone resistance given in MPa
                for t in h["readings"]:
                    t["qc"] *= 1000.0
                    t["fs"] = (t["fs"] or 0) * 1000.0 if (t["fs"] or 0) < 2 else t["fs"]
                    t["u2"] = (t["u2"] or 0) * 1000.0 if abs(t["u2"] or 0) < 5 else t["u2"]
                h["qc_was_mpa"] = True
    else:
        for h in out:
            h["layers"].sort(key=lambda t: t["top"])
    if not out:
        raise ValueError("No usable rows were found.")
    return sorted(out, key=lambda h: h["x"])


# ---------------------------------------------------------------------------------------- soil types
FINE = re.compile(r"\b(clay|silt|peat|organic|mud|ch|cl|mh|ml|oh|ol|pt|cl-ml)\b", re.I)
CLAY = re.compile(r"\b(clay|peat|organic|mud|ch|cl|oh|ol|pt)\b", re.I)
ROCK = re.compile(r"\b(rock|bedrock|sandstone|shale|siltstone|granite|basalt|limestone|mudstone)\b", re.I)


def soil_type(name: str, pi=None) -> str:
    """'rock', 'clay' (fine-grained, plastic), 'silt' or 'sand' (granular, incl. gravel)."""
    if ROCK.search(name or ""):
        return "rock"
    if CLAY.search(name or "") or (pi is not None and pi >= 7):
        return "clay"
    if FINE.search(name or ""):
        return "silt"
    return "sand"


def from_spt(name: str, N: float | None, sve: float, fc=None, pi=None) -> dict:
    """Soil parameters from an SPT N60 value. Returns c, phi, gamma, k, Su, E and the source of each."""
    kind = soil_type(name, pi)
    if kind == "rock":
        return {"kind": kind, "model": "bedrock", "c": 0.0, "phi": 0.0, "gamma": 23.0, "k": 1e-8, "E": 5e5,
                "Su": None, "note": "rock: treated as impenetrable bedrock"}
    N = 10.0 if N is None else max(N, 0.0)
    if kind == "clay":
        su = 5.0 * N                                         # Stroud (1974), f1 about 5 for medium PI
        gamma = min(21.0, 16.0 + 0.1 * N)
        phi = 30.0 - 0.15 * min(pi or 25.0, 60.0) if pi is not None else 26.0
        return {"kind": kind, "model": "mohr_coulomb", "c": round(min(5.0 + 0.2 * N, 15.0), 1), "phi": round(phi, 1),
                "Su": su, "gamma": gamma, "k": 1e-9, "E": 400.0 * su,
                "note": f"clay: Su = 5 N = {su:.0f} kPa (Stroud); drained c', phi' typical for PI"}
    cn = min(1.7, math.sqrt(PA / max(sve, 1.0)))
    n160 = cn * N
    phi = min(45.0, math.sqrt(15.4 * n160) + 20.0)           # Hatanaka & Uchida (1996)
    gamma = min(21.0, 16.5 + 0.1 * N)
    fcv = fc if fc is not None else (40.0 if kind == "silt" else 8.0)
    k = 1e-4 if fcv < 5 else 2e-5 if fcv < 15 else 3e-6 if fcv < 35 else 5e-7 if fcv < 50 else 1e-7
    return {"kind": kind, "model": "mohr_coulomb", "c": 0.0 if kind == "sand" else 2.0, "phi": round(phi, 1),
            "Su": None, "gamma": gamma, "k": k, "E": 1000.0 * (7.0 + 0.5 * N) if kind == "sand" else 500.0 * (5 + N),
            "note": f"{kind}: (N1)60 = {n160:.1f}, phi' = sqrt(15.4 (N1)60) + 20 (Hatanaka & Uchida)"}


def from_cpt(qt: float, fs: float, sv: float, sve: float) -> dict:
    """Soil parameters from one cone reading (kPa)."""
    qnet = max(qt - sv, 1.0)
    Fr = 100 * fs / qnet
    n = 1.0
    for _ in range(50):
        Qtn = qnet / PA * (PA / sve) ** n
        Ic = math.sqrt((3.47 - math.log10(max(Qtn, 1e-6))) ** 2 + (math.log10(max(Fr, 1e-3)) + 1.22) ** 2)
        n2 = min(1.0, max(0.5, 0.381 * Ic + 0.05 * sve / PA - 0.15))
        if abs(n2 - n) < 1e-4:
            break
        n = n2
    Rf = max(100 * fs / max(qt, 1.0), 0.01)
    gamma = GAMMA_W * (0.27 * math.log10(Rf) + 0.36 * math.log10(max(qt, 1.0) / PA) + 1.236)
    k = 10 ** (0.952 - 3.04 * Ic) if Ic <= 4.0 else 10 ** (-4.52 - 1.37 * Ic)
    if Ic > 2.6:
        su = qnet / 14.0
        return {"kind": "clay", "Ic": Ic, "Su": su, "c": round(min(5 + su / 20, 15), 1), "phi": 25.0,
                "gamma": min(max(gamma, 14.0), 22.0), "k": k, "model": "mohr_coulomb"}
    phi = min(45.0, 17.6 + 11.0 * math.log10(max(Qtn, 1.0)))   # Kulhawy & Mayne (1990)
    return {"kind": "sand" if Ic < 2.05 else "silt", "Ic": Ic, "Su": None, "c": 0.0, "phi": round(phi, 1),
            "gamma": min(max(gamma, 15.0), 22.0), "k": k, "model": "mohr_coulomb"}


# --------------------------------------------------------------------------------- units and section
def _units(holes):
    """Soil units in order from the top, merged over all holes."""
    order: list[str] = []
    for h in holes:
        prev = -1
        for lay in h["layers"]:
            s = lay["soil"]
            if s in order:
                prev = max(prev, order.index(s))
            else:
                order.insert(prev + 1, s)
                prev += 1
    return order


def _cpt_layers(h, water_depth):
    """Split a CPT sounding into layers of the same soil behaviour type."""
    layers, cur = [], None
    sv = 0.0
    z0 = 0.0
    for t in h["readings"]:
        z = t["depth"]
        g = 18.0 if z <= water_depth else 19.0
        sv += g * (z - z0)
        z0 = z
        sve = max(sv - GAMMA_W * max(0.0, z - water_depth), 1.0)
        p = from_cpt(t["qc"], t["fs"] or 0.0, sv, sve)
        if cur is None or cur["kind"] != p["kind"]:
            if cur:
                cur["bottom"] = z
            cur = {"kind": p["kind"], "top": z if cur else 0.0, "soil": {"clay": "Clay (CPT)", "silt": "Silt (CPT)",
                                                                       "sand": "Sand (CPT)"}[p["kind"]],
                   "params": []}
            layers.append(cur)
        cur["params"].append(p)
        cur["bottom"] = z
    return layers


def unit_parameters(holes, water_depth: float = 2.0) -> dict:
    """Averaged parameters of each soil unit over all holes."""
    acc: dict[str, list] = {}
    for h in holes:
        if h["kind"] == "cpt":
            for lay in _cpt_layers(h, water_depth):
                acc.setdefault(lay["soil"], []).extend(lay["params"])
            continue
        sv = 0.0
        for lay in h["layers"]:
            mid = 0.5 * (lay["top"] + lay["bottom"])
            g = lay["gamma"] or 18.0
            sv_mid = sv + g * (mid - lay["top"])
            sve = max(sv_mid - GAMMA_W * max(0.0, mid - water_depth), 1.0)
            p = from_spt(lay["soil"], lay["N"], sve, lay["fc"], lay["pi"])
            if lay["gamma"]:
                p["gamma"] = lay["gamma"]
            acc.setdefault(lay["soil"], []).append(p)
            sv += g * (lay["bottom"] - lay["top"])
    out = {}
    for name, ps in acc.items():
        avg = lambda k: sum(p[k] for p in ps if p.get(k) is not None) / max(1, sum(1 for p in ps if p.get(k) is not None))
        out[name] = {"kind": ps[0]["kind"], "model": ps[0]["model"], "c": round(avg("c"), 1), "phi": round(avg("phi"), 1),
                     "gamma": round(avg("gamma"), 1),
                     "k": 10 ** (sum(math.log10(p["k"]) for p in ps) / len(ps)),
                     "Su": round(avg("Su"), 1) if any(p.get("Su") for p in ps) else None, "n": len(ps),
                     "note": ps[0].get("note", "")}
    return out


def build_section(holes, water_depth: float | None = 2.0, pad: float | None = None, units: str = "metric",
                  clay_undrained: bool = False, min_thickness: float = 0.1):
    """A GeoLab project with the layers of the holes interpolated along the section and one slope analysis
    (entry and exit set automatically). The water table is drawn water_depth below the ground (None: dry)."""
    from .examples import _auto_search
    from .model import MATERIAL_COLORS, new_project
    holes = sorted(holes, key=lambda h: h["x"])
    wd = 2.0 if water_depth is None else water_depth
    for h in holes:
        if h["kind"] == "cpt":
            h["layers"] = [{"top": l["top"], "bottom": l["bottom"], "soil": l["soil"]} for l in _cpt_layers(h, wd)]
    names = _units(holes)
    params = unit_parameters(holes, wd)
    p = new_project(units)
    p.materials.clear()
    p.title = "Section from " + ", ".join(h["hole"] for h in holes)
    mats = {}
    for i, n in enumerate(names):
        q = params.get(n, {"model": "mohr_coulomb", "c": 5, "phi": 30, "gamma": 18, "k": 1e-6, "Su": None})
        kw = dict(cohesion=q["c"], phi=q["phi"], unit_weight=q["gamma"], k_sat=q["k"],
                  color=MATERIAL_COLORS[i % len(MATERIAL_COLORS)])
        if q["model"] == "bedrock":
            kw.update(model="bedrock", cohesion=0.0, phi=0.0)
        elif clay_undrained and q.get("Su"):
            kw.update(model="undrained", cohesion=q["Su"], phi=0.0)
        mats[n] = p.add_material(n[:40], **kw)
    # boundary elevations of each unit at each hole: tops[i] = elevation of the top of unit i
    base_depth = max(l["bottom"] for h in holes for l in h["layers"])
    xs = [h["x"] for h in holes]
    span = (max(xs) - min(xs)) if len(xs) > 1 else 20.0
    pad = max(10.0, 0.5 * span) if pad is None else pad
    model_base = min(h["ground"] for h in holes) - base_depth
    bnd = []                          # per hole: [ground, bottom of unit 0, bottom of unit 1, ...]
    for h in holes:
        elev = [h["ground"]]
        by = {l["soil"]: l for l in h["layers"]}
        for n in names:
            lay = by.get(n)
            prev = elev[-1]
            if lay is None:
                elev.append(prev)
            else:
                elev.append(min(prev, h["ground"] - lay["bottom"]))
        elev[-1] = model_base
        bnd.append(elev)
    # x positions of the section: the ends plus each hole
    X = [min(xs) - pad] + xs + [max(xs) + pad]
    B = [bnd[0]] + bnd + [bnd[-1]]
    if len(holes) == 1:
        X = [xs[0] - pad, xs[0], xs[0] + pad]
        B = [bnd[0]] * 3
    # enforce a minimum thickness so that every polygon is valid
    nb = len(names) + 1
    for col in B:
        for j in range(1, nb):
            if j < nb - 1:
                col[j] = min(col[j], col[j - 1] - min_thickness)
            else:
                col[j] = min(col[j], col[j - 1] - min_thickness)
    lowest = min(col[-1] for col in B)
    for col in B:
        col[-1] = lowest
    for i, n in enumerate(names):
        top = [(x, col[i]) for x, col in zip(X, B)]
        bot = [(x, col[i + 1]) for x, col in zip(X, B)]
        poly = bot + list(reversed(top))
        p.add_region(_dedupe(poly), mats[n].id)
    if water_depth is not None:
        p.piezometric_line = [[x, col[0] - water_depth] for x, col in zip(X, B)]
        p.analyses[0].pwp = "piezometric"
    p.boreholes = holes
    p.description = "Built from borehole logs. Parameters from correlations: " + "; ".join(
        f"{n}: {params[n]['note']}" for n in names if n in params and params[n].get("note"))[:900]
    _auto_search(p, p.analyses[0])
    return p, params


def _dedupe(poly):
    out = []
    for q in poly:
        q = (float(q[0]), float(q[1]))
        if not out or abs(q[0] - out[-1][0]) > 1e-9 or abs(q[1] - out[-1][1]) > 1e-9:
            out.append(q)
    if len(out) > 2 and abs(out[0][0] - out[-1][0]) < 1e-9 and abs(out[0][1] - out[-1][1]) < 1e-9:
        out.pop()
    return out


def spt_rows_for_liquefaction(hole: dict) -> list[dict]:
    """Rows for liquefaction.spt from a borehole log (N at the middle of each layer)."""
    rows = []
    for lay in hole["layers"]:
        if lay.get("N") is None:
            continue
        rows.append({"depth": 0.5 * (lay["top"] + lay["bottom"]), "N": lay["N"], "fc": lay.get("fc") or 0.0,
                     "pi": lay.get("pi") if soil_type(lay["soil"], lay.get("pi")) != "clay" else (lay.get("pi") or 20),
                     "gamma": lay.get("gamma")})
    return rows


SAMPLE_BOREHOLES = """hole,x,ground,top,bottom,soil,N,fc,pi
BH1,0,12,0,3,Silty clay (CL),6,85,18
BH1,0,12,3,9,Silty sand (SM),12,25,
BH1,0,12,9,16,Dense sand (SP),35,5,
BH2,30,8,0,2,Silty clay (CL),5,85,18
BH2,30,8,2,7,Silty sand (SM),9,25,
BH2,30,8,7,14,Dense sand (SP),32,5,
BH3,60,6,0,1.5,Silty clay (CL),4,85,18
BH3,60,6,1.5,6,Silty sand (SM),8,25,
BH3,60,6,6,13,Dense sand (SP),30,5,
"""
