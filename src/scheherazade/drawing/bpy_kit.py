"""A draughtsman's kit for paper architecture, run inside Blender.

The artist writes a short script with these words; the kit turns it into a
sheet: a section, an elevation, a perspective or an axonometric view, in
ink, wash or chiaroscuro. Units are metres, Z is up.

Everything here is plain bpy; a script may also call bpy directly.
"""

from __future__ import annotations

import math

import bmesh
import bpy
from mathutils import Vector

_STYLE = {"name": "chiaroscuro"}

PALETTE = {
    "stone": ((0.62, 0.58, 0.52), 0.85),
    "plaster": ((0.82, 0.79, 0.73), 0.9),
    "wood": ((0.45, 0.33, 0.22), 0.7),
    "iron": ((0.12, 0.12, 0.13), 0.5),
    "earth": ((0.35, 0.30, 0.24), 1.0),
    "water": ((0.20, 0.25, 0.28), 0.05),
    "glass": ((0.55, 0.62, 0.65), 0.05),
    "cloth": ((0.55, 0.50, 0.46), 1.0),
    "figure": ((0.30, 0.27, 0.24), 0.9),
    "ink": ((0.02, 0.02, 0.02), 1.0),
    "paper": ((0.93, 0.90, 0.84), 1.0),
    "brick": ((0.55, 0.36, 0.28), 0.9),
    "gold": ((0.83, 0.64, 0.26), 0.3),
}


