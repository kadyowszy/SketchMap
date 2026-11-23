# SketchMap

An offline desktop tool that turns a photo or scan of a hand-drawn level (black pen, white A4) into an editable 2D grid map and
exports it as **JSON** (any engine) or a **Godot scene (.tscn)** with a tile map and physics colliders.
Classical image processing only (OpenCV: illumination correction, thresholding, Zhang-Suen thinning, Ramer-Douglas-Peucker). No AI, no accounts, no network.

> **Beta build.** From a photo, SketchMap currently recognizes only: Boundary, Wall, Player start (an arrow), Enemy spawn (a hollow triangle) and Door (a hollow box in a wall gap). Other symbols are not recognized yet; place them in the Edit page. The app says this on the Home page, in Library, in About and in the window title.

## Run it

```bash
python -m pip install -r requirements.txt
python main.py                 # opens the app;  python main.py sketch.png  opens a sketch directly
```

Headless: `python -m sketchmap.cli sketch.png --out out/` writes `level.json`, `level.tscn`, previews and the stats text.

## Use it

Import a sketch (Ctrl+O or drag-and-drop) -> straighten it in *Prepare & Straighten* -> check the map -> fix anything in the Edit page -> Export.
The three-line **menu** (bottom left) opens the user manual (F1), symbol legend, shortcuts, settings and About.
**Themes:** choose *Match system*, *Dark*, *Light*, *Midnight* or *High contrast* from Menu → Theme (or Settings → Appearance). The change is instant and remembered.
A print-ready drawing guide is in `sketchmap/docs/drawing_guide.png`; the full manual is `docs/USER_MANUAL.pdf`.

## Check it

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q                         # 19 checks mapped to SRS requirements
python benchmark/score.py                   # recognition accuracy (SRS 5.1.3) + timing (SRS 5.1.1)
python -m sketchmap.schema level.json       # validate an export against the SRS 3.3.4 format
python tools/make_test_report.py            # regenerate docs/TEST_REPORT.md
```

## Build the standalone app

`packaging\build.bat` (Windows) or `bash packaging/build.sh` -> `dist/SketchMap/`. Zip that folder; users need no Python.

## Layout

| Path | What |
|---|---|
| `sketchmap/` | the application: `preprocess`, `segmentation`, `thinning`, `vectorize`, `gridmap`, `exporters`, `godot_export`, `pipeline`, `ui/` |
| `sketchmap/docs/` | in-app manual + drawing guide |
| `docs/` | PDF manual, SRS addendum, architecture notes, test report |
| `tests/` | automated SRS checks |
| `benchmark/` | sketch generator, ground-truth scorer |
| `tools/` | manual / icon / report builders |
| `packaging/` | PyInstaller spec and build scripts |

Requirements: Python 3.10+, PyQt6, OpenCV, NumPy, Pillow (see `requirements.txt`).
