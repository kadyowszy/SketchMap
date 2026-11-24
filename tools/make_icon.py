import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def main():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from sketchmap.ui import icons
    from PIL import Image
    pm = icons.logo_pixmap(256, 1.0)
    png = os.path.join(ROOT, "sketchmap", "ui", "assets", "app_icon.png")
    os.makedirs(os.path.dirname(png), exist_ok=True)
    pm.save(png)
    ico = os.path.join(ROOT, "packaging", "sketchmap.ico")
    Image.open(png).convert("RGBA").save(ico, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("wrote", png, "and", ico)


if __name__ == "__main__":
    main()
