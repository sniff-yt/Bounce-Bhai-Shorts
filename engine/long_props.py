#!/usr/bin/env python3
"""Props for the long-form cartoons: hand-held objects (coin, bag of coins, pot of gold, mango, roti, letter ...)
and stage pieces (food carts for pani puri / samosa / chai / momos, a well, a charpai, a magic pot)."""
import math

import skia

from toon2d import rgb, C, shade, paint, stroke, fill_ink, oval, rrect, poly, smooth_closed, INK

GOLD, GOLD_D = rgb("f2c230"), rgb("c8901a")
OBJECTS = ["coin", "coins", "coin_bag", "gold_pot", "pot", "mango", "roti", "letter", "basket", "umbrella", "stick",
           "gift", "bowl", "plate", "flower", "key", "lamp", "magic_pot", "samosa", "pani_puri", "chai", "momos",
           "rice_sack", "book", "seed", "egg", "bread", "jar", "money", "necklace", "fish", "water", "ice_cream"]
OBJ_ALIASES = {"coins_bag": "coin_bag", "money_bag": "coin_bag", "bag": "coin_bag", "gold": "gold_pot",
               "treasure": "gold_pot", "matka": "pot", "pitcher": "pot", "fruit": "mango", "apple": "mango",
               "chapati": "roti", "food": "plate", "tea": "chai", "cup": "chai", "glass": "chai", "note": "letter",
               "paper": "letter", "box": "gift", "present": "gift", "puri": "pani_puri", "golgappa": "pani_puri",
               "rupees": "money", "cash": "money", "notes": "money", "diya": "lamp", "jewel": "necklace",
               "jewellery": "necklace", "jewelry": "necklace", "magic": "magic_pot", "rice": "rice_sack",
               "sack": "rice_sack", "seeds": "seed", "water_pot": "pot", "jug": "jar", "gold_coin": "coin",
               "coin_pot": "gold_pot", "icecream": "ice_cream", "ice_cream_cone": "ice_cream", "cone": "ice_cream", "kulfi": "ice_cream", "dumplings": "momos", "momo": "momos", "pen": "stick", "rope": "stick"}


def obj_name(o):
    o = (o or "").lower().strip().replace(" ", "_")
    if not o or o == "none":
        return None
    return o if o in OBJECTS else OBJ_ALIASES.get(o, "gift" if o else None)


