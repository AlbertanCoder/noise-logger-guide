"""Checks the guide page (exit 1 on any miss).
Part 1 reads the files: links, totals that match the noise-logger totals script, steps complete, wording, no personal details.
Part 2 opens the real page in a browser at phone width (checks/selftest.html) and measures what is drawn: sizes, pictures, 3D buttons.
Run:  python scripts/check_page.py            (add --links to also ask each shop and source link if it still answers)"""
import functools
import html as htmllib
import http.server
import json
import re
import subprocess
import sys
import tempfile
import threading
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
none_rules = re.findall(r"([^{}]+)\{[^}]*touch-action:none", css)
ok(all("grabbed" in r for r in none_rules), f"touch-action:none only after 'Move the model' is pressed ({[r.strip() for r in none_rules]})")
ok("ONE: grabbed ? THREE.TOUCH.ROTATE : null" in viewer and "stopPropagation" in viewer, "one finger and the mouse wheel scroll the page until 'Move the model'")
ok("touch-action: pan-x pan-y" in html and "gesturestart" in html and "user-scalable=no" in html, "the page itself never zooms (pinch or double-tap, iPhone included)")
ok(html.count("</html>") == 1, "exactly one </html>")
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
ok("plus PiShop shipping" in html and "PiShop shipping is extra" in app and "Solen shipping" not in html + app, "both totals say shipping is extra")
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
ok(len(t.get("explodedLabels", [])) == 5, f"Exploded view: all 5 labels are inside the picture, lid included ({t.get('explodedLabels')})")
ok(str(t.get("step5Title", "")).startswith("5.") and t.get("step5SolidRed", 100) < 2, f"stepping to step 5 ghosts the case so the card shows ({t.get('step5SolidRed')}% of the picture is still solid red)")
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
