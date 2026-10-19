#!/usr/bin/env python3
"""Build assets/characters/cast.blend from the CC0 Quaternius packs (run once, by hand; output is committed).

  blender -b --factory-startup --python assets/characters/build_library.py -- MEN_GLTF_DIR WOMEN_GLTF_DIR ROBOT_BLEND

Sources (CC0, quaternius.com):
  Ultimate Modular Men Pack (Feb 2022)   -> Individual Characters/glTF/*.gltf
  Ultimate Modular Women Pack (Apr 2022) -> Individual Characters/glTF/*.gltf
  Animated Robot (Oct 2018)              -> Blend/Robot.blend

Output: one collection per character "Q_<key>" holding an armature "<key>_rig" (meshes parented to it),
plus a shared clip set per rig family stored as fake-user actions named "<family>|<Clip>"
(family M = men, W = women, R = robot). The renderer links nothing at run time from the web.
"""
import os, sys
import bpy

argv = sys.argv[sys.argv.index("--") + 1:]
MEN, WOMEN, ROBOT = argv[:3]
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cast.blend")

MEN_CHARS = ["Casual_Hoodie", "Casual_2", "Beach", "Suit", "Farmer", "King", "Punk", "Worker", "Spacesuit", "Adventurer"]
WOMEN_CHARS = ["Casual", "Formal", "Punk", "Adventurer", "Medieval", "SciFi", "Suit", "Worker"]
CLIPS = ["Idle", "Idle_Neutral", "Walk", "Run", "Wave", "Interact", "Idle_Gun_Pointing", "HitRecieve",
         "Death", "Punch_Right", "Roll"]
ROBOT_CLIPS = ["Idle", "Walking", "Running", "Wave", "Dance", "Death", "Jump", "Sitting", "Yes", "No",
               "ThumbsUp", "Punch", "Standing"]

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.context.scene.render.fps = 24
keep_actions = set()


def import_gltf(path, family, key, take_clips):
    before_o, before_a = set(bpy.data.objects), set(bpy.data.actions)
    bpy.ops.import_scene.gltf(filepath=path)
    new_o = [o for o in bpy.data.objects if o not in before_o]
    new_a = [a for a in bpy.data.actions if a not in before_a]
    rig = next(o for o in new_o if o.type == "ARMATURE")
    stray = [o for o in new_o if o.type == "MESH" and o.parent is not rig]   # an icosphere ships in every file
    new_o = [o for o in new_o if o not in stray]
    for o in stray:
        bpy.data.objects.remove(o, do_unlink=True)
    col = bpy.data.collections.new(f"Q_{key}")
    bpy.context.scene.collection.children.link(col)
    for o in new_o:
        for c in list(o.users_collection):
            c.objects.unlink(o)
        col.objects.link(o)
    rig.name = f"{key}_rig"
    rig["bb_family"] = family
    if rig.animation_data:
        rig.animation_data.action = None
    for a in new_a:
        clip = a.name.replace("_CharacterArmature", "").split("|")[-1]
        if take_clips and clip in CLIPS:
            a.name = f"{family}|{clip}"
            a.use_fake_user = True
            keep_actions.add(a.name)
        else:
            bpy.data.actions.remove(a)
    for o in new_o:
        if o.type == "MESH":
            o.name = f"{key}_{o.name.split('_')[-1]}"
    return rig


for i, n in enumerate(MEN_CHARS):
    import_gltf(os.path.join(MEN, n + ".gltf"), "M", "M_" + n, i == 0)
for i, n in enumerate(WOMEN_CHARS):
    import_gltf(os.path.join(WOMEN, n + ".gltf"), "W", "W_" + n, i == 0)

# robot: append from its .blend (actions are named Robot_<Clip>)
with bpy.data.libraries.load(ROBOT, link=False) as (src, dst):
    dst.objects = list(src.objects)
    dst.actions = [a for a in src.actions if a.replace("Robot_", "") in ROBOT_CLIPS]
col = bpy.data.collections.new("Q_R_Robot")
bpy.context.scene.collection.children.link(col)
rig = None
for o in dst.objects:
    if o is None:
        continue
    if o.type not in ("ARMATURE", "MESH"):
        bpy.data.objects.remove(o, do_unlink=True); continue
    col.objects.link(o)
    if o.type == "ARMATURE":
        rig = o
rig.name = "R_Robot_rig"; rig["bb_family"] = "R"
if rig.animation_data:
    rig.animation_data.action = None
for a in dst.actions:
    a.name = "R|" + a.name.replace("Robot_", "")
    a.use_fake_user = True
    keep_actions.add(a.name)

for a in list(bpy.data.actions):
    if a.name not in keep_actions:
        bpy.data.actions.remove(a)
for block in (bpy.data.meshes, bpy.data.materials, bpy.data.armatures):
    for d in list(block):
        if d.users == 0:
            block.remove(d)
print("characters:", sorted(c.name for c in bpy.data.collections))
print("clips:", sorted(keep_actions))
bpy.ops.wm.save_as_mainfile(filepath=OUT, compress=True)
print("saved", OUT, os.path.getsize(OUT) // 1024, "KB")
