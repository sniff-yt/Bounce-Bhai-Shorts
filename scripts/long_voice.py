#!/usr/bin/env python3
"""Voice a long-form story and build the timeline. Primary: Gemini TTS voice acting (scripts/gemini_tts.py: one
distinct prebuilt voice per character, per-line emotion style prompts, Whisper-checked words, Whisper word timestamps
for lip-sync). Fallback for lines Gemini could not do: free Microsoft neural voices (edge-tts).

usage: python scripts/long_voice.py out/long_x.json
Adds to every line: audio (wav path), start, end, words [[t0, t1, word] ...] (absolute seconds), voice.
Adds to every scene: start, end. Adds story["duration"], story["speech_wav"], story["voices"].

Each character gets a fixed voice + pitch/rate offset (by type and order) so they sound distinct; the narrator is
a calm, slightly slower voice. Word-boundary timings drive the lip-sync and subtitle timing.
"""
import asyncio, json, os, re, subprocess, sys, threading, time, wave

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SR = 44100
VOICES = {   # (female, male) native voices
    "te": ("te-IN-ShrutiNeural", "te-IN-MohanNeural"),
    "hi": ("hi-IN-SwaraNeural", "hi-IN-MadhurNeural"),
    "en": ("en-IN-NeerjaNeural", "en-IN-PrabhatNeural"),
}
# extra voices for supporting characters: Microsoft multilingual neural voices read Telugu / Hindi text natively.
# They are only used after a speech-recognition check (Groq Whisper) shows they are understood about as well as the
# native voice (see check_extra_voices), so a voice that mangles the language never reaches an episode.
EXTRA = {
    "f": ["fr-FR-VivienneMultilingualNeural", "en-US-AvaMultilingualNeural", "en-US-EmmaMultilingualNeural",
          "de-DE-SeraphinaMultilingualNeural"],
    "m": ["en-US-BrianMultilingualNeural", "en-AU-WilliamMultilingualNeural", "de-DE-FlorianMultilingualNeural"],
}
EXTRA_EN = {"f": ["en-IN-NeerjaExpressiveNeural"], "m": []}
CHECK_TEXT = {"te": "అమ్మమ్మ, రాజు దగ్గర అప్పు తీసుకుంటే మనకు కష్టాలు తప్పవు కదా?",
              "hi": "दादी, साहूकार से कर्ज़ लेना ठीक नहीं होगा, हम मेहनत करके पैसे जोड़ेंगे।",
              "en": "Grandma, borrowing money from the moneylender will only bring us more trouble."}
# type -> (gender, base pitch Hz, base rate %, formant factor). The formant factor scales the voice's resonances
# (asetrate + atempo, duration unchanged): >1 younger / smaller, <1 older / bigger.
TYPE_VOICE = {"man": ("m", 0, 0, 1.0), "oldman": ("m", -14, -12, 0.93), "woman": ("f", 4, 2, 1.0),
              "oldwoman": ("f", -18, -12, 0.92), "boy": ("f", 18, 6, 1.12), "girl": ("f", 26, 8, 1.16)}
VARIANTS = [(0, 0, 1.0), (-9, -4, 0.96), (9, 5, 1.05), (-4, 8, 0.98), (14, -2, 1.07), (-15, 3, 0.94)]
GAP = {"same": 0.32, "switch": 0.5, "emotional": 0.7}
SCENE_IN, SCENE_OUT = 2.0, 0.7   # 2 s establishing wide (ambience + music) before a scene's first line
REACT_GAP = 0.95                 # the listener's reaction beat after a strong line (the reaction shot is there)
STRONG = {"angry", "cry", "surprised", "shocked", "scared", "sad", "greedy", "proud", "laugh", "happy", "worried"}
LEAD = 0.6


def clean(text):
    t = re.sub(r"\[[^\]]*\]|\([^)]*\)|\*[^*]*\*", " ", text or "")   # stage directions
    t = re.sub(r"[\U0001F000-\U0001FAFF\u2600-\u27BF]", " ", t)       # emoji
    t = t.replace("\u201c", "").replace("\u201d", "").replace('"', "").replace("\u2018", "'").replace("\u2019", "'")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _norm(s):
    return re.sub(r"[\W_]+", "", s.lower())


