#!/usr/bin/env python3
"""What works on Bounce Bhai: joins YouTube numbers (data branch stats.json) with data/history.json.

Used by write_story.py (feed winners/flops into the prompt, weight genres, block repeat topics)
and by make_short.sh (pick the format: animated story vs. ball-escape sim).
    python scripts/insights.py format      -> prints "story" or "sim"
    python scripts/insights.py report      -> human summary
"""
import json, math, os, random, re, sys, time, urllib.request, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HIST = os.path.join(ROOT, "data", "history.json")
STATS_URL = os.environ.get("BB_STATS_URL",
                           "https://raw.githubusercontent.com/sniff-yt/Bounce-Bhai-Shorts/data/stats.json")
MIN_AGE_H = 6          # a video needs this long before its views count

STOP = set("""the a an of and or to in on at for with from by is was are be as it its this that my your our their his her
first last lost forgotten secret secrets hidden mystery story tale legend real true truth strange amazing incredible
great little big old new one two ever never day time world thing things who what why how when where man woman boy girl
king queen failed began wrong missing broken talking unsold unfinished infinite silent vanishing unstoppable intelligent golden fun facts why
ki ka ke ek hai aur se mein jo ne kya kaise kyun wala wali bhi tha thi""".split())


def _load_history():
    try:
        return json.load(open(HIST, encoding="utf-8"))
    except Exception:
        return []


def _load_stats():
    p = os.environ.get("BB_STATS_FILE")
    try:
        if p and os.path.exists(p):
            return json.load(open(p, encoding="utf-8"))
        with urllib.request.urlopen(STATS_URL + f"?t={int(time.time())}", timeout=15) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print("insights: no stats:", e, file=sys.stderr)
        return {}


def _ts(s):
    try:
        return datetime.datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0


def videos():
    """Every known video with views, age, format, genre, topic."""
    hist = _load_history()
    by_id = {h["video_id"]: h for h in hist if h.get("video_id")}
    out = []
    for v in (_load_stats().get("videos") or _load_stats().get("recent") or []):
        h = by_id.get(v["id"], {})
        fmt = h.get("format") or ("promo" if re.search(r"bhai drive|parking|game", v["title"], re.I) else
                                  "race" if re.search(r"kaun jeetega|race|winner|🏁|🟢", v["title"], re.I) else
                                  "sim" if re.search(r"gap|nikal|escape|bahar|🔴", v["title"], re.I) else "story")
        age_h = (time.time() - _ts(v.get("published"))) / 3600
        out.append({"id": v["id"], "title": v["title"], "views": v.get("views", 0), "likes": v.get("likes", 0),
                    "age_h": age_h, "format": fmt, "genre": h.get("genre"), "topic": h.get("topic")})
    return out


def _score(vs):
    """Mean log-views with a weak prior, so one lucky video doesn't decide everything."""
    vs = [v for v in vs if v["age_h"] >= MIN_AGE_H]
    prior_n, prior = 2, math.log1p(5)
    return (sum(math.log1p(v["views"]) for v in vs) + prior_n * prior) / (len(vs) + prior_n), len(vs)


def promo_due(hours=20):
    """One Bhai Drive game promo per day (BB_PROMO=0 turns them off)."""
    if os.environ.get("BB_PROMO", "1") == "0":
        return False
    last = max([_ts(h.get("date")) for h in _load_history() if h.get("format") == "promo" and h.get("video_id")] or [0])
    return time.time() - last > hours * 3600


RACE_SHARE = float(os.environ.get("BB_RACE_SHARE", "0.85"))   # owner (2026-10-28): race Shorts get the most views -> lean in


ALLOWED_FORMATS = ("race", "sim")   # OWNER'S STRICT RULE (2026-10-25): only ball-race, ball-escape and the daily Bhai Drive game promo. No stories.


def pick_format(rng=random):
    """~85% races, ~15% ball-escapes, plus one Bhai Drive promo a day.
    Stats check (2026-10-28, videos >= 6 h old): race median 220 views (8 of 11 >= 100), sim median 8 overall /
    ~150 since 2026-10-22, promo 183. Escapes only take over if they clearly beat races on recent videos."""
    forced = os.environ.get("BB_FORMAT")
    if forced in ALLOWED_FORMATS + ("promo",):
        return forced
    if promo_due():
        return "promo"
    share = RACE_SHARE
    cutoff = time.time() - 7 * 86400
    vs = [v for v in videos() if _ts_pub(v) >= cutoff]
    (rs, rn), (ss, sn) = (_score([v for v in vs if v["format"] == f]) for f in ("race", "sim"))
    if rn >= 5 and sn >= 5 and ss > rs + 0.7:   # escapes clearly winning lately (~2x views): rebalance, still keep races
        share = 0.5
    return "race" if rng.random() < share else "sim"


def _ts_pub(v):
    return time.time() - v["age_h"] * 3600


def genre_weights(genres):
    vs = [v for v in videos() if v["format"] == "story" and v.get("genre")]
    w = {}
    for g in genres:
        s, _ = _score([v for v in vs if v["genre"] == g])
        w[g] = math.exp(s)
    return w


def prompt_block():
    """Winners and flops for the story prompt."""
    vs = [v for v in videos() if v["age_h"] >= MIN_AGE_H]
    if not vs:
        return ""
    vs.sort(key=lambda v: v["views"], reverse=True)
    top = [v for v in vs[:4] if v["views"] > 0]
    flop = [v for v in vs[-4:] if v not in top]
    lines = ["WHAT WORKS ON THIS CHANNEL (real YouTube views). Copy the style of the winners, avoid the flops' style:"]
    lines += [f'- WINNER {v["views"]} views: "{v["title"]}"' for v in top]
    lines += [f'- FLOP {v["views"]} views: "{v["title"]}"' for v in flop]
    lines.append("Winners speak directly to the viewer with a challenge or question in the first second "
                 "(\"Is gap se nikal paayegi?\"). Make the hook and yt_title do that.")
    return "\n".join(lines)


def _tokens(text):
    return {w for w in re.findall(r"[a-z]+", (text or "").lower().replace("'s", "")) if len(w) > 2 and w not in STOP}


def used_subjects(n=80):
    """Subject words already used recently (clock, ashoka, potato ...)."""
    seen = {}
    for h in _load_history()[-n:]:
        for w in _tokens(h.get("topic")) | _tokens(h.get("title")):
            seen[w] = seen.get(w, 0) + 1
    return seen


def repeats(story, n=80):
    """Subject words this story shares with recent ones (empty set = fresh topic)."""
    mine = _tokens(story.get("topic")) | _tokens(story.get("title"))
    return mine & set(used_subjects(n))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "report"
    if cmd == "format":
        print(pick_format())
    else:
        vs = videos()
        for f in ("story", "sim", "race"):
            s, n = _score([v for v in vs if v["format"] == f])
            print(f"{f}: score {s:.2f} from {n} videos")
        print(prompt_block())
        print("used subjects:", sorted(used_subjects(), key=lambda w: -used_subjects()[w])[:30])
