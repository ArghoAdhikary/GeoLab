"""AI slope builder: turns a plain-language description into a StrataLab project using Claude.

The API key is read from the ANTHROPIC_API_KEY environment variable or passed in
from the app's settings. The model reply is constrained to a JSON schema and then
validated like any user input before it becomes a project.
"""
from __future__ import annotations

import json

from .geometry import auto_entry_exit, polygon_area, validate_geometry
from .model import Project, Surcharge, new_project

MODEL = "claude-opus-5-5"

_POINT = {"type": "object", "additionalProperties": False, "required": ["x", "y"],
          "properties": {"x": {"type": "number"}, "y": {"type": "number"}}}

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["title", "description", "units", "materials", "regions", "piezometric_line",
                 "surcharges", "method", "pore_pressure", "ru", "seismic_kh", "assumptions"],
    "properties": {
        "title": {"type": "string"},
        "description": {"type": "string"},
        "units": {"type": "string", "enum": ["metric", "imperial"]},
        "materials": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["name", "model", "unit_weight", "cohesion", "phi"],
            "properties": {
                "name": {"type": "string"},
                "model": {"type": "string", "enum": ["mohr_coulomb", "undrained", "bedrock"]},
                "unit_weight": {"type": "number"},
                "cohesion": {"type": "number"},
                "phi": {"type": "number"},
            }}},
        "regions": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["material_index", "points"],
            "properties": {"material_index": {"type": "integer"}, "points": {"type": "array", "items": _POINT}}}},
        "piezometric_line": {"type": "array", "items": _POINT},
        "surcharges": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["x1", "x2", "q"],
            "properties": {"x1": {"type": "number"}, "x2": {"type": "number"}, "q": {"type": "number"}}}},
        "method": {"type": "string", "enum": ["ordinary", "bishop", "janbu", "spencer", "morgenstern_price"]},
        "pore_pressure": {"type": "string", "enum": ["none", "piezometric", "ru"]},
        "ru": {"type": "number"},
        "seismic_kh": {"type": "number"},
        "assumptions": {"type": "string"},
    },
}

SYSTEM = """You set up 2D slope stability models for a geotechnical engineering application.
Convert the user's description into a model that follows these rules:
- Coordinates are a 2D cross-section: x horizontal, y vertical (up). Use the requested units
  (metric: m, kN/m3, kPa; imperial: ft, pcf, psf). Default to metric.
- Regions are simple, non-overlapping polygons listed in order around their boundary. Adjacent
  regions must share exact vertex coordinates along common edges. Together they must form one
  continuous soil profile with a flat base, vertical left and right sides, and the ground surface on top.
- Extend the model well beyond the slope: at least 1.5x the slope height beyond the toe and crest,
  and at least 0.5x the slope height below the toe.
- material_index refers to the position in the materials list (0-based).
- Use typical published parameter values when the user does not give them, and list every
  assumption you made in "assumptions".
- Use a piezometric line (pore_pressure = "piezometric") only if the user mentions groundwater,
  a water table or saturation; it must span the full model width. Otherwise use "none".
- Use "morgenstern_price" unless the user names another method. seismic_kh is 0 unless an
  earthquake / seismic coefficient is mentioned. Surcharges are vertical pressures on the ground."""


class AIError(Exception):
    pass


def project_from_ai(data: dict) -> tuple[Project, str]:
    """Validate the model's JSON and build a project. Raises AIError with a readable message."""
    units = data.get("units", "metric")
    if units not in ("metric", "imperial"):
        raise AIError(f"Unknown unit system '{units}'.")
    p = new_project(units)
    p.materials.clear()
    p.title = data.get("title") or "AI slope"
    p.description = data.get("description", "")
    mats = data.get("materials") or []
    if not mats:
        raise AIError("The AI response contained no materials.")
    for m in mats:
        if m["unit_weight"] <= 0 or m["cohesion"] < 0 or not (0 <= m["phi"] < 90):
            raise AIError(f"Material '{m['name']}' has out-of-range properties.")
        p.add_material(m["name"][:40], model=m["model"], unit_weight=float(m["unit_weight"]),
                       cohesion=float(m["cohesion"]), phi=float(m["phi"]))
    regions = data.get("regions") or []
    if not regions:
        raise AIError("The AI response contained no regions.")
    for r in regions:
        k = r["material_index"]
        if not 0 <= k < len(p.materials):
            raise AIError(f"A region refers to material #{k}, which does not exist.")
        pts = [[float(q["x"]), float(q["y"])] for q in r["points"]]
        if len(pts) > 3 and pts[0] == pts[-1]:
            pts = pts[:-1]
        if polygon_area(pts) < 0:
            pts.reverse()
        p.add_region(pts, p.materials[k].id)
    problems = validate_geometry(p)
    if problems:
        raise AIError("The generated geometry is not valid: " + "; ".join(problems))
    a = p.analyses[0]
    a.method = data.get("method", "morgenstern_price")
    a.kh = float(data.get("seismic_kh", 0.0))
    piezo = [[float(q["x"]), float(q["y"])] for q in data.get("piezometric_line", [])]
    if data.get("pore_pressure") == "piezometric" and len(piezo) >= 2:
        p.piezometric_line = sorted(piezo)
        a.pwp = "piezometric"
    elif data.get("pore_pressure") == "ru":
        a.pwp, a.ru = "ru", float(data.get("ru", 0.0))
    for s in data.get("surcharges", []):
        p.surcharges.append(Surcharge(float(s["x1"]), float(s["x2"]), float(s["q"])))
    (e1, e2), (x1, x2) = auto_entry_exit(p)
    st = a.search
    st.mode, st.entry_x1, st.entry_x2, st.exit_x1, st.exit_x2 = "entry_exit", e1, e2, x1, x2
    return p, data.get("assumptions", "")


def generate_project(prompt: str, api_key: str | None = None, client=None) -> tuple[Project, str]:
    """Ask Claude for a model matching `prompt`. Returns (project, assumptions)."""
    if not prompt.strip():
        raise AIError("Describe the slope you want to model.")
    import anthropic
    if client is None:
        client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
    try:
        resp = client.beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}},
            system=SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.AuthenticationError as e:
        raise AIError("The API key was rejected. Check it under AI > Settings.") from e
    except anthropic.RateLimitError as e:
        raise AIError("Rate limited by the API. Wait a moment and try again.") from e
    except anthropic.APIStatusError as e:
        raise AIError(f"The API returned an error ({e.status_code}): {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise AIError("Could not reach the API. Check your internet connection.") from e
    if resp.stop_reason == "refusal":
        raise AIError("The request was declined by the model.")
    if resp.stop_reason == "max_tokens":
        raise AIError("The response was cut off. Try a simpler description.")
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise AIError("The AI response was not valid JSON.") from e
    return project_from_ai(data)
