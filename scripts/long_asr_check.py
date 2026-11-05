#!/usr/bin/env python3
"""Whisper check of the FINAL voiced track: transcribe the speech mix (Groq whisper-large-v3) in ~2 minute windows
and compare each window's transcript with the script lines voiced in it. Writes story["asr_check"] and prints a
::notice (::warning when a window matches poorly). usage: python scripts/long_asr_check.py out/long_x.json"""
import difflib, json, os, re, subprocess, sys, time

import requests

p = sys.argv[1]
s = json.load(open(p, encoding="utf-8"))
key = os.environ.get("GROQ_API_KEY")
lang = s.get("lang", "te")
if not key or not s.get("speech_wav"):
    print("asr check: skipped (no GROQ_API_KEY / speech)")
    sys.exit(0)
lines = [ln for sc in s["scenes"] for ln in sc["lines"]]
norm = lambda x: re.sub(r"[\W_]+", "", (x or "").lower())
win, res = 120.0, []
t, dur = 0.0, s["duration"]
while t < dur - 5:
    a, b = t, min(dur, t + win)
    # cut at a pause: end the window at the end of the last line that finishes inside it
    inside = [ln for ln in lines if ln["start"] >= a - 0.01 and ln["end"] <= b]
    if not inside:
        t = b
        continue
    b = inside[-1]["end"] + 0.15
    out = f"/tmp/asr_{int(a)}.mp3"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{a:.2f}", "-to", f"{b:.2f}", "-i", s["speech_wav"], "-ac", "1",
                    "-ar", "16000", "-b:a", "48k", out], check=True)
    heard = None
    for k in range(4):
        r = requests.post("https://api.groq.com/openai/v1/audio/transcriptions", headers={"Authorization": f"Bearer {key}"},
                          files={"file": (os.path.basename(out), open(out, "rb"), "audio/mpeg")},
                          data={"model": "whisper-large-v3", "language": lang, "response_format": "json", "temperature": "0"},
                          timeout=120)
        if r.status_code == 200:
            heard = r.json().get("text", "")
            break
        time.sleep(10 + 10 * k)
    script = " ".join(ln["text"] for ln in inside)
    sim = difflib.SequenceMatcher(None, norm(script), norm(heard or "")).ratio() if heard is not None else None
    res.append({"from": round(a, 1), "to": round(b, 1), "lines": len(inside), "sim": None if sim is None else round(sim, 3),
                "heard_head": (heard or "")[:120]})
    t = b
sims = [r["sim"] for r in res if r["sim"] is not None]
s["asr_check"] = {"windows": res, "mean": round(sum(sims) / len(sims), 3) if sims else None}
json.dump(s, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
bad = [r for r in res if r["sim"] is not None and r["sim"] < 0.7]
print(f"::{'warning' if bad else 'notice'} title=whisper check::final speech track vs script: mean match "
      f"{s['asr_check']['mean']} over {len(res)} windows " + " ".join(f"{r['from']:.0f}s={r['sim']}" for r in res))
