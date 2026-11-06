"""Beginner helpers and the new feature dialogs, driven through the real widgets (offscreen)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(app, tmp_path, monkeypatch):
    from PySide6.QtCore import QSettings
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(tmp_path))
    from geolab.ui import main_window
    ini = str(tmp_path / "settings.ini")
    monkeypatch.setattr(main_window, "QSettings", lambda *a, **k: QSettings(ini, QSettings.IniFormat))
    w = main_window.MainWindow()
    w.resize(1200, 800)
    w.show()
    app.processEvents()
    yield w
    w.dirty = False
    w.close()


def test_step_guide_follows_the_work(win, app):
    from geolab.model import new_project
    win.set_project(new_project())
    texts = [b.text() for b in win.stepbar.buttons]
    assert "Draw the ground" in texts[0] and "Solve" in " ".join(texts)
    assert "Next: Draw the ground" in win.stepbar.hint.text()
    win.add_region([(0, 0), (30, 0), (30, 10), (0, 10)])
    app.processEvents()
    assert win.stepbar.buttons[0].text().strip().startswith("✓")
    win.stepbar.buttons[0].click()                     # opens the region tool
    assert win.canvas.mode == "region"
    win.a_steps.setChecked(False)
    assert not win.stepbar.isVisible()


def test_quick_slope_dialog_builds_a_layered_slope(win, app, monkeypatch):
    from geolab.ui.guide import QuickSlopeDialog
    d = QuickSlopeDialog(win, "metric")
    d.height.setValue(8)
    d.water_on.setChecked(True)
    d.water.setValue(3)
    d.solve_now.setChecked(False)
    d.try_accept()
    p = d.project
    assert p is not None and len(p.regions) == 2 and len(p.materials) == 2
    assert p.piezometric_line and p.analyses[0].pwp == "piezometric"
    monkeypatch.setattr("geolab.ui.main_window.QuickSlopeDialog", lambda *a, **k: d)
    d.exec = lambda: True
    win.quick_slope()
    assert win.project is p


def test_draw_a_wall_and_set_a_stage(win, app, monkeypatch):
    from geolab.examples import EXAMPLES
    from geolab.ui.dialogs import AnalysisEditor, StructureDialog
    win.set_project(EXAMPLES["Anchored excavation (staged)"]())
    p = win.project
    stage = p.analyses[1]
    win.current_aid = stage.id
    ed = AnalysisEditor(p, stage)
    assert ed.stage_list is not None and ed.stage_list.count() == 3
    ed.stage_list.item(1).setCheckState(Qt.Unchecked)
    a = ed.build()
    assert sorted(a.inactive_regions) == sorted([p.regions[0].id, p.regions[1].id])
    # draw a new geogrid with the mouse
    d = StructureDialog(None, win, p.unit, p)
    d.form.w["type"].setCurrentIndex(d.form.w["type"].findData("geogrid"))
    d.try_accept()
    monkeypatch.setattr("geolab.ui.main_window.StructureDialog", lambda *a, **k: d)
    d.exec = lambda: True
    c = win.canvas
    c.view.fit((0, 0, 40, 20), QRectF(c.rect()))
    win.set_draw_mode("structure")
    for x, y in ((20, 5), (30, 5)):
        pt = c.view.dev(x, y)
        QTest.mouseClick(c, Qt.LeftButton, Qt.NoModifier, QPoint(int(pt.x()), int(pt.y())))
    QTest.keyClick(c, Qt.Key_Return)
    st = p.structures[-1]
    assert st.type == "geogrid" and len(st.points) == 2
    # the drawing (with the stage hatching and structures) renders without errors
    win.refresh_all()
    win.canvas.grab()


def test_project_dialog_converts_units(win, app):
    from geolab.examples import EXAMPLES
    from geolab.ui.dialogs import ProjectDialog
    win.set_project(EXAMPLES["Homogeneous slope (benchmark)"]())
    d = ProjectDialog(win.project, win)
    d.units.setCurrentIndex(d.units.findData("imperial"))
    d.apply()
    assert win.project.units == "imperial"
    assert win.project.regions[0].points[1][0] == pytest.approx(70 * 3.280839895)
    assert d.not_converted


def test_material_and_bc_dialogs_have_the_new_fields(win, app):
    from geolab.ui.dialogs import BCDialog, MATERIAL_TABS, SLOPE_EXTRA
    keys = {f[0] for _, spec in MATERIAL_TABS for f in spec}
    assert {"hs_E50", "hs_Eur", "hs_m", "hs_pref", "hs_Rf", "cr", "phi_r"} <= keys
    assert any(f[0] == "rapid_drawdown" for _, spec in SLOPE_EXTRA for f in spec)
    d = BCDialog("Grass", "climate", 0.0, win, kinds=["hydraulic"], value3=3e-8, root_depth=0.5)
    pr = d.params()
    assert pr["value3"] == pytest.approx(3e-8) and pr["root_depth"] == 0.5
