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
    # time is in seconds in both systems; thermal values are SI-consistent (W, J)
    "metric": {
        "length": "m", "force": "kN", "pressure": "kPa", "unit_weight": "kN/m³",
        "k": "m/s", "flux": "m³/s", "gamma_w": 9.807, "g": 9.807, "time": "s",
        "modulus": "kPa", "compressibility": "1/kPa", "temperature": "°C",
        "conductivity_th": "W/m/°C", "heat_capacity": "J/m³/°C", "latent": 334e6,
        "concentration": "g/m³",
    },
    "imperial": {
        "length": "ft", "force": "lbf", "pressure": "psf", "unit_weight": "pcf",
        "k": "ft/s", "flux": "ft³/s", "gamma_w": 62.4, "g": 32.174, "time": "s",
        "modulus": "psf", "compressibility": "1/psf", "temperature": "°F",
        "conductivity_th": "Btu/s/ft/°F", "heat_capacity": "Btu/ft³/°F", "latent": 8970.0,
        "concentration": "lb/ft³",
    },
}

from .strength import STRENGTH_MODELS  # noqa: E402  (re-exported for the UI)

SLOPE_METHODS = {
    "ordinary": "Ordinary (Fellenius)",
    "bishop": "Bishop Simplified",
    "janbu": "Janbu Simplified",
    "janbu_corrected": "Janbu Simplified, corrected (f0)",
    "janbu_generalized": "Janbu Generalized",
    "spencer": "Spencer",
    "morgenstern_price": "Morgenstern-Price",
    "corps1": "Corps of Engineers #1",
    "corps2": "Corps of Engineers #2",
    "lowe_karafiath": "Lowe-Karafiath",
    "sarma": "Sarma (vertical slices)",
    "finite_element": "Finite element stress",
}

INTERSLICE_FUNCTIONS = {
    "half_sine": "Half-sine",
    "constant": "Constant",
    "clipped_sine": "Clipped sine",
    "trapezoidal": "Trapezoidal",
    "user": "Data points (x/L, f)",
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
    "grid_tangent": "Grid and tangent lines",
    "block": "Block (two grids)",
    "auto": "Auto locate",
    "fully_specified": "Fully specified",
}

HYDRAULIC_MODELS = {
    "saturated": "Saturated only (storage from compressibility)",
    "gardner": "Saturated / unsaturated (Gardner)",
    "van_genuchten": "Saturated / unsaturated (van Genuchten-Mualem)",
}

STRESS_MODELS = {
    "linear_elastic": "Linear elastic",
    "elastic_plastic": "Elastic-plastic (Mohr-Coulomb)",
    "cam_clay": "Modified Cam Clay (critical state)",
    "hyperbolic": "Hyperbolic (Duncan-Chang)",
    "none": "None (excluded)",
}

# boundary conditions, grouped by physics
BC_KINDS = {
    "hydraulic": {
        "head": "Total head",
        "pressure_head": "Pressure head",
        "flux": "Unit flux (inflow +)",
        "nodal_flux": "Total flux at nodes (inflow +)",
        "seepage_face": "Potential seepage face",
        "infiltration": "Infiltration with ponding review",
        "free_drainage": "Free drainage (unit gradient)",
        "climate": "Climate: rainfall (value) and potential evaporation (second value)",
    },
    "stress": {
        "fixed_x": "Fixed x",
        "fixed_y": "Fixed y",
        "fixed_xy": "Fixed x and y",
        "pressure": "Normal pressure (compression +)",
        "shear": "Shear stress (along edge)",
        "force_x": "Force x (total)",
        "force_y": "Force y (total)",
        "displacement_y": "Displacement y",
    },
    "thermal": {
        "temperature": "Temperature",
        "heat_flux": "Unit heat flux (into ground +)",
        "convective": "Convective (h, ambient temperature)",
    },
    "transport": {
        "concentration": "Concentration",
        "mass_flux": "Unit mass flux (in +)",
        "free_exit": "Free exit (advective outflow)",
    },
    "air": {
        "air_pressure": "Air pressure (gauge)",
        "air_flux": "Unit air flux (in +)",
    },
}
BC_TYPES = {k: v for group in BC_KINDS.values() for k, v in group.items()}
BC_KIND_OF = {k: kind for kind, group in BC_KINDS.items() for k in group}

ANALYSIS_KINDS = {
    "slope": "Slope stability (limit equilibrium)",
    "seepage": "Seepage (groundwater flow)",
    "stress": "Stress-deformation",
    "dynamic": "Dynamic (earthquake)",
    "thermal": "Thermal (heat transfer, freezing)",
    "transport": "Contaminant transport",
    "air": "Air flow",
}

# which BC groups and parent analyses each analysis kind uses
KIND_BCS = {"seepage": "hydraulic", "stress": "stress", "dynamic": "stress", "thermal": "thermal",
            "transport": "transport", "air": "air"}

