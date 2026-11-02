"""Dialogs: start page, materials, analysis settings, project settings and result viewers."""
from __future__ import annotations

import copy
import math

from PySide6.QtCore import QPointF, QRectF, Qt, QThread, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QFormLayout, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton,
                               QSpinBox, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from .. import APP_NAME, __version__
from ..geometry import auto_entry_exit
from ..model import (ANALYSIS_KINDS, BC_KIND_OF, BC_KINDS, BC_TYPES, HYDRAULIC_MODELS, INTERSLICE_FUNCTIONS,
                     MATERIAL_COLORS, PWP_MODES, REINFORCEMENT_TYPES, SEARCH_MODES, SLOPE_METHODS, STRENGTH_MODELS,
                     STRESS_MODELS, UNIT_SYSTEMS, Material)

BC_KINDS_LABEL = {"hydraulic": "Hydraulic", "stress": "Stress", "thermal": "Thermal", "transport": "Transport",
                  "air": "Air"}


def dspin(value, lo=-1e9, hi=1e9, dec=3, step=1.0):
    s = QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setDecimals(dec)
    s.setSingleStep(step)
    s.setValue(value)
    return s


def ispin(value, lo=1, hi=100000):
    s = QSpinBox()
    s.setRange(lo, hi)
    s.setValue(value)
    return s


def combo(options: dict, current):
    c = QComboBox()
    for k, v in options.items():
        c.addItem(v, k)
    i = c.findData(current)
    c.setCurrentIndex(max(i, 0))
    return c


# ---------------------------------------------------------------------------
# Start page
# ---------------------------------------------------------------------------
class StartPage(QDialog):
    """Opening screen: create, open, examples, recent files and the AI builder."""

    def __init__(self, recent: list[str], examples: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} - Start")
        self.setMinimumSize(760, 460)
        self.choice = None
        root = QHBoxLayout(self)

        left = QVBoxLayout()
        title = QLabel(f"<span style='font-size:26pt;font-weight:600;color:#1d4e89'>{APP_NAME}</span>"
                       f"<br><span style='color:#555'>Geotechnical analysis suite &nbsp; v{__version__}</span>")
        left.addWidget(title)
        left.addSpacing(14)
        self.units = QComboBox()
        self.units.addItem("Metric (m, kN, kPa)", "metric")
        self.units.addItem("Imperial (ft, lbf, psf)", "imperial")
        row = QHBoxLayout()
        row.addWidget(QLabel("Units for new projects:"))
        row.addWidget(self.units)
        left.addLayout(row)
        self.kind = combo(ANALYSIS_KINDS, "slope")
        row = QHBoxLayout()
        row.addWidget(QLabel("Analysis type:"))
        row.addWidget(self.kind, 1)
        left.addLayout(row)
        for label, action in (("New project", "new"), ("Open project...", "open"), ("AI Slope Builder...", "ai")):
            b = QPushButton(label)
            b.setMinimumHeight(40)
            b.setStyleSheet("text-align:left;padding-left:14px;font-size:11pt")
            b.clicked.connect(lambda _=False, a=action: self.pick(a, self.kind.currentData() if a == "new" else None))
            left.addWidget(b)
        left.addStretch(1)
        root.addLayout(left, 1)

        right = QVBoxLayout()
        right.addWidget(QLabel("<b>Examples</b>"))
        self.ex_list = QListWidget()
        for e in examples:
            self.ex_list.addItem(e)
        self.ex_list.itemDoubleClicked.connect(lambda it: self.pick("example", it.text()))
        right.addWidget(self.ex_list)
        right.addWidget(QLabel("<b>Recent files</b>"))
        self.recent = QListWidget()
        for r in recent:
            self.recent.addItem(QListWidgetItem(r))
        self.recent.itemDoubleClicked.connect(lambda it: self.pick("recent", it.text()))
        right.addWidget(self.recent)
        root.addLayout(right, 1)

    def pick(self, action, arg=None):
        self.choice = (action, arg, self.units.currentData())
        self.accept()


# ---------------------------------------------------------------------------
# Project settings
# ---------------------------------------------------------------------------
class ProjectDialog(QDialog):
    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Project Properties")
        self.p = project
        f = QFormLayout(self)
        self.title = QLineEdit(project.title)
        self.author = QLineEdit(project.author)
        self.desc = QPlainTextEdit(project.description)
        self.desc.setMaximumHeight(90)
        self.units = combo({k: k.capitalize() for k in UNIT_SYSTEMS}, project.units)
        self.grid = dspin(project.grid_spacing, 1e-4, 1e6, 4, 0.5)
        f.addRow("Title", self.title)
        f.addRow("Author", self.author)
        f.addRow("Description", self.desc)
        f.addRow("Units", self.units)
        f.addRow("Grid spacing", self.grid)
        note = QLabel("Changing units relabels values; it does not convert them.")
        note.setStyleSheet("color:#666")
        f.addRow(note)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)

    def apply(self):
        self.p.title = self.title.text().strip() or "Untitled"
        self.p.author = self.author.text().strip()
        self.p.description = self.desc.toPlainText().strip()
        self.p.units = self.units.currentData()
        self.p.grid_spacing = self.grid.value()


