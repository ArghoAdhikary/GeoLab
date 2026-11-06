"""Build the documentation that ships with GeoLab.

    python build_docs.py            (before python build.py)

1. solves every example and saves it as a .slab file         -> build/help/examples/, release/GeoLab-examples.zip
2. takes screenshots of the program with those results       -> geolab/help/img/
3. writes the manual and the tutorials as one PDF            -> build/help/GeoLab-User-Manual.pdf, release/
"""
from __future__ import annotations

import datetime
import os
import re
import shutil
import sys
import time
import zipfile
from pathlib import Path

# real windows give real fonts in the screenshots; elsewhere (and when asked) render off screen
os.environ.setdefault("QT_QPA_PLATFORM", "windows" if sys.platform == "win32" else "offscreen")
if sys.platform == "win32" and "QT_QPA_FONTDIR" not in os.environ:
    # the offscreen platform only finds fonts in its own folder: point it at the Windows fonts
    os.environ["QT_QPA_FONTDIR"] = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QMarginsF, QRectF, QSettings, QSizeF, Qt, QUrl  # noqa: E402
from PySide6.QtGui import QColor, QFont, QPageLayout, QPageSize, QPainter, QPdfWriter, QTextDocument  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from geolab import __version__  # noqa: E402
from geolab import help as docs  # noqa: E402
from geolab.examples import EXAMPLES, example_file_name  # noqa: E402
from geolab.fileio import save_project  # noqa: E402
from geolab.solver import solve_all  # noqa: E402

OUT = ROOT / "build" / "help"
REL = ROOT / "release"
IMG = docs.img_dir()


