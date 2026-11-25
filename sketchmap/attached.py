"""Find box symbols that are drawn *touching* walls (doors, gates, locked doors, push blocks, ...).

A door is usually drawn straight into a wall gap or corridor, so its outline is fused to the wall
strokes. Connected-component labelling then sees ONE big component and the whole thing is treated
as wall, so the symbol is never classified.

What still shows up in that big component is the symbol's interior: small, closed white cells
(a hollow box = 1 cell, a gate = several slim cells, an X block = 4 triangular cells ...), far smaller
than any room. This module:

  1. finds those small enclosed cells inside wall components,
  2. clusters cells that belong to the same box,
  3. checks that the cluster is framed by ink on all four sides (a real box, not a wobbly wall corner),
  4. cuts the box (with its attached wall stubs trimmed at the frame) out of the wall,
  5. hands the cut-out to the normal glyph classifier and keeps it only if it is a box-type symbol.
"""
import math

import cv2
import numpy as np

from .glyphs import classify

BOX_KINDS = {"door", "locked_door", "gate", "push_block", "chest", "breakable_prop", "pressure_plate", "teleporter"}

DEBUG = None                  # set to a list to collect why candidates were kept / rejected


def _dbg(*a):
    if DEBUG is not None:
        DEBUG.append(a)

MAX_CELL_ASPECT = 6.0         # slim gate cells are ~1:3, corridors / double lines are far more elongated
MIN_RECTNESS = 0.78           # cell-cluster hull area / min-area-rectangle area (tolerates a skewed hand-drawn box)
MAX_WINDOW_ASPECT = 2.6


def pen_width(mask):
    """Stroke thickness in px: median of the distance-transform ridge (robust to blobs and junctions)."""
    dt = cv2.distanceTransform(mask, cv2.DIST_L2, 3)
    ridge = (dt > 0) & (dt >= cv2.dilate(dt, np.ones((3, 3), np.uint8)) - 1e-6)
    return max(1.5, 2.0 * float(np.median(dt[ridge]))) if ridge.any() else 2.0


def _frame_ok(ink, x0, y0, x1, y1, m):
    """True if the rectangle (x0,y0)-(x1,y1) is framed by ink on every side (within m px of wobble)."""
    H, W = ink.shape
    cover = []
    for side in range(4):
        if side in (0, 1):            # top / bottom: look along x
            ys = (y0 - m, y0 + 1) if side == 0 else (y1 - 1, y1 + m)
            band = ink[max(ys[0], 0):min(ys[1] + 1, H), max(x0, 0):min(x1 + 1, W)]
            line = band.any(axis=0) if band.size else np.zeros(1, bool)
        else:                         # left / right: look along y
            xs = (x0 - m, x0 + 1) if side == 2 else (x1 - 1, x1 + m)
            band = ink[max(y0, 0):min(y1 + 1, H), max(xs[0], 0):min(xs[1] + 1, W)]
            line = band.any(axis=1) if band.size else np.zeros(1, bool)
        cover.append(float(line.mean()))
    return min(cover) >= FRAME_COVER, cover


def exits(m, wx0, wy0, wx1, wy1, reach=4):
    """Which sides of the window the wall ink continues through: dict of top/bottom/left/right -> bool."""
    H, W = m.shape
    def any_ink(x0, y0, x1, y1):
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, W - 1), min(y1, H - 1)
        return x1 >= x0 and y1 >= y0 and bool(m[y0:y1 + 1, x0:x1 + 1].any())
    return dict(top=any_ink(wx0, wy0 - reach, wx1, wy0 - 1), bottom=any_ink(wx0, wy1 + 1, wx1, wy1 + reach),
                left=any_ink(wx0 - reach, wy0, wx0 - 1, wy1), right=any_ink(wx1 + 1, wy0, wx1 + reach, wy1))


