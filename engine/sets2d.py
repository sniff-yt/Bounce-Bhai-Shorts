#!/usr/bin/env python3
"""Backgrounds for the 2D engine: one painter per setting, drawn once per shot into a cached image
(wider than the frame so the camera can pan). All vector, outlined in the same ink as the characters."""
import math
import random

import skia

from toon2d import C, INK, fill_ink, oval, paint, poly, rgb, rrect, shade, smooth_closed, stroke

BW, BH = 1600, 1920   # background canvas: wider than 1080 for camera pans
FLOOR_Y = 1560        # where feet stand


def grad(cv, l, t, r, b, c1, c2):
    p = skia.Paint(Shader=skia.GradientShader.MakeLinear([skia.Point(0, t), skia.Point(0, b)], [C(c1), C(c2)]))
    cv.drawRect(skia.Rect.MakeLTRB(l, t, r, b), p)


def cloud(cv, x, y, s, a=235):
    p = paint((255, 255, 255), a)
    for dx, dy, r in ((0, 0, 60), (60, -25, 70), (125, 0, 58), (60, 18, 62)):
        cv.drawCircle(x + dx * s, y + dy * s, r * s, p)


def tree(cv, x, y, s, rng):
    trunk = rgb("8a5a3b")
    fill_ink(cv, poly([(x - 18 * s, y), (x - 12 * s, y - 210 * s), (x + 12 * s, y - 210 * s), (x + 18 * s, y)]), trunk, w=5)
    g = rng.choice([rgb("4caf50"), rgb("43a047"), rgb("5cbf5a")])
    blobs = [(0, -300, 120), (-90, -240, 90), (90, -240, 95), (-40, -380, 95), (55, -370, 90)]
    for dx, dy, r in blobs:
        fill_ink(cv, oval(x + dx * s, y + dy * s, r * s, r * s * 0.92), g, w=5)
    for dx, dy, r in blobs:
        cv.drawCircle(x + dx * s - r * s * 0.25, y + dy * s - r * s * 0.3, r * s * 0.35, paint(shade(g, 1.25), 120))


def bush(cv, x, y, s, col=rgb("49a84a")):
    for dx, r in ((-50, 50), (0, 66), (52, 48)):
        fill_ink(cv, oval(x + dx * s, y - r * s * 0.6, r * s, r * s * 0.8), col, w=5)
    for k in range(5):
        cv.drawCircle(x + (-60 + k * 30) * s, y - 70 * s + (k % 2) * 20 * s, 7 * s,
                      paint([rgb("ff6f91"), rgb("ffd166"), rgb("ffffff")][k % 3]))


def window(cv, l, t, w, h, glass=rgb("bfe6ff"), frame=rgb("ffffff")):
    fill_ink(cv, rrect(l - 10, t - 10, l + w + 10, t + h + 10, 8), frame, w=5)
    grad(cv, l, t, l + w, t + h, glass, shade(glass, 1.3))
    cv.drawPath(rrect(l, t, l + w, t + h, 4), stroke(INK, 4))
    cv.drawPath(poly([(l + w / 2, t), (l + w / 2, t + h)], close=False), stroke(frame, 8))
    cv.drawPath(poly([(l, t + h / 2), (l + w, t + h / 2)], close=False), stroke(frame, 8))
    cv.drawPath(poly([(l + 16, t + h * 0.4), (l + w * 0.3, t + 16)], close=False), stroke((255, 255, 255), 6, a=150))


def room(cv, wall, floor, rng, wall2=None):
    grad(cv, 0, 0, BW, FLOOR_Y - 120, shade(wall, 1.08), wall)
    cv.drawRect(skia.Rect.MakeLTRB(0, FLOOR_Y - 140, BW, FLOOR_Y - 120), paint(shade(wall, 0.85)))
    grad(cv, 0, FLOOR_Y - 120, BW, BH, floor, shade(floor, 0.8))
    for k in range(9):   # floor boards perspective lines
        x = k * 200
        cv.drawPath(poly([(x, FLOOR_Y - 120), (x - 260 + k * 30, BH)], close=False), stroke(shade(floor, 0.82), 3))


