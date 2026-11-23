from pathlib import Path
from string import Template

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFontDatabase, QGuiApplication, QPalette
from PyQt6.QtWidgets import QApplication

BASE = dict(
    bg="#0B0C0F",
    surface="#14151A",
    surface2="#1B1C22",
    surface3="#252730",
    border="#2A2C35",
    border2="#3B3E4A",
    text="#ECEDF0",
    muted="#A0A3AE",
    faint="#6C6F7B",
    accent="#F5C84B",
    accent_ink="#1A1403",
    accent_text="#F5C84B",
    accent_hover="#FFD763",
    accent_dis_bg="#3A3320",
    accent_dis_fg="#6E6444",
    danger="#F0605D",
    danger_bg="#2A1A1B",
    success="#4CC38A",
    info="#6EA8FF",
    orange="#F2994A",
    board="#101116",
    grid="#1D1F26",
    wall="#C9CCD6",
    boundary="#F1F2F6",
    inset="#0F1014",
    code_fg="#D6D8DF",
    pressed="#2D2F39",
    card_hover="#20222A",
    drop_bg="#1A1810",
    scheme="dark",
)

THEMES = {
    "dark": {},
    "light": dict(
        bg="#EEF0F4", surface="#FFFFFF", surface2="#F7F8FB", surface3="#E4E7EE",
        border="#DADDE6", border2="#BFC4D1",
        text="#15171D", muted="#555A69", faint="#868B9A",
        accent="#F5C84B", accent_ink="#1A1403", accent_text="#8A6100", accent_hover="#E9B72E",
        accent_dis_bg="#EFE3BC", accent_dis_fg="#A8975F",
        danger="#C9322F", danger_bg="#FBE9E8", success="#17895A", info="#2563D6", orange="#C96A12",
        board="#E6E9F0", grid="#D3D7E1", wall="#2A2D38", boundary="#0E1016",
        inset="#E9EBF1", code_fg="#2A2D38", pressed="#D6DAE3", card_hover="#EEF0F5", drop_bg="#FBF3DA",
        scheme="light",
    ),
    "midnight": dict(
        bg="#0A0F1F", surface="#0F1730", surface2="#151F3D", surface3="#1F2C52",
        border="#22305A", border2="#34477D",
        text="#E7EDFB", muted="#9DAAD0", faint="#6677A3",
        accent_dis_bg="#2D3150", accent_dis_fg="#6F7390", danger_bg="#2B1A28",
        board="#0C1330", grid="#17224A", wall="#C3CFEE", boundary="#F2F6FF",
        inset="#0B1230", code_fg="#D5DEF5", pressed="#26356A", card_hover="#1A2750", drop_bg="#1B2142",
    ),
    "contrast": dict(
        bg="#000000", surface="#0A0A0A", surface2="#141414", surface3="#2A2A2A",
        border="#8C8C8C", border2="#FFFFFF",
        text="#FFFFFF", muted="#E6E6E6", faint="#B8B8B8",
        accent="#FFD400", accent_text="#FFD400", accent_hover="#FFE24D",
        accent_dis_bg="#3A3400", accent_dis_fg="#8F8433", danger="#FF6B66", danger_bg="#3A0F0F",
        success="#3CE08F", info="#7DB6FF", orange="#FFA14D",
        board="#000000", grid="#303030", wall="#FFFFFF", boundary="#FFD400",
        inset="#000000", code_fg="#FFFFFF", pressed="#3A3A3A", card_hover="#1E1E1E", drop_bg="#2A2500",
    ),
}

THEME_CHOICES = (("system", "Match system"), ("dark", "Dark"), ("light", "Light"),
                 ("midnight", "Midnight"), ("contrast", "High contrast"))
DEFAULT_THEME = "dark"

P = dict(BASE)
_current = {"choice": DEFAULT_THEME, "resolved": DEFAULT_THEME}


class _Bus(QObject):
    changed = pyqtSignal()


