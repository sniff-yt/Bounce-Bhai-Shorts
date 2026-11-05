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
from write_story import extract_json as _extract_json_strict   # noqa: E402


def extract_json(raw_text):
    """Lenient JSON: Gemini sometimes appends text / a second object after the JSON ("Extra data", run 41881160270),
    so decode the FIRST complete object with raw_decode and ignore whatever follows."""
    text = re.sub(r"<think>.*?</think>", "", raw_text or "", flags=re.DOTALL).strip()
    text = re.sub(r"^\s*```(?:json)?\s*", "", text)
    dec = json.JSONDecoder()
    i = text.find("{")
    while i >= 0:
        try:
            obj, _ = dec.raw_decode(text, i)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
        i = text.find("{", i + 1)
        if i > 2000:
            break
    return _extract_json_strict(raw_text)

TOPICS = os.path.join(ROOT, "data", "long_topics.json")
LANG_NAME = {"te": "Telugu", "hi": "Hindi", "en": "English"}
SCRIPT = {"te": (0x0C00, 0x0C7F), "hi": (0x0900, 0x097F)}
CHARS_PER_SEC = {"te": 11.4, "hi": 9.3, "en": 11.6}
TARGET_MIN = float(os.environ.get("BB_LONG_MINUTES", "9.5"))   # real minutes of video (target window 9-10)
REAL_RATIO = 0.92   # estimate_secs() over-estimates: run 41852353516 estimated 10.0 min, rendered 9.17 min
MIN_REAL, MAX_REAL = 9.15, 9.85
LANG_GUIDE = {
    "te": ("Write the way families in Telangana / Andhra villages really talk to each other: short simple sentences, "
           "everyday words (ఏంటి, చూడు, అయ్యో, సరే, ఇదిగో, రా, పదా, అమ్మా, నాన్నా, బాబూ), correct verb endings for "
           "gender and respect (మీరు / నువ్వు). No bookish Sanskrit words, no invented or misspelt words, no "
           "word-by-word translation from English, no English words in Telugu script unless villagers use them (బస్సు). "
           "Use the common word for things: pot = కుండ, money-lender = వడ్డీ వ్యాపారి, clever = తెలివైన, greed = అత్యాశ, "
           "magic = మాయ, loan = అప్పు, interest = వడ్డీ, stick = కర్ర, fruit = పండ్లు, kindness = దయ (never 'దయా' on its own; "
           "kind person = దయ ఉన్నవాడు / మంచి మనసున్నవాడు). Address a woman with అమ్మా / అక్కా, never ఏమయ్యా. Never write like these "
           "earlier bad scripts: 'బాణి' or 'కడవు' for a pot or stick, the non-words 'చతుర్తి' and 'కాంచం', the awkward moral 'బుద్ధి "
           "వృద్ధి వలన లాభం', 'అత్యాశ నన్ను కోల్పోయింది' (say 'అత్యాశ వల్ల అన్నీ పోగొట్టుకున్నా'), 'మీ మాటలు మమ్మల్ని బలవంతం "
           "చేస్తాయి' (say 'మీ మాటలు మాకు ధైర్యం ఇస్తాయి'), 'మనసులో ముద్దు పడి పోయారు', a hook asking if a man turns into a golden pig."),
    "hi": ("Write natural spoken Hindi the way families in small towns of UP / MP / Bihar talk (अरे, देखो, चलो, बेटा, "
           "अम्मा, भैया, दादी): short simple sentences, everyday words, common Hinglish only where people really use it "
           "(मोबाइल, बस). No shuddh / bookish Hindi, no heavy Urdu poetry, no invented words, no translation-ese. Use "
           "common words: pot = मटका, money-lender = साहूकार, clever = समझदार / चालाक, greed = लालच, loan = कर्ज़."),
    "en": "Write simple, warm Indian English as families speak it: short sentences, natural contractions, no fancy words.",
}
MORAL_EX = {"te": "'అత్యాశ ఎప్పటికైనా నష్టమే తెస్తుంది.', 'నిజాయితీకి ఎప్పుడూ విలువ ఉంటుంది.', 'చేసిన మేలు ఊరికే పోదు.'",
            "hi": "'लालच बुरी बला है।', 'ईमानदारी का फल मीठा होता है।', 'जैसी करनी वैसी भरनी।'",
            "en": "'Greed always costs more than it gives.', 'Honesty is the best policy.', 'As you sow, so shall you reap.'"}
TITLE_EX = {"te": "'తెలివైన అమ్మమ్మ, అత్యాశ వడ్డీ వ్యాపారి', 'మాయా కుండ రహస్యం', 'నిజాయితీ పండ్ల అమ్మాయి'",
            "hi": "'लालची साहूकार और समझदार दादी', 'जादुई मटके का राज़', 'ईमानदार समोसे वाला'",
            "en": "'The Greedy Moneylender and the Clever Grandma', 'The Magic Pot Secret', 'The Honest Samosa Seller'"}

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
           "proud, celebrate, beg, greedy, scratch, greet, sad, show, stop, shrug, count, eat, drink, sell, cook, comfort, "
           "shout, call_out, stomp, look_around, sneak, touch, sprinkle, burn")
EXPRS = "neutral, happy, laugh, sad, cry, angry, surprised, scared, greedy, sly, thinking, proud, worried, ashamed"
OBJECTS = ("coin, coins, coin_bag, money, gold_pot, pot, magic_pot, mango, roti, letter, basket, umbrella, stick, gift, "
           "bowl, plate, flower, key, lamp, samosa, pani_puri, chai, momos, rice_sack, book, necklace, fish, jar")
PROPS = ("weighing_scale, pani_puri_cart, samosa_cart, chai_cart, momos_cart, fruit_cart, vegetable_cart, jalebi_cart, ice_cream_cart, "
         "dosa_cart, idli_cart, vada_pav_cart, well, charpai, magic_pot, pot, sacks, tree, none")
SFX = "none, coins, knock, door, thunder, magic, boing, pop, splash, thud, laugh, ding"

