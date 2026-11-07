"""AI assistant chat: reply parsing, model edits, every AI service (faked, offline) and the chat window."""
import json
import os
import stat
import sys
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from geolab import assistant as A
from geolab.ai import AIError
from geolab.model import new_project

from test_ai import GOOD


def reply(text="ok", actions=()):
    return json.dumps({"reply": text, "actions": [{"type": t, "params": json.dumps(p)} for t, p in actions]})


def slope_project():
    p, _ = A.project_from_ai(GOOD)
    return p


# ---------------------------------------------------------------------------
# parsing and edits
# ---------------------------------------------------------------------------
def test_parse_reply_handles_fences_strings_and_plain_text():
    r = A.parse_reply("Sure!\n```json\n" + reply("Done", [("set_method", {"method": "bishop"})]) + "\n```")
    assert r.text == "Done" and r.actions == [{"type": "set_method", "params": {"method": "bishop"}}]
    r = A.parse_reply(json.dumps({"reply": "x", "actions": [{"type": "solve", "params": {}},
                                                            {"type": "format_disk", "params": "{}"},
                                                            {"type": "set_title", "params": "not json"}]}))
    assert [a["type"] for a in r.actions] == ["solve", "set_title"] and r.actions[1]["params"] == {}
    r = A.parse_reply("I could not do that, sorry.")
    assert r.text.startswith("I could not") and r.actions == []


def test_edits_change_the_model_and_reject_bad_values():
    p = slope_project()
    a = p.analyses[0]
    A.apply_edit(p, {"type": "set_material", "params": {"name": "clay", "cohesion": 15, "phi": 28}})
    clay = next(m for m in p.materials if m.name == "Clay")
    assert (clay.cohesion, clay.phi) == (15, 28)
    y0 = [y for _, y in p.piezometric_line]
    A.apply_edit(p, {"type": "move_water_table", "params": {"dy": 1}})
    assert [y for _, y in p.piezometric_line] == [y + 1 for y in y0]
    A.apply_edit(p, {"type": "remove_water_table", "params": {}})
    assert p.piezometric_line == [] and a.pwp == "none"
    A.apply_edit(p, {"type": "set_water_table", "params": {"points": [[80, 14], [0, 5]]}})
    assert p.piezometric_line == [[0, 5], [80, 14]] and a.pwp == "piezometric"
    A.apply_edit(p, {"type": "set_method", "params": {"method": "spencer"}})
    A.apply_edit(p, {"type": "set_seismic", "params": {"kh": 0.1}})
    A.apply_edit(p, {"type": "add_surcharge", "params": {"x1": 70, "x2": 60, "q": 5}})
    assert a.method == "spencer" and a.kh == 0.1 and (p.surcharges[-1].x1, p.surcharges[-1].x2) == (60, 70)
    for bad in ({"type": "set_material", "params": {"name": "rock"}},
                {"type": "set_material", "params": {"name": "Clay", "phi": 95}},
                {"type": "set_method", "params": {"method": "magic"}},
                {"type": "set_water_table", "params": {"points": [[0, 1]]}},
                {"type": "add_surcharge", "params": {"x1": 1, "x2": 1, "q": 3}}):
        with pytest.raises(AIError):
            A.apply_edit(p, bad)


def test_build_action_validates_spec():
    p, notes = A.build_from({"type": "build_model", "params": {"spec": GOOD}})
    assert len(p.regions) == 2 and notes
    with pytest.raises(AIError):
        A.build_from({"type": "build_model", "params": {}})
    with pytest.raises(AIError):
        A.build_from({"type": "build_model", "params": {"spec": {"units": "metric", "materials": []}}})


def test_assistant_sends_model_context_and_keeps_history():
    seen = []

    def transport(settings, system, messages):
        seen.append((system, messages))
        return reply("Water raised", [("move_water_table", {"dy": 1})])
    bot = A.Assistant(A.Settings(provider="claude"))
    p = slope_project()
    r = bot.ask("raise the water 1 m", p, transport=transport)
    assert r.actions[0]["type"] == "move_water_table"
    system, msgs = seen[0]
    assert "build_model" in system and '"materials"' in system           # model schema included
    ctx = json.loads(msgs[-1]["content"].split("\n\nUser:")[0].removeprefix("Current model: "))
    assert [m["name"] for m in ctx["materials"]] == ["Clay", "Sand"] and ctx["analysis"]["method"]
    bot.ask("thanks", p, transport=transport)
    assert [m["role"] for m in seen[1][1]] == ["user", "assistant", "user"]
    assert seen[1][1][0]["content"] == "raise the water 1 m"
    bot.clear()
    assert bot.history == []


