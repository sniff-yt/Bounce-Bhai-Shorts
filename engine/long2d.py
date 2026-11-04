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
import json, math, os, random, subprocess, sys, time, wave
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
GEST = {   # hand targets (out, down) for (left/back hand, right/front hand)
    "rest": ((16, 205), (16, 205)),
    "talk_a": ((16, 205), (120, 110)), "talk_b": ((60, 150), (95, 70)), "talk_c": ((70, 120), (70, 120)),
    "point": ((16, 205), (225, 5)), "give": ((16, 205), (195, 55)), "receive": ((120, 80), (170, 60)),
    "wave": ((16, 205), (80, -150)), "cry": ((-18, -116), (-18, -116)), "angry": ((45, 105), (60, -120)),
    "surprised": ((115, -140), (115, -140)), "scared": ((20, -70), (20, -70)), "think": ((-30, 95), (-28, -72)),
    "hips": ((45, 105), (45, 105)), "proud": ((45, 105), (45, 105)), "celebrate": ((100, -170), (100, -170)),
    "beg": ((120, 40), (120, 40)), "greedy": ((-34, 72), (-34, 72)), "laugh": ((-30, 95), (40, 70)),
    "scratch": ((16, 205), (10, -190)), "greet": ((-56, 40), (-56, 40)), "sad": ((10, 200), (10, 200)),
    "show": ((16, 205), (160, -20)), "stop": ((16, 205), (170, -60)), "shrug": ((95, 40), (95, 40)),
}
ACTION_GEST = {"point": "point", "give": "give", "wave": "wave", "cry": "cry", "angry": "angry", "surprised": "surprised",
               "shocked": "surprised", "scared": "scared", "think": "think", "hips": "hips", "proud": "proud",
               "celebrate": "celebrate", "jump": "celebrate", "dance": "celebrate", "beg": "beg", "plead": "beg",
               "greedy": "greedy", "rub_hands": "greedy", "laugh": "laugh", "scratch": "scratch", "confused": "scratch",
               "greet": "greet", "namaste": "greet", "sad": "sad", "show": "show", "stop": "stop", "shrug": "shrug",
               "count": "greedy", "eat": "show", "take": "receive", "receive": "receive", "hug": "receive",
               "bow": "greet", "shout": "angry", "scold": "point", "comfort": "receive", "work": "talk_c", "cook": "talk_c",
               "sell": "show", "call": "wave", "run": None, "walk": None, "enter": None, "exit": None, "talk": None,
               "sit": "think"}
ACTION_EXPR = {"cry": "cry", "angry": "angry", "surprised": "surprised", "shocked": "surprised", "scared": "scared",
               "laugh": "laugh", "greedy": "greedy", "celebrate": "happy", "think": "thinking", "proud": "proud",
               "beg": "worried", "sad": "sad", "confused": "thinking", "shout": "angry", "scold": "angry"}


