from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QWidget, QFrame, QLabel, QVBoxLayout, QHBoxLayout, QDoubleSpinBox, QPushButton, QSlider)

from ..theme import P
from ..widgets import PageHeader, ExportButton, IconButton, ToolButton, ToggleSwitch, make_button
from ..level_view import LevelView
from ..element_palette import ElementPalette
from ..stats_panel import StatsPanel


def _pill():
    f = QFrame()
    f.setObjectName("pill")
    v = QVBoxLayout(f)
    v.setContentsMargins(8, 10, 8, 10)
    v.setSpacing(4)
    return f, v


class EditPage(QWidget):
    back_clicked = pyqtSignal()
    export_chosen = pyqtSignal(str)
    scale_requested = pyqtSignal(float)
    auto_scale_requested = pyqtSignal()
    stats_toggled = pyqtSignal(bool)
    stage_changed = pyqtSignal()
    edited = pyqtSignal()
    customize_tileset_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._last_tool = "wall"
        self._has_analysis = False
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 24, 32, 18)
        root.setSpacing(16)
        root.addWidget(PageHeader())

        bar = QHBoxLayout()
        bar.setSpacing(10)
        self.back_btn = make_button("Back", "back", tooltip="Back to the preview")
        self.back_btn.clicked.connect(self.back_clicked.emit)
        bar.addWidget(self.back_btn)
        bar.addStretch(1)
        self.tileset_btn = make_button("Customize Tileset…", tooltip="Choose your sprite sheet and which cell draws each tile type", variant="ghost")
        self.tileset_btn.clicked.connect(self.customize_tileset_requested.emit)
        bar.addWidget(self.tileset_btn)
        self.export_btn = ExportButton()
        self.export_btn.chosen.connect(self.export_chosen.emit)
        bar.addWidget(self.export_btn)
        self.edit_btn = make_button("Edit", "edit", tooltip="Editing is on. Click to switch to view-only.")
        self.edit_btn.setCheckable(True)
        self.edit_btn.setChecked(True)
        self.edit_btn.toggled.connect(self._on_edit_mode)
        bar.addWidget(self.edit_btn)
        root.addLayout(bar)

        body = QHBoxLayout()
        body.setSpacing(14)

        self.palette = ElementPalette()
        self.palette.tool_chosen.connect(self._select_tool)
        self.palette.facing_changed.connect(lambda f: self.view.set_facing(f))
        body.addWidget(self.palette)

        self.canvas_card = QFrame()
        self.canvas_card.setObjectName("canvasCard")
        cv = QVBoxLayout(self.canvas_card)
        cv.setContentsMargins(8, 8, 8, 8)
        self.view = LevelView(editable=True, navigable=True)
        self.view.edited.connect(self._on_view_edited)
        cv.addWidget(self.view)
        body.addWidget(self.canvas_card, 1)

        right = QVBoxLayout()
        right.addStretch(1)
        pill, rv = _pill()
        self.pan_btn = ToolButton("pan", "Pan: drag to move the map  (Space or middle mouse also pan).\nMouse wheel zooms, double-click fits to screen.", checkable=True)
        self.zoom_out_btn = ToolButton("zoom_out", "Zoom out")
        self.undo_btn = ToolButton("undo", "Undo  (Ctrl+Z)")
        self.redo_btn = ToolButton("redo", "Redo  (Ctrl+Y)")
        self.zoom_in_btn = ToolButton("zoom_in", "Zoom in")
        for b in (self.pan_btn, self.zoom_out_btn, self.undo_btn, self.redo_btn, self.zoom_in_btn):
            rv.addWidget(b)
        right.addWidget(pill)
        right.addStretch(1)
        body.addLayout(right)

        self.pan_btn.toggled.connect(self._on_pan)
        self.zoom_out_btn.clicked.connect(lambda: self.view.zoom_by(1 / 1.25))
        self.zoom_in_btn.clicked.connect(lambda: self.view.zoom_by(1.25))
        self.undo_btn.clicked.connect(self.view.undo)
        self.redo_btn.clicked.connect(self.view.redo)

        self.drawer = StatsPanel()
        self.drawer.hide()
        self.drawer.closed.connect(lambda: self.stats_btn.setChecked(False))
        self.drawer.stage_changed.connect(self.stage_changed.emit)
        body.addWidget(self.drawer)
        root.addLayout(body, 1)

        info = QHBoxLayout()
        info.setContentsMargins(4, 0, 4, 0)
        info.setSpacing(12)
        self.summary = QLabel("")
        self.summary.setObjectName("muted")
        info.addWidget(self.summary)
        self.hover_lbl = QLabel("")
        self.hover_lbl.setObjectName("faint")
        info.addWidget(self.hover_lbl, 1)
        self.view.hovered.connect(self.hover_lbl.setText)

        self.scale_lbl = QLabel("Scale")
        self.scale_lbl.setObjectName("muted")
        self.spin = QDoubleSpinBox()
        self.spin.setRange(1.0, 100.0)
        self.spin.setDecimals(1)
        self.spin.setSingleStep(0.5)
        self.spin.setSuffix(" mm")
        self.spin.setKeyboardTracking(False)
        self.spin.setToolTip("Real-world size of one grid cell on the paper.\nBigger = coarser grid, smaller = finer grid.")
        self.spin.editingFinished.connect(lambda: self.scale_requested.emit(self.spin.value()))
        self.auto_btn = make_button("Auto", tooltip="Estimate the tile size from the symbols you drew", variant="ghost")
        self.auto_btn.clicked.connect(self.auto_scale_requested.emit)
        for w in (self.scale_lbl, self.spin, self.auto_btn):
            info.addWidget(w)
        info.addSpacing(10)

        self.overlay_lbl = QLabel("Sketch overlay")
        self.overlay_lbl.setObjectName("muted")
        self.overlay_sw = ToggleSwitch()
        self.overlay_sw.setToolTip("Show your original sketch faintly under the grid to check every detection")
        self.overlay_sw.toggled.connect(self.view.set_show_overlay)
        info.addWidget(self.overlay_lbl)
        info.addWidget(self.overlay_sw)
        self.opacity_sl = QSlider(Qt.Orientation.Horizontal)
        self.opacity_sl.setRange(0, 100)
        self.opacity_sl.setValue(100)
        self.opacity_sl.setFixedWidth(90)
        self.opacity_sl.setToolTip("Sketch overlay opacity")
        self.opacity_sl.valueChanged.connect(lambda v: self.view.set_overlay_opacity(v / 100.0))
        info.addWidget(self.opacity_sl)
        info.addSpacing(10)

        self.tiles_lbl = QLabel("Tile preview")
        self.tiles_lbl.setObjectName("muted")
        self.tiles_sw = ToggleSwitch()
        self.tiles_sw.setToolTip("Draw the map with the sprites of the current tileset")
        self.tiles_sw.toggled.connect(self.view.set_show_tiles)
        info.addWidget(self.tiles_lbl)
        info.addWidget(self.tiles_sw)
        info.addSpacing(10)

        self.stats_btn = IconButton("chart", 18, "Stats for nerds  (Ctrl+I)", "Stats for nerds", "ghost")
        self.stats_btn.setCheckable(True)
        self.stats_btn.toggled.connect(self._on_stats)
        info.addWidget(self.stats_btn)
        root.addLayout(info)

        self._select_tool(self._last_tool)
        self._sync_history()

    def _select_tool(self, tid):
        self._last_tool = tid
        self.palette.set_tool(tid)
        self.pan_btn.blockSignals(True)
        self.pan_btn.setChecked(False)
        self.pan_btn.blockSignals(False)
        self.pan_btn.refresh()
        self.view.set_tool(tid)

    def _on_pan(self, on):
        if on:
            self.palette.clear_selection()
            self.view.set_pan_mode(True)
        else:
            self._select_tool(self._last_tool)

    def _on_edit_mode(self, on):
        self.palette.setVisible(on)
        self.view.set_editable(on)
        self.edit_btn.setToolTip("Editing is on. Click to switch to view-only." if on else "View-only. Click to enable editing.")
        self._sync_history()

    def _on_stats(self, on):
        self.drawer.setVisible(on)
        self.stats_toggled.emit(on)

    def _on_view_edited(self):
        self._sync_history()
        self.edited.emit()

    def _sync_history(self):
        ed = self.edit_btn.isChecked()
        self.undo_btn.setEnabled(ed and bool(self.view.undo_stack))
        self.redo_btn.setEnabled(ed and bool(self.view.redo_stack))

    def set_level(self, model, A, st, overlay, cell_mm):
        self._has_analysis = A is not None
        self.view.set_model(model, overlay)
        self.view.set_show_overlay(self.overlay_sw.isChecked() and overlay is not None)
        for w in (self.spin, self.auto_btn, self.overlay_sw, self.opacity_sl, self.stats_btn, self.scale_lbl, self.overlay_lbl):
            w.setEnabled(self._has_analysis)
        tip = "" if self._has_analysis else "Only available for imported sketches (this level was opened from a .json file)."
        for w in (self.spin, self.auto_btn, self.overlay_sw, self.stats_btn):
            if tip:
                w.setToolTip(tip)
        if self._has_analysis:
            self.spin.setToolTip("Real-world size of one grid cell on the paper.\nBigger = coarser grid, smaller = finer grid.")
            self.auto_btn.setToolTip("Estimate the tile size from the symbols you drew")
            self.overlay_sw.setToolTip("Show your original sketch faintly under the grid to check every detection")
            self.stats_btn.setToolTip("Stats for nerds  (Ctrl+I)")
        else:
            self.overlay_sw.setChecked(False)
            self.stats_btn.setChecked(False)
        self.set_scale_value(cell_mm)
        self.drawer.set_data(st, A)
        self._sync_history()

    def set_overlay(self, overlay):
        self.view.set_overlay(overlay)
        self.view.set_show_overlay(self.overlay_sw.isChecked() and overlay is not None)

    def set_scale_value(self, mm):
        self.spin.blockSignals(True)
        self.spin.setValue(float(mm))
        self.spin.blockSignals(False)

    def set_summary(self, text):
        self.summary.setText(text)

    def stats_visible(self):
        return self.drawer.isVisible() or self.stats_btn.isChecked()

    def toggle_stats(self):
        if self.stats_btn.isEnabled():
            self.stats_btn.setChecked(not self.stats_btn.isChecked())