REINFORCEMENT_TYPES = {
    "anchor": "Anchor (bonded length at the end)",
    "nail": "Nail (bonded full length)",
    "geosynthetic": "Geosynthetic",
    "pile": "Pile / dowel (shear)",
}

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
    # -- more strength parameters (see strength.py) --
    phi_b: float = 0.0            # suction friction angle (unsaturated strength)
    c_rate: float = 0.0           # undrained strength increase per unit depth below datum
    datum: float = 0.0
    shansep_s: float = 0.22
    shansep_m: float = 0.8
    ocr: float = 1.0
    phi2: float = 20.0            # bilinear: friction angle above sigma_break
    sigma_break: float = 100.0
    sn_table: list = field(default_factory=list)   # [[normal stress, shear strength], ...]
    sigci: float = 10000.0        # Hoek-Brown intact UCS
    gsi: float = 50.0
    mi: float = 10.0
    hb_d: float = 0.0
    cohesion_v: float = 5.0       # anisotropic: values on a vertical plane
    phi_v: float = 30.0
    distribution: str = "normal"  # probabilistic: normal | lognormal | uniform
    # -- hydraulic --
    hyd_model: str = "gardner"
    theta_s: float = 0.40
    theta_r: float = 0.05
    vg_alpha: float = 1.0         # 1/length
    vg_n: float = 1.6
    mv: float = 1e-5              # coefficient of volume compressibility (1/pressure)
    # -- stress-deformation --
    stress_model: str = "linear_elastic"
    E: float = 20000.0
    nu: float = 0.3
    psi: float = 0.0              # dilation angle
    k0: float = 0.0               # 0 = nu / (1 - nu)
    cc_lambda: float = 0.20       # Modified Cam Clay: slope of the normal compression line (e vs ln p')
    cc_kappa: float = 0.04        # slope of the unload-reload line
    e0: float = 1.0               # initial void ratio
    dc_K: float = 300.0           # Duncan-Chang modulus number
    dc_Kur: float = 600.0         # unload-reload modulus number
    dc_n: float = 0.5             # modulus exponent
    dc_Rf: float = 0.9            # failure ratio
    # -- dynamic --
    damping: float = 0.05
    gamma_ref: float = 0.0        # reference shear strain for equivalent linear (0 = linear)
    damping_max: float = 0.20
    # -- thermal --
    th_k: float = 1.5             # unfrozen thermal conductivity
    th_k_frozen: float = 2.2
    th_c: float = 2.4e6           # unfrozen volumetric heat capacity
    th_c_frozen: float = 1.9e6
    th_water: float = 0.30        # volumetric water content for latent heat
    th_freeze_range: float = 1.0  # temperature range below 0 over which water freezes
    # -- contaminant transport --
    disp_l: float = 1.0           # longitudinal dispersivity
    disp_t: float = 0.1
    diffusion: float = 1e-9
    kd: float = 0.0               # distribution coefficient (adsorption)
    dry_density: float = 1600.0
    half_life: float = 0.0        # 0 = no decay
    # -- air flow --
    k_air: float = 1e-5           # air conductivity of dry soil

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
    value2: float = 0.0                              # second parameter (e.g. convective ambient temperature)
    fn: list = field(default_factory=list)           # [[time, value], ...] overrides value when given
    analyses: list = field(default_factory=list)     # analysis ids it applies to; empty = all
    fn2: list = field(default_factory=list)          # [[time, value2], ...] (e.g. potential evaporation)
    humidity: float = 0.5                            # climate: relative humidity of the air (0-1)

    @property
    def kind(self) -> str:
        return BC_KIND_OF.get(self.type, "hydraulic")

    @staticmethod
    def _interp(fn, t, default):
        if t is None or not fn:
            return default
        import numpy as np
        f = sorted(fn)
        return float(np.interp(t, [p[0] for p in f], [p[1] for p in f]))

    def at(self, t: float | None) -> float:
        return self._interp(self.fn, t, self.value)

    def at2(self, t: float | None) -> float:
        return self._interp(self.fn2, t, self.value2)

    @classmethod
    def from_dict(cls, d: dict) -> "BoundaryCondition":
        return cls(**_filtered(cls, d))


@dataclass
class Reinforcement:
    id: int
    type: str                    # anchor | nail | geosynthetic | pile
    x1: float                    # head (at the slope face)
    y1: float
    x2: float                    # far end (inside the slope)
    y2: float
    capacity: float = 100.0      # tensile (or shear, for piles) capacity per reinforcement
    bond: float = 50.0           # pullout resistance per unit length
    bond_length: float = 3.0     # anchors: bonded length at the far end
    spacing: float = 1.0         # out-of-plane spacing
    f_dependent: bool = False    # True: force is divided by the factor of safety

    @classmethod
    def from_dict(cls, d: dict) -> "Reinforcement":
        return cls(**_filtered(cls, d))


