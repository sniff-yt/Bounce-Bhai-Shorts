#!/usr/bin/env python3
"""Bounce Bhai 2D cartoon renderer: vector characters (toon2d) + painted sets (sets2d), drawn with skia at a native
1080x1920, 30 fps. No 3D, no sampling noise, renders a 40 s Short in a couple of minutes on a CPU runner.

usage:  python engine/render2d.py out/story.json [--frames A-B] [--still t1,t2,...]
Writes the same outputs as the Blender path so finish.py / upload.py are unchanged:
story["out"] (mp4 with voice + pad music + captions), <out>.meta.json, <out minus .mp4>.{hi,en,hd,te}.srt
"""
import json, math, os, random, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np
import skia
from PIL import Image, ImageDraw

import sets2d as S
import toon2d as T

FPS = 30
W, H = T.W, T.H
LEAD, GAP, TAIL = 0.4, 0.22, 1.0      # same voice timeline as finish.py
FEET_Y = 1650


def ffprobe_dur(p):
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                          "-of", "csv=p=0", p]).decode().strip())


def voice_env(path, n):
    """Mouth-open envelope (0..1) per frame for a voice line, lightly smoothed so lips don't flicker."""
    try:
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", "12000", "-f", "s16le", "-"],
                             capture_output=True, check=True).stdout
        a = np.frombuffer(raw[:len(raw) // 2 * 2], np.int16).astype(np.float32) / 32768
    except Exception:
        return np.zeros(n)
    hop = 12000 // FPS
    env = np.array([np.sqrt(np.mean(a[i * hop:(i + 1) * hop] ** 2)) if (i + 1) * hop <= len(a) else 0.0
                    for i in range(n)])
    ref = np.percentile(env[env > 0], 92) if np.any(env > 0) else 1.0
    env = np.clip(env / max(ref, 1e-4), 0, 1)
    out = np.copy(env)
    for i in range(1, n):          # fast attack, slower release
        out[i] = env[i] if env[i] > out[i - 1] else out[i - 1] * 0.55 + env[i] * 0.45
    out[out < 0.12] = 0
    return out


def ease(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def lerp(a, b, t):
    return a + (b - a) * t


# ============================================================================ story -> timeline
class Story:
    def __init__(self, path):
        self.path = path
        self.cfg = json.load(open(path))
        cfg = self.cfg
        vl = cfg.get("voice_lines") or []
        self.sst, self.durs, t = [], [], LEAD
        for i, s in enumerate(cfg["sentences"]):
            d = ffprobe_dur(vl[i]) if i < len(vl) and os.path.exists(vl[i]) else 0.35 + 0.075 * len(s.get("hd", s["hi"]))
            self.sst.append(t); self.durs.append(d)
            t += d + GAP
        self.total = t - GAP + TAIL
        self.N = int(math.ceil(self.total * FPS))
        self.envs = []
        for i, s in enumerate(cfg["sentences"]):
            n = int(math.ceil(self.durs[i] * FPS)) + 2
            self.envs.append(voice_env(vl[i], n) if i < len(vl) and os.path.exists(vl[i]) else
                             np.clip(np.abs(np.sin(np.arange(n) * 0.9)) * 0.9, 0, 1))
        seed = cfg.get("seed", 0)
        self.seed = seed
        self.looks = [T.make_look(c.get("type", "man"), c.get("color", "blue"), random.Random(f"{seed}:{ci}:look"))
                      for ci, c in enumerate(cfg["cast"])]
        self.bgs = {}
        # shot boundaries: a shot starts a little before its line and runs to the next line
        self.shot_t0 = [0.0] + [self.sst[j] - GAP / 2 for j in range(1, len(self.sst))]
        # camera plan per shot: wide by default, a close-up on the speaker for big moments / every few lines
        self.cam = []
        for j, s in enumerate(cfg["sentences"]):
            act = s["scene"]["action"]
            close = act in ("think", "shocked") or (j % 3 == 2 and len(s["scene"]["characters"]) > 1) or \
                (j == len(cfg["sentences"]) - 1 and act in ("talk", "celebrate", "point"))
            self.cam.append("close" if close and act not in ("walk", "run", "jump", "fall") else "wide")
        # per-character blink schedules (natural, unsynchronised)
        self.blinks = []
        for ci in range(len(cfg["cast"])):
            r = random.Random(f"{seed}:{ci}:blink")
            ts, t = [], r.uniform(0.4, 1.8)
            while t < self.total:
                ts.append(t)
                if r.random() < 0.2:
                    ts.append(t + 0.3)
                t += r.uniform(2.0, 4.6)
            self.blinks.append(ts)

    def bg(self, setting):
        if setting not in self.bgs:
            self.bgs[setting] = S.make_background(setting, self.seed)
        return self.bgs[setting]

    def shot_at(self, t):
        j = 0
        for k, t0 in enumerate(self.shot_t0):
            if t >= t0:
                j = k
        return j


# ============================================================================ animation
def blink_val(ts, t):
    for b in ts:
        d = t - b
        if 0 <= d < 0.2:
            return [0.6, 1.0, 1.0, 0.5, 0.15, 0][min(5, int(d * FPS))]
    return 0.0


def slots(n):
    return {1: [800], 2: [590, 1010], 3: [470, 800, 1130]}.get(n, [470, 800, 1130])


def char_scale(n, look):
    return {1: 1.42, 2: 1.28, 3: 1.06}.get(n, 1.0)


def pose_for(st, j, ci, role, t_shot, t_abs):
    """role 0 = lead (speaks this line), 1+ = others on screen."""
    cfg = st.cfg
    sc = cfg["sentences"][j]["scene"]
    group = sc["action"] in ("walk", "run")          # everyone on screen moves together, slightly staggered
    act = sc["action"] if (role == 0 or group) else "listen"
    ids = sc["characters"]
    n = len(ids)
    look = st.looks[ci]
    P = T.rest_pose()
    xs = slots(n)
    P["x"] = xs[ids.index(ci)]
    P["y"] = FEET_Y
    P["scale"] = char_scale(n, look)
    lead_x = xs[0]
    ph = (ci * 1.7 + j * 0.9)
    # idle: breathing + sway + blink
    P["bob"] = 3.0 * math.sin(t_abs * 2.1 + ph)
    P["lean"] = 1.2 * math.sin(t_abs * 0.9 + ph)
    P["l_sh"] = 8 + 2 * math.sin(t_abs * 1.3 + ph); P["r_sh"] = 8 + 2 * math.sin(t_abs * 1.2 + ph + 1)
    P["blink"] = blink_val(st.blinks[ci], t_abs)
    # mouth: lead speaks during its line
    line_t = t_abs - st.sst[j]
    talking = role == 0 and 0 <= line_t <= st.durs[j]
    env = 0.0
    if talking:
        e = st.envs[j]
        k = int(line_t * FPS)
        env = float(e[min(k, len(e) - 1)])
    P["mouth"] = env * 0.95
    # gaze: listeners look at the speaker, the speaker looks at listeners / the camera
    if role != 0 and not group:
        P["gaze"] = (max(-1, min(1, (lead_x - P["x"]) / 250.0)), 0.0)
        P["smile"] = 0.65
        P["head_tilt"] = 2.5 * math.sin(t_abs * 0.8 + ph)
        if sc["action"] in ("shocked", "fall"):
            P.update(brow_up=0.9, mouth=0.45 if t_shot > 0.3 else 0, smile=-0.2, l_sh=40, r_sh=40, l_el=80, r_el=80)
        elif sc["action"] == "celebrate":
            P.update(smile=1.0, r_sh=150, r_el=-20, bob=P["bob"] + abs(math.sin(t_abs * 7 + ph)) * 18)
        return P, None
    others = [xs[k] for k in range(n) if k != 0]
    look_dir = 0.0 if not others else max(-1, min(1, (sum(others) / len(others) - P["x"]) / 300.0))
    P["gaze"] = (look_dir * 0.7, 0.0)
    P["smile"] = 0.55
    fx = None   # optional effect: ("bang"|"think"|"stars"|"confetti", x, y)
    u = t_shot - (0.25 * (n - 1 - role) if group else 0.0)   # the one going furthest sets off first
    side = 1 if look_dir >= 0 else -1   # arm that gestures towards the others
    if group:
        side = 1                            # the whole group enters from the left
        P["gaze"] = (0.6 * side, 0.0)
    arm_sh, arm_el = ("r_sh", "r_el") if side > 0 else ("l_sh", "l_el")
    if act == "talk":
        beat = math.sin(t_abs * 3.4 + ph)
        P[arm_sh] = 30 + 28 * env + 8 * beat
        P[arm_el] = 55 + 25 * env
        P["head_tilt"] = 4 * math.sin(t_abs * 2.3) * (0.4 + env)
        P["brow_up"] = 0.35 * env
        P["bob"] += 5 * env
    elif act == "point":
        a = ease(u / 0.35)
        P[arm_sh] = lerp(10, 92, a); P[arm_el] = lerp(10, -6, a)
        P["lean"] += side * 4 * a
        P["brow_up"] = 0.4; P["smile"] = 0.7
    elif act == "wave":
        a = ease(u / 0.3)
        P["r_sh"] = lerp(10, 150, a); P["r_el"] = lerp(10, -35 + 28 * math.sin(t_abs * 9), a)
        P["smile"] = 1.0
    elif act == "think":
        a = ease(u / 0.4)
        P["r_sh"] = lerp(8, -15, a); P["r_el"] = lerp(10, -145, a)   # hand to chin
        P["gaze"] = (0.5 * a, -0.85 * a); P["brow"] = 0.35 * a; P["smile"] = 0.2
        P["head_tilt"] = -6 * a
        fx = ("think", P["x"], 0)
    elif act == "shocked":
        jolt = math.exp(-u * 6) * math.sin(u * 40)
        P["squash"] = 0.6 * max(0, math.exp(-u * 5))
        P.update(brow_up=1.0, smile=-0.3, l_sh=55, r_sh=55, l_el=95, r_el=95)
        P["mouth"] = max(P["mouth"], 0.6)
        P["x"] += 10 * jolt
        fx = ("bang", P["x"], 0)
    elif act == "celebrate":
        hop = abs(math.sin(u * 6.5))
        P["bob"] += hop * 70
        P["squash"] = -0.25 * hop + 0.2 * (1 - hop) ** 4
        P.update(l_sh=150 + 15 * math.sin(u * 13), r_sh=150 + 15 * math.cos(u * 13), l_el=-20, r_el=-20, smile=1.0,
                 brow_up=0.6)
        fx = ("confetti", P["x"], 0)
    elif act == "jump":
        k = (u * 1.1) % 1.2
        if k < 0.18:
            P["squash"] = 0.8 * math.sin(k / 0.18 * math.pi / 2); P["bob"] -= 0
        elif k < 0.78:
            v = (k - 0.18) / 0.6
            P["bob"] += 260 * math.sin(v * math.pi)
            P["squash"] = -0.35 * math.sin(v * math.pi)
            P.update(l_sh=150, r_sh=150, l_el=-10, r_el=-10, l_hip=-20, r_hip=-20, l_knee=40, r_knee=40)
        elif k < 0.95:
            P["squash"] = 0.7 * (1 - (k - 0.78) / 0.17)
        P["smile"] = 1.0; P["brow_up"] = 0.6
    elif act in ("walk", "run"):
        speed = 2.2 if act == "walk" else 4.0
        enter = 1.4 if act == "walk" else 0.9
        a = max(-0.5, min(1.0, u / enter))
        start = -260 if side > 0 else W + 520
        P["x"] = lerp(start, P["x"], 1 - (1 - a) ** 2) if a < 1 else P["x"]
        moving = a < 1 or act == "run"
        if a >= 1 and act == "walk":
            moving = False
        if moving:
            cyc = u * speed * math.pi * 2
            amp = 26 if act == "walk" else 42
            P["l_hip"] = amp * math.sin(cyc); P["r_hip"] = -amp * math.sin(cyc)
            P["l_knee"] = max(0, 40 * math.sin(cyc + 1.6)); P["r_knee"] = max(0, 40 * math.sin(cyc + 1.6 + math.pi))
            P["l_sh"] = 10 - amp * 0.9 * math.sin(cyc); P["r_sh"] = 10 + amp * 0.9 * math.sin(cyc)
            if act == "run":
                P["l_el"] = P["r_el"] = 75; P["lean"] += 9 * side
            P["bob"] += abs(math.sin(cyc)) * (12 if act == "walk" else 28)
            if act == "run" and a >= 1:   # run in place towards the camera feel: keep cycling at the slot
                P["x"] += 6 * math.sin(cyc * 0.5)
        P["smile"] = 0.8
    elif act == "fall":
        if u < 0.25:
            P["lean"] = 0
            P.update(l_sh=60, r_sh=60, brow_up=1.0, mouth=0.7)
        else:
            a = ease((u - 0.25) / 0.35)
            rec = ease((u - 1.9) / 0.5)
            P["lean"] = side * -82 * a * (1 - rec)
            P["x"] += side * 300 * P["scale"] * a * (1 - rec)   # keep the fallen body in frame
            P["bob"] = 0
            P.update(l_sh=lerp(60, 150, a), r_sh=lerp(60, 150, a), brow_up=1.0, smile=-0.3,
                     mouth=max(P["mouth"], 0.5))
            P["blink"] = 1.0 if 0.7 < u < 1.4 else P["blink"]
            if a > 0.9 and rec < 0.5:
                fx = ("stars", P["x"] - side * 420 * P["scale"], 0)
    elif act == "sit":
        P["sit"] = 1.0
        P["l_hip"] = -8; P["r_hip"] = 8; P["l_knee"] = 0; P["r_knee"] = 0
        P[arm_sh] = 25 + 25 * env; P[arm_el] = 60
        fx = ("stool", P["x"], 0)
    return P, fx


def head_y(P, look):
    s = P["scale"] * look["height"]
    kid = look.get("kid")
    return P["y"] - P["bob"] * s - (640 if not kid else 500) * s


# ============================================================================ effects
def draw_fx(cv, fx, P, look, t):
    kind, x, _ = fx
    hy = head_y(P, look)
    s = P["scale"]
    if kind == "bang":
        pts = []
        for k in range(16):
            r = (70 if k % 2 == 0 else 38) * s
            a = k / 16 * math.pi * 2
            pts.append((x + 150 * s + math.cos(a) * r, hy - 120 * s + math.sin(a) * r))
        T.fill_ink(cv, T.poly(pts), T.rgb("ffd23f"), w=5)
        f = skia.Font(skia.Typeface('DejaVu Sans', skia.FontStyle.Bold()), 80 * s); f.setEmbolden(True)
        cv.drawString("!", x + 138 * s, hy - 92 * s, f, T.paint(T.rgb("e8463d")))
    elif kind == "think":
        q = s * 0.72
        bx, by = x + 150 * s, hy - 175 * s
        for k, r in enumerate((10, 16)):
            T.fill_ink(cv, T.oval(x + (70 + k * 32) * s, hy - (55 + k * 55) * s, r * s, r * s), (255, 255, 255), w=4)
        cloud = T.smooth_closed([(bx - 110 * q, by), (bx - 80 * q, by - 70 * q), (bx, by - 95 * q), (bx + 90 * q, by - 70 * q),
                                 (bx + 115 * q, by), (bx + 80 * q, by + 60 * q), (bx, by + 75 * q), (bx - 85 * q, by + 60 * q)])
        T.fill_ink(cv, cloud, (255, 255, 255), w=5)
        f = skia.Font(skia.Typeface('DejaVu Sans', skia.FontStyle.Bold()), 96 * q)
        bob = 6 * math.sin(t * 5)
        cv.drawString("?", bx - 28 * q, by + 34 * q + bob, f, T.paint(T.rgb("3b7de0")))
    elif kind == "stars":
        for k in range(4):
            a = t * 4 + k * math.pi / 2
            sx, sy = x + math.cos(a) * 80 * s, P["y"] - 140 * s + math.sin(a) * 26 * s
            pts = []
            for q in range(10):
                r = (22 if q % 2 == 0 else 9) * s
                b = q / 10 * math.pi * 2 - math.pi / 2
                pts.append((sx + math.cos(b) * r, sy + math.sin(b) * r))
            T.fill_ink(cv, T.poly(pts), T.rgb("ffd23f"), w=3)
    elif kind == "confetti":
        r = random.Random(7)
        cols = [T.rgb(c) for c in ("e8463d", "3b7de0", "3fb36b", "f4c22b", "ef6fa8", "8b5cd6")]
        for k in range(46):
            px = x + r.uniform(-420, 420)
            fall = (t * r.uniform(180, 320) + r.uniform(0, 1400)) % 1400
            py = hy - 500 + fall
            cv.save(); cv.translate(px + 30 * math.sin(t * 3 + k), py); cv.rotate(t * 200 + k * 37)
            cv.drawRect(skia.Rect.MakeLTRB(-9, -5, 9, 5), T.paint(r.choice(cols)))
            cv.restore()


def draw_stool(cv, x):
    T.fill_ink(cv, T.rrect(x - 95, FEET_Y - 190, x + 95, FEET_Y - 150, 12), T.rgb("c17f4a"), w=5)
    for dx in (-75, 60):
        T.fill_ink(cv, T.rrect(x + dx - 8, FEET_Y - 155, x + dx + 8, FEET_Y - 4, 4), T.rgb("8a5a3b"), w=4)


# ============================================================================ frame
def camera(st, j, t):
    """(cx, cy, zoom) in background coordinates."""
    sc = st.cfg["sentences"][j]["scene"]
    ids = sc["characters"]
    xs = slots(len(ids))
    u = t - st.shot_t0[j]
    dur = (st.shot_t0[j + 1] if j + 1 < len(st.shot_t0) else st.total) - st.shot_t0[j]
    k = ease(u / max(0.5, dur))
    if st.cam[j] == "close":
        look = st.looks[ids[0]]
        P = T.rest_pose(); P["x"] = xs[0]; P["y"] = FEET_Y; P["scale"] = char_scale(len(ids), look)
        hy = head_y(P, look)
        z = lerp(1.55, 1.68, k)
        cx, cy = xs[0], hy + 250
    else:
        z = lerp(1.0, 1.07, k) if j % 2 == 0 else lerp(1.07, 1.0, k)
        cx = sum(xs) / len(xs) + (lerp(-30, 30, k) if j % 2 else lerp(30, -30, k))
        cy = 1060
    hw, hh = W / 2 / z, H / 2 / z
    cx = max(hw, min(S.BW - hw, cx))
    cy = max(hh, min(S.BH - hh, cy))
    return cx, cy, z


def draw_scene(cv, st, j, t):
    sc = st.cfg["sentences"][j]["scene"]
    cx, cy, z = camera(st, j, t)
    cv.save()
    cv.translate(W / 2, H / 2)
    if sc["action"] in ("shocked", "fall"):
        u = t - st.shot_t0[j]
        amp = 9 * math.exp(-max(0, u - (0.3 if sc["action"] == "fall" else 0)) * 5) * (u > (0.55 if sc["action"] == "fall" else 0))
        cv.translate(amp * math.sin(t * 61), amp * math.cos(t * 47))
    cv.scale(z, z)
    cv.translate(-cx, -cy)
    cv.drawImage(st.bg(sc["setting"]), 0, 0, skia.SamplingOptions(skia.FilterMode.kLinear))
    ids = sc["characters"]
    poses = []
    for role, ci in enumerate(ids):
        P, fx = pose_for(st, j, ci, role, t - st.shot_t0[j], t)
        poses.append((ci, P, fx))
    # back-to-front: lead drawn last so its gestures read over the others
    for ci, P, fx in poses:
        if fx and fx[0] == "stool":
            draw_stool(cv, P["x"])
    for ci, P, fx in reversed(poses):
        T.draw_character(cv, st.looks[ci], P)
    for ci, P, fx in poses:
        if fx and fx[0] != "stool":
            draw_fx(cv, fx, P, st.looks[ci], t)
    cv.restore()


try:  # dashboard live view (scripts/live.py); optional
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
    import live as _live
except Exception:
    _live = None


def render(story_path, frames=None, stills=None):
    sys.argv = [sys.argv[0]]
    import render3d as R

    st = Story(story_path)
    cfg = st.cfg
    surf = skia.Surface(W, H)
    cv = surf.getCanvas()
    XF = 0.18   # crossfade seconds when the setting changes

    def frame_rgb(t):
        j = st.shot_at(t)
        cv.clear(skia.ColorWHITE)
        draw_scene(cv, st, j, t)
        if j > 0 and t - st.shot_t0[j] < XF and \
                cfg["sentences"][j]["scene"]["setting"] != cfg["sentences"][j - 1]["scene"]["setting"]:
            a = 1 - (t - st.shot_t0[j]) / XF
            cv.saveLayerAlpha(None, int(255 * a))
            draw_scene(cv, st, j - 1, t)
            cv.restore()
        arr = surf.makeImageSnapshot().toarray(colorType=skia.kRGBA_8888_ColorType)
        return Image.fromarray(arr[:, :, :3])

    if stills:
        outs = []
        for t in stills:
            p = cfg["out"].replace(".mp4", f"_still_{t:.2f}.png")
            frame_rgb(t).save(p); outs.append(p)
        print("stills:", outs)
        return

    # ---- captions / subtitles / audio: identical behaviour to the Blender compose step
    vlines = [R.load_voice(p) for p in cfg["voice_lines"]] if cfg.get("voice_lines") else None
    sst, durs = st.sst, st.durs
    words = " ".join(s["hi"] for s in cfg["sentences"]).split()
    starts = []
    for j, s_ in enumerate(cfg["sentences"]):
        ws = s_["hi"].split(); d = durs[j]
        wt = np.array([0.22 + 0.045 * len(w) for w in ws]); a = np.cumsum(np.r_[0, wt[:-1]]) / wt.sum()
        starts += list(sst[j] + 0.05 + a * (d - 0.1))
    ch = R.chunks(words)
    total = st.N / FPS
    bounds, k = [], 0
    for s in cfg["sentences"]:
        n = len(s["hi"].split()); bounds.append((starts[k], k, k + n)); k += n
    for lang in ("hi", "en", "hd", "te"):
        lines = []
        for j, (s0, a, b) in enumerate(bounds):
            en = bounds[j + 1][0] if j + 1 < len(bounds) else total
            lines.append(f"{j+1}\n{R.srt_time(s0)} --> {R.srt_time(en)}\n{cfg['sentences'][j].get(lang, '')}\n")
        open(cfg["out"].replace(".mp4", f".{lang}.srt"), "w").write("\n".join(lines))
    esc = sst[len(cfg["sentences"]) - 1]
    wav = cfg["out"] + ".wav"
    R.audio([], int(total * R.FPS), esc, wav, list(zip(sst, vlines)) if vlines else None, music=True, bounces=False)
    fr = range(st.N) if frames is None else range(max(0, frames[0]), min(st.N, frames[1] + 1))
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", wav,
                           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16", "-preset", "slow",
                           "-tune", "animation", "-c:a", "aac", "-b:a", "192k", "-shortest",
                           "-movflags", "+faststart", cfg["out"]], stdin=subprocess.PIPE)
    t0 = time.time()
    for i in fr:
        t = i / FPS
        img = frame_rgb(t)
        dr = ImageDraw.Draw(img)
        if t < 2.4 and cfg.get("hook"):
            hook_words, lines, cur = cfg["hook"].split(), [], ""
            for w_ in hook_words:
                trial = (cur + " " + w_).strip()
                if cur and dr.textlength(trial, font=R.font(84)) > 960:
                    lines.append(cur); cur = w_
                else:
                    cur = trial
            if cur:
                lines.append(cur)
            for li, line in enumerate(lines[:3]):
                R.text_c(dr, 250 + li * 100, line, 84, stroke=7)
        cur = max([k for k, s0 in enumerate(starts) if s0 <= t] or [0])
        cid = next((c for c in ch if cur in c), ch[0])
        if t >= starts[0] - 0.1:
            R.draw_caption(dr, words, cid, cur if t >= starts[0] else -1)
        ff.stdin.write(img.tobytes())
        if _live:
            _live.frame(img, i, st.N)
        if i % 150 == 0:
            print(f"  frame {i}/{st.N}  {time.time() - t0:.0f}s", flush=True)
    ff.stdin.close()
    if ff.wait() != 0:
        raise SystemExit("ffmpeg mux failed")
    os.remove(wav)
    json.dump({"seed": cfg.get("seed"), "esc": esc, "bounces": 0, "tail_pad": 0.8, "engine": "2d"},
              open(cfg["out"] + ".meta.json", "w"))
    el = time.time() - t0
    json.dump({"render_s": round(el, 1), "frames": len(fr), "nframes": st.N, "per_frame_s": round(el / max(1, len(fr)), 4),
               "engine": "2d", "fps": FPS}, open(cfg["out"] + ".render.json", "w"))
    print(f"2d: {len(fr)} frames in {el:.0f}s ->", cfg["out"], flush=True)


if __name__ == "__main__":
    args = sys.argv[1:]
    path = args[0]
    frames = stills = None
    if "--frames" in args:
        a, b = args[args.index("--frames") + 1].split("-"); frames = (int(a), int(b))
    if "--still" in args:
        stills = [float(x) for x in args[args.index("--still") + 1].split(",")]
    render(path, frames, stills)
