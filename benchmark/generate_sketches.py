import argparse
import json
import math
import os
import random

import cv2
import numpy as np

PAGE_W, PAGE_H = 1754, 1240
CELL_MM = 8.0
CP = PAGE_W / 297.0 * CELL_MM


def jitter_line(img, p, q, th, wob, rng):
    n = max(int(math.dist(p, q) // 12), 2)
    pts = []
    for i in range(n + 1):
        t = i / n
        x, y = p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t
        if 0 < i < n:
            x += rng.uniform(-wob, wob)
            y += rng.uniform(-wob, wob)
        pts.append((int(round(x)), int(round(y))))
    cv2.polylines(img, [np.array(pts, np.int32)], False, 0, th, cv2.LINE_AA)


def build_spec(rng):
    W, H = rng.randint(18, 30), rng.randint(13, 20)
    walls = []
    for _ in range(rng.randint(1, 2)):
        if rng.random() < 0.5:
            x = rng.randint(5, W - 6)
            gap = rng.randint(3, H - 5)
            walls += [(x, 0, x, gap - 1), (x, gap + 2, x, H - 1)]
        else:
            y = rng.randint(4, H - 5)
            gap = rng.randint(3, W - 5)
            walls += [(0, y, gap - 1, y), (gap + 2, y, W - 1, y)]
    return W, H, walls


def free_cells(W, H, walls, used, margin=2):
    wallcells = set()
    for x1, y1, x2, y2 in walls:
        for x in range(min(x1, x2) - 1, max(x1, x2) + 2):
            for y in range(min(y1, y2) - 1, max(y1, y2) + 2):
                wallcells.add((x, y))
    out = []
    for x in range(margin, W - margin):
        for y in range(margin, H - margin):
            if (x, y) not in wallcells and all(abs(x - u) > 2 or abs(y - v) > 2 for u, v in used):
                out.append((x, y))
    return out


def draw_star(img, c, r, th, rng):
    pts = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * 0.42
        pts.append((c[0] + rr * math.cos(a), c[1] + rr * math.sin(a)))
    pts.append(pts[0])
    cv2.polylines(img, [np.array(pts, np.int32)], False, 0, th, cv2.LINE_AA)


def draw_square(img, c, r, th):
    cv2.rectangle(img, (int(c[0] - r), int(c[1] - r)), (int(c[0] + r), int(c[1] + r)), 0, th, cv2.LINE_AA)


def draw_triangle(img, c, r, th):
    pts = np.array([(c[0], c[1] - r), (c[0] + r * 0.95, c[1] + r * 0.8), (c[0] - r * 0.95, c[1] + r * 0.8)], np.int32)
    cv2.polylines(img, [pts], True, 0, th, cv2.LINE_AA)


def make(idx, seed):
    rng = random.Random(seed * 1000 + idx)
    W, H, walls = build_spec(rng)
    th = rng.choice([3, 4, 5, 6, 8])
    wob = rng.choice([0.0, 1.0, 1.5, 2.2])
    ox = (PAGE_W - W * CP) / 2
    oy = (PAGE_H - H * CP) / 2
    cx = lambda i: ox + (i + 0.5) * CP
    cy = lambda j: oy + (j + 0.5) * CP
    img = np.full((PAGE_H, PAGE_W), 255, np.uint8)
    gt = []
    for a, b in (((0, 0), (W - 1, 0)), ((W - 1, 0), (W - 1, H - 1)), ((W - 1, H - 1), (0, H - 1)), ((0, H - 1), (0, 0))):
        jitter_line(img, (cx(a[0]), cy(a[1])), (cx(b[0]), cy(b[1])), th, wob, rng)
        gt.append(dict(type="boundary", points=[list(a), list(b)]))
    for x1, y1, x2, y2 in walls:
        jitter_line(img, (cx(x1), cy(y1)), (cx(x2), cy(y2)), th, wob, rng)
        gt.append(dict(type="wall", points=[[x1, y1], [x2, y2]]))
    used = []
    spots = free_cells(W, H, walls, used)
    rng.shuffle(spots)

    def take():
        c = spots.pop()
        spots[:] = [s for s in spots if abs(s[0] - c[0]) > 2 or abs(s[1] - c[1]) > 2]
        return c
    s = take()
    draw_star(img, (cx(s[0]), cy(s[1])), CP * 0.62, max(th - 1, 3), rng)
    gt.append(dict(type="symbol", subtype="arrow_start", points=[list(s)]))
    for _ in range(rng.randint(1, 3)):
        if spots:
            s = take()
            draw_square(img, (cx(s[0]), cy(s[1])), CP * 0.5, max(th - 1, 3))
            gt.append(dict(type="interactable", subtype="door", points=[list(s)]))
    if rng.random() < 0.75 and spots:
        s = take()
        draw_triangle(img, (cx(s[0]), cy(s[1])), CP * 0.8, max(th - 1, 3))
        gt.append(dict(type="symbol", subtype="enemy_spawn", points=[list(s)]))
    yy, xx = np.mgrid[0:PAGE_H, 0:PAGE_W].astype(np.float32)
    amp = rng.choice([0.0, 25.0, 50.0, 70.0])
    ang = rng.uniform(0, 2 * math.pi)
    grad = (xx * math.cos(ang) + yy * math.sin(ang)) / PAGE_W
    grad = (grad - grad.min()) / (grad.max() - grad.min() + 1e-6)
    paper = 245.0 - amp * grad
    ink = img.astype(np.float32) / 255.0
    out = paper * ink + 20.0 * (1 - ink)
    out += np.random.RandomState(seed + idx).normal(0, rng.choice([0, 2, 4]), out.shape)
    out = np.clip(out, 0, 255).astype(np.uint8)
    tilt = rng.choice([0.0, 0.0, 0.8, -1.2])
    if tilt:
        M = cv2.getRotationMatrix2D((PAGE_W / 2, PAGE_H / 2), tilt, 1.0)
        out = cv2.warpAffine(out, M, (PAGE_W, PAGE_H), borderValue=int(paper.mean()))
    name = f"sketch_{idx:02d}"
    spec = dict(name=name, image=name + ".png", cell_mm=CELL_MM, grid=[W, H],
                conditions=dict(pen_px=th, wobble_px=wob, light_gradient=amp, tilt_deg=tilt), elements=gt)
    return name, out, spec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=24)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "sketches"))
    ap.add_argument("--seed", type=int, default=11)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    for i in range(1, a.count + 1):
        name, img, spec = make(i, a.seed)
        cv2.imwrite(os.path.join(a.out, name + ".png"), img)
        with open(os.path.join(a.out, name + ".json"), "w", encoding="utf-8") as f:
            json.dump(spec, f, indent=1)
    print(f"wrote {a.count} sketches + annotations to {a.out}")


if __name__ == "__main__":
    main()
