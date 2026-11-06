"""StrataLab Assistant chat: a round chat head in the bottom-right corner, a small chat box
that opens from it, and a full side panel on the right.

Modes: ``head`` (only the round button), ``popup`` (small chat box above the button) and
``side`` (docked panel on the right). The same chat panel moves between the popup and the dock,
so the conversation is kept.
"""
from __future__ import annotations

import html
import re

from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, QRectF, QSize, Qt, QThread, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QKeyEvent, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QDockWidget, QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel,
                               QPlainTextEdit, QPushButton, QTextBrowser, QToolButton, QVBoxLayout, QWidget)

from ..ai import AIError
from ..assistant import PROVIDERS, Assistant, Settings, describe_project
from .theme import is_dark, manager

ACCENT = "#2f6fe0"
HEAD_SIZE = 58
MARGIN = 18
GREETING = ("Hi! I am the StrataLab Assistant. Ask me to build a slope (\"10 m high clay slope with a water "
            "table\"), change the open model (\"raise the water 1 m\", \"make clay c' = 15\"), solve it, "
            "or explain a result.")


def bubble_icon(size=26, color="white") -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    g = QPainter(pm)
    g.setRenderHint(QPainter.Antialiasing)
    g.setPen(Qt.NoPen)
    g.setBrush(QColor(color))
    s = size
    path = QPainterPath()
    path.addRoundedRect(QRectF(s * 0.08, s * 0.12, s * 0.84, s * 0.62), s * 0.22, s * 0.22)
    tail = QPainterPath()
    tail.moveTo(s * 0.26, s * 0.66)
    tail.lineTo(s * 0.22, s * 0.92)
    tail.lineTo(s * 0.48, s * 0.70)
    tail.closeSubpath()
    g.drawPath(path.united(tail))
    g.setBrush(QColor(ACCENT))
    for k in range(3):
        g.drawEllipse(QPointF(s * (0.32 + 0.18 * k), s * 0.43), s * 0.055, s * 0.055)
    g.end()
    return pm


class ChatHead(QWidget):
    """Round floating button (the minimised chat)."""
    clicked = Signal()

    def __init__(self, parent):
        super().__init__(parent)
        self.setFixedSize(HEAD_SIZE + 8, HEAD_SIZE + 8)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("StrataLab Assistant (AI chat)")
        self.unread = False
        self._hover = False
        self._icon = bubble_icon(28)
        sh = QGraphicsDropShadowEffect(self)
        sh.setBlurRadius(16)
        sh.setOffset(0, 3)
        sh.setColor(QColor(0, 0, 0, 110))
        self.setGraphicsEffect(sh)

    def paintEvent(self, e):
        g = QPainter(self)
        g.setRenderHint(QPainter.Antialiasing)
        c = QColor(ACCENT).lighter(112) if self._hover else QColor(ACCENT)
        g.setPen(Qt.NoPen)
        g.setBrush(c)
        g.drawEllipse(QRectF(4, 4, HEAD_SIZE, HEAD_SIZE))
        g.drawPixmap(int(4 + (HEAD_SIZE - 28) / 2), int(4 + (HEAD_SIZE - 28) / 2 + 1), self._icon)
        if self.unread:
            g.setBrush(QColor("#e53935"))
            g.setPen(QPen(QColor("white"), 2))
            g.drawEllipse(QRectF(HEAD_SIZE - 10, 4, 14, 14))
        g.end()

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()


class _Input(QPlainTextEdit):
    send = Signal()

    def keyPressEvent(self, e: QKeyEvent):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter) and not (e.modifiers() & Qt.ShiftModifier):
            self.send.emit()
            return
        super().keyPressEvent(e)


