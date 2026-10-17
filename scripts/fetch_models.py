#!/usr/bin/env python3
"""Fetch downloadable Sketchfab models for a story's cast and attach local paths to the story JSON.

Usage: python scripts/fetch_models.py out/story.json

Environment:
- SKETCHFAB_TOKEB (preferred) or SKETCHFAB_TOKEN may contain the Sketchfab API token.

Behavior:
- For each cast entry in story["cast"] that does not already have a "model_path", the script
  searches Sketchfab for a downloadable model matching "<type> cartoon" (best-effort),
  downloads the model archive or glb, extracts a .glb/.gltf/.fbx if needed and writes the local
  path into cast[i]["model_path"].
- Downloaded files are saved under models/ (cached across runs if CI cache is used).

This script is defensive: it uses retries for network calls, temporary directories that are
always cleaned up, filename sanitization, and skips entries it cannot fetch instead of
modifying the story in-place incorrectly.
"""
import json
import os
import re
import shutil
import sys
import tempfile
import time
import zipfile
import tarfile
from pathlib import Path

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except Exception:
    print("The requests package is required. Install via: pip install requests", file=sys.stderr)
    raise

API_SEARCH = "https://api.sketchfab.com/v3/search"
API_MODEL_DOWNLOAD = "https://api.sketchfab.com/v3/models/{uid}/download"

ALLOWED_EXTS = (".glb", ".gltf", ".fbx")


def make_session(retries=3, backoff=1.0, status_forcelist=(429, 500, 502, 503, 504)):
    s = requests.Session()
    r = Retry(total=retries, backoff_factor=backoff, status_forcelist=list(status_forcelist), allowed_methods=None)
    a = HTTPAdapter(max_retries=r)
    s.mount("https://", a)
    s.mount("http://", a)
    return s


def sanitize_filename(name: str, maxlen: int = 160) -> str:
    # keep alnum, dot, dash, underscore
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", name)
    name = name.strip("-_.")
    if len(name) > maxlen:
        name = name[:maxlen]
    return name or "model"


def find_model_file(base_dir: Path):
    for ext in ALLOWED_EXTS:
        files = list(base_dir.rglob(f"*{ext}"))
        if files:
            files.sort(key=lambda p: (len(p.parts), str(p)))
            return files[0]
    return None


def extract_model_from_archive(path: Path, dest_dir: Path):
    path = Path(path)
    # direct model file
    if path.suffix.lower() in ALLOWED_EXTS:
        return path

    # try zip
    try:
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path, "r") as z:
                for name in z.namelist():
                    if name.lower().endswith(ALLOWED_EXTS):
                        z.extract(name, dest_dir)
                        return dest_dir / name
    except zipfile.BadZipFile:
        pass

    # try tar
    try:
        if tarfile.is_tarfile(path):
            with tarfile.open(path) as tf:
                for m in tf.getmembers():
                    if m.name.lower().endswith(ALLOWED_EXTS):
                        tf.extract(m, dest_dir)
                        return dest_dir / m.name
    except Exception:
        pass

    return None


def download_to_file(session: requests.Session, url: str, dest: Path, timeout: int = 120):
    dest.parent.mkdir(parents=True, exist_ok=True)
    with session.get(url, stream=True, timeout=timeout, allow_redirects=True) as r:
        r.raise_for_status()
        # attempt to get filename from headers
        cd = r.headers.get("content-disposition", "")
        fname = None
        if "filename=" in cd:
            fname = cd.split("filename=")[-1].strip('"')
        if not fname:
            last = r.url.split("/")[-1]
            fname = last or "model.bin"
        fname = sanitize_filename(fname)
        target = dest / fname
        with open(target, "wb") as fh:
            written = 0
            for chunk in r.iter_content(32 * 1024):
                if chunk:
                    fh.write(chunk)
                    written += len(chunk)
        if target.exists() and target.stat().st_size > 0:
            return target
        raise RuntimeError("Downloaded file appears empty")


