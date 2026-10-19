#!/usr/bin/env bash
# Bounce Bhai pipeline split into two stages for GitHub Actions:
#   bash scripts/make_short.sh prepare  -> build story/audio and cache Sketchfab actors in Blender
#   bash scripts/make_short.sh publish  -> animate/render, compose, and post the Short
set -Eeuo pipefail
trap 'echo "::error::Pipeline failed at line $LINENO: $BASH_COMMAND"' ERR
cd "$(dirname "$0")/.."

prepare_models() {
  NAME="short_$(date -u +%Y%m%d_%H%M)"
  mkdir -p out models/blender_cache
  printf '%s\n' "$NAME" > out/current_name.txt
  printf 'Preparing %s\n' "$NAME"

  T=$SECONDS
  python scripts/write_story.py "out/$NAME.json"
  echo "::notice title=timing::story $((SECONDS - T))s"; T=$SECONDS
  python scripts/voice.py "out/$NAME.json" voice/ref.wav
  echo "::notice title=timing::voice $((SECONDS - T))s"

  # Sketchfab actors are opt-in: search hits are random rigid meshes (cars etc.) that wreck the framing.
  # Default = rigged CC0 Quaternius characters with baked skeletal clips, lip-sync and gesture layers.
  case "${BB_USE_SKETCHFAB:-0}" in 1|true|yes) ;; *)
    echo "Using the rigged Quaternius cast (assets/characters/cast.blend; BB_USE_SKETCHFAB=1 for Sketchfab models)"
    echo "NAME=$NAME" >> "${GITHUB_ENV:-/dev/null}"
    echo "Setup complete: out/$NAME.json"
    return 0 ;;
  esac
  python scripts/fetch_models.py "out/$NAME.json"
  "${BLENDER:-blender}" -b --factory-startup --python engine/setup_models.py -- "out/$NAME.json"

  python - "$NAME" <<'PY'
import json, os, sys
name = sys.argv[1]
path = f"out/{name}.json"
with open(path, encoding="utf-8") as stream:
    story = json.load(stream)
cast = story.get("cast") or []
missing = [i for i, c in enumerate(cast) if not isinstance(c, dict) or
           not str(c.get("model_path", "")).endswith(".blend") or
           not os.path.isfile(c["model_path"])]
if missing:
    raise SystemExit(f"Blender model setup failed for cast indexes {missing}")
print(f"Blender setup validated for {len(cast)} actors")
PY

  echo "NAME=$NAME" >> "${GITHUB_ENV:-/dev/null}"
  echo "Setup complete: out/$NAME.json"
}

animate_and_post() {
  NAME="${NAME:-$(cat out/current_name.txt 2>/dev/null || true)}"
  if [ -z "$NAME" ] || [ ! -f "out/$NAME.json" ]; then
    echo "No prepared story found. Run the 'Setup the models in Blender' step first." >&2
    exit 1
  fi

  T=$SECONDS
  if [ "${BB_ENGINE:-2d}" = "blender" ]; then
    "${BLENDER:-blender}" -b --factory-startup --python engine/render_blender.py -- "out/$NAME.json"
  else
    python engine/render2d.py "out/$NAME.json"     # 2D vector cartoon (default): sharp 1080x1920 @ 30 fps
  fi
  echo "::notice title=timing::render ${BB_ENGINE:-2d} $((SECONDS - T))s; $(cat "out/$NAME.mp4.render.json" 2>/dev/null)"
  T=$SECONDS
  python scripts/finish.py "out/$NAME.json"
  echo "::notice title=timing::finish $((SECONDS - T))s"
  ffmpeg -v error -y -i "out/${NAME}_final.mp4" -af volumedetect -f null - 2>&1 | grep max_volume || true
  python scripts/upload.py "out/$NAME.json"

  python - "$NAME" <<'PY'
import json, sys, datetime
name = sys.argv[1]
with open(f"out/{name}.json", encoding="utf-8") as stream:
    story = json.load(stream)
history_path = "data/history.json"
try:
    with open(history_path, encoding="utf-8") as stream:
        history = json.load(stream)
except FileNotFoundError:
    history = []
history.append({"date": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "title": story.get("title", name), "hook": story.get("hook", ""),
                "video_id": story.get("video_id"), "seed": story.get("seed")})
with open(history_path, "w", encoding="utf-8") as stream:
    json.dump(history, stream, ensure_ascii=False, indent=1)
    stream.write("\n")
PY

  echo "Short rendered and upload step completed: out/${NAME}_final.mp4"
}

case "${1:-all}" in
  prepare) prepare_models ;;
  publish|animate) animate_and_post ;;
  all) prepare_models; animate_and_post ;;
  *) echo "Usage: bash scripts/make_short.sh [prepare|publish|all]" >&2; exit 2 ;;
esac
