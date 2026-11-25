import math
from types import SimpleNamespace

import cv2
import numpy as np

from .rdp import rdp
from .stats import Stats
from .thinning import zhang_suen
from .vectorize import crossing_number

NORM = 112
PAD = 6
DEEP_FRAC = 0.12


def _ell(r):
    r = max(1, int(round(r)))
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))


def normalise(parts):
    h, w = parts[0].shape
    f = NORM / max(h, w)
    nw, nh = max(1, round(w * f)), max(1, round(h * f))
    out = [np.pad((cv2.resize(p, (nw, nh), interpolation=cv2.INTER_CUBIC) > 127).astype(np.uint8), PAD) for p in parts]
    return out, f


TARGET_PEN = 0.055 * NORM


def pen_width(M):
    sk, _ = zhang_suen(M * 255)
    pts = sk > 0
    if not pts.any():
        return 2.0
    dt = cv2.distanceTransform(M, cv2.DIST_L2, 3)
    return 2.0 * float(np.median(dt[pts]))


def thin_parts(norm):
    closed = [cv2.morphologyEx(p, cv2.MORPH_CLOSE, _ell(4)) for p in norm]
    Mc = np.zeros_like(norm[0])
    for p in closed:
        Mc |= p
    t0 = pen_width(Mc)
    r = max(0.0, (t0 - TARGET_PEN) / 2.0)

    def thin(ps):
        return ps if r < 0.6 else [(cv2.distanceTransform(p, cv2.DIST_L2, 3) > r).astype(np.uint8) for p in ps]
    return thin(norm), thin(closed), t0, r


_N8 = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def _nb(sk, p):
    y, x = p
    return [(y + dy, x + dx) for dy, dx in _N8 if sk[y + dy, x + dx]]


def _end_pixels(sk):
    A = crossing_number(sk)
    return [(int(y), int(x)) for y, x in np.argwhere((sk == 1) & (A == 1))]


def _prune(sk, spur):
    sk = sk.copy()
    for _ in range(3):
        changed = False
        for e in _end_pixels(sk):
            if not sk[e]:
                continue
            path, seen, cur, junction = [e], {e}, e, False
            while len(path) <= spur:
                nb = [q for q in _nb(sk, cur) if q not in seen]
                if not nb:
                    break
                groups = []
                for q in nb:
                    for g in groups:
                        if any(max(abs(q[0] - r[0]), abs(q[1] - r[1])) <= 1 for r in g):
                            g.append(q)
                            break
                    else:
                        groups.append([q])
                if len(groups) >= 2:
                    junction = True
                    break
                g = groups[0]
                seen.update(g)
                nxt = max(g, key=lambda q: (q[0] - cur[0]) ** 2 + (q[1] - cur[1]) ** 2)
                path.extend(g)
                cur = nxt
            if junction and len(path) <= spur:
                path.pop()
                for q in path:
                    sk[q] = 0
                changed = True
        if not changed:
            break
    return sk


def bridge_gaps(M, gap):
    G = skeleton_graph(M)
    ends = G["ends"]
    out = M.copy()
    used = set()
    pairs = sorted((math.dist(a, b), i, j) for i, a in enumerate(ends) for j, b in enumerate(ends) if i < j)
    for d, i, j in pairs:
        if d <= gap and i not in used and j not in used:
            used.update((i, j))
            a, b = ends[i], ends[j]
            cv2.line(out, (int(round(a[0])), int(round(a[1]))), (int(round(b[0])), int(round(b[1]))), 1, max(2, int(TARGET_PEN)))
    return out


def skeleton_graph(M):
    sk, _ = zhang_suen(M * 255)
    pts = sk > 0
    dt = cv2.distanceTransform(M, cv2.DIST_L2, 3)
    t = 2.0 * float(np.median(dt[pts])) if pts.any() else 2.0
    spur = max(0.17 * NORM, 2.2 * t)
    sk = _prune(sk, spur)
    ends = [(float(x), float(y)) for y, x in _end_pixels(sk)]
    return dict(t=t, ends=ends, nodes=[], sk=sk, spur=spur)


