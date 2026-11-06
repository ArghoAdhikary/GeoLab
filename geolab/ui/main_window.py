"""Main application window."""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

from PySide6.QtCore import QSettings, QSize, Qt, QThread, Signal
from PySide6.QtGui import QAction, QActionGroup, QGuiApplication, QImage, QKeySequence, QPainter
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDockWidget, QFileDialog,
                               QInputDialog, QLabel, QMainWindow, QMenu, QMessageBox, QPlainTextEdit, QProgressBar,
                               QStyle, QTextBrowser, QToolBar, QToolButton, QLineEdit, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from .. import APP_NAME, FILE_EXT, __version__
from ..examples import EXAMPLES
from ..fileio import export_json, export_results_csv, import_points_csv, load_project, save_project
from ..geometry import polygon_area
from ..model import (ANALYSIS_KINDS, BC_KINDS, BC_TYPES, KIND_BCS, REINFORCEMENT_TYPES, SLOPE_METHODS, Project,
                     new_project)
from ..report import build_report
from ..solver import solve, verify
from .canvas import Canvas
from .chat import ChatController
from .theme import MODES as THEME_MODES
from .theme import apply_theme, is_dark, manager as theme_manager
from .dialogs import (AIDialog, BCDialog, DefineProjectDialog, EntryExitDialog, GraphDialog, MaterialsDialog, PointsDialog,
                      ProjectDialog, ReinforcementDialog, SliceTable, StructureDialog, TextDialog)
from .guide import QuickSlopeDialog, StepBar
from .home import HomePage
from .icons import set_dark_icons
from .icons import tool_icon as _tool_icon

DRAW_ORDER = ("region", "assign", None, "piezo", "bc", None, "point_load", "surcharge", "reinforcement", "structure", None,
              "entry_exit", "grid", None, "flux_section")
from .pdf import export_pdf, paint_pages
from .render import Renderer, View, available_fields, project_bounds, result_times

KIND_SHORT = {"slope": "Slope", "seepage": "Seepage", "stress": "Stress", "dynamic": "Dynamic",
              "thermal": "Thermal", "transport": "Transport", "air": "Air flow"}

FILTER = (f"All supported (*{FILE_EXT} *.gsz *.json);;{APP_NAME} project (*{FILE_EXT});;"
          "GeoStudio project (*.gsz);;JSON project (*.json)")
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


_EXTRA_WINDOWS: list = []        # windows opened by the AI assistant (kept alive)


