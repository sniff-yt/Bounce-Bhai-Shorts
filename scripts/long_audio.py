#!/usr/bin/env python3
"""Music + SFX + ducking for the long-form cartoons, all generated in code (no samples, nothing to license).

usage: python scripts/long_audio.py out/long_x.json   -> out/long_x_mix.wav (44.1 kHz stereo), story["mix_wav"]

Music: a soft Indian-flavoured score per scene mood (tanpura-style drone + bansuri-like flute phrases in a raga-ish
scale + light tabla-style keherwa for happy/funny scenes, bells for magical ones), crossfaded between scenes and
ducked under speech. SFX cues come from engine/long2d.py plan: footsteps, coins, door knock/creak, rain, thunder,
birds, crickets, river water, market murmur, fire crackle, whoosh, boing, magic shimmer, ding.
"""
import json, math, os, sys, wave

import numpy as np

SR = 44100
rng = np.random.default_rng(7)


def rd_wav(p):
    with wave.open(p) as w:
        a = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
        sr = w.getframerate()
    if sr != SR:
        idx = np.arange(0, len(a), sr / SR)
        a = np.interp(idx, np.arange(len(a)), a).astype(np.float32)
    return a


def add(buf, i, s):
    """buf[i:i+len(s)] += s, clipped to the buffer (never raises)."""
    i = int(i)
    if s is None or i >= len(buf) or i + len(s) <= 0:
        return
    if i < 0:
        s, i = s[-i:], 0
    m = min(len(s), len(buf) - i)
    buf[i:i + m] += s[:m]


def env_adsr(n, a=0.01, d=0.2, s=0.0, r=0.05):
    t = np.arange(n) / SR
    e = np.where(t < a, t / max(a, 1e-4), np.exp(-(t - a) / max(d, 1e-4)) * (1 - s) + s)
    rel = int(r * SR)
    if rel and n > rel:
        e[-rel:] *= np.linspace(1, 0, rel)
    return e.astype(np.float32)


def lowpass(x, cut):
    a = math.exp(-2 * math.pi * cut / SR)
    y = np.empty_like(x)
    acc = 0.0
    # vectorised one-pole via cumulative trick is unstable; use scipy-free block filter
    b = 1 - a
    for i in range(0, len(x), 65536):
        seg = x[i:i + 65536]
        out = np.empty_like(seg)
        for j in range(len(seg)):
            acc = b * seg[j] + a * acc
            out[j] = acc
        y[i:i + 65536] = out
    return y


def lp_fast(x, k):
    """Cheap low-pass: moving average of k samples (applied twice)."""
    if k <= 1:
        return x
    c = np.ones(k, np.float32) / k
    return np.convolve(np.convolve(x, c, "same"), c, "same").astype(np.float32)


def noise(n):
    return rng.standard_normal(n).astype(np.float32)


# ------------------------------------------------------------------------------------------------ instruments
def pluck(f, dur, bright=0.5):
    """Karplus-Strong pluck (tanpura / santoor-ish)."""
    n = int(dur * SR)
    p = max(2, int(SR / f))
    buf = rng.uniform(-1, 1, p).astype(np.float32)
    out = np.empty(n, np.float32)
    k = 0.5 + 0.49 * bright
    for i in range(n):
        v = buf[i % p]
        out[i] = v
        buf[i % p] = k * v + (1 - k) * buf[(i + 1) % p] if True else v
        buf[i % p] *= 0.996
    return out


def ks_cache():
    c = {}

    def get(f, dur, bright=0.5):
        key = (round(f, 1), round(dur, 2), bright)
        if key not in c:
            c[key] = pluck(f, dur, bright)
        return c[key]
    return get


PLUCK = ks_cache()


def flute(f, dur, vib=5.2):
    n = int(dur * SR)
    t = np.arange(n) / SR
    fm = f * (1 + 0.006 * np.sin(2 * math.pi * vib * t) * np.clip(t / 0.3, 0, 1))
    ph = 2 * math.pi * np.cumsum(fm) / SR
    s = np.sin(ph) + 0.18 * np.sin(2 * ph) + 0.06 * np.sin(3 * ph)
    br = lp_fast(noise(n), 6) * 0.05
    e = np.clip(t / 0.08, 0, 1) * np.clip((dur - t) / 0.18, 0, 1)
    return ((s + br) * e).astype(np.float32)


def bell(f, dur):
    n = int(dur * SR)
    t = np.arange(n) / SR
    s = np.sin(2 * math.pi * f * t) + 0.5 * np.sin(2 * math.pi * f * 2.76 * t) * np.exp(-t * 6) + 0.25 * np.sin(2 * math.pi * f * 5.4 * t) * np.exp(-t * 9)
    return (s * np.exp(-t * 2.2)).astype(np.float32)


