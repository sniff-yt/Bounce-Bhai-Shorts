#!/usr/bin/env python3
"""Gemini TTS voice acting for the long-form stories (Telugu / Hindi / English).

Each character gets one distinct prebuilt Gemini voice chosen by age, gender and role (old man, old woman, young
woman, child, king, villain, hero), and every line is performed with a natural-language style prompt built from the
character, the line's emotion and action ("say angrily", "whisper fearfully", "like an excited six-year-old"). The
narrator is a warm grandparent storyteller (slower, with pauses). Children use a youthful voice raised with a formant
shift (asetrate) so they sound like children.

Quality gate per line: Groq Whisper (whisper-large-v3) transcribes the generated audio; when the words do not match
the script (the model added / skipped words or read the style prompt aloud) the line is retried with a plainer prompt
and then another TTS model. Whisper's word timestamps on the real audio drive lip-sync and subtitles (Gemini TTS has
no word boundaries): the script words are aligned to the recognised words. Lines that still fail go to edge-tts.

Rate limits: a small worker pool, retryDelay-aware backoff on 429, a model whose daily quota is gone is skipped for
the rest of the run, and every synthesised line is cached on disk (keyed by model, voice, prompt and text).
"""
import base64, difflib, hashlib, json, os, re, threading, time, wave

import numpy as np
import requests

BASE = "https://generativelanguage.googleapis.com/v1beta"
# probe (run 41990024145): with the director's-notes / transcript prompt all three speak only the transcript (Whisper
# match 0.86-1.0 on Telugu); 2.5-pro-preview-tts has no quota on this key. Each model has its own per-minute quota,
# so characters are spread over the models (one character stays on one model = one consistent voice).
MODELS = [m for m in os.environ.get("BB_TTS_MODELS", "gemini-3.1-flash-tts-preview,gemini-2.5-flash-preview-tts,"
                                    "gemini-3.8-flash-tts,gemini-3.8-flash-lite-tts").split(",") if m]
SR_G = 24000
LANG_NAME = {"te": "Telugu", "hi": "Hindi", "en": "Indian English"}

# prebuilt voices (Gemini TTS): name -> (gender, character)
VOICE_POOL = {
    "narrator_f": ["Sulafat", "Vindemiatrix", "Gacrux"],
    "narrator_m": ["Sadaltager", "Algenib"],
    "king": ["Alnilam", "Orus", "Iapetus"],
    "villain": ["Algenib", "Rasalgethi", "Enceladus", "Fenrir"],
    "hero_m": ["Achird", "Puck", "Umbriel", "Zubenelgenubi"],
    "man": ["Iapetus", "Orus", "Charon", "Umbriel", "Schedar", "Sadachbia"],
    "oldman": ["Sadaltager", "Charon", "Schedar", "Algenib"],
    "woman": ["Kore", "Aoede", "Despina", "Erinome", "Callirrhoe", "Autonoe"],
    "villain_f": ["Pulcherrima", "Kore"],
    "oldwoman": ["Gacrux", "Vindemiatrix", "Achernar"],
    "girl": ["Leda", "Laomedeia", "Zephyr"],
    "boy": ["Laomedeia", "Leda", "Zephyr"],
}
# formant / pitch factor (asetrate): >1 younger / smaller
# probe: Leda already sounds like a child (median 370 Hz, Whisper match 1.0), so kids get only a small lift; the
# F0 gate below raises it further when a child voice comes out too low
FORMANT = {"girl": 1.05, "boy": 1.04, "oldman": 0.97, "oldwoman": 0.98}
F0_MIN_KID = 265.0      # a child's median pitch must reach this (Hz), else the formant is raised

