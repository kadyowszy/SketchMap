import json

import cv2
import numpy as np

from .. import elements as el
from ..gridmap import MapModel, Segment


def load_level(path):
    with open(path, "r", encoding="utf-8") as f:
        d = json.load(f)
    try:
        W, H = int(d["grid_width"]), int(d["grid_height"])
        elements = d["elements"]
    except (KeyError, TypeError, ValueError):
        raise ValueError("This file is not a SketchMap level (grid_width / grid_height / elements are missing).")
    if W < 1 or H < 1:
        raise ValueError("This level has an empty grid.")
    m = MapModel(W, H, dict(d.get("scale") or {}))
    crates = dropped = 0
    for e in elements:
        t, sub, pts = e.get("type"), e.get("subtype"), e.get("points") or []
        try:
            if t in ("wall", "boundary") and len(pts) == 2:
                (x1, y1), (x2, y2) = pts
                seg = Segment("boundary" if t == "boundary" else "wall", int(min(x1, x2)), int(min(y1, y2)), int(max(x1, x2)), int(max(y1, y2)))
                if sub == "breakable" or e.get("breakable"):
                    crates += len(seg.tiles())
                    for xy in seg.tiles():
                        m.objects[xy] = ("breakable_prop", 0)
                else:
                    m.segments.append(seg)
            elif t == "terrain" and pts:
                xy = (int(pts[0][0]), int(pts[0][1]))
                if sub in el.TERRAIN:
                    m.terrain[xy] = (sub, _facing(e))
                else:
                    dropped += 1
            elif t == "symbol" and pts:
                sub = "arrow_start" if sub == "spawn_star" else sub
                if sub in el.SYMBOLS:
                    m.objects[(int(pts[0][0]), int(pts[0][1]))] = (sub, _facing(e))
            elif t == "interactable" and pts:
                sub = "door" if sub in (None, "generic") else sub
                if sub in el.INTERACTABLES:
                    m.objects[(int(pts[0][0]), int(pts[0][1]))] = (sub, 0)
        except (TypeError, ValueError):
            continue
    m.normalize()
    m.edits = 0
    if crates:
        m.notes.append(f"{crates} breakable wall tile(s) were converted to breakable_prop objects.")
    if dropped:
        m.notes.append(f"{dropped} raised-terrain tile(s) were dropped (elevation is not supported).")
    return m


def _facing(e):
    f = e.get("facing", e.get("direction", 0))
    if isinstance(f, str):
        return el.DIRS.index(f) if f in el.DIRS else 0
    return int(f) % 4


def overlay_rgba(model, A, z=24):
    cp, (ox, oy) = A.cell_px, A.origin
    s = z / cp
    M = np.float32([[s, 0, (-ox + 0.5 * cp) * s], [0, s, (-oy + 0.5 * cp) * s]])
    ink = cv2.warpAffine(A.binary, M, (model.width * z, model.height * z), flags=cv2.INTER_AREA, borderValue=0)
    out = np.empty(ink.shape + (4,), np.uint8)
    out[..., 0], out[..., 1], out[..., 2] = 226, 230, 240
    out[..., 3] = (ink.astype(np.float32) * 0.55).astype(np.uint8)
    return out