# --------------------------------------------------------------------------- settings
def park(cv, rng):
    grad(cv, 0, 0, BW, 1250, rgb("7cc8ff"), rgb("dff3ff"))
    cv.drawCircle(1320, 260, 90, paint(rgb("fff3b0"))); cv.drawCircle(1320, 260, 130, paint(rgb("fff3b0"), 70))
    for x, y, s in ((180, 260, 1.1), (700, 170, 0.8), (1150, 420, 0.9)):
        cloud(cv, x, y, s)
    hill = smooth_closed([(-100, 1300), (300, 1000), (700, 1120), (1100, 960), (1700, 1150), (1700, 1400), (-100, 1400)])
    cv.drawPath(hill, paint(rgb("9bd88a")))
    cv.drawRect(skia.Rect.MakeLTRB(0, 1240, BW, BH), paint(rgb("7cc96a")))
    path = poly([(560, 1240), (1040, 1240), (1500, BH), (100, BH)])
    cv.drawPath(path, paint(rgb("f0d9a8")))
    cv.drawPath(path, stroke(shade(rgb("f0d9a8"), 0.85), 5))
    for x, s in ((130, 1.1), (1450, 1.15), (420, 0.7), (1180, 0.75)):
        tree(cv, x, 1250 + (40 if s > 1 else 0), s, rng)
    bush(cv, 300, 1330, 1.0); bush(cv, 1290, 1335, 0.9)
    # bench
    wood = rgb("c17f4a")
    for k in range(3):
        fill_ink(cv, rrect(1060, 1190 + k * 34, 1340, 1214 + k * 34, 8), wood, w=4)
    for x in (1080, 1310):
        fill_ink(cv, rrect(x - 8, 1260, x + 8, 1330, 4), rgb("4a4a52"), w=3)
    for k in range(30):
        x, y = rng.uniform(0, BW), rng.uniform(1300, BH)
        cv.drawPath(poly([(x, y), (x - 6, y - 18)], close=False), stroke(rgb("5fb456"), 4))
        cv.drawPath(poly([(x, y), (x + 6, y - 16)], close=False), stroke(rgb("5fb456"), 4))


def street(cv, rng):
    grad(cv, 0, 0, BW, 1150, rgb("8fd0ff"), rgb("fde9cf"))
    for x, y, s in ((250, 200, 1.0), (1100, 300, 0.8)):
        cloud(cv, x, y, s)
    cols = [rgb("f6b26b"), rgb("e98a8a"), rgb("8ecae6"), rgb("ffd166"), rgb("b5a3e0"), rgb("9fd89a")]
    x = -40
    while x < BW:
        w = rng.randint(230, 330); h = rng.randint(520, 820); c = rng.choice(cols)
        fill_ink(cv, rrect(x, 1240 - h, x + w, 1250, 6), c, w=5)
        fill_ink(cv, poly([(x - 14, 1240 - h), (x + w + 14, 1240 - h), (x + w, 1240 - h - 40), (x, 1240 - h - 40)]),
                 shade(c, 0.75), w=5)
        for ry in range(1240 - h + 60, 1080, 150):
            for rx in range(x + 30, x + w - 70, 100):
                window(cv, rx, ry, 56, 80)
        fill_ink(cv, rrect(x + w / 2 - 40, 1100, x + w / 2 + 40, 1250, 6), shade(c, 0.6), w=4)
        x += w + rng.randint(6, 26)
    cv.drawRect(skia.Rect.MakeLTRB(0, 1250, BW, 1330), paint(rgb("d9d4cc")))
    cv.drawPath(poly([(0, 1250), (BW, 1250)], close=False), stroke(INK, 5))
    grad(cv, 0, 1330, BW, BH, rgb("6f737b"), rgb("54575e"))
    for k in range(8):
        cv.drawRect(skia.Rect.MakeLTRB(k * 230 + 40, 1700, k * 230 + 170, 1716), paint(rgb("f2f2f2")))
    for x0 in (200, 1000):   # lamp posts
        fill_ink(cv, rrect(x0 - 9, 760, x0 + 9, 1290, 4), rgb("3d4450"), w=4)
        fill_ink(cv, oval(x0, 750, 34, 26), rgb("fff2a8"), w=4)


def home(cv, rng):
    room(cv, rgb("f7e3c6"), rgb("c9925e"), rng)
    window(cv, 120, 420, 300, 360)
    # curtains
    for sd, x in ((-1, 100), (1, 440)):
        fill_ink(cv, poly([(x - 40 * sd, 380), (x + 40 * sd, 380), (x + 30 * sd, 840), (x - 50 * sd, 840)]), rgb("e05d5d"), w=4)
    # sofa
    so = rgb("4f7fd1")
    fill_ink(cv, rrect(700, 1050, 1300, 1250, 40), so, w=5)
    fill_ink(cv, rrect(680, 1150, 1320, 1320, 36), shade(so, 1.1), w=5)
    for x in (660, 1300):
        fill_ink(cv, rrect(x, 1100, x + 60, 1320, 28), shade(so, 0.85), w=5)
    for x in (820, 1040):
        fill_ink(cv, rrect(x, 1080, x + 150, 1180, 30), rgb("ffd166"), w=4)
    # frame + plant + lamp
    fill_ink(cv, rrect(820, 600, 1100, 820, 6), rgb("7b4f2c"), w=5)
    grad(cv, 845, 625, 1075, 795, rgb("9ad1ff"), rgb("bfe6a8"))
    cv.drawPath(poly([(845, 795), (930, 690), (990, 760), (1030, 720), (1075, 795)]), paint(rgb("5aa469")))
    fill_ink(cv, poly([(1400, 1250), (1520, 1250), (1500, 1380), (1420, 1380)]), rgb("c76b3c"), w=4)
    for a in range(-60, 61, 30):
        cv.save(); cv.translate(1460, 1250); cv.rotate(a)
        fill_ink(cv, oval(0, -90, 26, 90), rgb("4caf50"), w=4); cv.restore()
    fill_ink(cv, rrect(450, 1150, 520, 1340, 8), rgb("8a5a3b"), w=4)
    fill_ink(cv, poly([(400, 1150), (570, 1150), (530, 1040), (440, 1040)]), rgb("fff2c4"), w=4)


