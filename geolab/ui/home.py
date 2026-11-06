"""Home page shown inside the main window when the app opens: New, Open and Getting Started."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QPushButton, QScrollArea, QStyle, QVBoxLayout, QWidget)

from .. import APP_NAME, __version__
from ..model import ANALYSIS_KINDS
from .icons import kind_icon, kind_pixmap

KIND_TITLES = {"slope": "Slope stability", "seepage": "Seepage", "stress": "Stress-deformation",
               "dynamic": "Dynamic (earthquake)", "thermal": "Thermal", "transport": "Contaminant transport",
               "air": "Air flow"}

STYLE = """
#home { background: %(page)s; }
#card { background: %(card)s; border-radius: 4px; }
#big { background: #4a8fe7; color: white; font-size: 20pt; border: none; border-radius: 2px;
       text-align: left; padding: 10px 22px; }
#big:hover { background: #3b7fd6; }
#big:pressed { background: #2f6cbd; }
#heading { font-size: 11pt; font-weight: 600; color: %(head)s; }
#kindbtn { background: %(field)s; border: none; border-radius: 3px; text-align: left; padding: 6px 10px;
           font-size: 11pt; color: %(text)s; }
#kindbtn:hover { background: %(hover)s; }
#kindbtn:checked { background: %(checked)s; }
#tag { color: #888; font-size: 9pt; }
#link { border: none; background: transparent; color: %(muted)s; font-size: 11pt; text-align: left; padding: 4px; }
#link:hover { color: %(link)s; text-decoration: underline; }
#banner { background: #5a5a5a; color: white; font-size: 10.5pt; padding: 8px 14px; }
QComboBox#field { background: %(field)s; color: %(text)s; border: none; padding: 6px 10px; font-size: 11pt;
                  min-height: 22px; }