def _app_settings():
    """Settings for this computer. A portable build (portable.txt next to the program) keeps them in
    GeoLab.ini beside the program; otherwise settings from the old StrataLab name are copied over once."""
    import sys
    exe_dir = Path(sys.executable).parent
    if getattr(sys, "frozen", False) and (exe_dir / "portable.txt").exists():
        return QSettings(str(exe_dir / "GeoLab.ini"), QSettings.IniFormat)
    s = QSettings("GeoLab", "GeoLab")
    if not s.allKeys():
        old = QSettings("StrataLab", "StrataLab")
        for k in old.allKeys():
            s.setValue(k, old.value(k))
        s.setValue("migrated_from_stratalab", True)
    return s


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._icon_actions = []    # (action, tool icon name), redrawn when the theme changes
        self.settings = _app_settings()
        self.project: Project = new_project()
        self.path: Path | None = None
        self.dirty = False
        self.undo_stack: list[dict] = []
        self.redo_stack: list[dict] = []
        self.current_aid = self.project.analyses[0].id
        self.view_mode = "define"
        self.opts = {"grid": True, "snap": True, "mesh": False, "slices": True, "trials": True,
                     "vectors": True, "contour": None, "axes": True, "labels": True, "deformed": False,
                     "time_index": None, "yield": True}
        self.probe = None          # last clicked point in the results view
        self.current_material_id = self.project.materials[0].id
        self.bc_params = {"name": "Head", "type": "head", "value": 10.0, "value2": 0.0, "fn": [], "analyses": [],
                          "fn2": [], "humidity": 0.5, "value3": 0.0, "root_depth": 0.0}
        self.struct_template = None
        self.reinf_template = None
        self.point_load = (100.0, 0.0)
        self.surcharge_q = 10.0
        self.worker = None
        self.setWindowTitle(APP_NAME)
        self.resize(1360, 860)
        self.canvas = Canvas(self)
        self.home = HomePage(self)
        self.home.chosen.connect(self.home_chosen)
        from PySide6.QtWidgets import QStackedWidget
        self.pages = QStackedWidget()
        self.stepbar = StepBar()
        self.stepbar.step_clicked.connect(self.step_clicked)
        self.stepbar.close_btn.clicked.connect(lambda: self.a_steps.setChecked(False))
        self.drawing = QWidget()
        dl = QVBoxLayout(self.drawing)
        dl.setContentsMargins(0, 0, 0, 0)
        dl.setSpacing(0)
        dl.addWidget(self.stepbar)
        dl.addWidget(self.canvas, 1)
        self.pages.addWidget(self.drawing)
        self.pages.addWidget(self.home)
        self.setCentralWidget(self.pages)
        self._hidden_on_home = []
        self._build_docks()
        self._build_actions()
        self._build_menus()
        self._build_toolbars()
        self._build_status()
        self.canvas.status.connect(self.mode_label.setText)
        self.canvas.coords.connect(self._cursor_moved)
        theme_manager().changed.connect(self._theme_changed)
        apply_theme(self.settings.value("ui/theme", "auto") or "auto")
        self._theme_changed(is_dark())
        self.chat = ChatController(self)
        self.chat.set_enabled(str(self.settings.value("ai/chat_enabled", "true")).lower() in ("true", "1"))
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

    def _set_tool_icon(self, act, name):
        self._icon_actions.append((act, name))
        act.setIcon(_tool_icon(name))

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
        self.a_new = A("&New Project...", self.new_project_dialog, "Ctrl+N", S.SP_FileIcon)
        self.a_new_kind = {k: A(f"New {v.split(' (')[0]} Project", lambda _=False, kk=k: self.new_file(kk))
                           for k, v in ANALYSIS_KINDS.items()}
        self.a_open = A("&Open...", self.open_file, "Ctrl+O", S.SP_DialogOpenButton)
        self.a_save = A("&Save", self.save, "Ctrl+S", S.SP_DialogSaveButton)
        self.a_save_as = A("Save &As...", self.save_as, "Ctrl+Shift+S")
        self.a_pdf = A("Export &PDF...", self.export_pdf, "Ctrl+E", S.SP_FileDialogDetailedView)
        self.a_png = A("Export &Image (PNG)...", self.export_png)
        self.a_csv = A("Export Results (&CSV)...", self.export_csv)
        self.a_json = A("Export Project (&JSON)...", self.export_json)
        self.a_gsz = A("Export &GeoStudio Project (.gsz)...", self.export_gsz)
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
        self.a_define = A("&Definition", lambda: self.set_view("define"), "Ctrl+1", checkable=True)
        self.a_results = A("&Results", lambda: self.set_view("results"), "Ctrl+2", checkable=True)
        self.a_layout = A("&Page Layout", self.page_layout, "Ctrl+3")
        self.a_solve_mgr = A("Solve &Manager", self.show_solve_manager, "Ctrl+F5")
        self.a_goto = A("&Go to Coordinate", self.goto_coordinate, "Ctrl+G")
        for act, name in ((self.a_define, "define"), (self.a_results, "results"), (self.a_layout, "layout")):
            self._set_tool_icon(act, name)
        g = QActionGroup(self)
        g.addAction(self.a_define)
        g.addAction(self.a_results)
        self.a_define.setChecked(True)
        self.opt_actions = {}
        for key, label in (("grid", "Show &Grid"), ("snap", "S&nap to Grid"), ("mesh", "Show &Mesh"),
                           ("slices", "Show S&lices"), ("trials", "Show &Trial Slip Surfaces"),
                           ("vectors", "Show Flow &Vectors"), ("axes", "Show &Axes"),
                           ("deformed", "Show &Deformed Mesh"), ("yield", "Show &Yielded Zones")):
            a = A(label, checkable=True)
            a.setChecked(self.opts[key])
            a.toggled.connect(lambda on, k=key: self.set_opt(k, on))
            self.opt_actions[key] = a
        self.a_report = A("&Report...", self.show_report, "Ctrl+R")
        self.a_slices = A("&Slice Information...", self.show_slices)
        self.a_graph = A("&Graph...", self.show_graph)
        self.a_proj = A("&Project Properties...", self.edit_project)
        self.a_mats = A("&Materials...", self.edit_materials, "Ctrl+M")
        self.a_analysis = A("&Analyses...", self.edit_analysis, "Ctrl+Shift+A")
        self.a_add = {k: A(v, lambda _=False, kk=k: self.add_analysis(kk)) for k, v in ANALYSIS_KINDS.items()}
        self.a_add_child = {k: A(v, lambda _=False, kk=k: self.add_analysis(kk, child=True))
                            for k, v in ANALYSIS_KINDS.items()}
        self.a_add_slope, self.a_add_seep = self.a_add["slope"], self.a_add["seepage"]
        self.a_del_analysis = A("Delete Analysis", self.delete_analysis)
        self.a_bcs = A("&Boundary Conditions...", self.edit_bcs)
        self.a_piezo_pts = A("Piezometric Line &Points...", self.edit_piezo)
        self.a_loads = A("&Loads...", self.edit_loads)
        self.a_reinf = A("&Reinforcement...", self.edit_reinforcement)
        self.a_flux = A("&Flux Sections...", self.edit_flux_sections)
        self.a_structs = A("S&tructures (walls, anchors, geogrids)...", self.edit_structures)
        self.a_quick = A("New &Quick Slope...", self.quick_slope, "Ctrl+Shift+N",
                         tip="Build a complete slope from a few numbers: height, steepness, soil layers, water")
        self.a_steps = A("Show &Step Guide", checkable=True,
                         tip="Show the numbered steps above the drawing with a hint for what to do next")
        self.a_steps.setChecked(str(self.settings.value("ui/step_guide", "true")).lower() in ("true", "1"))
        self.a_steps.toggled.connect(self._toggle_steps)
        self.draw_group = QActionGroup(self)
        self.draw_actions = {}
        for mode, label, key in (("select", "&Select", "Esc"), ("region", "&Regions", "Ctrl+Shift+R"),
                                 ("assign", "&Materials", None), ("piezo", "&Piezometric Line", None),
                                 ("bc", "&Boundary Conditions", None), ("point_load", "Point &Loads", None),
                                 ("surcharge", "S&urcharge Loads", None), ("entry_exit", "Slip Surface &Entry and Exit", None),
                                 ("grid", "Slip Surface &Grid", None), ("reinforcement", "Rein&forcement", None),
                                 ("structure", "Stru&ctures (wall, anchor, geogrid)", None),
                                 ("flux_section", "Flu&x Sections", None), ("text", "Sketch &Text", None),
                                 ("pan", "Pa&n", None)):
            a = A(label, lambda _=False, m=mode: self.set_draw_mode(m), key, checkable=True)
            self.draw_group.addAction(a)
            self.draw_actions[mode] = a
        self.draw_actions["select"].setChecked(True)
        from .canvas import MODE_HINTS
        for mode, act in self.draw_actions.items():
            self._set_tool_icon(act, mode)
            if mode in MODE_HINTS:
                act.setToolTip(f"<b>{act.text().replace('&', '')}</b><br>{MODE_HINTS[mode]}")
                act.setStatusTip(MODE_HINTS[mode])
        self._set_tool_icon(self.a_mats, "materials")
        for act, name in ((self.a_zin, "zoom_in"), (self.a_zout, "zoom_out"), (self.a_print, "print"),
                          (self.a_copy, "copy"), (self.opt_actions["grid"], "grid_toggle"),
                          (self.opt_actions["snap"], "snap")):
            self._set_tool_icon(act, name)
        self._set_tool_icon(self.a_analysis, "analyses")
        self.a_ee_dialog = A("Slip Surface Entry and Exit &Range...", self.entry_exit_dialog)
        self.a_verify = A("&Verify", self.verify_current, "F6", S.SP_DialogApplyButton)
        self.a_solve = A("&Solve Analysis", self.solve_current, "F5", S.SP_MediaPlay)
        self.a_solve_all = A("Solve &All", self.solve_all, "Shift+F5", S.SP_MediaSeekForward)
        self.a_stop = A("S&top", self.stop_solve, None, S.SP_MediaStop)
        self.a_stop.setEnabled(False)
        self.a_ai = A("AI &Slope Builder...", self.ai_builder, "Ctrl+Shift+I")
        self.a_chat = A("AI Assistant &Chat", lambda: self.chat.toggle() if self.chat.enabled
                        else self.preferences("ai"), "Ctrl+Shift+J")
        self.a_prefs = A("&Preferences...", lambda: self.preferences(), "Ctrl+,")
        self.theme_group = QActionGroup(self)
        self.a_theme = {}
        for key, label in THEME_MODES.items():
            ta = A(label, lambda _=False, k=key: self.set_theme(k), checkable=True)
            self.theme_group.addAction(ta)
            self.a_theme[key] = ta
        self.a_theme.get(self.settings.value("ui/theme", "auto") or "auto", self.a_theme["auto"]).setChecked(True)
        self.a_reset = A("&Reset Window Layout", self.reset_layout)
        self.a_start = A("&Start Page", self.show_start)
        self.a_guide = A("&Quick Guide", self.quick_guide, "F1")
        self.a_about = A("&About", self.about)

    def _build_menus(self):
        mb = self.menuBar()
        m = mb.addMenu("&File")
        m.addAction(self.a_new)
        m.addAction(self.a_quick)
        nm = m.addMenu("New by &Analysis Type")
        for a in self.a_new_kind.values():
            nm.addAction(a)
        m.addAction(self.a_open)
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
        for a in (self.a_pdf, self.a_png, self.a_csv, self.a_json, self.a_gsz):
            exp.addAction(a)
        m.addAction(self.a_print)
        m.addSeparator()
        m.addAction(self.a_clear)
        m.addSeparator()
        m.addAction(self.a_exit)

        m = mb.addMenu("&Edit")
        for a in (self.a_undo, self.a_redo, None, self.a_copy, None, self.a_goto, None, self.a_prefs):
            m.addSeparator() if a is None else m.addAction(a)

        m = mb.addMenu("&View")
        for a in (self.a_define, self.a_results, self.a_layout, None, self.a_fit, self.a_zin, self.a_zout, None):
            m.addSeparator() if a is None else m.addAction(a)
        for a in self.opt_actions.values():
            m.addAction(a)
        m.addSeparator()
        m.addAction(self.a_report)
        m.addAction(self.a_slices)
        m.addAction(self.a_graph)
        m.addSeparator()
        m.addAction(self.a_steps)
        tm = m.addMenu("&Theme")
        for a in self.a_theme.values():
            tm.addAction(a)

        m = mb.addMenu("&Define")
        for a in (self.a_proj, self.a_analysis, self.a_mats, None):
            m.addSeparator() if a is None else m.addAction(a)
        add = m.addMenu("Add &Analysis")
        for a in self.a_add.values():
            add.addAction(a)
        child = m.addMenu("Add &Child Analysis (uses the selected analysis)")
        for a in self.a_add_child.values():
            child.addAction(a)
        for a in (self.a_del_analysis, None, self.a_bcs, self.a_piezo_pts, self.a_loads, self.a_reinf, self.a_structs, self.a_flux):
            m.addSeparator() if a is None else m.addAction(a)

        m = mb.addMenu("D&raw")
        for mode in DRAW_ORDER:
            if mode is None:
                m.addSeparator()
                continue
            m.addAction(self.draw_actions[mode])
            if mode == "entry_exit":
                m.addAction(self.a_ee_dialog)

        m = mb.addMenu("&Sketch")
        m.addAction(self.draw_actions["text"])
        m.addAction(self.opt_actions["axes"])

        m = mb.addMenu("&Modify")
        for a in (self.draw_actions["select"], self.draw_actions["pan"], None, self.a_edit_points, self.a_del_region,
                  None, self.a_del_analysis, self.a_clear):
            m.addSeparator() if a is None else m.addAction(a)

        self.window_menu = mb.addMenu("&Window")
        for a in (self.a_solve_mgr, self.a_verify, self.a_solve, self.a_solve_all, self.a_stop):
            self.window_menu.addAction(a)
        self.window_menu.addSeparator()
        for d in (self.explorer_dock, self.props_dock, self.solve_dock):
            self.window_menu.addAction(d.toggleViewAction())
        self.window_menu.addSeparator()
        self.window_menu.addAction(self.a_reset)
        self.window_menu.addAction(self.a_start)

        self.window_menu.addAction(self.a_chat)

        m = mb.addMenu("&Help")
        m.addAction(self.a_guide)
        m.addAction(self.a_chat)
        m.addAction(self.a_ai)
        m.addSeparator()
        m.addAction(self.a_about)

    def _build_toolbars(self):
        first_window_action = self.window_menu.actions()[0]

        def tb(name, actions, area=Qt.TopToolBarArea):
            t = QToolBar(name, self)
            t.setObjectName(name)
            for a in actions:
                t.addSeparator() if a is None else t.addAction(a)
            self.addToolBar(area, t)
            self.window_menu.insertAction(first_window_action, t.toggleViewAction())
            return t
        tb("Standard", [self.a_new, self.a_quick, self.a_open, self.a_save, None, self.a_print, self.a_pdf, None, self.a_copy,
                        None, self.a_undo, self.a_redo, None, self.a_verify, self.a_solve, self.a_solve_all,
                        self.a_stop, None, self.a_zin, self.a_zout, self.a_fit])
        self.addToolBarBreak()
        m = tb("Mode", [self.a_define, self.a_results, self.a_layout, None, self.draw_actions["select"],
                        self.a_analysis, self.a_mats])
        m.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        for act in (self.draw_actions["select"], self.a_analysis, self.a_mats):
            m.widgetForAction(act).setToolButtonStyle(Qt.ToolButtonIconOnly)
        m.addSeparator()
        m.addWidget(QLabel(" Material: "))
        self.mat_combo = QComboBox()
        self.mat_combo.setMinimumWidth(150)
        self.mat_combo.activated.connect(lambda i: setattr(self, "current_material_id", self.mat_combo.itemData(i)))
        m.addWidget(self.mat_combo)
        r = tb("Results", [])
        r.addWidget(QLabel(" Contour: "))
        self.field_combo = QComboBox()
        self.field_combo.setMinimumWidth(190)
        self.field_combo.activated.connect(lambda i: self.set_opt("contour", self.field_combo.itemData(i)))
        r.addWidget(self.field_combo)
        r.addWidget(QLabel("  Time: "))
        self.time_combo = QComboBox()
        self.time_combo.setMinimumWidth(130)
        self.time_combo.activated.connect(lambda i: self.set_opt("time_index", self.time_combo.itemData(i)))
        r.addWidget(self.time_combo)
        r.addAction(self.opt_actions["deformed"])
        # drawing tools down the right-hand side of the drawing
        d = tb("Draw", [None if k is None else self.draw_actions[k] for k in DRAW_ORDER + ("text", "pan")],
               Qt.RightToolBarArea)
        d.setIconSize(QSize(26, 26))

    def _build_status(self):
        self.mode_label = QLabel("")
        self.xy_label = QLabel("")
        self.units_label = QLabel("")
        sb = self.statusBar()
        sb.addWidget(QLabel(" 2-Dimensional "))
        sb.addWidget(self.mode_label, 1)
        sb.addPermanentWidget(QLabel("Go to coordinate (Ctrl+G):"))
        self.goto_edit = QLineEdit()
        self.goto_edit.setFixedWidth(200)
        self.goto_edit.setToolTip("Cursor position. Type x, y and press Enter to centre the view there.")
        self.goto_edit.returnPressed.connect(self._goto_from_edit)
        sb.addPermanentWidget(self.goto_edit)
        for act in (self.opt_actions["grid"], self.opt_actions["snap"], self.a_zin, self.a_zout, self.a_fit):
            b = QToolButton()
            b.setDefaultAction(act)
            b.setAutoRaise(True)
            sb.addPermanentWidget(b)
        self.scale_label = QLabel("")
        sb.addPermanentWidget(self.scale_label)
        sb.addPermanentWidget(self.units_label)

    def _cursor_moved(self, x, y):
        unit = "m" if self.project.units == "metric" else "ft"
        if not self.goto_edit.hasFocus():
            self.goto_edit.setText(f"{x:.6f}, {y:.6f} {unit}")
        self.update_scale()

    def _goto_from_edit(self):
        try:
            txt = self.goto_edit.text().replace(";", ",").replace("ft", "").replace("m", "")
            x, y = (float(v) for v in txt.split(",")[:2])
        except ValueError:
            self.statusBar().showMessage("Type the coordinate as x, y", 3000)
            return
        self.canvas.view.cx, self.canvas.view.cy = x, y
        self.canvas.update()
        self.update_scale()

    def goto_coordinate(self):
        self.goto_edit.setFocus()
        self.goto_edit.selectAll()

    def update_scale(self):
        """Engineering scale of the drawing, 1 : N (model length per unit of screen length)."""
        dpm = self.canvas.logicalDpiX() / 0.0254           # screen pixels per metre
        s = self.canvas.view.s                               # pixels per model length unit
        if s > 0:
            unit_m = 1.0 if self.project.units == "metric" else 0.3048
            self.scale_label.setText(f"  1:{dpm * unit_m / s:,.0f}  ")

    def show_solve_manager(self):
        self.solve_dock.show()
        self.solve_dock.raise_()

    def page_layout(self):
        """Print preview of the drawing and results pages."""
        from PySide6.QtPrintSupport import QPrinter, QPrintPreviewDialog
        pr = QPrinter(QPrinter.HighResolution)
        pr.setPageOrientation(pr.pageLayout().Landscape)
        dlg = QPrintPreviewDialog(pr, self)
        dlg.setWindowTitle("Page Layout")
        mode = "results" if (self.current_analysis() and self.current_analysis().results) else "define"
        dlg.paintRequested.connect(lambda printer: paint_pages(printer, self.project, self.current_analysis(), mode,
                                                               self.opts, printer.newPage))
        dlg.resize(1100, 800)
        dlg.exec()

    def entry_exit_dialog(self):
        a = self.current_analysis()
        if a is None or a.kind != "slope":
            QMessageBox.information(self, APP_NAME, "Select a slope stability analysis first.")
            return
        d = EntryExitDialog(self.project, a, self)
        if d.exec():
            self.before_change()
            d.apply(a)
            self.after_change("Set entry and exit")

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
        bp = dict(self.bc_params)
        name = bp.pop("name")
        self.before_change()
        n = sum(1 for b in self.project.boundary_conditions if b.name.startswith(name))
        self.project.add_bc(name if n == 0 else f"{name} {n + 1}", bp.pop("type"), bp.pop("value"), pts, **bp)
        self.after_change("Add boundary condition")

    def add_reinforcement(self, x1, y1, x2, y2):
        t = self.reinf_template
        kw = {} if t is None else {k: getattr(t, k) for k in ("capacity", "bond", "bond_length", "spacing", "f_dependent")}
        self.before_change()
        self.project.add_reinforcement(t.type if t else "nail", x1, y1, x2, y2, **kw)
        self.after_change("Add reinforcement")

    def add_structure(self, pts):
        t = self.struct_template
        self.before_change()
        if t is None:
            self.project.add_structure("beam", pts)
        else:
            n = sum(1 for x in self.project.structures if x.type == t.type) + 1
            name = t.name if t.name and not any(x.name == t.name for x in self.project.structures) \
                else f"{t.type.capitalize()} {n}"
            self.project.add_structure(t.type, pts, name, EA=t.EA, EI=t.EI, spacing=t.spacing,
                                       prestress=t.prestress, analyses=list(t.analyses))
        self.after_change("Add structure")

    def add_flux_section(self, pts):
        self.before_change()
        self.project.add_flux_section(f"FS{len(self.project.flux_sections) + 1}", pts)
        self.after_change("Add flux section")

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
        if not r or r.get("type") == "slope":
            self.refresh_props()
            return
        import numpy as np
        from scipy.interpolate import LinearNDInterpolator
        nodes = np.asarray(r["nodes"])
        rows = []
        o = dict(self.opts)
        for key, label in available_fields(r):
            o["contour"] = key
            vals, per_elem, lab, unit = Renderer(self.project, a, View(), None, mode="results", opts=o).field_values(r)
            if per_elem:
                tris = np.asarray(r["tris"])
                cent = nodes[tris].mean(axis=1)
                val = float(vals[np.argmin(np.hypot(cent[:, 0] - x, cent[:, 1] - y))])
            else:
                val = float(LinearNDInterpolator(nodes, vals)(x, y))
            if np.isfinite(val):
                rows.append(f"<tr><td>{lab}</td><td align=right>{val:.5g}</td><td>{unit}</td></tr>")
        if not rows:
            return
        self.probe = (x, y)
        tsel = self.opts.get("time_index")
        when = f" at t = {result_times(r)[tsel]:g} s" if tsel is not None and result_times(r) else ""
        self.props.setHtml(f"<b>Result at ({x:.3f}, {y:.3f}){when}</b><table cellpadding=2>{''.join(rows)}</table>"
                           "<i>View > Graph plots this point against time.</i>")

    # ------------------------------------------------------------------
    # refresh
    # ------------------------------------------------------------------
    def refresh_all(self):
        if hasattr(self, "scale_label"):
            self.update_scale()
        self.refresh_tree()
        self.refresh_props()
        self.mat_combo.clear()
        for m in self.project.materials:
            self.mat_combo.addItem(m.name, m.id)
        if self.project.material(self.current_material_id) is None and self.project.materials:
            self.current_material_id = self.project.materials[0].id
        self.mat_combo.setCurrentIndex(max(0, self.mat_combo.findData(self.current_material_id)))
        self.units_label.setText(f"Units: {self.project.units}")
        self.refresh_result_controls()
        self.a_undo.setEnabled(bool(self.undo_stack))
        self.a_redo.setEnabled(bool(self.redo_stack))
        name = self.path.name if self.path else "Untitled"
        self.setWindowTitle(f"{name}{' *' if self.dirty else ''} - {self.project.title} - {APP_NAME}")
        if hasattr(self, "stepbar"):
            self.stepbar.setVisible(self.a_steps.isChecked())
            if self.a_steps.isChecked():
                self.stepbar.update_steps(self.project, self.current_analysis())
        self.canvas.update()

    def refresh_tree(self):
        self.tree.blockSignals(True)
        self.tree.clear()
        items = {}

        def label(a):
            r = a.results
            if a.kind == "slope":
                s = f"{a.name}  [{SLOPE_METHODS.get(a.method, a.method)}]"
                if r and r.get("critical"):
                    s += f"  F = {r['critical']['fos']:.3f}"
            else:
                extra = " transient" if getattr(a, "transient", False) and a.kind in ("seepage", "thermal", "air") else ""
                s = f"{a.name}  [{KIND_SHORT.get(a.kind, a.kind)}{extra}]"
                if r:
                    if r.get("srm_fos"):
                        s += f"  SRF = {r['srm_fos']:.3f}"
                    else:
                        s += "  solved" if r.get("converged", True) else "  not converged"
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
            html.append(f"Method: {SLOPE_METHODS.get(a.method, a.method)}<br>Search: {a.search.mode.replace('_', ' ')}<br>")
        r = a.results
        if not r:
            html.append("<i>Not solved. Press F5 to solve.</i>")
        elif r["type"] == "slope":
            c = r.get("critical")
            if c:
                html.append(f"<span style='font-size:16pt'><b>F = {c['fos']:.3f}</b></span><br>")
                dd = r.get("drawdown")
                if dd:
                    html.append(f"Rapid drawdown to {dd['level']:g} {p.unit('length')}:<br>"
                                f"&nbsp; stage 1 (before) F = {dd['stage1']:.3f}<br>"
                                f"&nbsp; stage 2 (undrained) F = {dd['stage2']:.3f}<br>"
                                f"&nbsp; stage 3 (lower of drained / undrained) F = {dd['stage3']:.3f}<br>"
                                f"&nbsp; {dd['undrained_slices']} of {dd['slices']} slices undrained<br>")
                html.append(f"Valid trial surfaces: {r['n_valid']} of {r['n_total']}<br><table>")
                for m, v in c["all_methods"].items():
                    val = "-" if v["fos"] is None else f"{v['fos']:.3f}"
                    html.append(f"<tr><td>{SLOPE_METHODS.get(m, m)}</td><td align=right>{val}</td></tr>")
                html.append("</table>")
                pr = r.get("probability")
                if pr and pr.get("n"):
                    html.append(f"<br>Mean F {pr['mean']:.3f}, P(failure) {100 * pr['pf']:.2f} %")
                nm = r.get("newmark")
                if nm and "displacement" in nm:
                    html.append(f"<br>Newmark: ky = {nm['ky']:.3f} g, permanent displacement "
                                f"{nm['displacement']:.4f} {p.unit('length')} (View > Graph)")
            else:
                html.append(f"<span style='color:#a00'>{r.get('message', 'No valid slip surface')}</span>")
        else:
            html.append(self.result_summary(a, r))
        self.props.setHtml("".join(html))

    def result_summary(self, a, r):
        p = self.project
        u = p.unit
        h = [f"Converged: {'yes' if r.get('converged', True) else '<b>no</b>'}<br>"]
        t = r["type"]
        if t in ("seepage", "air"):
            h.append(f"Inflow: {r['inflow']:.4e} {u('flux')}<br>Outflow: {r['outflow']:.4e} {u('flux')}<br>")
            for name, q in (r.get("flux_sections") or {}).items():
                h.append(f"Flux section {name}: {q:.4e} {u('flux')}<br>")
            if "balance_error" in r:
                h.append(f"Water balance error: {100 * r['balance_error']:.3f} %<br>")
            cl = r.get("climate")
            if cl:
                h.append(f"Rainfall {cl['rainfall']:.4g}, evaporation {cl['evaporation']:.4g}, runoff "
                         f"{cl['runoff']:.4g} {u('length')}³ per unit width<br>")
                if cl.get("potential_transpiration"):
                    h.append(f"Plant transpiration {cl['transpiration']:.4g} of a potential "
                             f"{cl['potential_transpiration']:.4g} {u('length')}³ per unit width<br>")
        elif t == "stress":
            if r.get("srm_fos"):
                h.append(f"<span style='font-size:14pt'><b>Strength reduction F = {r['srm_fos']:.3f}</b></span><br>")
            h.append(f"Max displacement: {max(abs(v) for v in r['dx'] + r['dy']):.4g} {u('length')}<br>")
            h.append(f"Yielded elements: {sum(r.get('yielded', []))} of {len(r['tris'])}<br>")
            for name, (rx, ry) in (r.get("reactions") or {}).items():
                h.append(f"Reaction {name}: x {rx:.4g}, y {ry:.4g} {u('force')}<br>")
            if r.get("settlement_history"):
                h.append(f"Final settlement (monitor point): {r['settlement_history'][-1]:.4g} {u('length')}<br>")
            if r.get("inactive") and any(r["inactive"]):
                h.append(f"Stage: {sum(r['inactive'])} elements not built / excavated<br>")
            for st in r.get("structures") or []:
                line = f"{st['name']}: max axial force {st['max_N']:.4g} {u('force')}/{u('length')}"
                if st["type"] == "beam":
                    line += f", max moment {st['max_M']:.4g} {u('force')}.{u('length')}/{u('length')}"
                h.append(line + " (tension +)<br>")
        elif t == "dynamic":
            f1 = r.get("natural_frequency")
            h.append(f"Peak acceleration: {max(r['max_acceleration']):.3f} g<br>")
            if f1:
                h.append(f"First natural frequency: {f1:.3f} Hz<br>")
        elif t == "thermal":
            h.append(f"Temperature range: {min(r['temperature']):.2f} to {max(r['temperature']):.2f} {u('temperature')}<br>")
            if "balance_error" in r:
                h.append(f"Energy balance error: {100 * r['balance_error']:.3f} %<br>")
        elif t == "transport":
            h.append(f"Max concentration: {max(r['concentration']):.4g} {u('concentration')}<br>"
                     f"Max grid Peclet number: {r['max_grid_peclet']:.2f}<br>")
            for prt in r.get("particles", []):
                h.append(f"Particle from {prt['start']}: travel {prt['time']:.4g} s<br>")
        if result_times(r):
            h.append(f"Saved times: {len(result_times(r))} (choose one in the Results toolbar)<br>")
        h.append(f"Nodes: {len(r['nodes'])}, elements: {len(r['tris'])}<br><i>Click the drawing to read values.</i>")
        return "".join(h)

    def refresh_result_controls(self):
        """Fill the Results toolbar for the current analysis."""
        a = self.current_analysis()
        r = a.results if a else None
        self.field_combo.blockSignals(True)
        self.time_combo.blockSignals(True)
        self.field_combo.clear()
        self.time_combo.clear()
        fields = available_fields(r)
        for key, label in fields:
            self.field_combo.addItem(label, key)
        if fields and self.opts.get("contour") not in [k for k, _ in fields]:
            self.opts["contour"] = fields[0][0]
        self.field_combo.setCurrentIndex(max(0, self.field_combo.findData(self.opts.get("contour"))))
        times = result_times(r)
        self.time_combo.addItem("Final", None)
        for i, tv in enumerate(times):
            self.time_combo.addItem(f"{tv:g} s", i)
        if self.opts.get("time_index") is not None and self.opts["time_index"] >= len(times):
            self.opts["time_index"] = None
        self.time_combo.setCurrentIndex(max(0, self.time_combo.findData(self.opts.get("time_index"))))
        self.field_combo.setEnabled(bool(fields))
        self.time_combo.setEnabled(bool(times))
        self.field_combo.blockSignals(False)
        self.time_combo.blockSignals(False)

    def tree_selected(self):
        it = self.tree.currentItem()
        if it:
            self.current_aid = it.data(0, Qt.UserRole)
            if self.view_mode == "results" and not self.current_analysis().results:
                self.set_view("define")
            self.opts["time_index"] = None
            self.refresh_props()
            self.refresh_result_controls()
            self.canvas.update()

    def tree_menu(self, pos):
        it = self.tree.itemAt(pos)
        m = QMenu(self)
        if it:
            self.current_aid = it.data(0, Qt.UserRole)
            m.addAction(self.a_analysis)
            m.addAction(self.a_solve)
            m.addAction("Rename...", self.rename_analysis)
            child = m.addMenu("Add Child Analysis")
            for a in self.a_add_child.values():
                child.addAction(a)
            m.addAction(self.a_del_analysis)
            m.addSeparator()
        add = m.addMenu("Add Analysis")
        for a in self.a_add.values():
            add.addAction(a)
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
            a = self.current_analysis()
            group = KIND_BCS.get(a.kind) if a else None
            bp = dict(self.bc_params)
            if group and bp["type"] not in BC_KINDS[group]:
                bp["type"] = next(iter(BC_KINDS[group]))
            d = BCDialog(bp["name"], bp["type"], bp["value"], parent=self, kinds=[group] if group else None,
                         value2=bp["value2"], fn=bp["fn"], analyses=bp["analyses"], project=self.project,
                         fn2=bp["fn2"], humidity=bp["humidity"], value3=bp.get("value3", 0.0),
                         root_depth=bp.get("root_depth", 0.0))
            if not d.exec():
                self.draw_actions["select"].setChecked(True)
                mode = "select"
            else:
                self.bc_params = d.params()
        if mode == "reinforcement":
            d = ReinforcementDialog(self.reinf_template, self, self.project.unit)
            if not d.exec():
                self.draw_actions["select"].setChecked(True)
                mode = "select"
            else:
                self.reinf_template = d.r
        if mode == "structure":
            a = self.current_analysis()
            if a is None or a.kind not in ("stress", "dynamic"):
                QMessageBox.information(self, APP_NAME, "Structures (walls, anchors, geogrids) are used by "
                                        "stress-deformation analyses. Select or add a stress analysis first.")
                self.draw_actions["select"].setChecked(True)
                mode = "select"
            else:
                d = StructureDialog(self.struct_template, self, self.project.unit, self.project)
                if not d.exec():
                    self.draw_actions["select"].setChecked(True)
                    mode = "select"
                else:
                    self.struct_template = d.st
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
        self.show_workspace()
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

    def new_project_dialog(self):
        labels = list(ANALYSIS_KINDS.values())
        item, ok = QInputDialog.getItem(self, "New Project", "First analysis type:", labels, 0, False)
        if ok:
            self.new_file(list(ANALYSIS_KINDS)[labels.index(item)])

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

    def export_gsz(self):
        path = self._ask_save("Export GeoStudio Project", ".gsz", "GeoStudio project (*.gsz)")
        if not path:
            return
        try:
            from ..gsz import write_gsz
            skipped = write_gsz(self.project, path)
        except Exception as e:
            QMessageBox.critical(self, "Export failed", str(e))
            return
        self.log_msg(f"Exported GeoStudio file: {path}")
        msg = ("Exported geometry, materials, in situ and consolidation stress analyses and their fixed, load "
               "and drainage boundaries.")
        if skipped:
            msg += "\n\nNot written (set these up in GeoStudio):\n- " + "\n- ".join(skipped)
            self.log_msg("Not written to .gsz: " + "; ".join(skipped))
        QMessageBox.information(self, APP_NAME, msg)

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
            old = self.project.units
            d.apply()
            converted = old != self.project.units and d.convert.isChecked()
            self.after_change("Project properties", keep_results=not converted)
            if converted:
                self.canvas.zoom_fit()
                QMessageBox.information(self, APP_NAME, f"All values were converted to {self.project.units} "
                                        "units. Not converted (check them): " + ", ".join(d.not_converted) + ".")

    def edit_materials(self):
        d = MaterialsDialog(self.project, self)
        if d.exec():
            self.before_change()
            self.project.materials = d.result_mats
            self.after_change("Edit materials")

    def edit_analysis(self):
        """Define Analyses window: the analysis tree with Add / Delete and the selected analysis' settings."""
        from dataclasses import fields

        def key(a):
            return {f.name: getattr(a, f.name) for f in fields(a) if f.name != "results"}
        d = DefineProjectDialog(self.project, self.current_aid, self)
        if not d.exec():
            return
        old = {a.id: a for a in self.project.analyses}
        new = d.p.analyses
        stale = {a.id for a in new if a.id not in old or key(old[a.id]) != key(a)}
        removed = set(old) - {a.id for a in new}
        sel = d.selected_id()
        if not stale and not removed:
            self.current_aid = sel if self.project.analysis(sel) else self.current_aid
            self.refresh_all()
            return
        self.before_change()
        for a in new:
            a.results = None if a.id in stale else old[a.id].results
        changed = True
        while changed:          # children of re-defined analyses must be solved again too
            changed = False
            for a in new:
                if a.results is not None and a.parent_id in stale:
                    a.results = None
                    stale.add(a.id)
                    changed = True
        self.project.analyses = new
        self.project.boundary_conditions = d.p.boundary_conditions
        self.current_aid = sel if self.project.analysis(sel) else (new[0].id if new else None)
        self.dirty = True
        self.set_view("define")
        self.refresh_all()

    def add_analysis(self, kind, child=False):
        parent = self.current_analysis() if child else None
        if child and parent is None:
            QMessageBox.information(self, APP_NAME, "Select the parent analysis first.")
            return
        self.before_change()
        n = len(self.project.analyses) + 1
        a = self.project.add_analysis(f"{KIND_SHORT[kind]} {n}", kind)
        if parent:
            a.parent_id = parent.id
            a.name = f"{KIND_SHORT[kind]} ({parent.name})"
            if parent.kind in ("seepage", "stress", "thermal", "air", "transport"):
                a.mesh_size = parent.mesh_size
            if kind == "seepage" and parent.kind == "seepage":
                a.transient, a.initial = True, "parent"
            if kind == "thermal" and parent.kind == "thermal":
                a.transient, a.initial = True, "parent"
            if kind == "stress" and parent.kind == "stress":
                a.stress_type = "load"
            if kind in ("slope", "stress") and parent.kind == "seepage":
                a.pwp = "seepage"
            if kind == "slope" and parent.kind == "stress":
                a.method = "finite_element"
        if kind == "slope":
            if self.project.regions:
                from ..geometry import auto_entry_exit
                (e1, e2), (x1, x2) = auto_entry_exit(self.project)
                a.search.entry_x1, a.search.entry_x2, a.search.exit_x1, a.search.exit_x2 = e1, e2, x1, x2
            if self.project.piezometric_line and a.pwp == "none":
                a.pwp = "piezometric"
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
        def fmt(b):
            parts = [b.name, b.type, f"{b.value:g}", " ".join(f"{x:g},{y:g}" for x, y in b.points)]
            if b.value2 or b.fn or b.analyses:
                parts.append(f"{b.value2:g}")
                parts.append(" ".join(f"{t:g}:{v:g}" for t, v in b.fn))
                parts.append(" ".join(str(i) for i in b.analyses))
            return "; ".join(parts)
        d = TextEditDialog("Boundary Conditions",
                           "One per line:  name; type; value; x1,y1 x2,y2 ...[; second value; t:v t:v ...; analysis ids]\n"
                           "Types: " + ", ".join(BC_TYPES),
                           "\n".join(fmt(b) for b in self.project.boundary_conditions), self)
        if not d.exec():
            return
        bcs = []
        line = ""
        try:
            for line in d.text().splitlines():
                if not line.strip():
                    continue
                f = [s.strip() for s in line.split(";")]
                if len(f) < 4:
                    raise ValueError("Expected at least: name; type; value; points")
                name, typ, val, pts = f[:4]
                if typ not in BC_TYPES:
                    raise ValueError(f"Unknown type '{typ}'")
                pp = [[float(v) for v in p.split(",")] for p in pts.split()]
                if len(pp) < 2:
                    raise ValueError(f"'{name}' needs at least two points")
                kw = {}
                if len(f) > 4 and f[4]:
                    kw["value2"] = float(f[4])
                if len(f) > 5 and f[5]:
                    kw["fn"] = [[float(a) for a in tv.split(":")] for tv in f[5].split()]
                if len(f) > 6 and f[6]:
                    kw["analyses"] = [int(i) for i in f[6].split()]
                bcs.append((name, typ, float(val), pp, kw))
        except ValueError as e:
            QMessageBox.warning(self, "Invalid input", f"{e}\n\nLine: {line}")
            return
        self.before_change()
        self.project.boundary_conditions = []
        for name, typ, val, pp, kw in bcs:
            self.project.add_bc(name, typ, val, pp, **kw)
        self.after_change("Edit boundary conditions")

    def edit_reinforcement(self):
        lines = [f"{r.type} {r.x1:g} {r.y1:g} {r.x2:g} {r.y2:g} {r.capacity:g} {r.bond:g} {r.bond_length:g} "
                 f"{r.spacing:g} {int(r.f_dependent)}" for r in self.project.reinforcements]
        d = TextEditDialog("Reinforcement",
                           "type x1 y1 x2 y2 capacity bond bond_length spacing f_dependent(0/1)\n"
                           "(x1, y1) is the head at the slope face. Types: " + ", ".join(REINFORCEMENT_TYPES),
                           "\n".join(lines), self)
        if not d.exec():
            return
        rows = []
        try:
            for line in d.text().splitlines():
                p = line.split()
                if not p:
                    continue
                if p[0] not in REINFORCEMENT_TYPES or len(p) != 10:
                    raise ValueError(line)
                rows.append((p[0], *map(float, p[1:9]), bool(int(p[9]))))
        except ValueError as e:
            QMessageBox.warning(self, "Invalid input", f"Could not read: {e}")
            return
        self.before_change()
        self.project.reinforcements = []
        for t, x1, y1, x2, y2, cap, bond, bl, sp, fd in rows:
            self.project.add_reinforcement(t, x1, y1, x2, y2, capacity=cap, bond=bond, bond_length=bl,
                                           spacing=sp, f_dependent=fd)
        self.after_change("Edit reinforcement")

    def edit_structures(self):
        from ..model import STRUCTURE_TYPES
        names = {a.id: a.name for a in self.project.analyses}
        lines = [f"{st.type}; {st.name}; {st.EA:g} {st.EI:g} {st.spacing:g} {st.prestress:g}; "
                 + " ".join(f"{x:g},{y:g}" for x, y in st.points)
                 + (f"; {','.join(str(i) for i in st.analyses)}" if st.analyses else "")
                 for st in self.project.structures]
        stages = ", ".join(f"{i} = {n}" for i, n in names.items())
        d = TextEditDialog("Structures",
                           "type; name; EA EI spacing prestress; x,y x,y ...; stage ids (optional)\n"
                           "Types: " + ", ".join(STRUCTURE_TYPES) + f".  Analysis ids: {stages}",
                           "\n".join(lines), self)
        if not d.exec():
            return
        rows = []
        try:
            for line in d.text().splitlines():
                if not line.strip():
                    continue
                parts = [x.strip() for x in line.split(";")]
                if len(parts) < 4 or parts[0] not in STRUCTURE_TYPES:
                    raise ValueError(line)
                EA, EI, sp, pre = (float(v) for v in parts[2].split())
                pts = [[float(a) for a in xy.split(",")] for xy in parts[3].split()]
                if len(pts) < 2:
                    raise ValueError(line)
                stg = [int(v) for v in parts[4].split(",")] if len(parts) > 4 and parts[4] else []
                rows.append((parts[0], parts[1], EA, EI, sp, pre, pts, stg))
        except ValueError as e:
            QMessageBox.warning(self, "Invalid input", f"Could not read: {e}")
            return
        self.before_change()
        self.project.structures = []
        for t, name, EA, EI, sp, pre, pts, stg in rows:
            self.project.add_structure(t, pts, name, EA=EA, EI=EI, spacing=sp, prestress=pre, analyses=stg)
        self.after_change("Edit structures")

    # -- beginners ------------------------------------------------------------
    def quick_slope(self):
        if not self.maybe_save():
            return
        d = QuickSlopeDialog(self, self.project.units)
        if not d.exec() or d.project is None:
            return
        self.show_workspace()
        self.set_project(d.project)
        self.canvas.zoom_fit()
        if d.solve_now.isChecked():
            self.solve_current()

    def _toggle_steps(self, on):
        self.settings.setValue("ui/step_guide", "true" if on else "false")
        self.stepbar.setVisible(on)
        if on:
            self.stepbar.update_steps(self.project, self.current_analysis())

    def step_clicked(self, key):
        if key in ("region", "piezo", "bc", "entry_exit"):
            if key == "entry_exit":
                self.entry_exit_dialog()
                return
            self.draw_actions[key].setChecked(True)
            self.set_draw_mode(key)
        elif key == "materials":
            self.edit_materials()
        elif key == "analysis":
            self.edit_analysis()
        elif key == "solve":
            self.solve_current()
        elif key == "results":
            self.a_results.setChecked(True)
            self.set_view("results")

    def edit_flux_sections(self):
        lines = [f"{f.name}; " + " ".join(f"{x:g},{y:g}" for x, y in f.points) for f in self.project.flux_sections]
        d = TextEditDialog("Flux Sections", "One per line:  name; x1,y1 x2,y2 ...  (flow to the right of the "
                           "drawing direction is positive)", "\n".join(lines), self)
        if not d.exec():
            return
        out = []
        try:
            for line in d.text().splitlines():
                if not line.strip():
                    continue
                name, pts = [s.strip() for s in line.split(";")]
                pp = [[float(v) for v in p.split(",")] for p in pts.split()]
                if len(pp) < 2:
                    raise ValueError(line)
                out.append((name, pp))
        except ValueError as e:
            QMessageBox.warning(self, "Invalid input", f"Could not read: {e}")
            return
        self.before_change()
        self.project.flux_sections = []
        for name, pp in out:
            self.project.add_flux_section(name, pp)
        self.after_change("Edit flux sections")

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
        t = r["type"]
        u = self.project.unit
        if t != "slope" and self.probe is not None and result_times(r):
            self.graph_probe(a, r)
            return
        if t == "stress" and r.get("settlement_history"):
            GraphDialog("Consolidation settlement", r["times"], r["settlement_history"], "Time (s)",
                        f"Settlement ({u('length')})", parent=self).exec()
            return
        if t == "stress" and r.get("srm_trials"):
            tr = sorted(r["srm_trials"])
            GraphDialog("Strength reduction trials", [x[0] for x in tr], [1.0 if x[1] else 0.0 for x in tr],
                        "Strength reduction factor", "Converged (1) / failed (0)", bars=True, parent=self).exec()
            return
        if t == "stress" and r.get("history"):
            h = r["history"]
            GraphDialog("Load steps", [x["step"] for x in h], [x["max_disp"] for x in h], "Load step",
                        f"Max displacement ({u('length')})", parent=self).exec()
            return
        if t == "dynamic":
            GraphDialog("Input acceleration", r["input_times"], r["input_acc"], "Time (s)", "Acceleration (g)",
                        parent=self).exec()
            return
        if t != "slope":
            if r.get("history"):
                GraphDialog("Convergence", list(range(1, len(r["history"]) + 1)), r["history"], "Iteration",
                            "Max change", parent=self).exec()
            else:
                QMessageBox.information(self, APP_NAME, "Click a point in the results view of a transient "
                                        "analysis to graph it against time.")
            return
        if r.get("newmark") and r["newmark"].get("displacement_history"):
            nm = r["newmark"]
            GraphDialog(f"Newmark displacement (ky = {nm['ky']:.3f} g)", nm["times"], nm["displacement_history"],
                        "Time (s)", f"Permanent displacement ({u('length')})", parent=self).exec()
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

    def graph_probe(self, a, r):
        import numpy as np
        from scipy.interpolate import LinearNDInterpolator
        x, y = self.probe
        times = result_times(r)
        o = dict(self.opts)
        vals = []
        label = unit = ""
        for i in range(len(times)):
            o["time_index"] = i
            v, _, label, unit = Renderer(self.project, a, View(), None, mode="results", opts=o).field_values(r)
            vals.append(float(LinearNDInterpolator(np.asarray(r["nodes"]), v)(x, y)))
        GraphDialog(f"{label} at ({x:.2f}, {y:.2f})", times, vals, "Time (s)",
                    f"{label} ({unit})" if unit else label, parent=self).exec()

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
        """Home page inside the window: New, Open, recent projects, examples and getting-started links."""
        self.home.populate(self.recent_files(), list(EXAMPLES), self.project.units)
        if self.pages.currentWidget() is not self.home:
            keep = getattr(getattr(self, "chat", None), "dock", None)
            self._hidden_on_home = [w for w in self.findChildren(QDockWidget) + self.findChildren(QToolBar)
                                    if w.isVisible() and w is not keep]
            for w in self._hidden_on_home:
                w.hide()
            self.pages.setCurrentWidget(self.home)
        self.setWindowTitle(APP_NAME)

    def show_workspace(self):
        if self.pages.currentWidget() is self.home:
            self.pages.setCurrentWidget(self.drawing)
            for w in self._hidden_on_home:
                w.show()
            self._hidden_on_home = []

    def on_home(self):
        return self.pages.currentWidget() is self.home

    def home_chosen(self, action, arg, units):
        if action == "new":
            if not self.maybe_save():
                return
            self.set_project(new_project(units, arg or "slope"))
            self.set_draw_mode("region")
            self.draw_actions["region"].setChecked(True)
            self.edit_analysis()
        elif action == "open":
            self.open_file()
        elif action == "recent":
            self.open_file(arg)
        elif action == "example":
            self.open_example(arg)
        elif action == "ai":
            self.ai_builder()
        elif action == "quick":
            self.quick_slope()
        elif action == "guide":
            self.quick_guide()
        elif action in ("docs", "issues"):
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(QUrl("https://github.com/ArghoAdhikary/GeoLab" +
                                          ("/issues" if action == "issues" else "#readme")))

    # -- appearance and AI assistant ------------------------------------------
    def _theme_changed(self, dark):
        set_dark_icons(dark)
        for act, name in self._icon_actions:
            act.setIcon(_tool_icon(name))
        self.home.set_dark(dark)
        self.canvas.update()

    def set_theme(self, mode):
        self.settings.setValue("ui/theme", mode)
        apply_theme(mode)
        if mode in self.a_theme:
            self.a_theme[mode].setChecked(True)

    def preferences(self, tab="appearance"):
        from .prefs import PreferencesDialog
        d = PreferencesDialog(self.settings, self, tab)
        if d.exec() != QDialog.Accepted:
            return
        d.save()
        self.set_theme(d.theme())
        for win in [self] + _EXTRA_WINDOWS:
            win.chat.refresh_settings()
            win.chat.set_enabled(d.enabled.isChecked())

    def open_in_new_window(self, project):
        win = MainWindow()
        _EXTRA_WINDOWS.append(win)
        win.destroyed.connect(lambda *_: _EXTRA_WINDOWS.remove(win) if win in _EXTRA_WINDOWS else None)
        win.setAttribute(Qt.WA_DeleteOnClose)
        win.set_project(project, None, dirty=True)
        g = self.geometry()
        win.setGeometry(g.x() + 40 * len(_EXTRA_WINDOWS), g.y() + 40 * len(_EXTRA_WINDOWS), g.width(), g.height())
        win.show()
        return win

    def quick_guide(self):
        TextDialog("Quick Guide", GUIDE, self).exec()

    def about(self):
        QMessageBox.about(self, f"About {APP_NAME}",
                          f"<b>{APP_NAME} {__version__}</b><br>2D geotechnical analysis: slope stability, "
                          "seepage, stress-deformation and consolidation, earthquake response, heat transfer "
                          "with freezing, contaminant transport and air flow.<br><br>"
                          f"Python {sys.version.split()[0]}, Qt for Python.<br>MIT License.")

    def closeEvent(self, e):
        if self.worker is not None:
            self.worker.cancelled = True
            self.worker.wait(3000)
        if not self.maybe_save():
            e.ignore()
            return
        self.show_workspace()          # never remember the home page's hidden docks and toolbars
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


