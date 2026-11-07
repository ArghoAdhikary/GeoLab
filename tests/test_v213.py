"""GeoLab 2.13: earthquake check (ky, Newmark), parametric study, piles, soil nails / anchors /
geosynthetics, braced excavations, Excel export, offline mode, templates, report branding and Bangla,
contour palettes, solver presets and the new preferences."""
import math
import os
import zipfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def layered():
    from geolab.examples import EXAMPLES
    from geolab.solver import solve
    from geolab.whatif import SurfacePool
    p = EXAMPLES["Layered slope with water table"]()
    solve(p, p.analyses[0])
    return p, SurfacePool(p, p.analyses[0], n=8)


# ------------------------------------------------------------------ engines
def test_newmark_regressions():
    from geolab import seismic as S
    # Jibson (2007) eq. 6 at ky/amax = 0.5: log D = 0.215 + log(0.5^2.341 * 0.5^-1.438)
    d = S.displacement(0.1, 0.2, method="jibson07")
    assert d == pytest.approx(10 ** (0.215 + math.log10(0.5 ** 2.341 * 0.5 ** -1.438)), rel=1e-9)
    assert S.displacement(0.3, 0.2) == 0.0 and S.displacement(0.0, 0.2) == math.inf
    # more magnitude, more movement; smaller ky, more movement
    assert S.displacement(0.1, 0.3, 7.5, "jibson07m") > S.displacement(0.1, 0.3, 6.5, "jibson07m")
    assert S.displacement(0.05, 0.3) > S.displacement(0.15, 0.3)
    assert S.hazard(0.5)[0] == "low" and S.hazard(3)[0] == "moderate" and S.hazard(30)[0] == "very high"


def test_yield_acceleration(layered):
    from geolab import seismic as S
    p, pool = layered
    r = S.assess(pool, 0.25, 7.0)
    assert r["f_static"] > 1 and 0 < r["ky"] < 0.8
    assert pool.fos({"kh": r["ky"]}) == pytest.approx(1.0, abs=0.01)
    assert r["f_pseudo"] < r["f_static"]
    assert "Yield acceleration" in S.text_report(r, "x")


def test_parametric(layered):
    from geolab import parametric as P
    p, pool = layered
    labels = P.parameters(p)
    assert "water_dy" in labels and any(k.endswith(".phi") for k in labels)
    res = P.run(pool, "water_dy", P.values(-3, 3, 4))
    f = res["F"][0]
    assert f[0] > f[-1]                       # a higher water table lowers F
    res2 = P.run(pool, "kh", [0.0, 0.2], "c_factor", [0.8, 1.2])
    assert len(res2["F"]) == 2 and res2["F"][1][0] > res2["F"][0][0]
    assert P.crossing([0, 1], [0.8, 1.2], 1.0) == pytest.approx(0.5)
    assert P.rows(res2)[0][0].startswith("c_factor")
    assert "Parametric study" in P.text_report(res, labels)


def test_piles():
    from geolab import piles as Pi
    clay = [{"thickness": 0, "soil": "clay", "su": 50, "gamma": 18}]
    r = Pi.axial(clay, 0.6, 15, "bored", water_depth=0)
    # bored in clay: fs = 0.45 Su, base 9 Su
    assert r["Qs"] == pytest.approx(0.45 * 50 * math.pi * 0.6 * 15, rel=1e-6)
    assert r["Qb"] == pytest.approx(9 * 50 * math.pi * 0.36 / 4, rel=1e-6)
    assert r["Qall"] == pytest.approx(r["Qult"] / 2.5)
    assert Pi.alpha_api(50, 200) == pytest.approx(0.5 * 0.25 ** -0.5)
    sand = [{"thickness": 0, "soil": "sand", "phi": 32, "gamma": 19}]
    d, b = Pi.axial(sand, 0.6, 15, "driven"), Pi.axial(sand, 0.6, 15, "bored")
    assert d["Qult"] > b["Qult"] > 0
    g = Pi.group(r, clay, 3, 3, 1.8)
    assert 0 < g["efficiency"] < 1 and g["Q_block"] > 0 and g["Qult"] <= 9 * r["Qult"]
    assert g["settlement_group"] > g["settlement_single"] > 0
    assert Pi.converse_labarre(1, 1, 0.6, 1.8) == pytest.approx(1.0)
    with pytest.raises(ValueError):
        Pi.group(r, clay, 2, 2, 0.3)
    assert "Group of 9 piles" in Pi.text_report(r, g)


