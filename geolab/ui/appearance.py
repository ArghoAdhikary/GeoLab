"""Interface styles, colour schemes, and per-element colours and fonts.

Three layers, each one on top of the last:

1. **Interface style**: the shape of the widgets. Options are Classic, Modern, Compact, Flat and
   Large / touch.
2. **Colour scheme**: the palette for day and night, plus the accent colour. Options include GeoLab
   blue, Ocean, Forest, Sunset, Purple, Graphite, Solarized and High contrast.
3. **Advanced**: a colour (background and text) and a font for any part of the window. This covers
   the title bar, menu bar, menus, toolbars, panel title bars, tabs, status bar, tooltips, step
   guide, chat head and chat box, and the drawing area.

The settings are kept in QSettings under ``ui/*``. The colours and fonts can be saved to and loaded
from a ``.geolab-theme`` (JSON) file. Fonts added by the user (.ttf / .otf) are copied to the GeoLab
fonts folder and loaded at every start.
"""
from __future__ import annotations

import json
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette

# --------------------------------------------------------------------------- styles and schemes
STYLES = {
    "classic": "Classic (standard Windows look)",
    "modern": "Modern (rounded, airy)",
    "compact": "Compact (more room for the drawing)",
    "flat": "Flat (minimal, no borders)",
    "touch": "Large / touch (bigger buttons and text)",
}

# window, base (text boxes), text, button, highlight, accent, link, alt (alternate rows), mid (lines)
SCHEMES = {
    "geolab": {"label": "GeoLab blue",
               "light": dict(window="#f0f0f0", base="#ffffff", text="#1a1a1a", button="#f0f0f0",
                             highlight="#3d7fd9", accent="#2f6fe0", link="#1d5fbf", alt="#f5f5f5", mid="#b8b8b8"),
               "dark": dict(window="#2b2d30", base="#1e1f22", text="#e6e6e6", button="#35373b",
                            highlight="#3d6fb8", accent="#2f6fe0", link="#6aa6ff", alt="#26282b", mid="#2f3236")},
    "ocean": {"label": "Ocean (teal)",
              "light": dict(window="#eef5f7", base="#ffffff", text="#10262e", button="#e3eef2",
                            highlight="#1b8a9e", accent="#0f7c91", link="#0b6b7d", alt="#f4f9fa", mid="#a9c3ca"),
              "dark": dict(window="#16262c", base="#0f1c21", text="#dcecef", button="#1f343b",
                           highlight="#1b7f91", accent="#22a3b8", link="#5fd0e0", alt="#142328", mid="#2a4249")},
    "forest": {"label": "Forest (green)",
               "light": dict(window="#f0f4ee", base="#ffffff", text="#17241a", button="#e6eee3",
                             highlight="#3f8a4f", accent="#2e7d3f", link="#276b35", alt="#f6f9f5", mid="#b3c4b0"),
               "dark": dict(window="#1d261e", base="#141b15", text="#e1ebe2", button="#283429",
                            highlight="#3c7a48", accent="#4caf62", link="#82d494", alt="#192119", mid="#324033")},
    "sunset": {"label": "Sunset (orange)",
               "light": dict(window="#f7f1ec", base="#ffffff", text="#2a1a12", button="#f0e6de",
                             highlight="#d9692b", accent="#d35b1c", link="#b44a12", alt="#fbf7f3", mid="#d1bcae"),
               "dark": dict(window="#2c221d", base="#1f1814", text="#f0e3da", button="#3a2d26",
                            highlight="#b8561f", accent="#ef7a36", link="#ffad7a", alt="#251c18", mid="#4a3a31")},
    "purple": {"label": "Purple",
               "light": dict(window="#f3f0f7", base="#ffffff", text="#1f1729", button="#eae4f1",
                             highlight="#7b4fc9", accent="#6a3fbd", link="#5a32a6", alt="#f8f6fb", mid="#c2b6d4"),
               "dark": dict(window="#25202d", base="#1a1620", text="#e9e2f2", button="#322a3d",
                            highlight="#6a46b0", accent="#9b72e8", link="#c2a6ff", alt="#201b27", mid="#3f3550")},
    "graphite": {"label": "Graphite (grey)",
                 "light": dict(window="#ececec", base="#fbfbfb", text="#202020", button="#e2e2e2",
                               highlight="#5c6670", accent="#4b5560", link="#3a4550", alt="#f3f3f3", mid="#b0b0b0"),
                 "dark": dict(window="#232323", base="#1a1a1a", text="#e0e0e0", button="#2e2e2e",
                              highlight="#5a6470", accent="#8a96a3", link="#b5c2cf", alt="#1f1f1f", mid="#3a3a3a")},
    "solarized": {"label": "Solarized",
                  "light": dict(window="#fdf6e3", base="#fffbf0", text="#073642", button="#eee8d5",
                                highlight="#268bd2", accent="#268bd2", link="#2aa198", alt="#f7f0dc", mid="#c9c2ad"),
                  "dark": dict(window="#073642", base="#002b36", text="#eee8d5", button="#0b4452",
                               highlight="#268bd2", accent="#2aa198", link="#93a1a1", alt="#04313c", mid="#1d5361")},
    "contrast": {"label": "High contrast",
                 "light": dict(window="#ffffff", base="#ffffff", text="#000000", button="#ffffff",
                               highlight="#0000c0", accent="#0000c0", link="#0000ee", alt="#f0f0f0", mid="#000000"),
                 "dark": dict(window="#000000", base="#000000", text="#ffffff", button="#000000",
                              highlight="#ffd400", accent="#ffd400", link="#8ad4ff", alt="#141414", mid="#ffffff")},
}

