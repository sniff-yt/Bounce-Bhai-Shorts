#!/usr/bin/env python3
"""Bounce Bhai: 3-ball parkour race (pure code, no AI).
Balls bounce in a circle -> drop down a pipe -> race a random parkour course.
Races are picked for lead changes, a tight pack, ball-vs-ball fights and a photo finish; rendered at 60 fps in an
anime / cinematic look (cel-shaded balls, glow trails, bloom, grade, grain, tracking + push-in camera, impact frames
with hit-stop on the biggest hits and the finish, slow-mo photo-finish replay). On-screen text is kept minimal:
hook at the start, a small 1-2-3 tag, at most a rare OVERTAKE!, and the end card.
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
JELLY = False             # "jelly" races: soft-body look (balls squash and wobble on every hit), bouncier walls
NAMES = [b[1] for b in BALLS]   # labels on screen; cfg "names" swaps in commenter names (fan-named balls)

# ---------------- course ----------------
def make_course(rnd):
    segs, bars, sliders, bumpers, pads, glass, sand = [], [], [], [], [], [], []
    n = 90
    a0, a1 = 90 + GAP / 2, 450 - GAP / 2
    pts = [(CX + CR * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
            CY + CR * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]
    segs += list(zip(pts[:-1], pts[1:]))
    gx = CR * math.sin(math.radians(GAP / 2))
    y = CY + CR * math.cos(math.radians(GAP / 2))
    segs += [((CX - gx, y), (CX - gx, 1000)), ((CX + gx, y), (CX + gx, 1000))]
    y = 1000
    pool = ["zigzag", "spinners", "bumpers", "slider", "funnel", "pads", "glass", "sand"]
    kinds = []
    while len(kinds) < rnd.randint(6, 8):   # tight ~22-34 s races (Shorts retention; 10-12 sections made 35-45 s)
        k = rnd.choice(pool)
        if k in ("glass", "sand") and kinds.count(k) >= (2 if k == "glass" else 1): continue
        if not kinds or k != kinds[-1]: kinds.append(k)
    if not any(k in ("glass", "sand") for k in kinds):     # every race gets a new-physics section (variety)
        kinds.insert(rnd.randint(1, len(kinds) - 1), rnd.choice(["glass", "glass", "sand"]))
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
        elif k == "glass":
            # breakable glass floor (two panes): balls pile on it until enough hits shatter a pane
            gy = y + 190
            glass.append(dict(seg=(XL, gy, 540, gy), hp=rnd.uniform(1900, 2600)))
            glass.append(dict(seg=(540, gy, XR, gy), hp=rnd.uniform(1900, 2600)))
            y += 400
        elif k == "sand":
            sand.append((XL, y + 60, XR, y + 380))          # sand pit: heavy drag, balls plough through it
            y += 440
        elif k == "pads":
            pads.append((XL, y + 220, 470, y + 300))   # joined to the walls: no slot for a ball to wedge into
            pads.append((610, y + 300, XR, y + 220))
            segs.append(((470, y + 300), (470, y + 330)))
            y += 400
    y += 420                 # open sprint straight before the line: chasers can close in -> photo finishes
    finish = y
    segs += [((XL, 1000), (XL, finish + 400)), ((XR, 1000), (XR, finish + 400)), ((XL, finish + 400), (XR, finish + 400))]
    return dict(segs=segs, bars=bars, sliders=sliders, bumpers=bumpers, pads=pads, glass=glass, sand=sand,
                finish=finish, kinds=kinds)

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
    best_y = [0.0] * 3; stall = [0.0] * 3; noprog = [0.0] * 3
    chase = [False] * 3
    mids = []
    rad = BR + T / 2
    last_clash = {}
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
                    elif behind > 220:
                        # rubber band (keeps the pack tight so they actually fight), stronger in the last third
                        late = 1.6 if p[1] > 1000 + (c["finish"] - 1000) * 0.62 else 1.0
                        v[1] += G * min(0.95, (behind - 220) / 1300 * late) * dt
                    if p[1] > c["finish"] - 900 and 0 < behind < 700:
                        v[1] += G * 0.55 * dt; chase[i] = True   # final-stretch surge: the chaser attacks the line
                if ts > COUNT + 1.2 and p[1] < CY + CR + 20 and math.hypot(p[0] - CX, p[1] - CY) < CR:
                    # still circling in the arena: settle toward the exit gap (it is only ~1 ball wide)
                    v[0] += (CX - p[0]) * 6.0 * dt; v[0] *= 1 - 2.0 * dt; v[1] += 700 * dt
                if ts > COUNT and i not in finish and noprog[i] > 2.5:
                    v[1] += G * min(1.0, (noprog[i] - 2.5) / 2) * dt     # bouncing in place too long: let it drop through
                if ts > COUNT + 1 and i not in finish and p[1] > 1000:
                    if i == lead_i and len(racing_y) >= 2:
                        lead = p[1] - sorted(racing_y)[-2]
                        if lead > 260 and v[1] > 0:      # runaway leader feels the air: lets the pack catch up
                            k = min(0.9, (lead - 260) / 800) * 1.4 * dt
                            v[0] *= 1 - k * 0.3; v[1] *= 1 - k
                    # herding: balls running side by side drift into each other -> shoving, blocking, overtakes
                    for j in range(3):
                        if j == i or j in finish: continue
                        dy = abs(P[j][1] - p[1]); dx = P[j][0] - p[0]
                        if dy < 260 and 2 * BR < abs(dx) < 420:
                            v[0] += (1 if dx > 0 else -1) * 520 * (1 - dy / 260) * dt
                p[0] += v[0] * dt; p[1] += v[1] * dt
                near = [sg for sg in statics if min(sg[1], sg[3]) - 80 < p[1] < max(sg[1], sg[3]) + 80]
                for sg in near:
                    hit = collide_seg(p, v, *sg, rad, 0.8 if JELLY else 0.72)
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
                        # bumpers fling sideways/down at full force but only half as hard back UP the course:
                        # full-strength upward kicks trapped balls pinballing for 10+ s (dead air, huge gaps)
                        v[0] += nx * KICK; v[1] += ny * KICK * (0.45 if ny < 0 else 1.0)
                        events.append((ts, "bump", i, (bx, by)))
                for (x1, y1, x2, y2) in c["sand"]:
                    if x1 < p[0] < x2 and y1 < p[1] < y2:       # sand: strong drag, a little sideways wobble
                        k = 5.0 * dt; v[0] *= 1 - k; v[1] *= 1 - k
                        v[0] += rnd.uniform(-1, 1) * 900 * dt
                for gl in c["glass"]:
                    if gl.get("broke") is not None: continue
                    x1, y1, x2, y2 = gl["seg"]
                    if abs(p[1] - y1) > rad + 4: continue
                    hit = collide_seg(p, v, x1, y1, x2, y2, rad, 0.55)
                    if hit > 0 and ts > COUNT:
                        gl.setdefault("first", ts)
                        if hit > 120:
                            gl["dmg"] = gl.get("dmg", 0) + hit; gl.setdefault("hits", []).append(ts)
                        # shatters on enough damage, or after ~1.8 s of sitting on it (no stuck races)
                        if gl.get("dmg", 0) > gl["hp"] or ts - gl["first"] > 1.8:
                            gl["broke"] = ts; v[1] += 250
                            events.append((ts, "glass", i, ((x1 + x2) / 2, y1)))
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
                            sh = 1.0 + (0.25 if ts > COUNT else 0.0)   # a little extra shove: hits push the other ball off line
                            V[i][0] += rv * nx * sh; V[i][1] += rv * ny * sh
                            V[j][0] -= rv * nx * sh; V[j][1] -= rv * ny * sh
                            if -rv > 260 and ts - last_clash.get((i, j), -9) > 0.08:
                                last_clash[(i, j)] = ts
                                events.append((ts, "clash", i, (j, (P[i][0] + P[j][0]) / 2, (P[i][1] + P[j][1]) / 2, -rv)))
            for i in range(3):
                sp = math.hypot(*V[i]); vm = VMAX * (1.12 if chase[i] else 1.0); chase[i] = False
                if sp > vm: V[i][0] *= vm / sp; V[i][1] *= vm / sp
            if s == sub // 2 - 1:
                mids.append([tuple(q) for q in P])     # half-frame positions -> true 60 fps output
        for i in range(3):
            sp = math.hypot(*V[i])
            slow[i] = slow[i] + 1 / FPS if (sp < 60 and t > COUNT and i not in finish) else 0
            if slow[i] > 1.2:
                V[i][0] += rnd.choice([-1, 1]) * 500; V[i][1] -= 600; slow[i] = 0
            # jitter-stuck (resting on a ledge/spinner but still moving): no downward progress for 1.5 s -> kick
            if P[i][1] > best_y[i] + 25: best_y[i] = P[i][1]; stall[i] = 0; noprog[i] = 0
            elif t > COUNT and i not in finish:
                stall[i] += 1 / FPS; noprog[i] += 1 / FPS
                if stall[i] > 1.5:
                    V[i][0] += (1 if P[i][0] < CX else -1) * 650; V[i][1] -= 250; stall[i] = 0
            if i not in finish and P[i][1] > c["finish"]:
                finish[i] = t; events.append((t, "finish", i, len(finish)))
        frames.append([tuple(p) for p in P])
        if len(finish) == 3 and t > max(finish.values()) + 0.5:
            break
        if t > COUNT + 8 and len(finish) == 0 and max(p[1] for p in P) < 1100:
            break  # stuck in arena
    c["mids"] = mids
    return c, frames, events, finish

# ---------------- race analysis ----------------
REPLAY_SPEED = 0.4        # photo-finish replay plays at 0.4x (interpolated, not duplicated frames)
END_HOLD = 2.4            # end card seconds (last 0.5 s cross-fades into frame 1 for the loop)
MARGIN = 14               # px a ball must be ahead before the displayed order flips (no flicker)

def rank_track(frames, finish):
    """Displayed order per frame, with hysteresis so side-by-side balls don't flicker the leaderboard."""
    out, cur = [], [0, 1, 2]
    for k, fr in enumerate(frames):
        t = k / FPS
        def better(b, a):
            fb, fa = b in finish and finish[b] <= t, a in finish and finish[a] <= t
            if fb: return (not fa) or finish[b] < finish[a]
            if fa: return False
            return fr[b][1] > fr[a][1] + MARGIN
        changed = True
        while changed:
            changed = False
            for p in range(2):
                if better(cur[p + 1], cur[p]):
                    cur[p], cur[p + 1] = cur[p + 1], cur[p]; changed = True
        out.append(tuple(cur))
    return out

