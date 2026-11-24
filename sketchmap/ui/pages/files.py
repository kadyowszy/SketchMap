import os
import time

from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QCursor, QDesktopServices
from PyQt6.QtWidgets import (QWidget, QFrame, QLabel, QVBoxLayout, QHBoxLayout, QLineEdit, QMenu, QMessageBox)

from .. import icons
from ..theme import P, bus
from ..widgets import (PageHeader, Card, ReflowGrid, PixView, IconButton, ElidedLabel, NavButton, ThemedIcon, divider)
from ..thumbs import thumbnail


def _thumb_or_placeholder(view, entry):
    path, kind = entry["path"], entry.get("kind")
    pm = thumbnail(path) if (kind == "sketch" and os.path.isfile(path)) else None
    if pm is not None:
        view.set_pixmap(pm)
    else:
        view.set_pixmap(None)
        if not os.path.isfile(path):
            view.set_placeholder("file", "File not found")
        elif kind == "level":
            view.set_placeholder("file", "Level data (.json)")
        else:
            view.set_placeholder("image", "")


class FileCard(Card):
    star_clicked = pyqtSignal(str)
    menu_requested = pyqtSignal(str, str)

    def __init__(self, entry):
        super().__init__(hoverable=True)
        self.path = entry["path"]
        v = QVBoxLayout(self)
        v.setContentsMargins(10, 8, 10, 12)
        v.setSpacing(2)
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        self.star = IconButton("star_fill" if entry.get("favorite") else "star", 18, "Favourite", variant="round",
                               norm="muted", hover="accent_text", checked="accent_text")
        self.star.setCheckable(True)
        self.star.setChecked(bool(entry.get("favorite")))
        self.star.setFixedSize(34, 34)
        self.star.toggled.connect(lambda on: self.star.set_icon_name("star_fill" if on else "star"))
        self.star.clicked.connect(lambda: self.star_clicked.emit(self.path))
        top.addWidget(self.star)
        top.addStretch(1)
        kb = IconButton("kebab", 18, "More", variant="round")
        kb.setFixedSize(34, 34)
        kb.clicked.connect(self._menu)
        top.addWidget(kb)
        v.addLayout(top)
        self.thumb = PixView(radius=10)
        self.thumb.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        _thumb_or_placeholder(self.thumb, entry)
        v.addWidget(self.thumb, 1)
        self.name = ElidedLabel(os.path.basename(self.path))
        self.name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        v.addWidget(self.name)

    def _menu(self):
        m = QMenu(self)
        for label, act in (("Open", "open"), ("Edit", "edit"), ("Reveal in folder", "reveal"), (None, None), ("Delete", "delete")):
            if label is None:
                m.addSeparator()
            else:
                a = m.addAction(label)
                a.triggered.connect(lambda _=False, k=act: self.menu_requested.emit(k, self.path))
        m.exec(QCursor.pos())