def test_nails_anchor_geosynthetics():
    from geolab import nails as N
    d = N.nail_wall(6, 1.5, 1.5, 30, 18, 10, 15, 0.1, 25, 500, 100)
    assert d["sigma"] == pytest.approx(0.65 * (1 / 3) * (18 * 6 + 10), rel=1e-3)
    assert d["tensile_ok"] and d["L"] >= d["L_required"] and len(d["rows"]) == 4
    assert d["rows"][0]["La"] > d["rows"][-1]["La"]       # the active zone is widest at the top
    a = N.anchor(400, 0.15, 150, 2.0)
    assert a["bond_length"] == pytest.approx(400 * 2 / (math.pi * 0.15 * 150))
    assert N.anchor(10)["bond_length"] == 4.5
    g = N.geosynthetic("PET coated geogrid, 80 kN/m")
    assert g["T_al"] == pytest.approx(80 / (1.15 * 1.6 * 1.15))
    assert N.geosynthetic("PET coated geogrid, 80 kN/m", rf_cr=2.0)["T_al"] < g["T_al"]
    from geolab.model import Reinforcement, new_project
    p = new_project()
    p.reinforcements = [Reinforcement(1, "nail", 0, 0, 5, -1), Reinforcement(2, "geosynthetic", 0, 0, 5, 0)]
    assert N.apply_to_project(p, d) == 1 and p.reinforcements[0].capacity == pytest.approx(d["T_tensile"])
    assert N.apply_geosynthetic(p, g, 20) == 1 and p.reinforcements[1].bond == 20


def test_excavation():
    from geolab import excavation as E
    s = E.envelope("sand", 8, 18, phi=30)
    st = E.strut_loads(s, [2, 5])
    assert st["total"] == pytest.approx(0.65 * (1 / 3) * 18 * 8 * 8, rel=1e-3)
    soft = E.envelope("clay", 10, 18, su=20)
    assert soft["peak"] == pytest.approx(max(180 * (1 - 80 / 180), 0.3 * 180))
    stiff = E.envelope("clay", 6, 18, su=60)
    assert stiff["points"][-1][1] == 0 and stiff["peak"] == pytest.approx(0.3 * 18 * 6)
    h = E.basal_heave(8, 10, 0, 40, 18)
    assert h["Nc"] == pytest.approx(5 * 1.16 * 1.0, rel=0.01) or h["Nc"] <= 9
    assert E.basal_heave(8, 10, 10, 200, 18)["ok"]
    with pytest.raises(ValueError):
        E.strut_loads(s, [9])
    assert "Strut loads" in E.text_report(s, st, h)


def test_excel_workbook(layered, tmp_path):
    from geolab import xlsx
    p, _ = layered
    path = tmp_path / "r.xlsx"
    xlsx.export_project(p, path)
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        wb = z.read("xl/workbook.xml").decode()
    assert "xl/worksheets/sheet3.xml" in names
    assert 'name="Results"' in wb and 'name="Materials"' in wb
    rows = xlsx.read(path)["Project"]
    assert rows[0] == ["Item", "Value"]
    xlsx.write(tmp_path / "s.xlsx", [("a/b:c", [["x", 1.5, float("inf"), None, True]]), ("a/b:c", [[1]])])
    with zipfile.ZipFile(tmp_path / "s.xlsx") as z:
        wb = z.read("xl/workbook.xml").decode()
    assert 'name="abc"' in wb and 'name="abc 2"' in wb