def find_attached(wall_mask, smin, smax, existing=()):
    """Return (symbols, cleaned_wall_mask). Symbols use the same dict layout as segmentation."""
    H, W = wall_mask.shape
    out_syms = []
    cleaned = wall_mask.copy()
    n, lab, stt, _c = cv2.connectedComponentsWithStats(wall_mask, connectivity=8)
    for i in range(1, n):
        x, y, w, h, area = [int(v) for v in stt[i]]
        if max(w, h) <= smax:
            continue                  # small things are handled by the normal symbol path
        pad = 3
        m = np.zeros((h + 2 * pad, w + 2 * pad), np.uint8)
        m[pad:pad + h, pad:pad + w] = (lab[y:y + h, x:x + w] == i).astype(np.uint8)
        t = pen_width(m)
        cn, hr = cv2.findContours(m, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
        if hr is None:
            continue
        min_area = max(10.0, (0.9 * t) ** 2)
        cells = np.zeros_like(m)
        n_cells = 0
        for c, r in zip(cn, hr[0]):
            if r[3] < 0:
                continue
            bx, by, bw, bh = cv2.boundingRect(c)
            a = cv2.contourArea(c)
            if a < min_area or max(bw, bh) > 1.1 * smax:
                continue
            if max(bw, bh) / max(1, min(bw, bh)) > MAX_CELL_ASPECT:
                continue
            cv2.drawContours(cells, [c], -1, 1, -1)
            n_cells += 1
        if not n_cells:
            continue
        # cells of one box are separated by a bar or two (~ one pen width): merge across that
        k = int(round(2.4 * t)) | 1
        grouped = cv2.dilate(cells, cv2.getStructuringElement(cv2.MORPH_RECT, (k, k)))
        gn, glab, gst, _gc = cv2.connectedComponentsWithStats(grouped, connectivity=8)
        for gi in range(1, gn):
            gm = (glab == gi) & (cells > 0)
            if not gm.any():
                continue
            ys_, xs_ = np.nonzero(gm)
            cx0, cx1, cy0, cy1 = int(xs_.min()), int(xs_.max()), int(ys_.min()), int(ys_.max())
            margin = int(math.ceil(t)) + 1
            wx0, wy0, wx1, wy1 = cx0 - margin, cy0 - margin, cx1 + margin, cy1 + margin
            ww, wh = wx1 - wx0 + 1, wy1 - wy0 + 1
            side = max(ww, wh)
            tag = (x + cx0 - pad, y + cy0 - pad, ww, wh)
            if side < 0.85 * smin or side > 1.1 * smax:
                _dbg(tag, "size", side, smin, smax)
                continue
            if max(ww, wh) / max(1, min(ww, wh)) > MAX_WINDOW_ASPECT:
                _dbg(tag, "aspect")
                continue
            pts = np.column_stack([xs_, ys_]).astype(np.float32)
            hull = cv2.convexHull(pts)
            ha = max(cv2.contourArea(hull), 1.0)
            (_rc, (rw_, rh_), _ra) = cv2.minAreaRect(hull)
            rectness = ha / max(rw_ * rh_, 1.0)
            if rectness < MIN_RECTNESS or max(rw_, rh_) / max(min(rw_, rh_), 1.0) > MAX_WINDOW_ASPECT * 1.4:
                _dbg(tag, "not-rectangular", round(rectness, 2))
                continue
            gx0, gy0 = max(wx0, 0), max(wy0, 0)
            gx1, gy1 = min(wx1, m.shape[1] - 1), min(wy1, m.shape[0] - 1)
            crop = (m[gy0:gy1 + 1, gx0:gx1 + 1] * 255).astype(np.uint8)
            res = classify([crop])
            if res["key"] not in BOX_KINDS:
                _dbg(tag, "class", res["key"], res["rules"][-1])
                continue
            _dbg(tag, "ACCEPT", res["key"])
            # image coordinates
            if res["key"] == "door":
                ex = exits(m, wx0, wy0, wx1, wy1)
                straight = (ex["left"] and ex["right"]) or (ex["top"] and ex["bottom"])
                if not straight:
                    _dbg(tag, "door-not-in-a-straight-wall", ex)
                    continue
            ix0, iy0 = x + gx0 - pad, y + gy0 - pad
            iw, ih = gx1 - gx0 + 1, gy1 - gy0 + 1
            if ix0 < 0:
                iw, ix0 = iw + ix0, 0
            if iy0 < 0:
                ih, iy0 = ih + iy0, 0
            bbox = (ix0, iy0, iw, ih)
            sx, sy = ix0 + bbox[2] / 2.0, iy0 + bbox[3] / 2.0
            if any(math.hypot(sx - e["cx"], sy - e["cy"]) < 0.6 * max(bbox[2], bbox[3]) for e in list(existing) + out_syms):
                continue
            out_syms.append(dict(kind=res["key"], cx=sx, cy=sy, bbox=bbox, side=max(bbox[2], bbox[3]), facing=0, comps=[],
                                 attached=True, rules=res["rules"]))
            sub = cleaned[iy0:iy0 + bbox[3], ix0:ix0 + bbox[2]]
            sub[lab[iy0:iy0 + bbox[3], ix0:ix0 + bbox[2]] == i] = 0
    return out_syms, cleaned
