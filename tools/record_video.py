"""Record the pitch video: drives the local prototype in a headless browser and writes MP4 clips.

One clip per shot (easy to reorder in an editor) plus the shots joined into one file.
Edit SHOTS below to change the story. Nothing is uploaded; output goes to a git-ignored folder.

Usage:
  .venv/bin/python tools/record_video.py                      # all shots, French
  .venv/bin/python tools/record_video.py --lang en --shots home,manage
  .venv/bin/python tools/record_video.py --audio voice.mp3    # add a narration or music track to the joined file
Setup once: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/playwright install chromium
"""
import argparse, base64, functools, http.server, shutil, subprocess, tempfile, threading
from pathlib import Path

import imageio_ffmpeg
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
FULL_W, FULL_H = 1920, 1080

# A visible pointer: headless recordings have no mouse cursor.
CURSOR_JS = """
addEventListener('DOMContentLoaded', () => {
  const c = document.createElement('div');
  c.style.cssText = 'position:fixed;left:0;top:0;width:22px;height:22px;margin:-11px 0 0 -11px;border-radius:50%;' +
    'background:rgba(20,20,20,.28);border:2px solid rgba(255,255,255,.95);box-shadow:0 0 0 1px rgba(0,0,0,.35);' +
    'z-index:2147483647;pointer-events:none;transform:translate(-100px,-100px);transition:width .12s,height .12s,margin .12s';
  document.body.appendChild(c);
  addEventListener('mousemove', e => c.style.transform = `translate(${e.clientX}px,${e.clientY}px)`, true);
  addEventListener('mousedown', () => { c.style.width = c.style.height = '14px'; c.style.margin = '-7px 0 0 -7px'; }, true);
  addEventListener('mouseup', () => { c.style.width = c.style.height = '22px'; c.style.margin = '-11px 0 0 -11px'; }, true);
});
"""


