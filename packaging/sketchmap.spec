import os
ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
datas = [
    (os.path.join(ROOT, "sketchmap", "assets"), "sketchmap/assets"),
    (os.path.join(ROOT, "sketchmap", "ui", "samples"), "sketchmap/ui/samples"),
    (os.path.join(ROOT, "sketchmap", "docs"), "sketchmap/docs"),
]
fonts = os.path.join(ROOT, "sketchmap", "ui", "assets")
if os.path.isdir(fonts):
    datas.append((fonts, "sketchmap/ui/assets"))
icon = os.path.join(ROOT, "packaging", "sketchmap.ico")

a = Analysis([os.path.join(ROOT, "main.py")], pathex=[ROOT], datas=datas,
             hiddenimports=["PIL", "PyQt6.QtSvg"], excludes=["tkinter", "matplotlib"])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="SketchMap", console=False,
          icon=icon if os.path.isfile(icon) else None)
coll = COLLECT(exe, a.binaries, a.datas, name="SketchMap")
