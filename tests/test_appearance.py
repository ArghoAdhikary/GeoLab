"""Interface styles, colour schemes, per-element colours and fonts, autosave, cloud backup,
Save As .gsz and Export as PDF (offscreen)."""
import datetime as dt
import os
import zipfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(app, tmp_path, monkeypatch):
    from PySide6.QtCore import QSettings

    from geolab import backup
    from geolab.ui import appearance, main_window
    ini = str(tmp_path / "settings.ini")
    monkeypatch.setattr(main_window, "QSettings", lambda *a, **k: QSettings(ini, QSettings.IniFormat))
    monkeypatch.setattr(main_window, "_app_settings", lambda: QSettings(ini, QSettings.IniFormat))
    monkeypatch.setattr(backup, "autosave_dir", lambda: tmp_path / "Autosave")
    monkeypatch.setattr(appearance, "fonts_dir", lambda: tmp_path / "fonts")
    w = main_window.MainWindow()
    w.resize(1200, 800)
    w.show()
    app.processEvents()
    yield w
    w.dirty = False
    appearance.set_config(appearance.Config())
    from geolab.ui.theme import manager
    manager().refresh()
    w.close()


def test_config_round_trip_and_theme_file(app, tmp_path):
    from geolab.ui import appearance as ap
    cfg = ap.Config(style="modern", scheme="forest", accent="#ff0000",
                    colors={"menubar": {"bg": "#123456", "fg": "#ffffff"}, "nope": {"bg": "#000"},
                            "chat_head": {"bg": "not a colour"}},
                    fonts={"menu": "Arial,12,-1,5,700,0,0,0,0,0", "input": "Arial,9"})
    c2 = ap.Config.from_dict(cfg.to_dict())
    assert c2.style == "modern" and c2.scheme == "forest" and c2.accent == "#ff0000"
    assert c2.colors == {"menubar": {"bg": "#123456", "fg": "#ffffff"}}     # unknown and invalid dropped
    assert "menu" in c2.fonts and "input" not in c2.fonts                    # input has no font slot
    ap.export_theme(c2, tmp_path / "t.geolab-theme")
    assert ap.import_theme(tmp_path / "t.geolab-theme").to_dict() == c2.to_dict()
    assert ap.Config.from_dict({"style": "weird", "scheme": "x"}).style == "classic"


def test_palette_stylesheet_and_lookups(app):
    from geolab.ui import appearance as ap
    from geolab.ui.theme import light_palette
    base = ap.Config()
    assert ap.stylesheet(False, base) == ""                       # classic look is unchanged
    assert ap.palette(False, base).color(QPalette.Window) == light_palette().color(QPalette.Window)
    cfg = ap.Config(style="flat", scheme="ocean",
                    colors={"menubar": {"bg": "#123456"}, "dock": {"fg": "#ff00ff"}, "window": {"bg": "#abcdef"},
                            "canvas": {"bg": "#101010", "fg": "#202020"}, "chat_head": {"bg": "#00aa00"}},
                    fonts={"statusbar": "Courier New,13,-1,5,400,0,0,0,0,0"})
    qss = ap.stylesheet(True, cfg)
    assert "QMenuBar { background: #123456; }" in qss and "QDockWidget { color: #ff00ff; }" in qss
    assert "Courier New" in qss and "border-bottom" in qss          # the flat style is in too
    assert ap.palette(True, cfg).color(QPalette.Window).name() == "#abcdef"
    assert ap.palette(True, cfg).color(QPalette.Base).name() == ap.SCHEMES["ocean"]["dark"]["base"]
    ap.set_config(cfg)
    try:
        assert ap.color("chat_head", "bg", "#999999") == "#00aa00"
        assert ap.color("chat_user", "bg", "#999999") == "#999999"
        assert ap.canvas_colors(False)["background"] == "#101010"
        assert ap.font("statusbar").family() == "Courier New"
        assert ap.accent() in (ap.SCHEMES["ocean"]["light"]["accent"], ap.SCHEMES["ocean"]["dark"]["accent"])
    finally:
        ap.set_config(ap.Config())
    for style in ap.STYLES:                                        # every style sheet parses
        app.setStyleSheet(ap.stylesheet(False, ap.Config(style=style, scheme="contrast")))
    app.setStyleSheet("")


