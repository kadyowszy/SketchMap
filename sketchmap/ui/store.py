import json
import os
import time
from pathlib import Path

SKETCH_EXT = (".png", ".jpg", ".jpeg")
LEVEL_EXT = (".json",)


def kind_of(path):
    ext = os.path.splitext(path)[1].lower()
    return "sketch" if ext in SKETCH_EXT else "level" if ext in LEVEL_EXT else None


def default_store_path():
    base = os.environ.get("SKETCHMAP_HOME")
    return Path(base) if base else Path.home() / ".sketchmap" / "recent.json"


def _norm(path):
    return os.path.normcase(os.path.abspath(path))


class RecentStore:
    def __init__(self, path=None, limit=60):
        self.path = Path(path) if path else default_store_path()
        self.limit = limit
        self.entries = []
        self.load()

    def load(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.entries = [e for e in data.get("files", []) if isinstance(e, dict) and e.get("path")]
        except (OSError, ValueError, AttributeError):
            self.entries = []

    def save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"files": self.entries}, indent=2), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError:
            pass

    def find(self, path):
        key = _norm(path)
        return next((e for e in self.entries if _norm(e["path"]) == key), None)

    def items(self, favorites_only=False, query=""):
        q = query.strip().lower()
        out = [e for e in self.entries
               if (not favorites_only or e.get("favorite"))
               and (not q or q in os.path.basename(e["path"]).lower())]
        return sorted(out, key=lambda e: e.get("opened", 0), reverse=True)

    def touch(self, path, kind):
        e = self.find(path)
        if e is None:
            e = dict(path=os.path.abspath(path), kind=kind, favorite=False)
            self.entries.append(e)
        e["kind"], e["opened"] = kind, time.time()
        self.entries = sorted(self.entries, key=lambda x: x.get("opened", 0), reverse=True)[: self.limit]
        self.save()

    def toggle_favorite(self, path):
        e = self.find(path)
        if e:
            e["favorite"] = not e.get("favorite", False)
            self.save()
            return e["favorite"]
        return False

    def remove(self, path):
        key = _norm(path)
        self.entries = [e for e in self.entries if _norm(e["path"]) != key]
        self.save()