class ChatPanel(QWidget):
    """Header, conversation and input box."""
    send = Signal(str)
    want_mode = Signal(str)          # head / popup / side
    want_settings = Signal()
    want_clear = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.messages: list[tuple[str, str]] = []      # (role, text): user / assistant / note / error
        self.setObjectName("chatpanel")
        self.setAttribute(Qt.WA_StyledBackground, True)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.header = QFrame()
        self.header.setObjectName("chatheader")
        h = QHBoxLayout(self.header)
        h.setContentsMargins(10, 6, 6, 6)
        icon = QLabel()
        icon.setPixmap(bubble_icon(20))
        h.addWidget(icon)
        col = QVBoxLayout()
        col.setSpacing(0)
        self.title = QLabel("<b>StrataLab Assistant</b>")
        self.subtitle = QLabel("")
        self.subtitle.setObjectName("chatsub")
        col.addWidget(self.title)
        col.addWidget(self.subtitle)
        h.addLayout(col, 1)

        def tb(text, tip, slot):
            b = QToolButton()
            b.setText(text)
            b.setToolTip(tip)
            b.setAutoRaise(True)
            b.setObjectName("chatbtn")
            b.clicked.connect(slot)
            h.addWidget(b)
            return b
        self.b_settings = tb("⚙", "AI settings", self.want_settings.emit)
        self.b_clear = tb("⟲", "New conversation", self.want_clear.emit)
        self.b_size = tb("⤢", "Open as side panel", lambda: self.want_mode.emit(
            "popup" if self.b_size.property("side") else "side"))
        self.b_min = tb("—", "Minimise to chat head", lambda: self.want_mode.emit("head"))
        v.addWidget(self.header)

        self.view = QTextBrowser()
        self.view.setOpenExternalLinks(True)
        self.view.setFrameShape(QFrame.NoFrame)
        v.addWidget(self.view, 1)

        self.busy = QLabel("")
        self.busy.setObjectName("chatsub")
        self.busy.setContentsMargins(12, 2, 12, 2)
        v.addWidget(self.busy)
        box = QFrame()
        box.setObjectName("chatinput")
        bl = QHBoxLayout(box)
        bl.setContentsMargins(8, 6, 8, 8)
        self.input = _Input()
        self.input.setPlaceholderText("Message the assistant (Enter to send, Shift+Enter new line)")
        self.input.setFixedHeight(64)
        self.input.send.connect(self._send)
        bl.addWidget(self.input, 1)
        self.b_send = QPushButton("Send")
        self.b_send.setObjectName("chatsend")
        self.b_send.clicked.connect(self._send)
        bl.addWidget(self.b_send, 0, Qt.AlignBottom)
        v.addWidget(box)
        self.restyle()

    def set_side(self, side: bool):
        self.b_size.setProperty("side", side)
        self.b_size.setText("⤡" if side else "⤢")
        self.b_size.setToolTip("Back to small chat box" if side else "Open as side panel")

    def set_busy(self, busy: bool, text="Thinking..."):
        self.busy.setText(text if busy else "")
        self.b_send.setEnabled(not busy)

    def _send(self):
        text = self.input.toPlainText().strip()
        if text and self.b_send.isEnabled():
            self.input.clear()
            self.send.emit(text)

    def add(self, role: str, text: str):
        self.messages.append((role, text))
        self.render()

    def clear(self):
        self.messages.clear()
        self.render()

    # -- looks ---------------------------------------------------------------
    def restyle(self):
        dark = is_dark()
        c = {"bg": "#1e1f22" if dark else "#ffffff", "head": "#2b2d30" if dark else "#f3f5f9",
             "line": "#3a3d42" if dark else "#dde1e8", "sub": "#9a9ea6" if dark else "#6b7280",
             "text": "#e6e6e6" if dark else "#1a1a1a"}
        self.setStyleSheet(f"""
            QWidget#chatpanel {{ background: {c['bg']}; }}
            QLabel#chatsub {{ background: transparent; }}
            QFrame#chatheader {{ background: {c['head']}; border-bottom: 1px solid {c['line']}; }}
            QLabel#chatsub {{ color: {c['sub']}; font-size: 8.5pt; }}
            QToolButton#chatbtn {{ font-size: 12pt; padding: 2px 6px; color: {c['text']}; }}
            QTextBrowser {{ background: {c['bg']}; color: {c['text']}; }}
            QFrame#chatinput {{ background: {c['bg']}; border-top: 1px solid {c['line']}; }}
            QPlainTextEdit {{ background: {c['head']}; color: {c['text']}; border: 1px solid {c['line']};
                              border-radius: 8px; padding: 4px; }}
            QPushButton#chatsend {{ background: {ACCENT}; color: white; border: none; border-radius: 8px;
                                    padding: 8px 14px; font-weight: 600; }}
            QPushButton#chatsend:disabled {{ background: #7f9fd9; }}
        """)
        self.render()

    def render(self):
        dark = is_dark()
        col = {"user": ("#2f6fe0", "#ffffff"),
               "assistant": ("#2f3237", "#e9e9e9") if dark else ("#eef1f6", "#1a1a1a"),
               "note": ("#203a2a", "#a8e0b8") if dark else ("#e9f7ee", "#1d5b32"),
               "error": ("#4a2323", "#ffb4b4") if dark else ("#fdecec", "#8a1c1c")}
        parts = ["<div style='font-family:Segoe UI, sans-serif; font-size:10pt'>"]
        msgs = self.messages or [("assistant", GREETING)]
        for role, text in msgs:
            bg, fg = col.get(role, col["assistant"])
            align = "right" if role == "user" else "left"
            body = _format(text)
            if role == "note":
                body = "✓ " + body
            parts.append(
                f"<table width='100%' cellspacing='0' cellpadding='0' style='margin:4px 0'><tr>"
                f"<td align='{align}'><table cellspacing='0' cellpadding='8' "
                f"style='background:{bg}; color:{fg}; border-radius:10px'>"
                f"<tr><td style='color:{fg}'>{body}</td></tr></table></td></tr></table>")
        parts.append("</div>")
        self.view.setHtml("".join(parts))
        sb = self.view.verticalScrollBar()
        sb.setValue(sb.maximum())