def tabla_dha(dur=0.35):
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = 95 * (1 + 0.6 * np.exp(-t * 30))
    s = np.sin(2 * math.pi * np.cumsum(f) / SR) * np.exp(-t * 9)
    s += lp_fast(noise(n), 3) * np.exp(-t * 60) * 0.3
    return s.astype(np.float32)


def tabla_na(dur=0.2):
    n = int(dur * SR)
    t = np.arange(n) / SR
    s = np.sin(2 * math.pi * 520 * t) * np.exp(-t * 28) + 0.4 * np.sin(2 * math.pi * 1310 * t) * np.exp(-t * 40)
    return s.astype(np.float32)


# Scales (semitones from Sa)
SCALES = {"happy": [0, 2, 4, 7, 9, 12, 14, 16], "calm": [0, 2, 4, 7, 9, 12, 14], "funny": [0, 2, 4, 7, 9, 12],
          "sad": [0, 1, 3, 5, 7, 8, 10, 12], "tense": [0, 1, 4, 5, 7, 8, 11, 12], "magical": [0, 2, 4, 6, 7, 9, 11, 12, 14]}
MOOD_ALIAS = {"hopeful": "calm", "peaceful": "calm", "emotional": "sad", "dramatic": "tense", "angry": "tense",
              "scary": "tense", "suspense": "tense", "mysterious": "magical", "joyful": "happy", "comedy": "funny",
              "climax": "tense", "celebration": "happy", "romantic": "calm", "neutral": "calm", "greedy": "funny"}
SA = 146.83  # D3


def mood_name(m):
    m = (m or "calm").lower()
    return m if m in SCALES else MOOD_ALIAS.get(m, "calm")


def music_segment(mood, dur, seed):
    r = np.random.default_rng(seed)
    n = int(dur * SR)
    out = np.zeros(n + SR * 3, np.float32)
    sc = SCALES[mood]
    bpm = {"happy": 96, "funny": 112, "calm": 72, "sad": 60, "tense": 84, "magical": 70}[mood]
    beat = 60 / bpm
    # drone: plucked Pa-Sa-Sa-Sa' cycle (tanpura)
    drone = [SA * 2 ** (7 / 12) / 2, SA, SA, SA / 2]
    t = 0.0
    k = 0
    while t < dur:
        f = drone[k % 4]
        s = PLUCK(f, 2.4, 0.3) * 0.22
        i = int(t * SR)
        add(out, i, s)
        t += beat * 2 if mood != "sad" else beat * 2.5
        k += 1
    # melody phrases
    t = 1.0 + r.uniform(0, 1)
    while t < dur - 1:
        phrase = r.integers(3, 6)
        idx = r.integers(0, len(sc) - 3)
        for p in range(phrase):
            idx = int(np.clip(idx + r.choice([-2, -1, 1, 1, 2]), 0, len(sc) - 1))
            f = SA * 2 * 2 ** (sc[idx] / 12)
            d = beat * r.choice([1, 1, 2, 0.5]) * (1.4 if mood == "sad" else 1)
            if mood == "magical":
                s = bell(f * 2, 1.8) * 0.12
            elif mood == "funny":
                s = PLUCK(f, 0.5, 0.7) * 0.28
            else:
                s = flute(f, d * 1.1) * (0.13 if mood != "tense" else 0.1)
            i = int(t * SR)
            add(out, i, s)
            t += d
        t += beat * r.integers(2, 5)
    # percussion
    if mood in ("happy", "funny", "tense"):
        pat = {"happy": "D.N.ND.N", "funny": "D.NNDN.N", "tense": "D...D..."}[mood]
        t = 0.0
        k = 0
        while t < dur:
            c = pat[k % len(pat)]
            if c == "D":
                s = tabla_dha() * (0.32 if mood != "tense" else 0.4)
            elif c == "N":
                s = tabla_na() * 0.16
            else:
                s = None
            if s is not None:
                i = int(t * SR)
                add(out, i, s)
            t += beat / 2
            k += 1
    if mood == "tense":   # low heartbeat pulse
        t = 0.0
        while t < dur:
            s = tabla_dha(0.5) * 0.25
            i = int(t * SR); add(out, i, s)
            t += beat * 2
    return out[:n]


