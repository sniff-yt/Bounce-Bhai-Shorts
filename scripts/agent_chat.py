#!/usr/bin/env python3
"""Chat with the code agent from the dashboard: you describe a problem in plain words, an LLM reads the
relevant code, patches it (scripts/, engine/, docs/ only), pushes to main and replies. The conversation lives in
chat.json on the orphan `data` branch so the dashboard can show it.

env: MESSAGE, GH_TOKEN, GITHUB_REPOSITORY, LLM keys (same as autofix.py)
"""
import json, os, re, subprocess, sys, time, urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from write_story import _post_json, extract_json   # noqa: E402


_MODELS = {}
def list_models(base, key):
    """Model ids a provider currently serves (cached). Providers retire models often, so pick from the live list."""
    if base not in _MODELS:
        import urllib.request
        try:
            r = urllib.request.Request(base + "/models", headers={"Authorization": f"Bearer {key}", "User-Agent": "bouncebhai-agent"})
            _MODELS[base] = [m["id"] for m in json.loads(urllib.request.urlopen(r, timeout=30).read())["data"]]
        except Exception as e:
            print("model list failed:", base, str(e)[:120], flush=True); _MODELS[base] = []
        print("models at", base, ":", len(_MODELS[base]), flush=True)
    return _MODELS[base]

def pick_models(ids, prefs):
    out = []
    for p in prefs:
        out += [i for i in ids if p in i.lower() and i not in out]
    return out

GROQ, NV = "https://api.groq.com/openai/v1", "https://integrate.api.nvidia.com/v1"
TEXT_PREFS = ["gpt-oss-120b", "kimi-k2", "qwen3", "llama-4-maverick", "deepseek-v", "gpt-oss-20b", "llama-3.3-70b", "llama-4-scout"]
VISION_PREFS = ["llama-4-maverick", "llama-4-scout", "qwen2.5-vl", "qwen3-vl", "vision", "gemma-3", "phi-4-multimodal", "nemotron-nano-vl", "-vl"]

REPO = os.environ.get("GITHUB_REPOSITORY", "sniff-yt/Bounce-Bhai-Shorts")
MSG = (os.environ.get("MESSAGE") or "").strip()[:2000]
ALLOWED = ("scripts/", "engine/", "docs/", "requirements.txt")
CHAT = "/tmp/data/chat.json"


