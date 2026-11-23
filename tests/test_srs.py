import hashlib
import json
import os
import re
import sys
import time

import cv2
import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "benchmark"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from sketchmap.config import Config
from sketchmap.pipeline import run_pipeline
from sketchmap.exporters import to_json_dict, save_json, save_tscn, existing_outputs
from sketchmap.schema import validate
from sketchmap.preprocess import load_image

SAMPLES = os.path.join(ROOT, "sketchmap", "ui", "samples")
SKETCHES = os.path.join(ROOT, "benchmark", "sketches")
CFG = Config()


@pytest.fixture(scope="module")
def demo():
    return run_pipeline(os.path.join(SAMPLES, "symbol_demo.png"), CFG, 8.0)


@pytest.mark.parametrize("kind", ["empty", "text_as_png", "truncated", "missing", "blank_page", "flat_low_contrast"])
def test_bad_input_gives_message_not_crash(tmp_path, kind):
    p = tmp_path / "x.png"
    if kind == "empty":
        p.write_bytes(b"")
    elif kind == "text_as_png":
        p.write_text("not an image")
    elif kind == "truncated":
        good = open(os.path.join(SAMPLES, "symbol_demo.png"), "rb").read()
        p.write_bytes(good[:2500])
    elif kind == "missing":
        p = tmp_path / "nope.png"
    elif kind == "blank_page":
        cv2.imwrite(str(p), np.full((800, 600, 3), 255, np.uint8))
    elif kind == "flat_low_contrast":
        rng = np.random.RandomState(0)
        cv2.imwrite(str(p), (200 + rng.randint(0, 5, (800, 600, 3))).astype(np.uint8))
    with pytest.raises(ValueError) as ex:
        run_pipeline(str(p), CFG, 8.0)
    assert len(str(ex.value)) > 10


def test_oversized_image_refused(tmp_path, monkeypatch):
    import sketchmap.preprocess as pp
    monkeypatch.setattr(pp, "MAX_IMAGE_PIXELS", 1000)
    cv2.imwrite(str(tmp_path / "big.png"), np.full((100, 100, 3), 255, np.uint8))
    with pytest.raises(ValueError, match="too many pixels"):
        load_image(str(tmp_path / "big.png"))


def test_symbol_demo_is_recognised(demo):
    A, model, _ = demo
    kinds = {k for (k, _f) in model.objects.values()}
    assert {"arrow_start", "door", "enemy_spawn", "breakable_prop"} <= kinds
    c = model.counts()
    assert c["boundary"] == 4 and c["walls"] >= 3


def test_unclassified_shape_is_flagged(tmp_path):
    img = np.full((1131, 1600, 3), 255, np.uint8)
    cv2.rectangle(img, (200, 150), (1400, 950), (0, 0, 0), 6)
    cv2.ellipse(img, (700, 500), (40, 28), 0, 0, 360, (0, 0, 0), 5)
    cv2.imwrite(str(tmp_path / "o.png"), img)
    A, model, _ = run_pipeline(str(tmp_path / "o.png"), CFG, 8.0)
    assert len(A.unclassified) == 1
    assert not any(True for (k, _f) in model.objects.values() if k not in ("breakable_prop",))


def test_fragmented_stroke_warns_and_is_pinned(tmp_path):
    img = np.full((1131, 1600, 3), 255, np.uint8)
    cv2.rectangle(img, (200, 150), (1400, 950), (0, 0, 0), 6)
    cv2.line(img, (700, 500), (720, 505), (0, 0, 0), 5)
    cv2.imwrite(str(tmp_path / "f.png"), img)
    A, _m, _ = run_pipeline(str(tmp_path / "f.png"), CFG, 8.0)
    frag = [w for w in A.warnings if "fragmented stroke excluded" in w]
    assert len(frag) == 1 and re.search(r"near \(\d+% x, \d+% y\)", frag[0])
    pin = (np.abs(A.previews["thinned"].astype(int) - np.array([0, 140, 255])).sum(axis=2) < 30)
    assert pin.sum() > 20


def test_same_sketch_same_export(tmp_path):
    p = os.path.join(SKETCHES, "sketch_01.png")
    hashes = set()
    for _ in range(3):
        _A, model, _ = run_pipeline(p, CFG, 8.0)
        hashes.add(hashlib.md5(json.dumps(to_json_dict(model, CFG), sort_keys=True).encode()).hexdigest())
        f = tmp_path / "t.tscn"
        save_tscn(str(f), model, CFG)
        hashes.add(hashlib.md5(f.read_bytes()).hexdigest())
    assert len(hashes) == 2


