#!/usr/bin/env python3
"""Bounce Bhai long-form cast: Indian village cutout puppets drawn with skia every frame.

A character = a fixed LOOK (built once from a seed: skin, costume like saree / lungi / dhoti / kurta, hair, moustache,
age, belly) + a POSE per frame (feet x/y, facing, lean, hand IK targets, leg angles, expression values).
Arms are 2-bone IK chains driven by hand targets, so gestures (point, give, cry into hands, hands on hips, wave)
are just target positions that the renderer eases between.
"""
import math
import random

import skia

from toon2d import (rgb, C, shade, mix, paint, stroke, fill_ink, oval, rrect, poly, smooth_closed, INK)

SKINS = [rgb("f3cba6"), rgb("e8b98f"), rgb("d7a074"), rgb("c48a5c"), rgb("a8704a"), rgb("8a5a3a")]
HAIRS = [rgb("1b1514"), rgb("2a1e19"), rgb("3c281c")]
GREY = rgb("c9c6c2")
COL = {"red": rgb("d9343b"), "maroon": rgb("8e1f3a"), "orange": rgb("f08a24"), "saffron": rgb("f5a623"),
       "yellow": rgb("f2c230"), "green": rgb("2f9e57"), "parrot": rgb("7cc242"), "teal": rgb("17a2a0"),
       "blue": rgb("2f6fd6"), "sky": rgb("59b7f0"), "purple": rgb("7b4fcf"), "pink": rgb("ec5f9f"),
       "magenta": rgb("c7287a"), "white": rgb("f4f1e8"), "cream": rgb("efe2c0"), "brown": rgb("8b5a34"),
       "grey": rgb("8b9098"), "black": rgb("34343c"), "gold": rgb("e8b923"), "indigo": rgb("3a3f9e")}
BORDER = [rgb("f2c230"), rgb("e8b923"), rgb("d9343b"), rgb("2f9e57"), rgb("7b4fcf"), rgb("f08a24")]

# ------------------------------------------------------------------------------------------------ looks
BODIES = ("man", "woman", "oldman", "oldwoman", "boy", "girl")
COSTUMES = {"man": ["lungi", "kurta", "shirt", "dhoti"], "oldman": ["dhoti", "kurta", "lungi"],
            "woman": ["saree", "saree", "salwar"], "oldwoman": ["saree"], "boy": ["shorts", "kurta_kid"],
            "girl": ["frock", "pavadai"]}


def _pick(rng, xs):
    return xs[rng.randrange(len(xs))]


def make_look(spec, seed):
    """spec: {"type": man|woman|oldman|oldwoman|boy|girl, "costume": optional, "color": optional, "role": ...,
    "build": thin|normal|fat, "headwear": optional}. Deterministic for (spec, seed)."""
    rng = random.Random(seed)
    t = spec.get("type", "man")
    if t not in BODIES:
        t = {"grandpa": "oldman", "grandma": "oldwoman", "king": "man", "queen": "woman", "merchant": "man",
             "child": "boy", "kid": "boy"}.get(t, "man")
    fem = t in ("woman", "oldwoman", "girl")
    kid = t in ("boy", "girl")
    old = t in ("oldman", "oldwoman")
    costume = spec.get("costume")
    if costume not in ("lungi", "kurta", "shirt", "dhoti", "saree", "salwar", "shorts", "kurta_kid", "frock",
                       "pavadai", "royal", "royal_f"):
        costume = _pick(rng, COSTUMES[t])
    if kid and costume not in ("shorts", "kurta_kid", "frock", "pavadai"):
        costume = _pick(rng, COSTUMES[t])
    if fem and costume in ("lungi", "dhoti", "shirt", "kurta", "shorts", "kurta_kid", "royal"):
        costume = "royal_f" if costume == "royal" else _pick(rng, COSTUMES[t])
    if not fem and costume in ("saree", "salwar", "frock", "pavadai", "royal_f"):
        costume = "royal" if costume == "royal_f" else _pick(rng, COSTUMES[t])
    main = COL.get(spec.get("color"), None) or _pick(rng, [COL[k] for k in ("red", "orange", "green", "blue", "teal",
                                                                             "purple", "pink", "yellow", "maroon", "sky")])
    build = spec.get("build") or ("fat" if spec.get("role") in ("greedy", "villain", "merchant") and rng.random() < 0.7
                                  else _pick(rng, ["thin", "normal", "normal"]))
    look = {
        "type": t, "female": fem, "kid": kid, "old": old, "costume": costume, "main": main,
        "second": _pick(rng, [b for b in BORDER if b != main]),
        "pants": _pick(rng, [rgb("efe7d4"), rgb("3a4a6b"), rgb("6b5a45"), rgb("f4f1e8")]),
        "skin": _pick(rng, SKINS[1:] if not fem else SKINS),
        "hair_col": GREY if old else _pick(rng, HAIRS),
        "hair": ("bun" if old else _pick(rng, ["plait", "bun", "plait"])) if (fem and not kid) else
                (_pick(rng, ["two_plaits", "plait", "bob"]) if (kid and fem) else _pick(rng, ["short", "curly", "side_part"]) if kid else
                 (_pick(rng, ["bald_ring", "short", "side_part"]) if old else _pick(rng, ["short", "side_part", "wavy", "curly"]))),
        "moustache": (not fem and not kid) and (rng.random() < (0.85 if old else 0.7)),
        "mous_style": _pick(rng, ["thick", "thin", "handlebar", "thick"]),
        "beard": (not fem and not kid and rng.random() < (0.3 if old else 0.12)),
        "bindi": fem and not kid,
        "nosering": fem and not kid and rng.random() < 0.45,
        "earrings": fem,
        "bangles": fem and not kid,
        "glasses": old and rng.random() < 0.55,
        "gamcha": (not fem and not kid and costume in ("lungi", "shirt", "dhoti") and rng.random() < 0.6),
        "headwear": spec.get("headwear") or ("pagdi" if (not fem and old and rng.random() < 0.4) else
                                              "topi" if (not fem and not kid and spec.get("role") == "merchant") else
                                              "crown" if costume in ("royal", "royal_f") else "none"),
        "ghoonghat": t == "oldwoman" and rng.random() < 0.6,
        "stick": t == "oldman" or (t == "oldwoman" and rng.random() < 0.5),
        "build": build,
        "belly": {"fat": 1.0, "normal": 0.25, "thin": 0.0}.get(build, 0.25) if not kid else 0.0,
        "width": {"fat": 1.16, "normal": 1.0, "thin": 0.9}.get(build, 1.0),
        "height": {"man": 1.0, "woman": 0.94, "oldman": 0.93, "oldwoman": 0.86, "boy": 0.66, "girl": 0.64}[t] * rng.uniform(0.97, 1.03),
        "head": 1.22 if kid else 1.0,
        "eye_col": _pick(rng, [rgb("6b4226"), rgb("5a3820"), rgb("7a4a2a")]),
        "shoes": _pick(rng, [rgb("6b3f25"), rgb("3a2a22"), rgb("8b5a34")]),
    }
    if look["headwear"] == "crown":
        look["gamcha"] = False
    if costume == "lungi":
        look["lungi_check"] = _pick(rng, [rgb("2f6fd6"), rgb("2f9e57"), rgb("d9343b"), rgb("7b4fcf")])
        look["vest"] = rng.random() < 0.45
    return look


def rest_pose():
    return {"x": 960.0, "y": 900.0, "scale": 1.0, "facing": 1, "lean": 0.0, "bob": 0.0, "hop": 0.0, "dip": 0.0,
            "breath": 0.0, "hip_shift": 0.0, "lf": (0.0, 0.0), "rf": (0.0, 0.0), "head_tilt": 0.0,
            "head_turn": 0.35, "squash": 0.0,
            # hand IK targets relative to each shoulder: (out, down); out>0 = away from the body centre
            "lh": (8.0, 200.0), "rh": (8.0, 200.0),
            "l_hip": 0.0, "l_knee": 0.0, "r_hip": 0.0, "r_knee": 0.0, "sit": 0.0,
            "mouth": 0.0, "smile": 0.3, "blink": 0.0, "eye_open": 1.0, "gaze": (0.3, 0.0), "brow": 0.0,
            "brow_up": 0.0, "tears": 0.0, "red": 0.0, "sweat": 0.0, "happy_eyes": 0.0, "o_mouth": 0.0,
            "grin": 0.0, "sly": 0.0, "hold": None, "hold_hand": "r", "highlight": 0.0}


# ------------------------------------------------------------------------------------------------ the puppet
# Local frame: feet soles on y=0, +x = the way the character faces (draw_character mirrors it), so the "l" limbs
# (side -1) are the FAR side (drawn behind the body) and the "r" limbs (side +1) the NEAR side (drawn in front).
GRIP = {   # how a held object sits in the hand: hang (hand grips the rim/neck, object below), palm (rests on the open
           # palm, drawn over the hand), pinch (held at its middle, the hand drawn over it); (dx, dy) object offset
    "gold_pot": ("hang", 0, 44), "pot": ("hang", 0, 44), "magic_pot": ("hang", 0, 44), "water": ("hang", 0, 44),
    "jar": ("hang", 0, 44), "coin_bag": ("hang", 0, 40), "rice_sack": ("hang", 0, 50), "basket": ("hang", 0, 24),
    "lamp": ("palm", 0, -24), "bowl": ("palm", 0, -26), "plate": ("palm", 0, -26), "samosa": ("palm", 0, -26),
    "pani_puri": ("palm", 0, -26), "momos": ("palm", 0, -26), "seed": ("palm", 0, -26), "egg": ("palm", 0, -26),
    "fish": ("palm", 0, -26), "mango": ("palm", 0, -30), "roti": ("palm", 0, -26), "bread": ("palm", 0, -26),
    "coins": ("palm", 0, -18), "chai": ("pinch", 4, -6), "letter": ("pinch", 20, -8), "money": ("pinch", 22, -6),
    "coin": ("pinch", 10, -14), "key": ("pinch", 10, 0), "flower": ("pinch", 0, -30), "book": ("pinch", 18, -6),
    "gift": ("pinch", 22, -14), "ice_cream": ("pinch", 0, -22), "necklace": ("hang", 0, 10), "stick": ("pinch", 0, 0), "umbrella": ("pinch", 0, 40),
}
HELD_SCALE = {"magic_pot": 1.25, "gold_pot": 1.25, "pot": 1.2, "rice_sack": 1.1}
FACE_CLEAR = 0.32   # a hand may overlap the face outline by at most this fraction of its radius


