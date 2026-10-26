#!/usr/bin/env python3
"""3-ball parkour race Short: circle arena -> pipe -> random obstacle course (engine/sim_race.py renders it).
usage: python scripts/make_race.py out/short_x.json
"""
import json, random, sys, os

HOOKS = [
    ("Kaun jeetega? Apna colour chuno! 🔴🔵🟢", "Who wins? Pick your colour! 🔴🔵🟢", "ఎవరు గెలుస్తారు? మీ రంగు ఎంచుకోండి! 🔴🔵🟢", "कौन जीतेगा? अपना कलर चुनो! 🔴🔵🟢"),
    ("Red, Blue ya Green? Race shuru! 🏁", "Red, Blue or Green? Race starts! 🏁", "ఎరుపు, నీలం లేదా పచ్చ? రేస్ మొదలు! 🏁", "रेड, ब्लू या ग्रीन? रेस शुरू! 🏁"),
    ("Is race ka winner guess karo 🏁", "Guess the winner of this race 🏁", "ఈ రేస్ విజేతను ఊహించండి 🏁", "इस रेस का विनर गेस करो 🏁"),
    ("Last second mein palat gaya? 😱", "Did it flip in the last second? 😱", "చివరి సెకనులో మారిపోయిందా? 😱", "लास्ट सेकंड में पलट गया? 😱"),
]
CTAS = ["Tumhara colour jeeta? Comment karo!", "Kaunsa colour tha tumhara? Comment!", "Next race mein kaun? Comment karo!"]


def main(out):
    rng = random.Random()
    hr, en, te, hd = rng.choice(HOOKS)
    name = os.path.splitext(os.path.basename(out))[0]
    cfg = {
        "format": "race", "title": f"Ball race {name[-13:]}", "topic": "ball race",
        "out": out.replace(".json", ".mp4"), "seed": rng.randint(1, 10 ** 6), "tries": 120, "budget": 150,
        "hook": "KAUN JEETEGA?", "cta": rng.choice(CTAS),
        "yt_title": {"hi_roman": f"{hr} #shorts", "en": f"{en} #shorts", "te": f"{te} #shorts", "hi": f"{hd} #shorts"},
        "question": {"hi_roman": "Tumhara colour kaunsa tha? 👇", "en": "Which colour did you pick? 👇",
                     "te": "మీరు ఏ రంగు ఎంచుకున్నారు? 👇", "hi": "तुम्हारा कलर कौनसा था? 👇"},
        "tags": ["shorts", "satisfying", "marble race", "ball race", "physics", "simulation", "oddly satisfying"],
        "genre_tag": "#marblerace",
    }
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    json.dump(cfg, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("race:", cfg["yt_title"]["hi_roman"], "seed", cfg["seed"])


if __name__ == "__main__":
    main(sys.argv[1])
