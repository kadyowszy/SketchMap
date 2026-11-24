import cv2
import numpy as np
from .config import LEGEND


def legend_image(w=380):
    row = 52
    img = np.full((row * len(LEGEND) + 10, w, 3), 255, np.uint8)
    for i, (_key, name, how) in enumerate(LEGEND):
        y = 10 + i * row + row // 2
        cv2.putText(img, name, (14, y - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (30, 30, 30), 1, cv2.LINE_AA)
        cv2.putText(img, how[:52], (14, y + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (110, 110, 110), 1, cv2.LINE_AA)
    return img