LEG_REST = 0.992   # standing: legs nearly straight (a slight natural knee bend), never a squat


def dims(look):
    kid, fem, old = look["kid"], look["female"], look["old"]
    wdt = look["width"]
    d = {"leg": 230.0 if not kid else 160.0, "torso": (215.0 if not kid else 150.0) * (0.97 if old else 1.0),
         "sh_x": (70 if not fem else 62) * wdt * (0.82 if kid else 1.0),
         "waist": (62 if not fem else 54) * wdt * (0.85 if kid else 1.0),
         "head_r": 90.0 * look["head"], "up": 110.0 if not kid else 80.0, "lo": 104.0 if not kid else 76.0,
         "aw": 44.0 if not kid else 34.0, "hand_r": 27.0 if not kid else 22.0, "lw": 54.0 if not kid else 42.0,
         "ankle": 24.0, "hip_dx": 30 * wdt}
    d["hip_rest"] = -(d["leg"] * LEG_REST + d["ankle"])
    return d


def head_top_k(look):
    """Head top above the head centre, in head radii (hair, bun, turban, crown)."""
    hw = look.get("headwear", "none")
    k = {"pagdi": 1.36, "crown": 1.62, "topi": 1.32}.get(hw, 1.12)
    if look.get("hair") == "bun" and not look.get("ghoonghat"):
        k = max(k, 1.5)
    if look.get("ghoonghat"):
        k = max(k, 1.16)
    return k


def _ik(sx, sy, tx, ty, a, b, side, down_w=1.0, side_w=0.5):
    """2-bone IK from joint (sx,sy) to target (tx,ty). The middle joint bends to the OUTSIDE (away from the body
    centre on `side`) and downward, so elbows never fold up/inward. Returns (elbow, hand)."""
    dx, dy = tx - sx, ty - sy
    d0 = math.hypot(dx, dy)
    d_min = math.sqrt(max(0.0, a * a + b * b - 2 * a * b * math.cos(math.radians(20))))   # elbow never folds < 20 deg
    d = max(d_min, abs(a - b) + 1, min(a + b - 0.5, d0))
    if d0 < 1e-3:
        dx, dy, d0 = 0.0, 1.0, 1.0
    ux, uy = dx / d0, dy / d0
    hx, hy = sx + ux * d, sy + uy * d
    cosA = max(-1.0, min(1.0, (a * a + d * d - b * b) / (2 * a * d)))
    ang = math.acos(cosA)
    best = None
    for sgn in (1, -1):
        ca, sa = math.cos(sgn * ang), math.sin(sgn * ang)
        ex = sx + (ux * ca - uy * sa) * a
        ey = sy + (ux * sa + uy * ca) * a
        # perpendicular offset of the elbow from the shoulder->hand line
        px, py = ex - (sx + ux * a * cosA), ey - (sy + uy * a * cosA)
        score = px * side * side_w + py * down_w
        if best is None or score > best[0]:
            best = (score, ex, ey)
    return (best[1], best[2]), (hx, hy)


def _leg_ik(hx, hy, fx, fy, a, b):
    """Hip -> ankle; the knee always bends FORWARD (+x)."""
    dx, dy = fx - hx, fy - hy
    d0 = max(1e-3, math.hypot(dx, dy))
    d = max(abs(a - b) + 1, min(a + b - 0.01, d0))
    ux, uy = dx / d0, dy / d0
    ax, ay = hx + ux * d, hy + uy * d
    cosA = max(-1.0, min(1.0, (a * a + d * d - b * b) / (2 * a * d)))
    ang = math.acos(cosA)
    cands = []
    for sgn in (1, -1):
        ca, sa = math.cos(sgn * ang), math.sin(sgn * ang)
        cands.append((hx + (ux * ca - uy * sa) * a, hy + (ux * sa + uy * ca) * a))
    knee = max(cands, key=lambda k: k[0] - (hx + ux * a * cosA))
    return knee, (ax, ay)


def rig(look, P):
    """Every joint of the puppet in its local frame (before mirroring/scale). Feet are planted on y=0 unless a foot
    target lifts them; the hips carry the dip/sway so the soles never float. Upper-body points are already rotated
    by the lean (around the hip)."""
    d = dims(look)
    wdt = look["width"]
    hip_x = P.get("hip_shift", 0.0)
    hip_y = d["hip_rest"] + P.get("dip", 0.0) + P.get("sit", 0.0) * 110
    thigh = shin = d["leg"] * 0.5
    R = {"d": d, "hip": (hip_x, hip_y), "lean": P.get("lean", 0.0)}
    for side, key in ((-1, "lf"), (1, "rf")):
        off, lift = P.get(key) or (0.0, 0.0)
        fx = side * d["hip_dx"] * 0.85 + off
        fy = -d["ankle"] - max(0.0, lift)
        hj = (hip_x + side * d["hip_dx"], hip_y)
        knee, ankle = _leg_ik(hj[0], hj[1], fx, fy, thigh, shin)
        R["hipj" + key[0]] = hj
        R["knee" + key[0]] = knee
        R["ankle" + key[0]] = ankle
        R["sole" + key[0]] = ankle[1] + d["ankle"]
    # ---- upper body (lean rotates it around the hip)
    lean = math.radians(P.get("lean", 0.0))
    cl, sl = math.cos(lean), math.sin(lean)

    def rot(x, y):
        x0, y0 = x - hip_x, y - hip_y
        return (hip_x + x0 * cl - y0 * sl, hip_y + x0 * sl + y0 * cl)

    R["rot"] = rot
    br = P.get("breath", 0.0)
    sh_y = hip_y - d["torso"] - 2.0 * br
    R["sh_y"] = sh_y
    neck_top = sh_y - 24
    r = d["head_r"]
    hc_y = neck_top - r * 0.92
    R["neck_top"] = neck_top
    # head tilt pivots at the neck: move the head centre accordingly
    tl = math.radians(P.get("head_tilt", 0.0))
    hcx = hip_x + (hc_y - neck_top) * -math.sin(tl)
    hcy = neck_top + (hc_y - neck_top) * math.cos(tl)
    R["head_local"] = (0.0, hc_y)
    R["head"] = rot(hcx, hcy)
    R["head_r"] = r
    k = (d["up"] + d["lo"]) / 214.0
    for side, key in ((-1, "lh"), (1, "rh")):
        sx, sy = hip_x + side * (d["sh_x"] - 12) + (4 if side < 0 else 0), sh_y + 16
        out, down = P.get(key) or (16.0, 205.0)
        tx, ty = sx + side * out * k, sy + down * k
        # keep the hand off the face: push it radially out of the head disc
        hx_, hy_ = hcx, hcy
        dd = math.hypot(tx - hx_, ty - hy_)
        clear = r * 1.02 + d["hand_r"] * (1 - FACE_CLEAR)
        if dd < clear:
            if dd < 1e-3:
                ux, uy = side, 0.0
            else:
                ux, uy = (tx - hx_) / dd, (ty - hy_) / dd
                if ux * side < 0.25:      # push to the hand's own side, not across the face
                    ux = side * 0.9; uy = uy * 0.45
                    n = math.hypot(ux, uy); ux, uy = ux / n, uy / n
            tx, ty = hx_ + ux * clear, hy_ + uy * clear
        for _ in range(3):   # the hand centre sits beyond the wrist: keep IT off the face too
            (ex, ey), (wx, wy) = _ik(sx, sy, tx, ty, d["up"], d["lo"], side)
            fx_, fy_ = wx - ex, wy - ey
            n = max(1e-6, math.hypot(fx_, fy_))
            hcx_, hcy_ = wx + fx_ / n * d["hand_r"] * 0.55, wy + fy_ / n * d["hand_r"] * 0.55
            dh = math.hypot(hcx_ - hx_, hcy_ - hy_)
            if dh >= clear + 2:
                break
            ux, uy = ((hcx_ - hx_) / dh, (hcy_ - hy_) / dh) if dh > 1e-3 else (side, 0.0)
            if ux * side < 0.25:
                ux = side * 0.9; uy *= 0.45
                nn = math.hypot(ux, uy); ux, uy = ux / nn, uy / nn
            tx, ty = tx + ux * (clear + 4 - dh), ty + uy * (clear + 4 - dh)
        R["sh" + key[0]] = rot(sx, sy)
        R["el" + key[0]] = rot(ex, ey)
        R["wr" + key[0]] = rot(wx, wy)
        # hand centre sits just beyond the wrist along the forearm
        fx_, fy_ = wx - ex, wy - ey
        n = max(1e-6, math.hypot(fx_, fy_))
        hcx_, hcy_ = wx + fx_ / n * d["hand_r"] * 0.55, wy + fy_ / n * d["hand_r"] * 0.55
        R["hand" + key[0]] = rot(hcx_, hcy_)
        R["hand_ang" + key[0]] = math.atan2(fy_, fx_) + lean
    return R


def joint_angle(a, b, c):
    """Interior angle at b (degrees) of the chain a-b-c."""
    v1 = (a[0] - b[0], a[1] - b[1]); v2 = (c[0] - b[0], c[1] - b[1])
    n = max(1e-6, math.hypot(*v1) * math.hypot(*v2))
    return math.degrees(math.acos(max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / n))))


