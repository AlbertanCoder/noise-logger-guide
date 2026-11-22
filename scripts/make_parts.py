"""Builds the 3D model for the web page (GLB), and the older printable case (STL, kept but not used in the build), from ONE table of numbers.
Board numbers: official Raspberry Pi 5 + Active Cooler mechanical drawings, measured from their lines (board corner = 0, 0).
Numbers marked PROVISIONAL are not in any drawing: measure the real part before printing.
Run:  python scripts/make_parts.py      (needs: trimesh, manifold3d, numpy)"""
import json
from pathlib import Path

import numpy as np
import trimesh

ROOT = Path(__file__).resolve().parent.parent
OUT_PRINT, OUT_MODEL = ROOT / "print", ROOT / "models"

# ---------------- numbers (mm) ----------------
BOARD = dict(w=85.0, h=56.0, t=1.41)                   # 85 x 56 READ; thickness 1.41 measured on the side view
HOLES = [(3.5, 3.5), (61.5, 3.5), (3.5, 52.5), (61.5, 52.5)]  # READ: 3.5 in, 58 x 49 apart
HOLE_D = 2.7                                           # READ
WALL, FLOOR, LID_T = 2.4, 3.0, 2.0                     # floor 3.0: the 2.2 mm nut pockets must not cut through
GAP_L, GAP_F, GAP_R, GAP_B = 3.0, 2.0, 1.0, 1.0        # left: card sticks out 1.73; front: sockets stick out 1.66, so they stay out of the wall
STANDOFF_H, HEADROOM = 4.0, 18.0                       # headroom: USB sockets 16.44 + 1.56 spare (cooler 13.7)
POST_R, POST_FOOT_R, POST_FOOT_H = 3.0, 4.0, 2.0       # posts flare to 8 mm where they meet the floor; 6 mm at the board (solder joints are close)
NUT_FLAT, NUT_DEEP = 5.3, 2.2                          # M2.5 nut 5.0 mm across flats + 0.3 play
EAR_R, SCREW_PILOT = 3.6, 2.2                          # lid ears with M2.5 self-tapping pilot holes
INNER_W, INNER_H = GAP_L + BOARD["w"] + GAP_R, GAP_F + BOARD["h"] + GAP_B        # 89.0 x 59.0
OUT_W, OUT_H = INNER_W + 2 * WALL, INNER_H + 2 * WALL                             # 93.8 x 63.8
BX, BY = WALL + GAP_L, WALL + GAP_F                    # board's bottom-left corner inside the case
Z_BOARD = FLOOR + STANDOFF_H                           # underside of the board
Z_TOP = Z_BOARD + BOARD["t"]                           # top of the board
WALL_TOP = Z_TOP + HEADROOM                            # lid sits here
SPARE = 1.5                                            # room round every socket, per side
# sockets: centre along the edge, width, bottom and top above the board, how far it sticks out (all measured on the drawing)
FRONT = {"usb-c_power": dict(c=11.185, w=8.75, z0=0.0, z1=3.2, out=1.31, d=7.5),
         "micro-hdmi_0": dict(c=25.79, w=7.20, z0=-0.25, z1=3.4, out=1.66, d=7.5),
         "micro-hdmi_1": dict(c=39.195, w=7.20, z0=-0.25, z1=3.4, out=1.66, d=7.5)}
RIGHT = {"ethernet": dict(c=10.21, w=15.98, z1=13.9, out=2.98, d=21.0),
         "usb_stack_lower": dict(c=29.07, w=14.60, z1=16.44, out=3.30, d=17.5),   # which stack is USB 3 is UNKNOWN: look at the board
         "usb_stack_upper": dict(c=47.005, w=14.57, z1=16.44, out=3.30, d=17.5)}