# ------------------------------------------------------------------------------------------------ SFX
def sfx(name, x=0.0):
    name = (name or "").lower()
    if name in ("step", "footsteps", "walk"):
        n = int(0.09 * SR); t = np.arange(n) / SR
        s = lp_fast(noise(n), 18) * np.exp(-t * 55) * 1.6 + np.sin(2 * math.pi * 80 * t) * np.exp(-t * 40) * 0.5
        return s * 0.5
    if name in ("coins", "coin", "money"):
        out = np.zeros(int(0.9 * SR), np.float32)
        for k in range(6):
            n = int(0.35 * SR); t = np.arange(n) / SR
            f = rng.uniform(2600, 4200)
            s = sum(np.sin(2 * math.pi * f * m * t) / (j + 1) for j, m in enumerate([1, 1.52, 2.31, 3.1])) * np.exp(-t * 14)
            i = int(rng.uniform(0, 0.45) * SR)
            add(out, i, s * 0.22)
        return out
    if name in ("knock", "door_knock"):
        out = np.zeros(int(0.9 * SR), np.float32)
        for k in range(3):
            n = int(0.12 * SR); t = np.arange(n) / SR
            s = np.sin(2 * math.pi * 140 * t) * np.exp(-t * 35) + lp_fast(noise(n), 6) * np.exp(-t * 70) * 0.4
            add(out, int(k * 0.22 * SR), s * 0.8)
        return out
    if name in ("door", "creak", "door_creak"):
        n = int(0.9 * SR); t = np.arange(n) / SR
        f = 220 + 140 * np.sin(t * 7) + rng.uniform(-30, 30, n) * 0.2
        ph = 2 * math.pi * np.cumsum(f) / SR
        s = (np.sign(np.sin(ph)) * 0.3 + np.sin(ph * 2) * 0.2) * np.clip(t / 0.1, 0, 1) * np.clip((0.9 - t) / 0.2, 0, 1)
        return lp_fast(s.astype(np.float32), 4) * 0.35
    if name == "thunder":
        n = int(3.5 * SR); t = np.arange(n) / SR
        s = lp_fast(np.cumsum(noise(n)) * 0.02, 60)
        s = s - lp_fast(s, 2000)
        s *= np.clip(t / 0.05, 0, 1) * np.exp(-t * 1.1) * (1 + 0.5 * np.sin(t * 9))
        return (s / (np.max(np.abs(s)) + 1e-6) * 0.7).astype(np.float32)
    if name in ("whoosh", "swoosh", "transition"):
        n = int(0.7 * SR); t = np.arange(n) / SR
        k = (2 + 30 * (t / 0.7)).astype(int)
        s = noise(n)
        s = lp_fast(s, 10) * np.sin(math.pi * t / 0.7) ** 2
        return s * 0.22
    if name in ("boing", "jump", "pop"):
        n = int(0.35 * SR); t = np.arange(n) / SR
        f = 300 + 500 * t / 0.35 if name != "pop" else 600 * np.exp(-t * 12) + 300
        s = np.sin(2 * math.pi * np.cumsum(np.full(n, 1.0) * f) / SR) * np.exp(-t * 9)
        return s.astype(np.float32) * 0.25
    if name in ("magic", "sparkle", "jadu", "chime"):
        out = np.zeros(int(2.2 * SR), np.float32)
        for k in range(9):
            s = bell(SA * 4 * 2 ** (SCALES["magical"][k % 9] / 12), 1.4) * 0.14
            i = int(k * 0.09 * SR); add(out, i, s)
        return out
    if name in ("ding", "bell"):
        return bell(SA * 6, 2.0) * 0.3
    if name in ("cry", "sob"):
        return np.zeros(10, np.float32)
    if name in ("slap", "thud", "fall", "hit"):
        n = int(0.25 * SR); t = np.arange(n) / SR
        return (np.sin(2 * math.pi * 70 * t) * np.exp(-t * 18) + lp_fast(noise(n), 4) * np.exp(-t * 40) * 0.5).astype(np.float32) * 0.7
    if name in ("splash", "water_splash"):
        n = int(0.8 * SR); t = np.arange(n) / SR
        return (lp_fast(noise(n), 3) * np.exp(-t * 6) * 0.35).astype(np.float32)
    if name in ("laugh", "crowd_laugh", "clap", "applause"):
        out = np.zeros(int(1.5 * SR), np.float32)
        for k in range(40):
            n = int(0.03 * SR); s = lp_fast(noise(n), 2) * np.exp(-np.arange(n) / SR * 120)
            add(out, int(rng.uniform(0, 1.4) * SR), s * 0.25)
        return out
    return None


