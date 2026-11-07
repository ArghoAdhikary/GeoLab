"""Python console: run scripts on the open model (batch runs, parameter studies, your own formulas).

Names ready to use:  project, analysis (the selected one), window, solve(a), solve_all(), geolab, np,
                     refresh() to redraw after a change, and print().
"""
from __future__ import annotations

import contextlib
import io
import traceback

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QSplitter, QVBoxLayout,
                               QWidget)

EXAMPLE = '''# Example: factor of safety for a range of cohesion values (Ctrl+Enter runs the script)
a = analysis
m = project.materials[0]
c0 = m.cohesion
for c in (2, 4, 6, 8, 10):
    m.cohesion = c
    r = solve(a)
    print(f"c = {c:5.1f}  F = {r['critical']['fos']:.3f}")
m.cohesion = c0
refresh()
'''


def run_code(code: str, namespace: dict) -> str:
    """Run code in the namespace; returns what it printed (and the error, if any)."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        try:
            try:
                res = eval(compile(code, "<console>", "eval"), namespace)
                if res is not None:
                    print(repr(res))
            except SyntaxError:
                exec(compile(code, "<console>", "exec"), namespace)
        except Exception:                                 # noqa: BLE001  (shown in the console)
            traceback.print_exc(limit=3)
    return out.getvalue()


class Console(QWidget):
    def __init__(self, main):
        super().__init__(main)
        self.main = main
        self.ns = {}
        v = QVBoxLayout(self)
        v.setContentsMargins(2, 2, 2, 2)
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.Monospace)
        split = QSplitter(Qt.Vertical)
        self.editor = QPlainTextEdit()
        self.editor.setFont(mono)
        self.editor.setPlainText(EXAMPLE)
        self.output = QPlainTextEdit()
        self.output.setFont(mono)
        self.output.setReadOnly(True)
        split.addWidget(self.editor)
        split.addWidget(self.output)
        v.addWidget(split, 1)
        row = QHBoxLayout()
        run = QPushButton("Run (Ctrl+Enter)")
        run.clicked.connect(self.run)
        clear = QPushButton("Clear output")
        clear.clicked.connect(self.output.clear)
        row.addWidget(QLabel("project, analysis, solve(a), solve_all(), refresh(), np, geolab"))
        row.addStretch(1)
        row.addWidget(clear)
        row.addWidget(run)
        v.addLayout(row)
        QShortcut(QKeySequence("Ctrl+Return"), self.editor, activated=self.run)

    def namespace(self):
        import numpy as np

        import geolab
        from ..solver import solve, solve_all
        m = self.main
        self.ns.update({"project": m.project, "analysis": m.current_analysis(), "window": m, "np": np,
                        "geolab": geolab, "solve": lambda a=None: solve(m.project, a or m.current_analysis()),
                        "solve_all": lambda: solve_all(m.project),
                        "refresh": lambda: (setattr(m, "dirty", True), m.refresh_all())})
        return self.ns

    def run(self):
        code = self.editor.textCursor().selectedText().replace(" ", "\n") or self.editor.toPlainText()
        self.output.appendPlainText(">>> run\n" + run_code(code, self.namespace()))