def plan(frames, finish):
    """Live footage until just after 2nd place crosses, then (if close) a slow-mo replay of the finish."""
    order = sorted(finish, key=finish.get)
    f1, f2 = finish[order[0]], finish[order[1]]
    k_cut = min(len(frames) - 1, int((f2 + 0.7) * FPS))
    photo = (f2 - f1) < 0.7
    rep = []
    if photo:
        a, b = max(COUNT, f1 - 0.9) * FPS, min(len(frames) - 1.001, (f2 + 0.25) * FPS)
        x = a
        while x <= b: rep.append(x); x += REPLAY_SPEED
    return k_cut, rep, photo

def score(c, frames, events, finish):
    if len(finish) < 3: return -1
    order = sorted(finish, key=finish.get)
    w = order[0]
    f1 = finish[w]
    gap = finish[order[1]] - f1
    win = f1 - COUNT
    spread = finish[order[2]] - f1
    k_cut, rep, photo = plan(frames, finish)
    out = (k_cut + 1 + len(rep)) / FPS + END_HOLD + 0.8     # + up to ~0.8 s of impact frames / hit-stops
    if out > 36 or win < 9: return -1
    ords = rank_track(frames, finish)
    changes, last = 0, None
    for k in range(int((COUNT + 1) * FPS), int(f1 * FPS) + 1):
        if last is not None and ords[k][0] != last: changes += 1
        last = ords[k][0]
    ks = range(int((COUNT + 2) * FPS), int(f1 * FPS), 3)
    def _tight(fr):
        ys = sorted((p[1] for p in fr), reverse=True)
        return (ys[0] - ys[1] < 260) * 0.7 + (ys[0] - ys[2] < 600) * 0.3
    tight = sum(_tight(frames[k]) for k in ks) / max(1, len(ks))
    clashes = sum(1 for e in events if e[1] == "clash" and COUNT < e[0] < f1)
    comeback = ords[max(0, int((f1 - 4) * FPS))].index(w)   # winner was 2nd/3rd four seconds before the line
    s = min(changes, 12) * 1.4 + tight * 14 + min(clashes, 30) * 0.3 + comeback * 3.5
    s += 12 if gap < 0.12 else 9 if gap < 0.3 else 5 if gap < 0.7 else -gap * 3
    s += 8 if 22 <= out <= 34 else -abs(out - 28) * 2
    s -= max(0, spread - 6) * 2
    return s, dict(dur=round(out, 1), gap=round(gap, 2), changes=changes, win=round(win, 1), spread=round(spread, 1),
                   tight=round(tight, 2), clashes=clashes, comeback=comeback)

# ---------------- look: anime / cinematic ----------------
OUT_FPS = 60              # rendered at 60 fps from half-frame physics samples (not interpolated duplicates)
PAL = [(255, 46, 92), (36, 150, 255), (40, 232, 120)]   # vivid anime palette (RED, BLUE, GREEN)
IMPACT_MIN = 850          # ball-vs-ball closing speed (px/s) that can earn an anime impact frame

def C(rgb, a=255): return skia.Color(int(rgb[0]), int(rgb[1]), int(rgb[2]), int(max(0, min(255, a))))
def lighten(col, d): return tuple(min(255, cc + d) for cc in col)
def darken(col, f): return tuple(cc * f for cc in col)

TF = skia.Typeface.MakeFromFile(FONT)
def text(cv, s, x, y, size, rgb=(255, 255, 255), center=True, stroke=8, alpha=255):
    f = skia.Font(TF, size); f.setSubpixel(True); f.setEdging(skia.Font.Edging.kSubpixelAntiAlias)
    w = f.measureText(s)
    if center and w > 940:                 # never let text run off the screen
        size = size * 940 / w; f = skia.Font(TF, size); w = f.measureText(s)
    x0 = x - w / 2 if center else x
    if stroke:
        cv.drawString(s, x0, y, f, skia.Paint(Color=C((0, 0, 0), alpha), AntiAlias=True, Style=skia.Paint.kStroke_Style, StrokeWidth=stroke, StrokeJoin=skia.Paint.kRound_Join))
    cv.drawString(s, x0, y, f, skia.Paint(Color=C(rgb, alpha), AntiAlias=True))

def _mat_grade(contrast=1.16, sat=1.22, lift=-0.015):
    lr, lg, lb = 0.2126, 0.7152, 0.0722
    S = [[lr * (1 - sat) + sat, lg * (1 - sat), lb * (1 - sat)],
         [lr * (1 - sat), lg * (1 - sat) + sat, lb * (1 - sat)],
         [lr * (1 - sat), lg * (1 - sat), lb * (1 - sat) + sat]]
    off = 0.5 * (1 - contrast) + lift
    m = []
    for r in range(3): m += [S[r][0] * contrast, S[r][1] * contrast, S[r][2] * contrast, 0, off]
    return m + [0, 0, 0, 1, 0]
GRADE = skia.ColorFilters.Matrix(_mat_grade())
BRIGHT = skia.ColorFilters.Matrix([2.2, 0, 0, 0, -1.25, 0, 2.2, 0, 0, -1.25, 0, 0, 2.2, 0, -1.25, 0, 0, 0, 1, 0])  # bloom bright-pass
INV = skia.ColorFilters.Matrix([-0.9, -1.75, -0.35, 0, 1.6] * 3 + [0, 0, 0, 1, 0])   # inverted high-contrast mono
LIN = skia.SamplingOptions(skia.FilterMode.kLinear, skia.MipmapMode.kNone)

def pick_impacts(events, finish):
    """The strongest ball-vs-ball hits only (max 2, >= 5 s apart, not right at the start or the line)."""
    f1 = min(finish.values())
    cands = sorted(((d[3], te, i, d) for (te, kind, i, d) in events
                    if kind == "clash" and d[3] >= IMPACT_MIN and COUNT + 3.0 < te < f1 - 1.0), reverse=True)
    out = []
    for st, te, i, d in cands:
        if all(abs(te - o[0]) >= 5 for o in out): out.append((te, (d[1], d[2]), st))
        if len(out) == 2: break
    return sorted(out)

def burst(cv, sx, sy, seed, rgb, alpha, r0=110, count=56):
    """Radial burst lines (thin wedges) around the hit point, like an anime impact panel."""
    rr = random.Random(seed)
    path = skia.Path()
    for _ in range(count):
        a = rr.uniform(0, 2 * math.pi); wdt = rr.uniform(0.006, 0.03); r1 = r0 + rr.uniform(0, 120)
        path.moveTo(sx + math.cos(a) * r1, sy + math.sin(a) * r1)
        path.lineTo(sx + math.cos(a - wdt) * 2600, sy + math.sin(a - wdt) * 2600)
        path.lineTo(sx + math.cos(a + wdt) * 2600, sy + math.sin(a + wdt) * 2600)
        path.close()
    cv.drawPath(path, skia.Paint(Color=C(rgb, alpha), AntiAlias=True))

