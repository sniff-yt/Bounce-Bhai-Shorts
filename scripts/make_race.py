#!/usr/bin/env python3
"""3-ball parkour race Short: circle arena -> pipe -> random obstacle course (engine/sim_race.py renders it).
usage: python scripts/make_race.py out/short_x.json
"""
import json, random, sys, os

# Hook = YouTube title (curiosity / challenge). Weights follow real views (scripts/insights.py, 2026-10-28):
# "Is race ka winner guess karo" median 944 views (3 posts) -> weight 4; "Kaun jeetega? Apna colour chuno" 421;
# "Red, Blue ya Green? Race shuru!" median 160 (4 posts, one 26) -> dropped.
# (weight, Hinglish, English, Telugu, Devanagari, on-screen sub-hook)
HOOKS = [
    (4, "Is race ka winner guess karo 🏁", "Guess the winner of this race 🏁", "ఈ రేస్ విజేతను ఊహించండి 🏁", "इस रेस का विनर गेस करो 🏁", "Winner guess karo!"),
    (2, "Kaun jeetega? Apna colour chuno! 🔴🔵🟢", "Who wins? Pick your colour! 🔴🔵🟢", "ఎవరు గెలుస్తారు? మీ రంగు ఎంచుకోండి! 🔴🔵🟢", "कौन जीतेगा? अपना कलर चुनो! 🔴🔵🟢", "Apna colour chuno!"),
    (2, "99% log is race ka winner galat guess karte hain 😳🏁", "99% guess this winner wrong 😳🏁", "99% మంది ఈ విజేతను తప్పుగా ఊహిస్తారు 😳🏁", "99% लोग इस रेस का विनर गलत गेस करते हैं 😳🏁", "99% galat guess karte hain!"),
    (2, "Which ball wins? Guess karo 🏁", "Which ball wins? Guess now 🏁", "ఏ బాల్ గెలుస్తుంది? ఊహించండి 🏁", "कौन सी बॉल जीतेगी? गेस करो 🏁", "Which ball wins?"),
    (1, "Last second mein palat gaya? 😱", "Did it flip in the last second? 😱", "చివరి సెకనులో మారిపోయిందా? 😱", "लास्ट सेकंड में पलट गया? 😱", "Last tak dekhna!"),
]
INTENSE_HOOKS = [
    (2, "Dil thaam ke dekhna 😤🔥", "Hold your breath for this one 😤🔥", "ఊపిరి బిగబట్టి చూడండి 😤🔥", "दिल थाम के देखना 😤🔥", "Winner guess karo!"),
    (2, "Photo finish! Winner guess karo 😱🔥", "Photo finish! Guess the winner 😱🔥", "ఫోటో ఫినిష్! విజేతను ఊహించండి 😱🔥", "फोटो फिनिश! विनर गेस करो 😱🔥", "Winner guess karo!"),
    (1, "Sabse INTENSE race! Kaun jeetega? 🔥", "The most INTENSE race! Who wins? 🔥", "అత్యంత ఉత్కంఠభరిత రేస్! ఎవరు గెలుస్తారు? 🔥", "सबसे इंटेंस रेस! कौन जीतेगा? 🔥", "Kaun jeetega?"),
]
CTAS = ["Tumhara colour jeeta? Comment karo!", "Kaunsa colour tha tumhara? Comment!", "Sahi guess kiya? Comment karo!"]
HIST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "history.json")


def _history():
    try:
        return json.load(open(HIST, encoding="utf-8"))
    except Exception:
        return []


def pick_hook(rng, pool, hist):
    """Weighted pick that never repeats one of the last 2 race titles (identical back-to-back titles flopped)."""
    recent = [h.get("yt_title", "") for h in hist if h.get("format") == "race"][-2:]
    cands = [h for h in pool if not any(r.startswith(h[1]) for r in recent)] or pool
    return rng.choices(cands, weights=[h[0] for h in cands])[0]


def main(out):
    rng = random.Random()
    intense = rng.random() < 0.35   # ~1 in 3 races is an "intense" one
    jelly = rng.random() < 0.35     # ~1 in 3 races uses soft jelly balls (variety: new physics look)
    hist = _history()
    _, hr, en, te, hd, sub = pick_hook(rng, INTENSE_HOOKS if intense else HOOKS, hist)
    name = os.path.splitext(os.path.basename(out))[0]
    ep = 1 + sum(1 for h in hist if h.get("format") == "race" and h.get("video_id") and not h.get("deleted"))
    series = f"Ball Race #{ep}"
    cfg = {
        "format": "race", "title": f"Ball race {name[-13:]}", "topic": "ball race",
        # parallel search (all runner cores) for the closest, most contested race; on-screen text is only the hook
        "out": out.replace(".json", ".mp4"), "seed": rng.randint(1, 10 ** 6), "tries": 400, "budget": 170,
        "hook": "JELLY RACE!" if jelly else "KAUN JEETEGA?", "intense": intense, "jelly": jelly,
        "variant": "jelly" if jelly else ("intense" if intense else "classic"),
        "series": series.upper(), "sub_line": "Roz nayi race!",
        "yt_title": {k: f"{v} | {series} #shorts" for k, v in (("hi_roman", hr), ("en", en), ("te", te), ("hi", hd))},
        "question": {"hi_roman": "Tumhara colour kaunsa tha? 👇", "en": "Which colour did you pick? 👇",
                     "te": "మీరు ఏ రంగు ఎంచుకున్నారు? 👇", "hi": "तुम्हारा कलर कौनसा था? 👇"},
        # first comment (the Data API cannot pin it; it is posted right after upload)
        "comment": f"{series}: finish se pehle apna guess comment karo 👇 🔴 RED / 🔵 BLUE / 🟢 GREEN?\n"
                   "Sahi nikla? Subscribe karo, roz nayi race aati hai 🔔",
        "tags": ["shorts", "marble race", "ball race", "guess the winner", "which ball wins", "satisfying",
                 "oddly satisfying", "physics simulation", "marble run", "bounce bhai", "race", "simulation"],
        "hashtags": "#shorts #marblerace #ballrace #guessthewinner #satisfying #physics #simulation",
        "genre_tag": "#marblerace",
    }
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    json.dump(cfg, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("race:", "INTENSE" if intense else "", "JELLY" if jelly else "", cfg["yt_title"]["hi_roman"], "seed", cfg["seed"])


if __name__ == "__main__":
    main(sys.argv[1])