def geometry(look, P):
    """World-space geometry for the camera planner and the frame checker."""
    R = rig(look, P)
    s = P["scale"] * look["height"]
    f = 1 if P.get("facing", 1) >= 0 else -1
    hop = P.get("hop", 0.0) + P.get("bob", 0.0)

    def W_(pt):
        return (P["x"] + pt[0] * s * f, P["y"] + (pt[1] - hop) * s)

    d = R["d"]
    hx, hy = W_(R["head"])
    r = R["head_r"] * s
    top_k = head_top_k(look)
    half = max(d["sh_x"] + d["aw"] * 0.5, d["waist"] + 30 + look["belly"] * 26) * s
    if look["costume"] in ("saree", "pavadai", "royal_f"):
        half = max(half, (d["waist"] + 52) * s)
    xs = [W_(R[k])[0] for k in ("handl", "handr", "ell", "elr")]
    g = {"x": P["x"], "s": s, "head": (hx, hy, r * 1.08, r * top_k, r * 1.12),   # cx, cy, half-width, up, down
         "head_box": (hx - r * 1.08, hy - r * top_k, hx + r * 1.08, hy + r * 1.12),
         "body": (P["x"] - half, hy - r * top_k, P["x"] + half, P["y"] - hop * s),
         "reach": (min(xs + [P["x"] - half]), max(xs + [P["x"] + half])),
         "sole": P["y"] + (max(R["solel"], R["soler"]) - hop) * s,
         "hands": {k: W_(R["hand" + k]) for k in ("l", "r")}, "hand_r": d["hand_r"] * s,
         "angles": {"elbow_l": joint_angle(R["shl"], R["ell"], R["wrl"]), "elbow_r": joint_angle(R["shr"], R["elr"], R["wrr"]),
                    "knee_l": joint_angle(R["hipjl"], R["kneel"], R["anklel"]), "knee_r": joint_angle(R["hipjr"], R["kneer"], R["ankler"])},
         "rig": R}
    # elbow on the outside of the shoulder->wrist line, scored like the IK picks it (elbows hang down / out, never up-and-in)
    for side, k in ((-1, "l"), (1, "r")):
        (sx, sy), (ex, ey), (wx, wy) = R["sh" + k], R["el" + k], R["wr" + k]
        dx, dy = wx - sx, wy - sy
        n = max(1e-6, math.hypot(dx, dy))
        ux, uy = dx / n, dy / n
        pr = (ex - sx) * ux + (ey - sy) * uy
        px, py = ex - (sx + ux * pr), ey - (sy + uy * pr)
        g["elbow_out_" + k] = px * side * 0.5 + py * 1.0
        kx = R["knee" + k][0] - (R["hipj" + k][0] + R["ankle" + k][0]) / 2
        g["knee_fwd_" + k] = kx
    return g


def soft_shadow(cv, cx, cy, rx, ry, a=60):
    sh = skia.Paint(AntiAlias=True)
    sh.setShader(skia.GradientShader.MakeRadial(skia.Point(cx, cy), rx,
                                                 [C((0, 0, 0), int(a)), C((0, 0, 0), int(a * 0.55)), C((0, 0, 0), 0)], [0.0, 0.55, 1.0]))
    cv.save()
    cv.scale(1, ry / rx)
    cv.drawCircle(cx, cy * rx / ry, rx, sh)
    cv.restore()


def _taper(cv, pts, widths, col, ink_w=8.0):
    """A soft tapered limb through pts (2 segments), ink outline first, then the fill (no seams at the joint)."""
    def shape():
        paths = []
        for (x0, y0), (x1, y1), w0, w1 in zip(pts, pts[1:], widths, widths[1:]):
            dx, dy = x1 - x0, y1 - y0
            n = max(1e-6, math.hypot(dx, dy))
            nx, ny = -dy / n, dx / n
            p = skia.Path()
            p.moveTo(x0 + nx * w0 / 2, y0 + ny * w0 / 2); p.lineTo(x1 + nx * w1 / 2, y1 + ny * w1 / 2)
            p.lineTo(x1 - nx * w1 / 2, y1 - ny * w1 / 2); p.lineTo(x0 - nx * w0 / 2, y0 - ny * w0 / 2); p.close()
            paths.append(p)
        for (x, y), w in zip(pts, widths):
            paths.append(oval(x, y, w / 2, w / 2))
        return paths
    ps = shape()
    ink = stroke(INK, ink_w)
    for p in ps:
        cv.drawPath(p, ink)
    fp = paint(col)
    for p in ps:
        cv.drawPath(p, fp)


def _capsule(x0, y0, x1, y1, w):
    p = skia.Path()
    dx, dy = x1 - x0, y1 - y0
    n = max(1e-6, math.hypot(dx, dy))
    nx, ny = -dy / n * w / 2, dx / n * w / 2
    p.moveTo(x0 + nx, y0 + ny); p.lineTo(x1 + nx, y1 + ny); p.lineTo(x1 - nx, y1 - ny); p.lineTo(x0 - nx, y0 - ny); p.close()
    p.addCircle(x0, y0, w / 2); p.addCircle(x1, y1, w / 2)
    return p


def _hand(cv, x, y, ang, r, skin, side=1, fist=False, shape=None):
    """A cartoon hand centred at (x, y), fingers along `ang` (radians). Shapes: open (palm + four fingers + thumb),
    palm (open, fingers together), point (fist + index finger), fist / hold / pinch (closed), cup (curled)."""
    shape = shape or ("fist" if fist else "open")
    cv.save(); cv.translate(x, y); cv.rotate(math.degrees(ang) - 90)
    parts = []
    if shape in ("fist", "hold", "pinch", "cup", "point"):
        parts.append(oval(0, r * 0.1, r * 0.92, r * 0.88))
        parts.append(_capsule(side * r * 0.62, -r * 0.1, side * r * 0.78, r * 0.42, r * 0.42))   # thumb
        if shape == "point":
            parts.append(_capsule(-side * r * 0.05, r * 0.5, -side * r * 0.08, r * 1.75, r * 0.38))
    else:
        spread = 0.16 if shape == "open" else 0.0
        parts.append(oval(0, r * 0.1, r * 0.8, r * 0.82))
        for k, fx in enumerate((-0.48, -0.16, 0.16, 0.46)):
            ln_ = (1.12, 1.3, 1.26, 1.05)[k]
            fx2 = fx * (1 + spread * 1.6)
            parts.append(_capsule(fx * r, r * 0.45, fx2 * r, r * ln_, r * 0.34))
        parts.append(_capsule(side * r * 0.55, -r * 0.05, side * r * (1.05 + spread), r * 0.42, r * 0.36))   # thumb
    ink = stroke(INK, 4.5)
    for pp in parts:
        cv.drawPath(pp, ink)
    fp = paint(skin)
    for pp in parts:
        cv.drawPath(pp, fp)
    if shape in ("fist", "hold", "pinch", "cup", "point"):
        for k in range(3):   # knuckle creases
            cv.drawPath(poly([(-r * 0.55 + k * r * 0.36, r * 0.62), (-r * 0.5 + k * r * 0.36, r * 0.82)], close=False),
                        stroke(shade(skin, 0.7), 2.5))
    cv.restore()


def draw_character(cv, look, P, t=0.0):
    s = P["scale"] * look["height"]
    f = P.get("facing", 1)
    hop = P.get("hop", 0.0) + P.get("bob", 0.0)
    cv.save()
    cv.translate(P["x"], P["y"])
    # contact shadow on the ground: shrinks and fades while airborne
    air = max(0.0, hop) / 60.0
    soft_shadow(cv, 0, -2 * s, 118 * s * look["width"] * (1 - 0.3 * min(1, air)), 22 * s, a=int(78 * (1 - 0.55 * min(1, air))))
    cv.scale(s * (f if abs(f) > 0.05 else 0.05), s)
    sq = P.get("squash", 0.0)
    cv.scale(1 + 0.1 * sq, 1 - 0.1 * sq)
    cv.translate(0, -hop)
    if P.get("highlight", 0) > 0.01:   # speaking: warm rim glow behind the body
        g = skia.Paint(AntiAlias=True)
        g.setShader(skia.GradientShader.MakeRadial(skia.Point(0, -330), 330,
                                                    [C((255, 236, 170), int(55 * P["highlight"])), C((255, 236, 170), 0)]))
        cv.drawCircle(0, -330, 330, g)
    # cel lighting: the body is drawn into its own layer, then a soft key light from the upper left and a cool fill /
    # shadow toward the lower right are painted over its pixels only (volume, and it sits in the painted sets)
    bounds = skia.Rect.MakeLTRB(-420, -1100, 420, 60)
    cv.saveLayer(bounds, None)
    _body(cv, look, P, t)
    lit = skia.Paint(AntiAlias=True, BlendMode=skia.BlendMode.kSrcATop)
    lit.setShader(skia.GradientShader.MakeLinear([skia.Point(-260 * f, -900), skia.Point(220 * f, -60)],
                                                 [C((255, 246, 220), 46), C((255, 246, 220), 0), C((30, 20, 60), 0), C((30, 20, 60), 62)],
                                                 [0.0, 0.42, 0.6, 1.0]))
    cv.drawRect(bounds, lit)
    rim = skia.Paint(AntiAlias=True, BlendMode=skia.BlendMode.kSrcATop)
    rim.setShader(skia.GradientShader.MakeLinear([skia.Point(-150 * f, 0), skia.Point(-60 * f, 0)],
                                                 [C((255, 240, 200), 40), C((255, 240, 200), 0)]))
    cv.drawRect(bounds, rim)
    cv.restore()
    cv.restore()