def _transcribe(path, lang):
    import requests
    key = os.environ.get("GROQ_API_KEY")
    r = requests.post("https://api.groq.com/openai/v1/audio/transcriptions", headers={"Authorization": f"Bearer {key}"},
                      files={"file": (os.path.basename(path), open(path, "rb"), "audio/mpeg")},
                      data={"model": "whisper-large-v3", "language": lang, "response_format": "json", "temperature": "0"},
                      timeout=60)
    r.raise_for_status()
    return r.json().get("text", "")


async def _synth_plain(text, voice, path):
    import edge_tts
    c = edge_tts.Communicate(text, voice)
    audio = bytearray()
    async for ch in c.stream():
        if ch["type"] == "audio":
            audio += ch["data"]
    if len(audio) < 2000:
        raise RuntimeError("no audio")
    open(path, "wb").write(bytes(audio))


async def check_extra_voices(lang, workdir):
    """Keep the extra voices whose speech Whisper understands nearly as well as the native voice's."""
    import difflib
    if os.environ.get("BB_EXTRA_VOICES", "1") == "0":
        return {"f": [], "m": []}
    pool = EXTRA_EN if lang == "en" else EXTRA
    if lang == "en":
        return pool   # Indian-English expressive variant needs no check
    if not os.environ.get("GROQ_API_KEY"):
        print("::notice title=voices::no GROQ_API_KEY for the speech check; using native voices only", flush=True)
        return {"f": [], "m": []}
    text = CHECK_TEXT[lang]
    fem, mal = VOICES[lang]
    scores = {}
    for v in [fem, mal] + pool["f"] + pool["m"]:
        p = os.path.join(workdir, f"check_{v}.mp3")
        try:
            await _synth_plain(text, v, p)
            heard = await asyncio.to_thread(_transcribe, p, lang)
            scores[v] = difflib.SequenceMatcher(None, _norm(text), _norm(heard)).ratio()
        except Exception as e:
            print(f"voice check {v}: {type(e).__name__} {str(e)[:120]}", flush=True)
        finally:
            if os.path.exists(p):
                os.remove(p)
    base = min([scores[v] for v in (fem, mal) if v in scores] or [0.0])
    if base == 0.0:
        return {"f": [], "m": []}
    ok = {g: [v for v in pool[g] if scores.get(v, 0) >= max(0.55, base - 0.08)] for g in ("f", "m")}
    print("::notice title=voice check::" + ", ".join(f"{v.split('-')[2][:-6]}={scores[v]:.2f}" for v in scores) +
          f" | native {base:.2f} | using extra: {ok['f'] + ok['m'] or 'none'}", flush=True)
    return ok


def assign_voices(story, extra=None):
    """narrator + one voice per character. The lead character of each gender keeps the native voice (with its own
    pitch / rate / formant styling); further characters get a verified extra voice when there is one, else a native
    voice with a clearly different pitch, rate and formant."""
    lang = story.get("lang", "hi")
    fem, mal = VOICES.get(lang, VOICES["hi"])
    extra = extra or {"f": [], "m": []}
    pool = {"f": list(extra.get("f", [])), "m": list(extra.get("m", []))}
    out = {"narrator": {"voice": fem if story.get("narrator_gender", "f") == "f" else mal, "pitch": -6, "rate": -6,
                        "formant": 0.97}}
    used = {}
    seen_g = {"f": 0, "m": 0}
    order = sorted(story["characters"], key=lambda c: (0 if c.get("role") in ("hero", "elder") else 1))
    for ch in order:
        g, p, r, f = TYPE_VOICE.get(ch.get("type", "man"), ("m", 0, 0, 1.0))
        k = used.get(ch.get("type"), 0)
        used[ch.get("type")] = k + 1
        dp, dr, df = VARIANTS[k % len(VARIANTS)]
        if ch.get("role") in ("greedy", "villain") and g == "m":
            dp -= 6
            df *= 0.97
        voice = fem if g == "f" else mal
        kid = ch.get("type") in ("boy", "girl")
        if seen_g[g] >= 1 and pool[g] and not kid:   # second+ adult of this gender: a different speaker entirely
            voice = pool[g].pop(0)
            dp, dr = dp // 2, dr // 2
        if not kid:
            seen_g[g] += 1
        out[ch["id"]] = {"voice": voice, "pitch": p + dp, "rate": r + dr, "formant": round(f * df, 3)}
    # narrator must differ from any same-voice character with near pitch and formant
    for cid, v in out.items():
        if cid != "narrator" and v["voice"] == out["narrator"]["voice"] and abs(v["pitch"] - out["narrator"]["pitch"]) < 8 \
                and abs(v["formant"] - 1.0) < 0.03:
            v["pitch"] += 10
            v["formant"] = 1.05
    return out


