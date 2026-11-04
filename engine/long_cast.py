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
        "eye_col": _pick(rng, [rgb("3b2a20"), rgb("2a1d16"), rgb("4a3326")]),
        "shoes": _pick(rng, [rgb("6b3f25"), rgb("3a2a22"), rgb("8b5a34")]),
    }
    if look["headwear"] == "crown":
        look["gamcha"] = False
    if costume == "lungi":
        look["lungi_check"] = _pick(rng, [rgb("2f6fd6"), rgb("2f9e57"), rgb("d9343b"), rgb("7b4fcf")])
        look["vest"] = rng.random() < 0.45
    return look


def rest_pose():
    return {"x": 960.0, "y": 900.0, "scale": 1.0, "facing": 1, "lean": 0.0, "bob": 0.0, "head_tilt": 0.0,
            "head_turn": 0.35, "squash": 0.0,
            # hand IK targets relative to each shoulder: (out, down); out>0 = away from the body centre
            "lh": (16.0, 205.0), "rh": (16.0, 205.0),
            "l_hip": 0.0, "l_knee": 0.0, "r_hip": 0.0, "r_knee": 0.0, "sit": 0.0,
            "mouth": 0.0, "smile": 0.3, "blink": 0.0, "eye_open": 1.0, "gaze": (0.3, 0.0), "brow": 0.0,
            "brow_up": 0.0, "tears": 0.0, "red": 0.0, "sweat": 0.0, "happy_eyes": 0.0, "o_mouth": 0.0,
            "grin": 0.0, "sly": 0.0, "hold": None, "hold_hand": "r", "highlight": 0.0}


# ------------------------------------------------------------------------------------------------ helpers
def _ik(sx, sy, tx, ty, a, b, side):
    """2-bone IK from shoulder (sx,sy) to target (tx,ty). Elbow bends outward/down. Returns elbow, hand."""
    dx, dy = tx - sx, ty - sy
    d = math.hypot(dx, dy)
    d = max(abs(a - b) + 1, min(a + b - 0.5, d))
    if d < 1e-3:
        return (sx, sy + a), (sx, sy + a + b)
    ux, uy = dx / max(1e-6, math.hypot(dx, dy)), dy / max(1e-6, math.hypot(dx, dy))
    hx, hy = sx + ux * d, sy + uy * d
    cosA = (a * a + d * d - b * b) / (2 * a * d)
    cosA = max(-1, min(1, cosA))
    ang = math.acos(cosA)
    # rotate the shoulder->hand direction by +-ang; pick the elbow that is further outward / lower
    best = None
    for sgn in (1, -1):
        ca, sa = math.cos(sgn * ang), math.sin(sgn * ang)
        ex = sx + (ux * ca - uy * sa) * a
        ey = sy + (ux * sa + uy * ca) * a
        score = (ex - sx) * side * 1.0 + (ey - sy) * 0.35
        if best is None or score > best[0]:
            best = (score, ex, ey)
    return (best[1], best[2]), (hx, hy)


def _limb(cv, pts, col, w, ink_w=8):
    p = poly(pts, close=False)
    cv.drawPath(p, stroke(INK, w + ink_w))
    cv.drawPath(p, stroke(col, w))


def soft_shadow(cv, cx, cy, rx, ry, a=60):
    sh = skia.Paint(AntiAlias=True)
    sh.setShader(skia.GradientShader.MakeRadial(skia.Point(cx, cy), rx,
                                                 [C((0, 0, 0), a), C((0, 0, 0), 0)]))
    cv.save()
    cv.scale(1, ry / rx)
    cv.drawCircle(cx, cy * rx / ry, rx, sh)
    cv.restore()


# ------------------------------------------------------------------------------------------------ the puppet
def draw_character(cv, look, P, t=0.0):
    s = P["scale"] * look["height"]
    cv.save()
    cv.translate(P["x"], P["y"])
    soft_shadow(cv, 0, 4, 120 * s * look["width"], 24 * s)
    cv.scale(s * P.get("facing", 1), s)
    sq = P.get("squash", 0.0)
    cv.scale(1 + 0.1 * sq, 1 - 0.1 * sq)
    cv.translate(0, -P["bob"])
    cv.rotate(P["lean"])
    if P.get("highlight", 0) > 0.01:   # speaking: warm rim glow behind the body
        g = skia.Paint(AntiAlias=True)
        g.setShader(skia.GradientShader.MakeRadial(skia.Point(0, -330), 330,
                                                    [C((255, 236, 170), int(70 * P["highlight"])), C((255, 236, 170), 0)]))
        cv.drawCircle(0, -330, 330, g)
    _body(cv, look, P, t)
    cv.restore()


