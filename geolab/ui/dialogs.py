"""Dialogs: materials, analysis settings, project settings and result viewers."""
from __future__ import annotations

import copy
import math

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QThread, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QFormLayout, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QListWidget, QMenu, QMessageBox, QPlainTextEdit, QPushButton,
                               QScrollArea, QSpinBox, QStackedWidget, QStyle, QTableWidget, QTableWidgetItem, QTabWidget,
                               QTreeWidget, QTreeWidgetItem, QTreeWidgetItemIterator, QVBoxLayout, QWidget)

from .theme import ui_font
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
        self.convert = QCheckBox("Convert all values when the unit system changes (m <-> ft, kPa <-> psf ...)")
        self.convert.setChecked(True)
        f.addRow(self.convert)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)

    def apply(self):
        self.p.title = self.title.text().strip() or "Untitled"
        self.p.author = self.author.text().strip()
        self.p.description = self.desc.toPlainText().strip()
        new = self.units.currentData()
        self.p.grid_spacing = self.grid.value()
        self.not_converted = []
        if new != self.p.units and self.convert.isChecked():
            from ..units import convert_project
            self.not_converted = convert_project(self.p, new)
        self.p.units = new


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
        ("phi_v", "Anisotropic: phi on a vertical plane (deg)", "float"),
        ("cr", "Rapid drawdown: R envelope c_R (CU tests; 0 and 0 = free draining)", "float", "pressure"),
        ("phi_r", "Rapid drawdown: R envelope phi_R (deg)", "float")]),
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
        ("psi", "Dilation angle (deg)", "float"), ("k0", "K0 (0 = nu / (1 - nu))", "float"),
        ("cc_lambda", "Cam Clay: lambda (NCL slope, e vs ln p')", "float"),
        ("cc_kappa", "Cam Clay: kappa (unload-reload slope)", "float"),
        ("e0", "Cam Clay: initial void ratio", "float"),
        ("ocr", "Cam Clay / SHANSEP: overconsolidation ratio", "float"),
        ("dc_K", "Hyperbolic: modulus number K", "float"), ("dc_Kur", "Hyperbolic: unload-reload number Kur", "float"),
        ("dc_n", "Hyperbolic: modulus exponent n", "float"), ("dc_Rf", "Hyperbolic: failure ratio Rf", "float"),
        ("hs_E50", "Hardening Soil: E50 at the reference pressure", "float", "modulus"),
        ("hs_Eur", "Hardening Soil: Eur (unload-reload) at the reference pressure", "float", "modulus"),
        ("hs_m", "Hardening Soil: stress exponent m", "float"),
        ("hs_pref", "Hardening Soil: reference pressure", "float", "pressure"),
        ("hs_Rf", "Hardening Soil: failure ratio Rf", "float"),
        ("iface_ks", "Interface: shear stiffness ks (pressure per length of slip)", "float"),
        ("iface_kn", "Interface: normal stiffness kn (pressure per length)", "float"),
        ("iface_c", "Interface: adhesion", "float", "pressure"),
        ("iface_delta", "Interface: friction angle delta (deg)", "float")]),
    ("Dynamic", [
        ("damping", "Damping ratio (small strain)", "float"),
        ("gamma_ref", "Reference shear strain (0 = linear)", "float"), ("damping_max", "Maximum damping ratio", "float"),
        ("liq_crr", "Pore pressure: cyclic resistance ratio CRR for 15 cycles (0 = none)", "float"),
        ("liq_b", "Pore pressure: slope b of CRR vs cycles (CRR ~ N^-b)", "float"),
        ("liq_alpha", "Pore pressure: ru curve shape alpha (0.7)", "float")]),
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
    if m.stress_model == "cam_clay" and not (0 < m.cc_kappa < m.cc_lambda and m.e0 > 0 and m.ocr >= 1):
        raise ValueError(f"{m.name}: Cam Clay needs 0 < kappa < lambda, e0 > 0 and OCR >= 1.")
    if m.stress_model == "hyperbolic" and (m.dc_K <= 0 or m.dc_Kur <= 0 or not 0 < m.dc_Rf <= 1):
        raise ValueError(f"{m.name}: hyperbolic model needs K > 0, Kur > 0 and 0 < Rf <= 1.")
    if m.stress_model == "hardening_soil" and (m.hs_E50 <= 0 or m.hs_Eur <= 0 or m.hs_pref <= 0
                                               or not 0 < m.hs_Rf < 1 or not 0 <= m.hs_m <= 1):
        raise ValueError(f"{m.name}: Hardening Soil needs E50 > 0, Eur > 0, p_ref > 0, 0 < Rf < 1 and 0 <= m <= 1.")
    if m.cr < 0 or not 0 <= m.phi_r < 90:
        raise ValueError(f"{m.name}: the rapid drawdown R envelope needs c_R >= 0 and 0 <= phi_R < 90.")
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
STRESS_TYPES = {"insitu": "In Situ", "load": "Load-Deformation", "consolidation": "Coupled Stress/PWP (consolidation)"}
INSITU_METHODS = {"gravity": "Gravity Activation", "k0": "K0 Procedure"}
STRESS_PWP = {"none": "(none)", "seepage": "Parent Analysis", "piezometric": "Piezometric Surface"}
TIME = [("duration", "Duration (s)", "float"), ("n_steps", "Number of time steps", "int"),
        ("step_growth", "Time step growth ratio", "float")]
STEADY = {"steady": "Steady-State", "transient": "Transient"}

