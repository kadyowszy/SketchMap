import cv2
import numpy as np


def zhang_suen(binary, max_iter=300, progress=None):
    img = (binary > 0).astype(np.uint8)
    ys, xs = np.nonzero(img)
    info = dict(start_px=int(len(ys)), end_px=0, iterations=0, removed=[], remaining=[], ex_removed=None, ex_kept=None)
    if len(ys) == 0:
        return img, info
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    work = np.pad(img[y0:y1, x0:x1], 1)
    est = max(1, int(cv2.distanceTransform(work, cv2.DIST_L2, 3).max()))
    for it in range(max_iter):
        rem = []
        for step in (0, 1):
            p = work
            c = p[1:-1, 1:-1]
            N, NE, E, SE = p[:-2, 1:-1], p[:-2, 2:], p[1:-1, 2:], p[2:, 2:]
            S, SW, W, NW = p[2:, 1:-1], p[2:, :-2], p[1:-1, :-2], p[:-2, :-2]
            seq = [N, NE, E, SE, S, SW, W, NW]
            B = N + NE + E + SE + S + SW + W + NW
            A = np.zeros_like(c)
            for i in range(8):
                A += ((seq[i] == 0) & (seq[(i + 1) % 8] == 1))
            cond = ((N * E * S) == 0) & ((E * S * W) == 0) if step == 0 else ((N * E * W) == 0) & ((N * S * W) == 0)
            m = (c == 1) & (B >= 2) & (B <= 6) & (A == 1) & cond
            if it == 0 and step == 0:
                def grab(r, cc, removed):
                    return dict(pos=(int(x0 + cc), int(y0 + r)), vals=[int(s_[r, cc]) for s_ in seq], B=int(B[r, cc]), A=int(A[r, cc]), removed=removed, step=step)
                cand = np.argwhere(m)
                if len(cand):
                    r, cc = cand[len(cand) // 2]
                    info["ex_removed"] = grab(r, cc, True)
                kept = np.argwhere((c == 1) & ~m & (A >= 2))
                if not len(kept):
                    kept = np.argwhere((c == 1) & ~m)
                if len(kept):
                    r, cc = kept[len(kept) // 2]
                    info["ex_kept"] = grab(r, cc, False)
            rem.append(int(m.sum()))
            work[1:-1, 1:-1][m] = 0
        info["removed"].append(rem)
        info["remaining"].append(int(work.sum()))
        if progress:
            progress(min((it + 1) / (est + 1), 0.99),
                     f"Thinning strokes: pass {it + 1}, {int(work.sum()):,} px left (from {info['start_px']:,})")
        if sum(rem) == 0:
            break
    info["iterations"] = len(info["removed"])
    out = np.zeros_like(img)
    out[y0:y1, x0:x1] = work[1:-1, 1:-1]
    info["end_px"] = int(out.sum())
    return out, info


def prune_skeleton_spurs(skeleton, max_spur_len=10):
    orig = (skeleton > 0).astype(np.uint8)
    kernel = np.array([[1, 1, 1], [1, 0, 1], [1, 1, 1]], dtype=np.uint8)

    def endpoints(img):
        n = cv2.filter2D(img, -1, kernel, borderType=cv2.BORDER_CONSTANT)
        return (img == 1) & (n == 1)

    skel = orig.copy()
    for _ in range(max_spur_len):
        ep = endpoints(skel)
        if not ep.any():
            break
        skel[ep] = 0
    grow = np.zeros_like(skel)
    grow[endpoints(skel)] = 1
    cross = np.ones((3, 3), np.uint8)
    for _ in range(max_spur_len):
        grow = cv2.dilate(grow, cross) & orig & (1 - skel)
        skel = skel | grow
    return skel * 255
