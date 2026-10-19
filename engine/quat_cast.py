"""Rigged cartoon cast for render_blender.py: CC0 Quaternius characters + their baked skeletal clips.

Everything is local and deterministic: assets/characters/cast.blend (built by assets/characters/build_library.py)
holds 18 rigged people + 1 robot and one shared clip set per rig family (M men, W women, R robot).

The animator does NOT use the NLA. For every frame it samples the clip chosen for the story beat, cross-fades
into the next beat's clip, then layers procedural overlays (talk gestures, head nods, think/celebrate/shocked
arm poses, sitting legs) in armature space, and bakes one keyframe per bone per frame. So one-shot clips
(Death, HitRecieve) play once and hold, loops loop, and nothing depends on NLA evaluation quirks.
"""
import math
import os

import bpy
from mathutils import Matrix, Quaternion, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(HERE, "..", "assets", "characters", "cast.blend")

# story cast type -> candidate library characters (picked deterministically, never the same twice per story)
ROSTER = {
    "man": ["M_Casual_Hoodie", "M_Casual_2", "M_Punk", "M_Worker", "M_Adventurer", "M_Suit"],
    "woman": ["W_Casual", "W_Formal", "W_Punk", "W_Adventurer", "W_Worker", "W_Suit"],
    "boy": ["M_Beach", "M_Casual_2", "M_Casual_Hoodie"],
    "girl": ["W_Casual", "W_Adventurer", "W_Punk"],
    "grandpa": ["M_Farmer", "M_King"],
    "grandma": ["W_Medieval", "W_Formal"],
    "scientist": ["M_Suit", "W_SciFi", "M_Spacesuit"],
    "robot": ["R_Robot"],
}
# target standing height in metres (to the top of the hair) per cast type
HEIGHT = {"man": 1.80, "woman": 1.72, "boy": 1.30, "girl": 1.26, "grandpa": 1.72, "grandma": 1.64,
          "scientist": 1.80, "robot": 1.45}

# beat action -> clip per family. Loops loop; ONESHOT clips play once and hold their last frame.
CLIP = {
    "M": {"walk": "Walk", "run": "Run", "talk": "Idle", "listen": "Idle_Neutral", "point": "Idle_Neutral",
          "jump": "Idle", "fall": "Death", "sit": "Idle_Neutral", "celebrate": "Idle", "shocked": "HitRecieve",
          "wave": "Wave", "think": "Idle_Neutral"},
    "R": {"walk": "Walking", "run": "Running", "talk": "Idle", "listen": "Yes", "point": "ThumbsUp",
          "jump": "Jump", "fall": "Death", "sit": "Sitting", "celebrate": "Dance", "shocked": "No",
          "wave": "Wave", "think": "Idle"},
}
CLIP["W"] = dict(CLIP["M"])
ONESHOT = {"Death", "HitRecieve", "Sitting", "Standing", "Interact"}
# natural ground speed of the locomotion clips at scale 1 (measured from the foot plant), m/s
NATURAL_SPEED = {("M", "Walk"): 1.32, ("M", "Run"): 2.53, ("W", "Walk"): 1.06, ("W", "Run"): 2.08,
                 ("R", "Walking"): 3.09, ("R", "Running"): 4.1}
XFADE = 6   # frames of cross-fade between beats


def available():
    return os.path.isfile(LIB) and os.environ.get("BB_CHARACTERS", "quaternius") != "procedural"


def load_clips():
    with bpy.data.libraries.load(LIB, link=False) as (src, dst):
        dst.actions = list(src.actions)
    return {a.name: a for a in dst.actions if a is not None}


def pick_keys(cast, seed):
    used, outfits, keys = set(), set(), []
    for ci, c in enumerate(cast):
        opts = ROSTER.get(c["type"], ROSTER["man"])
        start = (seed + ci * 7) % len(opts)
        ring = [opts[(start + k) % len(opts)] for k in range(len(opts))]
        key = next((k for k in ring if k not in used and k[2:] not in outfits),
                   next((k for k in ring if k not in used), ring[0]))
        used.add(key); outfits.add(key[2:])
        keys.append(key)
    return keys


def _base_color(m):
    try:
        bsdf = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
        c = bsdf.inputs["Base Color"].default_value
        return (c[0], c[1], c[2])
    except Exception:
        c = m.diffuse_color
        return (c[0], c[1], c[2])