def search_model(session: requests.Session, query: str):
    params = {"type": "models", "downloadable": "true", "q": query, "page": 1}
    r = session.get(API_SEARCH, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    return data.get("results", [])


def download_model_by_uid(session: requests.Session, uid: str, dest_dir: Path):
    url = API_MODEL_DOWNLOAD.format(uid=uid)
    return download_to_file(session, url, dest_dir)


def main(story_path: str):
    story_path = os.path.abspath(story_path)
    with open(story_path, "r", encoding="utf-8") as fh:
        story = json.load(fh)

    # support both environment variable spellings
    token = os.environ.get("SKETCHFAB_TOKEB") or os.environ.get("SKETCHFAB_TOKEN")
    if not token:
        print("SKETCHFAB_TOKEB / SKETCHFAB_TOKEN not set: skipping model fetch (set it as a secret).")
        return 0

    session = make_session(retries=3, backoff=1.0)
    session.headers.update({"Authorization": f"Token {token}", "User-Agent": "bouncebhai/1.0"})

    models_dir = Path("models")
    models_dir.mkdir(parents=True, exist_ok=True)

    cast = story.get("cast") or []
    if not isinstance(cast, list):
        raise SystemExit("Story JSON cast field must be a list")

    changed = False
    for i, member in enumerate(cast):
        if not isinstance(member, dict):
            continue
        if member.get("model_path"):
            print(f"cast[{i}] already has model_path; skipping: {member.get('model_path')}")
            continue

        # prefer explicit sketchfab_id or model_url if provided by Gemini
        sketchfab_id = member.get("sketchfab_id")
        model_url = member.get("model_url")

        typ = member.get("type") or member.get("name") or "character"
        query = f"{typ} cartoon"
        if sketchfab_id:
            query = f"id:{sketchfab_id}"
        elif member.get("genre_tag"):
            query = f"{typ} {member.get('genre_tag').replace('#','')} cartoon"

        print(f"[fetch_models] cast[{i}] query: {query}")

        try:
            # if explicit model_url given, use it directly
            download_url = None
            if model_url:
                download_url = model_url
            elif sketchfab_id:
                # try to use direct download endpoint via UID
                # the download endpoint will typically redirect to the actual asset
                download_url = API_MODEL_DOWNLOAD.format(uid=sketchfab_id)
            else:
                results = search_model(session, query)
                if not results:
                    print(f"[fetch_models] No downloadable models found for: {query}")
                    continue
                best = results[0]
                sketchfab_id = best.get("uid")
                download_url = API_MODEL_DOWNLOAD.format(uid=sketchfab_id)

            # download + extract inside a tempdir to ensure cleanup
            with tempfile.TemporaryDirectory() as td:
                tmpdir = Path(td)
                # download to tmpdir (session will follow redirects)
                try:
                    downloaded = download_to_file(session, download_url, tmpdir)
                except Exception as exc:
                    # if downloading the /download endpoint failed for a UID, try resolving via search result's url
                    if not model_url and 'sketchfab_id' in locals() and sketchfab_id and not downloaded:
                        # attempt to download the API_MODEL_DOWNLOAD directly (already tried) -> fail gracefully
                        print(f"[fetch_models] download failed for uid {sketchfab_id}: {exc}")
                        continue
                    print(f"[fetch_models] download failed: {exc}")
                    continue

                # try to extract a model asset
                model_file = extract_model_from_archive(downloaded, tmpdir)
                if not model_file:
                    # maybe the download URL was itself a direct model file but with different name
                    # check tmpdir for any allowed extensions
                    model_file = find_model_file(tmpdir)

                if not model_file:
                    print("[fetch_models] Could not find a .glb/.gltf/.fbx inside the downloaded archive; skipping.")
                    continue

                # move to cache with sanitized name
                dest_name = sanitize_filename(f"{i}_{sketchfab_id or typ}{model_file.suffix}")
                dest = models_dir / dest_name
                shutil.move(str(model_file), dest)
                member["model_path"] = str(dest)
                changed = True
                print(f"[fetch_models] Resolved cast[{i}] -> {member['model_path']}")

        except Exception as exc:
            print(f"[fetch_models] Warning: failed to fetch model for cast[{i}]: {exc}")
            continue

    if changed:
        with open(story_path, "w", encoding="utf-8") as fh:
            json.dump(story, fh, ensure_ascii=False, indent=1)
        print(f"[fetch_models] Updated story with model_path entries; saved to {story_path}")
    else:
        print("[fetch_models] No changes made to story.json")

    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python scripts/fetch_models.py out/story.json")
    raise SystemExit(main(sys.argv[1]))
