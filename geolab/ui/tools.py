"""Windows for the design tools: back-analysis, k calibration, design optimizer, what-if sliders, design
code check (AS / BNBC), liquefaction, borehole import, rainfall, monitoring, model from a photo, river
bank / flood embankment templates and the design report."""
from __future__ import annotations

import copy
import datetime
import os
import traceback
from pathlib import Path

from PySide6.QtCore import QRectF, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox,
                               QDoubleSpinBox, QFileDialog, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
                               QPlainTextEdit, QProgressBar, QPushButton, QSlider, QSpinBox, QTableWidget,
                               QTableWidgetItem, QVBoxLayout)

from .. import backcalc, codes, liquefaction, monitoring, optimize, rainfall
from ..whatif import SurfacePool, apply_changes

MONO = QFont("Consolas")
MONO.setStyleHint(QFont.Monospace)


class Job(QThread):
    done = Signal(object)
    failed = Signal(str)
    progress = Signal(int)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def run(self):
        try:
            self.done.emit(self.fn(self.progress.emit))
        except Exception as e:                       # noqa: BLE001  (shown to the user)
            traceback.print_exc()
            self.failed.emit(str(e) or e.__class__.__name__)


def num(val, lo, hi, dec=3, step=0.1, suffix=""):
    w = QDoubleSpinBox()
    w.setRange(lo, hi)
    w.setDecimals(dec)
    w.setSingleStep(step)
    w.setValue(val)
    if suffix:
        w.setSuffix(" " + suffix)
    return w


def render_png(project, analysis, surface=None, fos=None, w=900, h=480, dark=False) -> QImage:
    """Picture of the model (definition view) with an optional slip surface and factor of safety."""
    from ..geometry import GroundProfile
    from ..slope import find_extent
    from .render import Renderer, View, project_bounds
    img = QImage(w, h, QImage.Format_ARGB32)
    img.fill(Qt.white)
    g = QPainter(img)
    v = View()
    v.fit(project_bounds(project), QRectF(0, 0, w, h))
    r = Renderer(project, analysis, v, g, mode="define" if surface is not None or not (analysis and analysis.results)
                 else "results", opts={"grid": False, "screen": True, "dark": dark, "trials": False})
    r.draw()
    if surface is not None:
        gp = GroundProfile(project.regions, samples=400)
        ext = find_extent(gp, surface, samples=300)
        if ext:
            pts = r._surface_pts(surface, gp, ext[:2])
            g.setPen(r.pen("#c01010", 2.6))
            g.drawPolyline(r.poly(pts))
            if fos is not None:
                mx = 0.5 * (ext[0] + ext[1])
                a = v.dev(mx, float(gp.ground(mx)))
                g.setFont(r.font(17, True))
                g.setPen(QColor("#111111"))
                g.drawText(QRectF(a.x() - 80, a.y() - 42, 160, 32), Qt.AlignCenter, f"{fos:.3f}")
    g.end()
    return img


def png_bytes(img: QImage) -> bytes:
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    return bytes(ba.data())


class ToolDialog(QDialog):
    """Common frame: inputs at the top, Run, a progress bar and the answer as text."""

    def __init__(self, main, title, intro, run_label="Run"):
        super().__init__(main)
        self.main = main
        self.setWindowTitle(title)
        self.resize(760, 640)
        self.v = QVBoxLayout(self)
        lab = QLabel(intro)
        lab.setWordWrap(True)
        self.v.addWidget(lab)
        self.form = QFormLayout()
        self.v.addLayout(self.form)
        row = QHBoxLayout()
        self.run_btn = QPushButton(run_label)
        self.run_btn.setDefault(True)
        self.run_btn.clicked.connect(self.run)
        self.bar = QProgressBar()
        self.bar.setRange(0, 0)
        self.bar.hide()
        row.addWidget(self.run_btn)
        row.addWidget(self.bar, 1)
        self.v.addLayout(row)
        self.out = QPlainTextEdit()
        self.out.setReadOnly(True)
        self.out.setFont(MONO)
        self.v.addWidget(self.out, 1)
        self.buttons = QHBoxLayout()
        self.buttons.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        self.v.addLayout(self.buttons)
        self.buttons.addWidget(close)
        self.job = None
        self.result = None

    def add_button(self, text, slot, enabled=False):
        b = QPushButton(text)
        b.clicked.connect(slot)
        b.setEnabled(enabled)
        self.buttons.insertWidget(self.buttons.count() - 1, b)
        return b

    def start(self, fn, on_done):
        if self.job is not None and self.job.isRunning():
            return
        self.run_btn.setEnabled(False)
        self.bar.show()
        self.out.setPlainText("Working...")
        self.job = Job(fn)
        self.job.done.connect(lambda r: self._done(r, on_done))
        self.job.failed.connect(self._failed)
        self.job.progress.connect(lambda p: (self.bar.setRange(0, 100), self.bar.setValue(p)))
        self.job.start()

    def _done(self, r, on_done):
        self.bar.hide()
        self.run_btn.setEnabled(True)
        self.result = r
        on_done(r)

    def _failed(self, msg):
        self.bar.hide()
        self.run_btn.setEnabled(True)
        self.out.setPlainText("Could not finish:\n" + msg)

    def run(self):
        pass

    def done(self, r):
        if self.job is not None and self.job.isRunning():
            self.job.wait(30000)
        super().done(r)


def slope_analyses(project, solved_only=False):
    return [a for a in project.analyses if a.kind == "slope" and a.method != "finite_element"
            and (not solved_only or (a.results and a.results.get("critical")))]


def analysis_combo(analyses, current=None):
    c = QComboBox()
    for a in analyses:
        c.addItem(a.name, a.id)
    if current is not None:
        i = c.findData(current.id)
        if i >= 0:
            c.setCurrentIndex(i)
    return c


def _need(main, kind_text, items):
    if not items:
        QMessageBox.information(main, "GeoLab", f"This tool needs {kind_text}. Open or build one first "
                                                "(File > Open Example has ready models).")
        return False
    return True


