#!/usr/bin/env python3
"""Fetch downloadable Sketchfab models for a story's cast and attach local paths to the story JSON.

Usage: python scripts/fetch_models.py out/story.json

Requires environment variable SKETCHFAB_TOKEB (or SKETCHFAB_TOKEN for backwards compatibility)
to be set. If missing, the script prints a message and exits without modifying the story.

Behavior:
- For each cast entry in story["cast"] that does not already have a "model_path", the script
  searches Sketchfab for a downloadable model matching "<type> cartoon" (best-effort),
  downloads the model archive or glb, extracts a .glb/.gltf if needed and writes the local
  path into cast[i]["model_path"].
- Downloaded files are saved under models/ and can be cached in CI.
"""
import json, os, sys, shutil, zipfile, tempfile
from pathlib import Path

try:
    import requests
except Exception:
    print("The requests package is required. Install via pip install requests", file=sys.stderr)
    raise

API_SEARCH = "https://api.sketchfab.com/v3/search"
API_MODEL_DOWNLOAD = "https://api.sketchfab.com/v3/models/{uid}/download"

if len(sys.argv) < 2:
    print("usage: python scripts/fetch_models.py out/story.json")
    sys.exit(2)

story_path = sys.argv[1]
if not os.path.exists(story_path):
    print("story json not found:", story_path)
    sys.exit(2)

with open(story_path, encoding="utf-8") as f:
    story = json.load(f)

token = os.environ.get("SKETCHFAB_TOKEB") or os.environ.get("SKETCHFAB_TOKEN")
if not token:
    print("SKETCHFAB_TOKEB not set: skipping model fetch (set it as a secret).")
    sys.exit(0)

headers = {"Authorization": f"Token {token}"}
models_dir = Path("models")
models_dir.mkdir(exist_ok=True)


def search_model(query):
    params = {"type": "models", "downloadable": "true", "q": query, "page": 1}
    r = requests.get(API_SEARCH, params=params, headers=headers, timeout=30)
    r.raise_for_status()
    data = r.json()
    return data.get("results", [])


def download_model(uid, dest_dir):
    url = API_MODEL_DOWNLOAD.format(uid=uid)
    r = requests.get(url, headers=headers, stream=True, timeout=60, allow_redirects=True)
    r.raise_for_status()
    cd = r.headers.get("content-disposition", "")
    fname = None
    if "filename=" in cd:
        fname = cd.split("filename=")[-1].strip('"')
    if not fname:
        last = r.url.split("/")[-1]
        fname = last or f"{uid}.model"
    target = dest_dir / fname
    with open(target, "wb") as fh:
        for chunk in r.iter_content(32768):
            if chunk:
                fh.write(chunk)
    return target


def extract_glb_from_archive(path, dest_dir):
    path = Path(path)
    if path.suffix.lower() in (".glb", ".gltf", ".fbx"):
        return path
    try:
        with zipfile.ZipFile(path, "r") as z:
            for name in z.namelist():
                lname = name.lower()
                if lname.endswith(".glb") or lname.endswith(".gltf") or lname.endswith(".fbx"):
                    z.extract(name, dest_dir)
                    return dest_dir / name
    except zipfile.BadZipFile:
        pass
    return None


changed = False
for i, c in enumerate(story.get("cast", [])):
    if c.get("model_path"):
        print(f"cast[{i}] already has model_path; skipping: {c.get('model_path')}")
        continue
    typ = c.get("type") or c.get("name") or "character"
    query = f"{typ} cartoon"
    print("Searching Sketchfab for:", query)
    try:
        results = search_model(query)
    except Exception as e:
        print("Sketchfab search failed:", e)
        continue
    if not results:
        print("No downloadable models found for", query)
        continue
    best = results[0]
    uid = best.get("uid")
    title = best.get("name") or uid
    print(f"Selected model: {title} ({uid})")
    try:
        tmpdir = Path(tempfile.mkdtemp())
        dl = download_model(uid, tmpdir)
        model_file = extract_glb_from_archive(dl, tmpdir)
        if not model_file:
            print("Could not find a .glb/.gltf/.fbx inside the downloaded archive; skipping.")
            shutil.rmtree(tmpdir, ignore_errors=True)
            continue
        dest = models_dir / f"{i}_{uid}{model_file.suffix}"
        shutil.move(str(model_file), dest)
        print("Saved model to", dest)
        c["model_path"] = str(dest)
        changed = True
        shutil.rmtree(tmpdir, ignore_errors=True)
    except Exception as e:
        print("Failed to download/extract model:", e)
        continue

if changed:
    with open(story_path, "w", encoding="utf-8") as f:
        json.dump(story, f, ensure_ascii=False, indent=1)
    print("Updated story with model_path entries; saved to", story_path)
else:
    print("No changes made to story.json")
