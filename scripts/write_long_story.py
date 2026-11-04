#!/usr/bin/env python3
"""Write an ORIGINAL 8-10 minute moral cartoon story ("kahani") natively in Telugu, Hindi or English.

usage: python scripts/write_long_story.py out/long_x.json te|hi|en

Two LLM stages so long stories stay coherent and free-tier token limits are respected:
  1. outline (English control fields + native title / moral / thumbnail text): cast with fixed looks, 11-14 scenes
     with set, time, weather, mood, props and what happens (hook -> conflict -> rising tension -> twist -> payoff)
  2. dialogue for 3-4 scenes per call, written natively in the target language, with speakers, emotions, actions
     (walk, point, give an object, cry, laugh, angry, surprised ...), objects and SFX
Every reply is parsed, repaired and validated (script check, known speakers/sets/actions); failing calls retry on the
next live model (Groq / NVIDIA / NaraRouter model lists are read from their /models endpoints).
Themes already used (data/long_topics.json) are never repeated.
"""
import json, os, random, re, sys, time, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "engine"))
from write_story import extract_json   # noqa: E402

TOPICS = os.path.join(ROOT, "data", "long_topics.json")
LANG_NAME = {"te": "Telugu", "hi": "Hindi", "en": "English"}
SCRIPT = {"te": (0x0C00, 0x0C7F), "hi": (0x0900, 0x097F)}
CHARS_PER_SEC = {"te": 11.4, "hi": 9.3, "en": 11.6}
TARGET_MIN = float(os.environ.get("BB_LONG_MINUTES", "9.0"))

THEME_BANK = [
    "a greedy pani puri seller who cheats customers vs an honest neighbour seller",
    "an honest samosa seller whose kindness to a hungry old woman is rewarded",
    "a clever old woman (chalak budhiya) who outsmarts a greedy money-lender",
    "a poor family surviving a flood in the rainy season, and the neighbour who helps",
    "a greedy merchant who weighs grain with a false scale and gets caught",
    "two brothers who divide their father's land, one greedy, one generous",
    "a mother-in-law who is strict and a daughter-in-law who wins her heart with patience",
    "a magical clay pot (jadui matka) that doubles whatever is put in it, and a greedy neighbour",
    "a lazy son and a hard-working daughter and their father's hidden treasure in the field",
    "a chai seller at a village bus stop who returns a lost bag of money",
    "a momos seller who uses stale food and learns a lesson",
    "a poor potter whose magic pots grant food only to the honest",
    "a greedy landlord (zamindar) and a clever farmer who tricks him fairly",
    "a jealous neighbour who copies a kind woman to get magical gifts and fails",
    "a poor boy selling mangoes who refuses to cheat and becomes rich",
    "an honest woodcutter whose axe falls in the river and a magical spirit tests him",
    "a greedy sweet-shop owner (jalebi wala) and the festival day crowd",
    "a poor widow who feeds travellers in the rain and gets a surprise",
    "a stingy rich man who never shares and the day his village saves him",
    "two friends, one who keeps a promise and one who breaks it",
    "a clever daughter-in-law who saves the family shop from a cheat",
    "a magical cooking pan (jadui kadhai) that makes endless dosas",
    "a proud king who learns humility from a poor vegetable seller",
    "a greedy brother-in-law who tries to steal a poor family's cow",
    "a village girl who studies under a street lamp and becomes a teacher",
    "an old grandfather's magic walking stick that only works for the kind",
    "a greedy ice-cream cart owner in summer and a thirsty old man",
    "a poor tailor and a magical needle that sews gold thread",
    "a vada pav seller in a small town who never wastes food",
    "a mother who sells idli to send her son to school, and the son's gratitude",
]
SETS = "village_street, house_interior, village_home (courtyard), field, market, forest, river, palace, school, shop"
TYPES = "man, woman, oldman, oldwoman, boy, girl"
COSTUMES = "lungi, dhoti, kurta, shirt, saree, salwar, frock, pavadai, shorts, royal, royal_f"
COLORS = "red, maroon, orange, saffron, yellow, green, parrot, teal, blue, sky, purple, pink, magenta, white, cream, brown, grey, gold, indigo"
ACTIONS = ("talk, walk, run, enter, exit, point, give, take, wave, cry, laugh, angry, surprised, scared, think, hips, "
           "proud, celebrate, beg, greedy, scratch, greet, sad, show, stop, shrug, count, eat, sell, cook, comfort, shout")
