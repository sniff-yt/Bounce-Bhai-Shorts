#!/usr/bin/env python3
"""Ball Multiply Short (new format, 2026-11-03, manual-only trial): every wall hit = +1 ball until 500, then the ring cracks.
Writes the config + YouTube metadata that engine/sim_multiply.py and scripts/upload.py read.
usage: python scripts/make_multiply.py out/short_x.json
"""
import json, random, sys, os

HOOKS = [
    ("Har bounce = +1 ball 🤯", "Every bounce = +1 ball 🤯", "ప్రతి బౌన్స్ = +1 బాల్ 🤯", "हर बाउंस = +1 बॉल 🤯", "HAR BOUNCE = +1 BALL!"),
    ("500 balls tak kab pahunchegi? 😱", "When will it hit 500 balls? 😱", "500 బాల్స్ ఎప్పుడు? 😱", "500 बॉल्स कब तक? 😱", "500 BALLS KAB HONGI?"),
    ("1 ball se 500 balls 🔴", "1 ball becomes 500 🔴", "1 బాల్ నుండి 500 🔴", "1 बॉल से 500 बॉल्स 🔴", "1 BALL SE 500 BALLS!"),
]
CTAS = ["Guess karo: kab full hoga?", "Comment karo: kitne second?", "Pehle guess karo, phir dekho!"]
HIST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "history.json")


def main(out):
    rng = random.Random()
    try: hist = json.load(open(HIST, encoding="utf-8"))
    except Exception: hist = []
    hr, en, te, hd, onscreen = rng.choice(HOOKS)
    ep = 1 + sum(1 for h in hist if h.get("format") == "multiply" and h.get("video_id"))
    series = f"Ball Multiply #{ep}"
    name = os.path.splitext(os.path.basename(out))[0]
    cfg = {
        "format": "multiply", "title": f"Ball multiply {name[-13:]}", "topic": "ball multiply",
        "out": out.replace(".json", ".mp4"), "seed": rng.randint(1, 99999), "max_balls": 500,
        "hook": onscreen, "cta": rng.choice(CTAS), "series": series.upper(), "target": [18, 23],
        "yt_title": {k: f"{v} | {series} #shorts" for k, v in (("hi_roman", hr), ("en", en), ("te", te), ("hi", hd))},
        "question": {"hi_roman": "Tumhara guess kya tha? Kitne second mein full? 👇", "en": "What was your guess? How many seconds to fill? 👇",
                     "te": "మీ అంచనా ఎంత? ఎన్ని సెకన్లలో ఫుల్? 👇", "hi": "तुम्हारा गेस क्या था? कितने सेकंड में फुल? 👇"},
        "comment": f"{series}: har bounce pe ek nayi ball! Kitne second mein 500 hongi? Guess karo 👇\n"
                   "Agla target 1000 balls? Subscribe karo 🔔",
        "tags": ["shorts", "satisfying", "oddly satisfying", "ball multiply", "physics", "simulation", "bouncing balls",
                 "500 balls", "ball duplication", "bounce bhai", "marble"],
        "hashtags": "#shorts #satisfying #oddlysatisfying #physics #simulation #bouncingball",
        "genre_tag": "#satisfying",
    }
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    json.dump(cfg, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("multiply:", cfg["yt_title"]["hi_roman"], "seed", cfg["seed"])


if __name__ == "__main__":
    main(sys.argv[1])