async def _tts(text, v, path, sem):
    """edge-tts with patient retries (run 41851447734 lost one line to a transient failure after 5 quick tries).
    After 4 failures the line is retried with plain prosody; if it still fails, None (the caller drops the line)."""
    import edge_tts
    last = ""
    async with sem:
        for attempt in range(8):
            try:
                rate, pitch = (f"{v['rate']:+d}%", f"{v['pitch']:+d}Hz") if attempt < 4 else ("+0%", "+0Hz")
                c = edge_tts.Communicate(text, v["voice"], rate=rate, pitch=pitch, boundary="WordBoundary")
                words, audio = [], bytearray()
                async for ch in c.stream():
                    if ch["type"] == "audio":
                        audio += ch["data"]
                    elif ch["type"] == "WordBoundary":
                        words.append([ch["offset"] / 1e7, (ch["offset"] + ch["duration"]) / 1e7, ch["text"]])
                if len(audio) < 2000:
                    raise RuntimeError("empty audio")
                open(path + ".mp3", "wb").write(bytes(audio))
                return words
            except Exception as e:
                last = f"{type(e).__name__}: {str(e)[:160]}"
                print(f"tts retry {attempt + 1} for {os.path.basename(path)}: {last}", flush=True)
                await asyncio.sleep(min(40, 3 + attempt * 6))
    print(f"::warning title=tts::dropped a line after 8 tries ({last}): {text[:60]}", flush=True)
    return None


def decode(path, formant=1.0):
    af = []
    if abs(formant - 1.0) > 0.005:   # shift resonances (and pitch) by `formant`, keep the duration
        af = ["-af", f"aresample={SR},asetrate={SR * formant:.0f},aresample={SR},atempo={1 / formant:.5f}"]
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, *af, "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).copy()


def trim(a, thr=0.008):
    idx = np.where(np.abs(a) > thr)[0]
    if len(idx) == 0:
        return a, 0.0
    s = max(0, idx[0] - int(0.02 * SR))
    e = min(len(a), idx[-1] + int(0.08 * SR))
    return a[s:e], s / SR


def write_wav(path, a, sr=SR):
    a = np.clip(a, -1, 1)
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((a * 32767).astype(np.int16).tobytes())


EMO = {"cry", "angry", "surprised", "scared", "sad", "shocked"}


MAX_MIN = float(os.environ.get("BB_LONG_MAX_MIN", "9.7"))   # video length incl. end screen (target 9-10 min)
GAP_SCALE = 1.0   # shrinks the pauses between lines when dropping lines was not enough
FILLER = {"laugh", "surprised", "shrug", "scratch", "think", "nod", "wave", "greet", "hips", "proud", "celebrate"}


def _gap(sc, li):
    ln, prev = sc["lines"][li], sc["lines"][li - 1]
    g = GAP["emotional"] if (ln.get("emotion") in EMO or prev.get("emotion") in EMO) else \
        GAP["same"] if ln.get("speaker") == prev.get("speaker") else GAP["switch"]
    return g * GAP_SCALE + (0.25 if ln.get("action") in ("walk", "enter", "exit", "give", "run") else 0) + \
        (prev.get("react_gap", REACT_GAP) if prev.get("react_by") else 0.0)


def mark_reactions(story):
    """Choose the lines followed by a listener reaction beat: a strong line said TO somebody (target, the next speaker,
    or a listed reaction), at most every other line."""
    n = 0
    for sc in story["scenes"]:
        ls = sc["lines"]
        last = -9
        for li, ln in enumerate(ls[:-1]):
            ln.pop("react_by", None)
            sp = ln.get("speaker")
            if not sp or sp == "narrator":
                continue
            nxt = ls[li + 1]
            lis = ln.get("target") if ln.get("target") not in (None, sp, "narrator") else None
            if not lis and nxt.get("speaker") not in (None, sp, "narrator"):
                lis = nxt.get("speaker")
            if not lis:
                lis = next((k for k in (ln.get("reactions") or {}) if k != sp), None)
            if not lis:
                continue
            strong = (ln.get("emotion") in STRONG) or bool(ln.get("reactions")) or \
                (ln.get("action") or "") in ("give", "shout", "scold", "stomp", "beg", "point")
            if strong and li - last >= 2:
                ln["react_by"] = lis
                ln["react_gap"] = REACT_GAP
                last = li
                n += 1
    return n


