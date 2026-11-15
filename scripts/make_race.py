#!/usr/bin/env python3
"""3-ball parkour race Short: circle arena -> pipe -> random obstacle course (engine/sim_race.py renders it).
usage: python scripts/make_race.py out/short_x.json
"""
import json, os, random, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import race_teams

# Hook = YouTube title (curiosity / challenge). Curated for stronger first-second retention:
# direct viewer challenge, prediction, and "wait for finish" framing. A/B variants tracked via cfg["ab"].
# (weight, Hinglish, English, Telugu, Devanagari, on-screen sub-hook)
HOOKS = [
    (4, "3 second mein winner guess karo 🏁", "Guess the winner in 3 seconds 🏁", "3 సెకన్లలో విజేతను ఊహించండి 🏁", "3 सेकंड में विनर गेस करो 🏁", "3 sec mein pick karo!"),
    (4, "Kaun jeetega? Apna colour chuno! 🔴🔵🟢", "Who wins? Pick your colour! 🔴🔵🟢", "ఎవరు గెలుస్తారు? మీ రంగు ఎంచుకోండి! 🔴🔵🟢", "कौन जीतेगा? अपना कलर चुनो! 🔴🔵🟢", "Apna colour chuno!"),
    (3, "99% log galat guess karte hain 😳🏁", "99% guess this race wrong 😳🏁", "99% మంది ఈ రేస్‌ను తప్పుగా ఊహిస్తారు 😳🏁", "99% लोग गलत गेस करते हैं 😳🏁", "99% galat guess!"),
    (3, "Finish line pe kya hua? 😱🏁", "What happened at the finish line? 😱🏁", "ఫినిష్ లైన్ దగ్గర ఏమైంది? 😱🏁", "फिनिश लाइन पे क्या हुआ? 😱🏁", "Finish tak dekhna!"),
    (2, "Last second twist! Kaun jeeta? 🔥", "Last-second twist! Who won? 🔥", "చివరి సెకను ట్విస్ట్! ఎవరు గెలిచారు? 🔥", "लास्ट सेकंड ट्विस्ट! कौन जीता? 🔥", "Last tak dekhna!"),
    (2, "RED, BLUE ya GREEN? Comment se pehle guess karo 👇", "RED, BLUE or GREEN? Guess before you comment 👇", "RED, BLUE లేదా GREEN? కామెంట్ ముందే ఊహించండి 👇", "RED, BLUE या GREEN? कमेंट से पहले गेस करो 👇", "Colour chuno!"),
]
INTENSE_HOOKS = [
    (3, "Photo finish! Winner guess karo 😱🔥", "Photo finish! Guess the winner 😱🔥", "ఫోటో ఫినిష్! విజేతను ఊహించండి 😱🔥", "फोटो फिनिश! विनर गेस करो 😱🔥", "Winner guess karo!"),
    (3, "Sabse CLOSE race! Kaun jeetega? 🔥", "The CLOSEST race! Who wins? 🔥", "అత్యంత దగ్గరి రేస్! ఎవరు గెలుస్తారు? 🔥", "सबसे CLOSE रेस! कौन जीतेगा? 🔥", "Kaun jeetega?"),
    (2, "Dil thaam ke dekhna 😤🔥", "Hold your breath for this one 😤🔥", "ఊపిరి బిగబట్టి చూడండి 😤🔥", "दिल थाम के देखना 😤🔥", "Finish tak dekhna!"),
    (2, "Last frame tak suspense! 😱🔥", "Suspense till the last frame! 😱🔥", "చివరి ఫ్రేమ్ వరకు సస్పెన్స్! 😱🔥", "लास्ट फ्रेम तक सस्पेंस! 😱🔥", "Last tak dekhna!"),
]
# Team races (owner 2026-11-08): label balls as IPL teams / states / cities / countries.
# {m} = "CSK vs MI vs RCB", {e} = 🏏 (IPL) or 🔥. (weight, Hinglish, English, Telugu, Devanagari)
TEAM_SHARE = 0.25  # keep as a minority variant; A/B via history, not forced
TEAM_HOOKS = [
    (3, "{m} {e} Kaun jeetega?", "{m} {e} Who wins?", "{m} {e} ఎవరు గెలుస్తారు?", "{m} {e} कौन जीतेगा?"),
    (3, "{m} {e} Apni team chuno 👇", "{m} {e} Pick your team 👇", "{m} {e} మీ టీమ్ ఎంచుకోండి 👇", "{m} {e} अपनी टीम चुनो 👇"),
    (2, "{m} {e} Finish tak dekhna 😱", "{m} {e} Watch till the finish 😱", "{m} {e} ఫినిష్ వరకు చూడండి 😱", "{m} {e} फिनिश तक देखना 😱"),
]
TEAM_PINS = ["Finish se pehle apni team comment karo!", "Comment your team before the finish!"]
POOL_TAGS = {"ipl": (["ipl", "ipl 2026", "cricket"], "#ipl #cricket"), "state": (["india", "indian states"], "#india"),
             "city": (["india", "indian cities"], "#india"), "country": (["countryballs", "country race"], "#countryballs")}
