
#!/usr/bin/env python3
"""Fetch downloadable Sketchfab models and attach local paths to story JSON."""
import json
import os
import re
import shutil
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

API_SEARCH = "https://api.sketchfab.com/v3/search"
API_DOWNLOAD = "https://api.sketchfab.com/v3/models/{}/download"
EXTENSIONS = (".glb", ".gltf", ".fbx")
MAX_BYTES = 500 * 1024 * 1024


def make_session(token=None):
    session = requests.Session()
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=1,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers["User-Agent"] = "BounceBhaiShorts/1.1"
    if token:
        session.headers["Authorization"] = f"Token {token}"
    return session


def safe_name(value):
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value))
    return value.strip("-_.")[:140] or "model"


def find_model(folder):
    files = [
        p for p in Path(folder).rglob("*")
        if p.is_file() and p.suffix.lower() in EXTENSIONS
    ]
    files.sort(key=lambda p: (
        EXTENSIONS.index(p.suffix.lower()), len(p.parts), str(p)
    ))
    return files[0] if files else None


def safe_target(root, name):
    root = Path(root).resolve()
    target = (root / name).resolve()
    if target != root and root not in target.parents:
        raise ValueError("Unsafe path in model archive")
    return target


def extract_model(archive_path, folder):
    archive_path = Path(archive_path)
    folder = Path(folder)

    if archive_path.suffix.lower() in EXTENSIONS:
        return archive_path

    if zipfile.is_zipfile(archive_path):
        with zipfile.ZipFile(archive_path) as archive:
            names = [
                n for n in archive.namelist()
                if not n.endswith("/")
                and Path(n).suffix.lower() in EXTENSIONS
            ]
            names.sort(key=lambda n: (
                EXTENSIONS.index(Path(n).suffix.lower()), len(Path(n).parts)
            ))
            for name in names:
                target = safe_target(folder, name)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(name) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                return target

    if tarfile.is_tarfile(archive_path):
        with tarfile.open(archive_path, "r:*") as archive:
            members = [
                m for m in archive.getmembers()
                if m.isfile() and Path(m.name).suffix.lower() in EXTENSIONS
            ]
            members.sort(key=lambda m: (
                EXTENSIONS.index(Path(m.name).suffix.lower()),
                len(Path(m.name).parts),
            ))
            for member in members:
                target = safe_target(folder, member.name)
                source = archive.extractfile(member)
                if source is None:
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with source, open(target, "wb") as dst:
                    shutil.copyfileobj(source, dst)
                return target

    return None


def search_model(session, query):
    response = session.get(
        API_SEARCH,
        params={
            "type": "models",
            "downloadable": "true",
            "q": query,
            "page": 1,
        },
        timeout=30,
    )
    response.raise_for_status()
    result = response.json()
    return result.get("results", []) if isinstance(result, dict) else []


def resolve_download_url(session, uid):
    """Resolve Sketchfab's API response into a signed asset URL."""
    response = session.get(API_DOWNLOAD.format(uid), timeout=30)
    response.raise_for_status()

    if "json" not in response.headers.get("content-type", "").lower():
        return response.url

    data = response.json()

    # Sketchfab commonly returns {"glb": {"url": "..."}}, etc.
    for fmt in ("glb", "gltf", "fbx"):
        item = data.get(fmt)
        if isinstance(item, dict) and item.get("url"):
            return item["url"]

    # Tolerate alternate response structures.
    for value in data.values():
        if isinstance(value, dict):
            for fmt in ("glb", "gltf", "fbx"):
                item = value.get(fmt)
                if isinstance(item, dict) and item.get("url"):
                    return item["url"]

    raise RuntimeError(
        "Sketchfab returned no GLB/GLTF/FBX download URL. "
        "The model may not be downloadable with this account."
    )