def _arm(cv, look, R, P, side, skin, sleeve_col, sleeve_long, t, hold=None):
    k = "l" if side < 0 else "r"
    d = R["d"]
    S, E, Wr, Hc = R["sh" + k], R["el" + k], R["wr" + k], R["hand" + k]
    aw = d["aw"]
    col = skin if side > 0 else shade(skin, 0.9)
    _taper(cv, [S, E, Wr], [aw + 4, aw + 1, aw - 4], col)
    if sleeve_col is not None:
        sc = sleeve_col if side > 0 else shade(sleeve_col, 0.9)
        if sleeve_long:
            m = (E[0] + (Wr[0] - E[0]) * 0.78, E[1] + (Wr[1] - E[1]) * 0.78)
            _taper(cv, [S, E, m], [aw + 14, aw + 8, aw + 4], sc, ink_w=7)
            cv.drawPath(poly([m, (m[0] + (Wr[0] - E[0]) * 0.001, m[1] + (Wr[1] - E[1]) * 0.001)], close=False),
                        stroke(shade(sc, 0.75), aw + 4, cap=skia.Paint.kButt_Cap))
        else:
            m = (S[0] + (E[0] - S[0]) * 0.55, S[1] + (E[1] - S[1]) * 0.55)
            _taper(cv, [S, (S[0] + (m[0] - S[0]) * 0.5, S[1] + (m[1] - S[1]) * 0.5), m], [aw + 18, aw + 16, aw + 14], sc, ink_w=7)
    if look.get("bangles"):
        bx, by = E[0] + (Wr[0] - E[0]) * 0.86, E[1] + (Wr[1] - E[1]) * 0.86
        cv.drawCircle(bx, by, aw * 0.5, stroke(rgb("e8b923"), 5))
        cv.drawCircle(bx + (Wr[0] - E[0]) * 0.06, by + (Wr[1] - E[1]) * 0.06, aw * 0.5, stroke(rgb("d9343b"), 4))
    ang = R["hand_ang" + k]
    grip = None
    if hold:
        import long_props
        g, dx, dy = GRIP.get(hold, ("pinch", 0, 0))
        hs = HELD_SCALE.get(hold, 1.0)
        grip = (g, Hc[0] + dx * hs, Hc[1] + dy * hs, hs)
        if g in ("hang", "pinch"):
            long_props.draw_object(cv, hold, grip[1], grip[2], hs, t)
    shape = P.get("shape_" + k)
    if grip is not None:
        shape = "fist" if grip[0] in ("hang", "pinch") else "palm"
    elif shape is None:
        shape = "fist" if P.get("fist" + k, False) else "open"
    _hand(cv, Hc[0], Hc[1], ang, d["hand_r"], col, side=side, shape=shape)
    if grip and grip[0] == "palm":
        import long_props
        long_props.draw_object(cv, hold, grip[1], grip[2], grip[3], t)


def _body(cv, look, P, t):
    kid, fem, old = look["kid"], look["female"], look["old"]
    wdt = look["width"]
    cos = look["costume"]
    skin, main, sec = look["skin"], look["main"], look["second"]
    R = rig(look, P)
    d = R["d"]
    hip_x, hip_y = R["hip"]
    sh_y = R["sh_y"]
    sh_x, waist = d["sh_x"], d["waist"]
    belly = look["belly"]
    top_col = main
    if cos == "lungi" and look.get("vest"):
        top_col = rgb("f7f5ef")
    sleeve_long = cos in ("kurta", "shirt", "royal", "kurta_kid", "salwar") or (cos == "dhoti")
    sleeve_col = top_col if cos not in ("saree", "pavadai", "royal_f") else (sec if cos != "pavadai" else main)
    if cos == "lungi" and look.get("vest"):
        sleeve_col = None
    hold = None
    if P.get("hold"):
        import long_props
        hold = long_props.obj_name(P["hold"])

    # ----- far arm (and the old folks' walking stick) behind everything
    _arm(cv, look, R, P, -1, skin, sleeve_col, sleeve_long, t)
    if look.get("stick"):
        hx, hy = R["handl"]
        cv.drawPath(poly([(hx, hy - 34), (hx - 14, 0)], close=False), stroke(INK, 16))
        cv.drawPath(poly([(hx, hy - 34), (hx - 14, 0)], close=False), stroke(rgb("8b5a34"), 10))
        _hand(cv, hx, hy, R["hand_angl"], d["hand_r"], shade(skin, 0.9), side=-1, fist=True)

    # ----- legs + feet (far leg first)
    feet = []
    for k, side in (("l", -1), ("r", 1)):
        hj, kn, an = R["hipj" + k], R["knee" + k], R["ankle" + k]
        feet.append((side, hj[0], kn[0], kn[1], an[0], an[1] + d["ankle"], hj, kn, an))
    long_skirt = cos in ("saree", "dhoti", "pavadai", "royal", "royal_f")
    legcol = {"lungi": skin, "shorts": skin, "frock": skin, "kurta": look["pants"], "shirt": look["pants"],
              "salwar": shade(sec, 1.1), "kurta_kid": look["pants"]}.get(cos, skin)
    lw = d["lw"] * (0.82 if legcol == skin else 1.0)
    for side, hx, kx, ky, fx, fy, hj, kn, an in feet:
        lc = legcol if side > 0 else shade(legcol, 0.92)
        if not long_skirt:
            _taper(cv, [hj, kn, an], [lw + 6, lw, lw - 8], lc)
            if cos in ("kurta", "shirt", "salwar", "kurta_kid") and legcol != skin:
                cv.drawPath(poly([(an[0] - lw * 0.42, an[1] - 4), (an[0] + lw * 0.42, an[1] - 4)], close=False),
                            stroke(shade(lc, 0.75), 6))
        # chappal / jutti: sole on the ground line (y = fy)
        flen = 42 if not kid else 32
        fh = 15 if not kid else 12
        foot = oval(an[0] + 14, fy - fh, flen, fh)
        fill_ink(cv, foot, look["shoes"] if side > 0 else shade(look["shoes"], 0.85), w=4.5)
        cv.drawPath(oval(an[0] + 18, fy - fh * 1.55, flen * 0.48, fh * 0.6), paint(skin if side > 0 else shade(skin, 0.9)))
    # ----- lower garment over the legs (anchored at the hips)
    swing = (feet[1][4] - feet[0][4]) * 0.12
    cv.save(); cv.translate(hip_x, 0)
    fl, fr = feet[0], feet[1]
    if cos in ("saree", "pavadai", "royal_f"):
        hem_y = -8 - max(0, -max(fl[5], fr[5])) * 0.5
        hem_w = waist + 48 + abs(swing) * 0.5
        sk = skia.Path()
        sk.moveTo(-waist - 4, hip_y - 30)
        sk.lineTo(waist + 4, hip_y - 30)
        sk.quadTo(waist + 30, hip_y + 120, hem_w + swing * 0.4, hem_y)
        sk.quadTo(swing * 0.3, hem_y + 10, -hem_w + swing * 0.4, hem_y)
        sk.quadTo(-waist - 30, hip_y + 120, -waist - 4, hip_y - 30)
        sk.close()
        col = main if cos != "pavadai" else sec
        fill_ink(cv, sk, col)
        cv.save(); cv.clipPath(sk, doAntiAlias=True)
        cv.drawRect(skia.Rect.MakeLTRB(-200, hem_y - 26, 200, hem_y + 20), paint(sec if cos != "pavadai" else main))
        cv.drawRect(skia.Rect.MakeLTRB(-200, hem_y - 32, 200, hem_y - 26), paint(rgb("f6e27a")))
        for k in range(-3, 4):   # pleats
            cv.drawPath(poly([(k * 9 + 12, hip_y + 20), (k * 14 + 18 + swing * 0.3, hem_y - 30)], close=False),
                        stroke(shade(col, 0.78), 3))
        cv.drawPath(oval(waist + 26, (hip_y + hem_y) / 2, 40, 160), paint(shade(col, 0.82), 120))
        cv.restore()
        cv.drawPath(sk, stroke(INK, 5))
    elif cos in ("dhoti", "royal"):
        col = rgb("f6f2e6") if cos == "dhoti" else main
        for side, hx, kx, ky, fx, fy, hj, kn, an in feet:
            ax = an[0] - hip_x
            leg = poly([(side * 4, hip_y - 20), (side * (waist + 8), hip_y - 20), (ax + side * 34 + 6, an[1] + 6),
                        (ax - side * 26 + 6, an[1] + 6)])
            fill_ink(cv, leg, col if side > 0 else shade(col, 0.95))
            cv.drawPath(poly([(ax - 26 + 6, an[1] + 2), (ax + 34 + 6, an[1] + 2)], close=False),
                        stroke(rgb("d8a72c") if cos == "dhoti" else sec, 6))
        cv.drawPath(poly([(0, hip_y - 10), (swing * 0.2, -60)], close=False), stroke(shade(col, 0.82), 6))
    elif cos == "lungi":
        hem_y = -78
        col = rgb("f3efe6")
        chk = look["lungi_check"]
        lg = skia.Path()
        lg.moveTo(-waist - 6, hip_y - 26); lg.lineTo(waist + 6, hip_y - 26)
        lg.quadTo(waist + 22, hip_y + 80, waist + 30 + swing * 0.4, hem_y)
        lg.lineTo(-waist - 30 + swing * 0.4, hem_y)
        lg.quadTo(-waist - 22, hip_y + 80, -waist - 6, hip_y - 26)
        lg.close()
        fill_ink(cv, lg, col)
        cv.save(); cv.clipPath(lg, doAntiAlias=True)
        for k in range(-6, 7):
            cv.drawPath(poly([(k * 22, hip_y - 40), (k * 22 + swing * 0.3, 0)], close=False), stroke(chk, 6, a=170))
        for k in range(8):
            y = hip_y - 20 + k * 26
            cv.drawPath(poly([(-150, y), (150, y)], close=False), stroke(chk, 5, a=150))
        cv.restore()
        cv.drawPath(lg, stroke(INK, 5))
        cv.drawPath(poly([(-waist * 0.2, hip_y - 22), (waist * 0.1, hip_y + 30), (waist * 0.35, hip_y - 20)]),
                    paint(shade(col, 0.88)))
    elif cos in ("shorts",):
        for side, hx, kx, ky, fx, fy, hj, kn, an in feet:
            kx_ = kn[0] - hip_x
            leg = poly([(side * 2, hip_y - 20), (side * (waist + 4), hip_y - 20), (kx_ + 28, kn[1] - 8), (kx_ - 22, kn[1] - 8)])
            fill_ink(cv, leg, look["pants"] if look["pants"] != rgb("f4f1e8") else rgb("3a4a6b"))
    cv.restore()

    # ----- upper body: lean around the hip
    cv.save()
    cv.translate(hip_x, hip_y); cv.rotate(R["lean"]); cv.translate(-hip_x, -hip_y)
    cv.translate(hip_x, 0)
    long_top = cos in ("kurta", "salwar", "kurta_kid", "royal")
    hem = hip_y + (110 if long_top else 18)
    if cos == "frock":
        hem = hip_y + 70
    hem_w = waist + (36 if long_top else 8) + belly * 18
    if cos == "frock":
        hem_w = waist + 60
    bw = belly * 26
    torso = skia.Path()
    torso.moveTo(-sh_x, sh_y + 18)
    torso.quadTo(-sh_x - 4, sh_y - 6, -sh_x + 30, sh_y - 8)
    torso.lineTo(sh_x - 30, sh_y - 8)
    torso.quadTo(sh_x + 4, sh_y - 6, sh_x, sh_y + 18)
    torso.quadTo(waist + 14 + bw * 1.6, (sh_y + hip_y) / 2 + 20, waist + bw * 0.6, hip_y - 10)
    torso.lineTo(hem_w, hem)
    torso.quadTo(0, hem + 16, -hem_w, hem)
    torso.lineTo(-waist - bw * 0.6, hip_y - 10)
    torso.quadTo(-waist - 14 - bw * 1.6, (sh_y + hip_y) / 2 + 20, -sh_x, sh_y + 18)
    torso.close()
    if cos in ("saree", "pavadai", "royal_f"):
        blouse = rrect(-sh_x, sh_y - 8, sh_x, sh_y + 110, 36)
        cv.drawPath(rrect(-waist - 2, sh_y + 80, waist + 2, hip_y - 20, 20), paint(skin))
        cv.drawPath(rrect(-waist - 2, sh_y + 80, waist + 2, hip_y - 20, 20), stroke(INK, 5))
        fill_ink(cv, blouse, sec if cos != "pavadai" else main)
        drape = skia.Path()
        drape.moveTo(-sh_x + 8, sh_y - 6)
        drape.lineTo(-sh_x + 54, sh_y - 10)
        drape.quadTo(waist * 0.4, sh_y + 120, waist + 10, hip_y - 4)
        drape.lineTo(waist - 26, hip_y + 34)
        drape.quadTo(-waist * 0.5, sh_y + 140, -sh_x + 8, sh_y + 40)
        drape.close()
        col = main if cos != "pavadai" else rgb("f4f1e8")
        fill_ink(cv, drape, col)
        cv.save(); cv.clipPath(drape, doAntiAlias=True)
        for k in range(3):
            cv.drawPath(poly([(-sh_x + 20 + k * 14, sh_y), (waist - 20 + k * 12, hip_y + 20)], close=False),
                        stroke(shade(col, 0.8), 3))
        cv.restore()
        cv.drawPath(poly([(-sh_x + 50, sh_y - 8), (waist + 8, hip_y - 2)], close=False), stroke(look["second"], 8))
        if cos == "saree":
            pal = poly([(-sh_x - 6, sh_y - 4), (-sh_x - 30, sh_y + 160), (-sh_x + 6, sh_y + 170), (-sh_x + 20, sh_y + 10)])
            fill_ink(cv, pal, shade(col, 0.92), w=4)
            cv.drawPath(poly([(-sh_x - 30, sh_y + 150), (-sh_x + 6, sh_y + 160)], close=False), stroke(sec, 9))
    else:
        fill_ink(cv, torso, top_col)
        cv.save(); cv.clipPath(torso, doAntiAlias=True)
        cv.drawPath(oval(waist + 44, (sh_y + hem) / 2, 60, 220), paint(shade(top_col, 0.8), 140))
        if cos == "royal":
            for k in range(6):
                cv.drawCircle(0, sh_y + 30 + k * 40, 7, paint(look["second"]))
            cv.drawRect(skia.Rect.MakeLTRB(-200, hem - 22, 200, hem + 20), paint(look["second"]))
        if cos in ("kurta", "kurta_kid", "salwar"):
            cv.drawRect(skia.Rect.MakeLTRB(-200, hem - 18, 200, hem + 20), paint(shade(top_col, 0.75)))
        if cos == "frock":
            cv.drawRect(skia.Rect.MakeLTRB(-200, hem - 20, 200, hem - 8), paint(look["second"]))
            cv.drawRect(skia.Rect.MakeLTRB(-200, hip_y - 30, 200, hip_y - 18), paint(look["second"]))
        if cos == "lungi" and look.get("vest"):
            cv.drawPath(oval(0, sh_y - 6, 40, 40), paint(skin))
        cv.restore()
        cv.drawPath(torso, stroke(INK, 5))
        if cos in ("kurta", "kurta_kid", "salwar", "shirt", "dhoti", "royal") or (cos == "lungi" and not look.get("vest")):
            cv.drawPath(poly([(0, sh_y - 6), (0, sh_y + (80 if cos != "shirt" else hip_y - sh_y))], close=False),
                        stroke(shade(top_col, 0.6), 4))
            for k in range(3):
                cv.drawCircle(0, sh_y + 20 + k * 22, 4.5, paint(shade(top_col, 0.5)))
            col = poly([(-30, sh_y - 8), (0, sh_y + 22), (30, sh_y - 8), (16, sh_y - 14), (0, sh_y + 4), (-16, sh_y - 14)])
            fill_ink(cv, col, shade(top_col, 1.15), w=4)
        if cos == "salwar":   # dupatta over both shoulders
            dp = skia.Path()
            dp.moveTo(-sh_x - 4, sh_y + 2); dp.quadTo(0, sh_y + 90, sh_x + 4, sh_y + 2)
            dp.lineTo(sh_x + 10, sh_y + 30); dp.quadTo(0, sh_y + 130, -sh_x - 10, sh_y + 30); dp.close()
            fill_ink(cv, dp, look["second"], w=4)
    if look.get("gamcha"):
        g = poly([(sh_x - 34, sh_y - 10), (sh_x + 6, sh_y - 4), (sh_x + 2, sh_y + 120), (sh_x - 26, sh_y + 116)])
        fill_ink(cv, g, rgb("e8443a"), w=4)
        for k in range(3):
            cv.drawPath(poly([(sh_x - 28, sh_y + 20 + k * 30), (sh_x + 4, sh_y + 22 + k * 30)], close=False),
                        stroke(rgb("f5f0e6"), 4))
    # ----- neck + head
    head_r = d["head_r"]
    neck_top = R["neck_top"]
    cv.drawPath(rrect(-21, neck_top - 10, 21, sh_y + 6, 10), paint(shade(skin, 0.86)))
    hc_y = R["head_local"][1]
    cv.save()
    cv.translate(0, neck_top)
    cv.rotate(P["head_tilt"])
    cv.translate(0, -neck_top)
    draw_head(cv, look, P, 0, hc_y, head_r, t)
    cv.restore()
    cv.restore()
    # ----- near arm last, in front of body and face; held objects sit in this hand
    # (rig points are already lean-rotated and include hip_x, so draw in the unrotated frame)
    _arm(cv, look, R, P, 1, skin, sleeve_col, sleeve_long, t, hold=hold)
    P["_hands"] = {"lh": R["handl"], "rh": R["handr"]}
    P["_rig"] = R