# ---------------------------------------------------------------------------
# the AI services (no network)
# ---------------------------------------------------------------------------
def test_claude_service_uses_structured_output(monkeypatch):
    import anthropic
    calls = []

    class Fake:
        def __init__(self, **kw):
            calls.append(("init", kw))
            self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

        def create(self, **kw):
            calls.append(("create", kw))
            return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=reply("hi"))])
    monkeypatch.setattr(anthropic, "Anthropic", Fake)
    text = A.call_provider(A.Settings(provider="claude", api_key="k"), "sys", [{"role": "user", "content": "x"}])
    kw = calls[1][1]
    assert A.parse_reply(text).text == "hi"
    assert kw["model"] == "claude-opus-5-5" and kw["system"] == "sys"
    assert kw["output_config"]["format"]["schema"] == A.REPLY_SCHEMA
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(AIError, match="API key"):
        A.call_provider(A.Settings(provider="claude"), "s", [])


def test_openai_and_compatible_services(monkeypatch):
    posts = []

    def fake_post(url, body, key, timeout):
        posts.append((url, body, key))
        if "response_format" in body and "localhost" in url:
            raise AIError("The AI service returned an error (400).")
        return {"choices": [{"message": {"content": reply("hello")}}]}
    monkeypatch.setattr(A, "_post_json", fake_post)
    t = A.call_provider(A.Settings(provider="openai", api_key="sk"), "sys", [{"role": "user", "content": "hi"}])
    url, body, key = posts[0]
    assert url == "https://api.openai.com/v1/chat/completions" and key == "sk" and body["model"] == "gpt-5"
    assert body["messages"][0] == {"role": "system", "content": "sys"} and A.parse_reply(t).text == "hello"
    s = A.Settings(provider="compatible", base_url="http://localhost:11434/v1/", model="llama3.1")
    A.call_provider(s, "sys", [])
    assert posts[-1][0] == "http://localhost:11434/v1/chat/completions" and "response_format" not in posts[-1][1]
    with pytest.raises(AIError, match="server address"):
        A.call_provider(A.Settings(provider="compatible", model="m"), "s", [])
    with pytest.raises(AIError, match="model name"):
        A.call_provider(A.Settings(provider="compatible", base_url="http://x/v1"), "s", [])


def _fake_cli(tmp_path, name):
    """A stand-in for the claude / codex programs: answers with JSON (codex writes it to a file)."""
    script = tmp_path / f"{name}.py"
    script.write_text(
        "import sys, json\n"
        "prompt = sys.stdin.read()\n"
        "ans = json.dumps({'reply': 'cli ok %d' % len(prompt), 'actions': [{'type': 'solve', 'params': '{}'}]})\n"
        "args = sys.argv[1:]\n"
        "if '--output-last-message' in args:\n"
        "    open(args[args.index('--output-last-message') + 1], 'w').write(ans)\n"
        "    print('progress noise')\n"
        "else:\n"
        "    print(ans)\n")
    if sys.platform.startswith("win"):
        exe = tmp_path / f"{name}.bat"
        exe.write_text(f'@"{sys.executable}" "{script}" %*\n')
    else:
        exe = tmp_path / name
        exe.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n')
        exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    return str(exe)


@pytest.mark.parametrize("provider", ["claude_cli", "codex_cli"])
def test_account_services_through_cli(tmp_path, provider):
    exe = _fake_cli(tmp_path, provider)
    s = A.Settings(provider=provider, command=exe, timeout=60)
    r = A.parse_reply(A.call_provider(s, "SYSTEM TEXT", [{"role": "user", "content": "hello"}]))
    assert r.text.startswith("cli ok") and r.actions == [{"type": "solve", "params": {}}]
    with pytest.raises(AIError, match="not found"):
        A.call_provider(A.Settings(provider=provider, command=str(tmp_path / "missing")), "s", [])


# ---------------------------------------------------------------------------
# chat window, theme and preferences
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(app, tmp_path, monkeypatch):
    from PySide6.QtCore import QSettings
    from geolab.ui import main_window
    ini = str(tmp_path / "settings.ini")
    monkeypatch.setattr(main_window, "QSettings", lambda *a, **k: QSettings(ini, QSettings.IniFormat))
    w = main_window.MainWindow()
    w.resize(1200, 800)
    w.show()
    app.processEvents()
    yield w
    for extra in list(main_window._EXTRA_WINDOWS):
        extra.dirty = False
        extra.close()
    w.dirty = False
    w.close()
    from geolab.ui.theme import apply_theme
    apply_theme("light")


def test_chat_head_popup_and_side_panel(win, app):
    c = win.chat
    assert c.enabled and c.head.isVisible() and not c.popup.isVisible()
    head = c.head.geometry()
    area = win.centralWidget().geometry()
    assert head.right() <= area.right() and area.bottom() - head.bottom() < 40     # bottom-right corner
    c.head.clicked.emit()
    assert c.mode == "popup" and c.popup.isVisible() and c.popup.geometry().bottom() < c.head.geometry().top()
    c.panel.want_mode.emit("side")
    app.processEvents()
    assert c.mode == "side" and c.dock.isVisible() and c.dock.widget() is c.panel and not c.head.isVisible()
    c.panel.want_mode.emit("popup")
    assert c.popup.isVisible() and c.panel.parent() is c.popup and not c.dock.isVisible()
    c.panel.want_mode.emit("head")
    assert not c.popup.isVisible() and c.head.isVisible()
    assert win.settings.value("ai/chat_mode") == "head"
    c.set_enabled(False)
    assert not c.head.isVisible() and not c.popup.isVisible() and not c.dock.isVisible()


