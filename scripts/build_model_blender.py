"""Builds the 3D model for the web page (models/noise-logger.glb and models/colors.json) in Blender.
Made the way the drone guide's models are (its scripts/build/lib_core.py): real materials, rounded edges, and names,
accuracy tags and label points carried inside the file.

Every measurement comes from the number table in make_parts.py (official Pi 5 drawing, case sizes, PROVISIONAL marks).
Nothing is retyped here. What IS drawn by eye here is marked 'by eye' below: the case's shape details, the mic,
the tripod, the bookshelf with its books and the cable routes. The viewer tells the reader which is which (tap a part).

Units: millimetres, Z up, the same axes as before (the case's front-left bottom corner is 0, 0, 0).
Run:  blender -b --factory-startup -P scripts/build_model_blender.py
      (set NL_MODEL_OUT to write somewhere other than models/)"""
import json
import math
import os
import sys
import types

import bmesh
import bpy
import numpy as np
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.environ.get("NL_MODEL_OUT") or os.path.join(ROOT, "models")
sys.path.insert(0, HERE)
if "trimesh" not in sys.modules:              # make_parts.py needs its mesh library only to cut the print files, not for the numbers
    try:
        import trimesh  # noqa: F401
    except ImportError:
        sys.modules["trimesh"] = types.ModuleType("trimesh")
import glb_pack  # noqa: E402
import make_parts as M  # noqa: E402

bpy.ops.wm.read_factory_settings(use_empty=True)
SCENE = bpy.context.scene
HEX = {}                                       # mesh name -> colour, written to colors.json


