#!/usr/bin/env bash
set -euo pipefail
python3 -m pip install -r requirements-dev.txt
python3 -m pytest -q
python3 tools/make_icon.py
python3 -m PyInstaller --noconfirm packaging/sketchmap.spec
echo "Done: dist/SketchMap/  (zip that folder to share it)"