POWER_WINDOW = (13.0, 7.5)                             # the plug's plastic body must go in (USB-C allows 12.85 x 7 per plug)
BUTTON = dict(y=18.4, z=1.70, d=5.5, out=0.46)         # the part that sticks out of the left edge; pressed with a pen
LIGHT = dict(y=13.3, z=0.50, d=2.8)                    # status light (does not stick out)
CARD = dict(c=28.10, w=9.98, z0=-3.00, z1=-2.01, out=1.73)  # memory card, under the board, left edge
NOTCH = dict(y0=21.6, y1=38.6, z1=8.0, x1=5.0)         # finger notch for the card: wall and floor, open underneath
GPIO_C = 32.49                                         # header centre from the board corner (the drawing's 29 starts at the screw hole)
COOLER = dict(w=63.5, d=42.5, h=13.7, fan=30.0)        # READ
# bought official Pi 5 case: outside size READ from its product brief (98.5 x 70.3 x 33, "approximate"); the shape is simplified
OCASE = dict(w=98.5, d=70.3, h=33.0, board=(8.2, 7.15), foot=1.0, base_h=20.0, frame_h=6.0, wall=2.0)   # board position measured off the brief's drawing (about 1 mm)
HEATSINK = (12.0, 17.0, 4.0)                           # READ from the same brief
# drawn by eye from the maker's photo: no size is published
UMIK = dict(body_r=10.0, body_l=58.0, cone_l=20.0, neck_r=5.2, neck_l=68.0, foam_r=8.5, foam_l=34.0, tilt=50.0)
SHELF_Z, SHELF_W, SHELF_D = 150.0, 190.0, 120.0        # drawn close together: the real mic stands at least 1 m from the Pi
MIC = dict(d=45.0, l=150.0)                            # FIFINE body: PROVISIONAL until measured (build step 3)
# mic holder: back plate, two saddles, two pairs of tie wings, shelf with an open cable slot
PLATE = dict(w=60.0, h=100.0, t=3.0)                   # wall strips are about 93 mm long
SHELF_T, CABLE_SLOT = 4.0, 12.0
SADDLES, SADDLE_T = (16.0, 76.0), 8.0                  # heights up the plate
WINGS = (36.0, 58.0)                                   # heights of the tie wings; their slots sit in front of the plate, clear of the strips
WING = dict(t=4.0, h=14.0, out=11.0, slot=7.0, slot_h=4.0)


def box(sx, sy, sz, x, y, z):
    m = trimesh.creation.box(extents=(sx, sy, sz))
    m.apply_translation((x + sx / 2, y + sy / 2, z + sz / 2))
    return m


def cyl(r, h, x, y, z, sections=48):
    m = trimesh.creation.cylinder(radius=r, height=h, sections=sections)
    m.apply_translation((x, y, z + h / 2))
    return m


def union(ms):
    return trimesh.boolean.union(ms, engine="manifold")


def diff(a, bs):
    return trimesh.boolean.difference([a] + list(bs), engine="manifold")


def round_hole_x(d, y, z):
    """A round hole through the left wall, centred on (y, z)."""
    m = trimesh.creation.cylinder(radius=d / 2, height=WALL + 2, sections=48)
    m.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, (0, 1, 0)))
    m.apply_translation((WALL / 2, y, z))
    return m