GUIDE = """GeoLab quick guide

0. Easiest start
   - File > New Quick Slope (Ctrl+Shift+N): type the height, steepness, soil layers and water depth;
     GeoLab draws the model and solves it. Change anything afterwards.
   - The step guide above the drawing shows the steps of the selected analysis. The blue step is the
     next one; click it to open the right tool. Ticked steps are done. View > Show Step Guide hides it.
   - Hover over any drawing tool for a one-line explanation.

1. Define the problem
   - File > New Project: pick the first analysis type (slope, seepage, stress, dynamic, thermal,
     contaminant transport or air flow). More analyses can be added later (Define > Add Analysis).
   - Define > Materials: one material list with tabs for strength, probabilistic, hydraulic, stress,
     dynamic, thermal, transport and air properties. Only the tabs an analysis uses matter.
   - Draw > Regions: click the corners of each soil region (snaps to grid and existing points).
     Click the first point, press Enter or right-click to close. Edit > Edit Region Points for typed input.
   - Draw > Materials: pick a material in the toolbar and click regions to assign it.
   - Draw > Piezometric Line, Point Loads, Surcharge Loads, Reinforcement, Flux Sections as needed.

2. Analyses and their parents
   - Each analysis can have a parent (Define > Analyses > Parent). Children use their parents' results:
     seepage -> pore pressures for slope and stress, flow for transport, saturation for air flow;
     stress -> stresses for the finite element slope method and initial stresses for later stages;
     dynamic -> Newmark displacement of a slope; earlier seepage / thermal -> initial conditions.
   - Define > Add Child Analysis creates a child of the selected analysis with sensible settings.

3. Boundary conditions
   - Draw > Boundary Conditions offers the types that fit the selected analysis (hydraulic, stress,
     thermal, transport or air). A boundary can vary with time (value vs time table) and can be limited
     to one analysis ("Applies to"), e.g. a footing displacement used only in the load stage.
   - Head boundaries above the water level automatically act as potential seepage faces.

4. Slope stability
   - Methods: Ordinary, Bishop, Janbu (simplified, corrected, generalized), Spencer, Morgenstern-Price,
     Corps of Engineers 1 and 2, Lowe-Karafiath, Sarma, and the finite element stress method.
   - Searches: entry and exit, grid and radius, grid and tangent lines, block, auto locate, fully
     specified; optional optimization of the critical surface.
   - Loads and Cracks tab: seismic kh / kv, tension crack depth or angle and its water, optimization.

5. Solve and review
   - Analysis > Verify (F6), Solve (F5), Solve All (Shift+F5).
   - Results view (Ctrl+2): pick the contour field and the time step in the Results toolbar;
     View > Show Deformed Mesh for stress results. Click the drawing to read every value at a point.
   - View > Graph: load steps, consolidation settlement, input motion, Newmark displacement, or, after
     clicking a point in a transient result, that point against time.
   - View > Report, Slice Information. File > Export > PDF, PNG, CSV.

6. AI help
   - AI Assistant chat: the round button in the bottom-right corner opens a small chat box; its
     expand button turns it into a side panel, its minus button shrinks it back to the button.
     Ask it to build slopes ("make two 8 m clay slopes, one with water"), change the open model
     ("raise the water table 1 m", "set clay c' to 15") or solve and explain the result.
     Edit > Preferences > AI Assistant turns it on or off and chooses the AI: Claude or ChatGPT with
     an API key, any OpenAI-compatible service (Gemini, OpenRouter, Ollama...), or your Claude /
     ChatGPT account through the Claude Code or Codex app.
   - Help > AI Slope Builder: describe one slope in words and Claude builds the model.
   Review every value before relying on the result.

7. Construction stages, walls and anchors (stress-deformation)
   - Make one stress analysis per stage, each a child of the previous one (in situ first).
   - Analysis settings > Construction Stage: untick the regions dug out (excavation) or not built yet
     (fill placed later). Removed soil releases its stresses; new fill adds its weight.
   - Draw > Structures: walls / beams (bending), anchors / struts (axial, optional prestress), geogrids
     (tension only); choose the stages each one is present in. Results show axial force and moment.
   - Soil models: linear elastic, Mohr-Coulomb, Modified Cam Clay, hyperbolic and Hardening Soil;
     consolidation stages can be elastic-plastic.

8. More
   - Slope: Rapid Drawdown tab (Duncan-Wright-Wong): draw the water table at the full reservoir,
     enter the level after drawdown and the R envelope (c_R, phi_R) of each clay in Materials.
   - Seepage climate boundary: plant transpiration and root depth (root water uptake).
   - Define > Project Properties: switching metric / imperial converts every value.

9. Day and night
   - View > Theme (or Edit > Preferences): Light, Dark or Auto (follows the operating system).

Mouse: wheel zooms, middle button pans, right-click finishes a line. Keys: Esc select, F fit, Del delete region.
"""
