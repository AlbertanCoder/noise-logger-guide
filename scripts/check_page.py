"""Checks the guide page (exit 1 on any miss).
Part 1 reads the files: links, totals that match the noise-logger totals script, steps complete, wording, no personal details.
Part 2 opens the real page in a browser at phone width (checks/selftest.html) and measures what is drawn: sizes, pictures, 3D buttons.
Run:  python scripts/check_page.py            (add --links to also ask each shop and source link if it still answers)"""
import functools
import html as htmllib
import http.server
import json
import re
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
html = (ROOT / "index.html").read_text(encoding="utf-8")
app = (ROOT / "js" / "app2.js").read_text(encoding="utf-8")
viewer = (ROOT / "js" / "viewer.js").read_text(encoding="utf-8")
fails = 0


def ok(cond, msg):
    global fails
    print(("PASS " if cond else "FAIL ") + msg)
    fails += 0 if cond else 1


# ======================= Part 1: the files =======================
css = re.search(r"<style>(.*?)</style>", html, re.S).group(1)
btn = re.search(r"\.btn\{[^}]*min-height:(\d+)px", css)
ok(btn and int(btn.group(1)) >= 44, f"buttons at least 44 px tall (found {btn.group(1) if btn else None})")
nav = re.search(r"\.tabs button\{[^}]*min-height:(\d+)px", css)
ok(nav and int(nav.group(1)) >= 44, f"bottom tabs at least 44 px tall (found {nav.group(1) if nav else None})")
lab = re.search(r"\.vlabel\{[^}]*font-size:(\d+)px", css)
ok(lab and int(lab.group(1)) >= 13, f"3D labels at least 13 px (found {lab.group(1) if lab else None})")
# Round 2 of the 3D plan (24 Nov 2026): the 3D view handles like the drone guide's
none_rules = [r.strip() for r in re.findall(r"([^{}]+)\{[^}]*touch-action:none", re.sub(r"/\*.*?\*/", "", css, flags=re.S))]
ok(none_rules and all(r.startswith("#viewer") for r in none_rules), f"touch-action:none on the 3D view only, so the page scrolls outside it ({none_rules})")
ok("ONE: THREE.TOUCH.ROTATE, TWO: THREE.TOUCH.DOLLY_PAN" in viewer and "stopPropagation" not in viewer, "one finger turns, two fingers zoom, and the wheel zooms (no wheel blocker)")
ok("b-grab" not in html + viewer and "grabbed" not in html + viewer and "Move the model" not in html + viewer, "'Move the model' is gone")
ok("enableDamping = false" in viewer, "no glide: the model stops dead when you let go")
ok("dist * 0.25" in viewer and "dist * 3.2" in viewer and "Math.PI * 0.495" in viewer, "zoom limits 0.25x to 3.2x the fitted distance, and a floor, as on the drone guide")
ok('id="b-reset"' in html and ">Reset view<" in html and 'id="b-full"' in html and ">Full screen<" in html, "Reset view and Full screen buttons")
ok(">Drag to rotate &middot; scroll to zoom &middot; right-drag to pan<" in html and "pinch to zoom" in viewer, "the hint line in the drone guide's words, with the touch wording on touch screens")
vh = re.search(r"@media \(min-width:900px\)\{#viewer\{height:min\((\d+)px", css)
ok(vh and int(vh.group(1)) >= 560 and "grid-template-columns:1fr 320px" not in css, f"a big 3D frame on a laptop (about 585 px) with the step panel under it ({vh.group(1) if vh else None} px)")
# Rounds 3 and 4 of the 3D plan (24 Nov 2026): the Blender model, the drone guide's look, highlight, tap to name, Play per step
glb = (ROOT / "models" / "noise-logger.glb").read_bytes()
gj = json.loads(glb[20:20 + struct.unpack_from("<I", glb, 12)[0]])
parts = {n["name"]: n.get("extras", {}) for n in gj["nodes"] if "mesh" in n}
points = {n["extras"]["key"]: n["extras"].get("ride") for n in gj["nodes"] if n.get("extras", {}).get("kind") == "label"}
ok(len(glb) < 500 * 1024 and "Blender" in gj["asset"].get("generator", ""), f"the model is built in Blender and stays under 500 KB ({len(glb) // 1024} KB, {len(parts)} parts)")
need = ["case_base", "case_frame", "case_lid", "board", "fan", "fan__hub", "fan__blades", "heatsink", "sdcard", "usb-c_power", "mic", "shelf", "cable__usb", "cable__power", "cable__plug", "cable__powerplug", "cable__micplug"]
ok(all(n in parts for n in need), f"the model keeps the part names the 3D view relies on ({[n for n in need if n not in parts]})")
ok(all(e.get("part") and e.get("acc") in ("official", "simplified", "eye") for e in parts.values()), "every part of the model carries a plain name and how exact its drawing is")
ok(parts.get("mic", {}).get("acc") == "eye" and parts.get("board", {}).get("acc") == "official" and parts.get("case_base", {}).get("acc") == "simplified",
   "the mic is tagged drawn by eye, the Pi from the official drawing, the case simplified")
