from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QWidget, QFrame, QLabel, QVBoxLayout, QHBoxLayout, QStackedWidget, QProgressBar

from .. import icons
from ..theme import P, FONT
from ..widgets import PageHeader, Card, PixView, ExportButton, IconButton, NavButton, ThemedIcon, make_button, divider
from ..level_view import LevelView
from ..qtutil import repolish


class AttachPanel(QFrame):
    import_clicked = pyqtSignal()
    open_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("panel")
        self.setProperty("dragging", False)
        self.setFixedWidth(340)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 26, 28, 20)
        lay.setSpacing(0)

        head = QHBoxLayout()
        head.setSpacing(10)
        ic = ThemedIcon("paperclip", 22)
        head.addWidget(ic)
        t = QLabel("Attach File")
        t.setObjectName("panelTitle")
        head.addWidget(t)
        head.addStretch(1)
        lay.addLayout(head)
        lay.addSpacing(16)
        lay.addWidget(divider())

        lay.addStretch(2)
        cam = IconButton("camera", 54, "Choose a sketch photo", variant="round", norm="text", hover="accent_text")
        cam.setFixedSize(116, 116)
        cam.setStyleSheet("QPushButton { border-radius: 30px; }")
        cam.clicked.connect(self.import_clicked.emit)
        lay.addWidget(cam, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addStretch(2)

        lay.addWidget(divider())
        lay.addSpacing(16)
        drag = QLabel("or drag and drop the file here")
        lay.addWidget(drag)
        note = QLabel("PNG, JPG or JPEG sketch photos.\nOpen File loads a saved level (.json).")
        note.setObjectName("faint")
        note.setWordWrap(True)
        lay.addSpacing(6)
        lay.addWidget(note)
        lay.addStretch(3)

        lay.addWidget(divider())
        lay.addSpacing(8)
        row = QHBoxLayout()
        row.setSpacing(8)
        for name, label, sig in (("import", "Import File", self.import_clicked), ("open", "Open File", self.open_clicked)):
            b = NavButton(name, label)
            b.setCheckable(False)
            b.setFixedHeight(80)
            b.clicked.connect(sig.emit)
            row.addWidget(b, 1)
        lay.addLayout(row)
        lay.addSpacing(8)
        lay.addWidget(divider())

    def set_dragging(self, on):
        self.setProperty("dragging", bool(on))
        repolish(self)


class HomePage(QWidget):
    edit_clicked = pyqtSignal()
    export_chosen = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        main = QWidget()
        mv = QVBoxLayout(main)
        mv.setContentsMargins(32, 24, 32, 28)
        mv.setSpacing(22)
        mv.addWidget(PageHeader())
        self.stack = QStackedWidget()
        mv.addWidget(self.stack, 1)
        lay.addWidget(main, 1)
        self.panel = AttachPanel()
        lay.addWidget(self.panel)

        e = QWidget()
        ev = QVBoxLayout(e)
        ev.addStretch(1)
        t = QLabel("No current work. Start exploring")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        f = QFont(FONT["pixel"])
        f.setPixelSize(20)
        t.setFont(f)
        ev.addWidget(t)
        ev.addSpacing(10)
        ev.addStretch(1)
        self.stack.addWidget(e)

        l = QWidget()
        lv = QVBoxLayout(l)
        lv.addStretch(1)
        self.loading_title = QLabel("Digitalizing sketch…")
        self.loading_title.setObjectName("emptyTitle")
        self.loading_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lv.addWidget(self.loading_title)
        self.loading_name = QLabel("")
        self.loading_name.setObjectName("faint")
        self.loading_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lv.addWidget(self.loading_name)
        lv.addSpacing(14)
        self.loading_bar = QProgressBar()
        self.loading_bar.setRange(0, 100)
        self.loading_bar.setValue(0)
        self.loading_bar.setTextVisible(False)
        self.loading_bar.setFixedWidth(280)
        lv.addWidget(self.loading_bar, 0, Qt.AlignmentFlag.AlignHCenter)
        lv.addSpacing(8)
        self.loading_status = QLabel("")
        self.loading_status.setObjectName("faint")
        self.loading_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lv.addWidget(self.loading_status)
        lv.addStretch(1)
        self.stack.addWidget(l)

        pv = QWidget()
        v = QVBoxLayout(pv)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(18)
        row = QHBoxLayout()
        row.setSpacing(10)
        tb = QVBoxLayout()
        tb.setSpacing(2)
        title = QLabel("Preview")
        title.setObjectName("pageTitle")
        self.subtitle = QLabel("")
        self.subtitle.setObjectName("faint")
        tb.addWidget(title)
        tb.addWidget(self.subtitle)
        row.addLayout(tb)
        row.addStretch(1)
        self.export_btn = ExportButton()
        self.export_btn.chosen.connect(self.export_chosen.emit)
        row.addWidget(self.export_btn)
        self.edit_btn = make_button("Edit", "edit", tooltip="Open the level editor")
        self.edit_btn.clicked.connect(self.edit_clicked.emit)
        row.addWidget(self.edit_btn)
        v.addLayout(row)

        cards = QHBoxLayout()
        cards.setSpacing(20)
        self.input_view = PixView(radius=12)
        self.level_view = LevelView(editable=False, navigable=False)
        cards.addWidget(self._card("Input Sketch", self.input_view))
        cards.addWidget(self._card("Digitalized Level Preview", self.level_view))
        v.addLayout(cards, 1)
        self.stack.addWidget(pv)

    def _card(self, title, content):
        c = Card()
        cv = QVBoxLayout(c)
        cv.setContentsMargins(18, 16, 18, 18)
        cv.setSpacing(12)
        t = QLabel(title)
        t.setObjectName("cardTitle")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cv.addWidget(t)
        inset = QFrame()
        inset.setObjectName("inset")
        iv = QVBoxLayout(inset)
        iv.setContentsMargins(6, 6, 6, 6)
        iv.addWidget(content)
        cv.addWidget(inset, 1)
        return c

    def show_empty(self):
        self.stack.setCurrentIndex(0)

    def set_progress(self, pct, text):
        self.loading_bar.setValue(pct)
        self.loading_status.setText(f"{pct}%  -  {text}")

    def show_loading(self, name):
        self.loading_name.setText(name)
        self.loading_bar.setValue(0)
        self.loading_status.setText("Starting...")
        self.stack.setCurrentIndex(1)

    def show_preview(self, input_pixmap, model, overlay_rgba, subtitle):
        if input_pixmap is not None:
            self.input_view.set_pixmap(input_pixmap)
        else:
            self.input_view.set_pixmap(None)
            self.input_view.set_placeholder("image", "No source sketch: this level was opened from a .json file")
        self.level_view.set_model(model, overlay_rgba)
        self.subtitle.setText(subtitle)
        self.stack.setCurrentIndex(2)

    def set_subtitle(self, text):
        self.subtitle.setText(text)

    def has_work(self):
        return self.stack.currentIndex() == 2