# element key -> (label, colour slots {slot: label}, has a font)
ELEMENTS = {
    "window": ("Window (background and text)", {"bg": "Background", "fg": "Text"}, True),
    "input": ("Text boxes, lists and tables", {"bg": "Background", "fg": "Text"}, False),
    "button": ("Buttons", {"bg": "Background", "fg": "Text"}, True),
    "selection": ("Selection / highlight", {"bg": "Background", "fg": "Text"}, False),
    "titlebar": ("Window title bar (Windows 11)", {"bg": "Background", "fg": "Text"}, False),
    "menubar": ("Menu bar", {"bg": "Background", "fg": "Text"}, True),
    "menu": ("Menus (drop-down)", {"bg": "Background", "fg": "Text"}, True),
    "toolbar": ("Toolbars", {"bg": "Background", "fg": "Text"}, True),
    "dock": ("Panel title bars (Explorer, Properties, Log)", {"bg": "Background", "fg": "Text"}, True),
    "tabs": ("Tabs", {"bg": "Background", "fg": "Text"}, True),
    "statusbar": ("Status bar", {"bg": "Background", "fg": "Text"}, True),
    "tooltip": ("Tooltips", {"bg": "Background", "fg": "Text"}, True),
    "stepbar": ("Step guide bar", {"bg": "Background", "fg": "Next-step button"}, True),
    "chat_head": ("Chat head (round button)", {"bg": "Button colour", "fg": "Icon"}, False),
    "chat_header": ("Chat box title bar", {"bg": "Background", "fg": "Text"}, True),
    "chat_box": ("Chat box (conversation)", {"bg": "Background", "fg": "Text"}, True),
    "chat_user": ("Chat: your messages", {"bg": "Bubble", "fg": "Text"}, False),
    "chat_ai": ("Chat: assistant messages", {"bg": "Bubble", "fg": "Text"}, False),
    "chat_send": ("Chat: Send button", {"bg": "Background", "fg": "Text"}, False),
    "canvas": ("Drawing area (screen only)", {"bg": "Background", "fg": "Grid lines"}, True),
}


@dataclass
class Config:
    style: str = "classic"
    scheme: str = "geolab"
    accent: str = ""                  # overrides the scheme's accent
    font: str = ""                    # whole interface (QFont.toString)
    colors: dict = field(default_factory=dict)    # element -> {slot: "#rrggbb"}
    fonts: dict = field(default_factory=dict)     # element -> QFont.toString()

    def to_dict(self):
        return {"style": self.style, "scheme": self.scheme, "accent": self.accent, "font": self.font,
                "colors": self.colors, "fonts": self.fonts}

    @classmethod
    def from_dict(cls, d):
        c = cls()
        c.style = d.get("style") if d.get("style") in STYLES else "classic"
        c.scheme = d.get("scheme") if d.get("scheme") in SCHEMES else "geolab"
        c.accent = _hex(d.get("accent")) or ""
        c.font = str(d.get("font") or "")
        c.colors = {k: {s: _hex(v) for s, v in (slots or {}).items() if _hex(v) and s in ELEMENTS[k][1]}
                    for k, slots in (d.get("colors") or {}).items() if k in ELEMENTS}
        c.colors = {k: v for k, v in c.colors.items() if v}
        c.fonts = {k: str(v) for k, v in (d.get("fonts") or {}).items() if k in ELEMENTS and ELEMENTS[k][2] and v}
        return c


