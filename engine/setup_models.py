#!/usr/bin/env python3
"""Import and normalize downloaded Sketchfab actors into reusable Blender .blend caches.
Usage: blender -b --factory-startup --python engine/setup_models.py -- out/story.json
"""
import json
import sys
from pathlib import Path


def main(story_path):
    import bpy
    from mathutils import Vector

    story_file = Path(story_path).resolve()
    repo_root = Path.cwd().resolve()
    with story_file.open(encoding="utf-8") as stream:
        story = json.load(stream)
    cast = story.get("cast") or []
    if not isinstance(cast, list) or not cast:
        raise SystemExit("[setup_models] Story cast must be a non-empty list")

    cache_dir = repo_root / "models" / "blender_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    for index, member in enumerate(cast):
        if not isinstance(member, dict):
            raise SystemExit(f"[setup_models] cast[{index}] is not an object")
        source_value = member.get("source_model_path") or member.get("model_path")
        if not source_value:
            raise SystemExit(f"[setup_models] cast[{index}] has no downloaded model_path")
        source = Path(source_value).expanduser()
        if not source.is_absolute():
            source = (repo_root / source).resolve()
        if not source.is_file():
            raise SystemExit(f"[setup_models] Downloaded model is missing: {source}")

        print(f"[setup_models] Importing cast[{index}]: {source}", flush=True)
        bpy.ops.wm.read_factory_settings(use_empty=True)
        before = set(bpy.data.objects)
        extension = source.suffix.lower()
        if extension in (".glb", ".gltf"):
            bpy.ops.import_scene.gltf(filepath=str(source))
        elif extension == ".fbx":
            bpy.ops.import_scene.fbx(filepath=str(source))
        else:
            raise SystemExit(f"[setup_models] Unsupported model format: {extension}")

        imported = list(set(bpy.data.objects) - before)
        meshes = [obj for obj in imported if obj.type == "MESH"]
        if not imported or not meshes:
            raise SystemExit(f"[setup_models] No mesh objects imported from {source}")
        points = [obj.matrix_world @ Vector(corner) for obj in meshes for corner in obj.bound_box]
        min_x, max_x = min(p.x for p in points), max(p.x for p in points)
        min_y, max_y = min(p.y for p in points), max(p.y for p in points)
        min_z, max_z = min(p.z for p in points), max(p.z for p in points)
        height = max_z - min_z
        if height < 0.05:
            raise SystemExit(f"[setup_models] Model has no usable vertical height ({height:.3f}): {source}")

        actor_root = bpy.data.objects.new("BB_ACTOR_ROOT", None)
        bpy.context.scene.collection.objects.link(actor_root)
        actor_root["bb_actor_root"] = True
        imported_set = set(imported)
        top_level = [obj for obj in imported if obj.parent not in imported_set]
        for obj in top_level:
            world_matrix = obj.matrix_world.copy()
            obj.parent = actor_root
            obj.matrix_world = world_matrix
        center_x, center_y = (min_x + max_x) / 2.0, (min_y + max_y) / 2.0
        for obj in top_level:
            obj.location.x -= center_x
            obj.location.y -= center_y
            obj.location.z -= min_z
        factor = 1.70 / height
        actor_root.scale = (factor, factor, factor)
        actor_root.location = (0.0, 0.0, 0.0)
        try:
            bpy.ops.file.pack_all()
        except Exception as exc:
            print(f"[setup_models] Resource packing warning: {exc}", flush=True)

        cache_path = cache_dir / f"actor_{index}.blend"
        bpy.ops.wm.save_as_mainfile(filepath=str(cache_path))
        try:
            source_record = source.relative_to(repo_root).as_posix()
        except ValueError:
            source_record = str(source)
        member["source_model_path"] = source_record
        member["model_path"] = cache_path.relative_to(repo_root).as_posix()
        member["model_cache_format"] = "blender"
        print(f"[setup_models] Saved actor_{index}.blend (normalized height 1.70 units)", flush=True)

    with story_file.open("w", encoding="utf-8") as stream:
        json.dump(story, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(f"[setup_models] All {len(cast)} actors prepared: {story_file}", flush=True)


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    if len(argv) != 1:
        raise SystemExit("Usage: blender -b --python engine/setup_models.py -- out/story.json")
    main(argv[0])
