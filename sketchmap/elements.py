from dataclasses import dataclass

DIRS = ("right", "down", "left", "up")
DIR_VEC = {"right": (1, 0), "down": (0, 1), "left": (-1, 0), "up": (0, -1)}


@dataclass(frozen=True)
class Element:
    key: str
    category: str
    label: str
    code: str
    color: str
    pen: str
    look: str
    directional: bool = False
    detected: bool = False


ELEMENTS = [
    Element("boundary", "structural", "Boundary", "BD", "#F1F2F6",
            "One closed rectangle or polygon around the whole playable area.",
            "Walls_Boundary layer: solid collider on Physics Layer 0 so nothing can leave the level.", detected=True),
    Element("wall", "structural", "Wall", "WL", "#C9CCD6",
            "Thick strokes, or a filled 1-cell block. Leave a small pen gap on both sides of every doorway.",
            "Walls_Boundary layer: solid collider on Physics Layer 0, blocks light (occluder).", detected=True),
    Element("grass", "terrain", "Grass", "GR", "#6FCF6F",
            "A small W-shaped tuft (zig-zag of four strokes) on one cell.",
            "Ground_Terrain: walkable, navigable, slightly slower (speed_multiplier custom data)."),
    Element("water", "terrain", "Water", "WA", "#3B8EEA",
            "Stacked wavy lines on one cell.",
            "Ground_Terrain: no navigation polygon (enemies route around it); blocks walking on Physics Layer 1."),
    Element("lava", "terrain", "Lava", "LA", "#F2593B",
            "A closed flat-bottomed M (twin-peak crown).",
            "Ground_Terrain: no navigation; damage_per_sec custom data."),
    Element("ice", "terrain", "Ice", "IC", "#8FE3F5",
            "Two parallel slashes //.",
            "Ground_Terrain: is_slippery custom data, so pushed blocks and players glide."),
    Element("mud", "terrain", "Mud", "MU", "#8B6A4A",
            "Three short parallel horizontal bars.",
            "Ground_Terrain: speed_multiplier below 1 slows movement."),
    Element("conveyor", "terrain", "Conveyor", "CV", "#9F7AEA",
            "A double chevron >> pointing the way it pushes.",
            "Ground_Terrain: push_direction custom data; the tile art is flipped / transposed to face the right way.",
            directional=True),
    Element("arrow_start", "symbol", "Player start", "PS", "#F5C84B",
            "An arrow; the tail-to-head direction is the way the player faces.",
            "Markers: Marker2D in group player_start, rotated to the arrow's facing.", directional=True, detected=True),
    Element("goal_exit", "symbol", "Level exit", "EX", "#FF8AD8",
            "A bullseye (two nested circles) in the final chamber.",
            "Markers: Area2D in group goal_exit; touching it wins the level."),
    Element("enemy_spawn", "symbol", "Enemy spawn", "ES", "#E5484D",
            "A hollow triangle.",
            "Markers: Marker2D in group enemy_spawn; an enemy prefab with NavigationAgent2D goes here.", detected=True),
    Element("checkpoint", "symbol", "Checkpoint", "CP", "#2DD4BF",
            "A flag: vertical stem with a closed loop.",
            "Markers: Area2D in group checkpoint; saves the respawn position when touched."),
    Element("patrol_waypoint", "symbol", "Patrol waypoint", "PW", "#A3A8B8",
            "A cross + or x.",
            "Markers: Marker2D in group patrol_points; the nearest enemy claims it."),
    Element("door", "interactable", "Door", "DR", "#C98A4B",
            "A hollow box drawn in a wall gap.",
            "Interactables: Door.tscn; blocks until touched, then opens.", detected=True),
    Element("locked_door", "interactable", "Locked door", "LD", "#A0522D",
            "A box with a double bar [|].",
            "Interactables: LockedDoor.tscn; opens only if the keys counter is above 0 and uses one."),
    Element("key", "interactable", "Key", "KY", "#F6D55C",
            "A ring with a notched shaft.",
            "Interactables: Key.tscn; pickup that adds 1 to the keys counter."),
    Element("chest", "interactable", "Chest", "CH", "#D69E2E",
            "A box divided in two (a box with a middle line).",
            "Interactables: Chest.tscn; opens once and awards score and a key."),
    Element("collectible", "interactable", "Collectible", "CO", "#34D399",
            "A hollow circle.",
            "Interactables: Collectible.tscn; walk-over pickup that adds score."),
    Element("push_block", "interactable", "Push block", "PB", "#94A3B8",
            "A box with an X.",
            "Interactables: PushBlock.tscn; slides one tile when pushed and can rest on pressure plates."),
    Element("breakable_prop", "interactable", "Breakable prop", "BP", "#F2994A",
            "A box with a single slash.",
            "Interactables: BreakableProp.tscn; takes hits and breaks (replaces breakable walls)."),
    Element("pressure_plate", "interactable", "Pressure plate", "PP", "#60A5FA",
            "A circle inside a box.",
            "Interactables: PressurePlate.tscn; reports to the puzzle_plates group."),
    Element("gate", "interactable", "Gate", "GT", "#818CF8",
            "A barred portcullis: a box with vertical bars.",
            "Interactables: Gate.tscn; opens when every pressure plate in the level is pressed."),
    Element("spike_trap", "interactable", "Spike trap", "ST", "#F87171",
            "A six-ray star (asterisk).",
            "Interactables: SpikeTrap.tscn; spikes cycle between safe and harmful on a timer."),
    Element("torch", "interactable", "Torch", "TO", "#FB923C",
            "A five-point star.",
            "Interactables: Torch.tscn; flame with a PointLight2D that casts shadows against walls."),
    Element("teleporter", "interactable", "Teleporter", "TP", "#E879F9",
            "Nested squares (a box inside a box). Draw exactly two.",
            "Interactables: Teleporter.tscn; two pads pair up automatically through the teleporters group."),
]