colours = json.loads((ROOT / "models" / "colors.json").read_text(encoding="utf-8"))
ok(set(colours) == set(parts) and all(re.fullmatch(r"#[0-9a-f]{6}", c) for c in colours.values()), "colors.json names every part of the model, and nothing else")
numbers = json.loads((ROOT / "models" / "numbers.json").read_text(encoding="utf-8"))
pos = gj["accessors"][gj["meshes"][next(n["mesh"] for n in gj["nodes"] if n.get("name") == "board")]["primitives"][0]["attributes"]["POSITION"]]
bx, by = numbers["board_corner_in_bought_case_mm"]
ok(abs(pos["min"][0] - bx) < 0.01 and abs(pos["min"][1] - by) < 0.01 and abs(pos["max"][0] - bx - 85) < 0.01 and abs(pos["max"][1] - by - 56) < 0.01 and abs(pos["max"][2] - numbers["board_top_z_mm"]) < 0.01,
   f"the board in the model is 85 x 56 mm and sits where numbers.json says ({[round(v, 2) for v in pos['min']]} to {[round(v, 2) for v in pos['max']]})")
case_top = max(gj["accessors"][gj["meshes"][n["mesh"]]["primitives"][0]["attributes"]["POSITION"]]["max"][2] for n in gj["nodes"] if n.get("name") == "case_lid")
ok(abs(case_top - numbers["bought_case_mm"][2]) < 0.01, f"the case in the model is as tall as the maker's number ({case_top:.1f} mm)")
builder = (ROOT / "scripts" / "build_model_blender.py").read_text(encoding="utf-8")
ok("import make_parts as M" in builder and not re.search(r"(?<![\d.])(98\.5|70\.3|85\.0|56\.0|58\.0|49\.0|1\.41)(?![\d])", builder),
   "the Blender script reads its measurements from make_parts.py and retypes none of them")
labels_json = json.loads(re.search(r'id="model-labels">(.*?)</script>', html, re.S).group(1))
ok(set(points) == set(labels_json) and all(r in parts for r in points.values()), f"the model carries a point for every 3D label ({sorted(set(labels_json) ^ set(points))})")
ok("ACESFilmicToneMapping" in viewer and "toneMappingExposure = 1.05" in viewer and "0xf7f2e8" in viewer and "opacity: 0.16" in viewer and viewer.count("DirectionalLight(") == 4 and "HemisphereLight(" in viewer,
   "the drone guide's look: cream backdrop, ACES tone 1.05, four lamps and a sky light, a soft 0.16 shadow")
ok("0.62 * b.opacity" in viewer and "0xc2571b" in viewer and "emissiveIntensity = pale ? 0.1 : 0.75" in viewer, "the step's parts glow orange and the other parts dim to 62%")
ok('store.get("labels") === "1"' in viewer and 'store.set("labels"' in viewer and "try { window.localStorage" in viewer and 'id="b-labels" aria-pressed="false"' in html
   and html.index('id="b-labels"') < html.index('<details class="more">'),
   "labels are hidden at first, a Labels button in the main row shows them, and the choice is remembered (storage may be missing)")