def reset(style: str = "chiaroscuro"):
    """Start an empty sheet. style: ink | wash | chiaroscuro | color."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    _STYLE["name"] = style
    sc = bpy.context.scene
    sc.unit_settings.system = "METRIC"
    w = bpy.data.worlds.new("World")
    sc.world = w
    w.use_nodes = True
    world(0.6 if style in ("ink", "wash") else 0.08)


def world(strength: float = 0.1, color=(0.85, 0.83, 0.78)):
    """Ambient light from the sky dome; low for chiaroscuro, high for ink."""
    bg = bpy.context.scene.world.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (*color, 1)
    bg.inputs[1].default_value = strength


def mat(name: str, color=None, rough: float | None = None, emit: float = 0.0):
    """A material by palette name, or a new one with an RGB color."""
    key = f"{name}:{_STYLE['name']}"
    if key in bpy.data.materials:
        return bpy.data.materials[key]
    base, r = PALETTE.get(name, ((0.7, 0.7, 0.7), 0.8))
    color = color or base
    rough = r if rough is None else rough
    if _STYLE["name"] == "ink" and name != "ink":
        color = (0.92, 0.91, 0.88)
    m = bpy.data.materials.new(key)
    m.use_nodes = True
    p = m.node_tree.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = (*color, 1)
    p.inputs["Roughness"].default_value = rough
    if name == "glass":
        p.inputs["Transmission Weight"].default_value = 0.9
    if emit:
        p.inputs["Emission Color"].default_value = (*color, 1)
        p.inputs["Emission Strength"].default_value = emit
    return m


def _link(obj, material):
    bpy.context.scene.collection.objects.link(obj)
    if material is not None:
        obj.data.materials.append(mat(material) if isinstance(material, str) else material)
    return obj


def mesh(name: str, verts, faces, material="stone"):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], [tuple(f) for f in faces])
    me.update()
    return _link(bpy.data.objects.new(name, me), material)


def box(x0, y0, z0, x1, y1, z1, material="stone", name="box"):
    """An axis-aligned block between two corners."""
    x0, x1 = sorted((x0, x1))
    y0, y1 = sorted((y0, y1))
    z0, z1 = sorted((z0, z1))
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    f = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    return mesh(name, v, f, material)


def prism(profile, a, b, material="stone", name="prism"):
    """Extrude a closed 2D profile [(u, v), …] from point a to point b.
    u runs horizontally across the run, v is height above the run."""
    a, b = Vector(a), Vector(b)
    run = b - a
    across = Vector((-run.y, run.x, 0)).normalized() if (run.x or run.y) else Vector((1, 0, 0))
    up = Vector((0, 0, 1))
    n = len(profile)
    verts = [a + across * u + up * v for u, v in profile] + [b + across * u + up * v for u, v in profile]
    faces = [tuple(range(n))[::-1], tuple(range(n, 2 * n))]
    faces += [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)]
    o = mesh(name, verts, faces, material)
    _fix_normals(o)
    return o


def vault(x0, y0, x1, y1, z_spring, rise=None, thickness=0.4, along="y", segments=32, material="stone",
          name="vault"):
    """A barrel vault over the rectangle, springing at z_spring and running
    along x or y. rise defaults to half the span (a round arch)."""
    if along == "y":
        span = abs(x1 - x0)
        a, b = (0, min(y0, y1), z_spring), (0, max(y0, y1), z_spring)
    else:
        span = abs(y1 - y0)
        a, b = (min(x0, x1), 0, z_spring), (max(x0, x1), 0, z_spring)
    rise = span / 2 if rise is None else rise
    outer, inner = [], []
    for i in range(segments + 1):
        t = math.pi * i / segments
        outer.append((-(span / 2 + thickness) * math.cos(t), (rise + thickness) * math.sin(t)))
        inner.append((-(span / 2) * math.cos(t), rise * math.sin(t)))
    profile = outer + inner[::-1]
    o = prism(profile, a, b, material, name)
    if along == "y":
        o.location.x = (x0 + x1) / 2
    else:
        o.location.y = (y0 + y1) / 2
    return o


def cornice(a, b, z, depth=0.35, height=0.4, material="stone", name="cornice", side=1):
    """A moulded cornice along the line a→b at height z, projecting to the
    left of the run (side=1) or to the right (side=-1)."""
    d, h = depth * side, height
    profile = [(0, 0), (0.25 * d, 0.05 * h), (0.3 * d, 0.3 * h), (0.6 * d, 0.45 * h), (0.65 * d, 0.7 * h),
               (d, 0.85 * h), (d, h), (0, h)]
    if side < 0:
        profile = profile[::-1]
    return prism(profile, (a[0], a[1], z), (b[0], b[1], z), material, name)


def cylinder(x, y, z0, z1, r, material="stone", name="cylinder", vertices=32):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=r, depth=z1 - z0,
                                        location=(x, y, (z0 + z1) / 2))
    o = bpy.context.active_object
    o.name = name
    o.data.materials.append(mat(material) if isinstance(material, str) else material)
    return o


def sphere(x, y, z, r, material="stone", name="sphere"):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, location=(x, y, z), segments=48, ring_count=24)
    o = bpy.context.active_object
    o.name = name
    o.data.materials.append(mat(material) if isinstance(material, str) else material)
    bpy.ops.object.shade_smooth()
    return o


def rod(p, q, r=0.03, material="iron", name="rod"):
    """A round bar between two points (cables, pipes, limbs, chains)."""
    p, q = Vector(p), Vector(q)
    d = q - p
    bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=r, depth=d.length, location=(p + q) / 2)
    o = bpy.context.active_object
    o.name = name
    o.rotation_mode = "QUATERNION"
    o.rotation_quaternion = d.to_track_quat("Z", "Y")
    o.data.materials.append(mat(material) if isinstance(material, str) else material)
    return o


def cut(target, cutter, keep_cutter=False):
    """Subtract one object from another (openings, niches, ruins)."""
    m = target.modifiers.new("cut", "BOOLEAN")
    m.operation = "DIFFERENCE"
    m.object = cutter
    m.solver = "EXACT"
    bpy.context.view_layer.objects.active = target
    bpy.ops.object.modifier_apply(modifier=m.name)
    if not keep_cutter:
        bpy.data.objects.remove(cutter, do_unlink=True)
    return target


def opening(wall, x0, y0, z0, x1, y1, z1, arched=False):
    """Cut a door or window through a wall; arched adds a round head."""
    c = box(x0, y0, z0, x1, y1, z1, None, "opening")
    if arched:
        # the head spans the opening's width, the thin side runs through the wall
        r = max(abs(x1 - x0), abs(y1 - y0)) / 2
        cut(wall, _half_disc(x0, y0, x1, y1, z1, r))
    return cut(wall, c)


def _half_disc(x0, y0, x1, y1, z, r):
    thick_x = abs(x1 - x0) < abs(y1 - y0)
    pts = [(-r * math.cos(math.pi * i / 24), r * math.sin(math.pi * i / 24)) for i in range(25)]
    if thick_x:
        a, b = ((x0 + x1) / 2 - 1, (y0 + y1) / 2, z), ((x0 + x1) / 2 + 1, (y0 + y1) / 2, z)
    else:
        a, b = ((x0 + x1) / 2, (y0 + y1) / 2 - 1, z), ((x0 + x1) / 2, (y0 + y1) / 2 + 1, z)
    return prism(pts, a, b, None, "archhead")


def stair(x, y, z, run, rise, width, steps, direction=0, material="stone", name="stair"):
    """A straight flight starting at (x, y, z), climbing towards direction
    (degrees from +X)."""
    objs = []
    for i in range(steps):
        objs.append(box(i * run / steps, 0, 0, (i + 1) * run / steps, width, (i + 1) * rise / steps, material,
                        f"{name}{i}"))
    o = join(objs, name)
    o.rotation_euler.z = math.radians(direction)
    o.location = (x, y, z)
    return o


def join(objs, name="group"):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    o = bpy.context.active_object
    o.name = name
    return o


def place(obj, x=0, y=0, z=0, rotate=0):
    """Move an object (or a list) and turn it around Z by degrees."""
    for o in obj if isinstance(obj, (list, tuple)) else [obj]:
        o.location = (o.location.x + x, o.location.y + y, o.location.z + z)
        o.rotation_euler.z += math.radians(rotate)
    return obj


def _fix_normals(o):
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(o.data)
    bm.free()


# --- furniture and people -------------------------------------------------

def _local(x, y, z, facing):
    a = math.radians(facing)
    return lambda u, v, w: (x + u * math.cos(a) - v * math.sin(a), y + u * math.sin(a) + v * math.cos(a), z + w)


def chair(x, y, z=0, facing=0, material="wood", name="chair"):
    """A plain chair; its sitter looks towards facing (degrees from +X)."""
    L = _local(x, y, z, facing)
    parts = [box(*L(-0.22, -0.22, 0.43), *L(0.22, 0.22, 0.47), material=material)]
    for u, v in ((-0.2, -0.2), (0.2, -0.2), (0.2, 0.2), (-0.2, 0.2)):
        parts.append(rod(L(u, v, 0), L(u, v, 0.43), 0.02, material))
    parts.append(box(*L(-0.24, -0.2, 0.47), *L(-0.2, 0.2, 0.95), material=material))
    return join(parts, name)


def table(x0, y0, x1, y1, z=0, height=0.76, material="wood", name="table"):
    parts = [box(x0, y0, z + height - 0.05, x1, y1, z + height, material)]
    for u, v in ((x0 + 0.05, y0 + 0.05), (x1 - 0.05, y0 + 0.05), (x1 - 0.05, y1 - 0.05), (x0 + 0.05, y1 - 0.05)):
        parts.append(box(u - 0.03, v - 0.03, z, u + 0.03, v + 0.03, z + height - 0.05, material))
    return join(parts, name)


def stove(x, y, z=0, w=0.7, d=0.6, h=1.1, flue_to=None, material="iron", name="stove"):
    """A small iron stove; flue_to is the height its pipe rises to."""
    parts = [box(x - w / 2, y - d / 2, z, x + w / 2, y + d / 2, z + h, material)]
    if flue_to:
        parts.append(rod((x, y, z + h), (x, y, flue_to), 0.08, material))
    return join(parts, name)


def bucket(x, y, z=0, material="iron", name="bucket"):
    return cylinder(x, y, z, z + 0.32, 0.15, material, name, 16)


POSES = {
    # joints in the figure's own frame: u forward, v left, w up; feet on 0
    "stand": dict(head=(0, 0, 1.58), neck=(0, 0, 1.45), hip=(0, 0, 0.92), knee=(0.02, 0, 0.5), foot=(0, 0, 0.03),
                  hand=(0.05, 0, 0.82), elbow=(0, 0, 1.15)),
    "walk": dict(head=(0.05, 0, 1.57), neck=(0.03, 0, 1.44), hip=(0, 0, 0.9), knee=(0.15, 0, 0.5),
                 foot=(0.3, 0, 0.03), knee2=(-0.1, 0, 0.48), foot2=(-0.3, 0, 0.08), hand=(-0.2, 0, 0.85),
                 elbow=(-0.1, 0, 1.15)),
    "carry": dict(head=(0, 0, 1.58), neck=(0, 0, 1.45), hip=(0, 0, 0.92), knee=(0.02, 0, 0.5), foot=(0, 0, 0.03),
                  hand=(0.4, 0, 1.05), elbow=(0.25, 0, 1.15)),
    # seat height is z: the hip rests on it
    "sit": dict(head=(0, 0, 0.72), neck=(0, 0, 0.58), hip=(0, 0, 0.05), knee=(0.45, 0, 0.08),
                foot=(0.5, 0, -0.42), hand=(0.35, 0, 0.12), elbow=(0.15, 0, 0.3)),
    "sit_ledge": dict(head=(0.05, 0, 0.72), neck=(0.03, 0, 0.58), hip=(0, 0, 0.05), knee=(0.45, 0, 0.12),
                      foot=(0.85, 0, 0.1), hand=(-0.15, 0, 0.02), elbow=(-0.1, 0, 0.3)),
    "recline": dict(head=(-0.55, 0, 0.55), neck=(-0.45, 0, 0.45), hip=(0, 0, 0.08), knee=(0.45, 0, 0.12),
                    foot=(0.9, 0, 0.05), hand=(0.1, 0, 0.15), elbow=(-0.25, 0, 0.25)),
    "kneel": dict(head=(0.1, 0, 1.12), neck=(0.08, 0, 1.0), hip=(0, 0, 0.5), knee=(0.2, 0, 0.05),
                  foot=(-0.3, 0, 0.03), hand=(0.4, 0, 0.45), elbow=(0.2, 0, 0.75)),
}


def figure(x, y, z=0, pose="stand", facing=0, scale=1.0, material="figure", name="figure"):
    """Staffage: a small human figure for scale, as in Piranesi or Boullée.
    pose: stand | walk | carry | sit | sit_ledge | recline | kneel."""
    j = POSES[pose]
    L = _local(x, y, z, facing)
    s = lambda p, side=0.0: L(p[0] * scale, (p[1] + side) * scale, p[2] * scale)
    r = 0.06 * scale
    parts = [sphere(*s(j["head"]), 0.11 * scale, material),
             rod(s(j["neck"]), s(j["hip"]), 0.14 * scale, material)]
    for side in (0.1, -0.1):
        knee, foot = (j["knee"], j["foot"]) if side > 0 or "knee2" not in j else (j["knee2"], j["foot2"])
        parts += [rod(s(j["hip"], side), s(knee, side), r, material), rod(s(knee, side), s(foot, side), r, material)]
        parts += [rod(s(j["neck"], side * 1.8), s(j["elbow"], side * 2.2), r * 0.8, material),
                  rod(s(j["elbow"], side * 2.2), s(j["hand"], side * 1.5), r * 0.7, material)]
    return join(parts, name)


# --- light, camera, drawing -------------------------------------------------

def sun(azimuth=210, elevation=25, strength=4.0, softness=1.0, color=(1.0, 0.95, 0.88)):
    """Sunlight from a compass direction (degrees from +X towards +Y) and
    height above the horizon; low elevation gives long raking shadows."""
    d = bpy.data.lights.new("sun", "SUN")
    d.energy = strength
    d.angle = math.radians(softness)
    d.color = color
    o = bpy.data.objects.new("sun", d)
    bpy.context.scene.collection.objects.link(o)
    az, el = math.radians(azimuth), math.radians(elevation)
    direction = Vector((math.cos(az) * math.cos(el), math.sin(az) * math.cos(el), math.sin(el)))
    o.rotation_mode = "QUATERNION"
    o.rotation_quaternion = (-direction).to_track_quat("-Z", "Y")
    return o


def lamp(x, y, z, power=200, radius=0.1, color=(1.0, 0.85, 0.65)):
    """A point of warm light: a candle, a lamp, a fire."""
    d = bpy.data.lights.new("lamp", "POINT")
    d.energy = power
    d.shadow_soft_size = radius
    d.color = color
    o = bpy.data.objects.new("lamp", d)
    o.location = (x, y, z)
    bpy.context.scene.collection.objects.link(o)
    return o


def glow(x0, y0, z0, x1, y1, z1, power=300, color=(1.0, 0.95, 0.85)):
    """Light coming through an opening (a window, a skylight): an area light
    filling the rectangle and shining inward along its thin axis."""
    dims = [abs(x1 - x0), abs(y1 - y0), abs(z1 - z0)]
    thin = dims.index(min(dims))
    d = bpy.data.lights.new("glow", "AREA")
    d.energy = power
    d.color = color
    d.shape = "RECTANGLE"
    o = bpy.data.objects.new("glow", d)
    o.location = ((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)
    others = [i for i in range(3) if i != thin]
    d.size, d.size_y = dims[others[0]], dims[others[1]]
    if thin == 0:
        o.rotation_euler = (0, math.radians(90), 0)
    elif thin == 1:
        o.rotation_euler = (math.radians(90), 0, 0)
    bpy.context.scene.collection.objects.link(o)
    return o


def camera(location, target, lens=35.0, ortho_scale=None, shift=(0, 0)):
    """Perspective view (lens in mm), or orthographic when ortho_scale is
    set (the width of the view in metres): elevations, sections, axonometry."""
    c = bpy.data.cameras.new("camera")
    if ortho_scale:
        c.type = "ORTHO"
        c.ortho_scale = ortho_scale
    else:
        c.lens = lens
    c.shift_x, c.shift_y = shift
    c.clip_end = 2000
    o = bpy.data.objects.new("camera", c)
    bpy.context.scene.collection.objects.link(o)
    o.location = location
    o.rotation_mode = "QUATERNION"
    o.rotation_quaternion = (Vector(target) - Vector(location)).to_track_quat("-Z", "Y")
    bpy.context.scene.camera = o
    return o


def axonometric(target, distance=60, azimuth=225, elevation=35, ortho_scale=30):
    """A military/isometric-like view from above at an angle."""
    az, el = math.radians(azimuth), math.radians(elevation)
    loc = Vector(target) + distance * Vector((math.cos(az) * math.cos(el), math.sin(az) * math.cos(el), math.sin(el)))
    return camera(tuple(loc), target, ortho_scale=ortho_scale)


def section(axis="y", at=0.0, keep="-", poche="ink"):
    """Slice every solid by a plane (x=at or y=at), keep the side below
    (keep="-") or above (keep="+") the plane, and fill the cut with black
    poché, as in an architect's section. Look at it from the removed side."""
    big = 500
    i = 0 if axis == "x" else 1
    lo, hi = [-big, -big, -big], [big, big, big]
    if keep == "-":
        lo[i] = at
    else:
        hi[i] = at
    cutter = box(*lo, *hi, None, "section-cutter")
    ink = mat(poche)
    for o in list(bpy.context.scene.objects):
        if o.type != "MESH" or o is cutter:
            continue
        m = o.modifiers.new("section", "BOOLEAN")
        m.operation = "DIFFERENCE"
        m.object = cutter
        m.solver = "EXACT"
        bpy.context.view_layer.objects.active = o
        try:
            bpy.ops.object.modifier_apply(modifier=m.name)
        except RuntimeError:
            o.modifiers.remove(m)
            continue
        if ink.name not in o.data.materials:
            o.data.materials.append(ink)
        slot = list(o.data.materials).index(o.data.materials[ink.name])
        mw = o.matrix_world
        for f in o.data.polygons:
            if all(abs((mw @ o.data.vertices[v].co)[i] - at) < 1e-3 for v in f.vertices):
                f.material_index = slot
    bpy.data.objects.remove(cutter, do_unlink=True)


