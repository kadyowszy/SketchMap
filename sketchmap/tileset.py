import json
import os
import shutil
from dataclasses import dataclass, field

import cv2
import numpy as np

KINDS = ("floor", "wall", "boundary", "grass", "water", "lava", "ice", "mud", "conveyor")
REQUIRED = ("floor", "wall")
FALLBACK = {"boundary": "wall"}
LEGACY_KINDS = ("breakable", "raised")

DEFAULT_SHEET = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "sketchmap_tiles.png")
DEFAULT_TILE_PX = 64
DEFAULT_TILES = {"floor": (0, 3), "wall": (16, 8), "boundary": (17, 8), "grass": (0, 9), "water": (12, 11),
                 "lava": (14, 11), "ice": (12, 10), "mud": (15, 11), "conveyor": (16, 10)}


@dataclass
class TilesetSpec:
    image_path: str
    tile_px: int
    tiles: dict = field(default_factory=dict)
    res_dir: str = "res://"

    @property
    def res_path(self):
        d = self.res_dir if self.res_dir.endswith("/") else self.res_dir + "/"
        return d + os.path.basename(self.image_path)


def default_spec():
    return TilesetSpec(DEFAULT_SHEET, DEFAULT_TILE_PX, dict(DEFAULT_TILES), "res://")


def _read_size(path):
    try:
        img = cv2.imdecode(np.fromfile(path, np.uint8), cv2.IMREAD_UNCHANGED)
    except OSError:
        raise ValueError(f"Cannot find or read the tileset image '{os.path.basename(path)}'.")
    if img is None:
        raise ValueError(f"'{os.path.basename(path)}' is not a readable PNG/JPG image.")
    return img.shape[1], img.shape[0]


COMMON_TILE_PX = (64, 48, 32, 24, 16, 8)


def guess_layout(w, h):
    if h < w and w % h == 0:
        return h
    for px in COMMON_TILE_PX:
        if w % px == 0 and h % px == 0:
            return px
    from math import gcd
    return max(1, gcd(w, h))


def load_tileset(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".json":
        try:
            with open(path, "r", encoding="utf-8") as f:
                d = json.load(f)
            image = os.path.join(os.path.dirname(os.path.abspath(path)), d["image"])
            tile_px = int(d["tile_px"])
            raw = d["tiles"]
            tiles = {k: (int(raw[k][0]), int(raw[k][1])) for k in raw}
        except (OSError, json.JSONDecodeError) as ex:
            raise ValueError(f"Cannot read tileset manifest: {ex}")
        except (KeyError, TypeError, ValueError, IndexError):
            raise ValueError('Manifest needs "image", "tile_px" and "tiles" (kind -> [column, row]).')
        res_dir = str(d.get("res_dir", "res://"))
    elif ext in (".png", ".jpg", ".jpeg"):
        image = os.path.abspath(path)
        w, h = _read_size(image)
        tile_px, tiles, res_dir = guess_layout(w, h), None, "res://"
        cols, rows = w // tile_px, h // tile_px
        cells = [(i % cols, i // cols) for i in range(min(len(KINDS), cols * rows))]
        tiles = dict(zip(KINDS, cells))
    else:
        raise ValueError("Tileset must be a .json manifest or a .png/.jpg sprite sheet.")
    spec = TilesetSpec(image, tile_px, tiles, res_dir if res_dir.startswith("res://") else "res://" + res_dir)
    validate(spec)
    return spec


def validate(spec):
    if spec.tile_px < 1:
        raise ValueError("tile_px must be at least 1.")
    for k in list(spec.tiles):
        if k in LEGACY_KINDS:
            del spec.tiles[k]
    for k in spec.tiles:
        if k not in KINDS:
            raise ValueError(f"Unknown tile kind '{k}'. Use: {', '.join(KINDS)}.")
    for k in REQUIRED:
        if k not in spec.tiles:
            raise ValueError(f"The tileset must map at least '{' and '.join(REQUIRED)}'.")
    w, h = _read_size(spec.image_path)
    for k, (ax, ay) in spec.tiles.items():
        if ax < 0 or ay < 0 or (ax + 1) * spec.tile_px > w or (ay + 1) * spec.tile_px > h:
            raise ValueError(f"Tile '{k}' at [{ax}, {ay}] lies outside the {w}x{h} image "
                             f"(tile size {spec.tile_px}px).")


def resolved(spec_tiles):
    return {k: spec_tiles.get(k) or spec_tiles[FALLBACK.get(k, "floor")] for k in KINDS}


def write_template(folder):
    os.makedirs(folder, exist_ok=True)
    png, man = os.path.join(folder, "tileset_template.png"), os.path.join(folder, "tileset_template.json")
    shutil.copyfile(DEFAULT_SHEET, png)
    with open(man, "w", encoding="utf-8") as f:
        json.dump({"image": "tileset_template.png", "tile_px": DEFAULT_TILE_PX, "res_dir": "res://",
                   "tiles": {k: list(v) for k, v in DEFAULT_TILES.items()}}, f, indent=2)
    return png, man