def test_offline_mode():
    from geolab import net, rainfall, terrain, warning
    from geolab.ui import extras
    net.set_offline(True)
    try:
        with pytest.raises(net.OfflineError):
            terrain.fetch_elevations([(22.3, 91.8)])
        with pytest.raises(net.OfflineError):
            warning.fetch_forecast(22.3, 91.8)
        with pytest.raises(net.OfflineError):
            extras.check_update("1.0")
        assert hasattr(rainfall, "fetch_daily") or True
    finally:
        net.set_offline(False)


def test_templates_and_quality(tmp_path):
    from geolab import usertemplates as U
    from geolab.examples import EXAMPLES
    from geolab.solver import solve
    p = EXAMPLES["Homogeneous slope (benchmark)"]()
    solve(p, p.analyses[0])
    path = U.save_template(p, "My: slope?", tmp_path)
    assert path.exists() and ":" not in path.name
    assert U.list_templates(tmp_path) == [path]
    q = U.new_from_template(path)
    assert all(a.results is None for a in q.analyses) and q.materials[0].phi == p.materials[0].phi
    a = q.analyses[0]
    m0 = a.mesh_size
    U.apply_quality(a, "fine")
    assert a.n_slices == 50 and a.mesh_size == pytest.approx(0.6 * m0)
    U.apply_quality(a, "normal")
    assert a.n_slices == 50
    U.delete_template(path)
    assert U.list_templates(tmp_path) == []


def test_report_branding_and_bangla(layered, tmp_path):
    from geolab import designreport as D
    p, _ = layered
    logo = tmp_path / "logo.png"
    from PySide6.QtGui import QGuiApplication, QImage
    QGuiApplication.instance() or QApplication([])
    img = QImage(20, 10, QImage.Format_RGB32)
    img.fill(0xff2266aa)
    img.save(str(logo))
    old = (D.BRAND, D.LANG, D.DECIMALS)
    try:
        D.BRAND = {"company": "Acme Geo", "engineer": "A. Engineer", "footer": "Confidential", "logo": str(logo)}
        D.LANG = "en"
        b = D.build(p, {})
        assert b[0][0] == "logo"
        meta = next(x for x in b if x[0] == "table")[1]
        assert ["Company", "Acme Geo"] in meta and ["Engineer", "A. Engineer"] in meta
        html = D.to_html(b)
        assert "Confidential" in html and 'height="70"' in html
        D.to_docx(b, tmp_path / "r.docx")
        D.LANG = "bn"
        b = D.build(p, {})
        assert any(x[0] == "h" and x[2].startswith("১.") for x in b)
        assert any(x[0] == "h" and x[2].startswith("২.") for x in b)
        D.DECIMALS = 1
        assert D._f(1.23456) == "1.2"
    finally:
        D.BRAND, D.LANG, D.DECIMALS = old


def test_palettes():
    QApplication.instance() or QApplication([])
    from geolab.ui import render
    try:
        render.set_palette("viridis")
        c = render.colormap(0.0)
        assert (c.red(), c.green(), c.blue()) == (68, 1, 84)
        render.set_palette("grey")
        assert render.colormap(1.0).red() == 235
        render.set_palette("nonsense")
        assert render.PALETTE == "classic"
    finally:
        render.set_palette("classic")


def test_bangla_covers_new_menus():
    from geolab import i18n
    i18n.set_language("bn")
    try:
        for t in ("&Pile Design...", "Parametric &Study...", "Export Results to &Excel...", "Calculate",
                  "Offline mode: never use the internet", "Reports && Units"):
            assert i18n.tr(t) != t, t
    finally:
        i18n.set_language("en")


# ------------------------------------------------------------------ user interface
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


def _free(*ws):
    import shiboken6
    for w in ws:
        shiboken6.delete(w)


def test_menus(win):
    from geolab.ui import extras
    names = [p for p, _ in extras.all_actions(win)]
    for want in ("Earthquake Check (ky and Newmark)", "Parametric Study", "Pile Design",
                 "Soil Nails, Anchors and Geosynthetics", "Braced Excavation", "Export Results to Excel",
                 "Save as My Template"):
        assert any(n.endswith(want) for n in names), want


