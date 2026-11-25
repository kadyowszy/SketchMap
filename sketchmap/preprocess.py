import os
from dataclasses import dataclass
from typing import Tuple
import cv2
import numpy as np

from .config import PreprocessParams
from .imgutil import resize_keep_aspect, cap_working_resolution

S1 = "1. Preprocessing"


MAX_IMAGE_PIXELS = 60_000_000
MAX_FILE_BYTES = 80 * 1024 * 1024


def load_image(path):
    try:
        size = os.path.getsize(path)
    except OSError:
        raise ValueError("The file cannot be read (missing or access denied).")
    if size == 0:
        raise ValueError("The file is empty (0 bytes).")
    if size > MAX_FILE_BYTES:
        raise ValueError("The file is too large (over 80 MB). Export a smaller JPEG/PNG of the sketch.")
    img = None
    try:
        from PIL import Image, ImageOps
        with Image.open(path) as pil:
            if pil.size[0] * pil.size[1] > MAX_IMAGE_PIXELS:
                raise ValueError("The image has too many pixels (over 60 megapixels). Use a smaller photo.")
            pil = ImageOps.exif_transpose(pil)
            if pil.mode in ("RGBA", "LA", "P"):
                pil = pil.convert("RGBA")
                bg = Image.new("RGBA", pil.size, (255, 255, 255, 255))
                pil = Image.alpha_composite(bg, pil)
            img = cv2.cvtColor(np.array(pil.convert("RGB")), cv2.COLOR_RGB2BGR)
    except ValueError:
        raise
    except Exception:
        try:
            img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
        except Exception:
            img = None
    if img is None:
        raise ValueError("Unsupported or corrupted image file (use JPEG/PNG).")
    return img


def resize_image(image, max_side=1600):
    return resize_keep_aspect(image, max_side)


def order_corners(pts):
    pts = np.asarray(pts, dtype="float32").reshape(4, 2)
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0], rect[2] = pts[np.argmin(s)], pts[np.argmax(s)]
    d = np.diff(pts, axis=1)
    rect[1], rect[3] = pts[np.argmin(d)], pts[np.argmax(d)]
    return rect


def _is_paper_edge(gray, quad, min_step=20):
    H, W = gray.shape
    inside = np.zeros((H, W), np.uint8)
    cv2.fillConvexPoly(inside, quad.astype(np.int32).reshape(-1, 2), 255)
    k = max(9, int(0.03 * max(H, W)) | 1)
    kern = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    ring = cv2.dilate(inside, kern) & ~cv2.dilate(inside, np.ones((5, 5), np.uint8))
    core = cv2.erode(inside, kern) & ~cv2.erode(inside, np.ones((k * 3, k * 3), np.uint8))
    if ring.sum() == 0 or core.sum() == 0:
        return True
    outside_px = gray[ring > 0]
    if outside_px.size < 0.5 * ring.sum() / 255 * 0.5:
        return True
    return float(np.median(gray[core > 0])) - float(np.median(outside_px)) >= min_step


def find_paper_corners(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    raw = cv2.GaussianBlur(gray, (9, 9), 0)
    lo, hi = np.percentile(gray, (2, 98))
    if hi - lo < 10:
        return None
    gray = cv2.normalize(np.clip(gray, lo, hi), None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 75, 200)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:5]
    min_area = 0.25 * image.shape[0] * image.shape[1]
    for c in contours:
        approx = cv2.approxPolyDP(c, 0.02 * cv2.arcLength(c, True), True)
        if len(approx) == 4 and cv2.contourArea(approx) > min_area and _is_paper_edge(raw, approx):
            return order_corners(approx)
    return None


def _quad_from_hull(hull):
    """4 corners for a convex hull: tighten approxPolyDP until it has 4 vertices, else the min-area rectangle."""
    per = cv2.arcLength(hull, True)
    for eps in (0.01, 0.015, 0.02, 0.03, 0.04, 0.05, 0.07):
        ap = cv2.approxPolyDP(hull, eps * per, True)
        if len(ap) == 4:
            return ap.reshape(4, 2).astype("float32")
        if len(ap) < 4:
            break
    return cv2.boxPoints(cv2.minAreaRect(hull)).astype("float32")