# ---------------------------------------------------------------------------
# Generic forms
# ---------------------------------------------------------------------------
class Form(QWidget):
    """Form built from a field spec: (key, label, kind[, extra]).

    kinds: text, float, int, bool, choice (extra = {value: label}), color,
    table2 / table3 (extra = column names; values are lists of rows), unit fields take
    extra = unit key for the label suffix.
    """

    def __init__(self, spec, unit=None, parent=None):
        super().__init__(parent)
        self.spec = spec
        self.w = {}
        f = QFormLayout(self)
        for key, label, kind, *extra in spec:
            extra = extra[0] if extra else None
            if kind == "float" and isinstance(extra, str) and unit:
                label = f"{label} ({unit(extra)})"
            if kind == "text":
                w = QLineEdit()
            elif kind == "float":
                w = QLineEdit()
                w.setMaximumWidth(160)
            elif kind == "int":
                w = ispin(1, 0, 10_000_000)
            elif kind == "bool":
                w = QCheckBox(label)
            elif kind == "choice":
                w = combo(extra, None)
            elif kind == "color":
                w = QPushButton()
                w.clicked.connect(lambda _=False, b=w: self._pick(b))
            else:  # tables
                w = QPlainTextEdit()
                w.setMaximumHeight(110)
                w.setFont(QFont("Consolas", 9))
                w.setPlaceholderText(", ".join(extra or []) + "   (one row per line)")
            self.w[key] = w
            if kind == "bool":
                f.addRow(w)
            else:
                f.addRow(label, w)

    def _pick(self, b):
        col = QColorDialog.getColor(QColor(b.property("color") or "#ffffff"), self)
        if col.isValid():
            self._set_color(b, col.name())

    @staticmethod
    def _set_color(b, c):
        b.setProperty("color", c)
        b.setStyleSheet(f"background:{c}; min-width:60px")

    def load(self, obj):
        for key, label, kind, *extra in self.spec:
            w, val = self.w[key], getattr(obj, key)
            if kind in ("text",):
                w.setText(str(val))
            elif kind == "float":
                w.setText(f"{val:.6g}")
            elif kind == "int":
                w.setValue(int(val))
            elif kind == "bool":
                w.setChecked(bool(val))
            elif kind == "choice":
                w.setCurrentIndex(max(0, w.findData(val)))
            elif kind == "color":
                self._set_color(w, val)
            else:
                w.setPlainText("\n".join(", ".join(f"{x:g}" for x in row) for row in (val or [])))

    def store(self, obj, what=""):
        """Write widget values to obj. Raises ValueError with a readable message."""
        for key, label, kind, *extra in self.spec:
            w = self.w[key]
            if kind == "text":
                setattr(obj, key, w.text().strip())
            elif kind == "float":
                txt = w.text().strip()
                try:
                    setattr(obj, key, float(txt))
                except ValueError:
                    raise ValueError(f"{what}'{txt}' is not a number for {label}.")
            elif kind == "int":
                setattr(obj, key, w.value())
            elif kind == "bool":
                setattr(obj, key, w.isChecked())
            elif kind == "choice":
                setattr(obj, key, w.currentData())
            elif kind == "color":
                setattr(obj, key, w.property("color"))
            else:
                n = len(extra[0]) if extra else 2
                rows = []
                for line in w.toPlainText().splitlines():
                    parts = [p for p in line.replace(";", ",").replace("\t", ",").replace(" ", ",").split(",") if p]
                    if not parts:
                        continue
                    if len(parts) != n:
                        raise ValueError(f"{what}{label}: expected {n} numbers per line, got '{line}'.")
                    try:
                        rows.append([float(p) for p in parts])
                    except ValueError:
                        raise ValueError(f"{what}{label}: not a number in '{line}'.")
                setattr(obj, key, rows)


# ---------------------------------------------------------------------------
# Materials
# ---------------------------------------------------------------------------
DISTRIBUTIONS = {"normal": "Normal", "lognormal": "Lognormal", "uniform": "Uniform"}

MATERIAL_TABS = [
    ("Strength", [
        ("name", "Name", "text"), ("color", "Colour", "color"),
        ("model", "Strength model", "choice", STRENGTH_MODELS),
        ("unit_weight", "Unit weight", "float", "unit_weight"),
        ("cohesion", "Cohesion c' (or su)", "float", "pressure"), ("phi", "Friction angle phi' (deg)", "float"),
        ("phi_b", "Suction friction angle phi-b (deg)", "float"),
        ("c_rate", "su increase per unit depth", "float"), ("datum", "Datum for su increase", "float", "length"),
        ("shansep_s", "SHANSEP S", "float"), ("shansep_m", "SHANSEP m", "float"), ("ocr", "OCR", "float"),
        ("phi2", "Bilinear: phi above break (deg)", "float"), ("sigma_break", "Bilinear: break normal stress", "float", "pressure"),
        ("sn_table", "Shear / normal function", "table2", ["normal stress", "shear strength"]),
        ("sigci", "Hoek-Brown: intact UCS", "float", "pressure"), ("gsi", "Hoek-Brown: GSI", "float"),
        ("mi", "Hoek-Brown: mi", "float"), ("hb_d", "Hoek-Brown: disturbance D", "float"),
        ("cohesion_v", "Anisotropic: c on a vertical plane", "float", "pressure"),
        ("phi_v", "Anisotropic: phi on a vertical plane (deg)", "float")]),
    ("Probabilistic", [
        ("distribution", "Distribution", "choice", DISTRIBUTIONS),
        ("cohesion_sd", "Cohesion std dev", "float", "pressure"), ("phi_sd", "Phi std dev (deg)", "float"),
        ("unit_weight_sd", "Unit weight std dev", "float", "unit_weight")]),
    ("Hydraulic", [
        ("hyd_model", "Hydraulic model", "choice", HYDRAULIC_MODELS),
        ("k_sat", "Saturated conductivity", "float", "k"), ("k_ratio", "Anisotropy ky/kx", "float"),
        ("theta_s", "Saturated water content", "float"), ("theta_r", "Residual water content", "float"),
        ("unsat_alpha", "Gardner alpha (1/length)", "float"), ("vg_alpha", "van Genuchten alpha (1/length)", "float"),
        ("vg_n", "van Genuchten n", "float"), ("mv", "Compressibility mv", "float", "compressibility")]),
    ("Stress", [
        ("stress_model", "Stress-strain model", "choice", STRESS_MODELS),
        ("E", "Young's modulus E'", "float", "modulus"), ("nu", "Poisson's ratio", "float"),
        ("psi", "Dilation angle (deg)", "float"), ("k0", "K0 (0 = nu / (1 - nu))", "float")]),
    ("Dynamic", [
        ("damping", "Damping ratio (small strain)", "float"),
        ("gamma_ref", "Reference shear strain (0 = linear)", "float"), ("damping_max", "Maximum damping ratio", "float")]),
    ("Thermal", [
        ("th_k", "Unfrozen thermal conductivity", "float", "conductivity_th"),
        ("th_k_frozen", "Frozen thermal conductivity", "float", "conductivity_th"),
        ("th_c", "Unfrozen volumetric heat capacity", "float", "heat_capacity"),
        ("th_c_frozen", "Frozen volumetric heat capacity", "float", "heat_capacity"),
        ("th_water", "Volumetric water content (latent heat)", "float"),
        ("th_freeze_range", "Freezing range below 0", "float", "temperature")]),
    ("Transport", [
        ("disp_l", "Longitudinal dispersivity", "float", "length"), ("disp_t", "Transverse dispersivity", "float", "length"),
        ("diffusion", "Molecular diffusion (length²/s)", "float"), ("kd", "Adsorption Kd (volume/mass)", "float"),
        ("dry_density", "Dry density (mass/volume)", "float"), ("half_life", "Decay half-life (s, 0 = none)", "float")]),
    ("Air", [("k_air", "Dry-soil air conductivity", "float", "k")]),
]