def build(c, ci, key, ctx):
    """Load one character, restyle its materials to the scene's toon shading, scale it, parent it to a fresh
    root empty and return the dict render_blender uses (root, rig, family, props, stool, mouth ...)."""
    mat, empty, prim, coll, SP = ctx["mat"], ctx["empty"], ctx["prim"], ctx["coll"], ctx["SP"]
    with bpy.data.libraries.load(LIB, link=False) as (src, dst):
        dst.collections = [f"Q_{key}"]
    col = dst.collections[0]
    col.name = f"c{ci}_{key}"
    coll.children.link(col)
    rig = next(o for o in col.objects if o.type == "ARMATURE")
    meshes = [o for o in col.objects if o.type == "MESH"]
    fam = rig["bb_family"]
    t = c["type"]

    # --- materials: same diffuse+ambient toon shading as the sets; shirt takes the story colour
    shirt = SP.COLORS[c["color"]]
    body = next((o for o in meshes if o.name.endswith("Body") or o.name.endswith("Torso")), None)
    tint_slot = None
    if body is not None and fam != "R":
        counts = {}
        for p in body.data.polygons:
            counts[p.material_index] = counts.get(p.material_index, 0) + 1
        skip = ("skin", "eye", "hair", "brow", "gold", "metal", "moustache", "earring")
        cands = [(n, i) for i, n in counts.items()
                 if i < len(body.data.materials) and body.data.materials[i]
                 and not any(s in body.data.materials[i].name.lower() for s in skip)]
        if cands:
            tint_slot = max(cands)[1]
    for o in meshes:
        for i, m in enumerate(o.data.materials):
            if m is None:
                continue
            rgb = _base_color(m)
            low = m.name.lower()
            if o is body and i == tint_slot:
                rgb = shirt
            elif t in ("grandpa", "grandma") and "hair" in low:
                rgb = (0.78, 0.78, 0.76)
            o.data.materials[i] = mat(rgb, 0.6, name=f"c{ci}_{m.name.split('.')[0]}")
        # smooth shading, hard creases kept (shoes, collars, helmet rims)
        o.data.polygons.foreach_set("use_smooth", [True] * len(o.data.polygons))
        try:
            o.data.set_sharp_from_angle(angle=math.radians(40))
        except Exception:
            pass

    # --- scale to the cast type's height, measured on the rest pose
    rig.data.pose_position = "REST"
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    top = 0.0
    head_mesh = None
    for o in meshes:
        e = o.evaluated_get(dg)
        me = e.to_mesh()
        zs = [(e.matrix_world @ v.co).z for v in me.vertices]
        top = max(top, max(zs) if zs else 0)
        e.to_mesh_clear()
        if o.name.endswith("Head"):
            head_mesh = o
    s = HEIGHT.get(t, 1.75) / max(0.3, top)
    root = empty(f"c{ci}_root")
    rig.parent = root
    rig.scale = (s, s, s)
    S = {"type": t, "root": root, "rig": rig, "family": fam, "key": key, "scale": s, "props": {},
         "collection": col}

    # --- lip-sync mouth: a dark disc over the modelled mouth, parented to the Head bone
    if fam != "R" and head_mesh is not None:
        bpy.context.view_layer.update()
        hb = rig.data.bones["Head"]
        mz = (rig.matrix_world @ hb.head_local).z + 0.026 * s
        e = head_mesh.evaluated_get(bpy.context.evaluated_depsgraph_get())
        me = e.to_mesh()
        front = min(((e.matrix_world @ v.co).y for v in me.vertices
                     if abs((e.matrix_world @ v.co).x) < 0.03 * s and abs((e.matrix_world @ v.co).z - mz) < 0.012 * s),
                    default=(rig.matrix_world @ hb.head_local).y - 0.12 * s)
        e.to_mesh_clear()
        mouth = prim("sphere", (0, 0, 0), (0.026 * s, 0.006 * s, 0.012 * s), m=mat((0.07, 0.01, 0.015), 0.4),
                     smooth=True, seg=14)
        mouth.name = f"c{ci}_mouth"
        world = Matrix.Translation((0.0, front - 0.004 * s, mz))
        mouth.parent = rig
        mouth.parent_type = "BONE"
        mouth.parent_bone = "Head"
        bpy.context.view_layer.update()
        mouth.matrix_world = world @ Matrix.Diagonal((0.026 * s, 0.006 * s, 0.012 * s, 1.0))
        S["mouth"] = mouth
        S["mouth_scale"] = tuple(mouth.scale)
    rig.data.pose_position = "POSE"

    # --- stool (shown when sitting): top at knee height
    knee = rig.data.bones.get("LowerLeg.L")
    seat = ((rig.matrix_world @ knee.head_local).z if knee else 0.45 * s) if fam != "R" else 0.0
    S["seat"] = seat
    hip = rig.data.bones.get("UpperLeg.L")
    S["sit_drop"] = max(0.0, ((rig.matrix_world @ hip.head_local).z - seat) - 0.03 * s) if (hip and knee) else 0.0
    stool = empty(f"c{ci}_stool", (0, 0.06 * s, 0), root)
    prim("cyl", (0, 0, seat - 0.03), (0.22, 0.22, 0.06), m=mat((0.5, 0.25, 0.08), 0.5), parent=stool, seg=20)
    prim("cyl", (0, 0, (seat - 0.06) / 2), (0.05, 0.05, max(0.05, seat - 0.06)), m=mat((0.2, 0.2, 0.2), 0.4),
         parent=stool, seg=10)
    S["stool"] = stool
    S["hand_bone"] = "Wrist.R" if fam != "R" else "LowerArm.R"
    S["head_bone"] = "Head"
    return S