EMO_STYLE = {
    "angry": "angrily, with real heat in the voice", "cry": "while crying, voice breaking with sobs",
    "sad": "sadly, softly, with a heavy heart", "happy": "happily, with a warm smile in the voice",
    "laugh": "laughing while saying it", "surprised": "with sudden surprise, eyes wide", "shocked": "in total shock",
    "scared": "fearfully, in a frightened whisper", "worried": "anxiously, worried", "greedy": "greedily, slyly, savouring every word",
    "sly": "slyly, with a sneaky little chuckle", "proud": "proudly and grandly, full of himself",
    "thinking": "thoughtfully, slowly, wondering", "ashamed": "quietly, ashamed, almost mumbling",
    "excited": "excitedly, fast and bubbly", "pleading": "pleading desperately", "neutral": "naturally, like a real conversation",
}
ACT_STYLE = {"shout": "shouting", "call": "calling out loudly to someone far away", "call_out": "calling out loudly like a street seller",
             "whisper": "whispering", "beg": "begging", "scold": "scolding sharply", "stomp": "furiously",
             "sneak": "in a hushed, secretive whisper", "comfort": "gently comforting", "celebrate": "joyfully, celebrating"}


def _type_key(ch):
    t = ch.get("type", "man")
    role = (ch.get("role") or "").lower()
    job = ((ch.get("job") or "") + " " + (ch.get("costume") or "")).lower()
    if t in ("boy", "girl", "oldman", "oldwoman"):
        return t
    female = t == "woman"
    if role in ("greedy", "villain") or "thief" in job or "lender" in job:
        return "villain_f" if female else "villain"
    if not female and any(k in job for k in ("king", "raja", "royal", "maharaja")):
        return "king"
    if female:
        return "woman"
    return "hero_m" if role == "hero" else "man"


def persona(ch, lang):
    t = ch.get("type", "man")
    who = {"man": "a man in his thirties", "woman": "a young woman in her late twenties", "oldman": "an old man of about seventy",
           "oldwoman": "an old grandmother of about seventy", "boy": "a small boy of about seven", "girl": "a little girl of about six"}.get(t, "a man")
    job = ch.get("job") or ""
    trait = ch.get("trait") or ""
    name = ch.get("name_en") or ch.get("name") or ch["id"]
    bits = [f"{name}, {who}"] + ([job] if job else []) + ([trait] if trait else [])
    kid = " Speak exactly like a real young child: high, bright, a little breathless." if t in ("boy", "girl") else ""
    return ", ".join(bits) + "." + kid


def assign(story):
    """voice per character + narrator: {id: {"gemini": name, "formant": f, "kind": key, "persona": str}}"""
    lang = story.get("lang", "te")
    used = set()
    out = {}
    nk = "narrator_f" if story.get("narrator_gender", "f") == "f" else "narrator_m"
    order = sorted(story["characters"], key=lambda c: (0 if c.get("role") in ("hero", "greedy", "villain") else 1))
    for ch in order:
        k = _type_key(ch)
        pool = VOICE_POOL[k] + VOICE_POOL["woman" if ch.get("type") in ("woman", "girl", "oldwoman") else "man"]
        v = next((x for x in pool if x not in used), pool[0])
        used.add(v)
        out[ch["id"]] = {"gemini": v, "formant": FORMANT.get(ch.get("type"), 1.0), "kind": k, "persona": persona(ch, lang)}
    nv = next((x for x in VOICE_POOL[nk] if x not in used), VOICE_POOL[nk][0])
    out["narrator"] = {"gemini": nv, "formant": 1.0, "kind": "narrator",
                       "persona": "a warm, loving grandmother telling a bedtime story to her grandchildren" if nk == "narrator_f"
                       else "a warm, loving grandfather telling a bedtime story to his grandchildren"}
    return out