bus = _Bus()


def col(x):
    return P.get(x, x)


def system_scheme():
    try:
        hints = QGuiApplication.styleHints()
        return "light" if hints.colorScheme() == Qt.ColorScheme.Light else "dark"
    except Exception:
        return DEFAULT_THEME


def resolve(choice):
    if choice == "system":
        return system_scheme()
    return choice if choice in THEMES else DEFAULT_THEME


def current_choice():
    return _current["choice"]


def _qpalette():
    pal = QPalette()
    c = lambda k: QColor(P[k])
    for role, key in ((QPalette.ColorRole.Window, "bg"), (QPalette.ColorRole.WindowText, "text"),
                      (QPalette.ColorRole.Base, "surface2"), (QPalette.ColorRole.AlternateBase, "surface"),
                      (QPalette.ColorRole.Text, "text"), (QPalette.ColorRole.Button, "surface2"),
                      (QPalette.ColorRole.ButtonText, "text"), (QPalette.ColorRole.ToolTipBase, "surface3"),
                      (QPalette.ColorRole.ToolTipText, "text"), (QPalette.ColorRole.Highlight, "accent"),
                      (QPalette.ColorRole.HighlightedText, "accent_ink"), (QPalette.ColorRole.PlaceholderText, "faint"),
                      (QPalette.ColorRole.Link, "info")):
        pal.setColor(role, c(key))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        pal.setColor(QPalette.ColorGroup.Disabled, role, c("faint"))
    return pal


def apply_theme(choice, app=None, save=True):
    app = app or QApplication.instance()
    if choice not in dict(THEME_CHOICES):
        choice = DEFAULT_THEME
    resolved = resolve(choice)
    P.clear()
    P.update(BASE)
    P.update(THEMES[resolved])
    _current.update(choice=choice, resolved=resolved)
    if save:
        from . import settings
        settings.put("theme", choice)
    if app is not None:
        app.setPalette(_qpalette())
        app.setStyleSheet(stylesheet())
        try:
            hints = app.styleHints()
            if choice == "system":
                hints.unsetColorScheme()
            else:
                hints.setColorScheme(Qt.ColorScheme.Light if P["scheme"] == "light" else Qt.ColorScheme.Dark)
        except Exception:
            pass
        bus.changed.emit()
        for w in app.allWidgets():
            w.update()


def follow_system(app):
    try:
        app.styleHints().colorSchemeChanged.connect(
            lambda *_: apply_theme("system", app, save=False) if _current["choice"] == "system" else None)
    except Exception:
        pass


FONT = dict(ui="Segoe UI", mono="Consolas", pixel="Consolas")

_UI_CANDIDATES = ("Inter", "Segoe UI Variable Text", "Segoe UI", "SF Pro Text", "Helvetica Neue", "Roboto", "Arial")
_MONO_CANDIDATES = ("JetBrains Mono", "Cascadia Mono", "Consolas", "SF Mono", "Menlo", "DejaVu Sans Mono", "Courier New")
_PIXEL_CANDIDATES = ("Press Start 2P", "Silkscreen", "Pixelify Sans", "VT323")


def setup_fonts():
    fdir = Path(__file__).parent / "assets" / "fonts"
    if fdir.is_dir():
        for f in sorted(fdir.iterdir()):
            if f.suffix.lower() in (".ttf", ".otf"):
                QFontDatabase.addApplicationFont(str(f))
    have = set(QFontDatabase.families())
    pick = lambda cands, fallback: next((c for c in cands if c in have), fallback)
    FONT["ui"] = pick(_UI_CANDIDATES, "Arial")
    FONT["mono"] = pick(_MONO_CANDIDATES, "Courier New")
    FONT["pixel"] = pick(_PIXEL_CANDIDATES, FONT["mono"])
    return FONT


