import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from sketchmap.elements import ELEMENTS, CATEGORY_TITLES
from sketchmap.version import __version__

TEMPLATE = """# SketchMap {version} - User Manual

SketchMap turns a photo or scan of a hand-drawn level into an editable 2D grid map, and exports it as a **JSON** file (any engine)
or a **Godot scene (.tscn)** with a tile map and physics colliders. It runs completely **offline**: there are no accounts, no logins
and nothing is ever sent over a network.

## 1. What you need

- A Windows, macOS or Linux computer (x86/x64; 2 GHz dual-core, 4 GB RAM and 500 MB free disk is enough).
- A photo or scan of your sketch as **JPEG or PNG**.
- To use the result: Godot 4 (for `.tscn`) or any program that can read JSON.

## 2. Drawing your sketch

![How to draw](drawing_guide.png)

- Use a **black pen on white A4 paper**, in even light, and capture the **whole sheet**.
- Draw walls along the paper edges (horizontal / vertical). Slightly crooked lines are straightened automatically; diagonal lines are forced to the nearest axis.
- Leave a gap in a wall for a doorway.
- Keep symbols (star, square, triangle) **apart from walls**: anything touching a wall is read as part of the wall.
- Draw one closed rectangle around the whole map: that is the **boundary**.

## 3. Step by step

1. **Import.** Press **Import File** (Ctrl+O) or drag a picture onto the window. Only JPEG and PNG pictures are accepted. A broken, empty, blank or very low-contrast picture shows a clear message instead of a result.
2. **Prepare & Straighten.** A window shows your photo. Drag the four paper corners if the page is not flat, rotate to level the walls (**Auto**), and tune lighting and the threshold until the walls look solid black on white. Press **OK**.
3. **Wait a moment.** SketchMap removes shadows, finds walls and symbols, thins strokes to one pixel (Zhang-Suen), simplifies them (Ramer-Douglas-Peucker), snaps them to a grid and builds the map. A normal sketch takes well under a second.
4. **Check.** The Home page shows the result and the file name is shown in the window title. Open **Edit** to see the grid-mapped map and compare it with your drawing (switch **Sketch overlay** on). Press **Ctrl+I** (Stats for nerds) and choose **Pipeline stages** to see the *Original*, *Preprocessed*, *Segmented* and *Thinned* previews one below the other.
5. **Fix.** In Edit mode, draw or erase walls and place any element from the palette. **Ctrl+Z / Ctrl+Y** undo and redo. Stray strokes that were too fragmented to use are marked with an orange **!** on the segmented and thinned previews, and listed under *Warnings* in Stats for nerds.
6. **Scale.** *Scale* is the real size of one grid cell on the paper (mm). Bigger means a coarser grid. **Auto** estimates it from your symbols.
7. **Export.** Choose **JSON** or **Godot (.tscn)** and a folder. If a file with that name already exists, SketchMap asks before replacing it.

## 4. Pages

- **Home** - your current map and the Import / Open buttons. Drag and drop works anywhere in the window.
- **Library** - every element, how to draw it, and what it becomes in Godot.
- **Files** - recently opened sketches and levels (favourites, search).
- **Templates** - two sample sketches to try the program.
- **Menu (the three-line button, bottom left)** - this manual (F1), the symbol legend, keyboard shortcuts, settings and *About*.

## 5. Elements

{legend}

Elements marked *auto* are recognised from the photo. The others are placed in the Edit page with the element palette.

## 6. Stats for nerds

Press **Ctrl+I** on the Edit page. *Computations* shows how every step was calculated, with the real numbers from your sketch: lighting correction, thresholding, symbol classification, Zhang-Suen thinning, RDP simplification, grid conversion and timings against the 10-second budget.

## 7. Customising the tileset

*Customize Tileset...* on the Edit page lets you choose your own sprite sheet and decide which cell draws each tile. The choice lasts for the session and is written into `.tscn` and `.json` exports.

## 8. Exported files

**JSON** (`schema_version`, `grid_width`, `grid_height`, `cell_size_px`, `elements[]` with `id`, `type`, `subtype`, `points`, `has_collider`, plus `tile_matrix`). Walls and boundaries are 2-point lines in grid coordinates (origin top-left). Check any file with `python -m sketchmap.schema level.json`.

**Godot scene** - `level.tscn` plus `master_tileset.tres` (tiles, physics and navigation), the sprite sheet, and a `prefabs/` folder. Copy all of them into your Godot project, keeping the folder layout, then open `level.tscn`. Wall and boundary tiles carry 2D physics colliders.

## 9. Keyboard shortcuts

| Keys | Action |
|---|---|
| Ctrl+O | Import a sketch |
| Ctrl+Z / Ctrl+Y | Undo / redo |
| Ctrl+I | Stats for nerds |
| F1 | This manual |
| Mouse wheel / Space + drag / F | Zoom / pan / fit to screen |

## 10. Troubleshooting

| Message or problem | What to do |
|---|---|
| "Unsupported or corrupted image file" | The file is not a real JPEG/PNG or is damaged. Re-export or re-photograph it. |
| "The file is empty" / "too large" | Use a normal photo under 80 MB and 60 megapixels. |
| "too little contrast" | Draw with a black pen on white paper and use even light. |
| "no recognizable features" / blank sketch | Nothing dark was found. Check the page is in the picture and the pen is dark enough. |
| Orange **!** on the preview | A short stroke was too fragmented to use and was left out. Redraw it or add the wall in Edit mode. |
| Red *unclassified* box | A shape matched no symbol. Redraw it more clearly as a star, square or triangle. |
| A whole region is missing or the map is the wrong size | Open Prepare & Straighten and set the four corners on the paper. |
| "Invalid or inaccessible export path" | Choose a folder you are allowed to write to. |
| Godot cannot find tiles | Keep `level.tscn`, `master_tileset.tres`, the sprite sheet and `prefabs/` together. |
| "level is incomplete" after export | The design check found e.g. no player start or no exit. The file is still saved. |

## 11. Limits

Flat, top-down 2D maps only (no height). Hand-drawn, axis-aligned lines on A4. Classical image processing only: no artificial intelligence is used.
"""