def style_prompt(v, ln, lang, plain=False):
    """Director's notes for one line (kept out of the transcript so the model never reads them aloud)."""
    L = LANG_NAME.get(lang, "Telugu")
    if v["kind"] == "narrator":
        if plain:
            return f"A warm storyteller, slowly, with gentle pauses. {L}."
        return (f"You are {v['persona']}. Slow, warm, expressive storytelling with gentle pauses at the commas and "
                f"a little wonder in the voice. Natural spoken {L}.")
    emo = (ln.get("emotion") or "neutral").lower()
    st = EMO_STYLE.get(emo, EMO_STYLE["neutral"])
    act = (ln.get("action") or "").lower()
    if act in ACT_STYLE:
        st = ACT_STYLE[act] + ", " + st
    if plain:
        return f"Say it {st}. {L}."
    return (f"Voice acting for an Indian cartoon. You are {v['persona']} Say the line {st}. Natural spoken {L} with "
            f"real emotion and natural pacing, never robotic.")


def group_notes(v, lns, lang):
    """Director's notes for several lines of ONE character performed in one take (one request instead of N)."""
    L = LANG_NAME.get(lang, "Telugu")
    dirs = []
    for k, ln in enumerate(lns):
        emo = (ln.get("emotion") or "neutral").lower()
        st = EMO_STYLE.get(emo, EMO_STYLE["neutral"])
        act = (ln.get("action") or "").lower()
        if act in ACT_STYLE:
            st = ACT_STYLE[act] + ", " + st
        dirs.append(f"line {k + 1}: {st}")
    who = (f"You are {v['persona']}. Storytelling voice: slow, warm, gentle pauses."
           if v["kind"] == "narrator" else f"Voice acting for an Indian cartoon. You are {v['persona']}")
    return (f"{who} The transcript has {len(lns)} separate lines from one scene. Perform each line with its own feeling "
            f"({'; '.join(dirs)}), in natural spoken {L} with real emotion, never robotic. Leave a clear silent pause of "
            f"about one second between the lines. Do not say the line numbers or these notes.")