EXPRS = "neutral, happy, laugh, sad, cry, angry, surprised, scared, greedy, sly, thinking, proud, worried, ashamed"
OBJECTS = ("coin, coins, coin_bag, money, gold_pot, pot, magic_pot, mango, roti, letter, basket, umbrella, stick, gift, "
           "bowl, plate, flower, key, lamp, samosa, pani_puri, chai, momos, rice_sack, book, necklace, fish, jar")
PROPS = ("pani_puri_cart, samosa_cart, chai_cart, momos_cart, fruit_cart, vegetable_cart, jalebi_cart, ice_cream_cart, "
         "dosa_cart, idli_cart, vada_pav_cart, well, charpai, magic_pot, pot, sacks, tree, none")
SFX = "none, coins, knock, door, thunder, magic, boing, pop, splash, thud, laugh, ding"

# ======================================================================================== LLM plumbing
GROQ, NV = "https://api.groq.com/openai/v1", "https://integrate.api.nvidia.com/v1"
NARA = os.environ.get("NARA_API_URL", "https://router.bynara.id/v1/chat/completions").rsplit("/chat/completions", 1)[0]
PREFS = {"groq": ["gpt-oss-120b", "kimi-k2", "llama-4-maverick", "qwen3", "llama-3.3-70b"],
         "nvidia": ["kimi-k2", "deepseek-v3", "deepseek-v4", "qwen3-235b", "qwen3-next", "gpt-oss-120b",
                    "llama-4-maverick", "mistral-large", "llama-3.3-70b", "nemotron-super"],
         "nara": []}
_MODELS = {}


def _get(url, key):
    r = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}", "User-Agent": "bouncebhai-long"})
    return json.loads(urllib.request.urlopen(r, timeout=30).read())


def list_models(base, key):
    if base not in _MODELS:
        try:
            _MODELS[base] = [m["id"] for m in _get(base + "/models", key)["data"]]
        except Exception as e:
            print("model list failed:", base, str(e)[:120], flush=True)
            _MODELS[base] = []
    return _MODELS[base]


def candidates():
    out = []
    g = os.environ.get("GROQ_API_KEY")
    if g:
        ids = list_models(GROQ, g)
        for p in PREFS["groq"]:
            out += [("groq", GROQ, g, i) for i in ids if p in i.lower() and ("groq", GROQ, g, i) not in out
                    and "guard" not in i and "tts" not in i and "whisper" not in i]
    n = os.environ.get("NVIDIA_API_KEY")
    if n:
        ids = list_models(NV, n)
        picked = []
        for p in PREFS["nvidia"]:
            picked += [i for i in ids if p in i.lower() and i not in picked and "embed" not in i and "reward" not in i
                       and "guard" not in i and "vl" not in i.lower().split("/")[-1].split("-")]
        out += [("nvidia", NV, n, i) for i in picked[:6]]
    k = os.environ.get("NARA_API_KEY")
    if k:
        for m in [m.strip() for m in os.environ.get("NARA_MODELS", "laguna-s-2.1,nemotron-3.5-lightning-free").split(",") if m.strip()]:
            out.append(("nara", NARA, k, m))
    return out


def chat(prompt, system, validate, max_tokens=9000, tries_per_model=1, label=""):
    """Try live models in order until one returns JSON that passes validate(obj) -> obj (raise to reject)."""
    cands = candidates()
    if not cands:
        raise SystemExit("No LLM keys (GROQ_API_KEY / NVIDIA_API_KEY / NARA_API_KEY)")
    errs = []
    for prov, base, key, model in cands:
        for attempt in range(tries_per_model + 1):
            body = {"model": model, "temperature": 0.85, "max_tokens": max_tokens,
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"}}
            if "gpt-oss" in model:
                body["reasoning_effort"] = "low"
            if "qwen3" in model and prov != "groq":
                body["chat_template_kwargs"] = {"thinking": False}
            t0 = time.time()
            try:
                req = urllib.request.Request(base + "/chat/completions", data=json.dumps(body).encode(),
                                             headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}",
                                                      "User-Agent": "bouncebhai-long"})
                try:
                    raw = urllib.request.urlopen(req, timeout=240).read().decode("utf-8", "replace")
                except urllib.error.HTTPError as e:
                    det = e.read().decode("utf-8", "replace")[:400]
                    if e.code == 400 and "response_format" in det:
                        body.pop("response_format")
                        req = urllib.request.Request(base + "/chat/completions", data=json.dumps(body).encode(),
                                                     headers=req.headers)
                        raw = urllib.request.urlopen(req, timeout=240).read().decode("utf-8", "replace")
                    elif e.code == 429:
                        m = re.search(r"try again in ([\d.]+)(m?s)", det)
                        wait = float(m.group(1)) / (1000 if m and m.group(2) == "ms" else 1) if m else 20
                        if wait <= 65 and attempt < tries_per_model:
                            print(f"  {label} {prov}:{model} rate-limited, waiting {wait:.0f}s", flush=True)
                            time.sleep(wait + 1)
                            continue
                        raise RuntimeError(f"HTTP 429 {det[:160]}")
                    else:
                        raise RuntimeError(f"HTTP {e.code} {det[:200]}")
                content = json.loads(raw)["choices"][0]["message"].get("content") or ""
                obj = validate(extract_json(content))
                print(f"  {label} ok: {prov}:{model} in {time.time() - t0:.0f}s", flush=True)
                return obj, f"{prov}:{model}"
            except Exception as e:
                msg = f"{prov}:{model}: {str(e)[:220]}"
                errs.append(msg)
                print(f"  {label} failed {msg}", flush=True)
                break
    raise RuntimeError(f"all models failed for {label}: " + " | ".join(errs[-6:]))