def draw_object(cv, name, x, y, s=1.0, t=0.0):
    """Draw a hand-held object centred near (x, y)."""
    name = obj_name(name)
    if not name:
        return
    cv.save(); cv.translate(x, y); cv.scale(s, s)
    if name in ("coin", "money"):
        if name == "coin":
            fill_ink(cv, oval(0, 0, 22, 22), GOLD, w=4)
            cv.drawCircle(0, 0, 13, stroke(GOLD_D, 3))
        else:
            for k in range(3):
                fill_ink(cv, rrect(-40 + k * 5, -26 + k * 6, 40 + k * 5, 6 + k * 6, 5), rgb("8fce7a"), w=3.5)
                cv.drawCircle(k * 5, -10 + k * 6, 9, stroke(rgb("4c8a3e"), 3))
    elif name == "coins":
        for k, (dx, dy) in enumerate([(-18, 6), (14, 4), (-2, -10), (20, -14), (-20, -12)]):
            fill_ink(cv, oval(dx, dy, 17, 17), GOLD, w=3.5)
    elif name == "coin_bag":
        b = smooth_closed([(-46, 10), (-40, 56), (0, 66), (40, 56), (46, 10), (18, -30), (-18, -30)])
        fill_ink(cv, b, rgb("b0743e"))
        fill_ink(cv, rrect(-22, -42, 22, -26, 6), rgb("8a5a2e"), w=4)
        cv.drawPath(poly([(-20, -34), (20, -34)], close=False), stroke(rgb("e8b923"), 5))
        for dx, dy in [(-8, -50), (10, -54), (0, -60)]:
            fill_ink(cv, oval(dx, dy, 12, 12), GOLD, w=3)
        cv.drawCircle(0, 22, 16, stroke(rgb("f2c230"), 5))
    elif name in ("gold_pot", "pot", "magic_pot", "water", "jar"):
        col = rgb("b5562c") if name != "magic_pot" else rgb("7b4fcf")
        if name == "jar":
            col = rgb("9fd0e0")
        body = smooth_closed([(-30, -36), (-56, 0), (-50, 40), (0, 58), (50, 40), (56, 0), (30, -36)])
        if name in ("gold_pot", "magic_pot"):
            for k in range(6):
                a = t * 2 + k
                gx, gy = math.cos(a) * 40, -50 - (k * 13 + t * 40) % 60
                pt = skia.Paint(AntiAlias=True, Color=C(rgb("fff2a8"), 200))
                cv.drawCircle(gx, gy, 5 + 2 * math.sin(a * 3), pt)
            for dx, dy in [(-22, -38), (0, -46), (22, -38), (-10, -32), (12, -30)]:
                fill_ink(cv, oval(dx, dy, 15, 15), GOLD, w=3)
        fill_ink(cv, body, col)
        fill_ink(cv, rrect(-34, -46, 34, -32, 7), shade(col, 1.15), w=4)
        cv.drawPath(poly([(-50, 6), (50, 6)], close=False), stroke(shade(col, 1.3), 5))
    elif name == "mango":
        fill_ink(cv, smooth_closed([(-20, -26), (24, -18), (30, 14), (0, 32), (-26, 12)]), rgb("f5b324"), w=4)
        cv.drawPath(smooth_closed([(0, -26), (14, -38), (24, -30), (8, -24)]), paint(rgb("3f9e45")))
    elif name in ("roti", "bread"):
        fill_ink(cv, oval(0, 0, 40, 34), rgb("e8c27a"), w=4)
        for dx, dy in [(-12, -8), (10, 6), (6, -14), (-6, 12)]:
            cv.drawCircle(dx, dy, 5, paint(rgb("a8702c")))
    elif name == "letter":
        fill_ink(cv, rrect(-38, -26, 38, 26, 3), rgb("fbf6e8"), w=4)
        cv.drawPath(poly([(-38, -26), (0, 4), (38, -26)], close=False), stroke(INK, 3.5))
    elif name == "basket":
        fill_ink(cv, poly([(-56, -16), (56, -16), (40, 36), (-40, 36)]), rgb("c58a3e"))
        for k in range(-3, 4):
            cv.drawPath(poly([(k * 14, -14), (k * 11, 34)], close=False), stroke(rgb("8a5a2e"), 3))
        for dx in (-30, -6, 18, 38):
            fill_ink(cv, oval(dx, -22, 16, 14), rgb("f5b324"), w=3)
    elif name == "umbrella":
        cv.drawPath(poly([(0, -140), (0, 30)], close=False), stroke(INK, 7))
        u = skia.Path(); u.moveTo(-110, -120); u.quadTo(0, -230, 110, -120); u.close()
        fill_ink(cv, u, rgb("2b2b33"))
    elif name == "stick":
        cv.drawPath(poly([(-10, -80), (10, 80)], close=False), stroke(INK, 16))
        cv.drawPath(poly([(-10, -80), (10, 80)], close=False), stroke(rgb("8b5a34"), 10))
    elif name == "gift":
        fill_ink(cv, rrect(-36, -30, 36, 34, 4), rgb("d9343b"), w=4)
        cv.drawRect(skia.Rect.MakeLTRB(-6, -30, 6, 34), paint(GOLD))
        cv.drawRect(skia.Rect.MakeLTRB(-36, -2, 36, 8), paint(GOLD))
    elif name in ("bowl", "plate", "samosa", "pani_puri", "momos", "seed", "egg", "fish"):
        fill_ink(cv, oval(0, 12, 52, 16), rgb("c9ced6"), w=4)
        food = {"samosa": "samosa", "pani_puri": "puri", "momos": "momo", "seed": "seed", "egg": "egg",
                "fish": "fish"}.get(name, "rice")
        _food(cv, food, 0, 0)
    elif name == "chai":
        fill_ink(cv, rrect(-18, -26, 18, 22, 6), rgb("e7f2f5"), w=4)
        cv.drawRect(skia.Rect.MakeLTRB(-14, -16, 14, 18), paint(rgb("b07040")))
        for k in range(2):
            s = skia.Path(); s.moveTo(-6 + k * 12, -32)
            s.quadTo(-14 + k * 12, -48 - 4 * math.sin(t * 3 + k), -4 + k * 12, -62)
            cv.drawPath(s, stroke((255, 255, 255), 4, a=150))
    elif name == "flower":
        cv.drawPath(poly([(0, 0), (0, 60)], close=False), stroke(rgb("3f9e45"), 6))
        for k in range(6):
            a = k * math.pi / 3
            fill_ink(cv, oval(math.cos(a) * 14, math.sin(a) * 14, 11, 11), rgb("f5a623"), w=2.5)
        cv.drawCircle(0, 0, 9, paint(rgb("d9343b")))
    elif name == "key":
        cv.drawCircle(-20, 0, 14, stroke(GOLD_D, 8))
        cv.drawPath(poly([(-6, 0), (36, 0), (36, 12)], close=False), stroke(GOLD_D, 8))
    elif name == "lamp":
        fill_ink(cv, smooth_closed([(-30, 0), (30, 0), (18, 18), (-18, 18)]), rgb("c8702c"), w=4)
        fl = 1 + 0.15 * math.sin(t * 17)
        glow = skia.Paint(AntiAlias=True)
        glow.setShader(skia.GradientShader.MakeRadial(skia.Point(12, -14), 70, [C(rgb("ffd76a"), 150), C(rgb("ffd76a"), 0)]))
        cv.drawCircle(12, -14, 70, glow)
        cv.drawPath(smooth_closed([(12, -38 * fl), (22, -10), (12, 0), (2, -10)]), paint(rgb("ffb52e")))
    elif name == "rice_sack":
        fill_ink(cv, smooth_closed([(-44, -50), (44, -50), (52, 40), (0, 56), (-52, 40)]), rgb("e5d3a8"))
        cv.drawPath(poly([(-30, -10), (30, -10)], close=False), stroke(rgb("2f9e57"), 6))
    elif name == "book":
        fill_ink(cv, rrect(-36, -26, 36, 26, 4), rgb("2f6fd6"), w=4)
        cv.drawRect(skia.Rect.MakeLTRB(-30, -20, 30, -12), paint(rgb("f2c230")))
    elif name == "necklace":
        cv.drawPath(oval(0, 0, 34, 28), stroke(GOLD, 7))
        fill_ink(cv, oval(0, 28, 10, 12), rgb("d9343b"), w=3)
    elif name == "ice_cream":   # a cone with two scoops, held at the cone
        fill_ink(cv, poly([(-17, -14), (17, -14), (0, 34)]), rgb("e0a454"), w=4)
        for k in range(3):
            cv.drawPath(poly([(-12 + k * 9, -12), (-2 + k * 6, 20)], close=False), stroke(rgb("b9782c"), 2.5))
        fill_ink(cv, oval(0, -24, 19, 15), rgb("f6a6c8"), w=4)
        fill_ink(cv, oval(0, -42, 15, 13), rgb("fff3d6"), w=4)
        cv.drawCircle(4, -54, 5, paint(rgb("d9343b")))
    cv.restore()