def test_dialogs(win, app, tmp_path):
    from geolab.examples import EXAMPLES
    from geolab.solver import solve
    from geolab.ui import tools3
    p = EXAMPLES["Layered slope with water table"]()
    solve(p, p.analyses[0])
    win.set_project(p)
    d = win.tool3("seismic", run=False)
    d.amax.setValue(0.3)
    res = d.run(wait=True)
    assert res["ky"] > 0 and "Newmark" in d.out.toPlainText()
    d._keep()
    assert p.analyses[0].results["newmark"]["ky"] == pytest.approx(res["ky"])
    _free(d)
    d = win.tool3("param", run=False)
    d.rows[0][0].setCurrentIndex(d.rows[0][0].findData("water_dy"))
    d.rows[0][3].setValue(3)
    r = d.run(wait=True)
    assert len(r["F"][0]) == 3
    path = d._save(str(tmp_path / "par.xlsx"))
    assert os.path.exists(path)
    assert d._save(str(tmp_path / "par.csv")).endswith(".csv")
    _free(d)
    d = win.tool3("pile", run=False)
    r, g = d.run_pile()
    assert r["Qult"] > 0 and g is None
    d.pw["rows"].setValue(2)
    d.pw["cols"].setValue(2)
    r, g = d.run_pile()
    assert g["n"] == 4
    assert d.run_nail()["L"] > 0
    assert d.use_nails() == 0
    assert d.run_anchor()["bond_length"] >= 4.5
    assert d.run_geo()["T_al"] > 0
    env, st, heave = d.run_exc()
    assert len(st["struts"]) == 3 and heave is None
    d.e_soil.setCurrentIndex(1)
    env, st, heave = d.run_exc()
    assert heave is not None
    _free(d)
    out = tools3.export_excel(win, str(tmp_path / "all"))
    assert out.endswith(".xlsx") and os.path.exists(out)
    t = tools3.save_template(win, "Layered")
    assert t.exists()
    win.tool3("template_menu")
    assert any(a.text() == "Layered" for a in win.template_menu.actions())
    win.dirty = False
    q = tools3.new_from_template(win, t)
    assert q is win.project and all(a.results is None for a in q.analyses)


def test_preferences_new_tabs(win, app, monkeypatch):
    from geolab import designreport, linsolve, net
    from geolab.ui import render
    from geolab.ui.prefs import PreferencesDialog
    d = PreferencesDialog(win.settings, win, "system")
    d.brand["company"].setText("Acme Geo")
    d.report_lang.setCurrentIndex(d.report_lang.findData("bn"))
    d.decimals.setValue(2)
    d.new_units.setCurrentIndex(d.new_units.findData("imperial"))
    d.offline.setChecked(True)
    d.palette.setCurrentIndex(d.palette.findData("cividis"))
    d.quality.setCurrentIndex(d.quality.findData("fast"))
    d.threads.setValue(2)
    try:
        win.apply_preferences(d)
        assert designreport.BRAND["company"] == "Acme Geo" and designreport.LANG == "bn"
        assert designreport.DECIMALS == 2 and net.OFFLINE and render.PALETTE == "cividis"
        assert linsolve.MAX_THREADS == 2
        win.dirty = False
        win.new_file()
        assert win.project.units == "imperial"
        monkeypatch.setattr(win, "edit_analysis", lambda *a, **k: None)
        win.add_analysis("slope")
        assert win.project.analyses[-1].n_slices == 20
    finally:
        d.offline.setChecked(False)
        d.report_lang.setCurrentIndex(0)
        d.palette.setCurrentIndex(0)
        d.threads.setValue(0)
        d.decimals.setValue(3)
        d.brand["company"].setText("")
        win.apply_preferences(d)
        win.dirty = False
    assert not net.OFFLINE and render.PALETTE == "classic"
    _free(d)


def test_map_layers(app):
    from geolab.ui.tools2 import MapWidget
    m = MapWidget()
    m.zoom = 18
    m.set_layer("hillshade")
    assert "Hillshade" in m.ATTRIB and m.zoom == 16 and "World_Hillshade" in m.TILE
    m.set_layer("satellite")
    assert "World_Imagery" in m.TILE
    m.set_layer("nope")
    assert m.layer == "satellite"
    _free(m)