def cutouts():
    cuts = []
    for name, p in FRONT.items():                      # closed windows in the front wall only (never into the posts)
        w, z0, z1 = p["w"] + 2 * SPARE, p["z0"] - SPARE, p["z1"] + SPARE
        if name == "usb-c_power":
            mid = (p["z0"] + p["z1"]) / 2
            w, z0, z1 = POWER_WINDOW[0], mid - POWER_WINDOW[1] / 2, mid + POWER_WINDOW[1] / 2
        cuts.append(box(w, WALL + 1.5, z1 - z0, BX + p["c"] - w / 2, -1.0, Z_TOP + z0))
    # right wall: one window for all three sockets, open to the top, so the board drops straight in
    y0 = min(p["c"] - p["w"] / 2 for p in RIGHT.values()) - SPARE
    y1 = max(p["c"] + p["w"] / 2 for p in RIGHT.values()) + SPARE
    cuts.append(box(WALL + 2, y1 - y0, HEADROOM + SPARE + 5, OUT_W - WALL - 0.5, BY + y0, Z_TOP - SPARE))
    # left wall: button hole, status light hole, and the finger notch for the memory card (open underneath)
    cuts.append(round_hole_x(BUTTON["d"], BY + BUTTON["y"], Z_TOP + BUTTON["z"]))
    cuts.append(round_hole_x(LIGHT["d"], BY + LIGHT["y"], Z_TOP + LIGHT["z"]))
    cuts.append(box(WALL + 1.5, NOTCH["y1"] - NOTCH["y0"], NOTCH["z1"] + 1, -1.0, BY + NOTCH["y0"], -1.0))
    cuts.append(box(BX + NOTCH["x1"] + 1, NOTCH["y1"] - NOTCH["y0"], FLOOR + 1.5, -1.0, BY + NOTCH["y0"], -1.0))
    return cuts


def ears():
    return [(0, 0), (OUT_W, 0), (0, OUT_H), (OUT_W, OUT_H)]


def post(x, y):
    """A 6 mm post that flares to 8 mm where it meets the floor."""
    foot = trimesh.convex.convex_hull(np.vstack([cyl(POST_FOOT_R, 0.01, x, y, FLOOR - 0.02).vertices,
                                                 cyl(POST_R, 0.01, x, y, FLOOR + POST_FOOT_H - 0.01).vertices]))
    return [foot, cyl(POST_R, STANDOFF_H + 0.01, x, y, FLOOR - 0.01)]


def nut_pocket(x, y):
    """Pocket for the nut, from below. Its ceiling closes in two small steps so it prints without supports."""
    hexa = trimesh.creation.cylinder(radius=(NUT_FLAT / 2) / np.cos(np.pi / 6), height=NUT_DEEP + 1, sections=6)
    hexa.apply_translation((x, y, (NUT_DEEP - 1) / 2))
    return [hexa, box(HOLE_D, NUT_FLAT - 0.02, 0.2, x - HOLE_D / 2, y - NUT_FLAT / 2 + 0.01, NUT_DEEP - 0.001),
            box(HOLE_D, HOLE_D, 0.2, x - HOLE_D / 2, y - HOLE_D / 2, NUT_DEEP + 0.198)]


def make_base():
    shell_ = box(OUT_W, OUT_H, WALL_TOP, 0, 0, 0)
    cavity = box(INNER_W, INNER_H, WALL_TOP, WALL, WALL, FLOOR)
    base = diff(shell_, [cavity])
    posts = [m for hx, hy in HOLES for m in post(BX + hx, BY + hy)]
    lugs = [cyl(EAR_R, WALL_TOP, ex, ey, 0) for ex, ey in ears()]
    base = union([base] + posts + lugs)                # no printed feet: the whole floor sits on the print bed
    holes = [cyl(HOLE_D / 2, STANDOFF_H + FLOOR + 3, BX + hx, BY + hy, -1) for hx, hy in HOLES]
    pockets = [m for hx, hy in HOLES for m in nut_pocket(BX + hx, BY + hy)]
    pilots = [cyl(SCREW_PILOT / 2, 12, ex, ey, WALL_TOP - 12 + 0.01) for ex, ey in ears()]
    return diff(base, holes + pockets + pilots + cutouts())


def make_lid():
    plate = union([box(OUT_W, OUT_H, LID_T, 0, 0, 0)] + [cyl(EAR_R, LID_T, ex, ey, 0) for ex, ey in ears()])
    # vent field over the cooler area (fan position INFERRED, so the field is generous): 10 slots 2 x 36
    slots = [box(2.0, 36.0, LID_T + 2, BX + 22 + i * 5.0, BY + 10, -1) for i in range(10)]
    screw = [cyl(1.4, LID_T + 2, ex, ey, -1) for ex, ey in ears()]  # M2.5 clearance
    return diff(plate, slots + screw)