# ======================================================================================== validation helpers
def script_share(text, lang):
    if lang == "en":
        letters = [c for c in text if c.isalpha()]
        return sum(c.isascii() for c in letters) / max(1, len(letters))
    lo, hi = SCRIPT[lang]
    letters = [c for c in text if c.isalpha() or lo <= ord(c) <= hi]
    return sum(lo <= ord(c) <= hi for c in letters) / max(1, len(letters))


def slug(s):
    s = re.sub(r"[^a-z0-9]+", "_", (s or "").lower()).strip("_")
    return s or "c"


def load_topics():
    try:
        return json.load(open(TOPICS, encoding="utf-8"))
    except Exception:
        return []


def pick_seed(lang, topics, rng):
    used = " ".join((t.get("seed") or t.get("theme") or "") for t in topics).lower()
    fresh = [s for s in THEME_BANK if s.lower() not in used]
    return rng.choice(fresh or THEME_BANK)


# ======================================================================================== stage 1: outline
OUTLINE = """You are the head writer of "Bounce Bhai", a YouTube channel of long animated moral stories (kahani) for Indian
families, like the top Hindi/Telugu "moral story" cartoon channels (titles such as "लालची आलू पुरी वाला | Hindi Kahani |
Moral Story"). Our videos are REAL 2D cutout animation, so write for acting: dialogue, emotions, movement, objects.

Plan ONE original story, about {minutes:.0f} minutes long, to be written in {lang_name}.
Story seed (make it your own, original, surprising): {seed}
Never reuse these earlier story themes: {used}

Rules:
- Human characters only (no talking animals), 3 to 5 named characters with distinct personalities, ages and looks,
  typical of an Indian village or small town (names natural for {lang_name} speakers). One may be a narrator-favourite
  elder. Family-friendly. No religion, gods, temples, prayer, politics, violence or romance.
- Strong structure over {n_scenes} scenes: scene 1 = HOOK in the first 15 seconds (a teaser question/shock to the
  viewer), relatable conflict, rising tension, a twist (can be gently magical: a jadui pot/tree/stick), an emotional
  payoff, and a clear moral. Gentle humour in several scenes. The last scene shows the happy ending.
- Vary sets and times: use at least 5 different sets and at least one night or rain scene.
- Each scene lists who is on screen (2 to 4 characters, rarely 1, max 4) with positions as fractions 0.1-0.9.
- title: in {lang_name} {script_hint}, click-worthy in the niche's style, 3 to 7 words, e.g. "<adjective> <food> seller"
  or "<character>'s magic pot". thumbnail_text: 2 to 4 punchy {lang_name} words (shock/greed/emotion), different from the title.
- moral: one short sentence in {lang_name}. description: 2-3 sentences in {lang_name} (no spoilers of the twist).

Allowed values:
- character type: {types}; costume: {costumes}; color: {colors}; build: thin | normal | fat;
  role: hero | greedy | villain | elder | wife | husband | child | vendor | friend | merchant | king | other
- set: {sets}; time: day | evening | night; weather: clear | rain;
  mood: happy | calm | funny | sad | tense | magical
- prop (a stage piece standing in the scene, or "none"): {props}; prop_owner: the character id who stands at it
- expression: {exprs}

Return ONLY JSON:
{{"theme": "<one-line English summary of THIS story's theme>",
  "title": "...", "thumbnail_text": "...", "moral": "...", "moral_en": "...", "description": "...",
  "tags": ["8-14 tags mixing {lang_name} and English, e.g. moral story, kahani, cartoon"],
  "thumbnail": {{"character": "<id>", "expression": "greedy|surprised|cry|angry|scared", "object": "<object or none>"}},
  "characters": [{{"id": "ramu", "name": "<name in {lang_name} script>", "name_en": "Ramu", "type": "man", "costume": "lungi",
                  "color": "orange", "build": "thin", "role": "hero", "trait": "honest, cheerful"}}],
  "scenes": [{{"set": "village_street", "time": "day", "weather": "clear", "mood": "happy", "prop": "pani_puri_cart",
              "prop_owner": "ramu", "cast": [{{"id": "ramu", "pos": 0.3, "expression": "happy"}}],
              "chapter": "<2-4 word chapter name in {lang_name}>",
              "what_happens": "2-3 English sentences: who does what, what is said, the emotional beat"}}]}}"""


