import os
import random
import sys

import cv2
import numpy as np

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
from tools.glyph_draw import STROKES, draw_glyph

OUT = os.path.join(ROOT, "sketchmap", "ui", "samples", "symbol_demo.png")
W, H = 1600, 1131
KEYS = [k for k in STROKES if k not in ("boundary", "wall")]


def main():
    rng = random.Random(7)
    img = np.full((H, W), 255, np.uint8)
    for a, b in [((200, 150), (1400, 150)), ((1400, 150), (1400, 950)), ((1400, 950), (200, 950)), ((200, 950), (200, 150)),
                 ((900, 150), (900, 450)), ((900, 450), (1400, 450)), ((200, 498), (700, 498)), ((700, 498), (700, 950))]:
        cv2.line(img, a, b, 0, 5, cv2.LINE_AA)
    zz = [(1150 + (14 if i % 2 else -14), 480 + i * 27) for i in range(11)]
    cv2.polylines(img, [np.array(zz, np.int32)], False, 0, 4, cv2.LINE_AA)
    slots = [(290 + 130 * i, 230 + 130 * j) for j in range(2) for i in range(5)]
    slots += [(990 + 130 * i, 230 + 130 * j) for j in range(2) for i in range(3)][:5]
    slots += [(290 + 130 * i, 590 + 120 * j) for j in range(3) for i in range(3)]
    slots += [(1010, 600), (1290, 600), (1290, 800), (1010, 850), (800, 560), (800, 780)]
    order = ["arrow_start"] + [k for k in KEYS if k != "arrow_start"]
    for k, c in zip(order, slots):
        draw_glyph(img, k, c, 84, 4, rng, wob=0.6, facing=0)
    g = np.linspace(215, 120, W)[None, :] * np.ones((H, 1))
    out = (img / 255.0 * g + np.random.RandomState(1).normal(0, 2, (H, W))).clip(0, 255).astype(np.uint8)
    cv2.imwrite(OUT, out)
    print("wrote", os.path.abspath(OUT), len(order), "symbols,", len(slots), "slots")


if __name__ == "__main__":
    main()
