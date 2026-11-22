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
ok('aria-pressed' in html and 'Auto-spin' in html and 'id="ring"' in html and 'data-printed=' in html, "pressed states, 'Auto-spin', progress ring and print ticks present")
ok('id="next-go"' in html and 'data-tab="build"' in html, "Home's 'Go to Step N' button and a Build tab")

buy = json.loads(re.search(r'id="buy-data">(.*?)</script>', html, re.S).group(1))
ok(all(l["url"].startswith("https://") for l in buy["lines"]), f"all {len(buy['lines'])} parts have a real https link")
ok('target = "_blank"' in app and 'rel = "noopener"' in app, "shop links open in a new tab")
ok(all(l.get("model") and l.get("shop") for l in buy["lines"]), "every part card has a model number and a shop")
total = round(sum(l["price"] for l in buy["lines"]) * (1 + buy["gst"]), 2)
totals_py = Path.home() / "noise-logger" / "scripts" / "totals.py"
out = subprocess.run([sys.executable, str(totals_py)], capture_output=True, text=True).stdout
m = re.search(r"PLAN-2GB .*?\n\s+parts\s+[\d.]+\s+GST\s+[\d.]+\s+total\s+([\d.]+)", out)
ok(m and abs(float(m.group(1)) - total) < 0.005, f"page total ${total:.2f} matches totals.py PLAN-2GB (${m.group(1) if m else '?'})")

steps = json.loads(re.search(r'id="steps-data">(.*?)</script>', html, re.S).group(1))
ok(len(steps) == 12 and all(s["check"] and s["actions"] for s in steps), f"{len(steps)} steps, each with actions and a 'check it worked'")
ok([s["n"] for s in steps if s["tested"]] == [0], "only the step actually done (step 0, laptop) is marked Tested")

# ---- every step can be followed as written (audit B-01 to B-05, A-02 to A-05) ----
T = {s["n"]: " ".join([s["title"]] + s["actions"] + [s.get("warn", ""), s["check"]] + s.get("tools", [])) for s in steps}
by_title = {s["title"]: s["n"] for s in steps}
mount = next((n for t, n in by_title.items() if t.startswith("Mount the mic")), 99)
quiet = next((n for t, n in by_title.items() if "quiet-room" in t), -1)


def has(n, *words):
    miss = [w for w in words if w not in T.get(n, "")]
    ok(not miss, f"step {n}: {', '.join(w[:38] for w in words)}" + (f" | MISSING {miss}" if miss else ""))


has(0, r".venv\Scripts\python -m pytest")
has(1, "2GB board only", "64 GB", "4 pairs", "shipping")
has(3, "85 × 56", "16.4", "14.6", "12.8 × 7.0", "clicks", "cable comes out", "base")
has(5, "card reader", "Localisation", "SSH")
has(6, "thermal pads", "FAN", "8 mm", "10 mm", "straight down")
has(7, "yes", "password", "free -h", "0x0")
has(8, "git archive", r"scp ..\noise-logger.tgz", "tar xzf", "bash deploy/install.sh")
ok(0 < mount < quiet, f"the mic is mounted (step {mount}) before its level and the quiet room are measured (step {quiet})")
has(mount, "both cables", "rubbing alcohol" if "rubbing alcohol" in T.get(mount, "") else "Rubbing alcohol", "zip tie", "side by side")
has(quiet, "arecord -l", "mic_name='USB'", ".venv/bin/python -m noise_logger --calibrate", "gain knob", "systemctl enable --now noise-logger noise-logger-web noise-logger-nightly.timer")
has(11, "http://noise-logger.local:8080", "hostname -I")
labels = json.loads(re.search(r'id="label-steps">(.*?)</script>', html, re.S).group(1))
ok(labels["mic_cradle"] == mount and labels["mic"] == quiet, f"3D labels point to the right steps (holder {labels['mic_cradle']}, mic {labels['mic']})")
ok(all((ROOT / "images" / "steps" / f"step-{s['n']}.jpg").exists() for s in steps), "a picture for every step")
ok('id="tools"' in html and "zip ties" in html and "s.tools" in app, "the small things are listed on the Buy page and in each step's 'You will need'")
ok("plus PiShop shipping" in html and "PiShop shipping is extra" in app, "both totals say PiShop shipping is extra")
ok(not any(re.fullmatch(r"B0[0-9A-Z]{8}", l["model"]) for l in buy["lines"]), "every card shows the maker's model number, not only Amazon's")
classic = (ROOT / "classic.html").read_text(encoding="utf-8")
for block in ("buy-data", "steps-data", "model-labels", "label-steps"):
    get = lambda t: json.loads(re.search(rf'id="{block}">(.*?)</script>', t, re.S).group(1))
    ok(get(html) == get(classic), f"the classic page carries the same {block}")

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
