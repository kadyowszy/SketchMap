from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QKeySequence, QPainter, QPixmap, QShortcut
from PyQt6.QtWidgets import QButtonGroup, QFrame, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from .. import elements as el
from .theme import P, col, bus

ARROWS = ("→", "↓", "←", "↑")
DRAW_TOOLS = (("wall", "Wall", "wall", "Wall: drag to draw a solid wall"),
              ("erase", "Erase", "faint", "Erase: drag across tiles to remove whatever is on them"))


def _chip(color):
    pm = QPixmap(18, 18)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    color = QColor(col(color))
    p.setBrush(color)
    p.setPen(color.darker(160))
    p.drawRoundedRect(1, 1, 16, 16, 4, 4)
    p.end()
    return QIcon(pm)


class ElementPalette(QFrame):
    tool_chosen = pyqtSignal(str)
    facing_changed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("palette")
        self.setFixedWidth(196)
        self._facing = 0
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll)
        inner = QWidget()
        inner.setObjectName("paletteInner")
        scroll.setWidget(inner)
        v = QVBoxLayout(inner)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(2)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons = {}
        self._chips = []
        bus.changed.connect(lambda: [b.setIcon(_chip(c)) for b, c in self._chips])

        def header(text):
            h = QLabel(text.upper())
            h.setObjectName("metaKey")
            h.setContentsMargins(6, 8, 0, 2)
            v.addWidget(h)

        def add(key, label, color, tip):
            b = QPushButton(label)
            b.setCheckable(True)
            b.setIcon(_chip(color))
            self._chips.append((b, color))
            b.setIconSize(QSize(18, 18))
            b.setToolTip(tip)
            b.setProperty("variant", "palette")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self.tool_chosen.emit(k))
            self.group.addButton(b)
            self.buttons[key] = b
            v.addWidget(b)

        header("Draw")
        for key, label, color, tip in DRAW_TOOLS:
            add(key, label, color, tip)
        self.facing_btn = QPushButton()
        self.facing_btn.setProperty("variant", "ghost")
        self.facing_btn.setToolTip("Direction for conveyors and the player start.  Press R to turn,\n"
                                   "or right-click a placed one to turn it.")
        self.facing_btn.clicked.connect(self.rotate)
        v.addWidget(self.facing_btn)
        for cat, title in el.CATEGORY_TITLES:
            header(title)
            for e in (x for x in el.ELEMENTS if x.category == cat):
                tip = f"{e.label}: {e.pen}"
                if not e.detected:
                    tip += "\n(not recognized from photos yet, place it by hand)"
                add(e.key, e.label, e.color, tip + ("  (click again to remove)" if cat != "terrain" else "  (drag to paint)"))
        v.addStretch(1)
        QShortcut(QKeySequence("R"), self, activated=self.rotate, context=Qt.ShortcutContext.WindowShortcut)
        self._sync_facing()

    def _sync_facing(self):
        self.facing_btn.setText(f"Facing  {ARROWS[self._facing]}   (R)")

    def rotate(self):
        self._facing = (self._facing + 1) % 4
        self._sync_facing()
        self.facing_changed.emit(self._facing)

    def set_tool(self, tool):
        b = self.buttons.get(tool)
        if b:
            b.setChecked(True)

    def clear_selection(self):
        self.group.setExclusive(False)
        for b in self.buttons.values():
            b.setChecked(False)
        self.group.setExclusive(True)
