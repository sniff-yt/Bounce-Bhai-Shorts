#!/usr/bin/env python3
"""Bounce Bhai LONG-FORM 2D cutout renderer (1920x1080, 24 fps).

usage:
  python engine/long2d.py plan   out/long_x.json            # stage plan + SFX cue list (needs long_voice.py timings)
  python engine/long2d.py render out/long_x.json [--audio mix.wav] [--frames A-B] [--stills t1,t2] [--no-subs]

A director turns the story's scenes/lines into per-character tracks (positions + walk cycles, facing, expression
changes, gestures, held objects, lip-sync windows) and camera shots (wide establishing, medium two-shots, close-ups on
emotional lines, slow push-ins and pans, cuts on big changes), then frames are drawn with skia in parallel worker
processes, each piping its contiguous frame range into its own ffmpeg encoder; the chunks are concatenated and muxed
with the mixed audio. Overlays (subtitles in the story language, title banner, moral card, end screen) are shaped with
Pillow+raqm so Telugu/Devanagari conjuncts render correctly.
"""
import bisect, json, math, os, random, subprocess, sys, time, wave
from multiprocessing import Process

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import numpy as np
import skia
from PIL import Image, ImageDraw, ImageFont, ImageFilter

import long_cast as LC
import long_props as LP
import long_sets as LS
import visemes as VZ
from toon2d import rgb, C, paint, stroke, fill_ink, oval, rrect, poly, smooth_closed, INK

FPS = 24
W, H = 1920, 1080
FLOOR = LS.FLOOR
SCALE = 0.86
SLOTS = {"far_left": 0.1, "left": 0.28, "center": 0.5, "centre": 0.5, "middle": 0.5, "right": 0.72, "far_right": 0.9}
WALK_SPEED = 330.0
EMOTIONAL = {"cry", "angry", "surprised", "scared", "sad", "ashamed", "greedy"}
FONT_DIR = os.path.join(ROOT, "assets", "fonts")
LBL = {"te": {"moral": "నీతి", "sub": "సబ్‌స్క్రైబ్ చేయండి!", "next": "మరో కొత్త కథతో మళ్ళీ కలుద్దాం!", "story": "కథ"},
       "hi": {"moral": "सीख", "sub": "सब्सक्राइब करें!", "next": "फिर मिलेंगे एक नई कहानी के साथ!", "story": "कहानी"},
       "en": {"moral": "Moral", "sub": "Subscribe!", "next": "See you in the next story!", "story": "Story"}}


def font(lang, size, black=False):
    name = {"te": "NotoSansTelugu", "hi": "NotoSansDevanagari"}.get(lang, "NotoSans")
    for n in ([f"{name}-Black.ttf"] if black else []) + [f"{name}-Bold.ttf", "NotoSans-Bold.ttf"]:
        p = os.path.join(FONT_DIR, n)
        if os.path.exists(p):
            return ImageFont.truetype(p, size, layout_engine=ImageFont.Layout.RAQM)
    return ImageFont.load_default()


