"""Additional slope methods, strength models, loads and searches."""
import copy
import math

import numpy as np
import pytest

from geolab.examples import homogeneous_slope
from geolab.geometry import GroundProfile
from geolab.model import new_project
from geolab.slope import (ALL_LE_METHODS, build_slices, circle_surface, factor_of_safety, make_pwp_fn,
                             run_slope)
from geolab.strength import hoek_brown_table, strength_at


@pytest.fixture(scope="module")
def acads_critical():
    p = homogeneous_slope()
    r = run_slope(p, p.analyses[0])
    return p, r["critical"]


def test_all_methods_agree_on_acads(acads_critical):
    """Rigorous and force-inclination methods bracket the published referee value (about 1.00)."""
    _, crit = acads_critical
    F = {k: v["fos"] for k, v in crit["all_methods"].items()}
    assert set(ALL_LE_METHODS) <= set(F)
    ref = F["morgenstern_price"]
    for m in ("spencer", "janbu_generalized", "sarma", "corps1", "corps2", "lowe_karafiath", "bishop"):
        assert abs(F[m] - ref) / ref < 0.015, (m, F[m], ref)
    assert F["janbu"] < F["janbu_corrected"] < F["janbu"] * 1.1
    assert F["ordinary"] < F["bishop"]


@pytest.mark.parametrize("model,extra", [
    ("shear_normal", lambda m: {"sn_table": [[0, m.cohesion], [1000, m.cohesion + 1000 * math.tan(math.radians(m.phi))]]}),
    ("bilinear", lambda m: {"phi2": m.phi, "sigma_break": 40.0}),
    ("anisotropic", lambda m: {"cohesion_v": m.cohesion, "phi_v": m.phi}),
])
def test_equivalent_strength_models_match_mohr_coulomb(acads_critical, model, extra):
    p, crit = acads_critical
    gp = GroundProfile(p.regions)
    s, _ = build_slices(p, p.analyses[0], crit["surface"], None, gp)
    ref = factor_of_safety(s, "morgenstern_price")[0]
    q = copy.deepcopy(p)
    m = q.materials[0]
    m.model = model
    for k, v in extra(m).items():
        setattr(m, k, v)
    s2, _ = build_slices(q, q.analyses[0], crit["surface"], None, gp)
    assert factor_of_safety(s2, "morgenstern_price")[0] == pytest.approx(ref, rel=1e-4)


def test_bilinear_reduces_strength_at_high_stress(acads_critical):
    p, crit = acads_critical
    gp = GroundProfile(p.regions)
    q = copy.deepcopy(p)
    m = q.materials[0]
    m.model, m.phi2, m.sigma_break = "bilinear", 10.0, 20.0
    s, _ = build_slices(q, q.analyses[0], crit["surface"], None, gp)
    assert factor_of_safety(s, "bishop")[0] < crit["all_methods"]["bishop"]["fos"] - 0.05


def test_undrained_depth_and_shansep():
    m = new_project().materials[0]
    m.model, m.cohesion, m.c_rate, m.datum = "undrained_depth", 10.0, 2.0, 20.0
    assert strength_at(m, 0.0, y=15.0) == (20.0, 0.0)
    assert strength_at(m, 0.0, y=25.0) == (10.0, 0.0)
    m.model, m.shansep_s, m.shansep_m, m.ocr, m.cohesion = "shansep", 0.25, 0.8, 2.0, 1.0
    c, t = strength_at(m, 0.0, sv_eff=100.0)
    assert c == pytest.approx(0.25 * 2.0 ** 0.8 * 100.0) and t == 0.0


