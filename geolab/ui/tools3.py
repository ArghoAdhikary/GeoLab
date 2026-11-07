"""Dialogs of GeoLab 2.13: quick earthquake check (ky and Newmark displacement), parametric study, pile
design, soil nails / anchors / geosynthetics, braced excavations, Excel export and my templates."""
from __future__ import annotations

import math

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFileDialog, QGridLayout,
                               QHBoxLayout, QInputDialog, QLabel, QMessageBox, QPlainTextEdit, QPushButton,
                               QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from .tools import ToolDialog, analysis_combo, num, slope_analyses
from .tools2 import Chart

SERIES = ["#2f6fe0", "#d9534f", "#5cb85c", "#e8a33d", "#8e44ad", "#16a085", "#7f8c8d", "#c0392b"]


# --------------------------------------------------------------------------- earthquake
class SeismicDialog(ToolDialog):
    def __init__(self, main):
        from .. import seismic
        super().__init__(main, "Earthquake Check (ky and Newmark Displacement)",
                         "Finds the yield acceleration ky (the seismic coefficient that brings F to 1) on the slip "
                         "surfaces of the solved slope analysis, then the permanent displacement from published "
                         "regressions of ky / amax. No acceleration record or dynamic analysis is needed.", "Run")
        self.S = seismic
        p = main.project
        self.analysis = analysis_combo(slope_analyses(p, solved_only=True), main.current_analysis())
        self.form.addRow("Analysis", self.analysis)
        pga, self.pga_text = seismic.code_pga(p)
        self.amax = num(pga or 0.15, 0.01, 2.0, 3, 0.01, "g")
        self.form.addRow("Peak ground acceleration amax", self.amax)
        lab = QLabel(self.pga_text or "Set the design code in Design > Design Code Settings to get amax from it.")
        lab.setWordWrap(True)
        lab.setEnabled(False)
        self.form.addRow("", lab)
        self.M = num(7.0, 4.0, 9.5, 1, 0.1)
        self.form.addRow("Earthquake magnitude M", self.M)
        self.chart = Chart("Displacement against amax", "amax (g)", "displacement (cm)")
        self.chart.setMinimumHeight(200)
        self.v.insertWidget(3, self.chart, 1)
        self.keep = self.add_button("Put in the Design Report", self._keep)

    def run(self, wait=False):
        p = self.main.project
        a = p.analysis(self.analysis.currentData())
        if a is None:
            return None
        amax, M = self.amax.value(), self.M.value()

        def job(progress=None, cancelled=None):
            from ..whatif import SurfacePool
            return self.S.assess(SurfacePool(p, a, n=20), amax, M), a.name
        if wait:
            return self._show(job())
        self.start(job, self._show)
        return None

    def _show(self, out):
        res, name = out
        self.result = res
        self.out.setPlainText(self.S.text_report(res, name, self.pga_text))
        self.chart.clear()
        if res["ky"] > 0:
            for i, m in enumerate(self.S.METHODS):
                pts = self.S.curve(res["ky"], res["M"], m, max(0.8, 1.5 * res["amax"]))
                if pts:
                    self.chart.line([x for x, _ in pts], [min(y, 500) for _, y in pts], SERIES[i], 2,
                                    self.S.METHODS[m])
            self.chart.vline(res["amax"], "#888", "amax")
        self.chart.update()
        self.keep.setEnabled(True)
        return res

    def _keep(self):
        p = self.main.project
        a = p.analysis(self.analysis.currentData())
        r = self.result
        if a is None or not a.results or not r:
            return
        d = r["displacement"]
        d_len = d / 100 * (3.280839895 if p.units == "imperial" else 1.0)
        a.results["newmark"] = {"displacement": d_len if math.isfinite(d) else None, "ky": r["ky"],
                                "amax": r["amax"], "M": r["M"], "hazard": r["hazard_label"],
                                "method": "regression on ky/amax (Jibson 2007; Ambraseys and Menu 1988)"}
        self.main.dirty = True
        self.main.refresh_all()
        self.main.log_msg(f"ky = {r['ky']:.3f}, Newmark displacement {d:.1f} cm kept for '{a.name}'.")


