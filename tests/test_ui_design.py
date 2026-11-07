"""The 2.10 design-tool windows, driven through the real widgets (offscreen)."""
import os
import zipfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(app, tmp_path, monkeypatch):
    from PySide6.QtCore import QSettings
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


def _wait(app, d):
    while d.job is not None and d.job.isRunning():
        d.job.wait(50)
        app.processEvents()
    app.processEvents()


@pytest.fixture
def solved(win):
    from geolab.examples import EXAMPLES
    from geolab.solver import solve
    win.set_project(EXAMPLES["Homogeneous slope (benchmark)"]())
    solve(win.project, win.current_analysis())
    return win


def test_menus_have_the_new_tools(win):
    titles = [a.text().replace("&", "") for a in win.menuBar().actions()]
    assert "Design" in titles and "Tools" in titles
    for a in (win.a_code, win.a_optimizer, win.a_whatif, win.a_backcalc, win.a_liq, win.a_dreport,
              win.a_boreholes, win.a_rain, win.a_monitor, win.a_photo, win.a_console, win.a_riverbank):
        assert a.text()


def test_back_analysis_dialog(app, solved):
    d = solved.tool("backcalc", run=False)
    d.line.setChecked(False)
    d.run()
    _wait(app, d)
    assert "3.22" in d.out.toPlainText() and d.apply_btn.isEnabled()
    d.apply()
    assert solved.project.material(1).cohesion == pytest.approx(3.22, abs=0.03)


def test_what_if_and_code_dialogs(app, solved):
    d = solved.what_if(run=False)
    assert d.big.text() == "F = 0.987"
    s, lo, step, _ = d.sl["c_factor"]
    s.setValue(int(round((2.0 - lo) / step)))
    d.update_fos()
    assert float(d.big.text().split("=")[1]) > 1.1
    d.use()
    assert solved.project.material(1).cohesion == pytest.approx(6.0)
    c = solved.tool("code", run=False)
    assert c.code.currentData() == "AS"
    c.code.setCurrentIndex(c.code.findData("BNBC"))
    c.widgets["city"].setCurrentIndex(c.widgets["city"].findData("Sylhet"))
    assert "zone 4" in c.seis.text() and solved.project.design_code == "BNBC"
    c.put_kh()
    assert any(a.kh == pytest.approx(0.162) for a in solved.project.analyses)


def test_liquefaction_borehole_template_dialogs(app, win):
    d = win.tool("liquefaction", run=False)
    d.run()
    _wait(app, d)
    assert "LPI" in d.out.toPlainText()
    d.keep()
    assert "_liquefaction" in win.project.code_settings
    b = win.tool("boreholes", run=False)
    b.sample()
    assert b.build_btn.isEnabled()
    win.dirty = False
    b.build()
    assert len(win.project.regions) == 3 and win.project.boreholes
    win.dirty = False
    t = win.new_template("riverbank", run=False)
    t.make()
    assert t.project is not None and len(t.project.analyses) == 3


def test_design_report_word(app, solved, tmp_path, monkeypatch):
    from PySide6.QtGui import QDesktopServices
    from PySide6.QtWidgets import QFileDialog
    out = tmp_path / "report.docx"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(out), "")))
    monkeypatch.setattr(QDesktopServices, "openUrl", staticmethod(lambda *a: True))
    assert solved.design_report() == str(out)
    with zipfile.ZipFile(out) as z:
        assert "word/media/image1.png" in z.namelist()
    pdf = tmp_path / "report.pdf"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(pdf), "")))
    solved.design_report()
    assert pdf.read_bytes()[:4] == b"%PDF"


def test_console_and_bangla(app, win):
    from geolab import i18n
    d = win.toggle_console()
    con = d.widget()
    con.editor.setPlainText("print(len(project.materials))")
    con.run()
    assert "1" in con.output.toPlainText()
    try:
        i18n.set_language("bn")
        i18n.translate_widget(win)
        titles = [a.text() for a in win.menuBar().actions()]
        assert "ফাইল" in titles and "ডিজাইন" in titles
    finally:
        i18n.set_language("en")
