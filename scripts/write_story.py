#!/usr/bin/env python3
"""Write a fresh Bounce Bhai story with Groq (free API) -> story JSON for the renderer.
usage: python scripts/write_story.py out/story.json
env: GROQ_API_KEY (optional) or GITHUB_TOKEN (GitHub Models, free in Actions)
"""
import json, os, random, re, sys, time, urllib.request, urllib.error
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "engine"))
import scene_spec as SP  # what the Blender renderer can draw (settings, characters, actions, props)
HIST = os.path.join(ROOT, "data", "history.json")
MODEL = os.environ.get("GROQ_MODEL", "whisper-large-v3-turbo")
# Ensure a GENRES list exists -- prefer SP.GENRES if scene_spec defines it, otherwise fall back
GENRES = getattr(SP, "GENRES", ["facts", "mystery", "history", "motivation", "funny"])

PROMPT = """You write viral YouTube Shorts stories for the Hindi/Hinglish channel "Bounce Bhai".
Write ONE original micro-story. Genre: {genre}.
Rules:
- 7 to 9 short sentences, 70-100 words total. Strong hook first sentence, twist/payoff in the LAST sentence.
- If the story is TRUE, use only facts you are highly confident are correct and widely documented (names, years, numbers). If unsure about a detail, leave it out.
- Never reuse these past stories: {past}
- Never write about scams, politics, religion, violence, or real private people. Never use the story "Ismaeel's Silent Journey".
- payoff_word: one single word that appears in the LAST sentence's "hi" text (the climax word).
- The video is a 3D cartoon. Give a "cast" of 1-3 characters (real people in true stories are shown as generic
  cartoon characters; "name" is just a label). type: one of {types}. color (their clothes): one of {colors}.
- Every sentence gets a "scene" the animator can act out:
  setting: one of {settings};
  characters: 1-3 cast names on screen (first one does the action);
  action: one of {actions} (pick the one that best SHOWS the sentence; vary them, avoid "talk" more than 3 times);
  prop: one of {props}.
Return ONLY JSON:
{{"title": "short English title",
  "cast": [{{"name": "Ravi", "type": "man", "color": "blue"}}],
  "hook": "Hinglish hook, max 34 characters, ends with ...",
  "payoff_word": "word",
  "sentences": [{{"hi": "Hinglish in Roman script", "hd": "same sentence in Devanagari Hindi, numbers written out as Hindi words, acronyms spaced like आई बी एम", "en": "natural English[...]",
  "yt_title": {{"hi_roman": "hook + 1 emoji + #shorts (<60 chars)", "hi": "Devanagari title + emoji + #shorts", "en": "English title + emoji + #shorts", "te": "Telugu title + emoji + #shorts"}},
  "question": {{"hi_roman": "one Hinglish question to viewers about the story", "hi": "Devanagari", "en": "English", "te": "Telugu"}},
  "tags": ["8 to 12 tags"],
  "genre_tag": "#facts or #mystery or #history or #motivation or #funny"}}"""


