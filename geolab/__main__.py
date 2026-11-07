"""Entry point.

    geolab                       start the desktop app
    geolab project.slab          open a project in the app
    geolab solve project.slab    solve from the command line (batch), print the report
"""
from __future__ import annotations

import argparse
import os
import sys


def cli_solve(argv) -> int:
    ap = argparse.ArgumentParser(prog="geolab solve", description="Solve a GeoLab project without the GUI.")
    ap.add_argument("file")
    ap.add_argument("--analysis", help="name of one analysis to solve (default: all)")
    ap.add_argument("--save", action="store_true", help="write results back into the project file")
    ap.add_argument("--pdf", help="also export a PDF report of the solved analysis")
    ap.add_argument("--csv", help="also export the results table as CSV")
    args = ap.parse_args(argv)
    from .fileio import export_results_csv, load_project, save_project
    from .report import build_report
    from .solver import solve, solve_all
    try:
        p = load_project(args.file)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if args.analysis:
        a = next((x for x in p.analyses if x.name == args.analysis), None)
        if a is None:
            print(f"error: no analysis named '{args.analysis}'", file=sys.stderr)
            return 2
        try:
            solve(p, a)
        except Exception as e:
            print(f"error: {a.name}: {e}", file=sys.stderr)
            return 1
        targets = [a]
    else:
        failed = [(n, e) for n, e in solve_all(p) if e]
        for n, e in failed:
            print(f"error: {n}: {e}", file=sys.stderr)
        targets = p.analyses
        if failed:
            return 1
    for a in targets:
        print(build_report(p, a))
        print()
    if args.save:
        save_project(p, args.file)
    if args.csv:
        export_results_csv(p, targets[-1], args.csv)
    if args.pdf:
        import os
        from PySide6.QtWidgets import QApplication
        qt_args = ["geolab"]
        if sys.platform.startswith("linux") and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
            qt_args += ["-platform", "offscreen"]   # headless Linux; Windows/macOS use the native platform (fonts)
        app = QApplication.instance() or QApplication(qt_args)
        from .ui.pdf import export_pdf
        export_pdf(args.pdf, p, targets[-1])
    return 0


def make_icon():
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPolygonF
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    g = QPainter(pm)
    g.setRenderHint(QPainter.Antialiasing)
    g.setBrush(QColor("#1d4e89"))
    g.setPen(Qt.NoPen)
    g.drawRoundedRect(2, 2, 60, 60, 12, 12)
    g.setBrush(QColor("#d9c49c"))
    g.drawPolygon(QPolygonF([QPointF(8, 54), QPointF(8, 40), QPointF(24, 40), QPointF(40, 20), QPointF(56, 20), QPointF(56, 54)]))
    g.setPen(QPen(QColor("#e03030"), 3))
    g.setBrush(Qt.NoBrush)
    g.drawArc(14, -6, 52, 56, 200 * 16, 110 * 16)
    g.end()
    return QIcon(pm)


def run_gui(argv) -> int:
    from PySide6.QtWidgets import QApplication
    from . import APP_NAME
    from .ui.main_window import _app_settings as _settings
    from .ui.prefs2 import scale_env
    scale_env(_settings())
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("GeoLab")
    app.setStyle("Fusion")
    app.setWindowIcon(make_icon())
    from . import i18n
    from .ui.main_window import MainWindow, _app_settings
    lang = os.environ.get("GEOLAB_LANG") or str(_app_settings().value("ui/language", "en") or "en")
    i18n.set_language(lang)
    if i18n.language() != "en":
        i18n.install(app)
    w = MainWindow()
    i18n.translate_widget(w)
    w.show()
    if argv and argv[0] == "--screenshot":
        # smoke test for packaged builds: open an example, solve, save a screenshot, exit
        from PySide6.QtCore import QTimer
        from .examples import EXAMPLES
        from .solver import solve_all
        w.open_example(list(EXAMPLES)[1])
        solve_all(w.project)
        w.set_view("results")
        w.refresh_all()

        def shoot():
            ok = w.grab().save(argv[1])
            w.dirty = False
            w.close()
            app.exit(0 if ok else 1)
        QTimer.singleShot(1500, shoot)
        return app.exec()
    if argv:
        w.open_file(argv[0])
    else:
        w.show_start()
    from PySide6.QtCore import QTimer
    from .ui import extras
    prev = extras.begin_session()
    app.aboutToQuit.connect(extras.end_session)
    if prev is not None:
        def offer():
            from PySide6.QtWidgets import QMessageBox
            r = QMessageBox.question(w, APP_NAME, "GeoLab did not close normally last time. Open the autosaved "
                                     "copies to recover your work?")
            if r == QMessageBox.Yes:
                w.recover_autosave()
        QTimer.singleShot(800, offer)
    QTimer.singleShot(5000, lambda: w.check_updates(quiet=True))
    return app.exec()


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "solve":
        return cli_solve(argv[1:])
    if argv and argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if argv and argv[0] in ("-V", "--version"):
        from . import __version__
        print(__version__)
        return 0
    return run_gui(argv)


if __name__ == "__main__":
    sys.exit(main())
