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
    img = np.full((H, W, 3), 255, np.uint8)
    text(img, "SketchMap - how to draw your level", 60, 90, 1.5, 3)
    text(img, "Black pen, white A4 paper, even light. Photograph or scan the WHOLE sheet, straight on.", 60, 140, 0.8, 2, (90, 90, 90))
    rows = [("Boundary", "One closed rectangle around the whole play area."),
            ("Wall", "Straight horizontal / vertical lines. Leave a gap for a doorway."),
            ("Player start", "A star. Leave white space around it; do not touch any line."),
            ("Door", "A small hollow square."),
            ("Enemy spawn", "A hollow triangle."),
            ("Breakable prop", "A zig-zag (jagged) line: becomes a row of breakable props.")]
    y = 230
    for name, how in rows:
        text(img, name, 60, y + 10, 1.0, 2)
        text(img, how, 60, y + 52, 0.7, 1, (90, 90, 90))
        cx, cy = 900, y + 20
        if name == "Boundary":
            cv2.rectangle(img, (780, cy - 40), (1130, cy + 55), 0, 5, cv2.LINE_AA)
        elif name == "Wall":
            cv2.line(img, (780, cy + 8), (950, cy + 8), 0, 6, cv2.LINE_AA)
            cv2.line(img, (1010, cy + 8), (1130, cy + 8), 0, 6, cv2.LINE_AA)
        elif name == "Player start":
            pts = [(cx + 90 + (46 if i % 2 == 0 else 20) * math.cos(-math.pi / 2 + i * math.pi / 5),
                    cy + 8 + (46 if i % 2 == 0 else 20) * math.sin(-math.pi / 2 + i * math.pi / 5)) for i in range(10)]
            pts.append(pts[0])
            cv2.polylines(img, [np.array(pts, np.int32)], False, 0, 4, cv2.LINE_AA)
        elif name == "Door":
            cv2.rectangle(img, (cx + 60, cy - 22), (cx + 118, cy + 36), 0, 4, cv2.LINE_AA)
        elif name == "Enemy spawn":
            cv2.polylines(img, [np.array([(cx + 90, cy - 30), (cx + 138, cy + 38), (cx + 42, cy + 38)], np.int32)], True, 0, 4, cv2.LINE_AA)
        else:
            zz = [(cx + 90 + (14 if i % 2 else -14), cy - 36 + i * 14) for i in range(11)]
            cv2.polylines(img, [np.array(zz, np.int32)], False, 0, 4, cv2.LINE_AA)
        y += 150
    cv2.line(img, (60, y), (W - 60, y), (200, 200, 200), 2)
    y += 60
    for l in ["Tips", "- Keep symbols apart from walls (a symbol that touches a wall is read as part of the wall).",
              "- Draw lines along the paper edges; slightly crooked lines are straightened automatically.",
              "- Everything else (water, lava, keys, chests, ...) is placed in the Edit page with the element palette.",
              "- Choose the tile size (Scale) so one square is about one grid cell. Use Auto to estimate it.",
              "- Avoid shadows across the page. A phone photo in daylight works well."]:
        text(img, l, 60, y, 0.8 if l != "Tips" else 1.0, 2 if l == "Tips" else 1, (30, 30, 30) if l == "Tips" else (70, 70, 70))
        y += 50
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    cv2.imwrite(OUT, img)
    print("wrote", os.path.abspath(OUT))


if __name__ == "__main__":
    sys.exit(main())
