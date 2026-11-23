from PyQt6.QtCore import Qt, QSize, QRect, QRectF, QPoint, QTimer, pyqtSignal, QEvent
from PyQt6.QtGui import QPainter, QColor, QFont, QPainterPath, QFontMetrics, QPixmap
from PyQt6.QtWidgets import (QFrame, QLabel, QPushButton, QHBoxLayout, QVBoxLayout, QWidget, QMenu,
                             QAbstractButton, QScrollArea, QGridLayout, QSizePolicy)

from . import icons
from .theme import P, FONT, col, bus
from .qtutil import repolish, A_HCENTER_TOP, A_CENTER, A_WRAP_CENTER


class IconButton(QPushButton):

    def __init__(self, name, size=20, tooltip="", text="", variant=None, norm=None, hover=None, checked=None, parent=None):
        super().__init__(text, parent)
        self._name, self._size = name, size
        self._norm = norm or "muted"
        self._hover_c = hover or "text"
        self._checked_c = checked or "text"
        self._hover = False
        if tooltip:
            self.setToolTip(tooltip)
        if variant:
            self.setProperty("variant", variant)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setIconSize(QSize(size, size))
        self.toggled.connect(lambda _=False: self._apply())
        bus.changed.connect(self._apply)
        self._apply()

    def set_icon_name(self, name):
        self._name = name
        self._apply()

    def refresh(self):
        self._apply()

    def set_colors(self, norm=None, hover=None, checked=None):
        self._norm = norm or self._norm
        self._hover_c = hover or self._hover_c
        self._checked_c = checked or self._checked_c
        self._apply()

    def _apply(self):
        if not self.isEnabled():
            c = P["faint"]
        elif self.isChecked():
            c = col(self._checked_c)
        elif self._hover:
            c = col(self._hover_c)
        else:
            c = col(self._norm)
        self.setIcon(icons.icon(self._name, self._size, c))

    def enterEvent(self, e):
        self._hover = True
        self._apply()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self._apply()
        super().leaveEvent(e)

    def changeEvent(self, e):
        if e.type() == QEvent.Type.EnabledChange:
            self._apply()
        super().changeEvent(e)


def make_button(text, icon_name=None, variant=None, tooltip="", size=18):
    if icon_name:
        b = IconButton(icon_name, size, tooltip, text, variant,
                       norm="accent_ink" if variant == "primary" else ("danger" if variant == "danger" else "muted"),
                       hover="accent_ink" if variant == "primary" else ("danger" if variant == "danger" else "text"),
                       checked="accent_ink" if variant == "primary" else "text")
    else:
        b = QPushButton(text)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        if tooltip:
            b.setToolTip(tooltip)
        if variant:
            b.setProperty("variant", variant)
    return b


class ToolButton(IconButton):

    def __init__(self, name, tooltip, checkable=False, size=22, box=44, parent=None):
        super().__init__(name, size, tooltip, "", "tool", norm="muted", hover="text", checked="accent_ink", parent=parent)
        self.setCheckable(checkable)
        self.setFixedSize(box, box)
        self._apply()


class NavButton(QPushButton):

    def __init__(self, name, label, parent=None):
        super().__init__(parent)
        self._name, self._label, self._hover = name, label, False
        self.setCheckable(True)
        self.setFixedHeight(78)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(label)

    def enterEvent(self, e):
        self._hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self.update()
        super().leaveEvent(e)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        on = self.isChecked()
        if on or self._hover:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(P["surface3"] if on else P["surface2"]))
            p.drawRoundedRect(QRectF(10, 4, w - 20, h - 8), 14, 14)
        color = P["text"] if (on or self._hover) else P["muted"]
        pm = icons.pixmap(self._name, 26, color, 1.7)
        p.drawPixmap((w - 26) // 2, 14, pm)
        f = QFont(FONT["ui"])
        f.setPixelSize(11)
        f.setWeight(QFont.Weight.DemiBold if on else QFont.Weight.Normal)
        p.setFont(f)
        p.setPen(QColor(color))
        p.drawText(QRect(0, 46, w, 18), A_HCENTER_TOP, self._label)
        if on:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(P["text"]))
            p.drawRoundedRect(QRectF(w - 3, 16, 3, h - 32), 1.5, 1.5)
        p.end()


