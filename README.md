# Build a Noise Logger

**[▶ Open the guide](https://albertancoder.github.io/noise-logger-guide/)** · works on a phone and a desktop · same layout as the Heat-Spotting Drone guide (Home · Build · 3D · Buy · Print) · [classic one-page version](https://albertancoder.github.io/noise-logger-guide/classic.html)

A step-by-step guide to a small Raspberry Pi device that keeps an automatic, timestamped record of noise
(when, how long, how loud, what kind of sound). It never keeps audio when it hears talking, and its log shows if an entry was changed.

- **Who made it:** Shad ([@AlbertanCoder](https://github.com/AlbertanCoder)) in Edmonton, by directing AI coding tools.
- **What's in it:** a parts list with live-checked prices and links; a detailed 3D model (102 parts: 40 GPIO pins, ports with openings, cooler fins and a spinning fan) with Exploded, X-ray, Labels, Show measurements and Power-on preview; a step panel that flies the camera to each step; print files for the case and a no-holes mic wall holder; and 12 plain build steps, each with a "check it worked".
- **Honest status:** step 0 (the logger on a laptop) is tested; steps 1–11 are written from the parts' documentation and are marked "Not tested yet" until the parts arrive.

## Where the numbers come from
- Board size, the 4 mounting holes (58 × 49 mm, Ø2.7), port positions and the cooler: the official Raspberry Pi 5 and Active Cooler mechanical drawings (datasheets.raspberrypi.com).
- Connector widths marked "size to confirm" are typical values; build step 3 measures the real parts before printing.
- Prices and stock: read on each shop's page on 2026-11-21.

## Checks (run before every release)
```
python scripts/make_parts.py     # builds print/*.stl and models/noise-logger.glb from one table of numbers
python scripts/check_parts.py    # sizes, watertight, and the 4 screw holes measured at 58 x 49 mm
python scripts/check_page.py     # 44 px buttons, 13 px labels, no scroll hijack, links, totals, no personal details
```

## Built with
One HTML page, no framework; [three.js](https://threejs.org/) r187 (MIT) is included in `vendor/three`. Parts made with trimesh + manifold3d.

## Limits
The logger is not a sound level meter: loudness is relative to its own microphone. Only a bylaw officer can confirm a noise violation.
