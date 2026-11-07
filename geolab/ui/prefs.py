"""Preferences: appearance (Light / Dark / Auto) and the AI assistant (on/off and which AI to use)."""
from __future__ import annotations

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                               QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QRadioButton,
                               QTabWidget, QVBoxLayout, QWidget)

from ..ai import AIError
from ..assistant import DEFAULT_MODELS, NEEDS_KEY, PROVIDERS, Settings, call_provider, find_cli
from .theme import MODES

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
        self.tabs.addTab(self._appearance(), "Appearance")
        self.tabs.addTab(self._ai(), "AI Assistant")
        self.tabs.setCurrentIndex(1 if tab == "ai" else 0)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
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