def _food(cv, kind, x, y):
    if kind == "samosa":
        for dx in (-26, 0, 26):
            fill_ink(cv, poly([(x + dx - 18, y + 8), (x + dx, y - 26), (x + dx + 18, y + 8)]), rgb("e0a43c"), w=3.5)
    elif kind == "puri":
        for dx, dy in [(-24, 2), (0, -2), (24, 2), (-12, -16), (12, -16)]:
            fill_ink(cv, oval(x + dx, y + dy, 14, 12), rgb("e8b45a"), w=3)
            cv.drawCircle(x + dx, y + dy - 3, 4, paint(rgb("8a5a2e")))
    elif kind == "momo":
        for dx, dy in [(-22, 0), (0, -4), (22, 0), (-10, -18), (12, -18)]:
            fill_ink(cv, smooth_closed([(x + dx - 13, y + dy + 6), (x + dx, y + dy - 14), (x + dx + 13, y + dy + 6)]),
                     rgb("f7f1e3"), w=3)
    elif kind == "egg":
        for dx in (-18, 0, 18):
            fill_ink(cv, oval(x + dx, y - 6, 12, 16), rgb("fbf6e8"), w=3)
    elif kind == "fish":
        fill_ink(cv, smooth_closed([(x - 36, y), (x, y - 16), (x + 30, y), (x, y + 14)]), rgb("8fb8d8"), w=3.5)
        fill_ink(cv, poly([(x + 28, y), (x + 46, y - 14), (x + 46, y + 14)]), rgb("8fb8d8"), w=3.5)
    elif kind == "seed":
        for dx, dy in [(-14, 0), (0, -4), (14, 0), (6, 4), (-6, 4)]:
            cv.drawCircle(x + dx, y + dy, 5, paint(rgb("6b4426")))
    else:
        fill_ink(cv, oval(x, y, 40, 16), rgb("fbf6ea"), w=3.5)