BY_KEY = {e.key: e for e in ELEMENTS}
TERRAIN = [e.key for e in ELEMENTS if e.category == "terrain"]
SYMBOLS = [e.key for e in ELEMENTS if e.category == "symbol"]
INTERACTABLES = [e.key for e in ELEMENTS if e.category == "interactable"]
OBJECTS = SYMBOLS + INTERACTABLES
CATEGORY_TITLES = (("terrain", "Terrain"), ("symbol", "Markers"), ("interactable", "Objects"))


def is_directional(key):
    e = BY_KEY.get(key)
    return bool(e and e.directional)


def legend_entries():
    out = []
    for e in ELEMENTS:
        out.append((e.key, e.label, e.pen if e.detected else e.pen + "  (place it with the editor)"))
    return out


def check(model):
    w = []
    objs = {}
    for (xy, (k, _f)) in model.objects.items():
        objs.setdefault(k, []).append(xy)
    n = lambda k: len(objs.get(k, []))
    if n("arrow_start") == 0:
        w.append("No player start (arrow_start): the player has nowhere to spawn.")
    elif n("arrow_start") > 1:
        w.append(f"{n('arrow_start')} player starts: only the first one is used.")
    if n("goal_exit") == 0:
        w.append("No level exit (goal_exit): the level cannot be won.")
    if n("teleporter") == 1:
        w.append("Only 1 teleporter: pads need a partner (draw exactly two).")
    elif n("teleporter") > 2:
        w.append(f"{n('teleporter')} teleporters: automatic pairing only works with exactly two.")
    keys_available = n("key") + n("chest")
    if n("locked_door") > keys_available:
        w.append(f"{n('locked_door')} locked door(s) but only {keys_available} key(s)/chest(s) to open them.")
    if n("gate") and not n("pressure_plate"):
        w.append("A gate is present but there is no pressure plate to open it.")
    if n("pressure_plate") and not n("gate"):
        w.append("A pressure plate is present but there is no gate for it to open.")
    if n("patrol_waypoint") and not n("enemy_spawn"):
        w.append("Patrol waypoints are present but there is no enemy_spawn to use them.")
    return w