def draw_head(cv, look, P, cx, cy, r, t=0.0):
    skin, hairc = look["skin"], look["hair_col"]
    turn = P.get("head_turn", 0.0) * 16
    hs = look["hair"]
    if look.get("ghoonghat"):
        hood = smooth_closed([(cx - r * 1.25, cy + r * 0.2), (cx - r * 1.2, cy - r * 1.1), (cx, cy - r * 1.45),
                              (cx + r * 1.2, cy - r * 1.1), (cx + r * 1.25, cy + r * 0.2), (cx + r * 1.1, cy + r * 1.6),
                              (cx - r * 1.1, cy + r * 1.6)])
        fill_ink(cv, hood, look["main"], w=5)
    if hs in ("plait", "two_plaits") and not look.get("ghoonghat"):
        sides = (1,) if hs == "plait" else (-1, 1)
        for sd in sides:
            for k in range(5):
                fill_ink(cv, oval(cx + sd * r * 0.92, cy + r * (0.3 + k * 0.3), r * 0.17, r * 0.19), hairc, w=4)
            cv.drawCircle(cx + sd * r * 0.92, cy + r * 1.75, r * 0.1, paint(rgb("d9343b")))
    for sd in (-1, 1):
        fill_ink(cv, oval(cx + sd * r * 0.98 + turn * 0.3, cy + r * 0.08, r * 0.16, r * 0.23), shade(skin, 0.95), w=4.5)
        if look.get("earrings"):
            cv.drawCircle(cx + sd * r * 0.98 + turn * 0.3, cy + r * 0.38, r * 0.08, paint(rgb("e8b923")))
            cv.drawCircle(cx + sd * r * 0.98 + turn * 0.3, cy + r * 0.38, r * 0.08, stroke(INK, 2.5))
    jaw = 0.86 if look["female"] or look["kid"] else 0.95
    chub = 1.0 + look["belly"] * 0.08
    face = smooth_closed([(cx, cy - r * 1.05), (cx + r * 0.98, cy - r * 0.55), (cx + r * 1.0 * chub, cy + r * 0.25),
                          (cx + r * 0.74 * jaw * chub, cy + r * 0.88), (cx, cy + r * 1.08), (cx - r * 0.74 * jaw * chub, cy + r * 0.88),
                          (cx - r * 1.0 * chub, cy + r * 0.25), (cx - r * 0.98, cy - r * 0.55)])
    red = P.get("red", 0.0)
    fskin = mix(skin, (225, 70, 60), min(0.55, red * 0.55))
    fill_ink(cv, face, fskin, w=5)
    cv.save(); cv.clipPath(face, doAntiAlias=True)
    cv.drawPath(oval(cx - r * 0.95 + turn * 0.4, cy + r * 0.3, r * 0.42, r * 1.1), paint(shade(fskin, 0.9), 130))
    if look["old"]:
        for k in range(2):
            cv.drawPath(poly([(cx - r * 0.3 + turn, cy - r * (0.62 + k * 0.12)), (cx + r * 0.3 + turn, cy - r * (0.62 + k * 0.12))],
                             close=False), stroke(shade(skin, 0.75), 3))
    cv.restore()
    cv.drawPath(face, stroke(INK, 5))
    fx = cx + turn
    if look.get("beard"):
        b = smooth_closed([(fx - r * 0.82, cy + r * 0.2), (fx - r * 0.6, cy + r * 0.98), (fx, cy + r * 1.22),
                           (fx + r * 0.6, cy + r * 0.98), (fx + r * 0.82, cy + r * 0.2), (fx, cy + r * 0.62)])
        fill_ink(cv, b, hairc, w=4)
    for sd in (-1, 1):
        cv.drawPath(oval(fx + sd * r * 0.58, cy + r * 0.44, r * 0.19, r * 0.11),
                    paint(rgb("f07a7a"), (95 if (look["female"] or look["kid"]) else 55) + int(90 * red)))
    # ---- eyes
    gx, gy = P.get("gaze", (0, 0))
    blink = max(0.0, min(1.0, P.get("blink", 0.0)))
    eo = P.get("eye_open", 1.0)
    he = P.get("happy_eyes", 0.0)
    sly = P.get("sly", 0.0)
    ey = cy + r * 0.04
    kidf = 1.12 if look["kid"] else 1.0
    ew, eh = r * 0.225 * kidf * (0.9 + 0.1 * eo), r * 0.285 * kidf * eo
    for sd in (-1, 1):
        ex = fx + sd * r * 0.37
        if he > 0.5 or blink > 0.85:
            lid = skia.Path()
            if he > 0.5:   # ^ ^ laughing eyes
                lid.moveTo(ex - ew, ey + eh * 0.2); lid.quadTo(ex, ey - eh * 0.9, ex + ew, ey + eh * 0.2)
            else:
                lid.moveTo(ex - ew, ey + eh * 0.1); lid.quadTo(ex, ey + eh * 0.55, ex + ew, ey + eh * 0.1)
            cv.drawPath(lid, stroke(INK, 6))
            continue
        eye = oval(ex, ey, ew, max(4, eh))
        cv.drawPath(eye, paint((255, 255, 255)))
        cv.save(); cv.clipPath(eye, doAntiAlias=True)
        ix, iy = ex + gx * ew * 0.45, ey + gy * eh * 0.35 + eh * 0.06
        pr = ew * (0.78 if eo < 1.2 else 0.56)
        ip = skia.Paint(AntiAlias=True)
        ic = look["eye_col"]
        ip.setShader(skia.GradientShader.MakeRadial(skia.Point(ix, iy + pr * 0.35), pr,
                                                    [C(mix(ic, (255, 220, 160), 0.35)), C(ic), C(shade(ic, 0.55))], [0.0, 0.6, 1.0]))
        cv.drawCircle(ix, iy, pr, ip)
        cv.drawCircle(ix, iy, pr, stroke(shade(ic, 0.4), 2.5))
        cv.drawCircle(ix, iy, pr * 0.5, paint((12, 10, 12)))
        cv.drawCircle(ix - pr * 0.36, iy - pr * 0.4, pr * 0.3, paint((255, 255, 255)))
        cv.drawCircle(ix + pr * 0.34, iy + pr * 0.32, pr * 0.13, paint((255, 255, 255), 220))
        # upper-lid shadow on the eyeball (depth)
        cv.drawPath(oval(ex, ey - eh * 0.95, ew * 1.1, eh * 0.38), paint((120, 90, 110), 60))
        lidc = max(blink, sly * 0.55)
        if lidc > 0:
            cv.drawRect(skia.Rect.MakeLTRB(ex - ew - 2, ey - eh - 2, ex + ew + 2, ey - eh + 2 * eh * lidc), paint(fskin))
            cv.drawPath(poly([(ex - ew, ey - eh + 2 * eh * lidc), (ex + ew, ey - eh + 2 * eh * lidc)], close=False),
                        stroke(INK, 4))
        cv.restore()
        cv.drawPath(eye, stroke(INK, 3.5))
        # a bold upper lid line (reads at any size) + lashes for women and girls
        lid = skia.Path()
        lid.addArc(skia.Rect.MakeLTRB(ex - ew * 1.04, ey - eh * 1.02, ex + ew * 1.04, ey + eh * 1.02), 192, 156)
        cv.drawPath(lid, stroke(INK, 7.5 if look["female"] else 6.0))
        if look["female"]:
            for k_, (ax_, ln_) in enumerate(((0.62, 1.0), (0.92, 0.85))):
                lash = skia.Path()
                bx_, by_ = ex + sd * ew * ax_, ey - eh * (0.82 if k_ == 0 else 0.45)
                lash.moveTo(bx_, by_); lash.quadTo(bx_ + sd * ew * 0.35, by_ - eh * 0.1, bx_ + sd * ew * 0.5 * ln_, by_ - eh * 0.32 * ln_)
                cv.drawPath(lash, stroke(INK, 4))
    if look.get("glasses"):
        for sd in (-1, 1):
            cv.drawCircle(fx + sd * r * 0.37, ey, r * 0.27, stroke(rgb("3a2a22"), 5))
        cv.drawPath(poly([(fx - r * 0.1, ey), (fx + r * 0.1, ey)], close=False), stroke(rgb("3a2a22"), 5))
    # ---- brows: brow>0 angry (inner down), brow<0 worried (inner up)
    bu = P.get("brow_up", 0.0) * r * 0.14
    bang = P.get("brow", 0.0)
    bc = hairc if not look["old"] else shade(GREY, 0.75)
    for sd in (-1, 1):
        bx = fx + sd * r * 0.37
        by = ey - r * 0.24 * max(eo, 0.8) - r * 0.14 - bu - (sly * r * 0.08 if sd > 0 else 0)
        p = skia.Path()
        p.moveTo(bx - sd * r * 0.21, by + bang * r * 0.1)
        p.quadTo(bx, by - r * 0.07, bx + sd * r * 0.21, by - bang * r * 0.04)
        cv.drawPath(p, stroke(bc, 8 if not look["female"] else 5.5))
    # ---- nose
    n = skia.Path(); n.moveTo(fx + r * 0.03, ey + r * 0.1); n.quadTo(fx + r * 0.16, ey + r * 0.36, fx - r * 0.04, ey + r * 0.38)
    cv.drawPath(n, stroke(shade(skin, 0.6), 4.5))
    if look.get("nosering"):
        cv.drawCircle(fx + r * 0.1, ey + r * 0.4, r * 0.06, stroke(rgb("e8b923"), 3.5))
    if look.get("bindi"):
        cv.drawCircle(fx, ey - r * 0.46, r * 0.055, paint(rgb("d8262f")))
    # ---- tears
    tears = P.get("tears", 0.0)
    if tears > 0.02:
        for sd in (-1, 1):
            ex = fx + sd * r * 0.37
            ln = r * 0.9 * tears
            tp = skia.Path()
            tp.moveTo(ex + sd * r * 0.05, ey + r * 0.15)
            tp.quadTo(ex + sd * r * 0.12, ey + r * 0.15 + ln * 0.5, ex + sd * r * 0.08, ey + r * 0.15 + ln)
            cv.drawPath(tp, stroke(rgb("7cc8f5"), 10, a=220))
            ph = (t * 1.6 + sd * 0.3) % 1.0
            cv.drawCircle(ex + sd * r * 0.1, ey + r * 0.2 + ln + ph * r * 0.6, 7 * (1 - ph * 0.5), paint(rgb("7cc8f5"), 220))
    # ---- mouth
    mo = max(0.0, min(1.0, P.get("mouth", 0.0)))
    sm = P.get("smile", 0.3)
    om = P.get("o_mouth", 0.0)
    grin = P.get("grin", 0.0)
    my = cy + r * 0.66
    mw = r * (0.25 + 0.07 * mo + 0.12 * grin) * (1 - 0.4 * om)
    vis = P.get("vis")
    if vis is not None:   # viseme lip-sync (speaking characters)
        draw_viseme_mouth(cv, vis, fx, my, r, sm)
    elif grin > 0.5 and mo < 0.3:   # toothy greedy grin
        p = skia.Path()
        p.moveTo(fx - mw, my - r * 0.08); p.quadTo(fx, my + r * 0.05, fx + mw, my - r * 0.08)
        p.quadTo(fx, my + r * 0.36, fx - mw, my - r * 0.08); p.close()
        cv.drawPath(p, paint((252, 252, 248)))
        cv.drawPath(poly([(fx - mw * 0.85, my + r * 0.02), (fx + mw * 0.85, my + r * 0.02)], close=False), stroke(INK, 2.5))
        for k in range(-2, 3):
            cv.drawPath(poly([(fx + k * mw * 0.3, my - r * 0.04), (fx + k * mw * 0.3, my + r * 0.16)], close=False), stroke(INK, 2))
        cv.drawPath(p, stroke(INK, 4.5))
    elif mo < 0.08 and om < 0.2:
        p = skia.Path(); p.moveTo(fx - mw, my - sm * r * 0.08); p.quadTo(fx, my + sm * r * 0.2, fx + mw, my - sm * r * 0.08)
        cv.drawPath(p, stroke(rgb("6d2b2b"), 5.5))
    elif om >= 0.2 and mo < 0.5:
        # surprised "O": a small round mouth below the moustache, warm interior, a visible upper lip
        orad = r * (0.075 + 0.07 * min(1.0, om))
        ocx, ocy = fx, my + r * 0.05 + orad
        o = oval(ocx, ocy, orad * 0.9, orad)
        cv.drawPath(o, paint(rgb("8c3a3f")))
        cv.save(); cv.clipPath(o, doAntiAlias=True)
        cv.drawPath(oval(ocx, ocy + orad * 0.85, orad * 0.75, orad * 0.5), paint(rgb("e88a90")))
        cv.drawPath(oval(ocx, ocy - orad * 0.95, orad * 0.8, orad * 0.28), paint(rgb("5e2328"), 140))
        cv.restore()
        cv.drawPath(o, stroke(rgb("c46b6b"), 5.5))
        cv.drawPath(oval(ocx, ocy, orad * 0.9 + 3, orad + 3), stroke(INK, 3.5))
        up = skia.Path(); up.moveTo(ocx - orad * 0.75, ocy - orad * 0.72); up.quadTo(ocx, ocy - orad * 1.32, ocx + orad * 0.75, ocy - orad * 0.72)
        cv.drawPath(up, stroke(rgb("b45a5c"), 5))
    else:
        mh = r * (0.06 + 0.28 * mo)
        p = skia.Path()
        lift = sm * r * 0.06
        p.moveTo(fx - mw, my - lift)
        p.quadTo(fx, my - mh * 0.25 + lift * 0.4, fx + mw, my - lift)
        p.quadTo(fx + mw * 0.6, my + mh * 1.1, fx, my + mh * 1.05)
        p.quadTo(fx - mw * 0.6, my + mh * 1.1, fx - mw, my - lift)
        p.close()
        cv.drawPath(p, paint(rgb("5a1e24")))
        cv.save(); cv.clipPath(p, doAntiAlias=True)
        cv.drawPath(oval(fx, my + mh * 1.05, mw * 0.55, mh * 0.45), paint(rgb("e0646e")))
        cv.drawRect(skia.Rect.MakeLTRB(fx - mw, my - mh, fx + mw, my + mh * 0.1), paint((250, 250, 248)))
        cv.restore()
        cv.drawPath(p, stroke(INK, 4))
    if look.get("moustache"):
        st = look.get("mous_style", "thick")
        m = skia.Path()
        k = {"thick": 1.0, "thin": 0.6, "handlebar": 1.0}[st]
        m.moveTo(fx, my - r * 0.14)
        m.cubicTo(fx - r * 0.2, my - r * (0.14 + 0.12 * k), fx - r * 0.38, my - r * 0.08, fx - r * 0.46, my + r * 0.0)
        if st == "handlebar":
            m.cubicTo(fx - r * 0.56, my - r * 0.12, fx - r * 0.6, my - r * 0.2, fx - r * 0.5, my - r * 0.24)
            m.cubicTo(fx - r * 0.5, my - r * 0.1, fx - r * 0.4, my - r * 0.02, fx - r * 0.3, my - r * 0.03)
        m.cubicTo(fx - r * 0.3, my - r * 0.04, fx - r * 0.16, my - r * 0.07, fx, my - r * 0.05)
        m.cubicTo(fx + r * 0.16, my - r * 0.07, fx + r * 0.3, my - r * 0.04, fx + r * 0.3, my - r * 0.03)
        if st == "handlebar":
            m.cubicTo(fx + r * 0.4, my - r * 0.02, fx + r * 0.5, my - r * 0.1, fx + r * 0.5, my - r * 0.24)
            m.cubicTo(fx + r * 0.6, my - r * 0.2, fx + r * 0.56, my - r * 0.12, fx + r * 0.46, my + r * 0.0)
        else:
            m.lineTo(fx + r * 0.46, my + r * 0.0)
        m.cubicTo(fx + r * 0.38, my - r * 0.08, fx + r * 0.2, my - r * (0.14 + 0.12 * k), fx, my - r * 0.14)
        fill_ink(cv, m, hairc if not look["old"] else rgb("e8e6e2"), w=3)
    if P.get("sweat", 0) > 0.05:
        sx, sy = cx + r * 0.85, cy - r * 0.55 + (t * 40 % 30)
        d = smooth_closed([(sx, sy - 18), (sx + 10, sy + 6), (sx, sy + 14), (sx - 10, sy + 6)])
        cv.drawPath(d, paint(rgb("9ad8ff"), int(230 * P["sweat"])))
        cv.drawPath(d, stroke(INK, 3, a=int(230 * P["sweat"])))
    draw_hair_front(cv, look, cx, cy, r, turn)


