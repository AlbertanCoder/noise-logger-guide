# Build a Noise Logger

**[▶ Open the guide](https://albertancoder.github.io/noise-logger-guide/)** · works on a phone and a desktop · same layout as the Heat-Spotting Drone guide (Home · Build · 3D · Buy)

A step-by-step guide to a small Raspberry Pi device that keeps an automatic, timestamped record of noise
(when, how long, how loud, what kind of sound). Saving audio is off. Each log entry carries a fingerprint of the one before, so accidental damage or a simple edit shows up; that alone does not prove nothing was removed or rewritten.

- **Who made it:** Shad ([@AlbertanCoder](https://github.com/AlbertanCoder)) in Edmonton, by directing AI coding tools.
- **What's in it:** a parts list with prices read on the shop pages; a 3D model (the Pi from its official drawing, the bought case simplified; the mic, shelf and cables drawn by eye) with Exploded, See inside, Labels, Show measurements and Power on (preview); and 12 plain build steps, each with a "check it worked".
- **Honest status:** step 0 (the logger on a laptop) is tested; steps 1–11 are written from the parts' documentation and are marked "Not tested yet" until the parts arrive.

## Where the numbers come from
- Board size, mounting holes, ports and sockets: the official Raspberry Pi 5 drawing (which calls its sizes approximate). Case outside size: the official case brief. The mic is drawn by eye.
- Prices and stock: read on each shop's page on 2026-11-22.

## Checks (run before every release)
```
python scripts/make_parts.py     # builds models/noise-logger.glb (and the older print files) from one table of numbers
python scripts/check_parts.py    # checks the older printable case in print/, which this build no longer uses
python scripts/make_pictures.py  # retakes the 12 step pictures from the 3D model
python scripts/check_page.py     # words and numbers first, then the real page in a browser at phone width: sizes, pictures, 3D, buttons
```

## Built with
One HTML page, no framework; [three.js](https://threejs.org/) r187 (MIT) is included in `vendor/three`. Parts made with trimesh + manifold3d.

## Limits
The logger is not a sound level meter: loudness is relative to its own microphone. Only a bylaw officer can confirm a noise violation.
