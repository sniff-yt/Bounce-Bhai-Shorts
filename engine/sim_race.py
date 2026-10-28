#!/usr/bin/env python3
"""Bounce Bhai: 3-ball parkour race (pure code, no AI).
Balls bounce in a circle -> drop down a pipe -> race a long random parkour course; camera follows the leader.
usage: python3 sim_race.py config.json
config: {"out": "x.mp4", "seed": 1, "tries": 40, "hook": "KAUN JEETEGA?", "cta": "...", "budget": 150}
"""
import json, math, random, sys, os, subprocess, wave, time
import numpy as np
import skia

W, H, FPS = 1080, 1920, 30
FONT = os.environ.get("BB_FONT", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
BALLS = [((255, 64, 84), "RED"), ((60, 170, 255), "BLUE"), ((70, 225, 120), "GREEN")]
BR, T = 30, 30            # ball radius, wall thickness
XL, XR = 40, 1040         # side walls
CX, CY, CR = 540, 420, 290
GAP = 21                  # arena exit gap (deg)
COUNT = 2.0               # countdown seconds (gate closed): short, so the race starts ~2 s in (Shorts hook)
INTENSE = False           # "intense" races: harder physics, closer finishes, red pulse, faster beat

# ---------------- course ----------------
def make_course(rnd):
    segs, bars, sliders, bumpers, pads = [], [], [], [], []
    n = 90
    a0, a1 = 90 + GAP / 2, 450 - GAP / 2
    pts = [(CX + CR * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
            CY + CR * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]
    segs += list(zip(pts[:-1], pts[1:]))
    gx = CR * math.sin(math.radians(GAP / 2))
    y = CY + CR * math.cos(math.radians(GAP / 2))
    segs += [((CX - gx, y), (CX - gx, 1000)), ((CX + gx, y), (CX + gx, 1000))]
    y = 1000
    pool = ["zigzag", "spinners", "bumpers", "slider", "funnel", "pads"]
    kinds = []
    while len(kinds) < rnd.randint(6, 8):   # tight ~22-34 s races (Shorts retention; 10-12 sections made 35-45 s)
        k = rnd.choice(pool)
        if not kinds or k != kinds[-1]: kinds.append(k)
    for k in kinds:
        if k == "zigzag":
            d = rnd.choice([-1, 1])
            for i in range(2):
                s = d if i == 0 else -d
                if s > 0: segs.append(((XL, y + 60), (XR - 170, y + 200)))
                else:     segs.append(((XR, y + 60), (XL + 170, y + 200)))
                y += 260
            y += 60
        elif k == "spinners":
            sp = rnd.uniform(1.8, 3.0)
            bars.append((300, y + 200, 175, sp, rnd.uniform(0, 6)))
            bars.append((780, y + 200, 175, -sp, rnd.uniform(0, 6)))
            y += 450
        elif k == "bumpers":
            for (bx, by) in [(270, y + 150), (810, y + 150), (540, y + 330)]:
                bumpers.append((bx + rnd.uniform(-40, 40), by, rnd.uniform(62, 80)))
            y += 500
        elif k == "slider":
            sliders.append((y + 150, 130, rnd.uniform(1.0, 1.7), rnd.uniform(0, 6)))
            y += 330
        elif k == "funnel":
            segs += [((XL, y + 40), (480, y + 260)), ((XR, y + 40), (600, y + 260))]
            y += 360
        elif k == "pads":
            pads.append((XL, y + 220, 470, y + 300))   # joined to the walls: no slot for a ball to wedge into
            pads.append((610, y + 300, XR, y + 220))
            segs.append(((470, y + 300), (470, y + 330)))
            y += 400
    y += 120
    finish = y
    segs += [((XL, 1000), (XL, finish + 400)), ((XR, 1000), (XR, finish + 400)), ((XL, finish + 400), (XR, finish + 400))]
    return dict(segs=segs, bars=bars, sliders=sliders, bumpers=bumpers, pads=pads, finish=finish, kinds=kinds)

def moving(c, t):
    """Moving walls at time t: list of (x1,y1,x2,y2, vx_fn) as segments + their angular data."""
    out = []
    for (bx, by, L, w, ph) in c["bars"]:
        a = ph + w * t
        out.append(("bar", bx - L * math.cos(a), by - L * math.sin(a), bx + L * math.cos(a), by + L * math.sin(a), (bx, by, w)))
    for (sy, gw, w, ph) in c["sliders"]:
        gx = 540 + 330 * math.sin(ph + w * t)
        vx = 330 * w * math.cos(ph + w * t)
        out.append(("sl", XL, sy, gx - gw / 2 - BR, sy, vx))
        out.append(("sl", gx + gw / 2 + BR, sy, XR, sy, vx))
    return out

# ---------------- physics ----------------
def collide_seg(p, v, x1, y1, x2, y2, rad, rest, surf=None):
    ax, ay, bx, by = x1, y1, x2, y2
    abx, aby = bx - ax, by - ay
    L2 = abx * abx + aby * aby + 1e-9
    u = max(0.0, min(1.0, ((p[0] - ax) * abx + (p[1] - ay) * aby) / L2))
    cx, cy = ax + abx * u, ay + aby * u
    dx, dy = p[0] - cx, p[1] - cy
    d2 = dx * dx + dy * dy
    if d2 >= rad * rad:
        return 0.0
    d = math.sqrt(d2) + 1e-9
    nx, ny = dx / d, dy / d
    p[0] += nx * (rad - d); p[1] += ny * (rad - d)
    sx, sy = surf(cx, cy) if surf else (0.0, 0.0)
    rvx, rvy = v[0] - sx, v[1] - sy
    vn = rvx * nx + rvy * ny
    if vn < 0:
        rvx -= (1 + rest) * vn * nx; rvy -= (1 + rest) * vn * ny
        rvx *= 0.995; rvy *= 0.995
        v[0], v[1] = rvx + sx, rvy + sy
        return -vn
    return 0.0

def simulate(seed, max_t=70.0):
    rnd = random.Random(seed)
    c = make_course(rnd)
    statics = [(a[0], a[1], b[0], b[1]) for a, b in c["segs"]]
    P = [[CX + rnd.uniform(-150, 150), CY + rnd.uniform(-150, 60)] for _ in range(3)]
    V = [[rnd.uniform(-800, 800), rnd.uniform(-900, 100)] for _ in range(3)]
    sub, G = 10, (2050.0 if INTENSE else 1700.0)
    KICK, PAD, VMAX = (1250, 1600, 2800) if INTENSE else (950, 1350, 2400)
    dt = 1.0 / (FPS * sub)
    frames, events, finish = [], [], {}
    slow = [0.0] * 3
    best_y = [0.0] * 3; stall = [0.0] * 3
    rad = BR + T / 2
    for f in range(int(max_t * FPS)):
        t = f / FPS
        for s in range(sub):
            ts = t + s * dt
            mv = moving(c, ts)
            racing_y = [P[j][1] for j in range(3) if j not in finish]
            lead_y = max(racing_y) if racing_y else 0
            lead_i = max((j for j in range(3) if j not in finish), key=lambda j: P[j][1], default=-1)
            for i in range(3):
                p, v = P[i], V[i]
                if i in finish and p[1] > c["finish"] + 200:
                    v[0] *= 0.98
                v[1] += G * dt
                if ts > COUNT and i not in finish and i != lead_i:
                    behind = lead_y - p[1]
                    if p[1] < CY + CR and lead_y > CY + CR + 200 and ts > COUNT + 2:
                        # still in the arena while others raced off: drift toward the exit gap
                        v[0] += (CX - p[0]) * 3.0 * dt; v[1] += 900 * dt
                    elif behind > 500:
                        v[1] += G * min(0.8, behind / 2500) * dt   # rubber band: no 30-second stragglers
                p[0] += v[0] * dt; p[1] += v[1] * dt
                near = [sg for sg in statics if min(sg[1], sg[3]) - 80 < p[1] < max(sg[1], sg[3]) + 80]
                for sg in near:
                    hit = collide_seg(p, v, *sg, rad, 0.72)
                    if hit > 320: events.append((ts, "wall", i, hit))
                if ts < COUNT:
                    hit = collide_seg(p, v, CX - 70, CY + CR - 4, CX + 70, CY + CR - 4, rad, 0.72)
                for m in mv:
                    if abs(m[2] - p[1]) > 260: continue
                    if m[0] == "bar":
                        bx, by, w = m[5]
                        surf = lambda x, y, bx=bx, by=by, w=w: (-w * (y - by), w * (x - bx))
                        hit = collide_seg(p, v, m[1], m[2], m[3], m[4], rad, 0.6, surf)
                    else:
                        vx = m[5]
                        hit = collide_seg(p, v, m[1], m[2], m[3], m[4], rad, 0.5, lambda x, y, vx=vx: (vx * 0.3, 0.0))
                    if hit > 250: events.append((ts, "kick", i, hit))
                for (bx, by, br) in c["bumpers"]:
                    dx, dy = p[0] - bx, p[1] - by
                    d = math.hypot(dx, dy)
                    if d < br + BR:
                        nx, ny = dx / d, dy / d
                        p[0], p[1] = bx + nx * (br + BR), by + ny * (br + BR)
                        vn = v[0] * nx + v[1] * ny
                        if vn < 0:
                            v[0] -= vn * nx; v[1] -= vn * ny
                        v[0] += nx * KICK; v[1] += ny * KICK
                        events.append((ts, "bump", i, (bx, by)))
                for (x1, y1, x2, y2) in c["pads"]:
                    before = v[1]
                    above = p[1] < y1 + (y2 - y1) * max(0.0, min(1.0, (p[0] - x1) / (x2 - x1)))
                    hit = collide_seg(p, v, x1, y1, x2, y2, rad, 1.0 if above else 0.6)
                    if hit > 0 and above:   # launch only from the top (from below it used to pin balls)
                        v[1] = min(v[1], -float(PAD)); events.append((ts, "pad", i, hit))
            for i in range(3):
                for j in range(i + 1, 3):
                    dx, dy = P[j][0] - P[i][0], P[j][1] - P[i][1]
                    d = math.hypot(dx, dy)
                    if 0 < d < 2 * BR:
                        nx, ny = dx / d, dy / d; ov = 2 * BR - d
                        P[i][0] -= nx * ov / 2; P[i][1] -= ny * ov / 2
                        P[j][0] += nx * ov / 2; P[j][1] += ny * ov / 2
                        rv = (V[j][0] - V[i][0]) * nx + (V[j][1] - V[i][1]) * ny
                        if rv < 0:
                            V[i][0] += rv * nx; V[i][1] += rv * ny
                            V[j][0] -= rv * nx; V[j][1] -= rv * ny
                            if -rv > 300: events.append((ts, "clash", i, j))
            for i in range(3):
                sp = math.hypot(*V[i])
                if sp > VMAX: V[i][0] *= VMAX / sp; V[i][1] *= VMAX / sp
        for i in range(3):
            sp = math.hypot(*V[i])
            slow[i] = slow[i] + 1 / FPS if (sp < 60 and t > COUNT and i not in finish) else 0
            if slow[i] > 1.2:
                V[i][0] += rnd.choice([-1, 1]) * 500; V[i][1] -= 600; slow[i] = 0
            # jitter-stuck (resting on a ledge/spinner but still moving): no downward progress for 1.5 s -> kick
            if P[i][1] > best_y[i] + 25: best_y[i] = P[i][1]; stall[i] = 0
            elif t > COUNT and i not in finish:
                stall[i] += 1 / FPS
                if stall[i] > 1.5:
                    V[i][0] += (1 if P[i][0] < CX else -1) * 650; V[i][1] -= 250; stall[i] = 0
            if i not in finish and P[i][1] > c["finish"]:
                finish[i] = t; events.append((t, "finish", i, len(finish)))
        frames.append([tuple(p) for p in P])
        if len(finish) == 3 and t > max(finish.values()) + 0.5:
            break
        if t > COUNT + 8 and len(finish) == 0 and max(p[1] for p in P) < 1100:
            break  # stuck in arena
    return c, frames, events, finish

def order_at(c, fr, finish, t):
    done = sorted([i for i in finish if finish[i] <= t], key=finish.get)
    rest = sorted([i for i in range(3) if i not in done], key=lambda i: -fr[i][1])
    return done + rest

def score(c, frames, finish):
    if len(finish) < 3: return -1
    dur = len(frames) / FPS
    order = sorted(finish, key=finish.get)
    gap = finish[order[1]] - finish[order[0]]
    win = finish[order[0]] - COUNT          # winner's race time
    spread = finish[order[2]] - finish[order[0]]
    if dur > 40 or spread > 9: return -1   # too long / a straggler leaves dead air
    changes, last = 0, None
    for k in range(int(COUNT * FPS), len(frames), 6):
        ldr = order_at(c, frames[k], finish, k / FPS)[0]
        if last is not None and ldr != last: changes += 1
        last = ldr
    s = min(changes, 8) * 2.0 - gap * 3 + (8 if 22 <= dur <= 34 else -abs(dur - 28) / 2) - spread - max(0, spread - 5) * 5 - max(0, 10 - win) * 4
    return s, dict(dur=round(dur, 1), gap=round(gap, 2), changes=changes, win=round(win, 1), spread=round(spread, 1))

# ---------------- render ----------------
def C(rgb, a=255): return skia.Color(int(rgb[0]), int(rgb[1]), int(rgb[2]), int(a))

TF = skia.Typeface.MakeFromFile(FONT)
def text(cv, s, x, y, size, rgb=(255, 255, 255), center=True, stroke=8):
    f = skia.Font(TF, size)
    w = f.measureText(s)
    if center and w > 940:                 # never let text run off the screen
        size = size * 940 / w; f = skia.Font(TF, size); w = f.measureText(s)
    x0 = x - w / 2 if center else x
    if stroke:
        cv.drawString(s, x0, y, f, skia.Paint(Color=C((0, 0, 0)), AntiAlias=True, Style=skia.Paint.kStroke_Style, StrokeWidth=stroke, StrokeJoin=skia.Paint.kRound_Join))
    cv.drawString(s, x0, y, f, skia.Paint(Color=C(rgb), AntiAlias=True))

def render(cfg, c, frames, events, finish, tmp):
    os.makedirs(tmp, exist_ok=True)
    surf = skia.Surface(W, H); cv = surf.getCanvas()
    wallP = skia.Paint(Color=C((235, 238, 255)), AntiAlias=True, Style=skia.Paint.kStroke_Style, StrokeWidth=T, StrokeCap=skia.Paint.kRound_Cap)
    glowP = skia.Paint(Color=C((120, 140, 255), 150), AntiAlias=True, Style=skia.Paint.kStroke_Style, StrokeWidth=T + 18,
                       StrokeCap=skia.Paint.kRound_Cap, MaskFilter=skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, 14))
    order_final = sorted(finish, key=finish.get)
    first, second = finish[order_final[0]], finish[order_final[1]]
    photo = (second - first) < 0.9
    # timeline with slow motion around a close finish
    tl = []
    for k in range(len(frames)):
        t = k / FPS
        tl.append(k)
        if photo and first - 0.8 <= t <= second + 0.2:
            tl.append(k)  # 2x slow-mo (duplicate)
    end_hold = int(2.4 * FPS)
    fade = int(0.5 * FPS)       # last 0.5 s cross-fades into frame 1, so the Short loops seamlessly
    first_img = None
    tl += [len(frames) - 1] * end_hold
    camy = frames[0][0][1]
    trails = [[], [], []]
    bump_t = {}
    for (te, kind, i, data) in events:
        if kind == "bump": bump_t.setdefault(data, []).append(te)
    shake_ev = sorted(te for (te, kind, i, d) in events if kind in ("bump", "clash", "pad"))
    last_leader, flash = None, -9
    lead_changes = []
    seq = []
    for n, k in enumerate(tl):
        t = k / FPS
        fr = frames[k]
        order = order_at(c, fr, finish, t)
        leader = order[0]
        if t > COUNT and last_leader is not None and leader != last_leader and n < len(tl) - end_hold:
            flash = n; lead_changes.append(n / FPS)
        last_leader = leader
        # camera: follow the leader that is still racing (or the pack), keep lookahead
        racing = [i for i in range(3) if i not in finish or finish[i] > t]
        tgt_i = racing[0] if racing and False else None
        ys = [fr[i][1] for i in (racing or range(3))]
        tgt = max(min(ys) * 0.35 + max(ys) * 0.65 - 760, 0)
        tgt = min(tgt, c["finish"] + 420 - H + 60)
        if t < COUNT: tgt = 0
        camy += (tgt - camy) * 0.12
        sh = 0
        for te in shake_ev:
            if 0 <= t - te < 0.18: sh = (15 if INTENSE else 9) * (1 - (t - te) / 0.18)
        ox = math.sin(n * 2.7) * sh; oy = math.cos(n * 3.1) * sh
        # background
        cv.clear(C((10, 10, 24)))
        bg = skia.Paint(Shader=skia.GradientShader.MakeLinear([(0, 0), (0, H)], [C((24, 14, 48)), C((6, 18, 36))]))
        cv.drawRect(skia.Rect(0, 0, W, H), bg)
        cv.save(); cv.translate(ox, -camy + oy)
        gp = skia.Paint(Color=C((255, 255, 255), 14), StrokeWidth=2)
        g0 = int(camy // 120) * 120
        for gy in range(g0, int(camy + H + 120), 120): cv.drawLine(0, gy, W, gy, gp)
        for gx in range(0, W, 120): cv.drawLine(gx, camy - 50, gx, camy + H + 50, gp)
        mv = moving(c, t)
        path = skia.Path()
        for (a, b) in c["segs"]:
            if max(a[1], b[1]) < camy - 60 or min(a[1], b[1]) > camy + H + 60: continue
            path.moveTo(*a); path.lineTo(*b)
        if t < COUNT:
            path.moveTo(CX - 70, CY + CR - 4); path.lineTo(CX + 70, CY + CR - 4)
        cv.drawPath(path, glowP); cv.drawPath(path, wallP)
        for m in mv:
            col = (255, 80, 190) if m[0] == "bar" else (255, 170, 40)
            p2 = skia.Paint(Color=C(col), AntiAlias=True, Style=skia.Paint.kStroke_Style, StrokeWidth=T, StrokeCap=skia.Paint.kRound_Cap)
            g2 = skia.Paint(Color=C(col, 160), AntiAlias=True, Style=skia.Paint.kStroke_Style, StrokeWidth=T + 20, StrokeCap=skia.Paint.kRound_Cap,
                            MaskFilter=skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, 14))
            cv.drawLine(m[1], m[2], m[3], m[4], g2); cv.drawLine(m[1], m[2], m[3], m[4], p2)
            if m[0] == "bar":
                cv.drawCircle(m[5][0], m[5][1], 16, skia.Paint(Color=C((255, 255, 255)), AntiAlias=True))
        for (bx, by, br) in c["bumpers"]:
            hot = any(0 <= t - te < 0.25 for te in bump_t.get((bx, by), []))
            rr = br * (1.12 if hot else 1.0)
            cv.drawCircle(bx, by, rr + 10, skia.Paint(Color=C((0, 230, 255), 140 if not hot else 230), AntiAlias=True,
                                                         MaskFilter=skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, 16)))
            cv.drawCircle(bx, by, rr, skia.Paint(Color=C((255, 255, 255) if hot else (0, 200, 240)), AntiAlias=True))
            cv.drawCircle(bx, by, rr * 0.62, skia.Paint(Color=C((10, 40, 70)), AntiAlias=True))
        for (x1, y1, x2, y2) in c["pads"]:
            pp = skia.Paint(Color=C((120, 255, 120)), AntiAlias=True, Style=skia.Paint.kStroke_Style, StrokeWidth=T, StrokeCap=skia.Paint.kRound_Cap)
            cv.drawLine(x1, y1, x2, y2, pp)
        # finish line
        fy = c["finish"]
        for q in range(0, 1000 // 40):
            for r2 in range(2):
                cv.drawRect(skia.Rect(XL + q * 40, fy + r2 * 20, XL + q * 40 + 40, fy + r2 * 20 + 20),
                            skia.Paint(Color=C((255, 255, 255) if (q + r2) % 2 else (20, 20, 20))))
        text(cv, "FINISH", 540, fy - 24, 54, (255, 230, 80), stroke=8)
        # balls
        for i in range(3):
            col, name = BALLS[i]; x, y = fr[i]
            trails[i].append((x, y)); trails[i] = trails[i][-12:]
            for j, (tx, ty) in enumerate(trails[i][:-1]):
                a = (j + 1) / len(trails[i])
                cv.drawCircle(tx, ty, BR * (0.35 + 0.55 * a), skia.Paint(Color=C(col, 90 * a), AntiAlias=True))
            cv.drawCircle(x, y, BR + 14, skia.Paint(Color=C(col, 170), AntiAlias=True, MaskFilter=skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, 14)))
            sh_ = skia.GradientShader.MakeRadial((x - BR * 0.35, y - BR * 0.35), BR * 1.3,
                                                 [C(tuple(min(255, cc + 110) for cc in col)), C(col), C(tuple(cc * 0.55 for cc in col))], [0, 0.55, 1])
            cv.drawCircle(x, y, BR, skia.Paint(Shader=sh_, AntiAlias=True))
            cv.drawCircle(x, y, BR, skia.Paint(Color=C((255, 255, 255)), AntiAlias=True, Style=skia.Paint.kStroke_Style, StrokeWidth=4))
        cv.restore()
        # HUD
        cv.drawRect(skia.Rect(0, 0, W, 300), skia.Paint(Shader=skia.GradientShader.MakeLinear([(0, 0), (0, 300)], [C((0, 0, 0), 200), C((0, 0, 0), 0)])))
        text(cv, cfg.get("hook", "KAUN JEETEGA?"), 540, 110, 78, (255, 255, 255), stroke=10)
        if t < COUNT:
            text(cv, "INTENSE RACE!" if INTENSE else cfg.get("sub_hook", "Apna colour chuno!"), 540, 185, 50, (255, 70, 70) if INTENSE else (255, 230, 80), stroke=8)
            text(cv, "Finish se pehle comment karo!", 540, 1680, 46, (255, 255, 255), stroke=7)
            num = str(int(COUNT) - int(t))
            sz = 260 * (1.3 - (t % 1) * 0.3)
            text(cv, num, 540, 1500, sz, (255, 230, 80), stroke=14)
        elif t < COUNT + 0.7:
            text(cv, "GO!", 540, 1500, 260, (90, 240, 120), stroke=14)
        else:
            for r_, i in enumerate(order):
                col, name = BALLS[i]
                y0 = 160 + r_ * 62
                cv.drawRRect(skia.RRect.MakeRectXY(skia.Rect(40, y0 - 44, 330, y0 + 12), 16, 16), skia.Paint(Color=C((0, 0, 0), 150), AntiAlias=True))
                cv.drawCircle(78, y0 - 16, 18, skia.Paint(Color=C(col), AntiAlias=True))
                text(cv, f"{r_ + 1}. {name}", 110, y0, 46, col, center=False, stroke=6)
        if INTENSE and t > COUNT and n < len(tl) - end_hold:
            ry = sorted((fr[i][1] for i in range(3) if i not in finish or finish[i] > t), reverse=True)
            close = len(ry) >= 2 and ry[0] - ry[1] < 220
            stretch = ry and c["finish"] - ry[0] < 750
            if close or stretch:   # red heartbeat pulse at the edges when it's neck and neck
                a = int(70 + 60 * (0.5 + 0.5 * math.sin(n * 0.55)))
                vg = skia.GradientShader.MakeRadial((540, 960), 1150, [C((255, 0, 40), 0), C((255, 0, 40), 0), C((255, 20, 50), a)], [0.0, 0.6, 1.0])
                cv.drawRect(skia.Rect(0, 0, W, H), skia.Paint(Shader=vg))
            if stretch:
                text(cv, "FINAL STRETCH!", 540, 380, 74, (255, 80, 80), stroke=10)
            elif close and (n // 8) % 2 == 0:
                text(cv, "NECK AND NECK!", 540, 380, 66, (255, 200, 60), stroke=10)
        # progress bar (right)
        top, bot = 330, 1650
        cv.drawRRect(skia.RRect.MakeRectXY(skia.Rect(1000, top, 1024, bot), 12, 12), skia.Paint(Color=C((255, 255, 255), 50), AntiAlias=True))
        for i in range(3):
            pr = max(0, min(1, (fr[i][1] - 900) / (c["finish"] - 900)))
            cv.drawCircle(1012, top + (bot - top) * pr, 17, skia.Paint(Color=C(BALLS[i][0]), AntiAlias=True))
        text(cv, "🏁" if False else "F", 1012, bot + 50, 40, (255, 230, 80), stroke=6)
        if photo and first - 0.8 <= t <= second + 0.6 and n < len(tl) - end_hold:
            text(cv, "PHOTO FINISH!", 540, 700, 92, (255, 255, 255), stroke=12)
        if n >= len(tl) - end_hold:
            w = order_final[0]
            cv.drawRect(skia.Rect(0, 0, W, H), skia.Paint(Color=C((0, 0, 0), 165)))
            text(cv, f"{BALLS[w][1]} JEET GAYA!", 540, 880, 120, BALLS[w][0], stroke=14)
            for r_, i in enumerate(order_final):
                text(cv, f"{['1st', '2nd', '3rd'][r_]}  {BALLS[i][1]}  {finish[i] - COUNT:0.2f}s", 540, 1010 + r_ * 80, 58, BALLS[i][0], stroke=8)
            text(cv, cfg.get("cta", "Tumhara colour jeeta? Comment karo!"), 540, 1300, 52, (255, 255, 255), stroke=8)
            # subscribe button (on-video CTA)
            cv.drawRRect(skia.RRect.MakeRectXY(skia.Rect(250, 1390, 830, 1500), 28, 28), skia.Paint(Color=C((230, 30, 40)), AntiAlias=True))
            text(cv, "SUBSCRIBE", 540, 1466, 64, (255, 255, 255), stroke=0)
            text(cv, cfg.get("sub_line", "Roz nayi race!"), 540, 1570, 46, (255, 230, 80), stroke=7)
        # series badge + handle (consistent branding on every frame)
        if cfg.get("series") and (t < COUNT or n >= len(tl) - end_hold):
            text(cv, cfg["series"], 540, 250, 40, (180, 200, 255), stroke=6)
        text(cv, "@bouncebhaiofficial", 540, 1880, 34, (200, 200, 220), stroke=5)
        if n == 0:
            first_img = surf.makeImageSnapshot()
        elif first_img is not None and n >= len(tl) - fade:
            a = (n - (len(tl) - fade) + 1) / fade
            cv.drawImage(first_img, 0, 0, skia.SamplingOptions(), skia.Paint(Alphaf=a))
        img = surf.makeImageSnapshot()
        img.save(f"{tmp}/f{n:05d}.jpg", skia.kJPEG, 92)
        seq.append(t)
    return seq, lead_changes, photo

# ---------------- audio ----------------
def tone(sr, f, dur, decay, kind="sine"):
    tt = np.arange(int(dur * sr)) / sr
    w = np.sin(2 * np.pi * f * tt) if kind == "sine" else np.sign(np.sin(2 * np.pi * f * tt)) * 0.5
    return w * np.exp(-tt * decay)

def audio(events, seq, lead_changes, path):
    sr = 44100; n = int(len(seq) / FPS * sr) + sr
    buf = np.zeros(n, np.float32)
    # map sim time -> output time (first occurrence)
    first_out = {}
    for idx, t in enumerate(seq):
        first_out.setdefault(round(t * FPS), idx / FPS)
    def at(t):
        return first_out.get(round(t * FPS), None)
    def add(s, t0, g):
        k = int(t0 * sr)
        if k >= n: return
        m = min(len(s), n - k); buf[k:k + m] += g * s[:m].astype(np.float32)
    # beat: kick + hat, 128 bpm after GO
    bpm = 150 if INTENSE else 128; step = 60 / bpm
    T_end = len(seq) / FPS
    t0 = at(COUNT) or COUNT
    kk = tone(sr, 55, 0.25, 18); _c = tone(sr, 110, 0.08, 40); kk[:len(_c)] += _c * 0.5
    hat = np.random.RandomState(1).randn(int(0.04 * sr)) * np.exp(-np.arange(int(0.04 * sr)) / sr * 90)
    bt = t0
    while bt < T_end - 2.3:
        add(kk, bt, 0.55); add(hat, bt + step / 2, 0.10); bt += step
    bass = [55, 55, 65.4, 49]
    for q, bt in enumerate(np.arange(t0, T_end - 2.3, step * 4)):
        add(tone(sr, bass[q % 4], step * 4, 1.2, "sq"), bt, 0.10)
    for s in range(3):
        add(tone(sr, 660, 0.18, 10), s, 0.35)
    add(tone(sr, 1320, 0.4, 6), COUNT, 0.4)
    pitch = [523.3, 659.3, 784.0]
    last = {}
    for (te, kind, i, d) in events:
        o = at(te)
        if o is None: continue
        if kind in ("wall", "kick", "clash"):
            if o - last.get(i, -1) < 0.06: continue
            last[i] = o; add(tone(sr, pitch[i] * (1.5 if kind == "kick" else 1), 0.14, 24), o, 0.20)
        elif kind == "bump":
            sw = np.arange(int(0.25 * sr)) / sr
            add(np.sin(2 * np.pi * (300 * sw + 900 * sw ** 2)) * np.exp(-sw * 10), o, 0.30)
        elif kind == "pad":
            sw = np.arange(int(0.35 * sr)) / sr
            add(np.sin(2 * np.pi * (200 * sw + 1400 * sw ** 2)) * np.exp(-sw * 7), o, 0.28)
        elif kind == "finish":
            for h, fq in enumerate([523, 659, 784, 1046] if d == 1 else [392, 494]):
                add(tone(sr, fq, 0.5, 5), o + h * 0.09, 0.30 if d == 1 else 0.18)
    for lc in lead_changes:
        sw = np.arange(int(0.4 * sr)) / sr
        add(np.random.RandomState(2).randn(len(sw)) * np.exp(-((sw - 0.2) / 0.1) ** 2), lc, 0.12)
    buf = buf / (np.abs(buf).max() or 1) * 0.85
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((buf * 32767).astype(np.int16).tobytes())

if __name__ == "__main__":
    cfg = json.load(open(sys.argv[1]))
    INTENSE = bool(cfg.get("intense"))
    s0 = cfg.get("seed", random.randint(1, 10 ** 6))
    best, t_start = None, time.time()
    for seed in range(s0, s0 + cfg.get("tries", 40)):
        c, fr, ev, fin = simulate(seed)
        sc = score(c, fr, fin)
        if sc == -1: continue
        print("seed", seed, round(sc[0], 1), sc[1], flush=True)
        if best is None or sc[0] > best[0]:
            best = (sc[0], seed, c, fr, ev, fin, sc[1])
        b = best[6]
        if b["changes"] >= (8 if INTENSE else 4) and b["gap"] < (0.5 if INTENSE else 0.8) and 22 <= b["dur"] <= 34 and b["spread"] <= 5 and b["win"] >= 10: break
        if time.time() - t_start > cfg.get("budget", 150) and best: break
    if not best: raise SystemExit("no race found")
    _, seed, c, fr, ev, fin, info = best
    print("using seed", seed, info, c["kinds"], flush=True)
    tmp = cfg["out"] + ".frames"; subprocess.run(["rm", "-rf", tmp])
    seq, lcs, photo = render(cfg, c, fr, ev, fin, tmp)
    wav = cfg["out"] + ".wav"; audio(ev, seq, lcs, wav)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", f"{tmp}/f%05d.jpg", "-i", wav,
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "19", "-preset", "medium", "-c:a", "aac", "-b:a", "160k",
                    "-shortest", cfg["out"]], check=True)
    subprocess.run(["rm", "-rf", tmp, wav])
    json.dump({"seed": seed, **info, "photo": photo, "lead_changes": len(lcs)}, open(cfg["out"] + ".json", "w"))
    print("done", cfg["out"], "photo" if photo else "", len(lcs), "lead changes")
