import cv2
import numpy as np

from . import elements as el

C = dict(wall=(60, 60, 60), boundary=(25, 25, 25), grid=(225, 225, 225))


def _bgr(hexcolor):
    h = hexcolor.lstrip("#")
    return int(h[4:6], 16), int(h[2:4], 16), int(h[0:2], 16)


def star_pts(cx, cy, r, inner=0.42):
    pts = []
    for i in range(10):
        ang = -np.pi / 2 + i * np.pi / 5
        rr = r if i % 2 == 0 else r * inner
        pts.append((cx + rr * np.cos(ang), cy + rr * np.sin(ang)))
    return np.array(pts, np.int32)


def draw_zigzag(img, x0, y0, x1, y1, color, amp, teeth=4, th=2):
    pts = []
    n = teeth * 2
    for i in range(n + 1):
        t = i / n
        off = 0 if i in (0, n) else (amp if i % 2 else -amp)
        if abs(x1 - x0) >= abs(y1 - y0):
            pts.append((x0 + (x1 - x0) * t, y0 + off))
        else:
            pts.append((x0 + off, y0 + (y1 - y0) * t))
    cv2.polylines(img, [np.array(pts, np.int32)], False, color, th, cv2.LINE_AA)


def draw_triangle(img, cx, cy, r, color, fill=True):
    t = np.array([(cx, cy - r), (cx + r, cy + r * 0.8), (cx - r, cy + r * 0.8)], np.int32)
    cv2.fillPoly(img, [t], color) if fill else cv2.polylines(img, [t], True, color, 2, cv2.LINE_AA)


def sketch_background(model, A, z):
    cp, (ox, oy) = A.cell_px, A.origin
    s = z / cp
    M = np.float32([[s, 0, (-ox + 0.5 * cp) * s], [0, s, (-oy + 0.5 * cp) * s]])
    g = cv2.warpAffine(A.gray, M, (model.width * z, model.height * z), flags=cv2.INTER_AREA, borderValue=255)
    g = (255 - (255 - g.astype(np.float32)) * 0.55).astype(np.uint8)
    return cv2.cvtColor(g, cv2.COLOR_GRAY2BGR)


def render_map(model, z=22, A=None, show_sketch=False, alpha=0.8):
    W, H = model.width, model.height
    base = sketch_background(model, A, z) if (show_sketch and A is not None) else np.full((H * z, W * z, 3), 255, np.uint8)
    ov = base.copy()
    for x in range(W + 1):
        cv2.line(ov, (x * z, 0), (x * z, H * z), C["grid"], 1)
    for y in range(H + 1):
        cv2.line(ov, (0, y * z), (W * z, y * z), C["grid"], 1)
    for (x, y), (k, f) in model.terrain.items():
        cv2.rectangle(ov, (x * z, y * z), ((x + 1) * z - 1, (y + 1) * z - 1), _bgr(el.BY_KEY[k].color), -1)
    for s in sorted(model.segments, key=lambda s: s.kind == "boundary"):
        for x, y in s.tiles():
            p0, p1 = (x * z, y * z), ((x + 1) * z - 1, (y + 1) * z - 1)
            cv2.rectangle(ov, p0, p1, C[s.kind], -1)
    for (x, y), (k, f) in model.objects.items():
        e = el.BY_KEY[k]
        p0, p1 = (x * z + z // 8, y * z + z // 8), ((x + 1) * z - z // 8, (y + 1) * z - z // 8)
        cv2.rectangle(ov, p0, p1, _bgr(e.color), -1)
        cv2.rectangle(ov, p0, p1, (40, 40, 40), 1)
        cv2.putText(ov, e.code, (x * z + z // 5, y * z + int(z * 0.68)), cv2.FONT_HERSHEY_SIMPLEX, z / 55, (20, 20, 20), 1, cv2.LINE_AA)
    return cv2.addWeighted(ov, alpha, base, 1 - alpha, 0) if show_sketch else ov
