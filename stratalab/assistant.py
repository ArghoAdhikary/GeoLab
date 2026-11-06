"""StrataLab Assistant: a chat helper that can build and edit slope models.

It works with any AI service:

* ``claude``      - Claude through the Anthropic API (API key)
* ``openai``      - ChatGPT models through the OpenAI API (API key)
* ``compatible``  - any OpenAI-compatible server: Google Gemini, OpenRouter, DeepSeek, Groq, Mistral,
                    a local Ollama or LM Studio, ... (base URL, model and, if needed, a key)
* ``claude_cli``  - your Claude account, through the Claude Code command line tool (``claude``)
                    after you sign in to it once; no API key in StrataLab
* ``codex_cli``   - your ChatGPT account, through the OpenAI Codex command line tool (``codex``)
                    after you sign in to it once; no API key in StrataLab

Every service is asked for the same JSON reply, ``{"reply": text, "actions": [...]}``. The actions
are validated here, like user input, before they change anything.
"""
from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from .ai import SCHEMA as MODEL_SCHEMA
from .ai import AIError, project_from_ai
from .model import Project, Surcharge

PROVIDERS = {
    "claude": "Claude (Anthropic API key)",
    "openai": "ChatGPT (OpenAI API key)",
    "compatible": "Other AI (OpenAI-compatible: Gemini, OpenRouter, Ollama, ...)",
    "claude_cli": "Claude account (Claude Code app, no key)",
    "codex_cli": "ChatGPT account (Codex app, no key)",
}
DEFAULT_MODELS = {"claude": "claude-opus-5-5", "openai": "gpt-5", "compatible": "", "claude_cli": "",
                  "codex_cli": ""}
NEEDS_KEY = {"claude", "openai"}

ACTIONS = ("build_model", "set_material", "set_water_table", "move_water_table", "remove_water_table",
           "set_method", "add_surcharge", "clear_surcharges", "set_seismic", "set_title", "solve")
METHODS = ("ordinary", "bishop", "janbu", "spencer", "morgenstern_price")

REPLY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["reply", "actions"],
    "properties": {
        "reply": {"type": "string"},
        "actions": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["type", "params"],
            "properties": {"type": {"type": "string", "enum": list(ACTIONS)},
                           "params": {"type": "string"}}}},
    },
}

SYSTEM = """You are the StrataLab Assistant inside StrataLab, a 2D geotechnical analysis desktop app
(slope stability by limit equilibrium, seepage, stress and more). You help an engineering student or
engineer build and change slope stability models, run them and understand the results. Answer in
the user's language (for example Bengali written in English letters if they write that way). Keep
replies short and practical.

Always answer with ONE JSON object and nothing else:
{"reply": "<message shown to the user>", "actions": [{"type": "<action>", "params": "<JSON object as a string>"}]}
Use an empty actions list when you only talk. The app performs the actions in order, then shows
the user what happened. Never claim a result (for example a factor of safety) before a "solve"
action has produced it; the app reports it after solving.

Actions (params is a JSON object encoded as a string):
- build_model: {"spec": <model spec>, "where": "current" | "new_window"}
  Creates a complete slope model. "current" replaces the open model (the user is asked to save
  first); "new_window" opens it in another window. When the user asks for several models, emit
  one build_model per model: the first "current", the rest "new_window".
  The model spec follows this JSON schema: MODEL_SCHEMA
  Spec rules: x horizontal, y up; metric = m, kN/m3, kPa (imperial = ft, pcf, psf). Regions are
  simple non-overlapping polygons, listed around their boundary; neighbours share exact vertices;
  together they form one soil profile with a flat base, vertical sides and the ground on top. Extend
  the model at least 1.5x the slope height beyond the toe and crest and 0.5x below the toe.
  material_index is 0-based. Use typical values for anything not given and list every assumption.
  Use a piezometric line only when the user mentions water; it spans the whole model width.
- set_material: {"name": "<existing material name>", "unit_weight": n, "cohesion": n, "phi": n}
  (give only the properties to change; "new_name" renames)
- set_water_table: {"points": [[x, y], ...]}  (piezometric line across the model; also switches
  the slope analysis to use it)
- move_water_table: {"dy": n}  (raise (+) or lower (-) the existing line)
- remove_water_table: {}
- set_method: {"method": "ordinary" | "bishop" | "janbu" | "spencer" | "morgenstern_price"}
- add_surcharge: {"x1": n, "x2": n, "q": n}  (vertical pressure on the ground)
- clear_surcharges: {}
- set_seismic: {"kh": n, "kv": n}
- set_title: {"title": "..."}
- solve: {}  (solves the current model; the app adds the factor of safety to the chat)

The user's current model is described in each message under "Current model". Use its material
names and coordinates. If the request is unclear, ask a short question instead of guessing."""


