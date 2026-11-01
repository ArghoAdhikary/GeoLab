"""Project data model.

All geometry is 2D in the (x, y) plane with y pointing up. Values are stored in
the project's unit system (see UNIT_SYSTEMS); the solvers are unit-agnostic and
only need the unit weight of water from the unit system.
"""
from __future__ import annotations

import copy
from dataclasses import asdict, dataclass, field, fields
from typing import Any

UNIT_SYSTEMS: dict[str, dict[str, Any]] = {
    "metric": {
        "length": "m", "force": "kN", "pressure": "kPa", "unit_weight": "kN/m³",
        "k": "m/s", "flux": "m³/s", "gamma_w": 9.807,
    },
    "imperial": {
        "length": "ft", "force": "lbf", "pressure": "psf", "unit_weight": "pcf",
        "k": "ft/s", "flux": "ft³/s", "gamma_w": 62.4,
    },
}

STRENGTH_MODELS = {
    "mohr_coulomb": "Mohr-Coulomb",
    "undrained": "Undrained (phi = 0)",
    "bedrock": "Bedrock (impenetrable)",
}

SLOPE_METHODS = {
    "ordinary": "Ordinary (Fellenius)",
    "bishop": "Bishop Simplified",
    "janbu": "Janbu Simplified",
    "spencer": "Spencer",
    "morgenstern_price": "Morgenstern-Price",
}

PWP_MODES = {
    "none": "None (dry)",
    "piezometric": "Piezometric line",
    "ru": "Ru coefficient",
    "seepage": "From seepage analysis",
}

SEARCH_MODES = {
    "entry_exit": "Entry and exit",
    "grid_radius": "Grid and radius",
    "fully_specified": "Fully specified",
}

BC_TYPES = {
    "head": "Total head",
    "pressure_head": "Pressure head",
    "flux": "Unit flux (inflow +)",
    "seepage_face": "Potential seepage face",
}

ANALYSIS_KINDS = {"slope": "Slope stability (limit equilibrium)", "seepage": "Seepage (finite element, steady state)"}

MATERIAL_COLORS = ["#d9c49c", "#a9c98f", "#c99f7f", "#9fb7d6", "#d6a3b8", "#b5b5b5", "#e3d37a", "#8fc9c2"]


def _filtered(cls, data: dict) -> dict:
    names = {f.name for f in fields(cls)}
    return {k: v for k, v in data.items() if k in names}


@dataclass
class Material:
    id: int
    name: str
    color: str = "#d9c49c"
    model: str = "mohr_coulomb"
    unit_weight: float = 20.0
    cohesion: float = 5.0
    phi: float = 30.0
    cohesion_sd: float = 0.0
    phi_sd: float = 0.0
    unit_weight_sd: float = 0.0
    k_sat: float = 1e-6
    k_ratio: float = 1.0          # ky / kx
    unsat_alpha: float = 2.0      # Gardner exponent (1/length) for relative conductivity

    @classmethod
    def from_dict(cls, d: dict) -> "Material":
        return cls(**_filtered(cls, d))


@dataclass
class Region:
    id: int
    points: list[list[float]]
    material_id: int | None = None

    @classmethod
    def from_dict(cls, d: dict) -> "Region":
        r = cls(**_filtered(cls, d))
        r.points = [[float(p[0]), float(p[1])] for p in r.points]
        return r


@dataclass
class PointLoad:
    x: float
    fy: float = 0.0   # vertical, downward positive
    fx: float = 0.0   # horizontal, positive in the direction of sliding


@dataclass
class Surcharge:
    x1: float
    x2: float
    q: float          # vertical pressure, downward positive


@dataclass
class BoundaryCondition:
    id: int
    name: str
    type: str
    value: float
    points: list[list[float]]

    @classmethod
    def from_dict(cls, d: dict) -> "BoundaryCondition":
        return cls(**_filtered(cls, d))


@dataclass
class SketchText:
    x: float
    y: float
    text: str
    size: float = 10.0


@dataclass
class SearchSettings:
    mode: str = "entry_exit"
    # entry and exit ranges (x coordinates on the ground surface)
    entry_x1: float = 0.0
    entry_x2: float = 0.0
    exit_x1: float = 0.0
    exit_x2: float = 0.0
    n_entry: int = 10
    n_exit: int = 10
    n_radius: int = 6
    # grid and radius
    grid_x1: float = 0.0
    grid_y1: float = 0.0
    grid_x2: float = 0.0
    grid_y2: float = 0.0
    grid_nx: int = 10
    grid_ny: int = 10
    radius_min: float = 5.0
    radius_max: float = 20.0
    n_radii: int = 8
    # fully specified circles: [xc, yc, R] and/or polylines
    circles: list[list[float]] = field(default_factory=list)
    polylines: list[list[list[float]]] = field(default_factory=list)
    min_depth: float = 0.1


