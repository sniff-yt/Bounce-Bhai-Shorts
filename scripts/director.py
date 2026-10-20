"""Runs the studio desktop (see desktop.sh) like an operator: switches between the terminal, Chrome, the AI Chat,
Voice Studio, Video Editor and YouTube Upload apps, the file manager and the text editor as the job moves through
its stages; feeds the apps real data (out/live/desk/state.js); screenshots the screen for the dashboard."""
import glob, json, os, shutil, subprocess, threading, time, wave

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LIVE = os.path.join(ROOT, "out", "live")
DESK = os.path.join(LIVE, "desk")
REPO = os.environ.get("GITHUB_REPOSITORY", "sniff-yt/Bounce-Bhai-Shorts")
RUN = os.environ.get("GITHUB_RUN_ID", "")
CHROME = next((shutil.which(c) for c in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser") if shutil.which(c)), None)
os.environ["DISPLAY"] = ":99"
try:
    for line in open("/tmp/bb-desktop.env"):
        k, _, v = line.strip().partition("="); os.environ[k] = v
except Exception:
    pass
GEOM = {"terminal": (20, 40, 700, 640), "browser": (300, 30, 960, 700), "files": (380, 120, 760, 520),
        "text": (240, 60, 820, 640), "chat": (180, 30, 900, 720), "voice": (240, 40, 820, 700),
        "editor": (60, 30, 1160, 720), "upload": (140, 40, 1000, 700)}
TITLE = {"terminal": "Terminal — bounce-bhai", "chat": "AI Chat — Bounce Bhai", "voice": "Voice Studio — Bounce Bhai",
         "editor": "Video Editor — Bounce Bhai", "upload": "YouTube Upload — Bounce Bhai"}


def sh(*a, timeout=20):
    try:
        return subprocess.run(a, capture_output=True, text=True, timeout=timeout).stdout.strip()
    except Exception:
        return ""


def find(name):
    t = TITLE.get(name)
    if name == "browser":
        ids = sh("xdotool", "search", "--onlyvisible", "--name", "(Google Chrome|Chromium)$").split()
    elif name == "files":
        ids = sh("xdotool", "search", "--onlyvisible", "--class", "Thunar").split()
    elif name == "text":
        ids = sh("xdotool", "search", "--onlyvisible", "--class", "Mousepad").split()
    else:
        ids = sh("xdotool", "search", "--onlyvisible", "--name", t).split()
    return ids[-1] if ids else ""


def chrome(*args):
    if CHROME:
        subprocess.Popen([CHROME, "--user-data-dir=/tmp/bb-chrome", "--no-first-run", "--no-default-browser-check",
                          "--disable-gpu", "--disable-dev-shm-usage", "--password-store=basic", "--disable-sync",
                          "--disable-features=Translate,MediaRouter,OptimizationHints", "--autoplay-policy=user-gesture-required",
                          "--allow-file-access-from-files", *args], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def launch(name, arg=None):
    x, y, w, h = GEOM[name]
    if name in ("chat", "voice", "editor", "upload"):
        chrome(f"--app=file://{DESK}/app.html?v={name}", f"--window-position={x},{y}", f"--window-size={w},{h}")
    elif name == "browser":
        chrome("--new-window", f"--window-position={x},{y}", f"--window-size={w},{h}", arg or "about:blank")
    elif name == "files":
        subprocess.Popen(["thunar", arg or os.path.join(ROOT, "out")], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif name == "text" and arg:
        subprocess.Popen(["mousepad", arg], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(30):
        time.sleep(0.4)
        wid = find(name)
        if wid:
            sh("xdotool", "windowsize", wid, str(w), str(h)); sh("xdotool", "windowmove", wid, str(x), str(y))
            return wid
    return ""


def focus(name, arg=None):
    """Bring an app to the front (opening it the first time), like clicking it in the taskbar."""
    wid = find(name) or launch(name, arg)
    if wid:
        sh("xdotool", "windowactivate", "--sync", wid, timeout=5); sh("xdotool", "windowraise", wid)
    return wid


def browse(url):
    wid = find("browser")
    if not wid:
        launch("browser", url); return
    focus("browser")
    sh("xdotool", "key", "--window", wid, "ctrl+t"); time.sleep(0.5)
    sh("xdotool", "key", "--window", wid, "ctrl+l"); time.sleep(0.2)
    sh("xdotool", "type", "--delay", "35", url, timeout=60); sh("xdotool", "key", "Return")


# ---------- real data for the apps ----------
_wave_done, _thumb_at, _last_frame = {}, [], None


def story_path():
    c = [p for p in glob.glob(os.path.join(ROOT, "out", "*.json")) if not p.endswith(".render.json")]
    return max(c, key=os.path.getmtime) if c else None


def load(p, default):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return default


def write_state(s):
    global _last_frame
    sp = story_path(); story = load(sp, {}) if sp else {}
    voice = []
    for i, x in enumerate(story.get("sentences") or []):
        if not isinstance(x, dict):
            continue
        v = {"hi": x.get("hi", ""), "en": x.get("en", "")}
        wav = f"{sp[:-5]}_line{i}.wav"
        if os.path.exists(wav):
            png = os.path.join(DESK, f"wave{i}.png")
            if _wave_done.get(i) != os.path.getmtime(wav):
                sh("ffmpeg", "-y", "-loglevel", "error", "-i", wav, "-filter_complex",
                   "showwavespic=s=600x60:colors=0xffffff", "-frames:v", "1", png, timeout=20)
                _wave_done[i] = os.path.getmtime(wav)
            if os.path.exists(png):
                v["wave"] = f"wave{i}.png?{int(_wave_done[i])}"
            try:
                with wave.open(wav) as w:
                    v["dur"] = round(w.getnframes() / w.getframerate(), 2)
            except Exception:
                pass
        voice.append(v)
    frame = os.path.join(LIVE, "frame.jpg"); fr = None
    if os.path.exists(frame):
        m = os.path.getmtime(frame)
        if m != _last_frame:
            _last_frame = m
            shutil.copyfile(frame, os.path.join(DESK, "frame.jpg"))
            n, f = float(s.get("nframes") or 0), float(s.get("frame") or 0)
            if n and (not _thumb_at or f - _thumb_at[-1] >= n / 14) and len(_thumb_at) < 16:
                shutil.copyfile(frame, os.path.join(DESK, f"th{len(_thumb_at)}.jpg")); _thumb_at.append(f)
        fr = f"frame.jpg?{int(m * 10)}"
    posted = next((e["text"].split("Posted: ", 1)[1] for e in reversed(s.get("events") or [])
                   if e.get("text", "").startswith("Posted: https://youtube.com/shorts/") and len(e["text"]) > 44), None)
    st = {"status": {k: s.get(k) for k in ("stage", "pct", "frame", "nframes", "window", "state")},
          "llm": load(os.path.join(LIVE, "llm.json"), []), "story": {"title": story.get("title"), "hook": story.get("hook")},
          "voice": voice, "frame": fr, "thumbs": [f"th{k}.jpg" for k in range(len(_thumb_at))],
          "upload": s.get("upload") or {}, "posted": posted}
    tmp = os.path.join(DESK, "state.tmp.js")
    open(tmp, "w", encoding="utf-8").write("STATE(" + json.dumps(st, ensure_ascii=False) + ");")
    os.replace(tmp, os.path.join(DESK, "state.js"))
    return sp, posted


def status():
    return load(os.path.join(LIVE, "status.json"), {})


def scene(s, posted):
    w, st = (s.get("window") or "").lower(), (s.get("stage") or "").lower()
    if posted:
        return "posted"
    for key, words in (("upload", ("upload", "youtube")), ("polish", ("caption", "polish", "music")),
                       ("animate", ("anim", "render", "cartoon")), ("voice", ("voice",)), ("story", ("story",))):
        if any(k in st for k in words) and ("make_short" in w or key != "story" or "story" in st):
            if key == "voice" and "unlock" in st:
                continue
            return key
    if "skia" in w: return "skia"
    if "torch" in w or "pip" in w: return "pip"
    if "blender" in w: return "blender"
    if "apt" in w: return "apt"
    return "start"


URL = {"start": f"https://github.com/{REPO}/actions/runs/{RUN}" if RUN else f"https://github.com/{REPO}",
       "apt": "https://packages.ubuntu.com/noble/ffmpeg", "blender": "https://download.blender.org/release/",
       "pip": "https://pypi.org/project/chatterbox-tts/", "skia": "https://pypi.org/project/skia-python/"}


def shoot():
    tmp = os.path.join(LIVE, "screen.tmp.jpg")
    sh("import", "-silent", "-window", "root", "-resize", "1024x640", "-quality", "68", tmp)
    if os.path.exists(tmp) and os.path.getsize(tmp) > 1000:
        os.replace(tmp, os.path.join(LIVE, "screen.jpg"))


SHARED = {"sp": None, "posted": None, "s": {}}


def feeder():
    """Real data for the apps every second, a screenshot every 2.5 s, never blocked by window switching."""
    last_shot = 0
    while True:
        try:
            s = status()
            SHARED["s"] = s
            SHARED["sp"], SHARED["posted"] = write_state(s)
            if time.time() - last_shot > 2.5:
                last_shot = time.time(); shoot()
        except Exception as e:
            print("feeder:", e, flush=True)
        time.sleep(1)


def main():
    threading.Thread(target=feeder, daemon=True).start()
    time.sleep(1.5)
    cur, since, story_seen, glance = None, 0, None, 0
    while True:
        try:
            s, sp, posted = SHARED["s"], SHARED["sp"], SHARED["posted"]
            now = time.time()
            sc = scene(s, posted)
            if sc != cur:
                cur, since, glance = sc, now, 0
                if sc in URL:
                    browse(URL[sc]); time.sleep(4); focus("terminal")
                elif sc == "story":
                    focus("chat")
                elif sc == "voice":
                    focus("voice")
                elif sc in ("animate", "polish"):
                    focus("editor")
                elif sc == "upload":
                    focus("upload")
                elif sc == "posted":
                    focus("upload"); time.sleep(4); browse(posted)
            t = now - since
            # the script just came back from the AI: open it in the text editor, then the project folder
            if sc in ("story", "voice") and sp and sp != story_seen and t > 3:
                story_seen = sp
                time.sleep(10 if sc == "story" else 2); focus("text", sp); time.sleep(7); focus("files", os.path.join(ROOT, "out")); time.sleep(4)
                focus("voice" if sc == "voice" else "chat")
            # keep switching apps the way a person would
            elif t > 30 and now - glance > 30:
                glance = now
                peek = {"voice": "files", "animate": "terminal", "polish": "terminal", "apt": "browser", "pip": "browser",
                        "blender": "browser", "skia": "browser", "start": "browser", "story": "terminal"}.get(sc)
                back = {"voice": "voice", "animate": "editor", "polish": "editor", "story": "chat"}.get(sc, "terminal")
                if peek:
                    focus(peek); time.sleep(5); focus(back)
        except Exception as e:
            print("director:", e, flush=True)
        time.sleep(0.5)


if __name__ == "__main__":
    main()
