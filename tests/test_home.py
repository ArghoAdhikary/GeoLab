"""Home page, Define Analyses window and the K0 in situ procedure."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from stratalab.model import new_project


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(app, tmp_path, monkeypatch):
    from PySide6.QtCore import QSettings
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(tmp_path))
    from stratalab.ui import main_window
    ini = str(tmp_path / "settings.ini")
    monkeypatch.setattr(main_window, "QSettings", lambda *a, **k: QSettings(ini, QSettings.IniFormat))
    w = main_window.MainWindow()
    w.show()
    yield w
    w.dirty = False
    w.close()


def test_home_page_new_analysis_opens_define_window(win, app, monkeypatch):
    from stratalab.ui import main_window
    seen = []

    class FakeDefine:
        def __init__(self, project, current, parent):
            seen.append([a.kind for a in project.analyses])

        def exec(self):
            return 0
    monkeypatch.setattr(main_window, "DefineProjectDialog", FakeDefine)
    win.show_start()
    assert win.on_home() and not win.solve_dock.isVisible()
    win.home.kind_buttons["stress"].click()
    assert not win.on_home() and win.solve_dock.isVisible()
    assert seen == [["stress"]] and win.project.analyses[0].kind == "stress"


def test_home_page_lists_recent_and_examples(win, tmp_path):
    f = tmp_path / "dam.gsz"
    f.write_text("x")
    win.add_recent(str(f))
    win.show_start()
    assert win.home.recent.item(0).text() == "dam.gsz"
    assert win.home.examples.count() > 3
    win.home.examples.itemClicked.emit(win.home.examples.item(0))
    assert not win.on_home()


def test_define_window_add_child_types_and_delete(app, monkeypatch):
    from stratalab.ui.dialogs import DefineProjectDialog
    p = new_project(kind="stress")
    d = DefineProjectDialog(p, p.analyses[0].id)
    ed = d.editors[p.analyses[0].id]
    # in situ: method choice enabled, time tab disabled
    assert ed.type_cb.currentData() == "insitu"
    assert ed._field("insitu_method")[1].isEnabled() and not ed._field("duration")[1].isEnabled()
    ed._field("insitu_method")[1].setCurrentIndex(1)
    child = d.add("stress")
    assert child.parent_id == p.analyses[0].id and child.stress_type == "load"
    ced = d.editors.get(child.id) or d._editor(child.id)
    ced.type_cb.setCurrentIndex(ced.type_cb.findData("consolidation"))
    assert ced._field("duration")[1].isEnabled()
    seep = d.add("seepage")
    assert seep.parent_id == child.id
    d.try_accept()
    assert d.result() == 1
    by = {a.id: a for a in d.p.analyses}
    assert by[p.analyses[0].id].insitu_method == "k0"
    assert by[child.id].stress_type == "consolidation"
    assert p.analyses[0].insitu_method == "gravity"          # original untouched until applied
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    d2 = DefineProjectDialog(d.p, child.id)
    d2.delete()                                              # removes the child and its seepage child
    assert [a.id for a in d2.p.analyses] == [p.analyses[0].id]


def test_define_window_applies_to_main_window(win, monkeypatch):
    from stratalab.ui import main_window
    from stratalab.ui.dialogs import DefineProjectDialog

    class AutoDefine(DefineProjectDialog):
        def exec(self):
            self.add("seepage")
            self.try_accept()
            return self.result()
    monkeypatch.setattr(main_window, "DefineProjectDialog", AutoDefine)
    win.set_project(new_project())
    win.edit_analysis()
    kinds = [a.kind for a in win.project.analyses]
    assert kinds == ["slope", "seepage"] and win.project.analyses[1].parent_id == win.project.analyses[0].id
    win.undo()
    assert [a.kind for a in win.project.analyses] == ["slope"]


def test_k0_procedure_matches_hand_calculation():
    from stratalab.sigma import k0_stress, overburden
    p = new_project(kind="stress")
    p.add_region([[0, 0], [10, 0], [10, 4], [0, 4]], p.materials[0].id)
    m2 = p.add_material("Top", unit_weight=18.0)
    p.add_region([[0, 4], [10, 4], [10, 6], [0, 6]], m2.id)
    x = np.array([5.0, 5.0, 5.0])
    y = np.array([5.0, 4.0, 1.0])
    sv = overburden(p, x, y)
    assert np.allclose(sv, [18.0, 36.0, 36.0 + 20.0 * 3])
    sig = k0_stress(p, x, y, np.full(3, 0.5), np.array([0.0, 0.0, 10.0 * 3]))
    assert np.allclose(-sig[:, 1], [18, 36, 66]) and np.allclose(sig[:, 0], 0.5 * sig[:, 1])


def test_k0_in_situ_analysis_solves():
    from stratalab.examples import EXAMPLES
    from stratalab.solver import solve
    names = [n for n in EXAMPLES if "onsolid" in n or "tress" in n]
    p = EXAMPLES[names[0]]()
    a = next(a for a in p.analyses if a.kind == "stress" and a.stress_type == "insitu")
    a.insitu_method = "k0"
    r = solve(p, a)
    assert r["converged"] and max(r["sy"]) > 0 and np.allclose(r["dx"], 0)