MOUTH_IN, TONGUE, LIP = rgb("6a2830"), rgb("e0646e"), rgb("8a3434")


def draw_viseme_mouth(cv, v, fx, my, r, smile=0.3):
    """A mouth drawn from a blended viseme vector (see engine/visemes.py): open, width, round, teeth_up, teeth_dn,
    tongue, tongue_up, bite, press. Every in-between value is drawable, so shapes morph smoothly."""
    o = max(0.0, min(1.0, v["open"]))
    ro = max(0.0, min(1.0, v["round"]))
    sm = max(-1.0, min(1.0, smile)) * (1 - 0.7 * ro) * (1 - 0.6 * o)
    mw = r * 0.30 * v["width"]
    mh = r * (0.015 + 0.40 * o)                 # inner opening height
    lift = sm * r * 0.07                          # smiling corners rise
    top = my - mh * (0.30 + 0.25 * ro)            # upper lip edge (centre)
    bot = my + mh * (0.95 + 0.15 * ro)            # lower lip edge (centre)
    press = v["press"]
    if o < 0.06 or press > 0.6:   # closed: a lip line; pressed lips bulge a little (m b p)
        p = skia.Path()
        p.moveTo(fx - mw, my - lift)
        p.quadTo(fx, my + sm * r * 0.16 + press * r * 0.02, fx + mw, my - lift)
        if press > 0.3:
            cv.drawPath(p, stroke(LIP, 9 + 4 * press, a=int(120 + 100 * press)))
        cv.drawPath(p, stroke(rgb("4a1a1a"), 5.5))
        if press > 0.3:   # tucked lower lip
            q = skia.Path(); q.moveTo(fx - mw * 0.45, my + r * 0.07); q.quadTo(fx, my + r * 0.12, fx + mw * 0.45, my + r * 0.07)
            cv.drawPath(q, stroke(shade(LIP, 0.8), 3, a=160))
        return
    # corner handles: sharp lens shape when spread, vertical tangents (ellipse) when round
    hx = mw * (0.25 + 0.30 * ro)
    cvy = mh * 0.55 * ro
    p = skia.Path()
    p.moveTo(fx - mw, my - lift)
    p.cubicTo(fx - mw + hx * (1 - ro) * 0.5, my - lift - cvy - mh * 0.15 * (1 - ro), fx - hx, top, fx, top)
    p.cubicTo(fx + hx, top, fx + mw - hx * (1 - ro) * 0.5, my - lift - cvy - mh * 0.15 * (1 - ro), fx + mw, my - lift)
    p.cubicTo(fx + mw - hx * (1 - ro) * 0.3, my - lift + cvy + mh * 0.5, fx + hx * 1.1, bot, fx, bot)
    p.cubicTo(fx - hx * 1.1, bot, fx - mw + hx * (1 - ro) * 0.3, my - lift + cvy + mh * 0.5, fx - mw, my - lift)
    p.close()
    cv.drawPath(p, paint(MOUTH_IN))
    cv.save(); cv.clipPath(p, doAntiAlias=True)
    h = bot - top
    if v["tongue"] > 0.05:
        ty = bot - h * 0.12 - v["tongue_up"] * h * 0.55
        cv.drawPath(oval(fx, ty, mw * (0.5 + 0.1 * v["tongue_up"]), h * (0.28 + 0.1 * v["tongue_up"])),
                    paint(TONGUE, int(255 * min(1.0, v["tongue"] + 0.2))))
    tu = v["teeth_up"]
    if tu > 0.05:
        th = min(h * 0.55, r * 0.09) * min(1.0, tu + 0.2) + (h * 0.15 if v["bite"] > 0.5 else 0)
        cv.drawRect(skia.Rect.MakeLTRB(fx - mw, top - r * 0.05, fx + mw, top + th), paint((250, 250, 246)))
    td = v["teeth_dn"]
    if td > 0.05:
        th = min(h * 0.45, r * 0.07) * td
        cv.drawRect(skia.Rect.MakeLTRB(fx - mw, bot - th, fx + mw, bot + r * 0.05), paint((244, 244, 240)))
    cv.restore()
    cv.drawPath(p, stroke(INK, 4))
    if v["bite"] > 0.3:   # f / v: lower lip tucked under the top teeth
        q = skia.Path(); q.moveTo(fx - mw * 0.8, bot - h * 0.1); q.quadTo(fx, bot + r * 0.06, fx + mw * 0.8, bot - h * 0.1)
        cv.drawPath(q, stroke(LIP, 7, a=int(230 * min(1, v["bite"]))))
        cv.drawPath(q, stroke(INK, 3, a=int(230 * min(1, v["bite"]))))
    if ro > 0.5:   # pursed-lip creases for o / u
        for sd in (-1, 1):
            q = skia.Path(); q.moveTo(fx + sd * (mw + r * 0.02), my - lift - r * 0.04); q.lineTo(fx + sd * (mw + r * 0.07), my - lift)
            q.lineTo(fx + sd * (mw + r * 0.02), my - lift + r * 0.04)
            cv.drawPath(q, stroke(shade(LIP, 0.8), 2.5, a=int(200 * (ro - 0.5) * 2)))


