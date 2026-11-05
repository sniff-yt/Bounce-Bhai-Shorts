#!/usr/bin/env bash
# Bounce Bhai long-form moral story: story -> voices -> stage plan -> music/SFX mix -> thumbnail -> render -> (upload)
#   bash scripts/make_long.sh te|hi|en [publish]
# Writes out/$NAME.mp4, out/${NAME}_thumb.jpg, out/$NAME.json. Uploads only when the 2nd arg is "publish".
set -Eeuo pipefail
trap 'echo "::error::make_long failed at line $LINENO: $BASH_COMMAND"' ERR
cd "$(dirname "$0")/.."
LANG_CODE="${1:-te}"
# run a step; on failure surface its last lines as an annotation (raw logs are hard to reach)
run() { local log; log=$(mktemp); set +e; "$@" 2>&1 | tee "$log"; local rc=${PIPESTATUS[0]}; set -e
  if [ "$rc" -ne 0 ]; then echo "::error title=$(basename "$2")::$(tail -n 6 "$log" | tr '\n' ' ' | cut -c1-900)"; exit "$rc"; fi; }
PUBLISH="${2:-}"
STORY_IN="${3:-}"          # sample mode: optional existing story json to reuse (skips the writer)
NAME="long_${LANG_CODE}_$(date -u +%Y%m%d_%H%M)"
[ "$PUBLISH" = "sample" ] && NAME="sample_${LANG_CODE}_$(date -u +%Y%m%d_%H%M)"
J="out/$NAME.json"
mkdir -p out
echo "NAME=$NAME" >> "${GITHUB_ENV:-/dev/null}"
python -c "from PIL import features; import sys; sys.exit(0 if features.check('raqm') else 1)" || {
  echo "::error::Pillow has no raqm text shaping: Telugu/Devanagari text would render broken"; exit 1; }

T=$SECONDS
if [ -n "$STORY_IN" ] && [ -f "$STORY_IN" ]; then
  python - "$STORY_IN" "$J" <<'PY'
import json, sys
s = json.load(open(sys.argv[1], encoding="utf-8"))
for sc in s["scenes"]:     # strip an earlier voicing so the story is voiced again
    for ln in sc["lines"]:
        for k in ("audio", "voice", "dur", "start", "end", "words", "beats", "react_by", "react_gap", "tts_match"):
            ln.pop(k, None)
    for k in ("start", "end"):
        sc.pop(k, None)
for k in ("duration", "speech_wav", "mix_wav", "voices", "voices_gemini", "end_screen", "sfx_cues", "scene_moods", "thumb", "video"):
    s.pop(k, None)
json.dump(s, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
PY
else
  run python scripts/write_long_story.py "$J" "$LANG_CODE"
fi
[ "$PUBLISH" = "sample" ] && run python scripts/long_sample.py "$J"
echo "::notice title=timing::story $((SECONDS - T))s"; T=$SECONDS
run python scripts/long_voice.py "$J"
echo "::notice title=timing::voices $((SECONDS - T))s"; T=$SECONDS
run python engine/long2d.py plan "$J"
# frame + STAGING checker on the render plan. Staging failures (speaker not on screen, a cut moving somebody, the
# 180-degree rule, partners apart / not facing, a listener cut inside a line) stop the episode; frame warnings don't.
set +e; trap - ERR
python scripts/long_qc.py "$J" --report "out/${NAME}_qc.json"
QC=$?
set -e; trap 'echo "::error::make_long failed at line $LINENO: $BASH_COMMAND"' ERR
if [ "$QC" -eq 2 ]; then echo "::error title=staging QC::staging failed (see out/${NAME}_qc.json)"; exit 1; fi
[ "$QC" -ne 0 ] && echo "::warning title=frame QC::soft frame warnings (see out/${NAME}_qc.json in the artifact)"
run python scripts/long_audio.py "$J"
echo "::notice title=timing::plan+music+sfx $((SECONDS - T))s"; T=$SECONDS
run python scripts/long_thumb.py "$J"
run python engine/long2d.py render "$J" --audio "out/${NAME}_mix.wav"
echo "::notice title=timing::render $((SECONDS - T))s"; T=$SECONDS

# ---- sanity checks on the finished file
python - "$J" <<'PY'
import json, subprocess, sys
p = sys.argv[1]
s = json.load(open(p, encoding="utf-8"))
mp4 = p[:-5] + ".mp4"
info = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height",
                                           "-of", "json", mp4]))
dur = float(info["format"]["duration"])
v = [x for x in info["streams"] if x["codec_type"] == "video"][0]
has_audio = any(x["codec_type"] == "audio" for x in info["streams"])
fz = subprocess.run(["ffmpeg", "-v", "info", "-i", mp4, "-vf", "freezedetect=n=0.003:d=3", "-map", "0:v", "-f", "null", "-"],
                    capture_output=True, text=True).stderr.count("freeze_start")
print(f"::notice title=video::{dur / 60:.2f} min, {v['width']}x{v['height']}, audio={has_audio}, freezes(>3s)={fz}, "
      f"title={s['title']}, moral={s['moral']}")
if not has_audio or v["width"] != 1920:
    raise SystemExit("bad output video")
if not s["scenes"][0].get("start") is None and len(s["scenes"]) > 2 and not (9.0 * 60 <= dur <= 10.0 * 60):
    print(f"::warning title=length::video is {dur / 60:.2f} min (target 9-10)")
s["video"] = mp4
json.dump(s, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
PY

if [ "$PUBLISH" = "publish" ]; then
  run python scripts/upload_long.py "$J"
  echo "::notice title=timing::upload $((SECONDS - T))s"
else
  echo "::notice title=publish::publish=false: not uploaded; mp4 + thumbnail + story json are in the workflow artifact"
fi