def validate_material(m: Material):
    if m.unit_weight <= 0:
        raise ValueError(f"{m.name}: unit weight must be positive.")
    if m.cohesion < 0 or not 0 <= m.phi < 90:
        raise ValueError(f"{m.name}: cohesion must be >= 0 and phi between 0 and 90 degrees.")
    if min(m.cohesion_sd, m.phi_sd, m.unit_weight_sd) < 0:
        raise ValueError(f"{m.name}: standard deviations cannot be negative.")
    if m.k_sat <= 0 or m.k_ratio <= 0:
        raise ValueError(f"{m.name}: k sat and ky/kx must be positive.")
    if not 0 <= m.theta_r < m.theta_s <= 1:
        raise ValueError(f"{m.name}: water contents need 0 <= residual < saturated <= 1.")
    if m.E <= 0 or not -1 < m.nu < 0.5:
        raise ValueError(f"{m.name}: E must be positive and Poisson's ratio below 0.5.")
    if m.model == "hoek_brown" and (m.sigci <= 0 or m.mi <= 0 or not 0 <= m.hb_d <= 1):
        raise ValueError(f"{m.name}: Hoek-Brown needs UCS > 0, mi > 0 and 0 <= D <= 1.")
    if m.model == "shear_normal" and len(m.sn_table) < 2:
        raise ValueError(f"{m.name}: a shear / normal function needs at least two points.")
    if min(m.th_k, m.th_k_frozen, m.th_c, m.th_c_frozen) <= 0:
        raise ValueError(f"{m.name}: thermal conductivities and heat capacities must be positive.")


class MaterialsDialog(QDialog):
    """Material list with tabbed property pages (strength, hydraulic, stress, thermal, ...)."""

    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Define Materials")
        self.resize(900, 620)
        self.p = project
        self.mats = copy.deepcopy(project.materials)
        root = QHBoxLayout(self)
        left = QVBoxLayout()
        self.list = QListWidget()
        self.list.setMaximumWidth(220)
        left.addWidget(self.list)
        row = QHBoxLayout()
        add = QPushButton("Add")
        add.clicked.connect(self.add)
        dup = QPushButton("Copy")
        dup.clicked.connect(self.duplicate)
        dele = QPushButton("Delete")
        dele.clicked.connect(self.delete)
        for b in (add, dup, dele):
            row.addWidget(b)
        left.addLayout(row)
        root.addLayout(left)
        right = QVBoxLayout()
        self.tabs = QTabWidget()
        self.forms = []
        self.fields = {}
        for title, spec in MATERIAL_TABS:
            form = Form(spec, project.unit)
            self.forms.append(form)
            self.fields.update(form.w)
            from PySide6.QtWidgets import QScrollArea
            sc = QScrollArea()
            sc.setWidgetResizable(True)
            sc.setWidget(form)
            self.tabs.addTab(sc, title)
        right.addWidget(self.tabs)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.try_accept)
        bb.rejected.connect(self.reject)
        right.addWidget(bb)
        root.addLayout(right, 1)
        self.cur = None
        for m in self.mats:
            self.list.addItem(m.name)
        self.list.currentRowChanged.connect(self.select)
        if self.mats:
            self.list.setCurrentRow(0)

    def _flush(self):
        """Write the form back into the current material (raises ValueError)."""
        if self.cur is None or self.cur >= len(self.mats):
            return
        m = self.mats[self.cur]
        for form in self.forms:
            form.store(m, f"{m.name}: ")
        m.name = m.name or f"Soil {m.id}"
        self.list.item(self.cur).setText(m.name)

    def select(self, row):
        if row == self.cur:
            return
        try:
            self._flush()
        except ValueError as e:
            QMessageBox.warning(self, "Invalid input", str(e))
            self.list.blockSignals(True)
            self.list.setCurrentRow(self.cur)
            self.list.blockSignals(False)
            return
        self.cur = row
        if 0 <= row < len(self.mats):
            for form in self.forms:
                form.load(self.mats[row])

    def add(self, base: Material | None = None):
        try:
            self._flush()
        except ValueError as e:
            QMessageBox.warning(self, "Invalid input", str(e))
            return
        mid = max([m.id for m in self.mats] + [0]) + 1
        if base is not None:
            m = copy.deepcopy(base)
            m.id, m.name = mid, f"{base.name} (copy)"
        else:
            m = Material(id=mid, name=f"Soil {mid}")
        m.color = MATERIAL_COLORS[(mid - 1) % len(MATERIAL_COLORS)]
        self.mats.append(m)
        self.list.addItem(m.name)
        self.cur = None
        self.list.setCurrentRow(len(self.mats) - 1)
        self.select(len(self.mats) - 1)

    def duplicate(self):
        if self.cur is not None and self.cur < len(self.mats):
            self.add(self.mats[self.cur])

    def delete(self):
        r = self.list.currentRow()
        if r < 0:
            return
        mid = self.mats[r].id
        used = [reg.id for reg in self.p.regions if reg.material_id == mid]
        if used:
            QMessageBox.warning(self, "In use", f"This material is assigned to region(s) {used}. "
                                "Assign another material first.")
            return
        self.cur = None
        del self.mats[r]
        self.list.blockSignals(True)
        self.list.takeItem(r)
        self.list.blockSignals(False)
        if self.mats:
            self.list.setCurrentRow(min(r, len(self.mats) - 1))
            self.select(min(r, len(self.mats) - 1))

    def collect(self) -> list[Material]:
        self._flush()
        if not self.mats:
            raise ValueError("Define at least one material.")
        for m in self.mats:
            validate_material(m)
        return copy.deepcopy(self.mats)

    def try_accept(self):
        try:
            self.result_mats = self.collect()
        except ValueError as e:
            QMessageBox.warning(self, "Invalid input", str(e))
            return
        self.accept()


