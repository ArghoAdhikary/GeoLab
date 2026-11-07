"""Preferences: appearance (theme, interface style, colour scheme, language), advanced colours and fonts
for every part of the window, files (autosave, cloud drive backup) and the AI assistant."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
                               QFileDialog, QFontComboBox, QFontDialog, QFormLayout, QGridLayout, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget, QMessageBox, QPushButton,
                               QRadioButton, QScrollArea, QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from ..ai import AIError
from ..assistant import DEFAULT_MODELS, NEEDS_KEY, PROVIDERS, Settings, call_provider, find_cli
from . import appearance
from .theme import MODES


def _bool(v, default=True):
    if v is None or v == "":
        return default
    return str(v).lower() in ("true", "1", "yes")


class ColorButton(QPushButton):
    """A colour swatch. Click to choose a colour; right-click to go back to the default."""
    changed = Signal()

    def __init__(self, value=None, placeholder="#808080", title="Colour"):
        super().__init__()
        self.value = value
        self.placeholder = placeholder
        self.title = title
        self.setFixedSize(68, 24)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Click to choose a colour. Right-click to go back to the default.")
        self.clicked.connect(self.choose)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(lambda *_: self.set_value(None))
        self._show()

    def choose(self):
        c = QColorDialog.getColor(QColor(self.value or self.placeholder), self, self.title)
        if c.isValid():
            self.set_value(c.name())

    def set_value(self, v):
        self.value = v
        self._show()
        self.changed.emit()

    def _show(self):
        if self.value:
            fg = "#000" if QColor(self.value).lightness() > 140 else "#fff"
            self.setText(self.value)
            self.setStyleSheet(f"QPushButton {{ background: {self.value}; color: {fg}; border: 1px solid #888;"
                               " border-radius: 4px; font-size: 8pt; }")
        else:
            self.setText("default")
            self.setStyleSheet("QPushButton { border: 1px dashed #888; border-radius: 4px; font-size: 8pt; }")


class FontButton(QPushButton):
    """Shows a font; click to choose one, right-click to go back to the default."""
    changed = Signal()

    def __init__(self, value=""):
        super().__init__()
        self.value = value or ""
        self.setMinimumWidth(150)
        self.setToolTip("Click to choose a font. Right-click to go back to the default.")
        self.clicked.connect(self.choose)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(lambda *_: self.set_value(""))
        self._show()

    def choose(self):
        f = QFont()
        if self.value:
            f.fromString(self.value)
        ok, f2 = QFontDialog.getFont(f, self, "Font")
        if isinstance(ok, QFont):              # PySide returns (ok, font) or (font, ok) by version
            ok, f2 = f2, ok
        if ok:
            self.set_value(f2.toString())

    def set_value(self, v):
        self.value = v or ""
        self._show()
        self.changed.emit()

    def _show(self):
        if self.value:
            f = QFont()
            f.fromString(self.value)
            self.setText(f"{f.family()} {f.pointSizeF():g}")
        else:
            self.setText("default font")

PRESETS = {
    "Google Gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    "OpenRouter (many models)": "https://openrouter.ai/api/v1",
    "DeepSeek": "https://api.deepseek.com/v1",
    "Groq": "https://api.groq.com/openai/v1",
    "Mistral": "https://api.mistral.ai/v1",
    "Ollama (on this computer)": "http://localhost:11434/v1",
    "LM Studio (on this computer)": "http://localhost:1234/v1",
}

HELP = {
    "claude": "Uses Claude through the Anthropic API. Get a key at console.anthropic.com (billed per use).",
    "openai": "Uses ChatGPT models through the OpenAI API. Get a key at platform.openai.com (billed per use).",
    "compatible": "Any service that speaks the OpenAI chat format: Google Gemini, OpenRouter, DeepSeek, "
                  "Groq, Mistral, or a model running on this computer with Ollama or LM Studio. "
                  "Pick a preset or type the server address, then the model name.",
    "claude_cli": "Uses your Claude account (Pro / Max) with no API key: install Claude Code, run "
                  "'claude' once in a terminal and sign in. GeoLab then talks to it directly.",
    "codex_cli": "Uses your ChatGPT account (Plus / Pro) with no API key: install Codex "
                 "(npm install -g @openai/codex), run 'codex' once in a terminal and sign in.",
}


class _TestWorker(QThread):
    done = Signal(str, bool)

    def __init__(self, settings):
        super().__init__()
        self.s = settings

    def run(self):
        try:
            text = call_provider(self.s, "Reply with a JSON object {\"reply\": \"...\", \"actions\": []}.",
                                 [{"role": "user", "content": "Say hello in five words."}])
            self.done.emit(text.strip()[:200] or "(empty answer)", True)
        except AIError as e:
            self.done.emit(str(e), False)
        except Exception as e:
            self.done.emit(f"{type(e).__name__}: {e}", False)


class PreferencesDialog(QDialog):
    def __init__(self, settings, parent=None, tab="appearance"):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.resize(560, 480)
        self.qs = settings
        self.keys = {p: settings.value(f"ai/key/{p}", "") or "" for p in PROVIDERS}
        if not self.keys["claude"]:
            self.keys["claude"] = settings.value("ai/api_key", "") or ""
        self.models = {p: settings.value(f"ai/model/{p}", "") or "" for p in PROVIDERS}
        self.commands = {p: settings.value(f"ai/command/{p}", "") or "" for p in PROVIDERS}
        self.worker = None
        v = QVBoxLayout(self)
        self.tabs = QTabWidget()
        v.addWidget(self.tabs)
        self.cfg = appearance.Config.from_dict(appearance.config().to_dict())
        self.on_apply = None             # set by the main window: shows the changes without closing
        self.on_backup_now = None
        self.tabs.addTab(self._appearance(), "Appearance")
        self.tabs.addTab(self._advanced(), "Advanced Colours && Fonts")
        self.tabs.addTab(self._files(), "Files && Backup")
        self.tabs.addTab(self._ai(), "AI Assistant")
        self.tabs.setCurrentIndex({"appearance": 0, "advanced": 1, "files": 2, "ai": 3}.get(tab, 0))
        self.resize(740, 640)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        bb.button(QDialogButtonBox.Apply).clicked.connect(self.apply_now)
        v.addWidget(bb)

    # -- tabs ----------------------------------------------------------------
    def _appearance(self):
        w = QWidget()
        v = QVBoxLayout(w)
        g = QGroupBox("Theme")
        gl = QVBoxLayout(g)
        self.theme_group = QButtonGroup(self)
        cur = self.qs.value("ui/theme", "auto") or "auto"
        self.theme_buttons = {}
        for key, label in MODES.items():
            b = QRadioButton(label)
            b.setChecked(key == cur)
            self.theme_group.addButton(b)
            self.theme_buttons[key] = b
            gl.addWidget(b)
        note = QLabel("Auto switches between day and night with your operating system. Printing and "
                      "PDF reports always use white paper.")
        note.setWordWrap(True)
        note.setEnabled(False)
        gl.addWidget(note)
        v.addWidget(g)
        sg = QGroupBox("Interface style and colours")
        sf = QFormLayout(sg)
        self.style_box = QComboBox()
        for k, label in appearance.STYLES.items():
            self.style_box.addItem(label, k)
        self.style_box.setCurrentIndex(max(0, self.style_box.findData(self.cfg.style)))
        sf.addRow("Interface style", self.style_box)
        self.scheme_box = QComboBox()
        for k, d in appearance.SCHEMES.items():
            self.scheme_box.addItem(d["label"], k)
        self.scheme_box.setCurrentIndex(max(0, self.scheme_box.findData(self.cfg.scheme)))
        sf.addRow("Colour scheme", self.scheme_box)
        self.accent_btn = ColorButton(self.cfg.accent or None, appearance.scheme_colors(cfg=self.cfg)["accent"],
                                      "Accent colour")
        sf.addRow("Accent colour", self.accent_btn)
        fr = QHBoxLayout()
        self.ui_font = QFontComboBox()
        self.ui_font_size = QSpinBox()
        self.ui_font_size.setRange(0, 24)
        self.ui_font_size.setSpecialValueText("auto")
        self.ui_font_size.setSuffix(" pt")
        self.ui_font_on = QCheckBox("Use")
        if self.cfg.font:
            f = QFont()
            f.fromString(self.cfg.font)
            self.ui_font.setCurrentFont(f)
            self.ui_font_size.setValue(int(round(f.pointSizeF())) if f.pointSizeF() > 0 else 0)
            self.ui_font_on.setChecked(True)
        fr.addWidget(self.ui_font_on)
        fr.addWidget(self.ui_font, 1)
        fr.addWidget(self.ui_font_size)
        sf.addRow("Interface font", fr)
        self.preview = QLabel()
        self.preview.setMinimumHeight(46)
        sf.addRow("Preview", self.preview)
        for wdg in (self.style_box, self.scheme_box):
            wdg.currentIndexChanged.connect(self._preview)
        self.accent_btn.changed.connect(self._preview)
        self.theme_group.buttonClicked.connect(self._preview)
        sn = QLabel("Press Apply to see a change straight away. The Advanced Colours & Fonts tab changes any "
                    "single part of the window.")
        sn.setWordWrap(True)
        sn.setEnabled(False)
        sf.addRow(sn)
        v.addWidget(sg)
        self._preview()
        from ..i18n import LANGUAGES
        lg = QGroupBox("Language")
        ll = QVBoxLayout(lg)
        self.lang_group = QButtonGroup(self)
        cur_lang = self.qs.value("ui/language", "en") or "en"
        self.lang_buttons = {}
        for key, label in LANGUAGES.items():
            b = QRadioButton(label)
            b.setChecked(key == cur_lang)
            self.lang_group.addButton(b)
            self.lang_buttons[key] = b
            ll.addWidget(b)
        ln = QLabel("Restart GeoLab to change the language of the menus and windows. "
                    "বাংলা: মেনু ও উইন্ডো বাংলায় দেখাতে GeoLab আবার চালু করুন।")
        ln.setWordWrap(True)
        ln.setEnabled(False)
        ll.addWidget(ln)
        v.addWidget(lg)
        v.addStretch(1)
        return w

    def _preview(self, *_):
        from .theme import manager
        mode = self.theme()
        dark = manager().system_dark() if mode == "auto" else mode == "dark"
        cfg = appearance.Config(scheme=self.scheme_box.currentData(), accent=self.accent_btn.value or "")
        c = appearance.scheme_colors(dark, cfg)
        self.accent_btn.placeholder = appearance.scheme_colors(dark, appearance.Config(scheme=cfg.scheme))["accent"]
        sw = "".join(f"<td style='background:{c[k]}; padding:10px 16px'>&nbsp;</td>"
                     for k in ("window", "base", "button", "highlight", "accent"))
        self.preview.setText(f"<table cellspacing='2'><tr>{sw}</tr></table>"
                             f"<span style='color:gray'>window, text box, button, selection, accent</span>")

    # -- advanced colours and fonts -------------------------------------------
    def _advanced(self):
        w = QWidget()
        v = QVBoxLayout(w)
        intro = QLabel('Choose a colour and a font for any part of the window. Leave "default" to follow the '
                       "theme and colour scheme. Right-click a button to clear it.")
        intro.setWordWrap(True)
        v.addWidget(intro)
        area = QScrollArea()
        area.setWidgetResizable(True)
        inner = QWidget()
        grid = QGridLayout(inner)
        grid.setColumnStretch(0, 1)
        for col, head in enumerate(("Part of the window", "Background", "Text", "Font", "")):
            grid.addWidget(QLabel(f"<b>{head}</b>"), 0, col)
        self.color_btns, self.font_btns = {}, {}
        for row, (key, (label, slots, has_font)) in enumerate(appearance.ELEMENTS.items(), start=1):
            grid.addWidget(QLabel(label), row, 0)
            cur = self.cfg.colors.get(key, {})
            for col, slot in ((1, "bg"), (2, "fg")):
                if slot in slots:
                    b = ColorButton(cur.get(slot), "#808080", f"{label}: {slots[slot]}")
                    b.setToolTip(f"{slots[slot]}. Right-click to go back to the default.")
                    self.color_btns[(key, slot)] = b
                    grid.addWidget(b, row, col)
            if has_font:
                fb = FontButton(self.cfg.fonts.get(key, ""))
                self.font_btns[key] = fb
                grid.addWidget(fb, row, 3)
            rb = QPushButton("Reset")
            rb.setFixedWidth(56)
            rb.clicked.connect(lambda _=False, k=key: self._reset_element(k))
            grid.addWidget(rb, row, 4)
        area.setWidget(inner)
        v.addWidget(area, 1)
        row = QHBoxLayout()
        for text, slot in (("Save Theme...", self._save_theme), ("Load Theme...", self._load_theme),
                           ("Reset All", self._reset_all)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addStretch(1)
        v.addLayout(row)
        fg = QGroupBox("Your fonts")
        fl = QHBoxLayout(fg)
        self.font_list = QListWidget()
        self.font_list.setMaximumHeight(80)
        self._fill_fonts()
        fl.addWidget(self.font_list, 1)
        col = QVBoxLayout()
        add = QPushButton("Add Font...")
        add.setToolTip("Add a .ttf or .otf font file (for example a Bangla font). It can then be chosen "
                       "for any part of the window.")
        add.clicked.connect(self._add_font)
        rem = QPushButton("Remove")
        rem.clicked.connect(self._remove_font)
        col.addWidget(add)
        col.addWidget(rem)
        col.addStretch(1)
        fl.addLayout(col)
        v.addWidget(fg)
        return w

    def _fill_fonts(self):
        self.font_list.clear()
        for name, fams in appearance.load_user_fonts().items():
            self.font_list.addItem(f"{name}  ({', '.join(fams) or 'not readable'})")
            self.font_list.item(self.font_list.count() - 1).setData(Qt.UserRole, name)

    def _add_font(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Add Font", str(Path.home()),
                                                "Fonts (*.ttf *.otf *.ttc)")
        added = []
        for p in paths:
            try:
                added += appearance.add_font(p)
            except (OSError, ValueError) as e:
                QMessageBox.warning(self, "Add font", str(e))
        self._fill_fonts()
        if added:
            QMessageBox.information(self, "Add font", "Added: " + ", ".join(added) +
                                    "\n\nChoose it with any Font button or as the interface font.")

    def _remove_font(self):
        it = self.font_list.currentItem()
        if it is not None:
            appearance.remove_font(it.data(Qt.UserRole))
            self._fill_fonts()

    def _reset_element(self, key):
        for slot in ("bg", "fg"):
            b = self.color_btns.get((key, slot))
            if b:
                b.set_value(None)
        if key in self.font_btns:
            self.font_btns[key].set_value("")

    def _reset_all(self):
        for k in appearance.ELEMENTS:
            self._reset_element(k)

    def appearance_config(self) -> appearance.Config:
        cfg = appearance.Config(style=self.style_box.currentData(), scheme=self.scheme_box.currentData(),
                                accent=self.accent_btn.value or "")
        if self.ui_font_on.isChecked():
            f = QFont(self.ui_font.currentFont())
            if self.ui_font_size.value() > 0:
                f.setPointSize(self.ui_font_size.value())
            cfg.font = f.toString()
        for (key, slot), b in self.color_btns.items():
            if b.value:
                cfg.colors.setdefault(key, {})[slot] = b.value
        for key, b in self.font_btns.items():
            if b.value:
                cfg.fonts[key] = b.value
        return cfg

    def _save_theme(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save Theme", str(Path.home() / "My theme.geolab-theme"),
                                              "GeoLab theme (*.geolab-theme)")
        if path:
            appearance.export_theme(self.appearance_config(), path)

    def _load_theme(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load Theme", str(Path.home()),
                                              "GeoLab theme (*.geolab-theme *.json)")
        if not path:
            return
        try:
            cfg = appearance.import_theme(path)
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "Load theme", f"Could not read the theme: {e}")
            return
        self.set_appearance(cfg)

    def set_appearance(self, cfg):
        self.style_box.setCurrentIndex(max(0, self.style_box.findData(cfg.style)))
        self.scheme_box.setCurrentIndex(max(0, self.scheme_box.findData(cfg.scheme)))
        self.accent_btn.set_value(cfg.accent or None)
        self.ui_font_on.setChecked(bool(cfg.font))
        if cfg.font:
            f = QFont()
            f.fromString(cfg.font)
            self.ui_font.setCurrentFont(f)
            self.ui_font_size.setValue(int(round(f.pointSizeF())) if f.pointSizeF() > 0 else 0)
        for (key, slot), b in self.color_btns.items():
            b.set_value((cfg.colors.get(key) or {}).get(slot))
        for key, b in self.font_btns.items():
            b.set_value(cfg.fonts.get(key, ""))

    # -- files: autosave and cloud backup -------------------------------------
    def _files(self):
        from .. import backup
        w = QWidget()
        v = QVBoxLayout(w)
        ag = QGroupBox("Autosave")
        af = QFormLayout(ag)
        self.autosave = QCheckBox("Save my work automatically (on by default)")
        self.autosave.setChecked(_bool(self.qs.value("files/autosave"), True))
        af.addRow(self.autosave)
        self.autosave_min = QSpinBox()
        self.autosave_min.setRange(1, 60)
        self.autosave_min.setSuffix(" min")
        self.autosave_min.setValue(int(self.qs.value("files/autosave_min", 2) or 2))
        af.addRow("Every", self.autosave_min)
        self.autosave_file = QCheckBox("Save into the project file itself (otherwise only a recovery copy)")
        self.autosave_file.setChecked(_bool(self.qs.value("files/autosave_into_file"), True))
        af.addRow(self.autosave_file)
        self.keep_bak = QCheckBox("Keep the previous version as a .bak file")
        self.keep_bak.setChecked(_bool(self.qs.value("files/keep_bak"), True))
        af.addRow(self.keep_bak)
        an = QLabel(f"Projects that have no file yet are autosaved to {backup.autosave_dir()}. "
                    "File > Recover Autosaved Project opens them.")
        an.setWordWrap(True)
        an.setEnabled(False)
        af.addRow(an)
        v.addWidget(ag)
        bg = QGroupBox("Backup to Google Drive / OneDrive / Dropbox / iCloud")
        bf = QFormLayout(bg)
        self.backup_on = QCheckBox("Back up a dated copy of the project to a cloud drive")
        self.backup_on.setChecked(_bool(self.qs.value("backup/enabled"), False))
        bf.addRow(self.backup_on)
        self.drive_box = QComboBox()
        self.drives = backup.detect_drives()
        for label, path in self.drives.items():
            self.drive_box.addItem(f"{label}: {path}", path)
        self.drive_box.addItem("Another folder...", "")
        self.backup_dir = QLineEdit(self.qs.value("backup/folder", "") or "")
        if not self.backup_dir.text() and self.drives:
            self.backup_dir.setText(next(iter(self.drives.values())))
        self.backup_dir.setPlaceholderText("for example G:\\My Drive")
        self.drive_box.activated.connect(self._drive_chosen)
        bf.addRow("Drive", self.drive_box)
        br = QHBoxLayout()
        br.addWidget(self.backup_dir, 1)
        browse = QPushButton("Browse...")
        browse.clicked.connect(self._browse_backup)
        br.addWidget(browse)
        bf.addRow("Folder", br)
        self.backup_keep = QSpinBox()
        self.backup_keep.setRange(0, 500)
        self.backup_keep.setSpecialValueText("all")
        self.backup_keep.setValue(int(self.qs.value("backup/keep", 20) or 0))
        bf.addRow("Versions to keep per project", self.backup_keep)
        self.backup_every = QSpinBox()
        self.backup_every.setRange(0, 240)
        self.backup_every.setSuffix(" min")
        self.backup_every.setSpecialValueText("every save")
        self.backup_every.setValue(int(self.qs.value("backup/every_min", 10) or 0))
        bf.addRow("At most one copy every", self.backup_every)
        row = QHBoxLayout()
        now = QPushButton("Back Up Now")
        now.clicked.connect(self._backup_now)
        opn = QPushButton("Open Backup Folder")
        opn.clicked.connect(self._open_backup)
        row.addWidget(now)
        row.addWidget(opn)
        row.addStretch(1)
        bf.addRow(row)
        self.backup_status = QLabel("")
        self.backup_status.setWordWrap(True)
        bf.addRow(self.backup_status)
        found = ", ".join(self.drives) if self.drives else "none found"
        bn = QLabel("GeoLab copies the project into the folder that Google Drive for desktop (or OneDrive, "
                    'Dropbox, iCloud) keeps in sync, under "GeoLab Backups". That app uploads it, so no '
                    f"sign-in is needed here. Synced drives on this computer: {found}.")
        bn.setWordWrap(True)
        bn.setEnabled(False)
        bf.addRow(bn)
        v.addWidget(bg)
        v.addStretch(1)
        return w

    def _drive_chosen(self, i):
        path = self.drive_box.itemData(i)
        if path:
            self.backup_dir.setText(path)
        else:
            self._browse_backup()

    def _browse_backup(self):
        d = QFileDialog.getExistingDirectory(self, "Backup Folder", self.backup_dir.text() or str(Path.home()))
        if d:
            self.backup_dir.setText(d)

    def _backup_now(self):
        if self.on_backup_now is None:
            return
        self.backup_status.setText(self.on_backup_now(self.backup_dir.text().strip(), self.backup_keep.value()))

    def _open_backup(self):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        from ..backup import BACKUP_FOLDER
        folder = self.backup_dir.text().strip()
        if not folder:
            return
        p = Path(folder) / BACKUP_FOLDER
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(p if p.is_dir() else Path(folder))))

    def apply_now(self):
        if self.on_apply is not None:
            self.on_apply(self)

    def language(self) -> str:
        return next((k for k, b in self.lang_buttons.items() if b.isChecked()), "en")

    def _ai(self):
        w = QWidget()
        v = QVBoxLayout(w)
        self.enabled = QCheckBox("Show the AI assistant chat head (round button, bottom-right corner)")
        self.enabled.setChecked(str(self.qs.value("ai/chat_enabled", "true")).lower() in ("true", "1"))
        v.addWidget(self.enabled)
        f = QFormLayout()
        self.provider = QComboBox()
        for k, label in PROVIDERS.items():
            self.provider.addItem(label, k)
        cur = self.qs.value("ai/provider", "claude") or "claude"
        self.provider.setCurrentIndex(max(0, self.provider.findData(cur)))
        self._prov = self.provider.currentData()
        self.provider.currentIndexChanged.connect(self._provider_changed)
        f.addRow("AI service", self.provider)
        self.help = QLabel()
        self.help.setWordWrap(True)
        f.addRow("", self.help)
        self.preset = QComboBox()
        self.preset.addItem("Choose a preset...", "")
        for name, url in PRESETS.items():
            self.preset.addItem(name, url)
        self.preset.activated.connect(lambda i: self.preset.itemData(i) and self.base.setText(self.preset.itemData(i)))
        self.base = QLineEdit(self.qs.value("ai/base_url", "") or "")
        self.base.setPlaceholderText("https://.../v1")
        f.addRow("Preset", self.preset)
        f.addRow("Server address", self.base)
        self.model = QLineEdit()
        f.addRow("Model", self.model)
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.Password)
        f.addRow("API key", self.key)
        self.command = QLineEdit()
        f.addRow("Program", self.command)
        self.cli_status = QLabel()
        f.addRow("", self.cli_status)
        self.form = f
        v.addLayout(f)
        row = QHBoxLayout()
        self.test = QPushButton("Test connection")
        self.test.clicked.connect(self._test)
        row.addWidget(self.test)
        row.addStretch(1)
        v.addLayout(row)
        self.test_result = QLabel("")
        self.test_result.setWordWrap(True)
        self.test_result.setTextInteractionFlags(Qt.TextSelectableByMouse)
        v.addWidget(self.test_result)
        privacy = QLabel("The assistant sends your message and a summary of the open model (materials, "
                         "coordinates, water table, results) to the AI service you choose. Keys are kept "
                         "in this computer's GeoLab settings.")
        privacy.setWordWrap(True)
        privacy.setEnabled(False)
        v.addWidget(privacy)
        v.addStretch(1)
        self._load_fields(self._prov)
        return w

    def _set_row_visible(self, field, visible):
        self.form.setRowVisible(field, visible)

    def _load_fields(self, prov):
        self.help.setText(HELP.get(prov, ""))
        self.model.setText(self.models.get(prov, ""))
        default = DEFAULT_MODELS.get(prov, "")
        self.model.setPlaceholderText(default or ("the CLI's default model" if prov.endswith("_cli")
                                                  else "for example gemini-2.5-flash, llama3.1"))
        self.key.setText(self.keys.get(prov, ""))
        self.key.setPlaceholderText({"claude": "uses ANTHROPIC_API_KEY if empty",
                                     "openai": "uses OPENAI_API_KEY if empty"}.get(prov, "leave empty if not needed"))
        self.command.setText(self.commands.get(prov, ""))
        self.command.setPlaceholderText("claude" if prov == "claude_cli" else "codex")
        cli = prov.endswith("_cli")
        self._set_row_visible(self.preset, prov == "compatible")
        self._set_row_visible(self.base, prov == "compatible")
        self._set_row_visible(self.key, not cli)
        self._set_row_visible(self.command, cli)
        self._set_row_visible(self.cli_status, cli)
        if cli:
            exe = find_cli(Settings(provider=prov, command=self.command.text()))
            self.cli_status.setText(f"Found: {exe}" if exe else "Not found on this computer yet.")

    def _store_fields(self, prov):
        self.models[prov] = self.model.text().strip()
        self.keys[prov] = self.key.text().strip()
        self.commands[prov] = self.command.text().strip()

    def _provider_changed(self, *_):
        self._store_fields(self._prov)
        self._prov = self.provider.currentData()
        self._load_fields(self._prov)
        self.test_result.setText("")

    def current_settings(self) -> Settings:
        prov = self.provider.currentData()
        return Settings(provider=prov, model=self.model.text().strip(), api_key=self.key.text().strip(),
                        base_url=self.base.text().strip(), command=self.command.text().strip(), timeout=90)

    def _test(self):
        if self.worker is not None:
            return
        self.test.setEnabled(False)
        self.test_result.setText("Testing...")
        self.worker = _TestWorker(self.current_settings())
        self.worker.done.connect(self._tested)
        self.worker.start()

    def _tested(self, text, ok):
        self.worker.wait()
        self.worker = None
        self.test.setEnabled(True)
        col = "#2e8b57" if ok else "#c0392b"
        self.test_result.setText(f"<span style='color:{col}'><b>{'Connected' if ok else 'Failed'}:</b></span> "
                                 + text.replace("<", "&lt;"))

    # -- saving --------------------------------------------------------------
    def theme(self) -> str:
        return next((k for k, b in self.theme_buttons.items() if b.isChecked()), "auto")

    def save(self):
        self._store_fields(self.provider.currentData())
        qs = self.qs
        qs.setValue("ui/theme", self.theme())
        qs.setValue("ui/language", self.language())
        appearance.save(qs, self.appearance_config())
        qs.setValue("files/autosave", "true" if self.autosave.isChecked() else "false")
        qs.setValue("files/autosave_min", self.autosave_min.value())
        qs.setValue("files/autosave_into_file", "true" if self.autosave_file.isChecked() else "false")
        qs.setValue("files/keep_bak", "true" if self.keep_bak.isChecked() else "false")
        qs.setValue("backup/enabled", "true" if self.backup_on.isChecked() else "false")
        qs.setValue("backup/folder", self.backup_dir.text().strip())
        qs.setValue("backup/keep", self.backup_keep.value())
        qs.setValue("backup/every_min", self.backup_every.value())
        qs.setValue("ai/chat_enabled", "true" if self.enabled.isChecked() else "false")
        qs.setValue("ai/provider", self.provider.currentData())
        qs.setValue("ai/base_url", self.base.text().strip())
        for p in PROVIDERS:
            for kind, store in (("model", self.models), ("command", self.commands)):
                if store.get(p):
                    qs.setValue(f"ai/{kind}/{p}", store[p])
                else:
                    qs.remove(f"ai/{kind}/{p}")
            if p in NEEDS_KEY or p == "compatible":
                if self.keys.get(p):
                    qs.setValue(f"ai/key/{p}", self.keys[p])
                else:
                    qs.remove(f"ai/key/{p}")
        if self.keys.get("claude"):
            qs.setValue("ai/api_key", self.keys["claude"])   # shared with the AI Slope Builder

    def done(self, r):
        if self.worker is not None:
            self.worker.wait(100)
        super().done(r)