# Analysis Type combo in the header: (attribute, {stored value: label}, {combo key: stored value} or None)
ANALYSIS_TYPES = {
    "slope": ("method", {"le": "Limit Equilibrium", "fe": "Finite Element Stress-based"}, None),
    "seepage": ("transient", STEADY, {"steady": False, "transient": True}),
    "thermal": ("transient", STEADY, {"steady": False, "transient": True}),
    "air": ("transient", STEADY, {"steady": False, "transient": True}),
    "stress": ("stress_type", STRESS_TYPES, None),
    "dynamic": ("equivalent_linear", {"linear": "Linear Elastic", "eqlin": "Equivalent Linear"},
                {"linear": False, "eqlin": True}),
    "transport": (None, {"ad": "Advection-Dispersion"}, None),
}

KIND_TABS = {
    "seepage": [("Seepage", [("mesh_size", "Mesh element size", "float", "length"),
                             ("unsaturated", "Include unsaturated flow (free phreatic surface)", "bool"),
                             ("initial", "Initial conditions", "choice", INITIAL),
                             ("initial_value", "Initial total head", "float", "length"),
                             ("max_iter", "Max iterations per step", "int"), ("tolerance", "Head tolerance", "float")]),
                ("Time", TIME),
                ("3D / Axisymmetric", [
                    ("three_d", "3D: extrude the section over a width (wedge elements)", "bool"),
                    ("width3d", "3D: width of the model in z", "float", "length"),
                    ("n_layers3d", "3D: element layers across the width", "int"),
                    ("slice_z", "3D: section shown in the results, z (negative = middle)", "float", "length"),
                    ("wells", "3D wells", "table6",
                     ["x", "z", "top y", "bottom y", "type (0 = fixed head, 1 = pumping rate)", "head or rate"]),
                    ("axisymmetric", "Axisymmetric: x is the radius, the section turns about x = 0", "bool")])],
    "stress": [("Stress", [("insitu_method", "Method", "choice", INSITU_METHODS),
                           ("pwp", "Final PWP conditions from", "choice", STRESS_PWP),
                           ("mesh_size", "Mesh element size", "float", "length"),
                           ("load_steps", "Load steps", "int"),
                           ("srm", "Compute strength reduction factor of safety (in situ)", "bool"),
                           ("max_iter", "Max plastic iterations", "int")]),
               ("Time", TIME)],
    "dynamic": [("Dynamic", [("mesh_size", "Mesh element size", "float", "length"), ("dt", "Time step (s)", "float"),
                             ("n_eq_iter", "Equivalent linear iterations", "int"),
                             ("pwp_generation", "Generate excess pore pressure and check liquefaction "
                              "(materials with a CRR)", "bool"),
                             ("motion", "Input acceleration", "table2", ["time (s)", "acceleration (g)"])])],
    "thermal": [("Thermal", [("mesh_size", "Mesh element size", "float", "length"),
                             ("initial", "Initial conditions", "choice", {k: v for k, v in INITIAL.items() if k != "water_table"}),
                             ("initial_value", "Initial temperature", "float", "temperature"),
                             ("max_iter", "Max iterations per step", "int"), ("tolerance", "Temperature tolerance", "float")]),
                ("Time", TIME)],
    "transport": [("Transport", [("initial_value", "Initial concentration", "float", "concentration"),
                                 ("particles", "Particle tracking start points", "table2", ["x", "y"])]),
                  ("Time", TIME)],
    "air": [("Air Flow", [("mesh_size", "Mesh element size", "float", "length"),
                          ("initial_value", "Initial air pressure", "float", "pressure"),
                          ("max_iter", "Max iterations per step", "int"), ("tolerance", "Pressure tolerance", "float")]),
            ("Time", TIME)],
}

SLOPE_EXTRA = [("Rapid Drawdown", [
    ("rapid_drawdown", "Rapid drawdown: three-stage method (Duncan, Wright and Wong)", "bool"),
    ("drawdown_level", "Reservoir level after drawdown (elevation)", "float", "length"),
    ("post_earthquake", "After an earthquake: add the excess pore pressure of the parent dynamic analysis",
     "bool")]),
    ("3D", [
        ("three_d", "3D: ellipsoidal slip surfaces on the section extruded over a width (3D Bishop)", "bool"),
        ("width3d", "Width of the model in z", "float", "length"),
        ("slide_lengths", "Trial slide lengths (empty = 1/4, 1/2, 3/4, 1 and 1.5 x the width)", "table1",
         ["length"]),
        ("slide_center_z", "Slide centre z (negative = middle of the load or of the width)", "float", "length"),
        ("load_z1", "Surcharges and point loads from z", "float", "length"),
        ("load_z2", "to z (both 0 = over the whole width)", "float", "length")])]
SLOPE_OPTIMIZATION = [("optimize", "Optimize the critical slip surface (non-circular)", "bool"),
                      ("opt_iterations", "Optimization trials", "int")]
SLOPE_CONVERGENCE = [("n_slices", "Number of slices", "int")]
SLOPE_LOADS = [("kh", "Horizontal seismic coefficient kh", "float"),
               ("kv", "Vertical seismic coefficient kv (down +)", "float")]
SLOPE_CRACK = [("tension_crack_depth", "Tension crack depth (0 = none)", "float", "length"),
               ("tension_crack_angle", "Tension crack where base steeper than (deg, 0 = off)", "float"),
               ("crack_water", "Fraction of crack filled with water", "float")]


def descendants(project, aid):
    out, changed = set(), True
    while changed:
        changed = False
        for o in project.analyses:
            if (o.parent_id == aid or o.parent_id in out) and o.id not in out:
                out.add(o.id)
                changed = True
    return out