def char_index(story):
    return {c["id"]: c for c in story["characters"]}


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
    # ---- positions: requested, then spread to avoid overlaps
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
    order = sorted(range(n), key=lambda i: want[i])
    gap = 0.2 if n <= 4 else 0.18
    xs = [want[i] for i in order]
    for k in range(1, n):
        xs[k] = max(xs[k], xs[k - 1] + gap)
    if n and xs[-1] > 0.92:
        sh = xs[-1] - 0.92
        xs = [x - sh for x in xs]
    for k in range(n - 2, -1, -1):
        xs[k] = min(xs[k], xs[k + 1] - gap)
    if n and xs[0] < 0.08:   # too crowded: spread evenly
        xs = default[:n]
    pos = {cast[order[k]]["id"]: pos_x(xs[k]) for k in range(n)}
    tracks = {}
    for c in cast:
        cid = c["id"]
        x = pos[cid]
        e0 = LC.expr_name(c.get("expression") or c.get("emotion"))
        tracks[cid] = {"keys": [(t0, x)], "walks": [], "expr": [(t0 - 1, e0)], "gest": [], "hold": [(t0 - 1, LP.obj_name(c.get("holding")))],
                       "speak": [], "face": [(t0 - 1, 1 if x < 960 else -1)], "fx": [], "hidden_until": None, "gone_after": None,
                       "base": x, "hop": []}
        if c.get("enter"):
            tracks[cid]["hidden_until"] = None
            tracks[cid]["keys"] = [(t0, -260 if x < 960 else W + 260)]
            tracks[cid]["pending_enter"] = x
    props = []
    if cart and owner:
        props.append(("cart", cart, pos[owner], owner))
    elif prop:
        px = pos_x(sc.get("prop_pos", 0.5 if not cast else (0.86 if max(pos.values()) < 1300 else 0.14)))
        props.append(("stage", prop, px, None))
    gives = []
    lines = sc["lines"]
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
                others = [o for o in tracks if o != actor]
                if others:
                    tgt_face = min(others, key=lambda o: abs(_x_at(tracks[o], ls) - ax))
                else:
                    tgt_face = None
            else:
                tgt_face = tgt
            if tgt_face:
                tracks[actor]["face"].append((ls - 0.15, 1 if _x_at(tracks[tgt_face], ls) > ax else -1))
            for o in tracks:
                if o != actor and sp in tracks:
                    tracks[o]["face"].append((ls - 0.1, 1 if ax > _x_at(tracks[o], ls) else -1))
        # movement
        if actor and (act in ("walk", "run", "enter", "exit") or tracks[actor].get("pending_enter") is not None):
            tr = tracks[actor]
            x0 = _x_at(tr, ls)
            if act == "exit":
                x1 = -300 if x0 < 960 else W + 300
                tr["gone_after"] = None
            elif tr.get("pending_enter") is not None:
                x1 = tr.pop("pending_enter")
            else:
                to = ln.get("to")
                if to is None and tgt:
                    tx = _x_at(tracks[tgt], ls)
                    x1 = tx - 250 if tx > x0 else tx + 250
                else:
                    x1 = pos_x(to if to is not None else (0.5 if abs(x0 - 960) > 200 else (0.25 if x0 > 960 else 0.75)))
            # never walk onto another character
            for o in tracks:
                if o != actor:
                    ox = _x_at(tracks[o], ls)
                    if abs(ox - x1) < 230:
                        x1 = ox - 240 if x0 < ox else ox + 240
            x1 = max(-320, min(W + 320, x1))
            speed = WALK_SPEED * (1.8 if act == "run" else 1.0)
            dur = max(0.5, min(3.2, abs(x1 - x0) / speed))
            ws = ls - (0.2 if act != "enter" else 0.6)
            tr["keys"].append((ws, x0)); tr["keys"].append((ws + dur, x1))
            tr["walks"].append((ws, ws + dur, x0, x1, 1.8 if act == "run" else 1.0))
            tr["face"].append((ws - 0.01, 1 if x1 > x0 else -1))
            if act != "exit" and tgt:
                tr["face"].append((ws + dur, 1 if _x_at(tracks[tgt], ls) > x1 else -1))
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
                tracks[actor]["hop"].append(gs)
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
            else:
                tracks[actor]["hold"].append((ls - 0.2, obj))
    for tr in tracks.values():
        for k in ("keys", "expr", "hold", "face"):
            tr[k].sort(key=lambda a: a[0])
        if tr.get("pending_enter") is not None:   # never got a line: walk in at the scene start
            x1 = tr.pop("pending_enter")
            x0 = tr["keys"][0][1]
            tr["keys"] = [(t0, x0), (t0 + 0.2, x0), (t0 + 0.2 + abs(x1 - x0) / WALK_SPEED, x1)]
            tr["walks"].append((t0 + 0.2, t0 + 0.2 + abs(x1 - x0) / WALK_SPEED, x0, x1, 1.0))
    return {"tracks": tracks, "props": props, "gives": gives, "owner": owner}


