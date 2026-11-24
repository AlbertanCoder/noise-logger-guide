"""Takes the 12 step pictures (images/steps/step-N.jpg) from the 3D model with headless Chrome.
Run after make_parts.py or after steps change order:  python scripts/make_pictures.py   (needs: pillow, Chrome)"""
import functools
import hashlib
import http.server
import json
import re
import subprocess
import tempfile
import threading
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
AT = {6: "&at=0.5"}   # step 6's picture is taken half way through its animation: the Pi in the base, the frame on its way down


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def shot(url, out, size="660,420"):
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as prof:
        subprocess.run([CHROME, "--headless=new", "--hide-scrollbars", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", f"--user-data-dir={prof}",
                        "--no-first-run", f"--window-size={size}", "--virtual-time-budget=14000", f"--screenshot={out}", url], capture_output=True, timeout=120)


def fingerprint(*names):
    h = hashlib.sha256()
    for n in names:
        h.update((ROOT / n).read_bytes().replace(b"\r\n", b"\n"))
    return h.hexdigest()[:8]


# file -> (the text in it that carries a fingerprint, the files the fingerprint is of); each one builds on the one before
STAMPS = [("js/viewer.js", r'(const MODEL_V = ")[0-9a-f]{8}(")', ("models/noise-logger.glb", "models/colors.json", "models/numbers.json")),
          ("js/app2.js", r'(js/viewer\.js\?v=)[0-9a-f]{8}(")', ("js/viewer.js",)),
          ("index.html", r'(js/app2\.js\?v=)[0-9a-f]{8}(")', ("js/app2.js",))]


def stamp():
    """Writes each file's fingerprint into the address it is loaded by, so a browser never shows a saved old copy after an update."""
    for name, pattern, of in STAMPS:
        text = (ROOT / name).read_text(encoding="utf-8")
        new, n = re.subn(pattern, lambda m: m.group(1) + fingerprint(*of) + m.group(2), text)
        assert n == 1, f"{name}: fingerprint place not found"
        if new != text:
            (ROOT / name).write_text(new, encoding="utf-8")


def main():
    stamp()
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(ROOT)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    steps = json.loads(re.search(r'id="steps-data">(.*?)</script>', (ROOT / "index.html").read_text(encoding="utf-8"), re.S).group(1))
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        for s in steps:
            png = Path(tmp) / f"{s['n']}.png"
            for attempt in range(3):   # now and then the hidden browser takes its picture before the model is drawn: try again
                shot(f"http://127.0.0.1:{srv.server_port}/checks/step-picture.html?step={s['n']}&mode=nolabels" + AT.get(s["n"], ""), png)
                im = Image.open(png).convert("RGB").crop((0, 0, 640, 388))
                colours = len(im.resize((80, 48)).getcolors(10000) or [])
                if colours > 40:
                    break
            assert colours > 40, f"step {s['n']}: the picture looks empty after 3 tries ({colours} colours)"
            im.save(ROOT / "images" / "steps" / f"step-{s['n']}.jpg", quality=86)
            print(f"step {s['n']}: saved ({colours} colours)")
    srv.shutdown()


if __name__ == "__main__":
    main()