def download_asset(session, url, folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)

    # Do not put the Sketchfab API token on signed asset/CDN requests.
    with session.get(url, stream=True, timeout=120) as response:
        response.raise_for_status()
        disposition = response.headers.get("content-disposition", "")
        match = re.search(
            r"""filename\*?=(?:UTF-8''|")?([^";]+)""",
            disposition,
            re.I,
        )
        if match:
            filename = unquote(match.group(1).strip('"'))
        else:
            filename = unquote(urlparse(response.url).path.rsplit("/", 1)[-1])

        target = folder / safe_name(filename or "model.download")
        total = 0

        with open(target, "wb") as output:
            for chunk in response.iter_content(64 * 1024):
                if not chunk:
                    continue
                total += len(chunk)
                if total > MAX_BYTES:
                    raise RuntimeError("Download exceeded the 500 MB limit")
                output.write(chunk)

    if target.stat().st_size == 0:
        raise RuntimeError("Downloaded file is empty")

    return target


def main(story_path):
    story_path = Path(story_path).resolve()
    with open(story_path, encoding="utf-8") as file:
        story = json.load(file)

    token = os.environ.get("SKETCHFAB_TOKEB") or os.environ.get("SKETCHFAB_TOKEN")
    if not token:
        print("[fetch_models] Sketchfab token missing; skipping models.")
        return 0

    api = make_session(token)
    assets = make_session()  # No API token sent to asset hosts.

    models_dir = Path("models")
    models_dir.mkdir(parents=True, exist_ok=True)

    cast = story.get("cast") or []
    if not isinstance(cast, list):
        raise SystemExit("Story JSON cast field must be a list")

    changed = False

    for index, member in enumerate(cast):
        if not isinstance(member, dict) or member.get("model_path"):
            continue

        uid = member.get("sketchfab_id")
        direct_url = member.get("model_url")
        kind = member.get("type") or member.get("name") or "character"
        query = f"{kind} cartoon"

        if member.get("genre_tag"):
            tag = str(member["genre_tag"]).replace("#", "")
            query = f"{kind} {tag} cartoon"

        print(f"[fetch_models] cast[{index}] query: {query}")

        try:
            if direct_url:
                parsed = urlparse(direct_url)
                if parsed.scheme not in ("http", "https"):
                    raise ValueError("model_url must use HTTP or HTTPS")
                if (
                    "sketchfab.com" in (parsed.hostname or "").lower()
                    and "/3d-models/" in parsed.path
                    and not parsed.path.lower().endswith(EXTENSIONS)
                ):
                    raise ValueError(
                        "model_url is a model page, not a direct file URL; "
                        "provide sketchfab_id instead"
                    )
                download_url = direct_url
            else:
                if not uid:
                    results = search_model(api, query)
                    if not results:
                        print("[fetch_models] No downloadable search results.")
                        continue

                    uid = results[0].get("uid")
                    if not uid:
                        print("[fetch_models] Search result has no UID.")
                        continue

                    print(
                        f"[fetch_models] Selected: "
                        f"{results[0].get('name', uid)} ({uid})"
                    )

                download_url = resolve_download_url(api, uid)

            with tempfile.TemporaryDirectory(prefix="bounce-model-") as temp:
                downloaded = download_asset(assets, download_url, temp)
                model = extract_model(downloaded, temp) or find_model(temp)

                if model is None:
                    print(
                        f"[fetch_models] Download wasn't a supported model "
                        f"or archive: {downloaded.name}"
                    )
                    continue

                extension = model.suffix.lower()
                if extension not in EXTENSIONS:
                    print("[fetch_models] Unsupported model extension.")
                    continue

                destination = models_dir / (
                    f"{index}_{safe_name(uid or kind)}{extension}"
                )
                shutil.copy2(model, destination)

                member["model_path"] = destination.as_posix()
                if uid:
                    member["sketchfab_id"] = uid

                changed = True
                print(f"[fetch_models] Saved model: {destination}")

        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            print(f"[fetch_models] HTTP {status} for cast[{index}]: {exc}")
        except Exception as exc:
            print(
                f"[fetch_models] Failed cast[{index}]: "
                f"{type(exc).__name__}: {exc}"
            )

    if changed:
        with open(story_path, "w", encoding="utf-8") as file:
            json.dump(story, file, ensure_ascii=False, indent=2)
            file.write("\n")
        print(f"[fetch_models] Updated story: {story_path}")
    else:
        print("[fetch_models] No changes made to story.json")

    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python scripts/fetch_models.py out/story.json")
    raise SystemExit(main(sys.argv[1]))
