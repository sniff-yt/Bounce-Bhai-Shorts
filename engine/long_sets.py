#!/usr/bin/env python3
"""Indian story sets for the long-form cartoons, 16:9, drawn in code as PARALLAX layers.

Every set paints five static layers (sky, far, mid, stage, fg) once into skia Pictures (vector, so camera push-ins
stay sharp), and a per-frame `animate` pass adds moving details: drifting clouds, flapping birds, chimney/stove
smoke, falling leaves, river shimmer, fire flicker, fireflies, twinkling stars, rain.

World units: the stage plane is the 1920x1080 frame at zoom 1; feet stand on FLOOR. Layers extend past the frame so
the camera can pan and push in. Variants: time = day | evening | night, weather = clear | rain.
"""
import math
import random

import skia

from toon2d import rgb, C, shade, mix, paint, stroke, fill_ink, oval, rrect, poly, smooth_closed, INK

W, H = 1920, 1080
FLOOR = 905
X0, X1 = -700, 2620          # world extent drawn for every layer
DEPTH = {"sky": 0.0, "far": 0.25, "mid": 0.6, "stage": 1.0, "fg": 1.3}
SETS = ["village_street", "house_interior", "field", "market", "forest", "river", "palace", "village_home",
        "school", "shop"]
SET_ALIASES = {"village": "village_street", "street": "village_street", "road": "village_street", "lane": "village_street",
               "home": "house_interior", "house": "house_interior", "hut": "house_interior", "kitchen": "house_interior",
               "room": "house_interior", "interior": "house_interior", "farm": "field", "fields": "field",
               "crop": "field", "bazaar": "market", "bazar": "market", "mela": "market", "fair": "market",
               "jungle": "forest", "woods": "forest", "lake": "river", "pond": "river", "riverbank": "river",
               "river_bank": "river", "ghat": "river", "court": "palace", "darbar": "palace", "king": "palace",
               "courtyard": "village_home", "house_outside": "village_home", "verandah": "village_home",
               "stall": "market", "store": "shop", "classroom": "school", "town": "market", "city": "market",
               "well": "village_street", "temple": "village_street", "outside": "village_street"}


def set_name(s):
    s = (s or "").lower().strip().replace(" ", "_").replace("-", "_")
    if s in SETS:
        return s
    for k, v in SET_ALIASES.items():
        if k in s:
            return v
    for k in SETS:
        if k.split("_")[0] in s:
            return k
    return "village_street"


def grad_rect(cv, l, t, r, b, c1, c2):
    p = skia.Paint(AntiAlias=False)
    p.setShader(skia.GradientShader.MakeLinear([skia.Point(0, t), skia.Point(0, b)], [C(c1), C(c2)]))
    cv.drawRect(skia.Rect.MakeLTRB(l, t, r, b), p)


SKY = {"day": (rgb("6fbdf0"), rgb("d6f0ff")), "evening": (rgb("5d4b9a"), rgb("ffb878")),
       "night": (rgb("0b1633"), rgb("27406e"))}


def _sky(cv, time, rng):
    a, b = SKY[time]
    grad_rect(cv, X0, -300, X1, FLOOR, a, b)
    cv.drawRect(skia.Rect.MakeLTRB(X0, FLOOR - 1, X1, H + 600), paint(b))
    if time == "day":
        g = skia.Paint(AntiAlias=True)
        g.setShader(skia.GradientShader.MakeRadial(skia.Point(1500, 170), 260, [C(rgb("fff6c8"), 230), C(rgb("fff6c8"), 0)]))
        cv.drawCircle(1500, 170, 260, g)
        cv.drawCircle(1500, 170, 70, paint(rgb("fff3b0")))
    elif time == "evening":
        g = skia.Paint(AntiAlias=True)
        g.setShader(skia.GradientShader.MakeRadial(skia.Point(1350, 560), 420, [C(rgb("ffd28a"), 240), C(rgb("ffd28a"), 0)]))
        cv.drawCircle(1350, 560, 420, g)
        cv.drawCircle(1350, 560, 95, paint(rgb("ffcf6b")))
    else:
        for _ in range(140):
            cv.drawCircle(rng.uniform(X0, X1), rng.uniform(-200, 600), rng.uniform(1, 2.6), paint((255, 255, 240), rng.randint(120, 255)))
        cv.drawCircle(1480, 160, 62, paint(rgb("f4f0d8")))
        cv.drawCircle(1505, 145, 58, paint(SKY["night"][0]))


def _hills(cv, y, col, rng, amp=110, n=6):
    p = skia.Path(); p.moveTo(X0, FLOOR + 200); p.lineTo(X0, y)
    xs = [X0 + (X1 - X0) * k / n for k in range(n + 1)]
    for i in range(n):
        x1, x2 = xs[i], xs[i + 1]
        p.quadTo((x1 + x2) / 2, y - amp * rng.uniform(0.5, 1.3), x2, y + rng.uniform(-20, 20))
    p.lineTo(X1, FLOOR + 200); p.close()
    cv.drawPath(p, paint(col))


def _palm(cv, x, y, s, col=rgb("2e7d4a")):
    cv.save(); cv.translate(x, y); cv.scale(s, s)
    tr = skia.Path(); tr.moveTo(-10, 0); tr.quadTo(10, -160, 40, -320); tr.lineTo(56, -318); tr.quadTo(30, -160, 12, 0); tr.close()
    cv.drawPath(tr, paint(rgb("8a6040")))
    for k in range(7):
        a = -math.pi * (0.05 + 0.9 * k / 6)
        lf = skia.Path(); lf.moveTo(48, -320)
        lf.quadTo(48 + math.cos(a) * 90, -320 + math.sin(a) * 90 - 40, 48 + math.cos(a) * 170, -320 + math.sin(a) * 120 + 50)
        cv.drawPath(lf, stroke(col, 22))
    cv.restore()