# ------------------------------------------------------------------------------------- back-analysis
class BackAnalysisDialog(ToolDialog):
    def __init__(self, main):
        super().__init__(main, "Back-Analysis (from a failure)",
                         "A slope that failed had a factor of safety of 1.0 when it failed. GeoLab finds the soil "
                         "strength that gives F = 1.0 (or another target) for this model - the strength the soil "
                         "really had. Leave 'c-phi line' ticked to get every (c', phi') pair that explains the "
                         "failure: a lab test or a second failed section then picks the right one.")
        p = main.project
        self.p = p
        self.an = analysis_combo(slope_analyses(p), main.current_analysis())
        self.mat = QComboBox()
        for m in p.materials:
            if m.model != "bedrock":
                self.mat.addItem(m.name, m.id)
        self.prop = QComboBox()
        for k, t in (("cohesion", "Cohesion c'"), ("phi", "Friction angle phi'"), ("unit_weight", "Unit weight")):
            self.prop.addItem(t, k)
        self.target = num(1.0, 0.5, 3.0, 3, 0.05)
        self.line = QCheckBox("Also the c-phi line (9 friction angles, takes longer)")
        self.line.setChecked(True)
        self.full = QCheckBox("Check the answer with a full slip-surface search")
        self.form.addRow("Slope analysis", self.an)
        self.form.addRow("Material", self.mat)
        self.form.addRow("Find", self.prop)
        self.form.addRow("Factor of safety at failure", self.target)
        self.form.addRow("", self.line)
        self.form.addRow("", self.full)
        self.apply_btn = self.add_button("Use this value in the model", self.apply)

    def run(self):
        a = self.p.analysis(self.an.currentData())
        mid, prop, tgt = self.mat.currentData(), self.prop.currentData(), self.target.value()
        line, full = self.line.isChecked(), self.full.isChecked()

        def work(progress):
            pool = SurfacePool(self.p, a)
            progress(20)
            r = backcalc.back_strength(self.p, a, mid, prop, tgt, pool=pool, full_check=full)
            progress(40)
            if line and prop in ("cohesion", "phi"):
                r["line"] = backcalc.c_phi_line(self.p, a, mid, tgt, pool=pool)
            return r
        self.start(work, self.show_result)

    def show_result(self, r):
        L = [r["message"], ""]
        if r.get("line"):
            L.append(f"c-phi pairs that give F = {r['target']:g} for '{r['material']}':")
            L.append(f"{'phi (deg)':>10}{'c':>12}{'F':>9}")
            for row in r["line"]["rows"]:
                c = "-" if row["c"] is None else f"{row['c']:.2f}"
                F = "-" if row["fos"] is None else f"{row['fos']:.3f}"
                L.append(f"{row['phi']:>10.1f}{c:>12}{F:>9}")
            L.append("")
        L.append(f"Quick evaluation on the slip surfaces of the last search ({r['evaluations']} runs). "
                 "Tick the full-search check for the final answer.")
        self.out.setPlainText("\n".join(L))
        self.apply_btn.setEnabled(r["status"] == "ok")

    def apply(self):
        r = self.result
        if not r or r["status"] != "ok":
            return
        self.main.before_change()
        setattr(self.main.project.material(r["material_id"]), r["prop"], round(r["value"], 4))
        self.main.after_change(f"Back-analysis: {r['prop']} of {r['material']} = {r['value']:.4g}")
        self.apply_btn.setEnabled(False)


