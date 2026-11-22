"""Checks the guide page against the Scope 2 list (exit 1 on any miss): touch sizes, label size, no scroll hijack,
real links that open in a new tab, totals that match the noise-logger totals script, steps complete, no personal details."""
import json
import re
import subprocess
import sys
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

buy = json.loads(re.search(r'id="buy-data">(.*?)</script>', html, re.S).group(1))
ok(all(l["url"].startswith("https://") for l in buy["lines"]), f"all {len(buy['lines'])} parts have a real https link")
ok('target = "_blank"' in app and 'rel = "noopener"' in app, "shop links open in a new tab")
ok(all(l.get("model") and l.get("shop") for l in buy["lines"]), "every part card has a model number and a shop")
total = round(sum(l["price"] for l in buy["lines"]) * (1 + buy["gst"]), 2)
totals_py = Path.home() / "noise-logger" / "scripts" / "totals.py"
out = subprocess.run([sys.executable, str(totals_py)], capture_output=True, text=True).stdout
m = re.search(r"PLAN-UMIK .*?\n\s+parts\s+[\d.]+\s+GST\s+[\d.]+\s+total\s+([\d.]+)", out)
ok(m and abs(float(m.group(1)) - total) < 0.005, f"page total ${total:.2f} matches totals.py PLAN-UMIK (${m.group(1) if m else '?'})")

steps = json.loads(re.search(r'id="steps-data">(.*?)</script>', html, re.S).group(1))
ok(len(steps) == 12 and all(s["check"] and s["actions"] for s in steps), f"{len(steps)} steps, each with actions and a 'check it worked'")
ok([s["n"] for s in steps if s["tested"]] == [0], "only the step actually done (step 0, laptop) is marked Tested")

# ---- every step can be followed as written (audit B-01 to B-05, A-02 to A-05) ----
T = {s["n"]: " ".join([s["title"]] + s["actions"] + [s.get("warn", ""), s["check"]] + s.get("tools", [])) for s in steps}
by_title = {s["title"]: s["n"] for s in steps}
mount = next((n for t, n in by_title.items() if "high shelf" in t), 99)
quiet = next((n for t, n in by_title.items() if "Quiet-room" in t), -1)


def has(n, *words):
    miss = [w for w in words if w not in T.get(n, "")]
    ok(not miss, f"step {n}: {', '.join(w[:38] for w in words)}" + (f" | MISSING {miss}" if miss else ""))


has(0, r".venv\Scripts\python -m pytest")
has(1, "2GB board only", "64 GB", "UMIK-2", "return policy", "shipping")
has(2, "serial number")
has(3, "--list-devices", "mic_name='umik'", "--calibrate", "--run", "9 of every 10", "return the mic")
has(4, "calibration", "serial number")
has(5, "card reader", "Localisation", "SSH")
has(6, "heatsink", "FAN", "plastic tab", "feet", "button")
has(7, "yes", "password", "free -h", "0x0")
has(8, "git archive", r"scp ..\noise-logger.tgz", "tar xzf", "bash deploy/install.sh")
ok(0 < mount < quiet, f"the mic is placed (step {mount}) before the quiet room is measured (step {quiet})")
has(mount, "1.5 m", "1.2 m", "at least 1 m", "all directions")
has(quiet, "arecord -l", "mic_name='umik'", ".venv/bin/python -m noise_logger --calibrate", "systemctl enable --now noise-logger noise-logger-web noise-logger-nightly.timer")
has(11, "http://noise-logger.local:8080", "hostname -I")
labels = json.loads(re.search(r'id="label-steps">(.*?)</script>', html, re.S).group(1))
ok(all(1 <= n <= 11 for n in labels.values()) and labels["shelf"] == mount, "3D labels point to real steps")
ok(all((ROOT / "images" / "steps" / f"step-{s['n']}.jpg").exists() for s in steps), "a picture for every step")
ids = {l["id"] for l in buy["lines"]}
ok(ids == {"pi", "psu", "case", "sd", "mic"} and all(set(s["parts"]) <= ids | {"all"} for s in steps), f"the 5 chosen parts, and steps only use those ({sorted(ids)})")
stale = [w for w in ("FIFINE", "K669", "Active Cooler", "Command Large", "M2.5", "case_base.stl", "mic_cradle", 'data-tab="print"', "zip tie", "Print files") if w.lower() in (html + app + viewer).lower()]
ok(not stale, f"nothing left from the old parts list ({stale})")
ok("PiShop and Solen shipping" in html and "PiShop and Solen shipping are extra" in app, "both totals say shipping is extra")
ok("honest dated record" in html and all(w in html for w in ("legal sound meter", "Know whose noise", "Keep conversations", "Play any sound", "Decibel estimates", "Short thump clips", "learns whose noise", "portfolio piece", "sleep record", "next door")), "Home says what it is for, does, does not, and later (agreed 2026-11-22)")
ok("not run on a Pi yet" in html and "Waiting for a second audit" in html, "Home and Buy say what is unproven")
ok("url=index.html" in (ROOT / "classic.html").read_text(encoding="utf-8"), "the classic page only forwards to the guide")

public = [ROOT / "index.html", ROOT / "classic.html", ROOT / "js" / "app.js", ROOT / "js" / "app2.js", ROOT / "js" / "viewer.js", ROOT / "README.md"]
# generic words here; personal words come from a private file that is never published
words = ["@gmail", "neighbou?r", "upstairs", "kids", "landlord", "street", "ssid", "wi-?fi password"]
private = Path.home() / "noise-logger" / "private-words.txt"
if private.exists():
    words += [w.strip() for w in private.read_text(encoding="utf-8").splitlines() if w.strip()]
ok(private.exists(), "private word list found (personal names/handles to keep out)")
bad = re.compile("|".join(words), re.I)
hits = [(p.name, m.group(0)) for p in public if p.exists() for m in bad.finditer(p.read_text(encoding="utf-8"))]
ok(not hits, f"no personal details in the public files ({hits})")
print(f"\n{'ALL PASS' if fails == 0 else str(fails) + ' FAILED'}")
sys.exit(1 if fails else 0)