def draw_hair_front(cv, look, cx, cy, r, turn):
    hs, hc = look["hair"], look["hair_col"]
    hw = look.get("headwear", "none")
    t = turn * 0.6
    if look.get("ghoonghat"):
        p = skia.Path()
        p.moveTo(cx - r * 1.1, cy + r * 0.1)
        p.cubicTo(cx - r * 1.15, cy - r * 1.5, cx + r * 1.15, cy - r * 1.5, cx + r * 1.1, cy + r * 0.1)
        p.quadTo(cx + r * 0.9, cy - r * 0.75, cx + t, cy - r * 0.82)
        p.quadTo(cx - r * 0.9, cy - r * 0.75, cx - r * 1.1, cy + r * 0.1)
        p.close()
        cv.drawPath(oval(cx + t, cy - r * 0.78, r * 0.7, r * 0.2), paint(GREY))
        fill_ink(cv, p, look["main"], w=5)
        cv.drawPath(poly([(cx - r * 1.08, cy), (cx - r * 0.5, cy - r * 0.78)], close=False), stroke(look["second"], 7))
        return
    if hs == "bald_ring":
        for sd in (-1, 1):
            fill_ink(cv, smooth_closed([(cx + sd * r * 1.02, cy - r * 0.45), (cx + sd * r * 0.82, cy - r * 0.72),
                                        (cx + sd * r * 0.78, cy - r * 0.1), (cx + sd * r * 1.04, cy + r * 0.05)]), hc, w=4)
        cv.drawPath(oval(cx - r * 0.3, cy - r * 0.8, r * 0.3, r * 0.1), paint((255, 255, 255), 70))
    else:
        top = skia.Path()
        top.moveTo(cx - r * 1.04, cy - r * 0.1)
        top.cubicTo(cx - r * 1.12, cy - r * 1.42, cx + r * 1.12, cy - r * 1.42, cx + r * 1.04, cy - r * 0.1)
        if look["female"]:
            top.quadTo(cx + r * 0.95, cy - r * 0.42, cx + r * 0.45, cy - r * 0.78)
            top.quadTo(cx + r * 0.1, cy - r * 0.95, cx + t * 0.2, cy - r * 0.9)
            top.quadTo(cx - r * 0.1, cy - r * 0.95, cx - r * 0.45, cy - r * 0.78)
            top.quadTo(cx - r * 0.95, cy - r * 0.42, cx - r * 1.04, cy - r * 0.1)
        elif hs == "curly":
            top.quadTo(cx, cy - r * 0.58, cx - r * 1.04, cy - r * 0.1)
        else:
            top.quadTo(cx + r * 0.9, cy - r * 0.62, cx + r * 0.5 + t, cy - r * 0.66)
            top.quadTo(cx - r * 0.1 + t, cy - r * 0.5, cx - r * 0.55 + t, cy - r * 0.62)
            top.quadTo(cx - r * 0.9, cy - r * 0.6, cx - r * 1.04, cy - r * 0.1)
        top.close()
        fill_ink(cv, top, hc, w=5)
        if hs == "curly":
            for k in range(9):
                a = math.pi * (0.08 + 0.84 * k / 8)
                fill_ink(cv, oval(cx - math.cos(a) * r * 0.98, cy - r * 0.35 - math.sin(a) * r * 0.85, r * 0.24, r * 0.22), hc, w=4)
        if hs == "wavy":
            fill_ink(cv, smooth_closed([(cx - r * 0.5 + t, cy - r * 0.95), (cx + r * 0.2 + t, cy - r * 1.36),
                                        (cx + r * 0.85 + t, cy - r * 1.05), (cx + r * 0.5 + t, cy - r * 0.75)]), hc, w=4)
        if hs == "bun":
            fill_ink(cv, oval(cx, cy - r * 1.2, r * 0.36, r * 0.28), hc, w=4)
            cv.drawCircle(cx + r * 0.28, cy - r * 1.24, r * 0.09, paint(rgb("f6f2e6")))   # jasmine flowers
            cv.drawCircle(cx + r * 0.38, cy - r * 1.12, r * 0.08, paint(rgb("f6f2e6")))
        if hs == "bob":
            for sd in (-1, 1):
                fill_ink(cv, smooth_closed([(cx + sd * r * 1.06, cy - r * 0.4), (cx + sd * r * 1.12, cy + r * 0.62),
                                            (cx + sd * r * 0.7, cy + r * 0.58), (cx + sd * r * 0.78, cy - r * 0.55)]), hc, w=4)
        cv.drawPath(oval(cx - r * 0.35, cy - r * 0.98, r * 0.28, r * 0.08), paint((255, 255, 255), 50))
    if hw == "pagdi":
        p = skia.Path()
        p.moveTo(cx - r * 1.1, cy - r * 0.45)
        p.cubicTo(cx - r * 1.25, cy - r * 1.75, cx + r * 1.25, cy - r * 1.75, cx + r * 1.1, cy - r * 0.45)
        p.quadTo(cx, cy - r * 0.68, cx - r * 1.1, cy - r * 0.45)
        p.close()
        col = look["second"]
        fill_ink(cv, p, col, w=5)
        for k in range(3):
            cv.drawPath(poly([(cx - r * 1.05, cy - r * (0.62 + k * 0.28)), (cx + r * 1.05, cy - r * (0.9 + k * 0.22))], close=False),
                        stroke(shade(col, 0.75), 5))
    elif hw == "topi":
        p = poly([(cx - r * 0.85, cy - r * 0.7), (cx - r * 0.75, cy - r * 1.3), (cx + r * 0.75, cy - r * 1.3), (cx + r * 0.85, cy - r * 0.7)])
        fill_ink(cv, p, rgb("f6f2e6"), w=5)
        cv.drawPath(poly([(cx, cy - r * 1.3), (cx + r * 0.1, cy - r * 0.75)], close=False), stroke(rgb("d6d0c0"), 4))
    elif hw == "crown":
        pts = [(cx - r * 0.8, cy - r * 0.8), (cx - r * 0.85, cy - r * 1.45), (cx - r * 0.45, cy - r * 1.15),
               (cx, cy - r * 1.6), (cx + r * 0.45, cy - r * 1.15), (cx + r * 0.85, cy - r * 1.45), (cx + r * 0.8, cy - r * 0.8)]
        fill_ink(cv, poly(pts), rgb("f2c230"), w=5)
        cv.drawCircle(cx, cy - r * 1.05, r * 0.12, paint(rgb("d9343b")))
        cv.drawCircle(cx, cy - r * 1.05, r * 0.12, stroke(INK, 3))