def _a_font_file():
    cands = [Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / n for n in ("arial.ttf", "segoeui.ttf")]
    cands += [Path("/System/Library/Fonts/Supplemental/Arial.ttf"), Path("/Library/Fonts/Arial.ttf"),
              Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")]
    try:
        import matplotlib
        cands.append(Path(matplotlib.get_data_path()) / "fonts" / "ttf" / "DejaVuSans.ttf")
    except ImportError:
        pass
    return next((p for p in cands if p.is_file()), None)


def test_add_and_remove_a_font(app, tmp_path):
    from geolab.ui import appearance as ap
    src = _a_font_file()
    if src is None:
        pytest.skip("no font file on this computer")
    fams = ap.add_font(src, tmp_path / "fonts")
    assert fams and (tmp_path / "fonts" / src.name).exists()
    assert src.name in ap.load_user_fonts(tmp_path / "fonts")
    bad = tmp_path / "x.txt"
    bad.write_text("x")
    with pytest.raises(ValueError):
        ap.add_font(bad, tmp_path / "fonts")
    ap.remove_font(src.name, tmp_path / "fonts")
    assert src.name not in ap.load_user_fonts(tmp_path / "fonts")


def test_backup_copies_versions_and_drives(tmp_path, monkeypatch):
    from geolab import backup
    src = tmp_path / "Bank A.slab"
    src.write_bytes(b"data")
    drive = tmp_path / "My Drive"
    drive.mkdir()
    t0 = dt.datetime(2026, 11, 8, 9, 0)
    for k in range(5):
        backup.backup_copy(src, drive, keep=3, now=t0 + dt.timedelta(minutes=k))
    vs = backup.versions(drive, "Bank A")
    assert len(vs) == 3 and vs[0].name == "Bank A 2026-11-08 0904.slab"
    assert backup.safe_name('a/b:c*?') == "a-b-c--"
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "Dropbox").mkdir()
    monkeypatch.setenv("OneDrive", str(drive))
    found = backup.detect_drives()
    assert str(tmp_path / "Dropbox") in found.values() and str(drive) in found.values()


def test_preferences_dialog_round_trip(win, app):
    from geolab.ui import appearance as ap
    from geolab.ui.prefs import PreferencesDialog
    d = PreferencesDialog(win.settings, win, "advanced")
    assert d.tabs.count() == 4 and d.tabs.currentIndex() == 1
    assert len(d.color_btns) >= 30 and "chat_box" in d.font_btns and "menubar" in d.font_btns
    d.style_box.setCurrentIndex(d.style_box.findData("modern"))
    d.scheme_box.setCurrentIndex(d.scheme_box.findData("sunset"))
    d.color_btns[("menubar", "bg")].set_value("#334455")
    d.color_btns[("chat_head", "bg")].set_value("#00ff00")
    d.font_btns["chat_box"].set_value("Arial,14,-1,5,400,0,0,0,0,0")
    d.autosave.setChecked(False)
    d.backup_on.setChecked(True)
    d.backup_dir.setText("X:/nowhere")
    win.apply_preferences(d)                         # what Apply and OK do
    cfg = ap.config()
    assert cfg.style == "modern" and cfg.scheme == "sunset"
    assert cfg.colors["menubar"]["bg"] == "#334455" and "chat_box" in cfg.fonts
    assert "#334455" in app.styleSheet()
    assert not win.autosave_timer.isActive()
    assert win.a_style["modern"].isChecked() and win.a_scheme["sunset"].isChecked()
    win.chat.panel.restyle()
    assert "Arial" in win.chat.panel.view.toHtml()
    # loading the saved settings again gives the same appearance
    assert ap.load(win.settings).to_dict() == cfg.to_dict()
    d2 = PreferencesDialog(win.settings, win)
    assert d2.color_btns[("menubar", "bg")].value == "#334455" and not d2.autosave.isChecked()
    d2.set_appearance(ap.Config())
    assert d2.appearance_config().to_dict() == ap.Config().to_dict()
    import shiboken6
    shiboken6.delete(d)
    shiboken6.delete(d2)


def test_view_menu_switches_style(win, app):
    win.set_ui_style(style="compact")
    assert "QToolBar { spacing: 0px" in app.styleSheet()
    win.set_ui_style(scheme="contrast")
    assert win.a_scheme["contrast"].isChecked()
    win.set_ui_style(style="classic", scheme="geolab")
    assert app.styleSheet() == ""


def test_autosave_backup_gsz_and_pdf(win, app, tmp_path):
    from geolab.examples import EXAMPLES
    win.set_project(EXAMPLES["Homogeneous slope (benchmark)"](), dirty=True)
    assert win.autosave_timer.isActive()                   # on by default
    out = win.autosave()                                   # no file yet: goes to the autosave folder
    assert out is not None and out.parent == tmp_path / "Autosave" and out.exists()
    assert win.dirty                                       # still needs a real save
    # with a file, autosave writes the file itself and keeps a .bak
    path = tmp_path / "slope.slab"
    win.path = path
    win._write_project(path)
    win.dirty = True
    assert win.autosave() == path and not win.dirty
    assert (tmp_path / "slope.slab.bak").exists()
    # cloud backup on every save
    drive = tmp_path / "Google Drive"
    drive.mkdir()
    win.settings.setValue("backup/enabled", "true")
    win.settings.setValue("backup/folder", str(drive))
    win.settings.setValue("backup/every_min", 0)
    win.dirty = True
    assert win.save()
    copies = list((drive / "GeoLab Backups" / "slope").glob("slope *.slab"))
    assert len(copies) == 1 and zipfile.is_zipfile(copies[0])
    assert "Backed up to" in win.backup_now()
    # Save As GeoStudio and Export as PDF
    gsz = tmp_path / "slope.gsz"
    assert win.export_gsz(str(gsz)) and zipfile.is_zipfile(gsz)
    assert win.path == path                                # the project stays tied to its .slab
    pdf = tmp_path / "all.pdf"
    from geolab.solver import solve
    solve(win.project, win.project.analyses[0])
    assert win.export_pdf_all(str(pdf))
    assert pdf.read_bytes()[:4] == b"%PDF" and pdf.stat().st_size > 5000
