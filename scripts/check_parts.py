"""Measures the exported print files (STL) and compares them with the official Raspberry Pi 5 drawing (exit 1 on any miss).
Everything is measured on the files themselves; the only numbers typed in here come from the drawing (board corner = 0, 0).
Checks: sizes, solid, prints without supports as the file lies, posts and nut pockets, the board drops straight in,
room round every socket, the power plug, button, status light, memory card, lid room, and the mic holder.
Run:  python scripts/check_parts.py [folder with the STL files]"""
import sys
from pathlib import Path

import numpy as np
import trimesh
from shapely.geometry import LineString, Point, Polygon, box as rect
from shapely.ops import unary_union

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
FILES = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "print"
TOL = 0.5
EXPECT = {"case_base": (101.0, 71.0, 26.4), "case_lid": (101.0, 71.0, 2.0), "mic_cradle": (60.0, 100.0, 51.0)}  # as the files lie on the bed

# ---- official Raspberry Pi 5 drawing, measured from its lines (mm) ----
BOARD_W, BOARD_H, BOARD_T = 85.0, 56.0, 1.41
USB_TOP, COOLER_TOP = 16.44, 13.70                           # above the board's top face
# name: edge, from, to (along the edge), bottom, top (above the board's top face), sticks out past the edge
SOCKETS = {
    "USB-C power": ("front", 6.81, 15.56, 0.0, 3.2, 1.31),
    "micro-HDMI 0": ("front", 22.19, 29.39, -0.25, 3.4, 1.66),
    "micro-HDMI 1": ("front", 35.60, 42.79, -0.25, 3.4, 1.66),
    "Ethernet": ("right", 2.22, 18.20, 0.0, 13.9, 2.98),
    "USB lower": ("right", 21.77, 36.37, 0.0, 16.44, 3.30),
    "USB upper": ("right", 39.72, 54.29, 0.0, 16.44, 3.30),
}
BUTTON = (18.4, 1.70, 0.46)                                  # along the left edge, height above the board, sticks out
LIGHT = (13.3, 0.50)
CARD = (23.11, 33.09, -3.00, -2.01, 1.73)                    # along the left edge, bottom, top, sticks out
SPARE = 1.5
fails = 0


def ok(cond, msg):
    global fails
    print(("PASS " if cond else "FAIL ") + msg)
    fails += 0 if cond else 1


def even_odd(loops):
    polys = [Polygon(p) for p in loops if len(p) >= 4]
    polys = [p if p.is_valid else p.buffer(0) for p in polys]
    g = Polygon()
    for p in sorted(polys, key=lambda q: -q.area):
        g = g.symmetric_difference(p)
    return g


def cut(mesh, axis, value):
    """Solid material in a flat cut. axis 2: (x, y); axis 0: (y, z); axis 1: (x, z)."""
    o, n = [0, 0, 0], [0, 0, 0]
    o[axis], n[axis] = value, 1
    s = mesh.section(plane_origin=o, plane_normal=n)
    keep = [i for i in range(3) if i != axis]
    return even_odd([np.asarray(l)[:, keep] for l in s.discrete]) if s is not None else Polygon()


def pieces(g):
    return [p for p in (g.geoms if hasattr(g, "geoms") else [g]) if not p.is_empty and p.area > 1e-6]


def runs(g, a, b, axis):
    """Solid stretches along the straight line a-b, as (from, to) on the given axis (0 or 1), in order."""
    s = g.intersection(LineString([a, b]))
    return sorted(tuple(sorted(c[axis] for c in (p.coords[0], p.coords[-1]))) for p in (s.geoms if hasattr(s, "geoms") else [s]) if not p.is_empty and p.length > 0.01)


