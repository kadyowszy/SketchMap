import math
import os
import struct

from . import elements as el
from . import tileset

TILESET_FILE = "master_tileset.tres"
PREFAB_DIR = "prefabs"
SCENES_SOURCE_ID = 1
PUSH = {"right": (1, 0), "down": (0, 1), "left": (-1, 0), "up": (0, -1)}
CONVEYOR_ALT_FLAGS = {"right": (), "down": ("transpose",), "left": ("flip_h",), "up": ("flip_h", "transpose")}


def res_dir(spec):
    d = spec.res_dir or "res://"
    return d if d.endswith("/") else d + "/"


def _num(v):
    return f"{v:g}" if isinstance(v, float) else str(v)


def tile_variants(spec):
    cells = tileset.resolved(spec.tiles)
    used, out = {}, {}

    def alloc(key, cell):
        alt = used.get(cell, 0)
        used[cell] = alt + 1
        out[key] = (cell[0], cell[1], alt)
    for kind in tileset.KINDS:
        if kind == "conveyor":
            for d in el.DIRS:
                alloc(("conveyor", d), cells["conveyor"])
        else:
            alloc((kind, None), cells[kind])
    return out


def _poly(px):
    h = px / 2
    return ", ".join(_num(v) for v in (-h, -h, h, -h, h, h, -h, h))


def master_tileset_text(spec):
    px = spec.tile_px
    base = res_dir(spec)
    variants = tile_variants(spec)
    scene_ids = {k: i for i, k in enumerate(el.INTERACTABLES, 1)}
    ext = [f'[ext_resource type="Texture2D" path="{spec.res_path}" id="1_sheet"]']
    for k, i in scene_ids.items():
        ext.append(f'[ext_resource type="PackedScene" path="{base}{PREFAB_DIR}/{prefab_name(k)}.tscn" id="scene_{i}"]')
    subs = [
        '[sub_resource type="NavigationPolygon" id="NavigationPolygon_walk"]\n'
        f'vertices = PackedVector2Array({_poly(px)})\npolygons = [PackedInt32Array(0, 1, 2, 3)]\n'
        f'outlines = [PackedVector2Array({_poly(px)})]\n',
        '[sub_resource type="OccluderPolygon2D" id="OccluderPolygon2D_wall"]\n'
        f'polygon = PackedVector2Array({_poly(px)})\n',
    ]
    lines = []
    for (kind, d), (ax, ay, alt) in sorted(variants.items(), key=lambda kv: (kv[1][0], kv[1][1], kv[1][2])):
        pre = f"{ax}:{ay}/{alt}"
        lines.append(f"{pre} = {alt}")
        for flag in CONVEYOR_ALT_FLAGS.get(d, ()):
            lines.append(f"{pre}/{flag} = true")
        if kind in ("wall", "boundary"):
            lines.append(f"{pre}/physics_layer_0/polygon_0/points = PackedVector2Array({_poly(px)})")
            lines.append(f'{pre}/occlusion_layer_0/polygon = SubResource("OccluderPolygon2D_wall")')
            continue
        if kind == "water":
            lines.append(f"{pre}/physics_layer_1/polygon_0/points = PackedVector2Array({_poly(px)})")
        if kind != "water" and kind != "lava":
            lines.append(f'{pre}/navigation_layer_0/polygon = SubResource("NavigationPolygon_walk")')
        speed = {"mud": 0.5, "grass": 0.9}.get(kind, 1.0 if kind != "water" else 0.0)
        lines.append(f"{pre}/custom_data_0 = {speed}")
        if kind == "lava":
            lines.append(f"{pre}/custom_data_1 = 10")
        if kind == "ice":
            lines.append(f"{pre}/custom_data_2 = true")
        if kind == "conveyor":
            dx, dy = PUSH[d]
            lines.append(f"{pre}/custom_data_3 = Vector2({dx}, {dy})")
    atlas = ('[sub_resource type="TileSetAtlasSource" id="TileSetAtlasSource_1"]\n'
             'texture = ExtResource("1_sheet")\n'
             f"texture_region_size = Vector2i({px}, {px})\n" + "\n".join(lines) + "\n")
    scenes = '[sub_resource type="TileSetScenesCollectionSource" id="TileSetScenesCollectionSource_1"]\n' + \
        "".join(f'scenes/{i}/scene = ExtResource("scene_{i}")\n' for i in scene_ids.values())
    res = ("[resource]\n"
           f"tile_size = Vector2i({px}, {px})\n"
           "physics_layer_0/collision_layer = 1\n"
           "physics_layer_1/collision_layer = 2\n"
           "navigation_layer_0/layers = 1\n"
           "occlusion_layer_0/light_mask = 1\n"
           'custom_data_layer_0/name = "speed_multiplier"\ncustom_data_layer_0/type = 3\n'
           'custom_data_layer_1/name = "damage_per_sec"\ncustom_data_layer_1/type = 2\n'
           'custom_data_layer_2/name = "is_slippery"\ncustom_data_layer_2/type = 1\n'
           'custom_data_layer_3/name = "push_direction"\ncustom_data_layer_3/type = 5\n'
           f'sources/0 = SubResource("TileSetAtlasSource_1")\nsources/{SCENES_SOURCE_ID} = SubResource("TileSetScenesCollectionSource_1")\n')
    steps = len(ext) + len(subs) + 2 + 1
    return (f'[gd_resource type="TileSet" load_steps={steps} format=3]\n\n' + "\n".join(ext) + "\n\n" +
            "\n".join(subs) + "\n" + atlas + "\n" + scenes + "\n" + res)