def _tree(cv, x, y, s, col=rgb("3f8f3f"), trunk=rgb("7a4f2e"), rng=None):
    cv.save(); cv.translate(x, y); cv.scale(s, s)
    fill_ink(cv, poly([(-30, 0), (-18, -260), (18, -260), (30, 0)]), trunk, w=5)
    cv.drawPath(poly([(0, -180), (-70, -280)], close=False), stroke(trunk, 18))
    for dx, dy, r in [(-110, -300, 110), (0, -380, 140), (110, -300, 110), (-60, -230, 90), (70, -230, 90), (0, -260, 110)]:
        fill_ink(cv, oval(dx, dy, r, r * 0.9), col, w=5)
    for dx, dy, r in [(-40, -400, 40), (60, -330, 34), (-120, -320, 30)]:
        cv.drawPath(oval(dx, dy, r, r * 0.7), paint(shade(col, 1.25), 150))
    cv.restore()


def _banyan(cv, x, y, s):
    cv.save(); cv.translate(x, y); cv.scale(s, s)
    fill_ink(cv, poly([(-70, 0), (-40, -300), (40, -300), (70, 0)]), rgb("6e4a2c"), w=5)
    for k in range(6):
        cv.drawPath(poly([(-200 + k * 80, -300), (-210 + k * 80, 0)], close=False), stroke(rgb("8a6040"), 6))
    for dx, dy, r in [(-230, -360, 150), (-80, -440, 180), (110, -430, 170), (250, -350, 150), (0, -330, 160)]:
        fill_ink(cv, oval(dx, dy, r, r * 0.75), rgb("2f7d3a"), w=5)
    for dx, dy in [(-100, -500), (120, -480), (-250, -390)]:
        cv.drawPath(oval(dx, dy, 60, 30), paint(rgb("4aa64f"), 160))
    cv.restore()


def _hut(cv, x, y, s, wall, roof=rgb("b8873e"), rng=None, door=True):
    cv.save(); cv.translate(x, y); cv.scale(s, s)
    fill_ink(cv, rrect(-170, -230, 170, 0, 6), wall)
    cv.drawRect(skia.Rect.MakeLTRB(-170, -36, 170, 0), paint(shade(wall, 0.75)))
    for k in range(3):   # rangoli-ish white dots band
        cv.drawCircle(-130 + k * 130, -120, 9, paint((255, 255, 255), 200))
    rf = poly([(-215, -220), (0, -380), (215, -220)])
    fill_ink(cv, rf, roof)
    for k in range(-9, 10):
        cv.drawPath(poly([(k * 22, -380 + abs(k) * 17 + 10), (k * 23, -222)], close=False), stroke(shade(roof, 0.75), 3))
    cv.drawPath(poly([(-215, -220), (215, -220)], close=False), stroke(shade(roof, 0.6), 8))
    if door:
        fill_ink(cv, rrect(-45, -150, 45, 0, 40), rgb("6b4426"))
        cv.drawPath(poly([(0, -146), (0, 0)], close=False), stroke(shade(rgb("6b4426"), 0.7), 4))
        cv.drawPath(poly([(-60, -160), (60, -160)], close=False), stroke(rgb("3f9e45"), 8))   # toran
        for k in range(5):
            cv.drawPath(poly([(-48 + k * 24, -158), (-44 + k * 24, -136), (-40 + k * 24, -158)]), paint(rgb("f5a623")))
    fill_ink(cv, rrect(90, -170, 145, -110, 4), rgb("3a2a22"), w=4)
    cv.drawPath(poly([(117, -170), (117, -110)], close=False), stroke(rgb("8b5a34"), 4))
    cv.restore()


def _house(cv, x, y, s, wall, trim):
    cv.save(); cv.translate(x, y); cv.scale(s, s)
    fill_ink(cv, rrect(-210, -330, 210, 0, 4), wall)
    fill_ink(cv, rrect(-230, -350, 230, -320, 4), trim, w=4)
    for wx in (-130, 130):
        fill_ink(cv, rrect(wx - 45, -250, wx + 45, -160, 4), rgb("3a2a22"), w=4)
        for k in range(3):
            cv.drawPath(poly([(wx - 30 + k * 30, -250), (wx - 30 + k * 30, -160)], close=False), stroke(trim, 5))
    fill_ink(cv, rrect(-50, -190, 50, 0, 6), shade(trim, 0.8))
    cv.restore()


def _stones(cv, rng, y0, y1, n=40, col=rgb("b9a888")):
    for _ in range(n):
        x, y = rng.uniform(X0, X1), rng.uniform(y0, y1)
        cv.drawPath(oval(x, y, rng.uniform(6, 16), rng.uniform(4, 8)), paint(shade(col, rng.uniform(0.8, 1.1))))


def _grass(cv, rng, y0, y1, n=60, col=rgb("4c9a3c")):
    for _ in range(n):
        x, y = rng.uniform(X0, X1), rng.uniform(y0, y1)
        for k in range(3):
            cv.drawPath(poly([(x + k * 6 - 6, y), (x + k * 8 - 10 + rng.uniform(-4, 4), y - rng.uniform(16, 30))], close=False),
                        stroke(col, 4))


def _ground(cv, top, bottom, col, rng, path=None):
    grad_rect(cv, X0, top, X1, H + 400, shade(col, 1.05), shade(col, 0.82))
    if path:
        p = skia.Path(); p.moveTo(X0, top + 30); p.lineTo(X1, top + 30); p.lineTo(X1, H + 400); p.lineTo(X0, H + 400); p.close()
        cv.drawPath(p, paint(path))
    cv.drawPath(poly([(X0, top), (X1, top)], close=False), stroke(shade(col, 0.75), 4))


