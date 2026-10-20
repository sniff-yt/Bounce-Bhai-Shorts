#!/usr/bin/env python3
"""Generate a Bounce Bhai story using NaraRouter, NVIDIA NIM, Groq, GitHub Models, or Gemini fallback."""

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
import insights as INS

HIST = os.path.join(ROOT, "data", "history.json")

# NaraRouter (OpenAI-compatible). Free tier: 15 req/min, 7M tokens/day.
NARA_API_URL = os.environ.get("NARA_API_URL", "https://router.bynara.id/v1/chat/completions")
# Comma-separated, tried in order. Override with NARA_MODELS if the aliases differ
# (check GET https://router.bynara.id/v1/models with your key).
NARA_MODELS = [
    m.strip()
    for m in os.environ.get("NARA_MODELS", "laguna-s-2.1,nemotron-3.5-lightning-free").split(",")
    if m.strip()
]
# none/minimal/low/medium/high/xhigh/max. Ignored by non-reasoning models.
NARA_REASONING = os.environ.get("NARA_REASONING", "none")

# NVIDIA NIM (build.nvidia.com, OpenAI-compatible). Key looks like nvapi-...
NVIDIA_API_URL = os.environ.get("NVIDIA_API_URL", "https://integrate.api.nvidia.com/v1/chat/completions")
# Comma-separated, tried in order. Pick any chat model from build.nvidia.com.
NVIDIA_MODELS = [
    m.strip()
    for m in os.environ.get(
        "NVIDIA_MODELS",
        "meta/llama-3.3-70b-instruct,nvidia/llama-3.3-nemotron-super-49b-v1.5"
    ).split(",")
    if m.strip()
]

GROQ_API_URL = os.environ.get("GROQ_API_URL", "https://api.groq.com/openai/v1/chat/completions")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")

GITHUB_MODELS_URL = "https://models.inference.ai.azure.com/chat/completions"
GITHUB_MODEL = "gpt-4o-mini"

GEMINI_API_URL = os.environ.get(
    "GEMINI_API_URL",
    "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
)

GENRES = getattr(
    SP, "GENRES",
    ["facts", "mystery", "history", "motivation", "funny"]
)

PROMPT = """You write viral YouTube Shorts stories for the Hindi/Hinglish channel "Bounce Bhai".

Write ONE original micro-story. Genre: {genre}.

Rules:
- 7 to 9 short sentences, 70-100 words total.
- Strong hook first sentence, twist/payoff in the LAST sentence.
- If TRUE, use only widely documented facts you are confident are correct.
- Never reuse these past stories: {past}
- FRESH SUBJECT ONLY. These subjects are already used, do not write about any of them: {used}
{insights}
- Never write about scams, politics, religion, violence, or real private people. Never use the story "Ismaeel's Silent Journey".
- payoff_word: one single word appearing in the LAST sentence's "hi" text.
- The video is a 2D cartoon. Give a cast of 1-3 characters.
- Character type must be one of: {types}.
- Character clothing color must be one of: {colors}.
- Every sentence needs an animatable scene:
  setting: one of {settings};
  characters: 1-3 cast names on screen;
  action: one of {actions};
  prop: one of {props}.

Return ONLY valid JSON matching this schema:
{{
  "title": "short English title",
  "topic": "the real-world subject in 1-3 English words (e.g. 'bubble wrap')",
  "cast": [
    {{"name": "Ravi", "type": "man", "color": "blue"}}
  ],
  "hook": "Hinglish hook spoken TO the viewer: a challenge or question, max 34 characters (e.g. 'Tum guess kar paoge?')",
  "payoff_word": "word",
  "sentences": [
    {{
      "hi": "Hinglish in Roman script",
      "hd": "Same sentence in Hindi written in DEVANAGARI script (like: एक चिड़िया का दिल), never Telugu script; numbers as Hindi words",
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
  "tags": ["shorts", "facts", "viral", "animation"],
  "genre_tag": "#{genre}"
}}
"""


def title_key(value):
    text = (value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def make_unique_title(title, used_titles):
    base = (title or "").strip()
    if not base:
        base = "Bounce Bhai Story"

    if title_key(base) not in used_titles:
        return base

    suffix = random.randint(100, 999)
    candidate = f"{base.rstrip(' .:-_')} {suffix}"
    if title_key(candidate) not in used_titles:
        return candidate

    for _ in range(50):
        alt = f"{base.rstrip(' .:-_')} {random.randint(100, 9999)}"
        if title_key(alt) not in used_titles:
            return alt

    return f"{base.rstrip(' .:-_')} {time.time_ns()}"


def extract_json(raw_text):
    text = (raw_text or "").strip()
    # Some reasoning models leak <think>...</think> blocks into content.
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    text = re.sub(r"^\s*```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```\s*$", "", text)
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        parsed = json.loads(text[start:end + 1])
        if isinstance(parsed, dict):
            return parsed
    raise RuntimeError("Response was not a valid JSON object")


LLM_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "out", "live", "llm.json")