def _body(cv, look, P, t):
    kid, fem, old = look["kid"], look["female"], look["old"]
    wdt = look["width"]
    cos = look["costume"]
    skin, main, sec = look["skin"], look["main"], look["second"]
    leg_len = 230 if not kid else 160
    sit = P.get("sit", 0.0)
    hip_y = -leg_len - 8 + sit * 110
    torso_h = (215 if not kid else 150) * (0.97 if old else 1.0)
    sh_y = hip_y - torso_h
    sh_x = (70 if not fem else 62) * wdt * (0.82 if kid else 1.0)
    waist = (62 if not fem else 54) * wdt * (0.85 if kid else 1.0)
    belly = look["belly"]

    # ----- back items: stick, long hair handled in head; ghoonghat back
    feet = []
    for side, hip_a, knee_a in ((-1, P["l_hip"], P["l_knee"]), (1, P["r_hip"], P["r_knee"])):
        hx = side * 30 * wdt
        thigh = leg_len * 0.5 * (1 - 0.5 * sit)
        kx = hx + math.sin(math.radians(hip_a)) * thigh + side * sit * 40
        ky = hip_y + math.cos(math.radians(hip_a)) * thigh
        a2 = math.radians(hip_a - knee_a)
        shin = leg_len * 0.5
        fx = kx + math.sin(a2) * shin + sit * 30
        fy = min(0.0, ky + math.cos(a2) * shin)
        feet.append((side, hx, kx, ky, fx, fy))

    long_skirt = cos in ("saree", "dhoti", "pavadai", "royal", "royal_f")
    legcol = {"lungi": skin, "shorts": skin, "frock": skin, "kurta": look["pants"], "shirt": look["pants"],
              "salwar": shade(sec, 1.1), "kurta_kid": look["pants"]}.get(cos, skin)
    lw = 54 if not kid else 42
    for side, hx, kx, ky, fx, fy in feet:
        if not long_skirt:
            _limb(cv, [(hx, hip_y), (kx, ky), (fx, fy - 10)], legcol, lw * (0.82 if legcol == skin else 1.0))
            if cos in ("kurta", "shirt", "salwar", "kurta_kid") and legcol != skin:
                cv.drawPath(poly([(fx - 24, fy - 30), (fx + 24, fy - 30)], close=False), stroke(skin, 22))
        # chappal / jutti
        foot = oval(fx + 14, fy - 6, 42 if not kid else 32, 15 if not kid else 12)
        fill_ink(cv, foot, look["shoes"], w=4.5)
        cv.drawPath(oval(fx + 18, fy - 14, 20, 9), paint(skin))
    # ----- lower garment over the legs
    swing = (P["r_hip"] - P["l_hip"]) * 0.9
    if cos in ("saree", "pavadai", "royal_f"):
        hem_y = -8
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
        for side, hx, kx, ky, fx, fy in feet:
            leg = poly([(side * 4, hip_y - 20), (side * (waist + 8), hip_y - 20), (fx + side * 34, fy - 18),
                        (fx - side * 26, fy - 18)])
            fill_ink(cv, leg, col)
            cv.drawPath(poly([(fx - 26, fy - 22), (fx + 34, fy - 22)], close=False),
                        stroke(rgb("d8a72c") if cos == "dhoti" else sec, 6))
        cv.drawPath(poly([(0, hip_y - 10), (swing * 0.2, -40)], close=False), stroke(shade(col, 0.82), 6))
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
        for side, hx, kx, ky, fx, fy in feet:
            leg = poly([(side * 2, hip_y - 20), (side * (waist + 4), hip_y - 20), (kx + side * 28, ky - 8), (kx - side * 22, ky - 8)])
            fill_ink(cv, leg, look["pants"] if look["pants"] != rgb("f4f1e8") else rgb("3a4a6b"))

    # ----- torso
    top_col = main
    if cos == "lungi" and look.get("vest"):
        top_col = rgb("f7f5ef")
    if cos in ("dhoti",) and not look["old"]:
        top_col = main
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
        # blouse (short) + midriff skin + pallu drape
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
        # pallu hanging behind the left shoulder
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
    if cos == "dhoti" or look["old"] and cos == "kurta":
        pass
    # ----- neck + head
    head_r = 90 * look["head"]
    neck_top = sh_y - 24
    cv.drawPath(rrect(-21, neck_top - 10, 21, sh_y + 6, 10), paint(shade(skin, 0.86)))
    hc_y = neck_top - head_r * 0.92
    cv.save()
    cv.translate(0, neck_top)
    cv.rotate(P["head_tilt"])
    cv.translate(0, -neck_top)
    draw_head(cv, look, P, 0, hc_y, head_r, t)
    cv.restore()
    if look.get("bangles") or True:
        pass
    # ----- arms (last so gestures cross the body); hold object drawn in hand
    hands = {}
    up, lo = (110, 104) if not kid else (80, 76)
    sleeve_long = cos in ("kurta", "shirt", "royal", "kurta_kid", "salwar") or (cos == "dhoti")
    sleeve_col = top_col if cos not in ("saree", "pavadai", "royal_f") else (sec if cos != "pavadai" else main)
    if cos == "lungi" and look.get("vest"):
        sleeve_col = None
    for side, key in ((-1, "lh"), (1, "rh")):
        sx, sy = side * (sh_x - 12), sh_y + 16
        out, down = P[key]
        tx, ty = sx + side * out, sy + down
        (ex, ey), (hx, hy) = _ik(sx, sy, tx, ty, up, lo, side)
        aw = 38 if not kid else 30
        _limb(cv, [(sx, sy), (ex, ey), (hx, hy)], skin, aw)
        if sleeve_col is not None:
            if sleeve_long:
                cv.drawPath(poly([(sx, sy), (ex, ey), (ex + (hx - ex) * 0.75, ey + (hy - ey) * 0.75)], close=False),
                            stroke(sleeve_col, aw + 2))
            else:
                cv.drawPath(poly([(sx, sy), (sx + (ex - sx) * 0.6, sy + (ey - sy) * 0.6)], close=False),
                            stroke(sleeve_col, aw + 10, cap=skia.Paint.kButt_Cap))
        if look.get("bangles"):
            bx, by = ex + (hx - ex) * 0.8, ey + (hy - ey) * 0.8
            cv.drawCircle(bx, by, 20, stroke(rgb("e8b923"), 5))
            cv.drawCircle(bx + (hx - ex) * 0.05, by + (hy - ey) * 0.05, 20, stroke(rgb("d9343b"), 4))
        fill_ink(cv, oval(hx, hy + 3, 23 if not kid else 19, 25 if not kid else 21), skin, w=4.5)
        hands[key] = (hx, hy)
    if look.get("stick"):
        hx, hy = hands["lh"]
        cv.drawPath(poly([(hx, hy - 30), (hx - 12, 0)], close=False), stroke(INK, 16))
        cv.drawPath(poly([(hx, hy - 30), (hx - 12, 0)], close=False), stroke(rgb("8b5a34"), 10))
    if P.get("hold"):
        import long_props
        key = "rh" if P.get("hold_hand", "r") == "r" else "lh"
        hx, hy = hands[key]
        long_props.draw_object(cv, P["hold"], hx, hy - 10, 1.0, t)
    P["_hands"] = hands


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
        cv.drawPath(oval(fx + sd * r * 0.55, cy + r * 0.42, r * 0.17, r * 0.1), paint(rgb("f07a7a"), 60 + int(90 * red)))
    # ---- eyes
    gx, gy = P.get("gaze", (0, 0))
    blink = max(0.0, min(1.0, P.get("blink", 0.0)))
    eo = P.get("eye_open", 1.0)
    he = P.get("happy_eyes", 0.0)
    sly = P.get("sly", 0.0)
    ey = cy + r * 0.04
    ew, eh = r * 0.19 * (0.9 + 0.1 * eo), r * 0.24 * eo
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
        pr = ew * (0.7 if eo < 1.2 else 0.5)
        cv.drawCircle(ix, iy, pr, paint(look["eye_col"]))
        cv.drawCircle(ix, iy, pr * 0.52, paint((12, 10, 12)))
        cv.drawCircle(ix - ew * 0.25, iy - ew * 0.3, ew * 0.2, paint((255, 255, 255)))
        lidc = max(blink, sly * 0.55)
        if lidc > 0:
            cv.drawRect(skia.Rect.MakeLTRB(ex - ew - 2, ey - eh - 2, ex + ew + 2, ey - eh + 2 * eh * lidc), paint(fskin))
            cv.drawPath(poly([(ex - ew, ey - eh + 2 * eh * lidc), (ex + ew, ey - eh + 2 * eh * lidc)], close=False),
                        stroke(INK, 4))
        cv.restore()
        cv.drawPath(eye, stroke(INK, 4.5))
        if look["female"]:
            lash = skia.Path(); lash.moveTo(ex + sd * ew * 0.6, ey - eh * 0.75); lash.lineTo(ex + sd * ew * 1.2, ey - eh * 1.0)
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
    if grin > 0.5 and mo < 0.3:   # toothy greedy grin
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
        oh = r * (0.12 + 0.18 * om)
        p = oval(fx, my + oh * 0.4, mw * 0.55 + 4, oh)
        cv.drawPath(p, paint(rgb("5a1e24")))
        cv.drawPath(p, stroke(INK, 4))
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