def _total(story):
    """Same arithmetic as the timeline below: the finished video's length in seconds."""
    t = LEAD
    for sc in story["scenes"]:
        t += SCENE_IN + sum(ln["dur"] for ln in sc["lines"]) + sum(_gap(sc, li) for li in range(1, len(sc["lines"])))
        t += SCENE_OUT + (1.6 if sc.get("moral_card") else 0)
    return t + 5.0


def cap_length(story):
    """The writer's length estimate is only approximate (run 41968766207: the post-TTS cap ran out of droppable lines
    and the video ended 10.83 min), so after synthesis measure the real voiced length and drop lines until the video
    fits, in stages: (1) filler lines from the middle of long scenes, (2) any plain talk / narrator line except a
    scene's first and last line, (3) then the pauses between lines shrink. Never the moral, objects, gives, entries
    or exits."""
    global GAP_SCALE
    dropped = 0
    for stage in (1, 2):
        while _total(story) > MAX_MIN * 60:
            best = None
            for si, sc in enumerate(story["scenes"]):
                ls = sc["lines"]
                if len(ls) <= (6 if stage == 1 else 4):
                    continue
                lo, hi = (2, len(ls) - 3) if stage == 1 else (1, len(ls) - 1)
                for li in range(lo, hi):
                    l = ls[li]
                    if l.get("object") or l.get("to") or l.get("action") in ("give", "take", "show", "enter", "exit", "walk", "run"):
                        continue
                    if sc.get("moral_card") and li == len(ls) - 1:
                        continue
                    score = (len(ls), l.get("action") in FILLER, l.get("speaker") == "narrator", -l["dur"])
                    if best is None or score > best[0]:
                        best = (score, si, li)
            if not best:
                break
            del story["scenes"][best[1]]["lines"][best[2]]
            dropped += 1
    while _total(story) > MAX_MIN * 60 and GAP_SCALE > 0.55:
        GAP_SCALE -= 0.05
    return dropped


def gemini_pass(story, base, jobs_spec):
    """Voice every line with Gemini TTS. jobs_spec: [(ln, p)]. Returns {id(ln): (wav24k_path, words_rel, model, sim)}
    for the lines that passed the Whisper word check."""
    import concurrent.futures as cf
    import gemini_tts as GT
    lang = story.get("lang", "te")
    key = os.environ.get("GEMINI_API_KEY", "")
    gkey = os.environ.get("GROQ_API_KEY", "")
    gv = GT.assign(story)
    story["voices_gemini"] = {k: {kk: vv for kk, vv in v.items()} for k, v in gv.items()}
    G = GT.Gemini(key, base + "_ttscache")
    wl = threading.Lock()
    last_w = [0.0]
    stats = {"ok": 0, "retry": 0, "fail": 0, "models": {}}

    def whisper(path):
        if not gkey:
            return None, []
        with wl:   # Groq free tier: ~20 requests / min for whisper-large-v3
            d = last_w[0] + 3.1 - time.time()
            if d > 0:
                time.sleep(d)
            last_w[0] = time.time()
        return GT.whisper_words(path, lang, gkey)

    def one(ln, p):
        sp = ln.get("speaker", "narrator")
        v = gv.get(sp) or gv["narrator"]
        text = ln["text"]
        best = None
        tries = 0
        k0 = home.get(sp, 0)
        for model in GT.MODELS[k0:] + GT.MODELS[:k0]:
            if model in G.dead:
                continue
            for plain in (False, True):
                try:
                    pcm = G.synth(model, v["gemini"], GT.style_prompt(v, ln, lang, plain), text)
                except Exception as e:
                    print(f"gemini {model} {os.path.basename(p)}: {str(e)[:140]}", flush=True)
                    break
                tries += 1
                wp = p + f"_g{tries}.wav"
                GT.write_pcm_wav(wp, pcm)
                heard, ww = whisper(wp)
                sim = GT.similarity(heard, text) if heard is not None else 0.7
                # long extra speech (the model read the notes aloud) shows up as too much audio for the words
                dur = len(pcm) / 2 / GT.SR_G
                cps = len(GT._norm(text)) / max(0.3, dur)
                if cps < 3.0:
                    sim = min(sim, 0.5)
                cand = (sim, model, wp, ww, dur)
                if best is None or cand[0] > best[0]:
                    best = cand
                if sim >= 0.8:
                    break
                stats["retry"] += 1
            if best and best[0] >= 0.8:
                break
        if best is None or best[0] < 0.55:
            stats["fail"] += 1
            return None
        stats["ok"] += 1
        stats["models"][best[1]] = stats["models"].get(best[1], 0) + 1
        return best

    # each character's home model (busiest characters on different models, so the per-minute quotas add up)
    cnt = {}
    for ln, p in jobs_spec:
        cnt[ln.get("speaker", "narrator")] = cnt.get(ln.get("speaker", "narrator"), 0) + 1
    home = {c: k % max(1, min(3, len(GT.MODELS))) for k, c in enumerate(sorted(cnt, key=lambda c: -cnt[c]))}
    out = {}
    t0 = time.time()
    with cf.ThreadPoolExecutor(int(os.environ.get("BB_TTS_WORKERS", "4"))) as ex:
        futs = {ex.submit(one, ln, p): (ln, p) for ln, p in jobs_spec}
        for f in cf.as_completed(futs):
            ln, p = futs[f]
            try:
                r = f.result()
            except Exception as e:
                print(f"gemini line failed: {e}", flush=True)
                r = None
            if r:
                out[id(ln)] = r
    sims = [r[0] for r in out.values()]
    print(f"::notice title=gemini tts::{stats['ok']}/{len(jobs_spec)} lines in {time.time() - t0:.0f}s, models {stats['models']}, "
          f"retries {stats['retry']}, failed {stats['fail']} (edge-tts for those), whisper word match median "
          f"{(sorted(sims)[len(sims) // 2] if sims else 0):.2f}, calls {G.calls}", flush=True)
    return out, gv


