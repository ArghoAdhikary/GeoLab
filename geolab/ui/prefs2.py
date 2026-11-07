"""Preferences tabs added in GeoLab 2.13: Reports & Units (company branding, report language, decimals,
default units, my templates) and Advanced (offline mode, interface size, contour colours, solver)."""
from __future__ import annotations

import os

from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QSpinBox, QVBoxLayout, QWidget)

BRAND_KEYS = [("company", "Company"), ("engineer", "Engineer"), ("licence", "Licence / registration no."),
              ("checked", "Checked by"), ("address", "Address"), ("header", "Header line (every report)"),
              ("footer", "Footer line (every report)")]
SCALES = [100, 110, 125, 150, 175, 200]


def _bool(v, default=False):
    if v is None or v == "":
        return default
    return str(v).lower() in ("true", "1", "yes")


def reports_tab(dlg) -> QWidget:
    qs = dlg.qs
    w = QWidget()
    v = QVBoxLayout(w)
    g = QGroupBox("Company branding on the design report, PDF and Word")
    f = QFormLayout(g)
    dlg.brand = {}
    for key, label in BRAND_KEYS:
        e = QLineEdit(qs.value(f"brand/{key}", "") or "")
        dlg.brand[key] = e
        f.addRow(label, e)
    row = QHBoxLayout()
    dlg.brand_logo = QLineEdit(qs.value("brand/logo", "") or "")
    dlg.brand_logo.setPlaceholderText("PNG or JPG")
    b = QPushButton("Browse...")
    b.clicked.connect(lambda: _browse_logo(dlg))
    row.addWidget(dlg.brand_logo, 1)
    row.addWidget(b)
    f.addRow("Logo", row)
    v.addWidget(g)
    g = QGroupBox("Reports and numbers")
    f = QFormLayout(g)
    dlg.report_lang = QComboBox()
    dlg.report_lang.addItem("English", "en")
    dlg.report_lang.addItem("বাংলা (Bangla)", "bn")
    dlg.report_lang.setCurrentIndex(max(0, dlg.report_lang.findData(qs.value("report/language", "en") or "en")))
    f.addRow("Design report language", dlg.report_lang)
    dlg.decimals = QSpinBox()
    dlg.decimals.setRange(1, 6)
    dlg.decimals.setValue(int(qs.value("report/decimals", 3) or 3))
    f.addRow("Decimal places in reports", dlg.decimals)
    dlg.new_units = QComboBox()
    dlg.new_units.addItem("Metric (m, kN, kPa)", "metric")
    dlg.new_units.addItem("Imperial (ft, lbf, psf)", "imperial")
    dlg.new_units.setCurrentIndex(max(0, dlg.new_units.findData(qs.value("new/units", "metric") or "metric")))
    f.addRow("Units of new projects", dlg.new_units)
    n = QLabel("An open project changes units in Define > Project Settings (every value is converted).")
    n.setWordWrap(True)
    n.setEnabled(False)
    f.addRow(n)
    v.addWidget(g)
    g = QGroupBox("My templates")
    f = QFormLayout(g)
    from ..usertemplates import list_templates, templates_dir
    t = list_templates()
    lab = QLabel(f"{len(t)} template(s) in {templates_dir()}. Make one with File > Save as My Template; "
                 "start from it with File > New from My Template.")
    lab.setWordWrap(True)
    f.addRow(lab)
    v.addWidget(g)
    v.addStretch(1)
    return w


def _browse_logo(dlg):
    p, _ = QFileDialog.getOpenFileName(dlg, "Company Logo", dlg.brand_logo.text(), "Pictures (*.png *.jpg *.jpeg)")
    if p:
        dlg.brand_logo.setText(p)


