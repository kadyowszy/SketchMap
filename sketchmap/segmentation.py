import cv2
import numpy as np

S2 = "2. Segmentation / symbol classification"
MAX_DETAIL = 25


def _shape_metrics(sub):
    pad = cv2.copyMakeBorder(sub, 3, 3, 3, 3, cv2.BORDER_CONSTANT, value=0)
    cnts, _ = cv2.findContours(pad, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    c = max(cnts, key=cv2.contourArea)
    peri = cv2.arcLength(c, True)
    area = cv2.contourArea(c)
    hull = cv2.convexHull(c)
    harea = max(cv2.contourArea(hull), 1e-6)
    approx = cv2.approxPolyDP(c, 0.05 * peri, True)
    h, w = sub.shape
    depths = []
    try:
        hi = cv2.convexHull(c, returnPoints=False)
        d = cv2.convexityDefects(c, hi)
        if d is not None:
            d = np.asarray(d).reshape(-1, 4)
            depths = sorted((float(x) / 256.0 for x in d[:, 3]), reverse=True)
    except cv2.error:
        pass
    thr = 0.12 * max(w, h)
    return dict(nv=len(approx), solidity=area / harea, aspect=w / h, deep=sum(1 for x in depths if x > thr),
                area=area, harea=harea, peri=peri, depths=depths, thr=thr, w=w, h=h,
                verts=[(int(q[0][0]) - 3, int(q[0][1]) - 3) for q in approx])


def classify_symbol(m):
    ok = lambda b: "PASS" if b else "fail"
    sol, nv, asp, deep = m["solidity"], m["nv"], m["aspect"], m["deep"]
    rules = [
        ("spawn", "STAR", [(f"deep concavities = {deep} >= 4", deep >= 4), (f"solidity = {sol:.3f} < 0.75", sol < 0.75)]),
        ("interactable", "SQUARE", [(f"vertices = {nv} == 4", nv == 4), (f"solidity = {sol:.3f} >= 0.88", sol >= 0.88), (f"aspect = {asp:.2f} within 0.75..1.33", 0.75 <= asp <= 1.33)]),
        ("raised", "TRIANGLE", [(f"vertices = {nv} == 3", nv == 3), (f"solidity = {sol:.3f} >= 0.80", sol >= 0.80)]),
    ]
    lines, kind = [], "unclassified"
    for k, name, checks in rules:
        res = [b for _, b in checks]
        lines.append(f"test {name}: " + " ; ".join(f"{t} [{ok(b)}]" for t, b in checks) + f"  => {'MATCH' if all(res) else 'no'}")
        if all(res) and kind == "unclassified":
            kind = k
    return kind, lines


def segment(binary, cfg, st):
    H, W = binary.shape
    long = max(H, W)
    smin, smax = cfg.symbol_min_frac * long, cfg.symbol_max_frac * long
    n, labels, stt, cents = cv2.connectedComponentsWithStats(binary, connectivity=8)
    wall_mask = np.zeros_like(binary)
    symbols, unclassified, specks = [], [], 0
    sym_blocks, wall_rows = [], []
    for i in range(1, n):
        x, y, w, h, area = [int(v) for v in stt[i]]
        side = max(w, h)
        sub = (labels[y:y + h, x:x + w] == i).astype(np.uint8) * 255
        compact = 0.5 <= w / h <= 2.0
        if side < smin and compact:
            specks += 1
            continue
        if side <= smax and compact:
            m = _shape_metrics(sub)
            kind, rules = classify_symbol(m)
            ys, xs = np.nonzero(sub)
            c = (x + xs.mean(), y + ys.mean())
            if kind == "unclassified":
                unclassified.append(dict(bbox=(x, y, w, h), center=c))
            else:
                symbols.append(dict(kind=kind, cx=c[0], cy=c[1], bbox=(x, y, w, h), side=side))
            dep = ", ".join(f"{d:.1f}" for d in m["depths"][:8]) or "none"
            sym_blocks.append((i, x, y, w, h, area, m, kind, rules, dep, c))
        else:
            wall_mask[labels == i] = 255
            why = f"side {side} > symbol max {smax:.0f}" if side > smax else f"aspect w/h = {w/h:.2f} outside 0.5..2 (elongated)"
            wall_rows.append(f"component #{i}: bbox=({x},{y},{w}x{h}) area={area}px  -> WALL STROKE  ({why})")

    areas = sorted((int(a) for a in stt[1:, cv2.CC_STAT_AREA]), reverse=True)
    st.block(S2, "2.1 Connected-component labelling (8-connectivity)",
             formula=["Two ink pixels belong to the same component if a chain of 8-neighbours (N,NE,E,SE,S,SW,W,NW) links them.",
                      "Each component gets: bounding box (x, y, w, h), area = pixel count, centroid."],
             compute=[f"{n-1} components found; largest areas: {areas[:6]}",
                      f"{specks} tiny compact components ignored as specks (side < {smin:.1f}px)"],
             result=f"{len(sym_blocks)} candidate symbols, {len(wall_rows)} wall-stroke components",
             visual="Each separate drawing (a wall network, a star, a square ...) now has its own label. Anything TOUCHING a wall merges into that wall's component, which is why symbols must be drawn apart from lines.")

    st.block(S2, "2.2 Symbol-size window (decides symbol vs. wall)",
             formula=["symbol candidate  <=>  smin <= max(w,h) <= smax   AND   0.5 <= w/h <= 2",
                      "smin = 1.2% of long side ,  smax = 7% of long side"],
             compute=[f"smin = 0.012*{long} = {smin:.1f}px ;  smax = 0.07*{long} = {smax:.1f}px",
                      f"on A4 this is about {smin*297/long:.1f} mm .. {smax*297/long:.1f} mm"],
             result=f"{len(sym_blocks)} components fall in the window",
             visual="Large or long components can never become symbols, so they all go to the thinning step as wall strokes (Tab 3, dark gray).")

    st.add(S2, "[2.3 Per-symbol contour analysis]")
    st.add(S2, "  FORMULA")
    for l in ["contour C = outer boundary of the component (findContours)",
              "perimeter P = sum of boundary segment lengths ;  A = contour area",
              "polygon = approxPolyDP(C, eps = 0.05*P)   (Douglas-Peucker on the closed outline) ;  vertices = len(polygon)",
              "solidity = A / A_hull   (1.0 = convex shape, small = spiky/concave)",
              "aspect = w / h ;   concavity depth d_k = distance from a hull edge to its deepest contour point; 'deep' if d_k > 0.12*max(w,h)"]:
        st.add(S2, "    " + l)
    st.add(S2, "")
    for (i, x, y, w, h, area, m, kind, rules, dep, c) in sym_blocks[:MAX_DETAIL]:
        st.block(S2, f"component #{i}  ->  {kind.upper()}",
                 compute=[f"bbox=({x},{y},{w}x{h}) area={area}px centroid=({c[0]:.1f},{c[1]:.1f})",
                          f"P = {m['peri']:.1f}px ; eps = 0.05*{m['peri']:.1f} = {0.05*m['peri']:.2f}px ; polygon vertices = {m['nv']} {m['verts'][:8]}",
                          f"A = {m['area']:.0f}, A_hull = {m['harea']:.0f}  ->  solidity = {m['area']:.0f}/{m['harea']:.0f} = {m['solidity']:.3f}",
                          f"aspect = {m['w']}/{m['h']} = {m['aspect']:.2f}",
                          f"concavity depths (px): {dep} ; threshold 0.12*{max(m['w'], m['h'])} = {m['thr']:.1f} -> deep = {m['deep']}",
                          *rules],
                 result=f"classified as {kind}",
                 visual={"spawn": "Tab 3 draws a gold box labelled 'spawn'; the map gets a player start (arrow_start) at this component's centroid tile.",
                         "interactable": "Tab 3 draws a green box labelled 'interactable'; the map gets a door at the centroid tile.",
                         "raised": "Tab 3 draws a blue box labelled 'raised'; the map gets an enemy_spawn at the centroid tile.",
                         "unclassified": "Tab 3 draws a RED box 'unclassified'; it is ignored in the map (redraw it more clearly)."}[kind])
    if len(sym_blocks) > MAX_DETAIL:
        st.add(S2, f"... {len(sym_blocks)-MAX_DETAIL} more symbol candidates not listed")
        st.add(S2, "")
    st.add(S2, "[2.4 Wall-stroke components]")
    for r in wall_rows[:15]:
        st.add(S2, "  " + r)
    if len(wall_rows) > 15:
        st.add(S2, f"  ... {len(wall_rows)-15} more")
    st.add(S2, f"  RESULT: {int((wall_mask>0).sum()):,} ink px sent to Zhang-Suen thinning")
    st.add(S2, "")
    st.add(S2, f"SUMMARY: {sum(1 for s in symbols if s['kind']=='spawn')} star, {sum(1 for s in symbols if s['kind']=='interactable')} square, "
               f"{sum(1 for s in symbols if s['kind']=='raised')} triangle, {len(unclassified)} unclassified, {specks} specks ignored")
    st.add(S2, "")
    return dict(symbols=symbols, wall_mask=wall_mask, unclassified=unclassified)