# ------------------------------------------------------------------------------------------------ painters
def village_street(L, cv, rng, time):
    if L == "sky":
        _sky(cv, time, rng)
    elif L == "far":
        _hills(cv, 520, rgb("8bb6a0") if time == "day" else rgb("7a6f9a"), rng)
        _hills(cv, 600, rgb("6aa080") if time == "day" else rgb("5d5684"), rng, amp=70)
        for k in range(9):
            _palm(cv, X0 + 150 + k * 380 + rng.uniform(-60, 60), 640, rng.uniform(0.5, 0.75), rgb("3d7a50"))
    elif L == "mid":
        grad_rect(cv, X0, 640, X1, H + 500, rgb("c8a46a"), rgb("a8834c"))
        walls = [rgb("e9d3a6"), rgb("f0c27a"), rgb("d9b38a"), rgb("e6e0cf"), rgb("cfe0d0")]
        xs = [X0 + 200 + k * 520 for k in range(7)]
        for i, x in enumerate(xs):
            if i % 3 == 2:
                _banyan(cv, x + 60, 760, 0.85)
            else:
                _hut(cv, x, 770, rng.uniform(0.9, 1.05), walls[i % len(walls)], rng=rng)
    elif L == "stage":
        _ground(cv, 760, H, rgb("d8b47c"), rng)
        p = skia.Path(); p.moveTo(X0, 820); p.quadTo(960, 800, X1, 830); p.lineTo(X1, 1000); p.quadTo(960, 980, X0, 1000); p.close()
        cv.drawPath(p, paint(rgb("e6c793")))
        _stones(cv, rng, 780, 1060, 60)
        _grass(cv, rng, 770, 800, 40)
    elif L == "fg":
        for x in (X0 + 300, 2300):
            for k in range(5):
                cv.drawPath(oval(x + k * 40 - 80, H + 60, 70, 110), paint(rgb("3d8a3a")))


def house_interior(L, cv, rng, time):
    wall = rgb("e9c48c")
    if L == "sky":
        grad_rect(cv, X0, -300, X1, H + 300, wall, shade(wall, 0.9))
    elif L == "far":
        pass
    elif L == "mid":
        grad_rect(cv, X0, -300, X1, H + 500, wall, shade(wall, 0.92))
        cv.drawRect(skia.Rect.MakeLTRB(X0, 700, X1, H + 500), paint(rgb("b8572f")))   # red-oxide dado
        cv.drawRect(skia.Rect.MakeLTRB(X0, 692, X1, 704), paint(rgb("f4f1e8")))
        for k in range(-1, 8):   # beams
            cv.drawRect(skia.Rect.MakeLTRB(X0 + k * 520, -300, X0 + k * 520 + 26, 30), paint(rgb("8b5a34")))
        cv.drawRect(skia.Rect.MakeLTRB(X0, 0, X1, 40), paint(rgb("7a4f2e")))
        # window with sky
        sky = SKY[time]
        for wx in (360, 1700):
            grad_rect(cv, wx - 120, 220, wx + 120, 470, sky[0], sky[1])
            cv.drawPath(rrect(wx - 130, 210, wx + 130, 480, 6), stroke(rgb("6b4426"), 18))
            for k in range(1, 4):
                cv.drawPath(poly([(wx - 120 + k * 60, 220), (wx - 120 + k * 60, 470)], close=False), stroke(rgb("4a3020"), 7))
        # door
        fill_ink(cv, rrect(880, 280, 1060, 800, 10), rgb("7a4f2e"))
        for k in range(2):
            cv.drawPath(rrect(900 + k * 82, 310, 960 + k * 82 + 18, 770, 6), stroke(rgb("5a3a24"), 6))
        cv.drawCircle(1040, 560, 9, paint(rgb("e8b923")))
        cv.drawPath(poly([(860, 270), (1080, 270)], close=False), stroke(rgb("3f9e45"), 10))
        for k in range(8):
            cv.drawPath(poly([(870 + k * 28, 270), (876 + k * 28, 300), (882 + k * 28, 270)]), paint(rgb("f5a623")))
        # shelf with pots and a wall clock / calendar
        cv.drawRect(skia.Rect.MakeLTRB(1250, 300, 1560, 318), paint(rgb("6b4426")))
        for k, c in enumerate([rgb("b5562c"), rgb("c9ced6"), rgb("e8b923"), rgb("b5562c")]):
            fill_ink(cv, smooth_closed([(1280 + k * 76, 300), (1270 + k * 76, 260), (1290 + k * 76, 230), (1330 + k * 76, 230),
                                        (1350 + k * 76, 260), (1340 + k * 76, 300)]), c, w=4)
        fill_ink(cv, rrect(150, 520, 300, 690, 6), rgb("f4f1e8"), w=4)
        cv.drawRect(skia.Rect.MakeLTRB(160, 530, 290, 590), paint(rgb("f5a623")))
        cv.drawCircle(-150, 300, 60, paint(rgb("f4f1e8"))); cv.drawCircle(-150, 300, 60, stroke(rgb("6b4426"), 10))
        cv.drawPath(poly([(-150, 300), (-150, 262), (-150, 300), (-122, 316)], close=False), stroke(INK, 6))
    elif L == "stage":
        grad_rect(cv, X0, 790, X1, H + 400, rgb("b98c5c"), rgb("8f6a44"))
        cv.drawRect(skia.Rect.MakeLTRB(X0, 790, X1, 800), paint(rgb("6b4426")))
        for k in range(14):   # cow-dung floor texture rings
            cv.drawPath(oval(rng.uniform(X0, X1), rng.uniform(840, 1060), rng.uniform(60, 140), 10), stroke(rgb("a07a50"), 3))
        # chulha (clay stove) at the left
        fill_ink(cv, rrect(-80, 760, 160, 850, 30), rgb("a0522d"))
        fill_ink(cv, oval(40, 762, 100, 18), rgb("5a2e18"), w=4)
        fill_ink(cv, smooth_closed([(-10, 760), (-30, 700), (10, 670), (90, 670), (110, 700), (90, 760)]), rgb("6b6f78"))
        # mat
        fill_ink(cv, rrect(1250, 900, 1700, 960, 10), rgb("d9b45a"), w=4)
        for k in range(10):
            cv.drawPath(poly([(1270 + k * 44, 902), (1270 + k * 44, 958)], close=False), stroke(rgb("b08a3a"), 4))
    elif L == "fg":
        pass


