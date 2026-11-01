import math

import numpy as np
import pytest

from stratalab.examples import homogeneous_slope
from stratalab.geometry import GroundProfile, point_in_polygon
from stratalab.model import new_project
from stratalab.slope import (build_slices, circle_surface, factor_of_safety, find_extent, polyline_surface,
                             run_slope)

METHODS = ["ordinary", "bishop", "janbu", "spencer", "morgenstern_price"]


def acads():
    return homogeneous_slope()


def test_acads_1a_benchmark():
    """ACADS EX1(a): referee factor of safety about 1.00 (published range 0.99-1.00)."""
    p = acads()
    a = p.analyses[0]
    for method, lo, hi in (("bishop", 0.96, 1.02), ("morgenstern_price", 0.96, 1.02), ("spencer", 0.96, 1.02)):
        a.method = method
        r = run_slope(p, a)
        assert lo < r["critical"]["fos"] < hi, (method, r["critical"]["fos"])


def test_method_ordering_on_critical_surface():
    p = acads()
    r = run_slope(p, p.analyses[0])
    m = {k: v["fos"] for k, v in r["critical"]["all_methods"].items()}
    assert m["ordinary"] < m["bishop"]
    assert abs(m["spencer"] - m["morgenstern_price"]) < 0.02
    assert abs(m["bishop"] - m["morgenstern_price"]) < 0.03


def undrained_project():
    p = new_project()
    m = p.materials[0]
    m.model, m.cohesion, m.phi, m.unit_weight = "undrained", 20.0, 0.0, 18.0
    p.add_region([(0, 0), (60, 0), (60, 14), (35, 14), (20, 4), (0, 4)], m.id)
    return p


def test_undrained_methods_agree_and_match_direct_integration():
    p = undrained_project()
    a = p.analyses[0]
    a.n_slices = 200
    surf = circle_surface(26.0, 24.0, 21.0)
    gp = GroundProfile(p.regions)
    s, why = build_slices(p, a, surf, None, gp)
    assert why is None
    F = {m: factor_of_safety(s, m)[0] for m in ("ordinary", "bishop", "spencer", "morgenstern_price")}
    assert abs(F["ordinary"] - F["bishop"]) < 1e-9          # identical when phi = 0
    assert abs(F["spencer"] - F["bishop"]) < 1e-4           # moment equilibrium independent of N
    assert abs(F["morgenstern_price"] - F["bishop"]) < 1e-4
    # independent check: F = c * arc * R / sum(gamma * dA * (x - xc)) by fine grid integration
    xl, xr, _ = find_extent(gp, surf)
    xc, yc, R = surf["xc"], surf["yc"], surf["R"]
    th = lambda x: math.asin((x - xc) / R)
    arc = R * (th(xr) - th(xl))
    h = 0.02
    xs = np.arange(xl + h / 2, xr, h)
    mom = 0.0
    for x in xs:
        ys = yc - math.sqrt(R * R - (x - xc) ** 2)
        top = float(gp.ground(x))
        if top > ys:
            mom += 18.0 * (top - ys) * h * (x - xc)
    F_direct = 20.0 * arc * R / abs(mom)
    assert abs(F["bishop"] - F_direct) / F_direct < 0.005


def test_mirrored_geometry_gives_same_fos():
    p = acads()
    a = p.analyses[0]
    a.method = "morgenstern_price"
    surf = circle_surface(19.2, 34.5, 29.5)
    s, _ = build_slices(p, a, surf)
    F1, _ = factor_of_safety(s, a.method)
    q = acads()
    q.regions[0].points = [[70 - x, y] for x, y in reversed(q.regions[0].points)]
    s2, _ = build_slices(q, q.analyses[0], circle_surface(70 - 19.2, 34.5, 29.5))
    F2, _ = factor_of_safety(s2, a.method)
    assert abs(F1 - F2) < 1e-6
    assert s.mirrored != s2.mirrored


def test_water_and_seismic_reduce_fos():
    p = acads()
    a = p.analyses[0]
    a.method = "bishop"
    surf = circle_surface(19.2, 34.5, 29.5)
    base, _ = factor_of_safety(build_slices(p, a, surf)[0], "bishop")
    p.piezometric_line = [[0, 5], [20, 5], [40, 12], [70, 12]]
    a.pwp = "piezometric"
    from stratalab.slope import make_pwp_fn
    wet, _ = factor_of_safety(build_slices(p, a, surf, make_pwp_fn(p, a))[0], "bishop")
    a.pwp = "none"
    a.kh = 0.1
    quake, _ = factor_of_safety(build_slices(p, a, surf)[0], "bishop")
    assert wet < base
    assert quake < base


