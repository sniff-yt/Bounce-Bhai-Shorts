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

def simulate(seed, gap, spin, grow, max_t=40.0, mode="gap"):
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
            gc = g0 + spin*t
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
                        events.append((t, bounces))
                        if hp is not None and hp[kb] > 0:
                            hp[kb] -= 1
                            if hp[kb] == 0: events.append((t, -1 - kb))      # brick shattered
                    p = [CX + nx*(rin - r), CY + ny*(rin - r)]
            if escaped_at is None and d - r > R + TH/2:
                escaped_at = t
        frames.append((p[0], p[1], r, (g0 + spin*t) % 360, bounces, tuple(hp) if hp else None))
        if escaped_at is not None and t > escaped_at + 2.2:
            break
    return frames, events, escaped_at

def _hits(ev): return [e for e in ev if e[1] > 0]

def find(cfg):
    lo, hi = cfg.get("target", [22, 28])
    s0 = cfg.get("seed", 1)
    import time
    best, best_d, t0 = None, 1e9, time.time()
    for seed in range(s0, s0 + 4000):
        fr, ev, esc = simulate(seed, cfg["gap_deg"], cfg["spin"], cfg["grow"], mode=cfg.get("variant", "gap"))
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

def render(cfg, frames, esc, tmpdir, events=()):
    os.makedirs(tmpdir, exist_ok=True)
    trail = []
    gap = cfg["gap_deg"]
    jelly = bool(cfg.get("jelly"))
    hit_t = [e[0] for e in events if e[1] > 0]
    breaks = [(e[0], -1 - e[1]) for e in events if e[1] < 0]
    name = (cfg.get("names") or [None])[0]
    for i, (x, y, r, gc, b, hp) in enumerate(frames):
        t = i / FPS
        img = Image.new("RGB", (W*SS, H*SS), (10, 10, 18))
        dr = ImageDraw.Draw(img)
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
        # trail
        trail.append((x, y, r, col)); trail[:] = trail[-14:]
        for j, (tx, ty, tr, tc) in enumerate(trail[:-1]):
            k = (j+1)/len(trail)
            c = tuple(int(10 + (cc-10)*k*0.55) for cc in tc)
            rr = tr*(0.5+0.5*k)
            dr.ellipse([(tx-rr)*SS, (ty-rr)*SS, (tx+rr)*SS, (ty+rr)*SS], fill=c)
        sx_ = sy_ = 1.0
        if jelly:     # jelly ball: squash + damped wobble after every bounce, glossy translucent core
            lh = max([h for h in hit_t if h <= t] or [-9]); age = t - lh
            if age < 0.8:
                a_ = 0.28*math.exp(-age*7)*math.cos(age*34); sx_, sy_ = 1 + a_, 1 - a_*0.9
        dr.ellipse([(x-r*sx_)*SS, (y-r*sy_)*SS, (x+r*sx_)*SS, (y+r*sy_)*SS], fill=col,
                   outline=(255,255,255), width=3*SS)
        if jelly:
            lc = tuple(min(255, cc + 90) for cc in col)
            dr.ellipse([(x-r*sx_*0.55+r*0.1)*SS, (y-r*sy_*0.55+r*0.15)*SS, (x+r*sx_*0.55+r*0.1)*SS, (y+r*sy_*0.55+r*0.15)*SS], fill=lc)
            dr.ellipse([(x-r*0.55)*SS, (y-r*0.6)*SS, (x-r*0.15)*SS, (y-r*0.3)*SS], fill=(255, 255, 255))
        # texts (hook on frame 1)
        text_center(dr, 200, cfg["hook"], 66, stroke=4)
        text_center(dr, 420, f"Bounces: {b}", 76, fill=col, stroke=4)
        if cfg.get("series"):
            text_center(dr, 115, cfg["series"], 38, fill=(180, 200, 255), stroke=3)
        if name:
            text_center(dr, 515, f"{name} KI BALL", 38, fill=col, stroke=3)
        text_center(dr, 1840, "@bouncebhaiofficial", 32, fill=(200, 200, 220), stroke=3)
        if esc is not None and t >= esc:
            text_center(dr, 1420, cfg.get("win", "BAHAR NIKAL GAYI!"), 70, fill=(255, 220, 60), stroke=5)
            if t >= esc + 0.5:   # on-video subscribe CTA on the end beat
                dr.rounded_rectangle([290*SS, 1560*SS, 790*SS, 1660*SS], radius=26*SS, fill=(230, 30, 40))
                text_center(dr, 1578, "SUBSCRIBE", 58, stroke=0)
                text_center(dr, 1690, "Roz naye challenges!", 42, fill=(255, 220, 60), stroke=3)
        else:
            text_center(dr, 1420, cfg["cta"], 46, fill=(220,220,230), stroke=3)
        img = img.resize((W, H), Image.LANCZOS)
        img.save(f"{tmpdir}/f{i:05d}.png", compress_level=1)
    return len(frames)

def audio(events, n_frames, esc, path):
    sr = 44100; n = int(n_frames/FPS*sr) + sr
    buf = np.zeros(n, dtype=np.float32)
    scale = [0, 2, 4, 7, 9]  # pentatonic
    R_ = np.random.RandomState(5)
    for (t, b) in events:
        if b < 0:      # brick shatter: short bright noise burst
            L = int(0.35*sr); tt = np.arange(L)/sr
            x = R_.randn(L)*np.exp(-tt*14); s = int(t*sr)
            buf[s:s+L] += 0.35*x[:max(0, min(L, n-s))]
            continue
        note = 60 + scale[b % 5] + 12*((b//5) % 3)
        fr = 440*2**((note-69)/12)
        L = int(0.22*sr); tt = np.arange(L)/sr
        tone = (np.sin(2*np.pi*fr*tt) + 0.3*np.sin(4*np.pi*fr*tt)) * np.exp(-tt*16)
        s = int(t*sr); buf[s:s+L] += 0.28*tone[:max(0, min(L, n-s))]
    if esc:
        L = int(0.8*sr); tt = np.arange(L)/sr
        sweep = np.sin(2*np.pi*(500*tt + 700*tt**2)) * np.exp(-tt*3)
        s = int(esc*sr); buf[s:s+L] += 0.3*sweep[:max(0, min(L, n-s))]
    peak = np.max(np.abs(buf)) or 1
    buf = buf/peak*0.8
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((buf*32767).astype(np.int16).tobytes())

if __name__ == "__main__":
    cfg = json.load(open(sys.argv[1]))
    seed, frames, events, esc = find(cfg)
    print("seed", seed, "escape", round(esc, 2), "bounces", len(_hits(events)), "frames", len(frames))
    tmp = cfg["out"] + ".frames"
    subprocess.run(["rm", "-rf", tmp])
    n = render(cfg, frames, esc, tmp, events)
    wav = cfg["out"] + ".wav"; audio(events, n, esc, wav)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", f"{tmp}/f%05d.png",
                    "-i", wav, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "medium",
                    "-c:a", "aac", "-b:a", "160k", "-shortest", cfg["out"]], check=True)
    subprocess.run(["rm", "-rf", tmp, wav])
    print("done", cfg["out"])