def _x_at(tr, t):
    ks = tr["keys"]
    if t <= ks[0][0]:
        return ks[0][1]
    for (ta, xa), (tb, xb) in zip(ks, ks[1:]):
        if ta <= t <= tb:
            return lerp(xa, xb, (t - ta) / max(1e-6, tb - ta))
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
def plan_shots(story, sc, plan, looks):
    """List of (t_start, kind, cx, cy, z) keyed shots for a scene."""
    tracks = plan["tracks"]
    shots = []
    t0 = sc["start"]

    def wide(t):
        xs = [_x_at(tr, t) for tr in tracks.values() if 0 < _x_at(tr, t) < W]
        cx = sum(xs) / len(xs) if xs else 960
        return (max(820, min(1100, cx)), 520, 1.0)

    def head_y(cid):
        return FLOOR - 640 * SCALE * looks[cid]["height"] + 90

    shots.append((t0, "wide") + wide(t0 + 1.0))
    last_kind = "wide"
    md = 0
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
            md += 1
            kind = "medium" if md % 3 else "two"
        if kind == "wide":
            shot = wide(t + 0.5)
        else:
            ax = _x_at(tracks[actor], ln["end"] if act in ("walk", "run", "enter") else t + 0.2)
            tgt = ln.get("target") if ln.get("target") in tracks else None
            if tgt is None and len(tracks) > 1:
                tgt = min((o for o in tracks if o != actor), key=lambda o: abs(_x_at(tracks[o], t) - ax))
            tx = _x_at(tracks[tgt], t) if tgt else ax
            if kind == "close":
                face = 1 if tx >= ax else -1
                shot = (ax + face * 50, head_y(actor) + 70, 2.05)
            elif kind == "medium":
                shot = (ax * 0.72 + tx * 0.28, head_y(actor) + 150, 1.5)
            else:
                cx = (ax + tx) / 2
                span = abs(ax - tx) + 520
                z = max(1.0, min(1.35, W / span))
                shot = (cx, 560 - (z - 1) * 60, z)
        if kind in ("medium", "two"):   # keep every visible head inside the frame (a tall man next to a child)
            cx_, cy_, z_ = shot
            hw_ = W / 2 / z_
            tops = [head_y(c) - 120 for c, tr in tracks.items() if abs(_x_at(tr, t + 0.2) - cx_) < hw_ + 60]
            if tops:
                shot = (cx_, min(cy_, min(tops) - 40 + H / 2 / z_), z_)
        shots.append((t - 0.05, kind) + shot)
        last_kind = kind
    if sc.get("moral_card"):
        shots.append((sc["lines"][-1]["start"] - 0.05, "wide") + wide(sc["lines"][-1]["start"]))
    return shots


def clamp_cam(cx, cy, z):
    hw, hh = W / 2 / z, H / 2 / z
    cx = max(LS.X0 + 120 + hw, min(LS.X1 - 120 - hw, cx))
    cy = max(-150 + hh, min(H + 260 - hh, cy))
    return cx, cy, z


def camera_at(shots, t, scene_end):
    # find current shot
    cur = 0
    for i, s in enumerate(shots):
        if s[0] <= t:
            cur = i
    s = shots[cur]
    ts, kind, cx, cy, z = s
    nxt = shots[cur + 1][0] if cur + 1 < len(shots) else scene_end
    prog = (t - ts) / max(0.5, nxt - ts)
    # smooth move from the previous shot when it's a gentle change, else hard cut
    if cur > 0:
        p = shots[cur - 1]
        big = abs(p[4] - z) > 0.4 or (p[1] == "close") != (kind == "close")
        if not big:
            k = ease((t - ts) / 0.8)
            cx, cy, z = lerp(p[2], cx, k), lerp(p[3], cy, k), lerp(p[4], z, k)
    # life: slow push-in and drift
    z *= 1 + 0.035 * max(0.0, min(1.0, prog))
    if kind == "wide":
        cx += 30 * math.sin(t / 6.0)
    return clamp_cam(cx, cy, z)


# ============================================================================================ overlays (PIL)
def _rgba_to_skimage(im):
    a = np.ascontiguousarray(np.array(im.convert("RGBA")))
    return skia.Image.fromarray(a, colorType=skia.kRGBA_8888_ColorType)


def wrap(draw, text, fnt, maxw):
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