ok(all(w in viewer for w in ("from the official drawing", "simplified", "drawn by eye", "}, 5000)", "< 6) pick(", '"pointermove"', 'e.pointerType !== "mouse"')),
   "tapping a part shows its name and how exact its drawing is for 5 s; pointing at it with the mouse does too; a drag is not a tap")
ok('id="b-play"' in html and 'id="v-seek"' in html and "Nothing moves in this step" in viewer and ".vtag{" in css, "a Play button and a slider under the 3D view, and a style for the tap name")
sys.path.insert(0, str(ROOT / "scripts"))
import make_pictures as pics  # noqa: E402
stale_marks = [name for name, pattern, of in pics.STAMPS if (re.search(pattern, (ROOT / name).read_text(encoding="utf-8")) or [""])[0].find(pics.fingerprint(*of)) < 0]
ok(not stale_marks, f"the model and scripts are loaded by addresses that carry their current fingerprint, so no phone shows a saved old copy ({stale_marks}; fix: python scripts/make_pictures.py)")
ok("js/viewer.js" in app and "poster" not in html + viewer, "the 3D view loads live as soon as the page opens, on a phone too (no still picture first)")
ok("touch-action: pan-x pan-y" in html and "gesturestart" in html and "user-scalable=no" in html, "the page itself never zooms (pinch or double-tap, iPhone included)")
ok(html.count("</html>") == 1, "exactly one </html>")
tab_marks = re.findall(r'<button role="tab" data-tab="(\w+)"[^>]*>(.*?)</button>', html)
ok(len(tab_marks) == 8 and all(re.match(r'<svg class="tabic" aria-hidden="true"><use href="#i-\w+"/></svg>[A-Za-z0-9]+$', m) for _, m in tab_marks)
   and all(f'<symbol id="i-{n}"' in html for n in ("home", "build", "3d", "buy")),
   "the four tab icons are one family of plain outlines, on the phone's bottom bar and the computer's side bar")
ok('aria-pressed' in html and 'Auto-spin' in html and 'id="ring"' in html and 'id="dc-mic"' in html, "pressed states, 'Auto-spin', progress ring and mic-test card present")
ok('id="next-go"' in html and 'data-tab="build"' in html, "Home's 'Go to Step N' button and a Build tab")
ok("needsUpdate = true" in viewer, "the 3D view tells the drawing library when a part turns see-through (final audit FA-03)")

buy = json.loads(re.search(r'id="buy-data">(.*?)</script>', html, re.S).group(1))
ok(all(l["url"].startswith("https://") for l in buy["lines"]), f"all {len(buy['lines'])} parts have a real https link")
ok(len({l["url"] for l in buy["lines"]}) == len(buy["lines"]), "no two parts share one shop link")
ok('target = "_blank"' in app and 'rel = "noopener"' in app, "shop links open in a new tab")
ok(all(l.get("model") and l.get("shop") for l in buy["lines"]), "every part card has a model number and a shop")
ok(all("stock" in l["stock"].lower() and "out of stock" not in l["stock"].lower() for l in buy["lines"]), "every part card says it is in stock")
total = round(sum(l["price"] for l in buy["lines"]) * (1 + buy["gst"]), 2)
totals_py = Path.home() / "noise-logger" / "scripts" / "totals.py"
out = subprocess.run([sys.executable, str(totals_py)], capture_output=True, text=True).stdout
m = re.search(r"PLAN-UMIK .*?\n\s+parts\s+[\d.]+\s+GST\s+[\d.]+\s+total\s+([\d.]+)", out)
ok(m and abs(float(m.group(1)) - total) < 0.005, f"page total ${total:.2f} matches totals.py PLAN-UMIK (${m.group(1) if m else '?'})")

