import numpy as np
import pytest

from stratalab.examples import earth_dam
from stratalab.model import new_project
from stratalab.seep import generate_mesh, pressure_head_interpolator, run_seepage
from stratalab.solver import solve_all


def box(w, h, k=1e-5, alpha=10.0):
    p = new_project(kind="seepage")
    m = p.materials[0]
    m.k_sat, m.unsat_alpha = k, alpha
    p.add_region([(0, 0), (w, 0), (w, h), (0, h)], m.id)
    return p


def test_mesh_covers_region_area():
    p = box(10, 4)
    p.add_region([(10, 0), (16, 0), (16, 4), (10, 4)], p.materials[0].id)
    nodes, tris, mats = generate_mesh(p, 0.7)
    P = nodes[tris]
    area = 0.5 * np.abs((P[:, 1, 0] - P[:, 0, 0]) * (P[:, 2, 1] - P[:, 0, 1]) - (P[:, 2, 0] - P[:, 0, 0]) * (P[:, 1, 1] - P[:, 0, 1]))
    assert abs(area.sum() - 64.0) < 1e-6


def test_confined_flow_exact():
    p = box(10, 2)
    p.add_bc("L", "head", 10, [(0, 0), (0, 2)])
    p.add_bc("R", "head", 5, [(10, 0), (10, 2)])
    a = p.analyses[0]
    a.unsaturated = False
    a.mesh_size = 0.5
    r = run_seepage(p, a)
    n, h = np.array(r["nodes"]), np.array(r["head"])
    assert np.abs(h - (10 - 0.5 * n[:, 0])).max() < 1e-9
    assert abs(r["inflow"] - 1e-5) < 1e-12          # q = k i A = 1e-5 * 0.5 * 2
    assert abs(r["inflow"] - r["outflow"]) < 1e-12


def test_anisotropy_ratio():
    p = box(2, 10)
    p.materials[0].k_ratio = 0.25
    p.add_bc("Top", "head", 20, [(0, 10), (2, 10)])
    p.add_bc("Bottom", "head", 10, [(0, 0), (2, 0)])
    a = p.analyses[0]
    a.unsaturated = False
    r = run_seepage(p, a)
    assert abs(r["inflow"] - 0.25e-5 * 1.0 * 2) < 1e-12


def test_rectangular_dam_matches_dupuit_discharge():
    """Dupuit's discharge formula is exact for a rectangular dam (Charny)."""
    p = box(10, 10)
    p.add_bc("Up", "head", 8, [(0, 0), (0, 8)])
    p.add_bc("Down", "head", 2, [(10, 0), (10, 2)])
    p.add_bc("Face", "seepage_face", 0, [(10, 2), (10, 10)])
    a = p.analyses[0]
    a.mesh_size = 0.4
    r = run_seepage(p, a)
    q = 1e-5 * (8 ** 2 - 2 ** 2) / (2 * 10)
    assert r["converged"]
    assert abs(r["inflow"] - q) / q < 0.05
    assert abs(r["inflow"] - r["outflow"]) / q < 1e-6
    assert r["seepage_face_nodes"]                  # water exits above the tailwater


def test_flux_boundary_conserves_mass():
    p = box(10, 2)
    p.add_bc("In", "flux", 2e-6, [(0, 0), (0, 2)])
    p.add_bc("Out", "head", 5, [(10, 0), (10, 2)])
    a = p.analyses[0]
    a.unsaturated = False
    r = run_seepage(p, a)
    assert abs(r["outflow"] - 4e-6) < 1e-12


def test_interpolator_gives_hydrostatic_pressure():
    p = box(10, 4)
    p.add_bc("L", "head", 3, [(0, 0), (0, 4)])
    p.add_bc("R", "head", 3, [(10, 0), (10, 4)])
    a = p.analyses[0]
    a.unsaturated = False
    r = run_seepage(p, a)
    f = pressure_head_interpolator(r)
    assert abs(f(5.0, 1.0)[0] - 2.0) < 1e-9


def test_errors_for_bad_input():
    p = box(10, 2)
    with pytest.raises(ValueError, match="boundary"):
        run_seepage(p, p.analyses[0])
    p.add_bc("Far", "head", 1, [(50, 50), (60, 50)])
    with pytest.raises(ValueError, match="does not touch"):
        run_seepage(p, p.analyses[0])


def test_earth_dam_seepage_feeds_stability():
    p = earth_dam()
    out = solve_all(p)
    assert all(err is None for _, err in out), out
    seep, slope = p.analyses
    assert seep.results["converged"]
    assert abs(seep.results["inflow"] - seep.results["outflow"]) / seep.results["inflow"] < 1e-6
    F_wet = slope.results["critical"]["fos"]
    slope.pwp = "none"
    from stratalab.slope import run_slope
    F_dry = run_slope(p, slope)["critical"]["fos"]
    assert F_wet < F_dry