def _hex(v):
    if not v:
        return None
    c = QColor(str(v))
    return c.name() if c.isValid() else None


_cfg = Config()
_dark = False


def config() -> Config:
    return _cfg


def set_config(cfg: Config):
    global _cfg
    _cfg = cfg


def load(qs) -> Config:
    """Read the appearance settings from QSettings."""
    def js(key):
        raw = qs.value(key, "") or ""
        try:
            return json.loads(raw) if isinstance(raw, str) and raw else (raw if isinstance(raw, dict) else {})
        except ValueError:
            return {}
    cfg = Config.from_dict({"style": qs.value("ui/style", "classic"), "scheme": qs.value("ui/scheme", "geolab"),
                            "accent": qs.value("ui/accent", ""), "font": qs.value("ui/font", ""),
                            "colors": js("ui/colors"), "fonts": js("ui/fonts")})
    set_config(cfg)
    return cfg


def save(qs, cfg: Config):
    qs.setValue("ui/style", cfg.style)
    qs.setValue("ui/scheme", cfg.scheme)
    qs.setValue("ui/accent", cfg.accent)
    qs.setValue("ui/font", cfg.font)
    qs.setValue("ui/colors", json.dumps(cfg.colors))
    qs.setValue("ui/fonts", json.dumps(cfg.fonts))


def export_theme(cfg: Config, path):
    Path(path).write_text(json.dumps({"geolab_theme": 1, **cfg.to_dict()}, indent=2), encoding="utf-8")


def import_theme(path) -> Config:
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(d, dict):
        raise ValueError("not a GeoLab theme file")
    return Config.from_dict(d)


# --------------------------------------------------------------------------- lookups
def scheme_colors(dark: bool | None = None, cfg: Config | None = None) -> dict:
    cfg = cfg or _cfg
    dark = _dark if dark is None else dark
    c = dict(SCHEMES.get(cfg.scheme, SCHEMES["geolab"])["dark" if dark else "light"])
    if cfg.accent:
        c["accent"] = cfg.accent
    return c


def accent() -> str:
    return scheme_colors()["accent"]


def color(element: str, slot: str, default: str | None = None) -> str | None:
    """The user's colour for one part of the window, or ``default``."""
    return (_cfg.colors.get(element) or {}).get(slot) or default


def font(element: str, base: QFont | None = None) -> QFont | None:
    """The user's font for one part of the window (or the interface font), or None."""
    s = _cfg.fonts.get(element) or (_cfg.font if element != "canvas" else "")
    if not s:
        return None
    f = QFont(base) if base is not None else QFont()
    f.fromString(s)
    return f


def font_css(element: str) -> str:
    f = font(element)
    if f is None:
        return ""
    out = f"font-family: '{f.family()}';"
    if f.pointSizeF() > 0:
        out += f" font-size: {f.pointSizeF():g}pt;"
    if f.bold():
        out += " font-weight: bold;"
    if f.italic():
        out += " font-style: italic;"
    return out


def canvas_colors(dark: bool) -> dict:
    from .theme import CANVAS
    c = dict(CANVAS[bool(dark)])
    c["background"] = color("canvas", "bg", c["background"])
    c["grid"] = color("canvas", "fg", c["grid"])
    if _cfg.scheme == "contrast":
        c["grid"] = color("canvas", "fg", "#606060" if not dark else "#a0a0a0")
    return c


