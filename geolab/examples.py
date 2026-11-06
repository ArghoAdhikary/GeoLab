"""Built-in example projects (shown on the start page)."""
from __future__ import annotations

import copy
import math

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


def _box_supports(p, x0, x1, ytop_left, ytop_right, kind="fixed_x"):
    p.add_bc("Left side", kind, 0, [(x0, ytop_left), (x0, 0)])
    p.add_bc("Right side", kind, 0, [(x1, 0), (x1, ytop_right)])
    p.add_bc("Base", "fixed_xy", 0, [(x0, 0), (x1, 0)])


def rapid_drawdown() -> Project:
    """Reservoir lowered over 5 days: transient seepage, then stability at the end of drawdown."""
    p = new_project(kind="seepage")
    p.title = "Reservoir drawdown (transient seepage + stability)"
    fill = p.materials[0]
    fill.name, fill.cohesion, fill.phi, fill.unit_weight = "Silty fill", 5.0, 30.0, 20.0
    fill.hyd_model, fill.k_sat, fill.theta_s, fill.theta_r, fill.vg_alpha, fill.vg_n, fill.mv = \
        "van_genuchten", 1e-6, 0.40, 0.08, 0.8, 1.6, 1e-5
    p.add_region([(0, 0), (80, 0), (80, 18), (55, 18), (25, 3), (0, 3)], fill.id)
    steady = p.analyses[0]
    steady.name, steady.mesh_size = "Full reservoir (steady)", 1.5
    p.add_bc("Reservoir", "head", 16.0, [(0, 3), (25, 3), (51, 16)],
             fn=[[0, 16.0], [432000, 4.0], [864000, 4.0]])
    p.add_bc("Upstream face above", "seepage_face", 0.0, [(51, 16), (55, 18)])
    p.add_bc("Groundwater", "head", 16.0, [(80, 0), (80, 18)])
    draw = p.add_analysis("Drawdown (5 days)", kind="seepage", parent_id=steady.id, transient=True,
                          duration=432000.0, n_steps=20, mesh_size=1.5, initial="parent")
    st = p.add_analysis("Stability after drawdown", kind="slope", parent_id=draw.id, pwp="seepage")
    _auto_search(p, st)
    st.search.entry_x1, st.search.entry_x2, st.search.exit_x1, st.search.exit_x2 = 48, 66, 10, 28
    return p


def strip_footing() -> Project:
    """Rigid strip footing pushed into undrained clay: load-settlement to bearing failure."""
    p = new_project(kind="stress")
    p.title = "Strip footing on clay (stress-deformation)"
    clay = p.materials[0]
    clay.name, clay.model, clay.stress_model, clay.cohesion, clay.phi = "Soft clay", "undrained", "elastic_plastic", 40.0, 0.0
    clay.E, clay.nu, clay.unit_weight = 1.2e4, 0.45, 17.0
    p.add_region([(0, 0), (10, 0), (10, 6), (0, 6)], clay.id)
    _box_supports(p, 0, 10, 6, 6)
    insitu = p.analyses[0]
    insitu.name, insitu.stress_type, insitu.mesh_size = "In situ", "insitu", 0.25
    load = p.add_analysis("Footing load", kind="stress", parent_id=insitu.id, stress_type="load",
                          load_steps=15, mesh_size=0.25)
    p.add_bc("Footing (half width 1 m)", "displacement_y", -0.15, [(0, 6), (1, 6)], analyses=[load.id])
    p.description = "Half model (symmetry on the left). Expected collapse pressure about 5.14 su = 206 kPa."
    return p


def slope_fe_stress() -> Project:
    """Same slope by limit equilibrium, finite element stresses and strength reduction."""
    p = homogeneous_slope()
    p.title = "Slope: limit equilibrium vs finite element"
    p.description = ("2:1 slope, 10 m high, c' = 8 kPa, phi' = 25 deg. Limit equilibrium, the finite element "
                     "stress method and strength reduction should agree within a few percent.")
    m = p.materials[0]
    m.cohesion, m.phi = 8.0, 25.0
    m.stress_model, m.E, m.nu = "elastic_plastic", 5e4, 0.3
    _box_supports(p, 0, 70, 5, 15)
    le = p.analyses[0]
    le.name = "Limit equilibrium"
    ins = p.add_analysis("In situ stresses", kind="stress", stress_type="insitu", mesh_size=1.5)
    fe = p.add_analysis("Finite element stress method", kind="slope", parent_id=ins.id, method="finite_element")
    fe.search = copy.deepcopy(le.search)
    p.add_analysis("Strength reduction", kind="stress", stress_type="insitu", srm=True, mesh_size=1.5)
    return p


