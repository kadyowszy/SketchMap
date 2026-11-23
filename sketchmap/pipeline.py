import re
from types import SimpleNamespace
import cv2
import numpy as np
from .config import Config, PreprocessParams, A4_LONG_MM
from .stats import Stats
from .preprocess import load_image, preprocess, preprocess_with_params, run_preprocessing, straighten_paper, resize_image
from .segmentation import segment
from .thinning import zhang_suen
from .vectorize import vectorize, manhattan, connect_snap, S7
from .gridmap import MapModel, Segment


S3 = "3. Zhang-Suen thinning"
S8 = "8. Scale + grid mapping"


def _zs_example(ex, title, removed):
    v = ex["vals"]
    P2, P3, P4, P5, P6, P7, P8, P9 = v
    step = ex["step"]
    if step == 0:
        c1, c2 = P2 * P4 * P6, P4 * P6 * P8
        t1, t2 = f"P2*P4*P6 = {P2}*{P4}*{P6} = {c1}", f"P4*P6*P8 = {P4}*{P6}*{P8} = {c2}"
    else:
        c1, c2 = P2 * P4 * P8, P2 * P6 * P8
        t1, t2 = f"P2*P4*P8 = {P2}*{P4}*{P8} = {c1}", f"P2*P6*P8 = {P2}*{P6}*{P8} = {c2}"
    B, A = ex["B"], ex["A"]
    checks = [(f"(a) 2 <= B <= 6: B = {'+'.join(map(str, v))} = {B}", 2 <= B <= 6), (f"(b) A = 1: A = {A}", A == 1),
              (f"(c) {t1} == 0", c1 == 0), (f"(d) {t2} == 0", c2 == 0)]
    lines = [f"pixel ({ex['pos'][0]},{ex['pos'][1]}), sub-iteration {step+1}, ring P2..P9 = {' '.join(map(str, v))}"]
    lines += [f"{t}   -> {'PASS' if ok else 'FAIL'}" for t, ok in checks]
    fail = [t[:3] for t, ok in checks if not ok]
    lines.append("all four conditions pass -> pixel is DELETED" if removed else f"condition(s) {', '.join(fail)} fail -> pixel is KEPT")
    return lines


def thinning_stats(info, st):
    st.block(S3, "3.1 Zhang-Suen rules",
             formula=["Neighbour labels around P1:      P9 P2 P3",
                      "                                 P8 P1 P4",
                      "                                 P7 P6 P5",
                      "B(P1) = P2+P3+...+P9 ;  A(P1) = number of 0->1 transitions in P2,P3,...,P9,P2",
                      "Sub-iteration 1: delete P1 if (a) 2<=B<=6 (b) A=1 (c) P2*P4*P6=0 (d) P4*P6*P8=0   (removes south-east boundary and north-west corners)",
                      "Sub-iteration 2: delete P1 if (a) 2<=B<=6 (b) A=1 (c) P2*P4*P8=0 (d) P2*P6*P8=0   (removes north-west boundary and south-east corners)",
                      "Repeat both sub-iterations until nothing is deleted.",
                      "Why: (a) keeps end points (B=1) and interior pixels (B=7,8); (b) keeps the pixel if deleting it would break the line into two pieces (A>=2)."],
             visual="All deletions happen in parallel on a frozen copy of the image, so the thinning is symmetric (no left/top bias).")
    if info["ex_removed"]:
        st.block(S3, "3.2 Worked example: a pixel that gets deleted", compute=_zs_example(info["ex_removed"], "", True),
                 result="This boundary pixel is not needed to keep the stroke connected, so it is removed.",
                 visual="One layer of pixels peels off the outer edge of the thick pen stroke.")
    if info["ex_kept"]:
        st.block(S3, "3.3 Worked example: a pixel that is kept", compute=_zs_example(info["ex_kept"], "", False),
                 result="Deleting this pixel would disconnect or shorten the line, so it stays.",
                 visual="This is how corners, junctions and end points survive thinning (SRS 3.2.3.3: structural connectivity is preserved).")
    rows = [f"start: {info['start_px']:,} ink px"]
    for i, ((a, b), rem) in enumerate(zip(info["removed"], info["remaining"]), 1):
        rows.append(f"iteration {i:2d}: sub-iter 1 removed {a:6,} ; sub-iter 2 removed {b:6,} ; remaining {rem:6,}")
    avg = info["start_px"] / max(info["end_px"], 1)
    st.block(S3, "3.4 Iteration table", compute=rows,
             result=[f"{info['start_px']:,} -> {info['end_px']:,} px ({(1-info['end_px']/max(info['start_px'],1))*100:.1f}% removed) in {info['iterations']} iterations (last one removes 0 = converged)"],
             visual=[f"Average stroke width ~ area / length = {info['start_px']:,} / {info['end_px']:,} = {avg:.1f}px  ->  1px after thinning.",
                     "Tab 4 shows the red 1-pixel centre lines: they sit in the middle of every pen stroke."])