def school(cv, rng):
    room(cv, rgb("e6f0d8"), rgb("d6b58a"), rng)
    fill_ink(cv, rrect(250, 380, 1350, 900, 10), rgb("7a5232"), w=5)
    grad(cv, 275, 405, 1325, 875, rgb("2f5d46"), rgb("264c39"))
    chalk = stroke((240, 240, 230), 6, a=220)
    cv.drawPath(poly([(330, 520), (520, 520)], close=False), chalk)
    cv.drawPath(poly([(330, 600), (650, 600)], close=False), chalk)
    p = skia.Path(); p.moveTo(800, 700); p.quadTo(950, 470, 1100, 700); cv.drawPath(p, chalk)
    cv.drawPath(poly([(1150, 520), (1250, 520), (1200, 600)]), chalk)
    fill_ink(cv, rrect(250, 900, 1350, 925, 4), rgb("9b7653"), w=4)
    for x in (140, 1460):
        cv.drawCircle(x, 300, 70, paint((255, 255, 255))); cv.drawCircle(x, 300, 70, stroke(INK, 5))
        cv.drawPath(poly([(x, 300), (x, 250)], close=False), stroke(INK, 5))
        cv.drawPath(poly([(x, 300), (x + 35, 315)], close=False), stroke(INK, 5))
    for x in (120, 1280):
        fill_ink(cv, rrect(x, 1200, x + 280, 1240, 6), rgb("c98b4e"), w=4)
        fill_ink(cv, rrect(x + 20, 1240, x + 40, 1360, 4), rgb("8a5a3b"), w=3)
        fill_ink(cv, rrect(x + 240, 1240, x + 260, 1360, 4), rgb("8a5a3b"), w=3)


def shop(cv, rng):
    room(cv, rgb("fff1d6"), rgb("e0c39a"), rng)
    cols = [rgb("e8463d"), rgb("3b7de0"), rgb("3fb36b"), rgb("f4c22b"), rgb("ef6fa8"), rgb("f28a2e")]
    for row in range(4):
        y = 380 + row * 200
        fill_ink(cv, rrect(80, y + 150, 1520, y + 172, 4), rgb("b07a48"), w=4)
        x = 100
        while x < 1480:
            w = rng.randint(50, 90); h = rng.randint(80, 140)
            fill_ink(cv, rrect(x, y + 150 - h, x + w, y + 150, 8), rng.choice(cols), w=4)
            cv.drawRect(skia.Rect.MakeLTRB(x + 8, y + 150 - h * 0.6, x + w - 8, y + 150 - h * 0.35), paint((255, 255, 255), 200))
            x += w + rng.randint(6, 18)
    fill_ink(cv, rrect(-20, 60, BW + 20, 200, 0), rgb("e8463d"), w=5)
    for k in range(0, BW, 160):
        cv.drawRect(skia.Rect.MakeLTRB(k, 60, k + 80, 200), paint((255, 255, 255)))
    cv.drawPath(poly([(0, 200), (BW, 200)], close=False), stroke(INK, 5))
    fill_ink(cv, rrect(900, 1150, 1500, 1360, 14), rgb("a8683e"), w=5)
    fill_ink(cv, rrect(880, 1130, 1520, 1170, 10), rgb("c98b4e"), w=5)