# ------------------------------------------------------------------------------------------------ expressions
EXPR = {  # target face values; renderer eases between them
    "neutral":   dict(smile=0.3, brow=0.0, brow_up=0.0, eye_open=1.0, tears=0.0, red=0.0, sweat=0.0, happy_eyes=0.0, o_mouth=0.0, grin=0.0, sly=0.0),
    "happy":     dict(smile=1.0, brow=-0.1, brow_up=0.35, eye_open=1.0, tears=0.0, red=0.0, sweat=0.0, happy_eyes=0.0, o_mouth=0.0, grin=0.0, sly=0.0),
    "laugh":     dict(smile=1.0, brow=-0.1, brow_up=0.4, eye_open=1.0, tears=0.0, red=0.0, sweat=0.0, happy_eyes=1.0, o_mouth=0.0, grin=0.0, sly=0.0),
    "sad":       dict(smile=-0.9, brow=-1.0, brow_up=0.2, eye_open=0.85, tears=0.0, red=0.0, sweat=0.0, happy_eyes=0.0, o_mouth=0.0, grin=0.0, sly=0.0),
    "cry":       dict(smile=-1.0, brow=-1.2, brow_up=0.3, eye_open=0.75, tears=1.0, red=0.15, sweat=0.0, happy_eyes=0.0, o_mouth=0.0, grin=0.0, sly=0.0),
    "angry":     dict(smile=-0.7, brow=1.3, brow_up=-0.2, eye_open=0.9, tears=0.0, red=0.75, sweat=0.0, happy_eyes=0.0, o_mouth=0.0, grin=0.0, sly=0.0),
    "surprised": dict(smile=0.0, brow=-0.2, brow_up=1.2, eye_open=1.35, tears=0.0, red=0.0, sweat=0.0, happy_eyes=0.0, o_mouth=0.9, grin=0.0, sly=0.0),
    "scared":    dict(smile=-0.8, brow=-1.0, brow_up=0.9, eye_open=1.3, tears=0.0, red=0.0, sweat=1.0, happy_eyes=0.0, o_mouth=0.4, grin=0.0, sly=0.0),
    "greedy":    dict(smile=1.0, brow=0.6, brow_up=0.0, eye_open=0.9, tears=0.0, red=0.0, sweat=0.0, happy_eyes=0.0, o_mouth=0.0, grin=1.0, sly=0.8),
    "sly":       dict(smile=0.8, brow=0.4, brow_up=0.0, eye_open=0.95, tears=0.0, red=0.0, sweat=0.0, happy_eyes=0.0, o_mouth=0.0, grin=0.0, sly=0.7),
    "thinking":  dict(smile=0.0, brow=-0.3, brow_up=0.4, eye_open=1.0, tears=0.0, red=0.0, sweat=0.0, happy_eyes=0.0, o_mouth=0.0, grin=0.0, sly=0.3),
    "proud":     dict(smile=1.0, brow=0.0, brow_up=0.2, eye_open=1.0, tears=0.0, red=0.0, sweat=0.0, happy_eyes=1.0, o_mouth=0.0, grin=0.0, sly=0.0),
    "worried":   dict(smile=-0.4, brow=-0.9, brow_up=0.5, eye_open=1.05, tears=0.0, red=0.0, sweat=0.6, happy_eyes=0.0, o_mouth=0.0, grin=0.0, sly=0.0),
    "ashamed":   dict(smile=-0.6, brow=-0.8, brow_up=0.0, eye_open=0.7, tears=0.3, red=0.45, sweat=0.4, happy_eyes=0.0, o_mouth=0.0, grin=0.0, sly=0.0),
}
EXPR_ALIASES = {"shock": "surprised", "shocked": "surprised", "smile": "happy", "joy": "happy", "excited": "happy",
                "crying": "cry", "tearful": "cry", "upset": "sad", "mad": "angry", "furious": "angry", "fear": "scared",
                "afraid": "scared", "nervous": "worried", "confused": "thinking", "curious": "thinking", "calm": "neutral",
                "kind": "happy", "grateful": "happy", "relieved": "happy", "laughing": "laugh", "evil": "sly",
                "cunning": "sly", "jealous": "sly", "embarrassed": "ashamed", "guilty": "ashamed", "determined": "proud",
                "hopeful": "happy", "tired": "sad", "hungry": "sad", "serious": "neutral", "wise": "neutral"}


def expr_name(e):
    e = (e or "neutral").lower().strip()
    return e if e in EXPR else EXPR_ALIASES.get(e, "neutral")