def _post(url, key, payload, timeout=120):
    """POST JSON to url and return a dict with either parsed JSON or raw body.
    Returns:
      {"ok": parsed_json} or {"raw": text} or {"http_error": {"code": int, "body": text}}
    Does not raise on HTTPError so the caller can retry/backoff as needed.
    """
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={
        "Authorization": "Bearer " + key, "Content-Type": "application/json", "User-Agent": "bouncebhai/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            text = r.read().decode(errors="replace")
            # Try to parse JSON: if parsing fails, return raw to allow caller to inspect
            try:
                parsed = json.loads(text)
                return {"ok": parsed}
            except ValueError:
                return {"raw": text}
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        return {"http_error": {"code": e.code, "body": body}}


def groq(prompt):
    """Groq if GROQ_API_KEY is set, otherwise free GitHub Models with the workflow's GITHUB_TOKEN.
    Tries a small, conservative list of models, with retries/backoff on transient errors,
    and validates returned text contains JSON before parsing.
    """
    msgs = [{"role": "user", "content": prompt}]
    cands = []  # (url, key, model)
    if os.environ.get("GROQ_API_KEY"):
        # If you have a GROQ key, prefer the single configured model to avoid trying many large models
        g = "https://api.groq.com/openai/v1/chat/completions"
        cands.append((g, os.environ["GROQ_API_KEY"], MODEL))
    if os.environ.get("GITHUB_TOKEN"):
        gh = "https://models.github.ai/inference/chat/completions"
        # prefer a small, widely-available GitHub model by default (set GH_MODEL to override)
        default_gh = os.environ.get("GH_MODEL", "openai/gpt-4o-mini")
        cands.append((gh, os.environ["GITHUB_TOKEN"], default_gh))

    if not cands:
        raise SystemExit("No model credentials found (set GROQ_API_KEY or ensure GITHUB_TOKEN is present)")

    last = None
    for url, key, model in cands:
        # Try json mode first, then plain text, but keep tries per model small
        for json_mode in (True, False):
            payload = {"model": model, "temperature": 0.8, "messages": msgs}
            if json_mode:
                payload["response_format"] = {"type": "json_object"}
            # retries with exponential backoff for transient errors
            backoff = 1.0
            for attempt in range(1, 4):
                res = _post(url, key, payload)
                # HTTP error handling
                if "http_error" in res:
                    code = res["http_error"]["code"]
                    body = res["http_error"]["body"]
                    print("API error", code, model, body[:1000], flush=True)
                    last = f"HTTP {code}"
                    if code in (429, 502, 503, 504):
                        sleep = backoff + random.random() * backoff
                        time.sleep(sleep)
                        backoff *= 2
                        continue
                    else:
                        # non-retryable for this model/payload; break retry loop to try next mode/model
                        break
                # successful HTTP; either parsed JSON or raw text
                if "ok" in res:
                    # typical response contains choices -> message -> content
                    ok = res["ok"]
                    try:
                        txt = ok["choices"][0]["message"]["content"]
                    except Exception as e:
                        # fallback: if response structure is unexpected, try to find any string content
                        txt = json.dumps(ok) if isinstance(ok, dict) else str(ok)
                else:
                    txt = res.get("raw", "") or ""
                if not txt or not txt.strip():
                    last = "empty response"
                    # empty body: treat as transient and retry a couple of times
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                # Ensure there's a JSON object inside the text before attempting to slice/parse
                if "{" not in txt or "}" not in txt:
                    last = "no-json-in-content"
                    # If not in JSON mode, maybe the model returned plain text; skip parsing attempt
                    print("story try failed:", model, "no JSON object found in content (len {})".format(len(txt)), flush=True)
                    break
                # extract the first {...} block robustly
                try:
                    start = txt.index("{")
                    end = txt.rindex("}") + 1
                    piece = txt[start:end]
                    parsed = json.loads(piece)
                    return parsed
                except Exception as e:
                    # parsing failed; record and decide whether to retry
                    print("story try failed:", model, "json_parse", str(e)[:200], flush=True)
                    last = e
                    # if this was JSON mode, don't retry same mode many times; break to try plain mode or next model
                    break
            # end retries for json_mode
            # move to next json_mode or next model
    raise SystemExit(f"story API failed on every model: {last}")

# rest of the file (valid, main, etc.) unchanged

def valid(s):
    ss = s.get("sentences") or []
    if not (6 <= len(ss) <= 10): return False
    if not all(all(x.get(k) for k in ("hi", "hd", "en", "te")) for x in ss): return False
    pw = s.get("payoff_word", "").strip("!.,").lower()
    return any(w.strip("!.,?").lower() == pw for w in ss[-1]["hi"].split())


def main(out):
    hist = json.load(open(HIST)) if os.path.exists(HIST) else []
    past = "; ".join(h["title"] for h in hist[-200:]) or "none"
    for attempt in range(4):
        s = groq(PROMPT.format(genre=random.choice(GENRES), past=past, types=", ".join(SP.CHAR_TYPES),
                               colors=", ".join(SP.COLORS), settings=", ".join(SP.SETTINGS),
                               actions=", ".join(SP.ACTIONS), props=", ".join(SP.PROPS)))
        if valid(s) and s["title"].lower() not in {h["title"].lower() for h in hist}: break
        time.sleep(3)
    else:
        raise SystemExit("story generation failed")
    SP.normalize(s)
    rnd = random.Random()
    s.update({
        "out": out.replace(".json", ".mp4"),
        "seed": rnd.randint(1, 99999),
        "gap_deg": rnd.randint(24, 40), "spin": rnd.randint(40, 110), "grow": round(rnd.uniform(0.8, 2.0), 2),
        "target": [25, 40], "hue": round(rnd.random(), 2), "ball_hue": round(rnd.random(), 2),
    })
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    json.dump(s, open(out, "w"), ensure_ascii=False, indent=1)
    print("story:", s["title"])


if __name__ == "__main__":
    main(sys.argv[1])
