from collections import deque, defaultdict
import cv2
import numpy as np
from .rdp import rdp, max_deviation

NB8 = [(-1, -1), (-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1)]
NAMES = ["P2", "P3", "P4", "P5", "P6", "P7", "P8", "P9"]
S4, S5, S6, S7 = "4. Skeleton graph", "5. Jagged-line test", "6. RDP simplification", "7. Perpendicular snapping"


def crossing_number(sk):
    p = np.pad(sk, 1).astype(np.int16)
    n = [p[:-2, 1:-1], p[:-2, 2:], p[1:-1, 2:], p[2:, 2:], p[2:, 1:-1], p[2:, :-2], p[1:-1, :-2], p[:-2, :-2]]
    A = np.zeros(sk.shape, np.int16)
    for i in range(8):
        A += ((n[i] == 0) & (n[(i + 1) % 8] == 1))
    return A


def explain_crossing(sk, x, y, label):
    p = np.pad(sk, 1)
    r, c = y + 1, x + 1
    v = [int(p[r - 1, c]), int(p[r - 1, c + 1]), int(p[r, c + 1]), int(p[r + 1, c + 1]), int(p[r + 1, c]), int(p[r + 1, c - 1]), int(p[r, c - 1]), int(p[r - 1, c - 1])]
    trans = [f"{NAMES[i]}->{NAMES[(i + 1) % 8]}" for i in range(8) if v[i] == 0 and v[(i + 1) % 8] == 1]
    return [f"{label}: pixel ({x},{y})",
            "  ring P2..P9 (N,NE,E,SE,S,SW,W,NW) = " + " ".join(map(str, v)),
            f"  B = {'+'.join(map(str, v))} = {sum(v)}",
            f"  0->1 transitions around the ring: {', '.join(trans) or 'none'}   =>  A = {len(trans)}"]


def _bfs(start, pix):
    prev, dq, last = {start: None}, deque([start]), start
    while dq:
        u = dq.popleft()
        last = u
        for dx, dy in NB8:
            v = (u[0] + dx, u[1] + dy)
            if v in pix and v not in prev:
                prev[v] = u
                dq.append(v)
    return last, prev


def _walk_loop(pix, start):
    seen, cur, path = {start}, start, [start]
    while True:
        nxt = None
        for dx, dy in NB8[1::2] + NB8[0::2]:
            v = (cur[0] + dx, cur[1] + dy)
            if v in pix and v not in seen:
                nxt = v
                break
        if nxt is None:
            break
        seen.add(nxt)
        path.append(nxt)
        cur = nxt
    return path


