import copy
import os

from PyQt6.QtCore import Qt, QRect, QRectF, QPointF, pyqtSignal
from PyQt6.QtGui import QColor, QKeySequence, QPainter, QPen, QPixmap, QShortcut
from PyQt6.QtWidgets import (QButtonGroup, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
                             QMessageBox, QPushButton, QScrollArea, QSlider, QSpinBox, QVBoxLayout, QWidget, QGridLayout)

from .. import tileset

KIND_COLORS = {
    "floor": QColor(72, 187, 120),
    "wall": QColor(229, 62, 62),
    "boundary": QColor(160, 174, 192),
    "grass": QColor(130, 220, 90),
    "water": QColor(66, 153, 225),
    "lava": QColor(255, 110, 70),
    "ice": QColor(150, 230, 245),
    "mud": QColor(170, 120, 80),
    "conveyor": QColor(170, 130, 240),
}


ZOOM_MIN, ZOOM_MAX = 0.25, 16.0


class AtlasGridPicker(QWidget):
    cell_picked = pyqtSignal(int, int)
    zoom_wheel = pyqtSignal(float, QPointF)
    pan_by = pyqtSignal(int, int)

    def __init__(self, spec, parent=None):
        super().__init__(parent)
        self.spec = spec
        self.active_kind = tileset.KINDS[0]
        self.pixmap = QPixmap()
        self.zoom = 1.0
        self._pan_last = None
        self.set_spec(spec)

    def set_spec(self, spec):
        self.spec = spec
        self.pixmap = QPixmap(spec.image_path)
        self._resize_to_zoom()
        self.update()

    def set_zoom(self, z):
        self.zoom = max(ZOOM_MIN, min(ZOOM_MAX, float(z)))
        self._resize_to_zoom()
        self.update()

    def _resize_to_zoom(self):
        if not self.pixmap.isNull():
            self.setFixedSize(max(1, round(self.pixmap.width() * self.zoom)),
                              max(1, round(self.pixmap.height() * self.zoom)))

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            dy = event.angleDelta().y()
            if dy:
                self.zoom_wheel.emit(1.25 ** (dy / 120.0), event.position())
            event.accept()
        else:
            event.ignore()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self._pan_last = event.globalPosition()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        if event.button() != Qt.MouseButton.LeftButton or self.pixmap.isNull():
            return
        px = max(1, self.spec.tile_px)
        col = int(event.position().x() / self.zoom) // px
        row = int(event.position().y() / self.zoom) // px
        if (col + 1) * px <= self.pixmap.width() and (row + 1) * px <= self.pixmap.height():
            self.cell_picked.emit(col, row)

    def mouseMoveEvent(self, event):
        if self._pan_last is not None:
            d = event.globalPosition() - self._pan_last
            self._pan_last = event.globalPosition()
            self.pan_by.emit(int(d.x()), int(d.y()))

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self._pan_last = None
            self.unsetCursor()

    def paintEvent(self, event):
        qp = QPainter(self)
        qp.fillRect(self.rect(), QColor(24, 26, 30))
        if self.pixmap.isNull():
            return
        z = self.zoom
        w, h = self.pixmap.width(), self.pixmap.height()
        qp.drawPixmap(QRectF(0, 0, w * z, h * z), self.pixmap, QRectF(0, 0, w, h))
        px = max(1, self.spec.tile_px)
        cs = px * z

        if cs >= 4:
            qp.setPen(QPen(QColor(255, 255, 255, 55), 1))
            for x in range(0, w + 1, px):
                qp.drawLine(round(x * z), 0, round(x * z), round(h * z))
            for y in range(0, h + 1, px):
                qp.drawLine(0, round(y * z), round(w * z), round(y * z))

        stack = {}
        for kind, (col, row) in tileset.resolved(self.spec.tiles).items():
            c = KIND_COLORS.get(kind, QColor(255, 255, 255))
            n = stack.get((col, row), 0)
            stack[(col, row)] = n + 1
            x0, y0 = round(col * cs), round(row * cs)
            qp.setPen(QPen(c, 3 if kind == self.active_kind else 2))
            qp.drawRect(QRect(x0 + 1, y0 + 1, max(1, round(cs) - 2), max(1, round(cs) - 2)))
            if cs >= 24:
                ly = y0 + n * 14
                qp.fillRect(QRect(x0, ly, round(cs), 14), QColor(0, 0, 0, 175))
                qp.setPen(c)
                qp.drawText(x0 + 3, ly + 11, kind[:5].upper())