_QSS = Template(r"""
* { outline: none; }
QWidget { color: $text; font-family: "$ui"; font-size: 13px; }
QMainWindow, QWidget#root { background: $bg; }
QLabel { background: transparent; }
QToolTip { background: $surface3; color: $text; border: 1px solid $border2; padding: 5px 9px; border-radius: 6px; }

/* ---------- structure ---------- */
QFrame#sidebar { background: $surface; border: none; border-right: 1px solid $border; }
QFrame#panel { background: $surface; border: none; border-left: 1px solid $border; }
QFrame#panel[dragging="true"] { border-left: 2px solid $accent; background: $drop_bg; }
QFrame#drawer { background: $surface; border: 1px solid $border; border-radius: 18px; }
QFrame#divider { background: $border; border: none; max-height: 1px; min-height: 1px; }
QFrame#pill { background: $surface; border: 1px solid $border; border-radius: 22px; }
QFrame#infobar { background: transparent; border: none; }

QFrame#card { background: $surface2; border: 1px solid $border; border-radius: 18px; }
QFrame#card[hoverable="true"]:hover { border: 1px solid $border2; background: $card_hover; }
QFrame#card[selected="true"] { border: 2px solid $accent; }
QFrame#inset { background: $board; border: 1px solid $border; border-radius: 14px; }
QFrame#canvasCard { background: $surface2; border: 1px solid $border; border-radius: 28px; }

QLabel#wordmark { color: $accent_text; }
QLabel#pageTitle { font-size: 22px; font-weight: 600; }
QLabel#cardTitle { font-size: 15px; font-weight: 600; color: $text; }
QLabel#panelTitle { font-size: 15px; font-weight: 600; }
QLabel#h2 { font-size: 20px; font-weight: 600; }
QLabel#muted { color: $muted; }
QLabel#faint { color: $faint; font-size: 12px; }
QLabel#emptyTitle { font-size: 16px; }
QLabel#metaKey { color: $faint; font-size: 12px; }
QLabel#metaVal { color: $text; font-size: 13px; }
QFrame#betaBanner { background: $surface2; border: 1px solid $border; border-left: 3px solid $accent; border-radius: 12px; }
QLabel#betaTag { background: $accent; color: $accent_ink; border-radius: 8px; padding: 2px 9px; font-size: 11px; font-weight: 700; }
QLabel#betaText { color: $muted; font-size: 12px; }
QLabel#statusTag { background: $surface3; border-radius: 9px; padding: 2px 9px; color: $muted; font-size: 11px; }
QLabel#statusTag[recognized="true"] { background: $accent; color: $accent_ink; font-weight: 600; }
QLabel#chip { background: $surface3; border-radius: 9px; padding: 3px 10px; color: $muted; font-size: 12px; }

/* ---------- buttons ---------- */
QPushButton { background: $surface2; border: 1px solid $border; border-radius: 10px; padding: 8px 16px; color: $text; font-weight: 500; }
QPushButton:hover { background: $surface3; border: 1px solid $border2; }
QPushButton:pressed { background: $pressed; }
QPushButton:disabled { color: $faint; background: $surface; border: 1px solid $border; }
QPushButton:checked { background: $surface3; border: 1px solid $accent; }
QPushButton[variant="primary"] { background: $accent; color: $accent_ink; border: 1px solid $accent; font-weight: 600; }
QPushButton[variant="primary"]:hover { background: $accent_hover; border: 1px solid $accent_hover; }
QPushButton[variant="primary"]:disabled { background: $accent_dis_bg; color: $accent_dis_fg; border: 1px solid $accent_dis_bg; }
QPushButton[variant="primary"]:checked { background: $accent; border: 1px solid $accent; }
QPushButton[variant="danger"] { color: $danger; }
QPushButton[variant="danger"]:hover { background: $danger_bg; border: 1px solid $danger; }
QPushButton[variant="ghost"] { background: transparent; border: 1px solid transparent; padding: 6px 10px; }
QPushButton[variant="ghost"]:hover { background: $surface3; }
QPushButton[variant="ghost"]:checked { background: $surface3; border: 1px solid transparent; }
QPushButton[variant="seg"] { background: transparent; border: none; border-radius: 8px; padding: 6px 14px; color: $muted; }
QPushButton[variant="seg"]:hover { color: $text; background: transparent; border: none; }
QPushButton[variant="seg"]:checked { background: $surface3; color: $text; border: none; }
QFrame#palette { background: $surface; border: 1px solid $border; border-radius: 14px; }
QWidget#paletteInner { background: transparent; }
QPushButton[variant="palette"] { text-align: left; background: transparent; border: 1px solid transparent; border-radius: 8px; padding: 5px 8px; color: $text; }
QPushButton[variant="palette"]:hover { background: $surface3; }
QPushButton[variant="palette"]:checked { background: $surface3; border: 1px solid $accent; }
QPushButton[variant="tool"] { background: transparent; border: 1px solid transparent; border-radius: 12px; padding: 0px; }
QPushButton[variant="tool"]:hover { background: $surface3; border: 1px solid transparent; }
QPushButton[variant="tool"]:checked { background: $accent; border: 1px solid $accent; }
QPushButton[variant="tool"]:disabled { background: transparent; border: 1px solid transparent; }
QPushButton[variant="round"] { background: transparent; border: 1px solid transparent; border-radius: 18px; padding: 0px; }
QPushButton[variant="round"]:hover { background: $surface3; }
QPushButton[variant="round"]:checked { background: $surface3; border: 1px solid $accent; }

/* ---------- inputs ---------- */
QLineEdit { background: $surface2; border: 1px solid $border; border-radius: 22px; padding: 10px 16px; selection-background-color: $accent; selection-color: $accent_ink; }
QLineEdit:focus { border: 1px solid $accent; }
QDoubleSpinBox { background: $surface2; border: 1px solid $border; border-radius: 9px; padding: 5px 8px; min-width: 78px; }
QDoubleSpinBox:focus { border: 1px solid $accent; }
QDoubleSpinBox:disabled { color: $faint; }
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button { width: 0px; border: none; }
QComboBox { background: $surface2; border: 1px solid $border; border-radius: 9px; padding: 6px 10px; }
QComboBox:hover { border: 1px solid $border2; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView { background: $surface2; border: 1px solid $border2; selection-background-color: $surface3; selection-color: $text; padding: 4px; outline: none; }

QPlainTextEdit { background: $inset; border: 1px solid $border; border-radius: 12px; padding: 10px; font-family: "$mono"; font-size: 12px; color: $code_fg; selection-background-color: $accent; selection-color: $accent_ink; }

QProgressBar { background: $surface3; border: none; border-radius: 3px; max-height: 6px; min-height: 6px; }
QProgressBar::chunk { background: $accent; border-radius: 3px; }

/* ---------- menus & dialogs ---------- */
QMenu { background: $surface2; border: 1px solid $border2; border-radius: 12px; padding: 6px; }
QMenu::item { padding: 8px 22px 8px 14px; border-radius: 8px; min-width: 96px; }
QMenu::item:selected { background: $surface3; color: $text; }
QMenu::separator { height: 1px; background: $border; margin: 5px 8px; }
QMessageBox, QDialog { background: $surface; }
QMessageBox QLabel { color: $text; }

/* ---------- scrolling ---------- */
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: $border2; border-radius: 4px; min-height: 28px; }
QScrollBar::handle:vertical:hover { background: $faint; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: $border2; border-radius: 4px; min-width: 28px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }

/* ---------- toast ---------- */
QFrame#toast { background: $surface3; border: 1px solid $border2; border-radius: 12px; }
QFrame#toast[kind="success"] { border: 1px solid $success; }
QFrame#toast[kind="error"] { border: 1px solid $danger; }
""")


def stylesheet():
    return _QSS.substitute(**P, **FONT)
