#!/usr/bin/env python3
"""1280x720 YouTube thumbnail for a long-form story, in the style of the big kahani channels:
the main character HUGE with an exaggerated expression, the key story object glowing, a second character reacting,
a bright saturated sunburst background and 2-4 big bold words in the video's language with a thick outline.

usage: python scripts/long_thumb.py out/long_x.json  -> out/long_x_thumb.jpg (story["thumb"])
"""
import json, math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "engine"))
import numpy as np
import skia
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance

import long_cast as LC
import long_props as LP
from long2d import font
from toon2d import rgb, C, paint

TW, TH = 1280, 720
PALETTES = {"greedy": (rgb("ffd93b"), rgb("ff7a00"), rgb("e0182d")), "surprised": (rgb("fff27a"), rgb("ffb300"), rgb("ff3d00")),
            "cry": (rgb("8fe3ff"), rgb("3a8dff"), rgb("4b2bbf")), "angry": (rgb("ffcf4a"), rgb("ff4d1a"), rgb("a8001c")),
            "scared": (rgb("d9ff7a"), rgb("4ccf6b"), rgb("0f6b4f")), "happy": (rgb("fff27a"), rgb("ffb300"), rgb("ff5a8a"))}
POSE = {"greedy": ((-34, 72), (-34, 72)), "surprised": ((120, -150), (120, -150)), "cry": ((10, 200), (-18, -116)),
        "angry": ((45, 105), (60, -130)), "scared": ((20, -70), (20, -70)), "happy": ((100, -170), (100, -170))}


def burst(cv, cx, cy, c1, c2, c3):
    bg = skia.Paint(AntiAlias=True)
    bg.setShader(skia.GradientShader.MakeRadial(skia.Point(cx, cy), 900, [C(c1), C(c2), C(c3)], [0, 0.45, 1.0]))
    cv.drawRect(skia.Rect.MakeWH(TW, TH), bg)
    n = 22
    for k in range(n):
        if k % 2:
            continue
        a0, a1 = k * 2 * math.pi / n, (k + 1) * 2 * math.pi / n
        p = skia.Path(); p.moveTo(cx, cy)
        p.lineTo(cx + math.cos(a0) * 1600, cy + math.sin(a0) * 1600); p.lineTo(cx + math.cos(a1) * 1600, cy + math.sin(a1) * 1600)
        p.close()
        cv.drawPath(p, paint((255, 255, 255), 38))


def glow(cv, x, y, r, col=(255, 240, 150)):
    g = skia.Paint(AntiAlias=True)
    g.setShader(skia.GradientShader.MakeRadial(skia.Point(x, y), r, [C(col, 230), C(col, 0)]))
    cv.drawCircle(x, y, r, g)


def thumb_plate(story, main_id):
    """The painted set of the story's most dramatic scene with the main character (blurred a little), as a skia image."""
    import long_sets as LS
    best, score = None, -1
    for i, sc in enumerate(story["scenes"]):
        ids = [c.get("id") if isinstance(c, dict) else c for c in sc.get("cast") or []]
        sc_ = (2 if main_id in ids else 0) + {"tense": 2, "sad": 1.5, "magical": 2.5}.get(sc.get("mood"), 0) + \
            (0.5 if sc.get("set") not in ("house_interior",) else 0)
        if sc_ > score:
            best, score = sc, sc_
    if not best:
        return None
    pf, _ = LS.plate_file(LS.set_name(best.get("set")), best.get("time", "day"))
    if not pf:
        return None
    im = Image.open(pf).convert("RGB")
    w, h = im.size
    # the upper 80 % of the painting (the empty ground band is not interesting), 16:9
    ch = int(h * 0.8); cw = int(ch * 16 / 9)
    if cw > w:
        cw = w; ch = int(w * 9 / 16)
    x0 = (w - cw) // 2
    im = im.crop((x0, 0, x0 + cw, ch)).resize((TW, TH), Image.LANCZOS).filter(ImageFilter.GaussianBlur(1.6))
    im = ImageEnhance.Color(im).enhance(1.2)
    a = np.ascontiguousarray(np.array(im.convert("RGBA")))
    return skia.Image.fromarray(a, colorType=skia.kRGBA_8888_ColorType)


