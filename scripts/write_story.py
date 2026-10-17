#!/usr/bin/env python3
"""Generate a Bounce Bhai story using Crystal API.
Usage: python scripts/write_story.py out/story.json

Environment:
  CRYSTAL_API_URL  Optional; defaults to the Crystal Worker URL
  CRYSTAL_API_KEY  Required; your Crystal API key
  CRYSTAL_MODEL    Optional; defaults to the configured Llama model
"""
import json
import os
import random
import re
import sys
import time
import urllib.request
import urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "engine"))
import scene_spec as SP

HIST = os.path.join(ROOT, "data", "history.json")

API_URL = os.environ.get(
    "CRYSTAL_API_URL",
    "https://crystal-api.baddampujithareddy19.workers.dev/"
)
MODEL = os.environ.get(
    "CRYSTAL_MODEL",
    "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
)

GENRES = getattr(
    SP, "GENRES",
    ["facts", "mystery", "history", "motivation", "funny"]
)

PROMPT = """You write viral YouTube Shorts stories for the Hindi/Hinglish
channel "Bounce Bhai".

Write ONE original micro-story. Genre: {genre}.

Rules:
- 7 to 9 short sentences, 70-100 words total.
- Strong hook first sentence, twist/payoff in the LAST sentence.
- If TRUE, use only widely documented facts you are confident are correct.
- Never reuse these past stories: {past}
- Never write about scams, politics, religion, violence, or real private
  people. Never use the story "Ismaeel's Silent Journey".
- payoff_word: one single word appearing in the LAST sentence's "hi" text.
- The video is a 3D cartoon. Give a cast of 1-3 characters.
- Character type must be one of: {types}.
- Character clothing color must be one of: {colors}.
- Every sentence needs an animatable scene:
  setting: one of {settings};
  characters: 1-3 cast names on screen;
  action: one of {actions};
  prop: one of {props}.

Return ONLY valid JSON with this structure:
{{
  "title": "short English title",
  "cast": [{{"name":"Ravi","type":"man","color":"blue"}}],
  "hook": "Hinglish hook, max 34 characters, ends with ...",
  "payoff_word": "word",
  "sentences": [
    {{
      "hi": "Hinglish in Roman script",
      "hd": "Same sentence in Devanagari Hindi; numbers written as Hindi words",
      "en": "Natural English",
      "te": "Natural Telugu",
      "scene": {{
        "setting": "allowed setting",
        "characters": ["Ravi"],
        "action": "allowed action",
        "prop": "allowed prop"
      }}
    }}
  ],
  "yt_title": {{
    "hi_roman": "Hinglish title + emoji + #shorts",
    "hi": "Devanagari title + emoji + #shorts",
    "en": "English title + emoji + #shorts",
    "te": "Telugu title + emoji + #shorts"
  }},
  "question": {{
    "hi_roman": "Hinglish question",
    "hi": "Devanagari question",
    "en": "English question",
    "te": "Telugu question"
  }},
  "tags": ["8 to 12 tags"],
  "genre_tag": "#facts or #mystery or #history or #motivation or #funny"
}}

Make every sentence's scene valid for the supplied animation options.
Keep all required fields. Return only the JSON object.
"""


def post_story(prompt):
    key = os.environ.get("CRYSTAL_API_KEY")
    if not key:
        raise SystemExit(
            "Missing CRYSTAL_API_KEY environment variable. "
            "Set your Crystal API key before running."
        )

    payload = {
        "model": MODEL,
        "prompt": prompt
    }

    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "X-Crystal-Key": key,
            "Content-Type": "application/json",
            "User-Agent": "bouncebhai/1.0"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Crystal API HTTP {exc.code}: {details[:1000]}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Crystal API connection failed: {exc}") from exc

    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Crystal API returned invalid JSON: {body[:1000]}"
        ) from exc

    # Support the response shape in your example: data.result.
    # Also accept common alternative response shapes.
    result = data.get("result") if isinstance(data, dict) else None

    if isinstance(result, dict):
        return result

    if isinstance(result, str):
        text = result.strip()
    elif isinstance(data, dict):
        text = data.get("response") or data.get("text") or ""
    else:
        text = ""

    if isinstance(text, dict):
        return text

    if not isinstance(text, str) or not text.strip():
        raise RuntimeError(
            "Crystal API response contains no usable result. "
            f"Response: {body[:1000]}"
        )

    # Handle JSON wrapped in Markdown fences.
    text = re.sub(r"^\s*```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```\s*$", "", text)

    # Parse the returned story JSON.
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(text[start:end + 1])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    raise RuntimeError(
        "Crystal API result was not a valid story JSON object: "
        + text[:1000]
    )


