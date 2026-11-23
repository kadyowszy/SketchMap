import argparse
import glob
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from sketchmap.config import Config
from sketchmap.pipeline import run_pipeline
from sketchmap import elements as el

TOL = 1
LINE_COVER = 0.9


def seg_cells(p, q):
    (x1, y1), (x2, y2) = p, q
    n = max(abs(x2 - x1), abs(y2 - y1))
    return [(round(x1 + (x2 - x1) * i / max(n, 1)), round(y1 + (y2 - y1) * i / max(n, 1))) for i in range(n + 1)]


def near(cell, cells, tol=TOL):
    x, y = cell
    return any(abs(x - a) <= tol and abs(y - b) <= tol for a, b in cells)


def detected(model):
    tm = model.tile_matrix()
    ys, xs = np.nonzero(tm == 1)
    wall = set(zip(xs.tolist(), ys.tolist()))
    ys, xs = np.nonzero(tm == 3)
    bnd = set(zip(xs.tolist(), ys.tolist()))
    pts = {}
    for (x, y), (k, _f) in model.objects.items():
        pts.setdefault(k, []).append((x, y))
    for (x, y), (k, _f) in model.terrain.items():
        pts.setdefault(k, []).append((x, y))
    return wall, bnd, pts


def score_one(spec, model):
    wall, bnd, pts = detected(model)
    used = {k: set() for k in pts}
    ok = total = 0
    rows = []
    for e in spec["elements"]:
        total += 1
        t = e["type"]
        good = False
        if t in ("wall", "boundary"):
            cells = seg_cells(*e["points"])
            ref = wall if t == "wall" else bnd
            hit = sum(1 for c in cells if near(c, ref))
            good = hit / len(cells) >= LINE_COVER
        else:
            k = e["subtype"]
            x, y = e["points"][0]
            for i, c in enumerate(pts.get(k, [])):
                if i not in used[k] and abs(c[0] - x) <= TOL and abs(c[1] - y) <= TOL:
                    used[k].add(i)
                    good = True
                    break
        ok += good
        rows.append((t, e.get("subtype", ""), good))
    return ok, total, rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "sketches"))
    ap.add_argument("--target", type=float, default=85.0)
    ap.add_argument("--report")
    a = ap.parse_args()
    specs = sorted(glob.glob(os.path.join(a.dir, "*.json")))
    if not specs:
        print("No annotated sketches found in", a.dir)
        return 2
    cfg = Config()
    accs, lines, times, by_type = [], [], [], {}
    for sp in specs:
        spec = json.load(open(sp, encoding="utf-8"))
        img = os.path.join(a.dir, spec["image"])
        t0 = time.perf_counter()
        try:
            _A, model, _st = run_pipeline(img, cfg, spec.get("cell_mm", cfg.cell_mm))
        except Exception as ex:
            print(f"{spec['name']}: FAILED ({ex})")
            accs.append(0.0)
            lines.append(f"| {spec['name']} | - | - | 0.0% | - | failed: {ex} |")
            continue
        dt = time.perf_counter() - t0
        ok, total, rows = score_one(spec, model)
        for t, sub, good in rows:
            d = by_type.setdefault(t, [0, 0])
            d[0] += good
            d[1] += 1
        acc = 100.0 * ok / total
        accs.append(acc)
        times.append(dt)
        miss = ", ".join(f"{t}{':' + s if s else ''}" for t, s, g in rows if not g) or "-"
        lines.append(f"| {spec['name']} | {ok}/{total} | {acc:.1f}% | {dt:.2f}s | {miss} |")
        print(f"{spec['name']}: {ok}/{total} = {acc:.1f}%  ({dt:.2f}s)  missed: {miss}")
    avg = float(np.mean(accs))
    print(f"\nAVERAGE RECOGNITION ACCURACY over {len(accs)} sketches: {avg:.1f}%  (target >= {a.target:.0f}%)")
    print(f"Slowest sketch: {max(times):.2f}s  (SRS 5.1.1 budget 10 s)")
    for t, (g, n) in sorted(by_type.items()):
        print(f"  {t:<13} {g}/{n} = {100*g/n:.1f}%")
    if a.report:
        with open(a.report, "w", encoding="utf-8") as f:
            f.write("# Recognition accuracy benchmark (SRS 5.1.3)\n\n")
            f.write(f"Sketches: {len(accs)} | tolerance: +/-{TOL} cell | **average accuracy: {avg:.1f}%** (target >= {a.target:.0f}%)\n\n")
            f.write("| Sketch | Correct | Accuracy | Time | Missed |\n|---|---|---|---|---|\n" + "\n".join(lines) + "\n\n")
            f.write("| Element type | Correct | Accuracy |\n|---|---|---|\n")
            for t, (g, n) in sorted(by_type.items()):
                f.write(f"| {t} | {g}/{n} | {100*g/n:.1f}% |\n")
    return 0 if avg >= a.target else 1


if __name__ == "__main__":
    sys.exit(main())
