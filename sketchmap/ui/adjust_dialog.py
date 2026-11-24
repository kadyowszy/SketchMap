from typing import Callable, Optional

import cv2
import numpy as np
from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF, QThreadPool, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap, QPainter, QPen, QColor
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QSplitter, QWidget, QLabel, QSlider, QPushButton,
    QComboBox, QCheckBox, QGroupBox, QScrollArea, QDoubleSpinBox, QButtonGroup,
    QRadioButton, QDialogButtonBox,
)

from ..config import PreprocessParams
from ..workers import PipelineWorker
from ..preprocess import (run_preprocessing, auto_detect_skew_angle, four_point_warp,
                          find_paper_corners, limit_side)

GRAB_RADIUS = 16


def _fast_morph_skeleton(binary: np.ndarray) -> np.ndarray:
    img = (binary > 0).astype(np.uint8) * 255
    skel = np.zeros_like(img)
    element = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
    for _ in range(64):
        eroded = cv2.erode(img, element)
        temp = cv2.subtract(img, cv2.dilate(eroded, element))
        skel = cv2.bitwise_or(skel, temp)
        img = eroded
        if cv2.countNonZero(img) == 0:
            break
    return skel


def compute_view(bgr, params, mode, thinning_fn):
    result = run_preprocessing(bgr, params)
    if mode == "straightened":
        return result.straightened_bgr
    if mode == "enhanced":
        return result.enhanced_gray
    if mode == "skeleton":
        skel = thinning_fn(result.binary_mask)
        overlay = (result.straightened_bgr * 0.45).astype(np.uint8)
        overlay[cv2.dilate(skel, np.ones((2, 2), np.uint8)) > 0] = (0, 220, 255)
        return overlay
    return cv2.bitwise_not(result.binary_mask)