# ------------------------------------------------------------------------------------------------ stage pieces
CARTS = {"pani_puri": ("puri", rgb("2f9e57")), "samosa": ("samosa", rgb("f08a24")), "chai": ("chai", rgb("8e1f3a")),
         "momos": ("momo", rgb("2f6fd6")), "fruit": ("fruit", rgb("d9343b")), "food": ("samosa", rgb("17a2a0")),
         "vegetable": ("veg", rgb("2f9e57")), "aloo_puri": ("puri", rgb("f2c230")), "jalebi": ("jalebi", rgb("f5a623")),
         "vada_pav": ("samosa", rgb("8e1f3a")), "dosa": ("rice", rgb("17a2a0")), "idli": ("rice", rgb("2f6fd6")),
         "chaat": ("puri", rgb("d9343b")), "ice_cream": ("ice", rgb("ec5f9f")), "bhel": ("puri", rgb("7b4fcf"))}


def cart_kind(name):
    n = (name or "").lower()
    for k in CARTS:
        if k.replace("_", "") in n.replace("_", "").replace(" ", ""):
            return k
    if "golgappa" in n or "puchka" in n or "pani" in n:
        return "pani_puri"
    if "tea" in n:
        return "chai"
    if "cart" in n or "stall" in n or "thela" in n:
        return "food"
    return None