CTAS = ["Tumhara colour jeeta? Comment karo!", "Kaunsa colour tha tumhara? Comment!", "Sahi guess kiya? Comment karo!"]
HIST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "history.json")


def _history():
    try:
        with open(HIST, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def pick_hook(rng, pool, hist):
    """Weighted pick that avoids recently used race titles to reduce fatigue/cannibalization."""
    recent = [str(h.get("yt_title") or "") for h in hist if h.get("format") == "race"][-10:]
    cands = [h for h in pool if not any(r.startswith(h[1]) for r in recent)]
    if not cands:   # every title in this pool was used lately: take the one used longest ago
        cands = [min(pool, key=lambda h: max([i for i, r in enumerate(recent) if r.startswith(h[1])] or [-1]))]
    return rng.choices(cands, weights=[h[0] for h in cands])[0]


def team_overlay(rng, hist, series, ab_variant):
    """cfg keys that turn a colour/fan race into a team race (names + colours only, physics untouched)."""
    pool, teams = race_teams.pick_team_race(rng, hist)
    disp = [t["name"] if pool == "ipl" else t["name"].title() for t in teams]
    m = " vs ".join(disp)
    e = "🏏" if pool == "ipl" else "🔥"
    last = [x.get("ab", "") for x in hist if x.get("teams")][-1:]
    cands = [h for i, h in enumerate(TEAM_HOOKS) if not (last and f"-h{i}-" in last[0])] or TEAM_HOOKS
    hk = rng.choices(cands, weights=[h[0] for h in cands])[0]
    big = " vs ".join(t["name"] for t in teams)
    if len(big) > 20:
        big = " vs ".join(t["abbr"] for t in teams)
    ptags, phash = POOL_TAGS[pool]
    ttags = [t["tags"][0] for t in teams] + [x for t in teams for x in t["tags"][1:2]]
    names = [t["name"] for t in teams]
    return {
        "race_kind": "team", "team_pool": pool, "teams": names, "names": names,
        "balls": [race_teams.ball_spec(t) for t in teams],
        "hook": big, "hook_sub": rng.choice(["Apni team chuno!", "Kaun jeetega? Team chuno!"]),
        "pin": rng.choice(TEAM_PINS), "ab": f"team-{pool}-h{TEAM_HOOKS.index(hk)}-{ab_variant}",
        "yt_title": {k: f"{v.format(m=m if len(f'{hk[1]}{m}{series}') < 80 else big, e=e)} | {series} #shorts"
                     for k, v in zip(("hi_roman", "en", "te", "hi"), hk[1:])},
        "desc_hook": {"hi_roman": f"{m}: finish se pehle apni team comment karo, phir dekho kaun jeeta 👀",
                      "en": f"{m}: comment your team before the finish, then watch who wins 👀",
                      "te": f"{m}: ఫినిష్ ముందే మీ టీమ్ కామెంట్ చేయండి, తర్వాత ఎవరు గెలిచారో చూడండి 👀",
                      "hi": f"{m}: फिनिश से पहले अपनी टीम कमेंट करो, फिर देखो कौन जीता 👀"},
        "question": {"hi_roman": "Tumhari team kaunsi thi? 👇", "en": "Which team did you pick? 👇",
                     "te": "మీరు ఏ టీమ్ ఎంచుకున్నారు? 👇", "hi": "तुम्हारी टीम कौनसी थी? 👇"},
        "comment": f"{series}: {m}! Finish se pehle apni team comment karo 👇 " + " / ".join(names) + "?\n"
                   "Sahi nikla? Subscribe karo, roz nayi race aati hai 🔔",
        "tags": ptags + ttags + ["ball race", "marble race", "guess the winner", "who will win", "satisfying race",
                                  "bounce bhai", "satisfying", "physics simulation", "race"],
        "hashtags": f"#shorts {phash} " + " ".join(t["hash"] for t in teams) + " #ballrace #marblerace #guessthewinner #satisfying",
        "genre_tag": "#ballrace",
    }


def main(out):
    rng = random.Random()
    intense = rng.random() < 0.40
    jelly = rng.random() < 0.30
    hist = _history()
    pool = INTENSE_HOOKS if intense else HOOKS
    hk = pick_hook(rng, pool, hist)
    _, hr, en, te, hd, sub = hk
    ab = ("intense" if intense else "race") + f"-h{pool.index(hk)}"
    name = os.path.splitext(os.path.basename(out))[0]
    ep = 1 + sum(1 for h in hist if h.get("format") == "race" and h.get("video_id") and not h.get("deleted"))
    series = f"Ball Race #{ep}"
    cfg = {
        "format": "race", "title": f"Ball race {name[-13:]}", "topic": "ball race",
        "out": out.replace(".json", ".mp4"), "seed": rng.randint(1, 10 ** 6), "tries": 400, "budget": 170,
        "hook": "JELLY RACE!" if jelly else "KAUN JEETEGA?", "intense": intense, "jelly": jelly,
        "hook_sub": sub, "ab": ab,
        "pin": "Finish se pehle colour comment karo!",
        "desc_hook": {"hi_roman": "Finish se pehle apna colour comment karo, phir dekho kaun jeeta 👀",
                      "en": "Comment your colour before the finish, then watch who wins 👀",
                      "te": "ఫినిష్ ముందే మీ రంగు కామెంట్ చేయండి, తర్వాత ఎవరు గెలిచారో చూడండి 👀",
                      "hi": "फिनिश से पहले अपना कलर कमेंट करो, फिर देखो कौन जीता 👀"},
        "variant": "jelly" if jelly else ("intense" if intense else "classic"),
        "series": series.upper(), "sub_line": "Roz nayi race!",
        "yt_title": {k: f"{v} | {series} #shorts" for k, v in (("hi_roman", hr), ("en", en), ("te", te), ("hi", hd))},
        "question": {"hi_roman": "Tumhara colour kaunsa tha? RED, BLUE ya GREEN? 👇", "en": "Which colour did you pick? RED, BLUE or GREEN? 👇",
                     "te": "మీరు ఏ రంగు ఎంచుకున్నారు? RED, BLUE లేదా GREEN? 👇", "hi": "तुम्हारा कलर कौनसा था? RED, BLUE या GREEN? 👇"},
        "comment": f"{series}: finish se pehle apna guess comment karo 👇 🔴 RED / 🔵 BLUE / 🟢 GREEN?\n"
                   "Sahi nikla? Subscribe karo, roz nayi race aati hai 🔔",
        "tags": ["shorts", "marble race", "ball race", "guess the winner", "which ball wins", "who will win",
                 "satisfying", "oddly satisfying", "physics simulation", "marble run", "bounce bhai", "race", "simulation"],
        "hashtags": "#shorts #marblerace #ballrace #guessthewinner #whowillwin #satisfying #physics #simulation",
        "genre_tag": "#marblerace",
    }
    team = team_overlay(rng, hist, series, cfg["variant"])
    if rng.random() < TEAM_SHARE:
        cfg["fan_alt"] = {k: cfg.get(k) for k in team}
        cfg.update(team)
    else:
        cfg["race_kind"] = "fan"
        if TEAM_SHARE > 0:
            cfg["team_alt"] = team
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=1)
    print("race:", cfg["race_kind"], "INTENSE" if intense else "", "JELLY" if jelly else "", cfg["yt_title"]["hi_roman"], "seed", cfg["seed"],
          "| team fallback:" if cfg.get("team_alt") else "", (cfg.get("team_alt") or {}).get("teams", ""))


if __name__ == "__main__":
    main(sys.argv[1])
