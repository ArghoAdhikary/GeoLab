"""Working comfort: command palette, own shortcuts and toolbar, undo history panel, version history,
thumbnails of recent projects, crash recovery, update check and sharing a report."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QIcon, QKeySequence, QPixmap
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QHBoxLayout, QHeaderView, QKeySequenceEdit,
                               QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit,
                               QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout)


def clean(text: str) -> str:
    return text.replace("&&", "\x00").replace("&", "").replace("\x00", "&").replace("...", "").strip()


def all_actions(window) -> list[tuple[str, QAction]]:
    """Every menu command of the window as (menu path, action), in menu order."""
    out, seen = [], set()

    def walk(menu, path):
        for a in menu.actions():
            if a.isSeparator():
                continue
            if a.menu() is not None:
                walk(a.menu(), path + [clean(a.text())])
            elif a.text() and id(a) not in seen:
                seen.add(id(a))
                out.append((" > ".join(path + [clean(a.text())]), a))
    for top in window.menuBar().actions():
        if top.menu() is not None:
            walk(top.menu(), [clean(top.text())])
    return out


def action_key(a: QAction) -> str:
    return re.sub(r"\s+", " ", clean(a.text()))


# --------------------------------------------------------------------------- command palette
class CommandPalette(QDialog):
    """Ctrl+K: type part of any command's name and press Enter."""

    def __init__(self, window):
        super().__init__(window)
        self.setWindowTitle("Command Palette")
        self.setWindowFlag(Qt.FramelessWindowHint, True)
        self.resize(620, 420)
        v = QVBoxLayout(self)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("Type a command, for example 'solve', 'pdf', 'rain', 'theme'...")
        self.edit.setMinimumHeight(34)
        v.addWidget(self.edit)
        self.list = QListWidget()
        v.addWidget(self.list, 1)
        self.items = [(p, a) for p, a in all_actions(window) if a.isEnabled() or True]
        self.edit.textChanged.connect(self.filter)
        self.edit.returnPressed.connect(self.run)
        self.list.itemActivated.connect(lambda *_: self.run())
        self.filter("")
        g = window.geometry()
        self.move(g.x() + (g.width() - self.width()) // 2, g.y() + 80)

    @staticmethod
    def score(query: str, text: str) -> int:
        q, t = query.lower().strip(), text.lower()
        if not q:
            return 1
        if q in t:
            return 100 - t.index(q) + (50 if t.split(" > ")[-1].startswith(q) else 0)
        words = q.split()
        if all(w in t for w in words):
            return 40
        # letters in order (fuzzy)
        i = 0
        for ch in t:
            if i < len(q) and ch == q[i]:
                i += 1
        return 10 if i == len(q) else 0

    def filter(self, text):
        self.list.clear()
        scored = sorted(((self.score(text, p), p, a) for p, a in self.items), key=lambda x: -x[0])
        for s, p, a in scored:
            if s <= 0:
                continue
            sc = a.shortcut().toString(QKeySequence.NativeText)
            it = QListWidgetItem(f"{p}" + (f"     {sc}" if sc else ""))
            it.setData(Qt.UserRole, a)
            if not a.isEnabled():
                it.setFlags(it.flags() & ~Qt.ItemIsEnabled)
            if not a.icon().isNull():
                it.setIcon(a.icon())
            self.list.addItem(it)
            if self.list.count() >= 60:
                break
        for i in range(self.list.count()):
            if self.list.item(i).flags() & Qt.ItemIsEnabled:
                self.list.setCurrentRow(i)
                break

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Down, Qt.Key_Up):
            self.list.keyPressEvent(e)
            return
        if e.key() == Qt.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(e)

    def run(self):
        it = self.list.currentItem()
        if it is None:
            return None
        a = it.data(Qt.UserRole)
        self.accept()
        if a is not None and a.isEnabled():
            a.trigger()
        return a


# --------------------------------------------------------------------------- shortcuts and my toolbar
def load_shortcuts(settings) -> dict:
    try:
        return json.loads(settings.value("ui/shortcuts", "") or "{}")
    except ValueError:
        return {}