def advanced_tab(dlg) -> QWidget:
    from ..usertemplates import QUALITY
    from .render import PALETTES
    qs = dlg.qs
    w = QWidget()
    v = QVBoxLayout(w)
    g = QGroupBox("Internet")
    f = QFormLayout(g)
    dlg.offline = QCheckBox("Offline mode: never use the internet")
    dlg.offline.setChecked(_bool(qs.value("net/offline"), False))
    f.addRow(dlg.offline)
    n = QLabel("Turns off the map, ground levels, rain and forecasts, the landslide watch, the update check and "
               "the online AI assistants. A local AI model (Ollama) keeps working.")
    n.setWordWrap(True)
    n.setEnabled(False)
    f.addRow(n)
    v.addWidget(g)
    g = QGroupBox("Accessibility")
    f = QFormLayout(g)
    dlg.ui_scale = QComboBox()
    for s in SCALES:
        dlg.ui_scale.addItem(f"{s} %", s)
    dlg.ui_scale.setCurrentIndex(max(0, dlg.ui_scale.findData(int(qs.value("ui/scale", 100) or 100))))
    f.addRow("Interface size (after a restart)", dlg.ui_scale)
    dlg.palette = QComboBox()
    for k, (label, _) in PALETTES.items():
        dlg.palette.addItem(label, k)
    dlg.palette.setCurrentIndex(max(0, dlg.palette.findData(qs.value("ui/palette", "classic") or "classic")))
    f.addRow("Contour colours", dlg.palette)
    n = QLabel("For high contrast pick View > Colour Scheme > High contrast.")
    n.setEnabled(False)
    f.addRow(n)
    v.addWidget(g)
    g = QGroupBox("Solver")
    f = QFormLayout(g)
    dlg.quality = QComboBox()
    for k, d in QUALITY.items():
        dlg.quality.addItem(d["label"], k)
    dlg.quality.setCurrentIndex(max(0, dlg.quality.findData(qs.value("solver/quality", "normal") or "normal")))
    f.addRow("Accuracy of new analyses", dlg.quality)
    dlg.threads = QSpinBox()
    dlg.threads.setRange(0, os.cpu_count() or 64)
    dlg.threads.setSpecialValueText(f"all ({os.cpu_count() or '?'})")
    dlg.threads.setValue(int(qs.value("solver/threads", 0) or 0))
    f.addRow("CPU cores for large models", dlg.threads)
    n = QLabel("Fewer cores leave the computer free for other work while a big model solves.")
    n.setEnabled(False)
    f.addRow(n)
    v.addWidget(g)
    v.addStretch(1)
    return w


def save(dlg):
    qs = dlg.qs
    for key, e in dlg.brand.items():
        qs.setValue(f"brand/{key}", e.text().strip())
    qs.setValue("brand/logo", dlg.brand_logo.text().strip())
    qs.setValue("report/language", dlg.report_lang.currentData())
    qs.setValue("report/decimals", dlg.decimals.value())
    qs.setValue("new/units", dlg.new_units.currentData())
    qs.setValue("net/offline", "true" if dlg.offline.isChecked() else "false")
    qs.setValue("ui/scale", dlg.ui_scale.currentData())
    qs.setValue("ui/palette", dlg.palette.currentData())
    qs.setValue("solver/quality", dlg.quality.currentData())
    qs.setValue("solver/threads", dlg.threads.value())


def apply_runtime(qs):
    """Put the saved settings into effect (at start and after Preferences > OK / Apply)."""
    from .. import designreport, linsolve, net
    from . import render
    designreport.BRAND = {k: (qs.value(f"brand/{k}", "") or "") for k, _ in BRAND_KEYS}
    designreport.BRAND["logo"] = qs.value("brand/logo", "") or ""
    designreport.LANG = qs.value("report/language", "en") or "en"
    try:
        designreport.DECIMALS = int(qs.value("report/decimals", 3) or 3)
    except (TypeError, ValueError):
        designreport.DECIMALS = 3
    net.set_offline(_bool(qs.value("net/offline"), False))
    render.set_palette(qs.value("ui/palette", "classic") or "classic")
    try:
        linsolve.MAX_THREADS = int(qs.value("solver/threads", 0) or 0)
    except (TypeError, ValueError):
        linsolve.MAX_THREADS = 0


def scale_env(qs):
    """Interface size: set before the application starts."""
    try:
        s = int(qs.value("ui/scale", 100) or 100)
    except (TypeError, ValueError):
        s = 100
    if s != 100 and "QT_SCALE_FACTOR" not in os.environ:
        os.environ["QT_SCALE_FACTOR"] = f"{s / 100:g}"
    return s