def make_cradle():
    """Upright: z up the wall, back of the plate at y = 0. Every side is straight, so it prints lying on its back with no supports."""
    r_in, r_out = MIC["d"] / 2, MIC["d"] / 2 + 4.0
    mic_y = PLATE["t"] + 3.0 + r_in                    # the mic's back stays 3 mm off the plate: the ties pass there
    parts = [box(PLATE["w"], PLATE["t"], PLATE["h"], -PLATE["w"] / 2, 0, 0)]
    for z in SADDLES:                                  # solid block with a half-round seat
        parts.append(diff(box(2 * r_out, mic_y, SADDLE_T, -r_out, 0, z - SADDLE_T / 2),
                          [cyl(r_in, SADDLE_T + 2, 0, mic_y, z - SADDLE_T / 2 - 1, 96)]))
    parts.append(box(2 * r_out, mic_y + r_in, SHELF_T, -r_out, 0, 0))
    for z in WINGS:
        for x in (-PLATE["w"] / 2, PLATE["w"] / 2 - WING["t"]):
            parts.append(box(WING["t"], PLATE["t"] + WING["out"], WING["h"], x, 0, z - WING["h"] / 2))
    cuts = [box(CABLE_SLOT, r_in * 2 + 20, SHELF_T + 2, -CABLE_SLOT / 2, PLATE["t"] + 5.0, -1)]   # the cable drops in from the front
    for z in WINGS:
        cuts.append(box(PLATE["w"] + 2, WING["slot_h"], WING["slot"], -PLATE["w"] / 2 - 1, PLATE["t"], z - WING["slot"] / 2))
    return diff(union(parts), cuts)


def lie_on_back(mesh):
    """Turns the upright holder so the back of its plate is on the print bed (x across, y up the wall, z away from the wall)."""
    m = mesh.copy()
    m.apply_transform(np.array([[-1, 0, 0, 0], [0, 0, 1, 0], [0, 1, 0, 0], [0, 0, 0, 1]], dtype=float))
    return m


def colored(mesh, hex_color, name):
    m = mesh.copy()
    rgba = [int(hex_color[i:i + 2], 16) for i in (1, 3, 5)] + [255]
    m.visual = trimesh.visual.ColorVisuals(m, face_colors=np.tile(rgba, (len(m.faces), 1)))
    m.metadata["name"] = name
    return m


def rounded_plate(w, h, t, r, x, y, z):
    """Rectangle with rounded vertical corners (convex hull of 4 corner cylinders)."""
    pts = [cyl(r, t, cx, cy, z, sections=24).vertices
           for cx, cy in ((x + r, y + r), (x + w - r, y + r), (x + r, y + h - r), (x + w - r, y + h - r))]
    return trimesh.convex.convex_hull(np.vstack(pts))


def shell(sx, sy, sz, x, y, z, opening_face, wall=0.6):
    """A connector: a metal box with an open mouth on one face ('-y' = bottom edge, '+x' = right edge)."""
    outer = box(sx, sy, sz, x, y, z)
    if opening_face == "-y":
        hole = box(sx - 2 * wall, sy - wall, sz - 2 * wall, x + wall, y - 0.5, z + wall)
    else:
        hole = box(sx - wall, sy - 2 * wall, sz - 2 * wall, x + wall + 0.5, y + wall, z + wall)
    return diff(outer, [hole])


# Outlines measured from the official drawing (300 dpi render, enclosed regions; mm from the board's bottom-left corner)
CHIPS = [("board__soc", 24.8, 14.2, 17.0, 17.0, "#a9afb6"), ("board__chip_ram", 26.1, 34.1, 14.1, 9.7, "#2b2e33"),
         ("board__chip_rp1", 52.6, 29.1, 11.7, 11.7, "#2b2e33"), ("board__wifi", 7.4, 35.9, 10.2, 12.8, "#c3c7cc"),
         ("board__pmic", 8.4, 12.3, 5.8, 5.8, "#2b2e33")]
