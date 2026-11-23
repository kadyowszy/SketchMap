import math

from PyQt6.QtCore import Qt, QByteArray
from PyQt6.QtGui import QPixmap, QPainter, QIcon

try:
    from PyQt6.QtSvg import QSvgRenderer
except Exception:
    QSvgRenderer = None

ICONS = {
    "home": '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9v10.5A1.5 1.5 0 0 0 6.5 21H10v-6h4v6h3.5a1.5 1.5 0 0 0 1.5-1.5V9"/>',
    "library": '<circle cx="12" cy="12" r="9"/><path d="M9.4 9.3a2.7 2.7 0 1 1 3.9 2.4c-.9.5-1.3 1.1-1.3 2"/><circle cx="12" cy="17.2" r=".7" fill="currentColor"/>',
    "files": '<path d="M3 7.5A2.5 2.5 0 0 1 5.5 5H9l2 2.5h7.5A2.5 2.5 0 0 1 21 10v7.5a2.5 2.5 0 0 1-2.5 2.5h-13A2.5 2.5 0 0 1 3 17.5z"/>',
    "templates": '<rect x="3.5" y="3.5" width="17" height="17" rx="2.5"/><path d="M3.5 9.5h17M10 20.5v-11"/>',
    "menu": '<path d="M4 6h16M4 12h16M4 18h16"/>',
    "help": '<circle cx="12" cy="12" r="9"/><path d="M9.4 9.3a2.7 2.7 0 1 1 3.9 2.4c-.9.5-1.3 1.1-1.3 2"/><circle cx="12" cy="17.2" r=".7" fill="currentColor"/>',
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4.5 20.5a7.5 7.5 0 0 1 15 0"/>',
    "camera": '<path d="M4 8.5A2.5 2.5 0 0 1 6.5 6H8l1.4-2h5.2L16 6h1.5A2.5 2.5 0 0 1 20 8.5v9a2.5 2.5 0 0 1-2.5 2.5h-11A2.5 2.5 0 0 1 4 17.5z"/><circle cx="12" cy="13" r="3.6"/>',
    "paperclip": '<path d="m20.5 11.5-8.4 8.4a5 5 0 0 1-7-7l8.4-8.4a3.3 3.3 0 0 1 4.7 4.7l-8.5 8.5a1.7 1.7 0 0 1-2.4-2.4l7.8-7.8"/>',
    "import": '<path d="M12 3.5v11"/><path d="m7.5 10.5 4.5 4.5 4.5-4.5"/><path d="M4 15v3.5A2.5 2.5 0 0 0 6.5 21h11a2.5 2.5 0 0 0 2.5-2.5V15"/>',
    "open": '<path d="M15 3H9.5A2.5 2.5 0 0 0 7 5.5v10A2.5 2.5 0 0 0 9.5 18h7a2.5 2.5 0 0 0 2.5-2.5V7z"/><path d="M15 3v4h4"/><path d="M4.5 8v11A2.5 2.5 0 0 0 7 21.5h8"/>',
    "file": '<path d="M14 3H7.5A2.5 2.5 0 0 0 5 5.5v13A2.5 2.5 0 0 0 7.5 21h9a2.5 2.5 0 0 0 2.5-2.5V8z"/><path d="M14 3v5h5"/>',
    "export": '<path d="M18.5 13.5v4a2.5 2.5 0 0 1-2.5 2.5H6.5A2.5 2.5 0 0 1 4 17.5V8a2.5 2.5 0 0 1 2.5-2.5H10.5"/><path d="M14.5 3.5h6v6"/><path d="M10.5 13.5 20.5 3.5"/>',
    "edit": '<path d="M11.5 4H6.5A2.5 2.5 0 0 0 4 6.5v11A2.5 2.5 0 0 0 6.5 20h11a2.5 2.5 0 0 0 2.5-2.5v-5"/><path d="M18.3 2.7a2 2 0 0 1 2.9 2.9L12 14.8 8 16l1.2-4z"/>',
    "back": '<path d="M19.5 12h-15"/><path d="m11 5.5-6.5 6.5 6.5 6.5"/>',
    "pan": '<path d="M12 3v18M3 12h18"/><path d="m8.5 6.5 3.5-3.5 3.5 3.5M8.5 17.5l3.5 3.5 3.5-3.5M6.5 8.5 3 12l3.5 3.5M17.5 8.5 21 12l-3.5 3.5"/>',
    "zoom_out": '<circle cx="12" cy="12" r="9"/><path d="M8 12h8"/>',
    "zoom_in": '<circle cx="12" cy="12" r="9"/><path d="M8 12h8M12 8v8"/>',
    "undo": '<path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11"/>',
    "redo": '<path d="m15 14 5-5-5-5"/><path d="M20 9H9.5a5.5 5.5 0 0 0 0 11H13"/>',
    "search": '<circle cx="11" cy="11" r="6.5"/><path d="m20 20-4-4"/>',
    "star": '<path d="m12 3.2 2.7 5.5 6 .9-4.4 4.2 1 6-5.3-2.8-5.4 2.8 1-6L3.3 9.6l6-.9z"/>',
    "star_fill": '<path fill="currentColor" d="m12 3.2 2.7 5.5 6 .9-4.4 4.2 1 6-5.3-2.8-5.4 2.8 1-6L3.3 9.6l6-.9z"/>',
    "kebab": '<circle cx="12" cy="5.5" r="1.5" fill="currentColor"/><circle cx="12" cy="12" r="1.5" fill="currentColor"/><circle cx="12" cy="18.5" r="1.5" fill="currentColor"/>',
    "trash": '<path d="M4 7h16"/><path d="M10 11v6M14 11v6"/><path d="M6 7l.9 11.5A2 2 0 0 0 8.9 20.4h6.2a2 2 0 0 0 2-1.9L18 7"/><path d="M9 7V4.5h6V7"/>',
    "close": '<path d="M6 6l12 12M18 6 6 18"/>',
    "chart": '<path d="M4 4v16h16"/><path d="m8 15 3.2-4.2 3 3 4.8-6.3"/>',
    "layers": '<path d="m12 3.5 9 5-9 5-9-5z"/><path d="m3 13 9 5 9-5"/>',
    "check": '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
    "folder_open": '<path d="M3 8V6.5A2.5 2.5 0 0 1 5.5 4H9l2 2.5h7a2.5 2.5 0 0 1 2.5 2.5V10"/><path d="M3.2 19.5h14.6a2 2 0 0 0 1.9-1.4l1.6-6.3a1.5 1.5 0 0 0-1.4-1.8H7.3a2 2 0 0 0-1.9 1.4z"/>',
    "image": '<rect x="3.5" y="4.5" width="17" height="15" rx="2.5"/><circle cx="9" cy="10" r="1.7"/><path d="m4 18 5-5 3.5 3.5 3-3 4.5 4.5"/>',
    "t_wall": '<rect x="3" y="9" width="18" height="6" rx="1.4"/>',
    "t_breakable": '<path d="M2.5 12 5.5 8l3 8 3-8 3 8 3-8 3 4"/>',
    "t_erase": '<path d="m7 21-4.3-4.3a2.4 2.4 0 0 1 0-3.4l9.6-9.6a2.4 2.4 0 0 1 3.4 0l5.6 5.6a2.4 2.4 0 0 1 0 3.4L13 21"/><path d="M22 21H7"/><path d="m5 11 8 8"/>',
    "t_toggle": '<path d="M4 8h14l-3-3"/><path d="M20 16H6l3 3"/>',
    "t_spawn": '<path d="m12 3.2 2.7 5.5 6 .9-4.4 4.2 1 6-5.3-2.8-5.4 2.8 1-6L3.3 9.6l6-.9z"/>',
    "t_interact": '<rect x="4" y="4" width="16" height="16" rx="3.5"/><rect x="9" y="9" width="6" height="6" rx="1.2" fill="currentColor"/>',
    "t_raised": '<path d="M12 4.5 21 19.5H3z"/>',
}


