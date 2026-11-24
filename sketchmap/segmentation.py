import cv2
import numpy as np

from . import elements as el
from .glyphs import classify

S2 = "2. Segmentation / symbol classification"
MAX_DETAIL = 25
FACES = ("right", "down", "left", "up")


class _DSU:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, a):
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def union(self, a, b):
        self.p[self.find(a)] = self.find(b)


def _close_enough(ci, cj, gap):
    xi, yi, wi, hi = ci["box"]
    xj, yj, wj, hj = cj["box"]
    if xi - gap > xj + wj or xj - gap > xi + wi or yi - gap > yj + hj or yj - gap > yi + hi:
        return False
    x0, y0 = min(xi, xj) - gap - 1, min(yi, yj) - gap - 1
    x1, y1 = max(xi + wi, xj + wj) + gap + 1, max(yi + hi, yj + hj) + gap + 1
    a = np.zeros((y1 - y0, x1 - x0), np.uint8)
    b = np.zeros_like(a)
    a[yi - y0:yi - y0 + hi, xi - x0:xi - x0 + wi] = ci["mask"]
    b[yj - y0:yj - y0 + hj, xj - x0:xj - x0 + wj] = cj["mask"]
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * gap + 1, 2 * gap + 1))
    return bool((cv2.dilate(a, k) & b).any())