@dataclass
class FluxSection:
    id: int
    name: str
    points: list[list[float]]

    @classmethod
    def from_dict(cls, d: dict) -> "FluxSection":
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
    # tangent lines (grid and tangent): horizontal lines y = tangent_y1 .. tangent_y2
    tangent_y1: float = 0.0
    tangent_y2: float = 0.0
    n_tangent: int = 6
    # block search: left and right grids of base points, projection angles in degrees
    block_left: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0])    # x1, y1, x2, y2
    block_right: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0])
    block_n: int = 4
    block_angle_left: float = 45.0
    block_angle_right: float = 45.0


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
    kv: float = 0.0                     # vertical seismic coefficient (downward +)
    interslice_points: list = field(default_factory=list)
    tension_crack_depth: float = 0.0
    tension_crack_angle: float = 0.0    # degrees; 0 = off
    crack_water: float = 0.0            # fraction of the crack filled with water
    optimize: bool = False
    opt_iterations: int = 400
    stress_parent_id: int | None = None  # finite element stress method
    # finite element analyses (seepage, stress, thermal, transport, air, dynamic)
    mesh_size: float = 1.0
    unsaturated: bool = True
    max_iter: int = 100
    tolerance: float = 1e-4
    transient: bool = False
    duration: float = 86400.0
    n_steps: int = 20
    step_growth: float = 1.0            # ratio between successive time steps
    initial: str = "parent"             # parent | water_table | value
    initial_value: float = 0.0
    # stress-deformation
    stress_type: str = "insitu"         # insitu | load | consolidation
    insitu_method: str = "gravity"      # gravity (finite element gravity activation) | k0 (K0 procedure)
    load_steps: int = 10
    srm: bool = False                   # strength reduction factor of safety
    # dynamic
    motion: list = field(default_factory=list)   # [[t, acceleration in g], ...]
    dt: float = 0.01
    equivalent_linear: bool = False
    n_eq_iter: int = 6
    # transport
    particles: list = field(default_factory=list)   # [[x, y], ...] for particle tracking
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
    reinforcements: list[Reinforcement] = field(default_factory=list)
    flux_sections: list[FluxSection] = field(default_factory=list)
    mesh_lines: list = field(default_factory=list)     # interior lines the mesh follows (e.g. drains)
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

    def add_bc(self, name: str, type: str, value: float, points, **kw) -> BoundaryCondition:
        bc = BoundaryCondition(id=self.next_id(self.boundary_conditions), name=name, type=type,
                               value=float(value), points=[[float(x), float(y)] for x, y in points], **kw)
        self.boundary_conditions.append(bc)
        return bc

    def add_reinforcement(self, type: str, x1, y1, x2, y2, **kw) -> Reinforcement:
        r = Reinforcement(id=self.next_id(self.reinforcements), type=type, x1=float(x1), y1=float(y1),
                          x2=float(x2), y2=float(y2), **kw)
        self.reinforcements.append(r)
        return r

    def add_flux_section(self, name: str, points) -> FluxSection:
        f = FluxSection(id=self.next_id(self.flux_sections), name=name,
                        points=[[float(x), float(y)] for x, y in points])
        self.flux_sections.append(f)
        return f

    def bcs(self, group: str, analysis=None) -> list[BoundaryCondition]:
        """Boundary conditions of one physics group, limited to those active in an analysis."""
        aid = getattr(analysis, "id", analysis)
        return [b for b in self.boundary_conditions
                if b.kind == group and (aid is None or not b.analyses or aid in b.analyses)]

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
                                "boundary_conditions", "analyses", "sketch_texts",
                                "reinforcements", "flux_sections")})
        if p.units not in UNIT_SYSTEMS:
            raise ValueError(f"Unknown unit system: {p.units}")
        p.materials = [Material.from_dict(m) for m in d.get("materials", [])]
        p.regions = [Region.from_dict(r) for r in d.get("regions", [])]
        p.point_loads = [PointLoad(**_filtered(PointLoad, x)) for x in d.get("point_loads", [])]
        p.surcharges = [Surcharge(**_filtered(Surcharge, x)) for x in d.get("surcharges", [])]
        p.boundary_conditions = [BoundaryCondition.from_dict(b) for b in d.get("boundary_conditions", [])]
        p.analyses = [Analysis.from_dict(a) for a in d.get("analyses", [])]
        p.sketch_texts = [SketchText(**_filtered(SketchText, t)) for t in d.get("sketch_texts", [])]
        p.reinforcements = [Reinforcement.from_dict(r) for r in d.get("reinforcements", [])]
        p.flux_sections = [FluxSection.from_dict(f) for f in d.get("flux_sections", [])]
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
    names = {"slope": "Slope Stability", "seepage": "Seepage", "stress": "Stress-Deformation",
             "dynamic": "Dynamic", "thermal": "Thermal", "transport": "Contaminant Transport", "air": "Air Flow"}
    p.add_analysis(names.get(kind, "Slope Stability"), kind=kind if kind in names else "slope")
    return p
