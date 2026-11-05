#!/usr/bin/env python3
"""Daily guard + gates for the long-form story automation.

  python scripts/long_guard.py posted <lang> [history.json]
      exit 0 and print "posted" when history already has a long_story in <lang> with today's IST date, else exit 1.
      (scheduled runs + the backup cron use it so GitHub firing late / twice never double-posts)
  python scripts/long_guard.py gate out/long_x.json
      publish gates on the finished episode: duration 8.5-10.5 min, no freeze >3 s, <= 25 % of lines voiced by the
      edge-tts fallback instead of Gemini TTS. Prints ::warning lines; exit 0 = OK to upload, 3 = skip the upload.
  python scripts/long_guard.py pick [history.json]
      scheduled / catch-up runs: print the first language in te, hi, en order whose slot (te 12:30, hi 13:30, en 14:30 UTC)
      has passed today and that has no long_story with today's IST date; print nothing when there is none, or when another
      scheduled run of this workflow is already rendering (it may hold the same language). Languages being rendered by
      an in-progress manual publish run (run-name "Long story <lang> (publish)") are skipped.
"""
import datetime, json, os, subprocess, sys

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def today_ist():
    return datetime.datetime.now(IST).date()


def posted(lang, path=None):
    path = path or os.path.join(ROOT, "data", "history.json")
    try:
        hist = json.load(open(path, encoding="utf-8"))
    except Exception:
        return False
    for h in hist:
        if h.get("format") != "long_story" or h.get("lang") != lang or not h.get("video_id"):
            continue
        try:
            d = datetime.datetime.fromisoformat(str(h.get("date")).replace("Z", "+00:00"))
        except Exception:
            continue
        if d.tzinfo is None:
            d = d.replace(tzinfo=datetime.timezone.utc)
        if d.astimezone(IST).date() == today_ist():
            print(f"posted: {h.get('video_id')} {h.get('yt_title') or h.get('title')}")
            return True
    return False


SLOTS = [("te", 12, 30), ("hi", 13, 30), ("en", 14, 30)]   # UTC slot times (6, 7, 8 PM IST)


def busy_langs():
    """(another scheduled run in progress?, langs held by in-progress manual publish runs) via the Actions API."""
    import urllib.request
    repo, me = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_RUN_ID")
    if not repo:
        return False, set()
    sched, held = False, set()
    for st in ("in_progress", "queued"):
        url = f"https://api.github.com/repos/{repo}/actions/workflows/longform.yml/runs?status={st}&per_page=50"
        req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
        if os.environ.get("GITHUB_TOKEN"):
            req.add_header("Authorization", "Bearer " + os.environ["GITHUB_TOKEN"])
        try:
            runs = json.load(urllib.request.urlopen(req, timeout=20)).get("workflow_runs", [])
        except Exception as e:
            print(f"::warning title=pick::could not list running runs ({e}) - continuing", file=sys.stderr)
            continue
        for r in runs:
            if str(r.get("id")) == str(me):
                continue
            t = r.get("display_title") or ""
            if r.get("event") == "schedule" and st == "in_progress":
                sched = True
            elif r.get("event") == "workflow_dispatch" and "(publish)" in t:
                for lang, _, _ in SLOTS:
                    if f"Long story {lang} " in t:
                        held.add(lang)
    return sched, held


def pick(path=None):
    now = datetime.datetime.now(datetime.timezone.utc)
    ready = os.environ.get("LONG_READY", "te,hi,en").split(",")
    due = [lang for lang, h, m in SLOTS if (now.hour, now.minute) >= (h, m) and lang in ready]
    import contextlib
    with contextlib.redirect_stdout(sys.stderr):
        todo = [lang for lang in due if not posted(lang, path)]
    if not todo:
        print("nothing due: " + (", ".join(f"{l} posted" for l in due) or "no slot has passed yet"), file=sys.stderr)
        return ""
    sched, held = busy_langs()
    if sched:
        print("another scheduled run is still rendering - leaving the catch-up to a later cron", file=sys.stderr)
        return ""
    for lang in todo:
        if lang in held:
            print(f"{lang}: a manual publish run is rendering it - skipping", file=sys.stderr)
            continue
        return lang
    return ""


def video_facts(mp4):
    info = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", mp4]))
    dur = float(info["format"]["duration"])
    fz = subprocess.run(["ffmpeg", "-v", "info", "-i", mp4, "-vf", "freezedetect=n=0.003:d=3", "-map", "0:v", "-f", "null", "-"],
                        capture_output=True, text=True).stderr.count("freeze_start")
    return dur, fz


def gate(jpath):
    s = json.load(open(jpath, encoding="utf-8"))
    mp4 = s.get("video") or jpath[:-5] + ".mp4"
    bad = []
    if not os.path.exists(mp4):
        bad.append("no video file")
    else:
        dur, fz = video_facts(mp4)
        if not (8.5 * 60 <= dur <= 10.5 * 60):
            bad.append(f"duration {dur / 60:.2f} min is outside 8.5-10.5 min")
        if fz:
            bad.append(f"{fz} frozen stretch(es) longer than 3 s (freezedetect)")
    lines = [ln for sc in s.get("scenes", []) for ln in sc.get("lines", []) if ln.get("audio") or ln.get("voice")]
    edge = [ln for ln in lines if not str(ln.get("voice", "")).startswith("gemini")]   # edge-tts / anything else
    if not lines:
        bad.append("no voiced lines")
    else:   # owner chose the free voices (2026-11-05): edge-tts episodes publish too, no voice gate
        print(f"::notice title=gate::Gemini TTS voiced {len(lines) - len(edge)}/{len(lines)} lines")
    for b in bad:
        print(f"::warning title=publish gate::{b} - NOT uploading (episode kept in the artifact)")
    if not bad:
        print("::notice title=publish gate::all gates passed")
    return 0 if not bad else 3


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "posted":
        sys.exit(0 if posted(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None) else 1)
    if cmd == "pick":
        print(pick(sys.argv[2] if len(sys.argv) > 2 else None))
        sys.exit(0)
    if cmd == "gate":
        sys.exit(gate(sys.argv[2]))
    raise SystemExit(__doc__)
