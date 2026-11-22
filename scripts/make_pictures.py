"""Takes the 12 step pictures (images/steps/step-N.jpg) from the 3D model with headless Chrome.
Run after make_parts.py or after steps change order:  python scripts/make_pictures.py   (needs: pillow, Chrome)"""
import functools
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


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def shot(url, out, size="660,420"):
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as prof:
        subprocess.run([CHROME, "--headless=new", "--hide-scrollbars", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", f"--user-data-dir={prof}",
                        "--no-first-run", f"--window-size={size}", "--virtual-time-budget=14000", f"--screenshot={out}", url], capture_output=True, timeout=120)


def main():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(ROOT)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    steps = json.loads(re.search(r'id="steps-data">(.*?)</script>', (ROOT / "index.html").read_text(encoding="utf-8"), re.S).group(1))
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        for s in steps:
            png = Path(tmp) / f"{s['n']}.png"
            shot(f"http://127.0.0.1:{srv.server_port}/checks/step-picture.html?step={s['n']}&mode=nolabels", png)
            im = Image.open(png).convert("RGB").crop((0, 0, 640, 388))
            colours = len(im.resize((80, 48)).getcolors(10000) or [])
            assert colours > 40, f"step {s['n']}: the picture looks empty ({colours} colours)"
            im.save(ROOT / "images" / "steps" / f"step-{s['n']}.jpg", quality=86)
            print(f"step {s['n']}: saved ({colours} colours)")
    srv.shutdown()


if __name__ == "__main__":
    main()