def validate_outline(o, lang):
    import long_sets as LS, long_cast as LC
    if not isinstance(o.get("characters"), list) or not (2 <= len(o["characters"]) <= 6):
        raise ValueError("need 2-6 characters")
    if not isinstance(o.get("scenes"), list) or len(o["scenes"]) < 8:
        raise ValueError(f"need >= 8 scenes, got {len(o.get('scenes') or [])}")
    for k in ("title", "moral", "thumbnail_text"):
        if not (o.get(k) or "").strip():
            raise ValueError(f"missing {k}")
        if lang != "en" and script_share(o[k], lang) < 0.6:
            raise ValueError(f"{k} not in {LANG_NAME[lang]} script: {o[k][:40]}")
    ids = {}
    for c in o["characters"]:
        cid = slug(c.get("id") or c.get("name_en") or c.get("name"))
        while cid in ids.values():
            cid += "x"
        ids[c.get("id")] = cid
        c["id"] = cid
        t = (c.get("type") or "man").lower()
        c["type"] = t if t in LC.BODIES else {"grandpa": "oldman", "grandma": "oldwoman", "old_man": "oldman",
                                               "old_woman": "oldwoman", "child": "boy", "king": "man", "queen": "woman"}.get(t, "man")
        if not (c.get("name") or "").strip():
            c["name"] = c.get("name_en") or cid.title()
    for sc in o["scenes"]:
        sc["set"] = LS.set_name(sc.get("set"))
        sc["time"] = sc.get("time") if sc.get("time") in ("day", "evening", "night") else "day"
        sc["weather"] = "rain" if sc.get("weather") == "rain" else "clear"
        sc["mood"] = (sc.get("mood") or "calm").lower()
        cast = []
        for c in sc.get("cast") or []:
            if isinstance(c, str):
                c = {"id": c}
            cid = ids.get(c.get("id"), slug(c.get("id")))
            if cid in ids.values() and cid not in [x["id"] for x in cast]:
                c["id"] = cid
                c["expression"] = LC.expr_name(c.get("expression"))
                cast.append(c)
        sc["cast"] = cast[:4]
        if sc.get("prop_owner"):
            sc["prop_owner"] = ids.get(sc["prop_owner"], slug(sc["prop_owner"]))
        if (sc.get("prop") or "none").lower() in ("none", "null", ""):
            sc["prop"] = None
    th = o.get("thumbnail") or {}
    th["character"] = ids.get(th.get("character"), slug(th.get("character")))
    if th["character"] not in ids.values():
        th["character"] = o["characters"][0]["id"]
    o["thumbnail"] = th
    o["tags"] = [str(t)[:40] for t in (o.get("tags") or [])][:15]
    return o


