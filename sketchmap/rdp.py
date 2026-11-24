import numpy as np


def point_line_dist(pts, a, b):
    ab = b - a
    L = float(np.hypot(*ab))
    if L == 0:
        return np.hypot(pts[:, 0] - a[0], pts[:, 1] - a[1])
    return np.abs(ab[0] * (pts[:, 1] - a[1]) - ab[1] * (pts[:, 0] - a[0])) / L


def seg_dist(pts, a, b):
    ab = b - a
    L2 = float(ab @ ab)
    if L2 == 0:
        return np.hypot(*(pts - a).T)
    t = np.clip(((pts - a) @ ab) / L2, 0, 1)
    proj = a + t[:, None] * ab
    return np.hypot(*(pts - proj).T)


def max_deviation(raw, poly):
    d = np.min([seg_dist(raw, poly[i], poly[i + 1]) for i in range(len(poly) - 1)], axis=0)
    return float(d.max()), float(d.mean())


def rdp(points, eps, trace=None, max_trace=40):
    pts = np.asarray(points, float)
    n = len(pts)
    if n < 3:
        return pts
    keep = np.zeros(n, bool)
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        s, e = stack.pop()
        if e <= s + 1:
            continue
        d = point_line_dist(pts[s + 1:e], pts[s], pts[e])
        k = int(np.argmax(d))
        dm = float(d[k])
        if trace is not None and len(trace) < max_trace:
            trace.append(dict(n=n, s=s, e=e, k=s + 1 + k, a=pts[s].copy(), b=pts[e].copy(), p=pts[s + 1 + k].copy(), d=dm, eps=eps, split=dm > eps))
        if dm > eps:
            idx = s + 1 + k
            keep[idx] = True
            stack += [(idx, e), (s, idx)]
    return pts[keep]
