import cv2
import numpy as np
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPixmap

A_CENTER = Qt.AlignmentFlag.AlignCenter.value
A_HCENTER_TOP = Qt.AlignmentFlag.AlignHCenter.value | Qt.AlignmentFlag.AlignTop.value
A_LEFT_VCENTER = Qt.AlignmentFlag.AlignLeft.value | Qt.AlignmentFlag.AlignVCenter.value
A_WRAP_CENTER = Qt.AlignmentFlag.AlignCenter.value | Qt.TextFlag.TextWordWrap.value


def to_qimage(img):
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    rgb = np.ascontiguousarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    h, w = rgb.shape[:2]
    return QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()


def rgba_to_qimage(arr):
    arr = np.ascontiguousarray(arr)
    h, w = arr.shape[:2]
    return QImage(arr.data, w, h, 4 * w, QImage.Format.Format_RGBA8888).copy()


def to_pixmap(img):
    return QPixmap.fromImage(to_qimage(img))


def repolish(w):
    w.style().unpolish(w)
    w.style().polish(w)
    w.update()
