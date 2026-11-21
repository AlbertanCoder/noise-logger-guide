"""Builds the printable parts (STL) and the 3D model for the web page (GLB) from ONE table of numbers.
Board numbers: official Raspberry Pi 5 + Active Cooler mechanical drawings (see checks/SOURCES.md).
Numbers marked PROVISIONAL are typical connector sizes, not from the drawing: tape-check the real Pi before printing.
Run:  python scripts/make_parts.py      (needs: trimesh, manifold3d, numpy)"""
import json
from pathlib import Path

import numpy as np
import trimesh

ROOT = Path(__file__).resolve().parent.parent
OUT_PRINT, OUT_MODEL = ROOT / "print", ROOT / "models"

# ---------------- numbers (mm) ----------------
BOARD = dict(w=85.0, h=56.0, t=1.6)                    # 85 x 56 READ; thickness 1.6 PROVISIONAL (not in the drawing)
HOLES = [(3.5, 3.5), (61.5, 3.5), (3.5, 52.5), (61.5, 52.5)]  # READ: 3.5 in, 58 x 49 apart
HOLE_D = 2.7                                           # READ
WALL, FLOOR, LID_T = 2.4, 2.0, 2.0
CLEAR_L, CLEAR = 2.5, 1.0                              # left side needs 2.5: parts stick out 1.70 mm there (vector measurement)
STANDOFF_H, HEADROOM = 4.0, 18.0                       # headroom >= cooler 13.7 + 3 air; tallest port UNKNOWN (tape check)
EAR_R, SCREW_PILOT = 3.6, 2.2                          # lid ears with M2.5 self-tapping pilot holes
INNER_W, INNER_H = CLEAR_L + BOARD["w"] + CLEAR, CLEAR + BOARD["h"] + CLEAR      # 88.5 x 58.0
OUT_W, OUT_H = INNER_W + 2 * WALL, INNER_H + 2 * WALL                             # 93.3 x 62.8
BX, BY = WALL + CLEAR_L, WALL + CLEAR                  # board's bottom-left corner inside the case
Z_BOARD = FLOOR + STANDOFF_H                           # underside of the board
Z_TOP = Z_BOARD + BOARD["t"]                           # top of the board
WALL_TOP = Z_TOP + HEADROOM                            # lid sits here
# connectors: (name, edge, centre along that edge from the board corner READ, width PROVISIONAL, height, colour)
PORTS = [
    ("USB-C power", "bottom", 11.2, 9.0, 3.2, "#c9ced3"),        # centre READ, height 3.2 READ
    ("micro-HDMI 0", "bottom", 25.8, 7.0, 3.4, "#c9ced3"),       # centre READ, height 3.4 READ
    ("micro-HDMI 1", "bottom", 39.2, 7.0, 3.4, "#c9ced3"),
    ("Ethernet", "right", 10.2, 16.0, 13.5, "#c9ced3"),          # centre READ; size PROVISIONAL
    ("USB stack (lower)", "right", 29.1, 13.5, 16.0, "#2f6fd6"),  # centre READ; colour order UNKNOWN
    ("USB stack (upper)", "right", 47.0, 13.5, 16.0, "#30343a"),
]
PORT_DEPTH = {"bottom": 7.5, "right": 21.0}
OVERHANG = {"bottom": 1.7, "right": 3.33}              # vector measurement of the official drawing
COOLER = dict(w=63.5, d=42.5, h=13.7, fan=30.0)        # READ
SD_SLOT_Y = 28.0                                       # INFERRED (underneath, left short edge): PROVISIONAL
POWER_BTN_Y = 13.3                                     # READ position (left edge)
MIC = dict(d=45.0, l=150.0)                            # FIFINE body: UNKNOWN until taped; cradle fits ~30-55 mm with zip ties


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


def port_cutouts(margin=1.0):
    cuts = []
    for name, edge, c, w, h, _ in PORTS:
        z0 = Z_TOP - 0.5
        if edge == "bottom":
            cuts.append(box(w + 2 * margin, WALL + 4, h + 2 * margin, BX + c - w / 2 - margin, -1, z0))
        else:
            cuts.append(box(WALL + 4, w + 2 * margin, h + 2 * margin, OUT_W - WALL - 1, BY + c - w / 2 - margin, z0))
    cuts.append(cyl(3.0, 1, 0, 0, 0))  # placeholder removed below
    cuts.pop()
    # power-button finger hole (left wall) and microSD slot under the board (left wall)
    btn = trimesh.creation.cylinder(radius=3.0, height=WALL + 4, sections=32)
    btn.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, (0, 1, 0)))
    btn.apply_translation((WALL / 2, BY + POWER_BTN_Y, Z_TOP + 1.0))
    cuts.append(btn)
    cuts.append(box(WALL + 4, 14.0, 3.6, -1, BY + SD_SLOT_Y - 7.0, FLOOR + 0.2))
    return cuts