class CalibrateKDialog(ToolDialog):
    def __init__(self, main):
        super().__init__(main, "Calibrate k from Piezometers",
                         "Enter the heads measured in piezometers (or import them in Tools > Monitoring Data). "
                         "GeoLab changes the hydraulic conductivity of the ticked materials until the seepage "
                         "analysis gives the same heads (least squares). With only head boundaries the heads "
                         "depend on the ratios of k, so leave one material unticked as the reference.")
        p = main.project
        self.p = p
        seeps = [a for a in p.analyses if a.kind == "seepage"]
        self.an = analysis_combo(seeps, main.current_analysis())
        self.form.addRow("Seepage analysis", self.an)
        self.mats = QListWidget()
        self.mats.setMaximumHeight(110)
        for i, m in enumerate(p.materials):
            it = QListWidgetItem(f"{m.name}   (k = {m.k_sat:.2e})")
            it.setData(Qt.UserRole, m.id)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if i == 0 else Qt.Unchecked)
            self.mats.addItem(it)
        self.form.addRow("Unknown k", self.mats)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["x", "y", f"measured head ({p.unit('length')})", "time (s, blank)"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setMaximumHeight(170)
        obs = [o for o in p.observations if o["kind"] == "head"]
        for o in obs or [{"x": "", "y": "", "value": "", "time": None}] * 3:
            self._row([o["x"], o["y"], o["value"], "" if o.get("time") is None else o["time"]])
        tb = QHBoxLayout()
        b1 = QPushButton("Add row")
        b1.clicked.connect(lambda: self._row(["", "", "", ""]))
        tb.addWidget(b1)
        tb.addStretch(1)
        self.form.addRow("Piezometers", self.table)
        self.form.addRow("", tb)
        self.apply_btn = self.add_button("Use the calibrated k", self.apply)

    def _row(self, vals):
        r = self.table.rowCount()
        self.table.insertRow(r)
        for j, v in enumerate(vals):
            self.table.setItem(r, j, QTableWidgetItem(str(v)))

    def run(self):
        obs = []
        for r in range(self.table.rowCount()):
            cells = [(self.table.item(r, j).text().strip() if self.table.item(r, j) else "") for j in range(4)]
            if not all(cells[:3]):
                continue
            try:
                obs.append({"x": float(cells[0]), "y": float(cells[1]), "head": float(cells[2]),
                            "time": float(cells[3]) if cells[3] else None})
            except ValueError:
                self.out.setPlainText(f"Row {r + 1} is not a number.")
                return
        mids = [self.mats.item(i).data(Qt.UserRole) for i in range(self.mats.count())
                if self.mats.item(i).checkState() == Qt.Checked]
        a = self.p.analysis(self.an.currentData())
        self.start(lambda progress: backcalc.calibrate_k(self.p, a, obs, mids, progress=progress), self.show_result)

    def show_result(self, r):
        L = [f"RMS head error: {r['rms_before']:.3f} before -> {r['rms_after']:.3f} after "
             f"({r['evaluations']} seepage runs)", ""]
        for m in r["materials"]:
            L.append(f"{m['name']}: k = {m['k_before']:.3e} -> {m['k_after']:.3e}")
        L += ["", f"{'x':>8}{'y':>8}{'measured':>11}{'computed':>11}"]
        for q in r["points"]:
            c = "-" if q["computed"] is None else f"{q['computed']:.3f}"
            L.append(f"{q['x']:>8.2f}{q['y']:>8.2f}{q['measured']:>11.3f}{c:>11}")
        self.out.setPlainText("\n".join(L))
        self.apply_btn.setEnabled(True)

    def apply(self):
        self.main.before_change()
        backcalc.apply_k(self.main.project, self.result)
        self.main.after_change("Calibrated k from piezometers")
        self.apply_btn.setEnabled(False)


# ---------------------------------------------------------------------------------------- optimizer
class OptimizerDialog(ToolDialog):
    def __init__(self, main):
        super().__init__(main, "Design Optimizer",
                         "Tell GeoLab the factor of safety you need and what you may change. It finds the "
                         "smallest change that is enough: how flat the slope, how wide a berm, how deep a drain, "
                         "how long or strong the reinforcement - or the largest load the crest can carry.")
        p = main.project
        self.p = p
        self.an = analysis_combo(slope_analyses(p), main.current_analysis())
        self.an.currentIndexChanged.connect(self._vars)
        self.var = QComboBox()
        self.var.currentIndexChanged.connect(self._range)
        self.why = QLabel()
        self.why.setWordWrap(True)
        self.why.setStyleSheet("color: #a05000")
        a = p.analysis(self.an.currentData()) if self.an.count() else None
        need = codes.required_fos(codes.code_of(p), codes.design_case(a) if a else "long_term",
                                  codes.settings_of(p))
        self.target = num(need, 0.8, 3.0, 2, 0.05)
        self.lo = num(0, -1e6, 1e6, 2, 0.5)
        self.hi = num(1, -1e6, 1e6, 2, 0.5)
        rr = QHBoxLayout()
        rr.addWidget(self.lo)
        rr.addWidget(QLabel("to"))
        rr.addWidget(self.hi)
        self.full = QCheckBox("Check the answer with a full slip-surface search")
        self.full.setChecked(True)
        self.form.addRow("Slope analysis", self.an)
        self.form.addRow("Change", self.var)
        self.form.addRow("", self.why)
        self.form.addRow(f"Target factor of safety ({codes.code_of(p)})", self.target)
        self.form.addRow("Search between", rr)
        self.form.addRow("", self.full)
        self.apply_btn = self.add_button("Use this design", self.apply)
        self._vars()

    def _vars(self):
        a = self.p.analysis(self.an.currentData())
        self.var.blockSignals(True)
        self.var.clear()
        if a is not None:
            for k, why in optimize.available(self.p, a).items():
                self.var.addItem(optimize.VARIABLES[k][0] + ("" if not why else "  (not available)"), k)
                self.var.setItemData(self.var.count() - 1, why, Qt.ToolTipRole)
        self.var.blockSignals(False)
        first = next((i for i in range(self.var.count()) if not self.var.itemData(i, Qt.ToolTipRole)), 0)
        self.var.setCurrentIndex(first)
        self._range()

    def _range(self):
        k = self.var.currentData()
        if not k:
            return
        why = self.var.itemData(self.var.currentIndex(), Qt.ToolTipRole)
        self.why.setText(why or "")
        self.run_btn.setEnabled(not why)
        lo, hi = optimize.VARIABLES[k][3]
        if k == "slope_ratio" and self.p.quick:
            lo = max(0.3, 0.5 * float(self.p.quick.get("ratio", 2)))
        self.lo.setValue(lo)
        self.hi.setValue(hi * (3.28 if self.p.units == "imperial" and optimize.VARIABLES[k][1] == "length" else 1))

    def run(self):
        a = self.p.analysis(self.an.currentData())
        k, t, lo, hi, full = self.var.currentData(), self.target.value(), self.lo.value(), self.hi.value(), \
            self.full.isChecked()
        self.start(lambda progress: optimize.optimize(self.p, a, k, t, lo, hi, progress, full), self.show_result)

    def show_result(self, r):
        L = [r["message"], "", "Steps tried:"]
        for x, F in r["history"]:
            L.append(f"   {x:>10.3f}   F = {F:.3f}" if F == F and F != float("inf") else f"   {x:>10.3f}   -")
        self.out.setPlainText("\n".join(L))
        self.apply_btn.setEnabled(r["status"] == "ok")

    def apply(self):
        r = self.result
        if r.get("project") is not None:
            if not self.main.maybe_save():
                return
            self.main.set_project(r["project"], dirty=True)
            self.main.log_msg("Design optimizer: " + r["message"])
        else:
            self.main.before_change()
            desc = optimize.apply(self.main.project, self.main.project.analysis(self.an.currentData()), r)
            self.main.after_change("Design optimizer: " + desc)
        self.apply_btn.setEnabled(False)


# --------------------------------------------------------------------------------------------- what-if
class WhatIfDialog(QDialog):
    """Sliders that change the model; the factor of safety and the slip surface follow at once."""

    SLIDERS = [  # key, label, lo, hi, step, default
        ("water_dy", "Water table up (+) / down (-)", -10.0, 10.0, 0.25, 0.0),
        ("load_factor", "Crest loads x", 0.0, 3.0, 0.05, 1.0),
        ("c_factor", "Cohesion x", 0.2, 2.0, 0.05, 1.0),
        ("tanphi_factor", "tan(phi) x", 0.5, 1.5, 0.02, 1.0),
        ("kh", "Earthquake kh", 0.0, 0.4, 0.01, 0.0),
        ("ru", "Pore-pressure ratio Ru", 0.0, 0.6, 0.02, 0.0),
    ]

    def __init__(self, main, pool: SurfacePool):
        super().__init__(main)
        self.main = main
        self.pool = pool
        self.setWindowTitle("What-If Sliders")
        self.resize(980, 700)
        a = pool.analysis
        v = QVBoxLayout(self)
        lab = QLabel("Move a slider and the factor of safety and the critical slip surface follow straight away. "
                     "Nothing in your model changes until you press 'Use in the model'. The answer comes from the "
                     f"{len(pool.surfaces)} slip surfaces of the last search; solve again to confirm.")
        lab.setWordWrap(True)
        v.addWidget(lab)
        top = QHBoxLayout()
        self.big = QLabel()
        f = QFont()
        f.setPointSize(30)
        f.setBold(True)
        self.big.setFont(f)
        self.big.setMinimumWidth(260)
        self.big.setAlignment(Qt.AlignCenter)
        top.addWidget(self.big)
        self.sub = QLabel()
        self.sub.setWordWrap(True)
        top.addWidget(self.sub, 1)
        v.addLayout(top)
        self.pic = QLabel()
        self.pic.setMinimumHeight(330)
        self.pic.setAlignment(Qt.AlignCenter)
        v.addWidget(self.pic, 1)
        grid = QGridLayout()
        self.sl = {}
        self.vals = {}
        rows = [s for s in self.SLIDERS if not (s[0] == "water_dy" and not (a.pwp == "piezometric"))
                and not (s[0] == "ru" and a.pwp != "ru")]
        for i, (k, label, lo, hi, step, default) in enumerate(rows):
            if k == "kh":
                default = a.kh
            if k == "ru":
                default = a.ru
            s = QSlider(Qt.Horizontal)
            n = int(round((hi - lo) / step))
            s.setRange(0, n)
            s.setValue(int(round((default - lo) / step)))
            val = QLabel()
            val.setMinimumWidth(70)
            s.valueChanged.connect(self._changed)
            grid.addWidget(QLabel(label), i // 2, (i % 2) * 3)
            grid.addWidget(s, i // 2, (i % 2) * 3 + 1)
            grid.addWidget(val, i // 2, (i % 2) * 3 + 2)
            self.sl[k] = (s, lo, step, default)
            self.vals[k] = val
        v.addLayout(grid)
        bb = QHBoxLayout()
        reset = QPushButton("Reset")
        reset.clicked.connect(self.reset)
        use = QPushButton("Use in the model")
        use.clicked.connect(self.use)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        bb.addWidget(reset)
        bb.addStretch(1)
        bb.addWidget(use)
        bb.addWidget(close)
        v.addLayout(bb)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(120)
        self.timer.timeout.connect(self.update_fos)
        self.need = codes.required_fos(codes.code_of(main.project), codes.design_case(a), codes.settings_of(main.project))
        self._changed()
        self.update_fos()

    def changes(self):
        out = {}
        for k, (s, lo, step, default) in self.sl.items():
            out[k] = lo + s.value() * step
        return out

    def _changed(self, *_):
        for k, val in self.changes().items():
            self.vals[k].setText(f"{val:+.2f}" if k == "water_dy" else f"{val:.2f}")
        self.timer.start()

    def reset(self):
        for k, (s, lo, step, default) in self.sl.items():
            s.blockSignals(True)
            s.setValue(int(round((default - lo) / step)))
            s.blockSignals(False)
        self._changed()

    def update_fos(self):
        ch = self.changes()
        p, a = apply_changes(self.pool.project, self.pool.analysis, ch)
        F, surf = self.pool.evaluate(project=p, analysis=a)
        ok = F >= self.need
        col = "#1a7f37" if ok else ("#b35900" if F >= 1.0 else "#c01010")
        self.big.setText(f"F = {F:.3f}" if F != float("inf") else "F = -")
        self.big.setStyleSheet(f"color: {col}")
        self.sub.setText(f"Before: F = {self.pool.base_fos:.3f}.  The design code ({codes.code_of(p)}) asks for "
                         f"F >= {self.need:g} in this case: " + ("enough." if ok else "not enough.")
                         + (" Below 1.0 the slope fails." if F < 1 else ""))
        w = max(600, self.pic.width())
        h = max(300, self.pic.height())
        self.pic.setPixmap(QPixmap.fromImage(render_png(p, a, surf, F if surf else None, w, h)))

    def use(self):
        ch = {k: v for k, v in self.changes().items()
              if abs(v - self.sl[k][3]) > 1e-9}
        if not ch:
            return
        p, a = apply_changes(self.main.project, self.pool.analysis, ch)
        self.main.before_change()
        self.main.project.materials = p.materials
        self.main.project.piezometric_line = p.piezometric_line
        self.main.project.surcharges = p.surcharges
        self.main.project.point_loads = p.point_loads
        tgt = self.main.project.analysis(a.id)
        tgt.kh, tgt.ru = a.kh, a.ru
        self.main.after_change("What-if: " + ", ".join(f"{k} {v:.3g}" for k, v in ch.items()))
        self.accept()


# ------------------------------------------------------------------------------------- design codes
class CodeDialog(QDialog):
    def __init__(self, main):
        super().__init__(main)
        self.main = main
        self.p = main.project
        self.setWindowTitle("Design Code Check")
        self.resize(820, 680)
        v = QVBoxLayout(self)
        f = QFormLayout()
        self.code = QComboBox()
        for k, t in codes.CODES.items():
            self.code.addItem(t, k)
        self.code.setCurrentIndex(self.code.findData(codes.code_of(self.p)))
        self.code.currentIndexChanged.connect(self._fill)
        f.addRow("Design code", self.code)
        v.addLayout(f)
        self.settings_box = QGroupBox("Site and design settings")
        self.sf = QFormLayout(self.settings_box)
        v.addWidget(self.settings_box)
        self.seis = QLabel()
        self.seis.setWordWrap(True)
        v.addWidget(self.seis)
        row = QHBoxLayout()
        self.use_kh = QPushButton("Put this kh in the earthquake analyses")
        self.use_kh.clicked.connect(self.put_kh)
        self.check_btn = QPushButton("Check the solved analyses")
        self.check_btn.setDefault(True)
        self.check_btn.clicked.connect(self.check)
        row.addWidget(self.use_kh)
        row.addStretch(1)
        row.addWidget(self.check_btn)
        v.addLayout(row)
        self.out = QPlainTextEdit()
        self.out.setReadOnly(True)
        self.out.setFont(MONO)
        v.addWidget(self.out, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self.widgets = {}
        self.job = None
        self._fill()

    def _combo(self, key, items, cur):
        c = QComboBox()
        for k, t in items:
            c.addItem(t, k)
        i = c.findData(cur)
        c.setCurrentIndex(max(0, i))
        c.currentIndexChanged.connect(self._changed)
        self.widgets[key] = c
        return c

    def _num(self, key, val, lo, hi, dec=3, step=0.01):
        w = num(val, lo, hi, dec, step)
        w.valueChanged.connect(self._changed)
        self.widgets[key] = w
        return w

    def _fill(self):
        while self.sf.rowCount():
            self.sf.removeRow(0)
        self.widgets = {}
        code = self.code.currentData()
        s = dict(codes.DEFAULT_SETTINGS.get(code, {}))
        s.update((self.p.code_settings or {}).get(code, {}))
        case_items = [("auto", "Automatic (from the analysis: kh, drawdown, 'temporary' in the name)")] + \
            list(codes.CASES.items())
        if code == "AS":
            self.sf.addRow("Soil class (AS 4678)", self._combo("soil_class", [(k, v["label"]) for k, v in
                                                                             codes.AS4678_CLASSES.items()],
                                                              s.get("soil_class")))
            city = self._combo("city", [(k, f"{k} (Z = {z:g})") for k, z in codes.AS1170_Z.items()]
                               + [("other", "Other place (enter Z)")], s.get("city"))
            city.currentIndexChanged.connect(self._city)
            self.sf.addRow("Location (AS 1170.4)", city)
            self.sf.addRow("Hazard factor Z (g)", self._num("Z", float(s.get("Z", 0.08)), 0.01, 0.6))
            self.sf.addRow("Annual probability of exceedance", self._combo(
                "probability", [(k, f"{k}  (kp = {v:g})") for k, v in codes.AS1170_KP.items()], s.get("probability")))
            self.sf.addRow("Site sub-soil class", self._combo(
                "site", [(k, f"{k} - {t} (Ch(0) = {c:g})") for k, (t, c) in codes.AS1170_SITE.items()], s.get("site")))
        elif code == "BNBC":
            city = self._combo("city", [(k, f"{k} (zone {z})") for k, z in codes.BNBC_CITIES.items()]
                               + [("other", "Other place (choose the zone)")], s.get("city"))
            city.currentIndexChanged.connect(self._city)
            self.sf.addRow("Location", city)
            self.sf.addRow("Seismic zone", self._combo(
                "zone", [(k, f"Zone {k} (Z = {z:g} g)") for k, z in codes.BNBC_ZONES.items()], int(s.get("zone", 2))))
            self.sf.addRow("Site class", self._combo(
                "site", [(k, f"{k} - {t} (S = {v:g})") for k, (t, v) in codes.BNBC_SITE.items()], s.get("site")))
            self.sf.addRow("Importance category", self._combo(
                "importance", [(k, f"{k} (I = {v:g})") for k, v in codes.BNBC_IMPORTANCE.items()], s.get("importance")))
        if code != "none":
            self.sf.addRow("kh as a fraction of the PGA", self._num("kh_fraction", float(s.get("kh_fraction", 0.5)),
                                                                   0.1, 1.0, 2, 0.05))
        self.sf.addRow("Design case", self._combo("case", case_items, s.get("case", "auto")))
        need = codes.MIN_FOS[code]
        for case, label in codes.CASES.items():
            self.sf.addRow(f"Minimum F, {label.lower()}", self._num(f"min_{case}", float(s.get(f"min_{case}", need[case])),
                                                                    0.8, 3.0, 2, 0.05))
        self._changed()

    def _city(self, *_):
        code = self.code.currentData()
        c = self.widgets["city"].currentData()
        if code == "AS" and c in codes.AS1170_Z:
            self.widgets["Z"].setValue(codes.AS1170_Z[c])
        if code == "BNBC" and c in codes.BNBC_CITIES:
            w = self.widgets["zone"]
            w.setCurrentIndex(w.findData(codes.BNBC_CITIES[c]))

    def values(self) -> dict:
        out = {}
        for k, w in self.widgets.items():
            out[k] = w.currentData() if isinstance(w, QComboBox) else w.value()
        return out

    def _changed(self, *_):
        code = self.code.currentData()
        self.p.design_code = code
        self.p.code_settings = dict(self.p.code_settings or {})
        self.p.code_settings[code] = self.values()
        self.main.dirty = True
        sz = codes.seismic(code, codes.settings_of(self.p))
        self.seis.setText(sz["text"])
        self.use_kh.setEnabled(code != "none")

    def put_kh(self):
        sz = codes.seismic(self.code.currentData(), codes.settings_of(self.p))
        eq = [a for a in self.p.analyses if a.kind == "slope" and abs(a.kh) > 0]
        if not eq:
            base = next(iter(slope_analyses(self.p)), None)
            if base is None:
                return
            self.main.before_change()
            import dataclasses
            d = dataclasses.asdict(base)
            d.update(id=self.p.next_id(self.p.analyses), name=base.name + " + earthquake", results=None,
                     kh=round(sz["kh"], 3))
            from ..model import Analysis
            self.p.analyses.append(Analysis.from_dict(d))
            self.main.after_change(f"Added an earthquake copy of '{base.name}' (kh = {sz['kh']:.3f})")
            return
        self.main.before_change()
        for a in eq:
            a.kh = round(sz["kh"], 3)
        self.main.after_change(f"Seismic kh = {sz['kh']:.3f} from {self.code.currentData()}")

    def check(self):
        if not slope_analyses(self.p, solved_only=True):
            self.out.setPlainText("Solve the slope analyses first (Shift+F5 solves them all).")
            return
        self.check_btn.setEnabled(False)
        self.out.setPlainText("Checking...")
        self.job = Job(lambda progress: codes.summary_text(self.p))
        self.job.done.connect(lambda t: (self.out.setPlainText(t), self.check_btn.setEnabled(True)))
        self.job.failed.connect(lambda m: (self.out.setPlainText(m), self.check_btn.setEnabled(True)))
        self.job.start()

    def done(self, r):
        if self.job is not None and self.job.isRunning():
            self.job.wait(30000)
        super().done(r)


# ------------------------------------------------------------------------------------- liquefaction
class LiquefactionDialog(ToolDialog):
    def __init__(self, main):
        super().__init__(main, "Liquefaction Check (SPT / CPT)",
                         "Loose saturated sand and silt can lose its strength in an earthquake. Enter the SPT N "
                         "values (or cone readings) with depth: GeoLab gives the factor of safety against "
                         "liquefaction at each depth and the liquefaction potential index LPI. The peak ground "
                         "acceleration comes from the design code (AS 1170.4 or BNBC 2020). Metric units.")
        p = main.project
        self.p = p
        self.method = QComboBox()
        self.method.addItem("SPT (Idriss & Boulanger 2014)", "spt")
        self.method.addItem("CPT (Robertson & Wride 1998)", "cpt")
        self.method.currentIndexChanged.connect(self._cols)
        self.wd = num(1.5, 0.0, 50.0, 2, 0.5, "m")
        sz = codes.seismic(codes.code_of(p), codes.settings_of(p))
        self.amax = num(round(sz["pga"], 3) or 0.15, 0.01, 1.5, 3, 0.01, "g")
        self.mag = num(7.5, 5.0, 9.0, 1, 0.1)
        self.form.addRow("Method", self.method)
        self.form.addRow("Water table depth", self.wd)
        self.form.addRow("Peak ground acceleration (g)", self.amax)
        self.form.addRow(f"({codes.code_of(p)}: {sz['text'][:90]}...)" if sz["pga"] else "", QLabel(""))
        self.form.addRow("Earthquake magnitude", self.mag)
        self.hole = QComboBox()
        self.hole.addItem("(type the values below)", None)
        for i, h in enumerate(p.boreholes or []):
            self.hole.addItem(f"{h['hole']} ({h['kind']})", i)
        self.hole.currentIndexChanged.connect(self._load_hole)
        self.form.addRow("Values from", self.hole)
        self.table = QTableWidget(0, 5)
        self.table.setMinimumHeight(180)
        self.form.addRow(self.table)
        b = QPushButton("Add row")
        b.clicked.connect(lambda: self.table.insertRow(self.table.rowCount()))
        ex = QPushButton("Example values")
        ex.clicked.connect(self._example)
        hb = QHBoxLayout()
        hb.addWidget(b)
        hb.addWidget(ex)
        hb.addStretch(1)
        self.form.addRow(hb)
        self.save_btn = self.add_button("Put in the design report", self.keep)
        self._cols()
        self._example()

    def _cols(self):
        spt = self.method.currentData() == "spt"
        self.table.setColumnCount(5 if spt else 4)
        self.table.setHorizontalHeaderLabels(["depth (m)", "SPT N", "fines %", "PI (blank = non-plastic)", "unit wt"]
                                             if spt else ["depth (m)", "qc (kPa)", "fs (kPa)", "u2 (kPa)"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

    def _example(self):
        spt = self.method.currentData() == "spt"
        rows = ([[1.5, 4, 60, 15, 17], [3, 6, 25, "", 18.5], [4.5, 8, 15, "", 18.5], [6, 11, 10, "", 19],
                 [7.5, 15, 8, "", 19], [9, 22, 5, "", 19.5], [12, 35, 5, "", 20]] if spt else
                [[1, 1500, 30, 0], [2, 2500, 25, 0], [3, 3500, 30, 0], [4, 4000, 40, 0], [5, 900, 35, 0],
                 [6, 6000, 50, 0], [8, 9000, 60, 0]])
        self._set_rows(rows)

    def _set_rows(self, rows):
        self.table.setRowCount(0)
        for r in rows:
            i = self.table.rowCount()
            self.table.insertRow(i)
            for j, v in enumerate(r):
                self.table.setItem(i, j, QTableWidgetItem("" if v is None else str(v)))

    def _load_hole(self):
        i = self.hole.currentData()
        if i is None:
            return
        from ..borehole import spt_rows_for_liquefaction
        h = self.p.boreholes[i]
        if h["kind"] == "cpt":
            self.method.setCurrentIndex(1)
            self._set_rows([[t["depth"], t["qc"], t["fs"], t["u2"]] for t in h["readings"]])
        else:
            self.method.setCurrentIndex(0)
            self._set_rows([[r["depth"], r["N"], r["fc"], "" if r.get("pi") is None else r["pi"], r.get("gamma") or ""]
                            for r in spt_rows_for_liquefaction(h)])

    def rows(self):
        spt = self.method.currentData() == "spt"
        out = []
        for r in range(self.table.rowCount()):
            cells = [(self.table.item(r, j).text().strip() if self.table.item(r, j) else "")
                     for j in range(self.table.columnCount())]
            if not cells[0] or not cells[1]:
                continue
            f = [float(c) if c else None for c in cells]
            out.append({"depth": f[0], "N": f[1], "fc": f[2] or 0, "pi": f[3], "gamma": f[4]} if spt else
                       {"depth": f[0], "qc": f[1], "fs": f[2] or 0, "u2": f[3] or 0})
        return out

    def run(self):
        try:
            rows = self.rows()
        except ValueError:
            self.out.setPlainText("Every cell must be a number.")
            return
        if not rows:
            self.out.setPlainText("Enter at least one row.")
            return
        fn = liquefaction.spt if self.method.currentData() == "spt" else liquefaction.cpt
        wd, am, M = self.wd.value(), self.amax.value(), self.mag.value()
        self.start(lambda progress: fn(rows, wd, am, M), lambda r: (
            self.out.setPlainText(liquefaction.text_report(r)), self.save_btn.setEnabled(True)))

    def keep(self):
        self.p.code_settings = dict(self.p.code_settings or {})
        self.p.code_settings["_liquefaction"] = liquefaction.text_report(self.result)
        self.main.dirty = True
        self.save_btn.setEnabled(False)
        self.main.log_msg("Liquefaction check saved for the design report.")


# ----------------------------------------------------------------------------------------- boreholes
class BoreholeDialog(ToolDialog):
    def __init__(self, main):
        super().__init__(main, "Import Boreholes / CPT",
                         "Read borehole logs (one row per layer: hole, x, ground, top, bottom, soil, N, fc, pi) or "
                         "CPT soundings (hole, x, ground, depth, qc, fs, u2) from CSV or Excel. GeoLab joins the "
                         "layers between the holes, estimates c', phi', unit weight and k from SPT N or the cone "
                         "(published correlations), and builds the cross-section with a slope analysis. Soil "
                         "names may be USCS symbols (AS 1726): CH, CL, SM, SP ...", run_label="Read the file")
        self.holes = None
        self.path = QLineEdit()
        browse = QPushButton("Browse")
        browse.clicked.connect(self.browse)
        sample = QPushButton("Use the sample logs")
        sample.clicked.connect(self.sample)
        r = QHBoxLayout()
        r.addWidget(self.path, 1)
        r.addWidget(browse)
        r.addWidget(sample)
        self.form.addRow("File", r)
        self.wd = num(2.0, 0.0, 50.0, 2, 0.5, main.project.unit("length"))
        self.dry = QCheckBox("No groundwater")
        self.undr = QCheckBox("Clay layers undrained (Su from N / cone) - short term")
        self.form.addRow("Water table depth below the ground", self.wd)
        self.form.addRow("", self.dry)
        self.form.addRow("", self.undr)
        self.build_btn = self.add_button("Build the section", self.build)
        self.text = None

    def browse(self):
        p, _ = QFileDialog.getOpenFileName(self, "Borehole or CPT log", self.main.last_dir(),
                                           "Logs (*.csv *.txt *.xlsx);;All files (*)")
        if p:
            self.path.setText(p)
            self.text = None
            self.run()

    def sample(self):
        from ..borehole import SAMPLE_BOREHOLES
        self.text = SAMPLE_BOREHOLES
        self.path.setText("(sample: three boreholes across a slope)")
        self.run()

    def run(self):
        from ..borehole import parse_logs, unit_parameters
        src = self.text or self.path.text().strip()
        if not src:
            self.out.setPlainText("Choose a file first.")
            return
        try:
            self.holes = parse_logs(src)
        except Exception as e:                    # noqa: BLE001
            self.out.setPlainText(f"Could not read the logs: {e}")
            return
        params = unit_parameters(self.holes, self.wd.value())
        L = [f"{len(self.holes)} hole(s):"]
        for h in self.holes:
            n = len(h["layers"]) if h["kind"] == "borehole" else len(h["readings"])
            L.append(f"  {h['hole']}: x = {h['x']:g}, ground {h['ground']:g}, {n} "
                     f"{'layers' if h['kind'] == 'borehole' else 'cone readings'}"
                     + (" (qc in MPa, converted)" if h.get("qc_was_mpa") else ""))
        L += ["", f"{'Soil unit':<28}{'type':<7}{'c':>6}{'phi':>6}{'gamma':>7}{'k (m/s)':>10}{'Su':>7}"]
        for n, q in params.items():
            L.append(f"{n[:27]:<28}{q['kind']:<7}{q['c']:>6.1f}{q['phi']:>6.1f}{q['gamma']:>7.1f}{q['k']:>10.1e}"
                     f"{'' if q['Su'] is None else format(q['Su'], '.0f'):>7}")
        L += ["", "Correlations: sand phi' from (N1)60 (Hatanaka & Uchida), clay Su = 5 N (Stroud), cone: "
                  "Robertson (Ic, unit weight, k), Kulhawy & Mayne (phi'). Check them against lab tests."]
        self.out.setPlainText("\n".join(L))
        self.build_btn.setEnabled(True)

    def build(self):
        from ..borehole import build_section
        if not self.main.maybe_save():
            return
        try:
            p, _ = build_section(copy.deepcopy(self.holes), None if self.dry.isChecked() else self.wd.value(),
                                 units=self.main.project.units, clay_undrained=self.undr.isChecked())
        except Exception as e:                    # noqa: BLE001
            QMessageBox.warning(self, "Boreholes", f"Could not build the section: {e}")
            return
        p.design_code = self.main.project.design_code
        self.main.set_project(p, dirty=True)
        self.main.log_msg(f"Section built from {len(self.holes)} borehole(s).")
        self.accept()


# ------------------------------------------------------------------------------------------ rainfall
class RainfallDialog(ToolDialog):
    def __init__(self, main):
        super().__init__(main, "Rainfall from Weather Data",
                         "Get the real daily rainfall and evaporation of a place from the free Open-Meteo weather "
                         "archive (internet needed; only the coordinates and dates are sent), read it from a CSV "
                         "file (date, rain mm/day, et0 mm/day), or make a design storm. GeoLab puts it on the "
                         "climate boundary of the transient seepage analysis, so the slope can be checked through "
                         "a real monsoon.", run_label="Get the weather data")
        from PySide6.QtCore import QDate
        self.p = main.project
        self.series = None
        self.place = QComboBox()
        for k in rainfall.PLACES:
            self.place.addItem(k, rainfall.PLACES[k])
        self.place.addItem("Other (enter latitude and longitude)", None)
        self.place.currentIndexChanged.connect(self._place)
        self.lat = num(22.3569, -90, 90, 4, 0.1)
        self.lon = num(91.7832, -180, 180, 4, 0.1)
        y = datetime.date.today().year - 1
        self.d0 = QDateEdit(QDate(y, 6, 1))
        self.d1 = QDateEdit(QDate(y, 9, 30))
        for d in (self.d0, self.d1):
            d.setCalendarPopup(True)
            d.setDisplayFormat("yyyy-MM-dd")
        self.form.addRow("Place", self.place)
        ll = QHBoxLayout()
        ll.addWidget(self.lat)
        ll.addWidget(self.lon)
        self.form.addRow("Latitude, longitude", ll)
        dd = QHBoxLayout()
        dd.addWidget(self.d0)
        dd.addWidget(QLabel("to"))
        dd.addWidget(self.d1)
        self.form.addRow("Dates", dd)
        other = QHBoxLayout()
        csvb = QPushButton("From a CSV file...")
        csvb.clicked.connect(self.from_csv)
        self.storm_mm = num(500, 1, 5000, 0, 10, "mm")
        self.storm_days = QSpinBox()
        self.storm_days.setRange(1, 120)
        self.storm_days.setValue(5)
        self.storm_days.setSuffix(" days")
        sb = QPushButton("Design storm")
        sb.clicked.connect(self.storm)
        other.addWidget(csvb)
        other.addStretch(1)
        other.addWidget(self.storm_mm)
        other.addWidget(self.storm_days)
        other.addWidget(sb)
        self.form.addRow("Or", other)
        seeps = [a for a in self.p.analyses if a.kind == "seepage"]
        self.an = analysis_combo(seeps, next((a for a in seeps if a.transient), None))
        self.form.addRow("Seepage analysis", self.an)
        self.apply_btn = self.add_button("Use in the model", self.apply)

    def _place(self):
        v = self.place.currentData()
        if v:
            self.lat.setValue(v[0])
            self.lon.setValue(v[1])

    def run(self):
        lat, lon = self.lat.value(), self.lon.value()
        a, b = self.d0.date().toString("yyyy-MM-dd"), self.d1.date().toString("yyyy-MM-dd")
        self.start(lambda progress: rainfall.fetch_open_meteo(lat, lon, a, b), self.show)

    def from_csv(self):
        p, _ = QFileDialog.getOpenFileName(self, "Rainfall CSV", self.main.last_dir(), "CSV (*.csv *.txt);;Excel (*.xlsx)")
        if p:
            try:
                self.show(rainfall.from_csv(p))
            except Exception as e:                 # noqa: BLE001
                self.out.setPlainText(str(e))

    def storm(self):
        self.show(rainfall.design_storm(self.storm_mm.value(), self.storm_days.value()))

    def show(self, s):
        self.series = s
        st = rainfall.stats(s)
        L = [s["source"], f"{st['days']} days, total rain {st['total']:.0f} mm, wettest day {st['max_day']:.0f} mm "
                          f"({st['max_day_date']}), wettest 5 days {st['max_5day']:.0f} mm, ET0 {st['et0_total']:.0f} mm", ""]
        peak = max(s["rain"]) or 1.0
        for d, r in list(zip(s["dates"], s["rain"]))[:400]:
            L.append(f"{d:>12} {r:7.1f} mm  " + "#" * int(round(40 * r / peak)))
        self.out.setPlainText("\n".join(L))
        self.apply_btn.setEnabled(self.an.count() > 0)

    def apply(self):
        a = self.p.analysis(self.an.currentData())
        self.main.before_change()
        try:
            msg = rainfall.apply_to_project(self.main.project, self.series, a)
        except ValueError as e:
            QMessageBox.warning(self, "Rainfall", str(e))
            return
        self.main.after_change(msg)
        QMessageBox.information(self, "Rainfall", msg + "\n\nSolve all (Shift+F5) to see the slope through the season.")
        self.apply_btn.setEnabled(False)


# ---------------------------------------------------------------------------------------- monitoring
class MonitoringDialog(ToolDialog):
    def __init__(self, main):
        super().__init__(main, "Monitoring Data",
                         "Import readings of piezometers, settlement plates or inclinometers (CSV: instrument, kind, "
                         "x, y, time, value; kind = head, pore_pressure, settlement, displacement_x or "
                         "displacement_y; time like '30 d') and compare them with an analysis. The readings are "
                         "kept in the project and go into the design report.", run_label="Compare")
        self.p = main.project
        imp = QPushButton("Import CSV...")
        imp.clicked.connect(self.import_csv)
        clr = QPushButton("Clear readings")
        clr.clicked.connect(self.clear)
        r = QHBoxLayout()
        self.count = QLabel()
        r.addWidget(imp)
        r.addWidget(clr)
        r.addWidget(self.count, 1)
        self.form.addRow("Readings", r)
        self.an = analysis_combo([a for a in self.p.analyses if a.kind in ("seepage", "stress")],
                                 main.current_analysis())
        self.form.addRow("Analysis", self.an)
        self.cal = self.add_button("Calibrate k from these heads...", self.calibrate, True)
        self._count()

    def _count(self):
        kinds = {}
        for o in self.p.observations:
            kinds[o["kind"]] = kinds.get(o["kind"], 0) + 1
        self.count.setText(", ".join(f"{v} {k}" for k, v in kinds.items()) or "none yet")

    def import_csv(self):
        path, _ = QFileDialog.getOpenFileName(self, "Monitoring CSV", self.main.last_dir(),
                                              "CSV (*.csv *.txt);;Excel (*.xlsx)")
        if not path:
            return
        try:
            obs = monitoring.parse(path)
        except Exception as e:                    # noqa: BLE001
            QMessageBox.warning(self, "Monitoring", str(e))
            return
        self.main.before_change()
        self.p.observations = list(self.p.observations) + obs
        self.main.after_change(f"Imported {len(obs)} monitoring readings", keep_results=True)
        self._count()

    def clear(self):
        self.main.before_change()
        self.p.observations = []
        self.main.after_change("Cleared the monitoring readings", keep_results=True)
        self._count()

    def run(self):
        a = self.p.analysis(self.an.currentData())
        if a is None:
            self.out.setPlainText("Add a seepage or stress-deformation analysis first.")
            return
        if not self.p.observations:
            self.out.setPlainText("Import readings first.")
            return
        self.start(lambda progress: monitoring.compare(self.p, a),
                   lambda r: self.out.setPlainText(monitoring.text_report(self.p, r)))

    def calibrate(self):
        self.accept()
        CalibrateKDialog(self.main).exec()


# ------------------------------------------------------------------------------------ photo -> model
class PhotoDialog(ToolDialog):
    def __init__(self, main):
        super().__init__(main, "Model from Photo or Sketch (AI)",
                         "Take a photo of a slope or river bank, or of a hand sketch or drawing of the "
                         "cross-section (dimensions written on it help). Claude reads the picture and builds the "
                         "model; check every number afterwards. The picture is sent to Anthropic with your API key "
                         "(Edit > Preferences > AI Assistant).", run_label="Build the model")
        self.image = None
        self.mt = None
        self.path = QLineEdit()
        b = QPushButton("Choose picture...")
        b.clicked.connect(self.choose)
        r = QHBoxLayout()
        r.addWidget(self.path, 1)
        r.addWidget(b)
        self.form.addRow("Picture", r)
        self.preview = QLabel()
        self.preview.setFixedHeight(200)
        self.preview.setAlignment(Qt.AlignCenter)
        self.form.addRow(self.preview)
        self.note = QLineEdit()
        self.note.setPlaceholderText("e.g. bank about 6 m high, clay over sand, river at the toe")
        self.form.addRow("Notes", self.note)
        self.open_btn = self.add_button("Open in GeoLab", self.open_model)

    def choose(self):
        from ..ai import IMAGE_TYPES
        p, _ = QFileDialog.getOpenFileName(self, "Photo or sketch", self.main.last_dir(),
                                           "Pictures (*.png *.jpg *.jpeg *.webp *.gif)")
        if not p:
            return
        ext = Path(p).suffix.lower()
        self.mt = IMAGE_TYPES.get(ext)
        data = Path(p).read_bytes()
        img = QImage.fromData(data)
        if len(data) > 4.5 * 1024 * 1024 and not img.isNull():   # shrink big phone photos
            img = img.scaled(2000, 2000, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            data = png_bytes(img) if self.mt == "image/png" else self._jpeg(img)
        self.image = data
        self.path.setText(p)
        if not img.isNull():
            self.preview.setPixmap(QPixmap.fromImage(img).scaled(500, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    @staticmethod
    def _jpeg(img):
        from PySide6.QtCore import QBuffer, QByteArray, QIODevice
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.WriteOnly)
        img.save(buf, "JPEG", 88)
        return bytes(ba.data())

    def run(self):
        from ..ai import generate_from_image
        if not self.image:
            self.out.setPlainText("Choose a picture first.")
            return
        key = str(self.main.settings.value("ai/api_key", "") or self.main.settings.value("ai/key/claude", "") or "")
        key = key or os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            self.out.setPlainText("Add your Anthropic API key in Edit > Preferences > AI Assistant first.")
            return
        img, mt, note = self.image, self.mt, self.note.text()
        self.start(lambda progress: generate_from_image(img, mt, note, api_key=key), self.show)

    def show(self, r):
        p, notes = r
        self.out.setPlainText(f"Model: {p.title}\n{len(p.materials)} materials, {len(p.regions)} regions.\n\n"
                              f"Assumptions:\n{notes or '(none listed)'}")
        self.open_btn.setEnabled(True)

    def open_model(self):
        if not self.main.maybe_save():
            return
        p, notes = self.result
        p.design_code = self.main.project.design_code
        self.main.set_project(p, dirty=True)
        self.main.log_msg("Model built from a picture. Assumptions: " + (notes or "-"))
        self.accept()


# ---------------------------------------------------------------------------------------- templates
class TemplateDialog(QDialog):
    """River bank or flood embankment from a few numbers."""

    def __init__(self, main, kind="riverbank"):
        super().__init__(main)
        from .. import templates
        self.main = main
        self.kind = kind
        self.project = None
        self.setWindowTitle("New River Bank" if kind == "riverbank" else "New Flood Embankment")
        v = QVBoxLayout(self)
        intro = QLabel(
            "A river bank with a clay top over fine sand and a scour hole at the toe (Padma, Jamuna, Meghna...). "
            "Three analyses: high flood, rapid drawdown after the flood (the usual cause of bank failures as the "
            "monsoon floods fall) and the flood with an earthquake. Levels are above the river bed at the toe."
            if kind == "riverbank" else
            "A flood embankment (levee) on soft clay over sand, river on the left: steady seepage at the flood level, "
            "the land side and the river side at flood, and the land side with the earthquake coefficient of the "
            "selected design code.")
        intro.setWordWrap(True)
        v.addWidget(intro)
        f = QFormLayout()
        self.w = {}
        d = templates.RIVERBANK_DEFAULTS if kind == "riverbank" else templates.FLOOD_DEFAULTS
        labels = ({"height": "Bank height (m)", "ratio": "Bank slope (H:1V)", "scour": "Scour depth at the toe (m)",
                   "flood": "Flood level (m)", "low": "Low water after the flood (m)",
                   "clay_thickness": "Clay top layer thickness (m)"} if kind == "riverbank" else
                  {"height": "Embankment height (m)", "crest_width": "Crest width (m)",
                   "river_slope": "River-side slope (H:1V)", "land_slope": "Land-side slope (H:1V)",
                   "clay": "Soft clay thickness (m)", "flood": "Flood level above the ground (m)"})
        for k, lab in labels.items():
            self.w[k] = num(float(d[k]), 0.0, 100.0, 2, 0.5)
            f.addRow(lab, self.w[k])
        v.addLayout(f)
        self.solve_now = QCheckBox("Solve straight away")
        self.solve_now.setChecked(True)
        v.addWidget(self.solve_now)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.make)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def make(self):
        from .. import templates
        q = {k: w.value() for k, w in self.w.items()}
        try:
            fn = templates.riverbank if self.kind == "riverbank" else templates.flood_embankment
            self.project = fn(q)
        except ValueError as e:
            QMessageBox.warning(self, self.windowTitle(), str(e))
            return
        self.accept()


# ------------------------------------------------------------------------------------- design report
def design_report(main):
    """Ask where to save the design report (Word or PDF) and write it."""
    from .. import designreport
    p = main.project
    if not any(a.results for a in p.analyses):
        if QMessageBox.question(main, "Design report", "No analysis is solved yet. Make the report anyway?") \
                != QMessageBox.Yes:
            return None
    path, flt = QFileDialog.getSaveFileName(main, "Design Report", str(Path(main.last_dir()) / (
        (p.title or "GeoLab").replace("/", "-") + " - design report.docx")),
        "Word document (*.docx);;PDF (*.pdf)")
    if not path:
        return None
    if not Path(path).suffix:
        path += ".pdf" if "PDF" in flt else ".docx"
    images = {}
    for a in p.analyses:
        if a.results:
            try:
                images[a.id] = png_bytes(render_png(p, a, w=1500, h=820))
            except Exception:                          # noqa: BLE001  (a missing picture is not fatal)
                traceback.print_exc()
    try:
        blocks = designreport.build(p, images)
    except Exception as e:                             # noqa: BLE001
        QMessageBox.warning(main, "Design report", f"Could not make the report: {e}")
        return None
    if path.lower().endswith(".pdf"):
        write_pdf(blocks, path, p.title)
    else:
        designreport.to_docx(blocks, path, title=p.title, author=p.author)
    main.log_msg(f"Design report saved: {path}")
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices
    QDesktopServices.openUrl(QUrl.fromLocalFile(path))
    return path


def write_pdf(blocks, path, title=""):
    from PySide6.QtCore import QMarginsF, QSizeF, QUrl
    from PySide6.QtGui import QPageLayout, QPageSize, QPdfWriter, QTextDocument

    from .. import designreport
    doc = QTextDocument()
    doc.setDefaultStyleSheet("body{font-family:'Segoe UI','Helvetica Neue','Nirmala UI','Kohinoor Bangla','Bangla Sangam MN',Arial;font-size:9.5pt}"
                             "h1{color:#1d4e89;font-size:18pt}h2{color:#1d4e89;font-size:13pt}h3{font-size:11pt}"
                             "th{background:#e8eef6}td,th{padding:3px}pre{font-family:Consolas;font-size:7.5pt}")
    imgs = []

    def src(i, png):
        url = f"report-img-{i}"
        imgs.append((url, png))
        return url
    html = designreport.to_html(blocks, src)
    for url, png in imgs:
        doc.addResource(QTextDocument.ImageResource, QUrl(url), QImage.fromData(png))
    doc.setHtml(html)
    w = QPdfWriter(path)
    w.setTitle(title or "Design report")
    w.setPageLayout(QPageLayout(QPageSize(QPageSize.A4), QPageLayout.Portrait, QMarginsF(16, 16, 16, 16),
                                QPageLayout.Millimeter))
    w.setResolution(150)
    from PySide6.QtCore import QRectF as _R
    paint = w.pageLayout().paintRectPixels(w.resolution())
    width_px = 680
    scale = paint.width() / width_px
    page_h = paint.height() / scale
    doc.setPageSize(QSizeF(width_px, page_h))
    g = QPainter(w)
    n = doc.pageCount()
    for i in range(n):
        if i:
            w.newPage()
        g.save()
        g.scale(scale, scale)
        g.translate(0, -i * page_h)
        doc.drawContents(g, _R(0, i * page_h, width_px, page_h))
        g.restore()
    g.end()
    return n
