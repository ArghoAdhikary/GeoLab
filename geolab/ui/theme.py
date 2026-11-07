"""Day / night appearance: Light, Dark or Auto (follows the operating system).

The theme is applied to the whole application with the Fusion style and a palette, so every
standard widget follows it. Widgets with their own colours (the drawing canvas, the start page,
the chat panel) ask :func:`is_dark` and listen to ``manager().changed``.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPalette

MODES = {"auto": "Auto (follow system)", "light": "Light (day)", "dark": "Dark (night)"}


class ThemeManager(QObject):
    changed = Signal(bool)          # True when the effective theme is dark

    def __init__(self):
        super().__init__()
        self.mode = "auto"
        self.dark = False
        self._hooked = False

    def system_dark(self) -> bool:
        app = QGuiApplication.instance()
        if app is None:
            return False
        try:
            return app.styleHints().colorScheme() == Qt.ColorScheme.Dark
        except AttributeError:      # very old Qt: judge from the default window colour
            return app.palette().color(QPalette.Window).lightness() < 128

    def apply(self, mode: str | None = None):
        app = QGuiApplication.instance()
        if mode is not None:
            self.mode = mode if mode in MODES else "auto"
        dark = self.system_dark() if self.mode == "auto" else self.mode == "dark"
        if app is not None:
            if not self._hooked:
                try:
                    app.styleHints().colorSchemeChanged.connect(self._system_changed)
                except AttributeError:
                    pass
                self._hooked = True
            from . import appearance
            appearance.apply(app, dark)
        changed = dark != self.dark
        self.dark = dark
        if changed or mode is not None:
            self.changed.emit(dark)
        return dark

    def refresh(self):
        """Re-apply the appearance (after the style, colours or fonts change)."""
        return self.apply(self.mode)

    def _system_changed(self, *_):
        if self.mode == "auto":
            self.apply()


def light_palette() -> QPalette:
    p = QPalette()
    c = {
        QPalette.Window: "#f0f0f0", QPalette.WindowText: "#1a1a1a", QPalette.Base: "#ffffff",
        QPalette.AlternateBase: "#f5f5f5", QPalette.ToolTipBase: "#ffffe1", QPalette.ToolTipText: "#1a1a1a",
        QPalette.Text: "#1a1a1a", QPalette.Button: "#f0f0f0", QPalette.ButtonText: "#1a1a1a",
        QPalette.BrightText: "#ff0000", QPalette.Link: "#1d5fbf", QPalette.Highlight: "#3d7fd9",
        QPalette.HighlightedText: "#ffffff", QPalette.PlaceholderText: "#8a8a8a",
        QPalette.Light: "#ffffff", QPalette.Midlight: "#e3e3e3", QPalette.Mid: "#b8b8b8",
        QPalette.Dark: "#a0a0a0", QPalette.Shadow: "#707070",
    }
    for role, col in c.items():
        p.setColor(role, QColor(col))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, role, QColor("#a0a0a0"))
    return p


def dark_palette() -> QPalette:
    p = QPalette()
    c = {
        QPalette.Window: "#2b2d30", QPalette.WindowText: "#e6e6e6", QPalette.Base: "#1e1f22",
        QPalette.AlternateBase: "#26282b", QPalette.ToolTipBase: "#3c3f44", QPalette.ToolTipText: "#e6e6e6",
        QPalette.Text: "#e6e6e6", QPalette.Button: "#35373b", QPalette.ButtonText: "#e6e6e6",
        QPalette.BrightText: "#ff6b6b", QPalette.Link: "#6aa6ff", QPalette.Highlight: "#3d6fb8",
        QPalette.HighlightedText: "#ffffff", QPalette.PlaceholderText: "#8c8f94",
        QPalette.Light: "#4a4d52", QPalette.Midlight: "#3e4146", QPalette.Mid: "#2f3236",
        QPalette.Dark: "#1b1c1f", QPalette.Shadow: "#000000",
    }
    for role, col in c.items():
        p.setColor(role, QColor(col))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, role, QColor("#6f7277"))
    return p


# canvas colours (screen only; printing and PDF stay on white paper)
CANVAS = {
    False: {"background": "#ffffff", "grid": "#c9cfd8", "axis": "#404040", "outline": "#202020",
            "text": "#303030"},
    True: {"background": "#1e1f22", "grid": "#454a52", "axis": "#c4c7cc", "outline": "#d0d3d8",
           "text": "#202020"},
}

_manager: ThemeManager | None = None


def manager() -> ThemeManager:
    global _manager
    if _manager is None:
        _manager = ThemeManager()
    return _manager


def is_dark() -> bool:
    return manager().dark


def apply_theme(mode: str | None = None) -> bool:
    return manager().apply(mode)