def make(path):
    story = json.load(open(path, encoding="utf-8"))
    lang = story.get("lang", "hi")
    th = story.get("thumbnail") or {}
    chars = {c["id"]: c for c in story["characters"]}
    main_id = th.get("character") if th.get("character") in chars else story["characters"][0]["id"]
    expr = LC.expr_name(th.get("expression") or "surprised")
    if expr not in PALETTES:
        expr = {"sly": "greedy", "sad": "cry", "worried": "scared", "laugh": "happy", "proud": "happy"}.get(expr, "surprised")
    obj = LP.obj_name(th.get("object"))
    seed = int(story.get("seed", 7))
    looks = {c["id"]: LC.make_look(c, seed * 131 + sum(map(ord, c["id"]))) for c in story["characters"]}
    # the reacting second character: contrast the main one
    main_role = chars[main_id].get("role")
    others = [c for c in story["characters"] if c["id"] != main_id]
    second = None
    if others:
        pref = ("hero", "elder", "wife") if main_role in ("greedy", "villain", "merchant") else ("greedy", "villain", "merchant")
        second = next((c for c in others if c.get("role") in pref), others[0])
    arr = np.zeros((TH, TW, 4), np.uint8)
    surf = skia.Surface(arr, colorType=skia.kRGBA_8888_ColorType, alphaType=skia.kPremul_AlphaType)
    cv = surf.getCanvas()
    c1, c2, c3 = PALETTES[expr]
    plate = thumb_plate(story, main_id)
    if plate is not None:
        # the story's own painted set (rich and detailed like the big kahani channels), with a coloured glow + soft
        # sunburst behind the main character so the faces pop off it
        cv.drawImageRect(plate, skia.Rect.MakeWH(TW, TH), skia.SamplingOptions(skia.FilterMode.kLinear))
        g = skia.Paint(AntiAlias=True)
        g.setShader(skia.GradientShader.MakeRadial(skia.Point(430, 330), 760, [C(c1, 170), C(c2, 90), C(c3, 0)], [0, 0.4, 1.0]))
        cv.drawRect(skia.Rect.MakeWH(TW, TH), g)
        n = 22
        for k_ in range(0, n, 2):
            a0, a1 = k_ * 2 * math.pi / n, (k_ + 1) * 2 * math.pi / n
            p_ = skia.Path(); p_.moveTo(430, 330)
            p_.lineTo(430 + math.cos(a0) * 1600, 330 + math.sin(a0) * 1600); p_.lineTo(430 + math.cos(a1) * 1600, 330 + math.sin(a1) * 1600)
            p_.close()
            cv.drawPath(p_, paint((255, 255, 255), 22))
        v = skia.Paint(AntiAlias=True)
        v.setShader(skia.GradientShader.MakeRadial(skia.Point(TW / 2, TH / 2), 860, [C((0, 0, 0), 0), C((0, 0, 0), 150)], [0.55, 1.0]))
        cv.drawRect(skia.Rect.MakeWH(TW, TH), v)
    else:
        burst(cv, 430, 330, c1, c2, c3)
    # second character (smaller, right, reacting)
    if second:
        P = LC.rest_pose()
        P.update(LC.EXPR["angry" if expr in ("greedy",) else "greedy" if expr in ("cry", "scared") else "surprised"])
        P.update(x=1110, y=1060, scale=1.2, facing=-1, head_turn=0.5, gaze=(0.5, 0.1))
        P["lh"], P["rh"] = POSE.get("angry" if expr == "greedy" else "greedy" if expr in ("cry", "scared") else "surprised")
        LC.draw_character(cv, looks[second["id"]], P, 0.4)
    # object with glow (right-centre, big)
    if obj:
        glow(cv, 820, 470, 230)
        LP.draw_object(cv, obj, 820, 480, 2.6, 0.8)
    # main character, huge, head in the upper-left third
    look = looks[main_id]
    P = LC.rest_pose()
    P.update(LC.EXPR[expr])
    if expr == "surprised":
        P.update(eye_open=1.5, o_mouth=1.0, brow_up=1.6)
    if expr == "greedy":
        P.update(grin=1.0, sly=0.9, brow=0.9)
    if expr == "cry":
        P.update(tears=1.0, mouth=0.75, smile=-1.0)
    if expr == "angry":
        P.update(mouth=0.7, red=1.0)
    k = 1.88 / look["height"]
    P.update(x=400, y=640 * k * look["height"] * 0.98 + 95, scale=k, facing=1, head_turn=0.35, gaze=(0.45, 0.0))
    P["lh"], P["rh"] = POSE.get(expr, POSE["surprised"])
    if obj and expr in ("greedy", "happy"):
        P["rh"] = (170, 40)
    LC.draw_character(cv, look, P, 0.4)
    img = Image.fromarray(arr[:, :, :3].copy())
    img = ImageEnhance.Color(img).enhance(1.25)
    img = ImageEnhance.Contrast(img).enhance(1.08)
    # big words
    text = (story.get("thumbnail_text") or story.get("title") or "").strip()
    words = text.split()
    rows = [" ".join(words[:max(1, len(words) // 2)]), " ".join(words[max(1, len(words) // 2):])] if len(words) > 2 else [text]
    rows = [r for r in rows if r]
    d = ImageDraw.Draw(img)
    maxw, size = 620, 150
    while size > 60:
        f = font(lang, size, black=True)
        if all(d.textlength(r, font=f) <= maxw for r in rows):
            break
        size -= 6
    f = font(lang, size, black=True)
    asc, desc = f.getmetrics()
    lh = int((asc + desc) * 0.98)
    y = 40
    fills = [(255, 236, 40), (255, 255, 255)]
    for i, r in enumerate(rows):
        w_ = d.textlength(r, font=f)
        x = TW - w_ - 40
        # drop shadow + thick outline
        sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).text((x + 8, y + 10), r, font=f, fill=(0, 0, 0, 170), stroke_width=16, stroke_fill=(0, 0, 0, 170))
        img.paste(sh.filter(ImageFilter.GaussianBlur(6)), (0, 0), sh.filter(ImageFilter.GaussianBlur(6)))
        d = ImageDraw.Draw(img)
        d.text((x, y), r, font=f, fill=fills[i % 2], stroke_width=14, stroke_fill=(20, 10, 10))
        y += lh
    # red arrow from the words to the object
    if obj:
        ax0, ay0, ax1, ay1 = 1000, y + 20, 900, 400
        d.line([(ax0, ay0), (ax1, ay1)], fill=(20, 10, 10), width=30)
        d.line([(ax0, ay0), (ax1, ay1)], fill=(235, 30, 40), width=18)
        ang = math.atan2(ay1 - ay0, ax1 - ax0)
        tip = [(ax1 + math.cos(ang) * 30, ay1 + math.sin(ang) * 30),
               (ax1 + math.cos(ang + 2.5) * 50, ay1 + math.sin(ang + 2.5) * 50),
               (ax1 + math.cos(ang - 2.5) * 50, ay1 + math.sin(ang - 2.5) * 50)]
        d.polygon(tip, fill=(235, 30, 40), outline=(20, 10, 10), width=6)
    # channel tag
    tag_f = font("en", 30, black=True)
    d.rounded_rectangle([20, TH - 66, 20 + d.textlength("BOUNCE BHAI", font=tag_f) + 36, TH - 18], radius=14, fill=(220, 20, 40))
    d.text((38, TH - 64), "BOUNCE BHAI", font=tag_f, fill=(255, 255, 255))
    out = path[:-5] + "_thumb.jpg"
    img.save(out, quality=92)
    story["thumb"] = out
    json.dump(story, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("thumbnail:", out, flush=True)
    return out


if __name__ == "__main__":
    make(sys.argv[1])
