"""GeoLab 2.12: map sections, early warning, probabilistic, DXF, foundations, lab tests, SWCC, quantities,
compare, and the working-comfort features (palette, shortcuts, tabs, history, versions, update check)."""
import io
import json
import math
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def opener_for(fn):
    """A urlopen stand-in that answers with fn(url) -> dict."""
    def op(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        return FakeResponse(json.dumps(fn(url)).encode())
    return op


def hill(n):
    return [50 + 40 / (1 + math.exp(-(i * 400 / (n - 1) - 200) / 30)) for i in range(n)]


# ------------------------------------------------------------------ engines
def test_terrain_profile_and_model():
    from geolab import terrain
    from urllib.parse import parse_qs, urlparse

    def answer(url):
        q = parse_qs(urlparse(url).query)
        n = len(q["latitude"][0].split(","))
        return {"elevation": hill(n)[:n]}
    pr = terrain.profile((22.30, 91.80), (22.30, 91.804), 40, opener=opener_for(answer))
    assert len(pr["x"]) == 40 and 380 < pr["length"] < 440
    assert abs(terrain.haversine(0, 0, 0, 1) - 111195) < 50
    p = terrain.build_model(pr, water_depth=2.0)
    assert len(p.regions) == 3 and p.piezometric_line and p.analyses[0].search.entry_x2 > 0
    with pytest.raises(ValueError):
        terrain.profile((1, 1), (1, 1), 10, opener=opener_for(answer))


def forecast_answer(url):
    days = [f"2026-07-{i + 1:02d}" for i in range(10)]
    return {"daily": {"time": days, "precipitation_sum": [0, 5, 30, 120, 95, 40, 0, 0, 0, 0],
                      "et0_fao_evapotranspiration": [3] * 10}}


def test_warning_quick_and_thresholds():
    from geolab import warning as W
    from geolab.examples import EXAMPLES
    from geolab.solver import solve
    from geolab.whatif import SurfacePool
    s = W.fetch_forecast(22.36, 91.78, 5, 5, opener=opener_for(forecast_answer))
    assert len(s["rain"]) == 10
    r = W.quick_assessment(s, None)
    assert r["days"][3]["level"] in ("yellow", "red")          # 120 mm in a day
    assert W.antecedent([10, 0], 0.5) == [10, 5]
    p = EXAMPLES["Layered slope with water table"]()
    solve(p, p.analyses[0])
    pool = SurfacePool(p, p.analyses[0], n=8)
    r2 = W.quick_assessment(s, pool)
    f = [d["fos"] for d in r2["days"]]
    assert f[5] < f[0]                                          # wetter -> lower F
    assert "Alert" in W.text_report(r2)


def test_warning_model_method_on_rainfall_example():
    from geolab import warning as W
    from geolab.examples import EXAMPLES
    p = EXAMPLES["Rainfall and evaporation on a slope"]()
    s = {"dates": [f"d{i}" for i in range(6)], "rain": [0, 60, 120, 80, 0, 0], "et0": [3] * 6, "first_forecast": 3}
    r = W.model_assessment(p, s)
    f = [d["fos"] for d in r["days"]]
    assert all(x is not None for x in f) and min(f) < f[0]


def test_reliability_and_tornado():
    from geolab import reliability as R
    from geolab.examples import EXAMPLES
    from geolab.solver import solve
    from geolab.whatif import SurfacePool
    p = EXAMPLES["Homogeneous slope (benchmark)"]()
    solve(p, p.analyses[0])
    pool = SurfacePool(p, p.analyses[0], n=6)
    vs = R.variables(p)
    assert {v["key"].split(".")[1] for v in vs} == {"cohesion", "phi", "unit_weight"}
    res = R.run(pool, vs, n=30, seed=3)
    assert res["n"] == 30 and 0.3 < res["pf"] < 0.9 and abs(res["mean"] - pool.base_fos) < 0.1
    t = R.tornado(pool, vs)
    assert t[0]["label"].endswith("phi'") and t[0]["low"] < pool.base_fos < t[0]["high"]
    assert R.usace(3.2) == "above average" and "Pf" in R.text_report(res, t, vs)


def test_dxf_round_trip(tmp_path):
    from geolab import dxf
    from geolab.examples import EXAMPLES
    from geolab.solver import solve
    p = EXAMPLES["Layered slope with water table"]()
    solve(p, p.analyses[0])
    out = tmp_path / "m.dxf"
    dxf.export_dxf(p, out, p.analyses[0])
    text = out.read_text()
    assert "SLIP_SURFACE" in text and "F = " in text
    q, notes = dxf.import_dxf(out)
    assert len(q.regions) == len(p.regions) and q.piezometric_line
    # LINE entities that close into a loop, in millimetres
    lines = "".join(f"0\nLINE\n8\nCLAY\n10\n{a[0]}\n20\n{a[1]}\n11\n{b[0]}\n21\n{b[1]}\n"
                    for a, b in [((0, 0), (10000, 0)), ((10000, 0), (10000, 5000)), ((10000, 5000), (0, 5000)),
                                 ((0, 5000), (0, 0))])
    f2 = tmp_path / "lines.dxf"
    f2.write_text(f"0\nSECTION\n2\nENTITIES\n{lines}0\nENDSEC\n0\nEOF\n")
    q2, _ = dxf.import_dxf(f2, scale=0.001)
    assert len(q2.regions) == 1 and max(x for x, _ in q2.regions[0].points) == pytest.approx(10.0)
    assert q2.materials[0].name == "CLAY"


def test_foundations():
    from geolab import foundations as F
    nc, nq, ng = F.factors(30)
    assert (round(nc, 2), round(nq, 2), round(ng, 2)) == (30.14, 18.40, 22.40)
    assert F.factors(0)[0] == 5.14
    r = F.bearing(2, 0, 1, 0, 30, 18)
    assert 700 < r["qu"] < 900
    # the water table at the base lowers the capacity
    assert F.bearing(2, 0, 1, 0, 30, 18, water_depth=1.0)["qu"] < r["qu"]
    assert F.ka(30) == pytest.approx(1 / 3) and F.kp(30) == pytest.approx(3.0)
    w = F.retaining_wall(5, 3.5, 0.8, 0.3, 0.5, 0.5)
    assert w["FS_overturning"] > 2 and w["middle_third"]
    assert F.retaining_wall(5, 3.5, 0.8, 0.3, 0.5, 0.5, water_h=3)["FS_sliding"] < w["FS_sliding"]
    sp = F.sheet_pile_cantilever(4, 32, 18)
    assert 2 < sp["d0"] < 6 and sp["embedment"] == pytest.approx(1.2 * sp["d0"])
    st = F.settlement(100, 2, 2, 1, [{"thickness": 4, "gamma": 17, "Cc": 0.3, "e0": 1.0, "kind": "clay"}],
                      water_depth=1)
    assert st["consolidation"] > 0.01


def test_labtest_and_swcc():
    from geolab import labtest, swcc
    rows = [{"sigma3": s3, "sigma1": s3 * 3 + 20 * math.sqrt(3)} for s3 in (50, 100, 200)]
    r = labtest.triaxial(rows)
    assert r["c"] == pytest.approx(10, abs=1e-6) and r["phi"] == pytest.approx(30, abs=1e-6)
    d = labtest.direct_shear(labtest.parse("sigma tau\n50 40\n100 69\n200 127", "direct_shear"))
    assert 10 < d["c"] < 12 and 29 < d["phi"] < 31
    assert labtest.unconsolidated_undrained([{"sigma3": 100, "sigma1": 180}])["su"] == 40
    sand = swcc.estimate(0.1, 0.3, 0.6)
    assert 1e-5 < sand["k_sat"] < 1e-3 and sand["vg_n"] > 1.5
    clay = swcc.estimate(e=0.8, uscs="CH")
    assert clay["texture"] == "clay" and clay["k_sat"] < 1e-6 and clay["air_entry_kpa"] > sand["air_entry_kpa"]


def test_quantities_and_compare():
    from geolab import quantities as Q
    from geolab.examples import EXAMPLES
    from geolab.solver import solve
    cf = Q.cut_fill([(0, 0), (10, 5), (20, 5)], [(0, 0), (10, 4), (20, 6)])
    assert cf["cut"] == pytest.approx(7.5, abs=0.05) and cf["fill"] == pytest.approx(2.5, abs=0.05)
    p = EXAMPLES["Homogeneous slope (benchmark)"]()
    solve(p, p.analyses[0])
    q = Q.quantities(p, 10)
    assert q["materials"]["Clayey sand"]["volume"] == pytest.approx(7500)
    c = Q.cost(q, {"material": {"Clayey sand": 100}})
    assert c["total"] == pytest.approx(750000)
    rows = Q.compare([("A", p)])
    assert rows[0]["fos"] == pytest.approx(p.analyses[0].results["critical"]["fos"]) and rows[0]["pass"] is False
    assert "FAIL" in Q.text_compare(rows)


def test_update_check_versions():
    from geolab.ui import extras
    rel = {"tag_name": "v9.9.9", "html_url": "u", "body": "notes",
           "assets": [{"name": "GeoLab-Setup.exe", "browser_download_url": "s"},
                      {"name": "GeoLab-macos-intel.zip", "browser_download_url": "m"}]}
    info = extras.check_update("2.12.0", opener=opener_for(lambda u: rel))
    assert info["version"] == "9.9.9" and info["assets"]["GeoLab-Setup.exe"] == "s"
    assert extras.check_update("9.9.9", opener=opener_for(lambda u: rel)) is None
    assert extras.parse_version("v2.10.1") > extras.parse_version("2.9.9")


# ------------------------------------------------------------------ user interface
@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(app, tmp_path, monkeypatch):
    from PySide6.QtCore import QSettings

    from geolab import backup
    from geolab.ui import appearance, main_window
    ini = str(tmp_path / "settings.ini")
    monkeypatch.setattr(main_window, "_app_settings", lambda: QSettings(ini, QSettings.IniFormat))
    monkeypatch.setattr(backup, "autosave_dir", lambda: tmp_path / "Autosave")
    monkeypatch.setattr(appearance, "fonts_dir", lambda: tmp_path / "fonts")
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


def test_menus_palette_and_shortcuts(win, app):
    from geolab.ui import extras
    names = [p for p, _ in extras.all_actions(win)]
    for want in ("Cross-Section from Map", "Landslide Early Warning", "Probabilistic Analysis and Sensitivity",
                 "Foundations and Retaining Walls", "Strength from Lab Tests", "Import AutoCAD DXF",
                 "Command Palette", "Version History", "New Tab", "Check for Updates"):
        assert any(n.endswith(want) for n in names), want
    pal = extras.CommandPalette(win)
    pal.edit.setText("version hist")
    assert "Version History" in pal.list.currentItem().text()
    pal.edit.setText("zzzzqqq")
    assert pal.list.count() == 0
    _free(pal)
    d = extras.ShortcutsDialog(win, win.settings)
    r = next(i for i, (p, _) in enumerate(d.acts) if p.endswith("Strength from Lab Tests"))
    from PySide6.QtGui import QKeySequence
    d.editors[r].setKeySequence(QKeySequence("Ctrl+Alt+L"))
    d.checks[r].setChecked(True)
    d.save()
    a = d.acts[r][1]
    assert a.shortcut().toString() == "Ctrl+Alt+L"
    assert a in win.my_toolbar.actions() and not win.my_toolbar.isHidden()
    # a clash is refused
    d2 = extras.ShortcutsDialog(win, win.settings)
    d2.editors[0].setKeySequence(QKeySequence("Ctrl+Alt+L"))
    d2.save()
    assert "twice" in d2.warn.text()
    _free(d, d2)


def test_tabs_undo_history_and_versions(win, app, tmp_path):
    from geolab.examples import EXAMPLES
    from geolab.fileio import save_project
    win.set_project(EXAMPLES["Homogeneous slope (benchmark)"]())
    first = win.project
    win.before_change()
    win.project.materials[0].cohesion = 9.0
    win.after_change("Cohesion 9")
    assert win.undo_desc == ["Cohesion 9"]
    win.history_dock.show()
    win.history.refresh()
    assert win.history.count() == 2
    win.new_tab(EXAMPLES["Layered slope with water table"]())
    assert win.tabbar.count() == 2 and win.tabbar.isVisible() and win.project is not first
    win.tabbar.setCurrentIndex(0)
    assert win.project is first and win.undo_desc == ["Cohesion 9"]
    win.history.go(win.history.item(0))                      # back to the start
    assert win.project.materials[0].cohesion != 9.0 and win.redo_desc == ["Cohesion 9"]
    win.tabbar.setCurrentIndex(1)
    win.dirty = False
    assert win.close_tab(1) and win.tabbar.count() == 1 and win.project is not None
    # version history: the file, .bak and a cloud copy
    path = tmp_path / "v.slab"
    win.path = path
    win._write_project(path)
    win.project.materials[0].cohesion = 12.0
    win._write_project(path)
    drive = tmp_path / "drive"
    drive.mkdir()
    win.settings.setValue("backup/folder", str(drive))
    win.cloud_backup(path, force=True)
    d = win.version_history(run=False)
    kinds = [x["kind"] for x in d.items]
    assert "current file" in kinds and "previous save (.bak)" in kinds and "cloud backup" in kinds
    win.project.materials[0].cohesion = 20.0
    d.table.selectRow(kinds.index("previous save (.bak)"))
    assert d.compare() is not None
    assert "Material" in d.out.toPlainText() and "20" in d.out.toPlainText()
    _free(d)


def test_tool_dialogs(win, app, tmp_path, monkeypatch):
    from geolab.examples import EXAMPLES
    from geolab.solver import solve
    p = EXAMPLES["Homogeneous slope (benchmark)"]()
    solve(p, p.analyses[0])
    win.set_project(p)
    # probabilistic
    d = win.tool2("prob", run=False)
    d.n.setValue(20)
    res, torn, vs = d.run(wait=True)
    assert res["n"] == 20 and torn and "Probability of failure" in d.out.toPlainText()
    d._keep()
    assert p.analyses[0].results["probability"]["n"] == 20
    # foundations
    f = win.tool2("found", run=False)
    assert f.run_bearing()["qu"] > 0 and "PASS" in f.out.toPlainText() or "FAIL" in f.out.toPlainText()
    assert f.run_wall()["FS_sliding"] > 0 and f.run_pile()["d0"] > 0 and f.run_settle()["total"] > 0
    # lab tests -> material
    lab = win.tool2("lab", run=False)
    r = lab.fit()
    lab.apply()
    assert win.project.materials[0].cohesion == pytest.approx(round(r["c"], 2))
    # swcc
    sw = win.tool2("swcc", run=False)
    sw.estimate()
    sw.apply()
    assert win.project.materials[0].hyd_model == "van_genuchten"
    # quantities and compare
    q = win.tool2("qty", run=False)
    assert q.calculate() is not None and "Total" in q.out.toPlainText()
    from geolab.fileio import save_project
    other = EXAMPLES["Layered slope with water table"]()
    save_project(other, tmp_path / "other.slab")
    c = win.tool2("compare", run=False)
    c.add_files([str(tmp_path / "other.slab")])
    rows = c.compare()
    assert len(rows) >= 2 and rows[-1]["fos"] is not None
    # early warning with a fake forecast
    w = win.tool2("warning", run=False)
    out = w.run(opener=opener_for(forecast_answer), wait=True)
    assert out["level"] in ("yellow", "orange", "red") and "Alert" in w.banner.text()
    watch = win.start_warning_watch(w, hours=1)
    assert watch["timer"].isActive()
    assert win.warning_tick(opener=opener_for(forecast_answer)) is not None
    # map section with fake ground levels
    m = win.tool2("map", run=False)
    m.a_lat.setText("22.30")
    m.a_lon.setText("91.80")
    m.b_lat.setText("22.30")
    m.b_lon.setText("91.804")
    from urllib.parse import parse_qs, urlparse

    def answer(url):
        n = len(parse_qs(urlparse(url).query)["latitude"][0].split(","))
        return {"elevation": hill(n)}
    assert m.get_levels(opener=opener_for(answer)) is not None
    win.dirty = False
    assert m.make_model() is not None and len(win.project.regions) == 3
    # DXF out and back in
    win.dirty = False
    path = win.export_dxf(str(tmp_path / "x.dxf"))
    assert win.import_dxf(path, scale=1.0) is not None
    # share report
    win.settings.setValue("backup/folder", str(tmp_path))
    out = win.share_report()
    assert out.exists() and "<html" in out.read_text(encoding="utf-8")[:200]
    win.dirty = False
    _free(d, f, lab, sw, q, c, w, m)


def test_thumbnail_and_crash_session(win, app, tmp_path):
    from geolab.examples import EXAMPLES
    from geolab.fileio import save_project
    from geolab.ui import extras
    f = tmp_path / "t.slab"
    save_project(EXAMPLES["Homogeneous slope (benchmark)"](), f)
    assert extras.thumbnail(f) is not None
    assert extras.begin_session() is None
    assert extras.begin_session() is not None              # the first one never ended
    extras.end_session()
    assert extras.begin_session() is None
    extras.end_session()
