"""Thermal, contaminant transport, air flow and dynamic analyses against closed-form solutions."""
import math

import numpy as np
import pytest
from scipy.optimize import brentq
from scipy.special import erf, erfc

from stratalab.air import run_air
from stratalab.model import new_project
from stratalab.quake import newmark_block, run_dynamic
from stratalab.seep import run_seepage
from stratalab.thermal import run_thermal
from stratalab.transport import run_transport


def strip(L, W, kind):
    p = new_project(kind=kind)
    m = p.materials[0]
    p.add_region([(0, 0), (L, 0), (L, W), (0, W)], m.id)
    return p, m, p.analyses[0]


def near_x(r, x, tol=0.06):
    n = np.array(r["nodes"])
    return np.abs(n[:, 0] - x) < tol


# -- thermal --------------------------------------------------------------
def test_conduction_matches_erfc():
    p, m, a = strip(10, 0.5, "thermal")
    m.th_k, m.th_c, m.th_water = 2.0, 2e6, 0.0
    alpha = m.th_k / m.th_c
    a.transient, a.duration, a.n_steps, a.step_growth = True, 10 * 86400.0, 60, 1.05
    a.initial, a.initial_value, a.mesh_size = "value", 10.0, 0.1
    p.add_bc("Surface", "temperature", 0.0, [(0, 0), (0, 0.5)])
    r = run_thermal(p, a)
    T = np.array(r["temperature"])
    for x in (0.5, 1.0, 2.0):
        exact = 10.0 * erf(x / (2 * math.sqrt(alpha * a.duration)))
        assert T[near_x(r, x)].mean() == pytest.approx(exact, abs=0.15), x
    assert r["balance_error"] < 1e-3


def test_freezing_front_matches_stefan():
    """One-phase Stefan problem: ground initially at 0 C, surface held at -10 C.
    Front at X = 2 lam sqrt(alpha_f t) with lam exp(lam^2) erf(lam) = St / sqrt(pi)."""
    p, m, a = strip(4, 0.25, "thermal")
    m.th_k_frozen, m.th_c_frozen, m.th_k, m.th_c = 2.2, 1.9e6, 1.5, 2.4e6
    m.th_water, m.th_freeze_range = 0.3, 0.05
    a.transient, a.duration, a.n_steps, a.step_growth = True, 20 * 86400.0, 80, 1.03
    a.initial, a.initial_value, a.mesh_size = "value", 0.0, 0.04
    p.add_bc("Surface", "temperature", -10.0, [(0, 0), (0, 0.25)])
    r = run_thermal(p, a)
    L = 334e6 * m.th_water
    St = m.th_c_frozen * 10.0 / L
    lam = brentq(lambda l: l * math.exp(l * l) * erf(l) - St / math.sqrt(math.pi), 1e-6, 2)
    X = 2 * lam * math.sqrt(m.th_k_frozen / m.th_c_frozen * a.duration)
    n = np.array(r["nodes"])
    ice = np.array(r["frozen_fraction"])
    on = np.abs(n[:, 1] - 0.0) < 1e-9
    xs, fs = n[on, 0], ice[on]
    order = np.argsort(xs)
    front = np.interp(0.5, fs[order][::-1], xs[order][::-1])
    assert front == pytest.approx(X, rel=0.05), (front, X)
    assert r["balance_error"] < 0.01


def test_convective_boundary_steady():
    p, m, a = strip(2, 0.5, "thermal")
    m.th_k = 1.0
    a.mesh_size = 0.1
    p.add_bc("Hot", "temperature", 20.0, [(0, 0), (0, 0.5)])
    p.add_bc("Air", "convective", 5.0, [(2, 0), (2, 0.5)], value2=0.0)
    r = run_thermal(p, a)
    # series resistance: q = 20 / (L/k + 1/h); surface T = q / h
    q = 20.0 / (2 / 1.0 + 1 / 5.0)
    T = np.array(r["temperature"])
    assert T[near_x(r, 2.0, 1e-6)].mean() == pytest.approx(q / 5.0, rel=1e-3)


# -- contaminant transport -----------------------------------------------
def column_flow(L=20.0, q=1e-6):
    p, m, a = strip(L, 0.5, "seepage")
    m.hyd_model, m.k_sat, m.theta_s = "saturated", 1e-5, 0.3
    a.unsaturated, a.mesh_size = False, 0.1
    dh = q * L / m.k_sat
    p.add_bc("In", "head", 10 + dh, [(0, 0), (0, 0.5)])
    p.add_bc("Out", "head", 10.0, [(L, 0), (L, 0.5)])
    run = run_seepage(p, a)
    return p, m, a, run


def ogata_banks(x, t, v, D):
    return 0.5 * (erfc((x - v * t) / (2 * math.sqrt(D * t))) + math.exp(v * x / D) * erfc((x + v * t) / (2 * math.sqrt(D * t))))


