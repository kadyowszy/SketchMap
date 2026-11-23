# Recognition-accuracy benchmark (SRS 5.1.3)

```
python benchmark/generate_sketches.py        # (re)create the 24 synthetic sketches + annotations
python benchmark/score.py --report benchmark/results.md
```

**Rule (from the SRS):** a ground-truth element is correct if the system output has an element of the same type (and subtype)
within +/-1 grid cell. Accuracy = correct / total, averaged over all sketches. Target >= 85 %.

## Adding your real hand-drawn sketches (recommended before the defense)

1. Photograph/scan a sketch (black pen, white A4) and save it in `benchmark/sketches/` as `real_01.jpg`.
2. Write `benchmark/sketches/real_01.json` **by hand, from the paper, not from SketchMap's output**:

```json
{
  "name": "real_01", "image": "real_01.jpg", "cell_mm": 8.0, "grid": [28, 20],
  "elements": [
    {"type": "boundary", "points": [[0, 0], [27, 0]]},
    {"type": "wall", "points": [[10, 0], [10, 12]]},
    {"type": "symbol", "subtype": "arrow_start", "points": [[3, 3]]},
    {"type": "interactable", "subtype": "door", "points": [[20, 8]]}
  ]
}
```

Coordinates are grid cells counted from the top-left corner of the drawn boundary (cell 0,0), the same as the exported JSON.
Use `symbol`/`arrow_start` for the star, `interactable`/`door` for the square, `symbol`/`enemy_spawn` for the triangle and
`interactable`/`breakable_prop` for each cell along a jagged line. Walls and boundaries are 2-point lines.

3. Re-run `score.py`. Real sketches are scored exactly like the synthetic ones. Missed elements are listed per sketch so you can see what to improve.