def find_paper_by_brightness(image):
    """Fallback paper finder for soft edges / curled corners / textured tables where Canny gives no clean 4-gon.

    The paper is the biggest bright blob. Threshold a blurred, down-scaled copy (Otsu), keep the largest component,
    fill the pen strokes inside it, fit a quadrilateral to its convex hull and check it looks like a sheet of paper.
    """
    H, W = image.shape[:2]
    f = 800.0 / max(H, W)
    small = cv2.resize(image, None, fx=f, fy=f, interpolation=cv2.INTER_AREA) if f < 1 else image.copy()
    g = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    g = cv2.GaussianBlur(g, (0, 0), max(2.0, 0.006 * max(g.shape)))
    # flatten slow lighting gradients so one threshold separates paper from table
    bgl = cv2.GaussianBlur(g, (0, 0), 0.25 * max(g.shape))
    flat = cv2.normalize(g.astype(np.float32) - 0.5 * bgl.astype(np.float32), None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    T, mask = cv2.threshold(flat, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (21, 21)))
    n, lab, stt, _c = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if n < 2:
        return None
    big = 1 + int(np.argmax(stt[1:, cv2.CC_STAT_AREA]))
    blob = (lab == big).astype(np.uint8) * 255
    cnts, _ = cv2.findContours(blob, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return None
    hull = cv2.convexHull(max(cnts, key=cv2.contourArea))
    quad = _quad_from_hull(hull)
    qa, ha = cv2.contourArea(order_corners(quad)), cv2.contourArea(hull)
    if qa < 0.25 * g.shape[0] * g.shape[1] or ha < 0.85 * qa:
        return None
    # a sheet of paper has ~4 right-ish angles and an A-series aspect (1.0 .. 2.0 allowed for perspective)
    q = order_corners(quad)
    w1, w2 = np.hypot(*(q[1] - q[0])), np.hypot(*(q[2] - q[3]))
    h1, h2 = np.hypot(*(q[3] - q[0])), np.hypot(*(q[2] - q[1]))
    asp = max(w1 + w2, h1 + h2) / max(min(w1 + w2, h1 + h2), 1.0)
    if not 1.1 <= asp <= 1.9:
        return None
    return order_corners(q / (f if f < 1 else 1.0))


def warp_to_rect(image, corners):
    tl, tr, br, bl = rect = order_corners(corners)
    w = max(int(np.hypot(*(br - bl))), int(np.hypot(*(tr - tl))))
    h = max(int(np.hypot(*(tr - br))), int(np.hypot(*(tl - bl))))
    if w < 50 or h < 50:
        return image
    dst = np.array([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], dtype="float32")
    return cv2.warpPerspective(image, cv2.getPerspectiveTransform(rect, dst), (w, h))


PAPER_INSET = 0.012   # trim the warped sheet by this fraction per side: its rim (curl, shadow, table sliver) is not drawing


def straighten_paper(image):
    rect = find_paper_corners(image)
    if rect is None:
        rect = find_paper_by_brightness(image)
    if rect is None:
        return image
    out = warp_to_rect(image, rect)
    h, w = out.shape[:2]
    dy, dx = int(round(PAPER_INSET * h)), int(round(PAPER_INSET * w))
    return out[dy:h - dy, dx:w - dx] if h > 4 * dy + 50 and w > 4 * dx + 50 else out


def get_initial_corners(image):
    rect = find_paper_corners(image)
    if rect is not None:
        return rect.tolist()
    h, w = image.shape[:2]
    return [[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]]


def apply_manual_transform(image, corners, alpha=1.0, beta=0):
    return cv2.convertScaleAbs(warp_to_rect(image, corners), alpha=alpha, beta=beta)


def fit_within(image, max_w=1000, max_h=640):
    h, w = image.shape[:2]
    s = min(1.0, max_w / w, max_h / h)
    if s < 1.0:
        image = cv2.resize(image, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
    return image, s


def otsu_terms(p, T):
    idx = np.arange(256)
    w0 = float(p[:T + 1].sum())
    w1 = 1 - w0
    if w0 <= 1e-12 or w1 <= 1e-12:
        return 0.0, w0, w1, 0.0, 0.0
    mu0 = float((idx[:T + 1] * p[:T + 1]).sum() / w0)
    mu1 = float((idx[T + 1:] * p[T + 1:]).sum() / w1)
    return w0 * w1 * (mu0 - mu1) ** 2, w0, w1, mu0, mu1


def preprocess(bgr, cfg, st):
    h, w = bgr.shape[:2]
    s = min(1.0, cfg.work_max_side / max(h, w))
    work = cv2.resize(bgr, None, fx=s, fy=s, interpolation=cv2.INTER_AREA) if s < 1 else bgr.copy()
    gray = cv2.cvtColor(work, cv2.COLOR_BGR2GRAY)
    H, W = gray.shape
    long = max(H, W)

    sw, sh = max(8, W // 4), max(8, H // 4)
    small = cv2.resize(gray, (sw, sh), interpolation=cv2.INTER_AREA)
    ks = max(3, ((long // 8) // 4) | 1)
    med = cv2.medianBlur(small, ks)
    bgu = cv2.resize(med, (W, H), interpolation=cv2.INTER_LINEAR)
    sigma = long / 60
    bg = np.maximum(cv2.GaussianBlur(bgu, (0, 0), sigma), 1).astype(np.uint8)
    norm = cv2.divide(gray, bg, scale=255)

    T, binm = cv2.threshold(norm, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    T = int(T)
    pre_speck = int((binm > 0).sum())
    n, lab, stt, _ = cv2.connectedComponentsWithStats(binm, connectivity=8)
    removed_areas = []
    for i in range(1, n):
        if stt[i, cv2.CC_STAT_AREA] < cfg.min_noise_area:
            removed_areas.append(int(stt[i, cv2.CC_STAT_AREA]))
            binm[lab == i] = 0
    ink = float((binm > 0).mean())
    paper = binm == 0

    ys, xs = np.nonzero(binm)
    ix, iy = (int(xs[len(xs) // 2]), int(ys[len(ys) // 2])) if len(xs) else (0, 0)
    cen = np.argwhere(paper[H // 4:3 * H // 4, W // 4:3 * W // 4])
    py, px = (int(cen[len(cen) // 2][0]) + H // 4, int(cen[len(cen) // 2][1]) + W // 4) if len(cen) else (H // 2, W // 2)

    st.block(S1, "1.1 Resize to working resolution",
             formula=["s = min(1, max_side / max(h, w))   ;   new size = (w*s, h*s)   ;   INTER_AREA: each output pixel = average of the input pixels it covers"],
             compute=[f"s = min(1, {cfg.work_max_side} / max({h}, {w})) = min(1, {cfg.work_max_side/max(h, w):.4f}) = {s:.4f}",
                      f"new size = {w}*{s:.4f} x {h}*{s:.4f} = {W} x {H} px",
                      f"pixels to process: {w*h:,} -> {W*H:,}  ({W*H/(w*h)*100:.1f}% of the original work)"],
             result=f"working image {W} x {H} px, long side = {long} px",
             visual=["Tab 1 'Original' shows this resized photo; every later coordinate is in this resolution.",
                     f"All size limits are fractions of the long side ({long}px), so results do not depend on the camera resolution."])

    b_, g_, r_ = [int(v) for v in work[py, px]]
    st.block(S1, "1.2 Colour -> grayscale",
             formula="Y = 0.299*R + 0.587*G + 0.114*B   (luma weights: the eye is most sensitive to green)",
             compute=[f"paper sample pixel ({px},{py}): B={b_} G={g_} R={r_}",
                      f"Y = 0.299*{r_} + 0.587*{g_} + 0.114*{b_} = {0.299*r_:.1f} + {0.587*g_:.1f} + {0.114*b_:.1f} = {0.299*r_+0.587*g_+0.114*b_:.1f}",
                      f"OpenCV (fixed-point rounding) gives {int(gray[py, px])}"],
             result="3 colour channels -> 1 brightness channel (0 = black, 255 = white)",
             visual="Pen colour no longer matters, only how dark it is compared with the paper.")

    r = ks // 2
    wy0, wy1, wx0, wx1 = max(0, py // 4 - r), min(sh, py // 4 + r + 1), max(0, px // 4 - r), min(sw, px // 4 + r + 1)
    win = np.sort(small[wy0:wy1, wx0:wx1].ravel())
    full_win = binm[wy0 * 4:wy1 * 4, wx0 * 4:wx1 * 4]
    st.block(S1, "1.3 Background (lighting) estimate: downsample + median",
             formula=["I_s(x,y) = mean of the 4x4 block of I      (INTER_AREA downsample, 16x fewer pixels, much faster)",
                      "B_s(x,y) = median{ I_s(x+i, y+j) : |i|,|j| <= (k-1)/2 }      with k = odd(long/8/4)",
                      "The median ignores outliers: if pen strokes cover < 50% of the window, the median is a PAPER value."],
             compute=[f"downsampled size = {sw} x {sh}; window k = ({long}//8)//4 -> odd = {ks}  (covers {ks*4}x{ks*4} px of the working image)",
                      f"window around paper pixel ({px},{py}) -> small-image pixel ({px//4},{py//4}): {win.size} values",
                      f"sorted: min={int(win[0])}  25%={int(np.percentile(win, 25))}  median={int(np.median(win))}  75%={int(np.percentile(win, 75))}  max={int(win[-1])}",
                      f"pen ink inside that window (full-res binary) = {full_win.mean()/255*100:.2f}% < 50%  ->  median = paper brightness, strokes are removed"],
             result=f"B_s = {int(med[min(py//4, sh-1), min(px//4, sw-1)])} at that location; the whole map B_s is then stretched back to {W}x{H} with bilinear interpolation",
             visual="The pen lines disappear from B: it only contains the paper's brightness (shadows, vignetting, gradients).")

    g0 = 1 / (sigma * np.sqrt(2 * np.pi))
    st.block(S1, "1.4 Smooth the background: Gaussian blur",
             formula=["G(i) = exp(-i^2 / (2*sigma^2)) / (sigma*sqrt(2*pi))     sigma = long/60",
                      "B(x,y) = sum_i sum_j G(i)*G(j)*B_up(x-i, y-j)      (separable: 1-D pass in x, then in y)"],
             compute=[f"sigma = {long}/60 = {sigma:.2f} px ; effective kernel radius ~ 3*sigma = {3*sigma:.0f} px",
                      f"G(0) = 1/({sigma:.2f}*2.5066) = {g0:.5f}",
                      f"G(sigma) = G(0)*exp(-0.5) = {g0*np.exp(-0.5):.5f}   (60.7% of the centre weight)",
                      f"G(2*sigma) = G(0)*exp(-2) = {g0*np.exp(-2):.5f}   (13.5% of the centre weight)"],
             result=[f"B min = {int(bg.min())}, max = {int(bg.max())}, mean = {bg.mean():.1f}",
                     f"lighting spread = (max-min)/mean = ({int(bg.max())}-{int(bg.min())})/{bg.mean():.1f} = {(int(bg.max())-int(bg.min()))/bg.mean()*100:.1f}%"],
             visual="B is now a smooth 'lighting map'. A spread of this size is the shading the camera/room added, and the next step removes it.")

    left = gray[:, :W // 5][paper[:, :W // 5]]
    right = gray[:, 4 * W // 5:][paper[:, 4 * W // 5:]]
    nleft = norm[:, :W // 5][paper[:, :W // 5]]
    nright = norm[:, 4 * W // 5:][paper[:, 4 * W // 5:]]
    pstd0, pstd1 = float(gray[paper].std()), float(norm[paper].std())
    lines = [f"paper pixel ({px},{py}): I={int(gray[py, px])}, B={int(bg[py, px])}  ->  I_norm = {int(gray[py, px])}/{int(bg[py, px])}*255 = {int(norm[py, px])}",
             f"ink pixel   ({ix},{iy}): I={int(gray[iy, ix])}, B={int(bg[iy, ix])}  ->  I_norm = {int(gray[iy, ix])}/{int(bg[iy, ix])}*255 = {int(norm[iy, ix])}"]
    yb, xb = np.unravel_index(np.argmin(bg), bg.shape)
    yw, xw = np.unravel_index(np.argmax(bg), bg.shape)
    lines += [f"darkest-lit corner ({xb},{yb}): {int(gray[yb, xb])}/{int(bg[yb, xb])}*255 = {int(norm[yb, xb])}",
              f"brightest-lit corner ({xw},{yw}): {int(gray[yw, xw])}/{int(bg[yw, xw])}*255 = {int(norm[yw, xw])}"]
    if len(left) and len(right):
        lines += [f"left-edge paper mean  : before {left.mean():.1f}  after {nleft.mean():.1f}",
                  f"right-edge paper mean : before {right.mean():.1f}  after {nright.mean():.1f}",
                  f"left-right difference : before {abs(left.mean()-right.mean()):.1f}  after {abs(nleft.mean()-nright.mean()):.1f}"]
    lines.append(f"std-dev of ALL paper pixels: before {pstd0:.2f}  after {pstd1:.2f}")
    st.block(S1, "1.5 Illumination correction (flat-field division)",
             formula="I_norm(x,y) = min(255, I(x,y) / B(x,y) * 255)      paper: I = B -> 255 ;  ink: I << B -> small value",
             compute=lines,
             result="paper becomes ~255 everywhere; ink keeps its darkness ratio relative to the local paper brightness",
             visual=["Tab 2 'Preprocessed' no longer has dark corners or a left-to-right brightness slope.",
                     f"Measured: paper brightness variation dropped from {pstd0:.2f} to {pstd1:.2f} (std-dev)."])

    hist = np.bincount(norm.ravel(), minlength=256).astype(float)
    p = hist / hist.sum()
    v, w0, w1, mu0, mu1 = otsu_terms(p, T)
    muT = float((np.arange(256) * p).sum())
    varT = float((((np.arange(256) - muT) ** 2) * p).sum())
    cmp_lines = []
    for t in (T - 10, T, T + 10):
        t = max(1, min(254, t))
        vv, a0, a1, m0, m1 = otsu_terms(p, t)
        cmp_lines.append(f"T={t:3d}: w0={a0:.4f} w1={a1:.4f} mu0={m0:.1f} mu1={m1:.1f}  s2_b = {a0:.4f}*{a1:.4f}*({m0:.1f}-{m1:.1f})^2 = {vv:.1f}" + ("   <- chosen (maximum)" if t == T else ""))
    st.block(S1, "1.6 Otsu automatic threshold",
             formula=["p_i = count_i / N   (histogram of I_norm)",
                      "w0(T) = sum_{i<=T} p_i ,  w1(T) = 1 - w0(T)       (class 0 = dark = ink, class 1 = paper)",
                      "mu0(T) = sum_{i<=T} i*p_i / w0 ,  mu1(T) = sum_{i>T} i*p_i / w1",
                      "s2_b(T) = w0 * w1 * (mu0 - mu1)^2      (between-class variance)   ;   T* = argmax_T s2_b(T)"],
             compute=[f"N = {int(hist.sum()):,} pixels",
                      *cmp_lines,
                      f"overall mean mu_T = {muT:.1f}, total variance s2_T = {varT:.1f}, separability eta = s2_b/s2_T = {v:.1f}/{varT:.1f} = {v/max(varT,1e-9):.3f}  (1.0 = perfectly two-class)"],
             result=f"T* = {T}  ->  pixel is INK if I_norm <= {T}",
             visual=f"Tab 2 shows the result: black = ink ({pre_speck:,} px = {pre_speck/(W*H)*100:.2f}% of the image), white = paper.")

    st.block(S1, "1.7 Speck removal (connected-component area filter)",
             formula="keep component C only if area(C) >= min_noise_area",
             compute=[f"min_noise_area = {cfg.min_noise_area} px ; {n-1} components found",
                      f"components removed: {len(removed_areas)}" + (f"  (areas: {sorted(removed_areas)[:12]})" if removed_areas else "")],
             result=f"ink after cleaning = {int((binm>0).sum()):,} px = {ink*100:.2f}% of the image",
             visual="Sensor noise / dust dots vanish from the binary image; real strokes and symbols are untouched.")
    warn = []
    if ink < 0.0005:
        warn.append("no recognizable ink found (blank or too low contrast)")
    elif ink > 0.35:
        warn.append("very high ink ratio - sketch may be low contrast / badly lit")
    return dict(work=work, gray=gray, norm=norm, binary=binm, long=long, scale=s, warnings=warn)


PREVIEW_MAX_SIDE = 1280


@dataclass
class PreprocessResult:
    straightened_bgr: np.ndarray
    enhanced_gray: np.ndarray
    binary_mask: np.ndarray


def limit_side(image, max_side=PREVIEW_MAX_SIDE):
    return cap_working_resolution(image, max_side)


def auto_detect_skew_angle(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image.copy()
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 50, 150, apertureSize=3)
    min_len = max(30, int(min(gray.shape[:2]) * 0.08))
    lines = cv2.HoughLinesP(edges, rho=1, theta=np.pi / 720, threshold=60,
                            minLineLength=min_len, maxLineGap=15)
    if lines is None or len(lines) == 0:
        return 0.0
    angles, weights = [], []
    for x1, y1, x2, y2 in np.asarray(lines).reshape(-1, 4):
        dx, dy = float(x2 - x1), float(y2 - y1)
        length = np.hypot(dx, dy)
        if length < 1e-3:
            continue
        deg = np.degrees(np.arctan2(dy, dx))
        angles.append(((deg + 45.0) % 90.0) - 45.0)
        weights.append(length)
    if not angles:
        return 0.0
    order = np.argsort(angles)
    sa, sw = np.array(angles)[order], np.array(weights)[order]
    idx = int(np.searchsorted(np.cumsum(sw), 0.5 * sw.sum()))
    return float(np.round(sa[min(idx, len(sa) - 1)], 2))


def four_point_warp(image, norm_pts):
    h, w = image.shape[:2]
    src = np.array([[x * w, y * h] for (x, y) in norm_pts], dtype=np.float32)
    tl, tr, br, bl = src
    max_w = max(16, int(round(max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl)))))
    max_h = max(16, int(round(max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr)))))
    dst = np.array([[0, 0], [max_w - 1, 0], [max_w - 1, max_h - 1], [0, max_h - 1]], dtype=np.float32)
    m = cv2.getPerspectiveTransform(src, dst)
    border = (255, 255, 255) if image.ndim == 3 else 255
    return cv2.warpPerspective(image, m, (max_w, max_h), flags=cv2.INTER_CUBIC,
                               borderMode=cv2.BORDER_CONSTANT, borderValue=border)


def rotate_image_bound(image, angle_deg):
    if abs(angle_deg) < 1e-3:
        return image
    h, w = image.shape[:2]
    cx, cy = w / 2.0, h / 2.0
    m = cv2.getRotationMatrix2D((cx, cy), angle_deg, 1.0)
    cos, sin = abs(m[0, 0]), abs(m[0, 1])
    new_w, new_h = int(round(h * sin + w * cos)), int(round(h * cos + w * sin))
    m[0, 2] += new_w / 2.0 - cx
    m[1, 2] += new_h / 2.0 - cy
    if image.ndim == 3:
        border = tuple(int(c) for c in np.median(image.reshape(-1, image.shape[2]), axis=0))
    else:
        border = int(np.median(image))
    return cv2.warpAffine(image, m, (new_w, new_h), flags=cv2.INTER_CUBIC,
                          borderMode=cv2.BORDER_CONSTANT, borderValue=border)


def remove_shadows(gray, strength):
    if strength <= 0.0:
        return gray
    h, w = gray.shape[:2]
    f = min(1.0, 400.0 / max(h, w))
    small = cv2.resize(gray, None, fx=f, fy=f, interpolation=cv2.INTER_AREA) if f < 1 else gray
    k = max(7, (min(small.shape[:2]) // 12) | 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    bg = cv2.morphologyEx(small, cv2.MORPH_CLOSE, kernel)
    bg = cv2.GaussianBlur(bg, (0, 0), sigmaX=k * 0.4)
    if f < 1:
        bg = cv2.resize(bg, (w, h), interpolation=cv2.INTER_LINEAR)
    normalized = cv2.divide(gray, np.maximum(bg, 1), scale=255)
    return cv2.addWeighted(gray, 1.0 - strength, normalized, strength, 0)


def remove_small_components(binary, min_area):
    if min_area <= 1:
        return binary
    n, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    if n <= 1:
        return binary
    keep = np.zeros(n, dtype=np.uint8)
    keep[1:] = (stats[1:, cv2.CC_STAT_AREA] >= min_area).astype(np.uint8) * 255
    return keep[labels]


def fill_stroke_pinholes(binary, max_hole_area=36):
    n, labels, stats, _ = cv2.connectedComponentsWithStats(cv2.bitwise_not(binary), connectivity=4)
    if n <= 1:
        return binary
    small = np.zeros(n, dtype=bool)
    small[1:] = stats[1:, cv2.CC_STAT_AREA] <= max_hole_area
    out = binary.copy()
    out[small[labels]] = 255
    return out


def run_preprocessing(image_bgr, params):
    work = image_bgr.copy()
    if work.ndim == 2:
        work = cv2.cvtColor(work, cv2.COLOR_GRAY2BGR)
    elif work.shape[2] == 4:
        work = cv2.cvtColor(work, cv2.COLOR_BGRA2BGR)

    if params.perspective_points is not None and len(params.perspective_points) == 4:
        work = four_point_warp(work, params.perspective_points)
    if abs(params.rotation_deg) > 1e-3:
        work = rotate_image_bound(work, params.rotation_deg)
    l_m, t_m, r_m, b_m = [float(np.clip(v, 0.0, 0.45)) for v in params.crop_margins]
    h, w = work.shape[:2]
    x0, y0 = int(round(w * l_m)), int(round(h * t_m))
    x1 = min(w, max(x0 + 16, int(round(w * (1.0 - r_m)))))
    y1 = min(h, max(y0 + 16, int(round(h * (1.0 - b_m)))))
    straightened = work[y0:y1, x0:x1].copy()

    gray = cv2.cvtColor(straightened, cv2.COLOR_BGR2GRAY)
    gray = remove_shadows(gray, params.shadow_removal)
    if abs(params.contrast - 1.0) > 1e-3 or params.brightness != 0:
        gray = np.clip((gray.astype(np.float32) - 128.0) * float(params.contrast) + 128.0 + float(params.brightness),
                       0, 255).astype(np.uint8)
    if abs(params.gamma - 1.0) > 1e-3:
        inv_gamma = 1.0 / max(0.05, float(params.gamma))
        lut = np.array([((i / 255.0) ** inv_gamma) * 255 for i in range(256)], dtype=np.uint8)
        gray = cv2.LUT(gray, lut)
    if params.clahe_strength > 0.01:
        gray = cv2.createCLAHE(clipLimit=float(params.clahe_strength), tileGridSize=(8, 8)).apply(gray)

    if params.denoise_strength > 0:
        d = int(params.denoise_strength)
        gray = cv2.medianBlur(gray, 3 if d <= 2 else 5)
        gray = cv2.bilateralFilter(gray, d=5, sigmaColor=15 * d, sigmaSpace=15 * d)

    if params.invert == "invert":
        should_invert = True
    elif params.invert == "auto":
        should_invert = float(np.median(gray)) < 128.0
    else:
        should_invert = False
    thresh_type = cv2.THRESH_BINARY if should_invert else cv2.THRESH_BINARY_INV

    if params.threshold_mode == "otsu":
        _, binary = cv2.threshold(gray, 0, 255, thresh_type | cv2.THRESH_OTSU)
    elif params.threshold_mode == "manual":
        _, binary = cv2.threshold(gray, int(np.clip(params.threshold_offset, 0, 255)), 255, thresh_type)
    else:
        block = max(3, int(params.adaptive_block_size) | 1)
        method = (cv2.ADAPTIVE_THRESH_GAUSSIAN_C if params.threshold_mode == "adaptive_gaussian"
                  else cv2.ADAPTIVE_THRESH_MEAN_C)
        c_val = -int(params.threshold_offset) if should_invert else int(params.threshold_offset)
        binary = cv2.adaptiveThreshold(gray, 255, method, thresh_type, block, c_val)

    if params.stroke_adjust_px != 0:
        k = abs(int(params.stroke_adjust_px)) * 2 + 1
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
        binary = cv2.dilate(binary, kernel) if params.stroke_adjust_px > 0 else cv2.erode(binary, kernel)
    if params.close_gaps_px > 0:
        k = int(params.close_gaps_px) * 2 + 1
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    binary = remove_small_components(binary, params.min_speckle_area)
    if params.fill_pinholes:
        binary = fill_stroke_pinholes(binary)

    return PreprocessResult(straightened_bgr=straightened, enhanced_gray=gray, binary_mask=binary)


def preprocess_with_params(bgr, cfg, st, params):
    bgr = limit_side(bgr)
    res = run_preprocessing(bgr, params)
    work, gray, binm = res.straightened_bgr, res.enhanced_gray, res.binary_mask
    H0, W0 = gray.shape
    s = min(1.0, cfg.work_max_side / max(H0, W0))
    if s < 1:
        work = cv2.resize(work, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        gray = cv2.resize(gray, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        binm = (cv2.resize(binm, None, fx=s, fy=s, interpolation=cv2.INTER_AREA) > 127).astype(np.uint8) * 255
    H, W = gray.shape
    long = max(H, W)
    ink = float((binm > 0).mean())

    p = params
    geo = []
    if p.perspective_points is not None:
        geo.append("perspective: 4-point warp of normalized corners " + ", ".join(f"({x:.3f},{y:.3f})" for x, y in p.perspective_points))
    geo.append(f"rotation: {p.rotation_deg:+.2f} deg")
    geo.append(f"border trim (L,T,R,B): {tuple(round(v, 3) for v in p.crop_margins)}")
    st.block(S1, "1.1 Straighten, rotate and crop (user settings)",
             formula=["perspective: M = getPerspectiveTransform(corners -> rectangle) ; out(x,y) = in(M^-1 (x,y))",
                      "rotation about the centre with the canvas enlarged so no corner is cut off ; then trim the margins"],
             compute=[f"input {bgr.shape[1]} x {bgr.shape[0]} px (capped to {PREVIEW_MAX_SIDE}px long side)"] + geo
             + [f"straightened image {W0} x {H0} px" + (f" -> working size {W} x {H} px" if s < 1 else "")],
             result=f"working image {W} x {H} px, long side = {long} px",
             visual="Tab 1 'Original' shows this straightened photo; later coordinates are in this resolution.")
    st.block(S1, "1.2 Lighting, contrast and denoise",
             formula=["shadow flatten: I' = (1-a)*I + a*min(255, I / B * 255)   (B = paper brightness from a morphological closing)",
                      "contrast/brightness: I' = (I-128)*c + 128 + b ;  gamma: I' = 255*(I/255)^(1/g) ;  CLAHE: local histogram equalization",
                      "denoise: median blur, then edge-preserving bilateral filter"],
             compute=[f"shadow removal a = {p.shadow_removal:.2f} ; brightness b = {p.brightness:+d} ; contrast c = {p.contrast:.2f} ; gamma g = {p.gamma:.2f}",
                      f"CLAHE clip = {p.clahe_strength:.1f} ; denoise strength = {p.denoise_strength}",
                      f"enhanced gray: mean {gray.mean():.1f}, std {gray.std():.1f}"],
             result="uneven lighting and paper noise reduced before binarizing",
             visual="Tab 2 'Preprocessed' shows the enhanced gray image.")
    st.block(S1, "1.3 Binarization",
             formula=["adaptive: pixel is ink if I < localMean(block) - C ;  otsu: one global threshold maximizing between-class variance ;  manual: fixed level",
                      "polarity 'auto': if median(I) < 128 the picture is light ink on a dark background and is inverted"],
             compute=[f"mode = {p.threshold_mode} ; polarity = {p.invert} ; block = {int(p.adaptive_block_size) | 1} ; offset/level = {p.threshold_offset}"],
             result=f"ink = {ink*100:.2f}% of the image",
             visual="Tab 3 'Binary' shows black = ink, white = paper.")
    st.block(S1, "1.4 Topology clean-up",
             formula=["stroke adjust: dilate (+) or erode (-) with an elliptical kernel of (2n+1) px",
                      "close gaps: morphological closing with (2n+1) px kernel (seals pen breaks in walls)",
                      "speckles: drop connected components smaller than N px ; pinholes: fill holes <= 36 px inside strokes"],
             compute=[f"stroke adjust = {p.stroke_adjust_px:+d} px ; close gaps = {p.close_gaps_px} px ; min speckle = {p.min_speckle_area} px ; fill pinholes = {p.fill_pinholes}"],
             result=f"final ink = {int((binm > 0).sum()):,} px = {ink*100:.2f}% of the image",
             visual="Walls are continuous and noise-free, so thinning/segmentation do not leak or grow spurs.")
    warn = []
    if ink < 0.0005:
        warn.append("no recognizable ink found (blank or too low contrast)")
    elif ink > 0.35:
        warn.append("very high ink ratio - sketch may be low contrast / badly lit")
    return dict(work=work, gray=gray, norm=gray, binary=binm, long=long, scale=s, warnings=warn)
