#!/usr/bin/env python3
"""Config + YouTube metadata for a Bhai Drive promo Short (rendered by scripts/promo.py).
usage: python scripts/make_promo.py out/short_x.json
"""
import json, os, random, sys

GAME_URL = os.environ.get("BB_GAME_URL", "https://sniff-yt.github.io/Bounce-Bhai-Shorts/game/")

# (on-screen hook, Hinglish title, English title, Telugu title, Devanagari title)
HOOKS = [
    ("Ye parking kar paoge?", "Ye parking kar paoge? 🚗", "Can you park this? 🚗", "ఈ పార్కింగ్ చేయగలరా? 🚗", "ये पार्किंग कर पाओगे? 🚗"),
    ("Maine apna khud ka game banaya!", "Maine apna khud ka game banaya! 🎮", "I made my own game! 🎮", "నా సొంత గేమ్ చేశాను! 🎮", "मैंने अपना खुद का गेम बनाया! 🎮"),
    ("Parking test: pass ya fail?", "Parking test: pass ya fail? 😅", "Parking test: pass or fail? 😅", "పార్కింగ్ టెస్ట్: పాస్ లేదా ఫెయిల్? 😅", "पार्किंग टेस्ट: पास या फेल? 😅"),
    ("Real steering wheel wala game", "Real steering wheel wala FREE game 🚗", "A FREE game with a real steering wheel 🚗", "రియల్ స్టీరింగ్ వీల్ గేమ్, ఫ్రీ 🚗", "असली स्टीयरिंग व्हील वाला फ्री गेम 🚗"),
    ("Sabse chill car game?", "Sabse chill car game? 😌🚗", "The chillest car game? 😌🚗", "అత్యంత చిల్ కార్ గేమ్? 😌🚗", "सबसे चिल कार गेम? 😌🚗"),
    ("3 star parking challenge", "3 star parking challenge ⭐⭐⭐", "3-star parking challenge ⭐⭐⭐", "3 స్టార్ పార్కింగ్ ఛాలెంజ్ ⭐⭐⭐", "3 स्टार पार्किंग चैलेंज ⭐⭐⭐"),
]
FREE_LINES = ["Asli gaadi jaise controls", "Wheel, pedals, gear: sab real", "Town mein ghoomo, park karo, paise kamao"]
PARK_LINES = ["12 parking puzzles", "Clean park = 3 stars", "Crash nahi, sirf chill"]


def main(out):
    rng = random.Random()
    hook, hr, en, te, hd = rng.choice(HOOKS)
    cfg = {
        "format": "promo", "title": f"Bhai Drive promo {os.path.basename(out)[6:19]}", "topic": "bhai drive game promo",
        "out": out.replace(".json", ".mp4"), "seed": rng.randint(1, 99999),
        "hook": hook, "line_free": rng.choice(FREE_LINES), "line_park": rng.choice(PARK_LINES),
        "end_lines": ["FREE GAME", "Link: channel bio", "+ description"],
        "game_url": GAME_URL,
        "yt_title": {"hi_roman": f"{hr} #shorts", "en": f"{en} #shorts", "te": f"{te} #shorts", "hi": f"{hd} #shorts"},
        "question": {"hi_roman": f"Bhai Drive FREE mein khelo 👉 {GAME_URL}  Tumhe kitne stars mile? ⭐",
                     "en": f"Play Bhai Drive free 👉 {GAME_URL}  How many stars did you get? ⭐",
                     "te": f"భాయ్ డ్రైవ్ ఫ్రీగా ఆడండి 👉 {GAME_URL}",
                     "hi": f"भाई ड्राइव फ्री में खेलो 👉 {GAME_URL}"},
        "tags": ["shorts", "car game", "parking game", "android game", "indie game", "car parking", "bhai drive", "gaming"],
        "genre_tag": "#gaming",
    }
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    json.dump(cfg, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("promo:", cfg["yt_title"]["hi_roman"])


if __name__ == "__main__":
    main(sys.argv[1])