class Look:
    """Per-process resources: surfaces, film grain, defocused bokeh backdrop, vignette."""
    def __init__(self, course_h):
        self.surf = skia.Surface(W, H); self.cv = self.surf.getCanvas()
        self.small = skia.Surface(W // 4, H // 4); self.small2 = skia.Surface(W // 4, H // 4)
        R = np.random.RandomState(11)
        self.grain = []
        for _ in range(3):
            g = R.randn(H, W).astype(np.float32)
            a = np.clip(np.abs(g) * 5.5, 0, 14).astype(np.uint8)
            arr = np.zeros((H, W, 4), np.uint8)
            arr[..., 3] = a
            arr[..., 0] = arr[..., 1] = arr[..., 2] = np.where(g > 0, a, 0)   # premultiplied white / black specks
            self.grain.append(skia.Image.fromarray(arr, colorType=skia.kRGBA_8888_ColorType, alphaType=skia.kPremul_AlphaType))
        # defocused backdrop: soft bokeh discs (shallow depth of field), scrolls at half speed (parallax)
        self.bh = 2600
        bs = skia.Surface(W, self.bh); bc = bs.getCanvas(); bc.clear(C((0, 0, 0), 0))
        rr = random.Random(3)
        for _ in range(46):
            col = rr.choice([(150, 70, 255), (255, 60, 170), (40, 160, 255), (255, 170, 60)])
            x, y, r = rr.uniform(0, W), rr.uniform(0, self.bh), rr.uniform(18, 70)
            for dy in (-self.bh, 0, self.bh):
                bc.drawCircle(x, y + dy, r, skia.Paint(Color=C(col, rr.uniform(35, 75)), AntiAlias=True,
                                                       MaskFilter=skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, r * 0.45)))
        self.bokeh = bs.makeImageSnapshot()
        self.vig = skia.Paint(Shader=skia.GradientShader.MakeRadial((540, 900), 1250, [C((0, 0, 0), 0), C((0, 0, 0), 0), C((0, 0, 0), 175)], [0.0, 0.55, 1.0]))
        self.bg = skia.Paint(Shader=skia.GradientShader.MakeLinear([(0, 0), (0, H)], [C((30, 10, 58)), C((4, 16, 40))]))

def ball(cv, x, y, col, vx, vy, lead, wob=None):
    """Cel-shaded anime ball: bold outline, hard shadow crescent, rim light, specular highlight, speed smear.
    wob = (age, strength) of the last hit: jelly balls squash and wobble (damped spring)."""
    sp = math.hypot(vx, vy)
    cv.save(); cv.translate(x, y)
    if wob is not None:
        age, st_ = wob
        a_ = st_ * math.exp(-age * 7) * math.cos(age * 34)
        cv.scale(1 + a_, 1 - a_ * 0.9)
    elif sp > 700:       # squash & stretch along the motion = motion smear
        ang = math.degrees(math.atan2(vy, vx)); st = min(0.28, (sp - 700) / 6000)
        cv.rotate(ang); cv.scale(1 + st, 1 - st * 0.55); cv.rotate(-ang)
    cv.drawCircle(0, 0, BR + 16, skia.Paint(Color=C(col, 150), AntiAlias=True, MaskFilter=skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, 16)))
    if lead:
        cv.drawCircle(0, 0, BR + 12, skia.Paint(Color=C((255, 214, 60)), AntiAlias=True, Style=skia.Paint.kStroke_Style, StrokeWidth=6))
    cv.drawCircle(0, 0, BR + 4.5, skia.Paint(Color=C((8, 6, 18)), AntiAlias=True))           # bold ink outline
    cv.save(); cv.clipPath(skia.Path().addCircle(0, 0, BR), skia.ClipOp.kIntersect, True)
    cv.drawCircle(0, 0, BR, skia.Paint(Color=C(darken(col, 0.58)), AntiAlias=True))        # shadow tone
    cv.drawCircle(-BR * 0.2, -BR * 0.22, BR * 0.93, skia.Paint(Color=C(col), AntiAlias=True))  # lit tone (hard cel edge)
    if JELLY:   # jelly: translucent glossy core + inner bubbles
        cv.drawCircle(BR * 0.1, BR * 0.15, BR * 0.6, skia.Paint(Color=C(lighten(col, 90), 120), AntiAlias=True, MaskFilter=skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, 8)))
        for (bx_, by_, br_) in ((0.35, 0.3, 0.12), (-0.1, 0.45, 0.08), (0.45, -0.05, 0.07)):
            cv.drawCircle(BR * bx_, BR * by_, BR * br_, skia.Paint(Color=C((255, 255, 255), 150), AntiAlias=True, Style=skia.Paint.kStroke_Style, StrokeWidth=2))
    cv.drawArc(skia.Rect(-BR + 3, -BR + 3, BR - 3, BR - 3), 15, 95, False,
               skia.Paint(Color=C(lighten(col, 150), 230), AntiAlias=True, Style=skia.Paint.kStroke_Style, StrokeWidth=4, StrokeCap=skia.Paint.kRound_Cap))  # rim light
    cv.restore()
    cv.drawOval(skia.Rect(-BR * 0.62, -BR * 0.7, -BR * 0.08, -BR * 0.32), skia.Paint(Color=C((255, 255, 255), 235), AntiAlias=True))
    cv.drawCircle(BR * 0.05, -BR * 0.5, BR * 0.09, skia.Paint(Color=C((255, 255, 255), 220), AntiAlias=True))
    cv.restore()