steps = json.loads(re.search(r'id="steps-data">(.*?)</script>', html, re.S).group(1))
ok(len(steps) == 12 and all(s["check"] and s["actions"] for s in steps), f"{len(steps)} steps, each with actions and a 'check it worked'")
ok([s["n"] for s in steps if s["tested"]] == [0], "only the step actually done (step 0, laptop) is marked Tested")

# ---- every step can be followed as written (audit B-01 to B-05, A-02 to A-05; final audit FA-06 to FA-13) ----
T = {s["n"]: " ".join([s["title"]] + s["actions"] + [s.get("warn", ""), s["check"]] + s.get("tools", [])) for s in steps}
A = {s["n"]: s["actions"] for s in steps}
by_title = {s["title"]: s["n"] for s in steps}
mount = next((n for t, n in by_title.items() if "high shelf" in t), 99)
quiet = next((n for t, n in by_title.items() if "Quiet-room" in t), -1)


def has(n, *words):
    miss = [w for w in words if w not in T.get(n, "")]
    ok(not miss, f"step {n}: {', '.join(w[:38] for w in words)}" + (f" | MISSING {miss}" if miss else ""))


def before(n, first, second):
    """Inside step n, the action holding `first` comes before the action holding `second`."""
    i = next((k for k, a in enumerate(A[n]) if first in a), None)
    j = next((k for k, a in enumerate(A[n]) if second in a), None)
    ok(i is not None and j is not None and i < j, f"step {n}: '{first[:30]}' comes before '{second[:30]}'")


has(0, r".venv\Scripts\python -m pytest")
has(1, "2GB board only", "64 GB", "UMIK-2", "FREE returns", "return date", "shipping", "new and unused condition", "from Amazon")
has(2, "serial number", "mini-USB", "box", "SC1159")
has(3, "--list-devices", "mic_name='umik'", "--calibrate", "--run", "9 of every 10", "return the mic", "never heard this ceiling", "40 thumps", "Audio enhancements", "dB above the quiet room")
before(3, "--calibrate", "--run")
has(4, "calibration", "serial number", r"data\calibration")
has(5, "card reader", "Localisation", "capital city", "lowercase", "SSH")
has(6, "envelope", "heatsink", "FAN", "plastic tab", "feet", "button")
before(6, "Put the Pi in the base", "Clip the frame back")
has(7, "yes", "password", "free -h", "0x0", "sudo poweroff")
has(8, "0.2.0 or higher", "noise_logger.__version__", "git archive", r"scp ..\noise-logger.tgz", "tar xzf", "bash deploy/install.sh")
before(8, "git archive", "scp ")
before(8, "tar xzf", "bash deploy/install.sh")
ok(0 < mount < quiet, f"the mic is placed (step {mount}) before the quiet room is measured (step {quiet})")
has(mount, "1.5 m", "1.2 m", "at least 1 m", "all directions")
has(quiet, "arecord -l", "mic_name='umik'", ".venv/bin/python -m noise_logger --calibrate", "systemctl enable --now noise-logger noise-logger-web noise-logger-nightly.timer",
    "systemctl stop noise-logger", "systemctl start noise-logger")
before(quiet, "--calibrate", "systemctl enable --now")
has(11, "http://noise-logger.local:8080", "hostname -I", "pull_backup.ps1 -PiUser", "send_fingerprint.py")
ok("Read this first" in app and app.index("Read this first") < app.index("Show the written steps"), "a step's warning is shown before its actions (final audit FA-06)")
labels = json.loads(re.search(r'id="label-steps">(.*?)</script>', html, re.S).group(1))
ok(all(1 <= n <= 11 for n in labels.values()) and labels["shelf"] == mount, "3D labels point to real steps")
pics = [ROOT / "images" / "steps" / f"step-{s['n']}.jpg" for s in steps]
ok(all(p.exists() and p.stat().st_size > 4000 for p in pics), "a picture for every step")
newest_source = max((ROOT / f).stat().st_mtime for f in ("js/viewer.js", "models/noise-logger.glb"))
ok(all(p.stat().st_mtime >= newest_source - 120 for p in pics if p.exists()), "the step pictures were retaken after the last 3D change (python scripts/make_pictures.py)")
ids = {l["id"] for l in buy["lines"]}
ok(ids == {"pi", "psu", "case", "sd", "mic"} and all(set(s["parts"]) <= ids | {"all"} for s in steps), f"the 5 chosen parts, and steps only use those ({sorted(ids)})")
manifest = (ROOT / "manifest.webmanifest").read_text(encoding="utf-8")
stale = [w for w in ("FIFINE", "K669", "Active Cooler", "Command Large", "M2.5", "case_base.stl", "mic_cradle", 'data-tab="print"', "zip tie", "Print files", "print files", "X-ray")
         if w.lower() in (html + app + viewer + manifest).lower()]