MIPI = [(47.4, 0.5, 2.8, 16.2), (53.6, 0.5, 2.8, 16.2)]   # two camera/display connectors (raster-measured)
POE = (59.5, 6.7, 3.7, 5.4)
FAN_PLUG = (65.5, 40.4, 4.1, 7.0)
COOLER_AT = (1.5, 7.5)                                     # INFERRED: its diagonal pins over the board's two cooler holes


def pi_model():
    """The Pi in detail, placed where it sits inside the case. Names 'key__part' group details under one part."""
    P = []

    def add(key, mesh, col):
        P.append((key, colored(mesh, col, key)))

    add("board", diff(rounded_plate(BOARD["w"], BOARD["h"], BOARD["t"], 3.0, BX, BY, Z_BOARD),
                      [cyl(HOLE_D / 2, BOARD["t"] + 2, BX + hx, BY + hy, Z_BOARD - 1) for hx, hy in HOLES]), "#2f7d4f")
    for key, x, y, w, h, col in CHIPS:
        add(key, box(w, h, 1.2, BX + x, BY + y, Z_TOP), col)
    # GPIO: black base + 40 gold pins, 2.54 mm pitch, rows 3.5 mm in from the top edge
    add("gpio", box(50.8, 5.0, 2.5, BX + GPIO_C - 25.4, BY + BOARD["h"] - 6.0, Z_TOP), "#202225")
    for i in range(20):
        for j in range(2):
            px = BX + GPIO_C - 24.13 + i * 2.54
            py = BY + BOARD["h"] - 3.5 + (j - 0.5) * 2.54
            add("gpio__pin", box(0.64, 0.64, 6.0, px - 0.32, py - 0.32, Z_TOP + 2.5), "#d4a940")
    # front-edge and right-edge sockets: the same table the windows are cut from
    for key, f in FRONT.items():
        z0 = max(f["z0"], 0.0)
        add(key, shell(f["w"], f["d"], f["z1"] - z0, BX + f["c"] - f["w"] / 2, BY - f["out"], Z_TOP + z0, "-y"), "#c9ced3")
    for key, r in RIGHT.items():
        x0, y0 = BX + BOARD["w"] + r["out"] - r["d"], BY + r["c"] - r["w"] / 2
        add(key, shell(r["d"], r["w"], r["z1"], x0, y0, Z_TOP, "+x"), "#c9ced3")
        if key == "ethernet":
            add("ethernet__led_g", box(0.6, 2.0, 1.2, x0 + r["d"], y0 + 1.5, Z_TOP + 11.0), "#2ecc71")
            add("ethernet__led_y", box(0.6, 2.0, 1.2, x0 + r["d"], y0 + r["w"] - 3.5, Z_TOP + 11.0), "#f1c40f")
        else:                                          # USB 3 blue, USB 2 black
            for zz in (Z_TOP + 2.2, Z_TOP + 9.8):
                add(key + "__tongue", box(14.0, r["w"] - 4.0, 1.8, x0 + 2.5, y0 + 2.0, zz + 1.6), "#2f6fd6" if key == "usb_stack_lower" else "#1c1e21")
    for x, y, w, h in MIPI:
        add("mipi", box(w, h, 4.0, BX + x, BY + y, Z_TOP), "#e8e3d6")
    add("poe", box(POE[2], POE[3], 5.5, BX + POE[0], BY + POE[1], Z_TOP), "#202225")
    add("fan_plug", box(FAN_PLUG[2], FAN_PLUG[3], 4.0, BX + FAN_PLUG[0], BY + FAN_PLUG[1], Z_TOP), "#f2efe6")
    add("power_button", box(2.54, 4.23, 2.58, BX + 0.39, BY + BUTTON["y"] - 2.12, Z_TOP), "#202225")
    add("power_button__cap", box(0.85, 2.01, 1.97, BX - BUTTON["out"], BY + BUTTON["y"] - 1.0, Z_TOP + 0.71), "#d8d8d8")
    add("board__led_pwr", box(1.48, 2.01, 0.99, BX + 0.14, BY + LIGHT["y"] - 1.0, Z_TOP), "#7a1b1b")
    add("pcie", box(3.05, 10.4, 2.5, BX + 1.15, BY + 24.9, Z_TOP), "#202225")
    add("sdcard", box(15.0, CARD["w"], CARD["z1"] - CARD["z0"], BX - CARD["out"], BY + CARD["c"] - CARD["w"] / 2, Z_TOP + CARD["z0"]), "#3b82c4")
    soc = CHIPS[0]
    hx, hy, hz = HEATSINK
    add("heatsink", box(hx, hy, hz, BX + soc[1] + soc[3] / 2 - hx / 2, BY + soc[2] + soc[4] / 2 - hy / 2, Z_TOP + 1.2), "#c4c8cd")
    return P


