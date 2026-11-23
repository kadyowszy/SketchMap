import copy
from dataclasses import dataclass, field
import numpy as np

from . import elements as el

KINDS = ("wall", "boundary")


@dataclass
class Segment:
    kind: str
    x1: int
    y1: int
    x2: int
    y2: int

    def tiles(self):
        if self.y1 == self.y2:
            return [(x, self.y1) for x in range(self.x1, self.x2 + 1)]
        return [(self.x1, y) for y in range(self.y1, self.y2 + 1)]

    def covers(self, x, y):
        return self.x1 <= x <= self.x2 and self.y1 <= y <= self.y2


class MapModel:
    def __init__(self, width, height, scale=None):
        self.width, self.height = width, height
        self.segments = []
        self.terrain = {}
        self.objects = {}
        self.scale = scale or {}
        self.edits = 0
        self.notes = []

    def snapshot(self):
        return copy.deepcopy((self.segments, self.terrain, self.objects, self.edits))

    def restore(self, snap):
        self.segments, self.terrain, self.objects, self.edits = copy.deepcopy(snap)

    @property
    def spawns(self):
        return sorted(xy for xy, (k, _f) in self.objects.items() if k == "arrow_start")

    def objects_of(self, category):
        keys = el.SYMBOLS if category == "symbol" else el.INTERACTABLES
        return {xy: v for xy, v in self.objects.items() if v[0] in keys}

    def wall_at(self, x, y):
        return any(s.covers(x, y) for s in self.segments)

    def inside(self, x, y):
        return 0 <= x < self.width and 0 <= y < self.height

    def _on_border(self, s):
        W, H = self.width, self.height
        if s.y1 == s.y2 and s.x1 != s.x2:
            return s.y1 in (0, H - 1)
        if s.x1 == s.x2 and s.y1 != s.y2:
            return s.x1 in (0, W - 1)
        return False

    def normalize(self):
        groups = {}
        for s in self.segments:
            s.kind = "boundary" if self._on_border(s) else "wall"
            horiz = s.y1 == s.y2
            key = (s.kind, "H" if horiz else "V", s.y1 if horiz else s.x1)
            groups.setdefault(key, []).append(s)
        out = []
        for (kind, o, c), lst in groups.items():
            lst.sort(key=lambda s: (s.x1, s.y1))
            cur = None
            for s in lst:
                a, b = (s.x1, s.x2) if o == "H" else (s.y1, s.y2)
                if cur and a <= cur[1] + 1:
                    cur[1] = max(cur[1], b)
                else:
                    if cur:
                        out.append(self._mk(kind, o, c, *cur))
                    cur = [a, b]
            if cur:
                out.append(self._mk(kind, o, c, *cur))
        out.sort(key=lambda s: (s.kind, s.y1, s.x1, s.y2, s.x2))
        self.segments = out
        self.prune()

    def prune(self):
        for d in (self.terrain, self.objects):
            for xy in [xy for xy in d if not self.inside(*xy) or self.wall_at(*xy)]:
                del d[xy]

    @staticmethod
    def _mk(kind, o, c, a, b):
        return Segment(kind, a, c, b, c) if o == "H" else Segment(kind, c, a, c, b)

    def add_segment(self, kind, p, q):
        (x1, y1), (x2, y2) = p, q
        if abs(x2 - x1) >= abs(y2 - y1):
            y2 = y1
        else:
            x2 = x1
        x1, x2 = sorted((x1, x2)); y1, y2 = sorted((y1, y2))
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(self.width - 1, x2), min(self.height - 1, y2)
        if x2 < x1 or y2 < y1:
            return
        self.segments.append(Segment(kind, x1, y1, x2, y2))
        self.normalize()
        self.edits += 1

    def erase_tile(self, x, y):
        new, hit = [], False
        for s in self.segments:
            if not s.covers(x, y):
                new.append(s)
                continue
            hit = True
            if s.y1 == s.y2:
                if x > s.x1: new.append(Segment(s.kind, s.x1, s.y1, x - 1, s.y2))
                if x < s.x2: new.append(Segment(s.kind, x + 1, s.y1, s.x2, s.y2))
            else:
                if y > s.y1: new.append(Segment(s.kind, s.x1, s.y1, s.x2, y - 1))
                if y < s.y2: new.append(Segment(s.kind, s.x1, y + 1, s.x2, s.y2))
        self.segments = new
        for d in (self.objects, self.terrain):
            if d.pop((x, y), None) is not None:
                hit = True
        if hit:
            self.normalize(); self.edits += 1
        return hit

    def place(self, key, x, y, facing=0):
        e = el.BY_KEY.get(key)
        if e is None or e.category == "structural" or not self.inside(x, y) or self.wall_at(x, y):
            return False
        layer = self.terrain if e.category == "terrain" else self.objects
        new = (key, facing % 4 if e.directional else 0)
        if layer.get((x, y)) == new:
            return False
        layer[(x, y)] = new
        self.edits += 1
        return True

    def toggle(self, key, x, y, facing=0):
        e = el.BY_KEY.get(key)
        layer = self.terrain if e and e.category == "terrain" else self.objects
        cur = layer.get((x, y))
        if cur and cur[0] == key:
            del layer[(x, y)]
            self.edits += 1
            return True
        return self.place(key, x, y, facing)

    def rotate_at(self, x, y):
        for layer in (self.objects, self.terrain):
            cur = layer.get((x, y))
            if cur and el.is_directional(cur[0]):
                layer[(x, y)] = (cur[0], (cur[1] + 1) % 4)
                self.edits += 1
                return True
        return False

    def describe(self, x, y):
        parts = []
        if self.wall_at(x, y):
            parts.append(next(s.kind for s in self.segments if s.covers(x, y)))
        for layer in (self.terrain, self.objects):
            cur = layer.get((x, y))
            if cur:
                parts.append(cur[0] + (f" facing {el.DIRS[cur[1]]}" if el.is_directional(cur[0]) else ""))
        return ", ".join(parts) if parts else "floor"

    def tile_matrix(self):
        m = np.zeros((self.height, self.width), np.uint8)
        for code, kind in ((1, "wall"), (3, "boundary")):
            for s in self.segments:
                if s.kind == kind:
                    for x, y in s.tiles():
                        if self.inside(x, y): m[y, x] = code
        return m

    def counts(self):
        return dict(walls=sum(s.kind == "wall" for s in self.segments),
                    boundary=sum(s.kind == "boundary" for s in self.segments),
                    terrain=len(self.terrain),
                    symbols=sum(v[0] in el.SYMBOLS for v in self.objects.values()),
                    interactables=sum(v[0] in el.INTERACTABLES for v in self.objects.values()))

    def size_class(self, cfg):
        cells = self.width * self.height
        return "small" if cells <= cfg.size_small_cells else "medium" if cells <= cfg.size_medium_cells else "large"
