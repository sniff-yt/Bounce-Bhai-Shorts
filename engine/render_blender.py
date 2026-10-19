#!/usr/bin/env python3
"""Bounce Bhai 3D story renderer (Blender, headless, CPU).
Cast: rigged CC0 Quaternius characters with baked skeletal clips (engine/quat_cast.py, assets/characters/cast.blend).
Scene environments, camera moves, animation tracks, captions, and audio composition are generated here.

usage:  blender -b --factory-startup --python engine/render_blender.py -- out/story.json [options]
options: --frames A-B     render only frames A..B (testing)          --no-compose   stop after Blender frames
         --samples N      Cycles samples (default 8, OIDN denoise)   --res-pct P    local previews only (default 100)
env:     BB_BUDGET_MIN    minutes allowed for the Blender render (default 24); the renderer measures itself and
                          moves the sample count (up to BB_MAX_SAMPLES=16, down to 2) to fit. Resolution stays 100%.
         BB_CHARACTERS    quaternius (default) | procedural (old primitive puppets)
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
MAX_SAMPLES = int(os.environ.get("BB_MAX_SAMPLES", "16"))
LEAD, GAP, TAIL = 0.4, 0.22, 1.0      # same voice timeline as render3d/finish; TAIL = seconds rendered after last line
OUT_W, OUT_H = 1080, 1920



def use_sketchfab():
    """Sketchfab actors are opt-in (BB_USE_SKETCHFAB=1). Search hits are random meshes (cars, props),
    rigid and unrigged, so by default the procedural cartoon characters are used: they have faces,
    lip-sync and moving limbs."""
    return os.environ.get("BB_USE_SKETCHFAB", "0").lower() in ("1", "true", "yes")


def require_sketchfab_models(story):
    if not use_sketchfab():
        return
    cast = story.get("cast") or []
    if not isinstance(cast, list) or not cast:
        raise SystemExit("Sketchfab-only mode requires a non-empty cast list")
    missing = [
        i for i, member in enumerate(cast)
        if not isinstance(member, dict) or not str(member.get("model_path", "")).strip()
    ]
    if missing:
        raise SystemExit(
            "Sketchfab-only mode is enforced. Missing model_path for cast indexes "
            f"{missing}. Run the 'Setup the models in Blender' workflow step first."
        )


# ---------------------------------------------------------------- timeline (shared by both stages)
def ffprobe_dur(p):
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                          "-of", "csv=p=0", p]).decode().strip())


def timeline(story):
    """[(voice_start_s, voice_dur_s)] per sentence, + total seconds to render."""
    out, t = [], LEAD
    vl = story.get("voice_lines") or []
    for i, s in enumerate(story["sentences"]):
        d = ffprobe_dur(vl[i]) if i < len(vl) and os.path.exists(vl[i]) else 0.35 + 0.075 * len(s.get("hd", s["hi"]))
        out.append((t, d))
        t += d + GAP
    return out, t - GAP + TAIL


def voice_env(path, n, fps):
    """Mouth-open envelope (0..1) per frame for a voice line."""
    import array
    try:
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", "8000", "-f", "s16le", "-"],
                             capture_output=True, check=True).stdout
        a = array.array("h"); a.frombytes(raw[:len(raw) // 2 * 2])
    except Exception:
        return [0.0] * n
    hop = 8000 // fps
    env = []
    for i in range(n):
        seg = a[i * hop:(i + 1) * hop]
        env.append(sum(abs(x) for x in seg) / (len(seg) * 32768.0) if len(seg) else 0.0)
    ref = sorted(env)[int(0.95 * (len(env) - 1))] or 1.0
    return [min(1.0, e / ref) for e in env]


# ================================================================= BLENDER STAGE
def blender_main(argv):
    import bpy
    import quat_cast as QC

    story_path = argv[0]
    opt = {"frames": None, "compose": True, "samples": int(os.environ.get("BB_SAMPLES", "8")), "res_pct": 100}
    i = 1
    while i < len(argv):
        a = argv[i]
        if a == "--frames":   # "A-B" range or "a,b,c" list
            v = argv[i + 1]
            opt["frames"] = [int(x) for x in v.split(",")] if "," in v else \
                list(range(int(v.split("-")[0]), int(v.split("-")[-1]) + 1))
            i += 1
        elif a == "--no-compose": opt["compose"] = False
        elif a == "--samples": opt["samples"] = int(argv[i + 1]); i += 1
        elif a == "--res-pct": opt["res_pct"] = int(argv[i + 1]); i += 1
        i += 1
    # scene_spec.normalize() normalizes story fields but may drop custom asset metadata.
    # Preserve the prepared Blender cache paths from the original JSON before rendering.
    import copy
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

    require_sketchfab_models(story)
    rng = random.Random(story.get("seed", 1))
    tl, total = timeline(story)
    NF = int(math.ceil(total * FPS))
    # frame ranges per sentence: cut exactly when the voice line starts
    fst = [0] + [int(round(st * FPS)) for st, _ in tl[1:]]
    fen = [x - 1 for x in fst[1:]] + [NF - 1]

    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    coll = sc.collection

    # ------------------------------------------------------------ helpers
    MATS = {}
    # Toon-ish lighting that converges in a few samples: hard sun + shadowless fill sun + a flat "ambient"
    # term done as self-emission (shared node group, keyed per scene) instead of noisy sky/bounce lighting.
    amb = bpy.data.node_groups.new("Ambient", "ShaderNodeTree")
    try:
        amb.interface.new_socket(name="Value", in_out="OUTPUT", socket_type="NodeSocketFloat")
    except AttributeError:
        amb.outputs.new("NodeSocketFloat", "Value")
    amb_val = amb.nodes.new("ShaderNodeValue"); amb_val.outputs[0].default_value = 0.35
    amb_out = amb.nodes.new("NodeGroupOutput")
    amb.links.new(amb_val.outputs[0], amb_out.inputs[0])

    def mat(rgb, rough=0.55, emit=0.0, name=None):
        key = (tuple(round(c, 3) for c in rgb), rough, emit)
        if key in MATS:
            return MATS[key]
        m = bpy.data.materials.new(name or f"m{len(MATS)}")
        m.use_nodes = True
        nt = m.node_tree
        for nd in list(nt.nodes):
            if nd.type != "OUTPUT_MATERIAL": nt.nodes.remove(nd)
        out = next(nd for nd in nt.nodes if nd.type == "OUTPUT_MATERIAL")
        dif = nt.nodes.new("ShaderNodeBsdfDiffuse"); dif.inputs["Color"].default_value = (*rgb, 1)
        em = nt.nodes.new("ShaderNodeEmission"); em.inputs["Color"].default_value = (*rgb, 1)
        add = nt.nodes.new("ShaderNodeAddShader")
        nt.links.new(dif.outputs[0], add.inputs[0]); nt.links.new(em.outputs[0], add.inputs[1])
        nt.links.new(add.outputs[0], out.inputs["Surface"])
        if emit:
            em.inputs["Strength"].default_value = emit
        else:
            g = nt.nodes.new("ShaderNodeGroup"); g.node_tree = amb
            nt.links.new(g.outputs[0], em.inputs["Strength"])
        try:
            m.cycles.emission_sampling = "NONE"   # glow/ambient is not a light source: no extra noise
        except Exception:
            pass
        m.diffuse_color = (*rgb, 1)
        MATS[key] = m
        return m

    def empty(name, loc=(0, 0, 0), parent=None):
        o = bpy.data.objects.new(name, None)
        coll.objects.link(o)
        if parent: o.parent = parent
        o.location = loc
        return o

    def prim(kind, loc, scale=(1, 1, 1), rot=(0, 0, 0), m=None, parent=None, smooth=False, seg=16):
        if kind == "cube": bpy.ops.mesh.primitive_cube_add(size=1)
        elif kind == "sphere": bpy.ops.mesh.primitive_uv_sphere_add(segments=seg, ring_count=max(6, seg // 2), radius=1)
        elif kind == "ico": bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=1)
        elif kind == "cyl": bpy.ops.mesh.primitive_cylinder_add(vertices=seg, radius=1, depth=1)
        elif kind == "cone": bpy.ops.mesh.primitive_cone_add(vertices=seg, radius1=1, radius2=0, depth=1)
        elif kind == "torus": bpy.ops.mesh.primitive_torus_add(major_segments=24, minor_segments=8, major_radius=1, minor_radius=0.12)
        elif kind == "plane": bpy.ops.mesh.primitive_plane_add(size=1)
        o = bpy.context.active_object
        if parent: o.parent = parent
        o.location, o.scale, o.rotation_euler = loc, scale, rot
        if m: o.data.materials.append(m)
        if smooth: o.data.polygons.foreach_set("use_smooth", [True] * len(o.data.polygons))
        return o

    def text(body, loc, size, m, parent=None, rot=(math.pi / 2, 0, 0)):
        bpy.ops.object.text_add()
        o = bpy.context.active_object
        o.data.body = body; o.data.size = size; o.data.extrude = 0.015
        o.data.align_x = "CENTER"; o.data.align_y = "CENTER"
        if parent: o.parent = parent
        o.location, o.rotation_euler = loc, rot
        o.data.materials.append(m)
        return o

    # ------------------------------------------------------------ environments
    DAY_SKY, NIGHT_SKY = (0.45, 0.68, 1.0), (0.004, 0.006, 0.025)

    def ground(O, rgb, size=60):
        prim("plane", (O[0], O[1], 0), (size, size, 1), m=mat(rgb, 0.8))

    def tree(x, y, O, s=1.0):
        prim("cyl", (O[0] + x, O[1] + y, 1.0 * s), (0.18 * s, 0.18 * s, 2.0 * s), m=mat((0.25, 0.12, 0.04)), seg=8)
        for dx, dz, r, g in ((0, 2.3, 1.0, 0.35), (-0.5, 1.9, 0.7, 0.28), (0.55, 2.0, 0.75, 0.42)):
            prim("ico", (O[0] + x + dx * s, O[1] + y, dz * s), (r * s,) * 3, m=mat((0.05, g, 0.06), 0.8))

    def walls(O, back_rgb, side_rgb, floor_rgb, h=9.0):
        ground(O, floor_rgb, 30)
        prim("cube", (O[0], O[1] + 3.2, h / 2), (16, 0.2, h), m=mat(back_rgb, 0.85))
        prim("cube", (O[0] - 6.5, O[1] - 1, h / 2), (0.2, 12, h), m=mat(side_rgb, 0.85))
        prim("cube", (O[0] + 6.5, O[1] - 1, h / 2), (0.2, 12, h), m=mat(side_rgb, 0.85))
        prim("cube", (O[0], O[1] + 3.05, 0.12), (16, 0.12, 0.24), m=mat((0.95, 0.95, 0.92)))  # skirting
        prim("cube", (O[0], O[1] + 3.05, 3.6), (16, 0.08, 0.12), m=mat((0.95, 0.95, 0.92)))   # rail

    def window(x, z, w, h, O, y=3.08, glow=(0.6, 0.85, 1.0)):
        prim("cube", (O[0] + x, O[1] + y, z), (w + 0.2, 0.1, h + 0.2), m=mat((0.95, 0.95, 0.95)))
        prim("cube", (O[0] + x, O[1] + y - 0.06, z), (w, 0.04, h), m=mat(glow, 0.3, emit=1.6))
        prim("cube", (O[0] + x, O[1] + y - 0.09, z), (0.06, 0.03, h), m=mat((0.95, 0.95, 0.95)))
        prim("cube", (O[0] + x, O[1] + y - 0.09, z), (w, 0.03, 0.06), m=mat((0.95, 0.95, 0.95)))

    def build_street(O):
        ground(O, (0.09, 0.09, 0.1))
        prim("cube", (O[0], O[1] + 0.6, 0.04), (30, 4.2, 0.08), m=mat((0.45, 0.43, 0.4), 0.9))   # footpath
        for k in range(-7, 8):
            prim("cube", (O[0] + k * 2.4, O[1] - 2.4, 0.01), (1.2, 0.15, 0.02), m=mat((0.9, 0.85, 0.3)))
        cols = [(0.85, 0.45, 0.25), (0.95, 0.78, 0.4), (0.35, 0.6, 0.85), (0.85, 0.45, 0.6), (0.45, 0.75, 0.5),
                (0.95, 0.6, 0.3)]
        x = -12.0; k = 0
        while x < 12:
            w = rng.uniform(2.8, 4.0); h = rng.uniform(4.5, 10)
            c = cols[k % len(cols)]; k += 1
            prim("cube", (O[0] + x + w / 2, O[1] + 4.5, h / 2), (w - 0.15, 4, h), m=mat(c, 0.85))
            for wz in [1.6 + 1.5 * q for q in range(int((h - 2.4) / 1.5) + 1)]:
                for wx in (-w / 4, w / 4):
                    lit = rng.random() < 0.3
                    prim("cube", (O[0] + x + w / 2 + wx, O[1] + 2.47, wz), (0.6, 0.08, 0.8),
                         m=mat((1.0, 0.85, 0.5), 0.3, emit=1.2) if lit else mat((0.15, 0.25, 0.4), 0.2))
            prim("cube", (O[0] + x + w / 2, O[1] + 2.47, 0.9), (0.8, 0.1, 1.7), m=mat((0.3, 0.15, 0.07)))
            x += w
        # street lamp + tree + sign
        prim("cyl", (O[0] + 2.8, O[1] + 1.8, 2.0), (0.06, 0.06, 4.0), m=mat((0.15, 0.15, 0.17), 0.4), seg=8)
        prim("sphere", (O[0] + 2.8, O[1] + 1.8, 4.05), (0.22,) * 3, m=mat((1.0, 0.9, 0.6), 0.3, emit=3), seg=12)
        tree(-3.2, 2.0, O, 0.9)
        prim("cube", (O[0] - 1.0, O[1] + 2.42, 3.2), (2.2, 0.1, 0.6), m=mat((0.8, 0.1, 0.1)))
        text("CHAI", (O[0] - 1.0, O[1] + 2.35, 3.2), 0.42, mat((1, 1, 1), emit=0.5))

    def build_home(O):
        walls(O, (0.85, 0.62, 0.42), (0.75, 0.52, 0.34), (0.32, 0.17, 0.07))
        window(1.8, 2.3, 1.8, 1.5, O)
        prim("cyl", (O[0], O[1] + 0.2, 0.01), (2.0, 1.4, 0.02), m=mat((0.6, 0.08, 0.1), 0.9), seg=24)
        # sofa
        sx = -2.6
        prim("cube", (O[0] + sx, O[1] + 2.4, 0.3), (2.2, 0.9, 0.5), m=mat((0.05, 0.4, 0.45), 0.8))
        prim("cube", (O[0] + sx, O[1] + 2.8, 0.75), (2.2, 0.25, 0.9), m=mat((0.05, 0.4, 0.45), 0.8))
        for d in (-1, 1):
            prim("cube", (O[0] + sx + d * 1.15, O[1] + 2.4, 0.55), (0.25, 0.9, 0.6), m=mat((0.04, 0.33, 0.38), 0.8))
        prim("sphere", (O[0] + sx - 0.5, O[1] + 2.55, 0.75), (0.25, 0.1, 0.22), m=mat((0.95, 0.75, 0.2)), smooth=True)
        # table + lamp + frame + plant
        prim("cube", (O[0] + 2.6, O[1] + 2.2, 0.75), (1.2, 0.7, 0.08), m=mat((0.4, 0.22, 0.08), 0.6))
        for dx in (-0.5, 0.5):
            prim("cube", (O[0] + 2.6 + dx, O[1] + 2.2, 0.37), (0.07, 0.5, 0.75), m=mat((0.3, 0.16, 0.06)))
        prim("cyl", (O[0] + 2.9, O[1] + 2.2, 1.0), (0.05, 0.05, 0.45), m=mat((0.2, 0.2, 0.2)), seg=8)
        prim("cone", (O[0] + 2.9, O[1] + 2.2, 1.35), (0.25, 0.25, 0.3), m=mat((1.0, 0.85, 0.55), emit=1.5), seg=16)
        prim("cube", (O[0] - 2.6, O[1] + 3.08, 2.4), (1.4, 0.06, 0.9), m=mat((0.3, 0.15, 0.05)))
        prim("cube", (O[0] - 2.6, O[1] + 3.04, 2.4), (1.2, 0.04, 0.7), m=mat((0.95, 0.55, 0.15), 0.4))
        prim("sphere", (O[0] - 2.85, O[1] + 3.0, 2.45), (0.18,) * 3, m=mat((1, 0.95, 0.4), emit=1.0), seg=12)

    def build_school(O):
        walls(O, (0.92, 0.85, 0.62), (0.85, 0.75, 0.52), (0.35, 0.37, 0.42))
        prim("cube", (O[0], O[1] + 3.06, 2.2), (4.6, 0.08, 2.0), m=mat((0.35, 0.2, 0.08)))
        prim("cube", (O[0], O[1] + 3.0, 2.2), (4.3, 0.06, 1.75), m=mat((0.04, 0.2, 0.1), 0.9))
        text("A B C   1+1=2", (O[0] - 0.3, O[1] + 2.95, 2.5), 0.38, mat((0.95, 0.95, 0.95), emit=0.4))
        text("E = mc²", (O[0] + 0.9, O[1] + 2.95, 1.8), 0.32, mat((0.95, 0.9, 0.4), emit=0.4))
        for x in (-4.0, 4.0):
            for y in (0.9, 2.2):
                prim("cube", (O[0] + x, O[1] + y, 0.72), (1.3, 0.7, 0.07), m=mat((0.7, 0.45, 0.2), 0.6))
                for dx in (-0.55, 0.55):
                    prim("cube", (O[0] + x + dx, O[1] + y, 0.36), (0.06, 0.6, 0.72), m=mat((0.25, 0.25, 0.28)))
                prim("cube", (O[0] + x - 0.2, O[1] + y, 0.78), (0.35, 0.25, 0.06), m=mat((0.8, 0.15, 0.15)))
        prim("cyl", (O[0] + 3.6, O[1] + 3.05, 3.0), (0.38, 0.38, 0.06), (math.pi / 2, 0, 0), m=mat((0.95, 0.95, 0.95)), seg=24)
        prim("cube", (O[0] + 3.6, O[1] + 2.98, 3.08), (0.04, 0.02, 0.22), m=mat((0.05, 0.05, 0.05)))
        prim("cube", (O[0] + 3.66, O[1] + 2.98, 3.0), (0.16, 0.02, 0.04), m=mat((0.05, 0.05, 0.05)))

    def build_park(O):
        ground(O, (0.12, 0.42, 0.07))
        prim("cube", (O[0], O[1] + 0.2, 0.01), (30, 1.8, 0.02), m=mat((0.75, 0.6, 0.38), 0.9))
        for (x, y, s) in ((-4.0, 3.5, 1.1), (-1.5, 6.5, 1.3), (2.0, 5.0, 1.0), (4.6, 3.0, 1.2), (6.0, 7.5, 1.4),
                          (-6.5, 6.0, 1.3)):
            tree(x, y, O, s)
        for x in (-2.6, 0.8, 3.4):
            prim("ico", (O[0] + x, O[1] + 2.3, 0.3), (0.6, 0.45, 0.45), m=mat((0.08, 0.35, 0.05), 0.8))
        for k in range(14):
            prim("sphere", (O[0] + rng.uniform(-5, 5), O[1] + rng.uniform(1.4, 3), 0.12), (0.09,) * 3,
                 m=mat(rng.choice([(1, 0.2, 0.3), (1, 0.85, 0.1), (0.9, 0.9, 0.95), (0.7, 0.3, 1.0)])), seg=8)
        prim("sphere", (O[0] - 6, O[1] + 26, -4), (16, 10, 9), m=mat((0.15, 0.5, 0.12), 0.9), seg=24)
        prim("sphere", (O[0] + 12, O[1] + 30, -5), (18, 10, 10), m=mat((0.1, 0.4, 0.1), 0.9), seg=24)
        # bench
        prim("cube", (O[0] + 2.6, O[1] + 1.4, 0.45), (1.6, 0.5, 0.07), m=mat((0.55, 0.3, 0.1)))
        prim("cube", (O[0] + 2.6, O[1] + 1.65, 0.75), (1.6, 0.06, 0.4), m=mat((0.55, 0.3, 0.1)))
        for dx in (-0.7, 0.7):
            prim("cube", (O[0] + 2.6 + dx, O[1] + 1.4, 0.22), (0.07, 0.45, 0.45), m=mat((0.15, 0.15, 0.15)))
        for (x, z) in ((-3, 9), (3.5, 11), (0.5, 13)):
            for dx, r in ((0, 1.0), (0.9, 0.75), (-0.9, 0.7)):
                prim("sphere", (O[0] + x + dx, O[1] + 18, z), (r,) * 3, m=mat((1, 1, 1), 0.9, emit=0.8), seg=12)

    def build_shop(O):
        walls(O, (0.95, 0.85, 0.7), (0.9, 0.78, 0.6), (0.6, 0.55, 0.5))
        for z in (0.8, 1.6, 2.4, 3.2):
            prim("cube", (O[0] + 1.0, O[1] + 2.8, z), (7.5, 0.6, 0.06), m=mat((0.4, 0.22, 0.08)))
            x = -2.6
            while x < 4.6:
                w = rng.uniform(0.25, 0.45); h = rng.uniform(0.3, 0.6)
                c = rng.choice([(0.9, 0.1, 0.1), (0.1, 0.4, 0.9), (1, 0.8, 0.1), (0.1, 0.7, 0.2), (1, 0.45, 0.05), (0.9, 0.3, 0.6)])
                prim("cube", (O[0] + x, O[1] + 2.75, z + 0.03 + h / 2), (w, 0.35, h), m=mat(c, 0.5))
                x += w + 0.06
        prim("cube", (O[0] - 3.2, O[1] + 1.4, 0.55), (2.2, 0.8, 1.1), m=mat((0.55, 0.25, 0.08), 0.6))
        prim("cube", (O[0] - 3.2, O[1] + 1.4, 1.12), (2.3, 0.9, 0.06), m=mat((0.85, 0.85, 0.82)))
        prim("cube", (O[0] - 3.5, O[1] + 1.5, 1.3), (0.5, 0.4, 0.3), m=mat((0.2, 0.2, 0.22)))
        for k in range(8):
            prim("cube", (O[0] - 3.2 + (k - 3.5) * 0.9, O[1] + 2.0, 4.3), (0.9, 2.2, 0.08),
                 (0.35, 0, 0), m=mat((0.85, 0.1, 0.1) if k % 2 else (0.97, 0.97, 0.95)))
        prim("cube", (O[0] + 1.0, O[1] + 3.05, 4.0), (3.2, 0.1, 0.7), m=mat((0.95, 0.75, 0.05)))
        text("KIRANA STORE", (O[0] + 1.0, O[1] + 2.98, 4.0), 0.4, mat((0.6, 0.05, 0.05)))

    def build_office(O):
        walls(O, (0.7, 0.78, 0.85), (0.6, 0.68, 0.76), (0.3, 0.32, 0.36))
        for x in (-3.2, -1.0, 1.2):
            window(x, 2.6, 1.8, 2.2, O, glow=(0.55, 0.8, 1.0))
        prim("cube", (O[0] + 3.4, O[1] + 3.05, 2.2), (2.0, 0.06, 1.3), m=mat((0.97, 0.97, 0.97), 0.3))
        for k, (h, c) in enumerate(((0.3, (0.9, 0.2, 0.2)), (0.55, (1, 0.7, 0.1)), (0.9, (0.1, 0.7, 0.3)))):
            prim("cube", (O[0] + 2.9 + k * 0.45, O[1] + 3.0, 1.7 + h / 2), (0.3, 0.04, h), m=mat(c))
        prim("cube", (O[0] - 3.4, O[1] + 1.8, 0.75), (1.8, 0.85, 0.07), m=mat((0.9, 0.9, 0.88), 0.4))
        for dx in (-0.8, 0.8):
            prim("cube", (O[0] - 3.4 + dx, O[1] + 1.8, 0.37), (0.06, 0.8, 0.74), m=mat((0.2, 0.2, 0.22)))
        prim("cube", (O[0] - 3.4, O[1] + 2.0, 1.15), (0.8, 0.05, 0.5), m=mat((0.05, 0.05, 0.06), 0.3))
        prim("cube", (O[0] - 3.4, O[1] + 1.97, 1.15), (0.72, 0.03, 0.42), m=mat((0.2, 0.55, 1.0), emit=1.5))
        prim("cyl", (O[0] + 4.3, O[1] + 2.2, 0.3), (0.3, 0.3, 0.6), m=mat((0.8, 0.35, 0.15)), seg=12)
        prim("ico", (O[0] + 4.3, O[1] + 2.2, 1.0), (0.55, 0.55, 0.65), m=mat((0.1, 0.45, 0.1), 0.8))

    def build_night(O):
        ground(O, (0.02, 0.05, 0.04))
        prim("sphere", (O[0], O[1] + 30, -10), (40, 20, 12), m=mat((0.02, 0.06, 0.04), 0.9), seg=24)
        prim("sphere", (O[0] + 4, O[1] + 40, 22), (2.6,) * 3, m=mat((1.0, 0.95, 0.8), emit=3.0), seg=24)
        import bmesh
        bm = bmesh.new()
        for _ in range(170):
            r = rng.uniform(0.04, 0.12)
            m4 = __import__("mathutils").Matrix.Translation((O[0] + rng.uniform(-25, 25), O[1] + 45, rng.uniform(4, 40)))
            bmesh.ops.create_icosphere(bm, subdivisions=1, radius=r, matrix=m4)
        me = bpy.data.meshes.new("stars"); bm.to_mesh(me); bm.free()
        st = bpy.data.objects.new("stars", me); coll.objects.link(st)
        me.materials.append(mat((1, 1, 0.9), emit=6.0))
        for (x, w, h) in ((-6, 2.5, 2.2), (-3.2, 2.0, 1.8), (5.0, 2.8, 2.4)):
            prim("cube", (O[0] + x, O[1] + 6, h / 2), (w, 2, h), m=mat((0.05, 0.05, 0.09), 0.9))
            prim("cone", (O[0] + x, O[1] + 6, h + 0.5), (w * 0.75, 1.5, 1.0), rot=(0, 0, math.pi / 4),
                 m=mat((0.12, 0.04, 0.04), 0.9), seg=4)
            prim("cube", (O[0] + x + 0.4, O[1] + 4.98, h * 0.5), (0.45, 0.06, 0.45), m=mat((1, 0.75, 0.3), emit=2.5))
        # telescope
        tx, ty = 2.4, 1.6
        for a in (0, 2.1, 4.2):
            prim("cyl", (O[0] + tx + 0.25 * math.cos(a), O[1] + ty + 0.25 * math.sin(a), 0.5), (0.03, 0.03, 1.05),
                 (0.25 * math.sin(a), -0.25 * math.cos(a), 0), m=mat((0.6, 0.6, 0.6), 0.3), seg=6)
        prim("cyl", (O[0] + tx, O[1] + ty, 1.15), (0.12, 0.12, 1.1), (0.9, 0, 0), m=mat((0.9, 0.9, 0.95), 0.3), seg=12)
        for k in range(20):
            prim("sphere", (O[0] + rng.uniform(-5, 5), O[1] + rng.uniform(1.5, 5), rng.uniform(0.4, 2.2)), (0.035,) * 3,
                 m=mat((0.8, 1.0, 0.3), emit=6), seg=6)

    def build_lab(O):
        walls(O, (0.5, 0.78, 0.72), (0.42, 0.68, 0.64), (0.22, 0.27, 0.36))
        prim("cube", (O[0], O[1] + 2.2, 0.85), (6, 0.9, 0.08), m=mat((0.15, 0.17, 0.2), 0.3))
        prim("cube", (O[0], O[1] + 2.2, 0.42), (5.8, 0.8, 0.82), m=mat((0.9, 0.92, 0.95)))
        for k, c in enumerate(((0.1, 1.0, 0.3), (0.8, 0.1, 1.0), (0.1, 0.6, 1.0), (1, 0.4, 0.05), (1, 0.1, 0.3))):
            x = -2.4 + k * 1.2
            if k % 2:
                prim("sphere", (O[0] + x, O[1] + 2.2, 1.1), (0.2,) * 3, m=mat(c, 0.2, emit=2.0), seg=12)
                prim("cyl", (O[0] + x, O[1] + 2.2, 1.35), (0.05, 0.05, 0.3), m=mat((0.8, 0.9, 0.95), 0.1), seg=8)
            else:
                prim("cyl", (O[0] + x, O[1] + 2.2, 1.05), (0.12, 0.12, 0.35), m=mat(c, 0.2, emit=2.0), seg=12)
        prim("cube", (O[0] - 3.6, O[1] + 3.05, 2.6), (1.6, 0.05, 1.6), m=mat((0.97, 0.97, 0.97)))
        for a in (0, 1.05, 2.1):
            prim("torus", (O[0] - 3.6, O[1] + 3.0, 2.6), (0.6, 0.25, 0.6), (math.pi / 2, a, 0), m=mat((0.1, 0.4, 0.9)))
        prim("sphere", (O[0] - 3.6, O[1] + 2.98, 2.6), (0.12,) * 3, m=mat((0.9, 0.2, 0.1), emit=1.5), seg=12)
        window(3.2, 2.6, 2.0, 1.6, O, glow=(0.6, 0.9, 1.0))

    BUILD = {"street": build_street, "home": build_home, "school": build_school, "park": build_park,
             "shop": build_shop, "office": build_office, "night_sky": build_night, "lab": build_lab}
    used = []
    for s in story["sentences"]:
        if s["scene"]["setting"] not in used: used.append(s["scene"]["setting"])
    ORIG = {name: (k * 120.0, 0.0, 0.0) for k, name in enumerate(used)}
    for name in used:
        BUILD[name](ORIG[name])

    # ------------------------------------------------------------ characters
    SKINS = [(0.55, 0.3, 0.17), (0.42, 0.22, 0.11), (0.62, 0.38, 0.24), (0.33, 0.17, 0.08)]
    HAIR = (0.02, 0.015, 0.012)
    DARK = (0.02, 0.02, 0.025)

    def build_char(c, ci):
        # Track this character's procedural objects so a downloaded model can replace
        # their visible meshes without breaking the existing animation rig.
        objects_before = set(bpy.data.objects)
        t = c["type"]; shirt = SP.COLORS[c["color"]]
        skin = SKINS[(ci + story.get("seed", 0)) % len(SKINS)]
        robot = t == "robot"
        if robot: skin = (0.55, 0.58, 0.62)
        S = {"type": t}
        kid = t in ("boy", "girl")
        root = empty(f"c{ci}_root"); root.scale = (0.8,) * 3 if kid else (1, 1, 1)
        pel = empty(f"c{ci}_pelvis", (0, 0, 0.55), root)
        S.update(root=root, pelvis=pel)
        ms, mk = mat(shirt, 0.6), mat(skin, 0.5, name="skin")
        pants = mat((0.03, 0.05, 0.14) if not robot else (0.3, 0.32, 0.35), 0.7)
        dress = t in ("woman", "girl", "grandma")
        for side, nm in ((1, "hipR"), (-1, "hipL")):
            h = empty(f"c{ci}_{nm}", (side * 0.11, 0, 0), pel)
            prim("cyl", (0, 0, -0.25), (0.075, 0.075, 0.5), m=mk if dress else pants, parent=h, smooth=True, seg=10)
            prim("sphere", (0, -0.05, -0.52), (0.09, 0.15, 0.07), m=mat(DARK if not dress else (0.6, 0.05, 0.1), 0.4),
                 parent=h, smooth=True, seg=12)
            S[nm] = h
        if robot:
            prim("cube", (0, 0, 0.25), (0.5, 0.36, 0.55), m=ms, parent=pel)
            prim("cyl", (0, -0.19, 0.3), (0.09, 0.09, 0.03), (math.pi / 2, 0, 0), m=mat((1, 0.2, 0.1), emit=3), parent=pel, seg=12)
        else:
            prim("sphere", (0, 0, 0.25), (0.27, 0.2, 0.32), m=ms if t != "scientist" else mat((0.92, 0.93, 0.95), 0.6),
                 parent=pel, smooth=True)
            if t == "scientist":
                prim("cube", (0, -0.17, 0.33), (0.12, 0.06, 0.3), m=ms, parent=pel)
            if dress:
                prim("cone", (0, 0, 0.02), (0.33, 0.28, 0.55), m=ms, parent=pel, smooth=True, seg=16)
        chest = empty(f"c{ci}_chest", (0, 0, 0.47), pel)
        for side, nm in ((1, "shR"), (-1, "shL")):
            sh = empty(f"c{ci}_{nm}", (side * 0.29, 0, 0), chest)
            prim("cyl", (0, 0, -0.2), (0.062, 0.062, 0.42), m=ms if not robot else mat((0.45, 0.47, 0.5), 0.3),
                 parent=sh, smooth=True, seg=10)
            prim("sphere", (0, 0, -0.44), (0.085,) * 3, m=mk, parent=sh, smooth=True, seg=12)
            S[nm] = sh
        neck = empty(f"c{ci}_neck", (0, 0, 0.06), chest)
        S["neck"] = neck
        if robot:
            prim("cube", (0, 0, 0.3), (0.56, 0.5, 0.5), m=mat((0.6, 0.62, 0.66), 0.3), parent=neck)
            prim("cyl", (0, 0, 0.62), (0.02, 0.02, 0.2), m=mat((0.3, 0.3, 0.3)), parent=neck, seg=6)
            prim("sphere", (0, 0, 0.74), (0.06,) * 3, m=mat(shirt, emit=3), parent=neck, seg=10)
        else:
            prim("sphere", (0, 0, 0.3), (0.34,) * 3, m=mk, parent=neck, smooth=True, seg=24)
            prim("sphere", (0, -0.34, 0.25), (0.045, 0.04, 0.05), m=mk, parent=neck, smooth=True, seg=10)
            for sd in (1, -1):
                prim("sphere", (sd * 0.34, 0, 0.3), (0.05, 0.035, 0.08), m=mk, parent=neck, smooth=True, seg=10)
        eyes = []
        for sd in (1, -1):
            e = empty(f"c{ci}_eye{sd}", (sd * 0.12, -0.29 if not robot else -0.255, 0.33), neck)
            if robot:
                prim("cyl", (0, 0, 0), (0.08, 0.08, 0.02), (math.pi / 2, 0, 0), m=mat((0.2, 0.95, 1.0), emit=1.6), parent=e, seg=16)
            else:
                prim("sphere", (0, 0, 0), (0.095, 0.05, 0.11), m=mat((0.97, 0.97, 0.97), 0.25), parent=e, smooth=True)
                prim("sphere", (0, -0.04, -0.01), (0.058, 0.025, 0.064), m=mat((0.01, 0.01, 0.01), 0.15), parent=e, smooth=True, seg=12)
                prim("sphere", (0.018, -0.062, 0.022), (0.014,) * 3, m=mat((1, 1, 1), emit=2), parent=e, seg=8)
            eyes.append(e)
        S["eyes"] = eyes
        brow = empty(f"c{ci}_brows", (0, 0, 0), neck)
        if not robot:
            for sd in (1, -1):
                prim("cube", (sd * 0.12, -0.31, 0.46), (0.11, 0.03, 0.025),
                     (0, sd * 0.12, 0), m=mat((0.9, 0.9, 0.9) if t in ("grandpa", "grandma") else HAIR), parent=brow)
        S["brows"] = brow
        mouth = empty(f"c{ci}_mouth", (0, -0.31 if not robot else -0.255, 0.15), neck)
        if robot:
            prim("cube", (0, 0, 0), (0.24, 0.02, 0.04), m=mat((0.2, 0.95, 1.0), emit=1.6), parent=mouth)
        else:
            prim("sphere", (0, 0, 0), (0.085, 0.03, 0.03), m=mat((0.12, 0.01, 0.015), 0.4), parent=mouth, smooth=True, seg=12)
        S["mouth"] = mouth
        # hair & accessories
        hair = mat(HAIR, 0.5)
        white = mat((0.85, 0.85, 0.85), 0.6)
        if t in ("man", "boy", "woman", "girl", "scientist"):
            hm = mat((0.5, 0.5, 0.52), 0.6) if t == "scientist" else hair
            prim("sphere", (0, 0.04, 0.42), (0.36, 0.36, 0.3), m=hm, parent=neck, smooth=True, seg=20)
            if t == "boy":
                for a in (-0.5, 0, 0.5):
                    prim("cone", (a * 0.2, -0.18, 0.66), (0.08, 0.08, 0.16), (-0.6, a, 0), m=hair, parent=neck, seg=8)
        if t == "woman":
            prim("sphere", (0, 0.13, 0.12), (0.33, 0.2, 0.42), m=hair, parent=neck, smooth=True)
            prim("sphere", (0, -0.335, 0.43), (0.018, 0.01, 0.018), m=mat((0.9, 0.05, 0.05), emit=0.5), parent=neck, seg=8)
        if t == "girl":
            for sd in (1, -1):
                prim("sphere", (sd * 0.36, 0.06, 0.32), (0.11, 0.11, 0.15), m=hair, parent=neck, smooth=True, seg=12)
                prim("sphere", (sd * 0.31, 0.02, 0.42), (0.04,) * 3, m=mat((0.95, 0.2, 0.5)), parent=neck, seg=8)
        if t == "grandpa":
            for sd in (1, -1):
                prim("sphere", (sd * 0.3, 0.06, 0.36), (0.09, 0.14, 0.1), m=white, parent=neck, smooth=True, seg=12)
            prim("sphere", (0, -0.335, 0.2), (0.13, 0.04, 0.035), m=white, parent=neck, smooth=True, seg=12)
        if t == "grandma":
            prim("sphere", (0, 0.04, 0.42), (0.36, 0.36, 0.3), m=white, parent=neck, smooth=True, seg=20)
            prim("sphere", (0, 0.25, 0.56), (0.13,) * 3, m=white, parent=neck, smooth=True, seg=12)
        if t in ("grandpa", "grandma", "scientist"):
            for sd in (1, -1):
                prim("torus", (sd * 0.12, -0.345, 0.33), (0.1, 0.1, 0.25), (math.pi / 2, 0, 0), m=mat((0.05, 0.05, 0.05), 0.3), parent=neck)
            prim("cube", (0, -0.35, 0.34), (0.06, 0.012, 0.012), m=mat((0.05, 0.05, 0.05)), parent=neck)
        # stool (only shown when sitting)
        stool = empty(f"c{ci}_stool", (0, 0.05, 0), root)
        prim("cyl", (0, 0, 0.4), (0.24, 0.24, 0.06), m=mat((0.5, 0.25, 0.08), 0.5), parent=stool, seg=16)
        prim("cyl", (0, 0, 0.2), (0.05, 0.05, 0.4), m=mat((0.2, 0.2, 0.2), 0.4), parent=stool, seg=8)
        S["stool"] = stool
        S["props"] = {}

        # If fetch_models.py downloaded a Sketchfab asset, use it as the visible
        # character while retaining the procedural rig for the existing animation.
        model_path = c.get("model_path") if use_sketchfab() else None
        if model_path:
            candidates = [
                os.path.abspath(model_path),
                os.path.abspath(os.path.join(os.path.dirname(story_path), model_path)),
                os.path.abspath(os.path.join(HERE, "..", model_path)),
            ]
            resolved = next((path for path in candidates if os.path.isfile(path)), None)
            if resolved is None:
                raise FileNotFoundError(f"[Sketchfab] Model cache missing for cast[{ci}]: {model_path}")
            else:
                try:
                    # The setup workflow pre-imports and normalizes each model into a .blend cache.
                    if os.path.splitext(resolved)[1].lower() != ".blend":
                        raise ValueError(
                            "model_path must point to a prepared .blend cache; run engine/setup_models.py first"
                        )
                    with bpy.data.libraries.load(resolved, link=False) as (data_from, data_to):
                        if not data_from.objects:
                            raise RuntimeError("prepared .blend file contains no objects")
                        data_to.objects = list(data_from.objects)
                    imported = {obj for obj in data_to.objects if obj is not None}
                    if not imported:
                        raise RuntimeError("no objects loaded from the prepared .blend file")
                    for obj in imported:
                        if not any(existing == obj for existing in coll.objects):
                            coll.objects.link(obj)
                    wrapper = next((obj for obj in imported if obj.get("bb_actor_root", False)), None)
                    if wrapper is None:
                        raise RuntimeError("prepared .blend file is missing the BB_ACTOR_ROOT marker")

                    # Keep cached geometry, but attach it to the animation root.
                    bpy.context.view_layer.update()
                    world_matrix = wrapper.matrix_world.copy()
                    wrapper.parent = root
                    wrapper.matrix_parent_inverse = root.matrix_world.inverted()
                    wrapper.matrix_world = world_matrix
                    bpy.context.view_layer.update()

                    # Hide the procedural placeholder meshes. No silent fallback.
                    procedural = (set(bpy.data.objects) - objects_before) - imported
                    for obj in procedural:
                        if obj.type == "MESH":
                            obj.hide_render = True
                            try:
                                obj.hide_set(True)
                            except Exception:
                                pass
                    S["sketchfab_model"] = wrapper
                    print(f"[Sketchfab] Imported prepared cast[{ci}] model: {resolved}", flush=True)
                except Exception as exc:
                    raise RuntimeError(
                        f"[Sketchfab] Import failed for cast[{ci}] ({model_path}): "
                        f"{type(exc).__name__}: {exc}"
                    ) from exc
        return S

    def build_prop(S, kind, ci):
        """Held props hang from the right hand; lightbulb/clock float above the head."""
        if "rig" in S:
            return QC.attach_prop(S, kind, lambda p: prop_geo(p, kind), empty, CLIPS)
        if kind in ("lightbulb", "clock"):
            p = empty(f"c{ci}_{kind}", (0.0, 0.0, 0.85), S["neck"])
        else:
            p = empty(f"c{ci}_{kind}", (0, -0.06, -0.52), S["shR"])
        prop_geo(p, kind)
        S["props"][kind] = p
        return p

    def prop_geo(p, kind):
        if kind in ("lightbulb", "clock"):
            if kind == "lightbulb":
                prim("sphere", (0, 0, 0.12), (0.17,) * 3, m=mat((1, 0.9, 0.3), emit=4), parent=p, seg=16)
                prim("cyl", (0, 0, -0.08), (0.08, 0.08, 0.12), m=mat((0.6, 0.6, 0.6), 0.3), parent=p, seg=10)
            else:
                prim("cyl", (0, 0, 0), (0.2, 0.2, 0.05), (math.pi / 2, 0, 0), m=mat((0.95, 0.95, 0.95)), parent=p, seg=20)
                prim("torus", (0, 0, 0), (0.21, 0.21, 0.4), (math.pi / 2, 0, 0), m=mat((0.8, 0.1, 0.1)), parent=p)
                prim("cube", (0, -0.03, 0.05), (0.02, 0.01, 0.12), m=mat((0.05, 0.05, 0.05)), parent=p)
                prim("cube", (0.04, -0.03, 0), (0.09, 0.01, 0.02), m=mat((0.05, 0.05, 0.05)), parent=p)
        else:
            if kind == "book":
                prim("cube", (0, 0, 0), (0.06, 0.3, 0.38), m=mat((0.8, 0.1, 0.1)), parent=p)
                prim("cube", (0.005, 0, 0), (0.055, 0.28, 0.36), m=mat((0.97, 0.95, 0.88)), parent=p)
            elif kind == "phone":
                prim("cube", (0, 0, 0.03), (0.03, 0.1, 0.19), m=mat((0.03, 0.03, 0.03), 0.2), parent=p)
                prim("cube", (0, -0.016, 0.03), (0.026, 0.005, 0.16), m=mat((0.2, 0.6, 1.0), emit=2), parent=p)
            elif kind == "box":
                prim("cube", (0, -0.05, 0.05), (0.32, 0.32, 0.3), m=mat((0.65, 0.42, 0.2), 0.8), parent=p)
                prim("cube", (0, -0.05, 0.05), (0.33, 0.06, 0.31), m=mat((0.85, 0.75, 0.5), 0.8), parent=p)
            elif kind == "coin":
                prim("cyl", (0, -0.05, 0.05), (0.13, 0.13, 0.03), (math.pi / 2, 0, 0), m=mat((1, 0.7, 0.05), 0.25), parent=p, seg=20)
            elif kind == "trophy":
                prim("cyl", (0, 0, 0.0), (0.06, 0.06, 0.06), m=mat((1, 0.7, 0.05), 0.25), parent=p, seg=10)
                prim("cyl", (0, 0, 0.08), (0.02, 0.02, 0.12), m=mat((1, 0.7, 0.05), 0.25), parent=p, seg=8)
                prim("cone", (0, 0, 0.28), (0.13, 0.13, -0.25), m=mat((1, 0.7, 0.05), 0.25), parent=p, seg=16)
            elif kind == "laptop":
                prim("cube", (0, -0.1, 0.0), (0.38, 0.26, 0.02), m=mat((0.7, 0.72, 0.75), 0.3), parent=p)
                prim("cube", (0, 0.03, 0.13), (0.38, 0.02, 0.26), (-0.2, 0, 0), m=mat((0.7, 0.72, 0.75), 0.3), parent=p)
                prim("cube", (0, 0.015, 0.13), (0.34, 0.01, 0.22), (-0.2, 0, 0), m=mat((0.3, 0.7, 1.0), emit=2), parent=p)
            elif kind == "ball":
                prim("sphere", (0, -0.1, 0.05), (0.15,) * 3, m=mat((0.95, 0.4, 0.05), 0.5), parent=p, smooth=True)

    # Default cast: rigged CC0 Quaternius characters with their own skeletal clips (assets/characters/cast.blend).
    # BB_CHARACTERS=procedural keeps the old primitive puppets; BB_USE_SKETCHFAB=1 keeps the Sketchfab path.
    CLIPS = {}
    if QC.available() and not use_sketchfab():
        CLIPS = QC.load_clips()
        qkeys = QC.pick_recipes(story["cast"], story.get("seed", 0))
        qctx = {"mat": mat, "empty": empty, "prim": prim, "coll": coll, "SP": SP}
        CH = [QC.build(c, ci, qkeys[ci], qctx) for ci, c in enumerate(story["cast"])]
        print("cast:", ", ".join(f"{c['type']}->{k['label']}" for c, k in zip(story["cast"], qkeys)), flush=True)
    else:
        CH = [build_char(c, ci) for ci, c in enumerate(story["cast"])]
    for j, s in enumerate(story["sentences"]):
        pr = s["scene"]["prop"]
        lead = s["scene"]["characters"][0]
        if pr != "none" and pr not in CH[lead]["props"]:
            build_prop(CH[lead], pr, lead)

    # ------------------------------------------------------------ animation (sampled every frame)
    N = NF
    def chan():  # per-frame channel storage
        return [None] * N
    track = {}   # (obj, attr) -> list of per-frame values

    def put(obj, attr, f, val):
        k = (obj.name, attr)
        if k not in track: track[k] = (obj, chan())
        track[k][1][f] = val

    envs = []
    vl = story.get("voice_lines") or []
    for j, (st, d) in enumerate(tl):
        n = fen[j] - fst[j] + 1
        e = voice_env(vl[j], int(d * FPS) + 2, FPS) if j < len(vl) and os.path.exists(vl[j]) else \
            [0.5 + 0.5 * math.sin(k * 1.7) ** 2 for k in range(int(d * FPS) + 2)]
        off = int(round((st - fst[j] / FPS) * FPS))
        envs.append([0.0] * max(0, off) + list(e) + [0.0] * n)

    blink_at = set()
    t = rng.uniform(0.5, 2)
    while t * FPS < N:
        b = int(t * FPS); blink_at.update({b, b + 1, b + 2}); t += rng.uniform(2.2, 4.5)

    def slots(n):
        return {1: [0.0], 2: [-0.62, 0.62], 3: [-1.05, 0.0, 1.05]}[n]

    def ease(x):
        x = min(1, max(0, x)); return x * x * (3 - 2 * x)

    OFF = (0, 0, -60)
    # ---- rigged characters: per-frame clip plan, baked after the sentence loop
    QF = {ci: [None] * N for ci, S in enumerate(CH) if "rig" in S}
    QLAST = {}
    ANIM = {ci: QC.Animator(S, CLIPS) for ci, S in enumerate(CH) if "rig" in S}
    LISTEN_MAP = {"walk": "walk", "run": "run", "celebrate": "celebrate", "jump": "celebrate",
                  "shocked": "shocked", "fall": "shocked"}

    def beat_action(jj, ci):
        if jj < 0 or jj >= len(story["sentences"]):
            return None
        sc2 = story["sentences"][jj]["scene"]
        if ci not in sc2["characters"]:
            return None
        r = sc2["characters"].index(ci)
        return sc2["action"] if r == 0 else LISTEN_MAP.get(sc2["action"], "listen")

    def env_at(j, k, w=2):
        e = envs[j]
        lo, hi = max(0, k - w), min(len(e), k + w + 1)
        return sum(e[lo:hi]) / max(1, hi - lo)

    def rig_beat(S, ci, j, role, sc_, act, ids, n, xs, f0, f1, dur, dist):
        anim = ANIM[ci]
        O = ORIG[sc_["setting"]]
        mouth = S.get("mouth")
        if role is None:
            for f in range(f0, f1 + 1):
                put(S["root"], "location", f, OFF)
                put(S["stool"], "scale", f, (0.0,) * 3)
                for kind, p in S["props"].items():
                    put(p, "scale", f, (0.0,) * 3)
            QLAST.pop(ci, None)
            return
        a = beat_action(j, ci)
        fam = S["family"]
        clip = anim.clip_name(a)
        prev_a, next_a = beat_action(j - 1, ci), beat_action(j + 1, ci)
        x0 = xs[role]; y0 = 0.15 * abs(x0) * 0.4
        rz = (-0.35 if x0 > 0 else 0.35) if n > 1 else 0.0
        ph = role * 0.37
        lead_x = xs[0]
        rate = 1.0
        if a in ("walk", "run"):
            nat = QC.NATURAL_SPEED.get((fam, clip), 1.2) * S["scale"]
            rate = min(1.6, max(0.6, (dist / max(dur, 0.1)) / nat))
        prev = QLAST.get(ci)
        oneshot = clip in QC.ONESHOT
        base = prev[1] if (prev and prev[0] == clip and not oneshot) else (0.0 if oneshot else role * 9 + ci * 5)
        robot = fam == "R"
        for f in range(f0, f1 + 1):
            k_ = f - f0
            tt = k_ / FPS; u = tt / dur
            loc = [x0, y0, 0.0]; rot = [0.0, 0.0, rz]
            env = env_at(j, k_) if role == 0 else 0.0
            k_in = 1.0 if prev_a == a else QC.ease(tt / 0.3)
            k_out = 1.0 if next_a == a else QC.ease((dur - tt) / 0.25)
            k = min(k_in, k_out)
            ctime = base + k_ * rate
            over = {}
            mo = 0.0            # mouth opening 0..1
            stool = 0.0
            if a in ("walk", "run"):
                loc[0] = x0 - dist / 2 + dist * u
                rot[2] = 1.25
                mo = 0.4 * env
            elif a == "talk":
                over = {"gesture": k * min(1.0, 0.3 + 1.1 * env) * (0.75 + 0.25 * math.sin(2 * math.pi * 0.4 * tt)),
                        "nod": k * (0.025 + 0.06 * env * math.sin(2 * math.pi * 1.3 * tt)),
                        "lean": 0.04 * k, "turn": 0.0}
                rot[2] += 0.04 * math.sin(2 * math.pi * 0.3 * tt + ph)
                mo = env
            elif a == "listen":
                side = 1.0 if lead_x > x0 else -1.0
                over = {"nod": k * 0.07 * max(0.0, math.sin(2 * math.pi * 0.45 * tt + ph * 6)) ** 2,
                        "turn": k * 0.22 * side, "tilt": k * 0.05 * side}
            elif a == "point":
                tgt = 1.0 if (n == 1 or x0 <= 0) else -1.0
                over = {"pose": "point", "side": tgt, "k": QC.ease(tt / 0.3) * k_out, "nod": -0.03 * k,
                        "lean": 0.04 * k, "turn": 0.15 * tgt * k}
                mo = env
            elif a == "jump":
                per = 0.85; ph2 = (tt % per) / per
                if ph2 >= 0.25:
                    loc[2] = 0.55 * math.sin(math.pi * (ph2 - 0.25) / 0.75)
                over = {"pose": "jump", "k": min(1.0, loc[2] / 0.3) * k_out}
                mo = 0.6
                if robot:
                    ctime = (tt % per) / per * 17
            elif a == "fall":
                tf = 0.25 * dur
                ctime = max(0.0, tt - tf) * FPS
                mo = 0.8 if tt > tf else 0.0
            elif a == "sit":
                if not robot:
                    over = {"sit": k_in, "gesture": 0.6 * k * min(1.0, 0.2 + env), "nod": 0.03 * k}
                    loc[2] -= S["sit_drop"] * k_in
                    stool = 1.0
                mo = env
            elif a == "celebrate":
                loc[2] = (0.10 if robot else 0.22) * abs(math.sin(math.pi * (tt + ph) / 0.55))
                rot[2] += 0.22 * math.sin(2 * math.pi * 0.9 * tt + ph)
                over = {"pose": "celebrate", "k": k, "pump": math.sin(2 * math.pi * 2.4 * tt + ph * 5)}
                mo = 0.85
            elif a == "shocked":
                ks = QC.ease(tt / 0.25)
                loc[1] = y0 + 0.25 * ks
                if tt < 0.35:
                    loc[2] = 0.15 * math.sin(math.pi * tt / 0.35)
                over = {"pose": "shocked", "k": min(ks, k_out), "nod": -0.08 * ks}
                mo = 0.9 * ks
            elif a == "wave":
                mo = env
                over = {"nod": 0.03 * k}
            elif a == "think":
                over = {"pose": "think", "k": k, "tilt": 0.12 * k, "nod": -0.06 * k}
                rot[2] += 0.05 * math.sin(2 * math.pi * 0.25 * tt)
            fr = {"clip": clip, "t": ctime, "over": over}
            if prev and k_ < QC.XFADE and prev[0] != clip:
                w = QC.ease((k_ + 1) / (QC.XFADE + 1))
                fr = {"clip": prev[0], "t": prev[1] + k_ * prev[2], "clip2": clip, "t2": ctime, "w2": w, "over": over}
            QF[ci][f] = fr
            put(S["root"], "location", f, (O[0] + loc[0], O[1] + loc[1], O[2] + loc[2]))
            put(S["root"], "rotation_euler", f, tuple(rot))
            put(S["stool"], "scale", f, (stool,) * 3)
            if mouth is not None:
                bx, by, bz = S["mouth_scale"]
                o = min(1.0, max(0.0, mo))
                put(mouth, "scale", f, (bx * (1.0 + 0.2 * o), by, bz * (0.4 + 2.0 * o)))
            for kind, p in S["props"].items():
                show = role == 0 and sc_["prop"] == kind
                sz = 0.0
                if show:
                    sz = QC.ease(tt / 0.2)
                    if kind == "lightbulb":
                        sz *= 1 + 0.08 * math.sin(2 * math.pi * 2 * tt)
                put(p, "scale", f, (sz,) * 3)
        QLAST[ci] = (clip, base + (f1 - f0 + 1) * rate, rate)

    cam_keys = []   # (frame, cam_loc, aim_loc)
    world_keys, sun_keys = [], []
    payoff_j = len(story["sentences"]) - 1
    prev_shot = None
    for j, s in enumerate(story["sentences"]):
        sc_ = s["scene"]; O = ORIG[sc_["setting"]]
        act = sc_["action"]; ids = sc_["characters"]; n = len(ids)
        f0, f1 = fst[j], fen[j]; dur = (f1 - f0 + 1) / FPS
        xs = slots(n)
        moving = act in ("walk", "run")
        dist = min((1.0 if act == "walk" else 2.6) * dur, 3.6 if act == "walk" else 7.0) if moving else 0.0
        night = sc_["setting"] == "night_sky"
        world_keys.append((f0, NIGHT_SKY if night else DAY_SKY, 0.35 if night else 1.0))
        sun_keys.append((f0, (0.6, 0.7, 1.0) if night else (1.0, 0.95, 0.88), 1.5 if night else 2.4))
        for ci, S in enumerate(CH):
            role = ids.index(ci) if ci in ids else None
            if "rig" in S:
                rig_beat(S, ci, j, role, sc_, act, ids, n, xs, f0, f1, dur, dist)
                continue
            for f in range(f0, f1 + 1):
                if role is None:
                    put(S["root"], "location", f, OFF); continue
                tt = (f - f0) / FPS; u = tt / dur
                a = act if role == 0 else {"walk": "walk", "run": "run", "celebrate": "celebrate", "jump": "celebrate",
                                           "shocked": "shocked", "fall": "shocked"}.get(act, "listen")
                ph = role * 0.37
                x0 = xs[role]; y0 = 0.15 * abs(x0) * 0.4
                rz = (-0.35 if x0 > 0 else 0.35) if n > 1 else 0.0
                loc = [x0, y0, 0.0]; rot = [0.0, 0.0, rz]
                pz, prx = 0.0, 0.0
                hl = hr = 0.0                   # leg swing (rx)
                sl = [0.0, 0.0]; sr = [0.0, 0.0]  # shoulder (rx, ry)
                nrx = nry = nrz = 0.0
                eye = 1.0; brow = 0.0; mo = 1.0; stool = 0.0
                breath = 0.012 * math.sin(2 * math.pi * 0.35 * tt + ph * 5)
                pz += breath
                env = envs[j][f - f0] if f - f0 < len(envs[j]) else 0
                if a in ("walk", "run"):
                    run = a == "run"
                    loc[0] = x0 - dist / 2 + dist * u
                    rot[2] = 1.25
                    fr = (2.4 if run else 1.4)
                    w = math.sin(2 * math.pi * fr * tt + ph * 3)
                    amp = 0.65 if run else 0.38
                    hl, hr = amp * w, -amp * w
                    sl = [-amp * w * 0.9, -0.08]; sr = [amp * w * 0.9, 0.08]
                    pz += (0.07 if run else 0.03) * abs(math.cos(2 * math.pi * fr * tt + ph * 3))
                    prx = 0.25 if run else 0.04
                    if run: mo = 1.6
                elif a == "talk" or a == "listen":
                    g = math.sin(2 * math.pi * 0.6 * tt + ph * 4)
                    if a == "talk":
                        sr = [-0.5 - 0.35 * max(0, g), -0.15 - 0.2 * max(0, g)]
                        sl = [-0.15, 0.1]
                        nrx = 0.06 * math.sin(2 * math.pi * 1.1 * tt)
                        mo = 1 + 3.5 * env
                    else:
                        nrx = 0.07 * max(0, math.sin(2 * math.pi * 0.45 * tt + ph * 6)) ** 2
                        nrz = rz * 0.3
                        sl = [0.0, 0.06]; sr = [0.0, -0.06]
                    rot[2] += 0.05 * math.sin(2 * math.pi * 0.3 * tt + ph)
                elif a == "point":
                    k = ease(u / 0.15)
                    tgt = 1 if (n == 1 or x0 <= 0) else -1   # point toward the others / screen side
                    arm = sr if tgt > 0 else sl
                    arm[0] = -1.45 * k; arm[1] = -tgt * 0.55 * k
                    nrz = -tgt * 0.25 * k
                    mo = 1 + 3.0 * env
                    prx = 0.06 * k
                elif a == "jump":
                    per = 0.85; ph2 = (tt % per) / per
                    if ph2 < 0.25:
                        pz -= 0.12 * math.sin(math.pi * ph2 / 0.25); hl = hr = -0.3 * math.sin(math.pi * ph2 / 0.25)
                        sl = sr = [0.4, 0.0]
                    else:
                        q = (ph2 - 0.25) / 0.75
                        loc[2] = 0.55 * math.sin(math.pi * q)
                        sl = [0.0, 2.6]; sr = [0.0, -2.6]
                        hl, hr = -0.25, 0.25
                    sl = list(sl); sr = list(sr); mo = 1.8
                elif a == "fall":
                    tf = 0.25 * dur
                    k = ease((tt - tf) / 0.45) if tt > tf else 0
                    side = 1 if x0 >= 0 else -1
                    rot[1] = side * 1.45 * k
                    if 0 < k < 1: loc[2] = 0.15 * math.sin(math.pi * k)
                    flail = math.sin(2 * math.pi * 3 * tt)
                    sl = [-0.4, 1.8 + 0.5 * flail * (1 - k)]; sr = [-0.4, -1.8 - 0.5 * flail * (1 - k)]
                    hl, hr = -0.4 * k, 0.3 * k
                    eye = 1.3; brow = 0.04; mo = 2.8
                    if tt < tf:
                        prx = -0.12 * math.sin(2 * math.pi * 2 * tt); sl = [0.3, 0.6]; sr = [0.3, -0.6]; eye = 1.0; mo = 1
                elif a == "sit":
                    stool = 1.0
                    pz = -0.07 + breath
                    hl = hr = -1.0
                    sl = [-0.35, 0.05]; sr = [-0.6 - 0.2 * max(0, math.sin(2 * math.pi * 0.5 * tt)), -0.1]
                    nrx = 0.05 * math.sin(2 * math.pi * 0.4 * tt)
                    mo = 1 + 2.5 * env
                elif a == "celebrate":
                    per = 0.55
                    loc[2] = 0.25 * abs(math.sin(math.pi * (tt + ph) / per))
                    wv = math.sin(2 * math.pi * 2.4 * tt + ph * 5)
                    sl = [0.0, 2.55 + 0.25 * wv]; sr = [0.0, -2.55 + 0.25 * wv]
                    rot[2] += 0.25 * math.sin(2 * math.pi * 0.9 * tt + ph)
                    hl, hr = 0.2 * wv, -0.2 * wv
                    mo = 2.2; eye = 1.1; brow = 0.02
                elif a == "shocked":
                    k = ease(tt / 0.25)
                    loc[1] = y0 + 0.25 * k
                    if tt < 0.35: loc[2] = 0.18 * math.sin(math.pi * tt / 0.35)
                    tr = 0.06 * math.sin(2 * math.pi * 7 * tt)
                    sl = [-0.4 * k, 1.9 * k + tr]; sr = [-0.4 * k, -1.9 * k - tr]
                    prx = -0.12 * k
                    eye = 1 + 0.4 * k; brow = 0.05 * k; mo = 1 + 2.5 * k
                elif a == "wave":
                    wv = math.sin(2 * math.pi * 2.2 * tt)
                    k = ease(u / 0.12)
                    sr = [-0.2 * k, -2.5 * k + 0.4 * wv * k]
                    sl = [0.0, 0.08]
                    nrz = 0.12 * math.sin(2 * math.pi * 0.5 * tt)
                    mo = 1 + 2.5 * env
                elif a == "think":
                    k = ease(u / 0.15)
                    sr = [-2.25 * k, 0.55 * k]
                    sl = [-0.5 * k, -0.6 * k]
                    nry = 0.18 * k; nrx = -0.12 * k
                    rot[2] += 0.06 * math.sin(2 * math.pi * 0.25 * tt)
                    mo = 0.8
                # Extra whole-model motion for rigid Sketchfab meshes.
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
                if f in blink_at: eye_z = 0.12
                else: eye_z = eye
                put(S["root"], "location", f, (O[0] + loc[0], O[1] + loc[1], O[2] + loc[2]))
                put(S["root"], "rotation_euler", f, tuple(rot))
                put(S["pelvis"], "location", f, (0, 0, 0.55 + pz))
                put(S["pelvis"], "rotation_euler", f, (prx, 0, 0))
                put(S["hipL"], "rotation_euler", f, (hl, 0, 0))
                put(S["hipR"], "rotation_euler", f, (hr, 0, 0))
                put(S["shL"], "rotation_euler", f, (sl[0], sl[1], 0))
                put(S["shR"], "rotation_euler", f, (sr[0], sr[1], 0))
                put(S["neck"], "rotation_euler", f, (nrx, nry, nrz))
                for e in S["eyes"]: put(e, "scale", f, (eye, 1, eye_z))
                put(S["brows"], "location", f, (0, 0, brow))
                put(S["mouth"], "scale", f, (1 + 0.15 * (mo - 1) * 0.3, 1, min(4, mo)))
                put(S["stool"], "scale", f, (stool,) * 3)
                for kind, p in S["props"].items():
                    show = role == 0 and sc_["prop"] == kind
                    sz = 0.0
                    if show:
                        sz = ease(tt / 0.2)
                        if kind == "lightbulb": sz *= 1 + 0.08 * math.sin(2 * math.pi * 2 * tt)
                    put(p, "scale", f, (sz,) * 3)
                    if kind in ("lightbulb", "clock"):
                        put(p, "location", f, (0.0, 0.0, 0.85 + 0.04 * math.sin(2 * math.pi * 0.8 * tt)))

        # ---- camera for this sentence
        lead = CH[ids[0]]
        H = 1.75 * (0.8 if lead["type"] in ("boy", "girl") else 1.0)
        if act in ("celebrate", "jump", "shocked", "wave"): H += 0.5
        if sc_["prop"] in ("lightbulb", "clock"): H += 0.45
        W = {1: 1.5, 2: 2.5, 3: 3.4}[n]
        if act == "fall": W = max(W, 2.6)
        # Semantic shot plan: frame each story beat intentionally.
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

        prev_shot = shot
        lens = 32.0
        vt = 18.0 / lens; ht = vt * RES[0] / RES[1]
        d = (W / 2) / ht * 1.12
        az0 = az1 = 0.0; tilt = 0.12; zoom0, zoom1 = 1.0, 1.0
        if shot == "wide": zoom0, zoom1 = 1.18, 1.02
        elif shot == "medium": zoom0, zoom1 = 1.0, 0.93; az0, az1 = -0.08, 0.08
        elif shot == "low": tilt = -0.18; zoom0, zoom1 = 1.05, 0.95
        elif shot == "high": tilt = 0.42; zoom0, zoom1 = 1.08, 1.0
        elif shot == "orbit": az0, az1 = rng.choice([(-0.3, 0.1), (0.3, -0.1)])
        elif shot == "close": zoom0, zoom1 = 0.9, 0.82
        elif shot == "track_low": tilt = -0.1
        if moving:
            gx0, gx1 = sum(xs) / n - dist / 2, sum(xs) / n + dist / 2
            W2 = W + 0.6
            d = (W2 / 2) / ht * 1.12
        else:
            gx0 = gx1 = sum(xs) / n if shot != "close" else xs[0]
        if act == "fall":   # frame the body where it lands
            side = 1 if xs[0] >= 0 else -1
            gx0, gx1 = gx0 + side * 0.25, gx0 + side * 0.75
            if shot == "close": shot = "medium"
        gy = 0.1
        for (fk, gx, az, z) in ((f0, gx0, az0, zoom0), (f1, gx1, az1, zoom1)):
            dd = d * z
            V = 2 * dd * vt
            if shot == "close":
                aim_z = H * 0.72
            else:
                aim_z = max(0.18 * V, H - 0.28 * V)
            cz = aim_z + dd * math.tan(tilt)
            if shot in ("low", "track_low"): cz = max(0.35, cz)
            cam = (O[0] + gx + dd * math.sin(az), O[1] + gy - dd * math.cos(az), O[2] + cz)
            aim = (O[0] + gx, O[1] + gy, O[2] + aim_z)
            cam_keys.append((fk, cam, aim))

    # ------------------------------------------------------------ camera, lights, world
    camd = bpy.data.cameras.new("cam"); camd.lens = 32.0; camd.sensor_fit = "AUTO"; camd.sensor_width = 36
    camd.clip_start = 0.05; camd.clip_end = 300
    cam = bpy.data.objects.new("cam", camd); coll.objects.link(cam); sc.camera = cam
    aim = empty("aim")
    con = cam.constraints.new("TRACK_TO"); con.target = aim; con.track_axis = "TRACK_NEGATIVE_Z"; con.up_axis = "UP_Y"
    sund = bpy.data.lights.new("sun", "SUN"); sund.angle = math.radians(0.5)
    sun = bpy.data.objects.new("sun", sund); coll.objects.link(sun)
    sun.rotation_euler = (math.radians(48), math.radians(12), math.radians(-28))
    world = bpy.data.worlds.new("w"); world.use_nodes = True; sc.world = world
    wn = world.node_tree
    bg = wn.nodes["Background"]
    lp = wn.nodes.new("ShaderNodeLightPath"); mix = wn.nodes.new("ShaderNodeMixShader")
    dark = wn.nodes.new("ShaderNodeBackground"); dark.inputs["Strength"].default_value = 0.0
    wn.links.new(lp.outputs["Is Camera Ray"], mix.inputs[0])
    wn.links.new(dark.outputs[0], mix.inputs[1]); wn.links.new(bg.outputs[0], mix.inputs[2])
    wn.links.new(mix.outputs[0], wn.nodes["World Output"].inputs["Surface"])
    try:
        world.cycles.sampling_method = "NONE"
    except Exception:
        pass
    fill = bpy.data.lights.new("fill", "SUN"); fill.energy = 0.7; fill.color = (0.8, 0.88, 1.0)
    try:
        fill.cycles.cast_shadow = False
    except Exception:
        fill.use_shadow = False
    fo = bpy.data.objects.new("fill", fill); coll.objects.link(fo)
    fo.rotation_euler = (math.radians(60), math.radians(-35), math.radians(150))

    for (fk, c, a_) in cam_keys:
        cam.location = c; cam.keyframe_insert("location", frame=fk)
        aim.location = a_; aim.keyframe_insert("location", frame=fk)
    for k, (fk, col, st) in enumerate(world_keys):
        for ff in ([fk - 1, fk] if fk > 0 else [fk]):
            c_, s_ = (world_keys[k - 1][1], world_keys[k - 1][2]) if ff == fk - 1 else (col, st)
            bg.inputs["Color"].default_value = (*c_, 1); bg.inputs["Strength"].default_value = s_
            bg.inputs["Color"].keyframe_insert("default_value", frame=ff)
            bg.inputs["Strength"].keyframe_insert("default_value", frame=ff)
    for k, (fk, col, st) in enumerate(sun_keys):
        for ff in ([fk - 1, fk] if fk > 0 else [fk]):
            c_, s_ = (sun_keys[k - 1][1], sun_keys[k - 1][2]) if ff == fk - 1 else (col, st)
            sund.color = c_; sund.energy = s_
            sund.keyframe_insert("color", frame=ff); sund.keyframe_insert("energy", frame=ff)
            amb_val.outputs[0].default_value = 0.22 if s_ < 2 else 0.36
            amb_val.outputs[0].keyframe_insert("default_value", frame=ff)

    # bulk-write the per-frame character channels
    t_k = time.time()
    for ci, anim in ANIM.items():
        anim.bake(QF[ci])
        sk = CH[ci].get("blink")
        if sk is not None:   # natural, unsynchronised blinks: every 2.2-4.8 s, ~5 frames each
            brng = random.Random(story.get("seed", 1) * 31 + ci * 7)
            tb = brng.uniform(0.6, 2.0)
            keys = {0: 0.0}
            while tb * FPS < N - 6:
                b = int(tb * FPS)
                keys.update({b - 1: 0.0, b: 0.75, b + 1: 1.0, b + 2: 1.0, b + 3: 0.45, b + 4: 0.0})
                if brng.random() < 0.18 and (b + 9) < N - 6:   # occasional double blink
                    keys.update({b + 6: 0.8, b + 7: 1.0, b + 8: 0.4, b + 9: 0.0})
                tb += brng.uniform(2.2, 4.8)
            for fb in sorted(keys):
                sk.value = keys[fb]
                sk.keyframe_insert("value", frame=fb)
    if ANIM:
        print(f"skeletal bake: {len(ANIM)} rigs x {N} frames in {time.time() - t_k:.1f}s", flush=True)
    for key, (obj, vals) in track.items():
        attr = key[1]
        last = None
        for f in range(N):
            if vals[f] is None: vals[f] = last if last is not None else (OFF if attr == "location" and obj.name.endswith("_root") else getattr(obj, attr)[:])
            last = vals[f]
        bake(obj, attr, vals)
    print(f"keyframes: {len(track)} channels x {N} frames in {time.time() - t_k:.1f}s", flush=True)

    # ------------------------------------------------------------ render settings
    r = sc.render
    r.engine = "CYCLES"
    r.resolution_x, r.resolution_y = RES
    r.resolution_percentage = opt["res_pct"]   # 100 in production (CI never passes --res-pct); never lowered
    r.fps = FPS
    r.use_persistent_data = True
    r.image_settings.file_format = "PNG"; r.image_settings.color_mode = "RGB"; r.image_settings.compression = 15
    r.film_transparent = False
    try:
        sc.view_settings.view_transform = "Standard"; sc.view_settings.look = "None"
    except Exception:
        pass
    sc.view_settings.exposure = 0.0
    cy = sc.cycles
    cy.device = "CPU"
    cy.samples = opt["samples"]
    cy.use_adaptive_sampling = False
    cy.max_bounces = 0; cy.diffuse_bounces = 0; cy.glossy_bounces = 0; cy.transmission_bounces = 0
    cy.volume_bounces = 0; cy.transparent_max_bounces = 2; cy.caustics_reflective = False; cy.caustics_refractive = False
    cy.sample_clamp_indirect = 3.0
    cy.use_denoising = False
    try:
        cy.denoiser = "OPENIMAGEDENOISE"; cy.use_denoising = True
        cy.denoising_input_passes = "RGB_ALBEDO_NORMAL"; cy.denoising_prefilter = os.environ.get("BB_DENOISE_PREFILTER", "ACCURATE")
    except Exception as e:
        print("no OpenImageDenoise in this Blender build: rendering without denoise", flush=True)
    try:
        cy.use_light_tree = False   # no mesh lights here; faster without
    except Exception:
        pass

    for kv in filter(None, os.environ.get("BB_CYCLES", "").split(",")):   # tuning: BB_CYCLES="samples=8,max_bounces=1"
        k_, v_ = kv.split("=")
        cur = getattr(cy, k_)
        setattr(cy, k_, type(cur)(v_ if not isinstance(cur, bool) else v_ in ("1", "True", "true")))
        print("  cycles override", k_, "=", getattr(cy, k_), flush=True)

    frames_dir = story["out"].replace(".mp4", "_frames")
    os.makedirs(frames_dir, exist_ok=True)
    r.filepath = os.path.abspath(frames_dir) + "/f#####"
    todo = [f for f in (opt["frames"] or range(N)) if 0 <= f < N]
    budget = float(os.environ.get("BB_BUDGET_MIN", "24")) * 60
    if os.environ.get("BB_DEADLINE"):   # epoch seconds the Blender stage must finish by (set by the workflow)
        budget = min(budget, float(os.environ["BB_DEADLINE"]) - time.time())
    t0 = time.time(); done = 0; step = 1; k = 0; chunk = 8
    print(f"render: {len(todo)} frames ({N / FPS:.1f}s video) {RES[0]}x{RES[1]}@{r.resolution_percentage}% "
          f"samples={cy.samples} denoise={cy.use_denoising} budget={budget / 60:.1f}m", flush=True)
    while k < len(todo):
        batch = todo[k:k + chunk * step:step]
        k += chunk * step
        tc = time.time()
        # consecutive runs render as one animation call (fast, persistent data); others one by one
        runs, cur = [], [batch[0]]
        for x in batch[1:]:
            if x == cur[-1] + step: cur.append(x)
            else: runs.append(cur); cur = [x]
        runs.append(cur)
        for run in runs:
            sc.frame_start, sc.frame_end, sc.frame_step = run[0], run[-1], step
            bpy.ops.render.render(animation=True)
        done += len(batch)
        per = (time.time() - tc) / len(batch)          # seconds per rendered frame, latest settings
        el = time.time() - t0
        left = len(todo[k::step])
        proj = el + per * left
        print(f"  {done} frames  {per:.2f}s/frame  elapsed {el / 60:.1f}m  projected {proj / 60:.1f}m", flush=True)
        if left and proj < 0.62 * budget and cy.samples < MAX_SAMPLES and step == 1:
            cy.samples += 1   # comfortably inside the budget: spend it on cleaner frames
            print("  under budget -> samples", cy.samples, flush=True)
        elif left and proj > budget:
            # over budget: trade quality for time - samples, then resolution, then animate "on twos"
            # keep motion smooth (every frame) as long as possible; OIDN hides the low sample count
            # resolution is locked at 100%: only the sample count gives way (OIDN cleans the result)
            if cy.samples > 2:
                fit = int(cy.samples * (budget - el) / max(1e-3, per * left) * 0.92)
                cy.samples = max(2, min(cy.samples - 1, fit))
                print("  over budget -> samples", cy.samples, flush=True)
            elif step == 1 and opt["frames"] is None:
                step = 2; print("  over budget -> rendering every 2nd frame (held)", flush=True)
        chunk = 24
    print(f"blender frames done in {(time.time() - t0) / 60:.1f} min", flush=True)
    json.dump({"render_s": round(time.time() - t0, 1), "frames": done, "nframes": N,
               "per_frame_s": round((time.time() - t0) / max(1, done), 3),
               "samples": cy.samples, "res_pct": r.resolution_percentage, "step": step},
              open(story["out"] + ".render.json", "w"))
    if opt["compose"]:
        py = os.environ.get("BB_PYTHON") or shutil.which("python3") or "python3"
        env = {k: v for k, v in os.environ.items() if k not in ("PYTHONHOME", "PYTHONPATH")}
        subprocess.run([py, os.path.abspath(__file__), "--compose", story_path, frames_dir], check=True, env=env)


def bake(obj, attr, vals):
    """Write one keyframe per frame for obj.attr (vector or scalar). Fast fcurve path, slow fallback."""
    n = len(vals)
    vec = isinstance(vals[0], (tuple, list))
    dims = len(vals[0]) if vec else 1
    setattr(obj, attr, vals[0])
    obj.keyframe_insert(attr, frame=0)
    try:
        ad = obj.animation_data; act = ad.action
        try:
            fcs = act.fcurves
        except AttributeError:   # Blender 5 slotted actions
            fcs = act.layers[0].strips[0].channelbag(ad.action_slot).fcurves
        for i in range(dims):
            fc = fcs.find(attr, index=i)
            kp = fc.keyframe_points
            kp.add(n - 1)
            co = []
            for f in range(n):
                co += [float(f), float(vals[f][i] if vec else vals[f])]
            kp.foreach_set("co", co)
            kp.foreach_set("interpolation", [1] * n)  # LINEAR
            fc.update()
    except Exception as e:
        print("fast keyframes failed, slow path:", e, flush=True)
        for f in range(n):
            setattr(obj, attr, vals[f]); obj.keyframe_insert(attr, frame=f)


# ================================================================= COMPOSE STAGE (system python: numpy + Pillow)
def compose(story_path, frames_dir):
    import numpy as np
    from PIL import Image, ImageDraw, ImageFilter
    sys.argv = [sys.argv[0]]
    import render3d as R

    cfg = json.load(open(story_path))
    have = {int(p[1:-4]): p for p in os.listdir(frames_dir) if p.startswith("f") and p.endswith(".png")}
    if not have:
        raise SystemExit("no frames rendered")
    nfr = max(have) + 1                     # frames not rendered (on-twos fallback) hold the previous one
    frames, last = [], have[min(have)]
    for i in range(nfr):
        last = have.get(i, last); frames.append(last)
    vlines = [R.load_voice(p) for p in cfg["voice_lines"]] if cfg.get("voice_lines") else None
    if vlines:
        sst, t = [], LEAD
        for v in vlines:
            sst.append(t); t += len(v) / 44100 + GAP
        durs = [len(v) / 44100 for v in vlines]
    else:
        tl, _ = timeline(cfg)
        sst = [a for a, _ in tl]; durs = [b for _, b in tl]
    words = " ".join(s["hi"] for s in cfg["sentences"]).split()
    starts = []
    for j, s_ in enumerate(cfg["sentences"]):
        ws = s_["hi"].split(); d = durs[j]
        wt = np.array([0.22 + 0.045 * len(w) for w in ws]); a = np.cumsum(np.r_[0, wt[:-1]]) / wt.sum()
        starts += list(sst[j] + 0.05 + a * (d - 0.1))
    ch = R.chunks(words)
    total = nfr / FPS
    bounds, k = [], 0
    for s in cfg["sentences"]:
        n = len(s["hi"].split()); bounds.append((starts[k], k, k + n)); k += n
    for lang in ("hi", "en", "hd", "te"):
        lines = []
        for j, (st, a, b) in enumerate(bounds):
            en = bounds[j + 1][0] if j + 1 < len(bounds) else total
            lines.append(f"{j+1}\n{R.srt_time(st)} --> {R.srt_time(en)}\n{cfg['sentences'][j][lang]}\n")
        open(cfg["out"].replace(".mp4", f".{lang}.srt"), "w").write("\n".join(lines))
    pj = len(cfg["sentences"]) - 1
    esc = sst[pj]
    wav = cfg["out"] + ".wav"
    R.audio([], int(total * R.FPS), esc, wav, list(zip(sst, vlines)) if vlines else None, music=True, bounces=False)
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                           "-s", f"{OUT_W}x{OUT_H}", "-r", str(FPS), "-i", "-", "-i", wav,
                           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "19", "-preset", "veryfast",
                           "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", cfg["out"]],
                          stdin=subprocess.PIPE)
    t0 = time.time()
    prev_name, base = None, None
    for i, name in enumerate(frames):
        t = i / FPS
        if name != prev_name:
            base = Image.open(os.path.join(frames_dir, name)).convert("RGB")
            if base.size != (OUT_W, OUT_H):
                base = base.resize((OUT_W, OUT_H), Image.LANCZOS)
                base = base.filter(ImageFilter.UnsharpMask(radius=2, percent=70, threshold=2))
            prev_name = name
        img = base.copy()
        dr = ImageDraw.Draw(img)
        if t < 2.4 and cfg.get("hook"):
            # big two-line hook instead of one long line squeezed tiny
            hook_words = cfg["hook"].split()   # own name: `words` is the caption word list used below
            lines, cur = [], ""
            for w_ in hook_words:
                trial = (cur + " " + w_).strip()
                if cur and dr.textlength(trial, font=R.font(84)) > 960:
                    lines.append(cur); cur = w_
                else:
                    cur = trial
            if cur: lines.append(cur)
            for li, line in enumerate(lines[:3]):
                R.text_c(dr, 250 + li * 100, line, 84, stroke=7)
        cur = max([k for k, s0 in enumerate(starts) if s0 <= t] or [0])
        cid = next((c for c in ch if cur in c), ch[0])
        if t >= starts[0] - 0.1:
            R.draw_caption(dr, words, cid, cur if t >= starts[0] else -1)
        ff.stdin.write(img.tobytes())
    ff.stdin.close()
    if ff.wait() != 0:
        raise SystemExit("ffmpeg mux failed")
    os.remove(wav)
    if not os.environ.get("BB_KEEP_FRAMES"):
        shutil.rmtree(frames_dir, ignore_errors=True)
    json.dump({"seed": cfg.get("seed"), "esc": esc, "bounces": 0, "tail_pad": 0.8, "engine": "blender"},
              open(cfg["out"] + ".meta.json", "w"))
    print(f"composed {nfr} frames in {time.time() - t0:.0f}s ->", cfg["out"], flush=True)


if __name__ == "__main__":
    if "--compose" in sys.argv:
        i = sys.argv.index("--compose")
        compose(sys.argv[i + 1], sys.argv[i + 2])
    else:
        argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
        blender_main(argv)
