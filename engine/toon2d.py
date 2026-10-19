#!/usr/bin/env python3
"""Bounce Bhai 2D cartoon kit (skia vector drawing, 1080x1920 native).

Characters are puppets drawn from a "look" (skin, hair style + colour, clothes, accessories, proportions) and a
"pose" (arm/leg angles, lean, head tilt, mouth, blink, gaze, brows) every frame, so they can talk, blink, walk,
point, jump, sit, celebrate ... with no rendering noise and razor-sharp edges at any resolution.
"""
import math
import random

import skia

W, H = 1080, 1920

# ----------------------------------------------------------------------------------------------- colours
def rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def C(c, a=255):
    return skia.ColorSetARGB(a, int(c[0]), int(c[1]), int(c[2]))


def shade(c, k):
    """k<1 darker, k>1 lighter (towards white)."""
    if k <= 1:
        return tuple(max(0, min(255, v * k)) for v in c)
    t = k - 1
    return tuple(max(0, min(255, v + (255 - v) * t)) for v in c)


def mix(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


INK = (38, 28, 34)
SKINS = [rgb("f6d3b3"), rgb("eec19a"), rgb("d9a37c"), rgb("c08a5e"), rgb("9c6b45"), rgb("7a5234")]
HAIRS = [rgb("1d1716"), rgb("2e211c"), rgb("4a3020"), rgb("6b4426"), rgb("b9b6b2")]
CLOTH = {  # story colour -> cloth rgb
    "red": rgb("e8463d"), "blue": rgb("3b7de0"), "green": rgb("3fb36b"), "yellow": rgb("f4c22b"),
    "orange": rgb("f28a2e"), "purple": rgb("8b5cd6"), "pink": rgb("ef6fa8"), "white": rgb("f2f2ee"),
    "black": rgb("3a3a44"), "teal": rgb("1fa7a0"), "brown": rgb("9a6a43"), "grey": rgb("8d939c"),
    "gray": rgb("8d939c"),
}
PANTS = [rgb("2f3e66"), rgb("3b3b45"), rgb("6b5a45"), rgb("1f5f63"), rgb("5a4a72"), rgb("d8c9a8")]


def paint(c, a=255, aa=True):
    return skia.Paint(AntiAlias=aa, Color=C(c, a))


def stroke(c, w, a=255, cap=skia.Paint.kRound_Cap):
    return skia.Paint(AntiAlias=True, Color=C(c, a), Style=skia.Paint.kStroke_Style, StrokeWidth=w,
                      StrokeCap=cap, StrokeJoin=skia.Paint.kRound_Join)


def fill_ink(cv, path, col, ink=INK, w=5.0, a=255):
    cv.drawPath(path, paint(col, a))
    if w > 0:
        cv.drawPath(path, stroke(ink, w, a))


def oval(cx, cy, rx, ry):
    p = skia.Path()
    p.addOval(skia.Rect.MakeLTRB(cx - rx, cy - ry, cx + rx, cy + ry))
    return p


def rrect(l, t, r, b, rad):
    p = skia.Path()
    p.addRRect(skia.RRect.MakeRectXY(skia.Rect.MakeLTRB(l, t, r, b), rad, rad))
    return p


def poly(pts, close=True):
    p = skia.Path()
    p.moveTo(*pts[0])
    for q in pts[1:]:
        p.lineTo(*q)
    if close:
        p.close()
    return p


def smooth_closed(pts):
    """Closed Catmull-Rom-ish smooth path through points."""
    p = skia.Path()
    n = len(pts)
    p.moveTo((pts[0][0] + pts[1][0]) / 2, (pts[0][1] + pts[1][1]) / 2)
    for i in range(1, n + 1):
        a, b = pts[i % n], pts[(i + 1) % n]
        p.quadTo(a[0], a[1], (a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    p.close()
    return p


def soft_shadow(cv, cx, cy, rx, ry, a=70):
    pt = skia.Paint(AntiAlias=True, Color=C((0, 0, 0), a),
                    MaskFilter=skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, ry * 0.45))
    cv.drawOval(skia.Rect.MakeLTRB(cx - rx, cy - ry, cx + rx, cy + ry), pt)


# ----------------------------------------------------------------------------------------------- looks
MALE_HAIR = ["short", "side_part", "spiky", "curly", "quiff", "buzz"]
FEMALE_HAIR = ["long", "bun", "ponytail", "bob", "braid", "long_wavy"]


def make_look(ctype, color, rng):
    """A character's fixed appearance. rng: random.Random seeded per story+character (deterministic)."""
    female = ctype in ("woman", "girl", "grandma")
    kid = ctype in ("boy", "girl")
    old = ctype in ("grandpa", "grandma")
    look = {
        "type": ctype, "female": female, "kid": kid, "old": old,
        "skin": rng.choice(SKINS),
        "hair_col": HAIRS[4] if old else rng.choices(HAIRS[:4], weights=[5, 4, 2, 1])[0],
        "hair": rng.choice(FEMALE_HAIR if female else MALE_HAIR),
        "top": CLOTH.get(color, CLOTH["blue"]),
        "top_style": rng.choice(["tee", "shirt", "kurta", "hoodie"] if not female else
                                ["tee", "kurti", "top", "saree"] if not kid else ["tee", "frock", "top"]),
        "pants": rng.choice(PANTS),
        "shoes": rng.choice([rgb("2b2b33"), rgb("6b3f25"), rgb("e9e9e9"), rgb("c0392b")]),
        "glasses": (rng.random() < (0.55 if old else 0.18)) or ctype == "scientist",
        "moustache": (not female and not kid and rng.random() < (0.6 if old else 0.35)),
        "beard": (not female and not kid and rng.random() < (0.25 if old else 0.12)),
        "bindi": female and not kid and rng.random() < 0.55,
        "earrings": female and rng.random() < 0.6,
        "cap": (not female and rng.random() < 0.12),
        "eye_col": rng.choice([rgb("3b2a20"), rgb("4a3326"), rgb("2a1d16")]),
        "cheeks": rng.random() < 0.7,
        "height": {"man": 1.0, "woman": 0.95, "boy": 0.72, "girl": 0.7, "grandpa": 0.93, "grandma": 0.88,
                   "scientist": 1.0, "robot": 0.95}.get(ctype, 1.0) * rng.uniform(0.97, 1.03),
        "width": rng.uniform(0.94, 1.12) * (1.08 if old and not female else 1.0),
        "head": 1.18 if kid else 1.0,
    }
    if ctype == "scientist":
        look["top_style"] = "labcoat"
    if old and not female:
        look["hair"] = rng.choice(["bald_ring", "short", "side_part"])
    if old and female:
        look["hair"] = "bun"
        if look["top_style"] not in ("saree", "kurti"):
            look["top_style"] = rng.choice(["saree", "kurti"])
    if ctype == "robot":
        look.update({"robot": True, "glasses": False, "moustache": False, "beard": False})
    return look


def rest_pose():
    return {"x": 540.0, "y": 1500.0, "scale": 1.0, "lean": 0.0, "bob": 0.0, "head_tilt": 0.0, "head_turn": 0.0,
            # arm angles in degrees from straight down; positive swings the arm outward (away from the body)
            "l_sh": 8.0, "l_el": 10.0, "r_sh": 8.0, "r_el": 10.0,
            "l_hip": 0.0, "l_knee": 0.0, "r_hip": 0.0, "r_knee": 0.0,
            "mouth": 0.0, "smile": 0.5, "blink": 0.0, "gaze": (0.0, 0.0), "brow": 0.0, "brow_up": 0.0,
            "sit": 0.0, "squash": 0.0, "facing": 1}


# ----------------------------------------------------------------------------------------------- puppet
def draw_character(cv, look, P):
    """Draw at pose P. Units: the character is ~640 px tall at scale 1 (adult)."""
    if look.get("robot"):
        return draw_robot(cv, look, P)
    s = P["scale"] * look["height"]
    cv.save()
    cv.translate(P["x"], P["y"])
    soft_shadow(cv, 0, 0, 120 * s * look["width"], 26 * s)
    cv.scale(s, s)
    sq = P.get("squash", 0.0)
    cv.scale(1 + 0.12 * sq, 1 - 0.12 * sq)
    cv.translate(0, -P["bob"])
    cv.rotate(P["lean"])
    wdt = look["width"]
    kid, fem = look["kid"], look["female"]
    leg_len = 230 if not kid else 165
    hip_y = -leg_len - 10 + P.get("sit", 0) * 95
    torso_h = 215 if not kid else 160
    sh_y = hip_y - torso_h
    sh_x = 72 * wdt if not fem else 64 * wdt
    top, top_d = look["top"], shade(look["top"], 0.78)
    skin = look["skin"]
    pants = look["pants"]
    long_top = look["top_style"] in ("kurta", "kurti", "labcoat", "saree", "frock")

    # ---- legs
    sit = P.get("sit", 0)
    for side, hip_a, knee_a in ((-1, P["l_hip"], P["l_knee"]), (1, P["r_hip"], P["r_knee"])):
        hx = side * 34 * wdt
        a1 = math.radians(hip_a * side + sit * -85 * 0)  # hips bend forward when sitting (drawn in 2D as shorter)
        thigh = leg_len * 0.5 * (1 - 0.45 * sit)
        kx = hx + math.sin(math.radians(hip_a)) * thigh + side * sit * 36
        ky = hip_y + math.cos(math.radians(hip_a)) * thigh
        a2 = math.radians(hip_a - knee_a)
        shin = leg_len * 0.5
        fx = kx + math.sin(a2) * shin
        fy = ky + math.cos(a2) * shin
        lw = 62 if not kid else 50
        legcol = skin if (look["top_style"] in ("frock",) or (look["top_style"] == "saree")) else pants
        if look["top_style"] == "saree":
            legcol = top
        cv.drawPath(poly([(hx, hip_y), (kx, ky), (fx, fy)], close=False), stroke(INK, lw + 9))
        cv.drawPath(poly([(hx, hip_y), (kx, ky), (fx, fy)], close=False), stroke(legcol, lw))
        # shoe
        shoe = oval(fx + side * 10, fy + 6, 44 if not kid else 36, 22 if not kid else 19)
        fill_ink(cv, shoe, look["shoes"], w=5)
        cv.drawPath(oval(fx + side * 16, fy - 2, 16, 6), paint(shade(look["shoes"], 1.5), 120))

    # ---- torso
    waist = 66 * wdt if not fem else 56 * wdt
    hem = hip_y + (95 if long_top else 18)
    hem_w = (waist + (34 if long_top else 6)) if not look["top_style"] == "frock" else waist + 60
    torso = skia.Path()
    torso.moveTo(-sh_x, sh_y + 18)
    torso.quadTo(-sh_x - 4, sh_y - 6, -sh_x + 30, sh_y - 8)
    torso.lineTo(sh_x - 30, sh_y - 8)
    torso.quadTo(sh_x + 4, sh_y - 6, sh_x, sh_y + 18)
    torso.quadTo(waist + 10, (sh_y + hip_y) / 2, waist, hip_y - 10)
    torso.lineTo(hem_w, hem)
    torso.quadTo(0, hem + 14, -hem_w, hem)
    torso.lineTo(-waist, hip_y - 10)
    torso.quadTo(-waist - 10, (sh_y + hip_y) / 2, -sh_x, sh_y + 18)
    torso.close()
    if look["top_style"] == "labcoat":
        fill_ink(cv, torso, rgb("f4f6f8"))
        inner = poly([(-30, sh_y - 6), (30, sh_y - 6), (22, hem - 30), (-22, hem - 30)])
        cv.drawPath(inner, paint(top))
        cv.drawPath(poly([(0, sh_y - 4), (0, hem + 4)], close=False), stroke(INK, 4))
        cv.drawPath(poly([(-30, sh_y - 6), (-6, sh_y + 70), (-44, sh_y + 8)], close=True), paint(rgb("e3e7ec")))
        cv.drawPath(poly([(30, sh_y - 6), (6, sh_y + 70), (44, sh_y + 8)], close=True), paint(rgb("e3e7ec")))
        cv.drawPath(rrect(28, sh_y + 60, 62, sh_y + 92, 4), stroke(INK, 3.5))
    else:
        fill_ink(cv, torso, top)
        # soft side shading
        cv.save(); cv.clipPath(torso, doAntiAlias=True)
        cv.drawPath(oval(waist + 40, (sh_y + hem) / 2, 60, 200), paint(top_d, 150))
        cv.restore()
        cv.drawPath(torso, stroke(INK, 5))
        st = look["top_style"]
        if st in ("shirt", "kurta", "kurti"):
            cv.drawPath(poly([(0, sh_y - 6), (0, sh_y + (70 if st != "shirt" else hem - sh_y - 10))], close=False),
                        stroke(shade(top, 0.6), 4))
            for k in range(3 if st != "shirt" else 4):
                cv.drawCircle(0, sh_y + 22 + k * 22, 4.5, paint(shade(top, 0.55)))
            col = poly([(-34, sh_y - 8), (0, sh_y + 26), (34, sh_y - 8), (18, sh_y - 14), (0, sh_y + 6), (-18, sh_y - 14)])
            fill_ink(cv, col, shade(top, 1.18), w=4)
        elif st == "hoodie":
            cv.drawPath(oval(0, sh_y + 4, 58, 22), stroke(shade(top, 0.7), 10))
            cv.drawPath(rrect(-50, hip_y - 70, 50, hip_y - 20, 16), stroke(shade(top, 0.7), 4))
            cv.drawPath(poly([(-14, sh_y + 16), (-18, sh_y + 70)], close=False), stroke(rgb("f2f2f2"), 4))
            cv.drawPath(poly([(14, sh_y + 16), (18, sh_y + 70)], close=False), stroke(rgb("f2f2f2"), 4))
        elif st == "saree":
            drape = poly([(sh_x - 8, sh_y - 4), (sh_x - 40, sh_y - 8), (-waist + 4, hip_y + 30), (-waist + 40, hip_y + 50),
                          (sh_x + 2, sh_y + 30)])
            fill_ink(cv, drape, shade(top, 1.22), w=4)
            cv.drawPath(poly([(sh_x - 36, sh_y - 6), (-waist + 8, hip_y + 34)], close=False), stroke(rgb("f2c84b"), 7))
        elif st in ("tee", "top", "frock"):
            cv.drawPath(oval(0, sh_y - 4, 34, 13), paint(shade(top, 0.72)))
            if st == "frock":
                cv.drawPath(poly([(-hem_w + 6, hem - 16), (hem_w - 6, hem - 16)], close=False), stroke(rgb("fff4c2"), 7))
    # pants/waist band visible below short tops
    if not long_top:
        cv.drawPath(rrect(-waist + 2, hip_y + 4, waist - 2, hip_y + 26, 8), paint(shade(pants, 0.85)))

    # ---- neck + head
    head_r = 92 * look["head"]
    neck_top = sh_y - 26
    cv.drawPath(rrect(-22, neck_top - 10, 22, sh_y + 6, 10), paint(shade(skin, 0.86)))
    hc_y = neck_top - head_r * 0.92
    cv.save()
    cv.translate(0, neck_top)
    cv.rotate(P["head_tilt"])
    cv.translate(0, -neck_top)
    draw_head(cv, look, P, 0, hc_y, head_r)
    cv.restore()

    # ---- arms (drawn last so gestures cross the body)
    for side, sh_a, el_a in ((-1, P["l_sh"], P["l_el"]), (1, P["r_sh"], P["r_el"])):
        draw_arm(cv, look, side, side * (sh_x - 12), sh_y + 16, sh_a, el_a, kid)
    cv.restore()


def draw_arm(cv, look, side, sx, sy, sh_a, el_a, kid):
    up = 112 if not kid else 84
    lo = 106 if not kid else 80
    a1 = math.radians(sh_a)
    ex = sx + side * math.sin(a1) * up
    ey = sy + math.cos(a1) * up
    a2 = math.radians(sh_a + el_a)
    hx = ex + side * math.sin(a2) * lo
    hy = ey + math.cos(a2) * lo
    sleeve = look["top"] if look["top_style"] != "labcoat" else rgb("f4f6f8")
    long_sleeve = look["top_style"] in ("shirt", "hoodie", "labcoat", "kurta")
    aw = 40 if not kid else 33
    cv.drawPath(poly([(sx, sy), (ex, ey), (hx, hy)], close=False), stroke(INK, aw + 9))
    cv.drawPath(poly([(sx, sy), (ex, ey), (hx, hy)], close=False), stroke(look["skin"], aw))
    if long_sleeve:
        cv.drawPath(poly([(sx, sy), (ex, ey), (ex + (hx - ex) * 0.82, ey + (hy - ey) * 0.82)], close=False),
                    stroke(sleeve, aw + 2))
    else:
        cv.drawPath(poly([(sx, sy), (sx + (ex - sx) * 0.55, sy + (ey - sy) * 0.55)], close=False),
                    stroke(sleeve, aw + 8, cap=skia.Paint.kButt_Cap))
    hand = oval(hx, hy + 4, 25 if not kid else 21, 27 if not kid else 23)
    fill_ink(cv, hand, look["skin"], w=4.5)
    return hx, hy


def draw_head(cv, look, P, cx, cy, r):
    skin, hairc = look["skin"], look["hair_col"]
    turn = P.get("head_turn", 0.0) * 14
    hs = look["hair"]
    # back hair (long styles) behind the head
    if hs in ("long", "long_wavy", "braid", "ponytail"):
        if hs in ("long", "long_wavy"):
            back = smooth_closed([(cx - r * 1.08, cy - r * 0.3), (cx - r * 1.15, cy + r * 0.9), (cx - r * 0.7, cy + r * 1.55),
                                  (cx + r * 0.7, cy + r * 1.55), (cx + r * 1.15, cy + r * 0.9), (cx + r * 1.08, cy - r * 0.3),
                                  (cx, cy - r * 1.15)])
            fill_ink(cv, back, hairc, w=5)
        elif hs == "braid":
            for k in range(5):
                fill_ink(cv, oval(cx + r * 0.85, cy + r * (0.35 + k * 0.32), r * 0.2, r * 0.2), hairc, w=4)
        else:
            fill_ink(cv, oval(cx, cy - r * 0.95, r * 0.42, r * 0.36), hairc, w=4)
            fill_ink(cv, smooth_closed([(cx - r * 0.12, cy - r * 1.2), (cx + r * 0.25, cy - r * 1.35),
                                        (cx + r * 0.42, cy - r * 0.2), (cx + r * 0.1, cy + r * 0.2)]), hairc, w=4)
    # ears
    for sd in (-1, 1):
        fill_ink(cv, oval(cx + sd * r * 0.98 + turn * 0.3, cy + r * 0.08, r * 0.17, r * 0.24), shade(skin, 0.95), w=4.5)
        if look.get("earrings"):
            cv.drawCircle(cx + sd * r * 0.98 + turn * 0.3, cy + r * 0.36, r * 0.07, paint(rgb("f2c84b")))
    # face shape: slightly squarer jaw for men
    jaw = 0.88 if look["female"] or look["kid"] else 0.95
    face = smooth_closed([(cx, cy - r * 1.05), (cx + r * 0.98, cy - r * 0.55), (cx + r * 1.0, cy + r * 0.25),
                          (cx + r * 0.72 * jaw, cy + r * 0.88), (cx, cy + r * 1.08), (cx - r * 0.72 * jaw, cy + r * 0.88),
                          (cx - r * 1.0, cy + r * 0.25), (cx - r * 0.98, cy - r * 0.55)])
    fill_ink(cv, face, skin, w=5)
    cv.save(); cv.clipPath(face, doAntiAlias=True)
    cv.drawPath(oval(cx + r * 0.9, cy + r * 0.3, r * 0.4, r * 1.1), paint(shade(skin, 0.9), 140))
    cv.restore()
    cv.drawPath(face, stroke(INK, 5))
    fx = cx + turn
    if look.get("beard"):
        b = smooth_closed([(fx - r * 0.82, cy + r * 0.2), (fx - r * 0.6, cy + r * 0.95), (fx, cy + r * 1.18),
                           (fx + r * 0.6, cy + r * 0.95), (fx + r * 0.82, cy + r * 0.2), (fx, cy + r * 0.62)])
        fill_ink(cv, b, hairc, w=4)
    # cheeks
    if look.get("cheeks"):
        for sd in (-1, 1):
            cv.drawPath(oval(fx + sd * r * 0.55, cy + r * 0.42, r * 0.17, r * 0.1), paint(rgb("f08a8a"), 70))
    # eyes
    gx, gy = P.get("gaze", (0, 0))
    blink = max(0.0, min(1.0, P.get("blink", 0.0)))
    ey = cy + r * 0.05
    ew, eh = r * 0.2, r * 0.25
    for sd in (-1, 1):
        ex = fx + sd * r * 0.38
        if blink > 0.85:
            lid = skia.Path(); lid.moveTo(ex - ew, ey + eh * 0.1); lid.quadTo(ex, ey + eh * 0.55, ex + ew, ey + eh * 0.1)
            cv.drawPath(lid, stroke(INK, 5.5))
            continue
        eye = oval(ex, ey, ew, eh)
        cv.drawPath(eye, paint((255, 255, 255)))
        cv.save(); cv.clipPath(eye, doAntiAlias=True)
        ix, iy = ex + gx * ew * 0.45, ey + gy * eh * 0.35 + eh * 0.08
        cv.drawCircle(ix, iy, ew * 0.72, paint(look["eye_col"]))
        cv.drawCircle(ix, iy, ew * 0.38, paint((12, 10, 12)))
        cv.drawCircle(ix - ew * 0.25, iy - ew * 0.3, ew * 0.2, paint((255, 255, 255)))
        if blink > 0:
            cv.drawRect(skia.Rect.MakeLTRB(ex - ew - 2, ey - eh - 2, ex + ew + 2, ey - eh + 2 * eh * blink), paint(skin))
        cv.restore()
        cv.drawPath(eye, stroke(INK, 4.5))
        if look["female"]:
            lash = skia.Path(); lash.moveTo(ex + sd * ew * 0.6, ey - eh * 0.75); lash.lineTo(ex + sd * ew * 1.15, ey - eh * 1.0)
            cv.drawPath(lash, stroke(INK, 4))
    # brows
    bu = P.get("brow_up", 0.0) * r * 0.12
    bang = P.get("brow", 0.0)  # +1 angry/focused (inner down), -1 worried (inner up)
    for sd in (-1, 1):
        bx = fx + sd * r * 0.38
        by = ey - eh - r * 0.14 - bu
        p = skia.Path()
        p.moveTo(bx - sd * r * 0.2, by + bang * r * 0.08)
        p.quadTo(bx, by - r * 0.06, bx + sd * r * 0.2, by - bang * r * 0.03)
        cv.drawPath(p, stroke(hairc if not look["old"] else shade(hairc, 0.7), 7 if not look["female"] else 5.5))
    # nose
    n = skia.Path(); n.moveTo(fx + r * 0.02, ey + r * 0.12); n.quadTo(fx + r * 0.12, ey + r * 0.36, fx - r * 0.04, ey + r * 0.38)
    cv.drawPath(n, stroke(shade(skin, 0.62), 4.5))
    if look.get("bindi"):
        cv.drawCircle(fx, ey - eh - r * 0.2, r * 0.05, paint(rgb("d8262f")))
    # mouth
    mo = max(0.0, min(1.0, P.get("mouth", 0.0)))
    sm = P.get("smile", 0.5)
    my = cy + r * 0.66
    mw = r * (0.26 + 0.06 * mo)
    if mo < 0.08:
        p = skia.Path(); p.moveTo(fx - mw, my - sm * r * 0.06); p.quadTo(fx, my + sm * r * 0.16, fx + mw, my - sm * r * 0.06)
        cv.drawPath(p, stroke(rgb("6d2b2b"), 5.5))
    else:
        mh = r * (0.06 + 0.26 * mo)
        p = skia.Path()
        p.moveTo(fx - mw, my - sm * r * 0.04)
        p.quadTo(fx, my - mh * 0.25 + sm * r * 0.02, fx + mw, my - sm * r * 0.04)
        p.quadTo(fx + mw * 0.6, my + mh * 1.1, fx, my + mh * 1.05)
        p.quadTo(fx - mw * 0.6, my + mh * 1.1, fx - mw, my - sm * r * 0.04)
        p.close()
        cv.drawPath(p, paint(rgb("5a1e24")))
        cv.save(); cv.clipPath(p, doAntiAlias=True)
        cv.drawPath(oval(fx, my + mh * 1.05, mw * 0.55, mh * 0.45), paint(rgb("e0646e")))
        cv.drawRect(skia.Rect.MakeLTRB(fx - mw, my - mh, fx + mw, my + mh * 0.12), paint((250, 250, 248)))
        cv.restore()
        cv.drawPath(p, stroke(INK, 4))
    if look.get("moustache"):
        m = skia.Path()
        m.moveTo(fx, my - r * 0.12)
        m.cubicTo(fx - r * 0.2, my - r * 0.24, fx - r * 0.36, my - r * 0.06, fx - r * 0.42, my + r * 0.02)
        m.cubicTo(fx - r * 0.3, my - r * 0.02, fx - r * 0.16, my - r * 0.06, fx, my - r * 0.04)
        m.cubicTo(fx + r * 0.16, my - r * 0.06, fx + r * 0.3, my - r * 0.02, fx + r * 0.42, my + r * 0.02)
        m.cubicTo(fx + r * 0.36, my - r * 0.06, fx + r * 0.2, my - r * 0.24, fx, my - r * 0.12)
        fill_ink(cv, m, hairc, w=3)
    if look.get("glasses"):
        for sd in (-1, 1):
            cv.drawPath(rrect(fx + sd * r * 0.38 - r * 0.29, ey - r * 0.25, fx + sd * r * 0.38 + r * 0.29, ey + r * 0.25,
                              r * 0.1), stroke(rgb("2a2a30"), 6))
        cv.drawPath(poly([(fx - r * 0.09, ey - r * 0.05), (fx + r * 0.09, ey - r * 0.05)], close=False), stroke(rgb("2a2a30"), 6))
    draw_hair_front(cv, look, cx, cy, r, turn)


def draw_hair_front(cv, look, cx, cy, r, turn):
    hs, hc = look["hair"], look["hair_col"]
    t = turn * 0.6
    if look.get("cap"):
        cap = skia.Path()
        cap.moveTo(cx - r * 1.02, cy - r * 0.35)
        cap.cubicTo(cx - r * 1.0, cy - r * 1.35, cx + r * 1.0, cy - r * 1.35, cx + r * 1.02, cy - r * 0.35)
        cap.close()
        fill_ink(cv, cap, shade(look["top"], 0.8), w=5)
        fill_ink(cv, rrect(cx - r * 0.2 + t, cy - r * 0.48, cx + r * 1.35 + t, cy - r * 0.3, r * 0.1), shade(look["top"], 0.7), w=4)
        return
    if hs == "bald_ring":
        for sd in (-1, 1):
            fill_ink(cv, smooth_closed([(cx + sd * r * 1.02, cy - r * 0.45), (cx + sd * r * 0.82, cy - r * 0.72),
                                        (cx + sd * r * 0.78, cy - r * 0.1), (cx + sd * r * 1.04, cy + r * 0.05)]), hc, w=4)
        return
    if hs == "buzz":
        p = skia.Path(); p.moveTo(cx - r * 0.98, cy - r * 0.35)
        p.cubicTo(cx - r * 1.0, cy - r * 1.32, cx + r * 1.0, cy - r * 1.32, cx + r * 0.98, cy - r * 0.35)
        p.quadTo(cx, cy - r * 0.78, cx - r * 0.98, cy - r * 0.35); p.close()
        fill_ink(cv, p, hc, w=4)
        return
    # a cap of hair over the top of the head + a style-specific fringe
    top = skia.Path()
    top.moveTo(cx - r * 1.04, cy - r * 0.1)
    top.cubicTo(cx - r * 1.12, cy - r * 1.42, cx + r * 1.12, cy - r * 1.42, cx + r * 1.04, cy - r * 0.1)
    if hs in ("side_part", "short", "quiff"):
        top.quadTo(cx + r * 0.9, cy - r * 0.62, cx + r * 0.5 + t, cy - r * 0.66)
        top.quadTo(cx - r * 0.1 + t, cy - r * 0.5, cx - r * 0.55 + t, cy - r * 0.62)
        top.quadTo(cx - r * 0.9, cy - r * 0.6, cx - r * 1.04, cy - r * 0.1)
    elif hs == "spiky":
        pts = [(cx + r * 0.95, cy - r * 0.55)]
        for k in range(7):
            x = cx + r * (0.8 - k * 0.27) + t
            pts.append((x, cy - r * (0.58 if k % 2 == 0 else 0.78)))
        for x, y in pts:
            top.lineTo(x, y)
        top.lineTo(cx - r * 1.04, cy - r * 0.1)
    elif hs == "curly":
        top.quadTo(cx, cy - r * 0.58, cx - r * 1.04, cy - r * 0.1)
    else:  # female styles: centre parting framing the face
        top.quadTo(cx + r * 0.95, cy - r * 0.4, cx + r * 0.45, cy - r * 0.78)
        top.quadTo(cx + r * 0.1, cy - r * 0.95, cx + t * 0.2, cy - r * 0.92)
        top.quadTo(cx - r * 0.1, cy - r * 0.95, cx - r * 0.45, cy - r * 0.78)
        top.quadTo(cx - r * 0.95, cy - r * 0.4, cx - r * 1.04, cy - r * 0.1)
    top.close()
    fill_ink(cv, top, hc, w=5)
    if hs == "curly":
        for k in range(9):
            a = math.pi * (0.08 + 0.84 * k / 8)
            fill_ink(cv, oval(cx - math.cos(a) * r * 0.98, cy - r * 0.35 - math.sin(a) * r * 0.85, r * 0.24, r * 0.22), hc, w=4)
    if hs == "quiff":
        fill_ink(cv, smooth_closed([(cx - r * 0.4 + t, cy - r * 0.9), (cx + r * 0.1 + t, cy - r * 1.42),
                                    (cx + r * 0.8 + t, cy - r * 1.2), (cx + r * 0.6 + t, cy - r * 0.8)]), hc, w=4)
    if hs == "bun":
        fill_ink(cv, oval(cx, cy - r * 1.22, r * 0.38, r * 0.3), hc, w=4)
    if hs == "bob":
        for sd in (-1, 1):
            fill_ink(cv, smooth_closed([(cx + sd * r * 1.06, cy - r * 0.4), (cx + sd * r * 1.12, cy + r * 0.62),
                                        (cx + sd * r * 0.7, cy + r * 0.58), (cx + sd * r * 0.78, cy - r * 0.55)]), hc, w=4)
    # glossy highlight
    cv.drawPath(oval(cx - r * 0.35, cy - r * 0.98, r * 0.28, r * 0.08), paint((255, 255, 255), 55))


def draw_robot(cv, look, P):
    s = P["scale"] * look["height"]
    body = look["top"]
    cv.save(); cv.translate(P["x"], P["y"])
    soft_shadow(cv, 0, 0, 120 * s, 26 * s)
    cv.scale(s, s); cv.translate(0, -P["bob"]); cv.rotate(P["lean"])
    metal, dark = rgb("c9d1db"), rgb("5b6472")
    for side, hip in ((-1, P["l_hip"]), (1, P["r_hip"])):
        x = side * 40
        cv.save(); cv.translate(x, -230); cv.rotate(-hip * side * 0.6)
        fill_ink(cv, rrect(-22, 0, 22, 200, 14), metal)
        fill_ink(cv, rrect(-38, 190, 38, 232, 16), dark)
        cv.restore()
    fill_ink(cv, rrect(-105, -470, 105, -220, 40), body)
    fill_ink(cv, rrect(-60, -420, 60, -300, 16), rgb("1e2633"))
    for k in range(3):
        cv.drawCircle(-30 + k * 30, -360, 11, paint([rgb("7cf29a"), rgb("f2d36b"), rgb("f27b7b")][k]))
    for side, sh_a, el_a in ((-1, P["l_sh"], P["l_el"]), (1, P["r_sh"], P["r_el"])):
        sx, sy = side * 112, -440
        a1 = math.radians(sh_a); ex = sx + side * math.sin(a1) * 100; ey = sy + math.cos(a1) * 100
        a2 = math.radians(sh_a + el_a); hx = ex + side * math.sin(a2) * 95; hy = ey + math.cos(a2) * 95
        cv.drawPath(poly([(sx, sy), (ex, ey), (hx, hy)], close=False), stroke(INK, 40))
        cv.drawPath(poly([(sx, sy), (ex, ey), (hx, hy)], close=False), stroke(metal, 31))
        fill_ink(cv, oval(hx, hy, 24, 24), dark)
    cv.save(); cv.translate(0, -480); cv.rotate(P["head_tilt"])
    cv.drawPath(poly([(0, -150), (0, -200)], close=False), stroke(INK, 7))
    fill_ink(cv, oval(0, -205, 16, 16), rgb("f27b7b"))
    fill_ink(cv, rrect(-115, -160, 115, 0, 46), metal)
    fill_ink(cv, rrect(-90, -132, 90, -30, 30), rgb("1e2633"))
    blink = P.get("blink", 0)
    for sd in (-1, 1):
        h = 26 * (1 - 0.9 * blink)
        cv.drawPath(rrect(sd * 42 - 20, -84 - h / 2, sd * 42 + 20, -84 + h / 2, 10), paint(rgb("6be8ff")))
    mo = P.get("mouth", 0)
    cv.drawPath(rrect(-34, -52, 34, -44 + 18 * mo, 6), paint(rgb("6be8ff")))
    cv.restore(); cv.restore()