# ---------------- timeline + camera (state pass, cheap) ----------------
def build(cfg, c, frames, events, finish):
    F = [frames[0]]
    for f in range(1, len(frames)): F += [c["mids"][f], frames[f]]
    k_cut, rep30, photo = plan(frames, finish)
    ords = rank_track(frames, finish)
    order_final = sorted(finish, key=finish.get)
    f1 = finish[order_final[0]]; win_i = order_final[0]
    kc = 2 * k_cut
    rep = []
    if rep30:
        x = 2 * rep30[0]
        while x <= min(len(F) - 1.001, 2 * rep30[-1]): rep.append(x); x += REPLAY_SPEED   # 60 fps units: 0.4x slow motion
    hits = pick_impacts(events, finish)
    hit_at = {min(kc, int(te * OUT_FPS) + 1): (pt, 4, 0.9 + 0.1 * min(1, st / 1500)) for (te, pt, st) in hits}
    kf = int(math.ceil(f1 * OUT_FPS))
    if kf <= kc: hit_at[kf] = (None, 4, 1.0)
    def fx_seq(kind, tk, spec):
        pt, nflash, power = spec
        return [(kind, tk, ("flash", q, pt, power)) for q in range(nflash)] + [(kind, tk, ("freeze", q, pt, power)) for q in range(8)]
    shots = []
    for k in range(kc + 1):
        if k in hit_at: shots += fx_seq("live", float(k), hit_at[k])
        shots.append(("live", float(k), None))
    done = False
    for x in rep:
        if not done and x / OUT_FPS >= f1:
            done = True; shots += fx_seq("rep", x, (None, 6, 1.0))
        shots.append(("rep", x, None))
    rep_start = next((q for q, s_ in enumerate(shots) if s_[0] == "rep"), None)
    n_end = len(shots)
    shots += [("end", float(kc), None)] * int(END_HOLD * OUT_FPS)
    def P_at(tk):
        k0 = max(0, min(int(tk), len(F) - 1)); k1 = min(k0 + 1, len(F) - 1); a = max(0.0, tk - k0)
        return [(F[k0][i][0] * (1 - a) + F[k1][i][0] * a, F[k0][i][1] * (1 - a) + F[k1][i][1] * a) for i in range(3)]
    # rare pop-up only on a big overtake
    pops, lead_changes, held_from, last_pop = [], [], 0.0, -99
    for k in range(int(COUNT * FPS), k_cut + 1):
        t = k / FPS
        if ords[k][0] != ords[k - 1][0]:
            if t < f1 + 0.05: lead_changes.append(t)
            if t > COUNT + 4 and t < f1 - 0.3 and t - held_from >= 3.0 and t - last_pop >= 8 and len(pops) < 1:   # at most ONE pop-up per race
                pops.append((t, ords[k][0])); last_pop = t
            held_from = t
    impact_t = [te for (te, pt, st) in hits] + [f1]
    shake_ev = [(te, 1.0 if kind == "clash" else 0.6) for (te, kind, i, d) in events
                if kind in ("bump", "pad", "glass") or (kind == "clash" and d[3] > 450 and te > COUNT)]
    fy = c["finish"]
    # camera pass: tracking + push-ins on the leading pack, close-up push during the photo-finish replay
    cam, slots = [], []
    B_order = order_final
    cx, cy, z = W / 2, H / 2, 1.0; rcx = rcy = None; rz = 1.5
    slot = [70.0 + r * 58 for r in range(3)]
    slot_y = {ords[0][r]: slot[r] for r in range(3)}
    a_pos, a_z = 0.07, 0.035
    rep_i = 0
    for n, (kind, tk, fx) in enumerate(shots):
        t = tk / OUT_FPS; P = P_at(tk)
        racing = [i for i in range(3) if i not in finish or finish[i] > t]
        top2 = sorted((racing or range(3)) if kind == "live" else range(3), key=lambda i: -P[i][1])[:2]
        if kind == "rep": top2 = B_order[:2]          # replay stays on the winner and the runner-up
        ox = oy = 0.0
        if kind == "live" and fx is None:
            ys = [P[i][1] for i in top2]
            pack = ys[0] * 0.62 + ys[-1] * 0.38
            close = len(ys) > 1 and ys[0] - ys[1] < 260
            zt = 1.0
            if t > COUNT + 0.8 and close: zt = 1.24 if fy - ys[0] < 900 else 1.14
            z += (zt - z) * a_z
            xt = sum(P[i][0] for i in top2) / len(top2)
            xt = min(max(xt, W / (2 * z)), W - W / (2 * z))
            cx += (xt - cx) * a_pos
            cx = min(max(cx, W / (2 * z)), W - W / (2 * z))
            yt = pack + (H / 2 - 820) / z
            yt = max(H / (2 * z), min(yt, fy + 480 - H / (2 * z)))
            if t < COUNT: yt, z, cx = H / 2, 1.0, W / 2
            cy += (yt - cy) * a_pos
            sh = 0.0
            for te, g in shake_ev:
                if 0 <= t - te < 0.2: sh = max(sh, (13 if INTENSE else 9) * g * (1 - (t - te) / 0.2))
            for te in impact_t:
                if 0 <= t - te < 0.3: sh = max(sh, 18 * (1 - (t - te) / 0.3))
            ox, oy = math.sin(n * 1.9) * sh, math.cos(n * 2.3) * sh
            cam_live = (cx, cy, z)
        elif kind == "live":
            cam_live = (cx, cy, z)
        if kind == "rep":
            tx = sum(P[i][0] for i in top2) / len(top2); ty = sum(P[i][1] for i in top2) / len(top2) - 40
            if fx is None:
                rz = 1.5 + 0.38 * min(1, rep_i / max(1, len(rep) - 1)); rep_i += 1     # slow push-in
            tx = min(max(tx, W / (2 * rz)), W - W / (2 * rz)); ty = min(ty, fy + 400 - H / (2 * rz) + 40)
            if rcx is None: rcx, rcy = tx, ty
            if fx is None: rcx += (tx - rcx) * 0.12; rcy += (ty - rcy) * 0.12
            if fx is None and 0 <= t - f1 < 0.12:
                sh = 16 * (1 - (t - f1) / 0.12); ox, oy = math.sin(n * 1.9) * sh, math.cos(n * 2.3) * sh
            cam.append((rcx, rcy, rz, ox, oy))
        elif kind == "end":
            cam.append((*cam_end, 0.0, 0.0))
        else:
            cam.append((cx, cy, z, ox, oy))
            if k_cut * 2 == tk: cam_end = (cx, cy, z)
        if kind == "live" and fx is None and t >= COUNT:
            o = ords[min(int(tk / 2), len(ords) - 1)]
            for r_ in range(3): slot_y[o[r_]] += (slot[r_] - slot_y[o[r_]]) * 0.16
        slots.append(dict(slot_y))
    return dict(F=F, shots=shots, cam=cam, slots=slots, ords=ords, pops=pops, lead_changes=lead_changes,
                k_cut=k_cut, kc=kc, rep=rep, rep_start=rep_start, photo=photo, f1=f1, win_i=win_i, order_final=order_final, n_end=n_end, P_at=P_at)