class ToggleSwitch(QAbstractButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setFixedSize(38, 22)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def sizeHint(self):
        return QSize(38, 22)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        on, en = self.isChecked(), self.isEnabled()
        track = QColor(P["accent"] if on else P["border2"])
        if not en:
            track = QColor(P["surface3"])
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(QRectF(0, 1, 38, 20), 10, 10)
        p.setBrush(QColor(P["accent_ink"] if on and en else ("#FFFFFF" if en else P["faint"])))
        p.drawEllipse(QRectF(19 if on else 3, 4, 14, 14))
        p.end()


def divider():
    f = QFrame()
    f.setObjectName("divider")
    f.setFixedHeight(1)
    return f


class ThemedIcon(QLabel):

    def __init__(self, name, size=22, color="text", stroke=1.7, parent=None):
        super().__init__(parent)
        self._args = (name, size, color, stroke)
        bus.changed.connect(self._apply)
        self._apply()

    def _apply(self):
        name, size, color, stroke = self._args
        self.setPixmap(icons.pixmap(name, size, col(color), stroke))


class Wordmark(QLabel):
    def __init__(self, parent=None):
        super().__init__("SketchMap", parent)
        self.setObjectName("wordmark")
        f = QFont(FONT["pixel"])
        f.setPixelSize(20)
        f.setBold(True)
        self.setFont(f)


class PageHeader(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(14)
        self.row = QHBoxLayout()
        self.row.setContentsMargins(0, 0, 0, 0)
        self.row.setSpacing(6)
        self.row.addWidget(Wordmark())
        self.row.addStretch(1)
        v.addLayout(self.row)
        v.addWidget(divider())

    def add_right(self, w):
        self.row.addWidget(w)


class BetaBanner(QFrame):
    """Slim notice: BETA tag + what photo recognition currently covers."""

    def __init__(self, parent=None):
        super().__init__(parent)
        from .. import beta
        self.setObjectName("betaBanner")
        h = QHBoxLayout(self)
        h.setContentsMargins(14, 9, 14, 9)
        h.setSpacing(12)
        tag = QLabel("BETA")
        tag.setObjectName("betaTag")
        h.addWidget(tag, 0, Qt.AlignmentFlag.AlignVCenter)
        txt = QLabel(beta.banner_text())
        txt.setObjectName("betaText")
        txt.setWordWrap(True)
        txt.setToolTip(beta.plain_text())
        h.addWidget(txt, 1)


class Card(QFrame):
    clicked = pyqtSignal()
    activated = pyqtSignal()

    def __init__(self, hoverable=False, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setProperty("hoverable", hoverable)
        self.setProperty("selected", False)
        if hoverable:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hoverable = hoverable

    def set_selected(self, on):
        self.setProperty("selected", bool(on))
        repolish(self)

    def mousePressEvent(self, e):
        if self._hoverable and e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(e)

    def mouseDoubleClickEvent(self, e):
        if self._hoverable and e.button() == Qt.MouseButton.LeftButton:
            self.activated.emit()
        super().mouseDoubleClickEvent(e)


class ElidedLabel(QLabel):
    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self._full = ""
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.set_full_text(text)

    def set_full_text(self, t):
        self._full = t
        self.setToolTip(t)
        self._elide()

    def _elide(self):
        fm = QFontMetrics(self.font())
        QLabel.setText(self, fm.elidedText(self._full, Qt.TextElideMode.ElideMiddle, max(10, self.width() - 4)))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._elide()


class PixView(QWidget):

    def __init__(self, radius=12, bg=None, auto_height=False, parent=None):
        super().__init__(parent)
        self._pm = None
        self._radius = radius
        self._bg = bg
        self._auto_height = auto_height
        self._ph_icon, self._ph_text = "image", ""
        self._cache = (None, None)
        self.setMinimumSize(40, 40)

    def set_pixmap(self, pm):
        self._pm = pm
        self._cache = (None, None)
        self._fit_height()
        self.update()

    def set_placeholder(self, icon_name="image", text=""):
        self._ph_icon, self._ph_text = icon_name, text
        self.update()

    def _fit_height(self):
        if self._auto_height and self._pm is not None and not self._pm.isNull() and self.width() > 0:
            h = max(60, int(self.width() * self._pm.height() / self._pm.width()))
            if h != self.height():
                self.setFixedHeight(h)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._fit_height()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        r = QRectF(self.rect())
        path = QPainterPath()
        path.addRoundedRect(r, self._radius, self._radius)
        p.setClipPath(path)
        if self._bg:
            p.fillRect(r, QColor(col(self._bg)))
        if self._pm is not None and not self._pm.isNull():
            dpr = self.devicePixelRatioF()
            key = (self.width(), self.height(), dpr)
            if self._cache[0] != key:
                sc = self._pm.scaled(int(self.width() * dpr), int(self.height() * dpr),
                                     Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                sc.setDevicePixelRatio(dpr)
                self._cache = (key, sc)
            sc = self._cache[1]
            w, h = sc.width() / dpr, sc.height() / dpr
            p.drawPixmap(int((self.width() - w) / 2), int((self.height() - h) / 2), sc)
        else:
            ic = icons.pixmap(self._ph_icon, 34, P["faint"], 1.5)
            cx = self.width() // 2
            cy = self.height() // 2 - (12 if self._ph_text else 0)
            p.drawPixmap(cx - 17, cy - 17, ic)
            if self._ph_text:
                f = QFont(FONT["ui"])
                f.setPixelSize(12)
                p.setFont(f)
                p.setPen(QColor(P["faint"]))
                p.drawText(QRect(12, cy + 24, self.width() - 24, 40), A_WRAP_CENTER, self._ph_text)
        p.end()


class Toast(QFrame):
    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("toast")
        self.setProperty("kind", "info")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 10, 16, 10)
        self.label = QLabel("")
        lay.addWidget(self.label)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)
        self.hide()

    def show_message(self, text, kind="info", ms=3600):
        self.setProperty("kind", kind)
        repolish(self)
        self.label.setText(text)
        self.adjustSize()
        self.reposition()
        self.show()
        self.raise_()
        self._timer.start(ms)

    def reposition(self):
        par = self.parentWidget()
        if par is not None:
            self.move(max(8, (par.width() - self.width()) // 2), par.height() - self.height() - 28)


class ExportButton(QPushButton):
    chosen = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__("Export as", parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._menu = QMenu(self)
        self._menu.setToolTipsVisible(True)
        for fmt, tip in (("tscn", "Godot 4.3+ scene: Ground_Terrain, Walls_Boundary, Interactables and Markers layers, plus master_tileset.tres and prefabs/"),
                         ("json", "Portable level data: all 25 element types, tile matrix, scale and tileset")):
            a = self._menu.addAction("." + fmt)
            a.setToolTip(tip)
            a.triggered.connect(lambda _=False, f=fmt: self.chosen.emit(f))
        self._menu.addSeparator()
        for key, label, tip in (("tileset_customize", "Customize tileset…", "Pick the sprite sheet, tile size and which cell draws each tile type"),
                                ("tileset", "Load tileset file…", "Use your own sprite sheet (PNG/JPG) or a tileset .json manifest"),
                                ("tileset_template", "Save tileset template…", "Save a starter sprite sheet + manifest to repaint"),
                                ("tileset_reset", "Use built-in tileset", "Go back to the default placeholder tiles")):
            a = self._menu.addAction(label)
            a.setToolTip(tip)
            a.triggered.connect(lambda _=False, k=key: self.chosen.emit(k))
        self.clicked.connect(self._popup)
        self._hover = False
        bus.changed.connect(self._set_icon)
        self._set_icon()

    def _set_icon(self):
        self.setIcon(icons.icon("export", 18, P["text"] if self._hover and self.isEnabled() else P["muted"]))
        self.setIconSize(QSize(18, 18))

    def _popup(self):
        self._menu.exec(self.mapToGlobal(QPoint(0, self.height() + 6)))

    def enterEvent(self, e):
        self._hover = True
        self._set_icon()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self._set_icon()
        super().leaveEvent(e)


class ReflowGrid(QScrollArea):

    def __init__(self, min_card_w=250, card_h=214, gap=16, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._min_w, self._card_h, self._gap = min_card_w, card_h, gap
        self._widgets = []
        self._cols = 0
        self._rows = 0
        self._inner = QWidget()
        self._grid = QGridLayout(self._inner)
        self._grid.setContentsMargins(0, 0, 8, 8)
        self._grid.setSpacing(gap)
        self.setWidget(self._inner)

    def widgets(self):
        return list(self._widgets)

    def set_items(self, widgets):
        for w in self._widgets:
            self._grid.removeWidget(w)
            w.setParent(None)
            w.deleteLater()
        self._widgets = list(widgets)
        for w in self._widgets:
            w.setFixedHeight(self._card_h)
        self._cols = 0
        self._relayout()

    def _relayout(self):
        avail = max(1, self.viewport().width() - 8)
        cols = max(1, (avail + self._gap) // (self._min_w + self._gap))
        if cols == self._cols and self._widgets:
            return
        for c in range(max(self._cols, cols) + 1):
            self._grid.setColumnStretch(c, 0)
        self._grid.setRowStretch(self._rows, 0)
        for w in self._widgets:
            self._grid.removeWidget(w)
        self._cols = cols
        for i, w in enumerate(self._widgets):
            self._grid.addWidget(w, i // cols, i % cols)
            w.show()
        for c in range(cols):
            self._grid.setColumnStretch(c, 1)
        self._rows = (len(self._widgets) + cols - 1) // cols
        self._grid.setRowStretch(self._rows, 1)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._relayout()


class AspectPixmapLabel(QLabel):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._source = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.setScaledContents(False)

    def setPixmap(self, pixmap):
        self._source = pixmap
        self._rescale()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._rescale()

    def _rescale(self):
        if self._source is None or self._source.isNull():
            return
        QLabel.setPixmap(self, self._source.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                                   Qt.TransformationMode.SmoothTransformation))
