"""PDF export and printing. Page 1 is the drawing with a title block; later pages hold the report."""
from __future__ import annotations

import datetime

from PySide6.QtCore import QMarginsF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPageLayout, QPageSize, QPainter, QPdfWriter, QPen

from .. import APP_NAME, __version__
from ..report import build_report
from .render import Renderer, View, project_bounds


def paint_pages(device, project, analysis, mode, opts, new_page):
    g = QPainter(device)
    try:
        dpi = device.resolution() if hasattr(device, "resolution") else 150
        page = QRectF(0, 0, device.width(), device.height())
        pt = dpi / 72.0
        # --- page 1: drawing --------------------------------------------
        head_h = 60 * pt
        draw = QRectF(page.left(), page.top() + head_h, page.width(), page.height() - head_h - 24 * pt)
        g.setPen(QPen(QColor("#1d4e89"), 2 * pt))
        g.drawLine(page.left(), page.top() + head_h - 6 * pt, page.right(), page.top() + head_h - 6 * pt)
        f = QFont("Segoe UI")
        f.setPixelSize(int(16 * pt)); f.setBold(True)
        g.setFont(f)
        g.setPen(QColor("#111"))
        g.drawText(QRectF(page.left(), page.top(), page.width() * 0.7, 24 * pt), Qt.AlignLeft | Qt.AlignVCenter, project.title)
        f.setPixelSize(int(9 * pt)); f.setBold(False)
        g.setFont(f)
        sub = analysis.name if analysis else ""
        if analysis and analysis.results:
            r = analysis.results
            if r.get("type") == "slope" and r.get("critical"):
                sub += f"   |   Factor of safety {r['critical']['fos']:.3f}"
            elif r.get("type") == "seepage":
                sub += f"   |   Inflow {r['inflow']:.4e} {project.unit('flux')}"
        g.drawText(QRectF(page.left(), page.top() + 24 * pt, page.width() * 0.7, 18 * pt), Qt.AlignLeft | Qt.AlignVCenter, sub)
        info = f"{project.author}\n{datetime.date.today():%Y-%m-%d}   Units: {project.units}"
        g.drawText(QRectF(page.right() - page.width() * 0.3, page.top(), page.width() * 0.3, 44 * pt),
                   Qt.AlignRight | Qt.AlignVCenter, info)
        v = View()
        v.fit(project_bounds(project), draw, margin=0.06)
        g.save()
        g.setClipRect(draw)
        o = dict(opts or {})
        o.update({"screen": False, "grid": False})
        Renderer(project, analysis, v, g, mode=mode, opts=o).draw()
        g.restore()
        g.setFont(f)
        g.setPen(QColor("#666"))
        g.drawText(QRectF(page.left(), page.bottom() - 18 * pt, page.width(), 18 * pt), Qt.AlignLeft | Qt.AlignVCenter,
                   f"{APP_NAME} {__version__}")
        g.drawText(QRectF(page.left(), page.bottom() - 18 * pt, page.width(), 18 * pt), Qt.AlignRight | Qt.AlignVCenter, "Page 1")
        # --- report pages -------------------------------------------------
        if analysis is None:
            return
        lines = build_report(project, analysis).splitlines()
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.Monospace)
        mono.setPixelSize(int(7.5 * pt))
        line_h = 10 * pt
        per_page = int((page.height() - 40 * pt) / line_h)
        pages = [lines[i:i + per_page] for i in range(0, len(lines), per_page)]
        for k, chunk in enumerate(pages, start=2):
            new_page()
            g.setFont(mono)
            g.setPen(QColor("#111"))
            for i, line in enumerate(chunk):
                g.drawText(QRectF(page.left(), page.top() + i * line_h, page.width(), line_h),
                           Qt.AlignLeft | Qt.AlignVCenter, line)
            g.setFont(f)
            g.setPen(QColor("#666"))
            g.drawText(QRectF(page.left(), page.bottom() - 18 * pt, page.width(), 18 * pt),
                       Qt.AlignRight | Qt.AlignVCenter, f"Page {k}")
    finally:
        g.end()


def export_pdf(path, project, analysis, mode="results", opts=None):
    w = QPdfWriter(str(path))
    w.setResolution(150)
    w.setPageLayout(QPageLayout(QPageSize(QPageSize.A4), QPageLayout.Landscape, QMarginsF(12, 12, 12, 12),
                                QPageLayout.Millimeter))
    w.setTitle(project.title)
    w.setCreator(f"{APP_NAME} {__version__}")
    paint_pages(w, project, analysis, mode, opts, w.newPage)
