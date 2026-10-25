#!/usr/bin/env python3
"""Chat with the code agent from the dashboard: you describe a problem in plain words, an LLM reads the
relevant code, patches it (scripts/, engine/, docs/ only), pushes to main and replies. The conversation lives in
chat.json on the orphan `data` branch so the dashboard can show it.

env: MESSAGE, GH_TOKEN, GITHUB_REPOSITORY, LLM keys (same as autofix.py)
"""
import json, os, re, subprocess, sys, time, urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from write_story import _post_json, extract_json   # noqa: E402

REPO = os.environ.get("GITHUB_REPOSITORY", "sniff-yt/Bounce-Bhai-Shorts")
MSG = (os.environ.get("MESSAGE") or "").strip()[:2000]
ALLOWED = ("scripts/", "engine/", "docs/", "requirements.txt")
CHAT = "/tmp/data/chat.json"


def sh(*cmd, check=True, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if check and r.returncode:
        raise RuntimeError(f"{' '.join(cmd)} -> {r.stderr[-800:]}")
    return r.stdout


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
                               "User-Agent": "bouncebhai-agent"}, body, 240)
        return extract_json(json.loads(raw)["choices"][0]["message"]["content"])
    tries = []
    if os.environ.get("NVIDIA_API_KEY"):
        for m in ("moonshotai/kimi-k2.6", "deepseek-ai/deepseek-v4.1-flash", "mistralai/mistral-large-2-instruct"):
            tries.append((m, lambda m=m: oai("https://integrate.api.nvidia.com/v1/chat/completions", os.environ["NVIDIA_API_KEY"], m)))
    if os.environ.get("GROQ_API_KEY"):
        tries.append(("groq", lambda: oai("https://api.groq.com/openai/v1/chat/completions", os.environ["GROQ_API_KEY"],
                                          "openai/gpt-oss-120b", extra={"reasoning_effort": "low"}, limit=24000)))
        tries.append(("groq llama", lambda: oai("https://api.groq.com/openai/v1/chat/completions", os.environ["GROQ_API_KEY"],
                                                "llama-3.3-70b-versatile", limit=20000)))
    if os.environ.get("NARA_API_KEY"):
        tries.append(("nara", lambda: oai("https://router.bynara.id/v1/chat/completions", os.environ["NARA_API_KEY"], "laguna-s-2.1")))
    if os.environ.get("GH_TOKEN"):
        tries.append(("github models", lambda: oai("https://models.github.ai/inference/chat/completions",
                                                   os.environ["GH_TOKEN"], "openai/gpt-4.1", limit=28000)))
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


OVERVIEW = """Project: automated YouTube Shorts for the channel Bounce Bhai (GitHub Actions, posts ~5x/day).
scripts/make_short.sh runs everything. scripts/insights.py picks the format: "race" (engine/sim_race.py via
scripts/make_race.py: 3 balls race through a parkour course), "sim" (engine/sim_escape.py via scripts/make_sim.py:
a growing ball escapes a spinning ring with a gap), "promo" (game promo, scripts/promo.py), "story" (2D cartoon,
scripts/write_story.py + engine/render2d.py + scripts/finish.py). scripts/upload.py uploads to YouTube.
docs/index.html is the owner's web dashboard.
OWNER'S STRICT RULE: the channel posts ONLY "race" and "sim" (ball escape) Shorts. Never re-enable stories or promos,
never remove or replace either of these two formats, and keep every video under 60 seconds."""


def main():
    chat = load_chat()
    chat.append({"role": "user", "text": MSG, "ts": time.time()})
    save_chat(chat)
    history = "\n".join(f"{m['role'].upper()}: {m['text'][:600]}" for m in chat[-9:-1]) or "(new conversation)"
    files_list = [f for f in sh("git", "ls-files").split() if f.startswith(ALLOWED) and not f.startswith("docs/game/")]

    pick = llm(f"""{OVERVIEW}

Recent chat:
{history}

Owner's new message: {MSG}

Repo files you may read: {', '.join(files_list)}
Which files (at most 4) do you need to read to answer or fix this? Return {{"files": ["..."]}}""")
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
- Each edit replaces one exact snippet: "search" copied verbatim from the file, appearing exactly once.
- Keep everything else working. No big refactors.
- "reply": 1-3 short friendly sentences to the owner in simple English, saying what was wrong and what you changed
  (or your answer/question). No code in the reply.
- "test_now": true if he should see a fresh Short made with the fix right away.
Return JSON: {{"reply": "...", "summary": "commit title under 60 chars", "edits": [{{"path": "...", "search": "...", "replace": "..."}}],
 "test_now": false}}

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
    reply = (plan or {}).get("reply") or "Sorry, I couldn't work that out. Can you describe it a bit more?"
    entry = {"role": "agent", "text": reply, "ts": time.time()}
    if plan and plan.get("edits") and not changed:
        entry["text"] = reply + " (My patch didn't apply cleanly, so nothing was changed. Try telling me again.)"
    if changed:
        title = re.sub(r"\s+", " ", plan.get("summary") or "fix from chat")[:70]
        sh("git", "config", "user.name", "bouncebhai-agent")
        sh("git", "config", "user.email", "bot@users.noreply.github.com")
        sh("git", "add", *changed)
        sh("git", "commit", "-m", f"agent: {title}", "-m", f"Owner said: {MSG[:300]}")
        sh("git", "pull", "--rebase", "-q", "origin", "main")
        sh("git", "push", "-q", "origin", "HEAD:main")
        entry["commit"] = sh("git", "rev-parse", "--short", "HEAD").strip()
        entry["files"] = changed
        print("::notice title=agent::" + title)
        if plan.get("test_now"):
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
