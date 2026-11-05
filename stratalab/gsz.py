"""Import and export of GeoStudio project files (.gsz), for exchanging models with GeoStudio.

A .gsz file is a zip archive holding the project XML (<GSIData>) and, when solved, result files.
Reading covers geometry (points, lines, regions, interior meshed lines), materials and their region
assignments, analyses (kind, method, parent, duration, time steps) and boundary conditions with the
analyses that use them. Writing covers the geometry, materials, in situ and consolidation stress analyses and their
fixed / load / drainage boundaries. Results are not read.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from .model import MATERIAL_COLORS, Project, new_project

GSZ_VERSION = "11.12"
GSZ_APP = "25.2.1.39"

# GeoStudio-style property names -> StrataLab Material attributes (matched case-insensitively)
MATERIAL_PROPS = {
    "unitweight": "unit_weight", "cohesion": "cohesion", "cohesionprime": "cohesion", "c": "cohesion",
    "phi": "phi", "phiprime": "phi", "phib": "phi_b", "ksat": "k_sat", "satkx": "k_sat", "kx": "k_sat",
    "kykx": "k_ratio", "kyprimekx": "k_ratio", "emodulus": "E", "youngsmodulus": "E", "e": "E",
    "poissonsratio": "nu", "poisson": "nu", "nu": "nu",
}


def _local(tag):
    return tag.split("}")[-1]


def _text(el, name, default=None):
    for c in el:
        if _local(c.tag).lower() == name.lower():
            return (c.text or "").strip()
    return el.attrib.get(name, default)


def _num(v):
    try:
        return float(str(v).split("(")[0].replace("Value=", ""))
    except (TypeError, ValueError):
        return None


STRESS_MODEL_MAP = {"linearelastic": "linear_elastic", "elasticplastic": "elastic_plastic", "mohrcoulomb":
                    "elastic_plastic", "modifiedcamclay": "cam_clay", "camclay": "cam_clay",
                    "hyperbolic": "hyperbolic", "none": "none"}
SEEP_MODEL_MAP = {"satonly": "saturated", "saturatedonly": "saturated", "satunsat": "van_genuchten",
                  "saturatedunsaturated": "van_genuchten"}
SLOPE_MODEL_MAP = {"mohrcoulomb": "mohr_coulomb", "undrained": "undrained", "undrainedphi0": "undrained",
                   "bedrock": "bedrock", "impenetrable": "bedrock", "highstrength": "high_strength",
                   "shansep": "shansep", "bilinear": "bilinear", "hoekbrown": "hoek_brown",
                   "generalizedhoekbrown": "hoek_brown", "anisotropicstrength": "anisotropic"}
# GeoStudio property element / attribute names -> Material attributes (case-insensitive)
MATERIAL_PROPS.update({
    "youngsprimemodulus": "E", "youngsmodulus": "E", "effectivepoissonsratio": "nu", "initvoidratio": "e0",
    "ocratio": "ocr", "kyxratio": "k_ratio", "ksat": "k_sat", "cohesionprime": "cohesion", "phiprime": "phi",
    "dilationangle": "psi", "lambda": "cc_lambda", "kappa": "cc_kappa", "volwc": "theta_s", "beta": "mv",
})
SLOPE_METHOD_MAP = {"ordinary": "ordinary", "bishop": "bishop", "janbu": "janbu", "spencer": "spencer",
                    "morgensternprice": "morgenstern_price", "morgenstern-price": "morgenstern_price",
                    "gle": "morgenstern_price", "corpsofengineers1": "corps1", "corpsofengineers2": "corps2",
                    "lowekarafiath": "lowe_karafiath", "sarma": "sarma"}


def _read_xml(path):
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist() if n.lower().endswith(".xml")]
        if not names:
            raise ValueError(f"{Path(path).name} contains no GeoStudio XML document.")
        top = [n for n in names if "/" not in n]          # the project document sits at the top level
        return ET.fromstring(z.read((top or names)[0]))


def _children(el, name):
    return [c for c in el if _local(c.tag) == name] if el is not None else []


def _find(el, name):
    for c in el.iter():
        if _local(c.tag) == name:
            return c
    return None


def _func(s):
    """Parse 'Name(Key=Value,Key=Value)' into (name, {key: value})."""
    if not s or "(" not in s:
        return (s or "").strip(), {}
    name, rest = s.split("(", 1)
    args = {}
    for part in rest.rstrip(")").split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            args[k.strip()] = v.strip()
    return name.strip(), args


def _material(p, el):
    name = _text(el, "Name") or "Material"
    m = p.add_material(name)
    for c in el.iter():
        if c is el:
            continue
        if c.attrib.get("Missing") == "true":
            continue
        key = _local(c.tag).lower()
        attr = MATERIAL_PROPS.get(key)
        val = _num(c.text)
        if attr and val is not None:
            setattr(m, attr, val)
        for akey, aval in c.attrib.items():
            attr = MATERIAL_PROPS.get(akey.lower())
            if attr and _num(aval) is not None:
                setattr(m, attr, _num(aval))
    sm = (_text(el, "StressModel") or "").lower()
    m.stress_model = STRESS_MODEL_MAP.get(sm, m.stress_model)
    seep = (_text(el, "SeepModel") or "").lower()
    m.hyd_model = SEEP_MODEL_MAP.get(seep, m.hyd_model)
    slope = (_text(el, "SlopeModel") or "").lower()
    if slope in SLOPE_MODEL_MAP:
        m.model = SLOPE_MODEL_MAP[slope]
    color = _text(el, "Color")
    if color and color.startswith("RGB="):
        try:
            r, g, b = (int(v) for v in color[5:-1].split(","))
            m.color = f"#{r:02x}{g:02x}{b:02x}"
        except ValueError:
            pass
    return m


def _analysis(p, el):
    name = _text(el, "Name") or "Analysis"
    kind_g = (_text(el, "Kind") or "").upper()
    method = (_text(el, "Method") or "").lower()
    if kind_g.startswith("SIGMA"):
        kind = "stress"
    elif kind_g.startswith("SEEP"):
        kind = "seepage"
    elif kind_g.startswith("SLOPE"):
        kind = "slope"
    elif kind_g.startswith("QUAKE"):
        kind = "dynamic"
    elif kind_g.startswith("TEMP"):
        kind = "thermal"
    elif kind_g.startswith("CTRAN"):
        kind = "transport"
    elif kind_g.startswith("AIR"):
        kind = "air"
    else:
        kind = "slope"
    a = p.add_analysis(name, kind)
    ti = _find(el, "TimeIncrements")
    dur = _num(_text(ti, "Duration")) if ti is not None else None
    n = _num(_text(ti, "IncrementCount")) if ti is not None else None
    if dur:
        a.duration = dur
        a.transient = True
    if n:
        a.n_steps = int(n)
    if kind == "stress":
        a.stress_type = ("consolidation" if "consolidation" in method else
                         "insitu" if "insitu" in method else "load")
        a.transient = False
    if kind == "seepage" and "steady" in method:
        a.transient = False
    if kind == "slope":
        a.method = SLOPE_METHOD_MAP.get(method.replace(" ", ""), a.method)
    return a


def _bc_types(bc_el):
    """StrataLab boundary types for one GeoStudio boundary definition: {physics: (type, value, extra)}."""
    out = {}
    hyd = bc_el.attrib.get("Hydraulic")
    if hyd:
        f, args = _func(hyd)
        v = _num(args.get("Value", 0)) or 0.0
        review = args.get("Review", "false").lower() == "true"
        if f == "HydPressureHead":
            out["hydraulic"] = ("pressure_head", v)
        elif f == "HydTotalHead":
            out["hydraulic"] = ("head", v)
        elif f == "HydTotalFlux":
            out["hydraulic"] = ("seepage_face", 0.0) if review and v == 0 else ("nodal_flux", v)
        elif f in ("HydUnitFlux", "HydUnitNetFlux"):
            out["hydraulic"] = ("infiltration", v) if review else ("flux", v)
    fx, ax = _func(bc_el.attrib.get("XDisp", ""))
    fy, ay = _func(bc_el.attrib.get("YDisp", ""))
    if fx.startswith("DispNormTan") or fy.startswith("DispNormTan"):
        args = ax if fx.startswith("DispNormTan") else ay
        out["stress"] = ("pressure", _num(args.get("DispNorm", 0)) or 0.0)
        tan = _num(args.get("DispTan", 0)) or 0.0
        if tan:
            out["stress_shear"] = ("shear", tan)
    else:
        xfix = fx == "DispDisplacementX" and (_num(ax.get("Value", 0)) or 0.0) == 0.0
        yfix = fy == "DispDisplacementY"
        yval = _num(ay.get("Value", 0)) or 0.0
        if xfix and yfix and yval == 0.0:
            out["stress"] = ("fixed_xy", 0.0)
        elif xfix:
            out["stress"] = ("fixed_x", 0.0)
        elif yfix:
            out["stress"] = ("fixed_y", 0.0) if yval == 0.0 else ("displacement_y", yval)
        elif fx == "ForceX" or fx.startswith("Force"):
            out["stress"] = ("force_x", _num(ax.get("Value", 0)) or 0.0)
    return out


def _xy(el):
    if el is None:
        return None
    x, y = _num(el.attrib.get("X")), _num(el.attrib.get("Y"))
    return None if x is None or y is None else (x, y)


def _slope_items(root, p, an_map):
    """Slope stability settings: piezometric line, pore pressure source and the slip surface search
    (entry and exit ranges with their increments, direction of movement)."""
    for sec in _children(root, "WaterItems"):
        for item in _children(sec, "WaterItem"):
            a = p.analysis(an_map.get(_text(item, "AnalysisID")))
            opt = (_text(_find(item, "ResultInputInfo"), "Option") or "").lower() if _find(item, "ResultInputInfo") is not None else ""
            if a is None:
                continue
            if "piezo" in opt:
                a.pwp = "piezometric"
            elif "parent" in opt or "analysis" in opt:
                a.pwp = "seepage"
    for sec in _children(root, "StabilityItems"):
        for item in _children(sec, "StabilityItem"):
            a = p.analysis(an_map.get(_text(item, "AnalysisID")))
            entry = _find(item, "Entry")
            if a is None or entry is None:
                continue
            data = {}
            for dps in _children(entry, "DataPoints"):
                for dp in _children(dps, "DataPoint"):
                    xy = _xy(dp)
                    if xy:
                        data[dp.attrib.get("Number")] = list(xy)
            surfaces = [ps for sec2 in _children(entry, "PiezometricSurfaces") for ps in _children(sec2, "PiezometricSurface")]
            if surfaces and not p.piezometric_line:
                refs = [d.text.strip() for d in _find(surfaces[0], "DataPoints") if d.text and d.text.strip()]
                line = [data[r] for r in refs if r in data]
                if len(line) >= 2:
                    p.piezometric_line = sorted(line)
            if a.kind != "slope":
                continue
            slip = _find(entry, "SlipSurface")
            if slip is None:
                continue
            right_to_left = (_text(slip, "DirectionOfSlip") or "RightToLeft").lower() != "lefttoright"
            ee = _find(slip, "EntryExit")
            if ee is not None:
                l1, l2 = _xy(_find(ee, "LeftSideLeftPt")), _xy(_find(ee, "LeftSideRightPt"))
                r1, r2 = _xy(_find(ee, "RightSideLeftPt")), _xy(_find(ee, "RightSideRightPt"))
                li, ri = _num(_text(ee, "LeftInc")), _num(_text(ee, "RightInc"))
                if l1 and l2 and r1 and r2:
                    left, right = sorted((l1[0], l2[0])), sorted((r1[0], r2[0]))
                    entry_r, exit_r = (right, left) if right_to_left else (left, right)
                    entry_i, exit_i = (ri, li) if right_to_left else (li, ri)
                    st = a.search
                    st.mode = "entry_exit"
                    st.entry_x1, st.entry_x2 = entry_r
                    st.exit_x1, st.exit_x2 = exit_r
                    # GeoStudio counts increments (gaps); StrataLab counts points
                    st.n_entry = int(entry_i or 8) + 1
                    st.n_exit = int(exit_i or 8) + 1
                    st.n_radius = int(_num(_text(ee, "RadiusInc")) or 4) + 1
            seis = _find(entry, "Seismic")
            if seis is not None:
                a.kh = _num(seis.attrib.get("Horizontal")) or 0.0
                a.kv = _num(seis.attrib.get("Vertical")) or 0.0


def read_gsz(path) -> Project:
    """Read a GeoStudio .gsz project: geometry, materials and region assignments, analyses (with
    parents, durations and time steps) and boundary conditions (with the analyses that use them)."""
    try:
        root = _read_xml(path)
    except zipfile.BadZipFile as e:
        raise ValueError(f"{Path(path).name} is not a GeoStudio .gsz file (not a zip archive).") from e
    if _local(root.tag) != "GSIData":
        raise ValueError(f"{Path(path).name} is not a GeoStudio project (root element {root.tag}).")
    units = "metric"
    eng = _find(root, "EngCoords")
    if eng is not None and eng.attrib.get("UnitSystem", "Metric").lower().startswith("imp"):
        units = "imperial"
    p = new_project(units)
    p.materials, p.analyses = [], []
    info = _find(root, "FileInfo")
    p.title = (info.attrib.get("Title") if info is not None else None) or Path(path).stem
    p.author = info.attrib.get("Author", "") if info is not None else ""
    p.description = f"Imported from GeoStudio file {Path(path).name}"

    geoms = [g for g in root.iter() if _local(g.tag) == "Geometry"]
    if not geoms:
        raise ValueError("The file contains no geometry.")
    geom = geoms[0]
    pts = {}
    for section in _children(geom, "Points"):
        for el in section:
            if "X" in el.attrib and "Y" in el.attrib:
                pts[el.attrib["ID"]] = [float(el.attrib["X"]), float(el.attrib["Y"])]
    lines = {}
    for section in _children(geom, "Lines"):
        for el in section:
            a, b = _text(el, "PointID1"), _text(el, "PointID2")
            if a in pts and b in pts:
                flag = lambda k: (_text(el, k) or el.attrib.get(k, "")).lower() == "true"
                lines[_text(el, "ID")] = (a, b, flag("IsMeshed") or flag("Pinned"))
    region_els = [r for sec in _children(geom, "Regions") for r in _children(sec, "Region")]
    if not pts or not region_els:
        raise ValueError("The file has no regions to import.")

    # materials and analyses
    mat_map = {}
    for sec in _children(root, "Materials"):
        for el in _children(sec, "Material"):
            mat_map[_text(el, "ID") or str(len(mat_map) + 1)] = _material(p, el).id
    an_map = {}
    parents = {}
    for sec in _children(root, "Analyses"):
        for el in _children(sec, "Analysis"):
            a = _analysis(p, el)
            an_map[_text(el, "ID")] = a.id
            if _text(el, "ParentID"):
                parents[a.id] = _text(el, "ParentID")
    for aid, pid in parents.items():
        if pid in an_map:
            p.analysis(aid).parent_id = an_map[pid]
            child, parent = p.analysis(aid), p.analysis(an_map[pid])
            if child.kind == "seepage" and parent.kind == "seepage":
                child.initial = "parent"

    _slope_items(root, p, an_map)

    # region materials: direct reference, or the analysis contexts (first one that assigns it)
    contexts = [c for sec in _children(root, "Contexts") for c in _children(sec, "Context")]
    region_mat = {}
    for ctx in contexts:
        for use in ctx.iter():
            if _local(use.tag) == "GeometryUsesMaterial" and use.attrib.get("ID", "").startswith("Regions-"):
                region_mat.setdefault(use.attrib["ID"].split("-", 1)[1], use.attrib.get("Entry"))
    default_mat = None
    region_edges = set()
    for r in region_els:
        rid = _text(r, "ID")
        ids = [s.strip() for s in (_text(r, "PointIDs") or "").split(",") if s.strip()]
        poly = [pts[i] for i in ids if i in pts]
        if len(poly) < 3:
            continue
        for a_, b_ in zip(ids, ids[1:] + ids[:1]):
            region_edges.add(frozenset((a_, b_)))
        mref = _text(r, "MaterialID") or _text(r, "Material") or region_mat.get(rid)
        mid = mat_map.get(mref) if mref else None
        if mid is None:
            if default_mat is None:
                default_mat = p.add_material("Soil (unassigned in GeoStudio)")
            mid = default_mat.id
        area = sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1]
                   for i in range(len(poly)))
        p.add_region(poly if area > 0 else list(reversed(poly)), mid)
    if not p.regions:
        raise ValueError("No region in the file has three or more points.")
    # interior lines (drains, internal boundaries) become lines the mesh follows
    for lid, (a_, b_, meshed) in lines.items():
        if frozenset((a_, b_)) not in region_edges and meshed:
            p.mesh_lines.append([pts[a_], pts[b_]])

    # boundary conditions: definitions + which lines use them in which analyses
    defs = {el.attrib.get("ID"): el for sec in _children(root, "BCs") for el in _children(sec, "BC")}
    uses = {}                                   # (bc id, line id, physics) -> set of analysis ids
    for ctx in contexts:
        aid = an_map.get(_text(ctx, "AnalysisID"))
        if aid is None:
            continue
        for use in ctx.iter():
            tag = _local(use.tag)
            if not tag.startswith("GeometryUses") or not tag.endswith("BC"):
                continue
            ref = use.attrib.get("ID", "")
            if not ref.startswith("Lines-"):
                continue
            physics = "hydraulic" if "Hydraulic" in tag else "stress"
            uses.setdefault((use.attrib.get("Entry"), ref.split("-", 1)[1], physics), set()).add(aid)
    all_ids = {a.id for a in p.analyses}
    for (bid, lid, physics), aids in sorted(uses.items(), key=lambda t: (int(t[0][1]), t[0][0])):
        el = defs.get(bid)
        if el is None or lid not in lines:
            continue
        types = _bc_types(el)
        a_, b_, _m = lines[lid]
        pts_line = [pts[a_], pts[b_]]
        for key in ([physics] + (["stress_shear"] if physics == "stress" else [])):
            if key not in types:
                continue
            typ, val = types[key]
            p.add_bc(f"{el.attrib.get('Name', 'BC')} (line {lid})", typ, val, pts_line,
                     analyses=[] if aids == all_ids else sorted(aids))
    for i, m in enumerate(p.materials):
        if m.color == "#d9c49c" and i:
            m.color = MATERIAL_COLORS[i % len(MATERIAL_COLORS)]
    if not p.analyses:
        p.add_analysis("Slope Stability", "slope")
    return p


STRESS_MODEL_OUT = {"linear_elastic": "LinearElastic", "elastic_plastic": "ElasticPlastic", "none": "None"}
SEEP_MODEL_OUT = {"saturated": "SatOnly"}
METHOD_OUT = {"insitu": "Insitu2", "consolidation": "Consolidation"}
SLOPE_MODEL_OUT = {"mohr_coulomb": "MohrCoulomb"}
SLOPE_METHOD_OUT = {"ordinary": "Ordinary", "bishop": "Bishop", "janbu": "Janbu", "spencer": "Spencer",
                    "morgenstern_price": "Morgenstern-Price"}


def _bc_attrs(bc):
    """GeoStudio boundary definition attributes for a StrataLab boundary condition, or None."""
    v = f"{bc.value:.12g}"
    t = bc.type
    if t == "fixed_x":
        return {"XDisp": "DispDisplacementX(Variability=Constant,Value=0)", "YDisp": "ForceDispUndefined()"}
    if t == "fixed_y":
        return {"XDisp": "ForceDispUndefined()", "YDisp": "DispDisplacementY(Variability=Constant,Value=0)"}
    if t == "fixed_xy":
        return {"XDisp": "DispDisplacementX(Variability=Constant,Value=0)",
                "YDisp": "DispDisplacementY(Variability=Constant,Value=0)"}
    if t == "displacement_y":
        return {"XDisp": "ForceDispUndefined()", "YDisp": f"DispDisplacementY(Variability=Constant,Value={v})"}
    if t == "pressure":
        return {"XDisp": f"DispNormTanX(VariabilityNorm=Constant,DispNorm={v},VariabilityTan=Constant,DispTan=0)",
                "YDisp": "DispNormTanY(VariabilityNorm=Constant,DispNorm=0,VariabilityTan=Constant,DispTan=0)"}
    if t == "pressure_head":
        return {"Hydraulic": f"HydPressureHead(Variability=Constant,Value={v})"}
    if t == "head":
        return {"Hydraulic": f"HydTotalHead(Variability=Constant,Value={v})"}
    if t == "seepage_face":
        return {"Hydraulic": "HydTotalFlux(Variability=Constant,Value=0,Review=true)"}
    return None


def _edges_on(bc_points, edges, pts_xy, tol):
    from .geometry import dist_point_polyline
    out = []
    for lid, (a, b) in edges.items():
        pa, pb = pts_xy[a], pts_xy[b]
        mid = ((pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2)
        if all(dist_point_polyline(x, y, bc_points) <= tol for x, y in (pa, pb, mid)):
            out.append(lid)
    return out


def _write_model(root, project, region_ids, lines, points):
    """Materials, analyses, boundary definitions and per-analysis contexts (stress / consolidation
    analyses and their boundaries). Returns a list of items that could not be written."""
    skipped = []
    mats = ET.SubElement(root, "Materials", Len=str(len(project.materials)))
    for m in project.materials:
        el = ET.SubElement(mats, "Material")
        ET.SubElement(el, "ID").text = str(m.id)
        r, g, b = (int(m.color[i:i + 2], 16) for i in (1, 3, 5))
        ET.SubElement(el, "Color").text = f"RGB=({r},{g},{b})"
        ET.SubElement(el, "Name").text = m.name
        ET.SubElement(el, "SeepModel").text = SEEP_MODEL_OUT.get(m.hyd_model, "SatOnly")
        uses_slope = any(a.kind == "slope" for a in project.analyses)
        ET.SubElement(el, "SlopeModel").text = SLOPE_MODEL_OUT.get(m.model, "MohrCoulomb") if uses_slope else "None"
        if uses_slope and m.model not in SLOPE_MODEL_OUT:
            skipped.append(f"material '{m.name}': strength model {m.model} written as Mohr-Coulomb")
        ET.SubElement(el, "StressModel").text = STRESS_MODEL_OUT.get(m.stress_model, "LinearElastic")
        ss = ET.SubElement(el, "StressStrain")
        for tag, val in (("UnitWeight", m.unit_weight), ("CohesionPrime", m.cohesion), ("PhiPrime", m.phi),
                         ("YoungsPrimeModulus", m.E), ("EffectivePoissonsRatio", m.nu), ("InitVoidRatio", m.e0)):
            ET.SubElement(ss, tag).text = f"{val:.12g}"
        ET.SubElement(el, "Hydraulic", KYXRatio=f"{m.k_ratio:.12g}", KSat=f"{m.k_sat:.12g}", Beta=f"{m.mv:.12g}")
        if m.stress_model not in STRESS_MODEL_OUT:
            skipped.append(f"material '{m.name}': stress model {m.stress_model} written as linear elastic")
    exported = [a for a in project.analyses if (a.kind == "stress" and a.stress_type in METHOD_OUT)
                or (a.kind == "slope" and a.method in SLOPE_METHOD_OUT)]
    skipped += [f"analysis '{a.name}' ({a.kind})" for a in project.analyses if a not in exported]
    ans = ET.SubElement(root, "Analyses", Len=str(len(exported)))
    ids = {a.id for a in exported}
    for a in exported:
        el = ET.SubElement(ans, "Analysis")
        ET.SubElement(el, "ID").text = str(a.id)
        ET.SubElement(el, "Name").text = a.name
        ET.SubElement(el, "Kind").text = "SLOPE/W" if a.kind == "slope" else "SIGMA/W"
        if a.parent_id in ids:
            ET.SubElement(el, "ParentID").text = str(a.parent_id)
        ET.SubElement(el, "Method").text = (SLOPE_METHOD_OUT[a.method] if a.kind == "slope"
                                            else METHOD_OUT[a.stress_type])
        ET.SubElement(el, "GeometryId").text = "1"
        ti = ET.SubElement(el, "TimeIncrements")
        if a.kind == "slope":
            ET.SubElement(ti, "Duration", Missing="true")
            ts = ET.SubElement(ti, "TimeSteps", Len="1")
            ET.SubElement(ts, "TimeStep", Save="true")
            ET.SubElement(el, "ComputedPhysics", SlopeStability="true")
        elif a.stress_type == "consolidation":
            ET.SubElement(ti, "Duration").text = f"{a.duration:.12g}"
            ET.SubElement(ti, "IncrementCount").text = str(a.n_steps)
            ts = ET.SubElement(ti, "TimeSteps", Len=str(a.n_steps))
            dt, t = a.duration / a.n_steps, 0.0
            for _ in range(a.n_steps):
                t += dt
                ET.SubElement(ts, "TimeStep", Step=f"{dt:.12g}", ElapsedTime=f"{t:.12g}", Save="true")
            ET.SubElement(el, "ComputedPhysics", WaterTransfer="true", Stress="true")
            ET.SubElement(el, "PhysicsOptions", CoupledConsolidation="true")
        else:
            ET.SubElement(ti, "Duration", Missing="true")
            ts = ET.SubElement(ti, "TimeSteps", Len="1")
            ET.SubElement(ts, "TimeStep", Save="true")
            ET.SubElement(el, "ComputedPhysics", Stress="true")
            ET.SubElement(el, "PhysicsOptions", GravityActivation="true")
    # boundary definitions and which lines use them in which analyses
    edges = {lid: (a, b) for lid, (a, b) in enumerate(lines, 1)}
    span = max((max(abs(x), abs(y)) for x, y in points.values()), default=1.0)
    defs, uses = [], []
    for bc in project.boundary_conditions:
        attrs = _bc_attrs(bc)
        if attrs is None:
            skipped.append(f"boundary '{bc.name}' ({bc.type})")
            continue
        on = _edges_on(bc.points, edges, points, 1e-9 * max(span, 1.0) + 1e-9)
        if not on:
            skipped.append(f"boundary '{bc.name}' (not on a geometry line)")
            continue
        defs.append((bc, attrs))
        aids = [aid for aid in (bc.analyses or [a.id for a in exported if a.kind == "stress"]) if aid in ids]
        uses.append((len(defs), "Hydraulic" in attrs, on, aids))
    bcs = ET.SubElement(root, "BCs", Len=str(len(defs)))
    for i, (bc, attrs) in enumerate(defs, 1):
        ET.SubElement(bcs, "BC", ID=str(i), Name=bc.name, Color="RGB=(192,0,0)", **attrs)
    ctxs = ET.SubElement(root, "Contexts", Len=str(len(exported)))
    for a in exported:
        ctx = ET.SubElement(ctxs, "Context")
        ET.SubElement(ctx, "AnalysisID").text = str(a.id)
        um = ET.SubElement(ctx, "GeometryUsesMaterials", Len=str(len(region_ids)))
        for i, r in enumerate(project.regions, 1):
            ET.SubElement(um, "GeometryUsesMaterial", ID=f"Regions-{i}", Entry=str(r.material_id))
        hyd = [(bid, lid) for bid, is_h, on, aids in uses if is_h and a.id in aids for lid in on]
        mech = [(bid, lid) for bid, is_h, on, aids in uses if not is_h and a.id in aids for lid in on]
        if a.stress_type == "consolidation" and hyd:
            h = ET.SubElement(ctx, "GeometryUsesHydraulicBCs", Len=str(len(hyd)))
            for bid, lid in hyd:
                ET.SubElement(h, "GeometryUsesHydraulicBC", ID=f"Lines-{lid}", Entry=str(bid))
        for comp in (("X", "Y") if mech else ()):
            c = ET.SubElement(ctx, f"GeometryUses{comp}DispBCs", Len=str(len(mech)))
            for bid, lid in mech:
                ET.SubElement(c, f"GeometryUses{comp}DispBC", ID=f"Lines-{lid}", Entry=str(bid))
        ET.SubElement(ctx, "IsDefined").text = "true"
    _write_slope_items(root, project, [a for a in exported if a.kind == "slope"])
    return skipped


def _write_slope_items(root, project, slopes):
    """Piezometric line, pore pressure source and entry/exit slip surface search of slope analyses."""
    if not slopes:
        return
    from .geometry import GroundProfile
    gp = GroundProfile(project.regions, samples=800)
    items = ET.SubElement(root, "StabilityItems", Len=str(len(slopes)))
    water = ET.SubElement(root, "WaterItems", Len=str(len(slopes)))
    piezo = project.piezometric_line if len(project.piezometric_line) >= 2 else []
    for a in slopes:
        it = ET.SubElement(items, "StabilityItem")
        ET.SubElement(it, "AnalysisID").text = str(a.id)
        entry = ET.SubElement(it, "Entry")
        if piezo:
            dps = ET.SubElement(entry, "DataPoints", Len=str(len(piezo)))
            for i, (x, y) in enumerate(piezo, 1):
                ET.SubElement(dps, "DataPoint", Number=str(i), X=_f(x), Y=_f(y))
        slip = ET.SubElement(entry, "SlipSurface")
        st = a.search
        e = sorted((st.entry_x1, st.entry_x2))
        x = sorted((st.exit_x1, st.exit_x2))
        if st.mode in ("entry_exit", "auto") and e != x:
            if st.mode == "auto" or e == [0.0, 0.0]:
                from .geometry import auto_entry_exit
                e, x = (sorted(r) for r in auto_entry_exit(project))
            right_to_left = e[0] > x[0]
            left, right = (x, e) if right_to_left else (e, x)
            linc, rinc = (st.n_exit, st.n_entry) if right_to_left else (st.n_entry, st.n_exit)
            ee = ET.SubElement(slip, "EntryExit")
            for tag, xv in (("LeftSideLeftPt", left[0]), ("LeftSideRightPt", left[1])):
                ET.SubElement(ee, tag, X=_f(xv), Y=_f(gp.ground(xv)))
            ET.SubElement(ee, "LeftInc").text = str(max(1, linc - 1))
            for tag, xv in (("RightSideLeftPt", right[0]), ("RightSideRightPt", right[1])):
                ET.SubElement(ee, tag, X=_f(xv), Y=_f(gp.ground(xv)))
            ET.SubElement(ee, "RightInc").text = str(max(1, rinc - 1))
            ET.SubElement(slip, "DirectionOfSlip").text = "RightToLeft" if right_to_left else "LeftToRight"
        if a.kh or a.kv:
            ET.SubElement(entry, "Seismic", Horizontal=_f(a.kh), Vertical=_f(a.kv))
        if piezo:
            ps = ET.SubElement(ET.SubElement(entry, "PiezometricSurfaces", Len="1"), "PiezometricSurface")
            ET.SubElement(ps, "ID").text = "1"
            refs = ET.SubElement(ps, "DataPoints", Len=str(len(piezo)))
            for i in range(1, len(piezo) + 1):
                ET.SubElement(refs, "DataPoint").text = str(i)
            uses = ET.SubElement(entry, "MaterialUsesPiezs", Len=str(len(project.materials)))
            for m in project.materials:
                ET.SubElement(uses, "MaterialUsesPiez", ID=str(m.id), UsesID="1")
        w = ET.SubElement(water, "WaterItem")
        ET.SubElement(w, "AnalysisID").text = str(a.id)
        we = ET.SubElement(w, "Entry")
        if a.pwp == "piezometric" and piezo:
            ET.SubElement(ET.SubElement(we, "ResultInputInfo"), "Option").text = "PiezoSurface"
        ET.SubElement(we, "UnitWaterWeight").text = _f(project.gamma_w)


def write_gsz(project: Project, path):
    """Write the project as a GeoStudio .gsz file. Returns a list of items that could not be written.

    Written: geometry (shared region vertices become shared points, each distinct edge one line),
    materials (stress and hydraulic properties), in situ and consolidation stress analyses, and
    fixed / load / drainage boundaries with the analyses that use them.
    """
    key = lambda x, y: (round(x, 9), round(y, 9))
    point_id: dict = {}
    points = []
    for r in project.regions:
        for x, y in r.points:
            k = key(x, y)
            if k not in point_id:
                point_id[k] = len(points) + 1
                points.append((x, y))
    lines, line_set = [], set()
    region_ids = []
    for r in project.regions:
        ids = [point_id[key(x, y)] for x, y in r.points]
        region_ids.append(ids)
        for a, b in zip(ids, ids[1:] + ids[:1]):
            e = (min(a, b), max(a, b))
            if e not in line_set and a != b:
                line_set.add(e)
                lines.append((a, b))
    interior = set()
    for line in getattr(project, "mesh_lines", []) or []:       # drains and other interior lines
        for (x1, y1), (x2, y2) in zip(line[:-1], line[1:]):
            ids = []
            for x, y in ((x1, y1), (x2, y2)):
                k = key(x, y)
                if k not in point_id:
                    point_id[k] = len(points) + 1
                    points.append((x, y))
                ids.append(point_id[k])
            a, b = ids
            e = (min(a, b), max(a, b))
            if e not in line_set and a != b:
                line_set.add(e)
                lines.append((a, b))
                interior.add(len(lines))
    xs = [p[0] for p in points] or [0.0]
    ys = [p[1] for p in points] or [0.0]
    span = max(max(xs) - min(xs), max(ys) - min(ys), 1.0)

    root = ET.Element("GSIData", Version=GSZ_VERSION, AppVersion=GSZ_APP)
    ET.SubElement(root, "FileInfo", FileVersion=GSZ_VERSION, AppVersion=GSZ_APP, RevNumber="1")
    coords = ET.SubElement(root, "Coordinates")
    ET.SubElement(coords, "EngCoords", HorzScale="200", VertScale="200", MaxSnapDist="20", LockScales="false",
                  UnitSystem="Imperial" if project.units == "imperial" else "Metric",
                  XPageLeft=_f(min(xs) - 0.2 * span), XPageRight=_f(max(xs) + 0.2 * span),
                  YPageBottom=_f(min(ys) - 0.2 * span), YPageTop=_f(max(ys) + 0.2 * span),
                  XPageOrg=_f(-min(xs) + 0.2 * span), YPageOrg=_f(-min(ys) + 0.2 * span))
    geoms = ET.SubElement(root, "Geometries", Len="1")
    g = ET.SubElement(geoms, "Geometry")
    ET.SubElement(g, "Name").text = "2D Geometry"
    pe = ET.SubElement(g, "Points", Len=str(len(points)))
    for i, (x, y) in enumerate(points, 1):
        ET.SubElement(pe, "Point", ID=str(i), X=_f(x), Y=_f(y))
    le = ET.SubElement(g, "Lines", Len=str(len(lines)))
    for i, (a, b) in enumerate(lines, 1):
        ln = ET.SubElement(le, "Line")
        ET.SubElement(ln, "ID").text = str(i)
        ET.SubElement(ln, "PointID1").text = str(a)
        ET.SubElement(ln, "PointID2").text = str(b)
        if i in interior:
            ET.SubElement(ln, "Pinned").text = "true"
            ET.SubElement(ln, "IsMeshed").text = "true"
    re_ = ET.SubElement(g, "Regions", Len=str(len(region_ids)))
    for i, ids in enumerate(region_ids, 1):
        rg = ET.SubElement(re_, "Region")
        ET.SubElement(rg, "ID").text = str(i)
        ET.SubElement(rg, "PointIDs").text = ",".join(str(v) for v in ids)
    ET.SubElement(g, "Precision").text = "6,6,7"
    skipped = _write_model(root, project, region_ids, lines, {i: pt for i, pt in enumerate(points, 1)})
    order = ["FileInfo", "Analyses", "BCs", "Contexts", "Coordinates", "Geometries", "Materials", "StabilityItems",
             "WaterItems"]
    kids = sorted(list(root), key=lambda e: order.index(e.tag) if e.tag in order else len(order))
    for k in list(root):
        root.remove(k)
    root.extend(kids)
    xml = ET.tostring(root, encoding="UTF-8", xml_declaration=True)
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(path.stem + ".xml", xml)
    tmp.replace(path)
    return skipped


def _f(v):
    return f"{float(v):.12g}"