class Cam:
    """Small helpers so a shot reads like a storyboard."""

    def __init__(self, page, base, lang, start):
        self.page, self.base, self.lang, self.start = page, base, lang, start
        vp = page.viewport_size
        self.x, self.y = vp["width"] * 0.5, vp["height"] * 0.55

    def open(self, view, record=True):
        self.page.goto(f"{self.base}?lang={self.lang}#{view}")
        self.page.wait_for_timeout(800)
        if record:
            self.start()   # recording begins once the shot's first view is on screen

    def open_map(self, min_buildings=1, record=True):
        """Open the 3D tab and start recording only once the map is drawn."""
        self.open("carte", record=False)
        self.page.wait_for_selector("#m3 canvas", timeout=90000)
        self.page.wait_for_function(f"window.__m3 && window.__m3.n >= {min_buildings}", timeout=120000)
        # In a small clip the legend card covers half the map: hide it and the key hints, keep tools and credits.
        self.page.add_style_tag(content=".m3-card,.m3-hint{display:none!important}")
        self.wait(2.5)
        if record:
            self.start()

    def orbit_frames(self, dx, dy, n=180, button="right", there_and_back=True):
        """Turn the 3D map one small step per frame and take a picture of each step: smooth at 30 fps however
        slowly the machine renders. Use instead of start()/drag() (open the map with record=False)."""
        rendered = "() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))"
        self.page.mouse.move(self.x, self.y); self.page.mouse.down(button=button)
        files = []
        for i in range(n + 1):
            k = i / n; k = k * k * (3 - 2 * k)   # ease in and out
            self.page.mouse.move(self.x + dx * k, self.y + dy * k)
            self.page.evaluate(rendered)
            files.append(self.snap())
        self.page.mouse.up(button=button)
        if there_and_back:                       # replay the same pictures backwards: the clip loops without a jump
            for f in reversed(files[:-1]):
                self.snap(file=f)

    def wait(self, seconds):
        self.page.wait_for_timeout(int(seconds * 1000))

    def move(self, selector, seconds=0.7):
        el = self.page.locator(selector).first
        el.scroll_into_view_if_needed()
        b = el.bounding_box()
        tx, ty = b["x"] + b["width"] / 2, b["y"] + b["height"] / 2
        n = max(2, int(seconds * 30))
        for i in range(1, n + 1):
            k = i / n
            k = k * k * (3 - 2 * k)  # ease in and out
            self.page.mouse.move(self.x + (tx - self.x) * k, self.y + (ty - self.y) * k)
            self.page.wait_for_timeout(1000 // 30)
        self.x, self.y = tx, ty

    def click(self, selector, after=0.8):
        self.move(selector)
        self.page.mouse.down(); self.page.wait_for_timeout(90); self.page.mouse.up()
        self.wait(after)

    def scroll(self, pixels, seconds=1.5):
        n = max(2, int(seconds * 30))
        self.page.mouse.move(self.x, self.y)   # the pointer must be over the page, or it shows at the corner
        for _ in range(n):
            self.page.mouse.wheel(0, pixels / n)
            self.page.wait_for_timeout(1000 // 30)

    def drag(self, dx, dy, seconds=2.0, button="left"):
        """Drag from the current pointer position. On the 3D map: left = move, right = turn."""
        n = max(2, int(seconds * 30))
        self.page.mouse.down(button=button)
        for i in range(1, n + 1):
            self.page.mouse.move(self.x + dx * i / n, self.y + dy * i / n)
            self.page.wait_for_timeout(1000 // 30)
        self.page.mouse.up(button=button)
        self.x, self.y = self.x + dx, self.y + dy


# ---- The storyboard. One function per shot; order and selection in SHOTS. ----
def home(c):
    c.open("accueil"); c.wait(2.5)
    c.scroll(500, 2.0); c.wait(1.5)

def manage(c):
    c.open("gestion"); c.wait(2)
    c.click("[data-y='2023']"); c.click("[data-f='fossil']", after=1.5)
    c.click("#sites tbody tr[data-id]", after=3)   # opens the site page

def quality(c):
    c.open("qualite"); c.wait(2)
    c.scroll(700, 2.5); c.wait(1.5)

def citizens(c):
    c.open("citoyens"); c.wait(2)
    c.scroll(600, 2.5); c.wait(1.5)

def map3d(c):
    c.open("carte")
    c.page.wait_for_selector("#m3 canvas", timeout=60000)
    c.page.wait_for_function("window.__m3 && window.__m3.n > 0", timeout=60000)
    c.wait(2)
    c.move("#m3 canvas"); c.drag(260, 40, 3.0); c.wait(1.5)

# Shots for the pitch deck (prototype/pitch/clips/)
def map_rc(c):
    c.open_map(); c.wait(1)
    c.move("#m3 canvas"); c.drag(260, -30, 4.0, "right"); c.wait(0.8); c.drag(-160, 20, 3.0, "right"); c.wait(1.2)

def map_ge(c):
    c.page.evaluate("localStorage.setItem('energiack-map', 'ge')"); c.page.reload()   # the choice is read on load
    c.open_map(min_buildings=1000, record=False); c.wait(1)
    b = c.page.locator("#m3 canvas").bounding_box()
    c.x, c.y = b["x"] + b["width"] * 0.5, b["y"] + b["height"] * 0.5
    c.orbit_frames(300, -20, n=210)              # 7 s one way, 7 s back

def sheet(c):
    c.open_map(); c.wait(0.8)
    c.move("#m3 canvas"); c.drag(200, -25, 2.0, "right"); c.wait(0.8)
    c.page.evaluate("location.hash = '#fiche/S30-B1'")   # the building sheet of the indoor pool
    c.wait(2.2); c.scroll(450, 2.5); c.wait(1.5)

def access(c):
    """Server version with demo logins (--url): each role sees a different menu; the admin manages the accounts."""
    c.open("accueil"); c.wait(1.5)
    c.click("#login-btn", after=2.5)                 # the dialog lists one button per role
    c.click("[data-demo='elu']", after=2.5)
    c.click("#logout-btn", after=1.0)
    c.click("#login-btn", after=1.2)
    c.click("[data-demo='admin']", after=2.0)
    c.click("nav a[data-view='utilisateurs']", after=3.0)

SHOTS = [home, manage, quality, citizens, map3d, map_rc, map_ge, sheet, access]
# -----------------------------------------------------------------------------


def serve(folder):
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a): pass
    handler = functools.partial(Quiet, directory=str(folder))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{srv.server_address[1]}/"


def ffmpeg(*args):
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--lang", default="fr", choices=["fr", "en"])
    ap.add_argument("--shots", help="comma-separated shot names (default: all, in SHOTS order)")
    ap.add_argument("--out", default=str(ROOT / "video-out"), help="output folder (git-ignored)")
    ap.add_argument("--url", help="record a running copy instead of the local prototype/ (e.g. the server version, for logins)")
    ap.add_argument("--audio", help="narration or music file to put on the joined video")
    ap.add_argument("--scheme", default="light", choices=["light", "dark"])
    ap.add_argument("--zoom", type=float, default=1.5, help="page zoom, so text is readable on a projector")
    ap.add_argument("--size", default=f"{FULL_W}x{FULL_H}", help="clip size in pixels, e.g. 1200x900 for a panel beside slide text")
    a = ap.parse_args()
    W, H = (int(v) for v in a.size.split("x"))

    by_name = {f.__name__: f for f in SHOTS}
    shots = [by_name[n] for n in a.shots.split(",")] if a.shots else SHOTS
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    base = a.url or serve(ROOT / "prototype")
    tmp = Path(tempfile.mkdtemp(prefix="rec-"))
    clips = []

    with sync_playwright() as p:
        b = p.chromium.launch(args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        for i, shot in enumerate(shots, 1):
            # The page is laid out at W/zoom and rendered at W x H real pixels: bigger UI, still sharp.
            ctx = b.new_context(viewport={"width": round(W / a.zoom), "height": round(H / a.zoom)},
                                device_scale_factor=a.zoom, color_scheme=a.scheme)
            ctx.add_init_script(CURSOR_JS)
            page = ctx.new_page()
            errs = []
            page.on("pageerror", lambda e: errs.append(str(e)))
            page.goto(f"{base}?lang={a.lang}"); page.wait_for_timeout(600)
            # Capture the browser's own frames (Playwright's recorder is limited to the CSS size, so it is soft).
            fdir = tmp / f"f{i}"; fdir.mkdir()
            frames = []
            cdp = ctx.new_cdp_session(page)
            def on_frame(ev):
                f = fdir / f"{len(frames):06d}.jpg"
                f.write_bytes(base64.b64decode(ev["data"]))
                frames.append((f, ev["metadata"]["timestamp"]))
                cdp.send("Page.screencastFrameAck", {"sessionId": ev["sessionId"]})
            cdp.on("Page.screencastFrame", on_frame)
            started = []
            def start():
                if not started:
                    started.append(1)
                    cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 95, "maxWidth": W, "maxHeight": H})
            clock = [0.0]
            def snap(hold=1 / 30, file=None):   # one still picture as one video frame (frame-by-frame shots)
                if file is None:
                    file = fdir / f"{len(frames):06d}.jpg"
                    page.screenshot(path=str(file), type="jpeg", quality=95)
                frames.append((file, clock[0])); clock[0] += hold
                return file
            cam = Cam(page, base, a.lang, start); cam.snap = snap
            shot(cam)
            page.wait_for_timeout(300)
            cdp.send("Page.stopScreencast")
            ctx.close()
            # Frames only arrive when the picture changes: give each one its real duration.
            lst = fdir / "frames.txt"
            lines = []
            for (f, ts), nxt in zip(frames, frames[1:] + [(None, clock[0] or frames[-1][1] + 0.3)]):
                lines.append(f"file '{f}'\nduration {max(nxt[1] - ts, 0.001):.4f}\n")
            lst.write_text("".join(lines) + f"file '{frames[-1][0]}'\n")
            clip = out / f"{i:02d}-{shot.__name__}-{a.lang}.mp4"
            ffmpeg("-f", "concat", "-safe", "0", "-i", str(lst), "-vf", f"fps=30,scale={W}:{H}:flags=lanczos:out_range=tv,format=yuv420p",
                   "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p",
                   "-movflags", "+faststart", "-an", str(clip))
            clips.append(clip)
            secs = frames[-1][1] - frames[0][1]
            print(f"{clip.name}  {secs:.1f} s, {len(frames)} captured frames" + (f"  JS errors: {errs[:3]}" if errs else ""))
        b.close()

    lst = tmp / "list.txt"
    lst.write_text("".join(f"file '{c.resolve()}'\n" for c in clips))
    final = out / f"pitch-{a.lang}.mp4"
    if a.audio:
        ffmpeg("-f", "concat", "-safe", "0", "-i", str(lst), "-i", a.audio, "-map", "0:v", "-map", "1:a",
               "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", str(final))
    else:
        ffmpeg("-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", "-movflags", "+faststart", str(final))
    shutil.rmtree(tmp, ignore_errors=True)
    print("joined:", final)


if __name__ == "__main__":
    main()
