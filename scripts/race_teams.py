#!/usr/bin/env python3
"""Team races (owner, 2026-11-08): the 3 race balls carry team labels so the race has stakes.
Pools rotate: IPL teams, Indian states / cities, countries. Names and colours only (no logos, no artwork):
balls get the team's colours as simple painted bands / a dot / a cross. The physics still decides the winner;
the team -> ball assignment is random and never touches the simulation.

pick_team_race(rng, hist) -> dict(pool, teams=[{name, abbr, col, flag}], ...) used by scripts/make_race.py.
"""
import colorsys

# flag = {"dir": "h"|"v", "bands": [[r,g,b], ...], "w": [weights]?, "dot": [r,g,b]?, "cross": [r,g,b]?}
# col = the ball's main colour (glow, trail, chips, tags); bright enough to read on the dark navy background.
IPL = [
    dict(name="CSK", abbr="CSK", col=(255, 204, 0), flag=dict(dir="h", bands=[(255, 204, 0), (30, 90, 200), (255, 204, 0)], w=[.4, .2, .4]),
         tags=["csk", "chennai super kings", "dhoni"], hash="#csk"),
    dict(name="MI", abbr="MI", col=(40, 120, 255), flag=dict(dir="h", bands=[(30, 100, 235), (230, 190, 70), (30, 100, 235)], w=[.4, .2, .4]),
         tags=["mi", "mumbai indians", "rohit sharma"], hash="#mi"),
    dict(name="RCB", abbr="RCB", col=(240, 40, 50), flag=dict(dir="h", bands=[(235, 35, 45), (25, 25, 30), (235, 35, 45)], w=[.4, .2, .4]),
         tags=["rcb", "royal challengers bengaluru", "virat kohli"], hash="#rcb"),
    dict(name="KKR", abbr="KKR", col=(150, 90, 230), flag=dict(dir="h", bands=[(120, 70, 200), (235, 190, 60), (120, 70, 200)], w=[.4, .2, .4]),
         tags=["kkr", "kolkata knight riders"], hash="#kkr"),
    dict(name="SRH", abbr="SRH", col=(255, 120, 20), flag=dict(dir="h", bands=[(255, 115, 15), (25, 25, 30), (255, 115, 15)], w=[.4, .2, .4]),
         tags=["srh", "sunrisers hyderabad", "orange army"], hash="#srh"),
    dict(name="DC", abbr="DC", col=(60, 140, 255), flag=dict(dir="h", bands=[(40, 110, 230), (225, 40, 50), (40, 110, 230)], w=[.4, .2, .4]),
         tags=["dc", "delhi capitals"], hash="#dc"),
    dict(name="RR", abbr="RR", col=(240, 60, 150), flag=dict(dir="h", bands=[(235, 50, 140), (30, 60, 160), (235, 50, 140)], w=[.4, .2, .4]),
         tags=["rr", "rajasthan royals"], hash="#rr"),
    dict(name="PBKS", abbr="PBKS", col=(230, 30, 60), flag=dict(dir="h", bands=[(225, 30, 55), (200, 200, 210), (225, 30, 55)], w=[.4, .2, .4]),
         tags=["pbks", "punjab kings"], hash="#pbks"),
    dict(name="GT", abbr="GT", col=(90, 140, 220), flag=dict(dir="h", bands=[(40, 70, 140), (215, 180, 90), (40, 70, 140)], w=[.4, .2, .4]),
         tags=["gt", "gujarat titans"], hash="#gt"),
    dict(name="LSG", abbr="LSG", col=(0, 190, 230), flag=dict(dir="h", bands=[(0, 175, 220), (255, 110, 40), (0, 175, 220)], w=[.4, .2, .4]),
         tags=["lsg", "lucknow super giants"], hash="#lsg"),
]