# ======================================================================================== stage 2: dialogue
DIALOGUE = """You are writing the {lang_name} dialogue script of an animated moral story for the YouTube channel "Bounce Bhai".
Write natively in {lang_name} {script_hint} - natural, simple, spoken {lang_name} that families in villages speak, with
warmth and gentle humour. NOT a translation. Numbers as words.

STORY: "{title}" - theme: {theme}. Moral: {moral_en}
CHARACTERS (speaker ids): {chars}
FULL SCENE PLAN (for context): {plan}
{previous}
Now write scenes {first} to {last} only. Per scene about {lines_lo}-{lines_hi} lines totalling about {chars_target}
{lang_name} characters of spoken text ({secs} seconds of audio per scene). Mostly DIALOGUE between characters (at most
1 in 4 lines is narrator), each line 1-2 short sentences, so the actors can react.{hook}
Each line object:
- speaker: "narrator" or a character id
- text: the spoken words in {lang_name} only (no stage directions, no speaker names, no quotes, no emoji)
- emotion: one of {exprs}
- action (optional, the speaker's acting; for narrator lines use "actor" to name who acts): one of {actions}
- target (optional): character id the line is said to / given to / pointed at
- object (optional, for give/take/show/count/eat): one of {objects}
- to (optional, for walk/run): 0.1-0.9 where to walk
- sfx (optional): one of {sfx}
- reactions (optional): {{"<id>": "<emotion>"}} how listeners react
Use movement (enter/walk/exit), giving objects, pointing, crying, laughing, anger, surprise and humour naturally.

Return ONLY JSON: {{"scenes": [{{"index": {first}, "lines": [{{"speaker": "...", "text": "...", "emotion": "...", "action": "..."}}]}}]}}"""

ACTION_OK = set(a.strip() for a in ACTIONS.split(","))


def validate_dialogue(o, lang, ids, idx_range, min_lines=4):
    import long_cast as LC, long_props as LP
    scs = o.get("scenes")
    if not isinstance(scs, list) or not scs:
        raise ValueError("no scenes")
    got = {}
    for k, sc in enumerate(scs):
        i = sc.get("index")
        try:
            i = int(i)
        except Exception:
            i = idx_range[min(k, len(idx_range) - 1)]
        if i not in idx_range:
            i = idx_range[min(k, len(idx_range) - 1)]
        lines = []
        for ln in sc.get("lines") or []:
            if not isinstance(ln, dict):
                continue
            text = re.sub(r"\s+", " ", str(ln.get("text") or "")).strip().strip('"')
            text = re.sub(r"^\s*[\w\u0900-\u097F\u0C00-\u0C7F ]{1,20}\s*:\s*", "", text) if len(text) > 30 and ":" in text[:22] else text
            if len(text) < 2:
                continue
            sp = slug(ln.get("speaker"))
            if sp not in ids:
                sp = next((k2 for k2 in ids if sp and sp != "narrator" and (sp in k2 or k2 in sp)), "narrator")
            a = (ln.get("action") or "talk").lower().strip()
            a = a if a in ACTION_OK else "talk"
            item = {"speaker": sp, "text": text, "emotion": LC.expr_name(ln.get("emotion")), "action": a}
            for key in ("target", "actor"):
                v = slug(ln.get(key)) if ln.get(key) else None
                if v in ids:
                    item[key] = v
            ob = LP.obj_name(ln.get("object"))
            if ob:
                item["object"] = ob
            if ln.get("to") is not None:
                try:
                    item["to"] = max(0.08, min(0.92, float(ln["to"])))
                except Exception:
                    pass
            s = (ln.get("sfx") or "").lower()
            if s and s != "none":
                item["sfx"] = s
            if isinstance(ln.get("reactions"), dict):
                item["reactions"] = {slug(k2): v for k2, v in ln["reactions"].items() if slug(k2) in ids}
            lines.append(item)
        if len(lines) < min_lines:
            raise ValueError(f"scene {i}: only {len(lines)} lines")
        alltext = " ".join(l["text"] for l in lines)
        if script_share(alltext, lang) < 0.75:
            raise ValueError(f"scene {i} not in {LANG_NAME[lang]} script")
        got[i] = lines
    missing = [i for i in idx_range if i not in got]
    if missing:
        raise ValueError(f"missing scenes {missing}")
    return got