def system_prompt() -> str:
    return SYSTEM.replace("MODEL_SCHEMA", json.dumps(MODEL_SCHEMA, separators=(",", ":")))


@dataclass
class Settings:
    provider: str = "claude"
    model: str = ""
    api_key: str = ""
    base_url: str = ""
    command: str = ""          # path to the claude / codex program, if not on PATH
    timeout: float = 240.0

    def model_name(self) -> str:
        return self.model.strip() or DEFAULT_MODELS.get(self.provider, "")


@dataclass
class Reply:
    text: str
    actions: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Describing the model to the AI
# ---------------------------------------------------------------------------
def describe_project(p: Project | None) -> dict:
    if p is None:
        return {"open": False}
    a = next((x for x in p.analyses if x.kind == "slope"), p.analyses[0] if p.analyses else None)
    d = {
        "title": p.title, "units": p.units,
        "materials": [{"name": m.name, "model": m.model, "unit_weight": m.unit_weight,
                       "cohesion": m.cohesion, "phi": m.phi} for m in p.materials],
        "regions": [{"material": (p.material(r.material_id).name if p.material(r.material_id) else None),
                     "points": [[round(x, 3), round(y, 3)] for x, y in r.points]} for r in p.regions],
        "piezometric_line": [[round(x, 3), round(y, 3)] for x, y in p.piezometric_line],
        "surcharges": [{"x1": s.x1, "x2": s.x2, "q": s.q} for s in p.surcharges],
    }
    if a is not None:
        d["analysis"] = {"name": a.name, "kind": a.kind, "method": getattr(a, "method", None),
                         "pore_pressure": getattr(a, "pwp", None), "kh": getattr(a, "kh", 0.0),
                         "kv": getattr(a, "kv", 0.0)}
        r = a.results or {}
        crit = r.get("critical") if isinstance(r, dict) else None
        if crit and crit.get("fos") is not None:
            d["analysis"]["factor_of_safety"] = round(float(crit["fos"]), 3)
    return d


# ---------------------------------------------------------------------------
# Reading the AI's answer
# ---------------------------------------------------------------------------
def parse_reply(text: str) -> Reply:
    """Find the JSON object in the model's text. Plain text without JSON becomes a reply."""
    text = (text or "").strip()
    dec = json.JSONDecoder()
    data = None
    i = text.find("{")
    while i != -1:
        try:
            obj, _ = dec.raw_decode(text, i)
            if isinstance(obj, dict) and "reply" in obj:
                data = obj
                break
        except json.JSONDecodeError:
            pass
        i = text.find("{", i + 1)
    if data is None:
        return Reply(text or "(no answer)", [])
    actions = []
    for act in data.get("actions") or []:
        if not isinstance(act, dict) or act.get("type") not in ACTIONS:
            continue
        params = act.get("params", {})
        if isinstance(params, str):
            try:
                params = json.loads(params) if params.strip() else {}
            except json.JSONDecodeError:
                params = {}
        actions.append({"type": act["type"], "params": params if isinstance(params, dict) else {}})
    return Reply(str(data.get("reply", "")), actions)


# ---------------------------------------------------------------------------
# Applying actions
# ---------------------------------------------------------------------------
def _num(params, key, lo=-math.inf, hi=math.inf):
    v = params.get(key)
    if v is None:
        return None
    try:
        v = float(v)
    except (TypeError, ValueError):
        raise AIError(f"'{key}' must be a number.")
    if not (lo <= v <= hi) or not math.isfinite(v):
        raise AIError(f"'{key}' = {v:g} is out of range.")
    return v


def _slope_analyses(p):
    return [a for a in p.analyses if a.kind == "slope"] or p.analyses[:1]


