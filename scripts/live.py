#!/usr/bin/env python3
"""Live progress feed for the web dashboard (docs/index.html).

Everything lands in out/live/: status.json (stage, progress, recent events) and frame.jpg
(latest rendered frame).  scripts/live_push.sh force-pushes that folder to the `live` branch
every few seconds while a run is going, and the dashboard polls it.

CLI:   python scripts/live.py stage "Writing the story" [--pct 5]
       python scripts/live.py event "Story: Hummingbird ka dil"
       python scripts/live.py set key=value ...
       python scripts/live.py done ok|failed
Import: from live import update, event, frame
"""
import json, os, sys, time

DIR = os.environ.get("BB_LIVE_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "out", "live"))
PATH = os.path.join(DIR, "status.json")
_last_frame = [0.0]


def _load():
    try:
        return json.load(open(PATH, encoding="utf-8"))
    except Exception:
        return {"events": []}


def _save(s):
    os.makedirs(DIR, exist_ok=True)
    s["updated"] = time.time()
    s["run_id"] = os.environ.get("GITHUB_RUN_ID", s.get("run_id"))
    tmp = PATH + ".tmp"
    json.dump(s, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
    os.replace(tmp, PATH)


def update(**kw):
    try:
        s = _load(); s.update(kw); _save(s)
    except Exception as e:  # the feed must never break a render
        print("live: update failed:", e, flush=True)


def event(text, **kw):
    try:
        s = _load()
        s.setdefault("events", []).append({"t": time.time(), "text": str(text)[:200]})
        s["events"] = s["events"][-40:]
        s.update(kw); _save(s)
    except Exception as e:
        print("live: event failed:", e, flush=True)


def frame(img, i=None, n=None, every=2.0):
    """Save a small JPEG of a PIL image at most every `every` seconds."""
    now = time.time()
    if now - _last_frame[0] < every:
        return
    _last_frame[0] = now
    try:
        os.makedirs(DIR, exist_ok=True)
        small = img.copy(); small.thumbnail((432, 768))
        small.convert("RGB").save(os.path.join(DIR, "frame.tmp.jpg"), quality=72)
        os.replace(os.path.join(DIR, "frame.tmp.jpg"), os.path.join(DIR, "frame.jpg"))
        if i is not None and n:
            update(frame=i, nframes=n, pct=round(40 + 45 * i / n, 1))
    except Exception as e:
        print("live: frame failed:", e, flush=True)


def tee(title):
    """Pass stdin through to stdout and mirror it into the dashboard console (last 80 lines).
    Handles \r progress bars (pip, Hugging Face downloads) by rewriting the current line."""
    import re
    ansi = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
    lines, cur, last, inbar = [], "", 0.0, False
    try:
        s = _load(); lines = s.get("console", []) or []
    except Exception:
        pass
    lines.append(f"$ {title}")
    update(console=lines[-80:], window=title)
    out = sys.stdout.buffer
    while True:
        chunk = sys.stdin.buffer.read1(4096) if hasattr(sys.stdin.buffer, "read1") else sys.stdin.buffer.read(4096)
        if not chunk:
            break
        out.write(chunk); out.flush()
        for ch in ansi.sub("", chunk.decode("utf-8", "replace")):
            if ch == "\n":
                if cur.strip():
                    if inbar and lines and lines[-1].startswith("\u21bb "):
                        lines[-1] = "\u2713 " + cur[:156]
                    else:
                        lines.append(cur[:160])
                cur, inbar = "", False
            elif ch == "\r":
                if cur.strip():
                    if lines and lines[-1].startswith("\u21bb "):
                        lines[-1] = "\u21bb " + cur[:156]
                    else:
                        lines.append("\u21bb " + cur[:156])
                    inbar = True
                cur = ""
            else:
                cur += ch
        now = time.time()
        if now - last > 0.7:
            last = now
            update(console=[l for l in lines if not l.startswith("::")][-80:])
    if cur.strip():
        lines.append(cur[:160])
    update(console=[l for l in lines if not l.startswith("::")][-80:])


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        raise SystemExit(__doc__)
    cmd, rest = a[0], a[1:]
    kw = {}
    if "--pct" in rest:
        k = rest.index("--pct"); kw["pct"] = float(rest[k + 1]); rest = rest[:k] + rest[k + 2:]
    if cmd == "stage":
        event(" ".join(rest), stage=" ".join(rest), state="running", **kw)
    elif cmd == "event":
        event(" ".join(rest), **kw)
    elif cmd == "set":
        update(**{x.split("=", 1)[0]: x.split("=", 1)[1] for x in rest if "=" in x}, **kw)
    elif cmd == "tee":
        tee(" ".join(rest) or "run")
    elif cmd == "done":
        ok = (rest or ["ok"])[0] == "ok"
        event("Finished: posted" if ok else "Run failed", state="done" if ok else "failed",
              stage="Done" if ok else "Failed", pct=100 if ok else kw.get("pct", _load().get("pct", 0)))
    else:
        raise SystemExit(__doc__)