def consolidation() -> Project:
    p = new_project(kind="stress")
    p.title = "Consolidation under a fill load"
    clay = p.materials[0]
    clay.name, clay.E, clay.nu, clay.k_sat, clay.unit_weight = "Clay", 5000.0, 0.3, 1e-9, 18.0
    p.add_region([(0, 0), (30, 0), (30, 8), (0, 8)], clay.id)
    _box_supports(p, 0, 30, 8, 8)
    p.add_bc("Fill load", "pressure", 60.0, [(10, 8), (0, 8)])
    p.add_bc("Drained surface", "head", 8.0, [(0, 8), (30, 8)])
    a = p.analyses[0]
    a.name, a.stress_type, a.duration, a.n_steps, a.step_growth, a.mesh_size = \
        "Consolidation (1 year)", "consolidation", 3.15e7, 30, 1.2, 1.0
    return p


def earthquake_slope() -> Project:
    p = homogeneous_slope()
    p.title = "Earthquake: dynamic response and Newmark displacement"
    p.description = ("2:1 slope, 10 m high, c' = 10 kPa, phi' = 25 deg. A 0.25 g, 2 Hz pulse at the base; "
                     "the slope stability child computes the yield acceleration and Newmark displacement.")
    m = p.materials[0]
    m.cohesion, m.phi = 10.0, 25.0
    m.E, m.nu, m.damping, m.gamma_ref, m.damping_max = 1.2e5, 0.3, 0.03, 5e-4, 0.15
    p.add_bc("Base", "fixed_xy", 0, [(0, 0), (70, 0)])
    p.add_bc("Left side", "fixed_y", 0, [(0, 5), (0, 0)])
    p.add_bc("Right side", "fixed_y", 0, [(70, 0), (70, 15)])
    motion = [[round(t * 0.01, 4), 0.25 * math.sin(2 * math.pi * 2.0 * t * 0.01) * math.exp(-((t * 0.01 - 3) / 1.2) ** 2)]
              for t in range(0, 801)]
    dyn = p.add_analysis("Earthquake (8 s)", kind="dynamic", motion=motion, dt=0.01, mesh_size=2.0,
                         equivalent_linear=True, n_eq_iter=4)
    st = p.analyses[0]
    st.name, st.parent_id = "Newmark deformation", dyn.id
    return p


def frost_penetration() -> Project:
    p = new_project(kind="thermal")
    p.title = "Frost penetration under a cold winter"
    soil = p.materials[0]
    soil.name, soil.th_k, soil.th_k_frozen, soil.th_c, soil.th_c_frozen, soil.th_water = \
        "Silt", 1.4, 2.0, 2.5e6, 1.9e6, 0.32
    p.add_region([(0, 0), (4, 0), (4, 6), (0, 6)], soil.id)
    day = 86400.0
    p.add_bc("Air", "convective", 15.0, [(0, 6), (4, 6)], value2=-12.0,
             fn=[[0, 2.0], [20 * day, -12.0], [100 * day, -12.0], [150 * day, 5.0]])
    p.add_bc("Deep ground", "temperature", 6.0, [(0, 0), (4, 0)])
    a = p.analyses[0]
    a.name, a.transient, a.duration, a.n_steps, a.initial, a.initial_value, a.mesh_size = \
        "Winter (150 days)", True, 150 * day, 75, "value", 6.0, 0.25
    return p


def contaminant_plume() -> Project:
    p = new_project(kind="seepage")
    p.title = "Contaminant plume from a leaking pond"
    aq = p.materials[0]
    aq.name, aq.hyd_model, aq.k_sat, aq.theta_s, aq.disp_l, aq.disp_t = "Sand aquifer", "saturated", 2e-5, 0.3, 2.0, 0.2
    p.add_region([(0, 0), (120, 0), (120, 15), (0, 15)], aq.id)
    seep = p.analyses[0]
    seep.name, seep.unsaturated, seep.mesh_size = "Groundwater flow", False, 1.5
    p.add_bc("Upgradient", "head", 20.0, [(0, 0), (0, 15)])
    p.add_bc("Downgradient", "head", 18.0, [(120, 0), (120, 15)])
    p.add_bc("Pond", "concentration", 100.0, [(15, 15), (25, 15)])
    tr = p.add_analysis("Transport (10 years)", kind="transport", parent_id=seep.id, duration=3.15e8,
                        n_steps=60, mesh_size=1.5, particles=[[20, 14.5], [20, 8]])
    return p