def llm_log(provider, model, system=None, prompt=None, **kw):
    """Record each AI call (prompt in, answer out) for the studio desktop's AI Chat window."""
    try:
        os.makedirs(os.path.dirname(LLM_LOG), exist_ok=True)
        try:
            calls = json.load(open(LLM_LOG, encoding="utf-8"))
        except Exception:
            calls = []
        if prompt is not None:
            calls.append({"provider": provider, "model": model, "system": system or "", "prompt": prompt,
                          "state": "thinking", "t": time.time()})
        elif calls:
            calls[-1].update(kw)
        json.dump(calls[-8:], open(LLM_LOG + ".tmp", "w", encoding="utf-8"), ensure_ascii=False)
        os.replace(LLM_LOG + ".tmp", LLM_LOG)
    except Exception:
        pass


def _post_json(url, headers, payload, timeout):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def call_openai_compatible(url, api_key, model, prompt, provider_name,
                           max_tokens=2048, timeout=60, extra=None):
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You are a 3D animated shorts writer. Always return strictly valid JSON matching the requested schema."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.7,
        "max_tokens": max_tokens
    }
    if extra:
        payload.update(extra)

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "bouncebhai/2.0"
    }

    llm_log(provider_name, model, payload["messages"][0]["content"], prompt)
    try:
        try:
            body = _post_json(url, headers, payload, timeout)
        except urllib.error.HTTPError as exc:
            # Some gateways/models reject response_format; retry once without it.
            if exc.code == 400 and "response_format" in payload:
                payload.pop("response_format")
                body = _post_json(url, headers, payload, timeout)
            else:
                raise
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        llm_log(None, None, state="failed", error=f"HTTP {exc.code}: {details[:200]}", t2=time.time())
        raise RuntimeError(f"{provider_name} HTTP {exc.code}: {details[:500]}") from exc
    except urllib.error.URLError as exc:
        llm_log(None, None, state="failed", error=f"connection failed: {exc}"[:200], t2=time.time())
        raise RuntimeError(f"{provider_name} connection failed: {exc}") from exc

    data = json.loads(body)
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(f"{provider_name} returned no choices")

    content = choices[0].get("message", {}).get("content", "")
    llm_log(None, None, state="done", response=content or "", t2=time.time(),
            usage=data.get("usage") or {})
    if not (content or "").strip():
        raise RuntimeError(f"{provider_name} returned empty content (reasoning ate the token budget?)")
    return extract_json(content)


def call_gemini(api_key, url, prompt):
    # Ensure deprecated/invalid model URLs are upgraded to gemini-2.5-flash
    if "gemini-3.1-flash-lite:" in url:
        url = url.replace("gemini-3.1-flash-lite:", "gemini-2.5-flash:")

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"}
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "User-Agent": "bouncebhai/2.0",
            "x-goog-api-key": api_key,
        },
        method="POST"
    )

    llm_log("Gemini", url.split("/models/")[-1].split(":")[0], "", prompt)
    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Gemini HTTP {exc.code}: {details[:500]}") from exc

    data = json.loads(body)
    candidates = data.get("candidates") or []
    if not candidates:
        raise RuntimeError("Gemini returned no candidates")
    parts = candidates[0].get("content", {}).get("parts", [])
    text = parts[0].get("text", "") if parts else ""
    llm_log(None, None, state="done", response=text, t2=time.time())
    return extract_json(text)


def post_story(prompt):
    """Try NaraRouter (laguna -> nemotron) -> NVIDIA NIM -> Groq -> GitHub Models -> Gemini."""
    errors = []

    nara_key = (os.environ.get("NARA_API_KEY") or "").strip()
    if nara_key:
        for model in NARA_MODELS:
            try:
                return call_openai_compatible(
                    NARA_API_URL, nara_key, model, prompt, f"NaraRouter({model})",
                    max_tokens=4096, timeout=90,
                    extra={"reasoning_effort": NARA_REASONING},
                )
            except Exception as exc:
                errors.append(str(exc))
                print(f"NaraRouter model {model} failed: {exc}", flush=True)

    nvidia_key = (os.environ.get("NVIDIA_API_KEY") or "").strip()
    if nvidia_key:
        for model in NVIDIA_MODELS:
            try:
                return call_openai_compatible(
                    NVIDIA_API_URL, nvidia_key, model, prompt, f"NVIDIA({model})",
                    max_tokens=4096, timeout=90,
                )
            except Exception as exc:
                errors.append(str(exc))
                print(f"NVIDIA model {model} failed: {exc}", flush=True)

    groq_key = (os.environ.get("GROQ_API_KEY") or "").strip()
    if groq_key:
        try:
            return call_openai_compatible(GROQ_API_URL, groq_key, GROQ_MODEL, prompt, "Groq")
        except Exception as exc:
            errors.append(str(exc))

    gh_token = (os.environ.get("GITHUB_TOKEN") or "").strip()
    if gh_token:
        try:
            return call_openai_compatible(GITHUB_MODELS_URL, gh_token, GITHUB_MODEL, prompt, "GitHub Models")
        except Exception as exc:
            errors.append(str(exc))

    gemini_key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if gemini_key:
        try:
            return call_gemini(gemini_key, GEMINI_API_URL, prompt)
        except Exception as exc:
            errors.append(str(exc))

    if not errors:
        raise SystemExit("No API keys found (set NARA_API_KEY, NVIDIA_API_KEY, GROQ_API_KEY, GITHUB_TOKEN, or GEMINI_API_KEY)")

    raise RuntimeError(" | ".join(errors))


