import filecmp
import json
import os
import shutil

from . import elements as el
from . import godot_export, tileset


def sheet_conflict(path, spec=None):
    spec = spec or tileset.default_spec()
    dst = os.path.join(os.path.dirname(os.path.abspath(path)), os.path.basename(spec.image_path))
    if os.path.abspath(dst) == os.path.abspath(spec.image_path) or not os.path.exists(dst):
        return None
    try:
        return None if filecmp.cmp(spec.image_path, dst, shallow=False) else dst
    except OSError:
        return dst


def existing_outputs(path, fmt):
    folder = os.path.dirname(os.path.abspath(path))
    out = [path] if os.path.exists(path) else []
    tres = os.path.join(folder, godot_export.TILESET_FILE)
    if fmt == "tscn" and os.path.exists(tres):
        out.append(tres)
    return out


def _copy_sheet(path, spec, overwrite=False):
    dst = os.path.join(os.path.dirname(os.path.abspath(path)), os.path.basename(spec.image_path))
    if os.path.abspath(dst) == os.path.abspath(spec.image_path):
        return
    if overwrite or not os.path.exists(dst):
        shutil.copyfile(spec.image_path, dst)


def to_json_dict(model, cfg, cell_mm=None, tileset_spec=None):
    spec = tileset_spec or tileset.default_spec()
    els, n = [], {}

    def nid(t):
        n[t] = n.get(t, 0) + 1
        return f"{t}_{n[t]:03d}"
    for s in model.segments:
        t = "boundary" if s.kind == "boundary" else "wall"
        els.append(dict(id=nid(t), type=t, points=[[s.x1, s.y1], [s.x2, s.y2]], has_collider=True))
    for (x, y), (k, f) in sorted(model.terrain.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        e = dict(id=nid("terrain"), type="terrain", subtype=k, points=[[x, y]])
        if el.is_directional(k):
            e["direction"] = el.DIRS[f]
        els.append(e)
    for (x, y), (k, f) in sorted(model.objects.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        t = "symbol" if k in el.SYMBOLS else "interactable"
        e = dict(id=nid(t), type=t, subtype=k, points=[[x, y]])
        if el.is_directional(k):
            e["facing"] = el.DIRS[f]
        els.append(e)
    sc = dict(model.scale)
    return dict(schema_version="1.2", coordinate_system="grid", origin="top-left",
                grid_width=model.width, grid_height=model.height, cell_size_px=cfg.export_tile_px,
                scale=sc, size_class=model.size_class(cfg),
                tileset={"image": os.path.basename(spec.image_path), "tile_px": spec.tile_px, "res_dir": spec.res_dir,
                         "tiles": {k: list(v) for k, v in tileset.resolved(spec.tiles).items()}},
                elements=els, tile_matrix=model.tile_matrix().tolist())


def save_json(path, model, cfg, tileset_spec=None, overwrite_sheet=False):
    spec = tileset_spec or tileset.default_spec()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(to_json_dict(model, cfg, tileset_spec=spec), f, indent=2)
    if os.path.abspath(spec.image_path) != os.path.abspath(tileset.DEFAULT_SHEET):
        _copy_sheet(path, spec, overwrite_sheet)

def to_tscn(model, cfg, tileset_spec=None):
    return godot_export.to_tscn(model, cfg, tileset_spec)


def save_tscn(path, model, cfg, tileset_spec=None, overwrite_sheet=False):
    spec = tileset_spec or tileset.default_spec()
    with open(path, "w", encoding="utf-8") as f:
        f.write(to_tscn(model, cfg, spec))
    _copy_sheet(path, spec, overwrite_sheet)
    godot_export.write_support_files(os.path.dirname(os.path.abspath(path)), spec)