# ---------------------------------------------------------------- materials
class Mat:
    def __init__(self, name, hex_colour, metallic=0.0, rough=0.5, alpha=1.0, glow=0.0, image=None):
        self.hex = hex_colour
        m = self.mat = bpy.data.materials.new(name)
        m.use_nodes = True
        b = m.node_tree.nodes.get("Principled BSDF")
        rgb = [int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
        b.inputs["Base Color"].default_value = (*lin, 1.0)
        b.inputs["Metallic"].default_value = metallic
        b.inputs["Roughness"].default_value = rough
        b.inputs["Alpha"].default_value = alpha
        if glow:
            b.inputs["Emission Color"].default_value = (*lin, 1.0)
            b.inputs["Emission Strength"].default_value = glow
        if alpha < 1.0:
            for key, value in (("blend_method", "BLEND"), ("surface_render_method", "BLENDED")):
                if hasattr(m, key):
                    try:
                        setattr(m, key, value)
                    except (TypeError, AttributeError):
                        pass
        if image is not None:
            tex = m.node_tree.nodes.new("ShaderNodeTexImage")
            tex.image = image
            m.node_tree.links.new(tex.outputs["Color"], b.inputs["Base Color"])


def wood_image():
    """Wood grain for the shelf, drawn by eye: long streaks along the board, a little darker in the rings."""
    w, h = 256, 128
    rng = np.random.default_rng(7)
    u, v = np.linspace(0, 1, w)[None, :], np.linspace(0, 1, h)[:, None]
    warp = 0.012 * np.sin(2 * np.pi * (u + 0.3)) + 0.006 * np.sin(2 * np.pi * 2.3 * u)
    rings = (np.sin(2 * np.pi * (v + warp) * 7) * 0.5 + 0.5) ** 3
    fine = np.sin(2 * np.pi * (v + warp * 1.7) * 31 + 3 * np.sin(2 * np.pi * u)) * 0.5 + 0.5
    rows = np.convolve(rng.normal(size=h + 8), np.ones(9) / 9, mode="valid")[:, None]
    shade = 1.0 - 0.09 * rings - 0.05 * fine + 0.16 * rows
    base = np.array([0xb9, 0x8a, 0x5a]) / 255
    px = np.clip(shade[:, :, None] * base[None, None, :], 0, 1)
    rgba = np.concatenate([px, np.ones((h, w, 1))], axis=2).astype(np.float32)
    img = bpy.data.images.new("wood", w, h, alpha=False)
    img.pixels.foreach_set(rgba.ravel())
    path = os.path.join(OUT, "_wood.jpg")
    img.file_format = "JPEG"
    img.filepath_raw = path
    img.save(filepath=path, quality=80)
    return bpy.data.images.load(path), path


os.makedirs(OUT, exist_ok=True)
WOOD_IMG, WOOD_FILE = wood_image()
P = dict(
    pcb=Mat("PCBGreen", "#19653d", 0.0, 0.50), gold=Mat("Gold", "#c9a03a", 1.0, 0.34),
    chip=Mat("ChipBlack", "#22252a", 0.0, 0.45), lid=Mat("ChipLid", "#a9afb6", 0.9, 0.38),
    shield=Mat("ShieldCan", "#c3c7cc", 0.9, 0.42), shell=Mat("SocketMetal", "#c9ced3", 1.0, 0.30),
    black=Mat("PlasticBlack", "#202225", 0.0, 0.48), beige=Mat("PlasticBeige", "#e8e3d6", 0.0, 0.55),
    white=Mat("PlasticWhite", "#f2efe6", 0.0, 0.50), latch=Mat("LatchBrown", "#4a3b32", 0.0, 0.55),
    usb_blue=Mat("UsbBlue", "#2f6fd6", 0.0, 0.45), usb_black=Mat("UsbBlack", "#1c1e21", 0.0, 0.45),
    led_red=Mat("LedRed", "#7a1b1b", 0.0, 0.35), led_green=Mat("LedGreen", "#2ecc71", 0.0, 0.35),
    led_yellow=Mat("LedYellow", "#f1c40f", 0.0, 0.35), button=Mat("ButtonCap", "#d8d8d8", 0.0, 0.5),
    card=Mat("CardBlue", "#3b82c4", 0.0, 0.5), alu=Mat("Aluminium", "#c4c8cd", 1.0, 0.36),
    case_red=Mat("CaseRed", "#c51f4a", 0.0, 0.40), case_white=Mat("CaseWhite", "#f1eee8", 0.0, 0.42),
    lightpipe=Mat("LightPipe", "#fbfaf6", 0.0, 0.3), rubber_pale=Mat("FootSilicone", "#d6d4ce", 0.0, 0.85),
    fan_frame=Mat("FanFrame", "#2a2d31", 0.0, 0.5), fan_blade=Mat("FanBlade", "#3a3e44", 0.0, 0.42),
    fan_hub=Mat("FanHub", "#55595f", 0.0, 0.45), sticker=Mat("FanSticker", "#c9ccd0", 0.6, 0.4),
    wood=Mat("ShelfWood", "#b98a5a", 0.0, 0.62, image=WOOD_IMG),
    mic_body=Mat("MicBody", "#6f747b", 0.9, 0.36), mic_ring=Mat("MicRing", "#cfd2d6", 1.0, 0.28),
    mic_tube=Mat("MicTube", "#7d828a", 0.9, 0.34), foam=Mat("MicFoam", "#1d1f22", 0.0, 1.0),
    clip=Mat("MicClip", "#23262a", 0.0, 0.58), stand=Mat("TripodMetal", "#2b2e33", 0.6, 0.42),
    rubber=Mat("Rubber", "#17181a", 0.0, 0.85), mic_light=Mat("MicLight", "#3b82c4", 0.0, 0.3, glow=1.5),
    cable=Mat("CableUsb", "#2b2e33", 0.0, 0.58), cable_power=Mat("CablePower", "#1d1f22", 0.0, 0.58),
    plug=Mat("PlugMould", "#26282c", 0.0, 0.5),
    book0=Mat("BookGreen", "#3d6b58", 0.0, 0.7), book1=Mat("BookBrick", "#a4523a", 0.0, 0.7), book2=Mat("BookNavy", "#2f4a6b", 0.0, 0.7),
    book3=Mat("BookMustard", "#c79a3a", 0.0, 0.7), book4=Mat("BookCream", "#e6dcc3", 0.0, 0.75),
)


# ---------------------------------------------------------------- mesh helpers (no bpy.ops: stable in background mode)
def link(name, verts, faces, m):
    me = bpy.data.meshes.new("g_" + name)
    me.from_pydata([tuple(v) for v in verts], [], [tuple(f) for f in faces])
    me.validate(verbose=False)
    me.update()
    ob = bpy.data.objects.new(name, me)
    SCENE.collection.objects.link(ob)
    ob.data.materials.append(m.mat)
    HEX[id(ob)] = m.hex
    return ob


def apply(ob):
    """Bake the object's modifiers into its mesh."""
    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    old = ob.data
    ob.modifiers.clear()
    ob.data = me
    bpy.data.meshes.remove(old)
    return ob


def bevel(ob, width, seg=2):
    mod = ob.modifiers.new("Bevel", "BEVEL")
    mod.width, mod.segments, mod.limit_method, mod.angle_limit = width, seg, "ANGLE", math.radians(50)
    return apply(ob)


def cut(ob, cutters, op="DIFFERENCE"):
    for c in cutters:
        mod = ob.modifiers.new("Cut", "BOOLEAN")
        mod.operation, mod.object, mod.solver = op, c, "EXACT"
    apply(ob)
    for c in cutters:
        drop(c)
    return ob


def drop(ob):
    me = ob.data
    HEX.pop(id(ob), None)
    bpy.data.objects.remove(ob, do_unlink=True)
    bpy.data.meshes.remove(me)


def join(name, obs, m=None):
    """One mesh from several (all sit in world space, so the points are simply collected)."""
    verts, faces = [], []
    for ob in obs:
        off = len(verts)
        verts += [tuple(v.co) for v in ob.data.vertices]
        faces += [tuple(off + i for i in p.vertices) for p in ob.data.polygons]
    mat = m or next(k for k in P.values() if k.mat == obs[0].data.materials[0])
    for ob in obs:
        drop(ob)
    return link(name, verts, faces, mat)


def box(name, x, y, z, sx, sy, sz, m, bev=0.0, seg=1):
    """A box from its low corner (x, y, z) and its size, like make_parts.box."""
    v = [(x, y, z), (x + sx, y, z), (x + sx, y + sy, z), (x, y + sy, z),
         (x, y, z + sz), (x + sx, y, z + sz), (x + sx, y + sy, z + sz), (x, y + sy, z + sz)]
    f = [(3, 2, 1, 0), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    ob = link(name, v, f, m)
    return bevel(ob, bev, seg) if bev > 0 else ob


def rr(w, d, r, x=0.0, y=0.0, inset=0.0, steps=8):
    """Outline of a rectangle with rounded corners, counter-clockwise."""
    r = max(r - inset, 0.3)
    x0, y0, x1, y1 = x + inset, y + inset, x + w - inset, y + d - inset
    out = []
    for cx, cy, a0 in ((x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)):
        for s in range(steps + 1):
            a = math.radians(a0 + 90.0 * s / steps)
            out.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return out


def loft(name, rings, m):
    """Skin over a row of rings (each a list of 3D points, all the same length), closed at both ends."""
    n, verts, faces = len(rings[0]), [], []
    for ring in rings:
        verts += [tuple(p) for p in ring]
    for k in range(len(rings) - 1):
        a, b = k * n, (k + 1) * n
        for i in range(n):
            j = (i + 1) % n
            faces.append((a + i, a + j, b + j, b + i))
    faces.append(tuple(range(n - 1, -1, -1)))
    faces.append(tuple(range((len(rings) - 1) * n, len(rings) * n)))
    return link(name, verts, faces, m)


def stack(name, w, d, r, sections, m, x=0.0, y=0.0, steps=8):
    """A rounded block whose outline steps in or out as it rises: sections = [(inset, z), ...]. Gives soft edges."""
    return loft(name, [[(px, py, z) for px, py in rr(w, d, r, x, y, inset, steps)] for inset, z in sections], m)


def prism(name, outline, a0, a1, m, axis="z"):
    """Push a flat outline along an axis: 'z' (outline in x, y), 'y' (outline in x, z) or 'x' (outline in y, z)."""
    put = {"z": lambda u, v, t: (u, v, t), "y": lambda u, v, t: (u, t, v), "x": lambda u, v, t: (t, u, v)}[axis]
    return loft(name, [[put(u, v, t) for u, v in outline] for t in (a0, a1)], m)


def socket(name, outline_out, outline_in, lo, hi, m, axis, mouth, back=0.6):
    """A metal socket: a hollow shell with an open mouth at the 'lo' or the 'hi' end of the axis."""
    solid = prism(name, outline_out, lo, hi, m, axis)
    a, b = (lo - 1.0, hi - back) if mouth == "lo" else (lo + back, hi + 1.0)
    return cut(solid, [prism(name + "_c", outline_in, a, b, m, axis)])


def lathe(name, origin, axis, profile, m, seg=32):
    """Turn a profile [(distance along the axis, radius), ...] round an axis. Radius 0 closes the end in a point."""
    o, a = Vector(origin), Vector(axis).normalized()
    up = Vector((0, 0, 1)) if abs(a.z) < 0.95 else Vector((1, 0, 0))
    u = a.cross(up).normalized()
    v = a.cross(u).normalized()
    verts, faces, rings = [], [], []
    for s, r in profile:
        c = o + a * s
        if r < 1e-6:
            verts.append(tuple(c))
            rings.append([len(verts) - 1])
        else:
            first = len(verts)
            for i in range(seg):
                t = 2 * math.pi * i / seg
                verts.append(tuple(c + (u * math.cos(t) + v * math.sin(t)) * r))
            rings.append(list(range(first, first + seg)))
    for A, B in zip(rings[:-1], rings[1:]):
        for i in range(seg):
            j = (i + 1) % seg
            if len(A) == 1 and len(B) > 1:
                faces.append((A[0], B[j], B[i]))
            elif len(B) == 1 and len(A) > 1:
                faces.append((A[i], A[j], B[0]))
            elif len(A) > 1:
                faces.append((A[i], A[j], B[j], B[i]))
    if len(rings[0]) > 1:
        faces.append(tuple(rings[0][::-1]))
    if len(rings[-1]) > 1:
        faces.append(tuple(rings[-1]))
    return link(name, verts, faces, m)


def rod(name, p0, p1, r, m, seg=16, ch=0.0):
    """A round bar from p0 to p1, with an optional small chamfer at both ends."""
    p0, p1 = Vector(p0), Vector(p1)
    L = (p1 - p0).length
    prof = [(0, r - ch), (ch, r), (L - ch, r), (L, r - ch)] if ch > 0 else [(0, r), (L, r)]
    return lathe(name, p0, p1 - p0, prof, m, seg)


def smooth_path(points, per=4):
    """Catmull-Rom through the points (ends kept), so a cable bends in a curve (as lib_core._smooth_path)."""
    pts = [Vector(p) for p in points]
    Q = [pts[0]] + pts + [pts[-1]]
    out = []
    for i in range(1, len(Q) - 2):
        p0, p1, p2, p3 = Q[i - 1], Q[i], Q[i + 1], Q[i + 2]
        for k in range(per):
            t = k / per
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                              + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    out.append(pts[-1])
    return out


def tube(name, points, r, m, res=8, per=4):
    """A cable: a circle swept along a smooth path, without twisting."""
    pts = smooth_path(points, per)
    verts, faces, side = [], [], None
    for i, p in enumerate(pts):
        d = (pts[min(i + 1, len(pts) - 1)] - pts[max(i - 1, 0)]).normalized()
        if side is None:
            side = d.cross(Vector((0, 0, 1)) if abs(d.z) < 0.9 else Vector((0, 1, 0))).normalized()
        side = (side - d * side.dot(d)).normalized()
        up = d.cross(side)
        for s in range(res):
            a = 2 * math.pi * s / res
            verts.append(tuple(p + (side * math.cos(a) + up * math.sin(a)) * r))
    for i in range(len(pts) - 1):
        for s in range(res):
            s2, a, b = (s + 1) % res, i * res, (i + 1) * res
            faces.append((a + s, a + s2, b + s2, b + s))
    faces.append(tuple(range(res - 1, -1, -1)))
    faces.append(tuple(range((len(pts) - 1) * res, len(pts) * res)))
    return link(name, verts, faces, m)


def finish(ob, sharp_deg=35):
    """Normals outward, smooth shading, and a hard edge wherever two faces meet at more than sharp_deg."""
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0005)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    lim = math.radians(sharp_deg)
    for f in bm.faces:
        f.smooth = True
    for e in bm.edges:
        e.smooth = not (len(e.link_faces) == 2 and e.calc_face_angle(0.0) > lim)
    bm.to_mesh(ob.data)
    bm.free()
    ob.data.update()


def box_uv(ob, grain, x0, y0, z0, lx, ly, lz, shift=0.0):
    """Wood grain coordinates: u runs along the grain axis, v across it."""
    me = ob.data
    uv = me.uv_layers.new(name="UVMap")
    low, size = (x0, y0, z0), (lx, ly, lz)
    for poly in me.polygons:
        n = [abs(c) for c in poly.normal]
        flat = n.index(max(n))
        across = next(a for a in (1, 0, 2) if a != grain and a != flat) if flat != grain else next(a for a in (1, 0, 2) if a != grain)
        along = grain if flat != grain else next(a for a in (0, 1, 2) if a != grain and a != across)
        for li in poly.loop_indices:
            co = me.vertices[me.loops[li].vertex_index].co
            uv.data[li].uv = ((co[along] - low[along]) / size[along] * 0.96 + 0.02,
                              ((co[across] - low[across]) / size[across] * 0.9 + 0.05 + shift) % 1.0)


# ---------------------------------------------------------------- the numbers (all from make_parts.py)
C = M.OCASE
OX, OY = C["board"]                                      # board corner inside the bought case
ZB, ZT = M.Z_BOARD, M.Z_TOP                              # underside and top of the board
Z0, ZBASE = C["foot"], C["foot"] + C["base_h"]           # under the base; where the base meets the frame
ZFRAME = ZBASE + C["frame_h"]
BW, BH = M.BOARD["w"], M.BOARD["h"]
RIGHT_Y0 = min(p["c"] - p["w"] / 2 for p in M.RIGHT.values()) - 1
RIGHT_Y1 = max(p["c"] + p["w"] / 2 for p in M.RIGHT.values()) + 1
FAN_X, FAN_Y = C["w"] / 2 - 8, C["d"] / 2                # as in make_parts.official_case
PARTS = []                                               # finished meshes


def done(ob, sharp=35):
    finish(ob, sharp)
    PARTS.append(ob)
    return ob


# ---------------------------------------------------------------- Raspberry Pi 5 (official drawing)
def pi():
    holes = [(OX + hx, OY + hy) for hx, hy in M.HOLES]
    board = prism("board", rr(BW, BH, 3.0, OX, OY, steps=5), ZB, ZT, P["pcb"])
    cut(board, [lathe("h", (x, y, ZB - 1), (0, 0, 1), [(0, M.HOLE_D / 2), (M.BOARD["t"] + 2, M.HOLE_D / 2)], P["pcb"], 16) for x, y in holes])
    done(board)
    rings = []
    for x, y in holes:                                   # the gold ring round each mounting hole (6 mm, the posts' size)
        r = lathe("r", (x, y, ZT), (0, 0, 1), [(0, M.POST_R), (0.06, M.POST_R)], P["gold"], 20)
        rings.append(cut(r, [lathe("rc", (x, y, ZT - 1), (0, 0, 1), [(0, M.HOLE_D / 2), (2, M.HOLE_D / 2)], P["gold"], 16)]))
    done(join("board__ring", rings))
    chip_mat = {"board__soc": "lid", "board__wifi": "shield"}
    for key, x, y, w, h, _ in M.CHIPS:
        done(box(key, OX + x, OY + y, ZT, w, h, 1.2, P[chip_mat.get(key, "chip")], 0.22))
    # GPIO: black base and 40 gold pins, 2.54 mm apart
    gx = OX + M.GPIO_C
    done(box("gpio", gx - 25.4, OY + BH - 6.0, ZT, 50.8, 5.0, 2.5, P["black"], 0.25))
    pins = [box("p", gx - 24.13 + i * 2.54 - 0.32, OY + BH - 3.5 + (j - 0.5) * 2.54 - 0.32, ZT + 2.5, 0.64, 0.64, 6.0, P["gold"])
            for i in range(20) for j in range(2)]
    done(join("gpio__pin", pins))
    # front edge: USB-C power and two micro-HDMI, each a hollow metal shell with its tongue
    for key, f in M.FRONT.items():
        z0, z1 = ZT + max(f["z0"], 0.0), ZT + f["z1"]
        x0, x1, y0 = OX + f["c"] - f["w"] / 2, OX + f["c"] + f["w"] / 2, OY - f["out"]
        rad = (z1 - z0) / 2 - 0.02 if key == "usb-c_power" else 0.7
        wall = 0.3
        done(socket(key, rr(x1 - x0, z1 - z0, rad, x0, z0, steps=4), rr(x1 - x0, z1 - z0, rad, x0, z0, wall, steps=4),
                    y0, y0 + f["d"], P["shell"], "y", "lo"))
        done(box(key + "__tongue", x0 + 1.6, y0 + 0.8, (z0 + z1) / 2 - 0.35, f["w"] - 3.2, f["d"] - 1.6, 0.7, P["black"]))
    # right edge: network socket and two USB stacks
    for key, r in M.RIGHT.items():
        x1 = OX + BW + r["out"]
        x0, y0, y1 = x1 - r["d"], OY + r["c"] - r["w"] / 2, OY + r["c"] + r["w"] / 2
        done(socket(key, rr(r["w"], r["z1"], 0.5, y0, ZT, steps=2), rr(r["w"], r["z1"], 0.5, y0, ZT, 0.6, steps=2),
                    x0, x1, P["shell"], "x", "hi"))
        if key == "ethernet":
            done(box("ethernet__inner", x0 + 0.6, y0 + 1.6, ZT + 1.6, r["d"] - 8.0, r["w"] - 3.2, r["z1"] - 4.6, P["black"]))
            done(box("ethernet__led_g", x1 - 0.5, y0 + 1.5, ZT + 11.0, 0.6, 2.0, 1.2, P["led_green"]))
            done(box("ethernet__led_y", x1 - 0.5, y1 - 3.5, ZT + 11.0, 0.6, 2.0, 1.2, P["led_yellow"]))
        else:                                             # two sockets one above the other: a bar between them, a tongue in each
            done(box(key + "__bar", x1 - 6.0, y0 + 0.3, ZT + r["z1"] / 2 - 1.1, 5.9, r["w"] - 0.6, 2.2, P["shell"]))
            tongues = [box("t", x0 + 2.5, y0 + 2.0, zz + 1.6, 14.0, r["w"] - 4.0, 1.8, P["usb_blue"]) for zz in (ZT + 2.2, ZT + 9.8)]
            done(join(key + "__tongue", tongues, P["usb_blue" if key == "usb_stack_lower" else "usb_black"]))
    bodies, latches = [], []
    for x, y, w, h in M.MIPI:                             # camera / display connectors: pale body, dark latch
        bodies.append(box("m", OX + x, OY + y, ZT, w, h, 3.3, P["beige"], 0.15))
        latches.append(box("l", OX + x + 0.2, OY + y + 0.5, ZT + 3.3, w * 0.45, h - 1.0, 0.7, P["latch"]))
    done(join("mipi", bodies))
    done(join("mipi__latch", latches))
    px, py, pw, ph = M.POE
    done(box("poe", OX + px, OY + py, ZT, pw, ph, 2.5, P["black"], 0.15))
    done(join("poe__pin", [box("p", OX + px + pw * (0.27 + 0.46 * i) - 0.32, OY + py + ph * (0.27 + 0.46 * j) - 0.32, ZT + 2.5, 0.64, 0.64, 3.0, P["gold"])
                           for i in range(2) for j in range(2)]))
    fx, fy, fw, fh = M.FAN_PLUG
    done(box("fan_plug", OX + fx, OY + fy, ZT, fw, fh, 4.0, P["white"], 0.2))
    done(box("fan_plug__slot", OX + fx + 0.8, OY + fy + 0.8, ZT + 4.0, fw - 1.6, fh - 1.6, 0.05, P["chip"]))
    done(box("power_button", OX + 0.39, OY + M.BUTTON["y"] - 2.12, ZT, 2.54, 4.23, 2.58, P["black"], 0.15))
    done(box("power_button__cap", OX - M.BUTTON["out"], OY + M.BUTTON["y"] - 1.0, ZT + 0.71, 0.85, 2.01, 1.97, P["button"]))
    done(box("board__led_pwr", OX + 0.14, OY + M.LIGHT["y"] - 1.0, ZT, 1.48, 2.01, 0.99, P["led_red"]))
    done(box("pcie", OX + 1.15, OY + 24.9, ZT, 3.05, 10.4, 2.0, P["black"], 0.15))
    done(box("pcie__latch", OX + 1.15, OY + 25.4, ZT + 2.0, 1.4, 9.4, 0.5, P["latch"]))
    # memory card under the board, at the left edge: the card's outline with its notch
    cd = M.CARD
    cx0, cy0, cw, cl = OX - cd["out"], OY + cd["c"] - cd["w"] / 2, cd["w"], 15.0
    outline = [(cx0, cy0 + 1.0), (cx0 + 1.0, cy0), (cx0 + cl, cy0), (cx0 + cl, cy0 + cw), (cx0 + 5.6, cy0 + cw),
               (cx0 + 4.8, cy0 + cw - 0.9), (cx0 + 2.2, cy0 + cw - 0.9), (cx0 + 1.4, cy0 + cw), (cx0, cy0 + cw)]
    done(prism("sdcard", outline, ZT + cd["z0"], ZT + cd["z1"], P["card"]))
    # the case's small stick-on heatsink (size from the case's brief): a base and fins (fins by eye)
    soc = M.CHIPS[0]
    hx, hy, hz = M.HEATSINK
    sx0, sy0, sz0 = OX + soc[1] + soc[3] / 2 - hx / 2, OY + soc[2] + soc[4] / 2 - hy / 2, ZT + 1.2
    fins = [box("hb", sx0, sy0, sz0, hx, hy, 1.1, P["alu"])]
    nfin = 6
    for i in range(nfin):
        fins.append(box("hf", sx0 + i * (hx - 0.9) / (nfin - 1), sy0, sz0 + 1.0, 0.9, hy, hz - 1.0, P["alu"]))
    done(join("heatsink", fins))


# ---------------------------------------------------------------- the bought case (outside size official; shape simplified)
def case():
    w, d, wall, r = C["w"], C["d"], C["wall"], 8.0
    base = stack("case_base", w, d, r, [(1.5, Z0), (0.45, Z0 + 0.4), (0.0, Z0 + 1.5), (0.0, ZBASE)], P["case_red"])
    cuts = [stack("c", w, d, r, [(wall, Z0 + 2.0), (wall, ZBASE + 1)], P["case_red"])]
    for f in M.FRONT.values():                           # one opening per front socket (same sizes as before)
        cuts.append(box("c", OX + f["c"] - f["w"] / 2 - 2, -1, ZT - 1.5, f["w"] + 4, 12, f["z1"] + 3, P["case_red"]))
    cuts.append(box("c", w - 8, OY + RIGHT_Y0, ZT - 1, 14, RIGHT_Y1 - RIGHT_Y0, 30, P["case_red"]))   # network + USB end
    cd = M.CARD                                           # slot for the memory card in the left end
    cuts.append(box("c", -1, OY + cd["c"] - cd["w"] / 2 - 2, ZT + cd["z0"] - 2, wall + 3, cd["w"] + 4, 5.0, P["case_red"]))
    by, bz = OY + M.BUTTON["y"], ZT + M.BUTTON["z"]
    cuts.append(lathe("c", (-1, by, bz), (1, 0, 0), [(0, 2.3), (wall + 2, 2.3)], P["case_red"], 16))
    for gx in (16.0, 54.0):                               # air slots in the floor (by eye, from the maker's photo)
        for k in range(5):
            cuts.append(box("c", gx, 21.0 + k * 6.4, Z0 - 1, 26.0, 2.2, 4.0, P["case_red"]))
    cut(base, cuts)
    posts = [lathe("p", (OX + hx, OY + hy, Z0 + 1.8), (0, 0, 1), [(0, M.POST_FOOT_R), (M.POST_FOOT_H, M.POST_R), (ZB - Z0 - 1.8, M.POST_R)], P["case_red"], 20)
             for hx, hy in M.HOLES]
    done(join("case_base", [base] + posts))
    done(lathe("case_base__button", (-0.5, by, bz), (1, 0, 0), [(0, 1.5), (0.5, 2.0), (wall + 1.0, 2.0)], P["lightpipe"], 16))
    feet = [lathe("f", (x, y, 0.0), (0, 0, 1), [(0, 4.4), (0.5, 5.0), (Z0 + 0.25, 5.0)], P["rubber_pale"], 24)
            for x in (14, w - 14) for y in (12, d - 12)]
    done(join("case_base__feet", feet))

    # frame: white ring with a deck, the round fan opening, the slot over the 40-pin header, pillars between the sockets
    frame = stack("case_frame", w, d, r, [(0.0, ZBASE), (0.0, ZFRAME - 0.7), (0.7, ZFRAME)], P["case_white"])
    gx = OX + M.GPIO_C
    cut(frame, [stack("c", w, d, r, [(wall, ZBASE - 1), (wall, ZFRAME - 2.0)], P["case_white"]),
                lathe("c", (FAN_X, FAN_Y, ZFRAME - 3), (0, 0, 1), [(0, 14.6), (6, 14.6)], P["case_white"], 40),
                prism("c", rr(54.0, 7.0, 2.0, gx - 27.0, OY + BH - 7.0, steps=4), ZFRAME - 3, ZFRAME + 2, P["case_white"]),
                box("c", w - 8, OY + RIGHT_Y0, ZBASE - 1, 14, RIGHT_Y1 - RIGHT_Y0, C["frame_h"] - 1.0, P["case_white"])])
    gaps = sorted((p["c"] - p["w"] / 2, p["c"] + p["w"] / 2) for p in M.RIGHT.values())
    pillars = [box("pl", w - wall, OY + (a[1] + b[0]) / 2 - 1.1, ZT - 1, wall, 2.2, ZFRAME - 2.0 - (ZT - 1) + 0.2, P["case_white"])
               for a, b in zip(gaps[:-1], gaps[1:])]
    done(join("case_frame", [frame] + pillars))

    # fan in the frame: black housing with three struts, hub, seven blades (blade shape by eye)
    house = cut(prism("fh", rr(31.0, 31.0, 3.5, FAN_X - 15.5, FAN_Y - 15.5, steps=4), ZBASE - 2.0, ZBASE + 3.8, P["fan_frame"]),
                [lathe("c", (FAN_X, FAN_Y, ZBASE - 3), (0, 0, 1), [(0, 14.0), (8, 14.0)], P["fan_frame"], 40)])
    struts = []
    for k in range(3):
        a = 2 * math.pi * k / 3 + 0.5
        ca, sa = math.cos(a), math.sin(a)
        quad = [(FAN_X + ca * 5 - sa * 0.9, FAN_Y + sa * 5 + ca * 0.9), (FAN_X + ca * 5 + sa * 0.9, FAN_Y + sa * 5 - ca * 0.9),
                (FAN_X + ca * 14.3 + sa * 0.9, FAN_Y + sa * 14.3 - ca * 0.9), (FAN_X + ca * 14.3 - sa * 0.9, FAN_Y + sa * 14.3 + ca * 0.9)]
        struts.append(prism("s", quad, ZBASE - 2.0, ZBASE - 1.2, P["fan_frame"]))
    done(join("fan", [house] + struts))
    done(lathe("fan__hub", (FAN_X, FAN_Y, ZBASE - 1.6), (0, 0, 1), [(0, 0), (0, 6.2), (4.7, 6.2), (5.1, 5.8), (5.1, 0)], P["fan_hub"], 28))
    done(lathe("fan__sticker", (FAN_X, FAN_Y, ZBASE + 3.5), (0, 0, 1), [(0, 4.4), (0.05, 4.4)], P["sticker"], 24))
    blades = []
    for k in range(7):
        a0, rings = 2 * math.pi * k / 7, []
        for t in (0.0, 0.34, 0.67, 1.0):
            rad, th, half = 6.0 + t * 7.5, a0 + 0.55 * t, 0.42 - 0.10 * t
            lead = (FAN_X + rad * math.cos(th + half), FAN_Y + rad * math.sin(th + half))
            trail = (FAN_X + rad * math.cos(th - half), FAN_Y + rad * math.sin(th - half))
            zl, zt = ZBASE + 2.9, ZBASE - 0.6
            rings.append([(*lead, zl), (*trail, zt), (*trail, zt - 0.5), (*lead, zl - 0.5)])
        blades.append(loft("b", rings, P["fan_blade"]))
    done(join("fan__blades", blades), sharp=50)

    # lid: a soft-edged white plate standing on a narrower neck, so a shadow line runs round it (air gets in there)
    neck = stack("n", w, d, r, [(2.6, ZFRAME - 0.1), (2.6, ZFRAME + 1.3)], P["case_white"])
    top = stack("t", w, d, r, [(1.1, ZFRAME + 1.2), (0.25, ZFRAME + 1.7), (0.0, ZFRAME + 2.5), (0.0, C["h"] - 1.5),
                               (0.45, C["h"] - 0.5), (1.7, C["h"])], P["case_white"])
    done(join("case_lid", [neck, top]))


# ---------------------------------------------------------------- shelf, UMIK-1 on its tripod, cables (all by eye)
def room():
    u = M.UMIK
    x, y = C["w"] + 160, C["d"] / 2 + 20                  # where the mic stands (as before)
    z = M.SHELF_Z + 8.0                                   # top of the shelf board
    x0, y0 = x - M.SHELF_W / 2, y - M.SHELF_D / 2
    # a small bookshelf, as tall and wide as the old plain shelf (make_parts.py SHELF_*): top, two sides, a back,
    # a middle and a bottom board, and a few books. All of it is drawn by eye.
    W, D, H = M.SHELF_W, M.SHELF_D, M.SHELF_Z
    top = box("shelf", x0, y0, H, W, D, 8.0, P["wood"], 0.8, 2)
    box_uv(top, 0, x0, y0, H, W, D, 8.0)
    done(top)
    sides = join("shelf__side", [box("s", sx, y0 + 1.5, 0.0, 6.0, D - 3.0, H, P["wood"], 0.6, 2) for sx in (x0 + 2.0, x0 + W - 8.0)])
    box_uv(sides, 2, x0, y0, 0.0, W, D, H, shift=0.37)
    done(sides)
    mid_z, low_z, in_x, in_w = 74.0, 10.0, x0 + 8.0, W - 16.0
    boards = join("shelf__board", [box("b", in_x, y0 + 4.0, mid_z, in_w, D - 9.0, 6.0, P["wood"], 0.4),
                                   box("b", in_x, y0 + 4.0, low_z, in_w, D - 9.0, 6.0, P["wood"], 0.4),
                                   box("b", in_x, y0 + 7.0, 0.0, in_w, 3.0, low_z, P["wood"])])       # the plinth under the bottom board
    box_uv(boards, 0, x0, y0, 0.0, W, D, H, shift=0.61)
    done(boards)
    back = box("shelf__back", x0 + 5.0, y0 + D - 5.0, 3.0, W - 10.0, 3.0, H - 3.0, P["wood"])
    box_uv(back, 2, x0, y0, 0.0, W, D, H, shift=0.18)
    done(back)
    books = {k: [] for k in range(5)}
    fy = y0 + 11.0                                           # the spines stand a little back from the front edge

    def row(z, start, way, sizes):                           # books standing side by side: (thickness, height, depth, colour)
        cx = start
        for t, h, dp, col in sizes:
            books[col].append(box("bk", cx if way > 0 else cx - t, fy, z, t, dp, h, P[f"book{col}"], 0.5))
            cx += way * (t + 0.5)
        return cx

    end = row(low_z + 6.0, in_x + 3.0, 1, [(14, 50, 84, 0), (10, 46, 80, 1), (16, 52, 86, 2), (9, 42, 78, 3), (12, 48, 82, 4), (15, 51, 84, 1), (11, 44, 80, 0), (13, 49, 83, 2)])
    lean, lt, lh = math.radians(12), 11.0, 47.0              # one book leaning on the end of the row
    lx, lz = end + 49 * math.tan(lean), low_z + 6.0
    up, across = (-math.sin(lean), math.cos(lean)), (math.cos(lean), math.sin(lean))
    quad = [(lx, lz), (lx + across[0] * lt, lz + across[1] * lt), (lx + across[0] * lt + up[0] * lh, lz + across[1] * lt + up[1] * lh), (lx + up[0] * lh, lz + up[1] * lh)]
    books[3].append(prism("bk", quad, fy, fy + 80.0, P["book3"], "y"))
    row(mid_z + 6.0, in_x + in_w - 3.0, -1, [(13, 54, 84, 3), (10, 48, 80, 0), (15, 56, 86, 4), (9, 45, 78, 2), (12, 50, 82, 1)])
    for i, (bw, bh, col) in enumerate([(64, 12, 2), (60, 10, 1), (55, 9, 4)]):   # three books lying in a pile
        books[col].append(box("bk", in_x + 6.0 + i * 2.0, fy + i * 1.5, mid_z + 6.0 + sum(h for _, h, _ in [(64, 12, 2), (60, 10, 1), (55, 9, 4)][:i]), bw, 84.0 - i * 3, bh, P[f"book{col}"], 0.5))
    for col, obs in books.items():
        done(join(f"shelf__books_{col}", obs))

    # mini tripod: three legs with rubber tips, a collar, a tilting clip with its thumb screw
    hub = Vector((x, y, z + 34.0))
    feet = [Vector((x + 40 * math.cos(a), y + 40 * math.sin(a), z + 2.4)) for a in (2 * math.pi * k / 3 + math.pi / 2 for k in range(3))]
    done(join("mic__leg", [rod("l", hub, f, 2.2, P["stand"], 12) for f in feet]))
    done(join("mic__foot", [lathe("f", f + (hub - f).normalized() * 6.0, f - hub, [(0, 2.9), (5.0, 2.9), (7.6, 1.6), (8.2, 0)], P["rubber"], 12) for f in feet]))
    pivot = Vector((x, y, z + 62.0))
    knuckle = pivot - Vector((0, 0, 14.0))
    done(join("mic__post", [lathe("c", hub - Vector((0, 0, 4)), (0, 0, 1), [(0, 0), (0, 6.2), (0.8, 7.0), (9.2, 7.0), (10.0, 6.2), (10.0, 0)], P["stand"], 24),
                            rod("r", hub + Vector((0, 0, 5)), knuckle, 4.0, P["stand"], 16)]))
    done(join("mic__knuckle", [rod("k", knuckle - Vector((0, 6.5, 0)), knuckle + Vector((0, 6.5, 0)), 6.0, P["clip"], 20, 0.8),
                               rod("n", knuckle, pivot, 4.6, P["clip"], 16)]))
    done(rod("mic__screw", knuckle + Vector((0, 6.5, 0)), knuckle + Vector((0, 11.5, 0)), 4.6, P["stand"], 10, 0.6), sharp=20)

    t = math.radians(u["tilt"])
    axis = Vector((-math.cos(t), 0.0, math.sin(t)))       # the way the mic points: up and to the left
    rear, front = -u["body_l"] * 0.75, u["body_l"] * 0.25
    neck = front + u["cone_l"]
    foam0 = neck + u["neck_l"] - 12
    foam1 = foam0 + u["foam_l"]
    R, RN, RF = u["body_r"], u["neck_r"], u["foam_r"]

    def at(s):
        return pivot + axis * s

    done(lathe("mic", pivot, axis, [(rear, 0), (rear, R - 1.2), (rear + 1.2, R), (rear + 3.0, R), (rear + 3.0, R - 0.35), (rear + 3.6, R - 0.35),
                                    (rear + 3.6, R), (front, R)], P["mic_body"], 32))
    ring = [(rear + 5.0, R)]
    for k in range(5):                                    # the silver band with its fine grooves
        s = rear + 5.0 + k * 2.2
        ring += [(s, R + 0.45), (s + 1.6, R + 0.45), (s + 1.6, R + 0.1), (s + 2.2, R + 0.1)]
    ring += [(rear + 16.0, R)]
    done(lathe("mic__ring", pivot, axis, ring, P["mic_ring"], 32))
    done(lathe("mic__cone", pivot, axis, [(front, R), (front + 2.0, R - 0.3), (neck - 1.0, RN + 0.5), (neck, RN)], P["mic_body"], 32), sharp=50)
    done(lathe("mic__tube", pivot, axis, [(neck, RN), (foam0 + 2.0, RN)], P["mic_tube"], 24))
    foam = [(foam0, RN + 0.3), (foam0 + 1.0, RF - 1.2), (foam0 + 3.0, RF)]
    foam += [(foam1 - RF + RF * math.sin(a), RF * math.cos(a)) for a in (math.radians(k * 15) for k in range(6))] + [(foam1, 0)]
    done(lathe("mic__foam", pivot, axis, foam, P["foam"], 24), sharp=60)
    done(lathe("mic__clip", pivot, axis, [(-14, R + 0.2), (-13, R + 2.5), (9, R + 2.5), (10, R + 0.2)], P["clip"], 32))
    done(lathe("mic__light", at(rear) + Vector((0, 6.4, 0)), -axis, [(0, 1.2), (0.25, 1.2)], P["mic_light"], 12))

    # the mic's USB cable: plug in the mic, down onto the shelf, over the front edge, down to the floor, up into the Pi
    done(lathe("cable__micplug", at(rear), -axis, [(0, 4.2), (1.0, 4.6), (13.0, 4.6), (14.0, 4.0), (22.0, 2.4), (24.5, 2.0)], P["plug"], 20))
    usb = Vector((OX + BW + M.RIGHT["usb_stack_upper"]["out"], OY + M.RIGHT["usb_stack_upper"]["c"], ZT + 12.0))   # socket mouth (as before)
    zs = z + 2.1
    end = at(rear - 24.0)
    path = [end, end - axis * 5.0 + Vector((0, -0.6, -1.5)), (316, 51, zs + 0.3), (322, 41, zs), (319, 27, zs), (305, 12, zs), (280, 4, zs), (245, 1, zs),
            (219, -1, zs), (208.5, -3.2, zs + 0.2), (204.6, -6.6, z - 0.4), (203.4, -8.8, z - 8.0), (203, -9.3, 120), (203, -9.4, 60),
            (202.6, -9.7, 24), (200, -11.5, 9), (193, -14.5, 2.9), (180, -15.5, 2.1), (168, -12.5, 2.1), (160.5, 2, 2.1), (158.5, 22, 2.1),
            (156.5, 38, 2.9), (152, 47.5, 6.8), (144, 52.6, 13.6), (134, 54.0, 19.0), (127.5, usb.y, usb.z), (usb.x + 27.0, usb.y, usb.z)]
    done(tube("cable__usb", path, 2.0, P["cable"]))
    mould = box("m", usb.x + 3.0, usb.y - 8.0, usb.z - 4.0, 19.0, 16.0, 8.0, P["plug"], 1.4, 2)
    relief = lathe("r", (usb.x + 22.0, usb.y, usb.z), (1, 0, 0), [(0, 3.4), (5.5, 2.3)], P["plug"], 16)
    done(join("cable__plug", [mould, relief]))
    done(box("cable__plug_metal", usb.x - 10.5, usb.y - 6.0, usb.z - 2.25, 13.6, 12.0, 4.5, P["shell"], 0.3))

    # power cable: USB-C plug in the front socket, then down to the floor and away to the left (drawn short)
    f = M.FRONT["usb-c_power"]
    px, pz = OX + f["c"], ZT + (max(f["z0"], 0.0) + f["z1"]) / 2
    done(prism("cable__powerplug_metal", rr(7.9, 2.3, 1.1, px - 3.95, pz - 1.15, steps=4), -0.6, OY - f["out"] + 5.2, P["shell"], "y"))
    pm = prism("pm", rr(11.5, 6.5, 2.2, px - 5.75, pz - 3.25, steps=4), -21.5, -0.5, P["plug"], "y")
    pr = lathe("pr", (px, -21.5, pz), (0, -1, 0), [(0, 3.0), (7.5, 2.4)], P["plug"], 16)
    done(join("cable__powerplug", [pm, pr]))
    power = [(px, -28.5, pz), (px - 0.1, -35, pz - 0.5), (px - 0.8, -42.5, pz - 2.8), (px - 2.9, -48.5, 4.3), (11, -53.5, 2.5), (0, -56, 2.3),
             (-18, -55, 2.3), (-38, -51, 2.3), (-56, -50, 2.3), (-72, -51.5, 2.3)]
    done(tube("cable__power", power, 2.2, P["cable_power"]))
    return dict(mic=at(0) + Vector((0, 0, R + 4)), shelf=Vector((x, y0, z)), cable=Vector((203, -9.4, M.SHELF_Z)), sd_end=None)


# ---------------------------------------------------------------- names, accuracy tags, label points
# acc: 'official' = from the official drawing, 'simplified' = right size but simplified shape, 'eye' = drawn by eye
INFO = [("board__soc", "Main chip", "official"), ("board__chip_ram", "Memory chip", "official"), ("board__chip_rp1", "Chip that runs the sockets", "official"),
        ("board__wifi", "Wi-Fi and Bluetooth", "official"), ("board__pmic", "Power chip", "official"), ("board__led", "Status light", "official"),
        ("board__ring", "Mounting hole", "official"), ("board", "Raspberry Pi 5 board", "official"), ("gpio", "40-pin header", "official"),
        ("usb-c_power", "USB-C power socket", "official"), ("micro-hdmi", "Micro-HDMI socket", "official"), ("ethernet", "Network socket", "official"),
        ("usb_stack", "USB sockets", "official"), ("mipi", "Camera and display connector", "official"), ("poe", "Power-over-network pins", "official"),
        ("fan_plug", "Fan socket (marked FAN)", "official"), ("power_button", "Power button", "official"), ("pcie", "Connector for add-on boards", "official"),
        ("sdcard", "microSD card", "official"), ("heatsink", "Heatsink", "simplified"), ("case_base__feet", "Rubber feet", "simplified"),
        ("case_base__button", "Case button", "simplified"), ("case_base", "Case base", "simplified"), ("case_frame", "Case frame", "simplified"),
        ("case_lid", "Case lid", "simplified"), ("fan", "Fan", "simplified"), ("shelf__books", "Books", "eye"), ("shelf", "High shelf (a small bookshelf)", "eye"), ("mic__foam", "Wind screen", "eye"),
        ("mic__clip", "Mic clip", "eye"), ("mic__knuckle", "Mic clip", "eye"), ("mic__screw", "Clip screw", "eye"), ("mic__post", "Mini tripod", "eye"),
        ("mic__leg", "Mini tripod", "eye"), ("mic__foot", "Mini tripod", "eye"), ("mic", "UMIK-1 microphone", "eye"),
        ("cable__power", "Power cable", "eye"), ("cable", "Mic's USB cable", "eye")]


def label_point(key, pos, ride):
    """Where a label's dot sits. 'ride' names the mesh it moves with (exploded view, step animations)."""
    ob = bpy.data.objects.new("LBL_" + key, None)
    SCENE.collection.objects.link(ob)
    ob.location = pos
    ob["kind"], ob["key"], ob["ride"] = "label", key, ride


def build():
    pi()
    case()
    pts = room()
    soc = M.CHIPS[0]
    f = M.FRONT["usb-c_power"]
    label_point("board", (OX + 0.12 * BW, OY + BH / 2, ZT), "board")
    label_point("heatsink", (OX + soc[1] + soc[3] / 2, OY + soc[2] + soc[4] / 2, ZT + 1.2 + M.HEATSINK[2]), "heatsink")
    label_point("fan", (FAN_X, FAN_Y, ZBASE + 3.6), "fan__hub")
    label_point("usb-c_power", (OX + f["c"], OY - f["out"], ZT + f["z1"]), "usb-c_power")
    label_point("sdcard", (OX - M.CARD["out"], OY + M.CARD["c"], ZT + M.CARD["z0"]), "sdcard")
    label_point("case_base", (0.8 * C["w"], 0.0, (Z0 + ZBASE) / 2), "case_base")
    label_point("case_lid", (C["w"] / 2, C["d"] / 2, C["h"]), "case_lid")
    label_point("mic", pts["mic"], "mic")
    label_point("shelf", pts["shelf"], "shelf")
    label_point("cable", pts["cable"], "cable__usb")

    colours, tris = {}, 0
    for ob in PARTS:
        hit = next(((n, a) for pre, n, a in INFO if ob.name.startswith(pre)), None)
        assert hit, f"no name for {ob.name}"
        ob["part"], ob["acc"] = hit
        colours[ob.name] = HEX[id(ob)]
        ob.data.calc_loop_triangles()
        tris += len(ob.data.loop_triangles)
    stray = [o.name for o in SCENE.objects if o.type == "MESH" and o not in PARTS]
    assert not stray, f"helper meshes left in the scene: {stray}"
    path = os.path.join(OUT, "noise-logger.glb")
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=False, export_apply=True, export_yup=False,
                              export_extras=True, export_cameras=False, export_lights=False, export_materials="EXPORT",
                              export_animations=False, export_image_format="AUTO", export_tangents=False)
    before, after = glb_pack.pack(path)
    os.remove(WOOD_FILE)
    with open(os.path.join(OUT, "colors.json"), "w", encoding="utf-8") as fh:
        json.dump(colours, fh, indent=0)
    print(f"MODEL {path}: {len(PARTS)} meshes, {tris} triangles, {after / 1024:.0f} KB ({before / 1024:.0f} KB before packing)")
    assert after < 500 * 1024, "the model file must stay under 500 KB"


build()