def validate_with_reason(story):
    """Validate and auto-repair minor LLM schema drift."""
    if not isinstance(story, dict):
        return False, "Story is not a JSON object"

    cast = story.get("cast")
    if not cast or not isinstance(cast, list):
        story["cast"] = [{"name": "Ravi", "type": SP.CHAR_TYPES[0], "color": SP.COLORS[0]}]
    else:
        valid_cast = []
        for idx, c in enumerate(cast[:3]):
            if isinstance(c, dict):
                name = str(c.get("name") or f"Char{idx+1}").strip()
                ctype = c.get("type") if c.get("type") in SP.CHAR_TYPES else SP.CHAR_TYPES[0]
                ccolor = c.get("color") if c.get("color") in SP.COLORS else SP.COLORS[0]
                valid_cast.append({"name": name, "type": ctype, "color": ccolor})
        if not valid_cast:
            valid_cast = [{"name": "Ravi", "type": SP.CHAR_TYPES[0], "color": SP.COLORS[0]}]
        story["cast"] = valid_cast

    sentences = story.get("sentences") or []
    if not (7 <= len(sentences) <= 9):
        return False, f"Wrong sentence count: {len(sentences)} (expected 7-9)"

    for i, sentence in enumerate(sentences, start=1):
        if not isinstance(sentence, dict):
            return False, f"Sentence {i} is not an object"
        for k in ("hi", "hd", "en", "te"):
            if not sentence.get(k):
                return False, f"Sentence {i} missing field '{k}'"
        if _script_share(sentence["hd"], 0x0900, 0x097F) < 0.6:
            return False, f"Sentence {i} 'hd' is not Devanagari Hindi (the voice would read the wrong language)"
        if _script_share(sentence["te"], 0x0C00, 0x0C7F) < 0.6:
            return False, f"Sentence {i} 'te' is not Telugu"

    last_sentence = sentences[-1].get("hi", "")
    words = re.findall(r"\w+", last_sentence.lower())
    if not words:
        return False, "Last sentence 'hi' has no words"

    payoff = str(story.get("payoff_word", "")).strip("!.,? ").lower()
    if not payoff or payoff not in words:
        # Auto-fix payoff_word to the last word of the final Hinglish sentence
        story["payoff_word"] = words[-1]

    return True, None


def _script_share(text, lo, hi):
    """Share of letters in text that fall inside the Unicode block lo..hi."""
    letters = [ch for ch in str(text) if ch.isalpha()]
    return sum(lo <= ord(ch) <= hi for ch in letters) / max(1, len(letters))


def main(out):
    hist = []
    if os.path.exists(HIST):
        with open(HIST, encoding="utf-8") as file:
            hist = json.load(file)

    past = "; ".join(
        h["title"] for h in hist[-200:] if h.get("title")
    ) or "none"

    used_titles = {
        title_key(h["title"])
        for h in hist
        if h.get("title")
    }

    last_error = None
    story = None

    try:
        insights = INS.prompt_block()
        used = INS.used_subjects()
        used_txt = ", ".join(sorted(used, key=lambda w: -used[w])[:60]) or "none"
        gw = INS.genre_weights(GENRES)
    except Exception as exc:
        print("insights unavailable:", exc, flush=True)
        insights, used_txt, gw = "", "none", {}
    if insights:
        print(insights, flush=True)

    for attempt in range(6):
        genre = random.choices(GENRES, weights=[gw.get(g, 1.0) for g in GENRES])[0] if gw else random.choice(GENRES)
        prompt = PROMPT.format(
            genre=genre,
            past=past,
            used=used_txt,
            insights=insights,
            types=", ".join(SP.CHAR_TYPES),
            colors=", ".join(SP.COLORS),
            settings=", ".join(SP.SETTINGS),
            actions=", ".join(SP.ACTIONS),
            props=", ".join(SP.PROPS)
        )

        try:
            candidate = post_story(prompt)
            title = (candidate.get("title") or "").strip()
            candidate["title"] = make_unique_title(title, used_titles)

            ok, reason = validate_with_reason(candidate)

            rep = INS.repeats(candidate) if ok and attempt < 4 else set()
            if rep:
                ok, reason = False, f"Repeats a used subject: {', '.join(sorted(rep))}"

            if ok and title_key(candidate["title"]) not in used_titles:
                story = candidate
                break

            last_error = reason or "Reused previous title"
            print(f"Attempt {attempt + 1}/6 failed validation: {last_error}", flush=True)

        except Exception as exc:
            last_error = str(exc)
            print(f"API attempt {attempt + 1}/6 failed: {exc}", flush=True)

        if attempt < 5:
            time.sleep(2)

    if story is None:
        raise SystemExit(
            f"Story generation failed after 6 attempts: {last_error}"
        )

    SP.normalize(story)
    story["genre"] = genre
    story["format"] = "story"

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