def loud_norm(a, target_rms=0.085, peak=0.95):
    r = float(np.sqrt((a ** 2).mean())) or 1e-4
    a = a * (target_rms / r)
    m = float(np.max(np.abs(a))) or 1
    if m > peak:   # soft limit the peaks
        a = np.tanh(a / peak * 1.2) * peak / np.tanh(1.2)
    return a


async def main_async(path):
    import gemini_tts as GT
    story = json.load(open(path, encoding="utf-8"))
    base = path[:-5]
    os.makedirs(base + "_vo", exist_ok=True)
    use_gem = bool(os.environ.get("GEMINI_API_KEY")) and os.environ.get("BB_TTS", "gemini") == "gemini"
    extra = await check_extra_voices(story.get("lang", "hi"), base + "_vo") if not use_gem else {"f": [], "m": []}
    voices = assign_voices(story, extra)
    story["voices"] = voices
    spec = []
    for si, sc in enumerate(story["scenes"]):
        for li, ln in enumerate(sc["lines"]):
            text = clean(ln.get("text")) or "..."
            ln["text"] = text
            p = f"{base}_vo/s{si:02d}_l{li:02d}"
            ln["audio"] = p + ".wav"
            spec.append((ln, p))
    gem, gv = ({}, {})
    if use_gem:
        gem, gv = await asyncio.to_thread(gemini_pass, story, base, spec)
    # ---- edge-tts for whatever Gemini did not voice
    jobs, sem = [], asyncio.Semaphore(4)
    for ln, p in spec:
        if id(ln) in gem:
            continue
        sp = ln.get("speaker", "narrator")
        v = voices.get(sp) or voices["narrator"]
        ln["voice"] = f"edge {v['voice']} {v['pitch']:+d}Hz {v['rate']:+d}% f{v.get('formant', 1.0)}"
        jobs.append((ln, p, _tts(ln["text"], v, p, sem), v.get("formant", 1.0)))
    t0 = time.time()
    res = await asyncio.gather(*[j[2] for j in jobs])
    jobs = [(ln, p, f) for ln, p, _, f in jobs]
    if jobs:
        print(f"edge-tts: {len(jobs)} lines in {time.time() - t0:.0f}s", flush=True)
    failed = [ln for (ln, p, _f), words in zip(jobs, res) if words is None]
    if len(failed) > max(3, len(spec) // 20):
        raise SystemExit(f"TTS failed for {len(failed)} of {len(spec)} lines")
    for sc in story["scenes"]:
        sc["lines"] = [ln for ln in sc["lines"] if not any(ln is f for f in failed)]
    for (ln, p, fm), words in zip(jobs, res):
        if words is None:
            continue
        a = decode(p + ".mp3", fm)
        a, off = trim(a)
        a = loud_norm(a)
        write_wav(p + ".wav", a)
        os.remove(p + ".mp3")
        ln["dur"] = len(a) / SR
        ln["words_rel"] = [[max(0, w0 - off), max(0, w1 - off), w] for w0, w1, w in words]
    # ---- Gemini lines: formant (children up), trim, loudness, script words aligned to Whisper's timings
    by_char = {}
    for ln, p in spec:
        if id(ln) in gem:
            by_char.setdefault(ln.get("speaker", "narrator"), []).append((ln, p))
    for sp, items in by_char.items():
        v = gv.get(sp) or gv["narrator"]
        fm = v.get("formant", 1.0)
        kid = v.get("kind") in ("boy", "girl")
        for rnd in range(3):
            f0s, done = [], []
            for ln, p in items:
                sim, model, wp, ww, dur = gem[id(ln)]
                a = decode(wp, fm)
                a, off = trim(a)
                f0s.append(GT.f0_median(a, SR))
                done.append((ln, p, a, off, sim, model, ww))
            f0 = float(np.median([x for x in f0s if x > 0])) if any(x > 0 for x in f0s) else 0.0
            if kid and 0 < f0 < GT.F0_MIN_KID and fm < 1.25 and rnd < 2:
                fm = min(1.25, fm * GT.F0_MIN_KID / f0 * 1.02)   # not child-like enough yet: raise the voice
                continue
            break
        v["formant"] = round(fm, 3)
        v["f0_median"] = round(f0)
        for ln, p, a, off, sim, model, ww in done:
            a = loud_norm(a)
            write_wav(p + ".wav", a)
            env = GT.env100(a, SR)
            words = GT.align(ln["text"], [[w0 - off, w1 - off, w] for w0, w1, w in ww], len(a) / SR, env)
            ln["dur"] = len(a) / SR
            ln["words_rel"] = [[max(0.0, w0), max(0.0, w1), w] for w0, w1, w in words]
            ln["voice"] = f"gemini {model.replace('gemini-', '')} {v['gemini']} f{fm:.2f}"
            ln["tts_match"] = round(sim, 2)
    if gv:
        story["voices_gemini"] = gv
        print("::notice title=voices::" + ", ".join(f"{k}={v['gemini']}(f{v['formant']}, {v.get('f0_median', '?')}Hz)"
                                                   for k, v in gv.items()), flush=True)
    nr = mark_reactions(story)
    print(f"reaction beats: {nr}", flush=True)
    cut = cap_length(story)
    mark_reactions(story)
    if cut:
        print(f"::notice title=length::voiced story was over {MAX_MIN} min: dropped {cut} filler lines "
              f"-> {_total(story) / 60:.2f} min", flush=True)
    # ---- timeline
    t = LEAD
    speech = []
    prev_sp = None
    for si, sc in enumerate(story["scenes"]):
        sc["start"] = t
        t += SCENE_IN
        prev_sp = None
        for li, ln in enumerate(sc["lines"]):
            if prev_sp is not None:
                t += _gap(sc, li)
            ln["start"] = round(t, 3)
            ln["end"] = round(t + ln["dur"], 3)
            ln["words"] = [[round(t + a, 3), round(t + b, 3), w] for a, b, w in ln.pop("words_rel")]
            speech.append((ln["start"], ln["audio"]))
            t = ln["end"]
            prev_sp = ln.get("speaker")
        t += SCENE_OUT + (1.6 if sc.get("moral_card") else 0)
        sc["end"] = round(t, 3)
    story["end_screen"] = [round(t, 3), round(t + 5.0, 3)]
    story["duration"] = round(t + 5.0, 3)
    buf = np.zeros(int(story["duration"] * SR) + SR, np.float32)
    for st, p in speech:
        a = decode(p)
        i = int(st * SR)
        buf[i:i + len(a)] += a[:len(buf) - i]
    story["speech_wav"] = base + "_speech.wav"
    write_wav(story["speech_wav"], buf)
    json.dump(story, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    used = sorted({ln.get("voice", "").split(" ")[0] for sc in story["scenes"] for ln in sc["lines"]})
    print(f"::notice title=timeline::engines {used}; duration {story['duration'] / 60:.1f} min", flush=True)


def main(path):
    for k in ("HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy", "ALL_PROXY", "all_proxy"):
        if os.environ.get("BB_TTS_NO_PROXY") == "1":
            os.environ.pop(k, None)
    asyncio.run(main_async(path))


if __name__ == "__main__":
    main(sys.argv[1])