# --------------------------------------------------------------------------- parametric
class ParametricDialog(ToolDialog):
    def __init__(self, main):
        from .. import parametric
        super().__init__(main, "Parametric Study",
                         "Change one value (or two) over a range and see the factor of safety at every step, and "
                         "where it crosses 1.0 and the target. Uses the slip surfaces of the solved analysis, so "
                         "it is quick; tick 'Full search' to search again at every point (slower).", "Run")
        self.P = parametric
        p = main.project
        self.analysis = analysis_combo(slope_analyses(p, solved_only=True), main.current_analysis())
        self.form.addRow("Analysis", self.analysis)
        self.labels = parametric.parameters(p)
        self.rows = []
        for i, title in enumerate(("Vary", "and (optional)")):
            box = QComboBox()
            if i:
                box.addItem("(nothing)", "")
            for k, lab in self.labels.items():
                box.addItem(lab, k)
            lo, hi = num(0, -1e6, 1e6, 3, 0.1), num(1, -1e6, 1e6, 3, 0.1)
            n = QSpinBox()
            n.setRange(2, 101)
            n.setValue(11 if i == 0 else 5)
            row = QHBoxLayout()
            row.addWidget(box, 2)
            for t, w_ in (("from", lo), ("to", hi), ("steps", n)):
                row.addWidget(QLabel(t))
                row.addWidget(w_)
            self.form.addRow(title, row)
            box.currentIndexChanged.connect(lambda _=0, j=i: self._range(j))
            self.rows.append((box, lo, hi, n))
        self.target = num(1.5, 0.5, 5, 2, 0.05)
        self.full = QCheckBox("Full search at every point")
        r = QHBoxLayout()
        r.addWidget(self.target)
        r.addWidget(self.full)
        r.addStretch(1)
        self.form.addRow("Target F", r)
        self._range(0)
        self.chart = Chart("Factor of safety", "", "F")
        self.chart.setMinimumHeight(220)
        self.v.insertWidget(3, self.chart, 1)
        self.save_btn = self.add_button("Save Table (Excel / CSV)...", self._save)

    def _range(self, j):
        box, lo, hi, _ = self.rows[j]
        key = box.currentData()
        a = self.main.project.analysis(self.analysis.currentData())
        if key and a is not None:
            a0, b0 = self.P.default_range(self.main.project, a, key)
            lo.setValue(a0)
            hi.setValue(b0)

    def run(self, wait=False):
        p = self.main.project
        a = p.analysis(self.analysis.currentData())
        if a is None:
            return None
        b1, lo1, hi1, n1 = self.rows[0]
        b2, lo2, hi2, n2 = self.rows[1]
        k1, k2 = b1.currentData(), b2.currentData() or None
        xs = self.P.values(lo1.value(), hi1.value(), n1.value())
        ys = self.P.values(lo2.value(), hi2.value(), n2.value()) if k2 else None
        full = self.full.isChecked()

        def job(progress=None, cancelled=None):
            from ..whatif import SurfacePool
            pool = SurfacePool(p, a, n=20)
            return self.P.run(pool, k1, xs, k2, ys, confirm=full, progress=progress, cancelled=cancelled)
        if wait:
            return self._show(job())
        self.start(job, self._show)
        return None

    def _show(self, res):
        self.result = res
        t = self.target.value()
        self.out.setPlainText(self.P.text_report(res, self.labels, t))
        self.chart.clear()
        self.chart.xlabel = self.labels.get(res["key"], res["key"])
        for j, row in enumerate(res["F"]):
            lab = f"{self.labels.get(res['key2'], '')} = {res['ys'][j]:.3g}" if res["key2"] else "F"
            pts = [(x, v) for x, v in zip(res["xs"], row) if math.isfinite(v)]
            if pts:
                self.chart.line([x for x, _ in pts], [v for _, v in pts], SERIES[j % len(SERIES)], 2, lab,
                                points=True)
        self.chart.hline(1.0, "#d32f2f", "F = 1")
        self.chart.hline(t, "#2e9d4f", f"target {t:g}")
        self.chart.update()
        self.save_btn.setEnabled(True)
        return res

    def _save(self, path=None):
        if not self.result:
            return None
        if not path:
            path, _ = QFileDialog.getSaveFileName(self, "Save Table", self.main.last_dir(),
                                                  "Excel (*.xlsx);;CSV (*.csv)")
            if not path:
                return None
        rows = self.P.rows(self.result, self.labels)
        if path.lower().endswith(".csv"):
            import csv
            with open(path, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerows(rows)
        else:
            from .. import xlsx
            if not path.lower().endswith(".xlsx"):
                path += ".xlsx"
            xlsx.write(path, [("Parametric study", rows)])
        self.main.log_msg(f"Parametric table saved: {path}")
        return path


# --------------------------------------------------------------------------- piles, nails, excavations
def _spin(val, lo, hi, dec=2):
    s = QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setDecimals(dec)
    s.setValue(val)
    return s


class DesignToolsDialog(QDialog):
    """Piles, soil nails, ground anchors, geosynthetics and braced excavations (one tab each)."""
    TABS = ["pile", "nail", "anchor", "geo", "excavation"]

    def __init__(self, main, tab="pile"):
        super().__init__(main)
        from .. import excavation, nails, piles
        self.main, self.Pi, self.N, self.E = main, piles, nails, excavation
        self.setWindowTitle("Piles, Nails, Anchors and Excavations")
        self.resize(860, 720)
        v = QVBoxLayout(self)
        self.tabs = QTabWidget()
        v.addWidget(self.tabs, 1)
        self.out = QPlainTextEdit()
        self.out.setReadOnly(True)
        self.out.setFont(QFont("Consolas", 9))
        v.addWidget(self.out, 1)
        self.result = None
        self._pile_tab()
        self._nail_tab()
        self._anchor_tab()
        self._geo_tab()
        self._exc_tab()
        self.tabs.setCurrentIndex(self.TABS.index(tab) if tab in self.TABS else 0)

    def _grid(self, fields):
        g = QGridLayout()
        w = {}
        for i, (key, label, val, lo, hi) in enumerate(fields):
            w[key] = _spin(val, lo, hi)
            g.addWidget(QLabel(label), i // 2, (i % 2) * 2)
            g.addWidget(w[key], i // 2, (i % 2) * 2 + 1)
        return g, w

    def _page(self, title):
        page = QWidget()
        lay = QVBoxLayout(page)
        self.tabs.addTab(page, title)
        return lay

    @staticmethod
    def _vals(w):
        return {k: s.value() for k, s in w.items()}

    # -- piles
    def _pile_tab(self):
        lay = self._page("Pile capacity and groups")
        g, self.pw = self._grid([("D", "Diameter / width D (m)", 0.6, 0.1, 5), ("L", "Length (m)", 20.0, 1, 120),
                                 ("water", "Water table depth (m)", 1.0, 0, 100), ("FS", "Factor of safety", 2.5, 1, 5),
                                 ("rows", "Group: rows", 1, 1, 30), ("cols", "Group: columns", 1, 1, 30),
                                 ("s", "Group: spacing (m)", 1.8, 0.2, 20), ("load", "Load per pile (kN, 0 = allowable)", 0, 0, 1e6),
                                 ("E", "Pile modulus E (MPa)", 30000, 1000, 250000)])
        lay.addLayout(g)
        r = QHBoxLayout()
        self.p_kind = QComboBox()
        self.p_kind.addItem("Driven", "driven")
        self.p_kind.addItem("Bored (cast in place)", "bored")
        self.p_shape = QComboBox()
        self.p_shape.addItem("Circular", "circle")
        self.p_shape.addItem("Square", "square")
        for w_ in (QLabel("Pile"), self.p_kind, self.p_shape):
            r.addWidget(w_)
        r.addStretch(1)
        lay.addLayout(r)
        lay.addWidget(QLabel("Layers from the top: thickness (m, 0 = to the bottom), clay or sand, Su (kPa) "
                             "or phi' (deg), unit weight (kN/m3)"))
        self.p_layers = QPlainTextEdit("4, clay, 20, 17\n8, sand, 30, 19\n0, clay, 80, 19")
        self.p_layers.setMaximumHeight(90)
        lay.addWidget(self.p_layers)
        b = QPushButton("Calculate")
        b.clicked.connect(self.run_pile)
        lay.addWidget(b)
        self.p_chart = Chart("Shaft resistance with depth", "Qs (kN)", "depth (m)")
        self.p_chart.setMinimumHeight(140)
        lay.addWidget(self.p_chart, 1)

    def pile_layers(self):
        out = []
        for line in self.p_layers.toPlainText().splitlines():
            parts = [x.strip() for x in line.split(",") if x.strip()]
            if len(parts) < 3:
                continue
            soil = "sand" if parts[1].lower().startswith(("s", "g")) else "clay"
            d = {"thickness": float(parts[0]), "soil": soil, "gamma": float(parts[3]) if len(parts) > 3 else 18.0}
            d["su" if soil == "clay" else "phi"] = float(parts[2])
            out.append(d)
        return out

    def run_pile(self):
        v = self._vals(self.pw)
        try:
            layers = self.pile_layers()
            r = self.Pi.axial(layers, v["D"], v["L"], self.p_kind.currentData(), self.p_shape.currentData(),
                              v["water"], v["FS"])
            g = None
            if int(v["rows"]) * int(v["cols"]) > 1:
                g = self.Pi.group(r, layers, int(v["rows"]), int(v["cols"]), v["s"], v["FS"], v["E"] * 1000,
                                  (v["load"] * int(v["rows"]) * int(v["cols"])) or None)
        except (ValueError, IndexError) as e:
            self.out.setPlainText(f"Could not calculate: {e}")
            return None
        self.out.setPlainText(self.Pi.text_report(r, g))
        self.p_chart.clear()
        self.p_chart.line([x["Qs"] for x in r["rows"]], [-x["z"] for x in r["rows"]], SERIES[0], 2, "Qs")
        self.p_chart.update()
        self.result = (r, g)
        return r, g

    # -- soil nails
    def _nail_tab(self):
        lay = self._page("Soil nail wall")
        g, self.nw = self._grid([("H", "Wall height H (m)", 6.0, 1, 30), ("sh", "Horizontal spacing (m)", 1.5, 0.5, 4),
                                 ("sv", "Vertical spacing (m)", 1.5, 0.5, 4), ("incl", "Inclination (deg)", 15, 0, 45),
                                 ("phi", "Soil phi' (deg)", 30, 10, 45), ("gamma", "Unit weight (kN/m3)", 18, 10, 25),
                                 ("q", "Surcharge (kPa)", 10, 0, 200), ("drill", "Drill hole diameter (mm)", 100, 50, 300),
                                 ("qs", "Bond stress q_s (kPa)", 100, 10, 500), ("fy", "Bar yield fy (MPa)", 500, 250, 1000)])
        lay.addLayout(g)
        r = QHBoxLayout()
        self.n_bar = QComboBox()
        for d in self.N.BARS:
            self.n_bar.addItem(f"{d} mm", d)
        self.n_bar.setCurrentIndex(1)
        self.n_bond = QComboBox()
        self.n_bond.addItem("(enter q_s)", 0)
        for k, val in self.N.BOND.items():
            self.n_bond.addItem(f"{k}: {val} kPa", val)
        self.n_bond.activated.connect(lambda i: self.n_bond.itemData(i) and self.nw["qs"].setValue(self.n_bond.itemData(i)))
        for w_ in (QLabel("Bar"), self.n_bar, QLabel("Typical bond"), self.n_bond):
            r.addWidget(w_)
        r.addStretch(1)
        lay.addLayout(r)
        r = QHBoxLayout()
        b = QPushButton("Calculate")
        b.clicked.connect(self.run_nail)
        self.n_use = QPushButton("Use for the Model's Nails")
        self.n_use.setEnabled(False)
        self.n_use.clicked.connect(self.use_nails)
        r.addWidget(b)
        r.addWidget(self.n_use)
        r.addStretch(1)
        lay.addLayout(r)
        lay.addStretch(1)

    def run_nail(self):
        v = self._vals(self.nw)
        try:
            d = self.N.nail_wall(v["H"], v["sh"], v["sv"], v["phi"], v["gamma"], v["q"], v["incl"], v["drill"] / 1000,
                                 self.n_bar.currentData(), v["fy"], v["qs"])
        except ValueError as e:
            self.out.setPlainText(str(e))
            return None
        self.nail = d
        self.out.setPlainText(self.N.text_report(d))
        self.n_use.setEnabled(True)
        return d

    def use_nails(self):
        self.main.before_change()
        n = self.N.apply_to_project(self.main.project, self.nail)
        self.main.dirty = True
        self.main.refresh_all()
        self.out.appendPlainText(f"\n{n} nail(s) of the model updated." if n else
                                 "\nThe model has no nails yet: draw them with Define > Reinforcement (type nail).")
        return n

    # -- ground anchors
    def _anchor_tab(self):
        lay = self._page("Ground anchor")
        g, self.aw = self._grid([("T", "Design load T (kN)", 400, 10, 1e5), ("drill", "Drill hole (mm)", 150, 50, 400),
                                 ("qs", "Bond stress q_s (kPa)", 150, 10, 2000), ("FS", "Factor of safety on bond", 2.0, 1, 4),
                                 ("strands", "Strands", 4, 1, 40), ("area", "Strand area (mm2)", 140, 50, 300),
                                 ("fpu", "Strand fpu (MPa)", 1860, 1000, 2200), ("free", "Free length (m)", 6, 0, 50)])
        lay.addLayout(g)
        b = QPushButton("Calculate")
        b.clicked.connect(self.run_anchor)
        lay.addWidget(b)
        lay.addStretch(1)

    def run_anchor(self):
        v = self._vals(self.aw)
        r = self.N.anchor(v["T"], v["drill"] / 1000, v["qs"], v["FS"], int(v["strands"]), v["area"], v["fpu"], v["free"])
        self.out.setPlainText(
            f"Ground anchor, design load {r['T']:.0f} kN\n"
            f"Bond: {r['pullout_per_m']:.1f} kN/m ultimate -> bond length {r['bond_length']:.2f} m (at least 4.5 m)\n"
            f"Free length {r['free_length']:.1f} m (at least 4.5 m and past the slip surface)\n"
            f"Total length {r['total']:.2f} m\n"
            f"Tendon at 0.6 fpu: {r['tendon_capacity']:.0f} kN -> {'OK' if r['tendon_ok'] else 'NOT OK: add strands'}\n"
            "Proof test every anchor to 1.33 - 1.5 x the design load (BS 8081 / PTI).")
        return r

    # -- geosynthetics
    def _geo_tab(self):
        lay = self._page("Geosynthetics")
        r = QHBoxLayout()
        self.g_box = QComboBox()
        for k in self.N.GEOSYNTHETICS:
            self.g_box.addItem(k, k)
        r.addWidget(QLabel("Product type"))
        r.addWidget(self.g_box, 1)
        lay.addLayout(r)
        g, self.gw = self._grid([("rf_id", "RF installation damage", 0, 0, 5), ("rf_cr", "RF creep", 0, 0, 10),
                                 ("rf_d", "RF durability", 0, 0, 5), ("bond", "Pullout per m (kN/m, 0 = keep)", 0, 0, 1000)])
        lay.addLayout(g)
        lay.addWidget(QLabel("Leave a factor at 0 to use the library value. Use the manufacturer's certified "
                             "values for design."))
        r = QHBoxLayout()
        b = QPushButton("Calculate")
        b.clicked.connect(self.run_geo)
        self.g_use = QPushButton("Use for the Model's Geosynthetics")
        self.g_use.clicked.connect(self.use_geo)
        r.addWidget(b)
        r.addWidget(self.g_use)
        r.addStretch(1)
        lay.addLayout(r)
        lay.addStretch(1)

    def run_geo(self):
        v = self._vals(self.gw)
        g = self.N.geosynthetic(self.g_box.currentData(), v["rf_id"] or None, v["rf_cr"] or None, v["rf_d"] or None)
        self.geo = g
        self.out.setPlainText(
            f"{g['name']} ({g['kind']})\nT_ult = {g['T_ult']:g} kN/m\n"
            f"RF_ID = {g['RF_ID']:g}, RF_CR = {g['RF_CR']:g}, RF_D = {g['RF_D']:g}\n"
            f"Long-term design strength T_al = T_ult / (RF_ID RF_CR RF_D) = {g['T_al']:.1f} kN/m")
        return g

    def use_geo(self):
        g = self.run_geo()
        self.main.before_change()
        n = self.N.apply_geosynthetic(self.main.project, g, self.gw["bond"].value() or None)
        self.main.dirty = True
        self.main.refresh_all()
        self.out.appendPlainText(f"\n{n} geosynthetic layer(s) of the model updated." if n else
                                 "\nThe model has no geosynthetic reinforcement yet (Define > Reinforcement).")
        return n

    # -- braced excavation
    def _exc_tab(self):
        lay = self._page("Braced excavation")
        g, self.ew = self._grid([("H", "Depth H (m)", 8.0, 1, 40), ("gamma", "Unit weight (kN/m3)", 18, 10, 25),
                                 ("phi", "Sand phi' (deg)", 32, 10, 45), ("su", "Clay Su (kPa)", 40, 0, 1000),
                                 ("q", "Surcharge (kPa)", 10, 0, 200), ("spacing", "Strut spacing along the wall (m)", 3, 0.5, 20),
                                 ("B", "Excavation width B (m)", 10, 1, 200), ("Lx", "Length L (m, 0 = long)", 0, 0, 1000),
                                 ("su_base", "Su below the base (kPa)", 40, 0, 1000)])
        lay.addLayout(g)
        r = QHBoxLayout()
        self.e_soil = QComboBox()
        self.e_soil.addItem("Sand", "sand")
        self.e_soil.addItem("Clay", "clay")
        from PySide6.QtWidgets import QLineEdit
        self.e_levels = QLineEdit("1.5, 4.0, 6.5")
        for w_ in (QLabel("Soil"), self.e_soil, QLabel("Strut depths (m)"), self.e_levels):
            r.addWidget(w_)
        lay.addLayout(r)
        b = QPushButton("Calculate")
        b.clicked.connect(self.run_exc)
        lay.addWidget(b)
        self.e_chart = Chart("Apparent pressure", "pressure (kPa)", "depth (m)")
        self.e_chart.setMinimumHeight(140)
        lay.addWidget(self.e_chart, 1)

    def run_exc(self):
        v = self._vals(self.ew)
        try:
            env = self.E.envelope(self.e_soil.currentData(), v["H"], v["gamma"], v["phi"], v["su"], v["q"])
            levels = [float(x) for x in self.e_levels.text().replace(";", ",").split(",") if x.strip()]
            st = self.E.strut_loads(env, levels, v["spacing"])
            heave = (self.E.basal_heave(v["H"], v["B"], v["Lx"], v["su_base"], v["gamma"], v["q"])
                     if self.e_soil.currentData() == "clay" and v["su_base"] > 0 else None)
        except ValueError as e:
            self.out.setPlainText(f"Could not calculate: {e}")
            return None
        self.out.setPlainText(self.E.text_report(env, st, heave))
        self.e_chart.clear()
        pts = [(0.0, 0.0)] + [(p_, -z) for z, p_ in env["points"]] + [(0.0, -env["H"])]
        self.e_chart.line([x for x, _ in pts], [y for _, y in pts], SERIES[1], 2, "pressure")
        self.e_chart.update()
        return env, st, heave


# --------------------------------------------------------------------------- Excel and templates
def export_excel(main, path=None):
    if not path:
        stem = (main.project.title or "GeoLab").replace("/", "-")
        import os
        path, _ = QFileDialog.getSaveFileName(main, "Export Results to Excel",
                                              os.path.join(main.last_dir(), f"{stem}.xlsx"), "Excel (*.xlsx)")
        if not path:
            return None
    if not path.lower().endswith(".xlsx"):
        path += ".xlsx"
    from .. import xlsx
    try:
        xlsx.export_project(main.project, path)
    except OSError as e:
        QMessageBox.warning(main, "Export to Excel", f"Could not write the file: {e}")
        return None
    main.log_msg(f"Results exported to Excel: {path}")
    return path


def save_template(main, name=None):
    from .. import usertemplates
    if name is None:
        name, ok = QInputDialog.getText(main, "Save as My Template", "Template name:",
                                        text=main.project.title or "My template")
        if not ok or not name.strip():
            return None
    path = usertemplates.save_template(main.project, name.strip())
    main.log_msg(f"Template saved: {path}")
    return path


def fill_template_menu(main, menu):
    from .. import usertemplates
    menu.clear()
    items = usertemplates.list_templates()
    for p in items:
        menu.addAction(p.stem, lambda path=p: new_from_template(main, path))
    if items:
        menu.addSeparator()
    menu.addAction("Save the Open Project as a Template...", lambda: save_template(main))
    menu.addAction("Open the Templates Folder", lambda: _open_folder(usertemplates.templates_dir()))


def _open_folder(d):
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices
    d.mkdir(parents=True, exist_ok=True)
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(d)))


def new_from_template(main, path):
    from .. import usertemplates
    if not main.maybe_save():
        return None
    try:
        p = usertemplates.new_from_template(path)
    except Exception as e:                                 # noqa: BLE001
        QMessageBox.warning(main, "New from My Template", str(e))
        return None
    main.set_project(p)
    main.log_msg(f"New project from the template '{path.stem}'.")
    return p
