import os
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QWidget, QFrame, QLabel, QVBoxLayout, QHBoxLayout

from .. import icons
from ..theme import P
from ..widgets import PageHeader, Card, ReflowGrid, PixView, ElidedLabel, ThemedIcon, make_button, divider
from ..thumbs import thumbnail

SAMPLES = Path(__file__).resolve().parent.parent / "samples"

TEMPLATES = [
    ("symbol_demo.png", "Symbol demo",
     "Every symbol once: solid walls, a jagged line (becomes breakable props), a star (player start), squares (doors) and a triangle (enemy spawn). "
     "The quickest way to see how detection works."),
    ("labyrinth.jpg", "Labyrinth",
     "A photographed maze drawn with straight lines and a few jagged breakable lines. A good test of wall snapping and scale."),
]


class TemplateCard(Card):
    def __init__(self, path, name):
        super().__init__(hoverable=True)
        self.path = str(path)
        v = QVBoxLayout(self)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(8)
        th = PixView(radius=12, bg="inset")
        th.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        pm = thumbnail(self.path)
        if pm is not None:
            th.set_pixmap(pm)
        v.addWidget(th, 1)
        n = ElidedLabel(name)
        n.setObjectName("cardTitle")
        n.setAlignment(Qt.AlignmentFlag.AlignCenter)
        n.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        v.addWidget(n)


class TemplatesPage(QWidget):
    use_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.items = [(SAMPLES / f, n, d) for f, n, d in TEMPLATES if (SAMPLES / f).is_file()]
        self.selected = None
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        main = QWidget()
        mv = QVBoxLayout(main)
        mv.setContentsMargins(32, 24, 32, 28)
        mv.setSpacing(18)
        mv.addWidget(PageHeader())
        row = QHBoxLayout()
        row.setSpacing(12)
        chip = ThemedIcon("templates", 20)
        chip.setObjectName("chip")
        chip.setFixedSize(46, 36)
        chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(chip)
        t = QLabel("Templates")
        t.setObjectName("h2")
        row.addWidget(t)
        sub = QLabel("Example sketches to try")
        sub.setObjectName("faint")
        row.addWidget(sub)
        row.addStretch(1)
        mv.addLayout(row)
        self.grid = ReflowGrid(min_card_w=260, card_h=232)
        cards = []
        for path, name, _d in self.items:
            c = TemplateCard(path, name)
            c.clicked.connect(lambda p=str(path): self._select(p))
            c.activated.connect(lambda p=str(path): self.use_requested.emit(p))
            cards.append(c)
        self.grid.set_items(cards)
        self._cards = cards
        mv.addWidget(self.grid, 1)
        lay.addWidget(main, 1)

        panel = QFrame()
        panel.setObjectName("panel")
        panel.setFixedWidth(340)
        pv = QVBoxLayout(panel)
        pv.setContentsMargins(28, 26, 28, 24)
        pv.setSpacing(0)
        head = QHBoxLayout()
        head.setSpacing(10)
        ic = ThemedIcon("templates", 22)
        head.addWidget(ic)
        pt = QLabel("Template Preview")
        pt.setObjectName("panelTitle")
        head.addWidget(pt)
        head.addStretch(1)
        pv.addLayout(head)
        pv.addSpacing(16)
        pv.addWidget(divider())
        pv.addSpacing(18)
        self.preview = PixView(radius=14, bg="inset")
        self.preview.setFixedHeight(220)
        pv.addWidget(self.preview)
        pv.addSpacing(18)
        pv.addWidget(divider())
        pv.addSpacing(16)
        self.p_name = QLabel("")
        self.p_name.setObjectName("h2")
        pv.addWidget(self.p_name)
        pv.addSpacing(8)
        self.p_desc = QLabel("")
        self.p_desc.setObjectName("muted")
        self.p_desc.setWordWrap(True)
        pv.addWidget(self.p_desc)
        pv.addStretch(1)
        self.use_btn = make_button("Use template", "import", variant="primary")
        self.use_btn.clicked.connect(lambda: self.selected and self.use_requested.emit(self.selected))
        pv.addWidget(self.use_btn)
        lay.addWidget(panel)

        if self.items:
            self._select(str(self.items[0][0]))
        else:
            self.p_name.setText("No templates found")
            self.p_desc.setText("The samples folder next to the app is empty.")
            self.use_btn.setEnabled(False)

    def _select(self, path):
        self.selected = path
        for c in self._cards:
            c.set_selected(c.path == path)
        for p, name, desc in self.items:
            if str(p) == path:
                pm = thumbnail(path, 640, 440)
                self.preview.set_pixmap(pm)
                self.p_name.setText(name)
                self.p_desc.setText(desc)
