from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import cv2
import numpy as np
from PyQt6.QtCore import Qt, QRect, QPoint, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QKeySequence, QPainter, QPen, QPixmap, QShortcut, QUndoCommand, QUndoStack
from PyQt6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QHBoxLayout, QLabel, QPushButton, QSlider,
                             QVBoxLayout, QWidget)


@dataclass(frozen=True)
class TileDef:
    tile_id: int
    name: str
    rgba: Tuple[int, int, int, int]
    shortcut: str = ""


DEFAULT_TILE_PALETTE: Dict[int, TileDef] = {
    0: TileDef(0, "Void", (20, 22, 26, 90), "1"),
    1: TileDef(1, "Floor", (72, 187, 120, 175), "2"),
    2: TileDef(2, "Wall", (229, 62, 62, 220), "3"),
    3: TileDef(3, "Door", (236, 201, 75, 220), "4"),
    4: TileDef(4, "Spawn", (66, 153, 225, 235), "5"),
}

SKETCHMAP_TILE_PALETTE: Dict[int, TileDef] = {
    0: TileDef(0, "Floor", (72, 187, 120, 60), "1"),
    1: TileDef(1, "Wall", (120, 124, 140, 220), "2"),
    2: TileDef(2, "Breakable", (240, 140, 60, 220), "3"),
    3: TileDef(3, "Boundary", (30, 30, 36, 235), "4"),
}


class PaintTilesCommand(QUndoCommand):

    def __init__(self, canvas, changes, description="Paint Tiles"):
        super().__init__(description)
        self._canvas, self._changes = canvas, changes

    def redo(self):
        self._canvas._apply_cell_map({rc: new for rc, (_, new) in self._changes.items()})

    def undo(self):
        self._canvas._apply_cell_map({rc: old for rc, (old, _) in self._changes.items()})