def segment(binary, cfg, st):
    H, W = binary.shape
    long = max(H, W)
    smin, smax = cfg.symbol_min_frac * long, cfg.symbol_max_frac * long
    n, labels, stt, cents = cv2.connectedComponentsWithStats(binary, connectivity=8)
    wall_mask = np.zeros_like(binary)
    symbols, unclassified, specks = [], [], 0
    groups_log, wall_rows = [], []

    comps = {}
    for i in range(1, n):
        x, y, w, h, area = [int(v) for v in stt[i]]
        side = max(w, h)
        compact = 0.5 <= w / h <= 2.0
        if side > smax:
            wall_mask[labels == i] = 255
            wall_rows.append(f"component #{i}: bbox=({x},{y},{w}x{h}) area={area}px  -> WALL STROKE  (side {side} > symbol max {smax:.0f})")
            continue
        if side < 0.6 * smin or (side < smin and not compact and area < 2 * smin):
            if not compact:
                wall_mask[labels == i] = 255
                wall_rows.append(f"component #{i}: bbox=({x},{y},{w}x{h}) area={area}px  -> WALL STROKE  (tiny and elongated)")
            else:
                specks += 1
            continue
        mask = (labels[y:y + h, x:x + w] == i).astype(np.uint8) * 255
        pad = cv2.copyMakeBorder(mask, 2, 2, 2, 2, cv2.BORDER_CONSTANT, value=0)
        cn, hr = cv2.findContours(pad, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
        closed = hr is not None and any(r[3] >= 0 for r in hr[0])
        container = closed
        filled = np.zeros_like(pad)
        outer = [c for c, r in zip(cn, hr[0]) if r[3] < 0]
        cv2.drawContours(filled, outer, -1, 255, -1)
        if not closed and compact and w >= 0.5 * smin:
            hull = cv2.convexHull(np.vstack(outer))
            hfill = np.zeros_like(pad)
            cv2.fillConvexPoly(hfill, hull, 255)
            if area < 0.55 * int((hfill > 0).sum()) and 0.7 <= w / h <= 1.45 and cv2.contourArea(hull) > 0.6 * w * h * 0.7:
                container, filled = True, hfill
        comps[i] = dict(id=i, box=(x, y, w, h), side=side, area=area, mask=mask, closed=closed, container=container, compact=compact, speck=side < smin and compact,
                        filled=filled[2:-2, 2:-2], cx=x + w / 2.0, cy=y + h / 2.0)

    ids = list(comps)
    dsu = _DSU(n)
    links = 0
    for i in ids:
        ci = comps[i]
        if not ci["container"]:
            continue
        xi, yi, wi, hi = ci["box"]
        for j in ids:
            if j == i:
                continue
            cj = comps[j]
            lx, ly = int(round(cj["cx"] - xi)), int(round(cj["cy"] - yi))
            if 0 <= lx < wi and 0 <= ly < hi and ci["filled"][ly, lx] and cj["area"] < ci["area"]:
                dsu.union(i, j)
                links += 1
    def build(mem):
        x0 = min(comps[m]["box"][0] for m in mem)
        y0 = min(comps[m]["box"][1] for m in mem)
        x1 = max(comps[m]["box"][0] + comps[m]["box"][2] for m in mem)
        y1 = max(comps[m]["box"][1] + comps[m]["box"][3] for m in mem)
        parts = []
        for m in mem:
            c = comps[m]
            full = np.zeros((y1 - y0, x1 - x0), np.uint8)
            bx, by, bw, bh = c["box"]
            full[by - y0:by - y0 + bh, bx - x0:bx - x0 + bw] = c["mask"]
            parts.append(full)
        return (x0, y0, x1 - x0, y1 - y0), parts

    COMPLETE = {"collectible", "enemy_spawn", "goal_exit", "door", "chest", "locked_door", "gate", "push_block", "breakable_prop",
                "pressure_plate", "teleporter", "torch", "spike_trap", "patrol_waypoint", "key", "checkpoint"}
    complete = {}
    for i in ids:
        ci = comps[i]
        if ci["speck"] or max(ci["box"][2], ci["box"][3]) < smin or max(ci["box"][2], ci["box"][3]) > smax:
            complete[i] = False
            continue
        complete[i] = classify(build([i])[1])["key"] in COMPLETE
    for a_i, i in enumerate(ids):
        ci = comps[i]
        if ci["closed"] or ci["speck"] or complete[i]:
            continue
        for j in ids[a_i + 1:]:
            cj = comps[j]
            if cj["closed"] or cj["speck"] or complete[i] or complete[j] or (ci["container"] and cj["container"]):
                continue
            gap = int(round(min(max(0.55 * max(ci["side"], cj["side"]), 0.5 * smin), 0.04 * long)))
            if _close_enough(ci, cj, gap):
                dsu.union(i, j)
                links += 1
    members = {}
    for i in ids:
        members.setdefault(dsu.find(i), []).append(i)

    for root, mem in members.items():
        real = [m for m in mem if not comps[m]["speck"]]
        if not real:
            specks += len(mem)
            continue
        out = None
        box, parts = build(mem)
        if max(box[2], box[3]) <= smax * 1.25:
            res = classify(parts)
            out = (mem, box, res)
        if (out is None or out[2]["key"] is None) and len(real) > 1:
            sub = []
            for m in real:
                inner = [k for k in mem if k == m or (comps[m]["container"] and comps[k]["speck"] and
                         comps[m]["filled"][min(max(int(comps[k]["cy"] - comps[m]["box"][1]), 0), comps[m]["box"][3] - 1),
                                            min(max(int(comps[k]["cx"] - comps[m]["box"][0]), 0), comps[m]["box"][2] - 1)])]
                b2, p2 = build(inner)
                if max(b2[2], b2[3]) >= smin:
                    sub.append((inner, b2, classify(p2)))
            if sub and any(r["key"] for _m, _b, r in sub):
                for m_, b_, r_ in sub:
                    groups_log.append((m_, b_, r_, "tried on its own because the stroke group matched nothing"))
                continue_groups = sub
            else:
                continue_groups = None
        else:
            continue_groups = None
        if continue_groups is not None:
            for m_, b_, r_ in continue_groups:
                _emit(m_, b_, r_, comps, symbols, unclassified, wall_mask, labels, wall_rows)
            continue
        if out is None:
            for m in mem:
                wall_mask[labels == m] = 255
            wall_rows.append(f"components {mem}: group too large for a symbol -> WALL STROKE")
            continue
        m_, b_, r_ = out
        groups_log.append((m_, b_, r_, ""))
        _emit(m_, b_, r_, comps, symbols, unclassified, wall_mask, labels, wall_rows)

    areas = sorted((int(a) for a in stt[1:, cv2.CC_STAT_AREA]), reverse=True)
    st.block(S2, "2.1 Connected-component labelling (8-connectivity)",
             formula=["Two ink pixels belong to the same component if a chain of 8-neighbours (N,NE,E,SE,S,SW,W,NW) links them.",
                      "Each component gets: bounding box (x, y, w, h), area = pixel count, centroid."],
             compute=[f"{n-1} components found; largest areas: {areas[:6]}",
                      f"{specks} tiny compact components ignored as specks (side < {smin:.1f}px)"],
             result=f"{len(groups_log)} symbol groups, {len(wall_rows)} wall-stroke components",
             visual="Each separate drawing (a wall network, a star, a square ...) now has its own label. Anything TOUCHING a wall merges into that wall's component, which is why symbols must be drawn apart from lines.")

    st.block(S2, "2.2 Symbol-size window and stroke grouping",
             formula=["symbol candidate  <=>  max(w,h) <= smax  (larger components are walls)",
                      "smin = 1.2% of long side ,  smax = 7% of long side",
                      "multi-stroke symbols (ice //, mud, water, conveyor >>, nested circles / boxes, a mark inside a box) are joined:",
                      "   (a) a component whose centre lies inside the filled outline of a closed component belongs to it",
                      "   (b) two OPEN strokes closer than 0.55 x the longer one's size (at most 4% of the long side) belong together"],
             compute=[f"smin = 0.012*{long} = {smin:.1f}px ;  smax = 0.07*{long} = {smax:.1f}px",
                      f"on A4 this is about {smin*297/long:.1f} mm .. {smax*297/long:.1f} mm",
                      f"{links} links made between components"],
             result=f"{len(groups_log)} symbol groups to classify",
             visual="Large or long components can never become symbols, so they all go to the thinning step as wall strokes (Tab 3, dark gray). Leave a clear gap (at least half a symbol's width) between neighbouring symbols so they are not joined.")

    st.add(S2, "[2.3 Per-symbol analysis]")
    st.add(S2, "  FORMULA")
    for l in ["Each symbol is rescaled so its long side is 112 px and its pen is thinned to a fixed relative width, so size and pen thickness do not matter.",
              "Measured: closed loops (holes), skeleton free ends, outline solidity / rectangularity / circularity, polygon vertices (approxPolyDP, eps = 5% of perimeter),",
              "          deep convexity defects (> 12% of size), the white cells inside a box, loose ink inside an outline, and for stroke sets: tortuosity, corners, parallelism.",
              "The legend (Library page) is then tested in a fixed order; the trace below shows every measurement that led to the decision."]:
        st.add(S2, "    " + l)
    st.add(S2, "")
    for (mem, box, res, note) in groups_log[:MAX_DETAIL]:
        key = res["key"]
        st.block(S2, f"components {mem}  ->  {(key or 'unclassified').upper()}{'  facing ' + FACES[res['facing']] if key and el.is_directional(key) else ''}",
                 compute=[f"group bbox=({box[0]},{box[1]},{box[2]}x{box[3]})" + (f"  [{note}]" if note else "")] + res["rules"],
                 result=f"classified as {key or 'unclassified'}",
                 visual=("Tab 3 draws a coloured box labelled with the symbol; the map gets that element on the tile under the symbol's centre."
                         if key else "Tab 3 draws a RED box 'unclassified'; it is ignored in the map (redraw it more clearly)."))
    if len(groups_log) > MAX_DETAIL:
        st.add(S2, f"... {len(groups_log)-MAX_DETAIL} more symbol groups not listed")
        st.add(S2, "")
    st.add(S2, "[2.4 Wall-stroke components]")
    for r in wall_rows[:15]:
        st.add(S2, "  " + r)
    if len(wall_rows) > 15:
        st.add(S2, f"  ... {len(wall_rows)-15} more")
    st.add(S2, f"  RESULT: {int((wall_mask>0).sum()):,} ink px sent to Zhang-Suen thinning")
    st.add(S2, "")
    counts = {}
    for sy in symbols:
        counts[sy["kind"]] = counts.get(sy["kind"], 0) + 1
    st.add(S2, "SUMMARY: " + (", ".join(f"{v} {k}" for k, v in sorted(counts.items())) or "no symbols") +
           f", {len(unclassified)} unclassified, {specks} specks ignored")
    st.add(S2, "")
    return dict(symbols=symbols, wall_mask=wall_mask, unclassified=unclassified)


def _emit(mem, box, res, comps, symbols, unclassified, wall_mask, labels, wall_rows):
    x, y, w, h = box
    c = (x + w / 2.0, y + h / 2.0)
    if res["key"]:
        symbols.append(dict(kind=res["key"], cx=c[0], cy=c[1], bbox=box, side=max(w, h), facing=res["facing"], comps=list(mem)))
        return
    solo = len([m for m in mem if not comps[m]["speck"]]) == 1
    only = comps[[m for m in mem if not comps[m]["speck"]][0]] if solo else None
    if only is not None and not only["compact"]:
        for m in mem:
            wall_mask[labels == m] = 255
        wall_rows.append(f"components {mem}: bbox={box} -> WALL STROKE  (elongated, matches no symbol)")
    else:
        unclassified.append(dict(bbox=box, center=c))
