"""Import and export of GeoStudio project files (.gsz), for exchanging models with GeoStudio.

A .gsz file is a zip archive holding one XML document (<GSIData>). The geometry part is read and
written: points, lines and regions (Geometries/Geometry/Points|Lines|Regions). Material names,
region-material assignments and common strength / hydraulic properties are read when present
(tolerantly, by element name). Analyses, boundary conditions and results are not exchanged.
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


def _read_xml(path):
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist() if n.lower().endswith(".xml")]
        if not names:
            raise ValueError(f"{Path(path).name} contains no GeoStudio XML document.")
        return ET.fromstring(z.read(names[0]))


def read_gsz(path) -> Project:
    """Read the geometry (and, when present, materials) of a GeoStudio .gsz file."""
    try:
        root = _read_xml(path)
    except zipfile.BadZipFile as e:
        raise ValueError(f"{Path(path).name} is not a GeoStudio .gsz file (not a zip archive).") from e
    if _local(root.tag) != "GSIData":
        raise ValueError(f"{Path(path).name} is not a GeoStudio project (root element {root.tag}).")
    units = "metric"
    eng = root.find(".//EngCoords")
    if eng is not None and eng.attrib.get("UnitSystem", "Metric").lower().startswith("imp"):
        units = "imperial"
    p = new_project(units)
    p.materials = []
    p.title = Path(path).stem
    p.description = f"Imported from GeoStudio file {Path(path).name}"

    # materials (tolerant: any <Material> element with a name / id)
    mat_ids = {}
    for el in root.iter():
        if _local(el.tag) != "Material":
            continue
        name = _text(el, "Name") or f"Material {len(mat_ids) + 1}"
        gid = _text(el, "ID") or str(len(mat_ids) + 1)
        if gid in mat_ids:
            continue
        m = p.add_material(name)
        for c in el.iter():
            key = _local(c.tag).lower()
            attr = MATERIAL_PROPS.get(key)
            val = _num(c.text) if c is not el else None
            if attr and val is not None:
                setattr(m, attr, val)
            for akey, aval in c.attrib.items():
                attr = MATERIAL_PROPS.get(akey.lower())
                if attr and _num(aval) is not None:
                    setattr(m, attr, _num(aval))
        color = el.attrib.get("Color") or _text(el, "Color")
        if color and color.startswith("RGB="):
            try:
                r, g, b = (int(v) for v in color[5:-1].split(","))
                m.color = f"#{r:02x}{g:02x}{b:02x}"
            except ValueError:
                pass
        mat_ids[gid] = m.id

    geoms = [g for g in root.iter() if _local(g.tag) == "Geometry"]
    if not geoms:
        raise ValueError("The file contains no geometry.")
    geom = geoms[0]
    pts = {}
    for section in geom:
        if _local(section.tag) == "Points":
            for el in section:
                if "X" in el.attrib and "Y" in el.attrib:
                    pts[el.attrib["ID"]] = [float(el.attrib["X"]), float(el.attrib["Y"])]
    regions_el = [r for r in geom.iter() if _local(r.tag) == "Region"]
    if not pts or not regions_el:
        raise ValueError("The file has no regions to import.")
    default_mat = None
    for r in regions_el:
        ids = [s.strip() for s in (_text(r, "PointIDs") or "").split(",") if s.strip()]
        poly = [pts[i] for i in ids if i in pts]
        if len(poly) < 3:
            continue
        mref = _text(r, "MaterialID") or _text(r, "Material")
        mid = mat_ids.get(mref) if mref else None
        if mid is None:
            if default_mat is None:
                default_mat = p.add_material("Soil (unassigned in GeoStudio)")
            mid = default_mat.id
        area = sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1]
                   for i in range(len(poly)))
        p.add_region(poly if area > 0 else list(reversed(poly)), mid)
    if not p.regions:
        raise ValueError("No region in the file has three or more points.")
    for i, m in enumerate(p.materials):
        if m.color == "#d9c49c" and i:
            m.color = MATERIAL_COLORS[i % len(MATERIAL_COLORS)]
    return p


def write_gsz(project: Project, path):
    """Write the project geometry as a GeoStudio .gsz file (points, lines, regions).

    Shared region vertices become shared GeoStudio points, and each distinct edge becomes one line.
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
    re_ = ET.SubElement(g, "Regions", Len=str(len(region_ids)))
    for i, ids in enumerate(region_ids, 1):
        rg = ET.SubElement(re_, "Region")
        ET.SubElement(rg, "ID").text = str(i)
        ET.SubElement(rg, "PointIDs").text = ",".join(str(v) for v in ids)
    ET.SubElement(g, "Precision").text = "6,6,7"
    xml = ET.tostring(root, encoding="UTF-8", xml_declaration=True)
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(path.stem + ".xml", xml)
    tmp.replace(path)


def _f(v):
    return f"{float(v):.12g}"
