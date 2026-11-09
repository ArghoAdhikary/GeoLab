"""GeoLab 2.14: 3D slope stability (ellipsoids, 3D Bishop), 3D seepage with wells, axisymmetric
seepage, pore pressure generation and liquefaction in dynamic analysis, post-earthquake stability,
and interface elements in stress-deformation."""
import copy
import math
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication


# ------------------------------------------------------------------ 3D slope
@pytest.fixture(scope="module")
def slope2d():
    from geolab import examples
    from geolab.slope import run_slope
    p = examples.homogeneous_slope()
    a = p.analyses[0]
    a.method = "bishop"
    r = run_slope(p, a)
    return p, a, r


def test_long_ellipsoid_equals_2d_bishop(slope2d):
    from geolab.slope3d import Model3D
    p, a, r = slope2d
    s = r["critical"]["surface"]
    a3 = copy.copy(a)
    a3.three_d, a3.width3d = True, 40.0
    m = Model3D(p, a3)
    F, cols = m.fos(s["xc"], s["yc"], s["R"], 1e7, 20.0)
    assert F == pytest.approx(r["critical"]["fos"], rel=1e-6)
    assert cols["volume"] > 0 and cols["n"] > 100


def test_shorter_slides_are_safer(slope2d):
    from geolab.slope3d import Model3D
    p, a, r = slope2d
    s = r["critical"]["surface"]
    a3 = copy.copy(a)
    a3.three_d, a3.width3d = True, 200.0
    m = Model3D(p, a3)
    Fs = [m.fos(s["xc"], s["yc"], s["R"], L / 2, 100.0)[0] for L in (10, 20, 40, 80, 160)]
    assert all(F1 > F2 for F1, F2 in zip(Fs, Fs[1:]))           # end effects fade with length
    assert Fs[-1] > r["critical"]["fos"] and Fs[-1] < 1.05 * r["critical"]["fos"]


def test_slope3d_through_the_solver():
    from geolab import examples
    from geolab.solver import solve
    from geolab.slope3d import text_report
    p = examples.homogeneous_slope()
    a = p.analyses[0]
    a.three_d, a.width3d, a.slide_lengths = True, 30.0, [[10.0], [30.0]]
    r = solve(p, a)
    t = r["three_d"]
    assert t["fos"] >= t["fos_2d"] - 1e-6 and r["critical"]["fos3d"] == t["fos"]
    assert [L for L, _ in t["by_length"]] == [10.0, 30.0]
    assert t["by_length"][0][1] > t["by_length"][1][1]
    assert "3D Bishop" in text_report(r)


def test_load_over_part_of_the_width():
    from geolab import examples
    from geolab.model import Surcharge
    from geolab.slope import run_slope
    from geolab.slope3d import Model3D
    p = examples.homogeneous_slope()
    a = p.analyses[0]
    a.method = "bishop"
    c = run_slope(p, a)["critical"]
    s = c["surface"]
    xs = c["slice_x"]
    p.surcharges = [Surcharge(min(xs), max(xs), 30.0)]
    a.three_d, a.width3d = True, 60.0
    full = Model3D(p, a).fos(s["xc"], s["yc"], s["R"], 10.0, 30.0)[0]
    a.load_z1, a.load_z2 = 28.0, 32.0
    part = Model3D(p, a).fos(s["xc"], s["yc"], s["R"], 10.0, 30.0)[0]
    a.load_z1 = a.load_z2 = 0.0
    p.surcharges = []
    none = Model3D(p, a).fos(s["xc"], s["yc"], s["R"], 10.0, 30.0)[0]
    assert full != none and min(full, none) < part < max(full, none)


# ------------------------------------------------------------------ seepage
def _aquifer(r1=0.5, r2=50.0, b=5.0):
    from geolab.model import new_project
    p = new_project()
    p.analyses.clear()
    m = p.materials[0]
    m.k_sat, m.hyd_model = 1e-4, "saturated"
    p.add_region([(r1, 0), (r2, 0), (r2, b), (r1, b)], m.id)
    p.add_bc("Well", "head", 10, [(r1, 0), (r1, b)])
    p.add_bc("Far", "head", 20, [(r2, 0), (r2, b)])
    return p


def test_axisymmetric_matches_thiem():
    from geolab.solver import solve
    p = _aquifer()
    a = p.add_analysis("Pumping", "seepage", mesh_size=0.5, axisymmetric=True)
    r = solve(p, a)
    Q = 2 * math.pi * 1e-4 * 5.0 * 10.0 / math.log(50.0 / 0.5)
    assert r["axisymmetric"] and r["inflow"] == pytest.approx(Q, rel=0.015)
    nodes, h = np.asarray(r["nodes"]), np.asarray(r["head"])
    i = int(np.argmin(np.abs(nodes[:, 0] - 5.0) + np.abs(nodes[:, 1] - 2.5)))
    assert h[i] == pytest.approx(10 + 10 * math.log(nodes[i, 0] / 0.5) / math.log(100.0), abs=0.1)


