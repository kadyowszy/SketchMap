import math

import cv2
import numpy as np

def _circle(cx, cy, r, n=28):
    return [(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n)) for i in range(n)]


def _wave(y, x0=8, x1=56, amp=4.0, period=24.0, n=40):
    return [(x0 + (x1 - x0) * i / n, y - amp * math.sin(2 * math.pi * (x0 + (x1 - x0) * i / n - x0) / period)) for i in range(n + 1)]


def _star(cx=32, cy=33, r=24, inner=0.42):
    pts = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * inner
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    return pts


def _box(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


STROKES = {
    "boundary": [(_box(9, 11, 55, 53), True)],
    "wall": [([(7, 32), (57, 32)], False)],
    "grass": [([(12, 20), (22, 44), (32, 28), (42, 44), (52, 20)], False)],
    "water": [(_wave(26), False), (_wave(42), False)],
    "lava": [([(12, 48), (12, 20), (26, 36), (38, 36), (52, 20), (52, 48)], True)],
    "ice": [([(22, 48), (34, 16)], False), ([(36, 48), (48, 16)], False)],
    "mud": [([(14, 22), (50, 22)], False), ([(14, 32), (50, 32)], False), ([(14, 42), (50, 42)], False)],
    "conveyor": [([(14, 18), (28, 32), (14, 46)], False), ([(34, 18), (48, 32), (34, 46)], False)],
    "arrow_start": [([(10, 32), (52, 32)], False), ([(40, 20), (52, 32), (40, 44)], False)],
    "goal_exit": [(_circle(32, 32, 22), True), (_circle(32, 32, 10), True)],
    "enemy_spawn": [([(32, 12), (54, 50), (10, 50)], True)],
    "checkpoint": [([(18, 10), (18, 54)], False), ([(18, 12), (48, 21), (18, 30)], False)],
    "patrol_waypoint": [([(32, 14), (32, 50)], False), ([(14, 32), (50, 32)], False)],
    "door": [(_box(18, 14, 46, 50), True)],
    "locked_door": [(_box(14, 14, 50, 50), True), ([(28, 14), (28, 50)], False), ([(36, 14), (36, 50)], False)],
    "key": [(_circle(21, 32, 10), True), ([(31, 32), (55, 32)], False), ([(47, 32), (47, 41)], False), ([(54, 32), (54, 39)], False)],
    "chest": [(_box(10, 16, 54, 48), True), ([(10, 32), (54, 32)], False)],
    "collectible": [(_circle(32, 32, 19), True)],
    "push_block": [(_box(14, 14, 50, 50), True), ([(14, 14), (50, 50)], False), ([(50, 14), (14, 50)], False)],
    "breakable_prop": [(_box(14, 14, 50, 50), True), ([(14, 50), (50, 14)], False)],
    "pressure_plate": [(_box(10, 10, 54, 54), True), (_circle(32, 32, 11), True)],
    "gate": [(_box(12, 12, 52, 52), True), ([(22, 12), (22, 52)], False), ([(32, 12), (32, 52)], False), ([(42, 12), (42, 52)], False)],
    "spike_trap": [([(32, 10), (32, 54)], False), ([(13, 21), (51, 43)], False), ([(13, 43), (51, 21)], False)],
    "torch": [(_star(), True)],
    "teleporter": [(_box(10, 10, 54, 54), True), (_box(22, 22, 42, 42), True)],
}

DIRECTIONAL = ("arrow_start", "conveyor")


def _smooth_noise(n, amp, rng, scale=14.0):
    t = np.arange(n, dtype=float)
    out = np.zeros(n)
    for k in (1.0, 2.3, 4.1):
        out += rng.uniform(0.4, 1.0) * np.sin(2 * math.pi * t / (scale / k + 1e-6) + rng.uniform(0, 6.28))
    return out * amp / 1.6


def _resample(pts, closed, step):
    pts = list(pts) + ([pts[0]] if closed else [])
    out = []
    for a, b in zip(pts[:-1], pts[1:]):
        n = max(1, int(math.dist(a, b) / step))
        for i in range(n):
            out.append((a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n))
    out.append(pts[-1])
    return out


def glyph_polylines(key, size, rng, wob=0.0, facing=0, rot_deg=None, anis=None, gaps=True):
    k = size / 64.0
    if rot_deg is None:
        rot_deg = rng.uniform(-7, 7)
    if anis is None:
        anis = (rng.uniform(0.88, 1.12), rng.uniform(0.88, 1.12))
    ang = math.radians(rot_deg + (90.0 * facing if key in DIRECTIONAL else 0.0))
    ca, sa = math.cos(ang), math.sin(ang)
    allp = np.array([p for pts, _c in STROKES[key] for p in pts], float)
    ctr = (allp.min(axis=0) + allp.max(axis=0)) / 2
    out = []
    for pts, closed in STROKES[key]:
        rs = _resample(pts, closed, 3.0)
        a = np.array(rs, float) - ctr
        if wob > 0:
            n = len(a)
            a[:, 0] += _smooth_noise(n, wob / k, rng)
            a[:, 1] += _smooth_noise(n, wob / k, rng)
        a[:, 0] *= anis[0] * k
        a[:, 1] *= anis[1] * k
        a = np.stack([a[:, 0] * ca - a[:, 1] * sa, a[:, 0] * sa + a[:, 1] * ca], axis=1)
        if gaps and closed and len(a) > 8 and rng.random() < 0.25:
            a = a[: len(a) - 1]
        out.append((a, closed and not (gaps and len(a) < len(rs))))
    return out


def draw_glyph(img, key, centre, size, pen, rng, wob=0.0, facing=0, **kw):
    xs, ys = [], []
    for a, closed in glyph_polylines(key, size, rng, wob, facing, **kw):
        p = np.round(a + np.array(centre)).astype(np.int32)
        cv2.polylines(img, [p], closed, 0, pen, cv2.LINE_AA)
        xs += list(p[:, 0]); ys += list(p[:, 1])
    return min(xs), min(ys), max(xs), max(ys)


def extent_cells(key, size, cell_px):
    allp = np.array([p for pts, _c in STROKES[key] for p in pts], float)
    wh = (allp.max(axis=0) - allp.min(axis=0)) * size / 64.0 / cell_px
    return float(wh[0]), float(wh[1])