# States and cities have no official colours: distinct bright colours, plain two-tone band.
def _st(name, abbr, col, tag):
    dark = tuple(int(c * 0.55) for c in col)
    return dict(name=name, abbr=abbr, col=col, flag=dict(dir="h", bands=[col, (245, 245, 250), col], w=[.42, .16, .42]),
                tags=[tag], hash="#" + tag.replace(" ", ""), _dark=dark)

STATES = [
    _st("TELANGANA", "TG", (255, 80, 160), "telangana"), _st("ANDHRA", "AP", (40, 190, 255), "andhra pradesh"),
    _st("TAMIL NADU", "TN", (255, 70, 60), "tamil nadu"), _st("MAHARASHTRA", "MH", (255, 150, 30), "maharashtra"),
    _st("KARNATAKA", "KA", (255, 215, 0), "karnataka"), _st("KERALA", "KL", (40, 220, 110), "kerala"),
    _st("DELHI", "DL", (150, 100, 255), "delhi"), _st("PUNJAB", "PB", (0, 200, 200), "punjab"),
    _st("GUJARAT", "GJ", (255, 120, 200), "gujarat"), _st("BENGAL", "WB", (120, 230, 60), "west bengal"),
]
CITIES = [
    _st("HYDERABAD", "HYD", (255, 80, 160), "hyderabad"), _st("MUMBAI", "MUM", (40, 160, 255), "mumbai"),
    _st("CHENNAI", "CHE", (255, 215, 0), "chennai"), _st("BENGALURU", "BLR", (255, 70, 60), "bengaluru"),
    _st("DELHI", "DEL", (150, 100, 255), "delhi"), _st("KOLKATA", "KOL", (40, 220, 110), "kolkata"),
    _st("PUNE", "PUNE", (255, 150, 30), "pune"), _st("VIZAG", "VIZ", (0, 210, 210), "vizag"),
    _st("JAIPUR", "JAI", (255, 120, 200), "jaipur"), _st("LUCKNOW", "LKO", (120, 230, 60), "lucknow"),
]

W_, R_, G_, B_ = (245, 245, 250), (230, 40, 50), (20, 160, 80), (40, 90, 220)
COUNTRIES = [
    dict(name="INDIA", abbr="IND", col=(255, 153, 51), flag=dict(dir="h", bands=[(255, 153, 51), W_, (19, 160, 60)], dot=(30, 60, 160)), tags=["india"], hash="#india"),
    dict(name="PAKISTAN", abbr="PAK", col=(30, 200, 100), flag=dict(dir="v", bands=[W_, (10, 120, 60)], w=[.28, .72]), tags=["pakistan"], hash="#pakistan"),
    dict(name="AUSTRALIA", abbr="AUS", col=(255, 205, 0), flag=dict(dir="h", bands=[(0, 130, 70), (255, 205, 0), (0, 130, 70)], w=[.3, .4, .3]), tags=["australia"], hash="#australia"),
    dict(name="ENGLAND", abbr="ENG", col=(235, 235, 245), flag=dict(dir="h", bands=[W_], cross=(215, 30, 45)), tags=["england"], hash="#england"),
    dict(name="USA", abbr="USA", col=(70, 120, 255), flag=dict(dir="h", bands=[(40, 60, 150), R_, W_, R_, W_, R_], w=[.3, .14, .14, .14, .14, .14]), tags=["usa", "america"], hash="#usa"),
    dict(name="JAPAN", abbr="JPN", col=(255, 90, 110), flag=dict(dir="h", bands=[W_], dot=(220, 20, 50)), tags=["japan"], hash="#japan"),
    dict(name="BRAZIL", abbr="BRA", col=(60, 220, 90), flag=dict(dir="h", bands=[(0, 155, 60)], dot=(255, 215, 0)), tags=["brazil"], hash="#brazil"),
    dict(name="GERMANY", abbr="GER", col=(255, 200, 40), flag=dict(dir="h", bands=[(25, 25, 30), (220, 0, 20), (255, 200, 0)]), tags=["germany"], hash="#germany"),
    dict(name="FRANCE", abbr="FRA", col=(90, 140, 255), flag=dict(dir="v", bands=[(0, 60, 170), W_, (235, 40, 55)]), tags=["france"], hash="#france"),
    dict(name="ITALY", abbr="ITA", col=(40, 200, 110), flag=dict(dir="v", bands=[(0, 146, 70), W_, (206, 43, 55)]), tags=["italy"], hash="#italy"),
    dict(name="BANGLADESH", abbr="BAN", col=(20, 190, 110), flag=dict(dir="h", bands=[(0, 106, 78)], dot=(244, 42, 65)), tags=["bangladesh"], hash="#bangladesh"),
    dict(name="CHINA", abbr="CHN", col=(240, 50, 40), flag=dict(dir="h", bands=[(222, 41, 16)], dot=(255, 222, 0)), tags=["china"], hash="#china"),
    dict(name="ARGENTINA", abbr="ARG", col=(110, 190, 255), flag=dict(dir="h", bands=[(116, 172, 223), W_, (116, 172, 223)]), tags=["argentina"], hash="#argentina"),
    dict(name="CANADA", abbr="CAN", col=(255, 60, 70), flag=dict(dir="v", bands=[(216, 6, 33), W_, (216, 6, 33)], w=[.27, .46, .27], dot=(216, 6, 33)), tags=["canada"], hash="#canada"),
]

