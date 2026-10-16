#!/usr/bin/env python3
"""Narrate a story in the creator's cloned voice (Chatterbox Multilingual, MIT licence).
usage: python scripts/voice.py out/story.json voice/ref.wav
Adds "voice_lines" (one wav per sentence) to the story JSON.
"""
import json, os, sys
import torch, torchaudio
from chatterbox.mtl_tts import ChatterboxMultilingualTTS

story_path, ref = sys.argv[1], sys.argv[2]
s = json.load(open(story_path))
torch.set_num_threads(os.cpu_count() or 2)
m = ChatterboxMultilingualTTS.from_pretrained(device="cuda" if torch.cuda.is_available() else "cpu")
base = story_path.replace(".json", "")
paths = []
for i, sent in enumerate(s["sentences"]):
    best, best_err = None, 9e9
    expect = 0.35 + 0.075 * len(sent["hd"])
    for attempt in range(3):  # regenerate lines that come out cut off or rambling
        w = m.generate(sent["hd"], language_id="hi", audio_prompt_path=ref, exaggeration=0.6, cfg_weight=0.4)
        d = w.shape[-1] / m.sr
        err = abs(d / expect - 1)
        print(f"line {i} try {attempt}: {d:.2f}s (expected ~{expect:.2f}s)", flush=True)
        if err < best_err:
            best, best_err = w, err  # keep the closest try, not just the last one
        if 0.5 * expect <= d <= 1.8 * expect:
            break
    p = f"{base}_line{i}.wav"
    torchaudio.save(p, best, m.sr)
    paths.append(os.path.abspath(p))
    print(i, round(best.shape[-1] / m.sr, 2), "s", flush=True)
s["voice_lines"] = paths
json.dump(s, open(story_path, "w"), ensure_ascii=False, indent=1)
