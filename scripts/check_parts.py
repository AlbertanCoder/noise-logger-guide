"""Measures the exported STL files and compares them with the numbers from the official drawing (exit 1 on any miss).
Checks: overall sizes, watertight, and the 4 board-screw holes found by slicing the base: spacing must be 58 x 49 mm."""
import sys
from itertools import combinations
from pathlib import Path

import numpy as np
import trimesh

ROOT = Path(__file__).resolve().parent.parent
TOL = 0.5
EXPECT = {  # mm, from make_parts.py numbers: box 93.3 x 62.8 + lid ears (r 3.6) = 100.5 x 70.0; base 25.6 tall + 1.5 feet
    "case_base": (100.5, 70.0, 27.1),
    "case_lid": (100.5, 70.0, 2.0),
    "mic_cradle": (60.0, 55.0, 80.0),
}
fails = 0


def ok(cond, msg):
    global fails
    print(("PASS " if cond else "FAIL ") + msg)
    fails += 0 if cond else 1


for name, exp in EXPECT.items():
    m = trimesh.load(ROOT / "print" / f"{name}.stl")
    size = m.bounds[1] - m.bounds[0]
    ok(all(abs(a - b) <= TOL for a, b in zip(size, exp)), f"{name}: size {np.round(size, 2).tolist()} vs {list(exp)} (±{TOL})")
    ok(m.is_watertight, f"{name}: watertight (printable solid)")

# screw holes: slice the base through the standoff posts (z = 4.0 mm) and find the small round holes
base = trimesh.load(ROOT / "print" / "case_base.stl")
sec = base.section(plane_origin=(0, 0, 4.0), plane_normal=(0, 0, 1))
holes = []
for loop in sec.discrete:  # each closed outline in the slice, in real (x, y, z) mm
    pts = np.asarray(loop)[:, :2]
    d = pts.max(axis=0) - pts.min(axis=0)
    if 2.4 < d.mean() < 3.0 and abs(d[0] - d[1]) < 0.3:  # the round Ø2.7 board holes
        holes.append(pts.mean(axis=0))
ok(len(holes) == 4, f"found {len(holes)} board-screw holes of about Ø2.7 at the post height (need 4)")
if len(holes) == 4:
    h = np.array(holes)
    xs, ys = sorted(set(np.round(h[:, 0], 1))), sorted(set(np.round(h[:, 1], 1)))
    dx, dy = (max(xs) - min(xs)), (max(ys) - min(ys))
    ok(abs(dx - 58.0) <= TOL and abs(dy - 49.0) <= TOL, f"hole spacing {dx:.2f} x {dy:.2f} mm vs official 58 x 49")
print(f"\n{'ALL PASS' if fails == 0 else str(fails) + ' FAILED'}")
sys.exit(1 if fails else 0)