class AnalysisEditor(QWidget):
    """Settings of one analysis: header (name, parent, analysis type, description) and tabs."""

    changed = Signal()

    def __init__(self, project, analysis, parent=None):
        super().__init__(parent)
        from .icons import kind_pixmap
        self.p, self.a = project, analysis
        a = analysis
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)

        head = QGridLayout()
        icon = QLabel()
        icon.setPixmap(kind_pixmap(a.kind, 40))
        head.addWidget(icon, 0, 0, 3, 1, Qt.AlignTop)
        self.name = QLineEdit(a.name)
        self.name.textEdited.connect(lambda *_: self.changed.emit())
        self.parent_cb = QComboBox()
        self.parent_cb.addItem("(none)", None)
        banned = descendants(project, a.id) | {a.id}
        for o in project.analyses:
            if o.id not in banned:
                self.parent_cb.addItem(o.name, o.id)
        self.parent_cb.setCurrentIndex(max(0, self.parent_cb.findData(a.parent_id)))
        self.parent_cb.currentIndexChanged.connect(lambda *_: self.changed.emit())
        attr, labels, to_value = ANALYSIS_TYPES.get(a.kind, (None, {"": a.kind}, None))
        self.type_attr, self.type_map = attr, to_value
        current = None
        if a.kind == "slope":
            current = "fe" if a.method == "finite_element" else "le"
        elif attr:
            val = getattr(a, attr)
            current = next((k for k, x in to_value.items() if x == val), None) if to_value else val
        self.type_cb = combo(labels, current)
        self.type_cb.setEnabled(len(labels) > 1)
        self.type_cb.currentIndexChanged.connect(self._type_changed)
        for r, (lab, w) in enumerate((("Name:", self.name), ("Parent:", self.parent_cb),
                                      ("Analysis Type:", self.type_cb))):
            head.addWidget(QLabel(lab), r, 1)
            head.addWidget(w, r, 2)
        head.addWidget(QLabel("Description:"), 0, 3)
        self.desc = QPlainTextEdit(a.description)
        self.desc.setMaximumHeight(56)
        head.addWidget(self.desc, 1, 3, 2, 1)
        head.setColumnStretch(2, 2)
        head.setColumnStretch(3, 2)
        v.addLayout(head)

        self.tabs = QTabWidget()
        v.addWidget(self.tabs, 1)
        self.forms = []
        self.time_form = None
        if a.kind == "slope":
            self._slope_tabs(self.tabs)
        for title, spec in KIND_TABS.get(a.kind, []) + (SLOPE_EXTRA if a.kind == "slope" else []):
            form = Form(spec, project.unit)
            form.load(a)
            self.forms.append(form)
            if title == "Time":
                self.time_form = form
                self.time_note = QLabel()
                self.time_note.setStyleSheet("color:#666")
                form.layout().insertRow(0, self.time_note)
            self.tabs.addTab(form, title)
        self.stage_list = None
        if a.kind == "stress":
            self.tabs.addTab(self._stage_tab(), "Construction Stage")
        hint = QLabel("Children use their parents' results: seepage gives pore pressures and flow, stress gives "
                      "stresses for the finite element slope method, dynamic gives Newmark displacements, and "
                      "earlier steps give initial conditions.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#666")
        v.addWidget(hint)
        self._type_changed()

    def _stage_tab(self):
        """Staged construction: tick the regions that exist in this stage."""
        from PySide6.QtWidgets import QListWidget, QListWidgetItem
        from ..geometry import polygon_area
        w = QWidget()
        lay = QVBoxLayout(w)
        info = QLabel("Tick the regions that exist in this stage. Untick a region to <b>dig it out</b> "
                      "(excavation) or to say it is <b>not built yet</b> (a fill placed in a later stage). "
                      "Make each stage a child of the previous one: GeoLab then releases the soil that was dug "
                      "out, adds the weight of new fill and carries the stresses on. Structures (walls, anchors, "
                      "geogrids) are chosen per stage in Draw > Structures.")
        info.setWordWrap(True)
        lay.addWidget(info)
        self.stage_list = QListWidget()
        mats = {m.id: m.name for m in self.p.materials}
        off = set(self.a.inactive_regions or [])
        for r in self.p.regions:
            it = QListWidgetItem(f"Region {r.id}: {mats.get(r.material_id, 'no material')}  "
                                 f"({abs(polygon_area(r.points)):.1f} {self.p.unit('length')}²)")
            it.setData(Qt.UserRole, r.id)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Unchecked if r.id in off else Qt.Checked)
            self.stage_list.addItem(it)
        lay.addWidget(self.stage_list, 1)
        return w

    # ------------------------------------------------------------------
    def type_value(self):
        key = self.type_cb.currentData()
        if self.a.kind == "slope":
            return "finite_element" if key == "fe" else self.method.currentData()
        return self.type_map[key] if self.type_map else key

    def _field(self, key):
        for f in self.forms:
            if key in f.w:
                return f, f.w[key]
        return None, None

    def _enable(self, key, on):
        f, w = self._field(key)
        if w is not None:
            w.setEnabled(on)
            lab = f.layout().labelForField(w)
            if lab is not None:
                lab.setEnabled(on)

    def _type_changed(self, *_):
        a, val = self.a, self.type_value()
        if a.kind == "stress":
            self._enable("insitu_method", val == "insitu")
            self._enable("srm", val == "insitu")
            self._enable("load_steps", val != "consolidation")
            timed = val == "consolidation"
        elif a.kind == "dynamic":
            self._enable("n_eq_iter", bool(val))
            timed = True
        elif a.kind == "slope":
            le = self.type_cb.currentData() == "le"
            self.method.setEnabled(le)
            mp = le and self.method.currentData() == "morgenstern_price"
            self.inter.setEnabled(mp)
            self.inter_pts.setEnabled(mp)
            timed = False
        else:
            timed = bool(val) if a.kind in ("seepage", "thermal", "air") else True
        if self.time_form is not None:
            for key in self.time_form.w:
                self._enable(key, timed)
            self.time_note.setText("" if timed else "Steady state: this analysis has no time steps.")
        self.changed.emit()

    def _slope_tabs(self, tabs):
        a, project = self.a, self.p
        t = QWidget(); f = QFormLayout(t)
        self.method = combo({k: v for k, v in SLOPE_METHODS.items() if k != "finite_element"},
                            a.method if a.method != "finite_element" else "morgenstern_price")
        self.method.currentIndexChanged.connect(self._type_changed)
        self.inter = combo(INTERSLICE_FUNCTIONS, a.interslice)
        self.inter_pts = QPlainTextEdit("\n".join(f"{x:g}, {y:g}" for x, y in a.interslice_points))
        self.inter_pts.setMaximumHeight(60)
        self.inter_pts.setPlaceholderText("x/L, f(x)  per line (for 'Data points')")
        self.nsl = None
        self.pwp = combo(PWP_MODES, a.pwp)
        self.ru = dspin(a.ru, 0, 1, 3, 0.05)
        f.addRow("Method:", self.method)
        f.addRow("    Side Function:", self.inter)
        f.addRow("    Side function data points:", self.inter_pts)
        f.addRow("PWP Conditions from:", self.pwp)
        f.addRow("    Ru:", self.ru)
        loads = Form(SLOPE_LOADS, project.unit)
        loads.load(a)
        self.forms.append(loads)
        f.addRow(QLabel("<b>Seismic (pseudo-static)</b>"))
        f.addRow(loads)
        f.addRow(QLabel("<b>Physical Constants</b>"))
        uw = QLabel(f"{project.gamma_w:g} {project.unit('unit_weight') if hasattr(project, 'unit') else ''}")
        f.addRow("Unit Weight of Water:", uw)
        tabs.addTab(t, "Settings")

        s = a.search
        t = QWidget(); grid = QGridLayout(t)
        self.mode = combo(SEARCH_MODES, s.mode)
        grid.addWidget(QLabel("Slip surface"), 0, 0); grid.addWidget(self.mode, 0, 1, 1, 3)
        self.sf = {}
        fields = [("entry_x1", "Entry x from"), ("entry_x2", "Entry x to"), ("exit_x1", "Exit x from"),
                  ("exit_x2", "Exit x to"), ("n_entry", "Entry increments"), ("n_exit", "Exit increments"),
                  ("n_radius", "Radius increments"),
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
        crack = Form(SLOPE_CRACK, project.unit)
        crack.load(a)
        self.forms.append(crack)
        grid.addWidget(QLabel("<b>Tension crack</b>"), r + 6, 0, 1, 4)
        grid.addWidget(crack, r + 7, 0, 1, 4)
        scroll = QScrollArea()
        scroll.setWidget(t)
        scroll.setWidgetResizable(True)
        tabs.addTab(scroll, "Slip Surface")
        opt = Form(SLOPE_OPTIMIZATION, project.unit)
        opt.load(a)
        self.forms.append(opt)
        tabs.addTab(opt, "Optimization")

        t = QWidget(); f = QFormLayout(t)
        self.prob = QCheckBox("Run Monte Carlo on the critical slip surface")
        self.prob.setChecked(a.probabilistic)
        self.ns = ispin(a.n_samples, 10, 100000)
        self.seed = ispin(a.seed, 0, 2 ** 31 - 1)
        f.addRow(QLabel("<b>Probabilistic analysis</b>"))
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
        tabs.addTab(t, "Distribution")
        conv = Form(SLOPE_CONVERGENCE, project.unit)
        conv.load(a)
        self.forms.append(conv)
        self.min_depth = dspin(a.search.min_depth, 0, 1e6, 3, 0.1)
        conv.layout().addRow(f"Minimum slip surface depth ({project.unit('length')})", self.min_depth)
        tabs.addTab(conv, "Convergence")

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

    def build(self):
        """A validated copy of the analysis with the edited settings. Raises ValueError."""
        a = copy.deepcopy(self.a)
        a.name = self.name.text().strip() or a.name
        a.description = self.desc.toPlainText().strip()
        a.parent_id = self.parent_cb.currentData()
        for form in self.forms:
            form.store(a)
        if self.type_attr:
            setattr(a, self.type_attr, self.type_value())
        if a.kind == "slope":
            self._store_slope(a)
        if self.stage_list is not None:
            a.inactive_regions = [self.stage_list.item(i).data(Qt.UserRole) for i in range(self.stage_list.count())
                                  if self.stage_list.item(i).checkState() != Qt.Checked]
            if len(a.inactive_regions) == len(self.p.regions) and self.p.regions:
                raise ValueError("At least one region must exist in the stage.")
        if a.kind == "slope" and a.rapid_drawdown and a.pwp != "piezometric":
            raise ValueError("Rapid drawdown uses the piezometric line as the reservoir level before drawdown: "
                             "set Pore Water Pressure to 'Piezometric line'.")
        parent = self.p.analysis(a.parent_id)
        if a.kind == "transport" and (parent is None or parent.kind != "seepage"):
            raise ValueError("Contaminant transport needs a seepage analysis as its parent.")
        if a.kind in ("seepage", "thermal", "air") and a.transient and (a.duration <= 0 or a.n_steps < 1):
            raise ValueError("A transient analysis needs a positive duration and at least one time step.")
        if a.kind == "stress" and a.stress_type == "consolidation" and (a.duration <= 0 or a.n_steps < 1):
            raise ValueError("A consolidation analysis needs a positive duration and at least one time step.")
        if a.kind == "stress" and a.pwp == "seepage" and parent is None:
            raise ValueError("'Final PWP conditions from: Parent Analysis' needs a parent analysis.")
        if a.kind == "dynamic" and (len(a.motion) < 2 or a.dt <= 0):
            raise ValueError("Enter at least two rows of input acceleration and a positive time step.")
        if getattr(a, "mesh_size", 1) <= 0:
            raise ValueError("Mesh size must be positive.")
        return a

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
        a.interslice = self.inter.currentData()
        a.interslice_points = [r for r in self._parse_rows(self.inter_pts.toPlainText(), 2) if r]
        a.pwp = self.pwp.currentData()
        a.ru = self.ru.value()
        s = a.search
        s.mode = self.mode.currentData()
        s.min_depth = self.min_depth.value()
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


class AnalysisDialog(QDialog):
    """Settings of a single analysis."""

    def __init__(self, project, analysis, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Analysis Settings - {analysis.name}")
        self.resize(720, 660)
        self.a = analysis
        v = QVBoxLayout(self)
        self.editor = AnalysisEditor(project, analysis, self)
        self.forms = self.editor.forms
        v.addWidget(self.editor)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.try_accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def try_accept(self):
        try:
            a = self.editor.build()
        except ValueError as e:
            QMessageBox.warning(self, "Invalid input", str(e))
            return
        self.a.__dict__.update(a.__dict__)
        self.accept()


class DefineProjectDialog(QDialog):
    """All analyses of the project in one place: the analysis tree on the left (Add / Delete), the
    selected analysis' settings on the right. Works on a copy; OK applies everything at once."""

    def __init__(self, project, current_id=None, parent=None):
        super().__init__(parent)
        from .icons import kind_icon
        self._kind_icon = kind_icon
        self.setWindowTitle("Define Analyses")
        self.resize(1180, 680)
        self.p = copy.copy(project)          # results are not copied (they can be large)
        self.p.analyses = []
        for a in project.analyses:
            res, a.results = a.results, None
            try:
                self.p.analyses.append(copy.deepcopy(a))
            finally:
                a.results = res
        self.p.boundary_conditions = copy.deepcopy(project.boundary_conditions)
        self.editors = {}
        root = QHBoxLayout(self)

        left = QVBoxLayout()
        bar = QHBoxLayout()
        bar.addWidget(QLabel("Analyses:"))
        bar.addStretch(1)
        add = QPushButton("Add")
        menu = QMenu(add)
        for kind, label in ANALYSIS_KINDS.items():
            menu.addAction(kind_icon(kind), label, lambda k=kind: self.add(k))
        add.setMenu(menu)
        self.add_btn = add
        dele = QPushButton("Delete")
        dele.clicked.connect(self.delete)
        bar.addWidget(add)
        bar.addWidget(dele)
        left.addLayout(bar)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIconSize(QSize(18, 18))
        self.tree.currentItemChanged.connect(self._selected)
        left.addWidget(self.tree, 1)
        tip = QLabel("Add puts the new analysis under the selected one (its parent).")
        tip.setStyleSheet("color:#666")
        left.addWidget(tip)
        lw = QWidget()
        lw.setLayout(left)
        lw.setMinimumWidth(380)

        right = QVBoxLayout()
        self.stack = QStackedWidget()
        right.addWidget(self.stack, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.try_accept)
        bb.rejected.connect(self.reject)
        right.addWidget(bb)
        root.addWidget(lw, 2)
        root.addLayout(right, 3)

        self._current = None
        self.refresh(current_id if self.p.analysis(current_id) else (self.p.analyses[0].id if self.p.analyses else None))

    # ------------------------------------------------------------------
    def _label(self, aid):
        a = self.p.analysis(aid)
        ed = self.editors.get(aid)
        name = ed.name.text().strip() if ed else a.name
        kind = {"slope": "Slope", "seepage": "Seepage", "stress": "Stress", "dynamic": "Dynamic",
                "thermal": "Thermal", "transport": "Transport", "air": "Air flow"}.get(a.kind, a.kind)
        return f"{name or a.name}  [{kind}]"

    def _parent_of(self, aid):
        ed = self.editors.get(aid)
        return ed.parent_cb.currentData() if ed else self.p.analysis(aid).parent_id

    def refresh(self, select_id=None):
        self.tree.blockSignals(True)
        self.tree.clear()
        top = QTreeWidgetItem([self.p.title or "(untitled)"])
        top.setIcon(0, self._kind_icon("slope"))
        geo = QTreeWidgetItem(["2D Geometry"])
        geo.setIcon(0, self.style().standardIcon(QStyle.SP_DirIcon))
        top.addChild(geo)
        self.tree.addTopLevelItem(top)
        items = {}
        ids = {a.id for a in self.p.analyses}

        def add(a, parent_item, seen):
            it = QTreeWidgetItem([self._label(a.id)])
            it.setIcon(0, self._kind_icon(a.kind))
            it.setData(0, Qt.UserRole, a.id)
            parent_item.addChild(it)
            items[a.id] = it
            for c in self.p.analyses:
                if self._parent_of(c.id) == a.id and c.id not in seen:
                    add(c, it, seen | {c.id})

        for a in self.p.analyses:
            if self._parent_of(a.id) not in ids:
                add(a, geo, {a.id})
        self.tree.expandAll()
        self.tree.blockSignals(False)
        target = items.get(select_id) or items.get(self._current)
        if target is not None:
            self.tree.setCurrentItem(target)
            self._show(target.data(0, Qt.UserRole))

    def _editor(self, aid):
        if aid not in self.editors:
            ed = AnalysisEditor(self.p, self.p.analysis(aid), self)
            ed.changed.connect(lambda aid=aid: self._relabel(aid))
            ed.parent_cb.currentIndexChanged.connect(lambda *_: self.refresh(aid))
            self.editors[aid] = ed
            self.stack.addWidget(ed)
        return self.editors[aid]

    def _relabel(self, aid):
        it = self._find(aid)
        if it is not None:
            it.setText(0, self._label(aid))

    def _find(self, aid):
        itr = QTreeWidgetItemIterator(self.tree)
        while itr.value():
            if itr.value().data(0, Qt.UserRole) == aid:
                return itr.value()
            itr += 1
        return None

    def _show(self, aid):
        self._current = aid
        self.stack.setCurrentWidget(self._editor(aid))

    def _selected(self, item, _prev=None):
        aid = item.data(0, Qt.UserRole) if item is not None else None
        if aid is not None:
            self._show(aid)

    def selected_id(self):
        return self._current

    def add(self, kind):
        parent = self.p.analysis(self._current)
        names = {"slope": "Slope Stability", "seepage": "Seepage", "stress": "Stress-Deformation",
                 "dynamic": "Dynamic", "thermal": "Thermal", "transport": "Contaminant Transport", "air": "Air Flow"}
        n = sum(1 for a in self.p.analyses if a.kind == kind) + 1
        a = self.p.add_analysis(f"{names[kind]}{'' if n == 1 else f' {n}'}", kind=kind)
        if parent is not None:
            a.parent_id = parent.id
            if parent.kind in ("seepage", "stress", "thermal", "air", "transport"):
                a.mesh_size = parent.mesh_size
            if kind in ("seepage", "thermal") and parent.kind == kind:
                a.transient, a.initial = True, "parent"
            if kind == "stress" and parent.kind == "stress":
                a.stress_type = "load"
            if kind in ("slope", "stress") and parent.kind == "seepage":
                a.pwp = "seepage"
            if kind == "slope" and parent.kind == "stress":
                a.method = "finite_element"
        if kind == "slope":
            if self.p.regions:
                (e1, e2), (x1, x2) = auto_entry_exit(self.p)
                a.search.entry_x1, a.search.entry_x2, a.search.exit_x1, a.search.exit_x2 = e1, e2, x1, x2
            if self.p.piezometric_line and a.pwp == "none":
                a.pwp = "piezometric"
        # editors built earlier list parents from the old analysis set: rebuild them
        self._rebuild_editors()
        self.refresh(a.id)
        return a

    def _rebuild_editors(self):
        """Keep edits, then drop the editors so parent lists are rebuilt from the current analyses."""
        for aid, ed in list(self.editors.items()):
            try:
                built = ed.build()
            except ValueError:
                built = None
            if built is not None:
                self.p.analysis(aid).__dict__.update(built.__dict__)
            self.stack.removeWidget(ed)
            ed.deleteLater()
        self.editors.clear()

    def delete(self):
        a = self.p.analysis(self._current)
        if a is None:
            return
        if len(self.p.analyses) == 1:
            QMessageBox.information(self, "Define Analyses", "A project needs at least one analysis.")
            return
        kids = descendants(self.p, a.id)
        msg = f"Delete '{a.name}'" + (f" and its {len(kids)} child analyses" if kids else "") + "?"
        if QMessageBox.question(self, "Delete analysis", msg) != QMessageBox.Yes:
            return
        self._rebuild_editors()
        gone = kids | {a.id}
        self.p.analyses = [o for o in self.p.analyses if o.id not in gone]
        for bc in getattr(self.p, "boundary_conditions", []):
            if bc.analyses:
                bc.analyses = [i for i in bc.analyses if i not in gone]
        self._current = None
        self.refresh(a.parent_id if a.parent_id not in gone else None)
        if self._current is None and self.p.analyses:
            self.refresh(self.p.analyses[0].id)

    def try_accept(self):
        for aid, ed in self.editors.items():
            try:
                built = ed.build()
            except ValueError as e:
                self.tree.setCurrentItem(self._find(aid))
                QMessageBox.warning(self, "Invalid input", f"{ed.name.text()}: {e}")
                return
            self.p.analysis(aid).__dict__.update(built.__dict__)
        for a in self.p.analyses:
            seen, cur = {a.id}, a.parent_id
            while cur is not None and self.p.analysis(cur) is not None:
                if cur in seen:
                    QMessageBox.warning(self, "Invalid input", f"'{a.name}' is its own ancestor; change its parent.")
                    return
                seen.add(cur)
                cur = self.p.analysis(cur).parent_id
        self.accept()


class EntryExitDialog(QDialog):
    """Slip surface entry and exit ranges, entered as left-side and right-side ranges on the ground
    surface. The higher range is where slip surfaces enter, the lower one where they exit."""

    def __init__(self, project, analysis, parent=None):
        super().__init__(parent)
        from ..geometry import GroundProfile
        self.setWindowTitle("Draw Slip Surface Entry and Exit Range")
        self.gp = GroundProfile(project.regions, samples=800) if project.regions else None
        s = analysis.search
        if s.entry_x1 == s.entry_x2 == s.exit_x1 == s.exit_x2 == 0 and project.regions:
            (s_e1, s_e2), (s_x1, s_x2) = auto_entry_exit(project)
        else:
            s_e1, s_e2, s_x1, s_x2 = s.entry_x1, s.entry_x2, s.exit_x1, s.exit_x2
        entry, exit_ = sorted((s_e1, s_e2)), sorted((s_x1, s_x2))
        if entry[0] > exit_[0]:
            left, right, ninc_l, ninc_r = exit_, entry, s.n_exit, s.n_entry
        else:
            left, right, ninc_l, ninc_r = entry, exit_, s.n_entry, s.n_exit
        unit = project.unit("length") if hasattr(project, "unit") else ""
        v = QVBoxLayout(self)
        sides = QHBoxLayout()
        self.side = {}
        for key, rng, ninc in (("left", left, ninc_l), ("right", right, ninc_r)):
            box = QWidget()
            g = QGridLayout(box)
            g.setContentsMargins(0, 0, 12, 0)
            title = QLabel()
            title.setStyleSheet("font-weight:600")
            g.addWidget(title, 0, 0, 1, 5)
            typ = QComboBox()
            typ.addItems(["Range", "Point"])
            g.addWidget(QLabel("Type:"), 1, 0)
            g.addWidget(typ, 2, 0)
            g.addWidget(QLabel("Left Point:"), 1, 1, 1, 2)
            g.addWidget(QLabel("Right Point:"), 1, 3, 1, 2)
            x1, x2 = dspin(rng[0], -1e7, 1e7, 3), dspin(rng[1], -1e7, 1e7, 3)
            y1, y2 = QLabel(), QLabel()
            for w in (x1, x2):
                w.setSuffix(f" {unit}" if unit else "")
            g.addWidget(QLabel("X:"), 2, 1); g.addWidget(x1, 2, 2)
            g.addWidget(QLabel("X:"), 2, 3); g.addWidget(x2, 2, 4)
            g.addWidget(QLabel("Y:"), 3, 1); g.addWidget(y1, 3, 2)
            g.addWidget(QLabel("Y:"), 3, 3); g.addWidget(y2, 3, 4)
            n = ispin(max(1, int(ninc) - 1), 1, 200)
            g.addWidget(QLabel("Number of increments over range:"), 4, 0, 1, 3)
            g.addWidget(n, 4, 3, 1, 2)
            self.side[key] = {"title": title, "type": typ, "x1": x1, "x2": x2, "y1": y1, "y2": y2, "n": n}
            for w in (x1, x2):
                w.valueChanged.connect(self._update)
            typ.currentIndexChanged.connect(self._update)
            sides.addWidget(box)
        v.addLayout(sides)
        row = QHBoxLayout()
        row.addWidget(QLabel("Number of radius increments:"))
        self.nr = ispin(max(1, int(s.n_radius) - 1), 1, 200)
        row.addWidget(self.nr)
        row.addStretch(1)
        v.addLayout(row)
        note = QLabel("Y is read from the ground surface. Slip surfaces enter through the higher range and "
                      "exit through the lower one; the direction of movement follows from that.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#666")
        v.addWidget(note)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.try_accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self._update()

    def _ground(self, x):
        return float(self.gp.ground(x)) if self.gp is not None else float("nan")

    def _update(self, *_):
        for key, d in self.side.items():
            point = d["type"].currentIndex() == 1
            d["x2"].setEnabled(not point)
            d["n"].setEnabled(not point)
            if point:
                d["x2"].blockSignals(True)
                d["x2"].setValue(d["x1"].value())
                d["x2"].blockSignals(False)
            for xk, yk in (("x1", "y1"), ("x2", "y2")):
                d[yk].setText(f"{self._ground(d[xk].value()):.3f}")
        left_hi = self._mid_y("left") > self._mid_y("right")
        self.side["left"]["title"].setText("Entry Range (Left Side)" if left_hi else "Exit Range (Left Side)")
        self.side["right"]["title"].setText("Exit Range (Right Side)" if left_hi else "Entry Range (Right Side)")

    def _mid_y(self, key):
        d = self.side[key]
        return self._ground(0.5 * (d["x1"].value() + d["x2"].value()))

    def ranges(self):
        """((entry x1, x2, points), (exit x1, x2, points))."""
        out = {}
        for key, d in self.side.items():
            a, b = sorted((d["x1"].value(), d["x2"].value()))
            pts = 1 if d["type"].currentIndex() == 1 else d["n"].value() + 1
            out[key] = (a, b, pts)
        if self._mid_y("left") > self._mid_y("right"):
            return out["left"], out["right"]
        return out["right"], out["left"]

    def try_accept(self):
        (e1, e2, _), (x1, x2, _) = self.ranges()
        if max(e1, x1) <= min(e2, x2):
            QMessageBox.warning(self, "Invalid input", "The two ranges overlap; move one of them.")
            return
        self.accept()

    def apply(self, a):
        (e1, e2, ne), (x1, x2, nx) = self.ranges()
        s = a.search
        s.mode = "entry_exit"
        s.entry_x1, s.entry_x2, s.n_entry = e1, e2, ne
        s.exit_x1, s.exit_x2, s.n_exit = x1, x2, nx
        s.n_radius = self.nr.value() + 1


# ---------------------------------------------------------------------------
# Small editors
# ---------------------------------------------------------------------------
BC_HELP = {
    "hydraulic": "Head / pressure head in length units; unit flux per unit length per second (inflow +). "
                 "Climate: value = rainfall rate, second value = potential evaporation rate (length per second; "
                 "1 mm/day = 1.157e-8 m/s), plus air humidity; excess rain ponds and runs off.",
    "stress": "Pressure and shear in pressure units (compression +); forces are totals shared by the nodes; "
              "displacement in length units.",
    "thermal": "Temperature; heat flux per unit area (into the ground +); convective: value = h, second "
               "value = ambient temperature.",
    "transport": "Concentration; mass flux per unit length (inflow +).",
    "air": "Gauge air pressure; air flux per unit length (inflow +).",
}


class BCDialog(QDialog):
    def __init__(self, name="BC", type_="head", value=0.0, parent=None, kinds=None, value2=0.0, fn=None,
                 analyses=None, project=None, fn2=None, humidity=0.5, value3=0.0, root_depth=0.0, z1=0.0, z2=0.0):
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
        self.fn2 = QPlainTextEdit("\n".join(f"{t:g}, {v:g}" for t, v in (fn2 or [])))
        self.fn2.setMaximumHeight(70)
        self.fn2.setPlaceholderText("time (s), second value  per line (e.g. potential evaporation)")
        self.humidity = dspin(humidity, 0, 0.99, 2, 0.05)
        self.value3 = dspin(value3, 0, 1e12, 10)
        self.value3.setToolTip("Potential transpiration of the plants (water per unit area per second). "
                               "Example: 3 mm/day = 3.5e-8 m/s.")
        self.root_depth = dspin(root_depth, 0, 1e6, 3, 0.1)
        self.root_depth.setToolTip("Depth of the roots below the ground surface; 0 = bare soil (no plants).")
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
        f.addRow("Second value vs time", self.fn2)
        f.addRow("Air humidity (climate)", self.humidity)
        f.addRow("Plant transpiration (climate)", self.value3)
        f.addRow("Root depth (climate, 0 = no plants)", self.root_depth)
        f.addRow("Applies to", self.only)
        self.z1 = dspin(z1, -1e9, 1e9, 3)
        self.z2 = dspin(z2, -1e9, 1e9, 3)
        self.z1.setToolTip("3D analyses only: the boundary acts from z1 to z2 across the width. "
                           "Leave both 0 for the whole width.")
        self.z2.setToolTip(self.z1.toolTip())
        f.addRow("3D: from z", self.z1)
        f.addRow("3D: to z (both 0 = whole width)", self.z2)
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
            self.fn2_rows = [r for r in AnalysisDialog._parse_rows(self.fn2.toPlainText(), 2) if r]
        except ValueError as e:
            QMessageBox.warning(self, "Invalid input", str(e))
            return
        self.accept()

    def params(self):
        only = self.only.currentData()
        return dict(name=self.name.text().strip() or "BC", type=self.type.currentData(), value=self.value.value(),
                    value2=self.value2.value(), fn=getattr(self, "fn_rows", []), analyses=[only] if only else [],
                    fn2=getattr(self, "fn2_rows", []), humidity=self.humidity.value(),
                    value3=self.value3.value(), root_depth=self.root_depth.value(),
                    z1=self.z1.value(), z2=self.z2.value())


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


class StructureDialog(QDialog):
    """Properties of a structural element for stress-deformation analyses."""

    def __init__(self, st=None, parent=None, unit=None, project=None):
        super().__init__(parent)
        self.setWindowTitle("Structure (wall, anchor, geogrid)")
        from ..model import STRUCTURE_TYPES, Structure
        self.st = copy.deepcopy(st) if st else Structure(id=0, name="", type="beam", points=[])
        spec = [("name", "Name", "text"), ("type", "Type", "choice", STRUCTURE_TYPES),
                ("EA", "Axial stiffness EA (per unit width)", "float"),
                ("EI", "Bending stiffness EI (walls / beams)", "float"),
                ("spacing", "Out-of-plane spacing (anchors)", "float", "length"),
                ("prestress", "Prestress force when installed (anchors)", "float", "force")]
        v = QVBoxLayout(self)
        tip = QLabel("Walls / beams carry bending and axial force; anchors and struts carry axial force "
                     "only; geogrids carry tension only. Typical sheet pile: EA = 4e6, EI = 4e4 (kN, m).")
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#666")
        v.addWidget(tip)
        self.form = Form(spec, unit)
        self.form.load(self.st)
        v.addWidget(self.form)
        from PySide6.QtWidgets import QListWidget, QListWidgetItem
        self.stages = QListWidget()
        stress = [a for a in (project.analyses if project else []) if a.kind == "stress"]
        for a in stress:
            it = QListWidgetItem(a.name)
            it.setData(Qt.UserRole, a.id)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            on = not self.st.analyses or a.id in self.st.analyses
            it.setCheckState(Qt.Checked if on else Qt.Unchecked)
            self.stages.addItem(it)
        if stress:
            v.addWidget(QLabel("Present in these stress stages:"))
            self.stages.setMaximumHeight(120)
            v.addWidget(self.stages)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.try_accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def try_accept(self):
        try:
            self.form.store(self.st)
            if self.st.EA <= 0 or self.st.spacing <= 0 or (self.st.type == "beam" and self.st.EI <= 0):
                raise ValueError("EA, EI (for beams) and spacing must be positive.")
        except ValueError as e:
            QMessageBox.warning(self, "Invalid input", str(e))
            return
        ids = [self.stages.item(i).data(Qt.UserRole) for i in range(self.stages.count())]
        on = [i for k, i in enumerate(ids) if self.stages.item(k).checkState() == Qt.Checked]
        self.st.analyses = [] if len(on) == len(ids) else on
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
        g.setFont(ui_font(8))
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
