"""Checks the guide page against the Scope 2 list (exit 1 on any miss): touch sizes, label size, no scroll hijack,
real links that open in a new tab, totals that match the noise-logger totals script, steps complete, no personal details."""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
html = (ROOT / "index.html").read_text(encoding="utf-8")
app = (ROOT / "js" / "app.js").read_text(encoding="utf-8")
viewer = (ROOT / "js" / "viewer.js").read_text(encoding="utf-8")
fails = 0


def ok(cond, msg):
    global fails
    print(("PASS " if cond else "FAIL ") + msg)
    fails += 0 if cond else 1


css = re.search(r"<style>(.*?)</style>", html, re.S).group(1)
btn = re.search(r"\.btn\{[^}]*min-height:(\d+)px", css)
ok(btn and int(btn.group(1)) >= 44, f"buttons at least 44 px tall (found {btn.group(1) if btn else None})")
nav = re.search(r"nav\.tabs a\{[^}]*min-height:(\d+)px", css)
ok(nav and int(nav.group(1)) >= 44, f"bottom tabs at least 44 px tall (found {nav.group(1) if nav else None})")
lab = re.search(r"\.vlabel\{[^}]*font-size:(\d+)px", css)
ok(lab and int(lab.group(1)) >= 13, f"3D labels at least 13 px (found {lab.group(1) if lab else None})")
none_rules = re.findall(r"([^{}]+)\{[^}]*touch-action:none", css)
ok(all("grabbed" in r for r in none_rules), f"touch-action:none only after 'Move the model' is pressed ({[r.strip() for r in none_rules]})")
ok("controls.enabled = false" in viewer, "3D controls start OFF, so the page scrolls normally")
ok(html.count("</html>") == 1, "exactly one </html>")
ok('aria-pressed' in html and 'Auto-spin' in html, "toggle buttons show a pressed state; 'Auto-spin' wording")
ok('href="#build"' in html and "Start the build" in html, "'Start the build' button jumps to the steps")

buy = json.loads(re.search(r'id="buy-data">(.*?)</script>', html, re.S).group(1))
ok(all(l["url"].startswith("https://") for l in buy["lines"]), f"all {len(buy['lines'])} parts have a real https link")
ok('target="_blank" rel="noopener"' in app, "shop links open in a new tab")
ok(all(l.get("model") and l.get("shop") for l in buy["lines"]), "every part card has a model number and a shop")
total = round(sum(l["price"] for l in buy["lines"]) * (1 + buy["gst"]), 2)
totals_py = Path.home() / "noise-logger" / "scripts" / "totals.py"
out = subprocess.run([sys.executable, str(totals_py)], capture_output=True, text=True).stdout
m = re.search(r"PLAN-2GB .*?\n\s+parts\s+[\d.]+\s+GST\s+[\d.]+\s+total\s+([\d.]+)", out)
ok(m and abs(float(m.group(1)) - total) < 0.005, f"page total ${total:.2f} matches totals.py PLAN-2GB (${m.group(1) if m else '?'})")

steps = json.loads(re.search(r'id="steps-data">(.*?)</script>', html, re.S).group(1))
ok(len(steps) == 12 and all(s["check"] and s["actions"] for s in steps), f"{len(steps)} steps, each with actions and a 'check it worked'")
ok([s["n"] for s in steps if s["tested"]] == [0], "only the step actually done (step 0, laptop) is marked Tested")

public = [ROOT / "index.html", ROOT / "js" / "app.js", ROOT / "js" / "viewer.js", ROOT / "README.md"]
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