MIN_CONTRAST = 40
NOISY_SYMBOL_COUNT = 150


def _check_contrast(bgr):
    g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY) if bgr.ndim == 3 else bgr
    spread = float(np.median(g)) - float(np.percentile(g, 0.1))
    if spread < MIN_CONTRAST:
        raise ValueError("The sketch could not be segmented: the image has too little contrast "
                         f"(ink-to-paper difference {spread:.0f} of 255, needs at least {MIN_CONTRAST}). "
                         "Redraw with a black pen on white A4 paper in even light.")


def run_stage_a(bgr, cfg, st, progress=None, prep_params=None):
    prog = progress or (lambda pct, text: None)
    _check_contrast(bgr)
    prog(8, "Stage 2/6: Cleaning lighting and binarizing (Otsu)...")
    with st.timer("1 preprocess"):
        P = preprocess_with_params(bgr, cfg, st, prep_params) if prep_params is not None else preprocess(bgr, cfg, st)
    warnings = list(P["warnings"])
    if P["warnings"] and "no recognizable" in P["warnings"][0]:
        raise ValueError("The sketch could not be segmented: " + P["warnings"][0])
    prog(20, "Stage 3/6: Finding symbols and walls...")
    with st.timer("2 segment+classify"):
        S = segment(P["binary"], cfg, st)
    if not S["symbols"] and not S["wall_mask"].any():
        raise ValueError("The sketch could not be segmented: no recognizable features.")
    if len(S["symbols"]) + len(S["unclassified"]) > NOISY_SYMBOL_COUNT:
        warnings.append(f"{len(S['symbols']) + len(S['unclassified'])} small shapes were found, which usually means "
                        "speckled paper or uneven lighting. Check the Prepare step (shadow removal, threshold).")
    prog(35, "Stage 4/6: Thinning strokes to 1px (Zhang-Suen)...")
    with st.timer("3 Zhang-Suen"):
        skel, info = zhang_suen(S["wall_mask"], progress=lambda f, t: prog(35 + int(f * 40), "Stage 4/6: " + t))
    thinning_stats(info, st)
    prog(75, "Stage 5/6: Vectorizing lines...")
    with st.timer("4-6 trace+jagged+RDP"):
        items = vectorize(skel, cfg, P["long"], st, warnings,
                          progress=lambda f, t: prog(75 + int(f * 15), "Stage 5/6: " + t))
    ys, xs = np.nonzero(P["binary"])
    bbox = (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))
    A = SimpleNamespace(cfg=cfg, work=P["work"], gray=P["gray"], binary=P["binary"], skel=skel, items=items,
                        symbols=S["symbols"], unclassified=S["unclassified"], wall_mask=S["wall_mask"], bbox=bbox,
                        long=P["long"], warnings=warnings,
                        mm_per_px=A4_LONG_MM / P["long"], cell_px=1.0, origin=(0, 0))
    A.previews = make_previews(A)
    return A