def official_case():
    """The bought case, simplified: base with socket openings, frame with the fan, lid."""
    c, P = OCASE, []
    ox, oy = c["board"]
    z0, zb = c["foot"], c["foot"] + c["base_h"]
    outer = rounded_plate(c["w"], c["d"], c["base_h"], 8.0, 0, 0, z0)
    inner = rounded_plate(c["w"] - 2 * c["wall"], c["d"] - 2 * c["wall"], c["base_h"], 6.5, c["wall"], c["wall"], z0 + 2.0)
    cuts = [inner]
    for f in FRONT.values():
        cuts.append(box(f["w"] + 4, 12, f["z1"] + 3, ox + f["c"] - f["w"] / 2 - 2, -1, Z_TOP - 1.5))
    y0 = min(p["c"] - p["w"] / 2 for p in RIGHT.values()) - 1
    y1 = max(p["c"] + p["w"] / 2 for p in RIGHT.values()) + 1
    cuts.append(box(14, y1 - y0, 30, c["w"] - 8, oy + y0, Z_TOP - 1))
    feet = [cyl(5.0, z0 + 0.1, x, y, 0) for x in (14, c["w"] - 14) for y in (12, c["d"] - 12)]
    P.append(("case_base", union([diff(outer, cuts)] + feet), "#c51f4a"))
    frame = rounded_plate(c["w"], c["d"], c["frame_h"], 8.0, 0, 0, zb)
    fx, fy = c["w"] / 2 - 8, c["d"] / 2
    P.append(("case_frame", diff(frame, [rounded_plate(c["w"] - 8, c["d"] - 8, c["frame_h"], 5.0, 4, 4, zb - 2.0), cyl(17.0, 20, fx, fy, zb - 5),
                                         box(14, y1 - y0, 30, c["w"] - 8, oy + y0, zb - 20)]), "#f4f1ea"))
    P.append(("fan", diff(cyl(19.0, 6.0, fx, fy, zb - 2.0), [cyl(17.0, 8, fx, fy, zb - 3)]), "#2a2d31"))
    for k in range(7):
        blade = box(11.0, 2.4, 4.0, 4.0, -1.2, 0)
        blade.apply_transform(trimesh.transformations.rotation_matrix(2 * np.pi * k / 7, (0, 0, 1)))
        blade.apply_translation((fx, fy, zb - 1.0))
        P.append(("fan__blades", blade, "#3a3e44"))
    P.append(("fan__hub", cyl(5.0, 5.0, fx, fy, zb - 1.5), "#55595f"))
    zl = zb + c["frame_h"]
    P.append(("case_lid", rounded_plate(c["w"], c["d"], c["h"] - zl, 8.0, 0, 0, zl), "#f4f1ea"))
    return [(k, colored(m, col, k)) for k, m, col in P]


def tube(points, r):
    """A cable: short cylinders with a ball at every bend."""
    parts = []
    for a, b in zip(points[:-1], points[1:]):
        parts.append(trimesh.creation.cylinder(radius=r, segment=[a, b], sections=16))
    for p in points[1:-1]:
        ball = trimesh.creation.icosphere(subdivisions=2, radius=r)
        ball.apply_translation(p)
        parts.append(ball)
    return trimesh.util.concatenate(parts)