class TileOverlayCanvas(QWidget):
    grid_changed = pyqtSignal()

    def __init__(self, palette=None, parent=None, active_tile_id=2, erase_tile_id=1):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setMinimumSize(480, 420)
        self.palette = palette or DEFAULT_TILE_PALETTE
        self.undo_stack = QUndoStack(self)
        self._bg_pixmap: Optional[QPixmap] = None
        self._grid: Optional[np.ndarray] = None
        self._overlay_rgba: Optional[np.ndarray] = None
        self._overlay_qimage: Optional[QImage] = None
        self._overlay_alpha = 0.65
        self._show_grid_lines = True
        self._active_tile_id = active_tile_id
        self._erase_tile_id = erase_tile_id
        self._brush_size = 1
        self._is_painting = False
        self._paint_value = active_tile_id
        self._stroke_changes: Dict[Tuple[int, int], Tuple[int, int]] = {}
        self._hover_rc: Optional[Tuple[int, int]] = None
        self._lut = np.zeros((256, 4), dtype=np.uint8)
        for tid, tdef in self.palette.items():
            if 0 <= tid < 256:
                self._lut[tid] = tdef.rgba

    def set_data(self, straightened_bgr, grid):
        rgb = np.ascontiguousarray(cv2.cvtColor(straightened_bgr, cv2.COLOR_BGR2RGB))
        h, w, ch = rgb.shape
        self._bg_pixmap = QPixmap.fromImage(QImage(rgb.data, w, h, w * ch, QImage.Format.Format_RGB888).copy())
        self._grid = np.asarray(grid).astype(np.int32, copy=True)
        self.undo_stack.clear()
        self._rebuild_overlay_image()
        self.update()

    def get_grid(self):
        return None if self._grid is None else self._grid.copy()

    def set_overlay_alpha(self, alpha):
        self._overlay_alpha = float(np.clip(alpha, 0.0, 1.0))
        self.update()

    def set_show_grid_lines(self, show):
        self._show_grid_lines = show
        self.update()

    def set_active_tile(self, tile_id):
        self._active_tile_id = tile_id
        self.update()

    def set_brush_size(self, size):
        self._brush_size = max(1, min(7, int(size)))
        self.update()

    def _rebuild_overlay_image(self):
        if self._grid is None:
            self._overlay_rgba = self._overlay_qimage = None
            return
        rows, cols = self._grid.shape
        self._overlay_rgba = np.ascontiguousarray(self._lut[np.clip(self._grid, 0, 255)])
        self._overlay_qimage = QImage(self._overlay_rgba.data, cols, rows, cols * 4, QImage.Format.Format_RGBA8888)

    def _apply_cell_map(self, cell_values):
        if self._grid is None or not cell_values:
            return
        for (r, c), val in cell_values.items():
            self._grid[r, c] = val
        self._rebuild_overlay_image()
        self.update()
        self.grid_changed.emit()

    def _target_rect(self):
        if self._bg_pixmap is None or self._bg_pixmap.isNull():
            return QRect()
        sz = self._bg_pixmap.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
        return QRect((self.width() - sz.width()) // 2, (self.height() - sz.height()) // 2, sz.width(), sz.height())

    def _pos_to_cell(self, pos):
        if self._grid is None:
            return None
        rect = self._target_rect()
        if rect.width() <= 0 or rect.height() <= 0 or not rect.contains(pos):
            return None
        rows, cols = self._grid.shape
        col = min(cols - 1, max(0, int((pos.x() - rect.left()) / float(rect.width()) * cols)))
        row = min(rows - 1, max(0, int((pos.y() - rect.top()) / float(rect.height()) * rows)))
        return row, col

    def _brush_cells(self, center):
        if self._grid is None:
            return []
        rows, cols = self._grid.shape
        cr, cc = center
        neg, pos = (self._brush_size - 1) // 2, self._brush_size // 2
        return [(cr + dr, cc + dc) for dr in range(-neg, pos + 1) for dc in range(-neg, pos + 1)
                if 0 <= cr + dr < rows and 0 <= cc + dc < cols]

    def _paint_at(self, pos):
        center = self._pos_to_cell(pos)
        if self._grid is None or center is None:
            return
        dirty = False
        for r, c in self._brush_cells(center):
            cur = int(self._grid[r, c])
            if cur == self._paint_value:
                continue
            orig = self._stroke_changes.get((r, c), (cur, cur))[0]
            self._stroke_changes[(r, c)] = (orig, self._paint_value)
            self._grid[r, c] = self._paint_value
            dirty = True
        if dirty:
            self._rebuild_overlay_image()
            self.update()

    def mousePressEvent(self, event):
        if self._grid is None:
            return
        if event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
            self._is_painting = True
            self._paint_value = self._active_tile_id if event.button() == Qt.MouseButton.LeftButton else self._erase_tile_id
            self._stroke_changes.clear()
            self._paint_at(event.position().toPoint())

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()
        self._hover_rc = self._pos_to_cell(pos)
        if self._is_painting:
            self._paint_at(pos)
        else:
            self.update()

    def mouseReleaseEvent(self, event):
        if not self._is_painting or event.button() not in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
            return
        self._is_painting = False
        effective = {rc: ov for rc, ov in self._stroke_changes.items() if ov[0] != ov[1]}
        self._stroke_changes.clear()
        if effective:
            name = self.palette.get(self._paint_value, TileDef(self._paint_value, "Tile", (0, 0, 0, 0))).name
            self.undo_stack.push(PaintTilesCommand(self, effective, f"Paint {name} ({len(effective)})"))

    def leaveEvent(self, event):
        self._hover_rc = None
        self.update()

    def paintEvent(self, event):
        qp = QPainter(self)
        qp.fillRect(self.rect(), QColor(24, 26, 30))
        rect = self._target_rect()
        if rect.isEmpty() or self._bg_pixmap is None:
            return
        qp.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        qp.drawPixmap(rect, self._bg_pixmap)
        if self._overlay_qimage is not None and self._overlay_alpha > 0.001:
            qp.save()
            qp.setOpacity(self._overlay_alpha)
            qp.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
            qp.drawImage(rect, self._overlay_qimage)
            qp.restore()
        if self._grid is None:
            return
        rows, cols = self._grid.shape
        cw, ch = rect.width() / float(cols), rect.height() / float(rows)
        if self._show_grid_lines and cw >= 4.0 and ch >= 4.0:
            qp.setPen(QPen(QColor(255, 255, 255, int(110 * max(0.25, self._overlay_alpha))), 1))
            for c in range(1, cols):
                x = int(round(rect.left() + c * cw))
                qp.drawLine(x, rect.top(), x, rect.bottom())
            for r in range(1, rows):
                y = int(round(rect.top() + r * ch))
                qp.drawLine(rect.left(), y, rect.right(), y)
        if self._hover_rc is not None:
            qp.setPen(QPen(QColor(255, 255, 255, 220), 2))
            qp.setBrush(Qt.BrushStyle.NoBrush)
            for r, c in self._brush_cells(self._hover_rc):
                qp.drawRect(int(round(rect.left() + c * cw)), int(round(rect.top() + r * ch)),
                            max(1, int(round(cw))), max(1, int(round(ch))))


class LevelOverlayEditor(QWidget):

    def __init__(self, palette=None, parent=None, active_tile_id=2, erase_tile_id=1):
        super().__init__(parent)
        self.palette = palette or DEFAULT_TILE_PALETTE
        self.canvas = TileOverlayCanvas(self.palette, self, active_tile_id, erase_tile_id)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        bar = QHBoxLayout()

        self.tile_group = QButtonGroup(self)
        self.tile_group.setExclusive(True)
        for tid, tdef in self.palette.items():
            btn = QPushButton(f"{tdef.name} ({tdef.shortcut})" if tdef.shortcut else tdef.name)
            btn.setCheckable(True)
            r, g, b, _ = tdef.rgba
            btn.setStyleSheet(f"QPushButton {{ border-left: 6px solid rgb({r},{g},{b}); padding: 4px 10px; }}"
                              f"QPushButton:checked {{ font-weight: bold; background-color: rgba({r},{g},{b},70); }}")
            btn.setChecked(tid == active_tile_id)
            self.tile_group.addButton(btn, tid)
            bar.addWidget(btn)
            if tdef.shortcut:
                sc = QShortcut(QKeySequence(tdef.shortcut), self)
                sc.activated.connect(lambda b=btn, t=tid: (b.setChecked(True), self.canvas.set_active_tile(t)))
        self.tile_group.idClicked.connect(self.canvas.set_active_tile)

        bar.addSpacing(12)
        bar.addWidget(QLabel("Brush:"))
        self.cmb_brush = QComboBox()
        for n in (1, 2, 3):
            self.cmb_brush.addItem(f"{n}×{n}", n)
        self.cmb_brush.currentIndexChanged.connect(lambda _: self.canvas.set_brush_size(self.cmb_brush.currentData()))
        bar.addWidget(self.cmb_brush)
        bar.addSpacing(12)

        self.btn_undo = QPushButton("Undo")
        self.btn_undo.setEnabled(False)
        self.btn_undo.clicked.connect(self.canvas.undo_stack.undo)
        self.canvas.undo_stack.canUndoChanged.connect(self.btn_undo.setEnabled)
        bar.addWidget(self.btn_undo)
        self.btn_redo = QPushButton("Redo")
        self.btn_redo.setEnabled(False)
        self.btn_redo.clicked.connect(self.canvas.undo_stack.redo)
        self.canvas.undo_stack.canRedoChanged.connect(self.btn_redo.setEnabled)
        bar.addWidget(self.btn_redo)
        QShortcut(QKeySequence.StandardKey.Undo, self).activated.connect(self.canvas.undo_stack.undo)
        QShortcut(QKeySequence.StandardKey.Redo, self).activated.connect(self.canvas.undo_stack.redo)

        bar.addStretch()
        bar.addWidget(QLabel("Overlay Opacity:"))
        self.slider_opacity = QSlider(Qt.Orientation.Horizontal)
        self.slider_opacity.setRange(0, 100)
        self.slider_opacity.setValue(65)
        self.slider_opacity.setFixedWidth(130)
        self.lbl_opacity = QLabel("65%")
        self.lbl_opacity.setFixedWidth(36)
        self.slider_opacity.valueChanged.connect(self._on_opacity_changed)
        bar.addWidget(self.slider_opacity)
        bar.addWidget(self.lbl_opacity)
        self.chk_grid = QCheckBox("Grid")
        self.chk_grid.setChecked(True)
        self.chk_grid.toggled.connect(self.canvas.set_show_grid_lines)
        bar.addWidget(self.chk_grid)

        root.addLayout(bar)
        root.addWidget(self.canvas, 1)

    def _on_opacity_changed(self, value):
        self.lbl_opacity.setText(f"{value}%")
        self.canvas.set_overlay_alpha(value / 100.0)
