#!/usr/bin/env python3
"""Ball-escape physics Short.
Writes the config + YouTube metadata that engine/sim_escape.py and scripts/upload.py read.
usage: python scripts/make_sim.py out/short_x.json
"""
import json, os, random, sys

HOOKS = [
    ("3 second mein guess karo: nikal paayegi? 🔴", "Guess in 3 seconds: can it escape? 🔴", "3 సెకన్లలో ఊహించండి: బయటపడుతుందా? 🔴", "3 सेकंड में गेस करो: निकल पाएगी? 🔴"),
    ("Kitne bounce mein bahar niklegi? 🤯", "How many bounces to escape? 🤯", "ఎన్ని బౌన్సుల్లో బయటపడుతుంది? 🤯", "कितने बाउंस में बाहर निकलेगी? 🤯"),
    ("Is gap se bach paayegi ya nahi? 😱", "Will it escape this gap or not? 😱", "ఈ గ్యాప్ నుండి తప్పించుకుంటుందా? 😱", "इस गैप से बच पाएगी या नहीं? 😱"),
    ("Sirf 1 gap... bahar nikal paayegi? 🔴", "Only 1 gap... can it get out? 🔴", "ఒకే గ్యాప్... బయటపడుతుందా? 🔴", "सिर्फ 1 गैप... बाहर निकल पाएगी? 🔴"),
    ("Last bounce tak dekhna! ⏱️", "Watch till the last bounce! ⏱️", "చివరి బౌన్స్ వరకు చూడండి! ⏱️", "लास्ट बाउंस तक देखना! ⏱️"),
    ("Ring tez hota ja raha hai... nikal paayegi? 😰", "The ring keeps speeding up... can it escape? 😰", "రింగ్ వేగం పెరుగుతోంది... బయటపడుతుందా? 😰", "रिंग तेज़ होता जा रहा है... निकल पाएगी? 😰"),
]
BREAK_HOOKS = [
    ("Koi gap nahi... deewar todegi? 🧱", "No gap... will it break the wall? 🧱", "గ్యాప్ లేదు... గోడ పగలగొడుతుందా? 🧱", "कोई गैप नहीं... दीवार तोड़ेगी? 🧱"),
    ("Kitne hit mein deewar tootegi? 🧱", "How many hits to break the wall? 🧱", "ఎన్ని హిట్లలో గోడ పగులుతుంది? 🧱", "कितने हिट में दीवार टूटेगी? 🧱"),
    ("Deewar tod ke nikal paayegi? 😱🧱", "Can it smash its way out? 😱🧱", "గోడ పగలగొట్టి బయటపడుతుందా? 😱🧱", "दीवार तोड़ के निकल पाएगी? 😱🧱"),
]
CTAS = ["Comment karo: kitne bounce?", "Apna guess comment karo!", "Pehle guess karo, phir dekho!"]


HIST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "history.json")


def main(out):
    rng = random.Random()
    try:
        with open(HIST, encoding="utf-8") as f:
            hist = json.load(f)
    except Exception:
        hist = []
    # Avoid recently used escape titles to reduce fatigue/cannibalization.
    recent = [str(h.get("yt_title") or h.get("hook", "")) for h in hist if h.get("format") == "sim"][-10:]
    cands = [h for h in HOOKS if not any(r.startswith(h[0].rsplit(" ", 1)[0]) for r in recent)] or HOOKS
    hk = rng.choice(cands); hr, en, te, hd = hk; ab = f"sim-h{HOOKS.index(hk)}"
    variant = "break" if rng.random() < 0.35 else "gap"
    if variant == "break":
        bc = [h for h in BREAK_HOOKS if not any(r.startswith(h[0]) for r in recent)] or BREAK_HOOKS
        hk = rng.choice(bc); hr, en, te, hd = hk; ab = f"break-h{BREAK_HOOKS.index(hk)}"
    jelly = rng.random() < 0.30
    name = os.path.splitext(os.path.basename(out))[0]
    ep = 1 + sum(1 for h in hist if h.get("format") == "sim" and h.get("video_id") and not h.get("deleted"))
    series = f"Ball Escape #{ep}"
    cfg = {
        "format": "sim", "title": f"Ball escape {name[-13:]}", "topic": "ball escape",
        "out": out.replace(".json", ".mp4"), "seed": rng.randint(1, 99999),
        "hook": hr.rsplit(" ", 1)[0], "cta": rng.choice(CTAS),
        "gap_deg": rng.randint(24, 40), "spin": rng.randint(40, 110), "grow": round(rng.uniform(0.8, 2.0), 2),
        "target": [20, 28], "variant": variant, "jelly": jelly, "ab": ab,
        "spin_accel": 0.03,
        "pin": "Escape se pehle guess comment karo!",
        "desc_hook": {"hi_roman": "Escape se pehle guess comment karo: kitne bounce lagenge? 👀",
                      "en": "Comment your guess before it escapes: how many bounces? 👀",
                      "te": "బయటపడే ముందే మీ అంచనా కామెంట్ చేయండి: ఎన్ని బౌన్సులు? 👀",
                      "hi": "एस्केप से पहले गेस कमेंट करो: कितने बाउंस लगेंगे? 👀"},
        "series": series.upper(),
        "yt_title": {k: f"{v} | {series} #shorts" for k, v in (("hi_roman", hr), ("en", en), ("te", te), ("hi", hd))},
        "question": {"hi_roman": "Tumhara guess kya tha? Kitne bounce? 👇", "en": "What was your guess? How many bounces? 👇",
                     "te": "మీ అంచనా ఎంత? ఎన్ని బౌన్సులు? 👇", "hi": "तुम्हारा गेस क्या था? कितने बाउंस? 👇"},
        "comment": f"{series}: escape se pehle guess karo, kitne bounce lagenge? 👇\n"
                   "Sahi nikla? Subscribe karo, roz naye ball challenges aate hain 🔔",
        "tags": ["shorts", "satisfying", "ball escape", "physics", "bounce", "simulation", "oddly satisfying",
                 "bouncing ball", "physics simulation", "bounce bhai", "escape challenge", "guess the bounces"],
        "hashtags": "#shorts #satisfying #oddlysatisfying #physics #simulation #bouncingball #ballescape",
        "genre_tag": "#satisfying",
    }
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=1)
    print("sim:", cfg["yt_title"]["hi_roman"], "seed", cfg["seed"])


if __name__ == "__main__":
    main(sys.argv[1])