QListWidget#recent { border: none; font-size: 11pt; color: %(muted)s; background: %(card)s; }
QListWidget#recent::item { padding: 6px 2px; }
QListWidget#recent::item:hover { color: %(link)s; background: transparent; }
QScrollArea#cardscroll, QScrollArea#cardscroll > QWidget > QWidget { background: %(card)s; }
"""

COLORS = {
    False: {"page": "#eeeeee", "card": "#ffffff", "head": "#444444", "field": "#f1f1f1", "text": "#222222",
            "hover": "#e2ecfb", "checked": "#d3e3fa", "muted": "#555555", "link": "#1d5fbf",
            "title": "#333333", "version": "#666666", "badge": "color:#555; border:1px solid #bbb; background:#f6f6f6"},
    True: {"page": "#1b1c1f", "card": "#2b2d30", "head": "#d0d0d0", "field": "#35373b", "text": "#e6e6e6",
           "hover": "#33415a", "checked": "#2f4a73", "muted": "#b8bbc0", "link": "#6aa6ff",
           "title": "#eeeeee", "version": "#a0a0a0", "badge": "color:#c8c8c8; border:1px solid #555; background:#35373b"},
}


def _heading(text):
    lab = QLabel(text)
    lab.setObjectName("heading")
    return lab


class HomePage(QWidget):
    """Signals ``chosen(action, arg, units)`` with action in new / open / recent / example / ai / guide / docs."""

    chosen = Signal(str, object, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("home")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._dark = False
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(28, 18, 28, 18)
        top = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(kind_pixmap("slope", 30))
        top.addWidget(logo)
        self.title = title = QLabel()
        top.addWidget(title)
        top.addSpacing(30)
        self.edition = edition = QLabel("Free and open source (MIT)")
        top.addWidget(edition)
        top.addStretch(1)
        lay.addLayout(top)
        lay.addSpacing(14)

        cols = QHBoxLayout()
        cols.setSpacing(30)
        cols.addWidget(self._new_card(), 0)
        cols.addWidget(self._open_card(), 0)
        cols.addWidget(self._links(), 1)
        lay.addLayout(cols, 1)
        outer.addWidget(body, 1)

        banner = QLabel(f"You are using <b>{APP_NAME}</b>, free software: every analysis type is available "
                        "with no licence. Projects can be opened from and saved to GeoStudio (.gsz) files.")
        banner.setObjectName("banner")
        banner.setWordWrap(True)
        outer.addWidget(banner)
        self.set_dark(False)

    def set_dark(self, dark: bool):
        """Restyle the start page for the day (light) or night (dark) theme."""
        self._dark = bool(dark)
        c = COLORS[self._dark]
        self.setStyleSheet(STYLE % c)
        self.title.setText(f"<span style='font-size:19pt;color:{c['title']}'><b>{APP_NAME}</b> "
                           f"<span style='color:{c['version']}'>{__version__}</span></span>")
        self.edition.setStyleSheet(c["badge"] + "; padding:3px 10px")

    # ------------------------------------------------------------------
    def _card(self):
        card = QFrame()
        card.setObjectName("card")
        card.setFixedWidth(345)
        v = QVBoxLayout(card)
        v.setContentsMargins(18, 18, 18, 18)
        return card, v

    def _big(self, text, icon):
        b = QPushButton(f"  {text}")
        b.setObjectName("big")
        b.setIcon(self.style().standardIcon(icon))
        b.setIconSize(QSize(24, 24))
        b.setMinimumHeight(62)
        b.setCursor(Qt.PointingHandCursor)
        return b

    def _new_card(self):
        card, v = self._card()
        self.new_btn = self._big("New...", QStyle.SP_FileIcon)
        self.new_btn.clicked.connect(lambda: self._emit("new", self.selected_kind))
        v.addWidget(self.new_btn)
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color:#ddd")
        v.addSpacing(8)
        v.addWidget(line)
        v.addSpacing(6)
        v.addWidget(_heading("Select Template"))
        self.units = QComboBox()
        self.units.setObjectName("field")
        self.units.addItem("Metric (m, kN, kPa)", "metric")
        self.units.addItem("Imperial (ft, lbf, psf)", "imperial")
        v.addWidget(self.units)
        v.addSpacing(8)
        v.addWidget(_heading("Select Geometry Dimension"))
        dim = QComboBox()
        dim.setObjectName("field")
        dim.addItem("2D (plane strain)")
        v.addWidget(dim)
        v.addSpacing(8)
        v.addWidget(_heading("Select Analysis"))
        holder = QWidget()
        hv = QVBoxLayout(holder)
        hv.setContentsMargins(0, 0, 4, 0)
        hv.setSpacing(6)
        self.kind_buttons = {}
        self.selected_kind = "slope"
        for kind in ANALYSIS_KINDS:
            b = QPushButton(KIND_TITLES.get(kind, kind))
            b.setObjectName("kindbtn")
            b.setIcon(kind_icon(kind))
            b.setIconSize(QSize(24, 24))
            b.setMinimumHeight(40)
            b.setCursor(Qt.PointingHandCursor)
            b.setToolTip(f"Start a new project with a {ANALYSIS_KINDS[kind].lower()} analysis")
            b.clicked.connect(lambda _=False, k=kind: self._emit("new", k))
            tag = QLabel("FREE", b)
            tag.setObjectName("tag")
            row = QHBoxLayout(b)
            row.setContentsMargins(0, 0, 12, 0)
            row.addStretch(1)
            row.addWidget(tag)
            hv.addWidget(b)
            self.kind_buttons[kind] = b
        hv.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidget(holder)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setObjectName("cardscroll")
        v.addWidget(scroll, 1)
        return card

    def _open_card(self):
        card, v = self._card()
        b = self._big("Open...", QStyle.SP_DirOpenIcon)
        b.clicked.connect(lambda: self._emit("open", None))
        v.addWidget(b)
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color:#ddd")
        v.addSpacing(8)
        v.addWidget(line)
        v.addSpacing(6)
        v.addWidget(_heading("Recent Projects"))
        self.recent = QListWidget()
        self.recent.setObjectName("recent")
        self.recent.setCursor(Qt.PointingHandCursor)
        self.recent.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.recent.setTextElideMode(Qt.ElideMiddle)
        self.recent.itemClicked.connect(lambda it: self._emit("recent", it.data(Qt.UserRole)))
        v.addWidget(self.recent, 3)
        v.addWidget(_heading("Example Projects"))
        self.examples = QListWidget()
        self.examples.setObjectName("recent")
        self.examples.setCursor(Qt.PointingHandCursor)
        self.examples.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.examples.setTextElideMode(Qt.ElideRight)
        self.examples.itemClicked.connect(lambda it: self._emit("example", it.text()))
        v.addWidget(self.examples, 4)
        return card

    def _links(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(10, 6, 0, 0)
        v.addWidget(_heading("Getting Started?"))
        v.addSpacing(6)
        S = QStyle
        for text, action, icon in (("Read the quick guide for new users", "guide", S.SP_MessageBoxQuestion),
                                   ("Open a worked example project", "example_first", S.SP_DirOpenIcon),
                                   ("Build a slope from a description with AI", "ai", S.SP_ComputerIcon),
                                   ("Read the full documentation online", "docs", S.SP_FileDialogDetailedView),
                                   ("Report a problem or ask for a feature", "issues", S.SP_MessageBoxInformation)):
            b = QPushButton(f"  {text}")
            b.setObjectName("link")
            b.setIcon(self.style().standardIcon(icon))
            b.setIconSize(QSize(20, 20))
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, a=action: self._emit(a, None))
            v.addWidget(b)
        v.addStretch(1)
        return w

    # ------------------------------------------------------------------
    def _emit(self, action, arg):
        if action == "example_first" and self.examples.count():
            action, arg = "example", self.examples.item(0).text()
        self.chosen.emit(action, arg, self.units.currentData())

    def populate(self, recent: list[str], examples: list[str], units: str = "metric"):
        self.recent.clear()
        for path in recent:
            it = QListWidgetItem(Path(path).name)
            it.setData(Qt.UserRole, path)
            it.setToolTip(path)
            self.recent.addItem(it)
        if not recent:
            it = QListWidgetItem("(none yet)")
            it.setFlags(Qt.NoItemFlags)
            self.recent.addItem(it)
        self.examples.clear()
        for e in examples:
            self.examples.addItem(e)
        self.units.setCurrentIndex(max(0, self.units.findData(units)))
