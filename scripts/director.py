"""Drives the real studio desktop (see desktop.sh): opens Chrome, types URLs like an agent as the job moves
through its stages, renders a local studio page (story + frames), and screenshots the screen for the dashboard."""
import html, json, os, glob, shutil, subprocess, time

os.environ["DISPLAY"] = ":99"
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LIVE = os.path.join(ROOT, "out", "live")
DESK = os.path.join(LIVE, "desk")
REPO = os.environ.get("GITHUB_REPOSITORY", "sniff-yt/Bounce-Bhai-Shorts")
RUN = os.environ.get("GITHUB_RUN_ID", "")
CHROME = shutil.which("google-chrome") or shutil.which("google-chrome-stable") or shutil.which("chromium") or shutil.which("chromium-browser")
STUDIO = "file://" + os.path.join(DESK, "studio.html")


def sh(*a, timeout=20):
    try:
        return subprocess.run(a, capture_output=True, text=True, timeout=timeout).stdout.strip()
    except Exception:
        return ""


def status():
    try:
        with open(os.path.join(LIVE, "status.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def scene(s):
    w, st = (s.get("window") or "").lower(), (s.get("stage") or "").lower()
    ev = " ".join(e.get("text", "") for e in (s.get("events") or [])[-2:]).lower()
    posted = next((e["text"].split("Posted: ", 1)[1] for e in reversed(s.get("events") or [])
                   if e.get("text", "").startswith("Posted: https://youtube.com/shorts/") and len(e["text"]) > 44), None)
    if posted:
        return "posted", posted
    if "upload" in st or "youtube" in st:
        return "upload", "https://www.youtube.com/@bouncebhaiofficial/shorts"
    if "make_short" in w or any(k in st for k in ("story", "voice", "anim", "render", "caption", "polish", "music")):
        return "studio", STUDIO
    if "skia" in w:
        return "skia", "https://pypi.org/project/skia-python/"
    if "torch" in w or "pip" in w:
        return "pip", "https://pypi.org/project/chatterbox-tts/"
    if "blender" in w or "blender" in ev:
        return "blender", "https://download.blender.org/release/"
    if "apt" in w:
        return "apt", "https://packages.ubuntu.com/noble/ffmpeg"
    return "run", f"https://github.com/{REPO}/actions/runs/{RUN}" if RUN else f"https://github.com/{REPO}/actions"


def studio_page(s):
    os.makedirs(DESK, exist_ok=True)
    stories = sorted((p for p in glob.glob(os.path.join(ROOT, "out", "*.json")) if not p.endswith(".render.json")),
                     key=os.path.getmtime)
    story = {}
    if stories:
        try:
            story = json.load(open(stories[-1], encoding="utf-8"))
        except Exception:
            story = {}
    frame = os.path.join(LIVE, "frame.jpg")
    has_frame = os.path.exists(frame) and s.get("frame")
    if has_frame:
        shutil.copyfile(frame, os.path.join(DESK, "frame.jpg"))
    stage = html.escape(s.get("stage") or "Starting")
    lines = "".join(
        f"<li><b>{html.escape(x.get('hi',''))}</b><span>{html.escape(x.get('en',''))}</span></li>"
        for x in (story.get("sentences") or []) if isinstance(x, dict))
    title = html.escape(story.get("title") or story.get("hook") or "Writing today's story…")
    pct = s.get("pct") or 0
    right = (f"<img src='frame.jpg?{int(time.time())}'><p>Frame {s.get('frame')} of {s.get('nframes')}</p>" if has_frame
             else "<div class='ph'>The cartoon appears here once animation starts</div>")
    page = f"""<!doctype html><meta charset=utf-8><meta http-equiv=refresh content=2><title>Bounce Bhai Studio — {stage}</title>
<style>body{{margin:0;font:14px/1.45 'DejaVu Sans',sans-serif;background:#FBF7F1;color:#1c1a17;display:flex;gap:16px;padding:16px;height:100vh;box-sizing:border-box}}
.l{{flex:1;overflow:hidden}}h1{{font-size:18px;margin:0 0 4px}}.st{{color:#FF6A3D;font-weight:700;margin-bottom:8px}}
.bar{{height:6px;background:#eadfd2;border-radius:9px;margin-bottom:12px}}.bar i{{display:block;height:100%;width:{pct}%;background:#FF6A3D;border-radius:9px}}
ol{{padding-left:18px;margin:0}}li{{margin:0 0 8px}}li b{{display:block}}li span{{color:#7a7368;font-size:12px}}
.r{{width:230px;flex:none;text-align:center}}.r img{{width:230px;border-radius:12px;box-shadow:0 8px 20px rgba(0,0,0,.2)}}
.ph{{width:230px;aspect-ratio:9/16;border-radius:12px;background:#14120f;color:#8b857b;display:grid;place-items:center;padding:20px;box-sizing:border-box}}
.r p{{color:#7a7368;font-size:12px}}</style>
<div class=l><div class=st>{stage}</div><div class=bar><i></i></div><h1>{title}</h1><ol>{lines}</ol></div><div class=r>{right}</div>"""
    tmp = os.path.join(DESK, "studio.tmp.html")
    open(tmp, "w", encoding="utf-8").write(page)
    os.replace(tmp, os.path.join(DESK, "studio.html"))


def chrome_win():
    out = sh("xdotool", "search", "--onlyvisible", "--class", "google-chrome") or sh("xdotool", "search", "--onlyvisible", "--class", "chromium")
    return out.splitlines()[-1] if out else ""


def go(url, new_tab=True):
    w = chrome_win()
    if not w:
        if not CHROME:
            return
        subprocess.Popen([CHROME, "--user-data-dir=/tmp/bb-chrome", "--no-first-run", "--no-default-browser-check",
                          "--disable-gpu", "--disable-dev-shm-usage", "--password-store=basic", "--disable-sync",
                          "--disable-features=Translate,MediaRouter,OptimizationHints", "--autoplay-policy=user-gesture-required",
                          "--allow-file-access-from-files", "--window-position=500,8", "--window-size=772,750", url],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    sh("xdotool", "windowactivate", "--sync", w)
    if new_tab:
        sh("xdotool", "key", "--window", w, "ctrl+t")
        time.sleep(0.4)
    sh("xdotool", "key", "--window", w, "ctrl+l")
    time.sleep(0.2)
    sh("xdotool", "type", "--delay", "35", url, timeout=60)
    sh("xdotool", "key", "Return")


def shoot():
    tmp = os.path.join(LIVE, "screen.tmp.jpg")
    sh("import", "-silent", "-window", "root", "-resize", "1024x640", "-quality", "68", tmp)
    if os.path.exists(tmp) and os.path.getsize(tmp) > 1000:
        os.replace(tmp, os.path.join(LIVE, "screen.jpg"))


def main():
    cur, last_shot, last_page = None, 0, 0
    while True:
        try:
            s = status()
            if s.get("state") in ("ok", "failed") and cur == "posted":
                pass
            now = time.time()
            if now - last_page > 2:
                last_page = now
                studio_page(s)
            name, url = scene(s)
            if name != cur:
                same_tab = cur == "studio" and name == "studio"
                cur = name
                go(url, new_tab=not same_tab)
                time.sleep(1.5)
            if now - last_shot > 2.5:
                last_shot = now
                shoot()
        except Exception as e:
            print("director:", e, flush=True)
        time.sleep(0.5)


if __name__ == "__main__":
    main()
