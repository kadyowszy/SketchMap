import os

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QImageReader, QPixmap

_CACHE = {}


def thumbnail(path, max_w=420, max_h=300):
    try:
        key = (path, os.path.getmtime(path))
    except OSError:
        return None
    if key in _CACHE:
        return _CACHE[key]
    pm = None
    r = QImageReader(path)
    r.setAutoTransform(True)
    sz = r.size()
    if sz.isValid():
        sz.scale(max_w, max_h, Qt.AspectRatioMode.KeepAspectRatio)
        r.setScaledSize(sz)
        img = r.read()
        if not img.isNull():
            pm = QPixmap.fromImage(img)
    _CACHE[key] = pm
    return pm