# --------------------------------------------------------------------------- palette and style sheet
def palette(dark: bool, cfg: Config | None = None) -> QPalette:
    from .theme import dark_palette, light_palette
    cfg = cfg or _cfg
    if cfg.scheme == "geolab" and not cfg.colors and not cfg.accent:
        return dark_palette() if dark else light_palette()        # unchanged from earlier versions
    s = scheme_colors(dark, cfg)
    p = dark_palette() if dark else light_palette()

    def setc(role, col):
        p.setColor(QPalette.Active, role, QColor(col))
        p.setColor(QPalette.Inactive, role, QColor(col))
    win = QColor(s["window"])
    setc(QPalette.Window, s["window"])
    setc(QPalette.WindowText, s["text"])
    setc(QPalette.Base, s["base"])
    setc(QPalette.AlternateBase, s["alt"])
    setc(QPalette.Text, s["text"])
    setc(QPalette.Button, s["button"])
    setc(QPalette.ButtonText, s["text"])
    setc(QPalette.Highlight, s["highlight"])
    setc(QPalette.HighlightedText, "#000000" if QColor(s["highlight"]).lightness() > 170 else "#ffffff")
    setc(QPalette.Link, s["link"])
    setc(QPalette.Mid, s["mid"])
    setc(QPalette.Light, win.lighter(130).name())
    setc(QPalette.Midlight, win.lighter(112).name())
    setc(QPalette.Dark, win.darker(150).name())
    setc(QPalette.ToolTipBase, s["base"] if dark else "#ffffe1")
    setc(QPalette.ToolTipText, s["text"])
    ov = cfg.colors
    for el, roles in (("window", (QPalette.Window, QPalette.WindowText)), ("input", (QPalette.Base, QPalette.Text)),
                      ("button", (QPalette.Button, QPalette.ButtonText)),
                      ("selection", (QPalette.Highlight, QPalette.HighlightedText)),
                      ("tooltip", (QPalette.ToolTipBase, QPalette.ToolTipText))):
        o = ov.get(el) or {}
        if o.get("bg"):
            setc(roles[0], o["bg"])
        if o.get("fg"):
            setc(roles[1], o["fg"])
    return p


_SHAPES = {
    "modern": """
QPushButton { border: 1px solid palette(mid); border-radius: 7px; padding: 5px 14px; background: palette(button); }
QPushButton:hover { border-color: palette(highlight); }
QPushButton:default { border: 2px solid palette(highlight); }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit { border: 1px solid palette(mid);
    border-radius: 6px; padding: 3px 6px; background: palette(base); }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus { border-color: palette(highlight); }
QGroupBox { border: 1px solid palette(mid); border-radius: 8px; margin-top: 14px; padding-top: 6px; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
QTabBar::tab { padding: 6px 14px; border-top-left-radius: 7px; border-top-right-radius: 7px; }
QToolBar { spacing: 4px; padding: 3px; border: none; }
QToolButton { border-radius: 6px; padding: 3px; }
QToolButton:hover { background: palette(midlight); }
QMenu { border: 1px solid palette(mid); border-radius: 8px; padding: 4px; }
QMenu::item { padding: 5px 24px 5px 22px; border-radius: 5px; }
QMenu::item:selected { background: palette(highlight); color: palette(highlighted-text); }
QDockWidget::title { padding: 6px 8px; }
QStatusBar { border-top: 1px solid palette(mid); }
""",
    "compact": """
QPushButton { padding: 2px 8px; min-height: 18px; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox { padding: 0px 3px; min-height: 18px; }
QToolBar { spacing: 0px; padding: 0px; }
QToolButton { padding: 1px; }
QMenu::item { padding: 2px 18px 2px 18px; }
QTabBar::tab { padding: 2px 8px; }
QDockWidget::title { padding: 1px 4px; }
QStatusBar { min-height: 16px; }
""",
    "flat": """
QPushButton { border: none; border-radius: 3px; padding: 5px 12px; background: palette(midlight); }
QPushButton:hover { background: palette(highlight); color: palette(highlighted-text); }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit { border: none;
    border-bottom: 1px solid palette(mid); padding: 3px 4px; background: palette(base); }
QLineEdit:focus, QComboBox:focus { border-bottom: 2px solid palette(highlight); }
QGroupBox { border: none; margin-top: 16px; font-weight: bold; }
QGroupBox::title { subcontrol-origin: margin; left: 2px; }
QToolBar { border: none; spacing: 2px; }
QToolButton { border: none; padding: 3px; }
QToolButton:hover { background: palette(midlight); }
QMenu { border: 1px solid palette(mid); }
QMenu::item { padding: 5px 22px; }
QMenu::item:selected { background: palette(highlight); color: palette(highlighted-text); }
QTabBar::tab { border: none; padding: 6px 14px; }
QTabBar::tab:selected { border-bottom: 2px solid palette(highlight); }
QDockWidget::title { padding: 5px 6px; background: palette(window); }
QStatusBar { border: none; }
""",
    "touch": """
* { font-size: 11.5pt; }
QPushButton { border: 1px solid palette(mid); border-radius: 9px; padding: 9px 18px; min-height: 26px; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox { padding: 5px 8px; min-height: 28px; border-radius: 6px; }
QCheckBox::indicator, QRadioButton::indicator { width: 20px; height: 20px; }
QToolBar { spacing: 6px; padding: 4px; }
QToolButton { padding: 6px; border-radius: 6px; }
QMenu::item { padding: 9px 28px; }
QTabBar::tab { padding: 9px 18px; }
QDockWidget::title { padding: 8px 10px; }
QScrollBar:vertical { width: 18px; }
QScrollBar:horizontal { height: 18px; }
""",
}