def suggest_cell_mm(A):
    sizes = [s["side"] for s in A.symbols]
    return float(np.median(sizes) * A.mm_per_px) if len(sizes) >= 2 else None


def build_model(A, cfg, cell_mm, st, progress=None):
    if progress:
        progress(92, "Stage 6/6: Scaling to tiles and snapping to the grid...")
    st.reset(S7)
    st.reset(S8)
    with st.timer("7-8 scale+snap+grid"):
        cell_px = cell_mm / A.mm_per_px
        min_len = cfg.min_seg_cells * cell_px
        devs, segs, mlog = [], [], []
        for it in A.items:
            lg = []
            for s in manhattan(it["poly"], min_len, devs, lg):
                s["kind"] = it["kind"]
                s["id"] = it["id"]
                segs.append(s)
            mlog.append((it["id"], lg))
        tol = cfg.snap_tol_cells * cell_px
        slog = []
        snapped = connect_snap(segs, tol, slog)
        xs_ = [v for sg in segs for v in ((sg["a"], sg["b"]) if sg["o"] == "H" else (sg["c"],))]
        ys_ = [v for sg in segs for v in ((sg["c"],) if sg["o"] == "H" else (sg["a"], sg["b"]))]
        xs_ += [sy["cx"] for sy in A.symbols]
        ys_ += [sy["cy"] for sy in A.symbols]
        if xs_ and ys_ and max(xs_) > min(xs_) and max(ys_) > min(ys_):
            x0, y0, x1, y1 = min(xs_), min(ys_), max(xs_), max(ys_)
        else:
            x0, y0, x1, y1 = A.bbox
        W = int(round((x1 - x0) / cell_px)) + 1
        H = int(round((y1 - y0) / cell_px)) + 1
        A.cell_px, A.origin = cell_px, (x0, y0)
        scale = dict(cell_mm=cell_mm, mm_per_px=A.mm_per_px, cell_px_on_image=cell_px,
                     map_mm=[(x1 - x0) * A.mm_per_px, (y1 - y0) * A.mm_per_px], paper="A4 assumed")
        model = MapModel(W, H, scale)
        clamp = lambda v, hi: int(min(max(round(v), 0), hi))
        errs, map_lines = [], []

        def conv(v, o, hi):
            t = (v - o) / cell_px
            errs.append(abs(t - round(t)) * cell_px)
            return t, clamp(t, hi)
        for s in segs:
            if s["o"] == "H":
                tc, gy = conv(s["c"], y0, H - 1)
                ta, ga = conv(s["a"], x0, W - 1)
                tb, gb = conv(s["b"], x0, W - 1)
                model.segments.append(Segment(s["kind"], min(ga, gb), gy, max(ga, gb), gy))
                map_lines.append(f"B{s['id']} {s['kind']} H: y=({s['c']:.1f}-{y0})/{cell_px:.2f}={tc:.2f}->{gy} ; x=({s['a']:.1f}-{x0})/{cell_px:.2f}={ta:.2f}->{ga} .. ({s['b']:.1f}-{x0})/{cell_px:.2f}={tb:.2f}->{gb}")
            else:
                tc, gx = conv(s["c"], x0, W - 1)
                ta, ga = conv(s["a"], y0, H - 1)
                tb, gb = conv(s["b"], y0, H - 1)
                model.segments.append(Segment(s["kind"], gx, min(ga, gb), gx, max(ga, gb)))
                map_lines.append(f"B{s['id']} {s['kind']} V: x=({s['c']:.1f}-{x0})/{cell_px:.2f}={tc:.2f}->{gx} ; y=({s['a']:.1f}-{y0})/{cell_px:.2f}={ta:.2f}->{ga} .. ({s['b']:.1f}-{y0})/{cell_px:.2f}={tb:.2f}->{gb}")
        sym_lines = []
        for sy in A.symbols:
            tx, ty = (sy["cx"] - x0) / cell_px, (sy["cy"] - y0) / cell_px
            t = (clamp(tx, W - 1), clamp(ty, H - 1))
            sym_lines.append(f"{sy['kind']} centroid ({sy['cx']:.1f},{sy['cy']:.1f}) -> (({sy['cx']:.1f}-{x0})/{cell_px:.2f}, ({sy['cy']:.1f}-{y0})/{cell_px:.2f}) = ({tx:.2f},{ty:.2f}) -> tile {t}")
            model.objects[t] = {"spawn": ("arrow_start", 0), "interactable": ("door", 0)}.get(sy["kind"], ("enemy_spawn", 0))
        crates = [s for s in model.segments if s.kind == "breakable"]
        model.segments = [s for s in model.segments if s.kind != "breakable"]
        n_before = len(model.segments)
        model.normalize()
        n_props = 0
        for s in crates:
            for xy in s.tiles():
                if model.inside(*xy) and not model.wall_at(*xy) and xy not in model.objects:
                    model.objects[xy] = ("breakable_prop", 0)
                    n_props += 1
        model.edits = 0
    mw, mh = scale["map_mm"]
    d = np.array(devs) if devs else np.array([0.0])
    st.block(S7, "7.1 Force every segment onto the horizontal or vertical axis",
             formula=["orientation:  H if |dx| >= |dy| else V",
                      "tilt = atan( min(|dx|,|dy|) / max(|dx|,|dy|) )   (how far the hand-drawn segment was from the axis)",
                      "snapped coordinate:  H -> y = (y1+y2)/2 ;  V -> x = (x1+x2)/2",
                      "merge of consecutive same-orientation pieces:  c = (c1*w1 + c2*w2) / (w1 + w2)   (length-weighted)",
                      f"stub rule: pieces shorter than min_seg_cells*cell_px = {cfg.min_seg_cells}*{cell_px:.1f} = {min_len:.1f}px between two same-orientation pieces are hand wobble and are removed",
                      "corner: between an H piece (y=cH) and a V piece (x=cV) the corner is exactly (x=cV, y=cH)"],
             compute=[l for i, lg in mlog[:12] for l in ([f"-- branch B{i} --"] + lg[:14])]
             + ([f"... {len(mlog)-12} more branches"] if len(mlog) > 12 else []),
             result=f"{len(devs)} RDP segments analysed ; tilt before snapping: mean {d.mean():.2f} deg, max {d.max():.2f} deg ; after: exactly 0 deg",
             visual=["Slightly tilted or wobbly lines become perfectly horizontal / vertical (the requirement: only perpendicular lines).",
                     "Diagonal drawings are forced to the nearest axis, so draw walls along the paper edges."])
    st.block(S7, "7.2 Connect near-touching walls",
             formula=[f"tolerance = snap_tol_cells*cell_px = {cfg.snap_tol_cells}*{cell_px:.1f} = {tol:.1f}px",
                      "for an end point P of line s and a perpendicular line t with coordinate c_t spanning [a_t, b_t]:",
                      "   snap if  |P - c_t| <= tol   and   a_t - tol <= c_s <= b_t + tol   ->  P := c_t"],
             compute=slog[:30] + ([f"... {len(slog)-30} more"] if len(slog) > 30 else []) or ["no end points needed snapping"],
             result=f"{snapped} end points snapped",
             visual="Gaps and overshoots at T and L joints close, so walls are connected in the grid. A gap larger than the tolerance (about half a cell) stays open: that is how doorways are drawn.")
    st.block(S8, "8.1 Paper scale",
             formula=["mm_per_px = 297 mm / long side (px)       (A4 long edge = 297 mm, assumes the photo shows the whole sheet)",
                      "cell_px = cell_mm / mm_per_px              (cell_mm is the SCALE you choose: 1 grid cell = cell_mm on paper)"],
             compute=[f"mm_per_px = 297 / {A.long} = {A.mm_per_px:.4f}",
                      f"cell_px = {cell_mm:.1f} / {A.mm_per_px:.4f} = {cell_px:.2f} px",
                      f"export tile = {cfg.export_tile_px}px per cell  ->  exported level is {W*cfg.export_tile_px} x {H*cfg.export_tile_px} px"],
             result=f"1 cell = {cell_mm:.1f} mm = {cell_px:.1f} px on the image",
             visual="Change the scale box in the toolbar: bigger cell_mm = fewer, coarser tiles; smaller = finer grid.")
    st.block(S8, "8.2 Map size and size class",
             formula=["drawn size = (max-min) of all line centrelines and symbol centres ;   W = round(width_px / cell_px) + 1 ,  H = round(height_px / cell_px) + 1  (+1 because tile centres sit ON the lines)",
                      f"size class by cells = W*H :  <= {cfg.size_small_cells} small ;  <= {cfg.size_medium_cells} medium ;  else large"],
             compute=[f"line + symbol extent = x {x0}..{x1}, y {y0}..{y1}  ->  {x1-x0} x {y1-y0} px = {mw:.0f} x {mh:.0f} mm = {mw/A4_LONG_MM*100:.0f}% of the A4 long edge",
                      f"W = round({x1-x0}/{cell_px:.2f}) + 1 = {(x1-x0)/cell_px:.2f} -> {W-1} + 1 = {W}",
                      f"H = round({y1-y0}/{cell_px:.2f}) + 1 = {(y1-y0)/cell_px:.2f} -> {H-1} + 1 = {H}",
                      f"cells = {W} * {H} = {W*H}"],
             result=f"{W} x {H} tiles = {W*H} cells -> {model.size_class(cfg).upper()} map",
             visual="This sets the size of the grid in Tab 5 and the HUD label (small / medium / large).")
    st.block(S8, "8.3 Pixel -> tile conversion",
             formula="tile = clamp( round( (pixel - origin) / cell_px ), 0, size-1 )     origin = top-left of the line centrelines",
             compute=map_lines[:30] + ([f"... {len(map_lines)-30} more segments"] if len(map_lines) > 30 else []) + sym_lines,
             result=[f"{len(errs)} line coordinates rounded ; rounding error: mean {np.mean(errs) if errs else 0:.2f}px = {(np.mean(errs) if errs else 0)*A.mm_per_px:.2f}mm, max {max(errs) if errs else 0:.2f}px = {(max(errs) if errs else 0)*A.mm_per_px:.2f}mm",
                     "rounding error is at most half a cell = " + f"{cell_px/2:.1f}px"],
             visual="Every line lands exactly on tile centres, so two lines drawn at nearly the same place become the same tile column/row. A larger cell size means a larger rounding error.")
    kinds = []
    for s in model.segments:
        border = []
        if s.y1 == s.y2 and s.x1 != s.x2 and s.y1 in (0, H - 1): border.append(f"y={s.y1} is {'top' if s.y1==0 else 'bottom'} border (0 or {H-1})")
        if s.x1 == s.x2 and s.y1 != s.y2 and s.x1 in (0, W - 1): border.append(f"x={s.x1} is {'left' if s.x1==0 else 'right'} border (0 or {W-1})")
        kinds.append(f"({s.x1},{s.y1})-({s.x2},{s.y2}): " + (border[0] + " -> BOUNDARY" if border else "interior line -> solid WALL"))
    tm = model.tile_matrix()
    st.block(S8, "8.4 Merge, boundary classification and tile matrix",
             formula=["merge: same kind, same line, overlapping or touching (gap <= 1 tile) -> one segment",
                      f"boundary: a straight segment lying on x=0, x={W-1}, y=0 or y={H-1} ;  all other straight solid lines are walls ;  jagged lines become breakable_prop objects, not walls",
                      "tile_matrix[y][x] = 0 floor, 1 wall, 3 boundary  (2 is reserved)"],
             compute=[f"segments before merge: {n_before} ; after: {len(model.segments)}"] + kinds[:25]
             + [f"tile counts: floor {(tm==0).sum()} ; wall {(tm==1).sum()} ; boundary {(tm==3).sum()} ; total {tm.size}",
                f"jagged lines converted to breakable_prop: {n_props} tile(s)",
                f"occupied tiles = {(tm>0).sum()}/{tm.size} = {(tm>0).sum()/tm.size*100:.1f}%"],
             result=(lambda c: f"{c['walls']} wall, {c['boundary']} boundary, {c['symbols']} symbol, {c['interactables']} interactable, {c['terrain']} terrain")(model.counts()),
             visual=["Tab 5 draws gray tiles (walls), a bright frame (boundary) and a coloured badge for every symbol / interactable (star = player start, square = door, triangle = enemy spawn, jagged line = breakable props).",
                     "Turn on 'Show sketch under grid' to compare every tile against your original drawing, and fix mistakes with the editor tools."])
    return model