def sh(*cmd, check=True, err=False, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if check and r.returncode:
        raise RuntimeError(f"{' '.join(cmd)} -> {r.stderr[-800:]}")
    return r.stdout + (r.stderr if err else "")


def load_chat():
    try:
        return json.load(open(CHAT))
    except Exception:
        return []


def save_chat(chat):
    os.makedirs(os.path.dirname(CHAT), exist_ok=True)
    json.dump(chat[-60:], open(CHAT, "w"), ensure_ascii=False, indent=1)


def llm(prompt, sysmsg="You are a careful senior Python engineer. Reply with strictly valid JSON only."):
    def oai(url, key, model, extra=None, limit=None):
        body = {"model": model, "temperature": 0.2, "max_tokens": 7000,
                "messages": [{"role": "system", "content": sysmsg},
                             {"role": "user", "content": prompt[-limit:] if limit else prompt}]}
        body.update(extra or {})
        raw = _post_json(url, {"Content-Type": "application/json", "Authorization": f"Bearer {key}",
                               "User-Agent": "bouncebhai-agent"}, body, 100)
        return extract_json(json.loads(raw)["choices"][0]["message"]["content"])
    tries = []
    if os.environ.get("GROQ_API_KEY"):
        k = os.environ["GROQ_API_KEY"]
        for m in pick_models(list_models(GROQ, k), TEXT_PREFS)[:4]:
            ex = {"reasoning_effort": "low"} if "gpt-oss" in m else None
            tries.append(("groq " + m, lambda m=m, ex=ex: oai(GROQ + "/chat/completions", k, m, extra=ex, limit=15000)))
    if os.environ.get("NVIDIA_API_KEY"):
        k2 = os.environ["NVIDIA_API_KEY"]
        for m in pick_models(list_models(NV, k2), TEXT_PREFS)[:3]:
            tries.append(("nvidia " + m, lambda m=m: oai(NV + "/chat/completions", k2, m)))
    if os.environ.get("NARA_API_KEY"):
        tries.append(("nara", lambda: oai("https://router.bynara.id/v1/chat/completions", os.environ["NARA_API_KEY"], "laguna-s-2.1")))
    errs = []
    for name, fn in tries:
        try:
            out = fn(); print("LLM:", name, flush=True); return out
        except Exception as e:
            d = e.read().decode()[:200] if isinstance(e, urllib.error.HTTPError) else str(e)[:200]
            errs.append(f"{name}: {d}"); print("LLM failed:", name, d, flush=True)
    raise RuntimeError("no AI model answered (" + " | ".join(errs)[:400] + ")")


def apply(edits):
    backup = {}
    for e in edits:
        p = e.get("path", "")
        if not p.startswith(ALLOWED) or ".." in p or not os.path.isfile(p):
            raise ValueError(f"edit to {p!r} is not allowed")
        cur = open(p, encoding="utf-8").read()
        backup.setdefault(p, cur)
        if cur.count(e["search"]) != 1:
            raise ValueError(f"search text found {cur.count(e['search'])}x in {p} (must be exactly once)")
        open(p, "w", encoding="utf-8").write(cur.replace(e["search"], e["replace"], 1))
    try:
        for p in backup:
            if p.endswith(".py"):
                sh(sys.executable, "-m", "py_compile", p)
            elif p.endswith(".sh"):
                sh("bash", "-n", p)
    except Exception:
        for p, t in backup.items():
            open(p, "w", encoding="utf-8").write(t)
        raise
    return list(backup)


OVERVIEW = """Project: automated YouTube Shorts for the channel Bounce Bhai (GitHub Actions, posts hourly at the IST hours in data/schedule.json).
scripts/make_short.sh runs everything. scripts/insights.py picks the format: "race" (engine/sim_race.py via
scripts/make_race.py: 3 balls race through a parkour course), "sim" (engine/sim_escape.py via scripts/make_sim.py:
a growing ball escapes a spinning ring with a gap), "promo" (game promo, scripts/promo.py), "story" (2D cartoon,
scripts/write_story.py + engine/render2d.py + scripts/finish.py). scripts/upload.py uploads to YouTube.
docs/index.html is the owner's web dashboard.
OWNER'S STRICT RULE: the channel posts ONLY "race", "sim" (ball escape) and the daily "promo" (Bhai Drive game) Shorts. Never re-enable stories,
never remove or replace either of these two formats, and keep every video under 60 seconds."""


SCHEDULE = "data/schedule.json"


def recent_videos(n=10):
    """Latest posted Shorts (history.json) with views from the data branch stats."""
    try:
        hist = [h for h in json.load(open("data/history.json", encoding="utf-8")) if h.get("video_id")]
    except Exception:
        hist = []
    views = {}
    try:
        for v in json.load(open("/tmp/data/stats.json")).get("videos", []):
            views[v.get("id")] = v.get("views")
    except Exception:
        pass
    out = []
    for h in hist[-n:][::-1]:
        out.append({"video_id": h["video_id"], "format": h.get("format", "story"), "title": h.get("title"),
                    "posted": h.get("date"), "views": views.get(h["video_id"]), "deleted": bool(h.get("deleted"))})
    return out


def load_schedule():
    try:
        return json.load(open(SCHEDULE))
    except Exception:
        return {"hours_ist": list(range(6, 23))}


def look_at_video(vid, videos):
    """Download the Short's workflow artifact, make a frame contact sheet and let a vision model describe it."""
    h = next((v for v in videos if v["video_id"] == vid), None)
    m = re.search(r"\d{8}_\d{4}", (h or {}).get("title") or "")
    if not m:
        return "(couldn't find that video's file)"
    name = f"short_{m.group(0)}"
    d = "/tmp/look"
    sh("rm", "-rf", d, check=False)
    r = subprocess.run(["gh", "run", "download", "--repo", REPO, "-n", name, "-D", d], capture_output=True, text=True)
    mp4 = os.path.join(d, f"{name}_final.mp4")
    if r.returncode or not os.path.isfile(mp4):
        return f"(the video file has expired or is missing: {r.stderr[-200:]})"
    facts = ""
    for extra in (f"{name}.mp4.json",):
        if os.path.isfile(os.path.join(d, extra)):
            facts += open(os.path.join(d, extra)).read()[:600]
    dur = sh("ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", mp4, check=False).strip()
    # measured checks that don't need an AI: frozen stretches (nothing moving) in the video
    fz = sh("ffmpeg", "-hide_banner", "-i", mp4, "-vf", "freezedetect=n=0.003:d=2", "-map", "0:v", "-f", "null", "-", check=False, err=True)
    frozen = re.findall(r"freeze_start: ([\d.]+).*?freeze_duration: ([\d.]+)", fz.replace("\n", " "))
    facts += "; frozen stretches (start s, length s): " + (", ".join(f"{float(a):.1f}+{float(b):.1f}" for a, b in frozen) or "none")
    sheet = "/tmp/look/sheet.jpg"
    sh("ffmpeg", "-v", "error", "-y", "-i", mp4, "-vf", "fps=1/1.5,scale=128:-1,tile=10x3", "-frames:v", "1",
       "-q:v", "4", sheet, check=False)
    if not os.path.isfile(sheet):
        return f"(couldn't read frames) duration {dur}s, render facts {facts}"
    import base64
    b64 = base64.b64encode(open(sheet, "rb").read()).decode()
    ask = ("This contact sheet shows one frame every 1.5 s of a YouTube Short (read left to right, top to bottom; "
           f"duration {dur}s). Render facts: {facts}. List every visible bug or quality problem precisely: dead time where "
           "nothing happens, things stuck, text cut off at the edges or overlapping, objects off screen, glitches, "
           "and say at what time (seconds) each one happens. Be concise.")
    body = {"model": "openai/gpt-4.1", "temperature": 0.2, "max_tokens": 900,
            "messages": [{"role": "user", "content": [{"type": "text", "text": ask},
                                                      {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]}]}
    seen, errs = None, []
    vis = []
    for env, base in (("GROQ_API_KEY", GROQ), ("NVIDIA_API_KEY", NV)):
        if os.environ.get(env):
            for m in pick_models(list_models(base, os.environ[env]), VISION_PREFS)[:3]:
                vis.append((m, base + "/chat/completions", os.environ[env]))
    for m, url, key in vis:
        raw = ""
        try:
            raw = _post_json(url, {"Content-Type": "application/json", "Accept": "application/json",
                                   "Authorization": f"Bearer {key}", "User-Agent": "bouncebhai-agent"}, dict(body, model=m), 60)
            seen = json.loads(raw)["choices"][0]["message"]["content"]
            print("vision:", m, flush=True); break
        except Exception as e:
            d = e.read().decode()[:200] if isinstance(e, urllib.error.HTTPError) else (str(e)[:100] + " | " + str(raw)[:150])
            errs.append(f"{m}: {d}"); print("vision failed:", m, d, flush=True)
    if not seen:
        seen = "(vision models failed: " + " ; ".join(errs)[:300] + ")"
    return f"duration {dur}s; render facts {facts}; what the frames show: {seen}"


def run_actions(actions, videos):
    """Things beyond code edits: delete / repost / change posting hours. Returns (done list, changed files)."""
    done, changed = [], []
    ids = {v["video_id"] for v in videos}
    for a in actions or []:
        t = a.get("type")
        if t == "delete" and a.get("video_id") in ids:
            sh("gh", "workflow", "run", "delete.yml", "--repo", REPO, "-f", f"video_id={a['video_id']}")
            done.append(f"deleting {a['video_id']}")
        elif t == "post" and a.get("format") in ("race", "sim", "promo"):
            sh("gh", "workflow", "run", "shorts.yml", "--repo", REPO, "-f", f"format={a['format']}")
            done.append(f"posting a new {a['format']} Short")
        elif t == "schedule":
            hrs = sorted({int(x) for x in a.get("hours_ist", []) if str(x).lstrip("-").isdigit() and 0 <= int(x) <= 23})
            if hrs:
                json.dump({"hours_ist": hrs, "note": "IST hours when a scheduled run may post (runs start ~:40)"},
                          open(SCHEDULE, "w"), indent=1)
                changed.append(SCHEDULE)
                done.append("posting hours (IST) now " + ", ".join(map(str, hrs)))
    return done, changed


def main():
    chat = load_chat()
    chat.append({"role": "user", "text": MSG, "ts": time.time()})
    save_chat(chat)
    history = "\n".join(f"{m['role'].upper()}: {m['text'][:600]}" for m in chat[-9:-1]) or "(new conversation)"
    files_list = [f for f in sh("git", "ls-files").split() if f.startswith(ALLOWED) and not f.startswith("docs/game/")]
    videos = recent_videos()
    sched = load_schedule()
    world = (f"Latest Shorts (newest first, views may lag): {json.dumps(videos, ensure_ascii=False)}\n"
             f"Posting hours (IST, one Short per listed hour; YouTube caps ~10-13 uploads/day): {sched.get('hours_ist')}")

    pick = llm(f"""{OVERVIEW}

Recent chat:
{history}

Owner's new message: {MSG}

Repo files you may read: {', '.join(files_list)}
{world}

Which files (at most 4) do you need to read to answer or fix this? If he is talking about a specific video
(e.g. "the latest", "the one with 693 views", "this short has bugs"), set "look" to its video_id so you can watch it.
Return {{"files": ["..."], "look": "<video_id or null>"}}""")
    seen = LOOKED = ""
    if pick.get("look"):
        seen = f"\nYou watched video {pick['look']}: " + look_at_video(str(pick["look"]), videos)
        print("look:", seen[:1500], flush=True)
    LOOKED = seen
    paths = [p for p in pick.get("files", []) if p in files_list][:4] or ["scripts/make_short.sh"]
    budget, files = 80000, {}
    for p in paths:
        t = open(p, encoding="utf-8").read()
        if len(t) <= budget:
            files[p] = t; budget -= len(t)

    prompt = f"""{OVERVIEW}

You are the owner's code agent. He describes problems with his videos or the pipeline in plain (often Hinglish)
words. Understand what he sees, find the cause in the code, and fix it with the smallest safe change.
If he only asks a question, answer it with no edits. If you are not sure what he means, ask ONE short question.

Rules:
- Only edit: {', '.join(files)}. Never workflows or secrets.
- Besides code edits you can take actions (list them in "actions"):
  {{"type": "delete", "video_id": "..."}} only when he clearly asks to remove/delete a video;
  {{"type": "post", "format": "race"|"sim"|"promo"}} to post a fresh Short now (e.g. a repost after a fix);
  {{"type": "schedule", "hours_ist": [7, 8, ...]}} to change posting times (IST hours 0-23, one post per hour listed).
- If he says a video has bugs: use what you saw in it, fix the cause in the engine code, and if he asked, delete + repost.
- Each edit replaces one exact snippet: "search" copied verbatim from the file, appearing exactly once.
- Keep everything else working. No big refactors.
- "reply": 1-3 short friendly sentences to the owner in simple English, saying what was wrong and what you changed
  (or your answer/question). No code in the reply.
- "test_now": true if he should see a fresh Short made with the fix right away.
Return JSON: {{"reply": "...", "summary": "commit title under 60 chars", "edits": [{{"path": "...", "search": "...", "replace": "..."}}],
 "actions": [], "test_now": false}}

{world}{seen}

Recent chat:
{history}

Owner's new message: {MSG}

Files:
""" + "\n\n".join(f"===== {p} =====\n{t}" for p, t in files.items())

    plan, changed = None, None
    for attempt in range(2):
        plan = llm(prompt)
        if not plan.get("edits"):
            break
        try:
            changed = apply(plan["edits"]); break
        except Exception as e:
            print("patch rejected:", e, flush=True)
            prompt += f"\n\nYour previous patch was rejected: {e}. Copy search text exactly and try again."
    plan = plan or {}
    if not plan.get("reply"):
        try:
            again = llm(prompt + '\n\nYour last answer had no "reply" field. Answer again with the exact JSON shape asked for, '
                        'including "reply" (what you saw in the video / what you did, in simple English).')
            if again.get("reply"):
                plan = again if not changed else dict(plan, reply=again["reply"])
        except Exception as e:
            print("retry failed:", e, flush=True)
    print("plan:", json.dumps(plan, ensure_ascii=False)[:2000], flush=True)
    # code edits first, so a repost uses the fixed code
    if changed:
        sh("git", "config", "user.name", "bouncebhai-agent")
        sh("git", "config", "user.email", "bot@users.noreply.github.com")
        sh("git", "add", *changed)
        sh("git", "commit", "-m", "agent: " + re.sub(r"\s+", " ", plan.get("summary") or "fix from chat")[:70], "-m", f"Owner said: {MSG[:300]}")
        sh("git", "pull", "--rebase", "-q", "origin", "main")
        sh("git", "push", "-q", "origin", "HEAD:main")
    done, sched_files = run_actions(plan.get("actions"), videos)
    if sched_files:
        sh("git", "config", "user.name", "bouncebhai-agent")
        sh("git", "config", "user.email", "bot@users.noreply.github.com")
        sh("git", "add", *sched_files)
        sh("git", "commit", "-m", "agent: posting hours", check=False)
        sh("git", "pull", "--rebase", "-q", "origin", "main")
        sh("git", "push", "-q", "origin", "HEAD:main")
    reply = plan.get("reply")
    if not reply and (done or changed):
        reply = "Done: " + "; ".join(done or ["code updated"]) + "."
    if not reply and LOOKED:
        reply = "I watched it. " + LOOKED.split("what the frames show:", 1)[-1].strip()[:600]
    if not reply:
        reply = "I didn't get that. Tell me which video (or its views) and what looks wrong in it."
    if done and plan.get("reply"):
        reply += " (" + "; ".join(done) + ")"
    entry = {"role": "agent", "text": reply, "ts": time.time()}
    if plan and plan.get("edits") and not changed:
        entry["text"] = reply + " (My patch didn't apply cleanly, so nothing was changed. Try telling me again.)"
    if changed:
        title = re.sub(r"\s+", " ", plan.get("summary") or "fix from chat")[:70]
        entry["commit"] = sh("git", "rev-parse", "--short", "HEAD").strip()
        entry["files"] = changed
        print("::notice title=agent::" + title)
        if plan.get("test_now") and not any(d.startswith("posting a new") for d in done):
            sh("gh", "workflow", "run", "shorts.yml", "--repo", REPO, check=False)
            entry["text"] += " I've started a fresh Short so you can check it."
    chat.append(entry)
    save_chat(chat)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        chat = load_chat()
        chat.append({"role": "agent", "text": f"Something broke on my side: {str(e)[:300]}", "ts": time.time()})
        save_chat(chat)
        print("::error title=agent::" + str(e).replace("\n", " ")[:800])