_SELECTORS = {
    "menubar": ("QMenuBar", "QMenuBar::item"),
    "menu": ("QMenu", "QMenu::item"),
    "toolbar": ("QToolBar", "QToolBar QToolButton"),
    "dock": ("QDockWidget::title", "QDockWidget"),
    "tabs": ("QTabBar::tab", "QTabBar::tab"),
    "statusbar": ("QStatusBar", "QStatusBar QLabel"),
    "tooltip": ("QToolTip", "QToolTip"),
    "button": ("QPushButton", "QPushButton"),
    "stepbar": ("QWidget#stepbar", "QWidget#stepbar QLabel"),
}


def stylesheet(dark: bool, cfg: Config | None = None) -> str:
    """The application style sheet for the interface style and the advanced colours and fonts."""
    cfg = cfg or _cfg
    parts = [_SHAPES.get(cfg.style, "")]
    if cfg.scheme == "contrast":
        parts.append("QPushButton, QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox { border: 2px solid palette(text); }")
    for el, (sel_bg, sel_fg) in _SELECTORS.items():
        o = cfg.colors.get(el) or {}
        fcss = ""
        if el in cfg.fonts:
            fcss = font_css_for(cfg.fonts[el])
        if el == "button":                    # buttons go through the palette (keeps hover and pressed)
            if fcss:
                parts.append(f"QPushButton {{ {fcss} }}")
            continue
        if el == "stepbar":
            if o.get("bg"):
                parts.append(f"QWidget#stepbar {{ background: {o['bg']}; }}")
            if fcss:
                parts.append(f"QWidget#stepbar QLabel, QWidget#stepbar QPushButton {{ {fcss} }}")
            continue
        if o.get("bg"):
            parts.append(f"{sel_bg} {{ background: {o['bg']}; }}")
            if el == "menubar":
                parts.append("QMenuBar::item { background: transparent; }")
                parts.append(f"QMenuBar::item:selected {{ background: {QColor(o['bg']).lighter(125).name()}; }}")
            if el == "menu":
                parts.append("QMenu::item { background: transparent; }")
                parts.append("QMenu::item:selected { background: palette(highlight); color: palette(highlighted-text); }")
            if el == "tabs":
                parts.append(f"QTabBar::tab:selected {{ background: {QColor(o['bg']).lighter(118).name()}; }}")
        if o.get("fg"):
            fg_sel = {"dock": "QDockWidget", "menu": "QMenu::item", "menubar": "QMenuBar::item",
                      "toolbar": "QToolBar QToolButton", "tabs": "QTabBar::tab",
                      "statusbar": "QStatusBar, QStatusBar QLabel", "tooltip": "QToolTip"}[el]
            parts.append(f"{fg_sel} {{ color: {o['fg']}; }}")
            if el == "menu":
                parts.append("QMenu::item:selected { color: palette(highlighted-text); }")
        if fcss:
            sel = {"dock": "QDockWidget", "menu": "QMenu, QMenu::item", "menubar": "QMenuBar, QMenuBar::item",
                   "toolbar": "QToolBar, QToolBar QToolButton", "tabs": "QTabBar::tab",
                   "statusbar": "QStatusBar, QStatusBar QLabel", "tooltip": "QToolTip"}[el]
            parts.append(f"{sel} {{ {fcss} }}")
    return "\n".join(p.strip() for p in parts if p.strip())


def font_css_for(s: str) -> str:
    f = QFont()
    f.fromString(s)
    out = f"font-family: '{f.family()}';"
    if f.pointSizeF() > 0:
        out += f" font-size: {f.pointSizeF():g}pt;"
    if f.bold():
        out += " font-weight: bold;"
    if f.italic():
        out += " font-style: italic;"
    return out


_default_font: QFont | None = None


def apply(app, dark: bool):
    """Put the palette, style sheet, interface font and title bar colours on the application."""
    global _dark, _default_font
    _dark = bool(dark)
    if app is None:
        return
    if _default_font is None:
        _default_font = QFont(app.font())
    app.setPalette(palette(dark))
    if _cfg.font:
        f = QFont(_default_font)
        f.fromString(_cfg.font)
        app.setFont(f)
    else:
        app.setFont(_default_font)
    app.setStyleSheet(stylesheet(dark))
    try:
        for w in app.topLevelWidgets():
            if w.isWindow() and w.isVisible():
                style_titlebar(w)
    except Exception:                       # noqa: BLE001  (cosmetic only)
        pass