def ground(size=200, z=0.0, material="earth"):
    return box(-size, -size, z - 0.5, size, size, z, material, "ground")


def render(path, width=1800, height=1200, samples=96, lines=None, line_width=1.2):
    """Draw the sheet. lines: add ink contours (default on for ink/wash)."""
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = samples
    sc.cycles.use_denoising = True
    sc.render.resolution_x, sc.render.resolution_y = width, height
    sc.render.film_transparent = False
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Punchy" if _STYLE["name"] == "chiaroscuro" else "None"
    use_lines = _STYLE["name"] in ("ink", "wash") if lines is None else lines
    sc.render.use_freestyle = use_lines
    if use_lines:
        sc.render.line_thickness_mode = "ABSOLUTE"
        sc.render.line_thickness = line_width
        ls = sc.view_layers[0].freestyle_settings.linesets.new("ink") if not sc.view_layers[0].freestyle_settings.linesets else \
            sc.view_layers[0].freestyle_settings.linesets[0]
        ls.select_by_visibility = True
        ls.select_crease = ls.select_silhouette = ls.select_border = True
        if ls.linestyle is None:
            ls.linestyle = bpy.data.linestyles.new("ink")
        ls.linestyle.color = (0.08, 0.07, 0.06)
    sc.render.image_settings.file_format = "PNG"
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