def legend_md():
    rows = []
    for key, title in (("structural", "Structure"),) + tuple(CATEGORY_TITLES):
        rows.append(f"**{title}**\n\n| Element | How to draw it | In Godot | Detected |\n|---|---|---|---|")
        for e in ELEMENTS:
            if e.category == key:
                rows.append(f"| {e.label} | {e.pen} | {e.look} | {'auto' if e.detected else 'editor'} |")
        rows.append("")
    return "\n".join(rows)


def main():
    md = TEMPLATE.format(version=__version__, legend=legend_md())
    out = os.path.join(ROOT, "sketchmap", "docs", "USER_MANUAL.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write(md)
    print("wrote", out)
    try:
        import markdown
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("markdown/playwright not installed: skipped the PDF")
        return 0
    body = markdown.markdown(md, extensions=["tables"])
    css = ("body{font-family:Segoe UI,Helvetica,Arial,sans-serif;font-size:11pt;line-height:1.45;max-width:760px;margin:auto;color:#111}"
           "h1{border-bottom:3px solid #F5C84B;padding-bottom:6px}h2{margin-top:26px;border-bottom:1px solid #ddd}"
           "table{border-collapse:collapse;width:100%;font-size:9.5pt;margin:8px 0}th,td{border:1px solid #ccc;padding:4px 6px;vertical-align:top}"
           "th{background:#f3f3f3}img{max-width:62%;display:block;margin:10px auto;border:1px solid #ddd}code{background:#f3f3f3;padding:1px 4px}")
    docs = os.path.join(ROOT, "sketchmap", "docs")
    html = f"<html><head><meta charset='utf-8'><style>{css}</style></head><body>{body}</body></html>"
    tmp = os.path.join(docs, "_manual.html")
    open(tmp, "w", encoding="utf-8").write(html)
    pdf = os.path.join(ROOT, "docs", "USER_MANUAL.pdf")
    os.makedirs(os.path.dirname(pdf), exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        pg.goto("file://" + tmp)
        pg.pdf(path=pdf, format="A4", margin=dict(top="18mm", bottom="18mm", left="16mm", right="16mm"), print_background=True)
        b.close()
    os.remove(tmp)
    print("wrote", pdf)
    return 0


if __name__ == "__main__":
    sys.exit(main())
