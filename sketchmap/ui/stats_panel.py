from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (QFrame, QLabel, QVBoxLayout, QHBoxLayout, QPushButton, QStackedWidget, QComboBox,
                             QPlainTextEdit, QScrollArea, QWidget, QButtonGroup)

from .theme import FONT
from .widgets import IconButton, divider, PixView
from .qtutil import to_pixmap

STAGES = (("original", "1 · Original"), ("binary", "2 · Preprocessed (binary)"),
          ("segmented", "3 · Segmented"), ("thinned", "4 · Thinned (Zhang-Suen)"))


class StatsPanel(QFrame):
    closed = pyqtSignal()
    stage_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("drawer")
        self.setFixedWidth(540)
        self.st = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 18)
        lay.setSpacing(12)

        top = QHBoxLayout()
        title = QLabel("Stats for nerds")
        title.setObjectName("panelTitle")
        top.addWidget(title)
        top.addStretch(1)
        close = IconButton("close", 18, "Close", variant="round")
        close.setFixedSize(34, 34)
        close.clicked.connect(self.closed.emit)
        top.addWidget(close)
        lay.addLayout(top)
        sub = QLabel("Every algorithm shown as formula → computation → result → visual effect.")
        sub.setObjectName("faint")
        sub.setWordWrap(True)
        lay.addWidget(sub)

        seg = QHBoxLayout()
        seg.setSpacing(4)
        self.b_calc = QPushButton("Computations")
        self.b_pipe = QPushButton("Pipeline stages")
        grp = QButtonGroup(self)
        for i, b in enumerate((self.b_calc, self.b_pipe)):
            b.setCheckable(True)
            b.setProperty("variant", "seg")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            grp.addButton(b)
            seg.addWidget(b)
            b.clicked.connect(lambda _=False, i=i: self.stack.setCurrentIndex(i))
        seg.addStretch(1)
        self.b_calc.setChecked(True)
        lay.addLayout(seg)

        self.stack = QStackedWidget()
        lay.addWidget(self.stack, 1)

        pg = QWidget()
        v = QVBoxLayout(pg)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        row = QHBoxLayout()
        lab = QLabel("Show stage")
        lab.setObjectName("muted")
        row.addWidget(lab)
        self.combo = QComboBox()
        self.combo.addItem("All")
        self.combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.combo.currentTextChanged.connect(lambda _: self.stage_changed.emit())
        row.addWidget(self.combo, 1)
        v.addLayout(row)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        f = QFont(FONT["mono"])
        f.setPixelSize(12)
        self.text.setFont(f)
        v.addWidget(self.text, 1)
        self.stack.addWidget(pg)

        sc = QScrollArea()
        sc.setWidgetResizable(True)
        inner = QWidget()
        iv = QVBoxLayout(inner)
        iv.setContentsMargins(0, 0, 6, 0)
        iv.setSpacing(6)
        self.views = {}
        for key, name in STAGES:
            cap = QLabel(name)
            cap.setObjectName("cardTitle")
            iv.addWidget(cap)
            pv = PixView(radius=12, bg="inset", auto_height=True)
            pv.setMinimumHeight(150)
            pv.set_placeholder("image", "No image yet")
            self.views[key] = pv
            iv.addWidget(pv)
            iv.addSpacing(10)
        iv.addStretch(1)
        sc.setWidget(inner)
        self.stack.addWidget(sc)

    def set_data(self, st, A):
        self.st = st
        if A is not None:
            for k, v in A.previews.items():
                if k in self.views:
                    self.views[k].set_pixmap(to_pixmap(v))
        else:
            for pv in self.views.values():
                pv.set_pixmap(None)
                pv.set_placeholder("image", "Not available for opened level files")
        cur = self.combo.currentText()
        self.combo.blockSignals(True)
        self.combo.clear()
        self.combo.addItems(st.names() if st else ["All"])
        i = self.combo.findText(cur)
        self.combo.setCurrentIndex(max(i, 0))
        self.combo.blockSignals(False)

    def stage(self):
        return self.combo.currentText()

    def show_text(self, text):
        bar = self.text.verticalScrollBar()
        pos = bar.value()
        self.text.setPlainText(text)
        bar.setValue(pos)
