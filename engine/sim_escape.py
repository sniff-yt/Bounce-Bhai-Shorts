#!/usr/bin/env python3
"""Bounce Bhai: 'ball escape' physics Short. Pure code, no AI.
usage: python3 sim_escape.py config.json
config: {"out": "...mp4", "seed": 1, "hook": "...", "cta": "...", "gap_deg": 38, "spin": 70,
         "grow": 1.4, "target": [22, 28]}
"""
import json, math, random, sys, os, subprocess, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H, FPS, SS = 1080, 1920, 30, 2
CX, CY, R, TH = 540, 980, 400, 16
FONT = os.environ.get("BB_FONT", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")

def hsv(h, s=0.85, v=1.0):
    import colorsys
    r, g, b = colorsys.hsv_to_rgb(h % 1, s, v)
    return (int(r*255), int(g*255), int(b*255))

NSEG = 24                 # "break" variant: the ring is 24 bricks; each hit cracks one, at 0 hp it shatters

TAIL = 1.0                # seconds after the escape (was 2.2): tight ending, then the loop cross-fade
SLOW = 0.35               # escape moment plays at 0.35x (interpolated frames)
LOOP_FADE = 0.4           # last 0.4 s cross-fades into frame 1: auto-replays read as rewatches

def simulate(seed, gap, spin, grow, max_t=40.0, mode="gap", accel=0.0):
    """accel: the ring spins up over time (angle = spin*(t + accel*t^2/2)) -> rising tension, real physics."""
    rnd = random.Random(seed)
    hp = [rnd.randint(2, 4) for _ in range(NSEG)] if mode == "break" else None
    if mode == "break": gap = 360 / NSEG
    sub = 12; dt = 1.0/(FPS*sub)
    p = [CX + rnd.uniform(-60, 60), CY - rnd.uniform(80, 200)]
    ang = rnd.uniform(0, 2*math.pi); sp = rnd.uniform(500, 800)
    v = [math.cos(ang)*sp, math.sin(ang)*sp]
    r = 22.0; g0 = rnd.uniform(0, 360); G = 1500.0
    r_max = min(0.30*R, 0.42*2*R*math.sin(math.radians(gap)/2))   # never too big for the gap or the ring
    frames, bounces, events = [], 0, []
    escaped_at = None; t = 0.0
    for f in range(int(max_t*FPS)):
        for _ in range(sub):
            t += dt
            v[1] += G*dt
            p[0] += v[0]*dt; p[1] += v[1]*dt
            gc = g0 + spin*(t + accel*t*t/2)
            dx, dy = p[0]-CX, p[1]-CY; d = math.hypot(dx, dy)
            rin = R - TH/2
            if escaped_at is None and d + r > rin and d < R + TH/2 + r:
                a = math.degrees(math.atan2(dy, dx))
                diff = (a - gc + 180) % 360 - 180
                half_ball = math.degrees(r/R)
                if hp is not None:
                    rel = (a - gc) % 360; kb = int(rel // gap) % NSEG; ctr = (kb + 0.5) * gap
                    dd = abs(((rel - ctr) + 180) % 360 - 180)
                    # passes through a shattered brick (or two neighbouring ones)
                    lo_ok = hp[kb] <= 0 and (dd < gap/2 - half_ball or hp[(kb + (1 if rel > ctr else -1)) % NSEG] <= 0)
                    diff = 0.0 if lo_ok else 999
                if abs(diff) < gap/2 - half_ball:
                    pass  # flying through the gap
                elif d < rin + 4 or abs(diff) >= gap/2:
                    nx, ny = dx/d, dy/d
                    vn = v[0]*nx + v[1]*ny
                    if vn > 0:
                        v[0] -= 2*vn*nx; v[1] -= 2*vn*ny
                        # tiny random kick keeps it chaotic, energy floor keeps it lively
                        k = rnd.uniform(-0.08, 0.08)
                        c, s = math.cos(k), math.sin(k)
                        v = [v[0]*c - v[1]*s, v[0]*s + v[1]*c]
                        spd = math.hypot(*v)
                        target = max(spd*1.0, 900)
                        v = [v[0]/spd*target, v[1]/spd*target]
                        bounces += 1; r = min(r + grow, r_max)
                        events.append((t, bounces, spd))
                        if hp is not None and hp[kb] > 0:
                            hp[kb] -= 1
                            if hp[kb] == 0: events.append((t, -1 - kb, spd))      # brick shattered
                    p = [CX + nx*(rin - r), CY + ny*(rin - r)]
            if escaped_at is None and d - r > R + TH/2:
                escaped_at = t
        frames.append((p[0], p[1], r, (g0 + spin*(t + accel*t*t/2)) % 360, bounces, tuple(hp) if hp else None))
        if escaped_at is not None and t > escaped_at + TAIL:
            break
    return frames, events, escaped_at

def _hits(ev): return [e for e in ev if e[1] > 0]

def find(cfg):
    lo, hi = cfg.get("target", [22, 28])
    s0 = cfg.get("seed", 1)
    import time
    best, best_d, t0 = None, 1e9, time.time()
    for seed in range(s0, s0 + 4000):
        fr, ev, esc = simulate(seed, cfg["gap_deg"], cfg["spin"], cfg["grow"], mode=cfg.get("variant", "gap"),
                               accel=cfg.get("spin_accel", 0.03))
        if len(_hits(ev)) > 160:
            continue
        if esc and lo <= esc <= hi and len(_hits(ev)) >= 25:
            return seed, fr, ev, esc
        if esc and esc >= 12:  # remember the closest usable escape so a run never fails here
            d = (lo - esc if esc < lo else esc - hi if esc > hi else 0) + max(0, 25 - len(_hits(ev)))
            if d < best_d:
                best, best_d = (seed, fr, ev, esc), d
        if time.time() - t0 > 600 and best:
            break
    if best:
        print(f"no exact seed; using closest (off by {best_d:.1f})", flush=True)
        return best
    raise SystemExit("no seed found")

def text_center(dr, y, txt, size, fill=(255,255,255), stroke=0, max_w=960):
    """Centered text that always fits the frame: wraps to 2 lines, then shrinks."""
    words = txt.split()
    while True:
        f = ImageFont.truetype(FONT, size*SS)
        lines = [txt]
        if dr.textlength(txt, font=f) > max_w*SS and len(words) > 1:
            best = None
            for k in range(1, len(words)):
                a, b = " ".join(words[:k]), " ".join(words[k:])
                m = max(dr.textlength(a, font=f), dr.textlength(b, font=f))
                if best is None or m < best[0]:
                    best = (m, [a, b])
            lines = best[1]
        if max(dr.textlength(l, font=f) for l in lines) <= max_w*SS or size <= 30:
            break
        size -= 4
    for i, l in enumerate(lines):
        w = dr.textlength(l, font=f)
        dr.text(((W*SS - w)/2, (y + i*size*1.18)*SS), l, font=f, fill=fill,
                stroke_width=stroke*SS, stroke_fill=(0,0,0))

def timeline(frames, esc):
    """Output frame -> fractional sim frame. Real time, except the escape plays in slow motion."""
    tl, x, n = [], 0.0, len(frames) - 1
    a, b = ((esc - 0.35) * FPS, (esc + 0.4) * FPS) if esc else (1e9, 1e9)
    while x <= n:
        tl.append(x); x += SLOW if a <= x < b else 1.0
    return tl

def frame_at(frames, x):
    k0 = int(x); k1 = min(k0 + 1, len(frames) - 1); u = x - k0
    f0, f1 = frames[k0], frames[k1]
    dg = ((f1[3] - f0[3] + 180) % 360) - 180
    return (f0[0] + (f1[0] - f0[0]) * u, f0[1] + (f1[1] - f0[1]) * u, f0[2] + (f1[2] - f0[2]) * u,
            (f0[3] + dg * u) % 360, f0[4], f0[5])

def render(cfg, frames, esc, tmpdir, events=()):
    os.makedirs(tmpdir, exist_ok=True)
    trail = []
    gap = cfg["gap_deg"]
    jelly = bool(cfg.get("jelly"))
    hit_t = [e[0] for e in events if e[1] > 0]
    breaks = [(e[0], -1 - e[1]) for e in events if e[1] < 0]
    name = (cfg.get("names") or [None])[0]
    tl = timeline(frames, esc)
    sa, sb = ((esc - 0.35), (esc + 0.4)) if esc else (1e9, 1e9)
    nfade = int(LOOP_FADE * FPS); first = None
    for i, xf in enumerate(tl):
        x, y, r, gc, b, hp = frame_at(frames, xf)
        t = xf / FPS
        slow = sa <= t < sb
        img = Image.new("RGB", (W*SS, H*SS), (10, 10, 18))
        dr = ImageDraw.Draw(img)
        # tension: the background warms up and pulses on every bounce as time runs (and the ring spins up)
        lh = max([h for h in hit_t if h <= t] or [-9])
        heat = min(1.0, t / max(1.0, (esc or 30)))
        pulse = math.exp(-(t - lh) * 9) if esc is None or t < esc else 0.0
        bgc = (int(10 + 34*heat + 30*pulse*heat), int(10 + 6*pulse), int(18 + 10*pulse))
        img.paste(bgc, (0, 0, W*SS, H*SS))
        hue = 0.02 + b*0.031
        col = hsv(hue)
        # ring
        bb = [(CX-R)*SS, (CY-R)*SS, (CX+R)*SS, (CY+R)*SS]
        ring_col = hsv(hue + 0.5, 0.6, 1.0)
        if hp is not None:
            sg = 360 / NSEG
            for k, h in enumerate(hp):
                if h <= 0: continue
                cc = ring_col if h >= 3 else (255, 200, 80) if h == 2 else (255, 90, 70)   # cracked bricks heat up
                dr.arc(bb, gc + k*sg + 1.2, gc + (k + 1)*sg - 1.2, fill=cc, width=TH*SS)
            for (bt, k) in breaks:                     # shards fly off a shattered brick
                age = t - bt
                if not (0 <= age < 1.0): continue
                rs = random.Random(int(bt*1000) + k)
                a0 = math.radians(gc + (k + 0.5)*sg)
                for _ in range(14):
                    sp_ = rs.uniform(150, 520); da = rs.uniform(-0.5, 0.5)
                    px = CX + math.cos(a0)*R + math.cos(a0 + da)*sp_*age
                    py = CY + math.sin(a0)*R + math.sin(a0 + da)*sp_*age + 900*age*age
                    q = rs.uniform(5, 11)*(1 - age)
                    dr.polygon([((px - q)*SS, (py - q)*SS), ((px + q)*SS, (py - q*0.3)*SS), ((px - q*0.2)*SS, (py + q)*SS)], fill=ring_col)
        elif esc is None or t < esc:
            dr.arc(bb, gc + gap/2, gc + 360 - gap/2, fill=ring_col, width=TH*SS)
        elif t - esc < 0.6:                            # the ring bursts outward as the ball gets out
            age = t - esc; rr_ = R + 260*age
            ca = tuple(int(10 + (cc - 10)*(1 - age/0.6)) for cc in ring_col)
            dr.arc([(CX-rr_)*SS, (CY-rr_)*SS, (CX+rr_)*SS, (CY+rr_)*SS], gc + gap/2, gc + 360 - gap/2, fill=ca, width=max(2, int(TH*(1 - age/0.6)))*SS)
        # trail
        trail.append((x, y, r, col)); trail[:] = trail[-14:]
        for j, (tx, ty, tr, tc) in enumerate(trail[:-1]):
            k = (j+1)/len(trail)
            c = tuple(int(10 + (cc-10)*k*0.55) for cc in tc)
            rr = tr*(0.5+0.5*k)
            dr.ellipse([(tx-rr)*SS, (ty-rr)*SS, (tx+rr)*SS, (ty+rr)*SS], fill=c)
        sx_ = sy_ = 1.0
        if jelly:     # jelly ball: squash + damped wobble after every bounce, glossy translucent core
            age = t - lh
            if age < 0.8:
                a_ = 0.28*math.exp(-age*7)*math.cos(age*34); sx_, sy_ = 1 + a_, 1 - a_*0.9
        dr.ellipse([(x-r*sx_)*SS, (y-r*sy_)*SS, (x+r*sx_)*SS, (y+r*sy_)*SS], fill=col,
                   outline=(255,255,255), width=3*SS)
        if jelly:
            lc = tuple(min(255, cc + 90) for cc in col)
            dr.ellipse([(x-r*sx_*0.55+r*0.1)*SS, (y-r*sy_*0.55+r*0.15)*SS, (x+r*sx_*0.55+r*0.1)*SS, (y+r*sy_*0.55+r*0.15)*SS], fill=lc)
            dr.ellipse([(x-r*0.55)*SS, (y-r*0.6)*SS, (x-r*0.15)*SS, (y-r*0.3)*SS], fill=(255, 255, 255))
        if slow and esc and t >= esc - 0.35:           # slow-mo: escape flash ring around the ball
            fa = max(0.0, 1 - abs(t - esc) / 0.45)
            rr = r + 30 + 60*(1 - fa)
            dr.ellipse([(x-rr)*SS, (y-rr)*SS, (x+rr)*SS, (y+rr)*SS], outline=(255, 230, 120), width=max(1, int(8*fa))*SS)
        # texts: 0-second hook = big line on frame 1, settles to the normal title size after ~2 s
        hk = min(1.0, max(0.0, (t - 1.8) / 0.3))
        text_center(dr, int(170 + 30*hk), cfg["hook"], int(92 - 26*hk), stroke=5)
        text_center(dr, 420, f"Bounces: {b}", 76, fill=col, stroke=4)
        if cfg.get("series"):
            text_center(dr, 115, cfg["series"], 38, fill=(180, 200, 255), stroke=3)
        if name:
            text_center(dr, 515, f"{name} KI BALL", 38, fill=col, stroke=3)
        text_center(dr, 1840, "@bouncebhaiofficial", 32, fill=(200, 200, 220), stroke=3)
        if esc is not None and t >= esc:
            text_center(dr, 1420, cfg.get("win", "BAHAR NIKAL GAYI!"), 70, fill=(255, 220, 60), stroke=5)
            text_center(dr, 1530, f"{b} bounce mein bahar!", 50, fill=col, stroke=4)
            if t >= esc + 0.5:   # on-video subscribe CTA on the end beat
                dr.rounded_rectangle([320*SS, 1640*SS, 760*SS, 1730*SS], radius=26*SS, fill=(230, 30, 40))
                text_center(dr, 1654, "SUBSCRIBE", 54, stroke=0)
        else:
            text_center(dr, 1420, cfg["cta"], 46, fill=(220,220,230), stroke=3)
            tp0 = 6.0                                  # pinned-question pill (comment bait) mid-video
            if tp0 <= t < tp0 + 2.6 and (esc is None or t < esc - 2):
                ptxt = cfg.get("pin", "Escape se pehle guess comment karo!")
                f_ = ImageFont.truetype(FONT, 38*SS); pw = min(980, dr.textlength(ptxt, font=f_)/SS + 60)
                dr.rounded_rectangle([(540 - pw/2)*SS, 1520*SS, (540 + pw/2)*SS, 1582*SS], radius=31*SS, fill=(250, 250, 250))
                text_center(dr, 1528, ptxt, 38, fill=(20, 20, 30), stroke=0, max_w=pw - 50)
        img = img.resize((W, H), Image.LANCZOS)
        if i == 0: first = img.copy()
        if i >= len(tl) - nfade:                       # loop: cross-fade into frame 1
            img = Image.blend(img, first, (i - (len(tl) - nfade) + 1) / (nfade + 1))
        img.save(f"{tmpdir}/f{i:05d}.png", compress_level=1)
    return tl

def audio(events, tl, esc, path):
    sr = 44100; T_end = len(tl)/FPS; n = int(T_end*sr) + sr
    buf = np.zeros(n, dtype=np.float32)
    simt = np.array(tl)/FPS; outt = np.arange(len(tl))/FPS
    O = lambda ts: float(np.interp(ts, simt, outt))        # sim time -> output time (slow-mo stretches it)
    def add(x, t0, g):
        s = int(t0*sr)
        if s < 0 or s >= n: return
        m = min(len(x), n - s); buf[s:s+m] += g*np.asarray(x[:m], np.float32)
    scale = [0, 2, 4, 7, 9]  # pentatonic: every bounce climbs the scale (the melody IS the bounce count)
    R_ = np.random.RandomState(5)
    tt_ = lambda d: np.arange(int(d*sr))/sr
    # frame-1 sound: a punchy downbeat + a pulse that speeds up and gets louder as time runs (tension)
    tk = tt_(0.25); kick = np.sin(2*np.pi*(120*tk - 120*tk*tk))*np.exp(-tk*16)
    add(kick, 0.0, 0.5)
    end_beat = O(esc) if esc else T_end
    bt = 0.0
    while bt < end_beat - 0.05:
        p = min(1.0, bt/max(1.0, end_beat))
        add(kick, bt, 0.16 + 0.22*p)
        bt += 0.62 - 0.30*p                                 # 97 -> 187 bpm heartbeat
    for e in events:
        t, b = e[0], e[1]; spd = e[2] if len(e) > 2 else 900
        o = O(t)
        if b < 0:      # brick shatter: short bright noise burst
            tt = tt_(0.35); x = R_.randn(len(tt))*np.exp(-tt*14)
            add(x, o, 0.35); continue
        k = min(1.0, max(0.0, (spd - 800)/1400))          # impact speed -> brightness + level
        note = 60 + scale[b % 5] + 12*((b//5) % 3)
        fr = 440*2**((note-69)/12)
        tt = tt_(0.2)
        tone = (np.sin(2*np.pi*fr*tt) + (0.25 + 0.35*k)*np.sin(4*np.pi*fr*tt)) * np.exp(-tt*(18 - 4*k))
        tone[:int(0.003*sr)] += R_.randn(int(0.003*sr))*0.5*k        # crisp click transient on hard hits
        add(tone, o, 0.2 + 0.14*k)
    if esc:
        oe = O(esc)
        rl = 2.0; tt = tt_(rl); p = tt/rl                    # riser into the escape
        riser = np.sin(2*np.pi*np.cumsum(220 + 900*p**2)/sr)*0.5 + R_.randn(len(tt))*0.25
        add(riser*p**2, oe - rl, 0.2)
        tt = tt_(0.7); add(np.sin(2*np.pi*(150*tt - 80*tt*tt))*np.exp(-tt*4), O(esc - 0.35), 0.3)   # slow-mo whoomp
        tt = tt_(1.0)
        sweep = np.sin(2*np.pi*(500*tt + 700*tt**2)) * np.exp(-tt*3)
        add(sweep, oe, 0.32)
        boom = np.sin(2*np.pi*(80*tt - 25*tt*tt))*np.exp(-tt*3.5)
        add(boom, oe, 0.4)
        for h, fq in enumerate([523, 659, 784, 1046]):
            tt = tt_(0.4); add(np.sin(2*np.pi*fq*tt)*np.exp(-tt*6), oe + 0.25 + h*0.08, 0.15)
    peak = np.max(np.abs(buf)) or 1
    buf = np.tanh(buf/peak*1.6)/np.tanh(1.6)*0.88
    e = int(T_end*sr); fo = int(0.1*sr); buf[e-fo:e] *= np.linspace(1, 0.3, fo)
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((buf[:e]*32767).astype(np.int16).tobytes())

if __name__ == "__main__":
    cfg = json.load(open(sys.argv[1]))
    seed, frames, events, esc = find(cfg)
    print("seed", seed, "escape", round(esc, 2), "bounces", len(_hits(events)), "frames", len(frames))
    tmp = cfg["out"] + ".frames"
    subprocess.run(["rm", "-rf", tmp])
    tl = render(cfg, frames, esc, tmp, events)
    wav = cfg["out"] + ".wav"; audio(events, tl, esc, wav)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", f"{tmp}/f%05d.png",
                    "-i", wav, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "medium",
                    "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", cfg["out"]], check=True)
    subprocess.run(["rm", "-rf", tmp, wav])
    json.dump({"seed": seed, "escape": round(esc or 0, 2), "bounces": len(_hits(events)), "frames": len(tl),
               "dur": round(len(tl) / FPS, 2)}, open(cfg["out"] + ".json", "w"))
    print("done", cfg["out"], f"{len(tl)/FPS:.1f}s")
