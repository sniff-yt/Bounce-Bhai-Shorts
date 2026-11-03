#!/usr/bin/env python3
"""Bounce Bhai: 'ball multiply' Short. Every time a ball hits the ring it splits (+1 ball) until the ring is full,
then the ring cracks open and everything pours out. Pure code, no AI.
usage: python3 sim_multiply.py config.json
config: {"out": "...mp4", "seed": 1, "hook": "...", "cta": "...", "max_balls": 500, "target": [20, 27]}
"""
import json, math, random, sys, os, subprocess, wave, colorsys, time
import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H, FPS, SS = 1080, 1920, 30, 2
CX, CY, R, TH = 540, 1000, 410, 16
BR = 11                      # ball radius
FONT = os.environ.get("BB_FONT", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
G = 1300.0


def hsv(h, s=0.85, v=1.0):
    r, g, b = colorsys.hsv_to_rgb(h % 1, s, v)
    return (int(r * 255), int(g * 255), int(b * 255))


def simulate(seed, max_balls=500, cool=2.0, open_after=1.2, tail=3.2, max_t=45.0):
    rnd = np.random.RandomState(seed)
    sub = 6; dt = 1.0 / (FPS * sub)
    cap = max_balls
    P = np.zeros((cap, 2)); V = np.zeros((cap, 2)); born = np.zeros(cap); last = np.full(cap, -9.0)
    a = rnd.uniform(0, 2 * math.pi); sp = rnd.uniform(650, 850)
    P[0] = [CX + rnd.uniform(-40, 40), CY - rnd.uniform(100, 220)]
    V[0] = [math.cos(a) * sp, math.sin(a) * sp]
    n = 1; t = 0.0; full_at = None; open_at = None
    frames, events = [], []          # events: (t, n_after) on every split
    rin = R - TH / 2 - BR
    gap_c, gap_half = 90.0, 34.0    # opening at the bottom once the ring is full
    while t < max_t:
        for _ in range(sub):
            t += dt
            V[:n, 1] += G * dt
            P[:n] += V[:n] * dt
            d = np.hypot(P[:n, 0] - CX, P[:n, 1] - CY)
            hit = np.where(d > rin)[0]
            for i in hit:
                dx, dy = P[i, 0] - CX, P[i, 1] - CY; di = d[i]
                if open_at is not None:
                    ang = math.degrees(math.atan2(dy, dx))
                    if abs((ang - gap_c + 180) % 360 - 180) < gap_half or di > R + 30:
                        continue                         # falls out through the crack
                nx, ny = dx / di, dy / di
                vn = V[i, 0] * nx + V[i, 1] * ny
                if vn <= 0: continue
                V[i] -= 2 * vn * np.array([nx, ny])
                k = rnd.uniform(-0.1, 0.1); c, s = math.cos(k), math.sin(k)
                V[i] = [V[i, 0] * c - V[i, 1] * s, V[i, 0] * s + V[i, 1] * c]
                spd = math.hypot(*V[i]); tg = max(spd, 820.0)
                V[i] *= tg / spd
                P[i] = [CX + nx * rin, CY + ny * rin]
                if n < cap and t - last[i] > cool and open_at is None:
                    k2 = rnd.uniform(0.25, 0.6) * (1 if rnd.rand() < 0.5 else -1)
                    c, s = math.cos(k2), math.sin(k2)
                    P[n] = P[i]; V[n] = [V[i, 0] * c - V[i, 1] * s, V[i, 0] * s + V[i, 1] * c]
                    born[n] = t; last[n] = t; last[i] = t
                    n += 1; events.append((t, n))
                    if n >= cap and full_at is None: full_at = t
        if full_at is not None and open_at is None and t > full_at + open_after:
            open_at = t
        inside = int(np.sum(np.hypot(P[:n, 0] - CX, P[:n, 1] - CY) < R + 10))
        frames.append((P[:n].copy(), n, inside, t))
        if open_at is not None and t > open_at + tail:
            break
    return frames, events, full_at, open_at


def find(cfg):
    lo, hi = cfg.get("target", [18, 23]); s0 = cfg.get("seed", 1)
    best, bd = None, 1e9; t0 = time.time()
    for seed in range(s0, s0 + 300):
        fr, ev, full, op = simulate(seed, cfg.get("max_balls", 500), cfg.get("cool", 2.0))
        if full is None: continue
        if lo <= full <= hi: return seed, fr, ev, full, op
        dd = lo - full if full < lo else full - hi
        if dd < bd: best, bd = (seed, fr, ev, full, op), dd
        if time.time() - t0 > 240 and best: break
    if best: return best
    raise SystemExit("no seed")


def text_center(dr, y, txt, size, fill=(255, 255, 255), stroke=0, max_w=960):
    while True:
        f = ImageFont.truetype(FONT, size * SS)
        if dr.textlength(txt, font=f) <= max_w * SS or size <= 30: break
        size -= 4
    w = dr.textlength(txt, font=f)
    dr.text(((W * SS - w) / 2, y * SS), txt, font=f, fill=fill, stroke_width=stroke * SS, stroke_fill=(0, 0, 0))


def render(cfg, frames, full, op, tmp):
    os.makedirs(tmp, exist_ok=True)
    mx = cfg.get("max_balls", 500)
    cols = [hsv(0.0 + i * 0.618) for i in range(mx)]
    for fi, (P, n, inside, t) in enumerate(frames):
        img = Image.new("RGB", (W * SS, H * SS), (10, 10, 18)); dr = ImageDraw.Draw(img)
        prog = n / mx
        ring = hsv(0.55 - prog * 0.55, 0.7, 1.0)      # ring heats from blue to red as it fills
        bb = [(CX - R) * SS, (CY - R) * SS, (CX + R) * SS, (CY + R) * SS]
        if op is None or t < op:
            dr.arc(bb, 0, 360, fill=ring, width=TH * SS)
        else:
            dr.arc(bb, 90 + 34, 90 + 360 - 34, fill=ring, width=TH * SS)
            age = t - op
            if age < 0.9:                                # crack shards
                rs = random.Random(7)
                for _ in range(18):
                    a0 = math.radians(90 + rs.uniform(-34, 34)); sp_ = rs.uniform(150, 500)
                    px = CX + math.cos(a0) * R + math.cos(a0) * sp_ * age
                    py = CY + math.sin(a0) * R + math.sin(a0) * sp_ * age + 900 * age * age
                    q = rs.uniform(6, 12) * (1 - age)
                    dr.polygon([((px - q) * SS, (py - q) * SS), ((px + q) * SS, (py - q * .3) * SS), ((px - q * .2) * SS, (py + q) * SS)], fill=ring)
        for i in range(n):
            x, y = P[i]
            if y > H + 40: continue
            c = cols[i]
            dr.ellipse([(x - BR) * SS, (y - BR) * SS, (x + BR) * SS, (y + BR) * SS], fill=c)
            dr.ellipse([(x - BR * .55) * SS, (y - BR * .6) * SS, (x - BR * .05) * SS, (y - BR * .15) * SS], fill=(255, 255, 255))
        if cfg.get("series"): text_center(dr, 115, cfg["series"], 38, fill=(180, 200, 255), stroke=3)
        text_center(dr, 195, cfg["hook"], 64, stroke=4)
        pulse = 1.0 + (0.12 if any(abs(t - e) < 0.05 for e in ()) else 0)
        label = f"BALLS: {n}" if op is None or t < op else f"ANDAR: {inside}"
        text_center(dr, 300, label, int(96 * pulse), fill=hsv(0.55 - prog * 0.55), stroke=5)
        # progress bar to the target
        dr.rounded_rectangle([190 * SS, 430 * SS, 890 * SS, 462 * SS], radius=16 * SS, fill=(40, 40, 60))
        dr.rounded_rectangle([190 * SS, 430 * SS, (190 + 700 * prog) * SS, 462 * SS], radius=16 * SS, fill=hsv(0.55 - prog * 0.55))
        text_center(dr, 470, f"TARGET {mx}", 36, fill=(200, 200, 220), stroke=3)
        text_center(dr, 1840, "@bouncebhaiofficial", 32, fill=(200, 200, 220), stroke=3)
        if full is not None and t >= full:
            text_center(dr, 1470, cfg.get("win", f"{mx} BALLS! RING FULL!"), 66, fill=(255, 220, 60), stroke=5)
            if op is not None and t >= op + 0.8:
                dr.rounded_rectangle([290 * SS, 1590 * SS, 790 * SS, 1690 * SS], radius=26 * SS, fill=(230, 30, 40))
                text_center(dr, 1608, "SUBSCRIBE", 58)
                text_center(dr, 1715, "Agla target: 1000?", 42, fill=(255, 220, 60), stroke=3)
        else:
            text_center(dr, 1470, cfg["cta"], 46, fill=(220, 220, 230), stroke=3)
        img.resize((W, H), Image.LANCZOS).save(f"{tmp}/f{fi:05d}.png", compress_level=1)
    return len(frames)


def audio(events, nf, full, op, path, mx):
    sr = 44100; N = int(nf / FPS * sr) + sr; buf = np.zeros(N, dtype=np.float32)
    scale = [0, 2, 4, 7, 9]; lastt = -1
    for (t, n) in events:
        if t - lastt < 0.03: continue                   # keep it a fizz, not a wall of noise
        lastt = t
        step = int(n / mx * 30)
        note = 57 + scale[step % 5] + 12 * (step // 5) // 2
        fr = 440 * 2 ** ((note - 69) / 12); L = int(0.15 * sr); tt = np.arange(L) / sr
        tone = (np.sin(2 * np.pi * fr * tt) + 0.3 * np.sin(4 * np.pi * fr * tt)) * np.exp(-tt * 22)
        s = int(t * sr); buf[s:s + L] += 0.22 * tone[:max(0, min(L, N - s))]
    for (tt0, kind) in ((full, 0), (op, 1)):
        if tt0 is None: continue
        L = int(0.9 * sr); tt = np.arange(L) / sr; s = int(tt0 * sr)
        x = (np.sin(2 * np.pi * (400 * tt + 800 * tt ** 2)) * np.exp(-tt * 3)) if kind == 0 else \
            (np.random.RandomState(3).randn(L) * np.exp(-tt * 6))
        buf[s:s + L] += 0.35 * x[:max(0, min(L, N - s))]
    buf = buf / (np.max(np.abs(buf)) or 1) * 0.8
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((buf * 32767).astype(np.int16).tobytes())


if __name__ == "__main__":
    cfg = json.load(open(sys.argv[1]))
    seed, frames, events, full, op = find(cfg)
    print("seed", seed, "full", round(full, 2), "open", round(op or 0, 2), "frames", len(frames), flush=True)
    tmp = cfg["out"] + ".frames"; subprocess.run(["rm", "-rf", tmp])
    n = render(cfg, frames, full, op, tmp)
    wav = cfg["out"] + ".wav"; audio(events, n, full, op, wav, cfg.get("max_balls", 500))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", f"{tmp}/f%05d.png",
                    "-i", wav, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "medium",
                    "-c:a", "aac", "-b:a", "160k", "-shortest", cfg["out"]], check=True)
    subprocess.run(["rm", "-rf", tmp, wav])
    json.dump({"seed": seed, "full": full, "duration": n / FPS}, open(cfg["out"] + ".json", "w"))
    print("done", cfg["out"])
