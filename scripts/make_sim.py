#!/usr/bin/env python3
"""Ball-escape physics Short (the channel's best format so far: 'Is gap se nikal paayegi? 🔴', 1,284 views).
Writes the config + YouTube metadata that engine/sim_escape.py and scripts/upload.py read.
usage: python scripts/make_sim.py out/short_x.json
"""
import json, random, sys, os

HOOKS = [
    ("Is gap se nikal paayegi? 🔴", "Can it escape this gap? 🔴", "ఈ గ్యాప్ నుండి బయటపడుతుందా? 🔴", "क्या ये गैप से निकल पाएगी? 🔴"),
    ("Kitne bounce mein bahar? 🤯", "How many bounces to escape? 🤯", "ఎన్ని బౌన్సుల్లో బయటకు? 🤯", "कितने बाउंस में बाहर? 🤯"),
    ("Ye ball fasi rahegi ya nikalegi? 😱", "Will the ball stay trapped? 😱", "బాల్ చిక్కుకుంటుందా? 😱", "ये बॉल फंसी रहेगी या निकलेगी? 😱"),
    ("Sirf 1 gap... bahar nikal paayegi? 🔴", "Only 1 gap... can it get out? 🔴", "ఒకే గ్యాప్... బయటపడుతుందా? 🔴", "सिर्फ 1 गैप... बाहर निकल पाएगी? 🔴"),
    ("Guess karo: kab nikalegi? ⏱️", "Guess when it escapes ⏱️", "ఎప్పుడు బయటపడుతుందో ఊహించండి ⏱️", "गेस करो: कब निकलेगी? ⏱️"),
]
CTAS = ["Comment karo: kitne bounce?", "Apna guess comment karo!", "Pehle guess karo, phir dekho!"]   # on-screen font has no emoji


def main(out):
    rng = random.Random()
    hr, en, te, hd = rng.choice(HOOKS)
    name = os.path.splitext(os.path.basename(out))[0]
    cfg = {
        "format": "sim", "title": f"Ball escape {name[-13:]}", "topic": "ball escape",
        "out": out.replace(".json", ".mp4"), "seed": rng.randint(1, 99999),
        "hook": hr.rsplit(" ", 1)[0], "cta": rng.choice(CTAS),
        "gap_deg": rng.randint(24, 40), "spin": rng.randint(40, 110), "grow": round(rng.uniform(0.8, 2.0), 2),
        "target": [22, 30],
        "yt_title": {"hi_roman": f"{hr} #shorts", "en": f"{en} #shorts", "te": f"{te} #shorts", "hi": f"{hd} #shorts"},
        "question": {"hi_roman": "Tumhara guess kya tha? Kitne bounce? 👇", "en": "What was your guess? How many bounces? 👇",
                     "te": "మీ అంచనా ఎంత? ఎన్ని బౌన్సులు? 👇", "hi": "तुम्हारा गेस क्या था? कितने बाउंस? 👇"},
        "tags": ["shorts", "satisfying", "ball escape", "physics", "bounce", "simulation", "oddly satisfying"],
        "genre_tag": "#satisfying",
    }
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    json.dump(cfg, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("sim:", cfg["yt_title"]["hi_roman"], "seed", cfg["seed"])


if __name__ == "__main__":
    main(sys.argv[1])
