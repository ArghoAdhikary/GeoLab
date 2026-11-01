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
from ..model import (BC_TYPES, MATERIAL_COLORS, PWP_MODES, SEARCH_MODES, SLOPE_METHODS, STRENGTH_MODELS,
                     UNIT_SYSTEMS, Material)


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
                       f"<br><span style='color:#555'>Slope stability and seepage analysis &nbsp; v{__version__}</span>")
        left.addWidget(title)
        left.addSpacing(14)
        self.units = QComboBox()
        self.units.addItem("Metric (m, kN, kPa)", "metric")
        self.units.addItem("Imperial (ft, lbf, psf)", "imperial")
        row = QHBoxLayout()
        row.addWidget(QLabel("Units for new projects:"))
        row.addWidget(self.units)
        left.addLayout(row)
        for label, action in (("New slope stability project", "new_slope"),
                              ("New seepage project", "new_seep"),
                              ("Open project...", "open"),
                              ("AI Slope Builder...", "ai")):
            b = QPushButton(label)
            b.setMinimumHeight(40)
            b.setStyleSheet("text-align:left;padding-left:14px;font-size:11pt")
            b.clicked.connect(lambda _=False, a=action: self.pick(a))
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
# Materials
# ---------------------------------------------------------------------------
MAT_COLS = [("name", "Name"), ("color", "Colour"), ("model", "Strength model"), ("unit_weight", "Unit weight"),
            ("cohesion", "Cohesion"), ("phi", "Phi (deg)"), ("cohesion_sd", "c std dev"), ("phi_sd", "phi std dev"),
            ("unit_weight_sd", "Unit wt std dev"), ("k_sat", "k sat"), ("k_ratio", "ky/kx"), ("unsat_alpha", "Unsat alpha")]