def umik_model(x, y):
    """miniDSP UMIK-1 tilted in its clip on the mini tripod, on a high shelf, with its cable to the Pi and the power cable.
    Shapes drawn by eye from the maker's photo; the distances are drawn much shorter than real."""
    u, z = UMIK, SHELF_Z + 8.0
    x0, x1, y0 = x - SHELF_W / 2, x + SHELF_W / 2, y - SHELF_D / 2
    parts = [("shelf", box(SHELF_W, SHELF_D, 8.0, x0, y0, SHELF_Z), "#b98a5a"),
             ("shelf__side", box(6.0, SHELF_D, SHELF_Z, x1 - 6.0, y0, 0), "#a87a4b"),
             ("shelf__side", box(6.0, SHELF_D, SHELF_Z, x0, y0, 0), "#a87a4b")]
    hub = np.array([x, y, z + 34.0])
    for k in range(3):
        a = 2 * np.pi * k / 3 + np.pi / 2
        parts.append(("mic__leg", trimesh.creation.cylinder(radius=2.2, segment=[hub, [x + 40 * np.cos(a), y + 40 * np.sin(a), z + 2.2]]), "#2b2e33"))
    pivot = np.array([x, y, z + 62.0])
    parts += [("mic__post", trimesh.creation.cylinder(radius=7.0, segment=[hub - [0, 0, 4], hub + [0, 0, 14]]), "#23262a"),
              ("mic__post", trimesh.creation.cylinder(radius=4.5, segment=[hub, pivot]), "#23262a")]
    t = np.radians(u["tilt"])
    d = np.array([-np.cos(t), 0.0, np.sin(t)])                       # the way the mic points: up and to the left

    def at(s):
        return pivot + d * s

    def rod(r, a, b):
        return trimesh.creation.cylinder(radius=r, segment=[at(a), at(b)], sections=48)

    rear, front = -u["body_l"] * 0.75, u["body_l"] * 0.25
    cone = trimesh.creation.revolve([[0, 0], [u["body_r"], 0], [u["neck_r"], u["cone_l"]], [0, u["cone_l"]]], sections=48)
    cone.apply_transform(trimesh.geometry.align_vectors([0, 0, 1], d))
    cone.apply_translation(at(front))
    neck = front + u["cone_l"]
    foam0 = neck + u["neck_l"] - 12
    dome = trimesh.creation.icosphere(subdivisions=3, radius=u["foam_r"])
    dome.apply_translation(at(foam0 + u["foam_l"] - u["foam_r"]))
    parts += [("mic", rod(u["body_r"], rear, front), "#8d9299"), ("mic__cone", cone, "#8d9299"),
              ("mic__tube", rod(u["neck_r"], neck, neck + u["neck_l"]), "#9aa0a6"),
              ("mic__foam", rod(u["foam_r"], foam0, foam0 + u["foam_l"] - u["foam_r"]), "#1d1f22"), ("mic__foam", dome, "#1d1f22"),
              ("mic__clip", rod(u["body_r"] + 2.5, -14, 10), "#23262a"), ("mic__light", rod(1.6, rear - 0.6, rear + 1), "#3b82c4")]
    plug = at(rear - 12)
    ox, oy = OCASE["board"]
    usb = [ox + BOARD["w"] + RIGHT["usb_stack_upper"]["out"], oy + RIGHT["usb_stack_upper"]["c"], Z_TOP + 12.0]
    cx, cy = usb[0] + 22, y0 - 8                                     # the cable goes round the front of the side panel
    path = [usb, [usb[0] + 14, usb[1], usb[2]], [cx, usb[1] - 14, usb[2] - 6], [cx, cy + 10, 12], [cx + 6, cy, 30],
            [cx + 6, cy, z - 4], [cx + 14, cy + 8, z + 4], [cx + 26, cy + 18, z + 3], [plug[0] - 20, y0 + 16, z + 3],
            [plug[0] + 14, y0 + 30, z + 3], [plug[0] + 20, y - 8, z + 4], [plug[0] + 14, y, plug[2] - 14], list(plug)]
    uc = [ox + FRONT["usb-c_power"]["c"], oy, Z_TOP + 1.6]
    power = [[uc[0], oy - 12, uc[2]], [uc[0], oy - 34, uc[2]], [uc[0] - 6, oy - 44, 5], [uc[0] - 24, oy - 50, 2.4], [-70, oy - 50, 2.4]]
    parts += [("cable__usb", tube([np.array(q, float) for q in path], 2.0), "#2b2e33"),
              ("cable__plug", box(16, 12, 6, usb[0] - 2, usb[1] - 6, usb[2] - 3), "#2b2e33"),
              ("cable__micplug", trimesh.creation.cylinder(radius=5.0, segment=[at(rear), plug]), "#2b2e33"),
              ("cable__powerplug", box(11, 20, 6.5, uc[0] - 5.5, oy - 18, uc[2] - 3.2), "#1d1f22"),
              ("cable__power", tube([np.array(q, float) for q in power], 2.2), "#1d1f22")]
    return [(k, colored(m, c, k)) for k, m, c in parts]


