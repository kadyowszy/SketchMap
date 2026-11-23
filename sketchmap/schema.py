import json
import re
import sys

REQUIRED_TOP = {"schema_version": str, "coordinate_system": str, "origin": str, "grid_width": int, "grid_height": int,
                "cell_size_px": int, "elements": list}
TYPES = {"wall", "boundary", "terrain", "symbol", "interactable"}
LINE_TYPES = {"wall", "boundary"}
ID_RE = re.compile(r"^(wall|boundary|terrain|symbol|interactable)_\d{3,}$")


def validate(data):
    errs = []
    if not isinstance(data, dict):
        return ["top level is not a JSON object"]
    for k, t in REQUIRED_TOP.items():
        if k not in data:
            errs.append(f"missing top-level field '{k}'")
        elif not isinstance(data[k], t) or isinstance(data[k], bool):
            errs.append(f"'{k}' should be {t.__name__}")
    if errs:
        return errs
    if data["coordinate_system"] != "grid":
        errs.append("coordinate_system must be 'grid'")
    if data["origin"] != "top-left":
        errs.append("origin must be 'top-left'")
    W, H = data["grid_width"], data["grid_height"]
    if W < 1 or H < 1 or data["cell_size_px"] < 1:
        errs.append("grid_width, grid_height and cell_size_px must be positive")
    seen = set()
    for i, e in enumerate(data["elements"]):
        where = f"elements[{i}]"
        if not isinstance(e, dict):
            errs.append(f"{where} is not an object")
            continue
        eid, t, pts = e.get("id"), e.get("type"), e.get("points")
        if not isinstance(eid, str) or not ID_RE.match(eid):
            errs.append(f"{where}: bad id {eid!r} (expected e.g. wall_001)")
        elif eid in seen:
            errs.append(f"{where}: duplicate id {eid}")
        seen.add(eid)
        if t not in TYPES:
            errs.append(f"{where}: unknown type {t!r}")
            continue
        if isinstance(eid, str) and not eid.startswith(t + "_"):
            errs.append(f"{where}: id {eid} does not match type {t}")
        if t in LINE_TYPES:
            if e.get("has_collider") is not True:
                errs.append(f"{where}: {t} must have has_collider: true")
            if not isinstance(pts, list) or len(pts) < 2:
                errs.append(f"{where}: {t} needs at least 2 points")
        else:
            if not isinstance(e.get("subtype"), str) or not e["subtype"]:
                errs.append(f"{where}: {t} needs a subtype")
            if not isinstance(pts, list) or len(pts) < 1:
                errs.append(f"{where}: {t} needs at least 1 point")
        for p in pts if isinstance(pts, list) else []:
            if (not isinstance(p, list) or len(p) != 2 or not all(isinstance(v, int) and not isinstance(v, bool) for v in p)):
                errs.append(f"{where}: point {p!r} is not [x, y] integers")
            elif not (0 <= p[0] <= W and 0 <= p[1] <= H):
                errs.append(f"{where}: point {p} is outside the {W}x{H} grid")
    tm = data.get("tile_matrix")
    if tm is not None and (len(tm) != H or any(len(r) != W for r in tm)):
        errs.append(f"tile_matrix is not {W}x{H}")
    return errs


def main(argv=None):
    paths = (argv if argv is not None else sys.argv[1:])
    if not paths:
        print("usage: python -m sketchmap.schema level.json [more.json ...]")
        return 2
    bad = 0
    for p in paths:
        try:
            with open(p, encoding="utf-8") as f:
                problems = validate(json.load(f))
        except (OSError, ValueError) as ex:
            problems = [f"cannot read: {ex}"]
        print(f"{p}: " + ("OK, conforms to SRS 3.3.4" if not problems else f"{len(problems)} problem(s)"))
        for q in problems[:20]:
            print("  -", q)
        bad += bool(problems)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
