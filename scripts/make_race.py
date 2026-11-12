#!/usr/bin/env python3
"""3-ball parkour race Short: circle arena -> pipe -> random obstacle course (engine/sim_race.py renders it).
usage: python scripts/make_race.py out/short_x.json
"""
import json, random, sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import race_teams

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
    # A/B (2026-11-07, retention upgrade): new curiosity families, tracked via cfg["ab"] in history.json
    (2, "3 second mein winner pick karo ⏱️🏁", "Pick the winner in 3 seconds ⏱️🏁", "3 సెకన్లలో విజేతను ఎంచుకోండి ⏱️🏁", "3 सेकंड में विनर पिक करो ⏱️🏁", "3 sec mein pick karo!"),
    (2, "Finish line pe kya hua dekho 😳🏁", "Watch what happens at the finish line 😳🏁", "ఫినిష్ లైన్ దగ్గర ఏమైందో చూడండి 😳🏁", "फिनिश लाइन पे क्या हुआ देखो 😳🏁", "Finish tak dekhna!"),
    (1, "Tumhara colour jeetega? Comment karo 👇🏁", "Will your colour win? Comment 👇🏁", "మీ రంగు గెలుస్తుందా? కామెంట్ చేయండి 👇🏁", "तुम्हारा कलर जीतेगा? कमेंट करो 👇🏁", "Apna colour chuno!"),
]
INTENSE_HOOKS = [
    (2, "Dil thaam ke dekhna 😤🔥", "Hold your breath for this one 😤🔥", "ఊపిరి బిగబట్టి చూడండి 😤🔥", "दिल थाम के देखना 😤🔥", "Winner guess karo!"),
    (2, "Photo finish! Winner guess karo 😱🔥", "Photo finish! Guess the winner 😱🔥", "ఫోటో ఫినిష్! విజేతను ఊహించండి 😱🔥", "फोटो फिनिश! विनर गेस करो 😱🔥", "Winner guess karo!"),
    (1, "Sabse INTENSE race! Kaun jeetega? 🔥", "The most INTENSE race! Who wins? 🔥", "అత్యంత ఉత్కంఠభరిత రేస్! ఎవరు గెలుస్తారు? 🔥", "सबसे इंटेंस रेस! कौन जीतेगा? 🔥", "Kaun jeetega?"),
]
# Team races (owner 2026-11-08): ~60% of races label the balls as IPL teams / states / cities / countries.
# {m} = "CSK vs MI vs RCB", {e} = 🏏 (IPL) or 🔥. (weight, Hinglish, English, Telugu, Devanagari)
TEAM_SHARE = 0.0  # owner 2026-11-11: back to old style (team races underperformed: 371-808 vs ~1,000)
TEAM_HOOKS = [
    (3, "{m} {e} Kaun jeetega?", "{m} {e} Who wins?", "{m} {e} ఎవరు గెలుస్తారు?", "{m} {e} कौन जीतेगा?"),
    (3, "{m} {e} Apni team chuno 👇", "{m} {e} Pick your team 👇", "{m} {e} మీ టీమ్ ఎంచుకోండి 👇", "{m} {e} अपनी टीम चुनो 👇"),
    (2, "{m} {e} 99% galat guess karte hain 😳", "{m} {e} 99% guess this wrong 😳", "{m} {e} 99% మంది తప్పుగా ఊహిస్తారు 😳", "{m} {e} 99% गलत गेस करते हैं 😳"),
    (1, "{m} {e} Last tak dekhna 😱", "{m} {e} Watch till the end 😱", "{m} {e} చివరి వరకు చూడండి 😱", "{m} {e} लास्ट तक देखना 😱"),
]
TEAM_PINS = ["Finish se pehle apni team comment karo!", "Comment your team before the finish!"]
POOL_TAGS = {"ipl": (["ipl", "ipl 2026", "cricket"], "#ipl #cricket"), "state": (["india", "indian states"], "#india"),
             "city": (["india", "indian cities"], "#india"), "country": (["countryballs", "country race"], "#countryballs")}
CTAS = ["Tumhara colour jeeta? Comment karo!", "Kaunsa colour tha tumhara? Comment!", "Sahi guess kiya? Comment karo!"]
HIST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "history.json")


def _history():
    try:
        return json.load(open(HIST, encoding="utf-8"))
    except Exception:
        return []