def ears():
    return [(0, 0), (OUT_W, 0), (0, OUT_H), (OUT_W, OUT_H)]


def make_base():
    shell = box(OUT_W, OUT_H, WALL_TOP, 0, 0, 0)
    cavity = box(INNER_W, INNER_H, WALL_TOP, WALL, WALL, FLOOR)
    base = diff(shell, [cavity])
    posts = [cyl(3.0, STANDOFF_H, BX + hx, BY + hy, FLOOR - 0.01) for hx, hy in HOLES]
    lugs = [cyl(EAR_R, WALL_TOP, ex, ey, 0) for ex, ey in ears()]
    feet = [cyl(4.0, 1.5, x, y, -1.5) for x, y in [(10, 10), (OUT_W - 10, 10), (10, OUT_H - 10), (OUT_W - 10, OUT_H - 10)]]
    base = union([base] + posts + lugs + feet)
    holes = [cyl(HOLE_D / 2, STANDOFF_H + FLOOR + 3, BX + hx, BY + hy, -2) for hx, hy in HOLES]
    nut_traps = []
    for hx, hy in HOLES:  # M2.5 hex nut: 5.0 mm across flats + 0.3 mm play, 2.2 deep, from below
        n = trimesh.creation.cylinder(radius=(5.3 / 2) / np.cos(np.pi / 6), height=2.2 + 1.5, sections=6)
        n.apply_translation((BX + hx, BY + hy, -1.5 + (2.2 + 1.5) / 2))
        nut_traps.append(n)
    pilots = [cyl(SCREW_PILOT / 2, 12, ex, ey, WALL_TOP - 12 + 0.01) for ex, ey in ears()]
    return diff(base, holes + nut_traps + pilots + port_cutouts())


def make_lid():
    plate = union([box(OUT_W, OUT_H, LID_T, 0, 0, 0)] + [cyl(EAR_R, LID_T, ex, ey, 0) for ex, ey in ears()])
    # vent field over the cooler area (fan position INFERRED, so the field is generous): 10 slots 2 x 36
    slots = [box(2.0, 36.0, LID_T + 2, BX + 22 + i * 5.0, BY + 10, -1) for i in range(10)]
    screw = [cyl(1.4, LID_T + 2, ex, ey, -1) for ex, ey in ears()]  # M2.5 clearance
    return diff(plate, slots + screw)


def make_cradle():
    back = box(60.0, 3.0, 80.0, -30.0, 0.0, 0.0)  # flat back for 2 pairs of Command strips
    parts = [back]
    r_in, r_out = MIC["d"] / 2, MIC["d"] / 2 + 4.0
    for z in (12.0, 58.0):  # two half-rings hold the mic upright
        ring = diff(cyl(r_out, 8.0, 0, 3.0 + r_out - 1, z), [cyl(r_in, 10.0, 0, 3.0 + r_out - 1, z - 1)])
        cut_front = box(2 * r_out + 4, r_out + 4, 12, -r_out - 2, 3.0 + r_out - 1, z - 2)
        parts.append(diff(ring, [cut_front]))
    shelf = diff(cyl(r_out, 3.0, 0, 3.0 + r_out - 1, 0.0), [cyl(4.0, 5, 0, 3.0 + r_out - 1, -1)])  # cable hole in the floor
    parts.append(shelf)
    cradle = union(parts)
    slots = []
    for z in (12.0, 58.0):  # zip-tie slots through the back plate either side
        for x in (-24.0, 20.0):
            slots.append(box(4.0, 6.0, 3.0, x, -1.0, z + 2.5))
    return diff(cradle, slots)


def colored(mesh, hex_color, name):
    m = mesh.copy()
    rgba = [int(hex_color[i:i + 2], 16) for i in (1, 3, 5)] + [255]
    m.visual = trimesh.visual.ColorVisuals(m, face_colors=np.tile(rgba, (len(m.faces), 1)))
    m.metadata["name"] = name
    return m