def test_hoek_brown_envelope_is_the_principal_stress_criterion():
    """Each (sigma_n, tau) point must lie on a Mohr circle touching the Hoek-Brown envelope."""
    sigci, gsi, mi, D = 50000.0, 60.0, 12.0, 0.0
    mb = mi * math.exp((gsi - 100) / 28)
    s = math.exp((gsi - 100) / 9)
    a = 0.5 + (math.exp(-gsi / 15) - math.exp(-20 / 3)) / 6
    tab = np.array(hoek_brown_table(sigci, gsi, mi, D))
    assert np.all(np.diff(tab[:, 0]) > 0) and np.all(np.diff(tab[:, 1]) > 0)
    # Mohr circle for sigma3 = 1000: tangent point from the closed-form solution
    s3 = 1000.0
    s1 = s3 + sigci * (mb * s3 / sigci + s) ** a
    d = 1 + a * mb * (mb * s3 / sigci + s) ** (a - 1)
    sn = (s1 + s3) / 2 - (s1 - s3) / 2 * (d - 1) / (d + 1)
    tau = (s1 - s3) * math.sqrt(d) / (d + 1)
    assert np.interp(sn, tab[:, 0], tab[:, 1]) == pytest.approx(tau, rel=0.01)
    # tangent point lies on the circle
    assert (sn - (s1 + s3) / 2) ** 2 + tau ** 2 == pytest.approx(((s1 - s3) / 2) ** 2, rel=1e-6)


def submerged_project(water: bool):
    p = new_project()
    m = p.materials[0]
    m.cohesion, m.phi, m.unit_weight = 0.0, 32.0, 20.0
    p.add_region([(0, 0), (60, 0), (60, 15), (40, 15), (20, 5), (0, 5)], m.id)
    a = p.analyses[0]
    a.n_slices = 60
    if water:
        a.pwp = "piezometric"
        p.piezometric_line = [[0, 25], [60, 25]]
    return p, a


@pytest.mark.parametrize("method", ["bishop", "spencer", "morgenstern_price"])
def test_fully_submerged_cohesionless_slope_equals_dry(method):
    """With c = 0 and hydrostatic water everywhere (including ponded water on the slope),
    F depends only on geometry and phi, so it must equal the dry value."""
    surf = circle_surface(27.0, 24.0, 19.5)
    out = []
    for water in (False, True):
        p, a = submerged_project(water)
        s, why = build_slices(p, a, surf, make_pwp_fn(p, a), GroundProfile(p.regions))
        assert why is None
        out.append(factor_of_safety(s, method)[0])
    assert out[1] == pytest.approx(out[0], rel=0.005), out


def test_partial_ponding_destabilises_less_than_drawdown():
    """Lowering the reservoir in front of a slope (rapid drawdown, water table left high) lowers F."""
    p, a = submerged_project(True)
    surf = circle_surface(27.0, 24.0, 19.5)
    gp = GroundProfile(p.regions)
    p.piezometric_line = [[0, 14], [60, 14]]
    s, _ = build_slices(p, a, surf, make_pwp_fn(p, a), gp)
    F_full = factor_of_safety(s, "morgenstern_price")[0]
    p.piezometric_line = [[0, 5], [20, 5], [40, 14], [60, 14]]   # reservoir drawn down, slope still saturated
    s, _ = build_slices(p, a, surf, make_pwp_fn(p, a), gp)
    assert factor_of_safety(s, "morgenstern_price")[0] < F_full


def test_reinforcement_raises_fos(acads_critical):
    p, crit = acads_critical
    base = crit["fos"]
    q = copy.deepcopy(p)
    q.analyses[0].search = copy.deepcopy(p.analyses[0].search)
    # nail drilled into the slope face, slightly downward, crossing the critical surface
    q.add_reinforcement("nail", 30, 10, 48, 7, capacity=200.0, bond=60.0, spacing=1.0)
    gp = GroundProfile(q.regions)
    s, _ = build_slices(q, q.analyses[0], crit["surface"], None, gp)
    F1 = factor_of_safety(s, "morgenstern_price")[0]
    q.reinforcements[0].f_dependent = True
    s, _ = build_slices(q, q.analyses[0], crit["surface"], None, gp)
    F2 = factor_of_safety(s, "morgenstern_price")[0]
    assert F1 > base + 0.03 and F2 > base + 0.02
    # a pile resists by shear along the slip surface
    q.reinforcements = []
    q.add_reinforcement("pile", 30, 10, 30, -2, capacity=100.0)
    s, _ = build_slices(q, q.analyses[0], crit["surface"], None, gp)
    assert factor_of_safety(s, "morgenstern_price")[0] > base + 0.03