class TilesetCustomizerDialog(QDialog):
    def __init__(self, current_spec, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Customize tileset")
        self.resize(960, 720)
        self.spec = copy.deepcopy(current_spec)

        root = QVBoxLayout(self)

        top = QHBoxLayout()
        btn_load = QPushButton("Load image / JSON…")
        btn_load.clicked.connect(self._on_load_file)
        btn_reset = QPushButton("Reset to built-in")
        btn_reset.clicked.connect(self._on_reset)
        top.addWidget(btn_load)
        top.addWidget(btn_reset)
        top.addSpacing(12)
        top.addWidget(QLabel("Tile size (px):"))
        self.spin_px = QSpinBox()
        self.spin_px.setRange(1, 512)
        self.spin_px.setValue(self.spec.tile_px)
        self.spin_px.valueChanged.connect(self._on_px_changed)
        top.addWidget(self.spin_px)
        top.addSpacing(12)
        top.addWidget(QLabel("Godot res_dir:"))
        self.edit_res = QLineEdit(self.spec.res_dir)
        self.edit_res.setFixedWidth(170)
        self.edit_res.textChanged.connect(self._on_res_changed)
        top.addWidget(self.edit_res)
        top.addStretch(1)
        root.addLayout(top)

        self.sheet_lbl = QLabel()
        root.addWidget(self.sheet_lbl)

        root.addWidget(QLabel("Assign cell to:"))
        kind_bar = QGridLayout()
        self.kind_group = QButtonGroup(self)
        self.kind_buttons = {}
        for i, k in enumerate(tileset.KINDS):
            btn = QPushButton()
            btn.setCheckable(True)
            btn.setChecked(i == 0)
            self.kind_group.addButton(btn, i)
            self.kind_buttons[k] = btn
            kind_bar.addWidget(btn, i // 5, i % 5)
        self.kind_group.idClicked.connect(self._on_kind_selected)
        root.addLayout(kind_bar)

        hint = QLabel("Pick a tile type above, then click a cell in the sheet. Unassigned terrain reuses the floor cell. Interactables and markers are scenes, not tiles.")
        hint.setObjectName("faint")
        root.addWidget(hint)

        zoom_bar = QHBoxLayout()
        zoom_bar.addWidget(QLabel("Zoom:"))
        btn_out = QPushButton("−")
        btn_out.setFixedWidth(34)
        btn_out.setToolTip("Zoom out (Ctrl+−)")
        btn_out.clicked.connect(lambda: self._zoom_step(1 / 1.25))
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(0, 100)
        self.zoom_slider.setFixedWidth(220)
        self.zoom_slider.setToolTip("Drag to zoom the sheet in or out.")
        self.zoom_slider.valueChanged.connect(self._on_zoom_slider)
        btn_in = QPushButton("+")
        btn_in.setFixedWidth(34)
        btn_in.setToolTip("Zoom in (Ctrl++)")
        btn_in.clicked.connect(lambda: self._zoom_step(1.25))
        self.zoom_lbl = QLabel("100%")
        self.zoom_lbl.setMinimumWidth(48)
        btn_100 = QPushButton("100%")
        btn_100.setToolTip("Show the sheet at its real size (Ctrl+0)")
        btn_100.clicked.connect(lambda: self._set_zoom(1.0))
        btn_fit = QPushButton("Fit width")
        btn_fit.setToolTip("Shrink or grow the sheet so its full width fits the window")
        btn_fit.clicked.connect(self._fit_width)
        for w in (btn_out, self.zoom_slider, btn_in, self.zoom_lbl, btn_100, btn_fit):
            zoom_bar.addWidget(w)
        zoom_hint = QLabel("Ctrl + mouse wheel zooms. Hold the middle mouse button and drag to move around.")
        zoom_hint.setObjectName("faint")
        zoom_bar.addSpacing(10)
        zoom_bar.addWidget(zoom_hint)
        zoom_bar.addStretch(1)
        root.addLayout(zoom_bar)

        self.picker = AtlasGridPicker(self.spec)
        self.picker.cell_picked.connect(self._on_cell_picked)
        self.picker.zoom_wheel.connect(self._on_wheel_zoom)
        self.picker.pan_by.connect(self._on_pan)
        self.scroll = QScrollArea()
        self.scroll.setWidget(self.picker)
        root.addWidget(self.scroll, 1)
        QShortcut(QKeySequence("Ctrl++"), self, activated=lambda: self._zoom_step(1.25))
        QShortcut(QKeySequence("Ctrl+="), self, activated=lambda: self._zoom_step(1.25))
        QShortcut(QKeySequence("Ctrl+-"), self, activated=lambda: self._zoom_step(1 / 1.25))
        QShortcut(QKeySequence("Ctrl+0"), self, activated=lambda: self._set_zoom(1.0))

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self._refresh_labels()
        self._sync_zoom_controls()

    @staticmethod
    def _z_to_slider(z):
        import math
        return round(100 * math.log(z / ZOOM_MIN) / math.log(ZOOM_MAX / ZOOM_MIN))

    def _sync_zoom_controls(self):
        z = self.picker.zoom
        self.zoom_slider.blockSignals(True)
        self.zoom_slider.setValue(self._z_to_slider(z))
        self.zoom_slider.blockSignals(False)
        self.zoom_lbl.setText(f"{round(z * 100)}%")

    def _set_zoom(self, z, anchor=None):
        old = self.picker.zoom
        hb, vb = self.scroll.horizontalScrollBar(), self.scroll.verticalScrollBar()
        vp = self.scroll.viewport()
        if anchor is None:
            anchor = QPointF(hb.value() + vp.width() / 2, vb.value() + vp.height() / 2)
        self.picker.set_zoom(z)
        k = self.picker.zoom / old
        off_x, off_y = anchor.x() - hb.value(), anchor.y() - vb.value()
        hb.setValue(round(anchor.x() * k - off_x))
        vb.setValue(round(anchor.y() * k - off_y))
        self._sync_zoom_controls()

    def _zoom_step(self, factor):
        self._set_zoom(self.picker.zoom * factor)

    def _on_wheel_zoom(self, factor, pos):
        self._set_zoom(self.picker.zoom * factor, pos)

    def _on_zoom_slider(self, v):
        import math
        self._set_zoom(ZOOM_MIN * math.exp(math.log(ZOOM_MAX / ZOOM_MIN) * v / 100.0))

    def _fit_width(self):
        if not self.picker.pixmap.isNull():
            avail = self.scroll.viewport().width() - 2
            self._set_zoom(avail / self.picker.pixmap.width())
            self.scroll.horizontalScrollBar().setValue(0)

    def _on_pan(self, dx, dy):
        hb, vb = self.scroll.horizontalScrollBar(), self.scroll.verticalScrollBar()
        hb.setValue(hb.value() - dx)
        vb.setValue(vb.value() - dy)

    def _on_kind_selected(self, idx):
        self.picker.active_kind = tileset.KINDS[idx]
        self.picker.update()

    def _on_cell_picked(self, col, row):
        self.spec.tiles[self.picker.active_kind] = (col, row)
        self._refresh_labels()
        self.picker.update()

    def _on_px_changed(self, val):
        self.spec.tile_px = val
        self.picker.update()

    def _on_res_changed(self, text):
        text = text.strip()
        self.spec.res_dir = text if text.startswith("res://") else "res://" + text

    def _adopt(self, spec):
        self.spec = spec
        self.spin_px.setValue(spec.tile_px)
        self.edit_res.setText(spec.res_dir)
        self.picker.set_spec(spec)
        self._refresh_labels()
        self._fit_width() if (self.picker.pixmap.width() > self.scroll.viewport().width()) else self._set_zoom(1.0)

    def _on_load_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select tileset image or manifest", "",
                                              "Tilesets (*.png *.jpg *.jpeg *.json)")
        if not path:
            return
        try:
            self._adopt(tileset.load_tileset(path))
        except ValueError as ex:
            QMessageBox.warning(self, "Invalid tileset", str(ex))

    def _on_reset(self):
        self._adopt(tileset.default_spec())

    def _refresh_labels(self):
        res = tileset.resolved(self.spec.tiles)
        for k, btn in self.kind_buttons.items():
            col, row = res[k]
            btn.setText(f"{k.capitalize()} [{col}, {row}]")
        self.sheet_lbl.setText(f"Sheet: {os.path.basename(self.spec.image_path)}")

    def _on_accept(self):
        try:
            tileset.validate(self.spec)
        except ValueError as ex:
            QMessageBox.warning(self, "Tileset problem", str(ex))
            return
        self.accept()