def outline(M):
    cnts, hier = cv2.findContours(M, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    hier = hier[0]
    outers = [i for i in range(len(cnts)) if hier[i][3] == -1]
    main = max(outers, key=lambda i: cv2.contourArea(cnts[i]))
    c = cnts[main]
    A = max(cv2.contourArea(c), 1.0)
    P = cv2.arcLength(c, True)
    x, y, w, h = cv2.boundingRect(c)
    hull = cv2.convexHull(c)
    HA = max(cv2.contourArea(hull), 1e-6)
    approx = cv2.approxPolyDP(c, 0.05 * P, True)
    (rcx, rcy), (rw, rh), _ang = cv2.minAreaRect(c)
    rw, rh = max(rw, 1.0), max(rh, 1.0)
    depths = []
    try:
        hi = cv2.convexHull(c, returnPoints=False)
        d = cv2.convexityDefects(c, hi)
        if d is not None:
            depths = sorted((float(v) / 256.0 for v in np.asarray(d).reshape(-1, 4)[:, 3]), reverse=True)
    except cv2.error:
        pass
    S = max(w, h)
    deep = sum(1 for v in depths if v > DEEP_FRAC * S)
    raw = [i for i in range(len(cnts)) if hier[i][3] == main and cv2.contourArea(cnts[i]) >= 0.0025 * NORM * NORM]
    big = max((cv2.contourArea(cnts[i]) for i in raw), default=0.0)
    cells = []
    for i in raw:
        a = cv2.contourArea(cnts[i])
        if a < 0.12 * big:
            continue
        (_cc, (rw_, rh_), _aa) = cv2.minAreaRect(cnts[i])
        bx, by, bw, bh = cv2.boundingRect(cnts[i])
        pp = cv2.arcLength(cnts[i], True)
        hnv = len(cv2.approxPolyDP(cnts[i], 0.09 * pp, True))
        cells.append(dict(area=a, rect=a / max(rw_ * rh_, 1.0), asp=bw / max(bh, 1), circ=4 * math.pi * a / max(pp * pp, 1.0),
                          cx=bx + bw / 2.0, cy=by + bh / 2.0, nv=hnv, bw=bw, bh=bh))
    holes = [c["area"] for c in cells]
    filled = np.zeros_like(M)
    cv2.drawContours(filled, [c], -1, 1, -1)
    return dict(c=c, A=A, P=P, w=w, h=h, S=S, x=x, y=y, solidity=A / HA, nv=len(approx),
                circ=4 * math.pi * A / max(P * P, 1.0), rect=A / (rw * rh), rasp=max(rw, rh) / min(rw, rh),
                aspect=w / h, deep=deep, depths=depths, holes=holes, cells=cells, filled=filled, ctr=(x + w / 2.0, y + h / 2.0))


def interior_pieces(M, O, t):
    r = int(round(1.35 * t + 0.03 * NORM))
    inner = cv2.erode(O["filled"], _ell(r))
    content = (M & inner).astype(np.uint8)
    n, lab, st, cen = cv2.connectedComponentsWithStats(content, connectivity=8)
    ys, xs = np.nonzero(inner)
    if not len(xs):
        return [], inner
    span = max(xs.max() - xs.min(), ys.max() - ys.min(), 1)
    pieces = []
    for i in range(1, n):
        x, y, w, h, a = [int(v) for v in st[i]]
        sub = (lab[y:y + h, x:x + w] == i).astype(np.uint8)
        if a < 0.6 * t * t or max(w, h) < 0.12 * span:
            continue
        sp = np.pad(sub, PAD)
        cn, hr = cv2.findContours(sp, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
        hr = hr[0]
        oi = max((k for k in range(len(cn)) if hr[k][3] == -1), key=lambda k: cv2.contourArea(cn[k]))
        holes = [cv2.contourArea(cn[k]) for k in range(len(cn)) if hr[k][3] == oi and cv2.contourArea(cn[k]) >= 0.02 * w * h]
        oc = cn[oi]
        oa = max(cv2.contourArea(oc), 1.0)
        op = cv2.arcLength(oc, True)
        (_c, (rw, rh), _a) = cv2.minAreaRect(oc)
        rw, rh = max(rw, 1.0), max(rh, 1.0)
        mm = cv2.moments(sub, binaryImage=True)
        mu20, mu02, mu11 = mm["mu20"] / mm["m00"], mm["mu02"] / mm["m00"], mm["mu11"] / mm["m00"]
        common = math.sqrt(max(((mu20 - mu02) / 2) ** 2 + mu11 ** 2, 0.0))
        l1, l2 = (mu20 + mu02) / 2 + common, max((mu20 + mu02) / 2 - common, 1e-6)
        theta = math.degrees(0.5 * math.atan2(2 * mu11, mu20 - mu02))
        ang = abs(theta)
        orient = "h" if ang <= 25 else "v" if ang >= 65 else "d"
        g = skeleton_graph(np.pad(sub, PAD)) if not holes and math.sqrt(l1 / l2) < 2.6 else None
        cx, cy = x + w / 2.0, y + h / 2.0
        if not holes and 0.7 <= w / max(h, 1) <= 1.45:
            hull = cv2.convexHull(oc)
            ha = max(cv2.contourArea(hull), 1.0)
            if a < 0.55 * ha and len(sp) and cv2.arcLength(hull, True) > 0:
                (_c2, (hw, hh), _a2) = cv2.minAreaRect(hull)
                hp = cv2.arcLength(hull, True)
                holes = [ha]
                oa, op, rw, rh = ha, hp, max(hw, 1.0), max(hh, 1.0)
        pieces.append(dict(w=w, h=h, area=a, ring=bool(holes), elong=math.sqrt(l1 / l2), orient=orient, theta=theta,
                           circ=4 * math.pi * oa / max(op * op, 1.0), rect=oa / (rw * rh), rasp=max(rw, rh) / min(rw, rh),
                           fill=a / float(w * h), cx=cx, cy=cy, ends=len(g["ends"]) if g else 0,
                           nodes=len(g["nodes"]) if g else 0))
    for p in pieces:
        p["kind"] = _piece_kind(p)
    return pieces, inner


def _piece_kind(p):
    if p["ring"]:
        sh = _ring_shape(p["rect"], p["circ"])
        return "ring_box" if sh == "box" else "ring_round" if sh == "round" else "ring"
    if p["elong"] >= 3.0:
        return "bar_" + p["orient"]
    if p["ends"] >= 4:
        return "x"
    if p["circ"] >= 0.78 and 0.7 <= p["w"] / max(p["h"], 1) <= 1.4:
        return "dot"
    return "blob"


def stroke_part(Mp, t_ref):
    sk, _ = zhang_suen(Mp * 255)
    ys, xs = np.nonzero(sk)
    if len(xs) < 4:
        return None
    pix = {(int(x), int(y)) for x, y in zip(xs, ys)}
    from .vectorize import _bfs
    u, _ = _bfs(next(iter(pix)), pix)
    v, prev = _bfs(u, pix)
    path, cur = [], v
    while cur is not None:
        path.append(cur)
        cur = prev[cur]
    path = np.asarray(path, float)
    L = float(np.hypot(*np.diff(path, axis=0).T).sum())
    a, b = path[0], path[-1]
    chord = float(np.hypot(*(b - a)))
    ext = max(np.ptp(path[:, 0]), np.ptp(path[:, 1]), 1.0)
    d = np.zeros(len(path))
    if chord > 1:
        ux, uy = (b - a) / chord
        d = ux * (path[:, 1] - a[1]) - uy * (path[:, 0] - a[0])
    amp = 0.04 * NORM
    states, sign = [], 0
    for val in d:
        if abs(val) >= amp:
            s = 1 if val > 0 else -1
            if s != sign:
                states.append(s)
                sign = s
    flips = max(0, len(states) - 1)
    eps = max(0.07 * NORM, 1.4 * t_ref)
    poly = rdp(path, eps)
    apex = None
    if len(poly) == 3:
        p0, p1, p2 = poly
        v1, v2 = p0 - p1, p2 - p1
        n1, n2 = np.hypot(*v1), np.hypot(*v2)
        if n1 > 0 and n2 > 0:
            apex = dict(angle=math.degrees(math.acos(np.clip(v1 @ v2 / (n1 * n2), -1, 1))), arms=min(n1, n2) / max(n1, n2),
                        tip=p1, base=(p0 + p2) / 2.0)
    ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 180.0
    turns = [np.sign((poly[i + 1][0] - poly[i][0]) * (poly[i + 2][1] - poly[i + 1][1]) -
                     (poly[i + 1][1] - poly[i][1]) * (poly[i + 2][0] - poly[i + 1][0])) for i in range(len(poly) - 2)]
    zigzag = len(turns) >= 3 and all(turns[i] * turns[i + 1] < 0 for i in range(len(turns) - 1))
    return dict(zigzag=zigzag, len=L, chord=chord, ext=ext, tort=L / max(chord, 1.0), flips=flips, verts=len(poly), apex=apex, angle=ang,
                maxdev=float(np.abs(d).max()), cx=float(path[:, 0].mean()), cy=float(path[:, 1].mean()), path=path)


def _angdiff(a, b):
    d = abs(a - b) % 180.0
    return min(d, 180.0 - d)


def _facing_from(vx, vy):
    return int(round(math.atan2(vy, vx) / (math.pi / 2))) % 4


FACES = ("right", "down", "left", "up")


def _ring_shape(rect, circ):
    return "box" if rect - circ >= 0.04 else "round" if circ >= 0.74 else "ring"


def classify(parts):
    norm0, f = normalise(parts)
    norm_o, norm_c, t0, shrink = thin_parts(norm0)

    def union(ps, rad=1):
        m = np.zeros_like(ps[0])
        for p in ps:
            m |= p
        return cv2.morphologyEx(m, cv2.MORPH_CLOSE, _ell(rad))
    Mo = union(norm_o)
    Mb = bridge_gaps(Mo, 0.20 * NORM)
    if not Mo.any():
        norm_o = norm0
        Mo = Mb = union(norm0)
    O = outline(Mo)
    bridged = False
    Ob = outline(Mb)
    gain = sum(c["area"] for c in Ob["cells"]) - sum(c["area"] for c in O["cells"])
    if (len(Ob["cells"]) > len(O["cells"]) and gain >= 0.10 * Ob["A"]) or Ob["A"] > 1.25 * O["A"]:
        Mc, norm, bridged, O = Mb, norm_o, True, Ob
    else:
        Mc, norm = Mo, norm_o
    G = skeleton_graph(Mc)
    t, ends = G["t"], G["ends"]
    if not bridged and len(O["cells"]) == 0 and len(ends) in (2, 3):
        prs = sorted((math.dist(e1, e2), i, j) for i, e1 in enumerate(ends) for j, e2 in enumerate(ends) if i < j)
        if prs and prs[0][0] <= 0.34 * NORM:
            _d, i1, j1 = prs[0]
            Mx = Mc.copy()
            cv2.line(Mx, (int(round(ends[i1][0])), int(round(ends[i1][1]))), (int(round(ends[j1][0])), int(round(ends[j1][1]))), 1, max(2, int(TARGET_PEN)))
            Ox = outline(Mx)
            if len(Ox["cells"]) == 1 and Ox["solidity"] >= 0.80 and Ox["cells"][0]["area"] >= 0.12 * Ox["A"] and Ox["rasp"] <= 2.3:
                Mc, O, bridged = Mx, Ox, True
                G = skeleton_graph(Mc)
                t, ends = G["t"], G["ends"]
    holes, cells = len(O["cells"]), O["cells"]
    feats = dict(parts=len(parts), holes=holes, ends=len(ends), solidity=O["solidity"], nv=O["nv"], rect=O["rect"],
                 rasp=O["rasp"], circ=O["circ"], deep=O["deep"], t=t, scale=f)
    rules = []
    note = rules.append

    def done(key, facing=0, why=""):
        note(f"=> {key if key else 'unclassified'}{(' (' + why + ')') if why else ''}")
        return dict(key=key, facing=facing, rules=rules, feats=feats)

    note(f"normalised x{f:.2f} to {NORM}px ; pen {t0:.1f}px thinned to {t:.1f}px ; parts = {len(parts)} ; "
         f"closed loops (holes) = {holes}{' (a hairline pen gap was bridged)' if bridged else ''} ; skeleton free ends = {len(ends)}")
    note(f"outline: solidity = {O['solidity']:.2f} ; rectangularity = {O['rect']:.2f} ; rect aspect = {O['rasp']:.2f} ; "
         f"circularity = {O['circ']:.2f} ; polygon vertices = {O['nv']} ; deep concavities = {O['deep']}")

    if len(parts) >= 2 and not any(len(outline(p)["cells"]) for p in norm):
        return _stroke_set(norm, t, rules, feats, done)

    convex = O["solidity"] >= 0.80
    tri = O["nv"] in (3, 4) and convex and O["rect"] < 0.64 and O["rasp"] < 1.7 and holes <= 1 and len(ends) <= 4
    box = convex and not tri and O["rasp"] <= 2.3 and O["rect"] >= 0.72 and O["rect"] - O["circ"] >= 0.04
    rnd = convex and not tri and not box and O["circ"] >= 0.72 and O["rasp"] <= 1.5
    shape = "triangle" if tri else "box" if box else "round" if rnd else None

    if shape:
        note(f"closed convex outline = {shape}")
        pieces, _inner = interior_pieces(Mc, O, t) if holes <= 1 else ([], None)
        if pieces:
            note("ink inside the outline stroke: " + ", ".join(f"{p['kind']}({p['orient']})" for p in pieces))
        if shape == "triangle":
            return done("enemy_spawn", why="empty triangle") if not pieces else done(None, why="triangle with a mark inside")
        if shape == "round":
            if not pieces:
                return done("collectible", why="empty circle")
            if len(pieces) == 1 and pieces[0]["kind"] in ("ring_round", "ring", "dot", "blob"):
                return done("goal_exit", why="circle with a circle/dot inside")
            return done(None, why="circle with something else inside")
        return _box(O, cells, pieces, holes, done, note)

    if holes == 1 and shape is None and not bridged:
        hc = cells[0]
        ext = max(O["w"], O["h"]) / max(hc["bw"], hc["bh"], 1)
        if hc["nv"] == 3 and hc["rect"] < 0.66 and ext <= 1.75 and O["rasp"] < 1.9 and len(ends) <= 4:
            note(f"outline not convex (pen overshoot) but the enclosed cell is a triangle (outline/cell extent {ext:.2f})")
            return done("enemy_spawn", why="empty triangle (cell shape)")

    if holes == 1 and O["rasp"] >= 1.7 and O["rect"] >= 0.28 and cells[0]["circ"] >= 0.5:
        off = math.hypot(cells[0]["cx"] - O["ctr"][0], cells[0]["cy"] - O["ctr"][1]) / max(O["w"], O["h"], 1)
        if off >= 0.2:
            return done("key", why="ring at one end of a shaft")
    if holes == 1 and O["solidity"] < 0.80 and O["rect"] < 0.56 and (
            (O["deep"] >= 3 and len(ends) >= 4 and O["rasp"] < 2.0) or (O["deep"] in (4, 5) and O["rasp"] < 1.3)):
        return done("torch", why="outline with several deep points around one loop (star)")
    if holes == 0 and 2 <= len(ends) <= 5:
        sp = stroke_part(Mc, t)
        if sp is not None:
            note(f"open stroke: {sp['verts']} polyline vertices, corner turns alternate = {sp['zigzag']}")
            if sp["verts"] in (5, 6) and sp["zigzag"] and O["aspect"] >= 0.9:
                pa = sp["path"]
                poly = rdp(pa, max(0.07 * NORM, 1.4 * t))
                ends_y = (poly[0][1] + poly[-1][1]) / 2.0
                mid_y = float(np.mean([q[1] for q in poly[1:-1]]))
                if ends_y > mid_y + 0.06 * NORM:
                    return done("lava", why="open M: the zig-zag starts and ends at the bottom")
                return done("grass", why="W zig-zag of 4 strokes")
    if holes == 0 and len(ends) >= 4 and O["deep"] >= 3 and O["rasp"] < 2.2 and O["solidity"] < 0.5:
        arms = O["deep"]
        if len(ends) >= 7 and arms <= 4:
            return done("torch", why="many strokes around a scribbled centre (star)")
        if arms == 4 and len(ends) <= 6:
            return done("patrol_waypoint", why="4 arms from one crossing")
        if arms >= 5:
            return done("spike_trap", why=f"{arms} arms from one crossing (asterisk)")
        if arms == 3 and len(ends) >= 5:
            return done("torch", why="star with a scribbled centre")
    if holes == 0 and 3 <= len(ends) <= 5 and O["deep"] <= 3:
        iso = [min(math.dist(e, o) for o in ends if o is not e) for e in ends]
        ti = int(np.argmax(iso))
        tail = ends[ti]
        rest = [e for k, e in enumerate(ends) if k != ti]
        mid = (sum(e[0] for e in rest) / len(rest), sum(e[1] for e in rest) / len(rest))
        spread = max(math.dist(a_, b_) for a_ in rest for b_ in rest) / max(math.dist(tail, mid), 1.0)
        note(f"{len(ends)} free ends: tail-to-head distance {math.dist(tail, mid):.0f}px, barb spread ratio {spread:.2f}")
        if spread < 1.1:
            face = _facing_from(mid[0] - tail[0], mid[1] - tail[1])
            return done("arrow_start", face, f"shaft with a two-barb head; faces {FACES[face]}")
    if holes == 0 and len(ends) == 2:
        sp0 = stroke_part(Mc, t)
        if sp0 is not None and sp0["apex"] and sp0["apex"]["angle"] <= 75 and sp0["apex"]["arms"] <= 0.8:
            pa = sp0["path"]
            tip = sp0["apex"]["tip"]
            tail = pa[0] if math.dist(pa[0], tip) > math.dist(pa[-1], tip) else pa[-1]
            face = _facing_from(tip[0] - tail[0], tip[1] - tail[1])
            return done("arrow_start", face, f"shaft with an acute head corner (barbs merged); faces {FACES[face]}")
    if holes == 1:
        hc = cells[0]
        note(f"one loop: hole circularity {hc['circ']:.2f}, hole rectangularity {hc['rect']:.2f}")
        if O["deep"] == 1 and O["solidity"] < 0.85 and O["rect"] >= 0.57 and O["rasp"] < 1.9:
            return done("lava", why="closed crown outline with one dip")
        if (O["rect"] >= 0.40 and hc["circ"] >= 0.70 and O["rasp"] >= 1.6) or (O["rect"] >= 0.28 and hc["circ"] >= 0.50 and O["rasp"] >= 1.9):
            return done("key", why="ring with a long shaft")
        if O["rect"] < 0.40 or (hc["circ"] < 0.80 and O["rect"] < 0.45):
            return done("checkpoint", why="stem with a polygon pennant")
    return done(None, why="no legend entry matches these measurements")


def _box(O, cells, pieces, holes, done, note):
    if holes >= 2:
        rect = float(np.mean([c["rect"] for c in cells]))
        tall = sum(1 for c in cells if c["asp"] < 1.0)
        same = tall in (0, len(cells))
        note(f"{holes} white cells ; mean cell rectangularity {rect:.2f} ; cells all {'tall' if tall == len(cells) else 'wide' if tall == 0 else 'mixed'}")
        if rect >= 0.68 and same:
            return done("chest" if holes == 2 else "locked_door" if holes == 3 else "gate",
                        why=f"{holes - 1} straight divider(s) -> {holes} rectangular cells")
        if holes == 2 and rect < 0.68:
            return done("breakable_prop", why="two triangular cells = one diagonal slash")
        if holes == 4 and not same:
            return done("push_block", why="four triangular cells = an X")
        return done(None, why="box with an unrecognised pattern")
    if not pieces:
        return done("door", why="empty box")
    kinds = [p["kind"] for p in pieces]
    if len(pieces) == 1:
        k = kinds[0]
        if k == "ring_box" or (k == "ring" and False):
            return done("teleporter", why="box inside a box")
        if k in ("ring_round", "ring", "dot"):
            return done("pressure_plate", why="circle inside a box")
        if k == "x":
            return done("push_block", why="X inside a box")
        if k in ("bar_h", "bar_v"):
            return done("chest", why="one straight divider")
        if k == "bar_d":
            return done("breakable_prop", why="one diagonal slash")
        return done(None, why="box with an unrecognised mark")
    if all(k in ("bar_v", "bar_h") for k in kinds) and len(set(kinds)) == 1:
        return done("locked_door" if len(pieces) == 2 else "gate", why=f"{len(pieces)} loose parallel bars")
    if len(pieces) == 2 and all(k == "bar_d" for k in kinds):
        return done("push_block", why="two diagonal bars (an X drawn in two strokes)")
    return done(None, why="box with an unrecognised pattern")


def _stroke_set(norm, t, rules, feats, done):
    info = [stroke_part(p, t) for p in norm]
    if any(i is None for i in info):
        return done(None, why="a stroke too small to measure")
    for k, i in enumerate(info, 1):
        ap = f", apex {i['apex']['angle']:.0f} deg" if i["apex"] else ""
        rules.append(f"stroke {k}: length {i['len']:.0f}px, tortuosity {i['tort']:.2f}, vertices {i['verts']}, flips {i['flips']}, "
                     f"angle {i['angle']:.0f} deg{ap}")
    n = len(info)

    def kind(i):
        if i["apex"] and 40 <= i["apex"]["angle"] <= 155 and i["apex"]["arms"] >= 0.5 and i["flips"] <= 2:
            return "chevron"
        if 1.17 <= i["tort"] < 2.6 and (i["flips"] >= 1 or i["verts"] >= 4):
            return "wave"
        if i["tort"] < 1.16 and (i["verts"] <= 2 or (i["apex"] and i["apex"]["angle"] >= 140)):
            return "straight"
        return "other"
    kinds = [kind(i) for i in info]
    rules.append("stroke kinds: " + ", ".join(kinds))
    ang0 = info[0]["angle"]
    parallel = all(_angdiff(i["angle"], ang0) <= 25 for i in info)
    if all(k == "straight" for k in kinds) and parallel:
        horizontal = _angdiff(ang0, 0) <= 25
        if n == 2 and not horizontal:
            return done("ice", why="two parallel slashes")
        if 3 <= n <= 8 and horizontal:
            return done("mud", why=f"{n} parallel horizontal bars")
    if all(k == "wave" for k in kinds) and 2 <= n <= 4 and _angdiff(ang0, 0) <= 35:
        return done("water", why=f"{n} stacked wavy lines")
    if all(k == "chevron" for k in kinds) and n == 2:
        dirs = [(i["apex"]["tip"] - i["apex"]["base"]) for i in info]
        v = dirs[0] + dirs[1]
        a0, a1 = math.degrees(math.atan2(dirs[0][1], dirs[0][0])), math.degrees(math.atan2(dirs[1][1], dirs[1][0]))
        if abs((a0 - a1 + 180) % 360 - 180) <= 35:
            face = _facing_from(v[0], v[1])
            return done("conveyor", face, "double chevron pointing " + ("right", "down", "left", "up")[face])
    arrow = _arrow_from_strokes(info, kinds, n)
    if arrow is not None:
        face, why = arrow
        return done("arrow_start", face, why)
    return done(None, why="strokes do not form a legend entry")


def _vec_angle(u, v):
    nu, nv = math.hypot(*u), math.hypot(*v)
    if nu < 1e-6 or nv < 1e-6:
        return 180.0
    return math.degrees(math.acos(float(np.clip((u[0] * v[0] + u[1] * v[1]) / (nu * nv), -1, 1))))


def _arrow_from_strokes(info, kinds, n):
    """An arrow drawn as SEPARATE strokes (the pen lifts between shaft and head, which is very common):
         2 strokes: a straight shaft + a '>' chevron head whose tip points away from the shaft's far end
         3 strokes: a straight shaft + two short barbs that meet near one end of the shaft
       Returns (facing, why) or None."""
    if n == 2:
        ch = [k for k, kd in enumerate(kinds) if kd == "chevron"]
        sh = [k for k, kd in enumerate(kinds) if kd == "straight"]
        if len(ch) != 1 or len(sh) != 1:
            return None
        head, shaft = info[ch[0]], info[sh[0]]
        tip, base = head["apex"]["tip"], head["apex"]["base"]
        pa = shaft["path"]
        d0, d1 = math.dist(pa[0], tip), math.dist(pa[-1], tip)
        near, far = (pa[0], pa[-1]) if d0 <= d1 else (pa[-1], pa[0])
        gap = min(d0, d1)
        span = math.dist(base, tip)
        if shaft["len"] < 0.9 * span or gap > 1.1 * shaft["len"]:
            return None
        v = np.asarray(tip) - np.asarray(far)
        if _vec_angle(v, np.asarray(tip) - np.asarray(base)) > 55:
            return None
        face = _facing_from(v[0], v[1])
        return face, f"shaft + separate chevron head; faces {FACES[face]}"
    if n == 3:
        order = sorted(range(3), key=lambda k: -info[k]["len"])
        shaft, b1, b2 = info[order[0]], info[order[1]], info[order[2]]
        if shaft["tort"] >= 1.3 or shaft["len"] < 1.3 * max(b1["len"], b2["len"]):
            return None
        pa = shaft["path"]
        ends = (np.asarray(pa[0]), np.asarray(pa[-1]))
        bar = [np.asarray(b["path"][0]) for b in (b1, b2)] + [np.asarray(b["path"][-1]) for b in (b1, b2)]
        for tip_i in (0, 1):
            tip, far = ends[tip_i], ends[1 - tip_i]
            # each barb must start near the shaft tip and lie on the tail side of it
            near_pts, outer_pts = [], []
            for b in (b1, b2):
                p0, p1 = np.asarray(b["path"][0]), np.asarray(b["path"][-1])
                a, c = (p0, p1) if np.linalg.norm(p0 - tip) <= np.linalg.norm(p1 - tip) else (p1, p0)
                near_pts.append(np.linalg.norm(a - tip))
                outer_pts.append(c)
            if max(near_pts) > 0.55 * shaft["len"]:
                continue
            back = far - tip
            if all(_vec_angle(c - tip, back) < 80 for c in outer_pts):
                v = tip - far
                face = _facing_from(v[0], v[1])
                return face, f"shaft + two separate barbs; faces {FACES[face]}"
    return None
