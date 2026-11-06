"""GUI tests run on Qt's offscreen platform and drive the real widgets."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from geolab.solver import solve_all


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


def click(canvas, x, y, button=Qt.LeftButton):
    p = canvas.view.dev(x, y)
    QTest.mouseClick(canvas, button, Qt.NoModifier, QPoint(int(round(p.x())), int(round(p.y()))))


def test_draw_region_with_mouse_and_undo(win, app):
    c = win.canvas
    from PySide6.QtCore import QRectF
    c.view.fit((0, 0, 40, 20), QRectF(c.rect()))
    win.set_draw_mode("region")
    for x, y in [(0, 0), (40, 0), (40, 10), (20, 10), (10, 5), (0, 5)]:
        click(c, x, y)
    click(c, 0, 0)  # click the first point to close
    assert len(win.project.regions) == 1
    assert win.project.regions[0].points == [[0, 0], [40, 0], [40, 10], [20, 10], [10, 5], [0, 5]]
    win.undo()
    assert len(win.project.regions) == 0
    win.redo()
    assert len(win.project.regions) == 1


def test_entry_exit_by_mouse_then_solve_and_export(win, app, tmp_path, monkeypatch):
    from geolab.examples import homogeneous_slope
    from geolab.ui import main_window
    shown = []
    monkeypatch.setattr(main_window.EntryExitDialog, "exec", lambda self: shown.append(self) or 1)
    win.set_project(homogeneous_slope())
    c = win.canvas
    win.set_draw_mode("entry_exit")
    for x in (36, 52, 14, 24):
        click(c, x, win.project.analyses[0].search.min_depth)  # y does not matter; x is used
    s = win.project.analyses[0].search
    assert abs(s.entry_x1 - 36) < 0.6 and abs(s.exit_x2 - 24) < 0.6
    assert len(shown) == 1 and "Entry" in shown[0].side["right"]["title"].text()
    solve_all(win.project)
    win.set_view("results")
    assert win.view_mode == "results"
    img = win.render_image(800, 500)
    assert not img.isNull()
    from geolab.ui.pdf import export_pdf
    pdf = tmp_path / "out.pdf"
    export_pdf(pdf, win.project, win.project.analyses[0])
    assert pdf.read_bytes()[:4] == b"%PDF" and pdf.stat().st_size > 10000


def test_assign_material_and_delete_region(win, app):
    from geolab.examples import layered_slope_with_water
    win.set_project(layered_slope_with_water())
    c = win.canvas
    target = win.project.materials[1].id
    win.current_material_id = target
    win.set_draw_mode("assign")
    click(c, 70, 2)   # bedrock region
    assert win.project.regions[0].material_id == target
    win.set_draw_mode("select")
    click(c, 70, 2)
    assert c.selected_region == win.project.regions[0].id
    QTest.keyClick(c, Qt.Key_Delete)
    assert len(win.project.regions) == 2


def test_materials_dialog_validates(app):
    from geolab.examples import homogeneous_slope
    from geolab.ui.dialogs import MaterialsDialog
    p = homogeneous_slope()
    d = MaterialsDialog(p)
    d.add()
    mats = d.collect()
    assert len(mats) == 2
    d.fields["unit_weight"].setText("-5")      # the new material is selected
    with pytest.raises(ValueError, match="unit weight"):
        d.collect()
    d.fields["unit_weight"].setText("abc")
    with pytest.raises(ValueError, match="not a number"):
        d.collect()
    d.fields["unit_weight"].setText("18")
    d.fields["model"].setCurrentIndex(d.fields["model"].findData("hoek_brown"))
    d.fields["E"].setText("50000")
    mats = d.collect()
    assert mats[1].model == "hoek_brown" and mats[1].E == 50000 and mats[1].unit_weight == 18


@pytest.mark.parametrize("name", ["Strip footing (stress-deformation)", "Frost penetration (thermal)",
                                  "Reservoir drawdown (transient)", "Contaminant plume (transport)",
                                  "Earthquake + Newmark displacement"])
def test_results_view_for_every_analysis_type(win, app, name):
    from geolab.examples import EXAMPLES
    from geolab.ui.render import project_bounds
    win.set_project(EXAMPLES[name]())
    solve_all(win.project)
    for a in win.project.analyses:
        win.current_aid = a.id
        win.refresh_all()
        win.set_view("results")
        assert win.view_mode == "results"
        for i in range(win.field_combo.count()):
            win.set_opt("contour", win.field_combo.itemData(i))
            assert not win.render_image(400, 300).isNull()
        if win.time_combo.count() > 1:
            win.set_opt("time_index", win.time_combo.itemData(1))
            assert not win.render_image(400, 300).isNull()
            win.set_opt("time_index", None)
        if a.kind != "slope":
            x0, y0, x1, y1 = project_bounds(win.project)
            win.show_result_info(0.5 * (x0 + x1), 0.5 * (y0 + y1))
            assert "Result at" in win.props.toHtml()


def test_analysis_dialog_for_every_kind(app, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from geolab.model import ANALYSIS_KINDS, new_project
    from geolab.ui.dialogs import AnalysisDialog
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warnings.append(a[2]))
    for kind in ANALYSIS_KINDS:
        p = new_project(kind=kind)
        a = p.analyses[0]
        d = AnalysisDialog(p, a)
        if kind == "dynamic":
            d.forms[0].w["motion"].setPlainText("0, 0\n1, 0.1\n2, 0")
        d.try_accept()
        if kind == "transport":      # no seepage parent: refused with a message
            assert d.result() != 1 and "seepage" in warnings[-1]
        else:
            assert d.result() == 1, (kind, warnings)
        if kind == "dynamic":
            assert a.motion == [[0, 0], [1, 0.1], [2, 0]]


def test_save_open_roundtrip_through_window(win, tmp_path):
    from geolab.examples import earth_dam
    win.set_project(earth_dam())
    win.path = tmp_path / "dam.slab"
    assert win.save()
    win.set_project(earth_dam())
    win.open_file(str(tmp_path / "dam.slab"))
    assert win.project.title.startswith("Earth dam")
    assert win.path.name == "dam.slab"