def split_take(lines_text, ww, a, sr):
    """Cut one take of several lines into per-line pieces at the quietest point between them.
    Returns [(s0, s1, words_rel_to_s0, sim)] in samples, or None if the lines cannot be found."""
    full = " ".join(lines_text)
    dur = len(a) / sr
    e = env100(a, sr)
    words = align(full, ww, dur, e)
    if not words:
        return None
    n_tok = [len(t.split()) for t in lines_text]
    spans, k = [], 0
    for n in n_tok:
        seg = words[k:k + n]
        if not seg:
            return None
        spans.append((seg[0][0], seg[-1][1], seg))
        k += n
    cuts = [0.0]
    for i in range(len(spans) - 1):
        a0, b0 = spans[i][1], spans[i + 1][0]
        if b0 < a0 + 0.08:
            a0, b0 = min(a0, b0) - 0.25, max(a0, b0) + 0.25
        i0, i1 = max(0, int(a0 * 100)), min(len(e) - 1, int(b0 * 100) + 1)
        if i1 <= i0:
            return None
        w = e[i0:i1 + 1]
        thr = w.min() + 0.12 * (w.max() - w.min() + 1e-9)
        best, run0 = (0, i0), None
        for jj, val in enumerate(list(w) + [1e9]):
            if val <= thr and run0 is None:
                run0 = jj
            elif val > thr and run0 is not None:
                if jj - run0 > best[0]:
                    best = (jj - run0, i0 + (run0 + jj) // 2)
                run0 = None
        cuts.append(best[1] / 100.0)
    cuts.append(dur)
    out = []
    for i, (t0, t1, seg) in enumerate(spans):
        c0, c1 = cuts[i], cuts[i + 1]
        heard = " ".join(w[2] for w in ww if c0 <= (w[0] + w[1]) / 2 < c1)
        sim = similarity(heard, lines_text[i]) if ww else 0.7
        rel = [[max(0.0, w0 - c0), max(0.0, w1 - c0), w] for w0, w1, w in seg]
        out.append((int(c0 * sr), int(c1 * sr), rel, sim))
    return out


def make_prompt(notes, text):
    return f"# DIRECTOR'S NOTES (do not read aloud)\n{notes}\n\n# TRANSCRIPT (say exactly this, nothing else)\n{text}"


class Gemini:
    def __init__(self, key, cache_dir, log=print):
        self.key = key
        self.cache = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self.dead = set()
        self.lock = threading.Lock()
        self.next_ok = {}
        self.calls = {}
        self.log = log

    def synth(self, model, voice, prompt, text):
        """PCM int16 bytes at 24 kHz, or raises."""
        h = hashlib.sha1(json.dumps([model, voice, prompt, text], ensure_ascii=False).encode()).hexdigest()[:20]
        cp = os.path.join(self.cache, h + ".pcm")
        if os.path.exists(cp) and os.path.getsize(cp) > 4000:
            return open(cp, "rb").read()
        body = {"contents": [{"parts": [{"text": make_prompt(prompt, text)}]}],
                "generationConfig": {"responseModalities": ["AUDIO"],
                                     "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}}}
        for attempt in range(6):
            if model in self.dead:
                raise RuntimeError(f"{model} dead")
            with self.lock:
                wait = self.next_ok.get(model, 0) - time.time()
            if wait > 0:
                time.sleep(min(wait, 65))
            try:
                r = requests.post(f"{BASE}/models/{model}:generateContent?key={self.key}", json=body, timeout=150)
            except Exception as e:
                time.sleep(4 + attempt * 4)
                last = f"{type(e).__name__}"
                continue
            self.calls[model] = self.calls.get(model, 0) + 1
            if r.status_code == 200:
                try:
                    part = r.json()["candidates"][0]["content"]["parts"][0]["inlineData"]
                    pcm = base64.b64decode(part["data"])
                except Exception:
                    last = "no audio in response: " + r.text[:160]
                    if attempt >= 1:
                        raise RuntimeError(last)
                    time.sleep(2)
                    continue
                if len(pcm) < 4000:
                    last = "tiny audio"
                    continue
                open(cp, "wb").write(pcm)
                return pcm
            last = f"{r.status_code} {r.text[:200]}"
            if r.status_code == 429:
                txt = r.text
                if "PerDay" in txt or "per_day" in txt.lower() or "daily" in txt.lower():
                    self.dead.add(model)
                    self.log(f"::warning title=gemini tts::{model} daily quota exhausted; switching model")
                    raise RuntimeError(f"{model} quota")
                m = re.search(r'"retryDelay":\s*"(\d+)', txt)
                d = float(m.group(1)) + 1 if m else 15 + attempt * 10
                with self.lock:
                    self.next_ok[model] = time.time() + d
                continue
            if r.status_code in (400, 403, 404):
                if r.status_code == 404 or "not found" in r.text.lower() or "not supported" in r.text.lower():
                    self.dead.add(model)
                raise RuntimeError(last)
            time.sleep(3 + attempt * 5)
        raise RuntimeError(last)


def whisper_words(path, lang, key):
    """(text, [[t0, t1, word], ...]) from Groq whisper-large-v3 on the generated audio."""
    for attempt in range(4):
        try:
            r = requests.post("https://api.groq.com/openai/v1/audio/transcriptions", headers={"Authorization": f"Bearer {key}"},
                              files={"file": (os.path.basename(path), open(path, "rb"), "audio/wav")},
                              data={"model": "whisper-large-v3", "language": lang if lang != "en" else "en",
                                    "response_format": "verbose_json", "timestamp_granularities[]": "word", "temperature": "0"},
                              timeout=90)
            if r.status_code == 429:
                m = re.search(r"try again in ([\d.]+)s", r.text)
                time.sleep(float(m.group(1)) + 1 if m else 10 + attempt * 10)
                continue
            r.raise_for_status()
            j = r.json()
            return j.get("text", ""), [[w["start"], w["end"], w["word"]] for w in (j.get("words") or [])]
        except Exception:
            time.sleep(3 + attempt * 4)
    return None, []


def _norm(s):
    return re.sub(r"[\W_]+", "", (s or "").lower())


def similarity(a, b):
    return difflib.SequenceMatcher(None, _norm(a), _norm(b)).ratio()


def align(script, wwords, dur, env=None):
    """Script tokens -> [[t0, t1, token]] using the recognised words' timings (character-level alignment), with
    unmatched tokens interpolated inside the voiced region."""
    toks = script.split()
    if not toks:
        return []
    if wwords:
        sc, sidx = "", []
        for k, t in enumerate(toks):
            n = _norm(t)
            sc += n; sidx += [k] * len(n)
        wc, widx = "", []
        for k, w in enumerate(wwords):
            n = _norm(w[2])
            wc += n; widx += [k] * len(n)
        times = [[None, None] for _ in toks]
        sm = difflib.SequenceMatcher(None, sc, wc, autojunk=False)
        for a, b, n in sm.get_matching_blocks():
            for j in range(n):
                si, wi = sidx[a + j], widx[b + j]
                t0, t1 = wwords[wi][0], wwords[wi][1]
                cur = times[si]
                cur[0] = t0 if cur[0] is None else min(cur[0], t0)
                cur[1] = t1 if cur[1] is None else max(cur[1], t1)
    else:
        times = [[None, None] for _ in toks]
    # voiced region
    v0, v1 = 0.05, max(0.3, dur - 0.08)
    if env is not None and len(env):
        idx = np.where(env > 0.12 * env.max())[0]
        if len(idx):
            v0, v1 = idx[0] / 100.0, (idx[-1] + 1) / 100.0
    # interpolate the gaps (by token length)
    known = [k for k, t in enumerate(times) if t[0] is not None]
    if not known:
        tot = sum(len(t) for t in toks) or 1
        t, out = v0, []
        for tk in toks:
            d = (v1 - v0) * len(tk) / tot
            out.append([round(t, 3), round(t + d * 0.92, 3), tk]); t += d
        return out
    out = []
    k = 0
    while k < len(toks):
        if times[k][0] is not None:
            out.append([times[k][0], times[k][1], toks[k]]); k += 1
            continue
        j = k
        while j < len(toks) and times[j][0] is None:
            j += 1
        a = out[-1][1] if out else v0
        b = times[j][0] if j < len(toks) else v1
        if b - a < 0.05 * (j - k):
            b = a + 0.12 * (j - k)
        tot = sum(len(toks[x]) for x in range(k, j)) or 1
        t = a
        for x in range(k, j):
            d = (b - a) * len(toks[x]) / tot
            out.append([t, t + d * 0.92, toks[x]]); t += d
        k = j
    # monotonic
    for i in range(1, len(out)):
        if out[i][0] < out[i - 1][0]:
            out[i][0] = out[i - 1][0]
        out[i][1] = max(out[i][1], out[i][0] + 0.04)
    return [[round(a, 3), round(b, 3), w] for a, b, w in out]


def env100(a, sr):
    hop = sr // 100
    m = len(a) // hop
    if m <= 0:
        return np.zeros(1)
    return np.sqrt((a[:m * hop].reshape(m, hop) ** 2).mean(1))


def f0_median(a, sr):
    f0 = []
    for i in range(0, len(a) - 2048, 1600):
        x = a[i:i + 2048]
        if np.sqrt((x ** 2).mean()) < 0.03:
            continue
        x = x - x.mean()
        c = np.correlate(x, x, "full")[2047:]
        lo, hi = int(sr / 520), int(sr / 65)
        k = lo + int(np.argmax(c[lo:hi]))
        if c[k] > 0.35 * c[0]:
            f0.append(sr / k)
    return float(np.median(f0)) if f0 else 0.0


def write_pcm_wav(path, pcm, sr=SR_G):
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(pcm)
