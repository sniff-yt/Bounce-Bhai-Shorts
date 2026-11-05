#!/usr/bin/env python3
"""Probe Gemini TTS for the long-form voices: which TTS models the key lists, rate limits, and quality of a few
Telugu/Hindi lines per prebuilt voice + style prompt (Groq Whisper transcript similarity, loudness, median pitch).
usage: python scripts/tts_probe.py out/probe [te]"""
import base64, difflib, json, os, re, sys, time, wave
import numpy as np
import requests

KEY = os.environ.get("GEMINI_API_KEY", "")
BASE = "https://generativelanguage.googleapis.com/v1beta"
out = sys.argv[1] if len(sys.argv) > 1 else "out/probe"
lang = sys.argv[2] if len(sys.argv) > 2 else "te"
os.makedirs(out, exist_ok=True)

r = requests.get(f"{BASE}/models?key={KEY}&pageSize=200", timeout=30)
models = [m["name"] for m in r.json().get("models", [])]
TTSM = [m for m in models if "tts" in m]
print("::notice title=tts models::" + ", ".join(TTSM))
print("all models:", models)

SAMPLES = {"te": [
    ("narrator", "Gacrux", "Read this like a warm, loving grandmother telling a bedtime story to children, slowly, with gentle pauses",
     "ఒక ఊరిలో, రాము అనే ఒక చిన్న పిల్లవాడు ఉండేవాడు. వాడికి ఒక పెద్ద కల ఉండేది."),
    ("narrator2", "Sulafat", "Read this like a warm, loving grandmother telling a bedtime story to children, slowly, with gentle pauses",
     "ఒక ఊరిలో, రాము అనే ఒక చిన్న పిల్లవాడు ఉండేవాడు. వాడికి ఒక పెద్ద కల ఉండేది."),
    ("king_angry", "Alnilam", "Say this angrily, like a proud, furious king shouting at his court",
     "ఎవరక్కడ! ఈ దొంగని వెంటనే చెరసాలలో వేయండి!"),
    ("villain", "Algenib", "Say this slyly, like a greedy cunning money-lender, with a sneaky little laugh",
     "హహ్హ... ఈ బంగారం అంతా ఇక నాదే. ఎవరికీ తెలియదు."),
    ("child", "Leda", "Say this like an excited, happy six-year-old child",
     "అమ్మా! చూడు చూడు! నాకు బంగారు చేప దొరికింది!"),
    ("oldwoman_sad", "Gacrux", "Say this sadly, like a tired old grandmother, almost crying",
     "నాయనా, నా దగ్గర ఇంకేమీ మిగల్లేదు రా... ఈ కుండ ఒక్కటే."),
    ("youngwoman", "Kore", "Say this worried and pleading, like a young mother",
     "అయ్యో, ఆగండి! దయచేసి మా పిల్లవాడిని ఏమీ అనకండి!"),
    ("man_hero", "Achird", "Say this kindly and warmly, like a humble village farmer",
     "పర్వాలేదు అమ్మా, మనం కష్టపడి పని చేద్దాం. అంతా మంచే జరుగుతుంది."),
    ("oldman", "Charon", "Say this wisely and calmly, like an old village elder",
     "కష్టపడి సంపాదించిన డబ్బే నిలుస్తుంది, నాయనా."),
], "hi": [
    ("narrator", "Gacrux", "Read this like a warm, loving grandmother telling a bedtime story to children, slowly, with gentle pauses",
     "एक गाँव में, रामू नाम का एक छोटा सा लड़का रहता था। उसका एक बड़ा सपना था।"),
    ("child", "Leda", "Say this like an excited, happy six-year-old child", "माँ! देखो देखो! मुझे सोने की मछली मिली!"),
    ("king_angry", "Alnilam", "Say this angrily, like a proud, furious king", "कौन है वहाँ! इस चोर को अभी कैद में डाल दो!"),
]}


def tts(model, voice, style, text):
    body = {"contents": [{"parts": [{"text": f"{style}:\n{text}"}]}],
            "generationConfig": {"responseModalities": ["AUDIO"],
                                 "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}}}
    t0 = time.time()
    r = requests.post(f"{BASE}/models/{model}:generateContent?key={KEY}", json=body, timeout=180)
    dt = time.time() - t0
    if r.status_code != 200:
        return None, f"{r.status_code} {r.text[:300]}", dt
    p = r.json()["candidates"][0]["content"]["parts"][0]["inlineData"]
    return base64.b64decode(p["data"]), p.get("mimeType"), dt


def pitch_med(a, sr=24000):
    f0 = []
    for i in range(0, len(a) - 2048, 1200):
        x = a[i:i + 2048]
        if np.sqrt((x ** 2).mean()) < 0.02:
            continue
        x = x - x.mean()
        c = np.correlate(x, x, "full")[2047:]
        lo, hi = int(sr / 500), int(sr / 70)
        k = lo + int(np.argmax(c[lo:hi]))
        if c[k] > 0.3 * c[0]:
            f0.append(sr / k)
    return float(np.median(f0)) if f0 else 0.0


def whisper(path):
    r = requests.post("https://api.groq.com/openai/v1/audio/transcriptions",
                      headers={"Authorization": f"Bearer {os.environ.get('GROQ_API_KEY', '')}"},
                      files={"file": (os.path.basename(path), open(path, "rb"), "audio/wav")},
                      data={"model": "whisper-large-v3", "language": lang, "response_format": "verbose_json",
                            "timestamp_granularities[]": "word", "temperature": "0"}, timeout=90)
    if r.status_code != 200:
        return {"error": r.text[:200]}
    return r.json()


norm = lambda s: re.sub(r"[\W_]+", "", s.lower())
order = [m.split("/")[-1] for m in TTSM]
PREF = ("gemini-3.8-flash-tts", "gemini-2.5-pro-preview-tts", "gemini-3.1-flash-tts-preview", "gemini-2.5-flash-preview-tts")
pref = [m for m in PREF if m in order]
report = {"tts_models": TTSM, "samples": []}
for model in pref[:4]:
    for name, voice, style, text in SAMPLES[lang]:
        pcm, mime, dt = tts(model, voice, style, text)
        rec = {"model": model, "name": name, "voice": voice, "secs": round(dt, 1)}
        if pcm is None:
            rec["error"] = mime
            print(f"{model} {name}: ERROR {mime}", flush=True)
            report["samples"].append(rec)
            if "429" in mime:
                time.sleep(30)
            continue
        a = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768
        p = f"{out}/{model}_{name}.wav"
        with wave.open(p, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(pcm)
        wj = whisper(p)
        heard = wj.get("text", "")
        rec.update(mime=mime, dur=round(len(a) / 24000, 2), rms_db=round(20 * np.log10(np.sqrt((a ** 2).mean()) + 1e-9), 1),
                   f0=round(pitch_med(a)), heard=heard, sim=round(difflib.SequenceMatcher(None, norm(text), norm(heard)).ratio(), 2),
                   words=len(wj.get("words") or []), werr=wj.get("error"))
        print(json.dumps(rec, ensure_ascii=False), flush=True)
        report["samples"].append(rec)
        time.sleep(2)
json.dump(report, open(f"{out}/report.json", "w"), ensure_ascii=False, indent=1)