ok(not stale, f"nothing left from the old parts list or old button names ({stale})")
ok("all from Amazon" in html and "free delivery" in app and "PiShop shipping" not in html + app and "pishop.ca" not in html,
   "both totals say all five parts come from Amazon; no PiShop link or shipping line is left (agreed 2026-11-22)")
ok("Why this mic" in html and "below 100 Hz" in html and "Nobody has tested it on this ceiling yet" in html, "Buy says why this mic and what is unproven")
ok("new and unused" in html and "can go back if" not in html, "the mic's return is described with Amazon's own condition (final audit FA-02)")
faults = re.search(r"Fixed in the software on 2026-11-22, tested with made-up sound only</b>\s*<ul[^>]*>(.*?)</ul>", html, re.S)
ok(faults and faults.group(1).count("<li>") == 7 and "unplugged" in html and "rumble" in html and "Stopping or restarting" in html, "Home lists the seven software fixes and says they were tested with made-up sound only")
ok(f"${total:.2f}</b>parts, with GST" in html, "Home's written total is the same as the bill")
ok("0 of 11 steps done" in html and "REAL" in app, "step 0 is optional and not counted")
sizes = [float(x) for x in re.findall(r"font-size:\s*([0-9.]+)px", html)]
ok(min(x for x in sizes if x != 12) >= 13, f"no text under 13 px anywhere in the page file, apart from the small arrow ({sorted(set(sizes))[:4]})")
ok("honest dated record" in html and all(w in html for w in ("legal sound meter", "Know whose noise", "Keep conversations", "Play any sound", "Decibel estimates", "Short thump clips", "learns whose noise", "portfolio piece", "sleep record", "next door")), "Home says what it is for, does, does not, and later (agreed 2026-11-22)")
ok("has not run on a Pi or with this mic yet" in html and "Final audit done" in html and "Checked again in the final audit" in html, "Home and Buy say what is unproven and when the parts were last checked")
ok("url=index.html" in (ROOT / "classic.html").read_text(encoding="utf-8"), "the classic page only forwards to the guide")

# ---- no personal details in ANY public text file (final audit FA-18: the manifest and the scripts were not looked at) ----
# Both word lists live in the private repository and are never published; this script names no word itself.
private_dir = Path.home() / "noise-logger"
lists = [private_dir / "private-words.txt", private_dir / "checks" / "private-generic-words.txt"]
words = [w.strip() for p in lists if p.exists() for w in p.read_text(encoding="utf-8").splitlines() if w.strip() and not w.startswith("#")]
ok(all(p.exists() for p in lists) and len(words) >= 8, "both private word lists found (personal names, and general words that would give the story away)")
TEXT = {".html", ".js", ".md", ".json", ".webmanifest", ".py", ".svg", ".txt", ".css"}
public = [p for p in ROOT.rglob("*") if p.is_file() and p.suffix.lower() in TEXT and not ({".git", "vendor", "__pycache__"} & set(p.parts))]
if words:
    bad = re.compile("|".join(words), re.I)
    hits = sorted({(str(p.relative_to(ROOT)), m.group(0).lower()) for p in public for m in bad.finditer(p.read_text(encoding="utf-8", errors="replace"))})
    ok(not hits, f"no personal details in the {len(public)} public text files ({hits})")


