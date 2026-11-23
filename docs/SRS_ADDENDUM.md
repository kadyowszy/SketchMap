# SRS 1.0 -> 1.1: changes to record before the final defense

The program now does more than SRS 1.0 describes, and a few details differ. Add these to the SRS (or hand this page in as an addendum) so the document matches the product.

## Decisions that follow the SRS
| Topic | SRS | Product |
|---|---|---|
| Accounts | 2.1: no user authentication | The old "Account" button is now a **Menu** (hamburger) button: manual, legend, shortcuts, settings, About |
| Offline | 4.4, 5.3.2 | No network modules in the code (checked by an automated test) |
| Overwrite | 5.2.2 | A confirmation lists every file that would be replaced (level file and `master_tileset.tres`) |
| Errors | 5.2.1, 5.4.4.1 | Empty, huge, corrupted, blank and low-contrast images give a message; stray strokes are listed and pinned on the preview |

## Extensions beyond SRS 1.0 (add as new features / requirements)
1. **Prepare & Straighten dialog** (perspective corners, rotation, shadow removal, tone, threshold method, gap closing) before processing.
2. **Manual editing** of walls and elements, undo/redo, only perpendicular (axis-aligned) lines.
3. **Map scale and size class** (cell size in mm, Auto estimate, small / medium / large).
4. **Stats for nerds** panel: formulas, worked numbers and per-stage timings for every algorithm.
5. **Extended Symbol Legend** (25 elements, `sketchmap/elements.py`): star = player start, square = door, triangle = enemy spawn, jagged line = breakable props; the remaining elements are placed from the palette.
6. **Tileset customization** (session-level) exported with the level.
7. **Home / Library / Files / Templates** pages, recent files, favourites.
8. **Settings**, in-app **user manual** (F1), unsaved-edit protection.

## Differences from the SRS data format (3.3.4)
- `schema_version` is `"1.2"` (SRS example: `"1.0"`). All SRS fields are present; added: `scale`, `size_class`, `tileset`, `tile_matrix`, `direction` / `facing`.
- Walls and boundaries are exported as **2-point line segments** (`[[x1,y1],[x2,y2]]`). The SRS example shows the boundary as one 4-point polygon.
- Terrain / symbol / interactable subtypes follow the extended legend (e.g. `arrow_start`, `door`, `enemy_spawn`, `breakable_prop`).
- Validated by `python -m sketchmap.schema`.

## Scope changes
- **Elevation / raised terrain** is out of scope (SRS 2.4.4: flat top-down maps). Older files containing `raised` are converted and the elevation is dropped.
- **Godot version:** the SRS names Godot 4.7. The exporter writes Godot 4.x scene format 3 (`TileMapLayer`, requires 4.3+). Confirm by opening an export in your Godot version.
- **Recognised from a photo today:** boundary, walls, star, square, triangle, jagged line. Other elements are placed in the editor (the Library page marks which).

## Measurement method (5.1.3)
Implemented exactly as written: a ground-truth element is correct if an element of the same type exists within +/-1 cell; accuracy = correct / total averaged over sketches. Line elements count as correct when >= 90 % of their cells are covered. See `benchmark/README.md`.
