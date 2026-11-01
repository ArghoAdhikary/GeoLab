"""Main application window."""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QThread, Signal
from PySide6.QtGui import QAction, QActionGroup, QGuiApplication, QImage, QKeySequence, QPainter
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QDockWidget, QFileDialog, QInputDialog, QLabel,
                               QMainWindow, QMenu, QMessageBox, QPlainTextEdit, QProgressBar, QStyle,
                               QTextBrowser, QToolBar, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from .. import APP_NAME, FILE_EXT, __version__
from ..examples import EXAMPLES
from ..fileio import export_json, export_results_csv, import_points_csv, load_project, save_project
from ..geometry import polygon_area
from ..model import BC_TYPES, SLOPE_METHODS, Project, new_project
from ..report import build_report
from ..solver import solve, verify
from .canvas import Canvas
from .dialogs import (AIDialog, AnalysisDialog, BCDialog, GraphDialog, MaterialsDialog, PointsDialog,
                      ProjectDialog, SliceTable, StartPage, TextDialog)
from .pdf import export_pdf, paint_pages
from .render import Renderer, View, project_bounds

FILTER = f"{APP_NAME} project (*{FILE_EXT});;JSON project (*.json)"
MAX_UNDO = 60


class SolveWorker(QThread):
    progress = Signal(int)
    finished_solve = Signal(str)

    def __init__(self, project, analyses):
        super().__init__()
        self.project, self.analyses = project, analyses
        self.cancelled = False

    def run(self):
        errors = []
        for a in self.analyses:
            try:
                solve(self.project, a, self.progress.emit, lambda: self.cancelled)
            except Exception as e:
                a.results = None
                errors.append(f"{a.name}: {e}")
                if self.cancelled:
                    break
        self.finished_solve.emit("\n".join(errors))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("StrataLab", "StrataLab")
        self.project: Project = new_project()
        self.path: Path | None = None
        self.dirty = False
        self.undo_stack: list[dict] = []
        self.redo_stack: list[dict] = []
        self.current_aid = self.project.analyses[0].id
        self.view_mode = "define"
        self.opts = {"grid": True, "snap": True, "mesh": False, "slices": True, "trials": True,
                     "vectors": True, "contour": "head", "axes": True, "labels": True}
        self.current_material_id = self.project.materials[0].id
        self.bc_params = ("Head", "head", 10.0)
        self.point_load = (100.0, 0.0)
        self.surcharge_q = 10.0
        self.worker = None
        self.setWindowTitle(APP_NAME)
        self.resize(1360, 860)
        self.canvas = Canvas(self)
        self.setCentralWidget(self.canvas)
        self._build_docks()
        self._build_actions()
        self._build_menus()
        self._build_toolbars()
        self._build_status()
        self.canvas.status.connect(self.mode_label.setText)
        self.canvas.coords.connect(lambda x, y: self.xy_label.setText(f"x: {x:.3f}   y: {y:.3f}"))
        geom = self.settings.value("window/geometry")
        if geom is not None:
            self.restoreGeometry(geom)
        self.refresh_all()

    # ------------------------------------------------------------------
    # construction
    # ------------------------------------------------------------------
    def _build_docks(self):
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Analyses"])
        self.tree.itemSelectionChanged.connect(self.tree_selected)
        self.tree.itemDoubleClicked.connect(lambda *_: self.edit_analysis())
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.tree_menu)
        d = QDockWidget("Project Explorer", self)
        d.setObjectName("explorer")
        d.setWidget(self.tree)
        self.addDockWidget(Qt.LeftDockWidgetArea, d)
        self.explorer_dock = d

        self.props = QTextBrowser()
        d2 = QDockWidget("Properties", self)
        d2.setObjectName("properties")
        d2.setWidget(self.props)
        self.addDockWidget(Qt.LeftDockWidgetArea, d2)
        self.props_dock = d2

        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 4, 4, 4)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        lay.addWidget(self.progress)
        lay.addWidget(self.log)
        d3 = QDockWidget("Solve Manager", self)
        d3.setObjectName("solve")
        d3.setWidget(w)
        self.addDockWidget(Qt.BottomDockWidgetArea, d3)
        self.solve_dock = d3
        self.default_state = None

    def act(self, text, slot=None, shortcut=None, icon=None, checkable=False, tip=None):
        a = QAction(text, self)
        if icon is not None:
            a.setIcon(self.style().standardIcon(icon))
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        if checkable:
            a.setCheckable(True)
        if slot:
            a.triggered.connect(slot)
        if tip:
            a.setStatusTip(tip)
        return a

    def _build_actions(self):
        S = QStyle.StandardPixmap
        A = self.act
        self.a_new = A("&New Slope Project", lambda: self.new_file("slope"), "Ctrl+N", S.SP_FileIcon)
        self.a_new_seep = A("New &Seepage Project", lambda: self.new_file("seepage"))
        self.a_open = A("&Open...", self.open_file, "Ctrl+O", S.SP_DialogOpenButton)
        self.a_save = A("&Save", self.save, "Ctrl+S", S.SP_DialogSaveButton)
        self.a_save_as = A("Save &As...", self.save_as, "Ctrl+Shift+S")
        self.a_pdf = A("Export &PDF...", self.export_pdf, "Ctrl+E", S.SP_FileDialogDetailedView)
        self.a_png = A("Export &Image (PNG)...", self.export_png)
        self.a_csv = A("Export Results (&CSV)...", self.export_csv)
        self.a_json = A("Export Project (&JSON)...", self.export_json)
        self.a_import = A("&Import Region Points (CSV)...", self.import_points)
        self.a_print = A("&Print...", self.print_doc, "Ctrl+P")
        self.a_clear = A("&Delete All Results", self.delete_results)
        self.a_exit = A("E&xit", self.close, "Ctrl+Q")
        self.a_undo = A("&Undo", self.undo, "Ctrl+Z", S.SP_ArrowBack)
        self.a_redo = A("&Redo", self.redo, "Ctrl+Y", S.SP_ArrowForward)
        self.a_copy = A("&Copy Image", self.copy_image, "Ctrl+Shift+C")
        self.a_del_region = A("Delete Selected Region", lambda: self.delete_region(self.canvas.selected_region))
        self.a_edit_points = A("Edit Region &Points...", self.edit_region_points)
        self.a_fit = A("Zoom to &Fit", self.canvas.zoom_fit, "F", S.SP_BrowserReload)
        self.a_zin = A("Zoom &In", lambda: self.zoom(1.25), "Ctrl+=")
        self.a_zout = A("Zoom &Out", lambda: self.zoom(0.8), "Ctrl+-")
        self.a_define = A("&Definition View", lambda: self.set_view("define"), "Ctrl+1", checkable=True)
        self.a_results = A("&Results View", lambda: self.set_view("results"), "Ctrl+2", checkable=True)
        g = QActionGroup(self)
        g.addAction(self.a_define)
        g.addAction(self.a_results)
        self.a_define.setChecked(True)
        self.opt_actions = {}
        for key, label in (("grid", "Show &Grid"), ("snap", "S&nap to Grid"), ("mesh", "Show &Mesh"),
                           ("slices", "Show S&lices"), ("trials", "Show &Trial Slip Surfaces"),
                           ("vectors", "Show Flow &Vectors"), ("axes", "Show &Axes")):
            a = A(label, checkable=True)
            a.setChecked(self.opts[key])
            a.toggled.connect(lambda on, k=key: self.set_opt(k, on))
            self.opt_actions[key] = a
        self.a_contour_h = A("Contour Total &Head", lambda: self.set_opt("contour", "head"), checkable=True)
        self.a_contour_p = A("Contour Pressure H&ead", lambda: self.set_opt("contour", "pressure"), checkable=True)
        gc = QActionGroup(self)
        gc.addAction(self.a_contour_h)
        gc.addAction(self.a_contour_p)
        self.a_contour_h.setChecked(True)
        self.a_report = A("&Report...", self.show_report, "Ctrl+R")
        self.a_slices = A("&Slice Information...", self.show_slices)
        self.a_graph = A("&Graph...", self.show_graph)
        self.a_proj = A("&Project Properties...", self.edit_project)
        self.a_mats = A("&Materials...", self.edit_materials, "Ctrl+M")
        self.a_analysis = A("&Analysis Settings...", self.edit_analysis, "Ctrl+Shift+A")
        self.a_add_slope = A("Add Slope Stability Analysis", lambda: self.add_analysis("slope"))
        self.a_add_seep = A("Add Seepage Analysis", lambda: self.add_analysis("seepage"))
        self.a_add_child = A("Add Slope Analysis Using This Seepage", lambda: self.add_analysis("slope", child=True))
        self.a_del_analysis = A("Delete Analysis", self.delete_analysis)
        self.a_bcs = A("&Boundary Conditions...", self.edit_bcs)
        self.a_piezo_pts = A("Piezometric Line &Points...", self.edit_piezo)
        self.a_loads = A("&Loads...", self.edit_loads)
        self.draw_group = QActionGroup(self)
        self.draw_actions = {}
        for mode, label, key in (("select", "&Select", "Esc"), ("region", "&Regions", "Ctrl+Shift+R"),
                                 ("assign", "&Materials", None), ("piezo", "&Piezometric Line", None),
                                 ("bc", "&Boundary Conditions", None), ("point_load", "Point &Loads", None),
                                 ("surcharge", "S&urcharge Loads", None), ("entry_exit", "Slip Surface &Entry and Exit", None),
                                 ("grid", "Slip Surface &Grid", None), ("text", "Sketch &Text", None), ("pan", "Pa&n", None)):
            a = A(label, lambda _=False, m=mode: self.set_draw_mode(m), key, checkable=True)
            self.draw_group.addAction(a)
            self.draw_actions[mode] = a
        self.draw_actions["select"].setChecked(True)
        self.a_verify = A("&Verify", self.verify_current, "F6", S.SP_DialogApplyButton)
        self.a_solve = A("&Solve Analysis", self.solve_current, "F5", S.SP_MediaPlay)
        self.a_solve_all = A("Solve &All", self.solve_all, "Shift+F5", S.SP_MediaSeekForward)
        self.a_stop = A("S&top", self.stop_solve, None, S.SP_MediaStop)
        self.a_stop.setEnabled(False)
        self.a_ai = A("AI &Slope Builder...", self.ai_builder, "Ctrl+Shift+I")
        self.a_reset = A("&Reset Window Layout", self.reset_layout)
        self.a_start = A("&Start Page...", self.show_start)
        self.a_guide = A("&Quick Guide", self.quick_guide, "F1")
        self.a_about = A("&About", self.about)

    def _build_menus(self):
        mb = self.menuBar()
        m = mb.addMenu("&File")
        for a in (self.a_new, self.a_new_seep, self.a_open):
            m.addAction(a)
        ex = m.addMenu("Open &Example")
        for name in EXAMPLES:
            ex.addAction(name, lambda n=name: self.open_example(n))
        self.recent_menu = m.addMenu("Recent &Files")
        self.recent_menu.aboutToShow.connect(self.fill_recent)
        m.addSeparator()
        m.addAction(self.a_save)
        m.addAction(self.a_save_as)
        m.addSeparator()
        m.addAction(self.a_import)
        exp = m.addMenu("E&xport")
        for a in (self.a_pdf, self.a_png, self.a_csv, self.a_json):
            exp.addAction(a)
        m.addAction(self.a_print)
        m.addSeparator()
        m.addAction(self.a_clear)
        m.addSeparator()
        m.addAction(self.a_exit)

        m = mb.addMenu("&Edit")
        for a in (self.a_undo, self.a_redo, None, self.a_copy, None, self.a_edit_points, self.a_del_region):
            m.addSeparator() if a is None else m.addAction(a)

        m = mb.addMenu("&View")
        for a in (self.a_define, self.a_results, None, self.a_fit, self.a_zin, self.a_zout, None):
            m.addSeparator() if a is None else m.addAction(a)
        for a in self.opt_actions.values():
            m.addAction(a)
        m.addSeparator()
        m.addAction(self.a_contour_h)
        m.addAction(self.a_contour_p)
        m.addSeparator()
        m.addAction(self.a_report)
        m.addAction(self.a_slices)
        m.addAction(self.a_graph)

        m = mb.addMenu("&Define")
        for a in (self.a_proj, self.a_mats, self.a_analysis, None, self.a_add_slope, self.a_add_seep,
                  self.a_add_child, self.a_del_analysis, None, self.a_bcs, self.a_piezo_pts, self.a_loads):
            m.addSeparator() if a is None else m.addAction(a)

        m = mb.addMenu("D&raw")
        for mode, a in self.draw_actions.items():
            m.addAction(a)
            if mode in ("select", "assign", "surcharge", "grid"):
                m.addSeparator()

        m = mb.addMenu("&Analysis")
        for a in (self.a_verify, self.a_solve, self.a_solve_all, self.a_stop):
            m.addAction(a)

        m = mb.addMenu("A&I")
        m.addAction(self.a_ai)

        self.window_menu = mb.addMenu("&Window")
        for d in (self.explorer_dock, self.props_dock, self.solve_dock):
            self.window_menu.addAction(d.toggleViewAction())
        self.window_menu.addSeparator()
        self.window_menu.addAction(self.a_reset)
        self.window_menu.addAction(self.a_start)

        m = mb.addMenu("&Help")
        m.addAction(self.a_guide)
        m.addAction(self.a_about)

    def _build_toolbars(self):
        def tb(name, actions):
            t = QToolBar(name, self)
            t.setObjectName(name)
            for a in actions:
                t.addSeparator() if a is None else t.addAction(a)
            self.addToolBar(t)
            self.window_menu.insertAction(self.window_menu.actions()[0], t.toggleViewAction())
            return t
        tb("File", [self.a_new, self.a_open, self.a_save, None, self.a_pdf, self.a_undo, self.a_redo])
        tb("Mode", [self.a_define, self.a_results, None, self.a_fit])
        tb("Solve", [self.a_verify, self.a_solve, self.a_solve_all, self.a_stop])
        self.addToolBarBreak()
        t = tb("Draw", [self.draw_actions[k] for k in ("select", "region", "assign", "piezo", "bc", "point_load",
                                                        "surcharge", "entry_exit", "grid", "text", "pan")])
        t.addSeparator()
        t.addWidget(QLabel(" Material: "))
        self.mat_combo = QComboBox()
        self.mat_combo.setMinimumWidth(150)
        self.mat_combo.activated.connect(lambda i: setattr(self, "current_material_id", self.mat_combo.itemData(i)))
        t.addWidget(self.mat_combo)
        tb("AI", [self.a_ai])

    def _build_status(self):
        self.mode_label = QLabel("")
        self.xy_label = QLabel("")
        self.units_label = QLabel("")
        sb = self.statusBar()
        sb.addWidget(self.mode_label, 1)
        sb.addPermanentWidget(self.xy_label)
        sb.addPermanentWidget(self.units_label)

    def showEvent(self, e):
        if self.default_state is None:
            from PySide6.QtCore import QTimer

            def size_docks():
                self.resizeDocks([self.solve_dock], [130], Qt.Vertical)
                self.resizeDocks([self.explorer_dock], [320], Qt.Horizontal)
            QTimer.singleShot(0, size_docks)
            self.default_state = self.saveState()
            st = self.settings.value("window/state")
            if st is not None:
                self.restoreState(st)
        super().showEvent(e)

    # ------------------------------------------------------------------
    # state helpers used by the canvas
    # ------------------------------------------------------------------
    def current_analysis(self):
        return self.project.analysis(self.current_aid)

    def before_change(self):
        self.undo_stack.append(self.project.to_dict())
        if len(self.undo_stack) > MAX_UNDO:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def after_change(self, desc="Edit", keep_results=False):
        if not keep_results:
            self.project.clear_results()
            if self.view_mode == "results":
                self.set_view("define")
        self.dirty = True
        self.log_msg(desc)
        self.refresh_all()

    def load_params(self):
        return self.point_load

    def surcharge_value(self):
        return self.surcharge_q

    def region_selected(self, r):
        if r is None:
            self.refresh_props()
            return
        m = self.project.material(r.material_id)
        u = self.project.unit("length")
        pts = "".join(f"<tr><td>{i + 1}</td><td>{x:g}</td><td>{y:g}</td></tr>" for i, (x, y) in enumerate(r.points))
        self.props.setHtml(f"<b>Region {r.id}</b><br>Material: {m.name if m else '<i>none</i>'}<br>"
                           f"Area: {abs(polygon_area(r.points)):.3f} {u}²<br>"
                           f"<table cellpadding=2><tr><th>#</th><th>x</th><th>y</th></tr>{pts}</table>")

    def add_region(self, pts):
        if abs(polygon_area(pts)) < 1e-9:
            self.log_msg("Region ignored: zero area.")
            return
        if polygon_area(pts) < 0:
            pts = list(reversed(pts))
        self.before_change()
        self.project.add_region(pts, self.current_material_id)
        self.after_change("Add region")

    def delete_region(self, rid):
        if rid is None:
            return
        self.before_change()
        self.project.regions = [r for r in self.project.regions if r.id != rid]
        self.canvas.selected_region = None
        self.after_change("Delete region")

    def add_bc(self, pts):
        name, typ, val = self.bc_params
        self.before_change()
        n = sum(1 for b in self.project.boundary_conditions if b.name.startswith(name))
        self.project.add_bc(name if n == 0 else f"{name} {n + 1}", typ, val, pts)
        self.after_change("Add boundary condition")

    def add_text(self, x, y):
        text, ok = QInputDialog.getText(self, "Sketch Text", "Text:")
        if ok and text.strip():
            from ..model import SketchText
            self.before_change()
            self.project.sketch_texts.append(SketchText(x, y, text.strip()))
            self.after_change("Add text", keep_results=True)

    def show_result_info(self, x, y):
        a = self.current_analysis()
        r = a.results if a else None
        if not r:
            return
        if r["type"] == "seepage":
            import numpy as np
            from scipy.interpolate import LinearNDInterpolator
            nodes = np.asarray(r["nodes"])
            h = float(LinearNDInterpolator(nodes, r["head"])(x, y))
            if np.isnan(h):
                return
            u = self.project.unit
            self.props.setHtml(f"<b>Result at ({x:.3f}, {y:.3f})</b><br>Total head: {h:.4f} {u('length')}<br>"
                               f"Pressure head: {h - y:.4f} {u('length')}<br>"
                               f"Pore-water pressure: {(h - y) * self.project.gamma_w:.3f} {u('pressure')}")
        else:
            self.refresh_props()

    # ------------------------------------------------------------------
    # refresh
    # ------------------------------------------------------------------
    def refresh_all(self):
        self.refresh_tree()
        self.refresh_props()
        self.mat_combo.clear()
        for m in self.project.materials:
            self.mat_combo.addItem(m.name, m.id)
        if self.project.material(self.current_material_id) is None and self.project.materials:
            self.current_material_id = self.project.materials[0].id
        self.mat_combo.setCurrentIndex(max(0, self.mat_combo.findData(self.current_material_id)))
        self.units_label.setText(f"Units: {self.project.units}")
        self.a_undo.setEnabled(bool(self.undo_stack))
        self.a_redo.setEnabled(bool(self.redo_stack))
        name = self.path.name if self.path else "Untitled"
        self.setWindowTitle(f"{name}{' *' if self.dirty else ''} - {self.project.title} - {APP_NAME}")
        self.canvas.update()

    def refresh_tree(self):
        self.tree.blockSignals(True)
        self.tree.clear()
        items = {}

        def label(a):
            r = a.results
            if a.kind == "slope":
                s = f"{a.name}  [{SLOPE_METHODS[a.method]}]"
                if r and r.get("critical"):
                    s += f"  F = {r['critical']['fos']:.3f}"
            else:
                s = f"{a.name}  [Seepage]"
                if r:
                    s += "  solved" if r["converged"] else "  not converged"
            return s

        def add(a, parent):
            it = QTreeWidgetItem([label(a)])
            it.setData(0, Qt.UserRole, a.id)
            (parent.addChild(it) if parent else self.tree.addTopLevelItem(it))
            items[a.id] = it
            for c in self.project.children(a.id):
                add(c, it)

        for a in self.project.analyses:
            if self.project.analysis(a.parent_id) is None:
                add(a, None)
        self.tree.expandAll()
        if self.current_aid in items:
            self.tree.setCurrentItem(items[self.current_aid])
        self.tree.blockSignals(False)

    def refresh_props(self):
        a = self.current_analysis()
        if not a:
            self.props.setHtml("")
            return
        p = self.project
        html = [f"<b>{a.name}</b><br>"]
        if a.kind == "slope":
            html.append(f"Method: {SLOPE_METHODS[a.method]}<br>Search: {a.search.mode.replace('_', ' ')}<br>")
        r = a.results
        if not r:
            html.append("<i>Not solved. Press F5 to solve.</i>")
        elif r["type"] == "slope":
            c = r.get("critical")
            if c:
                html.append(f"<span style='font-size:16pt'><b>F = {c['fos']:.3f}</b></span><br>")
                html.append(f"Valid trial surfaces: {r['n_valid']} of {r['n_total']}<br><table>")
                for m, v in c["all_methods"].items():
                    val = "-" if v["fos"] is None else f"{v['fos']:.3f}"
                    html.append(f"<tr><td>{SLOPE_METHODS[m]}</td><td align=right>{val}</td></tr>")
                html.append("</table>")
                pr = r.get("probability")
                if pr and pr.get("n"):
                    html.append(f"<br>Mean F {pr['mean']:.3f}, P(failure) {100 * pr['pf']:.2f} %")
            else:
                html.append(f"<span style='color:#a00'>{r.get('message', 'No valid slip surface')}</span>")
        else:
            html.append(f"Converged: {'yes' if r['converged'] else '<b>no</b>'} ({r['iterations']} iterations)<br>"
                        f"Inflow: {r['inflow']:.4e} {p.unit('flux')}<br>Outflow: {r['outflow']:.4e} {p.unit('flux')}<br>"
                        f"Nodes: {len(r['nodes'])}, elements: {len(r['tris'])}<br>"
                        "<i>Click the drawing to read values.</i>")
        self.props.setHtml("".join(html))

    def tree_selected(self):
        it = self.tree.currentItem()
        if it:
            self.current_aid = it.data(0, Qt.UserRole)
            if self.view_mode == "results" and not self.current_analysis().results:
                self.set_view("define")
            self.refresh_props()
            self.canvas.update()

    def tree_menu(self, pos):
        it = self.tree.itemAt(pos)
        m = QMenu(self)
        if it:
            self.current_aid = it.data(0, Qt.UserRole)
            m.addAction(self.a_analysis)
            m.addAction(self.a_solve)
            m.addAction("Rename...", self.rename_analysis)
            if self.current_analysis().kind == "seepage":
                m.addAction(self.a_add_child)
            m.addAction(self.a_del_analysis)
            m.addSeparator()
        m.addAction(self.a_add_slope)
        m.addAction(self.a_add_seep)
        m.exec(self.tree.viewport().mapToGlobal(pos))

    def log_msg(self, text):
        self.log.appendPlainText(text)

    # ------------------------------------------------------------------
    # view
    # ------------------------------------------------------------------
    def set_view(self, mode):
        if mode == "results":
            a = self.current_analysis()
            if not (a and a.results):
                self.a_define.setChecked(True)
                self.statusBar().showMessage("Solve the analysis to see results (F5).", 4000)
                mode = "define"
        self.view_mode = mode
        (self.a_results if mode == "results" else self.a_define).setChecked(True)
        self.canvas.update()

    def set_opt(self, key, value):
        self.opts[key] = value
        self.canvas.update()

    def zoom(self, f):
        r = self.canvas.rect()
        self.canvas.view.zoom(f, r.center().x(), r.center().y())
        self.canvas.update()

    def set_draw_mode(self, mode):
        if mode in ("entry_exit", "grid") and (self.current_analysis() is None or self.current_analysis().kind != "slope"):
            QMessageBox.information(self, APP_NAME, "Select a slope stability analysis first.")
            self.draw_actions["select"].setChecked(True)
            mode = "select"
        if mode == "bc":
            d = BCDialog(*self.bc_params, parent=self)
            if not d.exec():
                self.draw_actions["select"].setChecked(True)
                mode = "select"
            else:
                self.bc_params = (d.name.text().strip() or "BC", d.type.currentData(), d.value.value())
        if mode == "point_load":
            fy, ok = QInputDialog.getDouble(self, "Point Load", f"Vertical load ({self.project.unit('force')}, down +):",
                                            self.point_load[0], -1e9, 1e9, 3)
            if ok:
                self.point_load = (fy, 0.0)
        if mode == "surcharge":
            q, ok = QInputDialog.getDouble(self, "Surcharge", f"Pressure ({self.project.unit('pressure')}, down +):",
                                           self.surcharge_q, -1e9, 1e9, 3)
            if ok:
                self.surcharge_q = q
        if mode != "select" and self.view_mode == "results":
            self.set_view("define")
        self.canvas.set_mode(mode)

    # ------------------------------------------------------------------
    # files
    # ------------------------------------------------------------------
    def maybe_save(self) -> bool:
        if not self.dirty:
            return True
        r = QMessageBox.question(self, APP_NAME, "Save changes to the current project?",
                                 QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if r == QMessageBox.Save:
            return self.save()
        return r == QMessageBox.Discard

    def set_project(self, project, path=None, dirty=False):
        self.project = project
        self.path = Path(path) if path else None
        self.dirty = dirty
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.current_aid = project.analyses[0].id if project.analyses else None
        self.current_material_id = project.materials[0].id if project.materials else None
        self.canvas.selected_region = None
        self.view_mode = "define"
        self.a_define.setChecked(True)
        self.canvas.zoom_fit()
        self.refresh_all()

    def new_file(self, kind="slope", units=None):
        if not self.maybe_save():
            return
        self.set_project(new_project(units or self.project.units, kind))
        self.set_draw_mode("region")
        self.draw_actions["region"].setChecked(True)

    def open_file(self, path=None):
        if not self.maybe_save():
            return
        if not path:
            path, _ = QFileDialog.getOpenFileName(self, "Open Project", self.last_dir(), FILTER)
            if not path:
                return
        try:
            p = load_project(path)
        except Exception as e:
            QMessageBox.critical(self, "Open failed", str(e))
            return
        self.set_project(p, path)
        self.add_recent(path)
        self.log_msg(f"Opened {path}")

    def open_example(self, name):
        if not self.maybe_save():
            return
        self.set_project(EXAMPLES[name](), dirty=False)
        self.log_msg(f"Opened example: {name}")

    def save(self) -> bool:
        if self.path is None or self.path.suffix.lower() != FILE_EXT:
            return self.save_as()
        try:
            save_project(self.project, self.path)
        except OSError as e:
            QMessageBox.critical(self, "Save failed", str(e))
            return False
        self.dirty = False
        self.add_recent(str(self.path))
        self.refresh_all()
        self.statusBar().showMessage(f"Saved {self.path}", 3000)
        return True

    def save_as(self) -> bool:
        default = str(Path(self.last_dir()) / ((self.project.title or "project").replace("/", "-") + FILE_EXT))
        path, _ = QFileDialog.getSaveFileName(self, "Save Project As", default, f"{APP_NAME} project (*{FILE_EXT})")
        if not path:
            return False
        if not path.lower().endswith(FILE_EXT):
            path += FILE_EXT
        self.path = Path(path)
        return self.save()

    def last_dir(self):
        return self.settings.value("files/last_dir", str(Path.home()))

    def add_recent(self, path):
        rec = [p for p in (self.settings.value("files/recent", []) or []) if p != str(path)]
        rec.insert(0, str(path))
        self.settings.setValue("files/recent", rec[:10])
        self.settings.setValue("files/last_dir", str(Path(path).parent))

    def recent_files(self):
        rec = self.settings.value("files/recent", []) or []
        if isinstance(rec, str):
            rec = [rec]
        return [p for p in rec if os.path.exists(p)]

    def fill_recent(self):
        self.recent_menu.clear()
        for p in self.recent_files():
            self.recent_menu.addAction(p, lambda path=p: self.open_file(path))
        if not self.recent_menu.actions():
            self.recent_menu.addAction("(none)").setEnabled(False)

    def _ask_save(self, title, ext, filt):
        base = (self.project.title or "project").replace("/", "-")
        path, _ = QFileDialog.getSaveFileName(self, title, str(Path(self.last_dir()) / (base + ext)), filt)
        if path and not path.lower().endswith(ext):
            path += ext
        return path

    def export_pdf(self):
        path = self._ask_save("Export PDF", ".pdf", "PDF (*.pdf)")
        if not path:
            return
        try:
            mode = "results" if (self.current_analysis() and self.current_analysis().results) else "define"
            export_pdf(path, self.project, self.current_analysis(), mode, self.opts)
        except Exception as e:
            QMessageBox.critical(self, "Export failed", str(e))
            return
        self.log_msg(f"Exported PDF: {path}")

    def render_image(self, w=1800, h=1100) -> QImage:
        img = QImage(w, h, QImage.Format_ARGB32)
        img.fill(Qt.white)
        g = QPainter(img)
        v = View()
        from PySide6.QtCore import QRectF
        v.fit(project_bounds(self.project), QRectF(0, 0, w, h))
        o = dict(self.opts)
        o.update({"grid": False, "screen": True})
        Renderer(self.project, self.current_analysis(), v, g, mode=self.view_mode, opts=o).draw()
        g.end()
        return img

    def export_png(self):
        path = self._ask_save("Export Image", ".png", "PNG image (*.png)")
        if path:
            if not self.render_image().save(path):
                QMessageBox.critical(self, "Export failed", f"Could not write {path}")
            else:
                self.log_msg(f"Exported image: {path}")

    def copy_image(self):
        QGuiApplication.clipboard().setImage(self.render_image())
        self.statusBar().showMessage("Drawing copied to clipboard", 3000)

    def export_csv(self):
        a = self.current_analysis()
        if not (a and a.results):
            QMessageBox.information(self, APP_NAME, "Solve the analysis first.")
            return
        path = self._ask_save("Export Results", ".csv", "CSV (*.csv)")
        if path:
            try:
                export_results_csv(self.project, a, path)
                self.log_msg(f"Exported results: {path}")
            except Exception as e:
                QMessageBox.critical(self, "Export failed", str(e))

    def export_json(self):
        path = self._ask_save("Export Project JSON", ".json", "JSON (*.json)")
        if path:
            export_json(self.project, path)
            self.log_msg(f"Exported JSON: {path}")

    def import_points(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import Region Points", self.last_dir(), "CSV (*.csv *.txt)")
        if not path:
            return
        try:
            pts = import_points_csv(path)
        except Exception as e:
            QMessageBox.critical(self, "Import failed", str(e))
            return
        self.add_region(pts)
        self.canvas.zoom_fit()

    def print_doc(self):
        from PySide6.QtPrintSupport import QPrintDialog, QPrinter
        pr = QPrinter(QPrinter.HighResolution)
        pr.setPageOrientation(pr.pageLayout().Landscape)
        if QPrintDialog(pr, self).exec():
            mode = "results" if (self.current_analysis() and self.current_analysis().results) else "define"
            paint_pages(pr, self.project, self.current_analysis(), mode, self.opts, pr.newPage)

    def delete_results(self):
        self.project.clear_results()
        self.set_view("define")
        self.dirty = True
        self.refresh_all()

    # ------------------------------------------------------------------
    # edit
    # ------------------------------------------------------------------
    def undo(self):
        if not self.undo_stack:
            return
        self.redo_stack.append(self.project.to_dict())
        self.project = Project.from_dict(self.undo_stack.pop())
        self.dirty = True
        self._fix_current()
        self.refresh_all()

    def redo(self):
        if not self.redo_stack:
            return
        self.undo_stack.append(self.project.to_dict())
        self.project = Project.from_dict(self.redo_stack.pop())
        self.dirty = True
        self._fix_current()
        self.refresh_all()

    def _fix_current(self):
        if self.current_analysis() is None and self.project.analyses:
            self.current_aid = self.project.analyses[0].id
        if self.view_mode == "results" and not (self.current_analysis() and self.current_analysis().results):
            self.set_view("define")

    def edit_region_points(self):
        rid = self.canvas.selected_region
        r = next((r for r in self.project.regions if r.id == rid), None)
        d = PointsDialog("Region Points" if r else "New Region Points", r.points if r else [], self)
        if not d.exec():
            return
        if len(d.points) < 3:
            QMessageBox.warning(self, APP_NAME, "A region needs at least three points.")
            return
        if r is None:
            self.add_region(d.points)
            self.canvas.zoom_fit()
            return
        self.before_change()
        r.points = d.points if polygon_area(d.points) > 0 else list(reversed(d.points))
        self.after_change("Edit region points")

    # ------------------------------------------------------------------
    # define
    # ------------------------------------------------------------------
    def edit_project(self):
        d = ProjectDialog(self.project, self)
        if d.exec():
            self.before_change()
            d.apply()
            self.after_change("Project properties", keep_results=True)

    def edit_materials(self):
        d = MaterialsDialog(self.project, self)
        if d.exec():
            self.before_change()
            self.project.materials = d.result_mats
            self.after_change("Edit materials")

    def edit_analysis(self):
        a = self.current_analysis()
        if a is None:
            return
        before = self.project.to_dict()
        d = AnalysisDialog(self.project, a, self)
        if d.exec():
            self.undo_stack.append(before)
            self.redo_stack.clear()
            a.results = None
            for c in self.project.children(a.id):
                c.results = None
            self.dirty = True
            self.set_view("define")
            self.refresh_all()

    def add_analysis(self, kind, child=False):
        parent = self.current_analysis() if child else None
        if child and (parent is None or parent.kind != "seepage"):
            QMessageBox.information(self, APP_NAME, "Select a seepage analysis first.")
            return
        self.before_change()
        n = len(self.project.analyses) + 1
        if kind == "slope":
            a = self.project.add_analysis(f"Slope Stability {n}", "slope")
            if parent:
                a.parent_id, a.pwp, a.name = parent.id, "seepage", f"Stability ({parent.name})"
            if self.project.regions:
                from ..geometry import auto_entry_exit
                (e1, e2), (x1, x2) = auto_entry_exit(self.project)
                a.search.entry_x1, a.search.entry_x2, a.search.exit_x1, a.search.exit_x2 = e1, e2, x1, x2
            if self.project.piezometric_line and not parent:
                a.pwp = "piezometric"
        else:
            a = self.project.add_analysis(f"Seepage {n}", "seepage")
        self.current_aid = a.id
        self.after_change(f"Add analysis {a.name}", keep_results=True)
        self.edit_analysis()

    def rename_analysis(self):
        a = self.current_analysis()
        name, ok = QInputDialog.getText(self, "Rename", "Name:", text=a.name)
        if ok and name.strip():
            self.before_change()
            a.name = name.strip()
            self.after_change("Rename analysis", keep_results=True)

    def delete_analysis(self):
        a = self.current_analysis()
        if a is None:
            return
        if len(self.project.analyses) == 1:
            QMessageBox.information(self, APP_NAME, "A project needs at least one analysis.")
            return
        if QMessageBox.question(self, APP_NAME, f"Delete '{a.name}' and its child analyses?") != QMessageBox.Yes:
            return
        self.before_change()
        gone = {a.id}
        changed = True
        while changed:
            changed = False
            for x in self.project.analyses:
                if x.parent_id in gone and x.id not in gone:
                    gone.add(x.id)
                    changed = True
        self.project.analyses = [x for x in self.project.analyses if x.id not in gone]
        self.current_aid = self.project.analyses[0].id
        self.after_change("Delete analysis", keep_results=True)

    def edit_bcs(self):
        lines = [f"{b.name}; {b.type}; {b.value:g}; " + " ".join(f"{x:g},{y:g}" for x, y in b.points)
                 for b in self.project.boundary_conditions]
        d = TextEditDialog("Boundary Conditions",
                           "One per line:  name; type; value; x1,y1 x2,y2 ...\nTypes: " + ", ".join(BC_TYPES),
                           "\n".join(lines), self)
        if not d.exec():
            return
        bcs = []
        try:
            for line in d.text().splitlines():
                if not line.strip():
                    continue
                name, typ, val, pts = [s.strip() for s in line.split(";")]
                if typ not in BC_TYPES:
                    raise ValueError(f"Unknown type '{typ}'")
                pp = [[float(v) for v in p.split(",")] for p in pts.split()]
                if len(pp) < 2:
                    raise ValueError(f"'{name}' needs at least two points")
                bcs.append((name, typ, float(val), pp))
        except ValueError as e:
            QMessageBox.warning(self, "Invalid input", f"{e}\n\nLine: {line}")
            return
        self.before_change()
        self.project.boundary_conditions = []
        for b in bcs:
            self.project.add_bc(*b)
        self.after_change("Edit boundary conditions")

    def edit_piezo(self):
        d = PointsDialog("Piezometric Line", self.project.piezometric_line, self)
        if d.exec():
            if len(d.points) == 1:
                QMessageBox.warning(self, APP_NAME, "A piezometric line needs at least two points.")
                return
            self.before_change()
            self.project.piezometric_line = sorted(d.points)
            self.after_change("Edit piezometric line")

    def edit_loads(self):
        from ..model import PointLoad, Surcharge
        lines = [f"surcharge {s.x1:g} {s.x2:g} {s.q:g}" for s in self.project.surcharges]
        lines += [f"point {p.x:g} {p.fy:g} {p.fx:g}" for p in self.project.point_loads]
        d = TextEditDialog("Loads", "surcharge x1 x2 q      (vertical pressure, down +)\n"
                                    "point x fy fx          (forces; fy down +, fx in sliding direction)",
                           "\n".join(lines), self)
        if not d.exec():
            return
        sur, pts = [], []
        try:
            for line in d.text().splitlines():
                parts = line.split()
                if not parts:
                    continue
                if parts[0] == "surcharge" and len(parts) == 4:
                    sur.append(Surcharge(*map(float, parts[1:])))
                elif parts[0] == "point" and len(parts) in (3, 4):
                    pts.append(PointLoad(*map(float, parts[1:])))
                else:
                    raise ValueError(line)
        except ValueError as e:
            QMessageBox.warning(self, "Invalid input", f"Could not read: {e}")
            return
        self.before_change()
        self.project.surcharges, self.project.point_loads = sur, pts
        self.after_change("Edit loads")

    # ------------------------------------------------------------------
    # solve
    # ------------------------------------------------------------------
    def verify_current(self):
        a = self.current_analysis()
        msgs = verify(self.project, a)
        if msgs:
            self.log_msg(f"Verify '{a.name}': {len(msgs)} problem(s)")
            for m in msgs:
                self.log_msg("  - " + m)
            QMessageBox.warning(self, "Verify", "\n".join(msgs))
        else:
            self.log_msg(f"Verify '{a.name}': no problems found.")
            self.statusBar().showMessage("No problems found.", 4000)
        return not msgs

    def _start(self, analyses):
        if self.worker is not None:
            return
        for a in analyses:
            msgs = verify(self.project, a)
            if msgs:
                QMessageBox.warning(self, "Cannot solve", f"{a.name}:\n" + "\n".join(msgs))
                return
        self.log_msg("Solving: " + ", ".join(a.name for a in analyses))
        self.progress.setValue(0)
        self.canvas.setEnabled(False)
        self.a_stop.setEnabled(True)
        self.a_solve.setEnabled(False)
        self.a_solve_all.setEnabled(False)
        self.worker = SolveWorker(self.project, analyses)
        self.worker.progress.connect(self.progress.setValue)
        self.worker.finished_solve.connect(self.solve_done)
        self.worker.start()

    def solve_current(self):
        a = self.current_analysis()
        if a:
            self._start([a])

    def solve_all(self):
        order, seen = [], set()

        def visit(a):
            if a.id in seen:
                return
            seen.add(a.id)
            if self.project.analysis(a.parent_id):
                visit(self.project.analysis(a.parent_id))
            order.append(a)
        for a in self.project.analyses:
            visit(a)
        self._start(order)

    def stop_solve(self):
        if self.worker:
            self.worker.cancelled = True

    def solve_done(self, errors):
        self.worker.wait()
        self.worker = None
        self.canvas.setEnabled(True)
        self.a_stop.setEnabled(False)
        self.a_solve.setEnabled(True)
        self.a_solve_all.setEnabled(True)
        self.progress.setValue(100)
        self.dirty = True
        if errors:
            self.log_msg("Errors:\n" + errors)
            QMessageBox.warning(self, "Solve", errors)
        else:
            self.log_msg("Solve finished.")
        a = self.current_analysis()
        if a and a.results:
            self.set_view("results")
            r = a.results
            if r["type"] == "slope" and r.get("critical"):
                self.log_msg(f"{a.name}: F = {r['critical']['fos']:.3f}")
        self.refresh_all()

    # ------------------------------------------------------------------
    # results
    # ------------------------------------------------------------------
    def show_report(self):
        a = self.current_analysis()
        text = build_report(self.project, a)

        def save():
            path = self._ask_save("Save Report", ".txt", "Text (*.txt)")
            if path:
                Path(path).write_text(text, encoding="utf-8")
        TextDialog(f"Report - {a.name}", text, self, save).exec()

    def show_slices(self):
        a = self.current_analysis()
        r = a.results if a else None
        if not (r and r["type"] == "slope" and r.get("critical")):
            QMessageBox.information(self, APP_NAME, "Solve a slope stability analysis first.")
            return
        SliceTable(r["critical"]["slices"], self).exec()

    def show_graph(self):
        a = self.current_analysis()
        r = a.results if a else None
        if not r:
            QMessageBox.information(self, APP_NAME, "Solve the analysis first.")
            return
        if r["type"] == "seepage":
            GraphDialog("Convergence", list(range(1, len(r["history"]) + 1)), r["history"], "Iteration",
                        "Max head change", parent=self).exec()
            return
        if r.get("sensitivity") and "values" in r["sensitivity"]:
            s = r["sensitivity"]
            GraphDialog("Sensitivity", s["values"], s["fos"], s["param"], "Factor of safety", parent=self).exec()
        if r.get("probability") and r["probability"].get("n"):
            p = r["probability"]
            e = p["hist_edges"]
            mids = [0.5 * (e[i] + e[i + 1]) for i in range(len(e) - 1)]
            GraphDialog("Probability Distribution", mids, p["histogram"], "Factor of safety", "Frequency",
                        bars=True, parent=self).exec()
        if not (r.get("sensitivity") or r.get("probability")):
            fs = [t["fos"] for t in r.get("trials", [])]
            GraphDialog("Trial Slip Surfaces", list(range(1, len(fs) + 1)), fs, "Trial (sorted)",
                        "Factor of safety", parent=self).exec()

    # ------------------------------------------------------------------
    # AI, window, help
    # ------------------------------------------------------------------
    def ai_builder(self):
        if not self.maybe_save():
            return
        d = AIDialog(self.settings, self)
        if d.exec() and d.project is not None:
            self.set_project(d.project, dirty=True)
            self.log_msg("AI Slope Builder created the model. Assumptions:\n" + (d.notes or "(none listed)"))
            if d.notes:
                QMessageBox.information(self, "AI assumptions", d.notes)

    def reset_layout(self):
        if self.default_state is not None:
            self.restoreState(self.default_state)
        for dock in (self.explorer_dock, self.props_dock, self.solve_dock):
            dock.show()

    def show_start(self):
        d = StartPage(self.recent_files(), list(EXAMPLES), self)
        if not d.exec() or not d.choice:
            return
        action, arg, units = d.choice
        if action == "new_slope":
            self.new_file("slope", units)
        elif action == "new_seep":
            self.new_file("seepage", units)
        elif action == "open":
            self.open_file()
        elif action == "ai":
            self.ai_builder()
        elif action == "example":
            self.open_example(arg)
        elif action == "recent":
            self.open_file(arg)

    def quick_guide(self):
        TextDialog("Quick Guide", GUIDE, self).exec()

    def about(self):
        QMessageBox.about(self, f"About {APP_NAME}",
                          f"<b>{APP_NAME} {__version__}</b><br>2D slope stability (limit equilibrium) and "
                          "steady-state seepage (finite element) analysis.<br><br>"
                          f"Python {sys.version.split()[0]}, Qt for Python.<br>MIT License.")

    def closeEvent(self, e):
        if self.worker is not None:
            self.worker.cancelled = True
            self.worker.wait(3000)
        if not self.maybe_save():
            e.ignore()
            return
        self.settings.setValue("window/geometry", self.saveGeometry())
        self.settings.setValue("window/state", self.saveState())
        e.accept()


class TextEditDialog(QDialog):
    def __init__(self, title, help_text, text, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(640, 380)
        v = QVBoxLayout(self)
        v.addWidget(QLabel(help_text))
        self.edit = QPlainTextEdit(text)
        v.addWidget(self.edit)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def text(self):
        return self.edit.toPlainText()


GUIDE = """StrataLab quick guide

1. Define the problem
   - Define > Project Properties: title, units, grid spacing.
   - Define > Materials: strength (c, phi, unit weight) and hydraulic (k sat) properties.
   - Draw > Regions: click the corners of each soil region (snaps to grid and existing points).
     Click the first point, press Enter or right-click to close. Edit > Edit Region Points for typed input.
   - Draw > Materials: pick a material in the toolbar and click regions to assign it.
   - Draw > Piezometric Line, Point Loads, Surcharge Loads as needed.

2. Slope stability
   - Define > Analysis Settings: method, pore-water pressure, seismic coefficient, slip surface search,
     probabilistic and sensitivity options.
   - Draw > Slip Surface Entry and Exit (or Grid), or use 'Auto' in the analysis settings.

3. Seepage
   - Add a seepage analysis (Define > Add Seepage Analysis).
   - Draw > Boundary Conditions along region edges: total head, pressure head, flux or seepage face.
   - To use seepage pore pressures in a stability analysis, select the seepage analysis and choose
     Define > Add Slope Analysis Using This Seepage.

4. Solve and review
   - Analysis > Verify (F6), Solve (F5), Solve All (Shift+F5).
   - Results view (Ctrl+2): critical slip surface and factor of safety, or head contours and the phreatic line.
   - View > Report, Slice Information, Graph. File > Export > PDF, PNG, CSV.

5. AI Slope Builder
   - AI > AI Slope Builder: describe the slope in words; Claude builds the model. Review every value
     before relying on the result.

Mouse: wheel zooms, middle button pans, right-click finishes a line. Keys: Esc select, F fit, Del delete region.
"""