def load_my_toolbar(settings) -> list:
    try:
        return json.loads(settings.value("ui/my_toolbar", "") or "[]")
    except ValueError:
        return []


def apply_shortcuts(window, settings):
    """Put the user's shortcuts on the actions (keeps the defaults for the rest)."""
    sc = load_shortcuts(settings)
    for _, a in all_actions(window):
        k = action_key(a)
        if not hasattr(a, "_default_sc"):
            a._default_sc = a.shortcut().toString()
        if k in sc:
            a.setShortcut(QKeySequence(sc[k]))
        else:
            a.setShortcut(QKeySequence(a._default_sc))


def build_my_toolbar(window, settings):
    tb = getattr(window, "my_toolbar", None)
    keys = load_my_toolbar(settings)
    if tb is None:
        tb = window.addToolBar("My Tools")
        tb.setObjectName("my_tools")
        window.my_toolbar = tb
    tb.clear()
    acts = {action_key(a): a for _, a in all_actions(window)}
    for k in keys:
        if k == "|":
            tb.addSeparator()
        elif k in acts:
            tb.addAction(acts[k])
    tb.setVisible(bool(keys))
    return tb


class ShortcutsDialog(QDialog):
    """Change any keyboard shortcut and choose the commands on the 'My Tools' toolbar."""

    def __init__(self, window, settings):
        super().__init__(window)
        self.w, self.s = window, settings
        self.setWindowTitle("Keyboard Shortcuts and My Toolbar")
        self.resize(820, 640)
        v = QVBoxLayout(self)
        top = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Find a command...")
        self.search.textChanged.connect(self.filter)
        top.addWidget(self.search, 1)
        v.addLayout(top)
        self.acts = all_actions(window)
        self.table = QTableWidget(len(self.acts), 3)
        self.table.setHorizontalHeaderLabels(["Command", "Shortcut", "On My Toolbar"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        mine = set(load_my_toolbar(settings))
        self.editors, self.checks = [], []
        for r, (path, a) in enumerate(self.acts):
            it = QTableWidgetItem(path)
            it.setFlags(it.flags() & ~Qt.ItemIsEditable)
            if not a.icon().isNull():
                it.setIcon(a.icon())
            self.table.setItem(r, 0, it)
            ed = QKeySequenceEdit(a.shortcut())
            self.table.setCellWidget(r, 1, ed)
            self.editors.append(ed)
            cb = QCheckBox()
            cb.setChecked(action_key(a) in mine)
            self.table.setCellWidget(r, 2, cb)
            self.checks.append(cb)
        v.addWidget(self.table, 1)
        self.warn = QLabel("")
        self.warn.setStyleSheet("color:#c0392b")
        v.addWidget(self.warn)
        row = QHBoxLayout()
        reset = QPushButton("Reset All Shortcuts")
        reset.clicked.connect(self.reset)
        row.addWidget(reset)
        row.addStretch(1)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.save)
        bb.rejected.connect(self.reject)
        row.addWidget(bb)
        v.addLayout(row)

    def filter(self, text):
        t = text.lower()
        for r, (path, _) in enumerate(self.acts):
            self.table.setRowHidden(r, bool(t) and t not in path.lower())

    def reset(self):
        for (_, a), ed in zip(self.acts, self.editors):
            ed.setKeySequence(QKeySequence(getattr(a, "_default_sc", a.shortcut().toString())))

    def conflicts(self):
        seen, bad = {}, []
        for (path, _), ed in zip(self.acts, self.editors):
            k = ed.keySequence().toString()
            if not k:
                continue
            if k in seen:
                bad.append(f"{k}: {seen[k]} and {path}")
            seen[k] = path
        return bad

    def save(self):
        bad = self.conflicts()
        if bad:
            self.warn.setText("The same key is used twice: " + "; ".join(bad[:3]))
            return
        sc = {}
        for (_, a), ed in zip(self.acts, self.editors):
            k = ed.keySequence().toString()
            if k != getattr(a, "_default_sc", a.shortcut().toString()):
                sc[action_key(a)] = k
        mine = [action_key(a) for (_, a), cb in zip(self.acts, self.checks) if cb.isChecked()]
        self.s.setValue("ui/shortcuts", json.dumps(sc))
        self.s.setValue("ui/my_toolbar", json.dumps(mine))
        apply_shortcuts(self.w, self.s)
        build_my_toolbar(self.w, self.s)
        self.accept()


# --------------------------------------------------------------------------- undo history
class UndoHistory(QListWidget):
    """The list of changes; click one to go back to just after it."""

    def __init__(self, window):
        super().__init__()
        self.w = window
        self.itemClicked.connect(self.go)

    def refresh(self):
        self.blockSignals(True)
        self.clear()
        self.addItem(QListWidgetItem("Opened / start"))
        for desc in getattr(self.w, "undo_desc", []):
            self.addItem(QListWidgetItem(desc))
        cur = self.count() - 1
        for desc in reversed(getattr(self.w, "redo_desc", [])):
            it = QListWidgetItem(desc + "   (undone)")
            it.setForeground(Qt.gray)
            self.addItem(it)
        self.setCurrentRow(cur)
        self.blockSignals(False)

    def go(self, item):
        row = self.row(item)
        n = len(self.w.undo_stack)
        while n > row and self.w.undo_stack:
            self.w.undo()
            n -= 1
        while n < row and self.w.redo_stack:
            self.w.redo()
            n += 1
        self.refresh()


# --------------------------------------------------------------------------- version history
def versions_of(path, title, settings) -> list[dict]:
    """Saved versions of a project: the file, its .bak, autosaves and cloud backups (newest first)."""
    from .. import backup
    out = []
    stem = Path(path).stem if path else backup.safe_name(title or "Untitled")

    def add(p, kind):
        p = Path(p)
        if p.is_file():
            out.append({"path": str(p), "kind": kind, "time": p.stat().st_mtime, "size": p.stat().st_size})
    if path:
        add(path, "current file")
        add(str(path) + ".bak", "previous save (.bak)")
    add(backup.autosave_path(stem), "autosave")
    folder = settings.value("backup/folder", "") or ""
    if folder:
        for p in backup.versions(folder, stem):
            add(p, "cloud backup")
    out.sort(key=lambda d: -d["time"])
    return out


def summary(project) -> dict:
    fos = {a.name: (a.results or {}).get("critical", {}).get("fos") for a in project.analyses if a.kind == "slope"}
    return {"materials": {m.name: (m.cohesion, m.phi, m.unit_weight) for m in project.materials},
            "regions": len(project.regions), "analyses": len(project.analyses), "fos": fos,
            "water": bool(project.piezometric_line)}


def diff_text(a, b) -> str:
    sa, sb = summary(a), summary(b)
    lines = []
    for name in sorted(set(sa["materials"]) | set(sb["materials"])):
        x, y = sa["materials"].get(name), sb["materials"].get(name)
        if x != y:
            fmt = (lambda t: "-" if t is None else f"c' {t[0]:g}, phi' {t[1]:g}, gamma {t[2]:g}")
            lines.append(f"Material {name}: {fmt(x)}  ->  {fmt(y)}")
    for k in ("regions", "analyses", "water"):
        if sa[k] != sb[k]:
            lines.append(f"{k.title()}: {sa[k]} -> {sb[k]}")
    for n in sorted(set(sa["fos"]) | set(sb["fos"])):
        x, y = sa["fos"].get(n), sb["fos"].get(n)
        if x != y:
            f = (lambda v: "not solved" if v is None else f"{v:.3f}")
            lines.append(f"F of {n}: {f(x)} -> {f(y)}")
    if a.to_dict(include_results=False) != b.to_dict(include_results=False) and not lines:
        lines.append("Other changes (points, boundary conditions or settings).")
    return "\n".join(lines) or "No differences."


class VersionHistoryDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.w = window
        self.setWindowTitle("Version History")
        self.resize(820, 560)
        v = QVBoxLayout(self)
        v.addWidget(QLabel("Saved versions of this project: the file, the previous save (.bak), the autosave and "
                           "the cloud drive backups. Compare one with the open project, open it in a new tab, or "
                           "restore it."))
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Saved", "Kind", "File"])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.verticalHeader().setVisible(False)
        v.addWidget(self.table, 2)
        row = QHBoxLayout()
        for text, slot in (("Compare with Open Project", self.compare), ("Open in New Tab", self.open_tab),
                           ("Restore This Version", self.restore)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addStretch(1)
        v.addLayout(row)
        self.out = QPlainTextEdit()
        self.out.setReadOnly(True)
        v.addWidget(self.out, 1)
        self.items = versions_of(window.path, window.project.title, window.settings)
        self.table.setRowCount(len(self.items))
        for r, d in enumerate(self.items):
            for c, val in enumerate((dt.datetime.fromtimestamp(d["time"]).strftime("%Y-%m-%d %H:%M"), d["kind"],
                                     d["path"])):
                it = QTableWidgetItem(val)
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(r, c, it)
        if self.items:
            self.table.selectRow(0)
        else:
            self.out.setPlainText("No saved versions yet. Save the project, and turn on the cloud backup in "
                                  "Edit > Preferences > Files & Backup to keep dated versions.")

    def chosen(self):
        r = self.table.currentRow()
        if r < 0 or r >= len(self.items):
            return None
        from ..fileio import load_project
        return load_project(self.items[r]["path"]), self.items[r]

    def compare(self):
        got = self.chosen()
        if got:
            self.out.setPlainText(f"{got[1]['kind']} ({got[1]['path']})  ->  open project\n\n"
                                  + diff_text(got[0], self.w.project))
        return got

    def open_tab(self):
        got = self.chosen()
        if got:
            self.w.new_tab(got[0], None, title=f"{Path(got[1]['path']).name}")
            self.accept()

    def restore(self):
        got = self.chosen()
        if not got:
            return
        self.w.before_change()
        path = self.w.path
        self.w.project = got[0]
        self.w.path = path
        self.w.after_change(f"Restored the version of {dt.datetime.fromtimestamp(got[1]['time']):%Y-%m-%d %H:%M}",
                            keep_results=True)
        self.accept()


# --------------------------------------------------------------------------- thumbnails
def thumb_dir() -> Path:
    from .. import backup
    return backup.autosave_dir().parent / "Thumbnails"


def thumbnail(path, size=(160, 96)) -> QIcon | None:
    """A small picture of a project file (cached by file name and time)."""
    p = Path(path)
    if not p.is_file():
        return None
    key = hashlib.sha1(f"{p.resolve()}|{p.stat().st_mtime}".encode()).hexdigest()[:16]
    d = thumb_dir()
    f = d / f"{key}.png"
    if not f.exists():
        try:
            from ..fileio import load_project
            from .tools import render_png
            proj = load_project(p)
            a = next((x for x in proj.analyses if x.results), proj.analyses[0] if proj.analyses else None)
            img = render_png(proj, a, w=size[0] * 2, h=size[1] * 2)
            d.mkdir(parents=True, exist_ok=True)
            img.scaled(size[0], size[1], Qt.KeepAspectRatio, Qt.SmoothTransformation).save(str(f))
        except Exception:                              # noqa: BLE001  (a missing picture is fine)
            return None
    pm = QPixmap(str(f))
    return QIcon(pm) if not pm.isNull() else None


# --------------------------------------------------------------------------- crash recovery
def session_file() -> Path:
    from .. import backup
    return backup.autosave_dir() / "session-running.json"


def begin_session():
    """Mark the session as running. Returns the info of a previous session that did not end normally."""
    f = session_file()
    prev = None
    if f.exists():
        try:
            prev = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            prev = {}
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"pid": os.getpid(), "started": time.time()}), encoding="utf-8")
    except OSError:
        pass
    return prev