def solve_examples() -> dict:
    ex_dir = OUT / "examples"
    if ex_dir.exists():
        shutil.rmtree(ex_dir)
    ex_dir.mkdir(parents=True)
    solved = {}
    for name, make in EXAMPLES.items():
        t = time.perf_counter()
        p = make()
        errors = [e for e in solve_all(p) if e[1]]
        if errors:
            raise SystemExit(f"Example '{name}' did not solve: {errors}")
        save_project(p, ex_dir / example_file_name(name))
        solved[name] = p
        print(f"  solved {name} ({time.perf_counter() - t:.1f} s)")
    REL.mkdir(exist_ok=True)
    with zipfile.ZipFile(REL / "GeoLab-examples.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(ex_dir.glob("*.slab")):
            z.write(f, f"GeoLab examples/{f.name}")
    return solved


def screenshots(app, solved: dict):
    from geolab.ui import main_window
    ini = OUT / "docs-settings.ini"
    main_window.QSettings = lambda *a, **k: QSettings(str(ini), QSettings.IniFormat)
    IMG.mkdir(parents=True, exist_ok=True)
    w = main_window.MainWindow()
    w.resize(1500, 900)
    w.show()
    app.processEvents()

    def show(name, index, field=None, view="results", opts=None, keep=False):
        p = solved[name] if keep else _copy(solved[name])
        w.set_project(p, dirty=False)
        w.current_aid = p.analyses[index].id
        w.opts.update({"time_index": None, "deformed": False, "yield": False, "trials": False,
                       "slices": False, "vectors": False, "mesh": False})
        if field:
            w.opts["contour"] = field
        w.opts.update(opts or {})
        for k, a in w.opt_actions.items():
            a.blockSignals(True)
            a.setChecked(bool(w.opts.get(k)))
            a.blockSignals(False)
        w.set_view(view)
        w.refresh_all()
        app.processEvents()
        w.canvas.zoom_fit()
        app.processEvents()
        return w

    def canvas(out, **kw):
        show(**kw)
        w.canvas.grab().save(str(IMG / out))

    show("Homogeneous slope (benchmark)", 0)
    w.grab().save(str(IMG / "window.png"))
    w.stepbar.grab().save(str(IMG / "step_guide.png"))
    canvas("slope.png", name="Homogeneous slope (benchmark)", index=0)
    canvas("tut_first_slope.png", name="Homogeneous slope (benchmark)", index=0, view="define")
    canvas("seepage.png", name="Earth dam: seepage + stability", index=0, field="head", opts={"vectors": True})
    canvas("drawdown.png", name="Rapid drawdown (Duncan-Wright-Wong)", index=0)
    canvas("footing.png", name="Strip footing (stress-deformation)", index=1, field="displacement",
           opts={"deformed": True})
    canvas("consolidation.png", name="Consolidation under a fill", index=0, field="excess_pwp")
    canvas("excavation.png", name="Anchored excavation (staged)", index=3, field="displacement")
    canvas("dynamic.png", name="Earthquake + Newmark displacement", index=1, field="max_acceleration")
    canvas("thermal.png", name="Frost penetration (thermal)", index=0, field="temperature")
    canvas("transport.png", name="Contaminant plume (transport)", index=1, field="concentration")

    from geolab.ui.guide import QuickSlopeDialog
    d = QuickSlopeDialog(w, "metric")
    d.water_on.setChecked(True)
    d.water.setValue(3)
    d.height.setValue(8)
    d.show()
    app.processEvents()
    d.grab().save(str(IMG / "quick_slope.png"))
    d.close()
    w.dirty = False
    w.close()
    print(f"  {len(list(IMG.glob('*.png')))} pictures in {IMG}")


def _copy(p):
    from geolab.model import Project
    return Project.from_dict(p.to_dict(include_results=True))


# ---------------------------------------------------------------------------------------------- PDF
CSS = """
body { font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif; font-size: 10pt; color: #1b1b1b; }
h1 { font-size: 20pt; color: #1d4e89; margin-top: 0; }
h2 { font-size: 13.5pt; color: #1d4e89; margin-top: 14px; }
h3 { font-size: 11pt; color: #333; }
table { border-collapse: collapse; margin: 6px 0 10px 0; }
th { background: #e8eef6; border: 1px solid #b9c6d6; padding: 3px 6px; text-align: left; }
td { border: 1px solid #c9d2dd; padding: 3px 6px; vertical-align: top; }
code { font-family: Consolas, monospace; background: #f1f1f1; }
"""
PAGE_W_PX = 640        # width of the text column in document pixels


def _md_html(md: str) -> str:
    d = QTextDocument()
    d.setMarkdown(docs.clean_markdown(md, with_images=True))
    html = d.toHtml()
    body = re.search(r"<body[^>]*>(.*)</body>", html, re.S).group(1)

    def img(m):
        src = m.group(1)
        path = docs.HERE / src
        width = PAGE_W_PX
        try:
            from PySide6.QtGui import QImage
            im = QImage(str(path))
            if not im.isNull():
                width = min(PAGE_W_PX, int(im.width() * 0.62))
        except Exception:                          # noqa: BLE001
            pass
        return f'<img src="{src}" width="{width}" />'
    body = re.sub(r'<img src="([^"]+)"[^>]*/?>', img, body)
    return body


def build_pdf():
    chapters, tuts = docs.chapters(), docs.tutorials()
    parts = [f"""
<div align="center"><br><br><br><br><br><br>
<h1 style="font-size:40pt; color:#1d4e89">GeoLab</h1>
<h2 style="font-size:18pt; color:#333333">User Manual and Tutorials</h2>
<p style="font-size:11pt">Version {__version__} &nbsp;·&nbsp; {datetime.date.today():%B %Y}</p>
<br><br><br>
<p style="font-size:10pt">2D geotechnical analysis: slope stability, seepage, stress-deformation and consolidation,<br>
earthquake response, heat transfer with freezing, contaminant transport and air flow.</p>
<br><br><br><br><br><br><br><br><br>
<p style="font-size:9pt; color:#555">https://github.com/ArghoAdhikary/GeoLab &nbsp;·&nbsp; MIT License</p>
</div>"""]
    toc = ['<h1>Contents</h1><p><b>Part I — User manual</b></p><ul>']
    toc += [f"<li>{c['title']}</li>" for c in chapters]
    toc += ['</ul><p><b>Part II — Tutorials</b></p><ul>']
    toc += [f"<li>{t['title']}</li>" for t in tuts]
    toc += ["</ul><p>Every number quoted in the tutorials is checked against the program by the automated "
            "tests, so the tutorials and the program always agree.</p>"]
    parts.append("".join(toc))
    parts.append('<div align="center"><br><br><br><br><br><br><br><br><h1 style="font-size:30pt">Part I</h1>'
                 '<h2 style="font-size:18pt; color:#333333">User manual</h2></div>')
    parts += [_md_html(c["text"]) for c in chapters]
    parts.append('<div align="center"><br><br><br><br><br><br><br><br><h1 style="font-size:30pt">Part II</h1>'
                 '<h2 style="font-size:18pt; color:#333333">Tutorials</h2>'
                 '<p>The models are in File &gt; Open Example and in Help &gt; Example Files Folder.</p></div>')
    parts += [_md_html(t["text"]) for t in tuts]
    html = "<html><body>" + "".join(
        (f'<div style="page-break-before:always">{p}</div>' if i else p) for i, p in enumerate(parts)) + "</body></html>"

    doc = QTextDocument()
    doc.setDefaultStyleSheet(CSS)
    doc.setDefaultFont(QFont("Segoe UI", 10))
    doc.setBaseUrl(QUrl.fromLocalFile(str(docs.HERE) + "/"))
    doc.setHtml(html)
    OUT.mkdir(parents=True, exist_ok=True)
    pdf = OUT / docs.PDF_NAME
    w = QPdfWriter(str(pdf))
    w.setTitle(f"GeoLab {__version__} User Manual")
    w.setCreator("GeoLab build_docs.py")
    w.setPageLayout(QPageLayout(QPageSize(QPageSize.A4), QPageLayout.Portrait, QMarginsF(18, 16, 18, 16),
                                QPageLayout.Millimeter))
    w.setResolution(300)
    # lay the text out on pages PAGE_W_PX wide, then paint each page scaled to the paper, with a footer
    paint = w.pageLayout().paintRectPixels(w.resolution())
    footer = 0.045 * paint.height()
    scale = paint.width() / PAGE_W_PX
    page_h = (paint.height() - footer) / scale
    doc.setPageSize(QSizeF(PAGE_W_PX, page_h))
    n = doc.pageCount()
    g = QPainter(w)
    ffont = QFont("Segoe UI")
    ffont.setPointSizeF(8)
    for i in range(n):
        if i:
            w.newPage()
        g.save()
        g.scale(scale, scale)
        g.translate(0, -i * page_h)
        doc.drawContents(g, QRectF(0, i * page_h, PAGE_W_PX, page_h))
        g.restore()
        if i:
            g.setFont(ffont)
            g.setPen(QColor("#777777"))
            box = QRectF(0, paint.height() - footer * 0.7, paint.width(), footer * 0.7)
            g.drawText(box, Qt.AlignLeft | Qt.AlignBottom, f"GeoLab {__version__} User Manual")
            g.drawText(box, Qt.AlignRight | Qt.AlignBottom, f"Page {i + 1} of {n}")
    g.end()
    del w
    REL.mkdir(exist_ok=True)
    shutil.copy2(pdf, REL / docs.PDF_NAME)
    print(f"  {pdf} ({pdf.stat().st_size / 1e6:.1f} MB, {n} pages)")
    return pdf, n


def main():
    app = QApplication.instance() or QApplication(["build_docs"])
    print("Solving the examples...")
    solved = solve_examples()
    print("Screenshots...")
    screenshots(app, solved)
    print("PDF manual...")
    build_pdf()


if __name__ == "__main__":
    main()