def test_json_conforms_to_srs_schema(demo, tmp_path):
    _A, model, _ = demo
    f = tmp_path / "level.json"
    save_json(str(f), model, CFG)
    data = json.loads(f.read_text(encoding="utf-8"))
    assert validate(data) == []
    assert data["schema_version"] and data["origin"] == "top-left" and data["coordinate_system"] == "grid"
    assert all(e["has_collider"] for e in data["elements"] if e["type"] in ("wall", "boundary"))


def test_validator_catches_a_broken_file():
    assert validate({"schema_version": "1.0"})
    bad = {"schema_version": "1.0", "coordinate_system": "grid", "origin": "top-left", "grid_width": 5, "grid_height": 5,
           "cell_size_px": 32, "elements": [{"id": "wall_001", "type": "wall", "points": [[0, 0], [9, 0]], "has_collider": True}]}
    assert any("outside" in p for p in validate(bad))


def test_tscn_has_tilemap_colliders_and_every_file_it_references(demo, tmp_path):
    _A, model, _ = demo
    f = tmp_path / "level.tscn"
    save_tscn(str(f), model, CFG)
    txt = f.read_text(encoding="utf-8")
    assert txt.startswith("[gd_scene")
    assert 'type="TileMapLayer"' in txt and "Walls_Boundary" in txt
    tres = (tmp_path / "master_tileset.tres").read_text(encoding="utf-8")
    assert "physics_layer_0/polygon_0/points" in tres
    refs = set()
    for fp in [f, tmp_path / "master_tileset.tres", *(tmp_path / "prefabs").glob("*.tscn")]:
        refs |= set(re.findall(r'res://([^"\s)]+)', fp.read_text(encoding="utf-8")))
    missing = [r for r in refs if not (tmp_path / r).exists()]
    assert missing == []


def test_existing_outputs_are_reported(demo, tmp_path):
    _A, model, _ = demo
    f = tmp_path / "level.json"
    assert existing_outputs(str(f), "json") == []
    save_json(str(f), model, CFG)
    assert [os.path.basename(x) for x in existing_outputs(str(f), "json")] == ["level.json"]
    t = tmp_path / "level.tscn"
    save_tscn(str(t), model, CFG)
    found = [os.path.basename(x) for x in existing_outputs(str(t), "tscn")]
    assert "level.tscn" in found and "master_tileset.tres" in found


def test_pipeline_under_ten_seconds():
    for name in sorted(os.listdir(SKETCHES))[:6]:
        if name.endswith(".png"):
            t = time.perf_counter()
            run_pipeline(os.path.join(SKETCHES, name), CFG, 8.0)
            assert time.perf_counter() - t < 10.0


def test_recognition_accuracy_meets_target():
    import glob
    import score
    accs = []
    for sp in sorted(glob.glob(os.path.join(SKETCHES, "*.json"))):
        spec = json.load(open(sp, encoding="utf-8"))
        _A, model, _ = run_pipeline(os.path.join(SKETCHES, spec["image"]), CFG, spec["cell_mm"])
        ok, total, _ = score.score_one(spec, model)
        accs.append(100.0 * ok / total)
    assert len(accs) >= 20
    assert float(np.mean(accs)) >= 85.0


def test_no_network_code_in_the_application():
    banned = re.compile(r"^\s*(import|from)\s+(socket|requests|urllib|http\.client|ftplib|smtplib|aiohttp|httpx)\b", re.M)
    for dp, _dn, files in os.walk(os.path.join(ROOT, "sketchmap")):
        for fn in files:
            if fn.endswith(".py"):
                src = open(os.path.join(dp, fn), encoding="utf-8").read()
                assert not banned.search(src), f"{fn} imports a network module"


def test_gui_menu_icon_and_dialogs():
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from sketchmap.ui import theme
    theme.setup_fonts()
    from sketchmap.ui.main_window import MainWindow
    from sketchmap.ui.help_dialog import HelpDialog
    from sketchmap.ui.settings import SettingsDialog
    w = MainWindow()
    assert w._menu_btn.toolTip() == "Menu"
    assert w._menu_btn._name == "menu"
    HelpDialog(w)
    SettingsDialog(w)
    w.close()


def test_beta_notice_lists_exactly_the_recognized_symbols():
    """The beta notice is generated from Element.detected; it must name exactly the five detected symbols."""
    from sketchmap import beta
    assert beta.names() == ["Boundary", "Wall", "Player start", "Enemy spawn", "Door"]
    assert beta.status_for("door") == beta.FROM_PHOTO
    assert beta.status_for("lava") == beta.EDITOR_ONLY
    assert "Beta" in beta.plain_text()