class PreviewCanvas(QWidget):
    cornersChanged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(520, 440)
        self.setMouseTracking(True)
        self._pixmap: Optional[QPixmap] = None
        self.show_grid = True
        self.grid_spacing = 40
        self.corner_mode = False
        self.corners = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
        self._drag: Optional[int] = None
        self._rect = QRectF()
        self._cache = (None, None)

    def set_image(self, img: np.ndarray):
        img = np.ascontiguousarray(img)
        if img.ndim == 2:
            h, w = img.shape
            qimg = QImage(img.data, w, h, w, QImage.Format.Format_Grayscale8).copy()
        else:
            rgb = np.ascontiguousarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
            h, w, ch = rgb.shape
            qimg = QImage(rgb.data, w, h, w * ch, QImage.Format.Format_RGB888).copy()
        self._pixmap = QPixmap.fromImage(qimg)
        self._cache = (None, None)
        self.update()

    def _image_rect(self) -> QRectF:
        if self._pixmap is None or self._pixmap.isNull():
            return QRectF()
        pw, ph = self._pixmap.width(), self._pixmap.height()
        s = min(self.width() / pw, self.height() / ph)
        w, h = pw * s, ph * s
        return QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)

    def _to_screen(self, p):
        r = self._rect
        return QPointF(r.x() + p[0] * r.width(), r.y() + p[1] * r.height())

    def paintEvent(self, event):
        qp = QPainter(self)
        qp.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        qp.setRenderHint(QPainter.RenderHint.Antialiasing)
        qp.fillRect(self.rect(), QColor(28, 30, 34))
        self._rect = self._image_rect()
        if self._rect.isEmpty():
            return
        dpr = self.devicePixelRatioF()
        key = (round(self._rect.width()), round(self._rect.height()), dpr, id(self._pixmap))
        if self._cache[0] != key:
            sc = self._pixmap.scaled(int(self._rect.width() * dpr), int(self._rect.height() * dpr),
                                     Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            sc.setDevicePixelRatio(dpr)
            self._cache = (key, sc)
        qp.drawPixmap(self._rect.topLeft(), self._cache[1])

        if self.show_grid and not self.corner_mode:
            qp.setPen(QPen(QColor(0, 200, 255, 70), 1, Qt.PenStyle.DashLine))
            x0, y0, x1, y1 = self._rect.left(), self._rect.top(), self._rect.right(), self._rect.bottom()
            gx = x0 + self.grid_spacing
            while gx < x1:
                qp.drawLine(QPointF(gx, y0), QPointF(gx, y1))
                gx += self.grid_spacing
            gy = y0 + self.grid_spacing
            while gy < y1:
                qp.drawLine(QPointF(x0, gy), QPointF(x1, gy))
                gy += self.grid_spacing

        if self.corner_mode:
            pts = [self._to_screen(p) for p in self.corners]
            qp.setPen(QPen(QColor(0, 220, 90), 2))
            for i in range(4):
                qp.drawLine(pts[i], pts[(i + 1) % 4])
            qp.setPen(QPen(QColor(255, 70, 70), 3))
            qp.setBrush(QColor(255, 70, 70, 110))
            for pt in pts:
                qp.drawEllipse(pt, 8, 8)

    def _norm(self, pos):
        r = self._rect
        if r.isEmpty():
            return None
        return (min(max((pos.x() - r.x()) / r.width(), 0.0), 1.0),
                min(max((pos.y() - r.y()) / r.height(), 0.0), 1.0))

    def mousePressEvent(self, e):
        if not self.corner_mode:
            return
        pos = e.position()
        d = [np.hypot(pos.x() - self._to_screen(c).x(), pos.y() - self._to_screen(c).y()) for c in self.corners]
        i = int(np.argmin(d))
        self._drag = i if d[i] < GRAB_RADIUS else None

    def mouseMoveEvent(self, e):
        if self._drag is not None:
            n = self._norm(e.position())
            if n is not None:
                self.corners[self._drag] = n
                self.update()
                self.cornersChanged.emit()

    def mouseReleaseEvent(self, e):
        self._drag = None


VIEW_TIPS = {
    "corners": "Shows the original photo with 4 corner handles. Drag them onto the paper corners.",
    "straightened": "Step 1: the photo after fixing the angle, rotating and trimming.",
    "enhanced": "Step 2: grey version after lighting fixes. Lines should be clearly darker than the paper.",
    "binary": "Step 3: pure black and white. This is what the app reads, so it should look like clean walls.",
    "skeleton": "Step 4: the thin centre lines the app will turn into walls, drawn over your sketch.",
}
ROT_TIP = ("Turns the picture so the walls are level.\n"
           "Move right: turns it one way. Move left: turns it the other way. Or press Auto-Straighten.")
METHOD_TIP = "How the app decides which marks are lines. 'Photo (recommended)' works for most phone pictures."
INK_TIP = ("Tells the app whether your lines are darker or lighter than the paper.\n"
           "'Auto' is right for almost every sketch.")


def _tip(widget, text):
    widget.setToolTip(text)
    return widget


class AdjustDialog(QDialog):

    def __init__(self, image_bgr: np.ndarray,
                 initial_params: Optional[PreprocessParams] = None,
                 thinning_preview_fn: Optional[Callable[[np.ndarray], np.ndarray]] = None,
                 auto_corners: bool = True,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("Clean Up Your Sketch")
        self.resize(1120, 740)

        self._preview_bgr = limit_side(image_bgr)
        self.params = PreprocessParams.from_dict(initial_params.to_dict()) if initial_params else PreprocessParams()
        self._thinning_fn = thinning_preview_fn or _fast_morph_skeleton
        self._labels = {}
        self._pool = QThreadPool.globalInstance()
        self._job_id = 0
        self._jobs = {}

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(35)
        self._debounce.timeout.connect(self._refresh_preview)

        self._build_ui()

        corners = self.params.perspective_points
        if corners is None and auto_corners:
            corners = self._detect_corners()
            if corners is not None:
                self.params.perspective_points = corners
        if corners is not None:
            self.canvas.corners = [tuple(c) for c in corners]
        self._sync_widgets_from_params()
        self._refresh_preview()

    def _build_ui(self):
        root = QVBoxLayout(self)

        top = QHBoxLayout()
        self.view_group = QButtonGroup(self)
        for idx, (key, label) in enumerate([("corners", "Corners"), ("straightened", "1. Straightened"),
                                            ("enhanced", "2. Lighting"), ("binary", "3. Black && White"),
                                            ("skeleton", "4. Final Lines")]):
            rb = QRadioButton(label)
            rb.setToolTip(VIEW_TIPS[key])
            rb.setProperty("view_mode", key)
            rb.setChecked(key == "binary")
            self.view_group.addButton(rb, idx)
            top.addWidget(rb)
        self.view_group.buttonClicked.connect(lambda _: self._refresh_preview())
        top.addStretch()

        self.chk_grid = QCheckBox("Guide Grid")
        self.chk_grid.setToolTip("Shows a grid over the preview so you can check that walls are straight.")
        self.chk_grid.setChecked(True)
        self.chk_grid.toggled.connect(self._on_grid_toggled)
        top.addWidget(self.chk_grid)
        btn_auto = QPushButton("Auto-Straighten")
        btn_auto.setToolTip("Finds the tilt of your walls and rotates the picture to level them.")
        btn_auto.clicked.connect(self._on_auto_straighten)
        top.addWidget(btn_auto)
        btn_reset = QPushButton("Reset All")
        btn_reset.setToolTip("Puts every setting back to how it was when you opened this window.")
        btn_reset.clicked.connect(self._on_reset)
        top.addWidget(btn_reset)
        root.addLayout(top)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.canvas = PreviewCanvas()
        self.canvas.cornersChanged.connect(self._on_corners_dragged)
        splitter.addWidget(self.canvas)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(390)
        host = QWidget()
        lay = QVBoxLayout(host)

        g = QGroupBox("1. Straighten && Crop")
        gl = QVBoxLayout(g)
        self.chk_persp = QCheckBox("Fix camera angle (drag the 4 corners in 'Corners' view)")
        self.chk_persp.setToolTip("On: the paper is stretched flat, like a scan, using the 4 corners you place.\n"
                                  "Use it when the photo was taken at an angle. Off: no change.")
        self.chk_persp.toggled.connect(self._on_persp_toggled)
        gl.addWidget(self.chk_persp)
        btn_corners = QPushButton("Find Paper Corners")
        btn_corners.setToolTip("Tries to find the 4 corners of the paper by itself. You can still drag them.")
        btn_corners.clicked.connect(self._on_detect_corners)
        gl.addWidget(btn_corners)

        rot = QHBoxLayout()
        lbl_rot = QLabel("Rotate (°):")
        lbl_rot.setToolTip(ROT_TIP)
        rot.addWidget(lbl_rot)
        self.spin_rot = QDoubleSpinBox()
        self.spin_rot.setRange(-45.0, 45.0)
        self.spin_rot.setSingleStep(0.25)
        self.spin_rot.setDecimals(2)
        self.slider_rot = QSlider(Qt.Orientation.Horizontal)
        self.slider_rot.setRange(-4500, 4500)
        self.slider_rot.setToolTip(ROT_TIP)
        self.spin_rot.setToolTip(ROT_TIP)
        self.slider_rot.valueChanged.connect(lambda v: self.spin_rot.setValue(v / 100.0))
        self.spin_rot.valueChanged.connect(self._on_rot_changed)
        rot.addWidget(self.slider_rot)
        rot.addWidget(self.spin_rot)
        gl.addLayout(rot)
        self.sl_crop = self._add_slider(gl, "Trim Edges (%)", 0, 30, 0,
                                    "Cuts away the outer edge of the picture (table, shadows, page border).\n"
                                    "Higher: more is cut off. Lower: more of the picture is kept.")
        lay.addWidget(g)

        g = QGroupBox("2. Light && Contrast")
        gl = QVBoxLayout(g)
        self.sl_shadow = self._add_slider(gl, "Remove Shadows", 0, 100, 35,
                                       "Evens out the lighting across the page.\n"
                                       "Higher: shadows and dark corners fade more (too high can weaken real lines).\n"
                                       "Lower: the photo's lighting is left as it is.")
        self.sl_bright = self._add_slider(gl, "Brightness", -100, 100, 0,
                                       "Higher: the whole picture gets lighter. Lower: it gets darker.")
        self.sl_contrast = self._add_slider(gl, "Contrast (%)", 50, 300, 100,
                                         "Higher: dark lines and light paper are pushed further apart.\n"
                                         "Lower: everything looks flatter and greyer. 100 = no change.")
        self.sl_gamma = self._add_slider(gl, "Midtone Lightness", 25, 250, 100,
                                       "Changes only the in-between greys.\n"
                                       "Lower: faint pencil lines get darker and easier to detect.\n"
                                       "Higher: grey areas get lighter, which hides faint marks. 100 = no change.")
        self.sl_clahe = self._add_slider(gl, "Bring Out Details", 0, 40, 0,
                                       "Boosts contrast in small areas so faint lines stand out.\n"
                                       "Higher: weak lines show up more (paper texture too).\n"
                                       "Lower / 0: off.")
        lay.addWidget(g)

        g = QGroupBox("3. Find the Lines")
        gl = QVBoxLayout(g)
        row = QHBoxLayout()
        row.addWidget(_tip(QLabel("Method:"), METHOD_TIP))
        self.cmb_thresh = QComboBox()
        self.cmb_thresh.addItem("Photo (recommended)", "adaptive_gaussian")
        self.cmb_thresh.addItem("Photo (alternative)", "adaptive_mean")
        self.cmb_thresh.addItem("Scan or even lighting", "otsu")
        self.cmb_thresh.addItem("Manual", "manual")
        for i, t in enumerate(("Best for phone photos. Judges each spot against the paper right around it, so uneven lighting is fine.",
                               "Like Photo (recommended), but a little rougher. Try it if the first one misses lines.",
                               "Best for scans or very evenly lit pictures. Uses one cut-off for the whole image.",
                               "You choose the cut-off yourself with the 'Ink Cutoff' slider.")):
            self.cmb_thresh.setItemData(i, t, Qt.ItemDataRole.ToolTipRole)
        self.cmb_thresh.setToolTip(METHOD_TIP)
        self.cmb_thresh.currentIndexChanged.connect(self._on_param_changed)
        row.addWidget(self.cmb_thresh)
        gl.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(_tip(QLabel("Ink Colour:"), INK_TIP))
        self.cmb_invert = QComboBox()
        self.cmb_invert.addItem("Auto", "auto")
        self.cmb_invert.addItem("Dark lines on light paper", "normal")
        self.cmb_invert.addItem("Light lines on dark paper", "invert")
        self.cmb_invert.setToolTip(INK_TIP)
        self.cmb_invert.currentIndexChanged.connect(self._on_param_changed)
        row.addWidget(self.cmb_invert)
        gl.addLayout(row)
        self.sl_denoise = self._add_slider(gl, "Smooth Paper Grain", 0, 5, 1,
                                         "Hides paper texture and camera grain.\n"
                                         "Higher: cleaner background, but very thin lines may blur away.\n"
                                         "Lower / 0: keeps every detail, including noise.")
        self.sl_block = self._add_slider(gl, "Area Size", 5, 99, 31,
                                       "How big an area is looked at to judge the paper brightness (Photo methods only).\n"
                                       "Higher: copes better with thick lines and big shadows.\n"
                                       "Lower: picks up finer details but may split thick lines.")
        self.sl_thresh = self._add_slider(gl, "Ink Cutoff", -30, 255, 12,
                                         "Photo methods: how much darker than the paper a mark must be to count as a line.\n"
                                         "Higher: only strong, dark lines are kept (less noise, faint lines lost).\n"
                                         "Lower: faint lines are kept too (more noise).\n"
                                         "Manual method: the grey level; higher keeps more as lines.")
        lay.addWidget(g)

        g = QGroupBox("4. Tidy the Lines")
        gl = QVBoxLayout(g)
        self.sl_close = self._add_slider(gl, "Close Small Gaps (px)", 0, 10, 0,
                                         "Joins lines that have tiny accidental breaks.\n"
                                         "Higher: bigger gaps get closed (doorways may close too).\n"
                                         "0: off, so doorways you left open stay open.")
        self.sl_stroke = self._add_slider(gl, "Line Thickness (px)", -4, 4, 0,
                                          "Higher: lines get thicker (joins broken lines, but can fill small rooms).\n"
                                          "Lower (negative): lines get thinner (separates lines that touch).\n"
                                          "0: no change.")
        self.sl_speckle = self._add_slider(gl, "Ignore Small Dots (px)", 0, 200, 25,
                                          "Removes stray dots and specks smaller than this size.\n"
                                          "Higher: more dirt is removed (tiny real marks can vanish too).\n"
                                          "Lower / 0: nothing is removed.")
        self.chk_pinholes = QCheckBox("Fill tiny holes in lines")
        self.chk_pinholes.setToolTip("On: fills tiny holes inside thick lines so they are not mistaken for rooms.\n"
                                     "Off: lines are left exactly as detected.")
        self.chk_pinholes.toggled.connect(self._on_param_changed)
        gl.addWidget(self.chk_pinholes)
        lay.addWidget(g)

        lay.addStretch()
        scroll.setWidget(host)
        splitter.addWidget(scroll)
        splitter.setSizes([720, 400])
        root.addWidget(splitter, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Apply && Build Map")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _add_slider(self, layout, text, lo, hi, default, tip="") -> QSlider:
        row = QHBoxLayout()
        lbl = QLabel(text)
        lbl.setMinimumWidth(145)
        sl = QSlider(Qt.Orientation.Horizontal)
        sl.setRange(lo, hi)
        sl.setValue(default)
        val = QLabel(str(default))
        val.setMinimumWidth(36)
        val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._labels[sl] = val
        sl.valueChanged.connect(lambda v, l=val: l.setText(str(v)))
        sl.valueChanged.connect(self._on_param_changed)
        if tip:
            for w in (lbl, sl, val):
                w.setToolTip(tip)
        row.addWidget(lbl)
        row.addWidget(sl)
        row.addWidget(val)
        layout.addLayout(row)
        return sl

    def _all_widgets(self):
        return [self.spin_rot, self.slider_rot, self.chk_persp, self.sl_crop, self.sl_shadow, self.sl_bright,
                self.sl_contrast, self.sl_gamma, self.sl_clahe, self.cmb_thresh, self.cmb_invert,
                self.sl_denoise, self.sl_block, self.sl_thresh, self.sl_close, self.sl_stroke,
                self.sl_speckle, self.chk_pinholes]

    def _set_slider(self, sl, v):
        sl.setValue(int(v))
        self._labels[sl].setText(str(int(v)))

    def _sync_widgets_from_params(self):
        ws = self._all_widgets()
        for w in ws:
            w.blockSignals(True)
        p = self.params
        self.spin_rot.setValue(p.rotation_deg)
        self.slider_rot.setValue(int(round(p.rotation_deg * 100)))
        self.chk_persp.setChecked(p.perspective_points is not None)
        self._set_slider(self.sl_crop, round(p.crop_margins[0] * 100))
        self._set_slider(self.sl_shadow, round(p.shadow_removal * 100))
        self._set_slider(self.sl_bright, p.brightness)
        self._set_slider(self.sl_contrast, round(p.contrast * 100))
        self._set_slider(self.sl_gamma, round(p.gamma * 100))
        self._set_slider(self.sl_clahe, round(p.clahe_strength * 10))
        self.cmb_thresh.setCurrentIndex(max(0, self.cmb_thresh.findData(p.threshold_mode)))
        self.cmb_invert.setCurrentIndex(max(0, self.cmb_invert.findData(p.invert)))
        self._set_slider(self.sl_denoise, p.denoise_strength)
        self._set_slider(self.sl_block, p.adaptive_block_size)
        self._set_slider(self.sl_thresh, p.threshold_offset)
        self._set_slider(self.sl_close, p.close_gaps_px)
        self._set_slider(self.sl_stroke, p.stroke_adjust_px)
        self._set_slider(self.sl_speckle, p.min_speckle_area)
        self.chk_pinholes.setChecked(p.fill_pinholes)
        for w in ws:
            w.blockSignals(False)

    def _read_params_from_widgets(self):
        p = self.params
        trim = self.sl_crop.value() / 100.0
        p.rotation_deg = float(self.spin_rot.value())
        p.perspective_points = tuple(tuple(c) for c in self.canvas.corners) if self.chk_persp.isChecked() else None
        p.crop_margins = (trim, trim, trim, trim)
        p.shadow_removal = self.sl_shadow.value() / 100.0
        p.brightness = int(self.sl_bright.value())
        p.contrast = self.sl_contrast.value() / 100.0
        p.gamma = self.sl_gamma.value() / 100.0
        p.clahe_strength = self.sl_clahe.value() / 10.0
        p.threshold_mode = self.cmb_thresh.currentData()
        p.invert = self.cmb_invert.currentData()
        p.denoise_strength = int(self.sl_denoise.value())
        p.adaptive_block_size = int(self.sl_block.value()) | 1
        p.threshold_offset = int(self.sl_thresh.value())
        p.close_gaps_px = int(self.sl_close.value())
        p.stroke_adjust_px = int(self.sl_stroke.value())
        p.min_speckle_area = int(self.sl_speckle.value())
        p.fill_pinholes = self.chk_pinholes.isChecked()

    def _on_rot_changed(self, val: float):
        self.slider_rot.blockSignals(True)
        self.slider_rot.setValue(int(round(val * 100)))
        self.slider_rot.blockSignals(False)
        self._on_param_changed()

    def _on_param_changed(self, *_):
        self._read_params_from_widgets()
        self._debounce.start()

    def _on_grid_toggled(self, checked: bool):
        self.canvas.show_grid = checked
        self.canvas.update()

    def _on_corners_dragged(self):
        if not self.chk_persp.isChecked():
            self.chk_persp.blockSignals(True)
            self.chk_persp.setChecked(True)
            self.chk_persp.blockSignals(False)
        self._on_param_changed()

    def _on_persp_toggled(self, checked: bool):
        if checked:
            self._select_view("corners")
        self._on_param_changed()

    def _select_view(self, key):
        for b in self.view_group.buttons():
            if b.property("view_mode") == key:
                b.setChecked(True)

    def _detect_corners(self):
        rect = find_paper_corners(self._preview_bgr)
        if rect is None:
            return None
        h, w = self._preview_bgr.shape[:2]
        return tuple((float(x) / w, float(y) / h) for x, y in rect)

    def _on_detect_corners(self):
        c = self._detect_corners()
        if c is None:
            c = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))
        self.canvas.corners = [tuple(p) for p in c]
        self.chk_persp.blockSignals(True)
        self.chk_persp.setChecked(True)
        self.chk_persp.blockSignals(False)
        self._select_view("corners")
        self._on_param_changed()

    def _on_auto_straighten(self):
        base = self._preview_bgr
        if self.chk_persp.isChecked():
            base = four_point_warp(base, self.canvas.corners)
        self.params.rotation_deg = float(np.clip(auto_detect_skew_angle(base), -45.0, 45.0))
        self._sync_widgets_from_params()
        self._read_params_from_widgets()
        self._refresh_preview()

    def _on_reset(self):
        self.params = PreprocessParams()
        self.canvas.corners = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
        self._sync_widgets_from_params()
        self._refresh_preview()

    def _current_view_mode(self) -> str:
        b = self.view_group.checkedButton()
        return b.property("view_mode") if b else "binary"

    def _refresh_preview(self):
        mode = self._current_view_mode()
        self.canvas.corner_mode = (mode == "corners")
        if mode == "corners":
            self._job_id += 1
            self.canvas.set_image(self._preview_bgr)
            return
        self._job_id += 1
        job = self._job_id
        params = PreprocessParams.from_dict(self.params.to_dict())
        worker = PipelineWorker(job, compute_view, self._preview_bgr, params, mode, self._thinning_fn)
        worker.signals.finished.connect(self._on_view_ready)
        worker.signals.error.connect(self._on_view_error)
        self._jobs[job] = worker
        self._pool.start(worker)

    def _on_view_ready(self, job_id, img):
        self._jobs.pop(job_id, None)
        if job_id == self._job_id:
            self.canvas.set_image(img)

    def _on_view_error(self, job_id, msg):
        self._jobs.pop(job_id, None)
        if job_id == self._job_id:
            self.setWindowTitle(f"Clean Up Your Sketch  -  preview error: {msg}")

    def done(self, r):
        self._job_id += 1
        super().done(r)

    def get_params(self) -> PreprocessParams:
        self._read_params_from_widgets()
        return self.params