def end_session():
    try:
        session_file().unlink()
    except OSError:
        pass


def install_crash_handler(window):
    """On an unexpected error: save a recovery copy, show the error, and keep running."""
    old = sys.excepthook

    def hook(etype, value, tb):
        import traceback
        text = "".join(traceback.format_exception(etype, value, tb))
        try:
            from .. import backup
            from ..fileio import save_project
            p = backup.autosave_path((window.project.title or "Untitled") + " (recovered)")
            p.parent.mkdir(parents=True, exist_ok=True)
            save_project(window.project, p)
            (p.parent / "last-error.txt").write_text(text, encoding="utf-8")
            saved = f"\n\nYour work was saved to:\n{p}"
        except Exception:                               # noqa: BLE001
            saved = ""
        if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
            QMessageBox.critical(window, "GeoLab", f"Something went wrong: {value}{saved}\n\nGeoLab keeps running. "
                                 "Please report it (Help > Report a Problem) with the file last-error.txt.")
        old(etype, value, tb)
    sys.excepthook = hook
    return hook


# --------------------------------------------------------------------------- update check
RELEASES = "https://api.github.com/repos/ArghoAdhikary/GeoLab/releases/latest"


def parse_version(v: str):
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3]) or (0,)


def check_update(current: str, opener=None, timeout=8.0) -> dict | None:
    """The latest release if it is newer than ``current``: {"version", "url", "assets": {name: url}}."""
    req = urllib.request.Request(RELEASES, headers={"User-Agent": "GeoLab", "Accept": "application/vnd.github+json"})
    with (opener or urllib.request.urlopen)(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8"))
    tag = data.get("tag_name", "")
    if parse_version(tag) <= parse_version(current):
        return None
    return {"version": tag.lstrip("v"), "url": data.get("html_url", ""), "notes": (data.get("body") or "")[:2000],
            "assets": {a["name"]: a["browser_download_url"] for a in data.get("assets", [])}}


def asset_for_this_computer(assets: dict) -> str | None:
    import platform
    if sys.platform == "win32":
        return assets.get("GeoLab-Setup.exe")
    if sys.platform == "darwin":
        return assets.get("GeoLab-macos-apple-silicon.zip" if platform.machine() == "arm64"
                          else "GeoLab-macos-intel.zip")
    return None


# --------------------------------------------------------------------------- share
def share_report(window, folder=None) -> Path:
    """Write the design report as one HTML file (pictures inside) into the cloud drive folder
    (GeoLab Shared), ready to share from Google Drive / OneDrive with a link."""
    import base64

    from .. import designreport
    from .tools import png_bytes, render_png
    p = window.project
    images = {}
    for a in p.analyses:
        if a.results:
            try:
                images[a.id] = png_bytes(render_png(p, a, w=1400, h=760))
            except Exception:                           # noqa: BLE001
                pass
    blocks = designreport.build(p, images)

    def src(i, png):
        return "data:image/png;base64," + base64.b64encode(png).decode("ascii")
    body = designreport.to_html(blocks, src)
    html = ("<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' "
            "content='width=device-width, initial-scale=1'>"
            f"<title>{(p.title or 'GeoLab report')}</title><style>body{{font-family:'Segoe UI','Helvetica Neue',"
            "Arial,sans-serif;max-width:960px;margin:24px auto;padding:0 16px;color:#1a1a1a}"
            "h1,h2{color:#1d4e89}table{border-collapse:collapse}td,th{border:1px solid #ccd;padding:4px 8px}"
            "img{max-width:100%}</style></head><body>" + body + "</body></html>")
    from .. import backup
    base = Path(folder or window.settings.value("backup/folder", "") or Path.home() / "Documents")
    out_dir = base / "GeoLab Shared"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{backup.safe_name(p.title or 'GeoLab report')} - report {dt.date.today():%Y-%m-%d}.html"
    out.write_text(html, encoding="utf-8")
    return out


__all__ = ["CommandPalette", "ShortcutsDialog", "UndoHistory", "VersionHistoryDialog", "thumbnail",
           "begin_session", "end_session", "install_crash_handler", "check_update", "share_report", "QSize"]