class MaterialsDialog(QDialog):
    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Define Materials")
        self.resize(1080, 380)
        self.p = project
        self.mats = copy.deepcopy(project.materials)
        v = QVBoxLayout(self)
        u = project.unit
        hint = QLabel(f"Unit weight in {u('unit_weight')}, cohesion in {u('pressure')}, k sat in {u('k')}. "
                      "Standard deviations are used by probabilistic analyses.")
        hint.setStyleSheet("color:#555")
        v.addWidget(hint)
        self.table = QTableWidget(0, len(MAT_COLS))
        self.table.setHorizontalHeaderLabels([c[1] for c in MAT_COLS])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.setColumnWidth(0, 150)
        self.table.setColumnWidth(2, 170)
        self.table.cellDoubleClicked.connect(self.pick_color)
        v.addWidget(self.table)
        row = QHBoxLayout()
        add = QPushButton("Add")
        add.clicked.connect(self.add)
        dele = QPushButton("Delete")
        dele.clicked.connect(self.delete)
        row.addWidget(add)
        row.addWidget(dele)
        row.addStretch(1)
        v.addLayout(row)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.try_accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        for m in self.mats:
            self._append(m)

    def _append(self, m: Material):
        r = self.table.rowCount()
        self.table.insertRow(r)
        for c, (key, _) in enumerate(MAT_COLS):
            val = getattr(m, key)
            if key == "model":
                cb = combo(STRENGTH_MODELS, val)
                self.table.setCellWidget(r, c, cb)
                continue
            it = QTableWidgetItem("" if key == "color" else (f"{val:g}" if isinstance(val, float) else str(val)))
            if key == "color":
                it.setBackground(QColor(val))
                it.setData(Qt.UserRole, val)
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(r, c, it)
        self.table.setVerticalHeaderItem(r, QTableWidgetItem(str(m.id)))

    def pick_color(self, r, c):
        if MAT_COLS[c][0] != "color":
            return
        it = self.table.item(r, c)
        col = QColorDialog.getColor(QColor(it.data(Qt.UserRole)), self)
        if col.isValid():
            it.setBackground(col)
            it.setData(Qt.UserRole, col.name())

    def add(self):
        mid = max([m.id for m in self.mats] + [int(self.table.verticalHeaderItem(r).text()) for r in range(self.table.rowCount())] + [0]) + 1
        m = Material(id=mid, name=f"Soil {mid}", color=MATERIAL_COLORS[(mid - 1) % len(MATERIAL_COLORS)])
        self._append(m)

    def delete(self):
        r = self.table.currentRow()
        if r < 0:
            return
        mid = int(self.table.verticalHeaderItem(r).text())
        used = [reg.id for reg in self.p.regions if reg.material_id == mid]
        if used:
            QMessageBox.warning(self, "In use", f"This material is assigned to region(s) {used}. "
                                "Assign another material first.")
            return
        self.table.removeRow(r)

    def collect(self) -> list[Material]:
        out = []
        for r in range(self.table.rowCount()):
            kw = {"id": int(self.table.verticalHeaderItem(r).text())}
            for c, (key, label) in enumerate(MAT_COLS):
                if key == "model":
                    kw[key] = self.table.cellWidget(r, c).currentData()
                elif key == "color":
                    kw[key] = self.table.item(r, c).data(Qt.UserRole)
                elif key == "name":
                    kw[key] = self.table.item(r, c).text().strip() or f"Soil {kw['id']}"
                else:
                    txt = self.table.item(r, c).text()
                    try:
                        kw[key] = float(txt)
                    except ValueError:
                        raise ValueError(f"Row {r + 1}: '{txt}' is not a number for {label}.")
            m = Material(**kw)
            if m.unit_weight <= 0:
                raise ValueError(f"{m.name}: unit weight must be positive.")
            if m.cohesion < 0 or not 0 <= m.phi < 90:
                raise ValueError(f"{m.name}: cohesion must be >= 0 and phi between 0 and 90 degrees.")
            if min(m.cohesion_sd, m.phi_sd, m.unit_weight_sd) < 0:
                raise ValueError(f"{m.name}: standard deviations cannot be negative.")
            if m.k_sat <= 0 or m.k_ratio <= 0:
                raise ValueError(f"{m.name}: k sat and ky/kx must be positive.")
            out.append(m)
        if not out:
            raise ValueError("Define at least one material.")
        return out

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
class AnalysisDialog(QDialog):
    def __init__(self, project, analysis, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Analysis Settings - {analysis.name}")
        self.p, self.a = project, analysis
        a = analysis
        v = QVBoxLayout(self)
        tabs = QTabWidget()
        v.addWidget(tabs)

        g = QWidget(); f = QFormLayout(g)
        self.name = QLineEdit(a.name)
        self.desc = QLineEdit(a.description)
        self.kind = QLabel("Slope stability (limit equilibrium)" if a.kind == "slope" else "Seepage (FE, steady state)")
        self.parent_cb = QComboBox()
        self.parent_cb.addItem("(none)", None)
        for o in project.analyses:
            if o.id != a.id and o.kind == "seepage":
                self.parent_cb.addItem(o.name, o.id)
        self.parent_cb.setCurrentIndex(max(0, self.parent_cb.findData(a.parent_id)))
        f.addRow("Name", self.name)
        f.addRow("Type", self.kind)
        f.addRow("Description", self.desc)
        f.addRow("Parent analysis", self.parent_cb)
        tabs.addTab(g, "General")

        if a.kind == "slope":
            t = QWidget(); f = QFormLayout(t)
            self.method = combo(SLOPE_METHODS, a.method)
            self.inter = combo({"half_sine": "Half-sine", "constant": "Constant"}, a.interslice)
            self.nsl = ispin(a.n_slices, 5, 200)
            self.pwp = combo(PWP_MODES, a.pwp)
            self.ru = dspin(a.ru, 0, 1, 3, 0.05)
            self.kh = dspin(a.kh, 0, 1, 3, 0.01)
            f.addRow("Method", self.method)
            f.addRow("Interslice function (M-P)", self.inter)
            f.addRow("Number of slices", self.nsl)
            f.addRow("Pore-water pressure", self.pwp)
            f.addRow("Ru", self.ru)
            f.addRow("Seismic coefficient kh", self.kh)
            tabs.addTab(t, "Slope Stability")

            s = a.search
            t = QWidget(); grid = QGridLayout(t)
            self.mode = combo(SEARCH_MODES, s.mode)
            grid.addWidget(QLabel("Slip surface"), 0, 0); grid.addWidget(self.mode, 0, 1, 1, 3)
            self.sf = {}
            fields = [("entry_x1", "Entry x from"), ("entry_x2", "Entry x to"), ("exit_x1", "Exit x from"),
                      ("exit_x2", "Exit x to"), ("n_entry", "Entry increments"), ("n_exit", "Exit increments"),
                      ("n_radius", "Radius increments"), ("grid_x1", "Grid x1"), ("grid_y1", "Grid y1"),
                      ("grid_x2", "Grid x2"), ("grid_y2", "Grid y2"), ("grid_nx", "Grid x increments"),
                      ("grid_ny", "Grid y increments"), ("radius_min", "Radius min"), ("radius_max", "Radius max"),
                      ("n_radii", "Radius increments (grid)"), ("min_depth", "Minimum slip depth")]
            for i, (key, label) in enumerate(fields):
                val = getattr(s, key)
                w = ispin(val, 1, 500) if isinstance(val, int) else dspin(val, -1e7, 1e7, 3)
                self.sf[key] = w
                grid.addWidget(QLabel(label), 1 + i // 2, (i % 2) * 2)
                grid.addWidget(w, 1 + i // 2, (i % 2) * 2 + 1)
            r = 2 + len(fields) // 2
            grid.addWidget(QLabel("Fully specified circles (xc, yc, R per line)"), r, 0, 1, 4)
            self.circles = QPlainTextEdit("\n".join(", ".join(f"{v:g}" for v in c[:3]) for c in s.circles))
            self.circles.setMaximumHeight(70)
            grid.addWidget(self.circles, r + 1, 0, 1, 4)
            grid.addWidget(QLabel("Fully specified polyline (x, y per line; blank line separates surfaces)"), r + 2, 0, 1, 4)
            self.polys = QPlainTextEdit("\n\n".join("\n".join(f"{x:g}, {y:g}" for x, y in pl) for pl in s.polylines))
            self.polys.setMaximumHeight(70)
            grid.addWidget(self.polys, r + 3, 0, 1, 4)
            auto = QPushButton("Auto entry/exit from geometry")
            auto.clicked.connect(self.auto)
            grid.addWidget(auto, r + 4, 0, 1, 2)
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
        else:
            t = QWidget(); f = QFormLayout(t)
            self.mesh = dspin(a.mesh_size, 1e-3, 1e5, 3, 0.25)
            self.unsat = QCheckBox("Include unsaturated flow (free phreatic surface)")
            self.unsat.setChecked(a.unsaturated)
            self.maxit = ispin(a.max_iter, 1, 10000)
            self.tol = dspin(a.tolerance, 1e-9, 1, 8, 1e-4)
            f.addRow("Mesh element size", self.mesh)
            f.addRow(self.unsat)
            f.addRow("Max iterations", self.maxit)
            f.addRow("Head tolerance", self.tol)
            tabs.addTab(t, "Seepage")

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.try_accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

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
        a = self.a
        try:
            if a.kind == "slope":
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
                if self.pwp.currentData() == "seepage" and self.parent_cb.currentData() is None:
                    raise ValueError("Pore pressure 'From seepage analysis' needs a parent seepage analysis.")
        except ValueError as e:
            QMessageBox.warning(self, "Invalid input", str(e))
            return
        a.name = self.name.text().strip() or a.name
        a.description = self.desc.text().strip()
        a.parent_id = self.parent_cb.currentData()
        if a.kind == "slope":
            a.method = self.method.currentData()
            a.interslice = self.inter.currentData()
            a.n_slices = self.nsl.value()
            a.pwp = self.pwp.currentData()
            a.ru = self.ru.value()
            a.kh = self.kh.value()
            s = a.search
            s.mode = self.mode.currentData()
            for k, w in self.sf.items():
                setattr(s, k, w.value())
            s.circles = circles
            s.polylines = polys
            a.probabilistic = self.prob.isChecked()
            a.n_samples = self.ns.value()
            a.seed = self.seed.value()
            a.sensitivity_param = self.sens.currentData()
            a.sensitivity_low, a.sensitivity_high = self.slo.value(), self.shi.value()
            a.sensitivity_steps = self.sst.value()
        else:
            a.mesh_size = self.mesh.value()
            a.unsaturated = self.unsat.isChecked()
            a.max_iter = self.maxit.value()
            a.tolerance = self.tol.value()
        self.accept()


# ---------------------------------------------------------------------------
# Small editors
# ---------------------------------------------------------------------------
class BCDialog(QDialog):
    def __init__(self, name="BC", type_="head", value=0.0, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Boundary Condition")
        f = QFormLayout(self)
        self.name = QLineEdit(name)
        self.type = combo(BC_TYPES, type_)
        self.value = dspin(value, -1e9, 1e9, 6)
        f.addRow("Name", self.name)
        f.addRow("Type", self.type)
        f.addRow("Value", self.value)
        f.addRow(QLabel("Head / pressure head in length units; flux per unit length (inflow positive)."))
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)


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
