#!/usr/bin/env bash
# Full pipeline: story -> voice -> Blender 3D story render -> audio/subtitles -> (upload)
set -euo pipefail
cd "$(dirname "$0")/.."
NAME="short_$(date -u +%Y%m%d_%H%M)"
mkdir -p out
python scripts/write_story.py "out/$NAME.json"
# fetch any external models referenced by the story (fills cast[].model_path)
python scripts/fetch_models.py "out/$NAME.json"
python scripts/voice.py "out/$NAME.json" voice/ref.wav
"${BLENDER:-blender}" -b --factory-startup --python engine/render_blender.py -- "out/$NAME.json"
python scripts/finish.py "out/$NAME.json"
ffmpeg -v error -y -i "out/${NAME}_final.mp4" -af volumedetect -f null - 2>&1 | grep max_volume || true
python scripts/upload.py "out/$NAME.json"
python - "$NAME" <<'EOF'
import json, sys, datetime
n = sys.argv[1]; c = json.load(open(f"out/{n}.json"))
h = json.load(open("data/history.json"))
h.append({"date": datetime.datetime.utcnow().isoformat() + "Z", "title": c["title"], "hook": c["hook"],
          "video_id": c.get("video_id"), "seed": c["seed"]})
json.dump(h, open("data/history.json", "w"), ensure_ascii=False, indent=1)
EOF
echo "NAME=$NAME" >> "${GITHUB_ENV:-/dev/null}"