def draw_cart(cv, kind, x, y, t=0.0, s=1.0):
    """A street-food cart standing on the floor at (x, y)."""
    food, col = CARTS.get(kind, CARTS["food"])
    cv.save(); cv.translate(x, y); cv.scale(s, s)
    for wx in (-130, 130):
        fill_ink(cv, oval(wx, -44, 44, 44), rgb("5a3a24"), w=5)
        cv.drawCircle(wx, -44, 30, stroke(rgb("8b5a34"), 5))
        a = t * 0
        for k in range(4):
            ang = a + k * math.pi / 4
            cv.drawPath(poly([(wx - math.cos(ang) * 30, -44 - math.sin(ang) * 30), (wx + math.cos(ang) * 30, -44 + math.sin(ang) * 30)],
                             close=False), stroke(rgb("8b5a34"), 4))
    fill_ink(cv, rrect(-200, -250, 200, -80, 12), col)
    cv.drawRect(skia.Rect.MakeLTRB(-200, -110, 200, -96), paint(shade(col, 0.7)))
    for k in range(5):   # decorative stripes
        cv.drawPath(poly([(-180 + k * 90, -230), (-150 + k * 90, -120)], close=False), stroke(shade(col, 1.3), 6))
    fill_ink(cv, rrect(-210, -268, 210, -246, 6), rgb("8b5a34"), w=4)
    # poles + canopy
    for px in (-190, 190):
        cv.drawPath(poly([(px, -268), (px, -740)], close=False), stroke(INK, 12))
        cv.drawPath(poly([(px, -268), (px, -740)], close=False), stroke(rgb("8b5a34"), 7))
    cv.translate(0, -265)
    can = skia.Path(); can.moveTo(-240, -470); can.lineTo(240, -470); can.lineTo(215, -530); can.lineTo(-215, -530); can.close()
    fill_ink(cv, can, rgb("f4f1e8"))
    cv.save(); cv.clipPath(can, doAntiAlias=True)
    for k in range(-6, 7, 2):
        cv.drawRect(skia.Rect.MakeLTRB(k * 40, -540, k * 40 + 40, -460), paint(rgb("d9343b")))
    cv.restore(); cv.drawPath(can, stroke(INK, 5))
    for k in range(-5, 6):   # scalloped edge
        fill_ink(cv, oval(k * 44, -468, 22, 14), rgb("d9343b") if k % 2 else rgb("f4f1e8"), w=3)
    cv.translate(0, 265)
    # goods on the counter
    if food == "chai":
        fill_ink(cv, smooth_closed([(-60, -268), (-90, -320), (-40, -350), (20, -330), (10, -268)]), rgb("b7bcc4"))
        fill_ink(cv, poly([(18, -320), (70, -340), (64, -326), (16, -304)]), rgb("b7bcc4"), w=4)
        for k in range(3):
            s2 = skia.Path(); s2.moveTo(-40 + k * 20, -356)
            s2.quadTo(-52 + k * 20, -380 - 6 * math.sin(t * 2.5 + k), -36 + k * 20, -410)
            cv.drawPath(s2, stroke((255, 255, 255), 6, a=140))
        for k in range(4):
            fill_ink(cv, rrect(60 + k * 30, -296, 82 + k * 30, -268, 4), rgb("e7f2f5"), w=3)
    elif food == "fruit" or food == "veg":
        for k in range(9):
            c2 = [rgb("d9343b"), rgb("f5b324"), rgb("7cc242")][k % 3]
            fill_ink(cv, oval(-150 + k * 36, -290 - (k % 2) * 16, 22, 20), c2, w=3)
    elif food == "ice":
        fill_ink(cv, rrect(-100, -360, 100, -268, 14), rgb("e7f2f5"))
        for k in range(3):
            fill_ink(cv, oval(-50 + k * 50, -372, 22, 20), [rgb("ec5f9f"), rgb("f6e27a"), rgb("7cc242")][k], w=3)
    elif food == "jalebi":
        for k in range(5):
            cv.drawCircle(-100 + k * 50, -296, 20, stroke(rgb("f5a623"), 9))
    else:
        fill_ink(cv, oval(-90, -282, 80, 22), rgb("c9ced6"), w=4)
        _food(cv, {"puri": "puri", "momo": "momo", "rice": "rice"}.get(food, "samosa"), -90, -298)
        if food == "puri":   # pani matka
            fill_ink(cv, smooth_closed([(70, -268), (40, -310), (60, -350), (130, -350), (150, -310), (120, -268)]), rgb("b5562c"))
            fill_ink(cv, oval(95, -352, 40, 10), rgb("8fd0c0"), w=3)
        else:
            fill_ink(cv, oval(95, -282, 70, 20), rgb("c9ced6"), w=4)
            _food(cv, {"puri": "puri", "momo": "momo"}.get(food, "samosa"), 95, -298)
    cv.restore()