def _format(text: str) -> str:
    t = html.escape(text)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    return t.replace("\n", "<br>")


class _Popup(QFrame):
    """The small chat box floating above the chat head."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("chatpopup")
        self.setFrameShape(QFrame.NoFrame)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(1, 1, 1, 1)
        sh = QGraphicsDropShadowEffect(self)
        sh.setBlurRadius(24)
        sh.setOffset(0, 4)
        sh.setColor(QColor(0, 0, 0, 120))
        self.setGraphicsEffect(sh)

    def restyle(self):
        line = "#3a3d42" if is_dark() else "#cfd5df"
        bg = "#1e1f22" if is_dark() else "#ffffff"
        self.setStyleSheet(f"QFrame#chatpopup {{ background: {bg}; border: 1px solid {line}; border-radius: 10px; }}")


class _Worker(QThread):
    done = Signal(object, str)

    def __init__(self, assistant, text, context):
        super().__init__()
        self.assistant, self.text, self.context = assistant, text, context

    def run(self):
        try:
            self.done.emit(self.assistant.ask(self.text, context=self.context), "")
        except AIError as e:
            self.done.emit(None, str(e))
        except Exception as e:             # network libraries can raise many things
            self.done.emit(None, f"{type(e).__name__}: {e}")


def load_settings(qs) -> Settings:
    prov = qs.value("ai/provider", "claude") or "claude"
    if prov not in PROVIDERS:
        prov = "claude"
    key = qs.value(f"ai/key/{prov}", "") or ""
    if prov == "claude" and not key:
        key = qs.value("ai/api_key", "") or ""          # key saved by the AI Slope Builder
    return Settings(provider=prov, model=qs.value(f"ai/model/{prov}", "") or "", api_key=key,
                    base_url=qs.value("ai/base_url", "") or "", command=qs.value(f"ai/command/{prov}", "") or "")


class ChatController(QObject):
    """Owns the chat head, the popup, the side dock and the assistant for one main window."""

    def __init__(self, window):
        super().__init__(window)
        self.w = window
        self.assistant = Assistant(load_settings(window.settings))
        self.head = ChatHead(window)
        self.head.clicked.connect(lambda: self.set_mode("popup"))
        self.popup = _Popup(window)
        self.panel = ChatPanel()
        self.popup.layout().addWidget(self.panel)
        self.dock = QDockWidget("Assistant", window)
        self.dock.setObjectName("assistant")
        self.dock.setAllowedAreas(Qt.RightDockWidgetArea | Qt.LeftDockWidgetArea)
        self.dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetClosable)
        window.addDockWidget(Qt.RightDockWidgetArea, self.dock)
        self.dock.hide()
        self.dock.visibilityChanged.connect(self._dock_visibility)
        self.panel.send.connect(self.send)
        self.panel.want_mode.connect(self.set_mode)
        self.panel.want_settings.connect(lambda: window.preferences("ai"))
        self.panel.want_clear.connect(self.clear)
        self.worker = None
        self._solving = False
        self.mode = "head"
        self.enabled = False
        window.installEventFilter(self)
        manager().changed.connect(self._restyle)
        self._restyle()
        self.refresh_subtitle()

    # -- state ---------------------------------------------------------------
    def set_enabled(self, on: bool):
        self.enabled = bool(on)
        if not self.enabled:
            self.head.hide()
            self.popup.hide()
            self._show_dock(False)
        else:
            self.set_mode(self.w.settings.value("ai/chat_mode", "head") or "head", remember=False)

    def set_mode(self, mode: str, remember=True):
        if mode not in ("head", "popup", "side"):
            mode = "head"
        if not self.enabled:
            return
        self.mode = mode
        if mode == "side":
            self.popup.hide()
            self.head.hide()
            self.dock.setWidget(self.panel)
            self.panel.set_side(True)
            self._show_dock(True)
            self.dock.raise_()
        else:
            self._show_dock(False)
            if self.panel.parent() is not self.popup:
                self.popup.layout().addWidget(self.panel)
            self.panel.set_side(False)
            self.head.setVisible(True)
            self.popup.setVisible(mode == "popup")
            if mode == "popup":
                self.head.unread = False
                self.head.update()
                self.panel.input.setFocus()
            self.place()
        if remember:
            self.w.settings.setValue("ai/chat_mode", mode)

    def toggle(self):
        if not self.enabled:
            return
        self.set_mode("head" if self.mode != "head" else "popup")

    def _show_dock(self, show):
        self._dock_change = True
        self.dock.setVisible(show)
        self._dock_change = False

    def _dock_visibility(self, visible):
        # the user closed the side panel with its own X: go back to the chat head
        if not visible and self.mode == "side" and not getattr(self, "_dock_change", False) \
                and not self.w.isMinimized() and self.w.isVisible() and not self.w.on_home():
            self.set_mode("head")

    def place(self):
        """Keep the head in the bottom-right corner of the window, the popup just above it."""
        w = self.w
        cw = w.centralWidget()
        if cw is None:
            return
        tl = cw.mapTo(w, QPoint(0, 0))
        area = QRectF(tl.x(), tl.y(), cw.width(), cw.height())
        hx = int(area.right() - self.head.width() - MARGIN + 4)
        hy = int(area.bottom() - self.head.height() - MARGIN + 4)
        self.head.move(hx, hy)
        self.head.raise_()
        pw = int(min(380, max(260, area.width() - 2 * MARGIN)))
        ph = int(min(540, max(260, area.height() - self.head.height() - 3 * MARGIN)))
        self.popup.setGeometry(int(area.right() - pw - MARGIN), int(hy - ph - 8), pw, ph)
        self.popup.raise_()

    def eventFilter(self, obj, ev):
        if obj is self.w and ev.type() in (QEvent.Resize, QEvent.Show, QEvent.LayoutRequest):
            self.place()
        return False

    def _restyle(self, *_):
        self.popup.restyle()
        self.panel.restyle()
        self.head.update()

    def refresh_settings(self):
        self.assistant.settings = load_settings(self.w.settings)
        self.refresh_subtitle()

    def refresh_subtitle(self):
        s = self.assistant.settings
        name = PROVIDERS.get(s.provider, s.provider).split(" (")[0]
        self.panel.subtitle.setText(f"{name} · {s.model_name() or 'default model'}")

    def clear(self):
        self.assistant.clear()
        self.panel.clear()

    # -- conversation ----------------------------------------------------------
    def send(self, text):
        if self.worker is not None:
            return
        self.panel.add("user", text)
        self.panel.set_busy(True)
        ctx = describe_project(self.w.project if not self.w.on_home() else None)
        self.worker = _Worker(self.assistant, text, ctx)
        self.worker.done.connect(self._answered)
        self.worker.start()

    def _answered(self, reply, err):
        self.worker.wait()
        self.worker = None
        self.panel.set_busy(False)
        if err:
            self.panel.add("error", err)
        else:
            if reply.text:
                self.panel.add("assistant", reply.text)
            self.run_actions(reply.actions)
        if self.mode == "head":
            self.head.unread = True
            self.head.update()

    def run_actions(self, actions):
        from ..assistant import apply_edit, build_from, invalidates_results
        w = self.w
        solve = False
        edited = False
        for act in actions:
            t = act["type"]
            try:
                if t == "solve":
                    solve = True
                elif t == "build_model":
                    p, notes = build_from(act)
                    where = (act.get("params") or {}).get("where", "current")
                    if where == "new_window":
                        win = w.open_in_new_window(p)
                        self.panel.add("note", f"Built '{p.title}' in a new window.")
                        if notes:
                            self.panel.add("assistant", "Assumptions: " + notes)
                        _ = win
                    else:
                        if not w.maybe_save():
                            self.panel.add("error", f"'{p.title}' was not opened (the current model was kept).")
                            continue
                        w.set_project(p, None, dirty=True)
                        self.panel.add("note", f"Built '{p.title}'.")
                        if notes:
                            self.panel.add("assistant", "Assumptions: " + notes)
                else:
                    if w.on_home():
                        w.show_workspace()
                    if not edited:
                        w.before_change()
                    note = apply_edit(w.project, act)
                    edited = edited or invalidates_results(act)
                    self.panel.add("note", note)
            except AIError as e:
                self.panel.add("error", str(e))
        if edited:
            w.after_change("AI assistant edit")
        elif actions:
            w.refresh_all()
        if solve:
            self.solve()

    def solve(self):
        w = self.w
        a = w.current_analysis()
        if a is None:
            self.panel.add("error", "There is no analysis to solve.")
            return
        if w.worker is not None:
            self.panel.add("error", "A solve is already running.")
            return
        w._start([a])
        if w.worker is None:                      # verify failed (a message box explained why)
            self.panel.add("error", "The model could not be solved; see the message.")
            return
        self.panel.set_busy(True, "Solving...")
        w.worker.finished_solve.connect(self._solved)

    def _solved(self, errors):
        self.panel.set_busy(False)
        a = self.w.current_analysis()
        r = a.results if a else None
        if errors:
            self.panel.add("error", "Solve failed: " + str(errors).strip())
        elif r and r.get("type") == "slope" and r.get("critical"):
            crit = r["critical"]
            meth = (a.method or "").replace("_", "-").title()
            others = crit.get("all_methods") or {}
            extra = ", ".join(f"{k.replace('_', ' ').title()} {v['fos']:.3f}" for k, v in others.items()
                              if k in ("ordinary", "bishop", "janbu", "spencer") and v.get("fos"))
            self.panel.add("note", f"Solved {a.name}: factor of safety **{crit['fos']:.3f}** ({meth})"
                           + (f". Other methods: {extra}." if extra else "."))
        else:
            self.panel.add("note", f"Solved {a.name if a else ''}. The results are on the canvas.")
        if self.mode == "head":
            self.head.unread = True
            self.head.update()