def trace_skeleton(skel, cfg, long, st, warnings):
    sk = (skel > 0).astype(np.uint8)
    A = crossing_number(sk)
    ends = (sk == 1) & (A == 1)
    junction = ((sk == 1) & (A >= 3)).astype(np.uint8)
    nj, jl = cv2.connectedComponents(junction, connectivity=8)
    nodes = {}
    for k in range(1, nj):
        ys, xs = np.nonzero(jl == k)
        nodes[k] = (float(xs.mean()), float(ys.mean()))
    jd = cv2.dilate(jl.astype(np.float32), np.ones((7, 7), np.uint8))
    jdil = jd > 0
    halo = cv2.dilate(junction, np.ones((3, 3), np.uint8)) > 0
    bp = ((sk == 1) & ~halo).astype(np.uint8)
    nb, bl = cv2.connectedComponents(bp, connectivity=8)
    ys, xs = np.nonzero(bl)
    labs = bl[ys, xs]
    idx = np.argsort(labs, kind="stable")
    groups = np.split(idx, np.flatnonzero(np.diff(labs[idx])) + 1) if len(idx) else []

    def node_at(p):
        v = int(jd[p[1], p[0]])
        return v if v > 0 else None

    branches = []
    for g in groups:
        pix = {(int(xs[i]), int(ys[i])) for i in g}
        if len(pix) < 2:
            continue
        has_end = any(ends[y, x] or jdil[y, x] for x, y in pix)
        if not has_end and len(pix) >= 8:
            path = _walk_loop(pix, next(iter(pix)))
            branches.append(dict(pts=[tuple(map(float, q)) for q in path], n0=None, n1=None, closed=True))
            continue
        u, _ = _bfs(next(iter(pix)), pix)
        v, prev = _bfs(u, pix)
        path, cur = [], v
        while cur is not None:
            path.append(cur)
            cur = prev[cur]
        branches.append(dict(pts=[tuple(map(float, q)) for q in path], n0=node_at(path[0]), n1=node_at(path[-1]), closed=False))

    def length(b):
        a = np.asarray(b["pts"])
        return float(np.hypot(*np.diff(a, axis=0).T).sum()) if len(a) > 1 else 0.0

    n_raw = len(branches)
    spur_len = cfg.spur_frac * long
    pruned_lines, changed = [], True
    while changed:
        changed = False
        for b in branches:
            if not b["closed"] and (b["n0"] is None) != (b["n1"] is None) and length(b) < spur_len:
                p0 = b["pts"][0]
                pruned_lines.append(f"spur removed near ({p0[0]:.0f},{p0[1]:.0f}): length {length(b):.1f}px < {spur_len:.1f}px and it has a free end")
                branches.remove(b)
                changed = True
                break
    merge_lines, changed = [], True
    while changed:
        changed = False
        inc = defaultdict(list)
        for bi, b in enumerate(branches):
            if b["n0"] is not None:
                inc[b["n0"]].append((bi, 0))
            if b["n1"] is not None:
                inc[b["n1"]].append((bi, 1))
        for nid, lst in inc.items():
            if len(lst) == 2 and lst[0][0] != lst[1][0]:
                (ia, ea), (ib, eb) = lst
                A_, B_ = branches[ia], branches[ib]
                pa = A_["pts"] if ea == 1 else A_["pts"][::-1]
                fa = A_["n0"] if ea == 1 else A_["n1"]
                pb = B_["pts"] if eb == 0 else B_["pts"][::-1]
                fb = B_["n1"] if eb == 0 else B_["n0"]
                new = dict(pts=pa + [nodes[nid]] + pb, n0=fa, n1=fb, closed=False)
                merge_lines.append(f"node {nid} at ({nodes[nid][0]:.0f},{nodes[nid][1]:.0f}) only had 2 branches -> not a real junction, branches joined")
                branches = [b for k, b in enumerate(branches) if k not in (ia, ib)] + [new]
                changed = True
                break
    out, dropped = [], []
    min_len = cfg.min_stroke_frac * long
    for b in branches:
        pts = list(b["pts"])
        if b["n0"] is not None:
            pts = [nodes[b["n0"]]] + pts
        if b["n1"] is not None:
            pts = pts + [nodes[b["n1"]]]
        arr = np.asarray(pts, float)
        L = length(dict(pts=pts))
        if not b["closed"] and b["n0"] is None and b["n1"] is None and L < min_len:
            cx, cy = arr.mean(axis=0)
            dropped.append(f"isolated stroke length {L:.1f}px < {min_len:.1f}px dropped at ({cx:.0f},{cy:.0f})")
            warnings.append(f"fragmented stroke excluded near ({cx/skel.shape[1]*100:.0f}% x, {cy/skel.shape[0]*100:.0f}% y) of the sketch")
            continue
        out.append(dict(path=arr, closed=b["closed"], length=L, n0=b["n0"], n1=b["n1"]))

    ex = []
    e_px = np.argwhere(ends)
    if len(e_px):
        y, x = e_px[len(e_px) // 2]
        ex += explain_crossing(sk, int(x), int(y), "END-POINT example")
    if nodes:
        k = sorted(nodes)[0]
        ys_, xs_ = np.nonzero(jl == k)
        ex += explain_crossing(sk, int(xs_[0]), int(ys_[0]), "JUNCTION example")
    st.block(S4, "4.1 Crossing number: find end points and junctions on the 1-pixel skeleton",
             formula=["Ring P2..P9 = the 8 neighbours of pixel P1, clockwise from North.",
                      "B(P1) = P2 + P3 + ... + P9   (number of skeleton neighbours)",
                      "A(P1) = number of 0 -> 1 transitions in the cyclic sequence P2,P3,...,P9,P2   (= number of separate branches leaving P1)",
                      "A = 1: end point    A = 2: ordinary path pixel    A >= 3: junction"],
             compute=ex + [f"over the whole skeleton ({int(sk.sum())} px): {int(ends.sum())} end pixels (A=1), {int(junction.sum())} junction pixels (A>=3) grouped into {len(nodes)} junction clusters"],
             result=[f"junction clusters (centroids): " + ", ".join(f"#{k}({v[0]:.0f},{v[1]:.0f})" for k, v in list(nodes.items())[:10])],
             visual="Junctions are where walls meet (T / L / + joints). The skeleton is cut at these points into separate branches, so each wall piece can be analysed on its own.")
    st.block(S4, "4.2 Branch extraction",
             formula=["Remove a 3x3 halo around every junction -> remaining skeleton falls apart into branches (8-connected components).",
                      "Order the pixels of each branch: BFS from any pixel to the farthest pixel u, BFS again from u to the farthest pixel v; the shortest path u->v is the ordered branch.",
                      "Closed loops (no end, no junction) are walked around greedily."],
             compute=[f"{nb-1} components after halo removal -> {n_raw} raw branches (closed loops: {sum(1 for b in branches if b['closed'])})"],
             result=f"{n_raw} branches before clean-up",
             visual="Each straight wall piece is now an ordered list of pixel coordinates, ready for shape tests.")
    st.block(S4, "4.3 Clean-up: spur pruning, false junctions, fragments",
             formula=["spur: branch with exactly one free end and  length < spur_frac * long_side   (thinning leaves tiny whiskers at corners)",
                      "false junction: a node that ended up with exactly 2 branches -> join them into one path",
                      "fragment: isolated stroke with length < min_stroke_frac * long_side -> dropped and reported as a warning"],
             compute=[f"spur limit = {cfg.spur_frac}*{long} = {spur_len:.1f}px ; fragment limit = {cfg.min_stroke_frac}*{long} = {min_len:.1f}px",
                      *(pruned_lines or ["no spurs found"]), *(merge_lines or ["no false junctions found"]), *(dropped or ["no fragments dropped"])],
             result=f"{len(out)} clean branches",
             visual="Whiskers and dust specks no longer count as walls; long walls that were split by a false junction become one continuous line again.")
    rows = []
    for i, b in enumerate(out, 1):
        a = b["path"]
        e0 = f"node {b['n0']}" if b["n0"] else f"free end ({a[0][0]:.0f},{a[0][1]:.0f})"
        e1 = f"node {b['n1']}" if b["n1"] else f"free end ({a[-1][0]:.0f},{a[-1][1]:.0f})"
        rows.append(f"B{i}: {len(a)} pts, length {b['length']:.1f}px, {e0} -> {e1}" + ("  [closed loop]" if b["closed"] else ""))
        b["id"] = i
    st.block(S4, "4.4 Branch table", compute=rows[:40] + ([f"... {len(rows)-40} more"] if len(rows) > 40 else []),
             result=f"{len(out)} branches", visual="This is the list of wall pieces the next stages classify (jagged or straight) and simplify.")
    return out


def jag_check(path, amp, min_flips):
    m = path.mean(axis=0)
    c = path - m
    cov = (c.T @ c) / len(c)
    w, v = np.linalg.eigh(cov)
    u = v[:, 1]
    along = c @ u
    span = float(along.max() - along.min())
    d = u[0] * c[:, 1] - u[1] * c[:, 0]
    states, sign = [], 0
    for val in d:
        if abs(val) >= amp:
            s = 1 if val > 0 else -1
            if s != sign:
                states.append(s)
                sign = s
    flips = max(0, len(states) - 1)
    band = float(d.max() - d.min())
    ok = span >= 4 * amp and flips >= max(min_flips, 4) and band <= 0.22 * span
    return dict(ok=ok, flips=flips, span=span, u=u, eig=w[::-1], dmax=float(d.max()), dmin=float(d.min()), states=states, amp=amp, cov=cov, mean=m, d=d)


def vectorize(skel, cfg, long, st, warnings, progress=None):
    if progress:
        progress(0.0, "Tracing skeleton into branches...")
    branches = trace_skeleton(skel, cfg, long, st, warnings)
    eps = max(2.0, cfg.rdp_eps_frac * long)
    amp = max(3.0, cfg.jag_amp_frac * long)
    items, jag_rows, rdp_rows, best, best_trace, best_id = [], [], [], -1, [], 0
    for bi, b in enumerate(branches):
        if progress and bi % 5 == 0:
            progress(0.3 + 0.7 * bi / max(len(branches), 1), f"Simplifying lines (RDP): branch {bi + 1} of {len(branches)}")
        path = b["path"]
        jag, jr = False, None
        if b["closed"]:
            c = path.mean(axis=0)
            i0 = int(np.argmax(np.hypot(*(path - c).T)))
            path = np.vstack([np.roll(path, -i0, axis=0), np.roll(path, -i0, axis=0)[:1]])
        else:
            jr = jag_check(path, amp, cfg.jag_min_flips)
            jag = jr["ok"]
        if jag:
            poly = np.vstack([path[0], path[-1]])
            tr = []
        else:
            tr = []
            poly = rdp(path, eps, trace=tr)
            if len(path) > best:
                best, best_trace, best_id = len(path), tr, b["id"]
        md = max_deviation(path, poly) if len(poly) > 1 and not jag else (0, 0)
        items.append(dict(kind="breakable" if jag else "wall", poly=poly, closed=b["closed"], raw=path, id=b["id"], jr=jr, maxdev=md))
        if jr is not None:
            u, ang = jr["u"], np.degrees(np.arctan2(jr["u"][1], jr["u"][0]))
            dsamp = ", ".join(f"{v:+.1f}" for v in jr["d"][::max(1, len(jr["d"]) // 12)][:12])
            seq = " ".join("+" if s > 0 else "-" for s in jr["states"][:24])
            jag_rows.append([
                f"B{b['id']}: n={len(path)} pts, centroid=({jr['mean'][0]:.1f},{jr['mean'][1]:.1f})",
                f"  covariance = [[{jr['cov'][0,0]:.1f}, {jr['cov'][0,1]:.1f}], [{jr['cov'][1,0]:.1f}, {jr['cov'][1,1]:.1f}]] ; eigenvalues = {jr['eig'][0]:.1f}, {jr['eig'][1]:.1f}",
                f"  principal axis u = ({u[0]:+.3f}, {u[1]:+.3f}) (angle {ang:.1f} deg); span along u = {jr['span']:.1f}px (needs >= 4*{amp:.1f} = {4*amp:.1f})",
                f"  signed deviation d: min {jr['dmin']:+.1f}, max {jr['dmax']:+.1f}px ; samples: {dsamp}",
                f"  sides with |d| >= {amp:.1f}: [{seq}]  -> flips = {jr['flips']} (needs >= {cfg.jag_min_flips})",
                f"  DECISION: {'JAGGED -> breakable wall' if jag else 'straight wall'}"])
    st.block(S5, "5.1 Jagged (breakable) line test, per branch",
             formula=["centroid m = mean of the branch pixels ;   centred points c_i = p_i - m",
                      "covariance  C = (1/n) * sum c_i c_i^T   (2x2) ;   principal axis u = eigenvector of the largest eigenvalue (the line's own direction)",
                      "signed deviation  d_i = u_x*c_iy - u_y*c_ix   (distance of the pixel from the axis line, + one side / - other side)",
                      "side flip: |d| reaches the amplitude threshold on the opposite side from the last time",
                      f"amplitude threshold amp = max(3, {cfg.jag_amp_frac}*long) = {amp:.1f}px ;   JAGGED  <=>  span >= 4*amp  AND  flips >= {cfg.jag_min_flips}"],
             compute=[l for r in jag_rows[:14] for l in r] + ([f"... {len(jag_rows)-14} more branches"] if len(jag_rows) > 14 else []),
             result=f"{sum(1 for i in items if i['kind']=='breakable')} jagged, {sum(1 for i in items if i['kind']=='wall' and not i['closed'])} straight, {sum(1 for i in items if i['closed'])} closed loops",
             visual=["A hand-drawn straight wall wobbles around its axis by only a pixel or two -> few flips -> solid wall.",
                     "A zig-zag crosses its axis many times with large amplitude -> breakable. In the grid map it is drawn orange with a white zig-zag glyph."])

    if best_trace:
        t = best_trace[0]
        a, b2, p = t["a"], t["b"], t["p"]
        num = abs((b2[0] - a[0]) * (a[1] - p[1]) - (b2[1] - a[1]) * (a[0] - p[0]))
        den = float(np.hypot(*(b2 - a)))
        first = [f"worked example on the longest branch (B{best_id}, {t['n']} points), first range:",
                 f"  A = first point ({a[0]:.0f},{a[1]:.0f}) ; B = last point ({b2[0]:.0f},{b2[1]:.0f}) ; |AB| = sqrt(({b2[0]-a[0]:.0f})^2 + ({b2[1]-a[1]:.0f})^2) = {den:.1f}",
                 f"  farthest point P = ({p[0]:.0f},{p[1]:.0f}) (index {t['k']})",
                 f"  d = |(Bx-Ax)(Ay-Py) - (By-Ay)(Ax-Px)| / |AB| = |({b2[0]-a[0]:.0f})({a[1]-p[1]:.0f}) - ({b2[1]-a[1]:.0f})({a[0]-p[0]:.0f})| / {den:.1f} = {num:.1f} / {den:.1f} = {t['d']:.2f}px",
                 f"  compare with epsilon {t['eps']:.1f}px: {'d > eps -> KEEP P, split into A..P and P..B and repeat' if t['split'] else 'd <= eps -> DROP every point between A and B'}"]
        steps = [f"  step {i+1}: idx[{s['s']}..{s['e']}] ({s['e']-s['s']+1} pts) farthest idx {s['k']} d={s['d']:.2f}px vs eps={s['eps']:.1f} -> " + ("keep, split" if s["split"] else "drop") for i, s in enumerate(best_trace[:16])]
        first += ["recursion log (first steps):"] + steps
    else:
        first = ["no non-jagged branch to demonstrate"]
    for it in items:
        if it["kind"] == "wall":
            md = it["maxdev"]
            rdp_rows.append(f"B{it['id']}: {len(it['raw'])} skeleton points -> {len(it['poly'])} vertices ; max deviation of the original from the simplified polyline = {md[0]:.2f}px (<= eps {eps:.1f}) ; mean {md[1]:.2f}px ; vertices {[(round(float(q[0])), round(float(q[1]))) for q in it['poly'][:8]]}")
    raw_total = sum(len(i["raw"]) for i in items if i["kind"] == "wall")
    kept = sum(len(i["poly"]) for i in items if i["kind"] == "wall")
    st.block(S6, "6.1 Ramer-Douglas-Peucker polyline simplification",
             formula=["Keep the first and last point. Find the point P farthest from the line A-B:",
                      "   d(P) = |(Bx-Ax)(Ay-Py) - (By-Ay)(Ax-Px)| / sqrt((Bx-Ax)^2 + (By-Ay)^2)",
                      "If d > epsilon: keep P and recurse on A..P and P..B. Otherwise drop all points between A and B.",
                      f"epsilon = {cfg.rdp_eps_frac}*long = {eps:.1f}px  (max(2, rdp_eps_frac*long))"],
             compute=first + ["per-branch result:"] + rdp_rows[:25],
             result=f"{raw_total} skeleton points -> {kept} vertices (kept {kept/max(raw_total,1)*100:.2f}%) ; guaranteed error <= {eps:.1f}px",
             visual=["Wobbly hand-drawn strokes (hundreds of pixels) turn into a few straight vertices (corners/ends).",
                     "This is what makes the later perpendicular snap reliable: each segment now has just two end points to analyse."])
    return items


def _merge_adjacent(segs, log=None):
    out = []
    for s in segs:
        if out and out[-1]["o"] == s["o"]:
            t = out[-1]
            w = t["w"] + s["w"]
            c_new = (t["c"] * t["w"] + s["c"] * s["w"]) / w
            if log is not None:
                log.append(f"merge two consecutive {s['o']} pieces: c = (c1*w1 + c2*w2)/(w1+w2) = ({t['c']:.1f}*{t['w']:.1f} + {s['c']:.1f}*{s['w']:.1f})/{w:.1f} = {c_new:.1f}")
            t["c"], t["b"], t["w"] = c_new, s["b"], w
        else:
            out.append(dict(s))
    return out


def manhattan(poly, min_len, devs=None, log=None):
    pts = np.asarray(poly, float)
    segs = []
    for p, q in zip(pts[:-1], pts[1:]):
        dx, dy = q - p
        if dx == 0 and dy == 0:
            continue
        theta = float(np.degrees(np.arctan2(min(abs(dx), abs(dy)), max(abs(dx), abs(dy)))))
        if devs is not None:
            devs.append(theta)
        if abs(dx) >= abs(dy):
            segs.append(dict(o="H", c=(p[1] + q[1]) / 2, a=p[0], b=q[0], w=abs(dx)))
            if log is not None:
                log.append(f"({p[0]:.0f},{p[1]:.0f})->({q[0]:.0f},{q[1]:.0f}): dx={dx:.0f}, dy={dy:.0f}; |dx|>=|dy| -> HORIZONTAL; tilt = atan(|dy|/|dx|) = {theta:.2f} deg; y = (y1+y2)/2 = ({p[1]:.1f}+{q[1]:.1f})/2 = {(p[1]+q[1])/2:.1f}")
        else:
            segs.append(dict(o="V", c=(p[0] + q[0]) / 2, a=p[1], b=q[1], w=abs(dy)))
            if log is not None:
                log.append(f"({p[0]:.0f},{p[1]:.0f})->({q[0]:.0f},{q[1]:.0f}): dx={dx:.0f}, dy={dy:.0f}; |dy|>|dx| -> VERTICAL; tilt = atan(|dx|/|dy|) = {theta:.2f} deg; x = (x1+x2)/2 = ({p[0]:.1f}+{q[0]:.1f})/2 = {(p[0]+q[0])/2:.1f}")
    segs = _merge_adjacent(segs, log)
    changed = True
    while changed and len(segs) > 1:
        changed = False
        for i, s in enumerate(segs):
            if abs(s["b"] - s["a"]) < min_len:
                if 0 < i < len(segs) - 1 and segs[i - 1]["o"] == segs[i + 1]["o"]:
                    if log is not None:
                        log.append(f"stub: {s['o']} piece of {abs(s['b']-s['a']):.1f}px < min {min_len:.1f}px between two {segs[i-1]['o']} pieces -> removed (hand wobble)")
                    del segs[i]
                    segs = _merge_adjacent(segs, log)
                    changed = True
                    break
                if i in (0, len(segs) - 1):
                    if log is not None:
                        log.append(f"stub: end piece of {abs(s['b']-s['a']):.1f}px < min {min_len:.1f}px -> removed")
                    del segs[i]
                    changed = True
                    break
    for i in range(len(segs) - 1):
        s, t = segs[i], segs[i + 1]
        if s["o"] != t["o"]:
            s["b"], t["a"] = t["c"], s["c"]
            if log is not None:
                cx, cy = (t["c"], s["c"]) if s["o"] == "H" else (s["c"], t["c"])
                log.append(f"corner between {s['o']} (c={s['c']:.1f}) and {t['o']} (c={t['c']:.1f}) -> intersection (x={cx:.1f}, y={cy:.1f})")
    for s in segs:
        if s["a"] > s["b"]:
            s["a"], s["b"] = s["b"], s["a"]
    return segs


def connect_snap(segs, tol, log=None):
    n = 0
    for s in segs:
        for end in ("a", "b"):
            P = s[end]
            best, bd, bt = None, tol + 1e-9, None
            for t in segs:
                if t is s or t["o"] == s["o"]:
                    continue
                if t["a"] - tol <= s["c"] <= t["b"] + tol and abs(P - t["c"]) <= bd:
                    best, bd, bt = t["c"], abs(P - t["c"]), t
            if best is not None and best != P:
                if log is not None:
                    axis = "x" if s["o"] == "H" else "y"
                    log.append(f"{s['o']} line (c={s['c']:.1f}) end {axis}={P:.1f}: nearest perpendicular wall {bt['o']} at c={bt['c']:.1f} spanning [{bt['a']:.1f},{bt['b']:.1f}]; |{P:.1f}-{bt['c']:.1f}| = {abs(P-best):.1f}px <= tol {tol:.1f}px -> moved to {best:.1f}")
                s[end] = best
                n += 1
    return n
