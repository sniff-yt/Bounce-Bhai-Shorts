#!/usr/bin/env bash
# Bounce Bhai pipeline split into two stages for GitHub Actions:
#   bash scripts/make_short.sh prepare  -> build story/audio and cache Sketchfab actors in Blender
#   bash scripts/make_short.sh publish  -> animate/render, compose, and post the Short
set -Eeuo pipefail
trap 'echo "::error::Pipeline failed at line $LINENO: $BASH_COMMAND"' ERR
cd "$(dirname "$0")/.."
live() { python scripts/live.py "$@" >/dev/null 2>&1 || true; }   # dashboard live feed (never fails the run)

prepare_models() {
  NAME="short_$(date -u +%Y%m%d_%H%M)"
  mkdir -p out models/blender_cache
  printf '%s\n' "$NAME" > out/current_name.txt
  printf 'Preparing %s\n' "$NAME"

  # Honour explicit override (workflow_dispatch input / env), else pick from insights.
  FORMAT="${BB_FORMAT:-$(python scripts/insights.py format 2>/dev/null || echo race)}"
  echo "Format selected: $FORMAT"
  echo "::notice title=format::$FORMAT"

  case "$FORMAT" in
    promo)
      live stage "Planning a Bhai Drive game promo" --pct 5
      python scripts/make_promo.py "out/$NAME.json"
      ;;
    race)
      live stage "Setting up a 3-ball race" --pct 5
      python scripts/make_race.py "out/$NAME.json"
      ;;
    multiply)
      live stage "Setting up a ball-multiply challenge" --pct 5
      python scripts/make_multiply.py "out/$NAME.json"
      ;;
    sim)
      live stage "Setting up a ball-escape challenge" --pct 5
      python scripts/make_sim.py "out/$NAME.json"
      ;;
    *)
      echo "::warning title=format::Unsupported format '$FORMAT' - falling back to race"
      live stage "Setting up a 3-ball race" --pct 5
      python scripts/make_race.py "out/$NAME.json"
      FORMAT="race"
      ;;
  esac

  echo "NAME=$NAME" >> "${GITHUB_ENV:-/dev/null}"
  echo "Setup complete: out/$NAME.json (format=$FORMAT)"
}

animate_and_post() {
  NAME="${NAME:-$(cat out/current_name.txt 2>/dev/null || true)}"
  if [ -z "$NAME" ] || [ ! -f "out/$NAME.json" ]; then
    echo "No prepared story found. Run the 'Setup the models in Blender' step first." >&2
    exit 1
  fi

  T=$SECONDS
  FORMAT="$(python -c 'import json,sys;print(json.load(open(sys.argv[1])).get("format","story"))' "out/$NAME.json")"
  if [ "$FORMAT" = "promo" ]; then
    live stage "Recording Bhai Drive gameplay" --pct 40
    pip install -q playwright
    export CHROME="${CHROME:-$(command -v google-chrome || command -v chromium || true)}"
    [ -n "$CHROME" ] || python -m playwright install --with-deps chromium
    python scripts/promo.py "out/$NAME.json"
    echo "::notice title=timing::render promo $((SECONDS - T))s"
  elif [ "$FORMAT" = "race" ]; then
    live stage "Racing the balls through the parkour" --pct 40
    python scripts/fan_names.py "out/$NAME.json" || true
    python engine/sim_race.py "out/$NAME.json"
    cp "out/$NAME.mp4" "out/${NAME}_final.mp4"
    echo "::notice title=timing::render race $((SECONDS - T))s; $(cat "out/$NAME.mp4.json" 2>/dev/null)"
  elif [ "$FORMAT" = "multiply" ]; then
    live stage "Multiplying the balls" --pct 40
    python engine/sim_multiply.py "out/$NAME.json"
    cp "out/$NAME.mp4" "out/${NAME}_final.mp4"
    echo "::notice title=timing::render multiply $((SECONDS - T))s; $(cat "out/$NAME.mp4.json" 2>/dev/null)"
  elif [ "$FORMAT" = "sim" ]; then
    live stage "Simulating the ball escape" --pct 40
    python scripts/fan_names.py "out/$NAME.json" || true
    python engine/sim_escape.py "out/$NAME.json"
    cp "out/$NAME.mp4" "out/${NAME}_final.mp4"
    echo "::notice title=timing::render sim $((SECONDS - T))s"
  else
  live stage "Animating the cartoon" --pct 40
  if [ "${BB_ENGINE:-2d}" = "blender" ]; then
    "${BLENDER:-blender}" -b --factory-startup --python engine/render_blender.py -- "out/$NAME.json"
  else
    python engine/render2d.py "out/$NAME.json"     # 2D vector cartoon (default): sharp 1080x1920 @ 30 fps
  fi
  echo "::notice title=timing::render ${BB_ENGINE:-2d} $((SECONDS - T))s; $(cat "out/$NAME.mp4.render.json" 2>/dev/null)"
  T=$SECONDS
  live stage "Adding captions, music and polish" --pct 86
  python scripts/finish.py "out/$NAME.json"
  echo "::notice title=timing::finish $((SECONDS - T))s"
  fi
  ffmpeg -v error -y -i "out/${NAME}_final.mp4" -af volumedetect -f null - 2>&1 | grep max_volume || true
  live stage "Uploading to YouTube" --pct 93
  python scripts/upload.py "out/$NAME.json"
  live event "Posted: https://youtube.com/shorts/$(python -c 'import json,sys;print(json.load(open(sys.argv[1])).get("video_id") or "")' "out/$NAME.json" 2>/dev/null)"

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
                "video_id": story.get("video_id"), "seed": story.get("seed"),
                "format": story.get("format", "story"), "genre": story.get("genre"), "topic": story.get("topic"),
                "yt_title": (story.get("yt_title") or {}).get("hi_roman"), "series": story.get("series"),
                "names": story.get("names"), "variant": story.get("variant"), "ab": story.get("ab"),
                "race_kind": story.get("race_kind"), "teams": story.get("teams"), "team_pool": story.get("team_pool"),
                "race_fallback": story.get("race_fallback")})
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