def main():
    OUT_PRINT.mkdir(exist_ok=True)
    OUT_MODEL.mkdir(exist_ok=True)
    base, lid, cradle = make_base(), make_lid(), make_cradle()
    lid_placed = lid.copy()
    lid_placed.apply_translation((0, 0, WALL_TOP))
    report = {}
    for name, m in [("case_base", base), ("case_lid", lid), ("mic_cradle", lie_on_back(cradle))]:   # each file lies the way it prints
        m.export(OUT_PRINT / f"{name}.stl")
        ext = m.bounds[1] - m.bounds[0]
        report[name] = {"size_mm": [round(float(v), 2) for v in ext], "watertight": bool(m.is_watertight),
                        "volume_cm3": round(float(m.volume) / 1000, 1)}
    scene = trimesh.Scene()
    def put(key, m):  # repeated detail parts get a #n suffix; the viewer groups by the name before '#' and '__'
        name = key
        while name in scene.graph.nodes:
            name = f"{key}#{len(scene.graph.nodes)}"
        scene.add_geometry(m, node_name=name, geom_name=name)
        rgba = m.visual.face_colors[0]
        COLOR_MAP[name] = "#%02x%02x%02x" % tuple(int(v) for v in rgba[:3])

    COLOR_MAP = {}
    shift = (OCASE["board"][0] - BX, OCASE["board"][1] - BY, 0)   # the Pi sits where it does in the bought case
    for key, m in pi_model():
        m.apply_translation(shift)
        put(key, m)
    for key, m in official_case() + umik_model(OCASE["w"] + 160, OCASE["d"] / 2 + 20):
        put(key, m)
    scene.export(OUT_MODEL / "noise-logger.glb")
    (OUT_MODEL / "colors.json").write_text(json.dumps(COLOR_MAP, indent=0))
    numbers = {"outer_mm": [round(OUT_W, 2), round(OUT_H, 2), round(WALL_TOP + LID_T, 2)],
               "inner_mm": [round(INNER_W, 2), round(INNER_H, 2)], "hole_spacing_mm": [58.0, 49.0],
               "board_corner_in_case_mm": [round(BX, 2), round(BY, 2)], "board_top_z_mm": round(Z_TOP, 2), "floor_mm": FLOOR,
               "bought_case_mm": [OCASE["w"], OCASE["d"], OCASE["h"]], "board_corner_in_bought_case_mm": list(OCASE["board"]), "parts": report}
    (ROOT / "models" / "numbers.json").write_text(json.dumps(numbers, indent=2))
    print(json.dumps(numbers, indent=2))


if __name__ == "__main__":
    main()
