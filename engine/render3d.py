#!/usr/bin/env python3
"""Bounce Bhai 3D-look renderer + story captions. Pure code (numpy/Pillow/ffmpeg), no AI.
usage: python3 render3d.py story.json
story.json: {"out","seed","gap_deg","spin","grow","target":[lo,hi],"hook","sentences":[{"hi":"Hinglish","en":"","hd":"","te":""}],
             "payoff_word": "Bubble", "hue": 0.55}
"""
import json, math, os, re, subprocess, sys, wave, random
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sim_escape as S

W, H, FPS = 1080, 1920, 30
S.CY = 880
CX, CY, R, TH = S.CX, S.CY, S.R, S.TH
FONT = os.environ.get("BB_FONT", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
LIGHT = np.array([-0.45, -0.6, 0.66]); LIGHT /= np.linalg.norm(LIGHT)

def hsv(h, s=0.85, v=1.0):
    import colorsys
    return tuple(int(c*255) for c in colorsys.hsv_to_rgb(h % 1, s, v))

# ---------- sprites ----------
_cache = {}
def sphere(r, col):
    key = (int(r*2), col)
    if key in _cache: return _cache[key]
    ss = 3; n = int(math.ceil(r))*2 + 4; N = n*ss
    yy, xx = np.mgrid[0:N, 0:N].astype(np.float32)
    c = N/2; rr = r*ss
    x = (xx - c)/rr; y = (yy - c)/rr; d2 = x*x + y*y
    inside = d2 <= 1
    z = np.sqrt(np.clip(1 - d2, 0, 1))
    nd = x*LIGHT[0] + y*LIGHT[1] + z*LIGHT[2]
    diff = np.clip(nd, 0, 1)
    hx, hy, hz = LIGHT[0], LIGHT[1], LIGHT[2] + 1
    hn = math.sqrt(hx*hx + hy*hy + hz*hz)
    spec = np.clip((x*hx + y*hy + z*hz)/hn, 0, 1)**60
    rim = (1 - z)**3
    base = np.array(col, np.float32)/255
    rgb = base[None, None, :]*(0.18 + 0.95*diff[..., None]) + 0.35*rim[..., None]*np.array([0.6, 0.8, 1.0])
    rgb += spec[..., None]*1.2
    # soft secondary bottom reflection
    rgb += 0.18*np.clip(y, 0, 1)[..., None]*np.clip(z, 0, 1)[..., None]*base
    rgb = np.clip(rgb, 0, 1)
    a = np.clip((1 - np.sqrt(d2))*rr/1.2, 0, 1)
    img = np.dstack([rgb*255, a*255]).astype(np.uint8)
    im = Image.fromarray(img, "RGBA").resize((n, n), Image.LANCZOS)
    _cache[key] = im
    return im

_shadow = {}
def shadow(r):
    k = int(r)
    if k in _shadow: return _shadow[k]
    n = int(r*4); im = Image.new("L", (n, n), 0)
    d = ImageDraw.Draw(im); d.ellipse([n/2 - r*1.05, n/2 - r*0.95, n/2 + r*1.05, n/2 + r*0.95], fill=150)
    im = im.filter(ImageFilter.GaussianBlur(r*0.35))
    sh = Image.new("RGBA", (n, n), (0, 0, 0, 0)); sh.putalpha(im)
    _shadow[k] = sh
    return sh

def background(hue):
    yy = np.linspace(0, 1, H)[:, None]
    top = np.array(hsv(hue + 0.08, 0.7, 0.16)); bot = np.array(hsv(hue - 0.05, 0.8, 0.07))
    g = (top*(1 - yy) + bot*yy)[:, None, :].repeat(W, 1) if False else None
    arr = np.zeros((H, W, 3), np.float32)
    arr[:] = (top*(1 - yy) + bot*yy)[:, None, :]
    # vignette
    Y, X = np.mgrid[0:H, 0:W]
    v = ((X - W/2)/(W*0.75))**2 + ((Y - H*0.45)/(H*0.6))**2
    arr *= np.clip(1.15 - 0.75*v, 0.25, 1.1)[..., None]
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    # bokeh
    bok = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(bok)
    rnd = random.Random(7)
    for _ in range(26):
        x, y, r = rnd.uniform(0, W), rnd.uniform(0, H), rnd.uniform(18, 70)
        c = hsv(hue + rnd.uniform(-0.15, 0.25), 0.6, 1.0)
        d.ellipse([x - r, y - r, x + r, y + r], fill=c + (rnd.randint(14, 34),))
    bok = bok.filter(ImageFilter.GaussianBlur(14))
    img = img.convert("RGBA"); img.alpha_composite(bok)
    # perspective grid floor below ring
    fl = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(fl)
    hor = 1330; gc = hsv(hue, 0.6, 0.9)
    for i in range(1, 14):
        y = hor + (H - hor)*(i/13)**2
        d.line([(0, y), (W, y)], fill=gc + (int(10 + 40*i/13),), width=2)
    for i in range(-12, 13):
        d.line([(W/2 + i*30, hor), (W/2 + i*260, H)], fill=gc + (34,), width=2)
    fl = fl.filter(ImageFilter.GaussianBlur(1.2))
    img.alpha_composite(fl)
    return img

def ring_layer(gc, gap, col, alpha=255):
    """neon tube ring, drawn 2x then downsampled; returns (RGBA crop, offset)."""
    pad = 60; sz = 2*R + 2*pad; ss = 2
    im = Image.new("RGBA", (sz*ss, sz*ss), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    bb = [pad*ss, pad*ss, (pad + 2*R)*ss, (pad + 2*R)*ss]
    a0, a1 = gc + gap/2, gc + 360 - gap/2
    dark = tuple(int(c*0.45) for c in col)
    d.arc(bb, a0, a1, fill=dark + (alpha,), width=(TH + 8)*ss)
    d.arc(bb, a0, a1, fill=col + (alpha,), width=TH*ss)
    inner = [b + (1 if i < 2 else -1)*3*ss for i, b in enumerate(bb)]
    d.arc(inner, a0, a1, fill=(255, 255, 255, int(alpha*0.85)), width=4*ss)
    im = im.resize((sz, sz), Image.LANCZOS)
    # glow
    small = im.resize((sz//4, sz//4), Image.BILINEAR).filter(ImageFilter.GaussianBlur(7))
    glow = small.resize((sz, sz), Image.BILINEAR)
    out = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
    out.alpha_composite(glow); out.alpha_composite(glow); out.alpha_composite(im)
    return out, (CX - R - pad, CY - R - pad)

# ---------- captions ----------
def word_timings(words, t0, t_payoff, idx_payoff, t_end):
    w = []
    for wd in words:
        x = 0.22 + 0.045*len(wd)
        if re.search(r"[.!?…]$", wd): x += 0.35
        elif wd.endswith(","): x += 0.15
        w.append(x)
    w = np.array(w)
    a = np.cumsum(np.r_[0, w[:-1]])
    pre = a[idx_payoff]
    k1 = (t_payoff - t0)/pre
    starts = t0 + a*k1
    post = a - pre
    if idx_payoff < len(words) - 1:
        k2 = (t_end - t_payoff)/(post[-1] + w[-1])
        starts[idx_payoff:] = t_payoff + post[idx_payoff:]*k2
    return list(starts)

def chunks(words):
    out, cur = [], []
    for i, wd in enumerate(words):
        cur.append(i)
        if len(cur) >= 4 or re.search(r"[.!?…,]$", wd) or (len(cur) >= 3 and len(" ".join(words[j] for j in cur)) > 18):
            out.append(cur); cur = []
    if cur: out.append(cur)
    return out

FONTS = {}
def font(sz):
    if sz not in FONTS: FONTS[sz] = ImageFont.truetype(FONT, sz)
    return FONTS[sz]

def draw_caption(dr, words, ids, cur, y=1470):
    f = font(82)
    line = [words[i] for i in ids]
    sp = dr.textlength(" ", font=f)
    widths = [dr.textlength(t, font=f) for t in line]
    total = sum(widths) + sp*(len(line) - 1)
    if total > 960:
        f = font(int(82*960/total)); sp = dr.textlength(" ", font=f)
        widths = [dr.textlength(t, font=f) for t in line]; total = sum(widths) + sp*(len(line) - 1)
    x = (W - total)/2
    for i, t, wdt in zip(ids, line, widths):
        c = (255, 222, 40) if i == cur else (255, 255, 255)
        dr.text((x, y), t, font=f, fill=c, stroke_width=8, stroke_fill=(0, 0, 0), anchor="lm")
        x += wdt + sp

def text_c(dr, y, txt, sz, fill=(255, 255, 255), stroke=5):
    f = font(sz)
    while dr.textlength(txt, font=f) > 980: sz -= 4; f = font(sz)
    dr.text((W/2, y), txt, font=f, fill=fill, stroke_width=stroke, stroke_fill=(0, 0, 0), anchor="mm")

def srt_time(t):
    ms = int(round(t*1000)); h, ms = divmod(ms, 3600000); m, ms = divmod(ms, 60000); s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

# ---------- audio ----------
def load_voice(path, sr=44100):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.int16).astype(np.float32)/32768

def audio(events, n_frames, esc, path, voice=None, music=True, bounces=False):
    sr = 44100; n = int(n_frames/FPS*sr) + sr
    buf = np.zeros(n, np.float32); scale = [0, 2, 4, 7, 9]
    for (t, b) in (events if bounces else []):
        note = 60 + scale[b % 5] + 12*((b//5) % 3); fr = 440*2**((note - 69)/12)
        L = int(0.22*sr); tt = np.arange(L)/sr
        tone = (np.sin(2*np.pi*fr*tt) + 0.3*np.sin(4*np.pi*fr*tt))*np.exp(-tt*16)
        s = int(t*sr); buf[s:s+L] += 0.26*tone[:max(0, min(L, n - s))]
    if esc and bounces:
        L = int(0.25*sr); tt = np.arange(L)/sr
        rnd = np.random.default_rng(1)
        pop = rnd.standard_normal(L)*np.exp(-tt*40) + 0.6*np.sin(2*np.pi*(900 - 2000*tt)*tt)*np.exp(-tt*20)
        s = int(esc*sr); buf[s:s+L] += 0.5*pop[:max(0, min(L, n - s))]
    buf = buf/(np.max(np.abs(buf)) or 1)*(0.8 if bounces else 0.35)
    if music:
        tt = np.arange(n)/sr; pad = np.zeros(n, np.float32)
        prog = [[57, 60, 64], [53, 57, 60], [48, 52, 55], [55, 59, 62]]  # Am F C G
        seg = 4.0
        for k in range(int(n/sr/seg) + 1):
            a, b = int(k*seg*sr), min(n, int((k + 1)*seg*sr + 0.8*sr))
            if a >= n: break
            t2 = np.arange(b - a)/sr; env = np.minimum(1, t2/1.2)*np.minimum(1, (b - a)/sr - t2)
            for note in prog[k % 4]:
                f = 440*2**((note - 69)/12)
                pad[a:b] += (np.sin(2*np.pi*f*t2) + 0.25*np.sin(2*np.pi*2*f*t2 + 0.3*np.sin(2*np.pi*0.2*t2)))*env
        pad = pad/(np.max(np.abs(pad)) or 1)
        fade = np.minimum(1, tt/1.5)*np.minimum(1, (n/sr - tt)/1.5)
        buf = buf + 0.09*pad*fade
    if voice:
        vb = np.zeros(n, np.float32)
        for (t, v) in voice:
            st = int(t*sr); m = max(0, min(len(v), n - st)); vb[st:st+m] += v[:m]
        vb = vb/(np.max(np.abs(vb)) or 1)*0.92
        env = np.convolve((np.abs(vb) > 0.02).astype(np.float32), np.ones(int(0.15*sr))/int(0.15*sr), "same")
        buf = buf*(1 - 0.6*np.clip(env*3, 0, 1))*0.55 + vb
        buf = buf/(np.max(np.abs(buf)) or 1)*0.89
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((buf*32767).astype(np.int16).tobytes())

def main(cfg):
    lo, hi = cfg["target"]; seed0 = cfg["seed"]
    vlines = None
    if cfg.get("voice_lines"):
        vlines = [load_voice(p) for p in cfg["voice_lines"]]
        sst, t = [], 0.4
        for v in vlines: sst.append(t); t += len(v)/44100 + 0.22
        words_all = [s["hi"].split() for s in cfg["sentences"]]
        pj = next(j for j, ws in enumerate(words_all) if any(w.strip("!.,").lower() == cfg["payoff_word"].lower() for w in ws))
        lo, hi = sst[pj] - 0.3, sst[pj] + 0.6
    for seed in range(seed0, seed0 + 600):
        fr, ev, esc = S.simulate(seed, cfg["gap_deg"], cfg["spin"], cfg["grow"], max_t=hi + 4)
        if esc and lo <= esc <= hi and len(ev) >= 25: break
    else: raise SystemExit("no seed")
    print("seed", seed, "esc", round(esc, 2), "bounces", len(ev), "frames", len(fr))
    story = " ".join(s["hi"] for s in cfg["sentences"]); words = story.split()
    pidx = next(i for i, w in enumerate(words) if w.strip("!.,").lower() == cfg["payoff_word"].lower())
    t_end = len(fr)/FPS - 0.3
    if vlines:
        starts = []
        for j, s_ in enumerate(cfg["sentences"]):
            ws = s_["hi"].split(); d = len(vlines[j])/44100
            wt = np.array([0.22 + 0.045*len(w) for w in ws]); a = np.cumsum(np.r_[0, wt[:-1]])/wt.sum()
            starts += list(sst[j] + 0.05 + a*(d - 0.1))
    else:
        starts = word_timings(words, 0.5, esc - 0.15, pidx, t_end)
    ch = chunks(words)
    # srt per language at sentence level
    bounds, k = [], 0
    for s in cfg["sentences"]:
        n = len(s["hi"].split()); bounds.append((starts[k], k, k + n)); k += n
    for lang in ("hi", "en", "hd", "te"):
        lines = []
        for j, (st, a, b) in enumerate(bounds):
            en = bounds[j + 1][0] if j + 1 < len(bounds) else len(fr)/FPS
            lines.append(f"{j+1}\n{srt_time(st)} --> {srt_time(en)}\n{cfg['sentences'][j][lang]}\n")
        open(cfg["out"].replace(".mp4", f".{lang}.srt"), "w").write("\n".join(lines))
    bg = background(cfg.get("hue", 0.6))
    tmp = cfg["out"] + ".frames"; subprocess.run(["rm", "-rf", tmp]); os.makedirs(tmp)
    trail = []; ring_col = hsv(cfg.get("hue", 0.6) + 0.5, 0.65, 1.0)
    for i, (x, y, r, gc, b) in enumerate(fr):
        t = i/FPS
        img = bg.copy()
        if t < esc:
            rl, off = ring_layer(gc, cfg["gap_deg"], ring_col); img.alpha_composite(rl, off)
        elif t < esc + 0.6:
            a = int(255*(1 - (t - esc)/0.6))
            rl, off = ring_layer(gc, cfg["gap_deg"], ring_col, a); img.alpha_composite(rl, off)
        col = hsv(cfg.get("ball_hue", 0.52) + b*0.012, 0.55, 1.0)
        # shadow
        sh = shadow(r); img.alpha_composite(sh, (int(x + r*0.35 - sh.width/2), int(y + r*0.55 - sh.height/2)))
        # motion trail
        trail.append((x, y)); trail[:] = trail[-7:]
        sp = sphere(r, col)
        for j, (tx, ty) in enumerate(trail[:-1]):
            ghost = sp.copy(); al = ghost.getchannel("A").point(lambda v, k=(j + 1)/len(trail): int(v*0.22*k))
            ghost.putalpha(al); img.alpha_composite(ghost, (int(tx - sp.width/2), int(ty - sp.height/2)))
        img.alpha_composite(sp, (int(x - sp.width/2), int(y - sp.height/2)))
        dr = ImageDraw.Draw(img)
        text_c(dr, 250, cfg["hook"], 66, stroke=6)
        text_c(dr, 345, f"Bounces: {b}", 40, fill=(200, 210, 230), stroke=4)
        cur = max([k for k, s0 in enumerate(starts) if s0 <= t] or [0])
        cid = next((c for c in ch if cur in c), ch[0])
        if t >= starts[0] - 0.1: draw_caption(dr, words, cid, cur if t >= starts[0] else -1)
        img.convert("RGB").save(f"{tmp}/f{i:05d}.png", compress_level=1)
    wav = cfg["out"] + ".wav"; audio(ev, len(fr), esc, wav, list(zip(sst, vlines)) if vlines else None)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", f"{tmp}/f%05d.png", "-i", wav,
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "19", "-preset", "veryfast",
                    "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", cfg["out"]], check=True)
    subprocess.run(["rm", "-rf", tmp, wav])
    json.dump({"seed": seed, "esc": esc, "bounces": len(ev)}, open(cfg["out"] + ".meta.json", "w"))
    print("done", cfg["out"])

if __name__ == "__main__":
    main(json.load(open(sys.argv[1])))