def air_flow() -> Project:
    p = new_project(kind="air")
    p.title = "Soil vapour extraction well"
    soil = p.materials[0]
    soil.name, soil.k_air = "Sand", 5e-4
    p.add_region([(0, 0), (30, 0), (30, 5), (0, 5)], soil.id)
    p.add_bc("Extraction well", "air_pressure", -5.0, [(14.5, 0), (15.5, 0)])
    p.add_bc("Ground surface", "air_pressure", 0.0, [(0, 5), (30, 5)])
    p.analyses[0].mesh_size = 0.5
    return p


def rainfall_slope() -> Project:
    """Wet season then dry spell on a silty slope: climate boundary, transient seepage, stability."""
    p = new_project(kind="seepage")
    p.title = "Rainfall and evaporation on a slope"
    m = p.materials[0]
    m.name, m.cohesion, m.phi, m.phi_b, m.unit_weight = "Silty soil", 4.0, 30.0, 15.0, 19.0
    m.hyd_model, m.k_sat, m.theta_s, m.theta_r, m.vg_alpha, m.vg_n, m.mv =         "van_genuchten", 2e-6, 0.42, 0.08, 1.0, 1.7, 1e-5
    p.add_region([(0, 0), (60, 0), (60, 16), (40, 16), (20, 6), (0, 6)], m.id)
    p.piezometric_line = [[0, 4], [20, 4], [40, 8], [60, 9]]
    day, mm = 86400.0, 1.157e-8
    p.add_bc("Weather", "climate", 0.0, [(0, 6), (20, 6), (40, 16), (60, 16)],
             fn=[[0, 25 * mm], [20 * day, 25 * mm], [20.01 * day, 0.0], [40 * day, 0.0]],
             value2=4 * mm, humidity=0.6)
    p.add_bc("Groundwater left", "head", 4.0, [(0, 0), (0, 4)])
    p.add_bc("Groundwater right", "head", 9.0, [(60, 0), (60, 9)])
    seep = p.analyses[0]
    seep.name, seep.transient, seep.duration, seep.n_steps, seep.step_growth = "Wet season and dry spell", True,         40 * day, 40, 1.0
    seep.initial, seep.mesh_size, seep.max_iter = "water_table", 1.0, 60
    st = p.add_analysis("Stability after the season", kind="slope", parent_id=seep.id, pwp="seepage")
    _auto_search(p, st)
    return p


def cam_clay_embankment() -> Project:
    """A wide fill load on soft normally consolidated clay (Modified Cam Clay)."""
    p = new_project(kind="stress")
    p.title = "Soft clay under a fill (Modified Cam Clay)"
    clay = p.materials[0]
    clay.name, clay.stress_model, clay.unit_weight, clay.E, clay.nu, clay.phi =         "Soft clay", "cam_clay", 16.0, 3000.0, 0.3, 25.0
    clay.cc_lambda, clay.cc_kappa, clay.e0, clay.ocr = 0.25, 0.05, 1.4, 1.2
    p.add_region([(0, 0), (40, 0), (40, 8), (0, 8)], clay.id)
    _box_supports(p, 0, 40, 8, 8)
    ins = p.analyses[0]
    ins.name, ins.stress_type, ins.mesh_size = "In situ", "insitu", 1.25
    load = p.add_analysis("Fill load (40 kPa)", kind="stress", parent_id=ins.id, stress_type="load",
                          load_steps=8, mesh_size=1.25)
    p.add_bc("Fill", "pressure", 40.0, [(15, 8), (0, 8)], analyses=[load.id])
    p.description = "Half model, symmetry on the left. Compare with the same model using linear elastic clay."
    return p


EXAMPLES = {
    "Homogeneous slope (benchmark)": homogeneous_slope,
    "Layered slope with water table": layered_slope_with_water,
    "Earth dam: seepage + stability": earth_dam,
    "Reservoir drawdown (transient)": rapid_drawdown,
    "Slope: LE vs finite element": slope_fe_stress,
    "Strip footing (stress-deformation)": strip_footing,
    "Consolidation under a fill": consolidation,
    "Earthquake + Newmark displacement": earthquake_slope,
    "Frost penetration (thermal)": frost_penetration,
    "Contaminant plume (transport)": contaminant_plume,
    "Soil vapour extraction (air flow)": air_flow,
    "Rainfall and evaporation on a slope": rainfall_slope,
    "Soft clay under a fill (Cam Clay)": cam_clay_embankment,
}