def test_axisymmetric_needs_positive_radius():
    from geolab.seep3d import run_axisymmetric
    p = _aquifer(r1=-1.0)
    a = p.add_analysis("Bad", "seepage", mesh_size=1.0)
    with pytest.raises(ValueError, match="radius"):
        run_axisymmetric(p, a)


def test_3d_extrusion_equals_2d():
    from geolab import examples
    from geolab.seep import run_seepage
    from geolab.solver import solve
    p = examples.earth_dam()
    a = next(x for x in p.analyses if x.kind == "seepage")
    r2 = run_seepage(p, a)
    a.three_d, a.width3d, a.n_layers3d = True, 10.0, 3
    r3 = solve(p, a)
    assert r3["three_d"]["n_nodes"] == 4 * len(r2["nodes"])
    assert r3["outflow"] == pytest.approx(10.0 * r2["outflow"], rel=1e-6)
    assert np.max(np.abs(np.asarray(r3["head"]) - np.asarray(r2["head"]))) < 1e-6


def test_3d_wells():
    from geolab.model import new_project
    from geolab.seep3d import run_seepage3d, slice_results, text_report
    p = new_project()
    p.analyses.clear()
    m = p.materials[0]
    m.k_sat, m.hyd_model = 1e-4, "saturated"
    p.add_region([(0, 0), (40, 0), (40, 5), (0, 5)], m.id)
    p.add_bc("Left", "head", 20, [(0, 0), (0, 5)])
    p.add_bc("Right", "head", 20, [(40, 0), (40, 5)])
    a = p.add_analysis("Well", "seepage", mesh_size=1.0, three_d=True, width3d=40.0, n_layers3d=10)
    a.wells = [[20.0, 20.0, 5.0, 0.0, 1, 0.002]]               # pumping 0.002 m3/s
    r = run_seepage3d(p, a)
    w = r["three_d"]["wells"][0]
    assert w["type"] == "flow" and w["flow"] == pytest.approx(0.002, rel=1e-6)
    assert r["inflow"] == pytest.approx(0.002, rel=1e-6)
    # the drawdown is largest at the well and symmetric about it
    near = slice_results(r, 20.0)
    far = slice_results(r, 2.0)
    assert min(near["head"]) < min(far["head"]) < 20.0
    a.wells = [[20.0, 20.0, 5.0, 0.0, 0, 15.0]]                 # fixed head 15 m
    r = run_seepage3d(p, a)
    assert r["three_d"]["wells"][0]["flow"] > 0
    assert "Well 1" in text_report(r, {"length": "m", "flux": "m3/s"})


def test_3d_boundary_over_part_of_the_width():
    from geolab.model import new_project
    from geolab.seep3d import run_seepage3d
    p = new_project()
    p.analyses.clear()
    m = p.materials[0]
    m.k_sat, m.hyd_model = 1e-5, "saturated"
    p.add_region([(0, 0), (20, 0), (20, 4), (0, 4)], m.id)
    p.add_bc("Left", "head", 10, [(0, 0), (0, 4)])
    p.add_bc("Right", "head", 5, [(20, 0), (20, 4)], z1=0.0, z2=5.0)
    a = p.add_analysis("Part", "seepage", mesh_size=1.0, three_d=True, width3d=20.0, n_layers3d=8)
    q_part = run_seepage3d(p, a)["outflow"]
    p.boundary_conditions[1].z2 = 0.0
    q_full = run_seepage3d(p, a)["outflow"]
    assert 0 < q_part < q_full


def test_3d_rejects_climate():
    from geolab.model import new_project
    from geolab.seep3d import run_seepage3d
    p = _aquifer()
    p.add_bc("Rain", "climate", 1e-7, [(0.5, 5), (50, 5)])
    a = p.add_analysis("3D", "seepage", mesh_size=2.0, three_d=True, width3d=10.0, n_layers3d=2)
    with pytest.raises(ValueError, match="not available in 3D"):
        run_seepage3d(p, a)