# ---------------------------------------------------------------------------
# Analysis settings
# ---------------------------------------------------------------------------
INITIAL = {"parent": "From parent analysis", "water_table": "Water table (piezometric line)", "value": "Uniform value"}
STRESS_TYPES = {"insitu": "In situ (gravity)", "load": "Load-deformation", "consolidation": "Coupled consolidation"}
TIME = [("transient", "Transient (time-dependent)", "bool"), ("duration", "Duration (s)", "float"),
        ("n_steps", "Number of time steps", "int"), ("step_growth", "Time step growth ratio", "float")]

KIND_TABS = {
    "seepage": [("Seepage", [("mesh_size", "Mesh element size", "float", "length"),
                             ("unsaturated", "Include unsaturated flow (free phreatic surface)", "bool"),
                             *TIME, ("initial", "Initial conditions", "choice", INITIAL),
                             ("initial_value", "Initial total head", "float", "length"),
                             ("max_iter", "Max iterations per step", "int"), ("tolerance", "Head tolerance", "float")])],
    "stress": [("Stress", [("stress_type", "Analysis type", "choice", STRESS_TYPES),
                           ("mesh_size", "Mesh element size", "float", "length"),
                           ("pwp", "Pore-water pressure", "choice", {k: v for k, v in PWP_MODES.items() if k != "ru"}),
                           ("load_steps", "Load steps", "int"),
                           ("srm", "Compute strength reduction factor of safety (in situ)", "bool"),
                           ("max_iter", "Max plastic iterations", "int"),
                           ("duration", "Consolidation duration (s)", "float"),
                           ("n_steps", "Consolidation time steps", "int"),
                           ("step_growth", "Time step growth ratio", "float")])],
    "dynamic": [("Dynamic", [("mesh_size", "Mesh element size", "float", "length"), ("dt", "Time step (s)", "float"),
                             ("equivalent_linear", "Equivalent linear (strain-dependent G and damping)", "bool"),
                             ("n_eq_iter", "Equivalent linear iterations", "int"),
                             ("motion", "Input acceleration", "table2", ["time (s)", "acceleration (g)"])])],
    "thermal": [("Thermal", [("mesh_size", "Mesh element size", "float", "length"), *TIME,
                             ("initial", "Initial conditions", "choice", {k: v for k, v in INITIAL.items() if k != "water_table"}),
                             ("initial_value", "Initial temperature", "float", "temperature"),
                             ("max_iter", "Max iterations per step", "int"), ("tolerance", "Temperature tolerance", "float")])],
    "transport": [("Transport", [("duration", "Duration (s)", "float"), ("n_steps", "Number of time steps", "int"),
                                 ("step_growth", "Time step growth ratio", "float"),
                                 ("initial_value", "Initial concentration", "float", "concentration"),
                                 ("particles", "Particle tracking start points", "table2", ["x", "y"])])],
    "air": [("Air Flow", [("mesh_size", "Mesh element size", "float", "length"), *TIME,
                          ("initial_value", "Initial air pressure", "float", "pressure"),
                          ("max_iter", "Max iterations per step", "int"), ("tolerance", "Pressure tolerance", "float")])],
}

SLOPE_EXTRA = [("Loads and Cracks", [
    ("kh", "Horizontal seismic coefficient kh", "float"), ("kv", "Vertical seismic coefficient kv (down +)", "float"),
    ("tension_crack_depth", "Tension crack depth (0 = none)", "float", "length"),
    ("tension_crack_angle", "Tension crack where base steeper than (deg, 0 = off)", "float"),
    ("crack_water", "Fraction of crack filled with water", "float"),
    ("optimize", "Optimize the critical slip surface (non-circular)", "bool"),
    ("opt_iterations", "Optimization trials", "int")])]