def pick_hook(rng, pool, hist):
    """Weighted pick that never repeats one of the last 2 race titles (identical back-to-back titles flopped)."""
    # 2026-11-12: the same title was coming back within hours (race-h0 at 13:28 and 18:17) -> no repeat in the last 8 races
    recent = [str(h.get("yt_title") or "") for h in hist if h.get("format") == "race"][-8:]
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
    last = [x.get("ab", "") for x in hist if x.get("teams")][-1:]          # never the same title family twice in a row
    cands = [h for i, h in enumerate(TEAM_HOOKS) if not (last and f"-h{i}-" in last[0])] or TEAM_HOOKS
    hk = rng.choices(cands, weights=[h[0] for h in cands])[0]
    big = " vs ".join(t["name"] for t in teams)
    if len(big) > 20: big = " vs ".join(t["abbr"] for t in teams)
    ptags, phash = POOL_TAGS[pool]
    ttags = [t["tags"][0] for t in teams] + [x for t in teams for x in t["tags"][1:2]]
    names = [t["name"] for t in teams]
    return {
        "race_kind": "team", "team_pool": pool, "teams": names, "names": names,
        "balls": [race_teams.ball_spec(t) for t in teams],
        "hook": big, "hook_sub": rng.choice(["Apni team chuno!", "Kaun jeetega? Team chuno!"]),
        "pin": rng.choice(TEAM_PINS), "ab": f"team-{pool}-h{TEAM_HOOKS.index(hk)}-{ab_variant}",
        "yt_title": {k: f"{v.format(m=m if len(f'{hk[1]}{m}{series}') < 80 else big, e=e)} | {series} #shorts"   # YouTube cuts at 95
                     for k, v in zip(("hi_roman", "en", "te", "hi"), hk[1:])},
        "desc_hook": {"hi_roman": f"{m}: finish se pehle apni team comment karo, phir dekho kaun jeeta 👀",
                      "en": f"{m}: comment your team before the finish, then watch who wins 👀",
                      "te": f"{m}: ఫినిష్ ముందే మీ టీమ్ కామెంట్ చేయండి, తర్వాత ఎవరు గెలిచారో చూడండి 👀",
                      "hi": f"{m}: फिनिश से पहले अपनी टीम कमेंट करो, फिर देखो कौन जीता 👀"},
        "question": {"hi_roman": "Tumhari team kaunsi thi? 👇", "en": "Which team did you pick? 👇",
                     "te": "మీరు ఏ టీమ్ ఎంచుకున్నారు? 👇", "hi": "तुम्हारी टीम कौनसी थी? 👇"},
        "comment": f"{series}: {m}! Finish se pehle apni team comment karo 👇 " + " / ".join(names) + "?\n"
                   "Sahi nikla? Subscribe karo, roz nayi race aati hai 🔔",
        "tags": ptags + ttags + ["ball race", "marble race", "guess the winner", "bounce bhai", "satisfying", "physics simulation", "race"],
        "hashtags": f"#shorts {phash} " + " ".join(t["hash"] for t in teams) + " #ballrace #marblerace #guessthewinner",
        "genre_tag": "#ballrace",
    }


def main(out):
    rng = random.Random()
    intense = rng.random() < 0.35   # ~1 in 3 races is an "intense" one
    jelly = rng.random() < 0.35     # ~1 in 3 races uses soft jelly balls (variety: new physics look)
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
        # parallel search (all runner cores) for the closest, most contested race; on-screen text is only the hook
        "out": out.replace(".json", ".mp4"), "seed": rng.randint(1, 10 ** 6), "tries": 400, "budget": 170,
        "hook": "JELLY RACE!" if jelly else "KAUN JEETEGA?", "intense": intense, "jelly": jelly,
        "hook_sub": sub, "ab": ab,     # 0-second hook: big line + sub-line on frame 1
        "pin": "Finish se pehle colour comment karo!",   # on-screen pinned-question (font has no emoji)
        "desc_hook": {"hi_roman": "Finish se pehle apna colour comment karo, phir dekho kaun jeeta 👀",
                      "en": "Comment your colour before the finish, then watch who wins 👀",
                      "te": "ఫినిష్ ముందే మీ రంగు కామెంట్ చేయండి, తర్వాత ఎవరు గెలిచారో చూడండి 👀",
                      "hi": "फिनिश से पहले अपना कलर कमेंट करो, फिर देखो कौन जीता 👀"},
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
    # Team race (~60%) or fan-name race; a fan race with too few fresh commenters falls back to its team overlay
    # (scripts/fan_names.py), and a pinned fan name (data/pin_names.json) turns a team race back into a fan race.
    team = team_overlay(rng, hist, series, cfg["variant"])
    if rng.random() < TEAM_SHARE:
        cfg["fan_alt"] = {k: cfg.get(k) for k in team}
        cfg.update(team)
    else:
        cfg["race_kind"] = "fan"
        if TEAM_SHARE > 0:
            cfg["team_alt"] = team
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    json.dump(cfg, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("race:", cfg["race_kind"], "INTENSE" if intense else "", "JELLY" if jelly else "", cfg["yt_title"]["hi_roman"], "seed", cfg["seed"],
          "| team fallback:" if cfg.get("team_alt") else "", (cfg.get("team_alt") or {}).get("teams", ""))


if __name__ == "__main__":
    main(sys.argv[1])