def test_slope3d_with_3d_seepage_pore_pressure():
    from geolab import examples
    from geolab.solver import solve
    p = examples.earth_dam()
    seep = next(x for x in p.analyses if x.kind == "seepage")
    slope = next(x for x in p.analyses if x.kind == "slope")
    seep.three_d, seep.width3d, seep.n_layers3d = True, 30.0, 3
    slope.three_d, slope.width3d, slope.slide_lengths = True, 30.0, [[30.0]]
    slope.pwp, slope.parent_id = "seepage", seep.id
    r = solve(p, slope)
    assert r["three_d"]["fos"] > 0 and r["three_d"]["fos"] >= r["three_d"]["fos_2d"] - 1e-6


# ------------------------------------------------------------------ dynamic pore pressure
def test_pore_pressure_functions():
    from geolab.quake import _Damage, cycles_to_liquefy, ru_from_damage
    assert ru_from_damage([0.0, 1.0, 3.0]).tolist() == [0.0, 1.0, 1.0]
    assert ru_from_damage(0.5, 0.5) == pytest.approx((2 / math.pi) * math.asin(0.5))
    assert cycles_to_liquefy(0.2, 0.2, 0.34) == pytest.approx(15.0)
    assert cycles_to_liquefy(0.4, 0.2, 0.34) == pytest.approx(15 * 2 ** (-1 / 0.34))
    # 15 uniform cycles at CSR = CRR15 liquefy (D = 1)
    d = _Damage(np.array([100.0]), np.array([0.2]), np.array([0.34]), np.array([0.7]))
    for k in range(15 * 40 + 1):
        d.step(np.array([20.0 * math.sin(2 * math.pi * k / 40 + 0.01)]), k / 40)
    assert d.D[0] == pytest.approx(1.0, rel=0.04) and d.finish()[0] > 0.95


@pytest.fixture(scope="module")
def quake():
    from geolab import examples
    p = examples.earthquake_slope()
    dyn = next(x for x in p.analyses if x.kind == "dynamic")
    dyn.motion = [r for r in dyn.motion if r[0] <= 5.0]
    dyn.n_eq_iter = 2
    return p, dyn


def test_liquefaction_grows_with_lower_resistance(quake):
    from geolab.quake import run_dynamic
    p, dyn = quake
    dyn.pwp_generation = True
    out = []
    for crr in (0.6, 0.12):
        for m in p.materials:
            m.liq_crr = crr
        r = run_dynamic(p, dyn)
        out.append(r)
        assert len(r["ru"]) == len(r["tris"]) and 0 <= min(r["ru"]) and max(r["ru"]) <= 1.0
    assert out[1]["liquefied_area"] > out[0]["liquefied_area"]
    assert np.mean(out[1]["ru"]) > np.mean(out[0]["ru"])


def test_pore_pressure_needs_crr(quake):
    from geolab.quake import run_dynamic
    p, dyn = quake
    p2 = p.copy()
    for m in p2.materials:
        m.liq_crr = 0.0
    a = p2.analysis(dyn.id)
    a.pwp_generation = True
    with pytest.raises(ValueError, match="cyclic resistance"):
        run_dynamic(p2, a)


def test_post_earthquake_stability_is_lower(quake):
    from geolab.solver import solve
    p, dyn = quake
    p = p.copy()
    for m in p.materials:
        m.liq_crr = 0.2
    d = p.analysis(dyn.id)
    d.pwp_generation = True
    slope = next(x for x in p.analyses if x.kind == "slope")
    slope.method = "bishop"
    static = solve(p, slope)["critical"]["fos"]
    slope.post_earthquake = True
    after = solve(p, slope)["critical"]["fos"]
    assert after < static


# ------------------------------------------------------------------ interface
def test_interface_return_map_is_exact():
    from geolab.interface import return_map, shear_normal
    th = math.radians(30)
    cs, sn = math.cos(th), math.sin(th)
    sig = np.array([[-80.0, -120.0, 400.0, -90.0]])
    tau, s_n = shear_normal(sig, cs, sn)
    out = return_map(sig, cs, sn, 5.0, math.tan(math.radians(20)))
    t2, n2 = shear_normal(out, cs, sn)
    assert n2[0] == pytest.approx(s_n[0]) and abs(t2[0]) == pytest.approx(5.0 - s_n[0] * math.tan(math.radians(20)))
    assert out[0, 3] == sig[0, 3]


def test_region_axis():
    from geolab.interface import region_axis
    th, t, L = region_axis([(0, 1), (10, 1), (10, 1.1), (0, 1.1)])
    assert abs(math.sin(th)) < 1e-9 and t == pytest.approx(0.1) and L == pytest.approx(10.0)
    th, t, L = region_axis([(0, 0), (0.2, 0), (0.2, 8), (0, 8)])
    assert abs(math.cos(th)) < 1e-9 and t == pytest.approx(0.2)