def make_previews(A):
    orig = A.work.copy()
    binv = cv2.cvtColor(255 - A.binary, cv2.COLOR_GRAY2BGR)
    seg = np.full_like(orig, 255)
    seg[A.wall_mask > 0] = (90, 90, 90)
    col = dict(spawn=(0, 190, 255), interactable=(60, 170, 60), raised=(200, 120, 40))
    for s in A.symbols:
        x, y, w, h = s["bbox"]
        cv2.rectangle(seg, (x - 3, y - 3), (x + w + 3, y + h + 3), col[s["kind"]], 2)
        cv2.putText(seg, s["kind"], (x, max(12, y - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, col[s["kind"]], 1, cv2.LINE_AA)
    for u in A.unclassified:
        x, y, w, h = u["bbox"]
        cv2.rectangle(seg, (x - 3, y - 3), (x + w + 3, y + h + 3), (0, 0, 220), 2)
        cv2.putText(seg, "unclassified", (x, max(12, y - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 220), 1, cv2.LINE_AA)
    thin = np.full_like(orig, 255)
    thin[cv2.dilate(A.skel, np.ones((2, 2), np.uint8)) > 0] = (0, 0, 200)
    H, W = orig.shape[:2]
    for w in getattr(A, "warnings", []):
        m = re.search(r"fragmented stroke excluded near \((\d+)% x, (\d+)% y\)", w)
        if m:
            c = (int(m.group(1)) * W // 100, int(m.group(2)) * H // 100)
            for img in (thin, seg):
                cv2.circle(img, c, 14, (0, 140, 255), 2, cv2.LINE_AA)
                cv2.putText(img, "!", (c[0] - 4, c[1] + 6), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 140, 255), 2, cv2.LINE_AA)
    return dict(original=orig, binary=binv, segmented=seg, thinned=thin)


def to_bgr(img):
    img = np.asarray(img)
    if img.dtype != np.uint8:
        img = cv2.normalize(img, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    if img.ndim == 2:
        return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    if img.shape[2] == 4:
        return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
    return img


def run_pipeline(source, cfg=None, cell_mm=None, progress=None, prepared=False, prep_params=None):
    prog = progress or (lambda pct, text: None)
    cfg = cfg or Config()
    st = Stats()
    prog(2, "Stage 1/6: Loading image...")
    bgr = to_bgr(load_image(source) if isinstance(source, str) else source)
    if prep_params is not None:
        prepared = True
    if not prepared:
        prog(5, "Stage 1/6: Detecting paper edges and straightening...")
        bgr = straighten_paper(resize_image(bgr))
    A = run_stage_a(bgr, cfg, st, progress=progress, prep_params=prep_params)
    model = build_model(A, cfg, cell_mm or cfg.cell_mm, st, progress=progress)
    prog(100, "Done!")
    return A, model, st


def process_sketch(image_bgr, preprocess_params=None):
    return run_preprocessing(image_bgr, preprocess_params or PreprocessParams())
