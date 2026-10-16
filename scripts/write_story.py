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

GENRES = [
    "a surprising TRUE invention/origin story (well documented, famous sources only)",
    "a surprising TRUE history story from India (well documented)",
    "a surprising TRUE science or nature fact told as a story",
    "a mystery with a twist (clearly fictional, no real names)",
    "an underdog / motivational TRUE story of a famous person (well documented)",
    "a 'kya aap jaante the' real-world story about a famous brand, food or place (well documented)",
    "a funny everyday desi story (clearly fictional, no real names)",
]

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
  "sentences": [{{"hi": "Hinglish in Roman script", "hd": "same sentence in Devanagari Hindi, numbers written out as Hindi words, acronyms spaced like आई बी एम", "en": "natural English", "te": "natural Telugu", "scene": {{"setting": "street", "characters": ["Ravi"], "action": "walk", "prop": "none"}}}}],
  "yt_title": {{"hi_roman": "hook + 1 emoji + #shorts (<60 chars)", "hi": "Devanagari title + emoji + #shorts", "en": "English title + emoji + #shorts", "te": "Telugu title + emoji + #shorts"}},
  "question": {{"hi_roman": "one Hinglish question to viewers about the story", "hi": "Devanagari", "en": "English", "te": "Telugu"}},
  "tags": ["8 to 12 tags"],
  "genre_tag": "#facts or #mystery or #history or #motivation or #funny"}}"""


def _post(url, key, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={
        "Authorization": "Bearer " + key, "Content-Type": "application/json", "User-Agent": "bouncebhai/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        print("API error", e.code, payload.get("model"), e.read().decode(errors="replace")[:500], flush=True)
        raise


def groq(prompt):
    """Groq if GROQ_API_KEY is set, otherwise free GitHub Models with the workflow's GITHUB_TOKEN.
    Tries a few models, with and without JSON mode, and prints the API's reason on failure."""
    msgs = [{"role": "user", "content": prompt}]
    cands = []  # (url, key, model): Groq first if a key is set, then free GitHub Models as backup
    if os.environ.get("GROQ_API_KEY"):
        g = "https://api.groq.com/openai/v1/chat/completions"
        for m in (MODEL, "llama-3.3-70b-versatile", "openai/gpt-oss-20b"):
            cands.append((g, os.environ["GROQ_API_KEY"], m))
    if os.environ.get("GITHUB_TOKEN"):
        gh = "https://models.github.ai/inference/chat/completions"
        for m in (os.environ.get("GH_MODEL", "openai/gpt-4.1"), "openai/gpt-4o-mini", "openai/gpt-4o"):
            cands.append((gh, os.environ["GITHUB_TOKEN"], m))
    last = None
    for url, key, model in cands:
        for json_mode in (True, False, False):  # JSON mode, then two plain tries (output is random)
            payload = {"model": model, "temperature": 0.8, "messages": msgs}
            if json_mode:
                payload["response_format"] = {"type": "json_object"}
            try:
                txt = _post(url, key, payload)["choices"][0]["message"]["content"]
                txt = txt[txt.index("{"):txt.rindex("}") + 1]  # tolerate text around the JSON
                return json.loads(txt)
            except Exception as e:
                print("story try failed:", model, "json" if json_mode else "plain", str(e)[:200], flush=True)
                last = e
    raise SystemExit(f"story API failed on every model: {last}")


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
    SP.normalize(s)  # unsupported scene values -> safe defaults (never fails the run)
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