def _wrap(body, color, stroke, vb=24):
    body = body.replace("currentColor", color)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {vb} {vb}" fill="none" stroke="{color}" '
            f'stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">{body}</svg>')


def _render(svg, size, dpr):
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.fill(Qt.GlobalColor.transparent)
    if QSvgRenderer is not None:
        r = QSvgRenderer(QByteArray(svg.encode("utf-8")))
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r.render(p)
        p.end()
    pm.setDevicePixelRatio(dpr)
    return pm


_CACHE = {}


def pixmap(name, size=20, color="#ECEDF0", stroke=1.8, dpr=2.0):
    key = (name, size, color, stroke, dpr)
    if key not in _CACHE:
        _CACHE[key] = _render(_wrap(ICONS[name], color, stroke), size, dpr)
    return _CACHE[key]


def icon(name, size=20, color="#ECEDF0", stroke=1.8):
    return QIcon(pixmap(name, size, color, stroke))


def _star_points(cx=32, cy=33, r=24, inner=0.42):
    pts = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * inner
        pts.append(f"{cx + rr * math.cos(a):.1f},{cy + rr * math.sin(a):.1f}")
    return " ".join(pts)


_SW = ' stroke-width="3.5"'
GLYPHS = {
    "boundary": '<rect x="9" y="11" width="46" height="42" rx="4" stroke-width="5"/>',
    "wall": '<path d="M7 32H57" stroke-width="4.5"/>',
    "grass": f'<path d="M12 20 22 44 32 28 42 44 52 20"{_SW}/>',
    "water": f'<path d="M8 26q6-8 12 0t12 0t12 0t12 0M8 42q6-8 12 0t12 0t12 0t12 0"{_SW}/>',
    "lava": f'<path d="M12 48V20l14 16h12l14-16v28z"{_SW}/>',
    "ice": f'<path d="M22 48 34 16M36 48 48 16"{_SW}/>',
    "mud": f'<path d="M14 22H50M14 32H50M14 42H50"{_SW}/>',
    "conveyor": f'<path d="M14 18 28 32 14 46M34 18 48 32 34 46"{_SW}/>',
    "arrow_start": f'<path d="M10 32H52M40 20 52 32 40 44"{_SW}/>',
    "goal_exit": f'<circle cx="32" cy="32" r="22"{_SW}/><circle cx="32" cy="32" r="10"{_SW}/>',
    "enemy_spawn": f'<path d="M32 12 54 50H10z"{_SW}/>',
    "checkpoint": f'<path d="M18 10V54M18 12 48 21 18 30"{_SW}/>',
    "patrol_waypoint": f'<path d="M32 14V50M14 32H50"{_SW}/>',
    "door": f'<rect x="18" y="14" width="28" height="36" rx="2"{_SW}/>',
    "locked_door": f'<rect x="14" y="14" width="36" height="36" rx="2"{_SW}/><path d="M28 14V50M36 14V50"{_SW}/>',
    "key": f'<circle cx="21" cy="32" r="10"{_SW}/><path d="M31 32H55M47 32V41M54 32V39"{_SW}/>',
    "chest": f'<rect x="10" y="16" width="44" height="32" rx="2"{_SW}/><path d="M10 32H54"{_SW}/>',
    "collectible": f'<circle cx="32" cy="32" r="19"{_SW}/>',
    "push_block": f'<rect x="14" y="14" width="36" height="36" rx="2"{_SW}/><path d="M14 14 50 50M50 14 14 50"{_SW}/>',
    "breakable_prop": f'<rect x="14" y="14" width="36" height="36" rx="2"{_SW}/><path d="M14 50 50 14"{_SW}/>',
    "pressure_plate": f'<rect x="10" y="10" width="44" height="44" rx="2"{_SW}/><circle cx="32" cy="32" r="11"{_SW}/>',
    "gate": f'<rect x="12" y="12" width="40" height="40" rx="2"{_SW}/><path d="M22 12V52M32 12V52M42 12V52"{_SW}/>',
    "spike_trap": f'<path d="M32 10V54M13 21 51 43M13 43 51 21"{_SW}/>',
    "torch": f'<polygon points="{_star_points()}"{_SW}/>',
    "teleporter": f'<rect x="10" y="10" width="44" height="44" rx="2"{_SW}/><rect x="22" y="22" width="20" height="20" rx="1"{_SW}/>',
}