def ambience(name, dur):
    n = int(dur * SR)
    t = np.arange(n) / SR
    if name == "rain":
        s = lp_fast(noise(n), 3) * 0.10 + lp_fast(noise(n), 30) * 0.08
        return s.astype(np.float32)
    if name == "birds":
        out = np.zeros(n, np.float32)
        k = 0.4
        while k < dur - 0.5:
            m = int(0.12 * SR); tt = np.arange(m) / SR
            f0 = rng.uniform(2800, 4200)
            f = f0 + 900 * np.sin(tt * rng.uniform(40, 80))
            s = np.sin(2 * math.pi * np.cumsum(f) / SR) * np.sin(math.pi * tt / 0.12)
            for rep in range(int(rng.integers(1, 4))):
                i = int((k + rep * 0.16) * SR)
                add(out, i, s * 0.035)
            k += rng.uniform(1.5, 4.5)
        return out
    if name == "crickets":
        am = (np.sin(2 * math.pi * 28 * t) > 0.3).astype(np.float32) * (np.sin(2 * math.pi * 0.7 * t) > -0.2)
        return (np.sin(2 * math.pi * 4400 * t) * am * 0.018).astype(np.float32)
    if name == "night_room":
        return (lp_fast(noise(n), 40) * 0.01).astype(np.float32)
    if name == "water":
        return (lp_fast(noise(n), 8) * (0.06 + 0.02 * np.sin(t * 1.3))).astype(np.float32)
    if name == "crowd":
        s = lp_fast(noise(n), 25) * (0.5 + 0.5 * np.sin(t * 2.1) * np.sin(t * 0.7))
        return (s * 0.09).astype(np.float32)
    if name == "fire":
        out = lp_fast(noise(n), 50) * 0.02
        for k in range(int(dur * 6)):
            i = int(rng.uniform(0, dur) * SR); m = 200
            add(out, i, noise(m) * np.exp(-np.arange(m) / 30) * 0.12)
        return out.astype(np.float32)
    return np.zeros(n, np.float32)


def main(path):
    story = json.load(open(path, encoding="utf-8"))
    dur = story["duration"]
    n = int(dur * SR) + SR
    speech = rd_wav(story["speech_wav"])[:n]
    speech = np.pad(speech, (0, n - len(speech)))
    # ---- music (per scene, 1.5 s crossfades)
    music = np.zeros(n, np.float32)
    moods = story.get("scene_moods") or [[0, dur, "calm"]]
    for k, (a, b, m) in enumerate(moods):
        if k == len(moods) - 1:
            b = dur
        a0 = max(0.0, a - 0.75)
        seg = music_segment(mood_name(m), b - a0 + 1.5, seed=k * 31 + 3)
        fade = int(1.5 * SR)
        e = np.ones(len(seg), np.float32)
        e[:fade] = np.linspace(0, 1, fade); e[-fade:] = np.linspace(1, 0, fade)
        add(music, a0 * SR, seg * e)
    music = music / (np.max(np.abs(music)) + 1e-6) * 0.5
    # ---- duck under speech
    hop = 441
    sp_env = np.sqrt(np.convolve(speech ** 2, np.ones(hop * 8) / (hop * 8), "same"))
    talk = (sp_env > 0.01).astype(np.float32)
    talk = np.convolve(talk, np.ones(int(0.35 * SR)) / int(0.35 * SR), "same")   # smooth attack/release
    talk = np.clip(talk * 2.5, 0, 1)
    gain = 0.42 - 0.31 * talk          # ~-7.5 dB in gaps, ~-19 dB under speech (relative)
    end0 = (story.get("end_screen") or [dur])[0]
    gain[int(end0 * SR):] = 0.55
    music *= gain
    # ---- sfx + ambience
    fx = np.zeros(n, np.float32)
    for c in story.get("sfx_cues", []):
        if c["type"] == "ambience":
            for name in c.get("names", []):
                a = ambience(name, c["end"] - c["t"])
                f_ = int(0.5 * SR)
                if len(a) > 2 * f_:
                    a[:f_] *= np.linspace(0, 1, f_); a[-f_:] *= np.linspace(1, 0, f_)
                add(fx, c["t"] * SR, a)
            continue
        s = sfx(c["type"], c.get("x", 0))
        if s is None:
            continue
        add(fx, c["t"] * SR, s)
    mix = speech * 0.95 + music + fx * 0.9
    # gentle limiter
    pk = np.max(np.abs(mix)) + 1e-6
    if pk > 0.95:
        mix = np.tanh(mix / pk * 1.4) / math.tanh(1.4) * 0.95
    stereo = np.stack([mix, mix], 1)
    out = path[:-5] + "_mix.wav"
    with wave.open(out, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((np.clip(stereo, -1, 1) * 32767).astype(np.int16).tobytes())
    story["mix_wav"] = out
    json.dump(story, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"mix: {out} ({dur / 60:.1f} min)", flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