def village_home(L, cv, rng, time):
    if L in ("sky", "far"):
        return village_street(L, cv, rng, time)
    if L == "mid":
        grad_rect(cv, X0, 640, X1, H + 500, rgb("c8a46a"), rgb("a8834c"))
        _house(cv, 960, 790, 1.35, rgb("f0e2c0"), rgb("2f8f8f"))
        _hut(cv, -100, 780, 1.0, rgb("e9d3a6"))
        _tree(cv, 1950, 780, 1.0, rng=rng)
        _tree(cv, 2400, 780, 0.8, rgb("4a9a48"))
        for k in range(10):   # little fence
            cv.drawPath(poly([(1500 + k * 40, 790), (1500 + k * 40, 700)], close=False), stroke(rgb("8b5a34"), 10))
        cv.drawPath(poly([(1490, 730), (1880, 730)], close=False), stroke(rgb("8b5a34"), 8))
    elif L == "stage":
        _ground(cv, 780, H, rgb("d4b07a"), rng)
        # rangoli at the doorstep
        cx, cy = 960, 860
        for k in range(8):
            a = k * math.pi / 4
            cv.drawPath(oval(cx + math.cos(a) * 40, cy + math.sin(a) * 14, 22, 9), paint([rgb("d9343b"), rgb("f5a623"), rgb("7b4fcf"), rgb("2f9e57")][k % 4]))
        cv.drawPath(oval(cx, cy, 20, 8), paint((255, 255, 255)))
        _stones(cv, rng, 800, 1060, 30)
        # tulsi-free courtyard: a clay pot stand and a broom
        fill_ink(cv, rrect(330, 760, 440, 820, 8), rgb("c97b4a"))
        fill_ink(cv, smooth_closed([(345, 760), (330, 720), (360, 690), (410, 690), (440, 720), (425, 760)]), rgb("b5562c"))
    elif L == "fg":
        village_street(L, cv, rng, time)


def field(L, cv, rng, time):
    if L == "sky":
        _sky(cv, time, rng)
    elif L == "far":
        _hills(cv, 470, rgb("7fa9c4") if time == "day" else rgb("6a6494"), rng, amp=160)
        _hills(cv, 560, rgb("79b37c") if time == "day" else rgb("5d6f84"), rng, amp=90)
    elif L == "mid":
        grad_rect(cv, X0, 610, X1, H + 500, rgb("8cc152"), rgb("5a982a"))
        for k in range(8):
            _tree(cv, X0 + 100 + k * 450 + rng.uniform(-80, 80), 650, rng.uniform(0.35, 0.5), rgb("3f8f3f"))
        _hut(cv, 1700, 690, 0.6, rgb("e9d3a6"))
        # scarecrow
        cv.save(); cv.translate(500, 720); cv.scale(0.8, 0.8)
        cv.drawPath(poly([(0, 0), (0, -260)], close=False), stroke(rgb("6b4426"), 12))
        cv.drawPath(poly([(-110, -190), (110, -190)], close=False), stroke(rgb("6b4426"), 12))
        fill_ink(cv, poly([(-80, -210), (80, -210), (60, -80), (-60, -80)]), rgb("d9343b"))
        fill_ink(cv, oval(0, -270, 42, 44), rgb("e8d8b0"))
        fill_ink(cv, poly([(-60, -295), (60, -295), (0, -350)]), rgb("c58a3e"))
        cv.restore()
    elif L == "stage":
        grad_rect(cv, X0, 740, X1, H + 400, rgb("7cbf4a"), rgb("4f8f2c"))
        for r_ in range(9):   # crop rows converging
            y = 760 + r_ * 38
            for k in range(70):
                x = X0 + k * 48 + (r_ % 2) * 24
                h = 22 + r_ * 6
                cv.drawPath(poly([(x, y), (x - 6, y - h), (x + 2, y - h * 0.6), (x + 8, y - h)], close=False),
                            stroke(shade(rgb("3f8f2c"), 0.9 + 0.03 * r_), 4 + r_ * 0.4))
        p = skia.Path(); p.moveTo(700, 760); p.lineTo(1220, 760); p.lineTo(1500, H + 400); p.lineTo(420, H + 400); p.close()
        cv.drawPath(p, paint(rgb("c9a46a")))
        _stones(cv, rng, 800, 1060, 25)
    elif L == "fg":
        for x in range(X0, X1, 110):
            for k in range(4):
                cv.drawPath(poly([(x + k * 12, H + 40), (x + k * 12 - 20, H - 120 - (k % 2) * 40)], close=False), stroke(rgb("3f7f2c"), 9))