def main(out, lang):
    if lang not in LANG_NAME:
        raise SystemExit("lang must be te, hi or en")
    rng = random.Random()
    topics = load_topics()
    seed = os.environ.get("BB_LONG_SEED_THEME") or pick_seed(lang, topics, rng)
    used = "; ".join(t.get("theme", "") for t in topics[-40:]) or "none yet"
    lang_name = LANG_NAME[lang]
    script_hint = {"te": "(Telugu script)", "hi": "(Devanagari script)", "en": "(simple Indian English)"}[lang]
    n_scenes = 12 if TARGET_MIN <= 9.5 else 14
    sysmsg = "You are an award-winning Indian children's and family story writer. Reply with strictly valid JSON only."
    print(f"long story: lang={lang} seed='{seed}'", flush=True)
    o, model1 = chat(OUTLINE.format(minutes=TARGET_MIN, lang_name=lang_name, seed=seed, used=used, n_scenes=n_scenes,
                                    script_hint=script_hint, types=TYPES, costumes=COSTUMES, colors=COLORS, sets=SETS,
                                    props=PROPS, exprs=EXPRS),
                     sysmsg, lambda x: validate_outline(x, lang), max_tokens=7000, tries_per_model=1, label="outline")
    ids = {c["id"]: c for c in o["characters"]}
    scenes = o["scenes"][:15]
    n = len(scenes)
    secs_total = TARGET_MIN * 60 - 8 - n * 1.6
    per_scene = secs_total / n
    speech_secs = per_scene - 4.5     # ~9 line gaps per scene
    chars_target = int(speech_secs * CHARS_PER_SEC[lang])
    lines_lo, lines_hi = 7, 11
    plan = json.dumps([{"index": i, "set": s["set"], "time": s["time"], "on_screen": [c["id"] for c in s["cast"]],
                        "prop": s.get("prop"), "what_happens": s.get("what_happens", "")} for i, s in enumerate(scenes)],
                      ensure_ascii=False)
    chars_desc = json.dumps([{"id": c["id"], "name": c["name"], "type": c["type"], "role": c.get("role"),
                              "trait": c.get("trait")} for c in o["characters"]], ensure_ascii=False)
    batch = 3
    written = {}
    models = [model1]
    prev_tail = ""
    for b0 in range(0, n, batch):
        rng_ = list(range(b0, min(n, b0 + batch)))
        hook = ""
        if b0 == 0:
            hook = ("\nSCENE 0 MUST OPEN WITH A HOOK: the first line is the narrator asking the viewer a gripping question or"
                    " teasing the shocking twist, in under 15 seconds, then the story starts.")
        if rng_[-1] == n - 1:
            hook += ("\nThe LAST scene ends with the happy ending and the characters' feelings; do NOT state the moral as a"
                     " narrator line, it is added separately.")
        prompt = DIALOGUE.format(lang_name=lang_name, script_hint=script_hint, title=o["title"], theme=o.get("theme"),
                                 moral_en=o.get("moral_en") or o["moral"], chars=chars_desc, plan=plan,
                                 previous=("The previous scene ended with: " + prev_tail) if prev_tail else "",
                                 first=rng_[0], last=rng_[-1], lines_lo=lines_lo, lines_hi=lines_hi,
                                 chars_target=chars_target, secs=int(per_scene), hook=hook, exprs=EXPRS,
                                 actions=ACTIONS, objects=OBJECTS, sfx=SFX)
        got, m = chat(prompt, sysmsg, lambda x, r=rng_: validate_dialogue(x, lang, ids, r), max_tokens=9000,
                      tries_per_model=1, label=f"scenes {rng_[0]}-{rng_[-1]}")
        models.append(m)
        written.update(got)
        last = got[rng_[-1]]
        prev_tail = json.dumps(last[-3:], ensure_ascii=False)
    # ---- assemble
    story = {"lang": lang, "format": "long_story", "seed": rng.randint(1, 10 ** 6), "theme": o.get("theme"),
             "seed_theme": seed, "title": o["title"].strip(), "thumbnail_text": o["thumbnail_text"].strip(),
             "moral": o["moral"].strip(), "moral_en": o.get("moral_en", ""), "description": o.get("description", ""),
             "tags": o.get("tags", []), "thumbnail": o["thumbnail"], "characters": o["characters"], "models": models,
             "scenes": []}
    for i, sc in enumerate(scenes):
        s = {k: sc.get(k) for k in ("set", "time", "weather", "mood", "prop", "prop_owner", "cast", "chapter")}
        s["summary"] = sc.get("what_happens", "")
        s["lines"] = written[i]
        story["scenes"].append(s)
    story["scenes"][-1]["lines"].append({"speaker": "narrator", "text": story["moral"], "emotion": "happy", "action": "talk"})
    story["scenes"][-1]["moral_card"] = True
    est = sum(len(l["text"]) for s in story["scenes"] for l in s["lines"]) / CHARS_PER_SEC[lang]
    est += sum(len(s["lines"]) for s in story["scenes"]) * 0.45 + len(story["scenes"]) * 1.6 + 8
    story["estimated_minutes"] = round(est / 60, 1)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    json.dump(story, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"::notice title=story::{story['title']} | {len(story['scenes'])} scenes, "
          f"{sum(len(s['lines']) for s in story['scenes'])} lines, ~{story['estimated_minutes']} min | models: {', '.join(sorted(set(models)))}",
          flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "te")