def test_advection_dispersion_matches_ogata_banks():
    p, m, a, seep = column_flow()
    m.disp_l, m.disp_t, m.diffusion = 0.5, 0.05, 0.0
    tr = p.add_analysis("Transport", kind="transport", parent_id=a.id)
    q, th = 1e-6, 0.3
    v = q / th
    tr.duration, tr.n_steps, tr.mesh_size = 10 / v, 200, 0.1
    p.add_bc("Source", "concentration", 1.0, [(0, 0), (0, 0.5)])
    r = run_transport(p, tr, seep_results=seep)
    c = np.array(r["concentration"])
    D = m.disp_l * v
    for x in (5.0, 10.0, 13.0):
        assert c[near_x(r, x)].mean() == pytest.approx(ogata_banks(x, tr.duration, v, D), abs=0.02), x


def test_retardation_and_particle_travel_time():
    p, m, a, seep = column_flow()
    m.disp_l, m.diffusion = 0.2, 0.0
    m.kd, m.dry_density = 0.6 / 1600, 1600.0          # R = 1 + 0.6 / 0.3 = 3
    tr = p.add_analysis("Transport", kind="transport", parent_id=a.id)
    v = 1e-6 / 0.3
    tr.duration, tr.n_steps, tr.mesh_size = 3 * 10 / v, 150, 0.1
    tr.particles = [[1.0, 0.25]]
    p.add_bc("Source", "concentration", 1.0, [(0, 0), (0, 0.5)])
    r = run_transport(p, tr, seep_results=seep)
    c = np.array(r["concentration"])
    assert c[near_x(r, 10.0)].mean() == pytest.approx(0.5, abs=0.04)        # front at x = v t / R
    path = r["particles"][0]
    assert path["path"][-1][0] == pytest.approx(1.0 + v * tr.duration / 3, rel=0.02)


# -- air flow ---------------------------------------------------------------
def test_air_flow_steady_flux():
    p, m, a = strip(5, 1, "air")
    m.k_air = 1e-4
    a.mesh_size = 0.25
    p.add_bc("Blower", "air_pressure", 2.0, [(0, 0), (0, 1)])
    p.add_bc("Open", "air_pressure", 0.0, [(5, 0), (5, 1)])
    r = run_air(p, a)
    kr = math.sqrt(1.0) * 1.0       # dry soil: Se = 0
    exact = m.k_air * kr / p.gamma_w * 2.0 / 5.0 * 1.0
    assert r["inflow"] == pytest.approx(exact, rel=1e-6)
    P = np.array(r["air_pressure"])
    assert P[near_x(r, 2.5, 1e-6)].mean() == pytest.approx(1.0, rel=1e-6)


# -- dynamic --------------------------------------------------------------
def layer(H=20.0, W=60.0, Vs=200.0, xi=0.02):
    p = new_project(kind="dynamic")
    m = p.materials[0]
    m.unit_weight, m.nu, m.damping = 19.6, 0.3, xi
    rho = m.unit_weight / 9.807
    G = rho * Vs * Vs
    m.E = 2 * G * (1 + m.nu)
    p.add_region([(0, 0), (W, 0), (W, H), (0, H)], m.id)
    p.add_bc("Base", "fixed_xy", 0, [(0, 0), (W, 0)])
    p.add_bc("Left", "fixed_y", 0, [(0, 0), (0, H)])
    p.add_bc("Right", "fixed_y", 0, [(W, 0), (W, H)])
    a = p.analyses[0]
    a.mesh_size = 2.5
    return p, m, a


def test_natural_frequency_of_soil_layer():
    p, m, a = layer()
    a.motion, a.dt = [[0, 0.0], [0.1, 0.0]], 0.01
    r = run_dynamic(p, a)
    assert r["natural_frequency"] == pytest.approx(200.0 / (4 * 20.0), rel=0.02)


def test_low_frequency_amplification():
    """Steady harmonic shaking well below resonance: top / base = 1 / cos(w H / Vs)."""
    p, m, a = layer(xi=0.05)
    f = 0.6
    ts = np.arange(0, 12, 0.005)
    a.motion = [[float(t), 0.1 * math.sin(2 * math.pi * f * t)] for t in ts]
    a.dt = 0.005
    r = run_dynamic(p, a)
    n = np.array(r["nodes"])
    top = np.argmin(np.hypot(n[:, 0] - 30, n[:, 1] - 20))
    ht = np.array(r["history_times"])
    ax = np.array(r["history_ax"])[:, top]
    late = ht > 6
    amp = np.abs(ax[late]).max() / 0.1
    assert amp == pytest.approx(1 / math.cos(2 * math.pi * f * 20 / 200), rel=0.03)


def test_newmark_rectangular_pulse():
    """Constant pulse a for duration T: d = (a - ky) g T^2 a / (2 ky)."""
    g, a_, ky, T = 9.807, 0.4, 0.1, 0.5
    t = np.linspace(0, 3, 30001)
    acc = np.where(t <= T, a_, 0.0)
    d, _ = newmark_block(t, acc, ky, g)
    assert d == pytest.approx((a_ - ky) * g * T * T * a_ / (2 * ky), rel=0.005)