def market(L, cv, rng, time):
    if L == "sky":
        _sky(cv, time, rng)
    elif L == "far":
        for k in range(14):
            x = X0 + k * 250
            h = rng.uniform(220, 420)
            col = [rgb("e7c9a0"), rgb("d8a8a0"), rgb("b8c8d8"), rgb("e0d0a0")][k % 4]
            cv.drawRect(skia.Rect.MakeLTRB(x, 680 - h, x + 230, 700), paint(shade(col, 0.95)))
            for r_ in range(int(h // 80)):
                for c_ in range(3):
                    cv.drawRect(skia.Rect.MakeLTRB(x + 25 + c_ * 70, 700 - h + 30 + r_ * 80, x + 60 + c_ * 70, 700 - h + 70 + r_ * 80),
                                paint(shade(col, 0.7)))
    elif L == "mid":
        grad_rect(cv, X0, 680, X1, H + 500, rgb("c9b08a"), rgb("b49a72"))
        cols = [rgb("d9343b"), rgb("2f6fd6"), rgb("f5a623"), rgb("2f9e57"), rgb("7b4fcf")]
        for k in range(8):
            x = X0 + 150 + k * 430
            c = cols[k % len(cols)]
            fill_ink(cv, rrect(x - 170, 620, x + 170, 790, 6), rgb("8b5a34"))
            for px in (x - 160, x + 160):
                cv.drawPath(poly([(px, 620), (px, 470)], close=False), stroke(rgb("6b4426"), 10))
            aw = poly([(x - 200, 470), (x + 200, 470), (x + 175, 420), (x - 175, 420)])
            fill_ink(cv, aw, rgb("f4f1e8"))
            cv.save(); cv.clipPath(aw, doAntiAlias=True)
            for j in range(-5, 6, 2):
                cv.drawRect(skia.Rect.MakeLTRB(x + j * 40, 410, x + j * 40 + 40, 480), paint(c))
            cv.restore()
            goods = [rgb("d9343b"), rgb("f5b324"), rgb("7cc242"), rgb("f08a24"), rgb("7b4fcf")]
            for j in range(9):
                fill_ink(cv, oval(x - 140 + j * 35, 600 - (j % 2) * 18, 20, 18), goods[(j + k) % 5], w=3)
            # hanging lanterns / marigold strings
            for j in range(5):
                cv.drawCircle(x - 150 + j * 75, 490 + (j % 2) * 10, 10, paint(rgb("f5a623")))
    elif L == "stage":
        _ground(cv, 790, H, rgb("cdb894"), rng)
        for k in range(40):   # paving stones
            x, y = rng.uniform(X0, X1), rng.uniform(820, 1060)
            cv.drawPath(rrect(x, y, x + 90, y + 30, 8), stroke(rgb("b09a74"), 3))
        for x in (40, 1850):
            for k in range(2):
                fill_ink(cv, rrect(x + k * 70, 830 - k * 20, x + k * 70 + 90, 900 - k * 20, 4), rgb("c58a3e"), w=4)
    elif L == "fg":
        pass


def forest(L, cv, rng, time):
    if L == "sky":
        _sky(cv, time, rng)
        grad_rect(cv, X0, 300, X1, FLOOR, rgb("9ccf9a") if time == "day" else rgb("3a4a5a"), rgb("6aa070") if time == "day" else rgb("2a3a4a"))
    elif L == "far":
        for k in range(22):
            x = X0 + k * 160 + rng.uniform(-40, 40)
            h = rng.uniform(300, 520)
            cv.drawPath(poly([(x - 90, 700), (x, 700 - h), (x + 90, 700)]), paint(rgb("4f8f6a")))
        cv.drawRect(skia.Rect.MakeLTRB(X0, 690, X1, H + 500), paint(rgb("4f8f6a")))
    elif L == "mid":
        for k in range(10):
            x = X0 + 100 + k * 350 + rng.uniform(-60, 60)
            cv.drawRect(skia.Rect.MakeLTRB(x - 40, -300, x + 40, 800), paint(rgb("6e4a2c")))
            cv.drawRect(skia.Rect.MakeLTRB(x - 40, -300, x - 20, 800), paint(rgb("5a3a24")))
            for dx, dy, r in [(-120, 80, 160), (100, 40, 170), (0, -60, 200)]:
                cv.drawPath(oval(x + dx, dy, r, r * 0.8), paint(rgb("2f6f3a")))
        for k in range(30):
            cv.drawPath(oval(rng.uniform(X0, X1), rng.uniform(720, 800), rng.uniform(60, 120), rng.uniform(40, 70)), paint(rgb("3f8f45")))
    elif L == "stage":
        _ground(cv, 790, H, rgb("7a9a4a"), rng)
        for k in range(18):   # mushrooms + ferns
            x, y = rng.uniform(X0, X1), rng.uniform(800, 1050)
            if k % 3 == 0:
                fill_ink(cv, rrect(x - 6, y - 26, x + 6, y, 4), rgb("f4f1e8"), w=3)
                fill_ink(cv, smooth_closed([(x - 22, y - 22), (x, y - 44), (x + 22, y - 22)]), rgb("d9343b"), w=3)
            else:
                for j in range(5):
                    a = -math.pi * (0.15 + 0.7 * j / 4)
                    cv.drawPath(poly([(x, y), (x + math.cos(a) * 50, y + math.sin(a) * 50)], close=False), stroke(rgb("4f9a3a"), 6))
        _stones(cv, rng, 820, 1060, 30, rgb("9a9a8a"))
    elif L == "fg":
        for x in (X0 + 250, 2250):
            for k in range(6):
                a = -math.pi * (0.1 + 0.8 * k / 5)
                lf = skia.Path(); lf.moveTo(x, H + 80)
                lf.quadTo(x + math.cos(a) * 160, H + 80 + math.sin(a) * 260, x + math.cos(a) * 260, H + 80 + math.sin(a) * 320)
                cv.drawPath(lf, stroke(rgb("2f6f2a"), 34))


def river(L, cv, rng, time):
    if L == "sky":
        _sky(cv, time, rng)
    elif L == "far":
        _hills(cv, 500, rgb("86b0c0") if time == "day" else rgb("6a6494"), rng, amp=150)
        for k in range(12):
            _palm(cv, X0 + 100 + k * 300 + rng.uniform(-50, 50), 620, rng.uniform(0.45, 0.6), rgb("3d7a50"))
        grad_rect(cv, X0, 610, X1, 640, rgb("7aa060"), rgb("6a9050"))
    elif L == "mid":
        wc = {"day": (rgb("4fa8d8"), rgb("2f7fb8")), "evening": (rgb("e8a070"), rgb("7a5aa0")), "night": (rgb("1f3a6a"), rgb("12244a"))}[time]
        grad_rect(cv, X0, 635, X1, H + 500, wc[0], wc[1])
        # a little boat
        cv.save(); cv.translate(1500, 690)
        b = skia.Path(); b.moveTo(-160, -20); b.quadTo(0, 40, 160, -20); b.lineTo(130, 10); b.quadTo(0, 50, -130, 10); b.close()
        fill_ink(cv, b, rgb("8b5a34"), w=4)
        fill_ink(cv, poly([(-60, -20), (0, -60), (60, -20)]), rgb("f4f1e8"), w=4)
        cv.restore()
    elif L == "stage":
        grad_rect(cv, X0, 780, X1, H + 400, rgb("c9b07a"), rgb("a88f5a"))
        p = skia.Path(); p.moveTo(X0, 790); p.quadTo(960, 770, X1, 795); p.lineTo(X1, 830); p.quadTo(960, 810, X0, 830); p.close()
        cv.drawPath(p, paint(rgb("8fbf5a")))
        for k in range(4):   # ghat steps on the right
            cv.drawRect(skia.Rect.MakeLTRB(1700 - k * 30, 780 + k * 26, X1, 806 + k * 26), paint(shade(rgb("cfc4b0"), 1 - k * 0.05)))
            cv.drawPath(poly([(1700 - k * 30, 806 + k * 26), (X1, 806 + k * 26)], close=False), stroke(rgb("9a8f7a"), 3))
        _stones(cv, rng, 830, 1060, 40, rgb("a09070"))
    elif L == "fg":
        for x in range(X0, X1, 260):
            for k in range(5):
                cv.drawPath(poly([(x + k * 14, H + 60), (x + k * 16 - 20, H - 160 - (k % 2) * 30)], close=False), stroke(rgb("5a8a3a"), 7))
                cv.drawPath(oval(x + k * 16 - 20, H - 170 - (k % 2) * 30, 7, 20), paint(rgb("8a5a2e")))


def palace(L, cv, rng, time):
    if L == "sky":
        grad_rect(cv, X0, -300, X1, H + 300, rgb("f3d9a8"), rgb("e8c88a"))
    elif L == "far":
        pass
    elif L == "mid":
        grad_rect(cv, X0, -300, X1, H + 500, rgb("f6e4c0"), rgb("ead2a0"))
        for k in range(9):   # arches
            x = X0 + 160 + k * 400
            a = skia.Path(); a.moveTo(x - 140, 760); a.lineTo(x - 140, 300); a.quadTo(x, 120, x + 140, 300); a.lineTo(x + 140, 760); a.close()
            cv.drawPath(a, paint(rgb("c9a46a")))
            sky = SKY[time]
            a2 = skia.Path(); a2.moveTo(x - 110, 760); a2.lineTo(x - 110, 310); a2.quadTo(x, 160, x + 110, 310); a2.lineTo(x + 110, 760); a2.close()
            cv.save(); cv.clipPath(a2, doAntiAlias=True); grad_rect(cv, x - 120, 150, x + 120, 760, sky[0], sky[1]); cv.restore()
            cv.drawPath(a2, stroke(rgb("8b5a34"), 6))
            fill_ink(cv, rrect(x + 160, 120, x + 240, 800, 8), rgb("f4f1e8"), w=4)   # pillar
            cv.drawRect(skia.Rect.MakeLTRB(x + 150, 110, x + 250, 140), paint(rgb("e8b923")))
            cv.drawRect(skia.Rect.MakeLTRB(x + 150, 770, x + 250, 800), paint(rgb("e8b923")))
        for k in range(10):   # curtains
            x = X0 + k * 400 - 40
            cv.drawPath(poly([(x, -300), (x + 140, -300), (x + 40, 260)]), paint(rgb("a8233a")))
        cv.drawRect(skia.Rect.MakeLTRB(X0, -300, X1, 40), paint(rgb("8e1f3a")))
        for k in range(60):
            cv.drawCircle(X0 + k * 60, 40, 14, paint(rgb("e8b923")))
        # throne on a dais at the centre-right
        fill_ink(cv, rrect(1300, 700, 1800, 800, 8), rgb("e8b923"))
        fill_ink(cv, rrect(1440, 380, 1660, 720, 30), rgb("d9343b"))
        fill_ink(cv, smooth_closed([(1430, 420), (1550, 300), (1670, 420), (1550, 380)]), rgb("e8b923"))
    elif L == "stage":
        grad_rect(cv, X0, 790, X1, H + 400, rgb("c98a5a"), rgb("a86a3a"))
        p = skia.Path(); p.moveTo(400, 800); p.lineTo(1520, 800); p.lineTo(1800, H + 400); p.lineTo(120, H + 400); p.close()
        cv.drawPath(p, paint(rgb("a8233a")))
        cv.drawPath(p, stroke(rgb("e8b923"), 10))
    elif L == "fg":
        pass


def school(L, cv, rng, time):
    if L in ("sky", "far"):
        return village_street(L, cv, rng, time)
    if L == "mid":
        grad_rect(cv, X0, 640, X1, H + 500, rgb("c8a46a"), rgb("a8834c"))
        _house(cv, 960, 790, 1.6, rgb("f2e6c8"), rgb("d9343b"))
        _tree(cv, 200, 780, 1.1, rng=rng)
        _tree(cv, 1800, 780, 1.0, rgb("4a9a48"))
        fill_ink(cv, rrect(1300, 520, 1500, 660, 6), rgb("2f4f3a"))   # blackboard outside
    elif L == "stage":
        _ground(cv, 780, H, rgb("d4b07a"), rng)
        _stones(cv, rng, 800, 1060, 30)
    elif L == "fg":
        pass


def shop(L, cv, rng, time):
    if L in ("sky", "far", "fg"):
        return market(L, cv, rng, time)
    if L == "mid":
        grad_rect(cv, X0, 640, X1, H + 500, rgb("c9b08a"), rgb("b49a72"))
        fill_ink(cv, rrect(300, 220, 1620, 790, 8), rgb("f0d8a8"))
        fill_ink(cv, rrect(270, 160, 1650, 240, 8), rgb("2f8f8f"))
        for r_ in range(3):   # shelves of jars and sacks
            y = 330 + r_ * 130
            cv.drawRect(skia.Rect.MakeLTRB(360, y, 1560, y + 14), paint(rgb("8b5a34")))
            for k in range(14):
                c = [rgb("d9343b"), rgb("f5b324"), rgb("7cc242"), rgb("e8e0d0")][(k + r_) % 4]
                fill_ink(cv, rrect(380 + k * 84, y - 70, 430 + k * 84, y, 8), c, w=3)
        fill_ink(cv, rrect(250, 640, 1670, 800, 6), rgb("8b5a34"))
    elif L == "stage":
        _ground(cv, 790, H, rgb("cdb894"), rng)


PAINT = {"village_street": village_street, "house_interior": house_interior, "field": field, "market": market,
         "forest": forest, "river": river, "palace": palace, "village_home": village_home, "school": school, "shop": shop}
INDOOR = {"house_interior", "palace", "shop"}


# ------------------------------------------------------------------------------------------------ build + animate
class Set:
    def __init__(self, name, time="day", weather="clear", seed=0):
        self.name = set_name(name)
        self.time = time if time in SKY else "day"
        self.weather = weather if weather in ("clear", "rain") else "clear"
        self.indoor = self.name in INDOOR
        if self.indoor and self.weather == "rain":
            self.weather = "rain_in"   # rain only through the window + sound
        self.seed = seed
        self.layers = {}
        for L in ("sky", "far", "mid", "stage", "fg"):
            rec = skia.PictureRecorder()
            cv = rec.beginRecording(skia.Rect.MakeLTRB(X0 - 100, -500, X1 + 100, H + 500))
            PAINT[self.name](L, cv, random.Random(hash((self.name, L, seed)) & 0xffffff), self.time)
            self.layers[L] = rec.finishRecordingAsPicture()
        rng = random.Random(seed + 11)
        self.clouds = [(rng.uniform(X0, X1), rng.uniform(40, 300), rng.uniform(0.6, 1.3), rng.uniform(6, 16)) for _ in range(7)]
        self.birds = [(rng.uniform(0, 1), rng.uniform(80, 330), rng.uniform(40, 90), rng.uniform(0, 6)) for _ in range(5)]
        self.leaves = [(rng.uniform(X0, X1), rng.uniform(0, 1), rng.uniform(0.6, 1.4)) for _ in range(14)]
        self.rain = [(rng.uniform(-200, W + 200), rng.uniform(0, H), rng.uniform(0.7, 1.3)) for _ in range(260)]
        self.flies = [(rng.uniform(0, W), rng.uniform(300, 900), rng.uniform(0, 6)) for _ in range(26)]
        self.smoke = {"village_street": [(X0 + 200 + 520 * 1 + 60, 470), (X0 + 200 + 520 * 4 + 60, 470)],
                      "house_interior": [(40, 740)], "village_home": [(960, 330)], "field": [(1700, 470)]}.get(self.name, [])
        self.fire = [(40, 760)] if self.name == "house_interior" else []

    def layer_xform(self, cv, cam, d):
        cx, cy, z = cam
        zd = 1 + (z - 1) * d
        cv.translate(W / 2, H / 2)
        cv.scale(zd, zd)
        cv.translate(-(W / 2 + (cx - W / 2) * d), -(H / 2 + (cy - H / 2) * d))

    def draw_back(self, cv, cam, t):
        for L in ("sky", "far", "mid"):
            cv.save(); self.layer_xform(cv, cam, DEPTH[L]); cv.drawPicture(self.layers[L])
            if L == "sky" and not self.indoor:
                self._clouds(cv, t)
                self._birds(cv, t)
            if L == "mid":
                self._mid_anim(cv, t)
            cv.restore()
        cv.save(); self.layer_xform(cv, cam, 1.0); cv.drawPicture(self.layers["stage"]); self._stage_anim(cv, t); cv.restore()

    def draw_front(self, cv, cam, t):
        cv.save(); self.layer_xform(cv, cam, DEPTH["fg"]); cv.drawPicture(self.layers["fg"])
        cv.restore()
        if not self.indoor and self.name in ("forest", "village_street", "village_home", "field"):
            cv.save(); self.layer_xform(cv, cam, 1.1); self._leaves(cv, t); cv.restore()

    def grade(self, cv, t):
        """Time-of-day / weather colour grade over the whole frame (characters included), then glows."""
        if self.time == "night":
            cv.drawRect(skia.Rect.MakeWH(W, H), skia.Paint(Color=C((150, 140, 185) if self.indoor else (115, 128, 190)),
                                                         BlendMode=skia.BlendMode.kMultiply))
            for x, y, ph in self.flies:
                if not self.indoor:
                    a = int(120 + 120 * math.sin(t * 2 + ph))
                    cv.drawCircle(x + 30 * math.sin(t * 0.5 + ph), y + 20 * math.cos(t * 0.7 + ph), 3.5, paint(rgb("fff59a"), max(0, a)))
            if self.indoor:   # warm lamp pool
                g = skia.Paint(AntiAlias=True, BlendMode=skia.BlendMode.kScreen)
                g.setShader(skia.GradientShader.MakeRadial(skia.Point(W * 0.5, H * 0.45), 900,
                                                            [C((150, 100, 30)), C((0, 0, 0))]))
                cv.drawRect(skia.Rect.MakeWH(W, H), g)
        elif self.time == "evening":
            cv.drawRect(skia.Rect.MakeWH(W, H), skia.Paint(Color=C((255, 214, 178)), BlendMode=skia.BlendMode.kMultiply))
        if self.weather in ("rain", "rain_in"):
            if self.weather == "rain":
                cv.drawRect(skia.Rect.MakeWH(W, H), skia.Paint(Color=C((175, 185, 205) if self.time != "night" else (225, 230, 240)),
                                                             BlendMode=skia.BlendMode.kMultiply))
                for x, y, s in self.rain:
                    yy = (y + t * 1500 * s) % (H + 100) - 50
                    xx = x - (t * 300 * s) % 400 + 200 - 0.25 * (yy)
                    cv.drawLine(xx, yy, xx - 10 * s, yy + 44 * s, stroke((220, 230, 250), 2.4, a=150))
                for k in range(16):
                    ph = (t * 1.7 + k * 0.37) % 1.0
                    x = (k * 263 + 90) % W
                    y = 930 + (k * 37) % 140
                    cv.drawPath(oval(x, y, 12 + 30 * ph, 3 + 6 * ph), stroke((230, 240, 255), 2.5, a=int(200 * (1 - ph))))
            else:
                cv.drawRect(skia.Rect.MakeWH(W, H), skia.Paint(Color=C((200, 205, 220)), BlendMode=skia.BlendMode.kMultiply))
            # lightning flash every ~9 s
            ph = t % 9.0
            if 0 < ph < 0.12 or 0.2 < ph < 0.26:
                cv.drawRect(skia.Rect.MakeWH(W, H), paint((255, 255, 255), 70))

    # ---- animated bits
    def _clouds(self, cv, t):
        if self.weather == "rain":
            for x, y, s, sp in self.clouds:
                xx = (x + t * sp * 0.6 - X0) % (X1 - X0) + X0
                for dx, dy, r in [(0, 0, 70), (60, -20, 60), (120, 0, 66), (60, 20, 60)]:
                    cv.drawCircle(xx + dx * s, y + dy * s, r * s * 1.2, paint((120, 125, 140), 230))
            return
        a = 235 if self.time == "day" else 150
        col = (255, 255, 255) if self.time == "day" else (255, 220, 200) if self.time == "evening" else (90, 100, 140)
        for x, y, s, sp in self.clouds:
            xx = (x + t * sp - X0) % (X1 - X0) + X0
            for dx, dy, r in [(0, 0, 60), (55, -25, 55), (110, 0, 58), (55, 15, 55)]:
                cv.drawCircle(xx + dx * s, y + dy * s, r * s, paint(col, a))

    def _birds(self, cv, t):
        if self.time == "night" or self.weather == "rain":
            return
        for u, y, sp, ph in self.birds:
            x = X0 + ((u * (X1 - X0)) + t * sp) % (X1 - X0)
            f = math.sin(t * 9 + ph)
            p = skia.Path(); p.moveTo(x - 16, y - 6 * f); p.quadTo(x - 6, y - 8 * f - 4, x, y); p.quadTo(x + 6, y - 8 * f - 4, x + 16, y - 6 * f)
            cv.drawPath(p, stroke((50, 45, 55), 3.5))

    def _mid_anim(self, cv, t):
        for sx, sy in self.smoke:
            for k in range(6):
                ph = (t * 0.35 + k / 6) % 1.0
                cv.drawCircle(sx + 30 * math.sin(ph * 6 + k) + ph * 60, sy - ph * 260, 14 + ph * 40, paint((235, 235, 240), int(120 * (1 - ph))))
        if self.name == "river":
            for k in range(40):
                x = X0 + (k * 97 + t * 30 * (1 + k % 3)) % (X1 - X0)
                y = 650 + (k * 53) % 130
                w = 30 + (k % 4) * 12
                a = int(120 + 100 * math.sin(t * 2 + k))
                cv.drawLine(x, y, x + w, y, stroke((255, 255, 255), 3, a=max(0, a)))

    def _stage_anim(self, cv, t):
        for fx, fy in self.fire:
            for k in range(3):
                fl = 1 + 0.25 * math.sin(t * 13 + k * 2)
                c = [rgb("ff6a1a"), rgb("ffa52a"), rgb("ffe066")][k]
                cv.drawPath(smooth_closed([(fx - 50 + k * 15, fy), (fx - 10 + k * 10, fy - (90 - k * 20) * fl), (fx + 30 - k * 5, fy - (60 - k * 10) * fl),
                                           (fx + 50 - k * 15, fy)]), paint(c, 230))
            g = skia.Paint(AntiAlias=True)
            g.setShader(skia.GradientShader.MakeRadial(skia.Point(fx, fy - 40), 260, [C(rgb("ffb040"), 90), C(rgb("ffb040"), 0)]))
            cv.drawCircle(fx, fy - 40, 260, g)

    def _leaves(self, cv, t):
        for x, ph, s in self.leaves:
            u = (t * 0.08 * s + ph) % 1.0
            y = -100 + u * 1200
            xx = x + 80 * math.sin(u * 9 + ph * 6)
            cv.save(); cv.translate(xx, y); cv.rotate(math.degrees(math.sin(u * 12 + ph)) * 0.8)
            cv.drawPath(oval(0, 0, 12 * s, 6 * s), paint(rgb("8fbf3a") if self.name != "forest" else rgb("d8a03a"), 220))
            cv.restore()
