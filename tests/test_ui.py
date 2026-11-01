"""GUI tests run on Qt's offscreen platform and drive the real widgets."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from stratalab.solver import solve_all


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(app, tmp_path, monkeypatch):
    from PySide6.QtCore import QSettings
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(tmp_path))
    from stratalab.ui.main_window import MainWindow
    w = MainWindow()
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


def test_entry_exit_by_mouse_then_solve_and_export(win, app, tmp_path):
    from stratalab.examples import homogeneous_slope
    win.set_project(homogeneous_slope())
    c = win.canvas
    win.set_draw_mode("entry_exit")
    for x in (36, 52, 14, 24):
        click(c, x, win.project.analyses[0].search.min_depth)  # y does not matter; x is used
    s = win.project.analyses[0].search
    assert abs(s.entry_x1 - 36) < 0.6 and abs(s.exit_x2 - 24) < 0.6
    solve_all(win.project)
    win.set_view("results")
    assert win.view_mode == "results"
    img = win.render_image(800, 500)
    assert not img.isNull()
    from stratalab.ui.pdf import export_pdf
    pdf = tmp_path / "out.pdf"
    export_pdf(pdf, win.project, win.project.analyses[0])
    assert pdf.read_bytes()[:4] == b"%PDF" and pdf.stat().st_size > 10000


def test_assign_material_and_delete_region(win, app):
    from stratalab.examples import layered_slope_with_water
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
    from stratalab.examples import homogeneous_slope
    from stratalab.ui.dialogs import MaterialsDialog
    p = homogeneous_slope()
    d = MaterialsDialog(p)
    d.add()
    mats = d.collect()
    assert len(mats) == 2
    d.table.item(1, 3).setText("-5")   # unit weight
    with pytest.raises(ValueError, match="unit weight"):
        d.collect()


def test_save_open_roundtrip_through_window(win, tmp_path):
    from stratalab.examples import earth_dam
    win.set_project(earth_dam())
    win.path = tmp_path / "dam.slab"
    assert win.save()
    win.set_project(earth_dam())
    win.open_file(str(tmp_path / "dam.slab"))
    assert win.project.title.startswith("Earth dam")
    assert win.path.name == "dam.slab"
