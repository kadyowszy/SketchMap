import math
import os
import sys

import cv2
import numpy as np

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sketchmap", "docs", "drawing_guide.png")
W, H = 1240, 1754


def text(img, s, x, y, scale=0.9, th=2, col=(30, 30, 30)):
    cv2.putText(img, s, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, col, th, cv2.LINE_AA)


def main():
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    import random
    from sketchmap import elements as el
    from tools.glyph_draw import draw_glyph, STROKES
    rng = random.Random(3)
    W2, H2 = 1240, 1754
    img = np.full((H2, W2, 3), 255, np.uint8)
    text(img, "SketchMap - how to draw your level", 60, 80, 1.4, 3)
    text(img, "Black pen, white A4 paper, even light. Photograph the WHOLE sheet, straight on.", 60, 120, 0.7, 2, (90, 90, 90))
    g = np.full((H2, W2), 255, np.uint8)
    keys = ["boundary", "wall"] + [e.key for e in el.ELEMENTS if e.key in STROKES and e.key not in ("boundary", "wall")]
    cols, cw, ch, y0 = 3, 380, 146, 150
    for i, k in enumerate(keys):
        cx0, cy0 = 60 + (i % cols) * cw, y0 + (i // cols) * ch
        e = el.BY_KEY[k]
        text(img, e.label, cx0, cy0 + 22, 0.7, 2)
        if k == "boundary":
            cv2.rectangle(g, (cx0 + 20, cy0 + 50), (cx0 + 150, cy0 + 130), 0, 4, cv2.LINE_AA)
        elif k == "wall":
            cv2.line(g, (cx0 + 10, cy0 + 90), (cx0 + 70, cy0 + 90), 0, 5, cv2.LINE_AA)
            cv2.line(g, (cx0 + 100, cy0 + 90), (cx0 + 160, cy0 + 90), 0, 5, cv2.LINE_AA)
        else:
            draw_glyph(g, k, (cx0 + 85, cy0 + 85), 80, 3, rng, wob=0.0, rot_deg=0, anis=(1, 1), gaps=False)
        words, line = e.pen.split(), ""
        yy = cy0 + 60
        for w in words:
            if len(line) + len(w) > 20:
                text(img, line, cx0 + 180, yy, 0.45, 1, (70, 70, 70)); yy += 22; line = ""
            line += w + " "
        text(img, line, cx0 + 180, yy, 0.45, 1, (70, 70, 70))
    img[g < 128] = 0
    y = y0 + ((len(keys) + cols - 1) // cols) * ch + 20
    cv2.line(img, (60, y), (W2 - 60, y), (200, 200, 200), 2)
    y += 45
    for l in ["Tips", "- Keep symbols apart from walls and at least half a symbol width from each other.",
              "- For a door in a wall gap leave a hair of white between the box and the wall.",
              "- Draw symbols about 11 mm or larger with a fine pen. Slightly crooked lines are fine.",
              "- A jagged (zig-zag) line becomes a row of breakable props. A star is a torch; the player start is an arrow.",
              "- Choose the tile size (Scale) so one square is about one grid cell; Auto estimates it from your symbols.",
              "- Avoid shadows across the page. A phone photo in daylight works well."]:
        text(img, l, 60, y, 0.7 if l != "Tips" else 0.9, 2 if l == "Tips" else 1, (30, 30, 30) if l == "Tips" else (70, 70, 70))
        y += 34
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    cv2.imwrite(OUT, img)
    print("wrote", os.path.abspath(OUT))


if __name__ == "__main__":
    sys.exit(main())
