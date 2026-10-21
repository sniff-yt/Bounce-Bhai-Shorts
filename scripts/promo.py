#!/usr/bin/env python3
"""Bhai Drive promo Short: record real gameplay from docs/game/play in headless Chrome (frame-exact virtual time),
then cut it with a hook, feature captions, an end card and the game's own music.
usage: python scripts/promo.py out/short_x.json      (json from scripts/make_promo.py)
needs: playwright + chromium (CHROME=/path to use a system browser), ffmpeg, Pillow
"""
import json, os, random, subprocess, sys, shutil
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAME = os.path.join(ROOT, "docs", "game", "play")
W, H, FPS = 1080, 1920, 30
LILITA = os.path.join(GAME, "fonts", "Lilita.ttf")

INIT = """
(() => {
  let q = [], now = 1000;
  window.requestAnimationFrame = cb => { q.push(cb); return q.length; };
  window.cancelAnimationFrame = () => {};
  performance.now = () => now;
  let s = %d; Math.random = () => { s = (s * 16807) %% 2147483647; return (s - 1) / 2147483646; };
  window.__step = (n) => { for (let i = 0; i < n; i++) { now += 1000/30; const c = q; q = []; c.forEach(f => { try { f(now); } catch(e) {} }); } };
})();
"""


def record(tmp, seed, levels):
    from playwright.sync_api import sync_playwright
    clips = {}

    def clip(page, name, seconds, before=None, each=None):
        if before:
            page.evaluate(before)
        page.evaluate("__step(3)")
        path = f"{tmp}/{name}.mp4"
        ff = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "image2pipe", "-framerate", str(FPS), "-i", "-",
                               "-vf", f"scale={W}:{H}:flags=lanczos", "-c:v", "libx264", "-crf", "15", "-preset", "fast",
                               "-pix_fmt", "yuv420p", path], stdin=subprocess.PIPE)
        for i in range(int(seconds * FPS)):
            if each:
                page.evaluate(each, i)
            page.evaluate("__step(1)")
            ff.stdin.write(page.screenshot(type="jpeg", quality=93))
        ff.stdin.close(); ff.wait()
        clips[name] = path
        print("recorded", name, flush=True)

    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=os.environ.get("CHROME") or None, args=["--mute-audio"])
        page = b.new_page(viewport={"width": 432, "height": 768}, device_scale_factor=2.5)
        page.add_init_script(INIT % seed)
        page.goto("file://" + os.path.join(GAME, "index.html"))
        page.wait_for_timeout(1500)
        page.evaluate("__step(90)")
        clip(page, "menu", 3.2)
        clip(page, "free", 9.5, before="Game.start('free'); Drive.load(TOWN, true);",
             each="i => { wheelDeg = CTRL.wheel * WHEEL_MAX; if (i === 2) Controls.sync(); }")
        for k in levels:
            clip(page, f"park{k}", 2.4, before=f"Game.quit(); Game.start('park', {k});")
        b.close()
    return clips


def font(sz):
    try:
        return ImageFont.truetype(LILITA, sz)
    except Exception:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", sz)


def wrap(dr, text, f, maxw):
    lines, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if cur and dr.textlength(t, font=f) > maxw:
            lines.append(cur); cur = w
        else:
            cur = t
    return lines + ([cur] if cur else [])