class FilesPage(QWidget):
    open_requested = pyqtSignal(str)
    edit_requested = pyqtSignal(str)

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.selected = None
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        main = QWidget()
        mv = QVBoxLayout(main)
        mv.setContentsMargins(32, 24, 32, 28)
        mv.setSpacing(18)
        self.header = PageHeader()
        self.search_btn = IconButton("search", 20, "Search files", variant="round")
        self.search_btn.setCheckable(True)
        self.search_btn.setFixedSize(38, 38)
        self.star_btn = IconButton("star", 20, "Show favourites only", variant="round", checked="accent_text")
        self.star_btn.setCheckable(True)
        self.star_btn.setFixedSize(38, 38)
        self.header.add_right(self.search_btn)
        self.header.add_right(self.star_btn)
        mv.addWidget(self.header)

        self.query = QLineEdit()
        self.query.setPlaceholderText("Search by file name")
        self.query.setClearButtonEnabled(True)
        self.query.hide()
        mv.addWidget(self.query)

        row = QHBoxLayout()
        row.setSpacing(12)
        chip = ThemedIcon("files", 20)
        chip.setObjectName("chip")
        chip.setFixedSize(46, 36)
        chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(chip)
        self.title = QLabel("Recent Files")
        self.title.setObjectName("h2")
        row.addWidget(self.title)
        self.count = QLabel("")
        self.count.setObjectName("faint")
        row.addWidget(self.count)
        row.addStretch(1)
        mv.addLayout(row)

        self.grid = ReflowGrid(min_card_w=260, card_h=232)
        mv.addWidget(self.grid, 1)
        self.empty = QLabel("")
        self.empty.setObjectName("muted")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mv.addWidget(self.empty, 1)
        lay.addWidget(main, 1)

        panel = QFrame()
        panel.setObjectName("panel")
        panel.setFixedWidth(340)
        pv = QVBoxLayout(panel)
        pv.setContentsMargins(28, 26, 28, 20)
        pv.setSpacing(0)
        head = QHBoxLayout()
        head.setSpacing(10)
        ic = ThemedIcon("files", 22)
        head.addWidget(ic)
        t = QLabel("File Preview")
        t.setObjectName("panelTitle")
        head.addWidget(t)
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
        self.p_name = ElidedLabel("Select a file")
        self.p_name.setObjectName("h2")
        pv.addWidget(self.p_name)
        pv.addSpacing(8)
        self.p_meta = QLabel("Pick a file on the left to preview it here.")
        self.p_meta.setObjectName("muted")
        self.p_meta.setWordWrap(True)
        pv.addWidget(self.p_meta)
        pv.addStretch(1)
        pv.addWidget(divider())
        pv.addSpacing(8)
        brow = QHBoxLayout()
        brow.setSpacing(8)
        self.edit_tile = NavButton("edit", "Edit")
        self.del_tile = NavButton("trash", "Delete")
        for b in (self.edit_tile, self.del_tile):
            b.setCheckable(False)
            b.setFixedHeight(80)
            brow.addWidget(b, 1)
        self.edit_tile.clicked.connect(lambda: self.selected and self.edit_requested.emit(self.selected))
        self.del_tile.clicked.connect(lambda: self.selected and self._delete(self.selected))
        pv.addLayout(brow)
        pv.addSpacing(8)
        pv.addWidget(divider())
        lay.addWidget(panel)

        self.search_btn.toggled.connect(self._toggle_search)
        self.star_btn.toggled.connect(lambda on: (self.star_btn.set_icon_name("star_fill" if on else "star"), self.refresh()))
        self.query.textChanged.connect(lambda _: self.refresh())
        self._show_selection()

    def _toggle_search(self, on):
        self.query.setVisible(on)
        if on:
            self.query.setFocus()
        else:
            self.query.clear()

    def refresh(self):
        favs = self.star_btn.isChecked()
        items = self.store.items(favorites_only=favs, query=self.query.text())
        self.title.setText("Favourites" if favs else "Recent Files")
        self.count.setText(f"{len(items)} file{'s' if len(items) != 1 else ''}")
        cards = []
        for e in items:
            c = FileCard(e)
            c.clicked.connect(lambda p=e["path"]: self._select(p))
            c.activated.connect(lambda p=e["path"]: self.open_requested.emit(p))
            c.star_clicked.connect(self._favorite)
            c.menu_requested.connect(self._menu_action)
            c.set_selected(e["path"] == self.selected)
            cards.append(c)
        self.grid.set_items(cards)
        self.grid.setVisible(bool(items))
        self.empty.setVisible(not items)
        if not items:
            if favs:
                self.empty.setText("No favourites yet. Tap the star on a file to pin it here.")
            elif self.query.text().strip():
                self.empty.setText("No file matches your search.")
            else:
                self.empty.setText("No files yet. Import a sketch on the Home page and it will show up here.")
        if self.selected and not self.store.find(self.selected):
            self.selected = None
        self._show_selection()

    def _select(self, path):
        self.selected = path
        for w in self.grid.widgets():
            if isinstance(w, FileCard):
                w.set_selected(w.path == path)
        self._show_selection()

    def _show_selection(self):
        e = self.store.find(self.selected) if self.selected else None
        for b in (self.edit_tile, self.del_tile):
            b.setEnabled(e is not None)
        if not e:
            self.p_name.set_full_text("Select a file")
            self.p_meta.setText("Pick a file on the left to preview it here.")
            self.preview.set_pixmap(None)
            self.preview.set_placeholder("file", "")
            return
        _thumb_or_placeholder(self.preview, e)
        path = e["path"]
        self.p_name.set_full_text(os.path.basename(path))
        lines = ["Sketch photo" if e.get("kind") == "sketch" else "Level file"]
        if os.path.isfile(path):
            lines.append(f"{os.path.getsize(path) / 1024:.0f} KB")
        else:
            lines.append("File not found on disk")
        lines.append("Last opened " + time.strftime("%d %b %Y, %H:%M", time.localtime(e.get("opened", 0))))
        lines.append(os.path.dirname(path))
        self.p_meta.setText("\n".join(lines))

    def _favorite(self, path):
        self.store.toggle_favorite(path)
        if self.star_btn.isChecked():
            self.refresh()

    def _menu_action(self, action, path):
        if action == "open":
            self.open_requested.emit(path)
        elif action == "edit":
            self.edit_requested.emit(path)
        elif action == "reveal":
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(path)))
        elif action == "delete":
            self._delete(path)

    def _delete(self, path):
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Delete from Files")
        box.setText(f"Delete \u201c{os.path.basename(path)}\u201d from your files?")
        box.setInformativeText("This only removes it from SketchMap's list. The original file on your disk is kept.")
        yes = box.addButton("Delete", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() == yes:
            self.store.remove(path)
            if self.selected == path:
                self.selected = None
            self.refresh()