def subtitle_chunks(ln, maxc):
    """Split a line into subtitle chunks timed by its word boundaries."""
    text = ln["text"]
    toks = text.split()
    words = ln.get("words") or []
    chunks, cur = [], []
    for tk in toks:
        if cur and len(" ".join(cur + [tk])) > maxc:
            chunks.append(cur); cur = []
        cur.append(tk)
        if tk[-1:] in ".!?।" and len(" ".join(cur)) > maxc * 0.5:
            chunks.append(cur); cur = []
    if cur:
        chunks.append(cur)
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
        self.shots = [plan_shots(story, sc, pl, self.looks) for sc, pl in zip(self.scenes, self.plans)]
        self.sets = {}
        self.cache = {}
        self.blink_seed = {cid: (sum(map(ord, cid)) % 97) / 97.0 for cid in self.looks}
        self.env = None
        self.names = {c["id"]: c.get("name", c["id"]) for c in story["characters"]}
        # subtitle chunks
        self.subchunks = []
        maxc = 56 if self.lang != "en" else 64
        for sc in self.scenes:
            for ln in sc["lines"]:
                for a, b, s in subtitle_chunks(ln, maxc):
                    self.subchunks.append((a, b, s, ln.get("speaker")))
        self._vig = None

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
        tr = self.plans[sc]["tracks"][cid]
        for a, b, li in tr["speak"]:
            if a - 0.02 <= t <= b:
                f = int(t * FPS)
                e = self.env[f] if self.env is not None and f < len(self.env) else 0.5
                words = self.scenes[sc]["lines"][li].get("words") or []
                inword = any(w0 - 0.03 <= t <= w1 + 0.02 for w0, w1, _ in words) if words else True
                if not inword:
                    return e * 0.3
                jaw = 0.5 + 0.5 * math.sin(t * 2 * math.pi * 5.2)   # syllable flap keeps the mouth moving
                return max(0.0, min(1.0, e * (0.65 + 0.35 * jaw) + 0.12))
        return 0.0

    def speaking(self, t, sc, cid):
        return any(a - 0.1 <= t <= b + 0.1 for a, b, _ in self.plans[sc]["tracks"][cid]["speak"])

    # ---------------------------------------------------------------- per-character pose
    def pose(self, t, sc_i, cid):
        tr = self.plans[sc_i]["tracks"][cid]
        look = self.looks[cid]
        P = LC.rest_pose()
        P["scale"] = SCALE
        P["y"] = FLOOR
        x = _x_at(tr, t)
        P["x"] = x
        face = _last(tr["face"], t, 1)
        P["facing"] = face
        # walking?
        walking = None
        for ws, we, x0, x1, sp in tr["walks"]:
            if ws <= t <= we:
                walking = (ws, we, x0, x1, sp)
        # expression with a short blend
        e, since, prev = _last2(tr["expr"], t)
        k = ease(since / 0.3)
        A, B = LC.EXPR[LC.expr_name(prev)], LC.EXPR[LC.expr_name(e)]
        for key in A:
            P[key] = lerp(A[key], B[key], k)
        ename = LC.expr_name(e)
        # blink (not when laughing/crying)
        bs = self.blink_seed[cid]
        period = 3.1 + bs * 2.2
        ph = (t + bs * 7) % period
        if ph < 0.13:
            P["blink"] = math.sin(ph / 0.13 * math.pi)
        # breathing + gaze
        P["bob"] = 2.5 * math.sin(t * 2 * math.pi / 3.4 + bs * 6)
        P["gaze"] = (0.35, 0.05 if ename != "sad" else 0.5)
        P["head_turn"] = 0.4
        P["head_tilt"] = {"sad": 6, "cry": 8, "ashamed": 9, "proud": -5, "thinking": 6, "greedy": -3, "worried": 4}.get(ename, 0)
        P["head_tilt"] += 1.5 * math.sin(t * 0.9 + bs * 4)
        speaking = self.speaking(t, sc_i, cid)
        P["mouth"] = self.mouth(t, sc_i, cid)
        if ename == "laugh":
            P["mouth"] = max(P["mouth"], 0.45 + 0.3 * math.sin(t * 22))
            P["bob"] += 6 * abs(math.sin(t * 11))
        if ename == "cry":
            P["bob"] += 3 * math.sin(t * 17)
            if not speaking:
                P["mouth"] = max(P["mouth"], 0.2 + 0.1 * math.sin(t * 9))
        if ename == "scared":
            P["x"] += 2.5 * math.sin(t * 47)
        P["highlight"] = 1.0 if speaking else 0.0
        # gestures
        lh, rh = GEST["rest"]
        g_active = None
        for gs, ge, g in tr["gest"]:
            if gs <= t <= ge + 0.45:
                g_active = (gs, ge, g)
        if speaking and not g_active:
            li = next(li for a, b, li in tr["speak"] if a - 0.1 <= t <= b + 0.1)
            g_active = (self.scenes[sc_i]["lines"][li]["start"], self.scenes[sc_i]["lines"][li]["end"],
                        ["talk_a", "talk_b", "talk_c", "talk_a"][li % 4])
        if g_active is None and ename in ("cry", "angry", "greedy", "laugh", "proud", "thinking", "scared"):
            g_active = (-1e9, 1e9, {"thinking": "think", "proud": "hips"}.get(ename, ename))
        if g_active:
            gs, ge, g = g_active
            tl, tr_ = GEST.get(g, GEST["rest"])
            kin = ease((t - gs) / 0.35)
            kout = 1 - ease((t - ge) / 0.45) if t > ge else 1
            kk = min(kin, kout)
            lh, rh = lerp2(lh, tl, kk), lerp2(rh, tr_, kk)
            if g == "wave":
                rh = (rh[0] + 30 * math.sin(t * 12) * kk, rh[1])
            elif g == "angry":
                rh = (rh[0] + 8 * math.sin(t * 25) * kk, rh[1] + 10 * math.sin(t * 25) * kk)
            elif g == "greedy":
                lh = (lh[0] + 14 * math.sin(t * 14) * kk, lh[1]); rh = (rh[0] - 14 * math.sin(t * 14) * kk, rh[1])
            elif g.startswith("talk"):
                e_ = P["mouth"]
                rh = (rh[0] + 18 * math.sin(t * 3.1) * kk, rh[1] - 25 * e_ * kk)
            elif g == "beg":
                P["lean"] = 7 * kk
            elif g == "celebrate":
                lh = (lh[0], lh[1] + 20 * math.sin(t * 10)); rh = (rh[0], rh[1] - 20 * math.sin(t * 10))
        # walk cycle overrides legs and swings arms
        if walking:
            ws, we, x0, x1, sp = walking
            dist = abs(_x_at(tr, t) - x0)
            ph = dist / (95.0 * (1.15 if sp > 1 else 1.0)) * math.pi
            amp = 24 if sp <= 1 else 34
            P["l_hip"], P["r_hip"] = amp * math.sin(ph), -amp * math.sin(ph)
            P["l_knee"] = max(0, 30 * math.sin(ph + 1.2)); P["r_knee"] = max(0, -30 * math.sin(ph + 1.2))
            P["bob"] += 7 * abs(math.sin(ph))
            P["lean"] = 4 * (1 if sp <= 1 else 2.2)
            if not g_active:
                lh = (16 + 40 * math.sin(ph), 200 - 10 * abs(math.sin(ph)))
                rh = (16 - 40 * math.sin(ph), 200 - 10 * abs(math.sin(ph)))
        # hops
        for hs in tr["hop"]:
            if hs <= t <= hs + 0.5:
                u = (t - hs) / 0.5
                P["bob"] += 46 * math.sin(u * math.pi)
                P["squash"] = -0.25 * math.sin(u * math.pi)
        P["lh"], P["rh"] = lh, rh
        P["hold"] = _last(tr["hold"], t, None)
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
                P.update(LC.EXPR["happy"]); P["rh"] = (80 + 30 * math.sin(t * 10 + k), -150); P["mouth"] = 0.0
                P["facing"] = 1 if P["x"] < 960 else -1
                P["bob"] = 3 * math.sin(t * 3 + k)
            else:
                P = self.pose(t, i, cid)
            poses[cid] = P
        owner = plan.get("owner")
        order = sorted(poses.keys(), key=lambda c: (0 if c == owner else 1, poses[c]["x"]))
        for kind, name, px, own in plan["props"]:
            if kind == "stage" and not endscreen:
                LP.draw_stage_prop(cv, name, px, FLOOR + 10, t)
        for cid in order:
            P = poses[cid]
            if -400 < P["x"] < W + 400:
                LC.draw_character(cv, self.looks[cid], P, t)
                if not endscreen:
                    self.draw_fx(cv, cid, P, t, i)
            if cid == owner and not endscreen:
                for kind, name, px, own in plan["props"]:
                    if kind == "cart":
                        # a child owner would vanish behind the counter: stand the cart beside them instead
                        dx = 20 if self.looks[cid]["height"] >= 0.8 else (-1 if px < W / 2 else 1) * 250 * SCALE
                        LP.draw_cart(cv, name, px + dx, FLOOR + 30, t, s=SCALE)
        if not endscreen:
            for gs, ge, obj, a, b in plan["gives"]:
                if gs <= t <= ge and a in poses and b in poses:
                    u = ease((t - gs) / (ge - gs))
                    ha = self._hand_world(poses[a], self.looks[a])
                    hb = self._hand_world(poses[b], self.looks[b])
                    x = lerp(ha[0], hb[0], u); y = lerp(ha[1], hb[1], u) - 120 * math.sin(u * math.pi)
                    LP.draw_object(cv, obj, x, y, SCALE, t)
        cv.restore()
        st.draw_front(cv, cam, t)
        st.grade(cv, t)

    def _hand_world(self, P, look):
        h = P.get("_hands", {}).get("rh")
        s = P["scale"] * look["height"]
        if not h:
            return (P["x"], P["y"] - 300 * s)
        return (P["x"] + h[0] * s * P["facing"], P["y"] + (h[1] - P["bob"]) * s)

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
                for k in range(10):
                    ang = k * 0.628 + t * 1.5
                    r = 120 + 50 * math.sin(t * 3 + k)
                    x, y = P["x"] + math.cos(ang) * r * s, P["y"] - 330 * s + math.sin(ang) * r * s
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
        card = text_card(s, self.lang, 48, 1500, sw=6, name=name)
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
        if i + 1 < len(self.scenes) and t > self.scenes[i]["end"] - XF:
            pass
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