def ease(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def lerp(a, b, t):
    return a + (b - a) * t


def lerp2(a, b, t):
    return (lerp(a[0], b[0], t), lerp(a[1], b[1], t))


def pos_x(p):
    if isinstance(p, str):
        p = SLOTS.get(p.lower(), 0.5)
    try:
        p = float(p)
    except Exception:
        p = 0.5
    if p > 1.5:   # already pixels
        return p
    return 160 + max(-0.2, min(1.2, p)) * 1600


# ============================================================================================ planning
GEST = {   # hand targets (out, down) relative to each shoulder, adult units: (far/back hand, near/front hand).
           # out > 0 = away from the body centre; a NEGATIVE out on the far hand reaches forward (two-handed gestures)
    "rest": ((8, 200), (8, 200)),
    "talk_a": ((10, 196), (70, 118)), "talk_b": ((30, 172), (98, 72)), "talk_c": ((-70, 140), (62, 126)),
    "talk_d": ((8, 200), (40, 150)),
    "point": ((10, 196), (200, 38)), "give": ((10, 196), (178, 92)), "receive": ((-196, 104), (150, 90)),
    "wave": ((10, 196), (66, -150)), "cry": ((6, 198), (64, -96)), "angry": ((24, 166), (96, -112)),
    "surprised": ((112, -112), (112, -112)), "scared": ((-150, 46), (58, 40)), "think": ((22, 160), (-36, 10)),
    "hips": ((22, 164), (22, 164)), "proud": ((22, 164), (22, 164)), "celebrate": ((88, -168), (88, -168)),
    "beg": ((-168, 66), (92, 60)), "greedy": ((-26, 118), (-34, 112)), "laugh": ((12, 194), (-26, 138)),
    "scratch": ((10, 196), (40, -168)), "greet": ((-44, 64), (-50, 62)), "sad": ((4, 204), (4, 204)),
    "show": ((10, 196), (124, 6)), "stop": ((10, 196), (166, -40)), "shrug": ((82, 52), (82, 52)),
    "worried": ((22, 170), (-32, 114)), "eat": ((10, 196), (74, 66)),
}
HOLD_POSE = {"hang": (36, 168), "palm": (86, 96), "pinch": (72, 116)}
STICK_POSE = (56, 176)
GEST_D = {"rest": 0.55}   # transition time into a gesture (s)
FREE_HAND = {"give", "show", "receive", "celebrate", "wave", "point", "eat", "stop"}
ACTION_GEST = {"point": "point", "give": "give", "wave": "wave", "cry": "cry", "angry": "angry", "surprised": "surprised",
               "shocked": "surprised", "scared": "scared", "think": "think", "hips": "hips", "proud": "proud",
               "celebrate": "celebrate", "jump": "celebrate", "dance": "celebrate", "beg": "beg", "plead": "beg",
               "greedy": "greedy", "rub_hands": "greedy", "laugh": "laugh", "scratch": "scratch", "confused": "scratch",
               "greet": "greet", "namaste": "greet", "sad": "sad", "show": "show", "stop": "stop", "shrug": "shrug",
               "count": "greedy", "eat": "eat", "take": "receive", "receive": "receive", "hug": "receive",
               "bow": "greet", "shout": "angry", "scold": "point", "comfort": "receive", "work": "talk_c", "cook": "talk_c",
               "sell": "show", "call": "wave", "run": None, "walk": None, "enter": None, "exit": None, "talk": None,
               "sit": "think"}
ACTION_EXPR = {"cry": "cry", "angry": "angry", "surprised": "surprised", "shocked": "surprised", "scared": "scared",
               "laugh": "laugh", "greedy": "greedy", "celebrate": "happy", "think": "thinking", "proud": "proud",
               "beg": "worried", "sad": "sad", "confused": "thinking", "shout": "angry", "scold": "angry"}
IDLE_GEST = {"cry": "cry", "angry": "hips", "greedy": "greedy", "laugh": "laugh", "proud": "hips", "thinking": "think",
             "scared": "scared", "sad": "sad", "worried": "worried"}
TALK_PATTERNS = [["talk_a", "talk_d", "talk_b"], ["talk_b", "talk_a", "talk_d"], ["talk_c", "talk_d", "talk_a"]]
# held objects that exist once in the story world: one instance per frame (held OR placed, never both)
UNIQUE_OBJ = {"magic_pot", "gold_pot", "necklace", "key", "letter", "lamp", "coin_bag", "gift", "book", "pot", "rice_sack",
              "basket", "jar", "umbrella", "stick"}
# objects a line merely refers to (pointing at it, talking about it) stay where they are
NO_HOLD_ACTIONS = {"point", "think", "talk", "scold", "look", "angry", "shout", "cry", "surprised", "shocked", "scared",
                   "laugh", "sad", "beg", "plead", "confused", "scratch", "walk", "run", "enter", "exit", "stop", "magic"}
SEP = 300.0          # min distance between two standing characters' centres (world px)
CHAR_HALF = 112.0    # body half-width incl. relaxed arms (world px) for spacing


def stage_obj_key(name):
    """The portable object a stage prop is (so it can be picked up), or None for fixed pieces."""
    n = (name or "").lower()
    if not n or LP.cart_kind(n):
        return None
    for keys, obj in ((("magic", "jadui"), "magic_pot"), (("gold", "treasure"), "gold_pot"), (("basket",), "basket"),
                      (("sack", "grain", "rice"), "rice_sack"), (("money_bag", "coin_bag", "bag"), "coin_bag"),
                      (("lamp", "diya"), "lamp"), (("pot", "matka", "pitcher"), "pot"), (("jar",), "jar")):
        if any(k in n for k in keys):
            return obj
    return None


def char_index(story):
    return {c["id"]: c for c in story["characters"]}


def _separate(items, lo, hi):
    """items: [id, x_want, left_off, right_off] (extent relative to x). Push apart so neighbours keep their gaps
    (char-char = SEP), stay in [lo, hi] and keep their left-to-right order. Returns {id: x}."""
    items = sorted(items, key=lambda it: it[1])
    n = len(items)
    if not n:
        return {}
    xs = [it[1] for it in items]

    def gap(a, b):
        return max(SEP, a[3] - b[2] + 76)

    for _ in range(3):
        for k in range(1, n):
            xs[k] = max(xs[k], xs[k - 1] + gap(items[k - 1], items[k]))
        if xs[-1] > hi:
            xs[-1] = hi
        for k in range(n - 2, -1, -1):
            xs[k] = min(xs[k], xs[k + 1] - gap(items[k], items[k + 1]))
        if xs[0] < lo:
            xs[0] = lo
    if xs[0] < lo - 1 or xs[-1] > hi + 1:   # does not fit: spread evenly
        xs = [lo + (hi - lo) * (k + 0.5) / n for k in range(n)]
    return {it[0]: x for it, x in zip(items, xs)}


def plan_scene(story, sc, looks):
    """Tracks for every character in the scene (times absolute)."""
    chars = char_index(story)
    t0, t1 = sc["start"], sc["end"]
    cast = []
    for c in sc.get("cast") or []:
        if isinstance(c, str):
            c = {"id": c}
        if c.get("id") in chars and c["id"] not in [x["id"] for x in cast]:
            cast.append(dict(c))
    for ln in sc["lines"]:   # anyone speaking or acting must be on stage
        for cid in (ln.get("speaker"), ln.get("actor"), ln.get("target")):
            if cid in chars and cid not in [x["id"] for x in cast]:
                cast.append({"id": cid, "pos": None, "enter": cid == ln.get("speaker") and ln is not sc["lines"][0]})
    cast = cast[:5]
    n = len(cast)
    default = {1: [0.5], 2: [0.33, 0.67], 3: [0.25, 0.5, 0.75], 4: [0.17, 0.39, 0.61, 0.83], 5: [0.1, 0.3, 0.5, 0.7, 0.9]}[max(1, n)]
    want = []
    for i, c in enumerate(cast):
        p = c.get("pos")
        if isinstance(p, str):
            p = SLOTS.get(p.lower())
        try:
            p = float(p)
        except Exception:
            p = None
        want.append(default[i] if p is None or not (0 <= p <= 1) else p)
    prop = sc.get("prop")
    cart = LP.cart_kind(prop) if prop else None
    owner = sc.get("prop_owner") if sc.get("prop_owner") in [c["id"] for c in cast] else None
    if cart and not owner:
        owner = next((c["id"] for c in cast if chars[c["id"]].get("role") in ("vendor", "hero", "seller", "greedy")),
                     cast[0]["id"] if cast else None)
    # ---- standing positions: requested order, spaced so nobody overlaps anybody (or someone else's cart)
    items = []
    for i, c in enumerate(cast):
        lo_, ro_ = -CHAR_HALF, CHAR_HALF
        if cart and c["id"] == owner:
            xw = pos_x(want[i])
            cl, cr = prop_extent("cart", cart, xw, owner, looks)
            lo_, ro_ = min(lo_, cl - xw), max(ro_, cr - xw)
        items.append([c["id"], pos_x(want[i]), lo_, ro_])
    pos = _separate(items, pos_x(0.06), pos_x(0.94))
    # child cart owners stand beside the cart on the side facing the middle: the cart itself is at pos[owner]
    tracks = {}
    for c in cast:
        cid = c["id"]
        x = pos[cid]
        e0 = LC.expr_name(c.get("expression") or c.get("emotion"))
        tracks[cid] = {"keys": [(t0, x)], "walks": [], "expr": [(t0 - 1, e0)], "gest": [],
                       "hold": [(t0 - 1, LP.obj_name(c.get("holding")))],
                       "speak": [], "face": [(t0 - 1, 1 if x < 960 else -1)], "fx": [], "hidden_until": None, "gone_after": None,
                       "base": x, "hop": []}
        if c.get("enter"):
            # come in from the side with nobody standing in the way (no walking through people)
            left_clear = not any(ox < x for oc, ox in pos.items() if oc != cid)
            right_clear = not any(ox > x for oc, ox in pos.items() if oc != cid)
            from_left = left_clear if left_clear != right_clear else x < 960
            tracks[cid]["keys"] = [(t0, -260 if from_left else W + 260)]
            tracks[cid]["pending_enter"] = x
    props = []
    if cart and owner:
        props.append(("cart", cart, pos[owner], owner))
    elif prop:
        # a free spot for the prop: as far from every standing position as possible (prefers the requested side)
        stand = list(pos.values())
        l_, r_ = prop_extent("stage", prop, 0.0)
        best = None
        req = sc.get("prop_pos")
        for k in range(0, 41):
            px = pos_x(0.06 + 0.88 * k / 40)
            clear = min([abs(px - sx) - (max(-l_, r_) + CHAR_HALF + 30) for sx in stand] + [400])
            score = (min(clear, 60), -abs(px - pos_x(req)) if req is not None else -abs(px - 960) * 0.2)
            if best is None or score > best[0]:
                best = (score, px)
        props.append(("stage", prop, best[1], None))
    stage_key = stage_obj_key(prop) if (prop and not cart) else None
    obstacles = [prop_extent(pk, nm, px, own, looks) + (own,) for pk, nm, px, own in props]
    gives = []
    lines = sc["lines"]
    walk_end = {cid: -1e9 for cid in tracks}

    def free_x(cid, want_x, t_at, x_from):
        """Nearest x to want_x where cid stands clear of everybody (at t_at and later) and of props."""
        others = []
        for o, tro in tracks.items():
            if o == cid:
                continue
            others.append(_x_at(tro, t_at))
            others.append(tro["keys"][-1][1])
        best = None
        for k in range(0, 160):
            for sgn in ((1,) if k == 0 else (1, -1)):
                x = want_x + sgn * k * 12
                if not (pos_x(0.04) <= x <= pos_x(0.96)):
                    continue
                if any(abs(x - ox) < SEP - 10 for ox in others if -200 < ox < W + 200):
                    continue
                if any(l_ - CHAR_HALF - 25 < x < r_ + CHAR_HALF + 25 for l_, r_, own in obstacles if own != cid):
                    continue
                best = x
                break
            if best is not None:
                break
        return want_x if best is None else best

    for li, ln in enumerate(lines):
        ls, le = ln["start"], ln["end"]
        sp = ln.get("speaker")
        actor = sp if sp in tracks else (ln.get("actor") if ln.get("actor") in tracks else None)
        tgt = ln.get("target") if ln.get("target") in tracks and ln.get("target") != actor else None
        act = (ln.get("action") or "talk").lower().strip()
        emo = ln.get("emotion")
        if sp in tracks:
            tracks[sp]["speak"].append((ls, le, li))
        # facing: speaker faces target (or nearest), listeners face speaker
        if actor:
            ax = _x_at(tracks[actor], ls)
            if tgt is None:
                others = [o for o in tracks if o != actor and -200 < _x_at(tracks[o], ls) < W + 200]
                tgt_face = min(others, key=lambda o: abs(_x_at(tracks[o], ls) - ax)) if others else None
            else:
                tgt_face = tgt
            if tgt_face:
                tracks[actor]["face"].append((ls - 0.15, 1 if _x_at(tracks[tgt_face], ls) > ax else -1))
            for o in tracks:
                if o != actor and sp in tracks:
                    tracks[o]["face"].append((ls - 0.05 + 0.12 * (hash(o) % 3), 1 if ax > _x_at(tracks[o], ls) else -1))
        # movement
        if actor and (act in ("walk", "run", "enter", "exit") or tracks[actor].get("pending_enter") is not None):
            tr = tracks[actor]
            ws = max(ls - (0.2 if act != "enter" else 0.6), walk_end[actor] + 0.15)
            x0 = _x_at(tr, ws)
            if act == "exit":
                x1 = -300 if x0 < 960 else W + 300
            elif tr.get("pending_enter") is not None:
                x1 = tr.pop("pending_enter")
            else:
                to = ln.get("to")
                if to is None and tgt:
                    tx = _x_at(tracks[tgt], ls)
                    x1 = tx - SEP if tx > x0 else tx + SEP
                else:
                    x1 = pos_x(to if to is not None else (0.5 if abs(x0 - 960) > 200 else (0.25 if x0 > 960 else 0.75)))
            speed = WALK_SPEED * (1.8 if act == "run" else 1.0) * (0.78 if looks[actor]["kid"] else 1.0)
            dur0 = max(0.6, min(4.5, abs(x1 - x0) / speed))
            entering = x0 < -150 or x0 > W + 150
            if act != "exit":
                if not entering:
                    # don't walk through somebody standing in the way: stop beside the first one
                    for o, tro in tracks.items():
                        ox = _x_at(tro, ws)
                        if o != actor and -200 < ox < W + 200 and min(x0, x1) < ox < max(x0, x1):
                            x1 = min(x1, ox - SEP) if x1 > x0 else max(x1, ox + SEP)
                x1 = free_x(actor, x1, ws + dur0, x0)
                if entering:   # enter from the side with nobody in between
                    others = [_x_at(tro, ws) for o, tro in tracks.items() if o != actor]
                    others = [ox for ox in others if -200 < ox < W + 200]
                    lc = not any(ox < x1 for ox in others)
                    rc = not any(ox > x1 for ox in others)
                    x0 = -260 if (lc if lc != rc else x1 < 960) else W + 260
                    tr["keys"] = [(k_[0], x0) for k_ in tr["keys"] if k_[0] <= ws] or [(t0, x0)]
            x1 = max(-320, min(W + 320, x1))
            if abs(x1 - x0) > 60:
                dur = max(0.6, min(4.5, abs(x1 - x0) / speed))
                tr["keys"].append((ws, x0)); tr["keys"].append((ws + dur, x1))
                tr["keys"].sort(key=lambda a: a[0])
                tr["walks"].append((ws, ws + dur, x0, x1, 1.8 if act == "run" else 1.0))
                walk_end[actor] = ws + dur
                if act != "exit":   # arrived: turn to the person spoken to (or the nearest one)
                    te_ = ws + dur
                    near = [o for o in tracks if o != actor and -200 < _x_at(tracks[o], te_) < W + 200]
                    fo = tgt if tgt else (min(near, key=lambda o: abs(_x_at(tracks[o], te_) - x1)) if near else None)
                    if fo:
                        tr["face"].append((te_ + 0.05, 1 if _x_at(tracks[fo], te_) > x1 else -1))
                        for o in near:   # and the others look at the newcomer
                            tracks[o]["face"].append((te_ + 0.1, 1 if x1 > _x_at(tracks[o], te_) else -1))
        # expression
        e = LC.expr_name(emo) if emo else (LC.expr_name(ACTION_EXPR[act]) if act in ACTION_EXPR else None)
        if actor and e:
            tracks[actor]["expr"].append((ls - 0.1, e))
        for rid, re_ in (ln.get("reactions") or {}).items():
            if rid in tracks:
                tracks[rid]["expr"].append((ls + 0.3, LC.expr_name(re_)))
        if tgt and actor and not ln.get("reactions"):
            if e == "angry":
                tracks[tgt]["expr"].append((ls + 0.4, "worried"))
            elif e == "cry" and LC.expr_name(tracks[tgt]["expr"][-1][1]) not in ("greedy", "sly", "angry"):
                tracks[tgt]["expr"].append((ls + 0.4, "sad"))
        # gestures
        g = ACTION_GEST.get(act)
        if actor and g:
            gs = ls if act not in ("walk", "run", "enter", "exit") else ls + 0.6
            tracks[actor]["gest"].append((gs, le + 0.15, g))
            if g in ("surprised", "celebrate"):
                tracks[actor]["hop"].append(gs + 0.1)
            if g == "angry":
                tracks[actor]["fx"].append((gs, le, "steam"))
            if g == "surprised":
                tracks[actor]["fx"].append((gs, gs + 1.1, "bang"))
            if g in ("think", "scratch"):
                tracks[actor]["fx"].append((gs, le, "question"))
        if actor and (ln.get("sfx") in ("magic", "sparkle") or act == "magic"):
            tracks[actor]["fx"].append((ls, ls + 2.0, "sparkle"))
        # objects
        obj = LP.obj_name(ln.get("object"))
        if actor and obj:
            on_stage = stage_key is not None and obj == stage_key
            if act == "give" and tgt:
                gs, ge = ls + (le - ls) * 0.3, ls + (le - ls) * 0.3 + 0.9
                tracks[actor]["hold"].append((ls - 0.3, obj))
                tracks[actor]["hold"].append((gs, None))
                tracks[tgt]["hold"].append((ge, obj))
                tracks[tgt]["gest"].append((gs - 0.3, ge + 0.6, "receive"))
                tracks[tgt]["expr"].append((ge, "happy" if LC.expr_name(tracks[tgt]["expr"][-1][1]) != "greedy" else "greedy"))
                gives.append((gs, ge, obj, actor, tgt))
            elif act in ("take", "receive"):
                tracks[actor]["hold"].append((ls + 0.4, obj))
            elif act in NO_HOLD_ACTIONS and (on_stage or act in ("point", "scold", "look")):
                pass    # it's referred to, not carried: it stays where it is
            else:
                tracks[actor]["hold"].append((ls - 0.2, obj))
    for tr in tracks.values():
        for k in ("keys", "expr", "hold", "face"):
            tr[k].sort(key=lambda a: a[0])
        if tr.get("pending_enter") is not None:   # never got a line: walk in at the scene start
            x1 = tr.pop("pending_enter")
            x0 = tr["keys"][0][1]
            d = max(0.6, min(4.5, abs(x1 - x0) / WALK_SPEED))
            tr["keys"] = [(t0, x0), (t0 + 0.2, x0), (t0 + 0.2 + d, x1)] + [k for k in tr["keys"][1:] if k[0] > t0 + 0.2 + d]
            tr["walks"].append((t0 + 0.2, t0 + 0.2 + d, x0, x1, 1.0))
    _unique_holds(tracks, gives)
    return {"tracks": tracks, "props": props, "gives": gives, "owner": owner, "stage_key": stage_key}


def _unique_holds(tracks, gives):
    """A unique object is in one hand at a time: when somebody picks it up, whoever had it lets go."""
    ev = []
    for cid, tr in tracks.items():
        for t, o in tr["hold"]:
            ev.append((t, cid, o))
    ev.sort(key=lambda e: e[0])
    holder = {}
    cur = {cid: None for cid in tracks}
    adds = []
    for t, cid, o in ev:
        prev = cur[cid]
        if prev in holder and holder[prev] == cid:
            del holder[prev]
        cur[cid] = o
        if o in UNIQUE_OBJ:
            h = holder.get(o)
            if h is not None and h != cid and cur.get(h) == o:
                adds.append((h, t - 0.01))
                cur[h] = None
            holder[o] = cid
    for h, t in adds:
        tracks[h]["hold"].append((t, None))
        tracks[h]["hold"].sort(key=lambda a: a[0])


def _walk_frac(u):
    """Eased walk progress: starts and stops gently (velocity 0.5x mean at the ends, 1.5x mid-walk)."""
    u = max(0.0, min(1.0, u))
    return u - 0.5 * math.sin(2 * math.pi * u) / (2 * math.pi)


def _x_at(tr, t):
    ks = tr["keys"]
    if t <= ks[0][0]:
        return ks[0][1]
    for (ta, xa), (tb, xb) in zip(ks, ks[1:]):
        if ta <= t <= tb:
            if xa == xb:
                return xa
            return lerp(xa, xb, _walk_frac((t - ta) / max(1e-6, tb - ta)))
    return ks[-1][1] if t >= ks[-1][0] else ks[0][1]


def _last(seq, t, default=None):
    v = default
    for ts, x in seq:
        if ts <= t:
            v = x
        else:
            break
    return v


def _last2(seq, t):
    """(value, time since it started, previous value)."""
    v, since, prev = seq[0][1], 1e9, seq[0][1]
    for ts, x in seq:
        if ts <= t:
            prev, v, since = v, x, t - ts
        else:
            break
    return v, since, prev


# ============================================================================================ camera
SHOT_Z = {"wide": 1.0, "two": 1.28, "medium": 1.55, "close": 2.15}
PUSH = 1.04          # the slow push-in over a shot (z grows up to 3.5 %)
WIDE_DRIFT = 32.0


def prop_extent(kind, name, px, owner=None, looks=None):
    """World x-extent (left, right) of a stage prop or cart."""
    n = (name or "").lower()
    if kind == "cart":
        dx = cart_dx(px, owner, looks)
        return px + dx - 235 * SCALE, px + dx + 235 * SCALE
    if LP.cart_kind(n):
        return px - 235, px + 235
    half, off = 120, 0
    for key, h, o in (("scale", 190, 0), ("weigh", 190, 0), ("well", 140, 0), ("charpai", 210, 0), ("cot", 210, 0),
                      ("sack", 170, 45), ("grain", 170, 45), ("tree", 270, 0), ("magic", 75, 0), ("pot", 75, 0),
                      ("matka", 75, 0)):
        if key in n:
            half, off = h, o
            break
    return px + off - half, px + off + half


def cart_dx(px, owner, looks):
    """A child owner would vanish behind the counter: the cart stands beside them instead."""
    if not looks or not owner or looks[owner]["height"] >= 0.8:
        return 20
    return (-1 if px < W / 2 else 1) * 250 * SCALE


def clamp_cam(cx, cy, z):
    hw, hh = W / 2 / z, H / 2 / z
    cx = max(LS.X0 + 120 + hw, min(LS.X1 - 120 - hw, cx))
    cy = max(-150 + hh, min(H + 260 - hh, cy))
    return cx, cy, z


def camera_at(shots, t, scene_end):
    cur = 0
    for i, s in enumerate(shots):
        if s[0] <= t:
            cur = i
    s = shots[cur]
    ts, kind, cx, cy, z = s[:5]
    nxt = shots[cur + 1][0] if cur + 1 < len(shots) else scene_end
    prog = (t - ts) / max(0.5, nxt - ts)
    # a gentle glide from the previous shot when it is nearly the same framing, otherwise a clean cut
    if cur > 0:
        p = shots[cur - 1]
        if p[1] == kind and abs(p[4] - z) < 0.12 and abs(p[2] - cx) < 220 and abs(p[3] - cy) < 90:
            k = ease((t - ts) / 0.8)
            cx, cy, z = lerp(p[2], cx, k), lerp(p[3], cy, k), lerp(p[4], z, k)
    z *= 1 + 0.035 * max(0.0, min(1.0, prog))
    if kind == "wide":
        cx += 30 * math.sin(t / 6.0)
    return clamp_cam(cx, cy, z)


def frame_rect(cam):
    cx, cy, z = cam
    return cx - W / 2 / z, cy - H / 2 / z, cx + W / 2 / z, cy + H / 2 / z


# ============================================================================================ overlays (PIL)
def _rgba_to_skimage(im):
    a = np.ascontiguousarray(np.array(im.convert("RGBA")))
    return skia.Image.fromarray(a, colorType=skia.kRGBA_8888_ColorType)


def wrap(draw, text, fnt, maxw):
    if "\n" in text:
        return [r for part in text.split("\n") for r in wrap(draw, part, fnt, maxw)]
    words, rows, cur = text.split(), [], ""
    for w_ in words:
        cand = (cur + " " + w_).strip()
        if draw.textlength(cand, font=fnt) <= maxw or not cur:
            cur = cand
        else:
            rows.append(cur); cur = w_
    if cur:
        rows.append(cur)
    return rows


def text_card(text, lang, size, maxw, fill=(255, 255, 255), stroke_col=(0, 0, 0), sw=6, black=False, align="center",
              name=None, name_col=(255, 214, 90)):
    fnt = font(lang, size, black)
    d = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    rows = wrap(d, text, fnt, maxw)
    asc, desc = fnt.getmetrics()
    lh = int((asc + desc) * 1.12)
    widths = [d.textlength(r, font=fnt) for r in rows]
    nw = 0
    if name:
        nf = font(lang, int(size * 0.72), black)
        nw = d.textlength(name, font=nf)
    w_ = int(max(widths + [nw]) + sw * 2 + 40)
    h_ = int(lh * len(rows) + sw * 2 + 20 + (lh * 0.8 if name else 0))
    im = Image.new("RGBA", (w_, h_), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    y = sw + 6
    if name:
        dr.text((w_ / 2 - nw / 2, y), name, font=nf, fill=name_col, stroke_width=sw - 1, stroke_fill=stroke_col)
        y += int(lh * 0.8)
    for r, rw in zip(rows, widths):
        x = (w_ - rw) / 2 if align == "center" else sw + 20
        dr.text((x, y), r, font=fnt, fill=fill, stroke_width=sw, stroke_fill=stroke_col)
        y += lh
    return im


SENT_END = tuple(".!?।॥")
CLAUSE_END = tuple(",;:–—")


def _split_balanced(toks, maxc):
    """Split a token list longer than maxc at the word boundary nearest its middle (each half >= 2 words)."""
    if len(" ".join(toks)) <= maxc or len(toks) < 4:
        return [toks]
    tot = len(" ".join(toks))
    best, bk = None, None
    for k in range(2, len(toks) - 1):
        d = abs(len(" ".join(toks[:k])) - tot / 2)
        if toks[k - 1][-1:] in CLAUSE_END + SENT_END:
            d -= 6   # prefer a comma near the middle
        if best is None or d < best:
            best, bk = d, k
    return _split_balanced(toks[:bk], maxc) + _split_balanced(toks[bk:], maxc)


def chunk_tokens(text, maxc):
    """Subtitle chunks on sentence / clause boundaries, each at most maxc characters (two lines), never a lone word."""
    toks = text.split()
    if not toks:
        return []
    clauses, cur = [], []
    for tk in toks:
        cur.append(tk)
        if tk[-1:] in SENT_END + CLAUSE_END:
            clauses.append((cur, tk[-1:] in SENT_END)); cur = []
    if cur:
        clauses.append((cur, True))
    pieces = []
    for cl, sent in clauses:
        parts = _split_balanced(cl, maxc)
        for k, pt in enumerate(parts):
            pieces.append((pt, sent and k == len(parts) - 1))
    chunks, cur, cur_end = [], [], False
    for pt, sent in pieces:
        n_new = len(" ".join(cur + pt))
        if cur and (n_new > maxc or (cur_end and len(" ".join(cur)) >= maxc * 0.45)):
            chunks.append(cur); cur = []
        cur = cur + pt
        cur_end = sent
    if cur:
        chunks.append(cur)
    # no lone-word (or tiny) chunks: merge into a neighbour, splitting again only when it gets too long
    k = 0
    while len(chunks) > 1 and k < len(chunks):
        c = chunks[k]
        if len(c) >= 2 and len(" ".join(c)) >= 10:
            k += 1
            continue
        if k > 0 and (k == len(chunks) - 1 or len(" ".join(chunks[k - 1])) <= len(" ".join(chunks[k + 1]))):
            merged = chunks[k - 1] + c; at = k - 1
        else:
            merged = c + chunks[k + 1]; at = k
        repl = [merged] if len(" ".join(merged)) <= maxc * 1.25 or len(merged) < 5 else _split_balanced(merged, maxc)
        if any(len(x) < 2 for x in repl):
            repl = [merged]
        chunks[at:at + 2] = repl
        k = 0 if len(repl) > 1 else at + 1
    return chunks


def two_lines(text, max_one=40):
    """Break a chunk into 1-2 balanced lines (explicit newline)."""
    toks = text.split()
    if len(text) <= max_one or len(toks) < 2:
        return text
    best, bk = None, 1
    for k in range(1, len(toks)):
        d = abs(len(" ".join(toks[:k])) - len(" ".join(toks[k:])))
        if toks[k - 1][-1:] in CLAUSE_END + SENT_END:
            d -= 8   # a comma near the middle is the natural break
        if best is None or d < best:
            best, bk = d, k
    return " ".join(toks[:bk]) + "\n" + " ".join(toks[bk:])


def subtitle_chunks(ln, maxc):
    """Split a line into subtitle chunks timed by its word boundaries."""
    text = ln["text"]
    toks = text.split()
    words = ln.get("words") or []
    chunks = chunk_tokens(text, maxc)
    out = []
    n_tok = max(1, len(toks))
    ls, le = ln["start"], ln["end"]
    i = 0
    for ch in chunks:
        a, b = i, i + len(ch)
        if words and len(words) >= n_tok * 0.6:   # map token index to word timings proportionally
            wa = words[min(len(words) - 1, int(a * len(words) / n_tok))][0]
            wb = words[min(len(words) - 1, max(0, int(b * len(words) / n_tok) - 1))][1]
        else:
            tot = len(text)
            ca = len(" ".join(toks[:a])); cb = len(" ".join(toks[:b]))
            wa, wb = ls + (le - ls) * ca / tot, ls + (le - ls) * cb / tot
        out.append((wa, wb, " ".join(ch)))
        i = b
    # make chunks continuous
    res = []
    for k, (a, b, s) in enumerate(out):
        a = ls if k == 0 else a
        b = le + 0.25 if k == len(out) - 1 else out[k + 1][0]
        res.append((a, max(b, a + 0.5), s))
    return res


# ============================================================================================ renderer
class Renderer:
    def __init__(self, story, subs=True):
        self.story = story
        self.lang = story.get("lang", "hi")
        self.subs = subs
        seed = int(story.get("seed", 7))
        self.looks = {c["id"]: LC.make_look(c, seed * 131 + sum(map(ord, c["id"]))) for c in story["characters"]}
        self.scenes = story["scenes"]
        self.plans = [plan_scene(story, sc, self.looks) for sc in self.scenes]
        self.sets = {}
        self.cache = {}
        self.blink_seed = {cid: (sum(map(ord, cid)) % 97) / 97.0 for cid in self.looks}
        self.env = None
        self.names = {c["id"]: c.get("name", c["id"]) for c in story["characters"]}
        # subtitle chunks
        self.subchunks = []
        maxc = 80 if self.lang != "en" else 88   # two balanced lines of ~40 characters
        for sc in self.scenes:
            for ln in sc["lines"]:
                for a, b, s in subtitle_chunks(ln, maxc):
                    self.subchunks.append((a, b, s, ln.get("speaker")))
        self._vig = None
        # viseme lip-sync timeline per line (edge-tts word boundaries split into aksharas / letters)
        self.vis = {}
        for si, sc in enumerate(self.scenes):
            for li, ln in enumerate(sc["lines"]):
                words = ln.get("words") or []
                if not words and ln.get("text") and "start" in ln:   # no boundaries: share the line by word length
                    toks = ln["text"].split()
                    tot = sum(len(x) for x in toks) or 1
                    t, words = ln["start"], []
                    for x in toks:
                        d = (ln["end"] - ln["start"]) * len(x) / tot
                        words.append([t, t + d * 0.92, x]); t += d
                self.vis[(si, li)] = VZ.Track(VZ.line_keys(words, self.lang))
        self.gtracks = {(si, cid): self.build_gestures(si, cid) for si, pl in enumerate(self.plans) for cid in pl["tracks"]}
        self.shots = [self.plan_shots(si) for si in range(len(self.scenes))]

    # ---------------------------------------------------------------- audio envelope for lip-sync
    def load_env(self):
        p = self.story.get("speech_wav")
        n = int(self.story["duration"] * FPS) + 2
        if not p or not os.path.exists(p):
            self.env = np.zeros(n); return
        with wave.open(p) as w:
            sr = w.getframerate()
            a = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
        hop = sr // FPS
        m = min(n, len(a) // hop)
        env = np.zeros(n)
        env[:m] = np.sqrt((a[:m * hop].reshape(m, hop) ** 2).mean(1))
        ref = np.percentile(env[env > 0.003], 90) if np.any(env > 0.003) else 1
        env = np.clip(env / max(ref, 1e-4), 0, 1)
        out = env.copy()
        for i in range(1, n):
            out[i] = env[i] if env[i] > out[i - 1] else out[i - 1] * 0.5 + env[i] * 0.5
        out[out < 0.1] = 0
        self.env = out

    def mouth(self, t, sc, cid):
        """Viseme vector for a speaking character at time t (None when not speaking). The text-driven shape is
        scaled by the speech envelope so the mouth closes in pauses and opens wider on loud syllables."""
        tr = self.plans[sc]["tracks"][cid]
        for a, b, li in tr["speak"]:
            if a - 0.06 <= t <= b + 0.08:
                v = self.vis[(sc, li)].sample(t)
                f = int(t * FPS)
                e = self.env[f] if self.env is not None and f < len(self.env) else 0.6
                if self.env is not None:
                    e = max(e, self.env[f + 1] if f + 1 < len(self.env) else 0)   # one frame look-ahead
                g = max(0.0, min(1.0, (e - 0.04) / 0.22))
                v = VZ.blend(VZ.REST, v, g)
                v["open"] *= 0.75 + 0.35 * min(1.0, e)
                return v
        return None

    def speaking(self, t, sc, cid):
        return any(a - 0.1 <= t <= b + 0.1 for a, b, _ in self.plans[sc]["tracks"][cid]["speak"])

    # ---------------------------------------------------------------- gesture timelines (eased keyframes)
    def build_gestures(self, sc_i, cid):
        tr = self.plans[sc_i]["tracks"][cid]
        sc = self.scenes[sc_i]
        segs = []
        for gs, ge, g in tr["gest"]:
            segs.append((gs, ge + 0.25, g, 3))
        for a, b, li in tr["speak"]:
            pat = TALK_PATTERNS[li % len(TALK_PATTERNS)]
            n = max(1, int(round((b - a) / 2.6)))
            for k in range(n):
                segs.append((a + (b - a) * k / n, a + (b - a) * (k + 1) / n + (0.3 if k == n - 1 else 0), pat[k % len(pat)], 2))
        ex = tr["expr"]
        for k, (ts, e) in enumerate(ex):
            te = ex[k + 1][0] if k + 1 < len(ex) else sc["end"] + 1
            g = IDLE_GEST.get(LC.expr_name(e))
            if g:
                segs.append((ts + 0.2, te, g, 1))
        bounds = sorted({x for sg in segs for x in (sg[0], sg[1])})
        keys, cur = [], "rest"
        for a, b in zip(bounds, bounds[1:]):
            mid = (a + b) / 2
            act = [sg for sg in segs if sg[0] <= mid < sg[1]]
            g = max(act, key=lambda sg: (sg[3], sg[0]))[2] if act else "rest"
            if g != cur:
                keys.append([a, g]); cur = g
        # no flicker: a pose held for less than 0.45 s is skipped (the previous one carries on)
        clean = []
        for k, (t_, g) in enumerate(keys):
            nxt = keys[k + 1][0] if k + 1 < len(keys) else 1e9
            if nxt - t_ < 0.45 and g in ("rest", "talk_a", "talk_b", "talk_c", "talk_d") and clean:
                continue
            if clean and clean[-1][1] == g:
                continue
            clean.append((t_, g))
        out, prev_t, prev_from, prev_g = [], -1e9, GEST["rest"], "rest"
        for t_, g in clean:
            k = ease((t_ - prev_t) / GEST_D.get(prev_g, 0.4))
            frm = (lerp2(prev_from[0], GEST[prev_g][0], k), lerp2(prev_from[1], GEST[prev_g][1], k))
            out.append((t_, g, frm))
            prev_t, prev_from, prev_g = t_, frm, g
        return out

    def gesture_at(self, sc_i, cid, t):
        """(back hand, front hand, gesture, weight) with eased transitions between keyframes."""
        keys = self.gtracks[(sc_i, cid)]
        i = bisect.bisect_right([k[0] for k in keys], t) - 1
        if i < 0:
            return GEST["rest"][0], GEST["rest"][1], "rest", 1.0
        t_, g, frm = keys[i]
        k = ease((t - t_) / GEST_D.get(g, 0.4))
        tl, tr_ = GEST[g]
        return lerp2(frm[0], tl, k), lerp2(frm[1], tr_, k), g, k

    # ---------------------------------------------------------------- camera planning (heads in frame)
    def geoms(self, sc_i, t):
        out = {}
        for cid in self.plans[sc_i]["tracks"]:
            P = self.pose(t, sc_i, cid)
            if -500 < P["x"] < W + 500:
                g = LC.geometry(self.looks[cid], P)
                g["walking"] = P.get("_walking", False)
                out[cid] = g
        return out

    def plan_shots(self, sc_i):
        sc = self.scenes[sc_i]
        tracks = self.plans[sc_i]["tracks"]
        wants = [(sc["start"], "wide", (), None, None)]
        for li, ln in enumerate(sc["lines"]):
            sp = ln.get("speaker")
            actor = sp if sp in tracks else ln.get("actor") if ln.get("actor") in tracks else None
            emo = LC.expr_name(ln.get("emotion")) if ln.get("emotion") else None
            act = ln.get("action") or ""
            t = ln["start"]
            if actor is None:
                kind = "wide"
            elif act in ("walk", "run", "enter", "exit", "give"):
                kind = "two" if len(tracks) > 1 else "wide"
            elif ln.get("close") or (emo in EMOTIONAL and emo != "sad") or (emo == "sad" and li % 2 == 0) or act in ("cry",):
                kind = "close"
            else:
                kind = "medium" if li % 3 != 2 else "two"
            subj = ()
            if actor:
                tgt = ln.get("target") if ln.get("target") in tracks and ln.get("target") != actor else None
                if tgt is None:
                    ax = _x_at(tracks[actor], t + 0.3)
                    near = [o for o in tracks if o != actor and -100 < _x_at(tracks[o], t + 0.3) < W + 100]
                    if near:
                        tgt = min(near, key=lambda o: abs(_x_at(tracks[o], t + 0.3) - ax))
                subj = (actor,) + ((tgt,) if tgt else ())
            if li == 0 and kind != "wide" and t - sc["start"] < 1.2:
                wants[0] = (sc["start"], "wide", (), None, None)
            arrive = None
            if actor and act in ("walk", "run", "enter"):
                ends = [we for ws, we, *_ in tracks[actor]["walks"] if ws <= t + 0.8 and we >= t - 0.3]
                arrive = max(ends) if ends else None
            wants.append((t - 0.05, kind, subj, actor, arrive))
        if sc.get("moral_card"):
            wants.append((sc["lines"][-1]["start"] - 0.05, "wide", (), None, None))
        shots = []
        for k, (ts, kind, subj, actor, arrive) in enumerate(wants):
            te = wants[k + 1][0] if k + 1 < len(wants) else sc["end"]
            if te - ts < 0.05:
                continue
            ta = min(te - 0.15, arrive) if arrive and arrive > ts else ts   # a walker is framed where they arrive
            cam = self.solve_shot(sc_i, kind, subj, ta, te)
            shots.append((ts, cam[3]) + cam[:3])
        return shots

    def solve_shot(self, sc_i, kind, subj, ta, tb):
        """Pick (cx, cy, z, kind) so every visible character's head is fully in frame or the character is fully out;
        the subjects (speaker + the one spoken to) are always in. Zooms out step by step until it works."""
        n = max(2, min(14, int((tb - ta) / 0.35) + 1))
        samples = [ta + 0.06 + (tb - ta - 0.12) * k / (n - 1) for k in range(n)]
        G = [self.geoms(sc_i, t) for t in samples]
        props = [prop_extent(pk, nm, px, own, self.looks) for pk, nm, px, own in self.plans[sc_i]["props"]]
        if not any(G):
            return (960.0, 540.0, 1.0, kind)
        z0 = SHOT_Z[kind]
        zs = []
        for f in (1.0, 0.93, 0.86, 0.79, 0.72, 0.65, 0.58, 0.5):
            if z0 * f >= 1.0:
                zs.append(z0 * f)
        if not zs or zs[-1] > 1.0:
            zs.append(1.0)
        subj = tuple(c for c in subj if c in G[0])
        if subj:
            hx = [G[0][c]["head"][0] for c in subj]
            pref = hx[0] if len(hx) == 1 else (hx[0] * 0.6 + hx[1] * 0.4 if kind in ("close", "medium") else sum(hx) / len(hx))
        else:
            xs = [g["x"] for g in G[0].values() if -100 < g["x"] < W + 100]
            pref = max(820, min(1100, sum(xs) / len(xs))) if xs else 960
        drift = WIDE_DRIFT if kind == "wide" else 0.0
        best = None
        for zi, z in enumerate(zs):
            zin = z * PUSH
            hw_in = W / 2 / zin - (14 + drift) / zin
            hw_out = W / 2 / z + drift
            hh = H / 2 / zin
            cands = {pref}
            for g in G:
                for cid, c in g.items():
                    l_, r_ = c["reach"]
                    hl, ht, hr, hb = c["head_box"]
                    bl, _, br, _ = c["body"]
                    cands |= {l_ - hw_out - 2, r_ + hw_out + 2, hl + hw_in + 1, hr - hw_in - 1, bl + hw_in + 1, br - hw_in - 1}
            for l_, r_ in props:
                cands |= {l_ + hw_in + 1, r_ - hw_in - 1, l_ - hw_out - 2, r_ + hw_out + 2}
            for cx in cands:
                if abs(cx - pref) > 950:
                    continue
                res = self._eval_cam(cx, z, kind, subj, G, props, hw_in, hw_out, hh)
                if res is None:
                    continue
                soft, cy = res
                cx2, cy2, _ = clamp_cam(cx, cy, z)
                if abs(cx2 - cx) > 1 or abs(cy2 - cy) > 1:
                    res = self._eval_cam(cx2, z, kind, subj, G, props, hw_in, hw_out, hh, cy_fixed=cy2)
                    if res is None:
                        continue
                    soft = res[0]
                key = (soft, zi, abs(cx2 - pref))
                if best is None or key < best[0]:
                    best = (key, (cx2, cy2, z, kind))
            if best and best[0][0] == 0:
                break
        if best is None:
            if subj and len(subj) > 1:
                return self.solve_shot(sc_i, kind, subj[:1], ta, tb)
            if subj:
                return self.solve_shot(sc_i, "wide" if kind != "wide" else kind, (), ta, tb) if kind != "wide" else (960.0, 540.0, 1.0, "wide")
            return (960.0, 540.0, 1.0, kind)
        return best[1]

    def _eval_cam(self, cx, z, kind, subj, G, props, hw_in, hw_out, hh, cy_fixed=None):
        Li, Ri, Lo, Ro = cx - hw_in, cx + hw_in, cx - hw_out, cx + hw_out
        soft = 0
        top, bottom = 1e9, -1e9
        for g in G:
            for cid, c in g.items():
                l_, r_ = c["reach"]
                hl, ht, hr, hb = c["head_box"]
                bl, _, br, _ = c["body"]
                out = r_ <= Lo or l_ >= Ro
                head_in = hl >= Li and hr <= Ri
                if cid in subj and not head_in:
                    return None
                if out:
                    continue
                if not head_in:
                    if c["walking"]:      # entering / leaving through the side of the frame
                        soft += 1
                        continue
                    return None
                top = min(top, ht)
                bottom = max(bottom, hb)
                if not (bl >= Li - 4 and br <= Ri + 4):
                    soft += 1
        for l_, r_ in props:
            if not (l_ >= Li and r_ <= Ri) and r_ > Lo and l_ < Ro:
                soft += 1
        if cy_fixed is not None:
            cy = cy_fixed
        elif kind == "wide" or top > 1e8:
            cy = max(540.0 + (0 if z <= 1.0 else 0), FLOOR + 60 - hh) if kind == "wide" else 540.0
            if top < 1e8:
                cy = min(cy, top - 0.05 * 2 * hh + hh)
        else:
            cy = top - 0.06 * 2 * hh + hh
        if top < 1e8:
            if top < cy - hh + 2 or bottom > cy + hh - 6:
                return None
        return soft, cy

    # ---------------------------------------------------------------- per-character pose
    def pose(self, t, sc_i, cid):
        tr = self.plans[sc_i]["tracks"][cid]
        look = self.looks[cid]
        P = LC.rest_pose()
        P["scale"] = SCALE
        P["y"] = FLOOR
        s = SCALE * look["height"]
        x = _x_at(tr, t)
        P["x"] = x
        bs = self.blink_seed[cid]
        walking = None
        for ws, we, x0, x1, sp in tr["walks"]:
            if ws <= t <= we:
                walking = (ws, we, x0, x1, sp)
        P["_walking"] = walking is not None
        # facing, with a quick cut-out turn (squash through the middle) when it changes
        if walking:
            face, since, prev = (1 if walking[3] > walking[2] else -1), 1e9, None
            pf = _last(tr["face"], walking[0] - 1e-3, 1)
            if t - walking[0] < 0.16 and pf != face:
                since, prev = t - walking[0], pf
        else:
            face, since, prev = _last2(tr["face"], t)
            # coming out of a walk: turn from the walking direction
            for ws, we, x0, x1, sp in tr["walks"]:
                if we <= t < we + 0.16:
                    wf = 1 if x1 > x0 else -1
                    if wf != face:
                        since, prev = t - we, wf
        if prev is not None and prev != face and since < 0.16:
            u = ease(since / 0.16)
            f = lerp(prev, face, u)
            P["facing"] = (1 if f >= 0 else -1) * max(0.25, abs(f))
            P["_turn_blink"] = math.sin(min(1.0, since / 0.16) * math.pi)
        else:
            P["facing"] = face
        # expression with a short blend
        e, since_e, preve = _last2(tr["expr"], t)
        k = ease(since_e / 0.3)
        A, B = LC.EXPR[LC.expr_name(preve)], LC.EXPR[LC.expr_name(e)]
        for key in A:
            P[key] = lerp(A[key], B[key], k)
        ename = LC.expr_name(e)
        period = 3.1 + bs * 2.2
        ph = (t + bs * 7) % period
        if ph < 0.13:
            P["blink"] = math.sin(ph / 0.13 * math.pi)
        # idle life: breathing (chest), slow weight shift (hips) and sway (lean); feet stay planted
        P["breath"] = math.sin(t * 2 * math.pi / 3.6 + bs * 6)
        P["hip_shift"] = 3.0 * math.sin(t * 0.55 + bs * 5)
        P["lean"] = 0.8 * math.sin(t * 0.45 + bs * 3)
        P["dip"] = 1.5 + 1.5 * math.sin(t * 2 * math.pi / 3.6 + bs * 6 + 1.2)
        if P.get("_turn_blink"):   # people blink as they turn their head
            P["blink"] = max(P["blink"], P["_turn_blink"])
        if (t + bs * 13) % 17.0 < 0.34:   # an occasional double blink
            u = ((t + bs * 13) % 17.0) / 0.34
            P["blink"] = max(P["blink"], abs(math.sin(u * 2 * math.pi)))
        # eyes: small saccades (look around a little, then back to the person in front)
        seg = int((t + bs * 5) / 2.3)
        hsh = (seg * 2654435761 + int(bs * 1000)) % 1000 / 1000.0
        gx = 0.35 + (0.22 * (hsh - 0.5) if hsh > 0.45 else 0.0)
        gy = (0.05 if ename != "sad" else 0.5) + (0.12 * (hsh - 0.7) if hsh > 0.7 else 0.0)
        P["gaze"] = (gx, gy)
        P["head_turn"] = 0.4
        P["head_tilt"] = {"sad": 6, "cry": 8, "ashamed": 9, "proud": -5, "thinking": 6, "greedy": -3, "worried": 4}.get(ename, 0)
        P["head_tilt"] += 1.5 * math.sin(t * 0.9 + bs * 4)
        speaking = self.speaking(t, sc_i, cid)
        if speaking:   # talkers nod and lift their brows a little as they speak
            P["head_tilt"] += 2.2 * math.sin(t * 3.7 + bs * 2) * (1 if ename not in ("cry", "sad") else 0.5)
            P["brow_up"] += 0.18 * max(0.0, math.sin(t * 1.9 + bs * 4))
        vis = self.mouth(t, sc_i, cid)
        P["vis"] = vis
        P["mouth"] = vis["open"] if vis else 0.0
        if vis is None:   # listeners: lips closed, an occasional small idle part of the lips
            ph = (t + bs * 11) % 9.0
            if 4.0 < ph < 4.7 and P.get("o_mouth", 0) < 0.2 and P.get("grin", 0) < 0.5:
                P["mouth"] = 0.0
                P["vis"] = dict(VZ.REST, open=0.07 * math.sin((ph - 4.0) / 0.7 * math.pi), width=0.95)
        if ename == "laugh" and not speaking:
            P["vis"] = None
            P["mouth"] = max(P["mouth"], 0.45 + 0.3 * math.sin(t * 22))
            P["dip"] += 5 * abs(math.sin(t * 11))
        if ename == "cry":
            P["dip"] += 2.5 * abs(math.sin(t * 8.5))
            if not speaking:
                P["vis"] = None
                P["mouth"] = max(P["mouth"], 0.2 + 0.1 * math.sin(t * 9))
        if ename == "scared":
            P["hip_shift"] += 2.5 * math.sin(t * 41)
        P["highlight"] = 1.0 if speaking else 0.0
        # ---- arms: eased gesture keyframes
        lh, rh, g, gk = self.gesture_at(sc_i, cid, t)
        if g == "wave":
            rh = (rh[0] + 26 * math.sin(t * 11) * gk, rh[1])
        elif g == "angry":
            rh = (rh[0] + 6 * math.sin(t * 22) * gk, rh[1] + 8 * math.sin(t * 22) * gk)
            P["fistr"] = gk > 0.5
        elif g == "greedy":
            rh = (rh[0] + 12 * math.sin(t * 12) * gk, rh[1] + 4 * math.sin(t * 24) * gk)
        elif g.startswith("talk"):
            rh = (rh[0] + 10 * math.sin(t * 2.3 + bs * 5) * gk, rh[1] + 9 * math.sin(t * 3.1 + bs * 3) * gk)
        elif g == "beg":
            P["lean"] += 6 * gk
        elif g == "celebrate":
            lh = (lh[0], lh[1] + 16 * math.sin(t * 10) * gk); rh = (rh[0], rh[1] - 16 * math.sin(t * 10) * gk)
        elif g == "cry":
            rh = (rh[0] + 4 * math.sin(t * 6), rh[1] + 6 * math.sin(t * 6))
            P["fistr"] = True
        elif g == "hips":
            P["fistl"] = P["fistr"] = gk > 0.6
        # breathing moves the hands a little with the shoulders
        lh = (lh[0], lh[1] - 2 * P["breath"]); rh = (rh[0], rh[1] - 2 * P["breath"])
        # ---- held object locks the near hand into a carrying pose (unless the gesture uses that hand)
        hold, hsince, _ = _last2(tr["hold"], t)
        hold = LP.obj_name(hold) if hold else None
        P["hold"] = hold
        if hold and g not in FREE_HAND:
            grip = LC.GRIP.get(hold, ("pinch", 0, 0))[0]
            hp = HOLD_POSE[grip]
            kh = ease(min(hsince, 5.0) / 0.3) if hsince < 1e8 else 1.0
            rh = lerp2(rh, hp, kh)
        if look.get("stick"):
            lh = STICK_POSE
        # an outstretched hand stops short of the person in front (no arms through bodies)
        if not walking and rh[0] > 40:
            ahead = [abs(_x_at(o, t) - x) for oc, o in self.plans[sc_i]["tracks"].items()
                     if oc != cid and (_x_at(o, t) - x) * (1 if P["facing"] >= 0 else -1) > 0]
            if ahead:
                d = LC.dims(look)
                k_ = (d["up"] + d["lo"]) / 214.0
                allowed = ((min(ahead) - 135) / s - (d["sh_x"] - 12) - d["hand_r"]) / k_
                if rh[0] > allowed:
                    rh = (max(30.0, allowed), rh[1])
        # ---- walking: procedural strides from the distance travelled (feet never skate)
        if walking:
            ws, we, x0, x1, sp = walking
            leg = 230.0 if not look["kid"] else 160.0
            dist_w = abs(x - x0)
            total_w = abs(x1 - x0)
            dl, Dl = dist_w / s, total_w / s
            speed_l = Dl / max(0.3, we - ws)
            step = min(leg * ((0.8 if look["kid"] else 0.68) if sp <= 1 else 0.85), max(leg * 0.3, speed_l / (1.9 if sp <= 1 else 2.6)))
            phase = (dl / (2 * step) + 0.25) % 1.0
            w_end = max(0.0, min(1.0, (Dl - dl) / (step * 0.5)))
            w_lift = min(1.0, dl / (step * 0.3) + 0.15) * w_end
            vert = leg * 0.975
            need = 0.0
            for key, p0 in (("rf", phase), ("lf", (phase + 0.5) % 1.0)):
                if p0 < 0.5:
                    off, lift = step / 2 - (p0 / 0.5) * step, 0.0
                else:
                    q = (p0 - 0.5) / 0.5
                    off, lift = -step / 2 + ease(q) * step, math.sin(q * math.pi) * leg * 0.16
                off *= w_end
                P[key] = (off, lift * w_lift)
                if lift * w_lift < 1:
                    need = max(need, vert - math.sqrt(max(1.0, leg * leg - off * off)) + 2)
            php = phase - 0.25
            P["dip"] = max(P["dip"], 7 * math.sin(2 * math.pi * php) ** 2 * w_end, need)
            P["lean"] += 3.5 * (1 if sp <= 1 else 2.2)
            if g in ("rest", "sad", "worried") or g.startswith("talk") or gk < 0.3:
                sw = math.sin(2 * math.pi * phase) * 34 * w_end
                if not look.get("stick"):
                    lh = (8 - sw * 0.9, 198 - abs(sw) * 0.25)
                if not hold:
                    rh = (8 + sw * 0.9, 198 - abs(sw) * 0.25)
        # ---- hops (surprise / joy): the whole puppet leaves the ground, with anticipation and landing squash
        for hs in tr["hop"]:
            if hs - 0.12 <= t < hs:
                u = (t - hs + 0.12) / 0.12
                P["dip"] = max(P["dip"], 18 * math.sin(u * math.pi / 2))
            elif hs <= t <= hs + 0.45:
                u = (t - hs) / 0.45
                P["hop"] = 40 * math.sin(u * math.pi)
                P["squash"] = -0.2 * math.sin(u * math.pi)
            elif hs + 0.45 < t <= hs + 0.6:
                u = (t - hs - 0.45) / 0.15
                P["dip"] = max(P["dip"], 14 * math.sin(u * math.pi))
        P["lh"], P["rh"] = lh, rh
        return P

    # ---------------------------------------------------------------- frame
    def get_set(self, i):
        if i not in self.sets:
            sc = self.scenes[i]
            self.sets[i] = LS.Set(sc.get("set"), sc.get("time", "day"), sc.get("weather", "clear"), seed=i * 13 + 5)
        return self.sets[i]

    def scene_at(self, t):
        for i, sc in enumerate(self.scenes):
            if t < sc["end"]:
                return i
        return len(self.scenes) - 1

    def draw_scene(self, cv, i, t, endscreen=False):
        sc = self.scenes[i]
        st = self.get_set(i)
        plan = self.plans[i]
        if endscreen:
            cam = (960, 540, 1.0)
        else:
            cam = camera_at(self.shots[i], t, sc["end"])
        st.draw_back(cv, cam, t)
        cv.save()
        st.layer_xform(cv, cam, 1.0)
        tracks = plan["tracks"]
        ids = list(tracks.keys())
        if endscreen:
            ids = list(self.looks.keys())[:5]
        poses = {}
        for cid in ids:
            if endscreen:
                P = LC.rest_pose(); P["scale"] = SCALE; P["y"] = FLOOR
                n = len(ids); k = ids.index(cid)
                P["x"] = 960 + (k - (n - 1) / 2) * 300
                P.update(LC.EXPR["happy"]); P["rh"] = (66 + 26 * math.sin(t * 10 + k), -150); P["mouth"] = 0.0
                P["facing"] = 1 if P["x"] < 960 else -1
                P["breath"] = math.sin(t * 2 + k)
            else:
                P = self.pose(t, i, cid)
            poses[cid] = P
        owner = plan.get("owner")
        order = sorted(poses.keys(), key=lambda c: (0 if c == owner else 1, 1 if poses[c].get("_walking") else 0, poses[c]["x"]))
        # a portable stage prop (the magic pot ...) is not on the floor while somebody holds it or it is mid-air
        key = plan.get("stage_key")
        taken = key is not None and not endscreen and (
            any(LP.obj_name(P.get("hold")) == key for P in poses.values()) or
            any(gs <= t <= ge and obj == key for gs, ge, obj, a, b in plan["gives"]))
        for kind, name, px, own in plan["props"]:
            if kind == "stage" and not endscreen and not taken:
                LP.draw_stage_prop(cv, name, px, FLOOR + 4, t)
        for cid in order:
            P = poses[cid]
            if -400 < P["x"] < W + 400:
                LC.draw_character(cv, self.looks[cid], P, t)
                if not endscreen:
                    self.draw_fx(cv, cid, P, t, i)
            if cid == owner and not endscreen:
                for kind, name, px, own in plan["props"]:
                    if kind == "cart":
                        LP.draw_cart(cv, name, px + cart_dx(px, cid, self.looks), FLOOR + 30, t, s=SCALE)
        if not endscreen:
            for gs, ge, obj, a, b in plan["gives"]:
                if gs <= t <= ge and a in poses and b in poses:
                    u = ease((t - gs) / (ge - gs))
                    ha = self._hand_world(poses[a], self.looks[a])
                    hb = self._hand_world(poses[b], self.looks[b])
                    x = lerp(ha[0], hb[0], u); y = lerp(ha[1], hb[1], u) - 120 * math.sin(u * math.pi)
                    LP.draw_object(cv, obj, x, y, SCALE * LC.HELD_SCALE.get(obj, 1.0), t)
        cv.restore()
        st.draw_front(cv, cam, t)
        st.grade(cv, t)

    def _hand_world(self, P, look):
        return LC.geometry(look, P)["hands"]["r"]

    def draw_fx(self, cv, cid, P, t, i):
        tr = self.plans[i]["tracks"][cid]
        look = self.looks[cid]
        s = P["scale"] * look["height"]
        hx, hy = P["x"], P["y"] - 640 * s - 20
        for fs, fe, kind in tr["fx"]:
            if not (fs <= t <= fe + 0.2):
                continue
            a = min(1.0, (t - fs) / 0.2, (fe + 0.2 - t) / 0.2)
            if kind == "steam":
                for k in range(3):
                    ph = (t * 1.4 + k / 3) % 1.0
                    sx = hx + (k - 1) * 60 * s
                    cv.drawCircle(sx + 10 * math.sin(ph * 8), hy + 30 - ph * 120, (14 + ph * 26) * s,
                                  paint((250, 250, 250), int(200 * (1 - ph) * a)))
            elif kind == "bang":
                u = min(1, (t - fs) / 0.25)
                cv.save(); cv.translate(hx + 90 * s * P["facing"], hy - 30); cv.scale(u, u)
                fill_ink(cv, poly([(-12, -60), (12, -60), (6, 10), (-6, 10)]), rgb("ffd23a"), w=4)
                fill_ink(cv, oval(0, 30, 11, 11), rgb("ffd23a"), w=4)
                cv.restore()
            elif kind == "question":
                cv.save(); cv.translate(hx + 80 * s * P["facing"], hy - 20 + 6 * math.sin(t * 3))
                q = skia.Path(); q.moveTo(-22, -30); q.cubicTo(-22, -70, 30, -70, 26, -36); q.cubicTo(24, -16, 0, -14, 0, 6)
                cv.drawPath(q, stroke(INK, 18, a=int(255 * a))); cv.drawPath(q, stroke(rgb("ffffff"), 10, a=int(255 * a)))
                cv.drawCircle(0, 28, 9, paint(rgb("ffffff"), int(255 * a)))
                cv.restore()
            elif kind == "sparkle":
                # around the magic object in the hand if there is one (never across the face), else around the body
                if P.get("hold"):
                    gx, gy = self._hand_world(P, look)
                    gy += 40 * s
                    rad = 0.7
                else:
                    gx, gy, rad = P["x"], P["y"] - 230 * s, 1.0
                for k in range(10):
                    ang = k * 0.628 + t * 1.5
                    r = (120 + 50 * math.sin(t * 3 + k)) * rad
                    x, y = gx + math.cos(ang) * r * s, gy + math.sin(ang) * r * s * 0.8
                    sz = 10 + 6 * math.sin(t * 8 + k)
                    cv.drawPath(poly([(x, y - sz * 2), (x + sz * 0.5, y - sz * 0.5), (x + sz * 2, y), (x + sz * 0.5, y + sz * 0.5),
                                      (x, y + sz * 2), (x - sz * 0.5, y + sz * 0.5), (x - sz * 2, y), (x - sz * 0.5, y - sz * 0.5)]),
                                paint(rgb("fff2a8"), int(230 * a)))

    # ---------------------------------------------------------------- overlays
    def overlay(self, cv, t):
        st = self.story
        # title banner (first seconds)
        if 0.8 <= t <= 6.0:
            im = self._cached("title", lambda: self._banner(st.get("title", ""), 64))
            a = min(1.0, (t - 0.8) / 0.4, (6.0 - t) / 0.5)
            y = 40 - 30 * (1 - ease((t - 0.8) / 0.4))
            self._blit(cv, im, (W - im.width()) / 2, y, a)
        # moral card
        msc = next((sc for sc in self.scenes if sc.get("moral_card")), None)
        if msc:
            ml = msc["lines"][-1]
            if ml["start"] - 0.2 <= t <= msc["end"]:
                im = self._cached("moral", self._moral_card)
                a = min(1.0, (t - ml["start"] + 0.2) / 0.5)
                sc_ = 0.92 + 0.08 * ease((t - ml["start"] + 0.2) / 0.5)
                cv.save(); cv.translate(W / 2, H * 0.42); cv.scale(sc_, sc_)
                self._blit(cv, im, -im.width() / 2, -im.height() / 2, a)
                cv.restore()
        # end screen
        es = st.get("end_screen")
        if es and t >= es[0]:
            im = self._cached("end", self._end_card)
            a = min(1.0, (t - es[0]) / 0.5)
            self._blit(cv, im, (W - im.width()) / 2, 120, a)
        # subtitles
        moral_on = msc is not None and t >= msc["lines"][-1]["start"] - 0.2
        if self.subs and not (es and t >= es[0]) and not moral_on:
            for k, (a_, b_, s, sp) in enumerate(self.subchunks):
                if a_ <= t < b_:
                    im = self._cached(("sub", k), lambda s=s, sp=sp: self._subtitle(s, sp))
                    self._blit(cv, im, (W - im.width()) / 2, H - im.height() - 36, 1.0)
                    break
        wm = self._cached("wm", lambda: _rgba_to_skimage(text_card("Bounce Bhai", "en", 30, 600, fill=(255, 255, 255),
                                                                   stroke_col=(40, 30, 60), sw=4)))
        self._blit(cv, wm, 18, 14, 0.75)
        if self._vig is None:
            v = skia.Paint()
            v.setShader(skia.GradientShader.MakeRadial(skia.Point(W / 2, H / 2), 1150, [C((0, 0, 0), 0), C((0, 0, 0), 0), C((0, 0, 0), 95)],
                                                        [0.0, 0.62, 1.0]))
            self._vig = v
        cv.drawRect(skia.Rect.MakeWH(W, H), self._vig)

    def _cached(self, key, fn):
        if key not in self.cache:
            r = fn()
            self.cache[key] = r if isinstance(r, skia.Image) else _rgba_to_skimage(r)
        return self.cache[key]

    def _blit(self, cv, im, x, y, a):
        p = skia.Paint(AntiAlias=True)
        p.setAlphaf(max(0.0, min(1.0, a)))
        cv.drawImage(im, x, y, skia.SamplingOptions(skia.FilterMode.kLinear), p)

    def _subtitle(self, s, sp):
        name = self.names.get(sp) if sp and sp != "narrator" else None
        card = text_card(two_lines(s, 40 if self.lang != "en" else 46), self.lang, 48, 1500, sw=6, name=name)
        bg = Image.new("RGBA", card.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(bg)
        d.rounded_rectangle([0, 0, card.width - 1, card.height - 1], radius=26, fill=(10, 8, 20, 120))
        bg.alpha_composite(card)
        return bg

    def _banner(self, text, size):
        card = text_card(text, self.lang, size, 1500, fill=(255, 245, 210), stroke_col=(90, 20, 10), sw=7, black=True)
        w_, h_ = card.width + 80, card.height + 30
        bg = Image.new("RGBA", (w_, h_), (0, 0, 0, 0))
        d = ImageDraw.Draw(bg)
        d.rounded_rectangle([4, 4, w_ - 5, h_ - 5], radius=40, fill=(196, 40, 52, 235), outline=(255, 205, 70, 255), width=7)
        bg.alpha_composite(card, (40, 15))
        return bg

    def _moral_card(self):
        lb = LBL.get(self.lang, LBL["en"])
        head = text_card(lb["moral"], self.lang, 74, 1200, fill=(255, 214, 70), stroke_col=(80, 30, 0), sw=7, black=True)
        body = text_card(self.story.get("moral", ""), self.lang, 54, 1220, fill=(255, 255, 255), stroke_col=(40, 20, 50), sw=6)
        w_ = max(head.width, body.width) + 140
        h_ = head.height + body.height + 90
        im = Image.new("RGBA", (w_, h_), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle([6, 6, w_ - 7, h_ - 7], radius=46, fill=(70, 30, 110, 230), outline=(255, 205, 70, 255), width=10)
        d.rounded_rectangle([24, 24, w_ - 25, h_ - 25], radius=34, outline=(255, 235, 160, 160), width=3)
        for cx in (52, w_ - 52):   # little lamp-flower motifs in the corners
            for cy in (52, h_ - 52):
                d.ellipse([cx - 14, cy - 14, cx + 14, cy + 14], fill=(255, 170, 40, 255))
                d.ellipse([cx - 6, cy - 6, cx + 6, cy + 6], fill=(220, 40, 60, 255))
        im.alpha_composite(head, ((w_ - head.width) // 2, 28))
        im.alpha_composite(body, ((w_ - body.width) // 2, 40 + head.height))
        return im

    def _end_card(self):
        lb = LBL.get(self.lang, LBL["en"])
        a = text_card(lb["sub"], self.lang, 84, 1500, fill=(255, 255, 255), stroke_col=(150, 10, 20), sw=9, black=True)
        b = text_card(lb["next"], self.lang, 46, 1500, fill=(255, 240, 200), stroke_col=(40, 20, 50), sw=6)
        w_ = max(a.width, b.width) + 60
        im = Image.new("RGBA", (w_, a.height + b.height + 40), (0, 0, 0, 0))
        im.alpha_composite(a, ((w_ - a.width) // 2, 0))
        im.alpha_composite(b, ((w_ - b.width) // 2, a.height + 20))
        return im

    # ---------------------------------------------------------------- one full frame
    def frame(self, cv, t):
        es = self.story.get("end_screen")
        if es and t >= es[0]:
            self.draw_scene(cv, len(self.scenes) - 1, t, endscreen=True)
            self.overlay(cv, t)
            return
        i = self.scene_at(t)
        self.draw_scene(cv, i, t)
        # crossfade into the next scene across the boundary (0.5 s each side)
        XF = 0.45
        if i + 1 < len(self.scenes) and t > self.scenes[i]["end"] - XF:   # first half: the next scene fades in
            a = (t - (self.scenes[i]["end"] - XF)) / (2 * XF)
            if a > 0.01:
                surf = skia.Surface(W, H)
                c2 = surf.getCanvas()
                self.draw_scene(c2, i + 1, t)
                p = skia.Paint(); p.setAlphaf(min(1.0, a))
                cv.drawImage(surf.makeImageSnapshot(), 0, 0, skia.SamplingOptions(), p)
        if i > 0 and t < self.scenes[i]["start"] + XF:
            a = 1 - (t - (self.scenes[i]["start"] - XF)) / (2 * XF)
            if a > 0.01:
                surf = skia.Surface(W, H)
                c2 = surf.getCanvas()
                self.draw_scene(c2, i - 1, t)
                p = skia.Paint(); p.setAlphaf(min(1.0, a))
                cv.drawImage(surf.makeImageSnapshot(), 0, 0, skia.SamplingOptions(), p)
        self.overlay(cv, t)


# ============================================================================================ entry points
def plan_cmd(path):
    """Write SFX cues (footsteps, gives, scene whooshes, ambience, thunder) for long_audio.py."""
    story = json.load(open(path, encoding="utf-8"))
    r = Renderer(story, subs=False)
    cues = []
    for i, (sc, pl) in enumerate(zip(r.scenes, r.plans)):
        st = LS.set_name(sc.get("set"))
        amb = []
        indoor = st in LS.INDOOR
        if sc.get("weather") == "rain":
            amb.append("rain")
        if sc.get("time") == "night":
            amb.append("crickets" if not indoor else "night_room")
        elif not indoor and sc.get("weather") != "rain":
            amb.append("birds")
        if st == "river":
            amb.append("water")
        if st == "market":
            amb.append("crowd")
        if st == "house_interior":
            amb.append("fire")
        cues.append({"t": sc["start"], "end": sc["end"], "type": "ambience", "names": amb})
        if i > 0:
            cues.append({"t": sc["start"] - 0.25, "type": "whoosh"})
        if sc.get("weather") == "rain":
            k = math.ceil(sc["start"] / 9.0)
            while k * 9 < sc["end"]:
                cues.append({"t": k * 9 + 0.35, "type": "thunder"}); k += 1
        for cid, tr in pl["tracks"].items():
            for ws, we, x0, x1, sp in tr["walks"]:
                n = int((we - ws) / (0.29 / sp))
                for k in range(n):
                    tt = ws + k * 0.29 / sp
                    cues.append({"t": round(tt, 3), "type": "step", "x": (_x_at(tr, tt) - 960) / 960})
            for hs in tr["hop"]:
                cues.append({"t": hs, "type": "boing"})
        for gs, ge, obj, a, b in pl["gives"]:
            cues.append({"t": ge - 0.1, "type": "coins" if obj in ("coin", "coins", "coin_bag", "gold_pot", "money") else "pop"})
        for ln in sc["lines"]:
            s = (ln.get("sfx") or "").lower()
            if s and s != "none":
                cues.append({"t": ln["start"] - 0.15, "type": s})
            if ln.get("object") in ("coins", "coin_bag", "gold_pot", "coin") and ln.get("action") not in ("give",) and not s:
                cues.append({"t": ln["start"] + 0.2, "type": "coins"})
        if sc.get("moral_card"):
            cues.append({"t": sc["lines"][-1]["start"] - 0.25, "type": "ding"})
    es = story.get("end_screen")
    if es:
        cues.append({"t": es[0], "type": "ding"})
    story["sfx_cues"] = sorted(cues, key=lambda c: c["t"])
    story["scene_moods"] = [[sc["start"], sc["end"], sc.get("mood", "calm")] for sc in story["scenes"]]
    json.dump(story, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"plan: {len(cues)} sfx cues", flush=True)


def _worker(path, f0, f1, out, subs):
    story = json.load(open(path, encoding="utf-8"))
    r = Renderer(story, subs=subs)
    r.load_env()
    arr = np.zeros((H, W, 4), np.uint8)
    surf = skia.Surface(arr, colorType=skia.kRGBA_8888_ColorType, alphaType=skia.kPremul_AlphaType)
    cv = surf.getCanvas()
    ff = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}",
                           "-r", str(FPS), "-i", "-", "-an", "-c:v", "libx264", "-preset", os.environ.get("BB_X264", "veryfast"),
                           "-tune", "animation", "-crf", "20", "-pix_fmt", "yuv420p", "-g", "48", out],
                          stdin=subprocess.PIPE)
    t0 = time.time()
    for f in range(f0, f1):
        cv.clear(skia.ColorBLACK)
        r.frame(cv, f / FPS)
        surf.flushAndSubmit() if hasattr(surf, "flushAndSubmit") else None
        ff.stdin.write(arr.tobytes())
        if (f - f0) % 600 == 0 and f > f0:
            el = time.time() - t0
            print(f"  worker {f0}-{f1}: {f - f0}/{f1 - f0} frames, {el / (f - f0) * 1000:.0f} ms/frame", flush=True)
    ff.stdin.close()
    if ff.wait() != 0:
        raise SystemExit(f"ffmpeg failed for chunk {out}")


def render_cmd(path, audio=None, frames=None, stills=None, subs=True):
    story = json.load(open(path, encoding="utf-8"))
    base = path[:-5]
    n = int(story["duration"] * FPS)
    if stills:
        r = Renderer(story, subs=subs)
        r.load_env()
        outs = []
        for k, ts in enumerate(stills):
            arr = np.zeros((H, W, 4), np.uint8)
            surf = skia.Surface(arr, colorType=skia.kRGBA_8888_ColorType, alphaType=skia.kPremul_AlphaType)
            r.frame(surf.getCanvas(), ts)
            p = f"{base}_still_{k:02d}.png"
            Image.fromarray(arr[:, :, :3]).save(p)
            outs.append(p)
        print("stills:", outs)
        return outs
    f0, f1 = (0, n) if not frames else frames
    workers = int(os.environ.get("BB_WORKERS", os.cpu_count() or 2))
    t0 = time.time()
    bounds = [f0 + (f1 - f0) * k // workers for k in range(workers + 1)]
    chunks = [f"{base}_chunk{k:02d}.mp4" for k in range(workers)]
    ps = [Process(target=_worker, args=(path, bounds[k], bounds[k + 1], chunks[k], subs)) for k in range(workers)]
    for p in ps:
        p.start()
    for p in ps:
        p.join()
    if any(p.exitcode != 0 for p in ps):
        raise SystemExit("a render worker failed")
    lst = base + "_chunks.txt"
    open(lst, "w").write("".join(f"file '{os.path.abspath(c)}'\n" for c in chunks))
    out = base + ".mp4"
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst]
    if audio and os.path.exists(audio):
        cmd += ["-ss", f"{f0 / FPS:.3f}", "-i", audio, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
                "-shortest"]
    else:
        cmd += ["-c", "copy"]
    import shutil, tempfile
    tmp = os.path.join(tempfile.gettempdir(), os.path.basename(out))   # some mounted filesystems break faststart
    cmd += ["-movflags", "+faststart", tmp]
    subprocess.run(cmd, check=True)
    shutil.move(tmp, out)
    for c in chunks:
        os.remove(c)
    os.remove(lst)
    el = time.time() - t0
    info = {"frames": f1 - f0, "seconds": round(el), "ms_per_frame": round(el / max(1, f1 - f0) * 1000 * workers),
            "workers": workers}
    json.dump(info, open(out + ".render.json", "w"))
    print(f"::notice title=render::{f1 - f0} frames in {el / 60:.1f} min with {workers} workers -> {out}", flush=True)
    return out


if __name__ == "__main__":
    cmd, path = sys.argv[1], sys.argv[2]
    args = sys.argv[3:]
    if cmd == "plan":
        plan_cmd(path)
    else:
        audio = args[args.index("--audio") + 1] if "--audio" in args else None
        frames = tuple(int(x) for x in args[args.index("--frames") + 1].split("-")) if "--frames" in args else None
        stills = [float(x) for x in args[args.index("--stills") + 1].split(",")] if "--stills" in args else None
        render_cmd(path, audio, frames, stills, subs="--no-subs" not in args)
