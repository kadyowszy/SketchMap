@echo off
python -m pip install -r requirements-dev.txt || exit /b 1
python tools\make_icon.py
python -m PyInstaller --noconfirm packaging\sketchmap.spec || exit /b 1
echo.
echo Done: dist\SketchMap\SketchMap.exe  (zip the dist\SketchMap folder to share it)