def _shear_box(tau, delta=20.0):
    from geolab.model import new_project
    p = new_project()
    p.analyses.clear()
    soil = p.materials[0]
    soil.E, soil.nu, soil.unit_weight, soil.stress_model = 1e6, 0.3, 0.0, "linear_elastic"
    ifm = p.add_material("Interface", stress_model="interface", E=1e5, nu=0.3, unit_weight=0.0,
                         iface_ks=1e4, iface_kn=1e6, iface_c=0.0, iface_delta=delta)
    p.add_region([(0, 0), (10, 0), (10, 1), (0, 1)], soil.id)
    p.add_region([(0, 1), (10, 1), (10, 1.1), (0, 1.1)], ifm.id)
    p.add_region([(0, 1.1), (10, 1.1), (10, 2.1), (0, 2.1)], soil.id)
    a = p.add_analysis("Shear", "stress", stress_type="load", mesh_size=0.25, load_steps=5)
    p.add_bc("Base", "fixed_xy", 0, [(0, 0), (10, 0)])
    p.add_bc("Left", "fixed_x", 0, [(0, 0), (0, 1)])
    p.add_bc("Right", "fixed_x", 0, [(10, 0), (10, 1)])
    p.add_bc("Normal", "pressure", 50, [(10, 2.1), (0, 2.1)])
    p.add_bc("Shear", "shear", tau, [(10, 2.1), (0, 2.1)])
    return p, a


def _slip(r):
    n, dx = np.asarray(r["nodes"]), np.asarray(r["dx"])
    return abs(dx[np.abs(n[:, 1] - 2.1) < 1e-6].mean() - dx[np.abs(n[:, 1] - 1.0) < 1e-6].mean())


def test_interface_elastic_slip():
    from geolab.sigma import run_stress
    p, a = _shear_box(10.0)
    r = run_stress(p, a)
    assert r["converged"]
    # slip = tau / ks, plus a little shear of the 2 m of soil (2 tau / G = 5 %)
    assert _slip(r) == pytest.approx(10.0 / 1e4 * 1.05, rel=0.03)


def test_interface_slides_beyond_its_strength():
    from geolab.sigma import run_stress
    p, a = _shear_box(25.0)              # strength 50 tan 20 = 18.2 kPa
    r = run_stress(p, a)
    assert not r["converged"] and _slip(r) > 0.05


# ------------------------------------------------------------------ UI
@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(app, tmp_path, monkeypatch):
    from PySide6.QtCore import QSettings

    from geolab import backup, usertemplates
    from geolab.ui import appearance, main_window
    ini = str(tmp_path / "settings.ini")
    monkeypatch.setattr(main_window, "_app_settings", lambda: QSettings(ini, QSettings.IniFormat))
    monkeypatch.setattr(backup, "autosave_dir", lambda: tmp_path / "Autosave")
    monkeypatch.setattr(appearance, "fonts_dir", lambda: tmp_path / "fonts")
    monkeypatch.setattr(usertemplates, "templates_dir", lambda: tmp_path / "Templates")
    w = main_window.MainWindow()
    w.resize(1200, 800)
    w.show()
    app.processEvents()
    yield w
    for i in range(len(w.docs)):
        if w.docs[i]:
            w.docs[i]["dirty"] = False
    w.dirty = False
    w.close()


def test_settings_tabs(app):
    from geolab import examples
    from geolab.ui.dialogs import AnalysisEditor
    p = examples.earth_dam()
    for a in p.analyses:
        ed = AnalysisEditor(p, a)
        titles = [ed.tabs.tabText(i) for i in range(ed.tabs.count())]
        if a.kind == "seepage":
            assert "3D / Axisymmetric" in titles
        if a.kind == "slope":
            assert "3D" in titles


def test_3d_views(win, app):
    from geolab import examples
    from geolab.solver import solve
    from geolab.ui.view3d import View3DDialog
    p = examples.earth_dam()
    seep = next(x for x in p.analyses if x.kind == "seepage")
    seep.three_d, seep.width3d, seep.n_layers3d = True, 20.0, 2
    seep.wells = [[60.0, 10.0, 10.0, 2.0, 0, 5.0]]
    win.set_project(p) if hasattr(win, "set_project") else setattr(win, "project", p)
    solve(p, seep)
    win.current_aid = seep.id
    d = View3DDialog(win, seep)
    d.show()
    app.processEvents()
    assert not d.view.grab().isNull()
    d.close()
    html = win.result_summary(seep, seep.results)
    assert "3D" in html and "Well 1" in html
    z = win.choose_section(5.0)
    assert z == 5.0 and seep.results["slice_z"] == 5.0