def attach_prop(S, kind, build_geo, empty, clips):
    """Held props follow the right hand bone; lightbulb/clock float above the head bone.
    Attached while the rig shows its idle pose, so a held prop sits naturally in the lowered hand."""
    rig = S["rig"]
    if rig.animation_data is None:
        rig.animation_data_create()
    rig.animation_data.action = clips.get(f"{S['family']}|Idle")
    bpy.context.scene.frame_set(0)
    p = empty(f"{rig.name}_{kind}")
    p.parent = rig
    p.parent_type = "BONE"
    floating = kind in ("lightbulb", "clock")
    p.parent_bone = S["head_bone"] if floating else S["hand_bone"]
    bpy.context.view_layer.update()
    s = S["scale"]
    pb = rig.pose.bones[p.parent_bone]
    if floating:
        top = rig.matrix_world @ pb.tail
        p.matrix_world = Matrix.Translation((top.x, top.y, top.z + 0.42 * s))
    else:
        tip = rig.matrix_world @ pb.tail
        p.matrix_world = Matrix.Translation((tip.x, tip.y - 0.04 * s, tip.z - 0.06 * s))
    rig.animation_data.action = None
    build_geo(p)
    S["props"][kind] = p
    return p


# ============================================================================ animator
class Animator:
    """Samples clips, blends beats, layers overlays and bakes a per-frame pose for one rig."""

    def __init__(self, S, clips):
        self.S = S
        self.rig = S["rig"]
        self.fam = S["family"]
        self.clips = clips
        self.cache = {}
        bones = self.rig.data.bones
        self.order = [b.name for b in bones]   # bones are stored parent-first
        self.parent = {b.name: (b.parent.name if b.parent else None) for b in bones}
        self.rest_arm = {b.name: b.matrix_local.to_quaternion() for b in bones}
        self.rest_rel = {}
        for b in bones:
            pr = b.parent.matrix_local.to_quaternion() if b.parent else Quaternion()
            self.rest_rel[b.name] = pr.inverted() @ self.rest_arm[b.name]
        for pb in self.rig.pose.bones:
            pb.rotation_mode = "QUATERNION"

    # ---- clip sampling
    def clip_name(self, action):
        return CLIP[self.fam].get(action, CLIP[self.fam]["talk"])

    def table(self, clip):
        """Pre-sample a clip at every integer frame: list of {bone: (loc, quat, scale)}."""
        if clip in self.cache:
            return self.cache[clip]
        act = self.clips.get(f"{self.fam}|{clip}") or self.clips[f"{self.fam}|Idle"]
        chans = {}
        for fc in act.fcurves:
            dp = fc.data_path
            if not dp.startswith("pose.bones["):
                continue
            bone = dp.split('"')[1]
            prop = dp.rsplit(".", 1)[-1]
            chans.setdefault(bone, {}).setdefault(prop, {})[fc.array_index] = fc
        n = max(1, int(math.ceil(act.frame_range[1] - act.frame_range[0])))
        f0 = act.frame_range[0]
        rows = []
        for k in range(n + 1):
            fr = f0 + k
            row = {}
            for bone, props in chans.items():
                loc = Vector([props.get("location", {}).get(i).evaluate(fr) if i in props.get("location", {}) else 0.0
                              for i in range(3)])
                rq = props.get("rotation_quaternion", {})
                q = Quaternion([rq[i].evaluate(fr) if i in rq else (1.0 if i == 0 else 0.0) for i in range(4)])
                q.normalize()
                sc = props.get("scale", {})
                scl = Vector([sc[i].evaluate(fr) if i in sc else 1.0 for i in range(3)])
                row[bone] = (loc, q, scl)
            rows.append(row)
        self.cache[clip] = rows
        return rows

    def sample(self, clip, t):
        """t in clip frames (float). Loops wrap, one-shots clamp."""
        rows = self.table(clip)
        n = len(rows) - 1
        if clip in ONESHOT:
            t = min(max(t, 0.0), float(n))
        else:
            t = t % n if n > 0 else 0.0
        i = int(math.floor(t)); a = t - i
        r0, r1 = rows[i], rows[min(i + 1, n)]
        if clip not in ONESHOT and i + 1 > n:
            r1 = rows[0]
        return _mix(r0, r1, a)

    # ---- armature-space rotation helpers (rotations only; enough for aiming limbs)
    def arm_rot(self, pose, name, memo):
        if name in memo:
            return memo[name]
        p = self.parent[name]
        pr = self.arm_rot(pose, p, memo) if p else Quaternion()
        q = pose[name][1] if name in pose else Quaternion()
        r = pr @ self.rest_rel[name] @ q
        memo[name] = r
        return r

    def rotate(self, pose, name, D, memo):
        """Apply armature-space rotation D at bone `name` (children follow)."""
        if name not in self.parent:
            return
        p = self.parent[name]
        pr = self.arm_rot(pose, p, memo) if p else Quaternion()
        frame = pr @ self.rest_rel[name]
        loc, q, scl = pose.get(name, (Vector(), Quaternion(), Vector((1, 1, 1))))
        q2 = frame.inverted() @ D @ frame @ q
        q2.normalize()
        pose[name] = (loc, q2, scl)
        for k in [k for k in memo if k == name or self._below(k, name)]:
            memo.pop(k, None)

    def _below(self, k, name):
        p = self.parent.get(k)
        while p:
            if p == name:
                return True
            p = self.parent.get(p)
        return False

    def aim(self, pose, name, target, k, memo):
        """Swing bone `name` so its axis points along armature-space `target`, by weight k (0..1)."""
        if k <= 0.001 or name not in self.parent:
            return
        cur = self.arm_rot(pose, name, memo) @ Vector((0, 1, 0))
        D = cur.rotation_difference(Vector(target).normalized())
        self.rotate(pose, name, Quaternion().slerp(D, min(1.0, k)), memo)

    # ---- bake
    def bake(self, frames):
        """frames: list (one per frame) of dicts {clip, t, clip2, t2, w2, over} -> keyframes on the rig."""
        rig = self.rig
        n = len(frames)
        out = {}
        for f, fr in enumerate(frames):
            if fr is None:
                pose = self.sample(self.clip_name("listen"), 0.0)
            else:
                pose = self.sample(fr["clip"], fr["t"])
                if fr.get("w2", 0) > 0:
                    pose = _mix(pose, self.sample(fr["clip2"], fr["t2"]), fr["w2"])
                over = fr.get("over")
                if over and self.fam != "R":
                    self.overlay(pose, over)
            for bone, v in pose.items():
                out.setdefault(bone, [None] * n)[f] = v
        if rig.animation_data is None:
            rig.animation_data_create()
        rig.animation_data.action = None
        pbs = rig.pose.bones
        for bone, vals in out.items():
            pb = pbs.get(bone)
            if pb is None:
                continue
            last = next(v for v in vals if v is not None)
            for i in range(n):
                if vals[i] is None:
                    vals[i] = last
                last = vals[i]
            for prop, idx, dims in (("location", 0, 3), ("rotation_quaternion", 1, 4), ("scale", 2, 3)):
                series = [tuple(v[idx]) for v in vals]
                if prop == "scale" and all(abs(c - 1.0) < 1e-4 for s in series for c in s):
                    continue
                _bake_bone(rig, pb, prop, series)

    def overlay(self, pose, o):
        """Procedural layers on top of the clip, in armature space (character faces -Y, its right is -X)."""
        memo = {}
        k = o.get("k", 1.0)
        a = o.get("pose")
        if a == "think":       # right hand to the chin, head tilted
            self.aim(pose, "UpperArm.R", (-0.20, -0.55, -0.81), k, memo)
            self.aim(pose, "LowerArm.R", (0.55, -0.45, 0.70), k, memo)
            self.aim(pose, "UpperArm.L", (0.15, -0.35, -0.92), k * 0.6, memo)
            self.aim(pose, "LowerArm.L", (-0.75, -0.55, 0.05), k * 0.8, memo)
        elif a == "celebrate":  # both arms up, pumping
            pump = o.get("pump", 0.0)
            self.aim(pose, "UpperArm.R", (-0.55, -0.10, 0.83), k, memo)
            self.aim(pose, "UpperArm.L", (0.55, -0.10, 0.83), k, memo)
            self.aim(pose, "LowerArm.R", (-0.25 - 0.2 * pump, -0.15, 0.95), k, memo)
            self.aim(pose, "LowerArm.L", (0.25 + 0.2 * pump, -0.15, 0.95), k, memo)
        elif a == "shocked":    # hands thrown up beside the face
            self.aim(pose, "UpperArm.R", (-0.75, -0.25, -0.30), k, memo)
            self.aim(pose, "UpperArm.L", (0.75, -0.25, -0.30), k, memo)
            self.aim(pose, "LowerArm.R", (-0.15, -0.35, 0.92), k, memo)
            self.aim(pose, "LowerArm.L", (0.15, -0.35, 0.92), k, memo)
        elif a == "point":      # one arm straight out at the target (+1 = character's left / screen right)
            sd = o.get("side", 1.0)
            arm = "L" if sd > 0 else "R"
            self.aim(pose, f"UpperArm.{arm}", (0.80 * sd, -0.58, 0.16), k, memo)
            self.aim(pose, f"LowerArm.{arm}", (0.78 * sd, -0.60, 0.20), k, memo)
            self.aim(pose, f"Wrist.{arm}", (0.78 * sd, -0.60, 0.20), k, memo)
        elif a == "jump":       # arms swing up while airborne
            self.aim(pose, "UpperArm.R", (-0.50, -0.15, 0.85), k, memo)
            self.aim(pose, "UpperArm.L", (0.50, -0.15, 0.85), k, memo)
            self.aim(pose, "LowerArm.R", (-0.30, -0.15, 0.94), k, memo)
            self.aim(pose, "LowerArm.L", (0.30, -0.15, 0.94), k, memo)
        if o.get("sit"):        # thighs forward, shins down
            ks = o["sit"]
            for side in ("L", "R"):
                x = 0.08 if side == "L" else -0.08
                self.aim(pose, f"UpperLeg.{side}", (x, -1.0, -0.05), ks, memo)
                self.aim(pose, f"LowerLeg.{side}", (0.0, -0.12, -1.0), ks, memo)
                self.aim(pose, f"Foot.{side}", (0.0, -0.3, -0.95), ks * 0.5, memo)
        g = o.get("gesture", 0.0)   # talking hand: right forearm lifts and opens with the voice
        if g > 0.001 and a not in ("think", "celebrate", "shocked", "point"):
            self.aim(pose, "UpperArm.R", (-0.35, -0.45, -0.82), g * 0.8, memo)
            self.aim(pose, "LowerArm.R", (-0.25, -0.95, 0.20), g, memo)
        nod = o.get("nod", 0.0)
        turn = o.get("turn", 0.0)
        tilt = o.get("tilt", 0.0)
        if abs(nod) + abs(turn) + abs(tilt) > 1e-4:
            D = Quaternion((0, 0, 1), turn) @ Quaternion((1, 0, 0), nod) @ Quaternion((0, 1, 0), tilt)
            self.rotate(pose, "Head", D, memo)
        lean = o.get("lean", 0.0)
        if abs(lean) > 1e-4:
            self.rotate(pose, "Torso" if "Torso" in self.parent else "Chest", Quaternion((1, 0, 0), lean), memo)


