from .elements import ELEMENTS


def recognized():
    return [(e.key, e.label, e.pen) for e in ELEMENTS if e.detected]


def is_recognized(key):
    return any(k == key for k, _l, _d in recognized())


def names():
    return [label for _k, label, _d in recognized()]
