#!/usr/bin/env python3
"""After render: rebuild audio (voice + soft pad music only, no SFX), pad video so the voice
isn't cut, fix subtitle end times.  usage: python scripts/finish.py out/story.json
Writes out/<name>_final.mp4 and out/<name>.{hd,en,te}.srt
"""
import json, os, subprocess, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "engine"))
sys.argv, story_path = [sys.argv[0]], sys.argv[1]
import render3d as R

c = json.load(open(story_path))
m = json.load(open(c["out"] + ".meta.json"))
vl = [R.load_voice(p) for p in c["voice_lines"]]
sst, t = [], 0.4
for v in vl:
    sst.append(t); t += len(v) / 44100 + 0.22
dur0 = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", c["out"]]))
dur = max(dur0 + 3, t + 1.0)
R.audio([], int(dur * R.FPS), m["esc"], "mix.wav", list(zip(sst, vl)), music=True, bounces=False)
final = c["out"].replace(".mp4", "_final.mp4")
subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", c["out"], "-i", "mix.wav", "-map", "0:v", "-map", "1:a",
                "-vf", "tpad=stop_mode=clone:stop_duration=3", "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", final], check=True)
os.remove("mix.wav")
fd = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", final]))
end = R.srt_time(fd - 0.3)
for lang in ("hd", "en", "te", "hi"):
    p = c["out"].replace(".mp4", f".{lang}.srt")
    if os.path.exists(p):
        txt = open(p).read().rstrip("\n").split("\n")
        for i in range(len(txt) - 1, -1, -1):
            if "-->" in txt[i]:
                txt[i] = txt[i].split("-->")[0] + "--> " + end; break
        open(p, "w").write("\n".join(txt) + "\n")
print("final", final, round(fd, 2), "s")
