"""Beginner helpers: the step bar above the drawing and the Quick Slope dialog.

The step bar shows the steps of the current analysis in order (draw the ground, soil properties, water,
...), ticks the ones that are done, highlights the next one and says in plain words what to do next.
Each step is a button that opens the right tool.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QFrame,
                               QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
                               QToolButton, QVBoxLayout)

from .theme import is_dark

ACCENT = "#2f6fe0"


def steps_for(project, analysis):
    """[(key, title, done, hint)] for the analysis kind, in the order a beginner should follow."""
    p, a = project, analysis
    kind = a.kind if a is not None else "slope"
    have_regions = bool(p.regions)
    all_mats = have_regions and all(p.material(r.material_id) is not None for r in p.regions)
    edited_mats = all_mats and any(m.name != "Soil 1" or m.cohesion != 5.0 or m.phi != 30.0 for m in p.materials)
    solved = bool(a and a.results)
    steps = [("region", "Draw the ground", have_regions,
              "Click the corners of each soil layer on the drawing; click the first point again to close it. "
              "Or start from File > New Quick Slope."),
             ("materials", "Soil properties", edited_mats,
              "Open Materials and enter the strength (c', phi') and unit weight of each soil, then use "
              "Draw > Materials to click each region with its soil.")]
    if kind == "slope":
        water_done = len(p.piezometric_line) >= 2 or (a.pwp != "piezometric" and edited_mats)
        steps.append(("piezo", "Water table (optional)", water_done,
                      "If there is groundwater, draw the water table from left to right and press Enter. "
                      "If the slope is dry you can skip this."))
        s = a.search
        search_ok = s.mode != "entry_exit" or (s.entry_x1 != s.entry_x2 or s.exit_x1 != s.exit_x2)
        steps.append(("entry_exit", "Where it can slide", search_ok and have_regions,
                      "Tell GeoLab where slip surfaces may start (crest) and end (toe): Draw > Slip Surface Entry "
                      "and Exit, or press Auto in the analysis settings."))
    elif kind in ("seepage", "thermal", "transport", "air"):
        group = {"seepage": "hydraulic", "thermal": "thermal", "transport": "transport", "air": "air"}[kind]
        steps.append(("bc", "Boundary conditions", bool(p.bcs(group, a)),
                      "Draw the boundaries: for seepage, the water level on each side (total head) and where "
                      "water can leave (seepage face). Click along a region edge and press Enter."))
    elif kind in ("stress", "dynamic"):
        steps.append(("bc", "Supports and loads", bool(p.bcs("stress", a)),
                      "Fix the model: 'Fixed x' on the left and right sides, 'Fixed x and y' at the bottom. "
                      "Then draw pressures or loads."))
        if kind == "stress":
            staged = bool(a.inactive_regions) or bool(getattr(p, "structures", []))
            steps.append(("analysis", "Stages and structures (optional)", staged or a.parent_id is None,
                          "For excavations and fills, add child stages and tick which regions exist in each "
                          "(Analysis settings > Construction Stage); draw walls and anchors with Draw > Structures."))
    steps.append(("solve", "Solve", solved, "Press Solve (F5). The Solve Manager at the bottom shows progress."))
    steps.append(("results", "See the results", solved and False,
                  "Switch to Results to see the factor of safety, contours and graphs. View > Report gives "
                  "everything as text."))
    return steps


class StepBar(QFrame):
    """A row of numbered step buttons with a hint for the next step."""

    step_clicked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("stepbar")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(4)
        top = QHBoxLayout()
        top.setSpacing(6)
        self.row = QHBoxLayout()
        self.row.setSpacing(6)
        top.addLayout(self.row)
        top.addStretch(1)
        self.close_btn = QToolButton()
        from ..i18n import tr
        self.close_btn.setText(tr("Hide guide"))
        self.close_btn.setToolTip("Hide the step guide (View > Show Step Guide brings it back)")
        top.addWidget(self.close_btn)
        lay.addLayout(top)
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        lay.addWidget(self.hint)
        self.buttons = []

    def update_steps(self, project, analysis):
        for b in self.buttons:               # Qt keeps ownership: no Python-side delete racing deleteLater
            self.row.removeWidget(b)
            b.hide()
            b.deleteLater()
        self.buttons = []
        from ..i18n import tr
        steps = [(k, tr(t), d, tr(h)) for k, t, d, h in steps_for(project, analysis)]
        nxt = next((i for i, s in enumerate(steps) if not s[2]), len(steps) - 1)
        dark = is_dark()
        for i, (key, title, done, hint) in enumerate(steps):
            mark = "✓" if done else str(i + 1)
            b = QPushButton(f" {mark}  {title} ")
            b.setCursor(Qt.PointingHandCursor)
            b.setToolTip(hint)
            if i == nxt:
                from . import appearance
                style = (f"background:{appearance.color('stepbar', 'fg', appearance.accent())}; color:white; "
                         "font-weight:bold; border:0;")
            elif done:
                style = ("background:#1f3d2a; color:#9be2b0;" if dark else "background:#e3f4e8; color:#1e6b3a;") + " border:0;"
            else:
                style = ("background:#2a313b; color:#c6ced8;" if dark else "background:#eef1f5; color:#3b4654;") + " border:0;"
            b.setStyleSheet(f"QPushButton {{{style} border-radius:13px; padding:4px 10px;}}")
            b.clicked.connect(lambda _=False, k=key: self.step_clicked.emit(k))
            self.row.addWidget(b)
            self.buttons.append(b)
        key, title, done, hint = steps[nxt]
        self.hint.setText(f"<b>{tr('Next')}: {title}.</b> {hint}" if not all(s[2] for s in steps[:-1])
                          or nxt < len(steps) - 1 else f"<b>{tr('Done')}.</b> {steps[-1][3]}")
        from . import appearance
        line, bg = ("#313b47", "#1b2129") if dark else ("#d6dce4", "#fafbfd")
        self.setStyleSheet("#stepbar { border-bottom: 1px solid %s; background: %s; }"
                           % (line, appearance.color("stepbar", "bg", bg)))


class QuickSlopeDialog(QDialog):
    """Build a complete slope model from a few numbers (no drawing needed)."""

    def __init__(self, parent=None, units="metric"):
        super().__init__(parent)
        self.setWindowTitle("Quick Slope")
        self.units = units
        L = "m" if units == "metric" else "ft"
        Pu = "kPa" if units == "metric" else "psf"
        G = "kN/m³" if units == "metric" else "pcf"
        v = QVBoxLayout(self)
        intro = QLabel("Enter the size of the slope and its soil layers. GeoLab draws the model, sets up the "
                       "slip surface search and can solve it straight away. You can change anything afterwards.")
        intro.setWordWrap(True)
        v.addWidget(intro)
        f = QFormLayout()

        def num(val, lo, hi, dec=2, step=1.0):
            w = QDoubleSpinBox()
            w.setRange(lo, hi)
            w.setDecimals(dec)
            w.setSingleStep(step)
            w.setValue(val)
            return w
        scale = 1.0 if units == "metric" else 3.28
        self.height = num(10 * scale, 0.5, 1e4)
        self.ratio = num(2.0, 0.0, 20, 2, 0.25)
        self.crest = num(20 * scale, 1, 1e5)
        self.toe = num(20 * scale, 1, 1e5)
        self.base = num(5 * scale, 0.5, 1e5)
        self.water_on = QCheckBox("Water table")
        self.water = num(4 * scale, 0, 1e4)
        self.water.setEnabled(False)
        self.water_on.toggled.connect(self.water.setEnabled)
        self.load = num(0.0, 0, 1e6)
        f.addRow(f"Slope height ({L})", self.height)
        f.addRow("Slope steepness (horizontal : 1 vertical)", self.ratio)
        f.addRow(f"Ground behind the crest ({L})", self.crest)
        f.addRow(f"Ground in front of the toe ({L})", self.toe)
        f.addRow(f"Soil below the toe ({L})", self.base)
        wrow = QHBoxLayout()
        wrow.addWidget(self.water_on)
        wrow.addWidget(self.water)
        wrow.addWidget(QLabel(f"{L} below the crest"))
        f.addRow("Groundwater", wrow)
        f.addRow(f"Load on the crest ({Pu}, 0 = none)", self.load)
        v.addLayout(f)
        v.addWidget(QLabel("<b>Soil layers</b> (top to bottom; the last one goes to the bottom of the model)"))
        self.grid = QGridLayout()
        for c, t in enumerate(("Name", f"c' ({Pu})", "phi' (deg)", f"Unit weight ({G})", f"Thickness ({L})")):
            self.grid.addWidget(QLabel(t), 0, c)
        v.addLayout(self.grid)
        self.rows = []
        g = 18.0 if units == "metric" else 115.0
        self._add_row("Clay", 10 * (1 if units == "metric" else 20.9), 25, g, 5 * scale)
        self._add_row("Sand", 0, 34, g + (2 if units == "metric" else 12), 0)
        btns = QHBoxLayout()
        add = QPushButton("+ Add layer")
        add.clicked.connect(lambda: self._add_row(f"Soil {len(self.rows) + 1}", 5, 30, g, 3 * scale))
        rem = QPushButton("- Remove last layer")
        rem.clicked.connect(self._remove_row)
        btns.addWidget(add)
        btns.addWidget(rem)
        btns.addStretch(1)
        v.addLayout(btns)
        self.solve_now = QCheckBox("Solve straight away")
        self.solve_now.setChecked(True)
        v.addWidget(self.solve_now)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Build slope")
        bb.accepted.connect(self.try_accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self.project = None

    def _add_row(self, name, c, phi, gamma, thick):
        if len(self.rows) >= 6:
            return
        r = len(self.rows) + 1
        w = [QLineEdit(name)]
        for val, hi, dec in ((c, 1e6, 2), (phi, 89, 1), (gamma, 1e4, 2), (thick, 1e5, 2)):
            s = QDoubleSpinBox()
            s.setRange(0, hi)
            s.setDecimals(dec)
            s.setValue(val)
            w.append(s)
        for c_, wd in enumerate(w):
            self.grid.addWidget(wd, r, c_)
        self.rows.append(w)
        self._thickness_state()

    def _remove_row(self):
        if len(self.rows) <= 1:
            return
        for wd in self.rows.pop():
            self.grid.removeWidget(wd)
            wd.hide()
            wd.deleteLater()
        self._thickness_state()

    def _thickness_state(self):
        for i, w in enumerate(self.rows):
            w[4].setEnabled(i < len(self.rows) - 1)

    def params(self):
        layers = [{"name": w[0].text().strip() or f"Soil {i + 1}", "c": w[1].value(), "phi": w[2].value(),
                   "gamma": w[3].value(), "thickness": w[4].value()} for i, w in enumerate(self.rows)]
        return {"height": self.height.value(), "ratio": self.ratio.value(), "crest": self.crest.value(),
                "toe": self.toe.value(), "base": self.base.value(), "layers": layers,
                "water": self.water.value() if self.water_on.isChecked() else None,
                "surcharge": self.load.value()}

    def try_accept(self):
        from ..quick import quick_slope
        try:
            q = self.params()
            if any(l["gamma"] <= 0 for l in q["layers"]):
                raise ValueError("Every layer needs a positive unit weight.")
            if any(l["thickness"] <= 0 for l in q["layers"][:-1]):
                raise ValueError("Every layer except the last needs a thickness.")
            p = quick_slope(q)
            if self.units == "imperial":
                p.units = "imperial"
                p.title = p.title.replace(" m slope", " ft slope")
                p.grid_spacing = 2.0
        except ValueError as e:
            QMessageBox.warning(self, "Quick Slope", str(e))
            return
        self.project = p
        self.accept()