def draw_stage_prop(cv, name, x, y, t=0.0):
    n = (name or "").lower()
    k = cart_kind(n)
    if k:
        draw_cart(cv, k, x, y, t)
        return True
    if "scale" in n or "tarazu" in n or "taraju" in n or "weigh" in n or "balance" in n:
        fill_ink(cv, rrect(x - 170, y - 190, x + 170, y - 160, 6), rgb("8b5a34"))
        for px in (x - 150, x + 150):
            fill_ink(cv, rrect(px - 12, y - 165, px + 12, y, 4), rgb("6b4426"), w=4)
        tilt = 8 * math.sin(t * 1.3)
        cv.drawPath(poly([(x, y - 190), (x, y - 330)], close=False), stroke(INK, 12))
        cv.drawPath(poly([(x, y - 190), (x, y - 330)], close=False), stroke(rgb("c8901a"), 7))
        cv.save(); cv.translate(x, y - 330); cv.rotate(tilt)
        cv.drawPath(poly([(-110, 0), (110, 0)], close=False), stroke(INK, 10))
        cv.drawPath(poly([(-110, 0), (110, 0)], close=False), stroke(rgb("c8901a"), 6))
        for sx in (-110, 110):
            cv.save(); cv.translate(sx, 0); cv.rotate(-tilt)
            cv.drawPath(poly([(-34, 80), (0, 0), (34, 80)], close=False), stroke(rgb("6b6f78"), 3))
            fill_ink(cv, smooth_closed([(-46, 80), (46, 80), (30, 100), (-30, 100)]), rgb("c8901a"), w=4)
            cv.restore()
        cv.restore()
        return True
    if "well" in n:
        fill_ink(cv, rrect(x - 130, y - 150, x + 130, y, 10), rgb("b9b2a6"))
        for r_ in range(3):
            for c_ in range(4):
                cv.drawPath(rrect(x - 125 + c_ * 64 + (r_ % 2) * 30, y - 145 + r_ * 48, x - 70 + c_ * 64 + (r_ % 2) * 30, y - 105 + r_ * 48, 6),
                            stroke(shade(rgb("b9b2a6"), 0.7), 3))
        for px in (x - 110, x + 110):
            cv.drawPath(poly([(px, y - 150), (px, y - 330)], close=False), stroke(rgb("6b4426"), 14))
        cv.drawPath(poly([(x - 130, y - 330), (x + 130, y - 330)], close=False), stroke(rgb("6b4426"), 14))
        cv.drawPath(poly([(x, y - 330), (x, y - 220)], close=False), stroke(rgb("d6c7a0"), 4))
        fill_ink(cv, rrect(x - 26, y - 230, x + 26, y - 190, 6), rgb("8a8f98"), w=4)
        return True
    if "charpai" in n or "cot" in n or "bed" in n:
        fill_ink(cv, rrect(x - 200, y - 130, x + 200, y - 100, 8), rgb("8b5a34"))
        for px in (x - 190, x + 190):
            fill_ink(cv, rrect(px - 12, y - 110, px + 12, y, 4), rgb("6b4426"), w=4)
        for k in range(12):
            cv.drawPath(poly([(x - 190 + k * 34, y - 128), (x - 170 + k * 34, y - 102)], close=False), stroke(rgb("e8d8b0"), 4))
        return True
    if "magic" in n or "jadui" in n:
        draw_object(cv, "magic_pot", x, y - 64, 1.1, t)   # same size as when it is carried
        return True
    if "pot" in n or "matka" in n:
        draw_object(cv, "pot", x, y - 64, 1.1, t)
        return True
    if "sack" in n or "grain" in n:
        draw_object(cv, "rice_sack", x, y - 56, 1.5, t)
        draw_object(cv, "rice_sack", x + 90, y - 56, 1.5, t)
        return True
    if "tree" in n:
        cv.drawPath(rrect(x - 40, y - 420, x + 40, y, 20), paint(rgb("7a4f2e")))
        for dx, dy, rr in [(-120, -460, 120), (60, -520, 140), (150, -420, 110), (-30, -580, 120)]:
            cv.drawCircle(x + dx, y + dy, rr, paint(rgb("3f8f3f")))
        return True
    return False
