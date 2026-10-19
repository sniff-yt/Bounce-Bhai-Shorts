
#!/usr/bin/env python3
"""Improve Bounce Bhai Shorts animation and preserve model paths.

Run from the repository root:
python patch_render.py
"""
from pathlib import Path
import re
import sys

PATH = Path(sys.argv[1] if len(sys.argv) > 1 else "engine/render_blender.py")

if not PATH.is_file():
    raise SystemExit(f"Renderer not found: {PATH}")

text = PATH.read_text(encoding="utf-8")
changes = []

# 1. Preserve Sketchfab model cache paths through story normalization.
if 'copy.deepcopy(raw_story.get("cast")' not in text:
    start = text.find(
        '    with open(story_path, encoding="utf-8") as stream:'
    )
    end_marker = "    require_sketchfab_models(story)"
    end = text.find(end_marker, start)

    if start < 0 or end < 0:
        raise SystemExit(
            "Could not locate model-path normalization block."
        )

    end += len(end_marker)

    replacement = '''    import copy
    with open(story_path, encoding="utf-8") as stream:
        raw_story = json.load(stream)

    # Preserve custom model metadata before normalization.
    raw_cast = copy.deepcopy(raw_story.get("cast") or [])
    story = SP.normalize(copy.deepcopy(raw_story))
    normalized_cast = story.get("cast") or []

    if len(raw_cast) != len(normalized_cast):
        raise SystemExit(
            "Story normalization changed the cast count; "
            "refusing to map models to the wrong actors."
        )

    for index, (source_character, normalized_character) in enumerate(
        zip(raw_cast, normalized_cast)
    ):
        if not isinstance(source_character, dict) or not isinstance(
            normalized_character, dict
        ):
            raise SystemExit(f"Invalid cast entry at index {index}")

        for key in (
            "model_path",
            "source_model_path",
            "model_cache_format",
        ):
            if key in source_character:
                normalized_character[key] = source_character[key]

    require_sketchfab_models(story)'''

    text = text[:start] + replacement + text[end:]
    changes.append("preserve Sketchfab model paths")


# 2. Use story-aware camera shots instead of random cuts.
if "# Semantic shot plan: keep framing tied to the story" not in text:
    start_marker = '        choices = ["wide", "medium", "low", "orbit", "high"]'
    end_marker = "        shot = rng.choice(choices); prev_shot = shot"

    start = text.find(start_marker)
    end = text.find(end_marker, start)

    if start < 0 or end < 0:
        raise SystemExit(
            "Could not locate camera shot-selection block."
        )

    end += len(end_marker)

    replacement = '''        # Semantic shot plan: frame each story beat intentionally.
        if moving:
            shot = "track_low" if act == "run" else "track"
        elif j == payoff_j:
            shot = (
                "close"
                if n == 1 and act not in ("fall", "jump")
                else "medium"
            )
        elif n >= 2:
            shot = (
                "wide"
                if act in ("talk", "listen", "point")
                else "medium"
            )
        elif sc_["prop"] in ("lightbulb", "clock"):
            shot = (
                "close"
                if act in ("think", "shocked", "point")
                else "medium"
            )
        elif act in ("think", "wave"):
            shot = "close"
        elif act in ("celebrate", "jump", "shocked"):
            shot = "low"
        else:
            shot = "medium"

        # Keep consecutive dialogue in the same setting visually stable.
        if j > 0 and j != payoff_j and not moving:
            previous = story["sentences"][j - 1]["scene"]

            if (
                previous["setting"] == sc_["setting"]
                and previous["action"] in ("talk", "listen")
                and act in ("talk", "listen")
                and n == 1
            ):
                shot = "medium"

        prev_shot = shot'''

    text = text[:start] + replacement + text[end:]
    changes.append("use story-aware camera shots")


# 3. Add subtle whole-body acting to rigid Sketchfab models.
if "# Extra whole-model motion for rigid Sketchfab meshes" not in text:
    match = re.search(r"(?m)^([ \t]*)if f in blink_at:", text)

    if not match:
        raise SystemExit(
            "Could not locate character animation insertion point."
        )

    indent = match.group(1)

    body = """# Extra whole-model motion for rigid Sketchfab meshes.
# These models may not contain a usable armature or animation.
if "sketchfab_model" in S:
    phase = 2 * math.pi * tt

    if a in ("talk", "listen"):
        rot[0] += 0.025 * math.sin(phase * 0.65 + ph)
        rot[1] += 0.035 * math.sin(phase * 0.45 + ph)
        loc[2] += 0.022 * abs(
            math.sin(phase * 1.1 + ph)
        )

    elif a == "think":
        rot[0] -= 0.055
        rot[1] += 0.025 * math.sin(phase * 0.35 + ph)
        loc[2] += 0.012 * math.sin(phase * 0.5 + ph)

    elif a == "point":
        rot[1] -= 0.085 * ease(u / 0.18)
        loc[2] += 0.018 * abs(
            math.sin(phase * 0.8)
        )

    elif a == "shocked":
        recoil = ease(tt / 0.22)
        rot[1] += 0.11 * recoil
        loc[2] += 0.085 * math.exp(
            -((tt - 0.18) / 0.12) ** 2
        )

    elif a in ("celebrate", "jump"):
        loc[2] += 0.11 * abs(
            math.sin(math.pi * tt / 0.62)
        )
        rot[0] += 0.045 * math.sin(phase * 0.9 + ph)

    elif a == "wave":
        rot[0] += 0.03 * math.sin(phase * 0.7 + ph)
"""

    injected = "\n".join(
        indent + line if line else ""
        for line in body.rstrip("\n").split("\n")
    )

    text = (
        text[:match.start()]
        + injected
        + "\n"
        + indent
        + "if f in blink_at:"
        + text[match.end():]
    )

    changes.append("add whole-model acting")


# 4. Show the hook only at the beginning, not throughout the video.
if 'if t < 2.4 and cfg.get("hook")' not in text:
    hook_match = re.search(
        r'(?m)^([ \t]*)R\.text_c\(dr, 250, cfg\["hook"\], 66, stroke=6\)$',
        text,
    )

    if not hook_match:
        raise SystemExit(
            "Could not locate the persistent hook caption."
        )

    indent = hook_match.group(1)

    hook_block = (
        indent + 'if t < 2.4 and cfg.get("hook"):\n'
        + indent
        + '    R.text_c(dr, 250, cfg["hook"], 74, stroke=6)'
    )

    text = (
        text[:hook_match.start()]
        + hook_block
        + text[hook_match.end():]
    )

    changes.append("show hook only during opening")


# Validate before saving.
compile(text, str(PATH), "exec")
PATH.write_text(text, encoding="utf-8")

if changes:
    print(
        "Applied animation fixes: " + "; ".join(changes),
        flush=True,
    )
else:
    print(
        "Animation fixes already applied; nothing to do.",
        flush=True,
    )