# --------------------------------------------------------------------------- title bar (Windows 11)
def style_titlebar(widget):
    """Colour the native title bar on Windows 11 (DWM). Elsewhere this does nothing."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes
        hwnd = wintypes.HWND(int(widget.winId()))
        dwm = ctypes.windll.dwmapi

        def setattr_(attr, value):
            v = ctypes.c_uint(value)
            return dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(v), ctypes.sizeof(v)) == 0

        setattr_(20, 1 if _dark else 0)                 # DWMWA_USE_IMMERSIVE_DARK_MODE

        def colorref(hexcol):
            c = QColor(hexcol)
            return c.red() | (c.green() << 8) | (c.blue() << 16)
        bg = color("titlebar", "bg")
        fg = color("titlebar", "fg")
        setattr_(35, colorref(bg) if bg else 0xFFFFFFFF)    # DWMWA_CAPTION_COLOR (default when unset)
        setattr_(36, colorref(fg) if fg else 0xFFFFFFFF)    # DWMWA_TEXT_COLOR
        return True
    except Exception:                        # noqa: BLE001  (older Windows, no DWM)
        return False


class TitleBarFilter:
    """Colours the title bar of every window when it is first shown (installed on the app)."""

    def __new__(cls, app):
        from PySide6.QtCore import QEvent, QObject

        class _F(QObject):
            def eventFilter(self, obj, ev):
                if ev.type() == QEvent.Show and getattr(obj, "isWindow", None) and obj.isWindow():
                    try:
                        if obj.windowHandle() is not None:
                            style_titlebar(obj)
                    except Exception:            # noqa: BLE001
                        pass
                return False
        f = _F(app)
        app.installEventFilter(f)
        return f


# --------------------------------------------------------------------------- user fonts
def fonts_dir() -> Path:
    from PySide6.QtCore import QStandardPaths
    base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation) or str(Path.home() / ".geolab")
    exe_dir = Path(sys.executable).parent
    if getattr(sys, "frozen", False) and (exe_dir / "portable.txt").exists():
        base = str(exe_dir / "GeoLab data")
    d = Path(base) / "fonts"
    return d


_loaded: dict[str, tuple[int, list[str]]] = {}    # file name -> (font id, families)


def _add_from_file(path) -> int:
    """Load a font from its bytes, so the file is not kept open (it can then be removed on Windows)."""
    from PySide6.QtCore import QByteArray
    try:
        data = Path(path).read_bytes()
    except OSError:
        return -1
    return QFontDatabase.addApplicationFontFromData(QByteArray(data))


def load_user_fonts(folder: Path | None = None) -> dict[str, list[str]]:
    """Load every .ttf / .otf in the GeoLab fonts folder. Returns {file name: [families]}."""
    folder = Path(folder) if folder else fonts_dir()
    if not folder.is_dir():
        return {}
    for f in sorted(folder.iterdir()):
        if f.suffix.lower() in (".ttf", ".otf", ".ttc") and f.name not in _loaded:
            fid = _add_from_file(f)
            _loaded[f.name] = (fid, list(QFontDatabase.applicationFontFamilies(fid)) if fid >= 0 else [])
    return {k: v[1] for k, v in _loaded.items() if (folder / k).exists()}


def add_font(path, folder: Path | None = None) -> list[str]:
    """Copy a font file into the GeoLab fonts folder and load it. Returns its font families."""
    src = Path(path)
    if src.suffix.lower() not in (".ttf", ".otf", ".ttc"):
        raise ValueError("Choose a TrueType (.ttf) or OpenType (.otf) font file.")
    folder = Path(folder) if folder else fonts_dir()
    folder.mkdir(parents=True, exist_ok=True)
    dst = folder / src.name
    if src.resolve() != dst.resolve():
        shutil.copyfile(src, dst)
    fid = _add_from_file(dst)
    if fid < 0:
        dst.unlink(missing_ok=True)
        raise ValueError(f"{src.name} is not a font file Qt can read.")
    fams = list(QFontDatabase.applicationFontFamilies(fid))
    _loaded[dst.name] = (fid, fams)
    return fams


def remove_font(name, folder: Path | None = None):
    folder = Path(folder) if folder else fonts_dir()
    fid, _ = _loaded.pop(name, (-1, []))
    if fid >= 0:
        QFontDatabase.removeApplicationFont(fid)
    try:
        (folder / name).unlink()
    except OSError:
        pass
