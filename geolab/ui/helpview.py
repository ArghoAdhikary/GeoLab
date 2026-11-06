"""Help window: the user manual and the tutorials, readable while you work, plus the example files."""
from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import QStandardPaths, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMessageBox,
                               QPushButton, QSplitter, QTextBrowser, QVBoxLayout, QWidget)

from .. import help as docs


class HelpWindow(QDialog):
    """Chapters and tutorials on the left, the page on the right. Not modal, so a tutorial can stay
    open beside the drawing."""

    open_example = Signal(str)          # name of a built-in example
    open_quick = Signal(dict)           # Quick Slope inputs

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("GeoLab Help")
        self.setWindowFlag(Qt.WindowMinMaxButtonsHint, True)
        self.setModal(False)
        self.resize(980, 720)
        self.pages = [("manual", c) for c in docs.chapters()] + [("tutorial", t) for t in docs.tutorials()]

        self.list = QListWidget()
        self.list.setMinimumWidth(250)
        head = QListWidgetItem("User manual")
        head.setFlags(Qt.NoItemFlags)
        f = head.font(); f.setBold(True); head.setFont(f)
        self.list.addItem(head)
        self.rows = {}
        for i, (kind, page) in enumerate(self.pages):
            if kind == "tutorial" and not any(k == "tutorial" for k, _ in self.pages[:i]):
                h = QListWidgetItem("Tutorials")
                h.setFlags(Qt.NoItemFlags)
                h.setFont(f)
                self.list.addItem(h)
            it = QListWidgetItem("   " + page["title"])
            it.setData(Qt.UserRole, i)
            self.list.addItem(it)
            self.rows[i] = it
        self.list.currentItemChanged.connect(self._show)

        self.view = QTextBrowser()
        self.view.setOpenExternalLinks(True)
        self.view.setSearchPaths([str(docs.img_dir().parent)])
        self.view.document().setDefaultStyleSheet("table{border-collapse:collapse} td,th{padding:3px 8px}")

        self.ex_btn = QPushButton("Open the model for this tutorial")
        self.ex_btn.clicked.connect(self._open_model)
        pdf = QPushButton("Open the PDF manual")
        pdf.clicked.connect(self.open_pdf)
        pdf.setEnabled(docs.pdf_path() is not None)
        if docs.pdf_path() is None:
            pdf.setToolTip("The PDF manual is part of the installed program")
        exf = QPushButton("Example files folder")
        exf.clicked.connect(lambda: open_examples_folder(self))
        buttons = QHBoxLayout()
        buttons.addWidget(self.ex_btn)
        buttons.addStretch(1)
        buttons.addWidget(exf)
        buttons.addWidget(pdf)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.addWidget(self.view, 1)
        rv.addLayout(buttons)
        split = QSplitter()
        split.addWidget(self.list)
        split.addWidget(right)
        split.setStretchFactor(1, 1)
        v = QVBoxLayout(self)
        v.addWidget(split)
        self.show_page(0)

    # ------------------------------------------------------------------
    def show_page(self, index: int):
        if index in self.rows:
            self.list.setCurrentItem(self.rows[index])

    def show_tutorials(self):
        first = next((i for i, (k, _) in enumerate(self.pages) if k == "tutorial"), 0)
        self.show_page(first)

    def current(self):
        it = self.list.currentItem()
        if it is None or it.data(Qt.UserRole) is None:
            return None, None
        return self.pages[it.data(Qt.UserRole)]

    def _show(self, *_):
        kind, page = self.current()
        if page is None:
            return
        self.view.setMarkdown(docs.clean_markdown(page["text"]))
        self.view.verticalScrollBar().setValue(0)
        has_model = kind == "tutorial" and (page.get("example") or page.get("quick"))
        self.ex_btn.setVisible(bool(has_model))

    def _open_model(self):
        kind, page = self.current()
        if not page:
            return
        if page.get("example"):
            self.open_example.emit(page["example"])
        elif page.get("quick"):
            self.open_quick.emit(page["quick"])

    def open_pdf(self):
        p = docs.pdf_path()
        if p is None:
            QMessageBox.information(self, "User manual", "The PDF manual is part of the installed program and "
                                    "of every release on GitHub (GeoLab-User-Manual.pdf).")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))


def examples_target() -> Path:
    docs_dir = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation) or str(Path.home())
    return Path(docs_dir) / "GeoLab Examples"


def copy_examples(target: Path) -> int:
    """Put every example in target as a solved .slab file (copied from the program when it has them,
    otherwise written now without results). Returns the number of files."""
    target.mkdir(parents=True, exist_ok=True)
    src = docs.bundled_examples_dir()
    n = 0
    if src is not None:
        for f in sorted(src.glob("*.slab")):
            dst = target / f.name
            if not dst.exists():
                shutil.copy2(f, dst)
            n += 1
        return n
    from ..examples import write_example_files
    return len(write_example_files(target, solve=False, overwrite=False))


def open_examples_folder(parent=None):
    target = examples_target()
    try:
        n = copy_examples(target)
    except OSError as e:
        QMessageBox.warning(parent, "Example files", f"Could not write the example files to {target}:\n{e}")
        return None
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))
    return target, n