def block(x0, x1, y0, y1, z0, z1):
    m = trimesh.creation.box(extents=(x1 - x0, y1 - y0, z1 - z0))
    m.apply_translation(((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2))
    return m


def clash(mesh, blk):
    """Volume (mm3) that the block and the printed part would share."""
    r = trimesh.boolean.intersection([mesh, blk], engine="manifold")
    return 0.0 if r.is_empty else float(abs(r.volume))


def prints_without_supports(mesh, layer=0.2, max_bridge=20.0):
    """Goes up layer by layer. Bad = a piece starting in mid-air, or an overhang that is not a short bridge held on both sides."""
    lo, hi = float(mesh.bounds[0][2]), float(mesh.bounds[1][2])
    prev, bad, longest = None, [], 0.0
    first = cut(mesh, 2, lo + layer / 2)
    for z in np.arange(lo + layer / 2, hi, layer):
        g = cut(mesh, 2, float(z))
        if prev is not None:
            for p in pieces(g):
                if not p.intersects(prev):
                    bad.append(f"piece in mid-air at z {z - lo:.1f}")
            over = g.difference(prev.buffer(layer * 1.05))     # up to about 45 degrees is fine
            for p in pieces(over.buffer(-0.05).buffer(0.05)):
                edge = p.exterior
                inside = max([prev.distance(p.representative_point())] + [prev.distance(edge.interpolate(t, normalized=True)) for t in np.linspace(0, 1, 60)])
                if inside <= 0.6:
                    continue                                   # a lip under one and a half line widths
                touch = p.buffer(0.3).intersection(prev)
                held = touch.convex_hull.buffer(0.5).covers(p)
                minx, miny, maxx, maxy = p.bounds
                span = min(2 * inside, max(maxx - minx, maxy - miny)) if held else inside
                longest = max(longest, span)
                if not held:
                    bad.append(f"overhang of {inside:.1f} mm not held on both sides at z {z - lo:.1f}")
                elif span > max_bridge:
                    bad.append(f"bridge of {span:.1f} mm at z {z - lo:.1f}")
        prev = g
    foot = unary_union([cut(mesh, 2, float(z)) for z in np.linspace(lo + 0.1, hi - 0.1, 12)])
    return bad, longest, first.area / foot.area


# ---------------- 1. sizes, solid, printable as the file lies ----------------
M = {n: trimesh.load(FILES / f"{n}.stl") for n in EXPECT}
for name, exp in EXPECT.items():
    m = M[name]
    size = m.bounds[1] - m.bounds[0]
    ok(all(abs(a - b) <= TOL for a, b in zip(size, exp)), f"{name}: size {np.round(size, 2).tolist()} vs {list(exp)} (±{TOL})")
    ok(m.is_watertight and len(m.split(only_watertight=False)) == 1, f"{name}: one solid, watertight piece")
    bad, longest, on_bed = prints_without_supports(m)
    ok(not bad, f"{name}: prints without supports as the file lies (longest bridge {longest:.1f} mm){'' if not bad else ' | ' + '; '.join(bad[:3]) + f' ({len(bad)} in all)'}")
    ok(on_bed >= 0.80 or name == "mic_cradle", f"{name}: {on_bed * 100:.0f}% of its outline sits on the bed")

# ---------------- 2. board screws, posts, nut pockets ----------------
base, lid, cradle = M["case_base"], M["case_lid"], M["mic_cradle"]
holes = []
for loop in base.section(plane_origin=(0, 0, 5.0), plane_normal=(0, 0, 1)).discrete:
    pts = np.asarray(loop)[:, :2]
    d = pts.max(axis=0) - pts.min(axis=0)
    if 2.4 < d.mean() < 3.0 and abs(d[0] - d[1]) < 0.3:
        holes.append((pts.max(axis=0) + pts.min(axis=0)) / 2)
ok(len(holes) == 4, f"found {len(holes)} board-screw holes of about Ø2.7 (need 4)")
if len(holes) != 4:
    print("\nSTOPPED: without the 4 holes the board cannot be placed")
    sys.exit(1)
h = np.array(holes)
dx, dy = np.ptp(h[:, 0]), np.ptp(h[:, 1])
ok(abs(dx - 58.0) <= 0.1 and abs(dy - 49.0) <= 0.1, f"hole spacing {dx:.2f} x {dy:.2f} mm vs official 58 x 49")
ox, oy = float(h[:, 0].min() - 3.5), float(h[:, 1].min() - 3.5)          # the board's corner inside the case
low, top_z = float(base.bounds[0][2]), float(base.bounds[1][2])
post_top = float(max(p[2] for p in base.vertices if min(np.hypot(*(p[:2] - q)) for q in h) < 3.2 and p[2] < 15))
floor = runs(cut(base, 0, ox + 30.0), (oy + 46, -20), (oy + 46, 60), 1)[0][1]      # top of the floor on a clear spot
zt = post_top + BOARD_T                                                  # top face of the board
slab = cut(base, 2, floor + 0.5)
ax, ay = runs(slab, (-60, oy + 46), (200, oy + 46), 0), runs(slab, (ox + 30, -60), (ox + 30, 200), 1)
(lw0, lw1), (rw0, rw1), (fw0, fw1), (bw0, bw1) = ax[0], ax[-1], ay[0], ay[-1]      # left, right, front, back wall faces
for q in h:
    ring = cut(base, 2, floor + 0.05).intersection(Point(q).buffer(3.05, 64))
    under = cut(base, 2, floor - 0.1).intersection(Point(q).buffer(4.0, 64))
    full = Point(q).buffer(2.95, 64).difference(Point(q).buffer(1.40, 64))
    empty = [z for z in np.arange(low + 0.05, floor, 0.05) if not cut(base, 2, float(z)).contains(Point(q[0] + 2.0, q[1] + 1.0))]
    depth = (max(empty) - low + 0.025) if empty else 0.0
    ys = runs(cut(base, 2, low + 1.0), (q[0], q[1] - 6), (q[0], q[1] + 6), 1)
    gap = min((b[0] - a[1] for a, b in zip(ys, ys[1:])), default=0.0)
    ok(ring.buffer(0.02).covers(full) and len(pieces(ring)) == 1 and under.buffer(0.02).covers(full),
       f"post at ({q[0]:.1f}, {q[1]:.1f}) stands on one full solid ring ({ring.area:.1f} mm2, need 22)")
    ok(2.0 <= depth <= floor - low - 0.75 and 5.2 <= gap <= 5.5, f"   nut pocket {depth:.2f} deep, {gap:.2f} flat to flat; {floor - low - depth:.2f} mm of floor left above it")
tip = zt - 8.0 - low
ok(0.0 <= tip <= 1.0, f"an 8 mm board screw ends {tip:.2f} mm inside the underside, so it fills the nut and does not stick out")

# ---------------- 3. the board drops straight in ----------------
top = top_z + 5
drops = {"board": block(ox - 0.3, ox + BOARD_W + 0.3, oy - 0.3, oy + BOARD_H + 0.3, post_top + 0.05, top)}
for n, (edge, a, b, z0, z1, out) in SOCKETS.items():
    if edge == "front":
        drops[n] = block(ox + a - 0.3, ox + b + 0.3, oy - out - 0.3, oy + 5, zt + z0, top)
    else:
        drops[n] = block(ox + BOARD_W - 10, ox + BOARD_W + out, oy + a - 0.3, oy + b + 0.3, zt + z0, top)
drops["memory card"] = block(ox - CARD[4] - 0.3, ox + 5, oy + CARD[0] - 0.3, oy + CARD[1] + 0.3, zt + CARD[2], top)
drops["power button"] = block(ox - BUTTON[2] - 0.3, ox + 3, oy + 17.39, oy + 19.40, zt, top)
for n, b in drops.items():
    c = clash(base, b)
    ok(c < 0.01, f"drops straight in: {n} meets no plastic on the way down (clash {c:.2f} mm3)")

# ---------------- 4. room round every socket ----------------
front = cut(base, 1, (fw0 + fw1) / 2)
openings = [Polygon(i).bounds for p in pieces(front) for i in p.interiors]
for n, (edge, a, b, z0, z1, out) in SOCKETS.items():
    if edge == "front":
        mid = (ox + (a + b) / 2, zt + (z0 + z1) / 2)
        w = [o for o in openings if o[0] < mid[0] < o[2] and o[1] < mid[1] < o[3]]
        if not w:
            ok(False, f"{n}: no window found in the front wall")
            continue
        o = w[0]
        s = (ox + a - o[0], o[2] - (ox + b), zt + z0 - o[1], o[3] - (zt + z1))
        ok(min(s) >= SPARE - 0.01, f"{n}: window {o[2] - o[0]:.2f} x {o[3] - o[1]:.2f} mm, spare left {s[0]:.2f} right {s[1]:.2f} below {s[2]:.2f} above {s[3]:.2f} (need {SPARE})")
        if n == "USB-C power":
            ok(abs((o[0] + o[2]) / 2 - mid[0]) <= 0.1 and abs((o[1] + o[3]) / 2 - mid[1]) <= 0.1 and o[2] - o[0] >= 12.9 and o[3] - o[1] >= 7.4,
               "   power window is at least 13 x 7.5 mm and centred on the socket")
            plug = block(mid[0] - 6.4, mid[0] + 6.4, -20, oy - out, mid[1] - 3.5, mid[1] + 3.5)
            ok(clash(base, plug) < 0.01, "   a 12.8 x 7.0 mm plug body reaches the socket without touching plastic")
    else:
        c = clash(base, block(ox + BOARD_W, rw1 + 5, oy + a - SPARE + 0.01, oy + b + SPARE - 0.01, zt + z0 - SPARE + 0.01, top))
        ok(c < 0.01, f"{n}: {SPARE} mm clear on both sides and below, open to the top (clash {c:.2f} mm3)")
        ok(-0.6 <= rw1 - (ox + BOARD_W + out) <= 0.5, f"   its mouth is {rw1 - (ox + BOARD_W + out):.2f} mm inside the outside face (plugs seat fully)")
gaps = (ox - lw1, oy - fw1, rw0 - ox - BOARD_W, bw0 - oy - BOARD_H)
ok(gaps[0] >= 2.99 and gaps[1] >= 1.99 and gaps[2] >= 0.99 and gaps[3] >= 0.99, "gaps round the board: left %.2f front %.2f right %.2f back %.2f (need 3, 2, 1, 1)" % gaps)

# ---------------- 5. left wall: button, light, memory card ----------------
left = cut(base, 0, (lw0 + lw1) / 2)
left_holes = [Polygon(i) for p in pieces(left) for i in p.interiors]
for what, along, up, dia in (("power button", BUTTON[0], BUTTON[1], 5.0), ("status light", LIGHT[0], LIGHT[1], 2.5)):
    near = [p for p in left_holes if p.contains(Point(oy + along, zt + up))]
    if not near:
        ok(False, f"{what}: no hole over it")
        continue
    c, b = near[0].centroid, near[0].bounds
    ok(np.hypot(c.x - oy - along, c.y - zt - up) <= 0.2 and b[2] - b[0] >= dia, f"{what}: hole {b[2] - b[0]:.2f} mm across, centred {c.x - oy:.2f} along and {c.y - zt:.2f} above the board (drawing {along}, {up})")
card_out = block(-30, ox + 1, oy + CARD[0] - SPARE + 0.02, oy + CARD[1] + SPARE - 0.02, zt + CARD[2] - SPARE, zt + CARD[3] + SPARE - 0.02)
ok(clash(base, card_out) < 0.01, f"memory card slides straight out with {SPARE} mm spare")
finger = block(ox - 12, ox + 4.5, oy + 22, oy + 38, -10, zt + CARD[2])
ok(clash(base, finger) < 0.01, "memory card: a 16 mm wide finger space is open from below and from the side")

# ---------------- 6. no thin strips in the walls; room under the lid ----------------
for label, g in (("front wall", front), ("left wall", left), ("right wall", cut(base, 0, (rw0 + rw1) / 2)), ("back wall", cut(base, 1, (bw0 + bw1) / 2))):
    thin = g.difference(g.buffer(-0.49).buffer(0.52))
    worst = [p for p in pieces(thin) if p.area > 0.3]
    ok(not worst, f"{label}: no strip thinner than 1 mm ({len(worst)} found)")
ok(top_z - zt - USB_TOP >= SPARE, f"lid clears the USB sockets by {top_z - zt - USB_TOP:.2f} mm and the cooler by {top_z - zt - COOLER_TOP:.2f} mm")
pilots = [Polygon(i) for p in pieces(cut(base, 2, top_z - 1)) for i in p.interiors if Polygon(i).area < 8]
lids = [Polygon(i) for p in pieces(cut(lid, 2, 1.0)) for i in p.interiors if Polygon(i).area < 8]
ok(len(pilots) == 4 and len(lids) == 4 and all(min(a.centroid.distance(b.centroid) for b in lids) < 0.1 for a in pilots), f"the 4 lid holes sit over the 4 corner screw holes ({len(pilots)}, {len(lids)})")

# ---------------- 7. mic holder (lies on its back: x across, y up the wall, z away from the wall) ----------------
b0, b1 = cradle.bounds
back = cut(cradle, 2, float(b0[2]) + 0.2)
bx0, by0, bx1, by1 = back.bounds
ok(by1 - by0 >= 95, f"back plate {bx1 - bx0:.0f} x {by1 - by0:.0f} mm (wall strips are about 93 mm long)")
mx, my = (bx0 + bx1) / 2, (by0 + by1) / 2
strips = rect(mx - 20, my - 47, mx + 20, my + 47)                        # two 19 mm strips side by side
ok(cut(cradle, 2, float(b0[2]) + 1.5).buffer(0.01).covers(strips), "the 40 x 94 mm strip area on the back is solid: no tie runs behind it")
slots = []
for x in (mx - 28.0, mx + 28.0):
    found = [Polygon(i).bounds for p in pieces(cut(cradle, 0, x)) for i in p.interiors]
    slots.append([s for s in found if s[2] - s[0] >= 5.5 and s[3] - s[1] >= 2.5 and s[1] >= float(b0[2]) + 2.99])
ok(len(slots[0]) == 2 and len(slots[1]) == 2, f"2 zip-tie slots in each side wing, all in front of the plate ({len(slots[0])} + {len(slots[1])})")
for s in slots[1]:                                                       # the tie's straight path from wing to wing, behind the mic
    tie = block(mx - 40, mx + 40, s[0] + 0.5, s[0] + 5.3, s[1] + 0.2, s[1] + 1.8)
    ok(clash(cradle, tie) < 0.01, f"   a 4.8 x 1.6 mm tie passes both wings {s[0] - by0:.0f} mm up the holder")
shelf = cut(cradle, 1, by0 + 1.5)
cable = rect(mx - 5, float(b0[2]) + 10, mx + 5, float(b1[2]) + 1)
ok(shelf.area > 50 and shelf.intersection(cable).area < 0.01, "cable slot: 10 mm wide and open at the front, so the fixed cable drops in (no hole to thread)")
print(f"\n{'ALL PASS' if fails == 0 else str(fails) + ' FAILED'}")
sys.exit(1 if fails else 0)