def test_polyline_surface_matches_circle():
    """A polyline traced along a circle should give nearly the same F with the rigorous methods."""
    p = acads()
    a = p.analyses[0]
    xc, yc, R = 19.2, 34.5, 29.5
    gp = GroundProfile(p.regions)
    xl, xr, _ = find_extent(gp, circle_surface(xc, yc, R))
    xs = np.linspace(xl - 0.5, xr + 0.5, 80)
    pts = [(x, yc - math.sqrt(R * R - (x - xc) ** 2)) for x in xs]
    for m in ("spencer", "morgenstern_price"):
        Fc, _ = factor_of_safety(build_slices(p, a, circle_surface(xc, yc, R))[0], m)
        Fp, _ = factor_of_safety(build_slices(p, a, polyline_surface(pts))[0], m)
        assert abs(Fc - Fp) / Fc < 0.02, (m, Fc, Fp)


def test_bedrock_and_outside_surfaces_rejected():
    p = acads()
    a = p.analyses[0]
    rock = p.add_material("Rock", model="bedrock")
    p.add_region([(0, -5), (70, -5), (70, 0), (0, 0)], rock.id)
    s, why = build_slices(p, a, circle_surface(30, 30, 33))   # dips below y = 0
    assert s is None and "bedrock" in why
    s, why = build_slices(p, a, circle_surface(30, 60, 5))    # never reaches the ground
    assert s is None


def test_grid_radius_search_finds_similar_minimum():
    p = acads()
    a = p.analyses[0]
    a.method = "bishop"
    st = a.search
    st.mode = "grid_radius"
    st.grid_x1, st.grid_x2, st.grid_y1, st.grid_y2 = 14, 30, 24, 42
    st.grid_nx = st.grid_ny = 9
    st.radius_min, st.radius_max, st.n_radii = 15, 38, 12
    r = run_slope(p, a)
    assert 0.96 < r["critical"]["fos"] < 1.05


def test_probabilistic_with_zero_spread_is_deterministic():
    p = acads()
    a = p.analyses[0]
    a.method = "bishop"
    a.probabilistic = True
    a.n_samples = 50
    r = run_slope(p, a)
    pr = r["probability"]
    assert pr["n"] == 50
    assert abs(pr["mean"] - r["critical"]["fos"]) < 1e-9
    assert pr["sd"] < 1e-9


def test_probabilistic_spread():
    p = acads()
    m = p.materials[0]
    m.cohesion_sd, m.phi_sd = 1.0, 2.0
    a = p.analyses[0]
    a.method = "bishop"
    a.probabilistic = True
    a.n_samples = 400
    pr = run_slope(p, a)["probability"]
    assert 0.2 < pr["pf"] < 0.8          # mean F is close to 1, so failure is likely in a good share of samples
    assert pr["sd"] > 0.02


def test_sensitivity_increases_with_cohesion():
    p = acads()
    a = p.analyses[0]
    a.method = "bishop"
    a.sensitivity_param = f"{p.materials[0].id}:cohesion"
    a.sensitivity_low, a.sensitivity_high, a.sensitivity_steps = 0.0, 10.0, 6
    sv = run_slope(p, a)["sensitivity"]
    assert all(b > a_ for a_, b in zip(sv["fos"], sv["fos"][1:]))


def test_surcharge_reduces_fos_at_crest():
    from stratalab.model import Surcharge
    p = acads()
    a = p.analyses[0]
    a.method = "bishop"
    surf = circle_surface(19.2, 34.5, 29.5)
    F0, _ = factor_of_safety(build_slices(p, a, surf)[0], "bishop")
    p.surcharges.append(Surcharge(40, 48, 30.0))
    F1, _ = factor_of_safety(build_slices(p, a, surf)[0], "bishop")
    assert F1 < F0


def test_missing_inputs_raise_readable_errors():
    p = acads()
    a = p.analyses[0]
    a.pwp = "piezometric"
    with pytest.raises(ValueError, match="(?i)piezometric line"):
        run_slope(p, a)
    p.regions[0].material_id = 999
    with pytest.raises(ValueError, match="no material"):
        run_slope(p, a)
