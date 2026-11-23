"""Beta-build notice: one source of truth for what SketchMap recognizes from a photo.

The list is derived from `Element.detected` in elements.py, so the in-app wording can never drift
from what the recognizer actually does. Nothing here changes recognition.
"""
from .elements import ELEMENTS
from .version import RELEASE_STAGE, VERSION_LABEL

# How each recognized symbol looks on paper, in plain words (shown next to its name).
DRAWN_AS = {
    "boundary": "one closed rectangle around the whole map",
    "wall": "thick straight strokes",
    "arrow_start": "an arrow",
    "enemy_spawn": "a hollow triangle",
    "door": "a hollow box in a wall gap",
}

EDITOR_ONLY = "Editor only"
FROM_PHOTO = "Recognized from photo"


def recognized():
    """[(key, label, drawn_as)] for every element the recognizer currently detects."""
    return [(e.key, e.label, DRAWN_AS.get(e.key, "")) for e in ELEMENTS if e.detected]


def is_recognized(key):
    return any(k == key for k, _l, _d in recognized())


def names():
    return [label for _k, label, _d in recognized()]


def _join(items):
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def title():
    return f"{RELEASE_STAGE} build"


def banner_text():
    """One-line notice for banners (plain text)."""
    return (f"Photo recognition currently covers {len(names())} symbols: {_join(names())}. "
            "Every other element can still be placed by hand in the Edit page.")


def detail_lines():
    """Bulleted detail, e.g. 'Player start (an arrow)'."""
    return [f"{label} ({how})" if how else label for _k, label, how in recognized()]


def about_html():
    items = "".join(f"<li>{x}</li>" for x in detail_lines())
    return (f"<b>{title()}</b><br>This is an early release. From a photo, SketchMap currently recognizes only:"
            f"<ul>{items}</ul>"
            "Recognition of the other symbols is not included yet. You can still place them yourself with the "
            "palette in the Edit page, and they export normally.")


def plain_text():
    bullets = "\n".join(f"  - {x}" for x in detail_lines())
    return (f"SketchMap {VERSION_LABEL}: photo recognition is limited in this beta. Currently recognized:\n{bullets}\n"
            "Other symbols are not recognized yet (place them in the Edit page).")


def status_for(key):
    return FROM_PHOTO if is_recognized(key) else EDITOR_ONLY


def status_detail(key):
    if is_recognized(key):
        return "Detected automatically when you import a photo."
    return (f"Not recognized from photos in this {RELEASE_STAGE.lower()} build yet. "
            "Place it by hand with the palette in the Edit page.")
