#!/usr/bin/env python3
"""Narrate a story in the creator's cloned voice (Chatterbox Multilingual, MIT licence).
usage: python scripts/voice.py out/story.json voice/ref.wav
Adds "voice_lines" (one wav per sentence) to the story JSON.

This version adds a post-generation denoise and normalization step (noisereduce) to
reduce intermittent noise in the synthesized voice lines. If denoising fails, the
original generated audio is kept.
"""
import json, os, sys
import torch, torchaudio
import numpy as np
try:
    import noisereduce as nr
except Exception:
    nr = None
from chatterbox.mtl_tts import ChatterboxMultilingualTTS
try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import live as _live
except Exception:
    _live = None

story_path, ref = sys.argv[1], sys.argv[2]
s = json.load(open(story_path))
torch.set_num_threads(os.cpu_count() or 2)
m = ChatterboxMultilingualTTS.from_pretrained(device="cuda" if torch.cuda.is_available() else "cpu")
base = story_path.replace(".json", "")
paths = []
for i, sent in enumerate(s["sentences"]):
    best, best_err = None, 9e9
    text = sent["hd"]
    letters = [ch for ch in text if ch.isalpha()]
    if sum(0x0900 <= ord(ch) <= 0x097F for ch in letters) < 0.6 * max(1, len(letters)):
        print(f"line {i}: 'hd' is not Devanagari, speaking the Hinglish line instead", flush=True)
        text = sent["hi"]
    expect = 0.35 + 0.075 * len(text)
    for attempt in range(3):  # regenerate lines that come out cut off or rambling
        w = m.generate(text, language_id="hi", audio_prompt_path=ref, exaggeration=0.6, cfg_weight=0.4)
        d = w.shape[-1] / m.sr
        err = abs(d / expect - 1)
        print(f"line {i} try {attempt}: {d:.2f}s (expected ~{expect:.2f}s)", flush=True)
        if err < best_err:
            best, best_err = w, err  # keep the closest try, not just the last one
        if 0.5 * expect <= d <= 1.8 * expect:
            break
    p = f"{base}_line{i}.wav"

    # Post-process: denoise + normalize (best is a torch Tensor: [channels, samples])
    try:
        arr = best.detach().cpu().numpy()
        # convert to mono for denoiser if multi-channel
        if arr.ndim > 1 and arr.shape[0] > 1:
            y = np.mean(arr, axis=0)
        else:
            y = arr.reshape(-1)
        if nr is not None:
            try:
                denoised = nr.reduce_noise(y=y, sr=m.sr)
            except Exception as e:
                print(f"noisereduce failed: {e}; using original audio", flush=True)
                denoised = y
        else:
            denoised = y
        # simple peak normalization to -1..1 (leave a small headroom)
        peak = np.max(np.abs(denoised))
        if peak > 0:
            denoised = denoised * (0.95 / peak)
        tensor = torch.from_numpy(denoised).float().unsqueeze(0)
        torchaudio.save(p, tensor, m.sr)
    except Exception as e:
        print(f"post-process failed ({e}), saving raw waveform", flush=True)
        # fallback: save original tensor
        try:
            torchaudio.save(p, best, m.sr)
        except Exception as e2:
            print(f"failed to save audio: {e2}", flush=True)
            raise

    paths.append(os.path.abspath(p))
    print(i, round(best.shape[-1] / m.sr, 2), "s", flush=True)
    if _live:
        _live.event(f"Voice line {i + 1}/{len(s['sentences'])}: {sent.get('hi', '')[:80]}",
                    pct=round(10 + 28 * (i + 1) / len(s["sentences"]), 1))
s["voice_lines"] = paths
json.dump(s, open(story_path, "w"), ensure_ascii=False, indent=1)