def _tile_map_data(cells):
    out = bytearray(struct.pack("<H", 0))
    for c in cells:
        out += struct.pack("<hhHHHH", *c)
    return "PackedByteArray(" + ", ".join(str(b) for b in out) + ")"


def _layer(name, cells, scale, tileset_id="1_tileset"):
    s = f'[node name="{name}" type="TileMapLayer" parent="."]\nscale = Vector2({scale}, {scale})\n'
    if cells:
        s += f"tile_map_data = {_tile_map_data(cells)}\n"
    return s + f'tile_set = ExtResource("{tileset_id}")\n'


def to_tscn(model, cfg, spec=None):
    spec = spec or tileset.default_spec()
    cs, px = cfg.export_tile_px, spec.tile_px
    scale = cs / px
    variants = tile_variants(spec)
    tm = model.tile_matrix()
    scene_ids = {k: i for i, k in enumerate(el.INTERACTABLES, 1)}

    ground, walls, inter = [], [], []
    for y in range(model.height):
        for x in range(model.width):
            kind, facing = model.terrain.get((x, y), ("floor", 0))
            key = ("conveyor", el.DIRS[facing]) if kind == "conveyor" else (kind, None)
            ax, ay, alt = variants[key]
            ground.append((x, y, 0, ax, ay, alt))
            code = int(tm[y, x])
            if code in (1, 3):
                ax, ay, alt = variants[("wall" if code == 1 else "boundary", None)]
                walls.append((x, y, 0, ax, ay, alt))
    for (x, y), (k, _f) in sorted(model.objects.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        if k in scene_ids:
            inter.append((x, y, SCENES_SOURCE_ID, 0, 0, scene_ids[k]))

    subs, nodes = [], []
    sid = 0

    def rect(w, h):
        nonlocal sid
        sid += 1
        subs.append(f'[sub_resource type="RectangleShape2D" id="shape_{sid}"]\nsize = Vector2({w}, {h})\n')
        return sid
    nodes.append('[node name="Level" type="Node2D"]\nmetadata/grid_size = Vector2i(%d, %d)\n' % (model.width, model.height))
    nodes.append(_layer("Ground_Terrain", ground, scale))
    nodes.append(_layer("Walls_Boundary", walls, scale))
    nodes.append(_layer("Interactables", inter, scale))
    nodes.append('[node name="Markers" type="Node2D" parent="."]\n')
    count = {}
    for (x, y), (k, f) in sorted(model.objects.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        if k not in el.SYMBOLS:
            continue
        count[k] = count.get(k, 0) + 1
        name = "".join(w.capitalize() for w in k.split("_")) + str(count[k])
        pos = f"position = Vector2({x * cs + cs / 2}, {y * cs + cs / 2})"
        group = {"arrow_start": "player_start", "goal_exit": "goal_exit", "enemy_spawn": "enemy_spawn",
                 "checkpoint": "checkpoint", "patrol_waypoint": "patrol_points"}[k]
        if k in ("goal_exit", "checkpoint"):
            sh = rect(cs, cs)
            nodes.append(f'[node name="{name}" type="Area2D" parent="Markers" groups=["{group}"]]\n{pos}\n')
            nodes.append(f'[node name="Shape" type="CollisionShape2D" parent="Markers/{name}"]\nshape = SubResource("shape_{sh}")\n')
        else:
            extra = f"rotation = {math.radians(90 * f):.6f}\nmetadata/facing = \"{el.DIRS[f]}\"\n" if k == "arrow_start" else ""
            nodes.append(f'[node name="{name}" type="Marker2D" parent="Markers" groups=["{group}"]]\n{pos}\n{extra}')
    ext = [f'[ext_resource type="TileSet" path="{res_dir(spec)}{TILESET_FILE}" id="1_tileset"]\n']
    body = "".join(ext) + "\n" + "\n".join(subs) + ("\n" if subs else "") + "\n".join(nodes)
    steps = sum(l.startswith(("[sub_resource", "[ext_resource")) for l in body.splitlines()) + 1
    return f"[gd_scene load_steps={steps} format=3]\n\n" + body


def prefab_name(key):
    return "".join(w.capitalize() for w in key.split("_"))


_DOOR = '''extends StaticBody2D
# SketchMap door: blocks the way until a player touches the trigger, then opens.
# With requires_key it spends one key from the global keys counter (Engine meta "keys").
@export var requires_key := false
var is_open := false

func _ready() -> void:
	$Trigger.body_entered.connect(_on_body_entered)

func _on_body_entered(body: Node) -> void:
	if is_open or not body.is_in_group("player"):
		return
	if requires_key:
		var keys: int = Engine.get_meta("keys", 0)
		if keys <= 0:
			return
		Engine.set_meta("keys", keys - 1)
	open()

func open() -> void:
	is_open = true
	$Shape.set_deferred("disabled", true)
	$Visual.modulate.a = 0.25
'''

_KEY = '''extends Area2D
# SketchMap key: pickup that adds 1 to the global keys counter.
func _ready() -> void:
	body_entered.connect(_on_body_entered)

func _on_body_entered(body: Node) -> void:
	if body.is_in_group("player"):
		Engine.set_meta("keys", int(Engine.get_meta("keys", 0)) + 1)
		queue_free()
'''

_CHEST = '''extends Area2D
# SketchMap chest: opens once and awards score and a key.
var opened := false

func _ready() -> void:
	body_entered.connect(_on_body_entered)

func _on_body_entered(body: Node) -> void:
	if opened or not body.is_in_group("player"):
		return
	opened = true
	Engine.set_meta("score", int(Engine.get_meta("score", 0)) + 10)
	Engine.set_meta("keys", int(Engine.get_meta("keys", 0)) + 1)
	$Visual.modulate = Color(1, 1, 1, 0.4)
'''

_COLLECTIBLE = '''extends Area2D
# SketchMap collectible: walk-over pickup that adds score.
@export var value := 1

func _ready() -> void:
	body_entered.connect(_on_body_entered)

func _on_body_entered(body: Node) -> void:
	if body.is_in_group("player"):
		Engine.set_meta("score", int(Engine.get_meta("score", 0)) + value)
		queue_free()
'''

_PUSH = '''extends CharacterBody2D
# SketchMap push block: call push(direction) from the player when it walks into the block.
const TILE := __PX__
var moving := false

func push(dir: Vector2) -> bool:
	if moving:
		return false
	dir = Vector2(signf(dir.x), 0.0) if absf(dir.x) > absf(dir.y) else Vector2(0.0, signf(dir.y))
	if dir == Vector2.ZERO or test_move(global_transform, dir * TILE * global_scale):
		return false
	moving = true
	var tw := create_tween()
	tw.tween_property(self, "position", position + dir * TILE, 0.12)
	tw.finished.connect(func(): moving = false)
	return true
'''

_BREAKABLE = '''extends StaticBody2D
# SketchMap breakable prop: call damage() from a weapon or bomb. It carries its own hit points.
signal broken
@export var hp := 1

func damage(amount: int = 1) -> void:
	hp -= amount
	if hp <= 0:
		broken.emit()
		queue_free()
'''

_PLATE = '''extends Area2D
# SketchMap pressure plate: pressed while the player or a push block rests on it.
# Reports to every node in the "puzzle_gates" group; gates open when ALL plates are pressed.
var active := false
var _count := 0

func _ready() -> void:
	body_entered.connect(func(b): _change(b, 1))
	body_exited.connect(func(b): _change(b, -1))

func _change(body: Node, delta: int) -> void:
	if not (body.is_in_group("player") or body.is_in_group("push_block")):
		return
	_count = maxi(_count + delta, 0)
	var now := _count > 0
	if now != active:
		active = now
		$Visual.modulate = Color(0.6, 1.0, 0.6) if active else Color(1, 1, 1)
		get_tree().call_group("puzzle_gates", "check_plates")
'''

_GATE = '''extends StaticBody2D
# SketchMap gate: opens while every pressure plate in the level is pressed.
var is_open := false

func _ready() -> void:
	check_plates.call_deferred()          # scene tiles can initialise after their layer

func check_plates() -> void:
	var plates := get_tree().get_nodes_in_group("puzzle_plates")
	var all_on := plates.size() > 0
	for p in plates:
		if not p.active:
			all_on = false
	is_open = all_on
	$Shape.set_deferred("disabled", all_on)
	$Visual.modulate.a = 0.25 if all_on else 1.0
'''

_SPIKE = '''extends Area2D
# SketchMap spike trap: cycles between safe and harmful; hurts bodies that have take_damage(amount).
@export var period := 1.5
@export var damage := 1
var armed := false

func _ready() -> void:
	var t := Timer.new()
	t.wait_time = period
	t.autostart = true
	t.timeout.connect(_toggle)
	add_child(t)

func _toggle() -> void:
	armed = not armed
	$Visual.modulate = Color(1, 0.4, 0.4) if armed else Color(1, 1, 1, 0.5)
	if armed:
		for b in get_overlapping_bodies():
			if b.has_method("take_damage"):
				b.take_damage(damage)
'''

_TELEPORTER = '''extends Area2D
# SketchMap teleporter: two pads find each other through the "teleporters" group.
var _cooldown := false

func _ready() -> void:
	add_to_group("teleporters")
	body_entered.connect(_on_body_entered)

func _on_body_entered(body: Node) -> void:
	if _cooldown or not body.is_in_group("player"):
		return
	var other = _partner()
	if other == null:
		return
	other._cooldown = true
	body.global_position = other.global_position
	await get_tree().create_timer(0.6).timeout
	other._cooldown = false

func _partner():
	for p in get_tree().get_nodes_in_group("teleporters"):
		if p != self:
			return p
	return null
'''

PREFABS = {
    "door": ("StaticBody2D", "door.gd", _DOOR, True, True, ["door"], ""),
    "locked_door": ("StaticBody2D", "door.gd", _DOOR, True, True, ["door", "locked_door"], "requires_key = true\n"),
    "key": ("Area2D", "key.gd", _KEY, False, False, ["key"], ""),
    "chest": ("Area2D", "chest.gd", _CHEST, False, False, ["chest"], ""),
    "collectible": ("Area2D", "collectible.gd", _COLLECTIBLE, False, False, ["collectible"], ""),
    "push_block": ("CharacterBody2D", "push_block.gd", _PUSH, True, False, ["push_block"], ""),
    "breakable_prop": ("StaticBody2D", "breakable_prop.gd", _BREAKABLE, True, False, ["breakable"], ""),
    "pressure_plate": ("Area2D", "pressure_plate.gd", _PLATE, False, False, ["puzzle_plates"], ""),
    "gate": ("StaticBody2D", "gate.gd", _GATE, True, False, ["puzzle_gates"], ""),
    "spike_trap": ("Area2D", "spike_trap.gd", _SPIKE, False, False, ["spike_trap"], ""),
    "torch": ("Node2D", None, "", False, False, ["torch"], ""),
    "teleporter": ("Area2D", "teleporter.gd", _TELEPORTER, False, False, ["teleporter"], ""),
}


def _color(hexcolor):
    h = hexcolor.lstrip("#")
    return ", ".join(f"{int(h[i:i + 2], 16) / 255:.3f}" for i in (0, 2, 4)) + ", 1"


def prefab_scene_text(key, spec):
    root_type, script, _txt, body, trigger, groups, extra = PREFABS[key]
    e, px, base = el.BY_KEY[key], spec.tile_px, res_dir(spec)
    half, shape = px * 0.4, px * 0.8
    ext = [f'[ext_resource type="Script" path="{base}{PREFAB_DIR}/{script}" id="1_script"]'] if script else []
    subs = []
    if body or root_type == "Area2D":
        subs.append(f'[sub_resource type="RectangleShape2D" id="RectangleShape2D_body"]\nsize = Vector2({_num(shape)}, {_num(shape)})\n')
    if trigger:
        subs.append(f'[sub_resource type="RectangleShape2D" id="RectangleShape2D_trigger"]\nsize = Vector2({_num(px * 1.2)}, {_num(px * 1.2)})\n')
    if key == "torch":
        subs.append('[sub_resource type="Gradient" id="Gradient_glow"]\noffsets = PackedFloat32Array(0, 1)\n'
                    'colors = PackedColorArray(1, 0.75, 0.4, 1, 1, 0.75, 0.4, 0)\n')
        subs.append('[sub_resource type="GradientTexture2D" id="GradientTexture2D_glow"]\ngradient = SubResource("Gradient_glow")\n'
                    'width = 256\nheight = 256\nfill = 1\nfill_from = Vector2(0.5, 0.5)\nfill_to = Vector2(1, 0.5)\n')
    n = []
    gl = ", ".join(f'"{g}"' for g in groups)
    n.append(f'[node name="{prefab_name(key)}" type="{root_type}" groups=[{gl}]]\n' + (f'script = ExtResource("1_script")\n' if script else "") + extra)
    if body or root_type == "Area2D":
        n.append('[node name="Shape" type="CollisionShape2D" parent="."]\nshape = SubResource("RectangleShape2D_body")\n')
    if trigger:
        n.append('[node name="Trigger" type="Area2D" parent="."]\n')
        n.append('[node name="TriggerShape" type="CollisionShape2D" parent="Trigger"]\nshape = SubResource("RectangleShape2D_trigger")\n')
    n.append(f'[node name="Visual" type="ColorRect" parent="."]\noffset_left = {_num(-half)}\noffset_top = {_num(-half)}\n'
             f'offset_right = {_num(half)}\noffset_bottom = {_num(half)}\nmouse_filter = 2\ncolor = Color({_color(e.color)})\n')
    n.append(f'[node name="Label" type="Label" parent="."]\noffset_left = {_num(-half)}\noffset_top = {_num(-half)}\n'
             f'offset_right = {_num(half)}\noffset_bottom = {_num(half)}\nmouse_filter = 2\n'
             f'theme_override_colors/font_color = Color(0.08, 0.08, 0.1, 1)\ntheme_override_font_sizes/font_size = {max(8, int(px * 0.3))}\n'
             f'text = "{e.code}"\nhorizontal_alignment = 1\nvertical_alignment = 1\n')
    if key == "torch":
        n.append('[node name="Light" type="PointLight2D" parent="."]\nshadow_enabled = true\n'
                 f'texture = SubResource("GradientTexture2D_glow")\ntexture_scale = {px / 64 * 2:g}\n')
    steps = len(ext) + len(subs) + 1
    return (f"[gd_scene load_steps={steps} format=3]\n\n" + ("\n".join(ext) + "\n\n" if ext else "") +
            "\n".join(subs) + ("\n" if subs else "") + "\n".join(n))


def prefab_files(spec):
    out = {}
    for key, (_t, script, txt, *_r) in PREFABS.items():
        out[f"{PREFAB_DIR}/{prefab_name(key)}.tscn"] = prefab_scene_text(key, spec)
        if script:
            out[f"{PREFAB_DIR}/{script}"] = txt.replace("__PX__", str(spec.tile_px))
    return out


def write_support_files(folder, spec):
    written = []
    path = os.path.join(folder, TILESET_FILE)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(master_tileset_text(spec))
    written.append(path)
    os.makedirs(os.path.join(folder, PREFAB_DIR), exist_ok=True)
    for rel, text in prefab_files(spec).items():
        p = os.path.join(folder, *rel.split("/"))
        if not os.path.exists(p):
            with open(p, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
            written.append(p)
    return written
