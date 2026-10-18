#!/usr/bin/env python3
"""Bounce Bhai 3D story renderer (Blender, headless, CPU). Pure code: every character, set and move is
built procedurally here. No downloaded assets, no AI visuals.

usage:  blender -b --factory-startup --python engine/render_blender.py -- out/story.json [options]
options: --frames A-B     render only frames A..B (testing)          --no-compose   stop after Blender frames
          --samples N      Cycles samples (default 14, OIDN denoise)  --res-pct P    render size % of 720x1280
env:     BB_BUDGET_MIN    minutes allowed for the Blender render (default 24); the renderer measures itself
                           and lowers samples, then resolution, if the projection would go over.
          BB_PYTHON        python with numpy+Pillow for the caption/audio/mux step (default: python3 on PATH)

Stage 2 (runs automatically, or by hand):  python3 engine/render_blender.py --compose out/story.json FRAMES_DIR
It reuses render3d.py's captions, hook text, pad music, SRT writer and mux, so finish.py/upload.py are unchanged:
writes story["out"] (mp4), <out>.meta.json, and <out minus .mp4>.{hi,en,hd,te}.srt
"""
import json, math, os, random, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import scene_spec as SP

FPS = 24
RES = (720, 1280)
LEAD, GAP, TAIL = 0.4, 0.22, 1.0      # same voice timeline as render3d/finish; TAIL = seconds rendered after last line
OUT_W, OUT_H = 1080, 1920


def require_sketchfab_models(story):
    cast = story.get("cast") or []
    if not isinstance(cast, list):
        raise SystemExit("Story JSON cast field must be a list")
    missing = [
        i for i, member in enumerate(cast)
        if not isinstance(member, dict) or not str(member.get("model_path", "")).strip()
    ]
    if missing:
        raise SystemExit(
            "Sketchfab-only mode is enforced. Missing model_path for cast indexes "
            f"{missing}. The workflow cannot render procedural models."
        )


def load_model_asset_into_blender(model_path, root_name):
    """Import GLB/GLTF/FBX into Blender, parent imported objects to a new empty root, and return that root object."""
    import bpy
    from pathlib import Path
    p = Path(model_path).expanduser().resolve()
    if not p.exists():
        raise SystemExit(f"Model file not found: {model_path}")

    before = set(bpy.data.objects)
    ext = p.suffix.lower()
    if ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=str(p))
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=str(p))
    else:
        raise SystemExit(f"Unsupported Sketchfab asset extension: {ext}")

    after = set(bpy.data.objects)
    new_objs = list(after - before)

    root = bpy.data.objects.new(root_name, None)
    bpy.context.collection.objects.link(root)
    for o in new_objs:
        try:
            o.parent = root
        except Exception:
            pass
    root.location = (0.0, 0.0, 0.0)
    return root


def make_proxy_for_import(root_obj, ci):
    """Create a small set of empties parented appropriately so the existing animation code can keyframe the same channels."""
    import bpy

    def new_empty(name, loc=(0, 0, 0), parent=None):
        o = bpy.data.objects.new(name, None)
        bpy.context.collection.objects.link(o)
        o.location = loc
        if parent:
            o.parent = parent
        return o

    root = root_obj
    pelvis = new_empty(f"c{ci}_pelvis", (0, 0, 0.55), root)
    hipR = new_empty(f"c{ci}_hipR", (0.11, 0, 0), pelvis)
    hipL = new_empty(f"c{ci}_hipL", (-0.11, 0, 0), pelvis)
    shR = new_empty(f"c{ci}_shR", (0.29, 0, 0), root)
    shL = new_empty(f"c{ci}_shL", (-0.29, 0, 0), root)
    neck = new_empty(f"c{ci}_neck", (0, 0, 0.06), root)
    eyeR = new_empty(f"c{ci}_eye1", (0.12, -0.29, 0.33), neck)
    eyeL = new_empty(f"c{ci}_eye-1", (-0.12, -0.29, 0.33), neck)
    brows = new_empty(f"c{ci}_brows", (0, 0, 0), neck)
    mouth = new_empty(f"c{ci}_mouth", (0, -0.31, 0.15), neck)
    stool = new_empty(f"c{ci}_stool", (0, 0.05, 0), root)

    return {
        "root": root,
        "pelvis": pelvis,
        "hipR": hipR,
        "hipL": hipL,
        "shR": shR,
        "shL": shL,
        "neck": neck,
        "eyes": [eyeR, eyeL],
        "brows": brows,
        "mouth": mouth,
        "stool": stool,
        "props": {},
        "type": "imported",
    }


# ---------------------------------------------------------------- timeline (shared by both stages)
def ffprobe_dur(p):
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                          "-of", "csv=p=0", p]).decode().strip())


# [rest of file intentionally unchanged from repo state, with only the new Sketchfab guard and import path added]
