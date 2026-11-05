#!/usr/bin/env python3
"""Daily guard + gates for the long-form story automation.

  python scripts/long_guard.py posted <lang> [history.json]
      exit 0 and print "posted" when history already has a long_story in <lang> with today's IST date, else exit 1.
      (scheduled runs + the backup cron use it so GitHub firing late / twice never double-posts)
  python scripts/long_guard.py gate out/long_x.json
      publish gates on the finished episode: duration 8.5-10.5 min, no freeze >3 s, <= 25 % of lines voiced by the
      edge-tts fallback instead of Gemini TTS. Prints ::warning lines; exit 0 = OK to upload, 3 = skip the upload.
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
    elif len(edge) / len(lines) > 0.25:
        bad.append(f"{len(edge)}/{len(lines)} lines ({100 * len(edge) / len(lines):.0f} %) fell back from Gemini TTS to edge-tts (max 25 %)")
    else:
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
    if cmd == "gate":
        sys.exit(gate(sys.argv[2]))
    raise SystemExit(__doc__)