def office(cv, rng):
    room(cv, rgb("e9eef5"), rgb("9aa5b5"), rng)
    window(cv, 80, 300, 620, 560, glass=rgb("a9d8ff"))
    for k in range(5):   # skyline in the window
        h = rng.randint(120, 360); x = 100 + k * 120
        cv.drawRect(skia.Rect.MakeLTRB(x, 860 - h, x + 90, 860), paint(rgb("7f9fc4"), 200))
    fill_ink(cv, rrect(820, 1120, 1480, 1160, 8), rgb("c7ccd4"), w=5)
    fill_ink(cv, rrect(860, 1160, 880, 1340, 4), rgb("6b7280"), w=3)
    fill_ink(cv, rrect(1420, 1160, 1440, 1340, 4), rgb("6b7280"), w=3)
    fill_ink(cv, rrect(980, 900, 1300, 1100, 12), rgb("2c3440"), w=5)
    grad(cv, 1000, 920, 1280, 1080, rgb("4fa3ff"), rgb("8ad1ff"))
    fill_ink(cv, rrect(1120, 1100, 1160, 1124, 4), rgb("2c3440"), w=3)
    fill_ink(cv, rrect(1000, 260, 1400, 330, 10), rgb("3b7de0"), w=4)
    fill_ink(cv, poly([(1460, 1120), (1520, 1120), (1500, 1040), (1470, 1040)]), rgb("f2f2f2"), w=3)


def night_sky(cv, rng):
    grad(cv, 0, 0, BW, 1300, rgb("0d1b3d"), rgb("33427a"))
    for k in range(120):
        x, y, r = rng.uniform(0, BW), rng.uniform(0, 1150), rng.uniform(1.5, 4.5)
        cv.drawCircle(x, y, r, paint((255, 255, 240), rng.randint(140, 255)))
    cv.drawCircle(1200, 300, 110, paint(rgb("fff6d1")))
    cv.drawCircle(1250, 270, 100, paint(rgb("1b2a55")))
    cv.drawCircle(1200, 300, 170, paint(rgb("fff6d1"), 30))
    hill = smooth_closed([(-100, 1300), (400, 1080), (900, 1200), (1300, 1050), (1700, 1220), (1700, 1400), (-100, 1400)])
    cv.drawPath(hill, paint(rgb("1f3b2f")))
    grad(cv, 0, 1240, BW, BH, rgb("2a4d3b"), rgb("1d3529"))
    for x, s in ((150, 1.0), (1450, 1.05)):
        cv.saveLayer(None, paint((0, 0, 0), 255)); tree(cv, x, 1290, s, rng); cv.restore()
    for k in range(14):
        x, y = rng.uniform(0, BW), rng.uniform(1300, 1800)
        cv.drawCircle(x, y, 5, paint(rgb("f9ff8a"))); cv.drawCircle(x, y, 16, paint(rgb("f9ff8a"), 50))


def lab(cv, rng):
    room(cv, rgb("dff3f1"), rgb("b9c6cc"), rng)
    for k in range(3):
        fill_ink(cv, rrect(100 + k * 480, 300, 460 + k * 480, 360, 6), rgb("c7ccd4"), w=4)
    fill_ink(cv, rrect(60, 1100, 1540, 1150, 8), rgb("f2f4f7"), w=5)
    fill_ink(cv, rrect(80, 1150, 1520, 1360, 8), rgb("8fa1b3"), w=5)
    flasks = [(260, rgb("6be8ff")), (420, rgb("ff6fae")), (1150, rgb("8cff7a")), (1320, rgb("ffd166"))]
    for x, liq in flasks:
        p = poly([(x - 20, 960), (x + 20, 960), (x + 20, 1010), (x + 70, 1100), (x - 70, 1100), (x - 20, 1010)])
        fill_ink(cv, p, rgb("eef8ff"), w=5)
        cv.save(); cv.clipPath(p, doAntiAlias=True)
        cv.drawRect(skia.Rect.MakeLTRB(x - 80, 1040, x + 80, 1100), paint(liq)); cv.restore()
        cv.drawPath(p, stroke(INK, 5))
        for b in range(3):
            cv.drawCircle(x - 15 + b * 15, 1060 - b * 12, 7, paint((255, 255, 255), 180))
    fill_ink(cv, rrect(620, 860, 980, 1100, 14), rgb("2c3440"), w=5)
    p = skia.Path(); p.moveTo(650, 1000)
    for k in range(12):
        p.lineTo(650 + k * 27, 1000 + (math.sin(k * 1.3) * 60))
    cv.drawPath(p, stroke(rgb("7cf29a"), 6))
    fill_ink(cv, rrect(1150, 420, 1450, 820, 10), rgb("ffffff"), w=5)
    for k in range(5):
        cv.drawPath(poly([(1190, 480 + k * 60), (1410 - (k % 2) * 80, 480 + k * 60)], close=False), stroke(rgb("3b7de0"), 6))


PAINTERS = {"park": park, "street": street, "home": home, "school": school, "shop": shop, "office": office,
            "night_sky": night_sky, "lab": lab}


def make_background(setting, seed):
    surf = skia.Surface(BW, BH)
    cv = surf.getCanvas()
    PAINTERS.get(setting, street)(cv, random.Random(f"{seed}:{setting}"))
    return surf.makeImageSnapshot()