def apply_edit(p: Project, act: dict) -> str:
    """Apply one editing action to project ``p``. Returns a short note; raises AIError."""
    t, prm = act["type"], act.get("params") or {}
    if t == "set_material":
        name = str(prm.get("name", "")).strip().lower()
        m = next((m for m in p.materials if m.name.lower() == name), None)
        if m is None:
            raise AIError(f"No material named '{prm.get('name')}'.")
        changes = []
        for key, attr, lo, hi in (("unit_weight", "unit_weight", 0.1, 200), ("cohesion", "cohesion", 0, 1e5),
                                  ("phi", "phi", 0, 89.9)):
            v = _num(prm, key, lo, hi)
            if v is not None:
                setattr(m, attr, v)
                changes.append(f"{key} = {v:g}")
        if prm.get("new_name"):
            m.name = str(prm["new_name"])[:40]
            changes.append(f"name = {m.name}")
        return f"Material {m.name}: " + (", ".join(changes) or "no change")
    if t == "set_water_table":
        pts = []
        for q in prm.get("points") or []:
            try:
                x, y = float(q[0]), float(q[1])
            except (TypeError, ValueError, IndexError, KeyError):
                raise AIError("Water table points must be [x, y] pairs.")
            pts.append([x, y])
        if len(pts) < 2:
            raise AIError("A water table needs at least two points.")
        p.piezometric_line = sorted(pts)
        for a in _slope_analyses(p):
            a.pwp = "piezometric"
        return f"Water table set ({len(pts)} points)"
    if t == "move_water_table":
        dy = _num(prm, "dy", -1e4, 1e4) or 0.0
        if len(p.piezometric_line) < 2:
            raise AIError("There is no water table to move.")
        p.piezometric_line = [[x, y + dy] for x, y in p.piezometric_line]
        return f"Water table moved {dy:+g}"
    if t == "remove_water_table":
        p.piezometric_line = []
        for a in _slope_analyses(p):
            if a.pwp == "piezometric":
                a.pwp = "none"
        return "Water table removed"
    if t == "set_method":
        m = str(prm.get("method", ""))
        if m not in METHODS:
            raise AIError(f"Unknown method '{m}'.")
        for a in _slope_analyses(p):
            a.method = m
        return f"Method: {m}"
    if t == "add_surcharge":
        x1, x2 = _num(prm, "x1"), _num(prm, "x2")
        q = _num(prm, "q", -1e6, 1e6)
        if None in (x1, x2, q) or x1 == x2:
            raise AIError("A surcharge needs x1, x2 (different) and q.")
        p.surcharges.append(Surcharge(min(x1, x2), max(x1, x2), q))
        return f"Surcharge {q:g} from x = {min(x1, x2):g} to {max(x1, x2):g}"
    if t == "clear_surcharges":
        p.surcharges.clear()
        return "Surcharges removed"
    if t == "set_seismic":
        kh, kv = _num(prm, "kh", -1, 1), _num(prm, "kv", -1, 1)
        for a in _slope_analyses(p):
            if kh is not None:
                a.kh = kh
            if kv is not None:
                a.kv = kv
        return f"Seismic kh = {kh or 0:g}, kv = {kv or 0:g}"
    if t == "set_title":
        p.title = str(prm.get("title", p.title))[:120]
        return f"Title: {p.title}"
    raise AIError(f"'{t}' is not an editing action.")


def build_from(act: dict) -> tuple[Project, str]:
    spec = (act.get("params") or {}).get("spec")
    if not isinstance(spec, dict):
        raise AIError("build_model needs a model spec.")
    try:
        return project_from_ai(spec)
    except AIError:
        raise
    except (KeyError, TypeError, ValueError) as e:
        raise AIError(f"The model spec is incomplete ({e}).") from e


def invalidates_results(act: dict) -> bool:
    return act["type"] not in ("solve", "set_title", "build_model")


# ---------------------------------------------------------------------------
# Talking to the AI services
# ---------------------------------------------------------------------------
class Assistant:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()
        self.history: list[dict] = []        # {"role": "user"|"assistant", "content": str}

    def clear(self):
        self.history.clear()

    def ask(self, text: str, project: Project | None = None, transport=None, context: dict | None = None) -> Reply:
        """Send the user's message with the current model; return the parsed reply.

        ``context`` is a ready :func:`describe_project` result (lets a worker thread avoid touching
        the live project). ``transport(settings, system, messages) -> str`` replaces the network
        call (tests)."""
        if not text.strip():
            raise AIError("Type a message first.")
        ctx = json.dumps(context if context is not None else describe_project(project), separators=(",", ":"))
        msgs = list(self.history) + [{"role": "user", "content": f"Current model: {ctx}\n\nUser: {text}"}]
        send = transport or call_provider
        raw = send(self.settings, system_prompt(), msgs)
        reply = parse_reply(raw)
        self.history += [{"role": "user", "content": text},
                         {"role": "assistant", "content": json.dumps({"reply": reply.text})}]
        self.history = self.history[-24:]
        return reply


def call_provider(s: Settings, system: str, messages: list[dict]) -> str:
    prov = s.provider
    if prov == "claude":
        return _call_claude(s, system, messages)
    if prov in ("openai", "compatible"):
        return _call_openai_compatible(s, system, messages)
    if prov in ("claude_cli", "codex_cli"):
        return _call_cli(s, system, messages)
    raise AIError(f"Unknown AI service '{prov}'.")


