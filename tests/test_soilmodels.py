"""Advanced soil models against closed-form results."""
import math

import numpy as np
import pytest

from stratalab.model import new_project
from stratalab.sigma import run_stress
from stratalab.soilmodels import hyperbolic_integrate, mcc_integrate, p_q

LAM, KAP, NU, PHI = 0.20, 0.04, 0.3, 25.0
M = 6 * math.sin(math.radians(PHI)) / (3 - math.sin(math.radians(PHI)))


def one(v):
    return np.array([v], float)


def test_cam_clay_isotropic_compression_follows_ncl():
    s = np.array([[-100.0, -100.0, 0.0, -100.0]])
    pc, e = one(100.0), one(1.0)
    for _ in range(400):                         # small equal compressive strains
        d = np.array([[-5e-5, -5e-5, 0.0, -5e-5]])
        s, pc, e = mcc_integrate(s, pc, e, d, one(LAM), one(KAP), one(M), one(NU))
    p, q = p_q(s)
    assert q[0] == pytest.approx(0.0, abs=1e-6)
    assert e[0] == pytest.approx(1.0 - LAM * math.log(p[0] / 100.0), abs=2e-3)
    assert pc[0] == pytest.approx(p[0], rel=1e-3)


def test_cam_clay_unload_follows_url():
    s = np.array([[-200.0, -200.0, 0.0, -200.0]])
    pc, e = one(400.0), one(0.8)                 # lightly overconsolidated, elastic on unloading
    for _ in range(200):
        s, pc, e = mcc_integrate(s, pc, e, np.array([[2e-5, 2e-5, 0.0, 2e-5]]), one(LAM), one(KAP), one(M), one(NU))
    p, _ = p_q(s)
    assert pc[0] == pytest.approx(400.0)
    assert e[0] == pytest.approx(0.8 - KAP * math.log(p[0] / 200.0), abs=2e-3)


def test_cam_clay_undrained_shear_reaches_critical_state():
    s = np.array([[-100.0, -100.0, 0.0, -100.0]])
    pc, e = one(100.0), one(1.0)
    for _ in range(2000):                        # plane strain, constant volume
        s, pc, e = mcc_integrate(s, pc, e, np.array([[1e-4, -1e-4, 0.0, 0.0]]), one(LAM), one(KAP), one(M), one(NU))
    p, q = p_q(s)
    assert q[0] / p[0] == pytest.approx(M, rel=0.02)
    assert p[0] == pytest.approx(100.0 * 2 ** (-(LAM - KAP) / LAM), rel=0.02)
    assert e[0] == pytest.approx(1.0, abs=1e-9)


def test_duncan_chang_triaxial_is_hyperbolic():
    mat = {"K": one(300), "Kur": one(600), "n": one(0.5), "Rf": one(0.9), "c": one(0.0), "phi": one(35.0),
           "nu": one(0.3), "pa": one(101.325)}
    s3 = 100.0
    s = np.array([[-s3, -s3, 0.0, -s3]])
    slmax = one(0.0)
    eps, out = 0.0, []
    d = 1e-5
    for k in range(1500):
        s, slmax = hyperbolic_integrate(s, slmax, np.array([[NU * d, -d, 0.0, NU * d]]), mat, nsub=1)
        eps += d
        if k % 300 == 299:
            out.append((eps, -s[0, 1] - s3))
    Ei = 300 * 101.325 * (s3 / 101.325) ** 0.5
    sphi = math.sin(math.radians(35))
    qf = 2 * s3 * sphi / (1 - sphi)
    for e_, q_ in out:
        assert q_ == pytest.approx(e_ / (1 / Ei + 0.9 * e_ / qf), rel=0.01)
    assert s[0, 0] == pytest.approx(-s3, rel=1e-9)                  # lateral stress unchanged


def compression_column(model):
    p = new_project(kind="stress")
    m = p.materials[0]
    m.unit_weight, m.E, m.nu, m.phi = 0.0, 5000.0, NU, PHI
    m.stress_model, m.cc_lambda, m.cc_kappa, m.e0, m.ocr = model, LAM, KAP, 1.0, 1.0
    p.add_region([(0, 0), (1, 0), (1, 10), (0, 10)], m.id)
    p.add_bc("Sides", "fixed_x", 0, [(0, 10), (0, 0)])
    p.add_bc("Right", "fixed_x", 0, [(1, 0), (1, 10)])
    p.add_bc("Base", "fixed_xy", 0, [(0, 0), (1, 0)])
    ins = p.analyses[0]
    ins.stress_type, ins.mesh_size = "insitu", 0.5
    load = p.add_analysis("Load", kind="stress", parent_id=ins.id, stress_type="load", load_steps=20, mesh_size=0.5)
    p.add_bc("Initial stress", "pressure", 100.0, [(1, 10), (0, 10)], analyses=[ins.id])
    p.add_bc("Fill", "pressure", 100.0, [(1, 10), (0, 10)], analyses=[load.id])
    return p, ins, load


def test_cam_clay_one_dimensional_compression():
    """The finite element column (uniform, laterally confined) must reproduce the constitutive model
    driven along the same one-dimensional strain path from the same in situ stresses."""
    p, ins, load = compression_column("cam_clay")
    ins.results = run_stress(p, ins)
    r = run_stress(p, load, parent=ins)
    assert r["converged"]
    settle = -min(r["dy"])
    # element test: start at sigma_v = 100, sigma_h = K0 sigma_v (elastic in situ), normally consolidated
    k0 = NU / (1 - NU)
    s = np.array([[-100 * k0, -100.0, 0.0, -100 * k0]])
    pp, q = p_q(s)
    pc, e = pp + q * q / (M * M * pp), one(1.0)
    eps, d = 0.0, 2e-5
    while -s[0, 1] < 200.0:
        prev_s, prev_eps = -s[0, 1], eps
        s, pc, e = mcc_integrate(s, pc, e, np.array([[0.0, -d, 0.0, 0.0]]), one(LAM), one(KAP), one(M), one(NU))
        eps += d
    eps_200 = prev_eps + (200.0 - prev_s) / (-s[0, 1] - prev_s) * d
    assert settle == pytest.approx(10 * eps_200, rel=0.02)
    # and the textbook estimate for normally consolidated clay is of the right size
    assert settle == pytest.approx(10 * LAM * math.log(2) / 2.0, rel=0.25)
    assert r["reactions"]["Base"][1] == pytest.approx(100.0, rel=0.01)


def test_hyperbolic_settles_more_than_initial_tangent():
    p, ins, load = compression_column("hyperbolic")
    m = p.materials[0]
    m.phi, m.cohesion = 30.0, 0.0
    ins.results = run_stress(p, ins)
    r = run_stress(p, load, parent=ins)
    assert r["converged"]
    assert r["reactions"]["Base"][1] == pytest.approx(100.0, rel=0.01)
    assert -min(r["dy"]) > 0