def pi_model():
    """The Pi as simple shapes, placed where it sits inside the case."""
    board = diff(box(BOARD["w"], BOARD["h"], BOARD["t"], BX, BY, Z_BOARD),
                 [cyl(HOLE_D / 2, BOARD["t"] + 2, BX + hx, BY + hy, Z_BOARD - 1) for hx, hy in HOLES])  # the 4 official holes
    parts = [("board", colored(board, "#2f7d4f", "Raspberry Pi 5 board"))]
    parts.append(("gpio", colored(box(51.0, 5.0, 8.5, BX + 29 - 25.5, BY + BOARD["h"] - 6.0, Z_TOP), "#202225", "GPIO header (not used)")))
    for name, edge, c, w, h, col in PORTS:
        d = PORT_DEPTH[edge]
        if edge == "bottom":
            m = box(w, d, h, BX + c - w / 2, BY - OVERHANG[edge], Z_TOP)
        else:
            m = box(d, w, h, BX + BOARD["w"] - d + OVERHANG[edge], BY + c - w / 2, Z_TOP)
        parts.append((name.lower().replace(" ", "_").replace("(", "").replace(")", ""), colored(m, col, name)))
    cx, cy = BX + (BOARD["w"] - COOLER["w"]) / 2, BY + (BOARD["h"] - COOLER["d"]) / 2  # centred: exact spot INFERRED
    parts.append(("cooler", colored(box(COOLER["w"], COOLER["d"], 11.0, cx, cy, Z_TOP + 1.0), "#b8bcc2", "Active Cooler")))
    parts.append(("fan", colored(cyl(COOLER["fan"] / 2 - 1, 1.0, cx + COOLER["w"] - COOLER["fan"] / 2, cy + COOLER["d"] / 2, Z_TOP + 12.0), "#2a2d31", "Cooler fan")))
    parts.append(("sdcard", colored(box(15.0, 11.0, 1.0, BX - 2.5, BY + SD_SLOT_Y - 5.5, Z_BOARD - 1.4), "#3b82c4", "microSD card (underneath)")))
    return parts


def main():
    OUT_PRINT.mkdir(exist_ok=True)
    OUT_MODEL.mkdir(exist_ok=True)
    base, lid, cradle = make_base(), make_lid(), make_cradle()
    lid_placed = lid.copy()
    lid_placed.apply_translation((0, 0, WALL_TOP))
    report = {}
    for name, m in [("case_base", base), ("case_lid", lid), ("mic_cradle", cradle)]:
        m.export(OUT_PRINT / f"{name}.stl")
        ext = m.bounds[1] - m.bounds[0]
        report[name] = {"size_mm": [round(float(v), 2) for v in ext], "watertight": bool(m.is_watertight),
                        "volume_cm3": round(float(m.volume) / 1000, 1)}
    scene = trimesh.Scene()
    for key, m in [("case_base", colored(base, "#e8e2d4", "Printed case (base)")),
                   ("case_lid", colored(lid_placed, "#e8e2d4", "Printed lid"))] + pi_model():
        scene.add_geometry(m, node_name=key, geom_name=key)
    cr = colored(cradle, "#e8e2d4", "Mic wall holder")
    cr.apply_translation((OUT_W + 60, OUT_H / 2, 0))
    scene.add_geometry(cr, node_name="mic_cradle", geom_name="mic_cradle")
    mic = colored(cyl(MIC["d"] / 2 - 2, MIC["l"], OUT_W + 60, OUT_H / 2 + 3 + MIC["d"] / 2 + 3, 3.0), "#1d1f22", "FIFINE K669B mic (size to confirm)")
    scene.add_geometry(mic, node_name="mic", geom_name="mic")
    scene.export(OUT_MODEL / "noise-logger.glb")
    numbers = {"outer_mm": [round(OUT_W, 2), round(OUT_H, 2), round(WALL_TOP + LID_T, 2)],
               "inner_mm": [round(INNER_W, 2), round(INNER_H, 2)], "hole_spacing_mm": [58.0, 49.0],
               "board_corner_in_case_mm": [BX, BY], "parts": report}
    (ROOT / "models" / "numbers.json").write_text(json.dumps(numbers, indent=2))
    print(json.dumps(numbers, indent=2))


if __name__ == "__main__":
    main()
