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
VOICES = {   # (female, male)
    "te": ("te-IN-ShrutiNeural", "te-IN-MohanNeural"),
    "hi": ("hi-IN-SwaraNeural", "hi-IN-MadhurNeural"),
    "en": ("en-IN-NeerjaNeural", "en-IN-PrabhatNeural"),
}
# type -> (gender, base pitch Hz, base rate %)
TYPE_VOICE = {"man": ("m", 0, 0), "oldman": ("m", -14, -10), "woman": ("f", 4, 2), "oldwoman": ("f", -16, -10),
              "boy": ("f", 22, 6), "girl": ("f", 34, 8)}
VARIANTS = [(0, 0), (-9, -4), (9, 5), (-4, 8), (14, -2), (-15, 3)]   # extra (pitch, rate) per same-type character
GAP = {"same": 0.32, "switch": 0.5, "emotional": 0.7}
SCENE_IN, SCENE_OUT = 0.9, 0.7
LEAD = 0.6


def clean(text):
    t = re.sub(r"\[[^\]]*\]|\([^)]*\)|\*[^*]*\*", " ", text or "")   # stage directions
    t = re.sub(r"[\U0001F000-\U0001FAFF\u2600-\u27BF]", " ", t)       # emoji
    t = t.replace("\u201c", "").replace("\u201d", "").replace('"', "").replace("\u2018", "'").replace("\u2019", "'")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def assign_voices(story):
    lang = story.get("lang", "hi")
    fem, mal = VOICES.get(lang, VOICES["hi"])
    out = {"narrator": {"voice": fem if story.get("narrator_gender", "f") == "f" else mal, "pitch": -6, "rate": -6}}
    used = {}
    for ch in story["characters"]:
        g, p, r = TYPE_VOICE.get(ch.get("type", "man"), ("m", 0, 0))
        k = used.get(ch.get("type"), 0)
        used[ch.get("type")] = k + 1
        dp, dr = VARIANTS[k % len(VARIANTS)]
        if ch.get("role") in ("greedy", "villain") and g == "m":
            dp -= 6
        out[ch["id"]] = {"voice": fem if g == "f" else mal, "pitch": p + dp, "rate": r + dr}
    # narrator must differ from any same-voice character with near pitch
    for cid, v in out.items():
        if cid != "narrator" and v["voice"] == out["narrator"]["voice"] and abs(v["pitch"] - out["narrator"]["pitch"]) < 6:
            v["pitch"] += 10
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


def decode(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
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


async def main_async(path):
    story = json.load(open(path, encoding="utf-8"))
    base = path[:-5]
    os.makedirs(base + "_vo", exist_ok=True)
    voices = assign_voices(story)
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
            ln["voice"] = f"{v['voice']} {v['pitch']:+d}Hz {v['rate']:+d}%"
            jobs.append((ln, p, _tts(text, v, p, sem)))
    t0 = time.time()
    res = await asyncio.gather(*[j[2] for j in jobs])
    print(f"tts: {len(jobs)} lines in {time.time() - t0:.0f}s", flush=True)
    failed = [ln for (ln, p, _), words in zip(jobs, res) if words is None]
    if len(failed) > max(3, len(jobs) // 20):
        raise SystemExit(f"edge-tts failed for {len(failed)} of {len(jobs)} lines")
    for sc in story["scenes"]:
        sc["lines"] = [ln for ln in sc["lines"] if not any(ln is f for f in failed)]
    for (ln, p, _), words in zip(jobs, res):
        if words is None:
            continue
        a = decode(p + ".mp3")
        a, off = trim(a)
        peak = np.max(np.abs(a)) or 1
        a = a / peak * 0.85
        write_wav(p + ".wav", a)
        os.remove(p + ".mp3")
        ln["dur"] = len(a) / SR
        ln["words_rel"] = [[max(0, w0 - off), max(0, w1 - off), w] for w0, w1, w in words]
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