def _call_claude(s: Settings, system: str, messages: list[dict]) -> str:
    import anthropic
    key = s.api_key.strip() or os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise AIError("Add your Anthropic API key in Settings > AI Assistant.")
    client = anthropic.Anthropic(api_key=key, timeout=s.timeout)
    try:
        resp = client.beta.messages.create(
            model=s.model_name() or DEFAULT_MODELS["claude"],
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": REPLY_SCHEMA}},
            system=system,
            messages=messages,
        )
    except anthropic.AuthenticationError as e:
        raise AIError("The Anthropic API key was rejected. Check it in Settings > AI Assistant.") from e
    except anthropic.RateLimitError as e:
        raise AIError("Rate limited by the Anthropic API. Wait a moment and try again.") from e
    except anthropic.APIStatusError as e:
        raise AIError(f"The Anthropic API returned an error ({e.status_code}): {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise AIError("Could not reach the Anthropic API. Check your internet connection.") from e
    if resp.stop_reason == "refusal":
        raise AIError("The request was declined by the model.")
    if resp.stop_reason == "max_tokens":
        raise AIError("The answer was cut off. Try a shorter request.")
    return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")


def _call_openai_compatible(s: Settings, system: str, messages: list[dict]) -> str:
    if s.provider == "openai":
        base = "https://api.openai.com/v1"
        key = s.api_key.strip() or os.environ.get("OPENAI_API_KEY", "")
        if not key:
            raise AIError("Add your OpenAI API key in Settings > AI Assistant.")
    else:
        base = s.base_url.strip().rstrip("/")
        key = s.api_key.strip()
        if not base:
            raise AIError("Enter the server address (base URL) in Settings > AI Assistant, "
                          "for example http://localhost:11434/v1 for Ollama.")
    model = s.model_name()
    if not model:
        raise AIError("Enter the model name in Settings > AI Assistant.")
    body = {"model": model, "messages": [{"role": "system", "content": system}] + messages,
            "response_format": {"type": "json_object"}}
    try:
        data = _post_json(base + "/chat/completions", body, key, s.timeout)
    except AIError as e:
        if "400" not in str(e):
            raise
        body.pop("response_format")       # some servers do not support JSON mode
        data = _post_json(base + "/chat/completions", body, key, s.timeout)
    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as e:
        raise AIError("The AI service sent an answer StrataLab could not read.") from e


def _post_json(url, body, key, timeout):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json",
                                          **({"Authorization": f"Bearer {key}"} if key else {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = json.loads(e.read().decode("utf-8")).get("error", {}).get("message", "")
        except Exception:
            pass
        if e.code in (401, 403):
            raise AIError(f"The AI service rejected the key ({e.code}). {detail}".strip()) from e
        raise AIError(f"The AI service returned an error ({e.code}). {detail}".strip()) from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise AIError(f"Could not reach the AI service at {url}: {e}") from e


def find_cli(s: Settings) -> str | None:
    name = "claude" if s.provider == "claude_cli" else "codex"
    if s.command.strip():
        return s.command.strip() if os.path.exists(s.command.strip()) else shutil.which(s.command.strip())
    return shutil.which(name)


def _transcript(system: str, messages: list[dict]) -> str:
    parts = [system, "", "Conversation so far:"]
    for m in messages:
        parts.append(f"[{m['role']}] {m['content']}")
    parts.append("")
    parts.append("Answer the last user message now with only the JSON object described above.")
    return "\n".join(parts)


def _call_cli(s: Settings, system: str, messages: list[dict]) -> str:
    exe = find_cli(s)
    if not exe:
        if s.provider == "claude_cli":
            raise AIError("Claude Code was not found. Install it (https://claude.com/claude-code), run "
                          "'claude' once to sign in with your Claude account, then try again.")
        raise AIError("Codex was not found. Install it (npm install -g @openai/codex), run 'codex' "
                      "once to sign in with your ChatGPT account, then try again.")
    prompt = _transcript(system, messages)
    work = tempfile.mkdtemp(prefix="stratalab-ai-")
    out_file = os.path.join(work, "answer.txt")
    if s.provider == "claude_cli":
        args = [exe, "-p", "--output-format", "text"]
        if s.model.strip():
            args += ["--model", s.model.strip()]
    else:
        args = [exe, "exec", "--skip-git-repo-check", "--output-last-message", out_file]
        if s.model.strip():
            args += ["--model", s.model.strip()]
        args.append("-")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        r = subprocess.run(args, input=prompt, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=s.timeout, cwd=work, creationflags=flags)
    except subprocess.TimeoutExpired as e:
        raise AIError("The AI took too long to answer. Try again.") from e
    except OSError as e:
        raise AIError(f"Could not start {exe}: {e}") from e
    text = ""
    if os.path.exists(out_file):
        with open(out_file, encoding="utf-8", errors="replace") as f:
            text = f.read()
    text = text or r.stdout
    if r.returncode != 0 and not text.strip():
        err = (r.stderr or "").strip().splitlines()
        hint = " Sign in by running it once in a terminal." if any(
            w in (r.stderr or "").lower() for w in ("login", "log in", "sign in", "auth")) else ""
        raise AIError(f"{os.path.basename(exe)} failed: {err[-1] if err else r.returncode}.{hint}")
    shutil.rmtree(work, ignore_errors=True)
    return text