def overlay(path, text, y, size=96, fill=(255, 255, 255), box=None):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img); f = font(size)
    lines = wrap(dr, text, f, 960)
    lh = int(size * 1.12)
    if box:
        top = y - lh // 2 - 26; bot = y + lh * (len(lines) - 1) + lh // 2 + 26
        dr.rounded_rectangle([60, top, W - 60, bot], 36, fill=box, outline=(43, 42, 51), width=8)
    for i, ln in enumerate(lines):
        dr.text((W // 2, y + i * lh), ln, font=f, fill=fill, anchor="mm", stroke_width=0 if box else 10,
                stroke_fill=(20, 20, 26))
    img.save(path)


def end_card(path, icon, lines):
    img = Image.new("RGB", (W, H), (244, 236, 220))
    dr = ImageDraw.Draw(img)
    try:
        ic = Image.open(icon).convert("RGBA").resize((300, 300))
        img.paste(ic, (W // 2 - 150, 420), ic)
    except Exception:
        pass
    dr.text((W // 2, 860), "Bhai Drive", font=font(150), fill=(43, 42, 51), anchor="mm")
    dr.text((W // 2, 975), "by Bounce Bhai", font=font(64), fill=(110, 105, 120), anchor="mm")
    dr.rounded_rectangle([110, 1110, W - 110, 1290], 40, fill=(247, 183, 49), outline=(43, 42, 51), width=8)
    dr.text((W // 2, 1200), lines[0], font=font(92), fill=(43, 42, 51), anchor="mm")
    for i, ln in enumerate(lines[1:]):
        dr.text((W // 2, 1400 + i * 90), ln, font=font(66), fill=(43, 42, 51), anchor="mm")
    img.save(path)


def main(cfg_path):
    c = json.load(open(cfg_path, encoding="utf-8"))
    rng = random.Random(c["seed"])
    tmp = c["out"] + ".promo"; shutil.rmtree(tmp, ignore_errors=True); os.makedirs(tmp)
    levels = rng.sample(range(12), 2)
    clips = record(tmp, c["seed"], levels)

    overlay(f"{tmp}/o_hook.png", c["hook"], 540, 100, fill=(255, 255, 255), box=(43, 42, 51))
    overlay(f"{tmp}/o_free.png", c["line_free"], 540, 84, fill=(43, 42, 51), box=(255, 255, 255))
    overlay(f"{tmp}/o_park.png", c["line_park"], 540, 84, fill=(43, 42, 51), box=(247, 183, 49))
    end_card(f"{tmp}/end.png", os.path.join(ROOT, "docs", "game", "icon.png"), c["end_lines"])

    # action from frame 0 (hook over the drive), then features, then puzzle lots, menu, end card
    segs = [(clips["free"], f"{tmp}/o_hook.png", 0.0, 3.0), (clips["free"], f"{tmp}/o_free.png", 3.0, 9.3)]
    segs += [(clips[f"park{k}"], f"{tmp}/o_park.png", 0.0, 2.2) for k in levels]
    segs += [(clips["menu"], None, 0.0, 2.0)]
    args, fc, n = ["ffmpeg", "-v", "error", "-y"], [], 0
    blank = f"{tmp}/o_none.png"; Image.new("RGBA", (W, H), (0, 0, 0, 0)).save(blank)
    for i, (v, o, a, b) in enumerate(segs):
        args += ["-i", v, "-i", o or blank]
        fc.append(f"[{2*i}:v]trim={a}:{b},setpts=PTS-STARTPTS[v{i}];[v{i}][{2*i+1}:v]overlay=0:0,format=yuv420p,setsar=1[s{i}]")
        n += 1
    ei = 2 * len(segs)
    args += ["-loop", "1", "-t", "3.2", "-framerate", str(FPS), "-i", f"{tmp}/end.png"]
    fc.append(f"[{ei}:v]format=yuv420p,setsar=1,fade=in:st=0:d=0.25[s{n}]")
    n += 1
    music = os.path.join(GAME, "music", f"t{rng.randrange(6)}.mp3")
    args += ["-i", music]
    total = sum(b - a for _, _, a, b in segs) + 3.2
    fc.append("".join(f"[s{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[vout]")
    fc.append(f"[{ei+1}:a]atrim=0:{total},afade=t=in:d=0.3,afade=t=out:st={total-1.5}:d=1.5,loudnorm=I=-14:TP=-1.5[aout]")
    final = c["out"].replace(".mp4", "_final.mp4")
    args += ["-filter_complex", ";".join(fc), "-map", "[vout]", "-map", "[aout]", "-r", str(FPS),
             "-c:v", "libx264", "-crf", "17", "-preset", "medium", "-c:a", "aac", "-b:a", "192k",
             "-movflags", "+faststart", "-t", f"{total:.2f}", final]
    subprocess.run(args, check=True)
    shutil.rmtree(tmp, ignore_errors=True)
    print("promo:", final, f"{total:.1f}s", flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
