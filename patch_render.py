#!/usr/bin/env python3
"""One-shot fix for engine/render_blender.py ("Missing model_path for cast indexes [0, 1, 2]").

Run from the repo root:   python patch_render.py
Makes a backup at engine/render_blender.py.bak and is safe to run twice.
"""
import re
import sys

PATH = sys.argv[1] if len(sys.argv) > 1 else "engine/render_blender.py"

NEW_BODY = '''import copy
with open(story_path, encoding="utf-8") as stream:
    raw_story = json.load(stream)
# snapshot BEFORE normalize: SP.normalize() rewrites raw_story["cast"] in place
# and drops model_path / source_model_path / model_cache_format
raw_cast = copy.deepcopy(raw_story.get("cast") or [])
story = SP.normalize(copy.deepcopy(raw_story))
normalized_cast = story.get("cast") or []
if len(raw_cast) != len(normalized_cast):
    raise SystemExit(
        "Story normalization changed the cast count; refusing to map Sketchfab models to the wrong actors."
    )
for index, (source_character, normalized_character) in enumerate(zip(raw_cast, normalized_cast)):
    if not isinstance(source_character, dict) or not isinstance(normalized_character, dict):
        raise SystemExit(f"Invalid cast entry at index {index}")
    for key in ("model_path", "source_model_path", "model_cache_format"):
        if key in source_character:
            normalized_character[key] = source_character[key]
'''

with open(PATH, encoding="utf-8") as f:
    lines = f.read().split("\n")

text = "\n".join(lines)
if "copy.deepcopy(raw_story.get" in text:
    print("Already patched - nothing to do.")
    sys.exit(0)

start = next((i for i, l in enumerate(lines)
              if re.match(r'\s*with open\(story_path, encoding="utf-8"\) as stream:', l)), None)
end = next((i for i, l in enumerate(lines)
            if start is not None and i > start and re.match(r"\s*require_sketchfab_models\(story\)\s*$", l)), None)
if start is None or end is None:
    sys.exit("Could not find the block to replace (with open(story_path...) ... require_sketchfab_models(story)).")

indent = re.match(r"\s*", lines[start]).group(0)
new = [(indent + l) if l.strip() else l for l in NEW_BODY.rstrip("\n").split("\n")]

with open(PATH + ".bak", "w", encoding="utf-8") as f:
    f.write(text)
lines[start:end] = new
with open(PATH, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print(f"Patched {PATH} (lines {start + 1}-{end}); backup at {PATH}.bak")