# ---------------- drawing ----------------
_R = {}
def draw_shot(n, look):
    cfg, c, frames, events, finish, B = _R["cfg"], _R["c"], _R["frames"], _R["events"], _R["finish"], _R["B"]
    kind, tk, fx = B["shots"][n]
    cx, cy, z, ox, oy = B["cam"][n]
    P_at = B["P_at"]; P = P_at(tk); t = tk / OUT_FPS
    f1, fy = B["f1"], c["finish"]
    cv, surf = look.cv, look.surf
    live = kind == "live"
    racing = [i for i in range(3) if i not in finish or finish[i] > t]
    blur = lambda r: skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, r)
    vy0, vy1 = cy - H / (2 * z) - 80, cy + H / (2 * z) + 80
    # ---- backdrop: gradient + defocused bokeh with parallax ----
    cv.drawRect(skia.Rect(0, 0, W, H), look.bg)
    off = (cy * 0.45) % look.bh
    cv.drawImage(look.bokeh, 0, -off); cv.drawImage(look.bokeh, 0, look.bh - off)
    cv.save()
    cv.translate(W / 2 + ox, H / 2 + oy); cv.scale(z, z); cv.translate(-cx, -cy)
    # ---- course: ink outline + neon glow + clean core ----
    path = skia.Path()
    for (a, b) in c["segs"]:
        if max(a[1], b[1]) < vy0 or min(a[1], b[1]) > vy1: continue
        path.moveTo(*a); path.lineTo(*b)
    if t < COUNT:
        path.moveTo(CX - 70, CY + CR - 4); path.lineTo(CX + 70, CY + CR - 4)
    rc = skia.Paint.kRound_Cap
    cv.drawPath(path, skia.Paint(Color=C((140, 110, 255), 170), AntiAlias=True, Style=skia.Paint.kStroke_Style, StrokeWidth=T + 26, StrokeCap=rc, MaskFilter=blur(16)))
    cv.drawPath(path, skia.Paint(Color=C((8, 6, 18)), AntiAlias=True, Style=skia.Paint.kStroke_Style, StrokeWidth=T + 9, StrokeCap=rc))
    cv.drawPath(path, skia.Paint(Color=C((236, 240, 255)), AntiAlias=True, Style=skia.Paint.kStroke_Style, StrokeWidth=T, StrokeCap=rc))
    cv.drawPath(path, skia.Paint(Color=C((180, 190, 255)), AntiAlias=True, Style=skia.Paint.kStroke_Style, StrokeWidth=6, StrokeCap=rc))
    for m in moving(c, t):
        col = (255, 60, 190) if m[0] == "bar" else (255, 160, 30)
        cv.drawLine(m[1], m[2], m[3], m[4], skia.Paint(Color=C(col, 170), AntiAlias=True, StrokeWidth=T + 24, StrokeCap=rc, MaskFilter=blur(14)))
        cv.drawLine(m[1], m[2], m[3], m[4], skia.Paint(Color=C((8, 6, 18)), AntiAlias=True, StrokeWidth=T + 9, StrokeCap=rc))
        cv.drawLine(m[1], m[2], m[3], m[4], skia.Paint(Color=C(col), AntiAlias=True, StrokeWidth=T, StrokeCap=rc))
        cv.drawLine(m[1], m[2], m[3], m[4], skia.Paint(Color=C(lighten(col, 120)), AntiAlias=True, StrokeWidth=6, StrokeCap=rc))
        if m[0] == "bar":
            cv.drawCircle(m[5][0], m[5][1], 19, skia.Paint(Color=C((8, 6, 18)), AntiAlias=True))
            cv.drawCircle(m[5][0], m[5][1], 14, skia.Paint(Color=C((255, 255, 255)), AntiAlias=True))
    for (bx, by, br) in c["bumpers"]:
        hot = any(0 <= t - te < 0.25 for te in _R["bump_t"].get((bx, by), []))
        rr = br * (1.12 if hot else 1.0)
        cv.drawCircle(bx, by, rr + 12, skia.Paint(Color=C((0, 230, 255), 235 if hot else 140), AntiAlias=True, MaskFilter=blur(18)))
        cv.drawCircle(bx, by, rr + 5, skia.Paint(Color=C((8, 6, 18)), AntiAlias=True))
        cv.drawCircle(bx, by, rr, skia.Paint(Color=C((255, 255, 255) if hot else (0, 205, 245)), AntiAlias=True))
        cv.drawCircle(bx, by, rr * 0.62, skia.Paint(Color=C((10, 36, 70)), AntiAlias=True))
        cv.drawCircle(bx, by, rr * 0.36, skia.Paint(Color=C((120, 240, 255)), AntiAlias=True, Style=skia.Paint.kStroke_Style, StrokeWidth=6))
    for (x1, y1, x2, y2) in c["pads"]:
        cv.drawLine(x1, y1, x2, y2, skia.Paint(Color=C((90, 255, 120), 160), AntiAlias=True, StrokeWidth=T + 22, StrokeCap=rc, MaskFilter=blur(14)))
        cv.drawLine(x1, y1, x2, y2, skia.Paint(Color=C((8, 6, 18)), AntiAlias=True, StrokeWidth=T + 9, StrokeCap=rc))
        cv.drawLine(x1, y1, x2, y2, skia.Paint(Color=C((110, 255, 130)), AntiAlias=True, StrokeWidth=T, StrokeCap=rc))
    for (x1, y1, x2, y2) in c["sand"]:
        if y2 < vy0 or y1 > vy1: continue
        rr_s = random.Random(int(y1))
        cv.drawRect(skia.Rect(x1, y1, x2, y2), skia.Paint(Shader=skia.GradientShader.MakeLinear(
            [(0, y1), (0, y2)], [C((236, 196, 120), 215), C((176, 128, 64), 235)])))
        for _ in range(140):                                   # grains
            gx, gy = rr_s.uniform(x1, x2), rr_s.uniform(y1, y2)
            cv.drawCircle(gx, gy, rr_s.uniform(1.5, 3.5), skia.Paint(Color=C((120, 84, 40) if rr_s.random() < .5 else (255, 230, 170), 160), AntiAlias=True))
        cv.drawLine(x1, y1, x2, y1, skia.Paint(Color=C((255, 226, 150), 230), AntiAlias=True, StrokeWidth=6))
        if live and not (fx and fx[0] == "flash") and t < f1:
            text(cv, "SAND", 540, y1 - 18, 40, (255, 214, 130), stroke=6, alpha=200)
        for i in range(3):                                     # dust kicked up by balls ploughing through
            if x1 < P[i][0] < x2 and y1 < P[i][1] < y2:
                rd = random.Random(n * 7 + i)
                for _ in range(10):
                    a_ = rd.uniform(math.pi, 2 * math.pi); d_ = rd.uniform(20, 90)
                    cv.drawCircle(P[i][0] + math.cos(a_) * d_, P[i][1] + math.sin(a_) * d_ * 0.6, rd.uniform(3, 7),
                                  skia.Paint(Color=C((250, 220, 160), 170), AntiAlias=True))
    for gl in c["glass"]:
        x1, y1, x2, y2 = gl["seg"]
        if y1 < vy0 or y1 > vy1: continue
        broke = gl.get("broke")
        if broke is None or t < broke:
            nh = sum(1 for h in gl.get("hits", []) if h <= t)
            cv.drawLine(x1, y1, x2, y2, skia.Paint(Color=C((120, 240, 255), 150), AntiAlias=True, StrokeWidth=T + 26, MaskFilter=blur(14)))
            cv.drawLine(x1, y1, x2, y2, skia.Paint(Color=C((190, 248, 255), 150), AntiAlias=True, StrokeWidth=T + 4))
            cv.drawLine(x1, y1 - 6, x2, y2 - 6, skia.Paint(Color=C((255, 255, 255), 230), AntiAlias=True, StrokeWidth=4))
            rc_ = random.Random(int(x1 + y1))
            for q in range(min(nh, 10)):                        # cracks spread with every hit
                cx_ = rc_.uniform(x1 + 40, x2 - 40); L_ = rc_.uniform(40, 120)
                for _ in range(3):
                    a_ = rc_.uniform(-0.6, 0.6)
                    cv.drawLine(cx_, y1 - 12, cx_ + math.cos(a_) * L_ * rc_.choice([-1, 1]), y1 - 12 + math.sin(a_) * 22,
                                skia.Paint(Color=C((255, 255, 255), 235), AntiAlias=True, StrokeWidth=3))
            if live and nh == 0 and not (fx and fx[0] == "flash") and t < f1 and x1 == XL:
                text(cv, "GLASS", 540, y1 - 34, 40, (170, 240, 255), stroke=6, alpha=200)
        elif t - broke < 1.2:                                   # shards fly and fall
            age = t - broke; rs = random.Random(int(x1 * 3 + y1))
            for _ in range(26):
                sx0 = rs.uniform(x1, x2); vx_ = rs.uniform(-260, 260); vy_ = rs.uniform(-420, 80); rot = rs.uniform(-8, 8)
                px_, py_ = sx0 + vx_ * age, y1 + vy_ * age + 1500 * age * age
                sz = rs.uniform(10, 24); a_ = rot * age
                pth_ = skia.Path(); pth_.moveTo(px_ + math.cos(a_) * sz, py_ + math.sin(a_) * sz)
                pth_.lineTo(px_ + math.cos(a_ + 2.3) * sz * .7, py_ + math.sin(a_ + 2.3) * sz * .7)
                pth_.lineTo(px_ + math.cos(a_ + 4.1) * sz * .9, py_ + math.sin(a_ + 4.1) * sz * .9); pth_.close()
                cv.drawPath(pth_, skia.Paint(Color=C((200, 250, 255), 230 * (1 - age / 1.2)), AntiAlias=True))
            if age < 0.12:
                cv.drawCircle((x1 + x2) / 2, y1, 160, skia.Paint(Color=C((220, 250, 255), 200 * (1 - age / 0.12)), AntiAlias=True, MaskFilter=blur(40)))
    if fy - 60 < vy1 and kind != "end":          # nothing from the course shows through the end card
        for q in range(0, 1000 // 40):
            for r2 in range(2):
                cv.drawRect(skia.Rect(XL + q * 40, fy + r2 * 20, XL + q * 40 + 40, fy + r2 * 20 + 20),
                            skia.Paint(Color=C((255, 255, 255) if (q + r2) % 2 else (16, 14, 24))))
        if live and t < f1 and not (fx and fx[0] == "flash"):   # course label only before anyone finishes
            text(cv, "FINISH", 540, fy - 24, 54, (255, 226, 70), stroke=8)
    # ---- sparks ----
    for (te, i, d) in _R["clashes"]:
        age = t - te
        if not (0 <= age < 0.35): continue
        j, mx, my, stren = d
        k_ = min(1.0, stren / 1400); fa = 1 - age / 0.35
        cv.drawCircle(mx, my, 18 + 150 * age * (0.6 + k_), skia.Paint(Color=C((255, 255, 255), 220 * fa), AntiAlias=True, Style=skia.Paint.kStroke_Style, StrokeWidth=6 * fa + 1))
        if age < 0.07:
            cv.drawCircle(mx, my, 46 + 40 * k_, skia.Paint(Color=C((255, 250, 220), 200 * (1 - age / 0.07)), AntiAlias=True, MaskFilter=blur(18)))
        rr_ = random.Random(int(te * 1000) + i * 7)
        for s_ in range(12):
            ang = rr_.uniform(0, 2 * math.pi); spd = rr_.uniform(500, 1300) * (0.6 + k_)
            col = lighten(PAL[i if s_ % 2 else j], 120)
            x0, y0 = mx + math.cos(ang) * spd * age, my + math.sin(ang) * spd * age + 500 * age * age
            L = 30 * fa + 4
            cv.drawLine(x0, y0, x0 - math.cos(ang) * L, y0 - math.sin(ang) * L, skia.Paint(Color=C(col, 255 * fa), AntiAlias=True, StrokeWidth=5, StrokeCap=rc))
    # ---- glowing trails, ball speed lines, cel balls ----
    leader = B["ords"][min(int(tk / 2), len(B["ords"]) - 1)][0]
    hist = [P_at(tk - j * 1.2) for j in range(0, 12)]
    vel = []
    for i in range(3):
        px, py = P_at(tk - 1)[i]
        vel.append(((P[i][0] - px) * OUT_FPS, (P[i][1] - py) * OUT_FPS))
    for i in range(3):
        col = PAL[i]
        pth = skia.Path(); pth.moveTo(*hist[0][i])
        for j in range(1, 12): pth.lineTo(*hist[j][i])
        cv.drawPath(pth, skia.Paint(Color=C(col, 120), AntiAlias=True, Style=skia.Paint.kStroke_Style, StrokeWidth=BR * 1.3, StrokeCap=rc,
                                    StrokeJoin=skia.Paint.kRound_Join, MaskFilter=blur(12)))
        for j in range(1, 12):
            a = 1 - j / 12
            cv.drawLine(*hist[j - 1][i], *hist[j][i], skia.Paint(Color=C(lighten(col, 90), 200 * a), AntiAlias=True, StrokeWidth=2 * BR * 0.55 * a + 2, StrokeCap=rc))
        vx, vy = vel[i]; sp = math.hypot(vx, vy)
        if sp > 1250 and t > COUNT:
            ux, uy = vx / sp, vy / sp; L = min(240, 70 + (sp - 1250) * 0.16)
            for off_ in (-0.75, -0.25, 0.3, 0.8):
                bx_, by_ = P[i][0] - ux * (BR + 14) - uy * off_ * BR, P[i][1] - uy * (BR + 14) + ux * off_ * BR
                ll = L * (0.6 + 0.4 * ((hash((n // 2, i, off_)) % 100) / 100))
                cv.drawLine(bx_, by_, bx_ - ux * ll, by_ - uy * ll, skia.Paint(Color=C((255, 255, 255), min(170, (sp - 1250) * 0.25)), AntiAlias=True, StrokeWidth=3.5, StrokeCap=rc))
    for i in sorted(range(3), key=lambda i: i == leader):
        wob = None
        if JELLY:
            hs = _R["imp"].get(i, [])
            k_ = next((q for q in range(len(hs) - 1, -1, -1) if hs[q][0] <= t), None)
            if k_ is not None and t - hs[k_][0] < 0.8: wob = (t - hs[k_][0], hs[k_][1])
        ball(cv, P[i][0], P[i][1], PAL[i], *vel[i], i == leader and t > COUNT + 0.6 and kind != "end", wob)
    cv.restore()
    # ---- grade (contrast + saturation) and bloom ----
    img = surf.makeImageSnapshot()
    sm = look.small.getCanvas(); sm.clear(C((0, 0, 0)))
    sm.drawImageRect(img, skia.Rect(0, 0, W // 4, H // 4), LIN, skia.Paint(ColorFilter=BRIGHT))
    s2 = look.small2.getCanvas(); s2.clear(C((0, 0, 0)))
    s2.drawImage(look.small.makeImageSnapshot(), 0, 0, LIN, skia.Paint(ImageFilter=skia.ImageFilters.Blur(7, 7)))
    cv.drawImage(img, 0, 0, LIN, skia.Paint(ColorFilter=GRADE))
    cv.drawImageRect(look.small2.makeImageSnapshot(), skia.Rect(0, 0, W, H), LIN, skia.Paint(BlendMode=skia.BlendMode.kScreen, Alphaf=0.75))
    # ---- anime focus lines at screen edges when the leader is flying ----
    if live and fx is None and t > COUNT:
        vx, vy = vel[leader]; sp = math.hypot(vx, vy)
        if sp > 1500:
            rr = random.Random(n // 2); a = min(110, (sp - 1500) * 0.12)
            ux, uy = (vx / sp, vy / sp)
            for _ in range(16):
                x0 = rr.choice([rr.uniform(0, 210), rr.uniform(870, W)]); y0 = rr.uniform(0, H); L = rr.uniform(160, 420)
                cv.drawLine(x0, y0, x0 - ux * L, y0 - uy * L, skia.Paint(Color=C((255, 255, 255), a), AntiAlias=True, StrokeWidth=rr.uniform(2, 5), StrokeCap=rc))
    # ---- impact frame ----
    if fx is not None:
        mode, q, pt, power = fx
        wx, wy = (P[B["win_i"]][0], fy + 10) if pt is None else pt
        sx, sy = (wx - cx) * z + W / 2 + ox, (wy - cy) * z + H / 2 + oy
        if mode == "flash":
            img = surf.makeImageSnapshot()
            if (q // 2) % 2 == 0:     # inverted black/white frame + black burst + white core
                cv.clear(C((255, 255, 255)))
                cv.drawImage(img, 0, 0, LIN, skia.Paint(ColorFilter=INV))
                burst(cv, sx, sy, n // 2, (0, 0, 0), 255)
                cv.drawCircle(sx, sy, 70 * power, skia.Paint(Color=C((0, 0, 0)), AntiAlias=True))
                cv.drawCircle(sx, sy, 46 * power, skia.Paint(Color=C((255, 255, 255)), AntiAlias=True))
            else:                     # blown-out white flash, colour frame showing through, ink burst
                cv.drawRect(skia.Rect(0, 0, W, H), skia.Paint(Color=C((255, 250, 235), 190)))
                burst(cv, sx, sy, n // 2 + 1, (10, 10, 20), 235, r0=140, count=44)
                cv.drawCircle(sx, sy, 95 * power, skia.Paint(Color=C((255, 255, 255)), AntiAlias=True, MaskFilter=blur(22)))
        else:                         # hit-stop: frozen frame, white burst fading out + expanding ring
            fa = 1 - q / 8
            burst(cv, sx, sy, 99, (255, 255, 255), 150 * fa, r0=150 + q * 16, count=36)
            cv.drawCircle(sx, sy, 80 + q * 24, skia.Paint(Color=C((255, 255, 255), 230 * fa), AntiAlias=True, Style=skia.Paint.kStroke_Style, StrokeWidth=10 * fa + 2))
    # ---- vignette + grain ----
    cv.drawRect(skia.Rect(0, 0, W, H), look.vig)
    if live and t > COUNT and t < f1 + 0.1:
        ry = sorted((P[i][1] for i in racing), reverse=True)
        if ry and fy - ry[0] < 800 and (len(ry) < 2 or ry[0] - ry[1] < 260):   # final-stretch red pulse (no text)
            a = int((70 if INTENSE else 45) + 50 * (0.5 + 0.5 * math.sin(n * 0.28)))
            vg = skia.GradientShader.MakeRadial((540, 960), 1150, [C((255, 0, 40), 0), C((255, 0, 40), 0), C((255, 20, 50), a)], [0.0, 0.62, 1.0])
            cv.drawRect(skia.Rect(0, 0, W, H), skia.Paint(Shader=vg))
    cv.drawImage(look.grain[n % 3], 0, 0)
    # ---- HUD: hook at the start, small 1-2-3 tag, one rare pop-up, end card ----
    if live:
        cv.drawRect(skia.Rect(0, 0, W, 300), skia.Paint(Shader=skia.GradientShader.MakeLinear([(0, 0), (0, 300)], [C((0, 0, 0), 170), C((0, 0, 0), 0)])))
        ha = 255 if t < COUNT + 0.3 else max(0, 255 * (1 - (t - COUNT - 0.3) / 0.6))   # hook gone before the tag shows
        if ha > 0:
            text(cv, cfg.get("hook", "KAUN JEETEGA?"), 540, 110, 78, (255, 255, 255), stroke=10, alpha=ha)
            if cfg.get("series"):
                text(cv, cfg["series"], 540, 175, 40, (190, 205, 255), stroke=6, alpha=ha)
        if t < COUNT:
            text(cv, str(int(COUNT) - int(t)), 540, 1500, 260 * (1.3 - (t % 1) * 0.3), (255, 226, 70), stroke=14)
        elif t < COUNT + 0.7:
            text(cv, "GO!", 540, 1500, 260, (90, 240, 120), stroke=14, alpha=255 * min(1, (COUNT + 0.7 - t) / 0.25))
        la = 0 if t < COUNT + 0.9 else min(255, (t - COUNT - 0.9) / 0.4 * 255)
        if la > 0:
            o = B["ords"][min(int(tk / 2), len(B["ords"]) - 1)]; sy_ = B["slots"][n]
            for r_ in range(3):
                i = o[r_]; col, name = PAL[i], NAMES[i]; y0 = sy_[i]
                rect = skia.Rect(28, y0 - 23, max(232, 136 + 19 * len(name)), y0 + 23)
                cv.drawRRect(skia.RRect.MakeRectXY(rect, 23, 23), skia.Paint(Color=C((0, 0, 0), 0.62 * la), AntiAlias=True))
                if r_ == 0:
                    cv.drawRRect(skia.RRect.MakeRectXY(rect, 23, 23), skia.Paint(Color=C((255, 214, 60), la), AntiAlias=True, Style=skia.Paint.kStroke_Style, StrokeWidth=3))
                text(cv, str(r_ + 1), 52, y0 + 12, 32, (255, 214, 60) if r_ == 0 else (230, 230, 240), stroke=0, alpha=la)
                cv.drawCircle(92, y0, 13, skia.Paint(Color=C(col, la), AntiAlias=True))
                text(cv, name, 116, y0 + 12, 32, lighten(col, 40), center=False, stroke=0, alpha=la)
        for (tp, who) in B["pops"]:
            age = t - tp
            if 0 <= age < 0.9:
                s_ = 1.25 - 0.25 * min(1, age / 0.15)
                text(cv, "OVERTAKE!", 540, 400, 84 * s_, lighten(PAL[who], 30), stroke=11, alpha=255 * min(1, (0.9 - age) / 0.3))
        top, bot = 330, 1650
        cv.drawRRect(skia.RRect.MakeRectXY(skia.Rect(1000, top, 1024, bot), 12, 12), skia.Paint(Color=C((255, 255, 255), 50), AntiAlias=True))
        for q in range(2):
            for r2 in range(2):
                cv.drawRect(skia.Rect(1000 + q * 12, bot + 8 + r2 * 12, 1012 + q * 12, bot + 20 + r2 * 12), skia.Paint(Color=C((255, 255, 255) if (q + r2) % 2 else (20, 20, 20))))
        for i in range(3):
            pr = max(0, min(1, (P[i][1] - 900) / (fy - 900)))
            cv.drawCircle(1012, top + (bot - top) * pr, 17, skia.Paint(Color=C(PAL[i]), AntiAlias=True))
    elif kind == "rep":
        cv.drawRRect(skia.RRect.MakeRectXY(skia.Rect(28, 52, 330, 104), 26, 26), skia.Paint(Color=C((0, 0, 0), 170), AntiAlias=True))
        if (n // 24) % 2 == 0:
            cv.drawCircle(58, 78, 11, skia.Paint(Color=C((255, 50, 60)), AntiAlias=True))
        text(cv, "SLOW-MO REPLAY", 80, 90, 32, (255, 255, 255), center=False, stroke=0)
        ri = n - B["rep_start"]
        if 0 <= ri < 8 and fx is None:     # flash cut into the replay
            cv.drawRect(skia.Rect(0, 0, W, H), skia.Paint(Color=C((255, 255, 255), 230 * (1 - ri / 8))))
    else:
        w = B["order_final"][0]
        cv.drawRect(skia.Rect(0, 0, W, H), skia.Paint(Color=C((0, 0, 0), 215)))
        if cfg.get("series"):      # same spot as on frame 1, so the loop cross-fade doesn't double it
            text(cv, cfg["series"], 540, 175, 40, (190, 205, 255), stroke=6)
        wl = f"{NAMES[w]} JEET GAYA!"
        text(cv, wl, 540, 880, min(120, int(1700 / max(1, len(wl)))), PAL[w], stroke=14)
        for r_, i in enumerate(B["order_final"]):
            rl = f"{['1st', '2nd', '3rd'][r_]}  {NAMES[i]}  {finish[i] - COUNT:0.2f}s"
            text(cv, rl, 540, 1010 + r_ * 80, min(58, int(1650 / max(1, len(rl)))), lighten(PAL[i], 20), stroke=8)
        if NAMES != [b[1] for b in BALLS]:
            text(cv, "Comment karo, agli race mein tumhari ball!", 540, 1250, 40, (220, 220, 235), stroke=6)
        cv.drawRRect(skia.RRect.MakeRectXY(skia.Rect(250, 1330, 830, 1440), 28, 28), skia.Paint(Color=C((230, 30, 40)), AntiAlias=True))
        text(cv, "SUBSCRIBE", 540, 1406, 64, (255, 255, 255), stroke=0)
        text(cv, cfg.get("sub_line", "Roz nayi race!"), 540, 1520, 46, (255, 226, 70), stroke=7)
    text(cv, "@bouncebhaiofficial", 540, 1880, 34, (200, 200, 220), stroke=5)

def _render_chunk(args):
    lo, hi, tmp = args
    look = Look(_R["c"]["finish"])
    shots = _R["B"]["shots"]; fade = int(0.5 * OUT_FPS); first = None
    for n in range(lo, hi):
        if n >= len(shots) - fade and first is None:
            draw_shot(0, look); first = look.surf.makeImageSnapshot()
        draw_shot(n, look)
        if n >= len(shots) - fade:      # last 0.5 s cross-fades into frame 1: seamless loop
            a = (n - (len(shots) - fade) + 1) / fade
            look.cv.drawImage(first, 0, 0, LIN, skia.Paint(Alphaf=a))
        look.surf.makeImageSnapshot().save(f"{tmp}/f{n:05d}.jpg", skia.kJPEG, 95)
    return hi - lo

def render(cfg, c, frames, events, finish, tmp, workers=1):
    import multiprocessing as mp
    os.makedirs(tmp, exist_ok=True)
    B = build(cfg, c, frames, events, finish)
    if cfg.get("preview_frames"): B["shots"] = B["shots"][:cfg["preview_frames"]]   # local smoke tests only
    bump_t = {}
    for (te, kind, i, data) in events:
        if kind == "bump": bump_t.setdefault(data, []).append(te)
    imp = {}
    for (te, kind, i, data) in events:   # per-ball hit times + strength for the jelly wobble
        if kind in ("wall", "kick", "bump", "pad", "clash", "glass"):
            stv = data if isinstance(data, (int, float)) else (data[3] if kind == "clash" else 900)
            imp.setdefault(i, []).append((te, min(0.32, 0.08 + stv / 6000)))
            if kind == "clash": imp.setdefault(data[0], []).append((te, min(0.32, 0.08 + data[3] / 6000)))
    for i in imp: imp[i].sort()
    _R.update(cfg=cfg, c=c, frames=frames, events=events, finish=finish, B=B, bump_t=bump_t, imp=imp,
              clashes=[(te, i, d) for (te, kind, i, d) in events if kind == "clash" and d[3] > 300 and te > COUNT])
    N = len(B["shots"]); step = 60
    chunks = [(lo, min(N, lo + step), tmp) for lo in range(0, N, step)]
    if workers > 1:
        with mp.get_context("fork").Pool(workers) as pool: list(pool.imap_unordered(_render_chunk, chunks))
    else:
        for ch in chunks: _render_chunk(ch)
    return B

# ---------------- audio ----------------
SR = 44100
def tone(f, dur, decay, kind="sine", sr=SR):
    tt = np.arange(int(dur * sr)) / sr
    w = np.sin(2 * np.pi * f * tt) if kind == "sine" else np.sign(np.sin(2 * np.pi * f * tt)) * 0.5
    return w * np.exp(-tt * decay)

def lp(x, n): return np.convolve(x, np.ones(n) / n, mode="same")

def audio(events, finish, B, path):
    sr = SR; shots = B["shots"]; N = len(shots); T_end = N / OUT_FPS; n = int(T_end * sr) + sr
    buf = np.zeros(n, np.float32)
    R = np.random.RandomState(7)
    def add(s, t0, g):
        if t0 is None: return
        k = int(t0 * sr)
        if k >= n or k < 0: return
        m = min(len(s), n - k); buf[k:k + m] += g * np.asarray(s[:m], np.float32)
    # sim time -> output time (hit-stops and the replay shift everything after them)
    lt = np.array([tk / OUT_FPS for (k_, tk, fx) in shots if k_ == "live" and fx is None])
    ln = np.array([q for q, (k_, tk, fx) in enumerate(shots) if k_ == "live" and fx is None]) / OUT_FPS
    rt = np.array([tk / OUT_FPS for (k_, tk, fx) in shots if k_ == "rep" and fx is None])
    rn = np.array([q for q, (k_, tk, fx) in enumerate(shots) if k_ == "rep" and fx is None]) / OUT_FPS
    def L(ts): return None if ts > lt[-1] else float(np.interp(ts, lt, ln))
    def Rp(ts): return None if not len(rt) or ts < rt[0] or ts > rt[-1] else float(np.interp(ts, rt, rn))
    fx_starts = [q / OUT_FPS for q, (k_, tk, fx) in enumerate(shots) if fx and fx[0] == "flash" and fx[1] == 0]
    R0 = rn[0] if len(rn) else None; E0 = B["n_end"] / OUT_FPS
    f1 = B["f1"]; F1 = L(f1) or T_end
    noise = lambda d: R.randn(int(d * sr))
    def thump(f0, d=0.22):
        tt = np.arange(int(d * sr)) / sr
        s = np.sin(2 * np.pi * (f0 * tt - f0 * 0.6 * tt * tt / d / 2)) * np.exp(-tt * 18)
        s[:int(0.006 * sr)] += noise(0.006) * 0.6
        return s
    def whoosh(d=0.45):
        tt = np.arange(int(d * sr)) / sr
        return lp(noise(d), 6) * np.exp(-((tt - d * 0.55) / (d * 0.22)) ** 2) * 2.2
    def boom():
        tt = np.arange(int(1.2 * sr)) / sr
        return np.sin(2 * np.pi * (95 * tt - 30 * tt * tt)) * np.exp(-tt * 3.5) + lp(noise(1.2), 20) * np.exp(-tt * 9) * 2.0
    def crash(d=1.6):
        x = noise(d); return (x - lp(x, 4)) * np.exp(-np.arange(len(x)) / sr * 2.6)
    for s in range(int(COUNT)): add(tone(660, 0.18, 10), s, 0.35)
    add(tone(1320, 0.4, 6), COUNT, 0.4); add(whoosh(0.5), COUNT - 0.1, 0.25)
    # beat from GO to the line (in output time), then a drum roll / riser / crowd build over the last ~5 s
    bpm = 150 if INTENSE else 132; step = 60 / bpm
    kk = tone(55, 0.25, 18); _c = tone(110, 0.08, 40); kk[:len(_c)] += _c * 0.5
    hat = noise(0.04) * np.exp(-np.arange(int(0.04 * sr)) / sr * 90)
    snare = lp(noise(0.12), 2) * np.exp(-np.arange(int(0.12 * sr)) / sr * 30) + tone(190, 0.12, 30) * 0.5
    bt = COUNT
    while bt < F1 - 0.02:
        add(kk, bt, 0.5); add(hat, bt + step / 2, 0.09); bt += step
    bass = [55, 55, 65.4, 49]
    for q, bt in enumerate(np.arange(COUNT, F1 - step, step * 4)):
        add(tone(bass[q % 4], min(step * 4, F1 - bt), 1.2, "sq"), bt, 0.09)
    b0 = max(COUNT + 2, F1 - 5.0); bt = b0
    while bt < F1 - 0.03:
        p = (bt - b0) / max(0.1, F1 - b0); add(snare, bt, 0.06 + 0.16 * p); bt += step / (2 + 6 * p * p)
    rl = F1 - b0
    if rl > 0.5:
        tt = np.arange(int(rl * sr)) / sr; p = tt / rl
        riser = np.sin(2 * np.pi * np.cumsum(180 + 700 * p ** 2) / sr) * 0.5 + lp(noise(rl), 3) * 0.6
        add(riser * p ** 2, b0, 0.22)
        crowd = lp(noise(rl + 2.5), 25) * 6
        env = np.concatenate([p ** 1.5, np.exp(-np.arange(int(2.5 * sr)) / sr * 0.9)])
        mod = 1 + 0.35 * np.sin(2 * np.pi * np.arange(len(env)) / sr * 3.1) * np.sin(2 * np.pi * np.arange(len(env)) / sr * 0.7)
        add(crowd * env[:len(crowd)] * mod[:len(crowd)], b0, 0.22)
    # impact frames: a hard hit + shing at the start of each hit-stop
    for q in fx_starts:
        add(boom(), q, 0.55); add(crash(0.9), q, 0.2); add(tone(2400, 0.5, 7), q + 0.02, 0.06)
    last = {}; last_cl = -1
    for (te, kind, i, d) in events:
        o = L(te)
        if o is None: continue
        if kind == "clash" and te > COUNT:
            if te - last_cl < 0.05: continue
            last_cl = te; add(thump(130), o, 0.12 + 0.3 * min(1, d[3] / 1500))
        elif kind in ("wall", "kick"):
            if te - last.get(i, -1) < 0.07: continue
            last[i] = te; add(tone([523.3, 659.3, 784.0][i] * (1.5 if kind == "kick" else 1), 0.12, 26), o, 0.12)
        elif kind == "bump":
            sw = np.arange(int(0.25 * sr)) / sr; add(np.sin(2 * np.pi * (300 * sw + 900 * sw ** 2)) * np.exp(-sw * 10), o, 0.24)
        elif kind == "glass":       # shatter: bright noise burst + glassy tinkles
            add(crash(0.9), o, 0.5)
            for h in range(5): add(tone(2600 + 700 * h, 0.25, 14), o + 0.03 * h, 0.07)
        elif kind == "pad":
            sw = np.arange(int(0.35 * sr)) / sr; add(np.sin(2 * np.pi * (200 * sw + 1400 * sw ** 2)) * np.exp(-sw * 7), o, 0.22)
    lw = -9
    for lc in B["lead_changes"]:
        if lc - lw < 0.6: continue
        lw = lc; add(whoosh(), (L(lc) or 0) - 0.2, 0.22)
    for (tp, who) in B["pops"]: add(whoosh(0.6), (L(tp) or 0) - 0.25, 0.35)
    if R0 is not None:
        d = E0 - R0; tt = np.arange(int(d * sr)) / sr
        drone = (np.sin(2 * np.pi * 55 * tt) + 0.5 * np.sin(2 * np.pi * 82.4 * tt)) * np.minimum(1, tt / 0.3) * np.minimum(1, (d - tt) / 0.2 + 0.01)
        add(drone, R0, 0.12); add(whoosh(0.7), R0 - 0.3, 0.3)
        hb = 0.15
        while hb < d - 0.3:
            add(thump(60, 0.3), R0 + hb, 0.35); add(thump(55, 0.3), R0 + hb + 0.18, 0.22); hb += 0.75
        for (te, kind, i, dd) in events:
            if kind == "clash": add(thump(70, 0.4), Rp(te), 0.25)
    for h, fq in enumerate([523, 659, 784, 1046]):
        add(tone(fq, 0.6, 4), E0 + 0.05 + h * 0.1, 0.22)
    peak = np.abs(buf).max() or 1
    buf = np.tanh(buf / peak * 1.8) / np.tanh(1.8) * 0.9          # gentle limiter: punchy, never clips
    fo = int(0.35 * sr); e = int(T_end * sr)
    buf[e - fo:e] *= np.linspace(1, 0, fo)
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((buf[:e] * 32767).astype(np.int16).tobytes())

# ---------------- search ----------------
def _try(seed):
    try:
        c, fr, ev, fin = simulate(seed)
        sc = score(c, fr, ev, fin)
    except Exception:
        return seed, -1
    return seed, sc

def excellent(b):
    return (b["changes"] >= 8 and b["gap"] < 0.15 and b["tight"] >= 0.6 and b["comeback"] >= 1
            and 22 <= b["dur"] <= 34 and b["win"] >= 12)

def good_enough(b):
    return (b["changes"] >= (8 if INTENSE else 6) and b["gap"] < (0.2 if INTENSE else 0.3) and b["tight"] >= 0.55
            and 22 <= b["dur"] <= 34 and b["win"] >= 12)

if __name__ == "__main__":
    import multiprocessing as mp
    cfg = json.load(open(sys.argv[1]))
    INTENSE = bool(cfg.get("intense")); JELLY = bool(cfg.get("jelly"))
    if cfg.get("names") and len(cfg["names"]) == 3: NAMES = [str(x)[:12] for x in cfg["names"]]
    s0 = cfg.get("seed", random.randint(1, 10 ** 6))
    best, t_start, n_ok = None, time.time(), 0
    workers = max(1, min(8, os.cpu_count() or 1))
    if cfg.get("force_seed"):
        sc = score(*simulate(cfg["force_seed"]))
        best = (0, cfg["force_seed"], sc[1] if sc != -1 else {})
    else:
        pool = mp.get_context("fork").Pool(workers)
        try:
            for seed, sc in pool.imap_unordered(_try, range(s0, s0 + cfg.get("tries", 200))):
                if sc != -1:
                    n_ok += 1
                    print("seed", seed, round(sc[0], 1), sc[1], flush=True)
                    if best is None or sc[0] > best[0]: best = (sc[0], seed, sc[1])
                    el = time.time() - t_start
                    if excellent(best[2]) and n_ok >= 2 * workers: break
                    if good_enough(best[2]) and el > cfg.get("min_search", 60): break
                if time.time() - t_start > cfg.get("budget", 170) and best: break
        finally:
            pool.terminate()
    if not best: raise SystemExit("no race found")
    _, seed, info = best
    c, fr, ev, fin = simulate(seed)
    print("using seed", seed, info, c["kinds"], f"(searched {n_ok} races with {workers} workers in {time.time() - t_start:.0f}s)", flush=True)
    tmp = cfg["out"] + ".frames"; subprocess.run(["rm", "-rf", tmp])
    t_r = time.time()
    B = render(cfg, c, fr, ev, fin, tmp, workers)
    print(f"rendered {len(B['shots'])} frames @ {OUT_FPS} fps in {time.time() - t_r:.0f}s", flush=True)
    wav = cfg["out"] + ".wav"; audio(ev, fin, B, wav)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(OUT_FPS), "-i", f"{tmp}/f%05d.jpg", "-i", wav,
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "17", "-preset", "medium", "-tune", "animation",
                    "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-shortest", cfg["out"]], check=True)
    if not cfg.get("keep_frames"): subprocess.run(["rm", "-rf", tmp])
    subprocess.run(["rm", "-f", wav])
    json.dump({"seed": seed, **info, "photo": B["photo"], "lead_changes": len(B["lead_changes"]), "popups": len(B["pops"]),
               "fps": OUT_FPS, "frames": len(B["shots"])}, open(cfg["out"] + ".json", "w"))
    print("done", cfg["out"], "photo" if B["photo"] else "", len(B["lead_changes"]), "lead changes", len(B["pops"]), "pop-ups")