def validate_with_reason(story):
    """Return (True, None) if story is valid, otherwise (False, reason string)."""
    if not isinstance(story, dict):
        return False, "Story is not a JSON object"

    sentences = story.get("sentences") or []
    if not (7 <= len(sentences) <= 9):
        return False, f"Wrong sentence count: {len(sentences)} (expected 7-9)"

    for i, sentence in enumerate(sentences, start=1):
        if not isinstance(sentence, dict):
            return False, f"Sentence {i} is not an object"
        for k in ("hi", "hd", "en", "te"):
            if not sentence.get(k):
                return False, f"Sentence {i} missing field '{k}'"

    payoff = str(story.get("payoff_word", "")).strip("!.,? ").lower()
    if not payoff:
        return False, "Missing payoff_word"

    last_sentence = sentences[-1].get("hi", "")
    words = re.findall(r"\w+", last_sentence.lower())
    if payoff not in words:
        return False, f"payoff_word '{payoff}' not found in last sentence"

    return True, None


def main(out):
    hist = []
    if os.path.exists(HIST):
        with open(HIST, encoding="utf-8") as file:
            hist = json.load(file)

    past = "; ".join(
        h["title"] for h in hist[-200:] if h.get("title")
    ) or "none"

    old_titles = {
        h["title"].lower()
        for h in hist
        if h.get("title")
    }

    last_error = None
    story = None

    for attempt in range(4):
        prompt = PROMPT.format(
            genre=random.choice(GENRES),
            past=past,
            types=", ".join(SP.CHAR_TYPES),
            colors=", ".join(SP.COLORS),
            settings=", ".join(SP.SETTINGS),
            actions=", ".join(SP.ACTIONS),
            props=", ".join(SP.PROPS)
        )

        try:
            candidate = post_story(prompt)
            title = (candidate.get("title") or "<no title>").strip()
            ok, reason = validate_with_reason(candidate)

            if ok and title.lower() not in old_titles:
                story = candidate
                break

            if not ok:
                last_error = reason
                print(
                    f"Story attempt {attempt + 1}/4 failed validation: {reason}; title: {title}",
                    flush=True
                )
            else:
                last_error = "Reused previous title"
                print(
                    f"Story attempt {attempt + 1}/4 failed: reused previous title: {title}",
                    flush=True
                )

        except Exception as exc:
            last_error = str(exc)
            print(
                f"Crystal API attempt {attempt + 1}/4 failed: {exc}",
                flush=True
            )

        if attempt < 3:
            time.sleep(3)

    if story is None:
        raise SystemExit(
            f"Story generation failed after 4 attempts: {last_error}"
        )

    SP.normalize(story)

    rng = random.Random()
    story.update({
        "out": out.replace(".json", ".mp4"),
        "seed": rng.randint(1, 99999),
        "gap_deg": rng.randint(24, 40),
        "spin": rng.randint(40, 110),
        "grow": round(rng.uniform(0.8, 2.0), 2),
        "target": [25, 40],
        "hue": round(rng.random(), 2),
        "ball_hue": round(rng.random(), 2),
    })

    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as file:
        json.dump(story, file, ensure_ascii=False, indent=1)

    print("story:", story["title"])


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(
            "Usage: python scripts/write_story.py out/story.json"
        )
    main(sys.argv[1])