def test_chat_actions_edit_build_and_open_windows(win, app, monkeypatch):
    from geolab.ui import main_window
    c = win.chat
    win.set_project(slope_project())
    n_undo = len(win.undo_stack)
    c.run_actions(A.parse_reply(reply("", [("set_material", {"name": "Sand", "phi": 38}),
                                            ("move_water_table", {"dy": -1})])).actions)
    assert next(m for m in win.project.materials if m.name == "Sand").phi == 38
    assert len(win.undo_stack) == n_undo + 1 and win.dirty           # one undo step for the whole reply
    notes = [t for r, t in c.panel.messages if r == "note"]
    assert any("Sand" in t for t in notes) and any("moved" in t for t in notes)
    monkeypatch.setattr(win, "maybe_save", lambda: True)
    spec2 = dict(GOOD, title="Second slope")
    c.run_actions([{"type": "build_model", "params": {"spec": GOOD, "where": "current"}},
                   {"type": "build_model", "params": {"spec": spec2, "where": "new_window"}}])
    assert win.project.title == "Cut slope"
    assert [w.project.title for w in main_window._EXTRA_WINDOWS] == ["Second slope"]
    c.run_actions([{"type": "set_material", "params": {"name": "granite"}}])
    assert c.panel.messages[-1][0] == "error"


def test_chat_send_runs_in_background_and_solves(win, app, monkeypatch):
    c = win.chat
    win.set_project(slope_project())
    monkeypatch.setattr(A, "call_provider",
                        lambda s, system, msgs: reply("Solving now", [("solve", {})]))
    c.set_mode("popup")
    c.panel.input.setPlainText("solve it")
    c.panel._send()
    for _ in range(600):
        app.processEvents()
        if c.worker is None and win.worker is None and c.panel.messages[-1][0] != "user" \
                and "Solved" in c.panel.messages[-1][1]:
            break
        import time
        time.sleep(0.02)
    texts = [t for _, t in c.panel.messages]
    assert texts[0] == "solve it" and "Solving now" in texts
    assert "factor of safety" in texts[-1] and win.project.analyses[0].results


def test_theme_switch_recolours_canvas_and_home(win, app):
    from PySide6.QtGui import QPalette
    from geolab.ui import render
    from geolab.ui.theme import is_dark
    win.set_theme("dark")
    assert is_dark() and app.palette().color(QPalette.Window).lightness() < 80
    assert win.settings.value("ui/theme") == "dark" and win.a_theme["dark"].isChecked()
    assert "#1b1c1f" in win.home.styleSheet()
    r = render.Renderer(win.project, None, render.View(), None, opts={"dark": True})
    assert r.c["background"] != "#ffffff"
    assert render.Renderer(win.project, None, render.View(), None, opts={"dark": True, "screen": False}).c[
        "background"] == "#ffffff"                     # printing stays on white paper
    win.set_theme("light")
    assert not is_dark() and app.palette().color(QPalette.Window).lightness() > 200


def test_preferences_save_provider_and_toggle_chat(win, app, monkeypatch):
    from PySide6.QtWidgets import QDialog
    from geolab.ui import prefs
    d = prefs.PreferencesDialog(win.settings, win, "ai")
    assert d.tabs.tabText(d.tabs.currentIndex()) == "AI Assistant"
    d.provider.setCurrentIndex(d.provider.findData("compatible"))
    d.preset.activated.emit(d.preset.findText("Ollama (on this computer)"))
    assert d.base.text() == "http://localhost:11434/v1"
    d.model.setText("llama3.1")
    d.provider.setCurrentIndex(d.provider.findData("openai"))
    d.key.setText("sk-test")
    d.provider.setCurrentIndex(d.provider.findData("compatible"))
    assert d.model.text() == "llama3.1"                 # each service keeps its own fields
    d.enabled.setChecked(False)
    d.theme_buttons["dark"].setChecked(True)

    d.exec = lambda: QDialog.Accepted
    monkeypatch.setattr(prefs, "PreferencesDialog", lambda *a, **k: d)    # the window opens this dialog
    win.preferences("ai")
    qs = win.settings
    assert qs.value("ai/provider") == "compatible" and qs.value("ai/model/compatible") == "llama3.1"
    assert qs.value("ai/key/openai") == "sk-test" and qs.value("ai/base_url") == "http://localhost:11434/v1"
    assert qs.value("ai/chat_enabled") == "false" and not win.chat.enabled and not win.chat.head.isVisible()
    assert qs.value("ui/theme") == "dark"
    s = win.chat.assistant.settings
    assert (s.provider, s.model, s.base_url) == ("compatible", "llama3.1", "http://localhost:11434/v1")
