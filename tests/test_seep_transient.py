"""Transient and unsaturated seepage against exact solutions and conservation checks."""
import math

import numpy as np
import pytest

from stratalab.model import new_project
from stratalab.seep import relative_k, run_seepage, water_content


def column(H=10.0, width=1.0):
    p = new_project(kind="seepage")
    m = p.materials[0]
    p.add_region([(0, 0), (width, 0), (width, H), (0, H)], m.id)
    return p, m, p.analyses[0]


def terzaghi(Z, H, Tv, terms=200):
    """Normalised excess head for a layer drained at the top, impervious at the bottom."""
    s = 0.0
    for k in range(terms):
        M = math.pi * (2 * k + 1) / 2
        s += 2 / M * math.sin(M * Z / H) * math.exp(-M * M * Tv)
    return s


@pytest.mark.parametrize("Tv", [0.05, 0.2, 0.6])
def test_saturated_diffusion_matches_terzaghi(Tv):
    H = 10.0
    p, m, a = column(H)
    m.hyd_model, m.k_sat, m.mv = "saturated", 1e-6, 1e-4
    cv = m.k_sat / (m.mv * p.gamma_w)
    a.transient, a.duration, a.n_steps, a.step_growth = True, Tv * H * H / cv, 60, 1.06
    a.initial, a.initial_value = "value", 20.0
    a.mesh_size = 0.25
    p.add_bc("Drained top", "head", 15.0, [(0, H), (1, H)])
    r = run_seepage(p, a)
    nodes = np.array(r["nodes"])
    h = np.array(r["head"])
    for Z in (2.5, 5.0, 10.0):
        y = H - Z
        near = np.abs(nodes[:, 1] - y) < 0.13
        fe = (h[near].mean() - 15.0) / 5.0
        assert fe == pytest.approx(terzaghi(Z, H, Tv), abs=0.015), (Z, fe, terzaghi(Z, H, Tv))
    assert r["balance_error"] < 1e-3


def test_unsaturated_infiltration_conserves_mass():
    p, m, a = column(5.0)
    m.hyd_model, m.k_sat = "van_genuchten", 1e-5
    m.theta_s, m.theta_r, m.vg_alpha, m.vg_n, m.mv = 0.38, 0.05, 2.0, 2.2, 1e-6
    p.piezometric_line = [[0, 0.5], [1, 0.5]]
    a.transient, a.duration, a.n_steps, a.step_growth = True, 3 * 86400.0, 40, 1.05
    a.initial = "water_table"
    a.mesh_size = 0.2
    a.max_iter = 80
    p.add_bc("Rain", "flux", 2e-6, [(0, 5), (1, 5)])
    p.add_bc("Water table", "head", 0.5, [(0, 0), (1, 0)])
    r = run_seepage(p, a)
    assert r["converged"]
    assert r["storage_change"] > 0
    assert r["balance_error"] < 0.02
    # the wetting front has moved down: water content near the top went up
    nodes = np.array(r["nodes"])
    top = nodes[:, 1] > 4.6
    th0, _ = water_content(m, np.array(r["head_history"][0])[top] - nodes[top, 1], p.gamma_w)
    assert np.array(r["water_content"])[top].mean() > th0.mean() + 0.01


def test_van_genuchten_functions():
    m = new_project().materials[0]
    m.hyd_model, m.theta_s, m.theta_r, m.vg_alpha, m.vg_n = "van_genuchten", 0.4, 0.1, 1.0, 2.0
    th, dth = water_content(m, np.array([0.0, -1.0, -10.0]), 9.807)
    Se = (1 + 1.0) ** -0.5
    assert th[1] == pytest.approx(0.1 + 0.3 * Se)
    assert th[0] == pytest.approx(0.4) and th[2] < th[1]
    # derivative by finite difference
    e = 1e-6
    fd = (water_content(m, np.array([-1.0 + e]), 9.807)[0] - water_content(m, np.array([-1.0 - e]), 9.807)[0]) / (2 * e)
    assert dth[1] == pytest.approx(fd[0], rel=1e-4)
    kr = relative_k(m, np.array([-1.0]))[0]
    assert kr == pytest.approx(math.sqrt(Se) * (1 - (1 - Se ** 2) ** 0.5) ** 2)


def test_flux_section_matches_boundary_flow():
    p = new_project(kind="seepage")
    m = p.materials[0]
    m.k_sat = 1e-5
    p.add_region([(0, 0), (20, 0), (20, 4), (0, 4)], m.id)
    a = p.analyses[0]
    a.unsaturated = False
    a.mesh_size = 0.5
    p.add_bc("Left", "head", 10.0, [(0, 0), (0, 4)])
    p.add_bc("Right", "head", 6.0, [(20, 0), (20, 4)])
    p.add_flux_section("Middle", [(10.3, -0.1), (10.3, 4.1)])
    r = run_seepage(p, a)
    exact = 1e-5 * 4.0 / 20.0 * 4.0
    assert r["inflow"] == pytest.approx(exact, rel=1e-6)
    assert r["flux_sections"]["Middle"] == pytest.approx(exact, rel=1e-3)


def test_time_function_boundary_and_free_drainage():
    p, m, a = column(4.0)
    m.hyd_model, m.k_sat, m.unsat_alpha = "gardner", 1e-5, 1.0
    m.theta_s, m.theta_r = 0.4, 0.05
    a.transient, a.duration, a.n_steps = True, 2 * 86400.0, 24
    a.initial, a.initial_value = "value", 1.0
    a.mesh_size = 0.25
    p.add_bc("Ponding", "pressure_head", 0.0, [(0, 4), (1, 4)], fn=[[0, 0.0], [86400, 0.0], [86400.1, -2.0], [2e5, -2.0]])
    p.add_bc("Bottom", "free_drainage", 0.0, [(0, 0), (1, 0)])
    r = run_seepage(p, a)
    assert r["converged"]
    assert r["balance_error"] < 0.02
    assert r["outflow"] > 0
