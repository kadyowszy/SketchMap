import datetime
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

MAP = [
    ("3.1.2.1, 5.2.1, 5.4.3.1", "Unsupported / corrupted / empty / missing image shows a message", "test_bad_input_gives_message_not_crash"),
    ("5.4.4.1", "Blank and low-contrast sketches are refused gracefully (no crash)", "test_bad_input_gives_message_not_crash"),
    ("5.4.3.1", "Oversized images are refused", "test_oversized_image_refused"),
    ("3.1.3.4-3.1.3.7", "Walls, boundaries, symbols and interactables are classified on the shipped sample", "test_symbol_demo_is_recognised"),
    ("3.1.2.4", "A shape matching no legend entry is marked unclassified", "test_unclassified_shape_is_flagged"),
    ("3.2.2.2", "Fragmented strokes are excluded with a located warning", "test_fragmented_stroke_warns_and_is_pinned"),
    ("5.4.3.2", "The same sketch gives byte-identical JSON and .tscn every time", "test_same_sketch_same_export"),
    ("3.3.2.2, 3.3.3.2, 3.3.4", "Exported JSON conforms to the data-format specification", "test_json_conforms_to_srs_schema"),
    ("3.3.4", "The schema validator rejects malformed files", "test_validator_catches_a_broken_file"),
    ("3.3.2.3, 3.3.3.3, 3.3.3.4", "Godot scene has a tile map, colliders, and every file it references", "test_tscn_has_tilemap_colliders"),
    ("5.2.2", "Existing export files are detected so the user is asked first", "test_existing_outputs_are_reported"),
    ("5.1.1", "Full pipeline finishes in under 10 s", "test_pipeline_under_ten_seconds"),
    ("5.1.3", "Recognition accuracy >= 85% on 20-30 annotated sketches", "test_recognition_accuracy_meets_target"),
    ("5.3.1, 5.3.2, 4.4.1", "No network code anywhere in the application", "test_no_network_code_in_the_application"),
    ("2.1, 4.1", "GUI starts, menu is a hamburger menu (no accounts), manual and settings open", "test_gui_menu_icon_and_dialogs"),
]


def run(cmd):
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)


def main():
    t = run([sys.executable, "-m", "pytest", "-v", "-p", "no:cacheprovider"])
    status = {}
    for line in t.stdout.splitlines():
        m = re.match(r"tests/test_srs.py::(\S+)\s+(PASSED|FAILED|ERROR)", line)
        if m:
            name = re.sub(r"\[.*\]$", "", m.group(1))
            status[name] = "FAIL" if (m.group(2) != "PASSED" or status.get(name) == "FAIL") else "PASS"
    b = run([sys.executable, os.path.join("benchmark", "score.py"), "--report", os.path.join("benchmark", "results.md")])
    tail = [l for l in b.stdout.splitlines() if l.strip()][-8:]
    summary = [l for l in t.stdout.splitlines() if re.search(r"\d+ (passed|failed)", l)]
    out = ["# SketchMap test report", "",
           f"Generated {datetime.date.today().isoformat()} by `tools/make_test_report.py`. Result: **{summary[-1].strip('= ') if summary else 'unknown'}**.", "",
           "## Requirement coverage", "", "| SRS | Requirement | Evidence (test) | Result |", "|---|---|---|---|"]
    for sec, req, frag in MAP:
        name = next((n for n in status if frag in n), None)
        out.append(f"| {sec} | {req} | `{frag}` | {status.get(name, 'not run')} |")
    out += ["", "## Accuracy and speed benchmark (SRS 5.1.1, 5.1.3)", "", "```", *tail, "```", "",
            "Per-sketch results are in `benchmark/results.md`. The 24 sketches are generated with independent ground truth by "
            "`benchmark/generate_sketches.py` (varying pen thickness, hand wobble, lighting gradient, noise and tilt).",
            "", "**Important:** these are synthetic sketches. For the final defense, add the team's real hand-drawn photos with their own "
            "annotations (see `benchmark/README.md`) and re-run; the scorer treats both the same way.", "",
            "## Not covered by automated tests (do by hand before release)", "",
            "- Open a freshly exported `.tscn` in Godot 4.x (the SRS names 4.7) and confirm there are no warnings.",
            "- Run on the minimum hardware (dual-core 2 GHz, 4 GB RAM) and time a typical photo.",
            "- Try 5-10 real phone photos: shadows, pencil, curved page, page on a table.",
            "- Install and start the packaged app on a clean machine without Python.", ""]
    path = os.path.join(ROOT, "docs", "TEST_REPORT.md")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w", encoding="utf-8").write("\n".join(out))
    print("wrote", path)
    print("\n".join(out[:24]))
    return 0 if all(v == "PASS" for v in status.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