@dataclass
class Analysis:
    id: int
    name: str
    kind: str = "slope"
    parent_id: int | None = None
    description: str = ""
    # slope stability
    method: str = "morgenstern_price"
    interslice: str = "half_sine"       # for Morgenstern-Price
    n_slices: int = 30
    pwp: str = "none"
    ru: float = 0.0
    kh: float = 0.0
    search: SearchSettings = field(default_factory=SearchSettings)
    probabilistic: bool = False
    n_samples: int = 1000
    seed: int = 1
    sensitivity_param: str = ""        # e.g. "1:cohesion"
    sensitivity_low: float = 0.0
    sensitivity_high: float = 0.0
    sensitivity_steps: int = 10
    # seepage
    mesh_size: float = 1.0
    unsaturated: bool = True
    max_iter: int = 100
    tolerance: float = 1e-4
    results: dict | None = None

    @classmethod
    def from_dict(cls, d: dict) -> "Analysis":
        d = dict(d)
        search = SearchSettings(**_filtered(SearchSettings, d.pop("search", {}) or {}))
        a = cls(**_filtered(cls, d))
        a.search = search
        return a


@dataclass
class Project:
    title: str = "Untitled"
    author: str = ""
    description: str = ""
    units: str = "metric"
    materials: list[Material] = field(default_factory=list)
    regions: list[Region] = field(default_factory=list)
    piezometric_line: list[list[float]] = field(default_factory=list)
    point_loads: list[PointLoad] = field(default_factory=list)
    surcharges: list[Surcharge] = field(default_factory=list)
    boundary_conditions: list[BoundaryCondition] = field(default_factory=list)
    analyses: list[Analysis] = field(default_factory=list)
    sketch_texts: list[SketchText] = field(default_factory=list)
    grid_spacing: float = 1.0

    # -- lookups -------------------------------------------------------
    @property
    def gamma_w(self) -> float:
        return UNIT_SYSTEMS[self.units]["gamma_w"]

    def unit(self, key: str) -> str:
        return UNIT_SYSTEMS[self.units][key]

    def material(self, mid: int | None) -> Material | None:
        for m in self.materials:
            if m.id == mid:
                return m
        return None

    def analysis(self, aid: int | None) -> Analysis | None:
        for a in self.analyses:
            if a.id == aid:
                return a
        return None

    def next_id(self, items) -> int:
        return max((i.id for i in items), default=0) + 1

    def add_material(self, name: str, **kw) -> Material:
        mid = self.next_id(self.materials)
        kw.setdefault("color", MATERIAL_COLORS[(mid - 1) % len(MATERIAL_COLORS)])
        m = Material(id=mid, name=name, **kw)
        self.materials.append(m)
        return m

    def add_region(self, points, material_id=None) -> Region:
        r = Region(id=self.next_id(self.regions), points=[[float(x), float(y)] for x, y in points], material_id=material_id)
        self.regions.append(r)
        return r

    def add_analysis(self, name: str, kind: str = "slope", **kw) -> Analysis:
        a = Analysis(id=self.next_id(self.analyses), name=name, kind=kind, **kw)
        self.analyses.append(a)
        return a

    def add_bc(self, name: str, type: str, value: float, points) -> BoundaryCondition:
        bc = BoundaryCondition(id=self.next_id(self.boundary_conditions), name=name, type=type,
                               value=float(value), points=[[float(x), float(y)] for x, y in points])
        self.boundary_conditions.append(bc)
        return bc

    def children(self, aid: int | None) -> list[Analysis]:
        return [a for a in self.analyses if a.parent_id == aid]

    def clear_results(self):
        for a in self.analyses:
            a.results = None

    # -- serialization --------------------------------------------------
    def to_dict(self, include_results: bool = True) -> dict:
        d = asdict(self)
        if not include_results:
            for a in d["analyses"]:
                a["results"] = None
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Project":
        p = cls(**{k: v for k, v in _filtered(cls, d).items()
                   if k not in ("materials", "regions", "point_loads", "surcharges",
                                "boundary_conditions", "analyses", "sketch_texts")})
        if p.units not in UNIT_SYSTEMS:
            raise ValueError(f"Unknown unit system: {p.units}")
        p.materials = [Material.from_dict(m) for m in d.get("materials", [])]
        p.regions = [Region.from_dict(r) for r in d.get("regions", [])]
        p.point_loads = [PointLoad(**_filtered(PointLoad, x)) for x in d.get("point_loads", [])]
        p.surcharges = [Surcharge(**_filtered(Surcharge, x)) for x in d.get("surcharges", [])]
        p.boundary_conditions = [BoundaryCondition.from_dict(b) for b in d.get("boundary_conditions", [])]
        p.analyses = [Analysis.from_dict(a) for a in d.get("analyses", [])]
        p.sketch_texts = [SketchText(**_filtered(SketchText, t)) for t in d.get("sketch_texts", [])]
        p.piezometric_line = [[float(a), float(b)] for a, b in p.piezometric_line]
        return p

    def copy(self) -> "Project":
        return copy.deepcopy(self)


def new_project(units: str = "metric", kind: str = "slope") -> Project:
    """Blank project with one default material and one analysis."""
    p = Project(units=units)
    if units == "imperial":
        p.add_material("Soil 1", unit_weight=120.0, cohesion=100.0, phi=30.0, k_sat=3e-6)
        p.grid_spacing = 2.0
    else:
        p.add_material("Soil 1", unit_weight=20.0, cohesion=5.0, phi=30.0, k_sat=1e-6)
    if kind == "seepage":
        p.add_analysis("Seepage", kind="seepage")
    else:
        p.add_analysis("Slope Stability", kind="slope")
    return p
