"""Built-in example projects (shown on the start page)."""
from __future__ import annotations

from .geometry import auto_entry_exit
from .model import Project, Surcharge, new_project


def _auto_search(p: Project, a):
    (e1, e2), (x1, x2) = auto_entry_exit(p)
    s = a.search
    s.mode = "entry_exit"
    s.entry_x1, s.entry_x2, s.exit_x1, s.exit_x2 = e1, e2, x1, x2


def homogeneous_slope() -> Project:
    """2:1 homogeneous slope, 10 m high (the ACADS 1(a) benchmark problem)."""
    p = new_project()
    p.title = "Homogeneous slope (benchmark)"
    p.description = "2:1 slope, 10 m high, c' = 3 kPa, phi' = 19.6 deg, unit weight 20 kN/m3. Reference F ~ 1.0."
    m = p.materials[0]
    m.name, m.cohesion, m.phi, m.unit_weight = "Clayey sand", 3.0, 19.6, 20.0
    p.add_region([(0, 0), (70, 0), (70, 15), (40, 15), (20, 5), (0, 5)], m.id)
    _auto_search(p, p.analyses[0])
    return p


def layered_slope_with_water() -> Project:
    p = new_project()
    p.title = "Layered slope with water table"
    upper = p.materials[0]
    upper.name, upper.cohesion, upper.phi, upper.unit_weight = "Silty clay", 8.0, 24.0, 19.0
    upper.cohesion_sd, upper.phi_sd = 2.0, 2.0
    lower = p.add_material("Dense sand", cohesion=0.0, phi=36.0, unit_weight=20.5)
    rock = p.add_material("Bedrock", model="bedrock", unit_weight=24.0, cohesion=0.0, phi=0.0)
    p.add_region([(0, 0), (80, 0), (80, 4), (0, 4)], rock.id)
    p.add_region([(0, 4), (80, 4), (80, 12), (50, 12), (34, 8), (0, 8)], lower.id)
    p.add_region([(0, 8), (34, 8), (50, 12), (80, 12), (80, 20), (50, 20), (25, 10), (0, 10)], upper.id)
    p.piezometric_line = [[0, 9], [25, 9.5], [50, 15], [80, 16]]
    a = p.analyses[0]
    a.name = "Stability with water table"
    a.pwp = "piezometric"
    a.probabilistic = True
    a.n_samples = 300
    _auto_search(p, a)
    p.surcharges.append(Surcharge(58, 70, 15.0))
    return p


def earth_dam() -> Project:
    """Homogeneous earth dam: steady seepage, then downstream slope stability using its pore pressures."""
    p = new_project(kind="seepage")
    p.title = "Earth dam: seepage and stability"
    core = p.materials[0]
    core.name, core.cohesion, core.phi, core.unit_weight = "Compacted fill", 10.0, 28.0, 19.5
    core.k_sat, core.unsat_alpha = 1e-6, 3.0
    found = p.add_material("Foundation", cohesion=5.0, phi=32.0, unit_weight=20.0, k_sat=5e-7, unsat_alpha=3.0)
    p.add_region([(0, 0), (100, 0), (100, 5), (0, 5)], found.id)
    p.add_region([(10, 5), (45, 20), (55, 20), (90, 5)], core.id)
    seep = p.analyses[0]
    seep.name = "Steady-state seepage"
    seep.mesh_size = 1.5
    p.add_bc("Reservoir", "head", 19.0, [[0, 5], [10, 5], [42.6667, 19]])
    p.add_bc("Tailwater", "head", 5.0, [[90, 5], [100, 5]])
    p.add_bc("Downstream face", "seepage_face", 0.0, [[55, 20], [90, 5]])
    slope = p.add_analysis("Downstream stability", kind="slope", parent_id=seep.id, pwp="seepage",
                           method="morgenstern_price")
    s = slope.search
    s.mode = "entry_exit"
    s.entry_x1, s.entry_x2, s.exit_x1, s.exit_x2 = 50.0, 62.0, 78.0, 95.0
    s.n_entry, s.n_exit = 8, 8
    return p


EXAMPLES = {
    "Homogeneous slope (benchmark)": homogeneous_slope,
    "Layered slope with water table": layered_slope_with_water,
    "Earth dam: seepage + stability": earth_dam,
}
