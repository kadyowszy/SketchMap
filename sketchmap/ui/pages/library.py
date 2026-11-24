from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QFrame, QLabel, QVBoxLayout, QHBoxLayout, QLineEdit

from .. import icons
from ...config import LEGEND
from ...elements import ELEMENTS
from ..theme import P
from ..widgets import PageHeader, Card, ReflowGrid, ThemedIcon, divider
from ..theme import bus

MAP_LOOK = {e.key: (e.color, e.look) for e in ELEMENTS}


def glyph_color(key):
    if key in ("wall", "boundary"):
        return P[key]
    return MAP_LOOK[key][0]


class LibraryCard(Card):
    def __init__(self, key, name):
        super().__init__(hoverable=True)
        self.key = key
        v = QVBoxLayout(self)
        v.setContentsMargins(14, 18, 14, 16)
        v.addStretch(1)
        g = QLabel()
        g.setPixmap(icons.glyph_pixmap(key, 64, glyph_color(key)))
        bus.changed.connect(lambda: g.setPixmap(icons.glyph_pixmap(key, 64, glyph_color(key))))
        g.setAlignment(Qt.AlignmentFlag.AlignCenter)
        g.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        v.addWidget(g)
        v.addStretch(1)
        n = QLabel(name)
        n.setAlignment(Qt.AlignmentFlag.AlignCenter)
        n.setObjectName("cardTitle")
        n.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        v.addWidget(n)


class LibraryPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        main = QWidget()
        mv = QVBoxLayout(main)
        mv.setContentsMargins(32, 24, 32, 28)
        mv.setSpacing(20)
        mv.addWidget(PageHeader())
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search symbols")
        self.search.setClearButtonEnabled(True)
        self._search_act = self.search.addAction(icons.icon("search", 18, P["muted"]), QLineEdit.ActionPosition.TrailingPosition)
        bus.changed.connect(lambda: self._search_act.setIcon(icons.icon("search", 18, P["muted"])))
        self.search.textChanged.connect(self._filter)
        mv.addWidget(self.search)
        self.grid = ReflowGrid(min_card_w=210, card_h=206)
        mv.addWidget(self.grid, 1)
        self.empty = QLabel("No symbol matches your search.")
        self.empty.setObjectName("muted")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.hide()
        mv.addWidget(self.empty)
        lay.addWidget(main, 1)

        panel = QFrame()
        panel.setObjectName("panel")
        panel.setFixedWidth(340)
        pv = QVBoxLayout(panel)
        pv.setContentsMargins(28, 26, 28, 24)
        pv.setSpacing(0)
        head = QHBoxLayout()
        head.setSpacing(10)
        ic = ThemedIcon("library", 22)
        head.addWidget(ic)
        t = QLabel("Properties")
        t.setObjectName("panelTitle")
        head.addWidget(t)
        head.addStretch(1)
        pv.addLayout(head)
        pv.addSpacing(16)
        pv.addWidget(divider())
        pv.addStretch(1)
        self.big = QLabel()
        self.big.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pv.addWidget(self.big)
        pv.addStretch(1)
        pv.addWidget(divider())
        pv.addSpacing(18)
        self.name = QLabel("")
        self.name.setObjectName("h2")
        pv.addWidget(self.name)
        pv.addSpacing(14)
        k1 = QLabel("HOW TO DRAW IT")
        k1.setObjectName("metaKey")
        pv.addWidget(k1)
        self.how = QLabel("")
        self.how.setWordWrap(True)
        pv.addWidget(self.how)
        pv.addStretch(2)
        lay.addWidget(panel)

        bus.changed.connect(lambda: getattr(self, "_selected", None) and self._select(self._selected))
        self.cards = []
        self._build(LEGEND)
        if self.cards:
            self._select(self.cards[0].key)

    def _build(self, items):
        self.cards = []
        for key, name, _how in items:
            c = LibraryCard(key, name)
            c.clicked.connect(lambda k=key: self._select(k))
            self.cards.append(c)
        self.grid.set_items(self.cards)

    def _select(self, key):
        for c in self.cards:
            c.set_selected(c.key == key)
        entry = next((e for e in LEGEND if e[0] == key), None)
        if not entry:
            return
        _k, name, how = entry
        self.big.setPixmap(icons.glyph_pixmap(key, 120, glyph_color(key)))
        self.name.setText(name)
        self.how.setText(how)
        self._selected = key

    def _filter(self, text):
        q = text.strip().lower()
        items = [e for e in LEGEND if not q or q in e[1].lower() or q in e[2].lower()]
        self._build(items)
        self.empty.setVisible(not items)
        self.grid.setVisible(bool(items))
        sel = getattr(self, "_selected", None)
        if items:
            self._select(sel if any(e[0] == sel for e in items) else items[0][0])