class AnalysisDialog(QDialog):
    def __init__(self, project, analysis, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Analysis Settings - {analysis.name}")
        self.resize(640, 640)
        self.p, self.a = project, analysis
        a = analysis
        v = QVBoxLayout(self)
        tabs = QTabWidget()
        v.addWidget(tabs)

        g = QWidget(); f = QFormLayout(g)
        self.name = QLineEdit(a.name)
        self.desc = QLineEdit(a.description)
        self.parent_cb = QComboBox()
        self.parent_cb.addItem("(none)", None)
        banned = self._descendants(a.id) | {a.id}
        for o in project.analyses:
            if o.id not in banned:
                self.parent_cb.addItem(f"{o.name}  [{ANALYSIS_KINDS[o.kind].split(' (')[0]}]", o.id)
        self.parent_cb.setCurrentIndex(max(0, self.parent_cb.findData(a.parent_id)))
        f.addRow("Name", self.name)
        f.addRow("Type", QLabel(ANALYSIS_KINDS.get(a.kind, a.kind)))
        f.addRow("Description", self.desc)
        f.addRow("Parent analysis", self.parent_cb)
        hint = QLabel("Children use their parents' results: seepage gives pore pressures and flow, "
                      "stress gives stresses for the finite element slope method, dynamic gives Newmark "
                      "displacements, and earlier steps give initial conditions.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#555")
        f.addRow(hint)
        tabs.addTab(g, "General")
        self.forms = []

        if a.kind == "slope":
            self._slope_tabs(tabs)
        for title, spec in KIND_TABS.get(a.kind, []) + (SLOPE_EXTRA if a.kind == "slope" else []):
            form = Form(spec, project.unit)
            form.load(a)
            self.forms.append(form)
            tabs.addTab(form, title)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.try_accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def _descendants(self, aid):
        out, changed = set(), True
        while changed:
            changed = False
            for o in self.p.analyses:
                if (o.parent_id == aid or o.parent_id in out) and o.id not in out:
                    out.add(o.id)
                    changed = True
        return out

    def _slope_tabs(self, tabs):
        a, project = self.a, self.p
        t = QWidget(); f = QFormLayout(t)
        self.method = combo(SLOPE_METHODS, a.method)
        self.inter = combo(INTERSLICE_FUNCTIONS, a.interslice)
        self.inter_pts = QPlainTextEdit("\n".join(f"{x:g}, {y:g}" for x, y in a.interslice_points))
        self.inter_pts.setMaximumHeight(60)
        self.inter_pts.setPlaceholderText("x/L, f(x)  per line (for 'Data points')")
        self.nsl = ispin(a.n_slices, 5, 500)
        self.pwp = combo(PWP_MODES, a.pwp)
        self.ru = dspin(a.ru, 0, 1, 3, 0.05)
        f.addRow("Method", self.method)
        f.addRow("Interslice function (M-P)", self.inter)
        f.addRow("Interslice data points", self.inter_pts)
        f.addRow("Number of slices", self.nsl)
        f.addRow("Pore-water pressure", self.pwp)
        f.addRow("Ru", self.ru)
        tabs.addTab(t, "Slope Stability")

        s = a.search
        t = QWidget(); grid = QGridLayout(t)
        self.mode = combo(SEARCH_MODES, s.mode)
        grid.addWidget(QLabel("Slip surface"), 0, 0); grid.addWidget(self.mode, 0, 1, 1, 3)
        self.sf = {}
        fields = [("entry_x1", "Entry x from"), ("entry_x2", "Entry x to"), ("exit_x1", "Exit x from"),
                  ("exit_x2", "Exit x to"), ("n_entry", "Entry increments"), ("n_exit", "Exit increments"),
                  ("n_radius", "Radius increments"), ("min_depth", "Minimum slip depth"),
                  ("grid_x1", "Grid x1"), ("grid_y1", "Grid y1"), ("grid_x2", "Grid x2"), ("grid_y2", "Grid y2"),
                  ("grid_nx", "Grid x increments"), ("grid_ny", "Grid y increments"),
                  ("radius_min", "Radius min"), ("radius_max", "Radius max"), ("n_radii", "Radius increments (grid)"),
                  ("n_tangent", "Tangent line increments"), ("tangent_y1", "Tangent lines y from"),
                  ("tangent_y2", "Tangent lines y to"), ("block_n", "Block grid increments"),
                  ("block_angle_left", "Block left projection angle"), ("block_angle_right", "Block right projection angle")]
        for i, (key, label) in enumerate(fields):
            val = getattr(s, key)
            w = ispin(val, 1, 500) if isinstance(val, int) else dspin(val, -1e7, 1e7, 3)
            self.sf[key] = w
            grid.addWidget(QLabel(label), 1 + i // 2, (i % 2) * 2)
            grid.addWidget(w, 1 + i // 2, (i % 2) * 2 + 1)
        r = 2 + len(fields) // 2
        self.blocks = QLineEdit("  ".join(", ".join(f"{v:g}" for v in b) for b in (s.block_left, s.block_right)))
        grid.addWidget(QLabel("Block grids: left x1,y1,x2,y2  right x1,y1,x2,y2"), r, 0, 1, 2)
        grid.addWidget(self.blocks, r, 2, 1, 2)
        grid.addWidget(QLabel("Fully specified circles (xc, yc, R per line)"), r + 1, 0, 1, 4)
        self.circles = QPlainTextEdit("\n".join(", ".join(f"{v:g}" for v in c[:3]) for c in s.circles))
        self.circles.setMaximumHeight(60)
        grid.addWidget(self.circles, r + 2, 0, 1, 4)
        grid.addWidget(QLabel("Fully specified polyline (x, y per line; blank line separates surfaces)"), r + 3, 0, 1, 4)
        self.polys = QPlainTextEdit("\n\n".join("\n".join(f"{x:g}, {y:g}" for x, y in pl) for pl in s.polylines))
        self.polys.setMaximumHeight(60)
        grid.addWidget(self.polys, r + 4, 0, 1, 4)
        auto = QPushButton("Auto entry/exit from geometry")
        auto.clicked.connect(self.auto)
        grid.addWidget(auto, r + 5, 0, 1, 2)
        tabs.addTab(t, "Slip Surface")

        t = QWidget(); f = QFormLayout(t)
        self.prob = QCheckBox("Run Monte Carlo on the critical slip surface")
        self.prob.setChecked(a.probabilistic)
        self.ns = ispin(a.n_samples, 10, 100000)
        self.seed = ispin(a.seed, 0, 2 ** 31 - 1)
        f.addRow(self.prob)
        f.addRow("Number of samples", self.ns)
        f.addRow("Random seed", self.seed)
        self.sens = QComboBox()
        self.sens.addItem("(none)", "")
        for m in project.materials:
            for prop, lab in (("cohesion", "cohesion"), ("phi", "phi"), ("unit_weight", "unit weight")):
                self.sens.addItem(f"{m.name}: {lab}", f"{m.id}:{prop}")
        self.sens.setCurrentIndex(max(0, self.sens.findData(a.sensitivity_param)))
        self.slo = dspin(a.sensitivity_low, -1e6, 1e6)
        self.shi = dspin(a.sensitivity_high, -1e6, 1e6)
        self.sst = ispin(a.sensitivity_steps, 2, 200)
        f.addRow(QLabel("<b>Sensitivity</b>"))
        f.addRow("Parameter", self.sens)
        f.addRow("From", self.slo)
        f.addRow("To", self.shi)
        f.addRow("Steps", self.sst)
        tabs.addTab(t, "Probabilistic / Sensitivity")

    def auto(self):
        if not self.p.regions:
            return
        (e1, e2), (x1, x2) = auto_entry_exit(self.p)
        for k, val in (("entry_x1", e1), ("entry_x2", e2), ("exit_x1", x1), ("exit_x2", x2)):
            self.sf[k].setValue(val)
        self.mode.setCurrentIndex(self.mode.findData("entry_exit"))

    @staticmethod
    def _parse_rows(text, n):
        rows = []
        for line in text.splitlines():
            if not line.strip():
                rows.append(None)
                continue
            parts = [p for p in line.replace(";", ",").replace("\t", ",").split(",") if p.strip()]
            if len(parts) != n:
                raise ValueError(f"Expected {n} numbers per line: '{line}'")
            rows.append([float(p) for p in parts])
        return rows

    def try_accept(self):
        a = copy.deepcopy(self.a)
        try:
            a.name = self.name.text().strip() or a.name
            a.description = self.desc.text().strip()
            a.parent_id = self.parent_cb.currentData()
            if a.kind == "slope":
                self._store_slope(a)
            for form in self.forms:
                form.store(a)
            parent = self.p.analysis(a.parent_id)
            if a.kind == "transport" and (parent is None or parent.kind != "seepage"):
                raise ValueError("Contaminant transport needs a seepage analysis as its parent.")
            if a.kind in ("seepage", "thermal", "air") and a.transient and (a.duration <= 0 or a.n_steps < 1):
                raise ValueError("A transient analysis needs a positive duration and at least one time step.")
            if a.kind == "dynamic" and (len(a.motion) < 2 or a.dt <= 0):
                raise ValueError("Enter at least two rows of input acceleration and a positive time step.")
            if getattr(a, "mesh_size", 1) <= 0:
                raise ValueError("Mesh size must be positive.")
        except ValueError as e:
            QMessageBox.warning(self, "Invalid input", str(e))
            return
        self.a.__dict__.update(a.__dict__)
        self.accept()

    def _store_slope(self, a):
        circles = [r for r in self._parse_rows(self.circles.toPlainText(), 3) if r]
        for c in circles:
            if c[2] <= 0:
                raise ValueError("Circle radius must be positive.")
        polys, cur = [], []
        for r in self._parse_rows(self.polys.toPlainText(), 2):
            if r is None:
                if cur:
                    polys.append(cur)
                cur = []
            else:
                cur.append(r)
        if cur:
            polys.append(cur)
        if any(len(pl) < 2 for pl in polys):
            raise ValueError("Each polyline slip surface needs at least two points.")
        nums = [float(x) for x in self.blocks.text().replace(",", " ").split()] if self.blocks.text().strip() else []
        if nums and len(nums) != 8:
            raise ValueError("Block grids need 8 numbers: left x1 y1 x2 y2, right x1 y1 x2 y2.")
        if self.pwp.currentData() == "seepage" and self.parent_cb.currentData() is None:
            raise ValueError("Pore pressure 'From seepage analysis' needs a parent seepage analysis.")
        a.method = self.method.currentData()
        a.interslice = self.inter.currentData()
        a.interslice_points = [r for r in self._parse_rows(self.inter_pts.toPlainText(), 2) if r]
        a.n_slices = self.nsl.value()
        a.pwp = self.pwp.currentData()
        a.ru = self.ru.value()
        s = a.search
        s.mode = self.mode.currentData()
        for k, w in self.sf.items():
            setattr(s, k, w.value())
        if nums:
            s.block_left, s.block_right = nums[:4], nums[4:]
        s.circles = circles
        s.polylines = polys
        a.probabilistic = self.prob.isChecked()
        a.n_samples = self.ns.value()
        a.seed = self.seed.value()
        a.sensitivity_param = self.sens.currentData()
        a.sensitivity_low, a.sensitivity_high = self.slo.value(), self.shi.value()
        a.sensitivity_steps = self.sst.value()


# ---------------------------------------------------------------------------
# Small editors
# ---------------------------------------------------------------------------
BC_HELP = {
    "hydraulic": "Head / pressure head in length units; unit flux per unit length per second (inflow +).",
    "stress": "Pressure and shear in pressure units (compression +); forces are totals shared by the nodes; "
              "displacement in length units.",
    "thermal": "Temperature; heat flux per unit area (into the ground +); convective: value = h, second "
               "value = ambient temperature.",
    "transport": "Concentration; mass flux per unit length (inflow +).",
    "air": "Gauge air pressure; air flux per unit length (inflow +).",
}


class BCDialog(QDialog):
    def __init__(self, name="BC", type_="head", value=0.0, parent=None, kinds=None, value2=0.0, fn=None,
                 analyses=None, project=None):
        super().__init__(parent)
        self.setWindowTitle("Boundary Condition")
        f = QFormLayout(self)
        self.name = QLineEdit(name)
        groups = kinds or list(BC_KINDS)
        opts = {k: f"{BC_KINDS_LABEL[g]}: {v}" for g in groups for k, v in BC_KINDS[g].items()}
        self.type = combo(opts, type_)
        self.value = dspin(value, -1e12, 1e12, 6)
        self.value2 = dspin(value2, -1e12, 1e12, 6)
        self.fn = QPlainTextEdit("\n".join(f"{t:g}, {v:g}" for t, v in (fn or [])))
        self.fn.setMaximumHeight(80)
        self.fn.setPlaceholderText("time (s), value  per line - leave empty for a constant value")
        self.only = QComboBox()
        self.only.addItem("All analyses", None)
        for a in (project.analyses if project else []):
            self.only.addItem(f"Only: {a.name}", a.id)
        if analyses:
            self.only.setCurrentIndex(max(0, self.only.findData(analyses[0])))
        f.addRow("Name", self.name)
        f.addRow("Type", self.type)
        f.addRow("Value", self.value)
        f.addRow("Second value", self.value2)
        f.addRow("Value vs time", self.fn)
        f.addRow("Applies to", self.only)
        self.help = QLabel()
        self.help.setWordWrap(True)
        self.help.setStyleSheet("color:#555")
        f.addRow(self.help)
        self.type.currentIndexChanged.connect(self._help)
        self._help()
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.try_accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)

    def _help(self):
        self.help.setText(BC_HELP.get(BC_KIND_OF.get(self.type.currentData(), "hydraulic"), ""))

    def try_accept(self):
        try:
            self.fn_rows = [r for r in AnalysisDialog._parse_rows(self.fn.toPlainText(), 2) if r]
        except ValueError as e:
            QMessageBox.warning(self, "Invalid input", str(e))
            return
        self.accept()

    def params(self):
        only = self.only.currentData()
        return dict(name=self.name.text().strip() or "BC", type=self.type.currentData(), value=self.value.value(),
                    value2=self.value2.value(), fn=getattr(self, "fn_rows", []), analyses=[only] if only else [])


class ReinforcementDialog(QDialog):
    def __init__(self, r=None, parent=None, unit=None):
        super().__init__(parent)
        self.setWindowTitle("Reinforcement")
        from ..model import Reinforcement
        self.r = copy.deepcopy(r) if r else Reinforcement(id=0, type="nail", x1=0, y1=0, x2=0, y2=0)
        spec = [("type", "Type", "choice", REINFORCEMENT_TYPES),
                ("capacity", "Tensile (pile: shear) capacity", "float", "force"),
                ("bond", "Pullout resistance per length", "float"), ("bond_length", "Anchor bonded length", "float", "length"),
                ("spacing", "Out-of-plane spacing", "float", "length"),
                ("f_dependent", "Divide force by the factor of safety (F of S dependent)", "bool")]
        v = QVBoxLayout(self)
        self.form = Form(spec, unit)
        self.form.load(self.r)
        v.addWidget(self.form)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.try_accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def try_accept(self):
        try:
            self.form.store(self.r)
            if self.r.spacing <= 0 or self.r.capacity < 0 or self.r.bond < 0:
                raise ValueError("Spacing must be positive; capacity and pullout resistance cannot be negative.")
        except ValueError as e:
            QMessageBox.warning(self, "Invalid input", str(e))
            return
        self.accept()


class PointsDialog(QDialog):
    """Keyboard / paste entry of a list of points."""

    def __init__(self, title, points=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(360, 420)
        v = QVBoxLayout(self)
        v.addWidget(QLabel("One point per line: x, y  (comma, tab or space separated)"))
        self.text = QPlainTextEdit("\n".join(f"{x:g}, {y:g}" for x, y in (points or [])))
        self.text.setFont(QFont("Consolas", 10))
        v.addWidget(self.text)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.try_accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self.points = []

    def try_accept(self):
        pts = []
        for line in self.text.toPlainText().splitlines():
            parts = line.replace(",", " ").replace(";", " ").split()
            if not parts:
                continue
            if len(parts) != 2:
                QMessageBox.warning(self, "Invalid input", f"Expected two numbers: '{line}'")
                return
            try:
                pts.append([float(parts[0]), float(parts[1])])
            except ValueError:
                QMessageBox.warning(self, "Invalid input", f"Not a number: '{line}'")
                return
        self.points = pts
        self.accept()


class TextDialog(QDialog):
    """Read-only text (reports) with copy and save."""

    def __init__(self, title, text, parent=None, save_cb=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(820, 620)
        v = QVBoxLayout(self)
        self.edit = QPlainTextEdit(text)
        self.edit.setReadOnly(True)
        self.edit.setFont(QFont("Consolas", 9))
        v.addWidget(self.edit)
        row = QHBoxLayout()
        if save_cb:
            b = QPushButton("Save...")
            b.clicked.connect(save_cb)
            row.addWidget(b)
        c = QPushButton("Copy")
        c.clicked.connect(lambda: (self.edit.selectAll(), self.edit.copy()))
        row.addWidget(c)
        row.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        v.addLayout(row)


class SliceTable(QDialog):
    def __init__(self, rows, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Slice Information")
        self.resize(1000, 480)
        v = QVBoxLayout(self)
        keys = list(rows[0].keys())
        t = QTableWidget(len(rows), len(keys))
        t.setHorizontalHeaderLabels(keys)
        for i, r in enumerate(rows):
            for j, k in enumerate(keys):
                val = r[k]
                t.setItem(i, j, QTableWidgetItem(f"{val:.4g}" if isinstance(val, float) else str(val)))
        t.setEditTriggers(QTableWidget.NoEditTriggers)
        v.addWidget(t)


# ---------------------------------------------------------------------------
# Graphs
# ---------------------------------------------------------------------------
class GraphWidget(QWidget):
    def __init__(self, xs, ys, xlabel, ylabel, bars=False):
        super().__init__()
        self.xs, self.ys, self.xl, self.yl, self.bars = xs, ys, xlabel, ylabel, bars
        self.setMinimumSize(520, 340)

    def paintEvent(self, e):
        g = QPainter(self)
        g.setRenderHint(QPainter.Antialiasing)
        g.fillRect(self.rect(), QColor("white"))
        pts = [(x, y) for x, y in zip(self.xs, self.ys) if y is not None and math.isfinite(y)]
        if not pts:
            g.drawText(self.rect(), Qt.AlignCenter, "No data")
            return
        L, T, R, B = 70, 20, self.width() - 20, self.height() - 50
        x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts)
        y0, y1 = min(p[1] for p in pts), max(p[1] for p in pts)
        if self.bars:
            y0 = 0
        if x1 == x0:
            x1 += 1
        if y1 == y0:
            y1 += 1
        y0, y1 = y0 - 0.05 * (y1 - y0) * (not self.bars), y1 + 0.05 * (y1 - y0)
        X = lambda x: L + (x - x0) / (x1 - x0) * (R - L)
        Y = lambda y: B - (y - y0) / (y1 - y0) * (B - T)
        g.setPen(QPen(QColor("#333"), 1))
        g.drawRect(QRectF(L, T, R - L, B - T))
        g.setFont(QFont("Segoe UI", 8))
        for k in range(6):
            yv = y0 + k * (y1 - y0) / 5
            g.drawText(QRectF(0, Y(yv) - 8, L - 6, 16), Qt.AlignRight | Qt.AlignVCenter, f"{yv:.3g}")
            xv = x0 + k * (x1 - x0) / 5
            g.drawText(QRectF(X(xv) - 40, B + 4, 80, 16), Qt.AlignCenter, f"{xv:.3g}")
        g.drawText(QRectF(L, B + 22, R - L, 18), Qt.AlignCenter, self.xl)
        g.save()
        g.translate(14, (T + B) / 2)
        g.rotate(-90)
        g.drawText(QRectF(-100, -10, 200, 20), Qt.AlignCenter, self.yl)
        g.restore()
        if self.bars:
            w = (R - L) / max(len(pts), 1) * 0.9
            g.setBrush(QColor("#4c7fd1"))
            for x, y in pts:
                g.drawRect(QRectF(X(x) - w / 2, Y(y), w, B - Y(y)))
        else:
            g.setPen(QPen(QColor("#c01010"), 2))
            for (xa, ya), (xb, yb) in zip(pts, pts[1:]):
                g.drawLine(QPointF(X(xa), Y(ya)), QPointF(X(xb), Y(yb)))
            g.setBrush(QColor("#c01010"))
            for x, y in pts:
                g.drawEllipse(QPointF(X(x), Y(y)), 3, 3)


class GraphDialog(QDialog):
    def __init__(self, title, xs, ys, xlabel, ylabel, bars=False, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        v = QVBoxLayout(self)
        v.addWidget(GraphWidget(xs, ys, xlabel, ylabel, bars))


# ---------------------------------------------------------------------------
# AI builder
# ---------------------------------------------------------------------------
class _AIWorker(QThread):
    done = Signal(object, str, str)  # project, assumptions, error

    def __init__(self, prompt, key):
        super().__init__()
        self.prompt, self.key = prompt, key

    def run(self):
        from ..ai import AIError, generate_project
        try:
            p, notes = generate_project(self.prompt, self.key or None)
            self.done.emit(p, notes, "")
        except AIError as e:
            self.done.emit(None, "", str(e))
        except Exception as e:  # unexpected: surface it rather than crash the UI
            self.done.emit(None, "", f"Unexpected error: {e}")


class AIDialog(QDialog):
    EXAMPLE = ("A 12 m high cut slope at 1.5H:1V in stiff clay (c' = 10 kPa, phi' = 25 deg, 19 kN/m3) "
               "over dense sand. Water table 3 m below the crest, daylighting at the toe. "
               "A 20 kPa traffic load near the crest.")

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI Slope Builder")
        self.resize(640, 440)
        self.settings = settings
        self.project = None
        v = QVBoxLayout(self)
        v.addWidget(QLabel("Describe the slope: geometry, soil layers and strengths, groundwater and loads. "
                           "Claude sets up the regions, materials, water table and slip surface search."))
        self.prompt = QPlainTextEdit()
        self.prompt.setPlaceholderText(self.EXAMPLE)
        v.addWidget(self.prompt)
        f = QFormLayout()
        self.key = QLineEdit(settings.value("ai/api_key", "") or "")
        self.key.setEchoMode(QLineEdit.Password)
        self.key.setPlaceholderText("Uses ANTHROPIC_API_KEY if empty")
        self.remember = QCheckBox("Remember key on this computer")
        self.remember.setChecked(bool(self.key.text()))
        f.addRow("Anthropic API key", self.key)
        f.addRow("", self.remember)
        v.addLayout(f)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        v.addWidget(self.status)
        row = QHBoxLayout()
        ex = QPushButton("Use example")
        ex.clicked.connect(lambda: self.prompt.setPlainText(self.EXAMPLE))
        row.addWidget(ex)
        row.addStretch(1)
        self.go = QPushButton("Generate")
        self.go.setDefault(True)
        self.go.clicked.connect(self.generate)
        row.addWidget(self.go)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        v.addLayout(row)
        self.worker = None

    def generate(self):
        text = self.prompt.toPlainText().strip()
        if not text:
            self.status.setText("Describe the slope first (or click 'Use example').")
            return
        if self.remember.isChecked():
            self.settings.setValue("ai/api_key", self.key.text().strip())
        else:
            self.settings.remove("ai/api_key")
        self.go.setEnabled(False)
        self.status.setText("Generating model... this can take up to a minute.")
        self.worker = _AIWorker(text, self.key.text().strip())
        self.worker.done.connect(self.finished_ai)
        self.worker.start()

    def finished_ai(self, project, notes, err):
        self.go.setEnabled(True)
        if err:
            self.status.setText(f"<span style='color:#b00000'>{err}</span>")
            return
        self.project, self.notes = project, notes
        self.accept()