POOLS = {"ipl": IPL, "state": STATES, "city": CITIES, "country": COUNTRIES}
GROUP = {"ipl": "ipl", "state": "india", "city": "india", "country": "country"}   # rotation groups


def _hue(c):
    return colorsys.rgb_to_hsv(*(x / 255 for x in c))


def distinct(a, b):
    """Two ball colours a viewer can tell apart while they fly (hue gap, or a big brightness gap)."""
    ha, sa, va = _hue(a); hb, sb, vb = _hue(b)
    dh = min(abs(ha - hb), 1 - abs(ha - hb))
    if sa < 0.25 or sb < 0.25:               # a white-ish ball (England) vs any saturated colour
        return abs(sa - sb) > 0.4
    return dh > 0.09 and sum((x - y) ** 2 for x, y in zip(a, b)) > 9000


def pick_teams(rng, pool, avoid=(), anchor=None):
    for _ in range(400):
        t = rng.sample(pool, 3)
        if anchor and anchor not in t:
            t[rng.randrange(3)] = anchor
            if len({x["name"] for x in t}) < 3: continue
        if all(distinct(t[i]["col"], t[j]["col"]) for i in range(3) for j in range(i + 1, 3)):
            if {x["name"] for x in t} not in avoid:
                return t
    return rng.sample(pool, 3)


def pick_team_race(rng, hist):
    """Rotate pool groups: never the same group as the last team race (ipl -> india -> country ...)."""
    team = [h for h in hist if h.get("format") == "race" and h.get("teams")]
    last_grp = GROUP.get((team[-1].get("team_pool") if team else ""), "")
    groups = [g for g in ("ipl", "india", "country") if g != last_grp]
    grp = rng.choice(groups)
    pool_key = grp if grp != "india" else rng.choice(["state", "city"])
    avoid = [set(h["teams"]) for h in team[-6:]]
    # Indian audience: India is in ~70% of country races (India vs Pakistan vs Australia ...)
    anchor = COUNTRIES[0] if pool_key == "country" and rng.random() < 0.7 else None
    teams = pick_teams(rng, POOLS[pool_key], avoid, anchor)
    return pool_key, teams


def ball_spec(t):
    """What engine/sim_race.py needs per ball (JSON-safe)."""
    f = dict(t["flag"]); f["bands"] = [list(b) for b in f["bands"]]
    for k in ("dot", "cross"):
        if f.get(k): f[k] = list(f[k])
    return {"name": t["name"], "abbr": t["abbr"], "col": list(t["col"]), "flag": f}