# ======================================================================================== LLM plumbing
GROQ, NV = "https://api.groq.com/openai/v1", "https://integrate.api.nvidia.com/v1"
GEM = "https://generativelanguage.googleapis.com/v1beta/openai"   # Gemini, OpenAI-compatible (GEMINI_API_KEY)
NARA = os.environ.get("NARA_API_URL", "https://router.bynara.id/v1/chat/completions").rsplit("/chat/completions", 1)[0]
# Strongest free models first. GitHub Models (models.github.ai) was retired on 2026-07-30 and is no longer tried.
# Gemini writes far more natural Telugu / Hindi than gpt-oss (run 41869713268, gpt-oss-120b only: invented words,
# "కడవు" for a stick, duplicated lines); the editor role prefers a different model than the writer.
PREFS = {
    # gemini-2.5-pro / 3-pro answer 404 on this (free) key (run 41881160270): the flash models write the natural Telugu
    "gemini": {"write": ["gemini-3-flash", "gemini-flash-latest", "gemini-2.5-flash", "gemini-2.5-pro", "gemini-3-pro"],
               "edit": ["gemini-2.5-flash", "gemini-flash-latest", "gemini-3-flash", "gemini-2.5-pro"]},
    "nvidia": {"write": ["deepseek-v4", "deepseek-v3.2", "deepseek-v3.1", "deepseek-v3", "kimi-k2", "qwen3-235b", "llama-3.1-405b",
                         "mistral-large", "qwen3-next", "gpt-oss-120b", "llama-4-maverick", "llama-3.3-70b"],
               "edit": ["deepseek-v4", "kimi-k2", "deepseek-v3.2", "deepseek-v3.1", "deepseek-v3", "qwen3-235b", "llama-3.1-405b",
                        "mistral-large", "gpt-oss-120b"]},
    "groq": {"write": ["kimi-k2", "gpt-oss-120b", "llama-4-maverick", "qwen3", "llama-3.3-70b"],
             "edit": ["kimi-k2", "gpt-oss-120b", "llama-4-maverick", "qwen3"]},
}
_MODELS = {}
_DEAD = set()   # models that answered 429 / quota errors this run: skip them on later calls


def _get(url, key):
    r = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}", "User-Agent": "bouncebhai-long",
                                             "Accept": "application/json"})
    return json.loads(urllib.request.urlopen(r, timeout=30).read())


def list_models(base, key):
    if base not in _MODELS:
        try:
            if base == GEM:
                _MODELS[base] = [m["id"].split("models/")[-1] for m in _get(base + "/models", key)["data"]]
            else:
                _MODELS[base] = [m["id"] for m in _get(base + "/models", key)["data"]]
        except Exception as e:
            print("model list failed:", base, str(e)[:120], flush=True)
            _MODELS[base] = []
    return _MODELS[base]


SKIP_MODELS = ("deepseek-v4.1-flash", "mistral-large-4")   # timed out on every call (runs 41869713268, 41881160270)


def _pick(ids, prefs, n=6):
    ids = [i for i in ids if not any(sk in i.lower() for sk in SKIP_MODELS)]
    out = []
    for p in prefs:
        out += [i for i in ids if p in i.lower() and i not in out and "embed" not in i and "reward" not in i
                and "guard" not in i and "tts" not in i and "whisper" not in i
                and "vl" not in i.lower().split("/")[-1].split("-")]
    return out[:n]


def candidates(role="write"):
    out = []
    # GitHub Models (models.github.ai) was retired on 2026-07-30: it only answers "OK", so it is not tried any more.
    gk = os.environ.get("GEMINI_API_KEY")
    if gk:
        ids = [i for i in list_models(GEM, gk) if not any(w in i for w in ("tts", "image", "embed", "live", "audio", "lite"))]
        prefs = PREFS["gemini"][role]
        gm = []
        for p_ in prefs:
            m = next((i for i in ids if i == p_), None) or next((i for i in ids if i.startswith(p_)), None)
            if m and m not in gm and ("gemini", m) not in _DEAD:
                gm.append(m)
        out += [("gemini", GEM, gk, m) for m in gm[:3]]
    n = os.environ.get("NVIDIA_API_KEY")
    if n:
        out += [("nvidia", NV, n, i) for i in _pick(list_models(NV, n), PREFS["nvidia"][role], 5)]
    g = os.environ.get("GROQ_API_KEY")
    if g:
        out += [("groq", GROQ, g, i) for i in _pick(list_models(GROQ, g), PREFS["groq"][role], 4)]
    k = os.environ.get("NARA_API_KEY")
    if k:
        for m in [m.strip() for m in os.environ.get("NARA_MODELS", "laguna-s-2.1").split(",") if m.strip()]:
            out.append(("nara", NARA, k, m))
    return [c for c in out if (c[0], c[3]) not in _DEAD]


def report_models():
    """One notice listing the strong models each provider offers right now (for the run log / report)."""
    want = ("deepseek", "qwen3-235b", "405b", "kimi", "mistral-large", "gpt-4", "gpt-oss", "llama-4", "gemini", "grok")
    parts = []
    for name, base, env in (("gemini", GEM, "GEMINI_API_KEY"), ("nvidia", NV, "NVIDIA_API_KEY"), ("groq", GROQ, "GROQ_API_KEY")):
        key = os.environ.get(env)
        if not key:
            parts.append(f"{name}: no key")
            continue
        ids = [i for i in list_models(base, key) if any(w in i.lower() for w in want)]
        parts.append(f"{name}: {', '.join(ids[:14]) or 'none listed'}")
    print("::notice title=models available::" + " | ".join(parts)[:3500], flush=True)
    print("writer order:", [f"{c[0]}:{c[3]}" for c in candidates("write")], flush=True)
    print("editor order:", [f"{c[0]}:{c[3]}" for c in candidates("edit")], flush=True)


def chat(prompt, system, validate, max_tokens=9000, tries_per_model=1, label="", effort="low", rounds=2, role="write"):
    """Try live models in order until one returns JSON that passes validate(obj) -> obj (raise to reject).
    If every model fails (rate limits / timeouts), wait a minute and go round once more."""
    last = None
    for rnd in range(rounds):
        try:
            return _chat_once(prompt, system, validate, max_tokens, tries_per_model, label, effort, role)
        except RuntimeError as e:
            last = e
            if rnd + 1 < rounds:
                print(f"::warning title=llm::{label}: every model failed, retrying in 60 s", flush=True)
                _DEAD.clear()
                time.sleep(60)
    raise last


