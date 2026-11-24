import argparse, os, sys, cv2
from .config import Config
from .pipeline import run_pipeline
from .renderer import render_map
from .exporters import save_json, save_tscn
from .tileset import load_tileset, write_template
from .version import VERSION_LABEL
from . import recognition


def main(argv=None):
    ap = argparse.ArgumentParser(description="SketchMap headless run")
    ap.add_argument("image", nargs="?"); ap.add_argument("--tileset", help="custom tile set: sprite sheet or manifest .json")
    ap.add_argument("--tileset-template", metavar="DIR", help="write a starter sprite sheet + manifest to DIR and exit")
    ap.add_argument("--out", default="out"); ap.add_argument("--cell-mm", type=float, default=8.0)
    a = ap.parse_args(argv)
    if a.tileset_template:
        print("Wrote", *write_template(a.tileset_template)); return
    if not a.image: ap.error("image is required")
    ts = load_tileset(a.tileset) if a.tileset else None
    cfg = Config()
    A, model, st = run_pipeline(a.image, cfg, a.cell_mm)
    os.makedirs(a.out, exist_ok=True)
    for k, v in A.previews.items():
        cv2.imwrite(os.path.join(a.out, f"{k}.png"), v)
    cv2.imwrite(os.path.join(a.out, "grid.png"), render_map(model, 22))
    cv2.imwrite(os.path.join(a.out, "grid_on_sketch.png"), render_map(model, 22, A, True))
    save_json(os.path.join(a.out, "level.json"), model, cfg, ts)
    save_tscn(os.path.join(a.out, "level.tscn"), model, cfg, ts)
    open(os.path.join(a.out, "stats.txt"), "w", encoding="utf-8").write(st.render())
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    print(f"SketchMap {VERSION_LABEL}: recognizes {len(recognition.names())} elements from a photo")
    print(st.render())
    for w in A.warnings: print("WARNING:", w)


if __name__ == "__main__":
    main()