def glyph_pixmap(key, size=64, color="#ECEDF0", dpr=2.0):
    ck = ("glyph", key, size, color, dpr)
    if ck not in _CACHE:
        body = GLYPHS.get(key, GLYPHS["wall"]).replace("currentColor", color)
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" fill="none" stroke="{color}" '
               f'stroke-linecap="round" stroke-linejoin="round">{body}</svg>')
        _CACHE[ck] = _render(svg, size, dpr)
    return _CACHE[ck]


LOGO_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">'
    '<rect width="512" height="512" rx="108" fill="#F5C84B"/>'
    '<g stroke="#1A1403" stroke-opacity="0.12" stroke-width="5" fill="none">'
    '<path d="M136 0V512M256 0V512M376 0V512M0 136H512M0 256H512M0 376H512"/></g>'
    '<g transform="translate(-17 -3)">'
    '<path d="M376 136H166Q136 136 136 166V226Q136 256 166 256H346Q376 256 376 286V346Q376 376 346 376H216" '
    'fill="none" stroke="#1A1403" stroke-width="60"/>'
    '<polygon points="216,326 216,426 124,376" fill="#1A1403"/>'
    '<circle cx="376" cy="136" r="46" fill="#1A1403"/><circle cx="376" cy="136" r="16" fill="#F5C84B"/></g></svg>'
)


def logo_pixmap(size=44, dpr=2.0):
    ck = ("logo", size, dpr)
    if ck not in _CACHE:
        _CACHE[ck] = _render(LOGO_SVG, size, dpr)
    return _CACHE[ck]
