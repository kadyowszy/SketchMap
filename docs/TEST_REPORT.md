# SketchMap test report

Generated 2026-11-22 by `tools/make_test_report.py`. Result: **19 passed in 9.73s**.

## Requirement coverage

| SRS | Requirement | Evidence (test) | Result |
|---|---|---|---|
| 3.1.2.1, 5.2.1, 5.4.3.1 | Unsupported / corrupted / empty / missing image shows a message | `test_bad_input_gives_message_not_crash` | PASS |
| 5.4.4.1 | Blank and low-contrast sketches are refused gracefully (no crash) | `test_bad_input_gives_message_not_crash` | PASS |
| 5.4.3.1 | Oversized images are refused | `test_oversized_image_refused` | PASS |
| 3.1.3.4-3.1.3.7 | Walls, boundaries, symbols and interactables are classified on the shipped sample | `test_symbol_demo_is_recognised` | PASS |
| 3.1.2.4 | A shape matching no legend entry is marked unclassified | `test_unclassified_shape_is_flagged` | PASS |
| 3.2.2.2 | Fragmented strokes are excluded with a located warning | `test_fragmented_stroke_warns_and_is_pinned` | PASS |
| 5.4.3.2 | The same sketch gives byte-identical JSON and .tscn every time | `test_same_sketch_same_export` | PASS |
| 3.3.2.2, 3.3.3.2, 3.3.4 | Exported JSON conforms to the data-format specification | `test_json_conforms_to_srs_schema` | PASS |
| 3.3.4 | The schema validator rejects malformed files | `test_validator_catches_a_broken_file` | PASS |
| 3.3.2.3, 3.3.3.3, 3.3.3.4 | Godot scene has a tile map, colliders, and every file it references | `test_tscn_has_tilemap_colliders` | PASS |
| 5.2.2 | Existing export files are detected so the user is asked first | `test_existing_outputs_are_reported` | PASS |
| 5.1.1 | Full pipeline finishes in under 10 s | `test_pipeline_under_ten_seconds` | PASS |
| 5.1.3 | Recognition accuracy >= 85% on 20-30 annotated sketches | `test_recognition_accuracy_meets_target` | PASS |
| 5.3.1, 5.3.2, 4.4.1 | No network code anywhere in the application | `test_no_network_code_in_the_application` | PASS |
| 2.1, 4.1 | GUI starts, menu is a hamburger menu (no accounts), manual and settings open | `test_gui_menu_icon_and_dialogs` | PASS |

## Accuracy and speed benchmark (SRS 5.1.1, 5.1.3)

```
sketch_23: 11/11 = 100.0%  (0.26s)  missed: -
sketch_24: 11/11 = 100.0%  (0.30s)  missed: -
AVERAGE RECOGNITION ACCURACY over 24 sketches: 100.0%  (target >= 85%)
Slowest sketch: 0.43s  (SRS 5.1.1 budget 10 s)
  boundary      96/96 = 100.0%
  interactable  43/43 = 100.0%
  symbol        41/41 = 100.0%
  wall          72/72 = 100.0%
```

Per-sketch results are in `benchmark/results.md`. The 24 sketches are generated with independent ground truth by `benchmark/generate_sketches.py` (varying pen thickness, hand wobble, lighting gradient, noise and tilt).

**Important:** these are synthetic sketches. For the final defense, add the team's real hand-drawn photos with their own annotations (see `benchmark/README.md`) and re-run; the scorer treats both the same way.

## Not covered by automated tests (do by hand before release)

- Open a freshly exported `.tscn` in Godot 4.x (the SRS names 4.7) and confirm there are no warnings.
- Run on the minimum hardware (dual-core 2 GHz, 4 GB RAM) and time a typical photo.
- Try 5-10 real phone photos: shadows, pencil, curved page, page on a table.
- Install and start the packaged app on a clean machine without Python.
