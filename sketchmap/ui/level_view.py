import math

from PyQt6.QtCore import Qt, QPointF, QRect, QRectF, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QPolygonF, QFont, QPixmap
from PyQt6.QtWidgets import QWidget

from .theme import P, FONT
from .qtutil import rgba_to_qimage, A_CENTER
from .. import elements as el
from .. import tileset as tileset_mod

MIN_S, MAX_S, FIT_MAX = 3.0, 90.0, 54.0

class _Col:
    _MAP = dict(wall="wall", boundary="boundary", board="board", grid="grid", hover="accent")

    def __contains__(self, k):
        return k in self._MAP

    def __getitem__(self, k):
        return QColor(P[self._MAP[k]])


COL = _Col()


def axis_line(a, b):
    (x1, y1), (x2, y2) = a, b
    if abs(x2 - x1) >= abs(y2 - y1):
        return [(x, y1) for x in range(min(x1, x2), max(x1, x2) + 1)]
    return [(x1, y) for y in range(min(y1, y2), max(y1, y2) + 1)]


def line_cells(a, b):
    (x0, y0), (x1, y1) = a, b
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    err, out = dx + dy, []
    while True:
        out.append((x0, y0))
        if (x0, y0) == (x1, y1):
            return out
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


class LevelView(QWidget):
    edited = pyqtSignal()
    hovered = pyqtSignal(str)
    zoomed = pyqtSignal(float)

    def __init__(self, editable=False, navigable=False, parent=None):
        super().__init__(parent)
        self.editable, self.navigable = editable, navigable
        self.model = None
        self.overlay = None
        self.overlay_z = 24
        self.show_overlay = False
        self.overlay_opacity = 1.0
        self.highlight = []
        self.sheet = QPixmap()
        self.sprites = {}
        self.show_tiles = False
        self.tool = "wall"
        self.facing = 0
        self.paint = []
        self.pan_mode = False
        self.s, self.ox, self.oy = 20.0, 0.0, 0.0
        self.user_view = False
        self.hover = None
        self.drag = None
        self._pan_from = None
        self._space = False
        self.undo_stack, self.redo_stack = [], []
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(120, 120)

    def set_model(self, model, overlay_rgba=None, overlay_z=24):
        self.model = model
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.hover = self.drag = None
        self.highlight = []
        self.set_overlay(overlay_rgba, overlay_z)
        self.fit()
        self.edited.emit()

    def set_overlay(self, rgba, z=24):
        self.overlay = rgba_to_qimage(rgba) if rgba is not None else None
        self.overlay_z = z
        self.update()

    def set_highlight(self, tiles):
        self.highlight = list(tiles or [])
        self.update()

    def set_overlay_opacity(self, v):
        self.overlay_opacity = max(0.0, min(1.0, float(v)))
        self.update()

    def set_tileset(self, spec):
        spec = spec or tileset_mod.default_spec()
        self.sheet = QPixmap(spec.image_path)
        px = spec.tile_px
        self.sprites = {k: QRect(c * px, r * px, px, px) for k, (c, r) in tileset_mod.resolved(spec.tiles).items()}
        self.update()

    def set_show_tiles(self, on):
        self.show_tiles = bool(on)
        self.update()

    def _sprite(self, p, kind, x, y):
        p.drawPixmap(self._tile_rect(x, y), self.sheet, self.sprites[kind])

    def _tiles_ready(self):
        return self.show_tiles and not self.sheet.isNull() and bool(self.sprites)

    def set_show_overlay(self, on):
        self.show_overlay = bool(on)
        self.update()

    def _is_terrain_tool(self):
        return self.tool in el.TERRAIN

    def set_facing(self, facing):
        self.facing = facing % 4
        self.update()

    def set_tool(self, tool):
        self.tool = tool
        self.pan_mode = False
        self._update_cursor()

    def set_pan_mode(self, on):
        self.pan_mode = bool(on)
        self._update_cursor()

    def set_editable(self, on):
        self.editable = bool(on)
        self._update_cursor()
        self.update()

    def _update_cursor(self):
        if self.navigable and (self.pan_mode or self._space):
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        elif self.editable and self.navigable:
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.unsetCursor()

    def fit(self):
        if not self.model:
            return
        m = 22
        aw, ah = max(1, self.width() - 2 * m), max(1, self.height() - 2 * m)
        self.s = max(MIN_S, min(FIT_MAX, min(aw / self.model.width, ah / self.model.height)))
        self.ox = (self.width() - self.model.width * self.s) / 2
        self.oy = (self.height() - self.model.height * self.s) / 2
        self.user_view = False
        self.zoomed.emit(self.s)
        self.update()

    def zoom_by(self, f, anchor=None):
        if not self.model:
            return
        a = anchor or QPointF(self.width() / 2, self.height() / 2)
        ns = max(MIN_S, min(MAX_S, self.s * f))
        k = ns / self.s
        self.ox = a.x() - (a.x() - self.ox) * k
        self.oy = a.y() - (a.y() - self.oy) * k
        self.s = ns
        self.user_view = True
        self.zoomed.emit(ns)
        self.update()

    def _do(self, fn):
        snap, e0 = self.model.snapshot(), self.model.edits
        fn()
        if self.model.edits != e0:
            self.undo_stack.append(snap)
            self.redo_stack.clear()
            self.edited.emit()
        self.update()

    def undo(self):
        if self.undo_stack and self.model:
            self.redo_stack.append(self.model.snapshot())
            self.model.restore(self.undo_stack.pop())
            self.edited.emit()
            self.update()

    def redo(self):
        if self.redo_stack and self.model:
            self.undo_stack.append(self.model.snapshot())
            self.model.restore(self.redo_stack.pop())
            self.edited.emit()
            self.update()

    def tile_at(self, pos):
        return int(math.floor((pos.x() - self.ox) / self.s)), int(math.floor((pos.y() - self.oy) / self.s))

    def mousePressEvent(self, e):
        if not self.model or not self.navigable:
            return
        self.setFocus()
        b = e.button()
        if b == Qt.MouseButton.MiddleButton or (b == Qt.MouseButton.LeftButton and (self.pan_mode or self._space)):
            self._pan_from = (e.position(), self.ox, self.oy)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        if not self.editable:
            return
        t = self.tile_at(e.position())
        if b == Qt.MouseButton.RightButton:
            self._do(lambda: self.model.rotate_at(*t))
        elif b == Qt.MouseButton.LeftButton:
            self.drag = t
            self.paint = [t] if self._is_terrain_tool() else []

    def mouseMoveEvent(self, e):
        if not self.model or not self.navigable:
            return
        if self._pan_from is not None:
            p0, ox0, oy0 = self._pan_from
            self.ox = ox0 + (e.position().x() - p0.x())
            self.oy = oy0 + (e.position().y() - p0.y())
            self.user_view = True
            self.update()
            return
        prev, self.hover = self.hover, self.tile_at(e.position())
        x, y = self.hover
        if self.drag and self.paint and prev is not None:
            self.paint.extend(c for c in line_cells(prev, self.hover) if c not in self.paint)
        if self.model.inside(x, y):
            self.hovered.emit(f"tile ({x}, {y})  ·  {self.model.describe(x, y)}")
        else:
            self.hovered.emit("")
        self.update()

    def mouseReleaseEvent(self, e):
        if self._pan_from is not None and e.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton):
            self._pan_from = None
            self._update_cursor()
            return
        if not (self.model and self.editable and self.drag and e.button() == Qt.MouseButton.LeftButton):
            return
        a, b, self.drag = self.drag, self.tile_at(e.position()), None
        m, t = self.model, self.tool
        paint, self.paint = self.paint, []
        if t == "wall":
            self._do(lambda: m.add_segment("wall", a, b))
        elif t == "erase":
            self._do(lambda: [m.erase_tile(x, y) for x, y in axis_line(a, b)])
        elif t in el.TERRAIN:
            self._do(lambda: [m.place(t, x, y, self.facing) for x, y in (paint or [a])])
        elif t in el.OBJECTS:
            self._do(lambda: m.toggle(t, *a, self.facing))

    def mouseDoubleClickEvent(self, e):
        if self.navigable and self.pan_mode:
            self.fit()

    def wheelEvent(self, e):
        if not (self.model and self.navigable):
            e.ignore()
            return
        dy = e.angleDelta().y()
        if dy:
            self.zoom_by(1.15 ** (dy / 120.0), e.position())
        e.accept()

    def leaveEvent(self, e):
        self.hover = None
        self.hovered.emit("")
        self.update()
        super().leaveEvent(e)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Space and not e.isAutoRepeat():
            self._space = True
            self._update_cursor()
        elif e.key() == Qt.Key.Key_F and self.navigable:
            self.fit()
        else:
            super().keyPressEvent(e)

    def keyReleaseEvent(self, e):
        if e.key() == Qt.Key.Key_Space and not e.isAutoRepeat():
            self._space = False
            self._update_cursor()
        else:
            super().keyReleaseEvent(e)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if not self.user_view:
            self.fit()

    def _tile_rect(self, x, y):
        s = self.s
        x0, y0 = round(self.ox + x * s), round(self.oy + y * s)
        x1, y1 = round(self.ox + (x + 1) * s), round(self.oy + (y + 1) * s)
        return QRect(x0, y0, max(1, x1 - x0), max(1, y1 - y0))

    def paintEvent(self, e):
        m = self.model
        if not m:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        s = self.s
        board = QRectF(self.ox, self.oy, m.width * s, m.height * s)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(COL["board"])
        p.drawRoundedRect(board.adjusted(-6, -6, 6, 6), 10, 10)
        tiles_on = self._tiles_ready()
        if tiles_on:
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
            for y in range(m.height):
                for x in range(m.width):
                    self._sprite(p, "floor", x, y)
        if self.show_overlay and self.overlay is not None:
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            p.setOpacity(self.overlay_opacity)
            p.drawImage(board, self.overlay)
            p.setOpacity(1.0)
        if s >= 9:
            p.setPen(QPen(COL["grid"], 1))
            for x in range(m.width + 1):
                gx = round(self.ox + x * s)
                p.drawLine(gx, round(self.oy), gx, round(self.oy + m.height * s))
            for y in range(m.height + 1):
                gy = round(self.oy + y * s)
                p.drawLine(round(self.ox), gy, round(self.ox + m.width * s), gy)

        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        p.setPen(Qt.PenStyle.NoPen)
        for (x, y), (k, f) in m.terrain.items():
            self._draw_terrain(p, x, y, k, f, tiles_on)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(Qt.PenStyle.NoPen)

        if self.highlight:
            p.setBrush(QColor(229, 62, 62, 110))
            for x, y in self.highlight:
                p.drawRect(self._tile_rect(x, y))

        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        ordered = sorted(m.segments, key=lambda q: q.kind == "boundary")
        for seg in ordered:
            p.setBrush(COL[seg.kind] if seg.kind in COL else COL["wall"])
            for x, y in seg.tiles():
                if tiles_on:
                    self._sprite(p, seg.kind if seg.kind in self.sprites else "wall", x, y)
                else:
                    p.drawRect(self._tile_rect(x, y))
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        for (x, y), (k, f) in m.objects.items():
            self._draw_object(p, x, y, k, f)

        if self.editable and self.navigable and not (self.pan_mode or self._space):
            if self.drag and self.paint:
                c = QColor(el.BY_KEY[self.tool].color)
                c.setAlpha(110)
                p.setBrush(c)
                p.setPen(Qt.PenStyle.NoPen)
                for x, y in self.paint:
                    p.drawRect(self._tile_rect(x, y))
            elif self.drag and self.hover and self.tool in ("wall", "erase"):
                c = QColor(COL["hover"])
                c.setAlpha(80)
                p.setBrush(c)
                p.setPen(QPen(COL["hover"], 1.5))
                for x, y in axis_line(self.drag, self.hover):
                    p.drawRect(self._tile_rect(x, y))
            elif self.hover and m.inside(*self.hover):
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(COL["hover"], 2))
                p.drawRoundedRect(QRectF(self._tile_rect(*self.hover)).adjusted(1, 1, -1, -1), 3, 3)
        p.end()

    def _arrow(self, p, rect, facing, color, size=0.34):
        c = QRectF(rect).center()
        r = rect.width() * size
        dx, dy = el.DIR_VEC[el.DIRS[facing % 4]]
        nx, ny = -dy, dx
        pts = QPolygonF([QPointF(c.x() + dx * r, c.y() + dy * r),
                         QPointF(c.x() - dx * r * 0.8 + nx * r * 0.9, c.y() - dy * r * 0.8 + ny * r * 0.9),
                         QPointF(c.x() - dx * r * 0.8 - nx * r * 0.9, c.y() - dy * r * 0.8 - ny * r * 0.9)])
        p.setBrush(color)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPolygon(pts)

    def _label(self, p, rect, text, color):
        f = QFont(FONT["ui"])
        f.setPixelSize(max(8, int(self.s * 0.36)))
        f.setBold(True)
        p.setFont(f)
        p.setPen(color)
        p.drawText(QRectF(rect), A_CENTER, text)

    def _draw_terrain(self, p, x, y, k, f, tiles_on):
        r = self._tile_rect(x, y)
        e = el.BY_KEY[k]
        if tiles_on and k in self.sprites:
            if k == "conveyor" and f:
                p.save()
                p.translate(QRectF(r).center())
                p.rotate(90 * f)
                p.drawPixmap(QRect(-r.width() // 2, -r.height() // 2, r.width(), r.height()), self.sheet, self.sprites[k])
                p.restore()
            else:
                self._sprite(p, k, x, y)
            return
        c = QColor(e.color)
        c.setAlpha(170)
        p.setBrush(c)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(r)
        if k == "conveyor":
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            self._arrow(p, r, f, QColor(255, 255, 255, 235))
            p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        elif self.s >= 16:
            self._label(p, r, e.code, QColor(255, 255, 255, 220))
            p.setPen(Qt.PenStyle.NoPen)

    def _draw_object(self, p, x, y, k, f):
        e = el.BY_KEY[k]
        s = self.s
        r = QRectF(self._tile_rect(x, y)).adjusted(s * 0.1, s * 0.1, -s * 0.1, -s * 0.1)
        col = QColor(e.color)
        p.setBrush(col)
        p.setPen(QPen(col.darker(160), 1.2))
        if k == "arrow_start":
            p.drawEllipse(r)
            self._arrow(p, r, f, QColor("#1B1B1F"), 0.3)
            return
        p.drawRoundedRect(r, s * 0.16, s * 0.16)
        if s >= 14:
            self._label(p, r, e.code, QColor("#1B1B1F"))
        else:
            p.setPen(Qt.PenStyle.NoPen)
