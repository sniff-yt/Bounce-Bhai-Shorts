#!/usr/bin/env python3
"""Voice a long-form story with free Microsoft neural voices (edge-tts, no key) and build the timeline.

usage: python scripts/long_voice.py out/long_x.json
Adds to every line: audio (wav path), start, end, words [[t0, t1, word] ...] (absolute seconds), voice.
Adds to every scene: start, end. Adds story["duration"], story["speech_wav"], story["voices"].

Each character gets a fixed voice + pitch/rate offset (by type and order) so they sound distinct; the narrator is
a calm, slightly slower voice. Word-boundary timings drive the lip-sync and subtitle timing.
"""
import asyncio, json, os, re, subprocess, sys, time, wave

import numpy as np

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
SCENE_IN, SCENE_OUT = 0.9, 0.7
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


MAX_MIN = float(os.environ.get("BB_LONG_MAX_MIN", "9.85"))   # video length incl. end screen (target 9-10 min)
FILLER = {"laugh", "surprised", "shrug", "scratch", "think", "nod", "wave", "greet", "hips", "proud", "celebrate"}


def _gap(sc, li):
    ln, prev = sc["lines"][li], sc["lines"][li - 1]
    g = GAP["emotional"] if (ln.get("emotion") in EMO or prev.get("emotion") in EMO) else \
        GAP["same"] if ln.get("speaker") == prev.get("speaker") else GAP["switch"]
    return g + (0.25 if ln.get("action") in ("walk", "enter", "exit", "give", "run") else 0)


def _total(story):
    """Same arithmetic as the timeline below: the finished video's length in seconds."""
    t = LEAD
    for sc in story["scenes"]:
        t += SCENE_IN + sum(ln["dur"] for ln in sc["lines"]) + sum(_gap(sc, li) for li in range(1, len(sc["lines"])))
        t += SCENE_OUT + (1.6 if sc.get("moral_card") else 0)
    return t + 5.0


def cap_length(story):
    """The writer's length estimate is only approximate (run 41869713268: estimated 9.76 min, voiced 10.29 min with the
    extra multilingual voices), so after synthesis drop filler lines until the video fits. Never a scene's first 2 or
    last 3 lines, objects / gives / entries / exits, or the moral."""
    dropped = 0
    while _total(story) > MAX_MIN * 60:
        best = None
        for si, sc in enumerate(story["scenes"]):
            ls = sc["lines"]
            if len(ls) <= 6:
                continue
            for li in range(2, len(ls) - 3):
                l = ls[li]
                if l.get("object") or l.get("to") or l.get("action") in ("give", "take", "show", "enter", "exit", "walk", "run"):
                    continue
                score = (len(ls), l.get("action") in FILLER, l.get("speaker") == "narrator", -l["dur"])
                if best is None or score > best[0]:
                    best = (score, si, li)
        if not best:
            break
        del story["scenes"][best[1]]["lines"][best[2]]
        dropped += 1
    return dropped


async def main_async(path):
    story = json.load(open(path, encoding="utf-8"))
    base = path[:-5]
    os.makedirs(base + "_vo", exist_ok=True)
    extra = await check_extra_voices(story.get("lang", "hi"), base + "_vo")
    voices = assign_voices(story, extra)
    story["voices"] = voices
    jobs, sem = [], asyncio.Semaphore(4)
    for si, sc in enumerate(story["scenes"]):
        for li, ln in enumerate(sc["lines"]):
            sp = ln.get("speaker", "narrator")
            v = voices.get(sp) or voices["narrator"]
            text = clean(ln.get("text"))
            if not text:
                text = "..."
            ln["text"] = text
            p = f"{base}_vo/s{si:02d}_l{li:02d}"
            ln["audio"] = p + ".wav"
            ln["voice"] = f"{v['voice']} {v['pitch']:+d}Hz {v['rate']:+d}% f{v.get('formant', 1.0)}"
            jobs.append((ln, p, _tts(text, v, p, sem), v.get("formant", 1.0)))
    t0 = time.time()
    res = await asyncio.gather(*[j[2] for j in jobs])
    jobs = [(ln, p, f) for ln, p, _, f in jobs]
    print(f"tts: {len(jobs)} lines in {time.time() - t0:.0f}s", flush=True)
    failed = [ln for (ln, p, _f), words in zip(jobs, res) if words is None]
    if len(failed) > max(3, len(jobs) // 20):
        raise SystemExit(f"edge-tts failed for {len(failed)} of {len(jobs)} lines")
    for sc in story["scenes"]:
        sc["lines"] = [ln for ln in sc["lines"] if not any(ln is f for f in failed)]
    for (ln, p, fm), words in zip(jobs, res):
        if words is None:
            continue
        a = decode(p + ".mp3", fm)
        a, off = trim(a)
        peak = np.max(np.abs(a)) or 1
        a = a / peak * 0.85
        write_wav(p + ".wav", a)
        os.remove(p + ".mp3")
        ln["dur"] = len(a) / SR
        ln["words_rel"] = [[max(0, w0 - off), max(0, w1 - off), w] for w0, w1, w in words]
    cut = cap_length(story)
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
                g = GAP["emotional"] if (ln.get("emotion") in EMO or sc["lines"][li - 1].get("emotion") in EMO) else \
                    GAP["same"] if ln.get("speaker") == prev_sp else GAP["switch"]
                if ln.get("action") in ("walk", "enter", "exit", "give", "run"):
                    g += 0.25
                t += g
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
    used = sorted({v["voice"] for v in voices.values()})
    print(f"::notice title=voices::{', '.join(used)}; duration {story['duration'] / 60:.1f} min", flush=True)


def main(path):
    for k in ("HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy", "ALL_PROXY", "all_proxy"):
        if os.environ.get("BB_TTS_NO_PROXY") == "1":
            os.environ.pop(k, None)
    asyncio.run(main_async(path))


if __name__ == "__main__":
    main(sys.argv[1])