def test_anchor_pullout_limited_by_bond_beyond_slip(acads_critical):
    p, crit = acads_critical
    gp = GroundProfile(p.regions)
    F = []
    for bond_len in (1.0, 6.0):
        q = copy.deepcopy(p)
        q.add_reinforcement("anchor", 30, 10, 50, 6, capacity=1000.0, bond=20.0, bond_length=bond_len)
        s, _ = build_slices(q, q.analyses[0], crit["surface"], None, gp)
        F.append(factor_of_safety(s, "bishop")[0])
    assert F[1] > F[0]


def test_tension_crack_with_water_lowers_fos(acads_critical):
    p, crit = acads_critical
    gp = GroundProfile(p.regions)
    a = copy.deepcopy(p.analyses[0])
    a.tension_crack_depth = 2.0
    s, _ = build_slices(p, a, crit["surface"], None, gp)
    assert s.crack is not None and s.crack["depth"] >= 2.0 - 1e-6
    F_dry = factor_of_safety(s, "morgenstern_price")[0]
    a.crack_water = 1.0
    s, _ = build_slices(p, a, crit["surface"], None, gp)
    assert s.crack["water_force"] == pytest.approx(0.5 * p.gamma_w * s.crack["depth"] ** 2)
    assert factor_of_safety(s, "morgenstern_price")[0] < F_dry


def test_optimization_is_slice_independent_and_lower():
    p = homogeneous_slope()
    a = p.analyses[0]
    a.optimize = True
    r = run_slope(p, a)
    F = r["critical"]["fos"]
    assert F < r["optimized_from"]
    assert 0.95 < F < 1.0
    gp = GroundProfile(p.regions)
    vals = []
    for n in (30, 90):
        a.n_slices = n
        s, _ = build_slices(p, a, r["critical"]["surface"], None, gp)
        vals.append(factor_of_safety(s, "morgenstern_price")[0])
    assert vals[0] == pytest.approx(vals[1], rel=0.003)


def test_block_and_tangent_searches_find_similar_minimum(acads_critical):
    _, crit = acads_critical
    p = homogeneous_slope()
    a = p.analyses[0]
    st = a.search
    st.mode = "grid_tangent"
    st.grid_x1, st.grid_y1, st.grid_x2, st.grid_y2, st.grid_nx, st.grid_ny = 20, 18, 35, 32, 8, 8
    st.tangent_y1, st.tangent_y2, st.n_tangent = 0.5, 5.0, 8
    r = run_slope(p, a)
    assert r["critical"]["fos"] == pytest.approx(crit["fos"], abs=0.03)
    st.mode = "block"
    st.block_left = [20, 3, 26, 5]
    st.block_right = [30, 4, 36, 9]
    st.block_n = 4
    st.block_angle_left, st.block_angle_right = 30.0, 60.0
    r = run_slope(p, a)
    assert r["critical"] is not None
    assert crit["fos"] - 0.05 < r["critical"]["fos"] < crit["fos"] + 0.4


def test_auto_locate():
    p = homogeneous_slope()
    a = p.analyses[0]
    a.search.mode = "auto"
    a.search.n_entry = a.search.n_exit = 6
    r = run_slope(p, a)
    assert 0.95 < r["critical"]["fos"] < 1.0


def test_lognormal_probabilistic():
    p = homogeneous_slope()
    m = p.materials[0]
    m.cohesion_sd, m.phi_sd, m.distribution = 1.0, 2.0, "lognormal"
    a = p.analyses[0]
    a.probabilistic, a.n_samples = True, 300
    r = run_slope(p, a)
    pr = r["probability"]
    assert pr["n"] == 300 and 0.2 < pr["pf"] < 0.8