def _chat_once(prompt, system, validate, max_tokens, tries_per_model, label, effort, role):
    cands = candidates(role)
    if not cands:
        raise SystemExit("No LLM keys (GEMINI_API_KEY / GROQ_API_KEY / NVIDIA_API_KEY / NARA_API_KEY)")
    errs = []
    for prov, base, key, model in cands:
        for attempt in range(tries_per_model + 1):
            cap = {"groq": 8000, "gemini": 30000}.get(prov, max_tokens)
            body = {"model": model, "temperature": 0.8 if role == "write" else 0.4, "max_tokens": min(max_tokens, cap),
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"}}
            if "gpt-oss" in model:
                body["reasoning_effort"] = effort
            if prov == "gemini":   # thinking tokens count against max_tokens: give room, keep thinking light
                body["max_tokens"] = max(16000, min(max_tokens * 2, 30000))
                if "flash" in model:
                    body["reasoning_effort"] = "low"
            if "qwen3" in model and prov != "groq":
                body["chat_template_kwargs"] = {"thinking": False}
            t0 = time.time()
            hdr = {"Content-Type": "application/json", "Authorization": f"Bearer {key}", "User-Agent": "bouncebhai-long"}
            tmo = {"groq": 240, "gemini": 300, "nvidia": 180}.get(prov, 600)
            try:
                req = urllib.request.Request(base + "/chat/completions", data=json.dumps(body).encode(), headers=hdr)
                try:
                    raw = urllib.request.urlopen(req, timeout=tmo).read().decode("utf-8", "replace")
                except urllib.error.HTTPError as e:
                    det = e.read().decode("utf-8", "replace")[:400]
                    if e.code in (400, 422) and "response_format" in det:
                        body.pop("response_format")
                        req = urllib.request.Request(base + "/chat/completions", data=json.dumps(body).encode(), headers=hdr)
                        raw = urllib.request.urlopen(req, timeout=tmo).read().decode("utf-8", "replace")
                    elif e.code == 429:
                        m = re.search(r"try again in (?:(\d+)m)?([\d.]+)(ms|s)", det) or re.search(r"wait (\d+) seconds", det)
                        if m and m.re.pattern.startswith("wait"):
                            wait = float(m.group(1))
                        else:
                            wait = (int(m.group(1) or 0) * 60 + float(m.group(2)) / (1000 if m.group(3) == "ms" else 1)) if m else 20
                        if wait <= 130 and attempt < tries_per_model:
                            print(f"  {label} {prov}:{model} rate-limited, waiting {wait:.0f}s", flush=True)
                            time.sleep(wait + 1)
                            continue
                        _DEAD.add((prov, model))
                        raise RuntimeError(f"HTTP 429 {det[:160]}")
                    else:
                        if e.code in (401, 403, 404):
                            _DEAD.add((prov, model))
                        raise RuntimeError(f"HTTP {e.code} {det[:200]}")
                content = json.loads(raw)["choices"][0]["message"].get("content") or ""
                obj = validate(extract_json(content))
                print(f"  {label} ok: {prov}:{model} in {time.time() - t0:.0f}s", flush=True)
                return obj, f"{prov}:{model}"
            except Exception as e:
                if isinstance(e, (TimeoutError, ConnectionError, urllib.error.URLError)) or "Remote end closed" in str(e) \
                        or "timed out" in str(e):
                    _DEAD.add((prov, model))   # run 41869713268: nvidia mistral-large-4 hung ~4 min on every call
                msg = f"{prov}:{model}: {str(e)[:220]}"
                errs.append(msg)
                print(f"::warning title=llm {label}::{msg[:300]}", flush=True)
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
- LANGUAGE: {guide}
- Human characters only (no talking animals), 3 to 5 named characters with distinct personalities, ages and looks,
  typical of an Indian village or small town (names natural for {lang_name} speakers). One may be a narrator-favourite
  elder. Family-friendly. No religion, gods, temples, prayer, politics, violence or romance.
- STRUCTURE over {n_scenes} scenes (this is what makes viewers stay):
  * ONE clear protagonist (role hero) with a GOAL the viewer cares about in scene 1 (save the family's land, pay for
    the child's school, win the fair, get the stolen pot back...).
  * ONE villain / obstacle (role greedy or villain) who wants the opposite, with a believable, funny-mean personality.
  * 2-3 ESCALATING beats: each attempt by the hero is blocked and the stakes rise (a threat, a deadline, a loss);
    the low point comes around scene 8-9 with real tears.
  * A TWIST that is SET UP earlier (setup_scene: the viewer sees or hears the clue) and PAYS OFF later
    (twist_scene); it can be gently magical (a jadui pot / tree / stick) or clever (the hero's wit).
  * An EMOTIONAL PAYOFF: the villain gets his comeuppance or changes, the hero wins the goal, a hug, happy tears.
  * The MORAL is said NATURALLY by a character in the last scene (the elder or the hero, in their own words) - not
    preached by the narrator.
  Gentle humour in several scenes (a funny habit, a running joke). The last scene shows the happy ending.
- THE STORY IS TOLD THROUGH DIALOGUE AND ACTION, NOT NARRATION. The narrator only opens the story (a warm storyteller
  opener + teaser), gives a very short transition at the start of some scenes ("that night...", "the next morning..."),
  and says the moral at the very end. Everything else is characters talking and doing.
- LOGIC (most important): every scene must follow from the one before (cause -> effect); nobody acts out of their
  role. Give every character ONE plain job ("money-lender", "fruit seller", "farmer", "housewife", "schoolboy") and keep
  props and sets true to it: a food cart belongs only to the person whose job sells that food; a money-lender lends from
  his house or shop with a coin_bag / weighing_scale and never sells at a cart. The twist must be ONE simple idea a child
  can explain in one sentence (no fake-object-inside-fake-object tricks), shown or hinted to the viewer in an earlier
  scene (setup_scene) before it pays off (twist_scene); the ending is the clear result of the characters' choices.
- CAST: every person who speaks or does anything in any scene MUST be one of the characters (with an id) and in that
  scene's cast - never an unnamed or extra person (no "farmer Gopi" who is not in characters). The narrator only
  narrates in the third person; he never speaks for a character.
- RELATIONSHIPS are fixed and match how people address each other: a mother is called amma by her son, a wife is
  never called amma by her husband; give each character a "relation" to the hero and keep it in every scene.
- ONE magic object (if any), always called by the same plain word; title_en, title and every scene must agree on what
  it is (a pot is a pot everywhere, never a stick in one place and a pot in another).
- No two scenes show the same event again; every scene moves the story forward. Write what_happens in English.
- Vary sets and times: use at least 5 different sets and at least one night or rain scene.
- Each scene lists who is on screen (2 to 4 characters, rarely 1, max 4) with positions as fractions 0.1-0.9.
- WORDS: title, thumbnail_text, moral and names use only plain everyday {lang_name} words a village child knows
  (e.g. Telugu "వడ్డీ వ్యాపారి", "మాయా కుండ", "అత్యాశ"), never invented, misspelt or bookish words; give their English
  meaning in title_en and thumbnail_text_en.
- title: in {lang_name} {script_hint}, click-worthy in the niche's style, 3 to 7 words, a natural phrase like {title_ex}. thumbnail_text: ONE punchy exclamation of 2 to 4
  {lang_name} words that makes people click (shock, greed, tears, a secret), ending with "!" or "?", e.g. the {lang_name}
  for "Greed's Price!", "Magic Pot Secret?", "Mother's Tears!" - a phrase, never a comma list, different from the title.
- moral: one short, idiomatic {lang_name} saying people really use, like {moral_ex}. description: 2-3 sentences in
  {lang_name} (no spoilers of the twist).

Allowed values:
- character type: {types}; costume: {costumes}; color: {colors}; build: thin | normal | fat;
  role: hero | greedy | villain | elder | mother | father | grandmother | grandfather | wife | husband | child | vendor |
  friend | merchant | king | minister | other
- set: {sets}; time: day | evening | night; weather: clear | rain;
  mood: happy | calm | funny | sad | tense | magical
- prop (a stage piece standing in the scene, or "none"): {props}; prop_owner: the character id who stands at it
- expression: {exprs}

Return ONLY JSON:
{{"theme": "<one-line English summary of THIS story's theme>",
  "synopsis": "<4-6 English sentences: the whole plot including the twist and ending>",
  "twist": "<one English sentence>", "setup_scene": <index where the twist is planted>, "twist_scene": <index>,
  "title": "...", "title_en": "...", "thumbnail_text": "...", "thumbnail_text_en": "...", "moral": "...", "moral_en": "...", "description": "...",
  "tags": ["8-14 tags mixing {lang_name} and English, e.g. moral story, kahani, cartoon"],
  "thumbnail": {{"character": "<id>", "expression": "greedy|surprised|cry|angry|scared", "object": "<object or none>"}},
  "characters": [{{"id": "ramu", "name": "<name in {lang_name} script>", "name_en": "Ramu", "type": "man", "costume": "lungi",
                  "color": "orange", "build": "thin", "role": "hero", "job": "pani puri seller", "trait": "honest, cheerful",
                  "relation": "<who they are to the hero, e.g. 'the hero himself', 'Ramu's mother', 'Ramu's wife'>"}}],
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
    tt = re.sub(r"\s*[,،;/|]\s*", " ", (o.get("thumbnail_text") or "").strip()).strip()
    o["thumbnail_text"] = tt if tt[-1:] in "!?" else (tt + "!" if tt else tt)
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
    fix_roles(o)
    th = o.get("thumbnail") or {}
    th["character"] = ids.get(th.get("character"), slug(th.get("character")))
    if th["character"] not in ids.values():
        th["character"] = o["characters"][0]["id"]
    o["thumbnail"] = th
    o["tags"] = [str(t)[:40] for t in (o.get("tags") or [])][:15]
    return o


SELL_WORDS = ("sell", "vendor", "wala", "shop", "cart", "hawker", "trader", "merchant", "cook")


def fix_roles(o):
    """Props must belong to someone whose job fits (run 41852353516 put the money-lender behind a fruit cart)."""
    import long_props as LP
    chars = {c["id"]: c for c in o["characters"]}
    for sc in o["scenes"]:
        prop = sc.get("prop")
        kind = LP.cart_kind(prop) if prop else None
        if not kind:
            continue
        food = kind.replace("_", " ")

        def fits(cid):
            job = (chars.get(cid, {}).get("job") or "").lower()
            return food.split()[0] in job or (any(w in job for w in SELL_WORDS) and "lend" not in job)
        cast = [c["id"] for c in sc.get("cast") or []]
        if sc.get("prop_owner") in cast and fits(sc["prop_owner"]):
            continue
        alt = next((c for c in cast if fits(c)), None)
        if alt:
            sc["prop_owner"] = alt
        else:
            print(f"::notice title=logic::dropped {prop} (no seller on stage to own it)", flush=True)
            sc["prop"], sc["prop_owner"] = None, None


REVIEW = """You are the story editor and a native {lang_name} language editor for "Bounce Bhai" animated moral stories.
Check this story outline strictly and fix it:
1. ROLES: each character has one job; props and sets must fit it (a food cart belongs only to the person who sells that
   food; a money-lender lends from his house/shop, never sells at a cart; a child does not run a business alone).
2. TWIST: one simple idea, planted in an earlier scene (setup_scene) and paid off later (twist_scene); no muddled
   double tricks. 3. CAUSE -> EFFECT: every scene follows from the one before; the ending results from the characters'
   choices and shows the moral; no scene repeats an earlier scene's event; anyone who speaks or acts is one of the
   characters and in that scene's cast (add them to cast or rewrite the scene); the magic object is the same thing
   with the same name everywhere; what_happens stays in English. 4. WORDS: title, thumbnail_text and moral must be natural, idiomatic {lang_name} that a
   village child understands - real words only, no invented, misspelt or bookish words. Titles like {title_ex}; morals
   like {moral_ex}. {guide}
OUTLINE: {outline}
Return ONLY JSON with your fixes (omit what is already fine):
{{"issues": ["short English notes of each problem you fixed"], "title": "...", "title_en": "...", "thumbnail_text": "...",
  "thumbnail_text_en": "...", "moral": "...", "moral_en": "...", "synopsis": "...", "twist": "...", "setup_scene": 0,
  "twist_scene": 0, "characters": [{{"id": "<id>", "job": "..."}}],
  "scenes": [{{"index": 0, "what_happens": "...", "set": "...", "prop": "<prop or none>", "prop_owner": "<id>",
              "cast": ["<id>", "..."]}}]}}"""

EDITOR = """You are a native {lang_name} script editor for the animated moral story "{title}" ({synopsis}).
Polish EVERY line below into natural, simple, spoken {lang_name} {script_hint}. {guide}
Fix: wrong, invented, misspelt or bookish words; the wrong word for a thing; unnatural or translated phrasing; wrong
gender / respect endings; and any line that does not make sense here or contradicts the scene plan - rewrite it so it
does. Keep each line's speaker, meaning, order and length (never shorter than 70% of the original). No stage
directions, speaker names, quotes or emoji. The first line of scene 0 is the narrator's warm storyteller opener (like a
grandparent: "once in a village...") ending with a gripping teaser about this story's twist - keep it short and warm.
Make every character line sound like real people talking: short sentences, natural exclamations and fillers, the right
respect words between them (elders, husband/wife, king/minister), each character's own way of speaking. Address
terms must match the relationships in CHARACTERS (relation field): never call a wife "amma" or a mother by her name.
CHARACTERS: {chars}
SCENES: {scenes}
Return ONLY JSON: {{"scenes": [{{"index": <scene index>, "lines": ["<line 0 text>", "<line 1 text>", "..."]}}],
 "flags": ["short English notes: what you fixed, and anything that still does not make sense"]}}"""


def review_outline(o, lang, lang_name, script_hint):
    """Second model pass on the outline: role / prop consistency, a clear twist that is set up earlier, cause -> effect,
    natural title / moral. Returns the patched outline and the issues it fixed."""
    compact = {k: o.get(k) for k in ("title", "title_en", "thumbnail_text", "moral", "moral_en", "synopsis", "twist",
                                     "setup_scene", "twist_scene")}
    compact["characters"] = [{k: c.get(k) for k in ("id", "name_en", "type", "role", "job", "trait")} for c in o["characters"]]
    compact["scenes"] = [{"index": i, "set": sc["set"], "time": sc["time"], "prop": sc.get("prop"),
                          "prop_owner": sc.get("prop_owner"), "cast": [c["id"] for c in sc["cast"]],
                          "what_happens": sc.get("what_happens", "")} for i, sc in enumerate(o["scenes"])]
    prompt = REVIEW.format(lang_name=lang_name, title_ex=TITLE_EX[lang], moral_ex=MORAL_EX[lang], guide=LANG_GUIDE[lang],
                           outline=json.dumps(compact, ensure_ascii=False))
    ids = {c["id"] for c in o["characters"]}

    def val(r):
        if not isinstance(r, dict):
            raise ValueError("not an object")
        for k in ("title", "moral", "thumbnail_text"):
            if r.get(k) and lang != "en" and script_share(r[k], lang) < 0.6:
                raise ValueError(f"{k} not in script")
        return r
    try:
        r, model = chat(prompt, "You are a meticulous story editor. Reply with strictly valid JSON only.", val,
                        max_tokens=4000, label="outline review", role="edit", rounds=1)
    except Exception as e:
        print(f"::warning title=review::outline review failed, keeping the outline: {str(e)[:200]}", flush=True)
        return o, [], None
    for k in ("title", "title_en", "thumbnail_text", "thumbnail_text_en", "moral", "moral_en", "synopsis", "twist",
              "setup_scene", "twist_scene"):
        if r.get(k) not in (None, ""):
            o[k] = r[k]
    for c in r.get("characters") or []:
        if isinstance(c, dict) and c.get("id") in ids and c.get("job"):
            next(x for x in o["characters"] if x["id"] == c["id"])["job"] = c["job"]
    for sp in r.get("scenes") or []:
        try:
            i = int(sp.get("index"))
        except Exception:
            continue
        if not (0 <= i < len(o["scenes"])):
            continue
        sc = o["scenes"][i]
        if sp.get("what_happens"):
            sc["what_happens"] = sp["what_happens"]
        if sp.get("set"):
            sc["set"] = sp["set"]
        if "prop" in sp:
            sc["prop"] = sp.get("prop")
        if sp.get("prop_owner"):
            sc["prop_owner"] = sp["prop_owner"]
        if isinstance(sp.get("cast"), list) and sp["cast"]:
            old = {c["id"]: c for c in sc["cast"]}
            sc["cast"] = [old.get(cid, {"id": cid}) for cid in sp["cast"] if isinstance(cid, str)]
    o = validate_outline(o, lang)
    return o, [str(x)[:200] for x in (r.get("issues") or [])][:12], model


def edit_lines(got, idx, scenes_plan, o, lang, lang_name, script_hint, chars_desc):
    """Native-editor pass over written scenes: rewrites every line into natural spoken language and flags lines that
    do not make sense. Lines the editor breaks (wrong script, too short) keep the writer's text."""
    payload = [{"index": i, "plan": scenes_plan[i].get("what_happens", ""),
                "lines": [{"speaker": l["speaker"], "text": l["text"]} for l in got[i]]} for i in idx]
    prompt = EDITOR.format(lang_name=lang_name, title=o["title"], synopsis=o.get("synopsis") or o.get("theme"),
                           script_hint=script_hint, guide=LANG_GUIDE[lang], chars=chars_desc,
                           scenes=json.dumps(payload, ensure_ascii=False))

    def val(r):
        out = {}
        for k, sc in enumerate(r.get("scenes") or []):
            try:
                i = int(sc.get("index"))
            except Exception:
                i = idx[min(k, len(idx) - 1)]
            if i not in idx:
                continue
            ls = sc.get("lines") or []
            if len(ls) != len(got[i]):
                raise ValueError(f"scene {i}: {len(ls)} lines back for {len(got[i])}")
            out[i] = ls
        if set(out) != set(idx):
            raise ValueError("missing scenes")
        return {"lines": out, "flags": r.get("flags") or []}
    try:
        r, model = chat(prompt, "You are a native-speaker script editor. Reply with strictly valid JSON only.", val,
                        max_tokens=6000, label=f"edit {idx[0]}-{idx[-1]}", role="edit", rounds=1)
    except Exception as e:
        print(f"::warning title=editor::editor pass failed for scenes {idx}: {str(e)[:200]}", flush=True)
        return 0, [], None
    changed = 0
    for i in idx:
        for ln, new in zip(got[i], r["lines"][i]):
            new = re.sub(r"\s+", " ", str(new or "")).strip().strip('"')
            new = re.sub(r"^\s*[\w\u0900-\u097F\u0C00-\u0C7F .]{1,24}\s*:\s*", "", new) if ":" in new[:26] else new
            if len(new) < 0.6 * len(ln["text"]) or (lang != "en" and script_share(new, lang) < 0.75):
                continue
            if new != ln["text"]:
                ln["orig"] = ln["text"]
                ln["text"] = new
                changed += 1
    return changed, [str(x)[:220] for x in r["flags"]][:10], model


OPENER = {"te": "'ఒక ఊరిలో ...' / 'అనగనగా ఒక ఊరిలో ...'", "hi": "'एक गाँव में ...' / 'बहुत समय पहले, एक गाँव में ...'",
          "en": "'Once upon a time, in a small village ...'"}
TRANS_EX = {"te": "'ఆ రాత్రి...', 'మరుసటి రోజు ఉదయం...', 'కొన్ని రోజుల తర్వాత...'",
            "hi": "'उस रात...', 'अगली सुबह...', 'कुछ दिन बाद...'", "en": "'That night...', 'The next morning...'"}
EXCL = {"te": "అయ్యో!, అబ్బా!, ఓహో!, అరె!, ఏంటి?", "hi": "अरे!, हाय राम!, अच्छा!, क्या?, वाह!", "en": "Oh no!, Wow!, What?"}
NARR_MAX_WORDS = 16


def limit_narration(story):
    """Narration is minimal: the opener (scene 0, first line, kept as is), one short transition as a scene's first line,
    and the moral at the end. Any other narrator line is dropped (the dialogue carries the story); an over-long
    transition keeps only its first sentence."""
    dropped = 0
    for i, sc in enumerate(story["scenes"]):
        keep = []
        for k, ln in enumerate(sc["lines"]):
            if ln.get("speaker") != "narrator":
                keep.append(ln)
                continue
            if (i == 0 and k == 0) or (sc.get("moral_card") and k == len(sc["lines"]) - 1):
                keep.append(ln)
                continue
            if k == 0 and not any(l.get("speaker") == "narrator" for l in keep):
                words = ln["text"].split()
                if len(words) > NARR_MAX_WORDS:
                    first = re.split(r"(?<=[.!?।])\s+", ln["text"])[0]
                    if len(first.split()) <= NARR_MAX_WORDS + 4:
                        ln["text"] = first
                    else:
                        dropped += 1
                        continue
                keep.append(ln)
                continue
            dropped += 1
        if len([l for l in keep if l.get("speaker") != "narrator"]) >= 3:
            sc["lines"] = keep
        else:
            dropped -= len(sc["lines"]) - len(keep)
    return dropped


# ======================================================================================== stage 2: dialogue
DIALOGUE = """You are writing the {lang_name} dialogue script of an animated moral story for the YouTube channel "Bounce Bhai".
Write natively in {lang_name} {script_hint} - natural, simple, spoken {lang_name}, with warmth and gentle humour. NOT a
translation. Numbers as words. {guide}
Every line must make sense: it answers or reacts to the line before, fits the speaker's job and character, and moves
the scene's plan forward. Keep names, objects and facts consistent with the plan (the same pot stays the same pot).
Never repeat a line, or an event, from an earlier scene.

STORY: "{title}" - theme: {theme}. Moral: {moral_en}
SYNOPSIS: {synopsis}
CHARACTERS (speaker ids): {chars}
FULL SCENE PLAN (for context): {plan}
{previous}
Now write scenes {first} to {last} only. LENGTH MATTERS: every scene needs {lines_lo}-{lines_hi} lines and AT LEAST
{chars_target} {lang_name} characters of spoken text in total ({secs} seconds of audio). Mostly lively DIALOGUE between
characters with back-and-forth reactions, small jokes, feelings and details of village life; each line 1-3 short
sentences, the way people really talk (interruptions, exclamations like {excl}, questions, calling each other by name or
relation).
NARRATION RULES (strict): the story is carried by DIALOGUE and ACTION. The narrator may speak AT MOST ONE line per
scene, ONLY as that scene's FIRST line, and only for a short warm transition of at most 12 words, like a grandparent
telling a bedtime story ({trans_ex}). Never let the narrator explain feelings, motives or what the characters are about
to say - show it in their words instead. Most scenes need no narrator line at all.{hook}
Each line object:
- speaker: "narrator" or a character id from CHARACTERS - nobody else may speak (no extra villagers); the narrator
  only describes in the third person and never says a character's words or "I / me / my"
- text: the spoken words in {lang_name} only (no stage directions, no speaker names, no quotes, no emoji)
- emotion: one of {exprs}
- action (REQUIRED: what the speaker visibly DOES while saying it - it must match the words, e.g. a seller calling
  customers = call_out, handing money = give with object, scolding = stomp or point; for narrator lines it is what the
  described character does, and "actor" names that character): one of {actions}
- target (optional): character id the line is said to / given to / pointed at
- object (optional, for give/take/show/count/eat): one of {objects}
- to (optional, for walk/run): 0.1-0.9 where to walk
- sfx (optional): one of {sfx}
- reactions (optional): {{"<id>": "<emotion>"}} how listeners react
Use movement (enter/walk/exit), giving objects, pointing, crying, laughing, anger, surprise and humour naturally.

Return ONLY JSON: {{"scenes": [{{"index": {first}, "lines": [{{"speaker": "...", "text": "...", "emotion": "...", "action": "..."}}]}}]}}"""

EXPAND = """These scenes of the {lang_name} animated moral story "{title}" are TOO SHORT for the video. Rewrite each one
in {lang_name} {script_hint} with the same events, order and ending, but richer: more back-and-forth dialogue, reactions,
gentle humour, feelings and small village-life details, so each scene has {lines_lo}-{lines_hi} lines and AT LEAST
{chars_target} {lang_name} characters of spoken text. Keep the same JSON line format (speaker, text, emotion, action,
target, object, to, sfx, reactions) and speaker ids. CHARACTERS: {chars}
SCENES: {scenes}
Return ONLY JSON: {{"scenes": [{{"index": <same index>, "lines": [...]}}]}}"""

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
                raw = sp
                sp = next((k2 for k2 in ids if sp and sp != "narrator" and (sp in k2 or k2 in sp)), "narrator")
                if raw and raw != "narrator" and sp == "narrator":
                    # run 41869713268: an uncast "farmer Gopi" got his lines spoken by the narrator in the first person
                    raise ValueError(f"scene {i}: speaker '{raw}' is not a character (use only {sorted(ids)})")
            text = fix_words(text, lang)
            if sp == "narrator" and FIRST_PERSON.get(lang) and FIRST_PERSON[lang].search(text) and not re.search(r"[\"“”]", text):
                raise ValueError(f"scene {i}: narrator speaks in the first person: {text[:50]}")
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


FIRST_PERSON = {"te": re.compile(r"(?:^|[\s,.!?])(నేను|నాకు|నన్ను|నా|నాది|మేము|మాకు)(?=[\s,.!?]|$)"),
                "hi": re.compile(r"(?:^|[\s,.!?])(मैं|मुझे|मेरा|मेरी|मेरे|हम|हमें)(?=[\s,.!?।]|$)"),
                "en": re.compile(r"\b(I|me|my|I'm|I'll)\b")}


def fix_words(text, lang):
    """Deterministic fixes for errors the models keep making."""
    if lang == "te":
        text = re.sub(r"దయా(?=[\s,.!?]|$)", "దయ", text)          # 'దయా కలిగిన' / 'దయా బలం' -> దయ
        text = text.replace("దయ కలిగినవారికి", "దయ ఉన్నవాళ్లకి").replace("దయ కలిగినవాడివి", "దయ ఉన్నవాడివి")
    return text


def _norm(t):
    return re.sub(r"[\s,.!?।'\"“”‘’-]+", " ", t).strip()


def dedupe_lines(story):
    """Drop a line that repeats (nearly) word for word any earlier line: run 41869713268 copied whole exchanges from
    scene 5 into scene 6 and narrator lines from scene 8 into scenes 9 and 11. Keeps each scene's first line and the moral."""
    import difflib
    seen, dropped = [], 0
    for sc in story["scenes"]:
        keep = []
        for li, ln in enumerate(sc["lines"]):
            n = _norm(ln["text"])
            dup = len(n) > 12 and any(n == s or (abs(len(n) - len(s)) < 0.25 * len(n) and
                                                 difflib.SequenceMatcher(None, n, s).ratio() > 0.85) for s in seen)
            if dup and li > 0 and not (sc.get("moral_card") and li == len(sc["lines"]) - 1):
                dropped += 1
                continue
            seen.append(n)
            keep.append(ln)
        sc["lines"] = keep
    return dropped


def estimate_secs(story, lang):
    # measured on run 41845024685 (te): 12.5 chars/s spoken + gaps; this slightly over-estimates (14.3 est vs 13.4 real)
    est = sum(len(l["text"]) for s in story["scenes"] for l in s["lines"]) / CHARS_PER_SEC[lang]
    return est + sum(len(s["lines"]) for s in story["scenes"]) * 0.45 + len(story["scenes"]) * 1.6 + 8


FILLER_ACTIONS = {"laugh", "surprised", "shrug", "scratch", "think", "nod", "wave", "greet", "hips", "proud", "celebrate"}


def trim_to_length(story, lang, max_min):
    """Hard cap on length: drop filler lines (reactions, short asides) from the middle of the longest scenes.
    Never touches a scene's first 2 or last 3 lines, the hook, gives/takes (objects) or the moral."""
    dropped = 0
    while estimate_secs(story, lang) > max_min * 60:
        best = None
        for si, sc in enumerate(story["scenes"]):
            ls = sc["lines"]
            if len(ls) <= 7:
                continue
            for li in range(2, len(ls) - 3):
                l = ls[li]
                if l.get("object") or l.get("to") or l.get("action") in ("give", "take", "show", "enter", "exit", "walk", "run"):
                    continue
                score = (len(ls), l.get("action") in FILLER_ACTIONS, -len(l["text"]))
                if best is None or score > best[0]:
                    best = (score, si, li)
        if not best:
            break
        del story["scenes"][best[1]]["lines"][best[2]]
        dropped += 1
    return dropped


def real_minutes(story, lang):
    return estimate_secs(story, lang) * REAL_RATIO / 60


def main(out, lang):
    if lang not in LANG_NAME:
        raise SystemExit("lang must be te, hi or en")
    rng = random.Random()
    topics = load_topics()
    seed = os.environ.get("BB_LONG_SEED_THEME") or pick_seed(lang, topics, rng)
    used = "; ".join(t.get("theme", "") for t in topics[-40:]) or "none yet"
    lang_name = LANG_NAME[lang]
    script_hint = {"te": "(Telugu script)", "hi": "(Devanagari script)", "en": "(simple Indian English)"}[lang]
    n_scenes = 13 if TARGET_MIN <= 9.6 else 15
    sysmsg = ("You are an award-winning Indian children's and family story writer and a native " + lang_name +
              " speaker. Reply with strictly valid JSON only.")
    print(f"long story: lang={lang} seed='{seed}'", flush=True)
    report_models()
    stages = {}
    o, stages["outline"] = chat(OUTLINE.format(minutes=TARGET_MIN, lang_name=lang_name, seed=seed, used=used, n_scenes=n_scenes,
                                               script_hint=script_hint, types=TYPES, costumes=COSTUMES, colors=COLORS, sets=SETS,
                                               props=PROPS, exprs=EXPRS, guide=LANG_GUIDE[lang], title_ex=TITLE_EX[lang],
                                               moral_ex=MORAL_EX[lang]),
                                sysmsg, lambda x: validate_outline(x, lang), max_tokens=7000, tries_per_model=1, label="outline")
    o, issues, stages["review"] = review_outline(o, lang, lang_name, script_hint)
    if issues:
        print("::notice title=outline review::" + " | ".join(issues)[:900], flush=True)
    ids = {c["id"]: c for c in o["characters"]}
    scenes = o["scenes"][:15]
    n = len(scenes)
    secs_total = TARGET_MIN * 60 - 8 - n * 1.6
    per_scene = secs_total / n
    speech_secs = per_scene - 4.5     # ~9 line gaps per scene
    chars_target = int(speech_secs * CHARS_PER_SEC[lang])
    lines_lo, lines_hi = 8, 11   # run 41845024685: 10-14 lines gave 13.4 min for a 9 min target
    plan = json.dumps([{"index": i, "set": s["set"], "time": s["time"], "on_screen": [c["id"] for c in s["cast"]],
                        "prop": s.get("prop"), "prop_owner": s.get("prop_owner"), "what_happens": s.get("what_happens", "")}
                       for i, s in enumerate(scenes)], ensure_ascii=False)
    chars_desc = json.dumps([{"id": c["id"], "name": c["name"], "type": c["type"], "role": c.get("role"), "job": c.get("job"),
                              "trait": c.get("trait"), "relation": c.get("relation")} for c in o["characters"]], ensure_ascii=False)
    batch = 3
    written = {}
    models = [stages["outline"]] + ([stages["review"]] if stages["review"] else [])
    stages["dialogue"], stages["editor"] = [], []
    flags = []
    prev_tail = ""
    edited = 0
    for b0 in range(0, n, batch):
        rng_ = list(range(b0, min(n, b0 + batch)))
        hook = ""
        if b0 == 0:
            hook = ("\nSCENE 0 OPENS LIKE A STORYTELLER: its first line is the narrator's warm opener in the classic style "
                    f"({OPENER[lang]}) that introduces the hero and their world in one or two short sentences and ends with a "
                    "gripping teaser about THIS story's twist (e.g. 'In a village lived Ramu, a poor potter with one clay pot. "
                    "Who knew that pot would make the greediest man in the village beg?'), under 15 seconds. Then the "
                    "characters take over with dialogue straight away.")
        if rng_[-1] == n - 1:
            hook += ("\nThe LAST scene ends with the happy ending and the characters' feelings, and ONE character (the elder "
                     "or the hero) says the moral naturally in their own words to the others (not as a lecture, one or two"
                     " sentences). Do NOT add a narrator moral line, it is added separately.")
        prompt = DIALOGUE.format(lang_name=lang_name, script_hint=script_hint, title=o["title"], theme=o.get("theme"),
                                 moral_en=o.get("moral_en") or o["moral"], synopsis=o.get("synopsis") or o.get("theme"),
                                 chars=chars_desc, plan=plan, guide=LANG_GUIDE[lang],
                                 previous=("The previous scene ended with: " + prev_tail) if prev_tail else "",
                                 first=rng_[0], last=rng_[-1], lines_lo=lines_lo, lines_hi=lines_hi,
                                 chars_target=chars_target, secs=int(per_scene), hook=hook, exprs=EXPRS,
                                 excl=EXCL[lang], trans_ex=TRANS_EX[lang],
                                 actions=ACTIONS, objects=OBJECTS, sfx=SFX)
        got, m = chat(prompt, sysmsg, lambda x, r=rng_: validate_dialogue(x, lang, ids, r), max_tokens=12000,
                      tries_per_model=1, label=f"scenes {rng_[0]}-{rng_[-1]}", effort="low")
        models.append(m)
        stages["dialogue"].append(m)
        short = [i for i in rng_ if sum(len(l["text"]) for l in got[i]) < 0.7 * chars_target]
        if short:   # one expansion pass for scenes that came out too short
            cur = {i: got[i] for i in short}
            ep = EXPAND.format(lang_name=lang_name, script_hint=script_hint, title=o["title"], chars=chars_desc,
                               scenes=json.dumps([{"index": i, "what_happens": scenes[i].get("what_happens", ""),
                                                   "chars_now": sum(len(l["text"]) for l in cur[i]), "lines": cur[i]}
                                                  for i in short], ensure_ascii=False),
                               chars_target=chars_target, lines_lo=lines_lo, lines_hi=lines_hi + 2)
            try:
                more, m2 = chat(ep, sysmsg, lambda x, r=short: validate_dialogue(x, lang, ids, r, min_lines=6),
                                max_tokens=12000, tries_per_model=1, label=f"expand {short}", effort="low", rounds=1)
                for i in short:
                    if sum(len(l["text"]) for l in more[i]) > sum(len(l["text"]) for l in got[i]):
                        got[i] = more[i]
                models.append(m2)
            except Exception as e:
                print(f"::warning title=expand::could not lengthen scenes {short}: {str(e)[:200]}", flush=True)
        # native editor: a second model rewrites every line into natural spoken language and flags nonsense
        ch, fl, em = edit_lines(got, rng_, scenes, o, lang, lang_name, script_hint, chars_desc)
        edited += ch
        flags += fl
        if em:
            models.append(em)
            stages["editor"].append(em)
        for i in rng_:
            print(f"  scene {i}: {len(got[i])} lines, {sum(len(l['text']) for l in got[i])} chars (target {chars_target})", flush=True)
        written.update(got)
        last = got[rng_[-1]]
        prev_tail = json.dumps([{"speaker": l["speaker"], "text": l["text"]} for l in last[-3:]], ensure_ascii=False)
    print(f"::notice title=editor::{edited} lines rewritten by the native editor; flags: {' | '.join(flags)[:700]}", flush=True)
    # ---- assemble
    story = {"lang": lang, "format": "long_story", "seed": rng.randint(1, 10 ** 6), "theme": o.get("theme"),
             "seed_theme": seed, "title": o["title"].strip(), "title_en": (o.get("title_en") or "").strip(),
             "thumbnail_text": o["thumbnail_text"].strip(), "thumbnail_text_en": (o.get("thumbnail_text_en") or "").strip(),
             "moral": o["moral"].strip(), "moral_en": o.get("moral_en", ""), "description": o.get("description", ""),
             "synopsis": o.get("synopsis", ""), "twist": o.get("twist", ""),
             "tags": o.get("tags", []), "thumbnail": o["thumbnail"], "characters": o["characters"], "models": models,
             "models_by_stage": stages, "review_issues": issues, "editor_flags": flags, "scenes": []}
    for i, sc in enumerate(scenes):
        s = {k: sc.get(k) for k in ("set", "time", "weather", "mood", "prop", "prop_owner", "cast", "chapter")}
        s["summary"] = sc.get("what_happens", "")
        s["lines"] = written[i]
        story["scenes"].append(s)
    # everyone who speaks or acts in a scene must be in that scene's cast (else they pop in from nowhere)
    added = []
    for i, s in enumerate(story["scenes"]):
        cast = s.get("cast") or []
        have = {(c.get("id") if isinstance(c, dict) else c) for c in cast}
        for ln in s["lines"]:
            for cid in (ln.get("speaker"), ln.get("actor"), ln.get("target")):
                if cid and cid != "narrator" and cid in ids and cid not in have:
                    cast.append({"id": cid, "enter": True})
                    have.add(cid)
                    added.append(f"{cid}@{i}")
        s["cast"] = cast
    if added:
        print(f"::notice title=cast::speakers added to their scene cast (they walk in): {', '.join(added)[:500]}", flush=True)
    story["scenes"][-1]["lines"].append({"speaker": "narrator", "text": story["moral"], "emotion": "happy", "action": "talk"})
    story["scenes"][-1]["moral_card"] = True
    for sc in story["scenes"]:
        for ln in sc["lines"]:
            ln["text"] = fix_words(ln["text"], lang)
    nd = limit_narration(story)
    print(f"::notice title=narration::{nd} extra narrator lines dropped; narrator lines now "
          f"{sum(1 for sc in story['scenes'] for l in sc['lines'] if l.get('speaker') == 'narrator')} of "
          f"{sum(len(sc['lines']) for sc in story['scenes'])}", flush=True)
    dd = dedupe_lines(story)
    if dd:
        print(f"::notice title=dedupe::dropped {dd} repeated lines", flush=True)
    for k in ("title", "thumbnail_text", "moral"):
        story[k] = fix_words(story[k], lang)
    # ---- length window 9-10 min: lengthen the shortest scenes once if short, drop filler lines if long
    if real_minutes(story, lang) < MIN_REAL:
        short = sorted(range(n), key=lambda i: sum(len(l["text"]) for l in story["scenes"][i]["lines"]))[:3]
        short = sorted(i for i in short if not story["scenes"][i].get("moral_card"))
        ep = EXPAND.format(lang_name=lang_name, script_hint=script_hint, title=o["title"], chars=chars_desc,
                           scenes=json.dumps([{"index": i, "what_happens": scenes[i].get("what_happens", ""),
                                               "lines": story["scenes"][i]["lines"]} for i in short], ensure_ascii=False),
                           chars_target=int(chars_target * 1.25), lines_lo=lines_lo + 1, lines_hi=lines_hi + 3)
        try:
            more, m3 = chat(ep, sysmsg, lambda x, r=short: validate_dialogue(x, lang, ids, r, min_lines=6),
                            max_tokens=12000, tries_per_model=1, label=f"lengthen {short}", rounds=1)
            ch, fl, em = edit_lines(more, short, scenes, o, lang, lang_name, script_hint, chars_desc)
            for i in short:
                if sum(len(l["text"]) for l in more[i]) > sum(len(l["text"]) for l in story["scenes"][i]["lines"]):
                    story["scenes"][i]["lines"] = more[i]
            models.append(m3)
            print(f"::notice title=length::lengthened scenes {short}: now ~{real_minutes(story, lang):.1f} min", flush=True)
        except Exception as e:
            print(f"::warning title=length::could not lengthen: {str(e)[:200]}", flush=True)
    trimmed = trim_to_length(story, lang, MAX_REAL / REAL_RATIO)
    if trimmed:
        print(f"::notice title=trim::dropped {trimmed} filler lines to stay under {MAX_REAL} min", flush=True)
    story["estimated_minutes"] = round(real_minutes(story, lang), 2)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    json.dump(story, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"::notice title=story::{story['title']} ({story['title_en']}) | moral: {story['moral']} ({story['moral_en']}) | "
          f"{len(story['scenes'])} scenes, {sum(len(s['lines']) for s in story['scenes'])} lines, ~{story['estimated_minutes']} min | "
          f"outline {stages['outline']}, review {stages['review']}, dialogue {sorted(set(stages['dialogue']))}, "
          f"editor {sorted(set(stages['editor']))}", flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "te")