def _mix(a, b, w):
    if w <= 0.0:
        return dict(a)
    if w >= 1.0:
        return dict(b)
    out = {}
    for bone in set(a) | set(b):
        if bone not in a:
            out[bone] = b[bone]; continue
        if bone not in b:
            out[bone] = a[bone]; continue
        la, qa, sa = a[bone]
        lb, qb, sb = b[bone]
        if qa.dot(qb) < 0:
            qb = -qb
        q = Quaternion([qa[i] * (1 - w) + qb[i] * w for i in range(4)])
        q.normalize()
        out[bone] = (la.lerp(lb, w), q, sa.lerp(sb, w))
    return out


def _bake_bone(rig, pb, prop, series):
    n = len(series)
    setattr(pb, prop, series[0])
    pb.keyframe_insert(prop, frame=0)
    dp = f'pose.bones["{pb.name}"].{prop}'
    ad = rig.animation_data
    act = ad.action
    try:
        fcs = act.fcurves
    except AttributeError:   # Blender 5 slotted actions
        fcs = act.layers[0].strips[0].channelbag(ad.action_slot).fcurves
    for i in range(len(series[0])):
        fc = fcs.find(dp, index=i)
        kp = fc.keyframe_points
        kp.add(n - 1)
        co = []
        for f in range(n):
            co += [float(f), float(series[f][i])]
        kp.foreach_set("co", co)
        kp.foreach_set("interpolation", [1] * n)
        fc.update()


def ease(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)