# ======================= Part 2: the real page in a browser =======================
RESULT = {}
DONE = threading.Event()


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):  # a page opened with slow=N in its address gets the model file N seconds late, like a phone on a slow connection
        late = re.search(r"slow=(\d+)", self.headers.get("Referer") or "")
        if late and self.path.split("?")[0].endswith(".glb"):
            time.sleep(int(late.group(1)))
        super().do_GET()

    def end_headers(self):  # the test browser keeps nothing, so every load really asks this server
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_POST(self):  # the test page posts what it measured here when it has finished
        if self.path == "/selftest-result":
            RESULT.update(json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode("utf-8")))
            DONE.set()
        self.send_response(204)
        self.end_headers()


def browser_test():
    """Runs checks/selftest.html in a hidden Chrome in real time (so the 3D view draws every frame) and waits for its report."""
    chrome = next((c for c in (r"C:\Program Files\Google\Chrome\Application\chrome.exe", r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe") if Path(c).exists()), None)
    if not chrome:
        return None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(ROOT)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as prof:
            proc = subprocess.Popen([chrome, "--headless=new", "--hide-scrollbars", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", f"--user-data-dir={prof}", "--no-first-run",
                                     "--window-size=900,1000", f"http://127.0.0.1:{srv.server_port}/checks/selftest.html"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            DONE.wait(timeout=150)
            proc.terminate()
            try:
                proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                proc.kill()
        return dict(RESULT)
    finally:
        srv.shutdown()


print("\nOpening the real page in a hidden browser at phone width (about 30 seconds)...")
t = browser_test()
ok(t is not None, "Chrome found, so the browser part can run")
t = t or {}
ok(bool(t), "the test page finished and reported back")
ok(t.get("steps") == 12 and t.get("parts") == 5, f"the page draws 12 step cards and 5 part cards (found {t.get('steps')} and {t.get('parts')})")
ok(f"${total:.2f}" in t.get("bill", "") and t.get("progress") == "0 of 11 steps done", f"the bill shows ${total:.2f} and progress starts at 0 of 11 ({t.get('progress')!r})")
ok(t.get("model") == "yes" and t.get("pictureRange", 0) > 40, f"the 3D model loads and draws (loaded: {t.get('model')}, picture range {t.get('pictureRange')})")
ok(t.get("pictures") == 12, f"all 12 step pictures load ({t.get('pictures')})")
ok(t.get("warnFirst") is True, "on the page, every step's warning sits above its actions")
for tab in ("home", "build", "buy", "model"):
    r = t.get("tabs", {}).get(tab)
    ok(bool(r) and not r["sideways"] and not r["small"] and not r["taps"],
       f"{tab} tab at 390 px: no sideways scroll, no text under 13 px, nothing to tap under 44 px" + ("" if r and not (r["sideways"] or r["small"] or r["taps"]) else f" | {r}"))
ok(t.get("measurePressed") is True and t.get("seeInsideChange", 0) > 6, f"'See inside' really changes the picture (average change {t.get('seeInsideChange')}; under 1 means the case stayed solid)")
pc = t.get("pc") or {}
ok(len(t.get("measureMarks", [])) == 5, f"'Show measurements' at 390 px: all 5 numbers are whole inside the picture ({t.get('measureMarks')})")
ok(pc.get("width", 0) >= 900 and len(pc.get("measureMarks", [])) == 5, f"'Show measurements' at PC width ({pc.get('width')} px): all 5 numbers are whole inside the picture ({pc.get('measureMarks')})")
row = pc.get("stepRow") or {}
ok(row.get("shown") is True and row.get("withModel") is True and row.get("stays") is True and row.get("moved") == 2 and row.get("playRowTop") == (row.get("at") or [0, -1])[1],
   f"at PC width Back / Next sit right under the model, on screen with it, beside Play; two presses on the same spot move two steps ({row})")
ok(len(t.get("explodedLabels", [])) == 5, f"Exploded view: all 5 labels are inside the picture, lid included ({t.get('explodedLabels')})")
ok(str(t.get("step5Title", "")).startswith("5.") and t.get("step5SolidRed", 100) < 2, f"stepping to step 5 ghosts the case so the card shows ({t.get('step5SolidRed')}% of the picture is still solid red)")
ok(t.get("viewerH", 0) >= 300 and t.get("touchAction") == "none" and not t.get("grabButton"), f"at 390 px the 3D view is {t.get('viewerH')} px tall, one finger turns it (touch-action {t.get('touchAction')!r}), no 'Move the model'")
ok(t.get("wheelKeptFromPage") is True and t.get("wheelZoomChange", 0) > 2 and t.get("wheelMoved") is True, f"the wheel zooms the model instead of scrolling the page (picture change {t.get('wheelZoomChange')})")
ok(abs(t.get("zoomInStop", 0) - 1) < 0.02 and abs(t.get("zoomOutStop", 0) - 1) < 0.02 and abs(t.get("limitsRatio", 0) - 12.8) < 0.1,
   f"zooming stops at both limits (near {t.get('zoomInStop')}, far {t.get('zoomOutStop')}, far/near {t.get('limitsRatio')})")
ok(abs(t.get("overviewMaxPolar", 0) - 1.555) < 0.01 and abs(t.get("step5MaxPolar", 0) - 3.047) < 0.01 and t.get("damping") is False,
   f"the camera never goes under the floor, except in step 5's view from below (floor {t.get('overviewMaxPolar')}, step 5 {t.get('step5MaxPolar')}); no glide")
ok(t.get("resetBack", 99) < 1.5 and abs(t.get("resetDist", 0) - 1) < 0.01, f"Reset view puts the camera back where the step had it (picture difference {t.get('resetBack')}, distance {t.get('resetDist')})")
ok(t.get("fullOpen") is True and t.get("fullH", 0) > t.get("viewerH", 0) and t.get("fullLabel") == "Close full screen" and t.get("fullClosed") is True,
   f"Full screen opens ({t.get('fullH')} px tall) and Esc closes it")
ok(t.get("hint", "").startswith("Drag to rotate"), f"the hint line shows under the 3D view ({t.get('hint')!r})")
ok(t.get("tone") == 1.05 and t.get("poster") is False, f"the page draws with the drone guide's tone setting ({t.get('tone')}) and shows the live 3D with no still picture first")
ok(t.get("micGlow") == "c2571b" and t.get("micGlowPower", 0) > 0.5 and t.get("shelfOpacity") == 0.62, f"step 3: the mic glows orange ({t.get('micGlow')}) and the shelf dims to 62% ({t.get('shelfOpacity')})")
ok("drawn by eye" in t.get("tapTag", "") and "UMIK-1" in t.get("tapTag", "") and t.get("dragTag") == "" and t.get("tagGone") is True,
   f"tapping the mic says {t.get('tapTag')!r}; a drag shows nothing ({t.get('dragTag')!r})")
pl = t.get("play") or {}
ok(t.get("playOffAtStep0") is True and str(t.get("playTitle", "")).startswith("6.") and t.get("playReady") is True, "Play is off where nothing moves (step 0) and ready in step 6")
ok(pl.get("going") is True and pl.get("lidUp", 0) > 40 and pl.get("t2", 0) > pl.get("t1", 9) > 0.5 and "Pause" in pl.get("label", ""),
   f"Play animates the step: the lid is {pl.get('lidUp')} mm up at {pl.get('t1')} s and it keeps going ({pl.get('t2')} s)")
ok(pl.get("going") is True and pl.get("zoomed", 1) < 0.99, f"you can zoom while it plays (distance x{pl.get('zoomed')})")
ok(t.get("paused") is True and t.get("playEndLid") == 0, f"Pause stops it, and the slider's end puts every part in place (lid {t.get('playEndLid')} mm up)")
dr = t.get("drawing") or {}
ok(dr.get("on3D", 0) > 20 and dr.get("onHome", 1) == 0 and dr.get("backOn3D", 0) > 20,
   f"the 3D is drawn only while its tab is open ({dr.get('on3D')} drawing calls in a moment on the 3D tab, {dr.get('onHome')} on Home, {dr.get('backOn3D')} back on 3D)")
s2 = t.get("step2") or {}
ok(str(s2.get("title", "")).startswith("2.") and s2.get("atRest", 0) > 70 and s2.get("sliderStart") == 0 and s2.get("sliderEnd", 0) > 70 and s2.get("openPressed") is True,
   f"step 2: the slider's start shuts the case and its end opens it, as playing does (lid {s2.get('atRest')} mm up at rest, {s2.get('sliderStart')} at the start, {s2.get('sliderEnd')} at the end)")
s11, off, again = t.get("step11") or {}, (t.get("step11") or {}).get("off") or {}, (t.get("step11") or {}).get("onAgain") or {}
ok(str(s11.get("title", "")).startswith("11.") and s11.get("seeInside") is True and off.get("lit") is False and off.get("turned") is False and off.get("points", 99) <= 2
   and again.get("lit") is True and again.get("turned") is True and again.get("points", 0) >= 8,
   f"step 11: Play shows the box switching off and starting again (case see-through; while off, at {off.get('at')} s, {off.get('points')} of 9216 picture points move; "
   f"running again, at {again.get('at')} s, {again.get('points')} move)")
ok(t.get("labelsAtStart") is False and t.get("labelsShownAtStart") == 0, f"no labels on the model until they are asked for ({t.get('labelsShownAtStart')} shown at first)")
ok("drawn by eye" in t.get("pointTag", "") and t.get("pointGone") is True, f"the mouse resting on the mic says {t.get('pointTag')!r}, and the name goes when it moves off")
ok(t.get("labelsStored") == "1" and t.get("labelsAfterReload") is True and t.get("labelsButtonAfterReload") == "true" and t.get("labelsBackOff") == "0",
   f"the Labels choice survives a reload (stored {t.get('labelsStored')!r}, after reload {t.get('labelsAfterReload')})")
sl = t.get("slow") or {}
ok(sl.get("modelThereTooSoon") is False and "Loading" in sl.get("loadingSign", "") and sl.get("loadingSignGone") is True,
   f"while the model is on its way the 3D box says so ({sl.get('loadingSign')!r}), and the words go when it is there")
ok(str(sl.get("titleAfterModel", "")).startswith("3."), f"Next pressed three times before the model arrived is kept when it arrives ({sl.get('titleAfterModel')!r})")
ok(sl.get("watchPressedBeforeModel") is True and str(sl.get("watchTitle", "")).startswith("6.") and sl.get("watchPlaying") is True,
   f"'Watch it in 3D' pressed before the model arrived opens its step and plays it ({sl.get('watchTitle')!r}, playing: {sl.get('watchPlaying')})")
ok(not t.get("errors"), f"no script errors while the page was used ({t.get('errors')})")
links = t.get("links", [])
same_tab = [l["href"] for l in links if not l["newTab"]]
ok(len(links) >= 8 and not same_tab, f"{len(links)} outside links, all opening in a new tab" + (f" | these do not: {same_tab}" if same_tab else ""))

if "--links" in sys.argv:
    print("\nAsking each outside link if it still answers...")
    for url in sorted({l["href"] for l in links}):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36"})
            code = urllib.request.urlopen(req, timeout=30).status
        except urllib.error.HTTPError as e:
            code = e.code
        except Exception as e:  # noqa: BLE001
            code = f"no answer ({type(e).__name__})"
        if code in (404, 410):
            ok(False, f"link is dead ({code}): {url}")
        elif code == 200:
            ok(True, f"link answers: {url}")
        else:
            print(f"CAN'T CHECK ({code}; some shops turn away automatic visitors): {url}")

print(f"\n{'ALL PASS' if fails == 0 else str(fails) + ' FAILED'}")
sys.exit(1 if fails else 0)
