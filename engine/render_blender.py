@@
     def build_char(c, ci):
-        t = c["type"]; shirt = SP.COLORS[c["color"]]
+        t = c["type"]; shirt = SP.COLORS[c["color"]]
         skin = SKINS[(ci + story.get("seed", 0)) % len(SKINS)]
         robot = t == "robot"
         if robot: skin = (0.55, 0.58, 0.62)
-        S = {"type": t}
+        S = {"type": t}
+        # If an external high-quality model is provided, import it and use it as the character root.
+        # The fetch_models.py helper writes a cast[i]["model_path"] entry into the story JSON.
+        if c.get("model_path") and os.path.exists(c["model_path"]):
+            try:
+                # record objects before import
+                before = set(bpy.data.objects)
+                bpy.ops.import_scene.gltf(filepath=os.path.abspath(c["model_path"]))
+                after = [o for o in bpy.data.objects if o not in before]
+                # create a root empty and parent the imported objects to it
+                root = empty(f"c{ci}_root")
+                root.scale = (0.8,) * 3 if t in ("boy", "girl") else (1, 1, 1)
+                for o in after:
+                    o.parent = root
+                pel = empty(f"c{ci}_pelvis", (0, 0, 0.55), root)
+                S.update(root=root, pelvis=pel)
+                S["props"] = {}
+                S["stool"] = empty(f"c{ci}_stool", (0, 0.05, 0), root)
+                S["eyes"] = []
+                S["brows"] = empty(f"c{ci}_brows", (0, 0, 0), root)
+                S["mouth"] = empty(f"c{ci}_mouth", (0, -0.31, 0.15), root)
+                print(f"Imported external model for cast[{ci}]:", c.get("model_path"), flush=True)
+                return S
+            except Exception as e:
+                print("Model import failed, falling back to procedural build:", e, flush=True)
         kid = t in ("boy", "girl")
         root = empty(f"c{ci}_root"); root.scale = (0.8,) * 3 if kid else (1, 1, 1)
         pel = empty(f"c{ci}_pelvis", (0, 0, 0.55), root)
         S.update(root=root, pelvis=pel)
*** End Patch
