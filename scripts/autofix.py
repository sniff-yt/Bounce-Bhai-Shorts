#!/usr/bin/env python3
"""Bounce Bhai fixer agent: reads a failed Actions run, asks an LLM for a minimal patch,
checks it, pushes it to main and starts a fresh run.

env: RUN_ID, GH_TOKEN (GITHUB_TOKEN), GITHUB_REPOSITORY, LLM keys (GROQ/NVIDIA/NARA/GEMINI; GitHub Models as fallback)
It never touches .github/workflows (the Actions token is not allowed to) or secrets.
"""
import json, os, re, subprocess, sys, time, urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from write_story import _post_json, extract_json   # noqa: E402

RUN = os.environ["RUN_ID"]
REPO = os.environ.get("GITHUB_REPOSITORY", "sniff-yt/Bounce-Bhai-Shorts")
MAX_FIXES_6H = int(os.environ.get("AUTOFIX_MAX_6H", "3"))
ALLOWED = ("scripts/", "engine/", "requirements.txt", "docs/")
SUMMARY = os.environ.get("GITHUB_STEP_SUMMARY", "/dev/null")


def sh(*cmd, check=True, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if check and r.returncode:
        raise RuntimeError(f"{' '.join(cmd)} -> {r.stderr[-800:]}")
    return r.stdout


def say(msg):
    print(msg, flush=True)
    with open(SUMMARY, "a") as f:
        f.write(msg + "\n\n")


def notice(title, msg):
    print(f"::notice title={title}::" + msg.replace("\n", " ")[:900], flush=True)


# ---------- 1. what failed ----------
run = json.loads(sh("gh", "api", f"repos/{REPO}/actions/runs/{RUN}"))
wf_name = run.get("name", "")
logs = sh("gh", "run", "view", RUN, "--repo", REPO, "--log-failed", check=False)
logs = "\n".join(re.sub(r"^\S+\t\S+\t\S+Z ", "", ln) for ln in logs.splitlines())
tail = logs[-14000:]
jobs = json.loads(sh("gh", "api", f"repos/{REPO}/actions/runs/{RUN}/jobs"))["jobs"]
notes = []
for j in jobs:
    for a in json.loads(sh("gh", "api", f"repos/{REPO}/check-runs/{j['id']}/annotations", check=False) or "[]"):
        notes.append(f"[{a.get('annotation_level')}] {a.get('title') or ''}: {a.get('message', '')[:400]}")
    for st in j.get("steps", []):
        if st.get("conclusion") == "failure":
            notes.append(f"FAILED STEP: {j['name']} / {st['name']}")
say(f"## Fixer agent\nRun [{RUN}]({run.get('html_url')}) of **{wf_name}** failed.")

# ---------- 2. loop guard ----------
since = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 6 * 3600))
recent = json.loads(sh("gh", "api", f"repos/{REPO}/commits?sha=main&since={since}&per_page=50"))
fixes = [c for c in recent if c["commit"]["message"].startswith("autofix:")]
if len(fixes) >= MAX_FIXES_6H:
    say(f"Already pushed {len(fixes)} fixes in 6 hours; stopping so it can't loop. A human look is needed.")
    notice("fixer", "Fix limit reached; not patching again.")
    sys.exit(0)

# ---------- 3. context files ----------
paths = ["scripts/make_short.sh"]
for p in re.findall(r"((?:scripts|engine)/[\w./-]+\.(?:py|sh))", tail + "\n".join(notes)):
    p = p.split("/Bounce-Bhai-Shorts/")[-1]
    if os.path.isfile(p) and p not in paths:
        paths.append(p)
for p in re.findall(r'File "[^"]*?/((?:scripts|engine)/[\w/]+\.py)"', tail):
    if os.path.isfile(p) and p not in paths:
        paths.insert(1, p)
if wf_name == "Post my video":
    paths += [p for p in ("scripts/upload_own.py", "scripts/yt_client.py") if p not in paths]
if wf_name == "Dashboard stats":
    paths += [p for p in ("scripts/stats.py", "scripts/yt_client.py") if p not in paths]
budget, files = 70000, {}
for p in paths[:6]:
    txt = open(p, encoding="utf-8").read()
    if len(txt) > budget:
        continue
    files[p] = txt; budget -= len(txt)

PROMPT = """You are the on-call engineer for an automated YouTube Shorts pipeline (GitHub Actions, Python).
A run failed. Find the root cause and return the SMALLEST safe fix.

Rules:
- Only edit these files (exact paths): {paths}
- Never edit workflow files or secrets. If the cause is outside code (GitHub/YouTube/LLM outage, network,
  rate limit, quota, timeout from a slow runner) answer kind "transient" with no edits.
- If the fix needs a human (missing secret, expired login/token, quota), answer kind "human" with no edits.
- Each edit replaces one exact snippet: "search" must be copied verbatim from the file and appear exactly once.
- Keep behaviour the same apart from the fix. No refactors.
Return JSON: {{"kind": "code"|"transient"|"human", "diagnosis": "2-3 plain sentences",
 "summary": "commit title under 60 chars", "edits": [{{"path": "...", "search": "...", "replace": "..."}}]}}

Workflow: {wf}
Failed steps / annotations:
{notes}

Log tail:
{tail}

Files:
{files}
"""


def ask(prompt):
    errs = []
    sysmsg = "You fix Python/bash CI failures. Reply with strictly valid JSON only."

    def oai(url, key, model, extra=None, limit=None):
        body = {"model": model, "temperature": 0.1, "max_tokens": 6000,
                "messages": [{"role": "system", "content": sysmsg}, {"role": "user", "content": prompt[:limit] if limit else prompt}]}
        body.update(extra or {})
        raw = _post_json(url, {"Content-Type": "application/json", "Authorization": f"Bearer {key}",
                               "User-Agent": "bouncebhai-fixer"}, body, 180)
        return extract_json(json.loads(raw)["choices"][0]["message"]["content"])

    tries = []
    if os.environ.get("GROQ_API_KEY"):
        tries.append(("Groq", lambda: oai("https://api.groq.com/openai/v1/chat/completions", os.environ["GROQ_API_KEY"],
                                          os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b"))))
    if os.environ.get("NVIDIA_API_KEY"):
        for m in ("qwen/qwen3-coder-480b-a35b-instruct", "meta/llama-3.3-70b-instruct"):
            tries.append((f"NVIDIA {m}", lambda m=m: oai("https://integrate.api.nvidia.com/v1/chat/completions",
                                                          os.environ["NVIDIA_API_KEY"], m)))
    if os.environ.get("NARA_API_KEY"):
        tries.append(("Nara", lambda: oai("https://router.bynara.id/v1/chat/completions", os.environ["NARA_API_KEY"],
                                          "laguna-s-2.1")))
    if os.environ.get("GH_TOKEN"):
        tries.append(("GitHub Models", lambda: oai("https://models.github.ai/inference/chat/completions",
                                                   os.environ["GH_TOKEN"], "openai/gpt-4.1", limit=28000)))
    for name, fn in tries:
        try:
            out = fn(); print("LLM:", name, flush=True); return out
        except Exception as e:
            detail = e.read().decode()[:300] if isinstance(e, urllib.error.HTTPError) else str(e)[:300]
            errs.append(f"{name}: {detail}"); print("LLM failed:", name, detail, flush=True)
    raise SystemExit("No LLM answered: " + " | ".join(errs))


def apply(edits):
    backup = {}
    for e in edits:
        p = e.get("path", "")
        if not p.startswith(ALLOWED) or ".." in p or not os.path.isfile(p):
            raise ValueError(f"edit to {p!r} is not allowed")
        txt = backup.get(p) or open(p, encoding="utf-8").read()
        backup.setdefault(p, txt)
        cur = open(p, encoding="utf-8").read()
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


ctx = dict(paths=", ".join(files), wf=wf_name, notes="\n".join(notes)[-4000:] or "(none)", tail=tail,
           files="\n\n".join(f"===== {p} =====\n{t}" for p, t in files.items()))
prompt = PROMPT.format(**ctx)
plan, changed = None, None
for attempt in range(2):
    plan = ask(prompt)
    kind = plan.get("kind")
    if kind != "code" or not plan.get("edits"):
        break
    try:
        changed = apply(plan["edits"]); break
    except Exception as e:
        print("patch rejected:", e, flush=True)
        prompt += f"\n\nYour previous patch was rejected: {e}. Copy search text exactly from the files and try again."

diag = (plan or {}).get("diagnosis", "no diagnosis")
say(f"**Diagnosis:** {diag}")
if changed:
    title = re.sub(r"\s+", " ", plan.get("summary") or "fix failed run")[:70]
    sh("git", "config", "user.name", "bouncebhai-fixer")
    sh("git", "config", "user.email", "bot@users.noreply.github.com")
    sh("git", "add", *changed)
    sh("git", "commit", "-m", f"autofix: {title}", "-m", f"{diag}\n\nFailed run: {run.get('html_url')}")
    sh("git", "pull", "--rebase", "-q", "origin", "main")
    sh("git", "push", "-q", "origin", "HEAD:main")
    say(f"Pushed fix **{title}** ({', '.join(changed)}).")
    notice("fixer", f"Fixed: {title}. {diag}")
    if wf_name == "Bounce Bhai Shorts":
        sh("gh", "workflow", "run", "shorts.yml", "--repo", REPO, check=False)
        say("Started a fresh Short to test the fix.")
    else:
        sh("gh", "run", "rerun", RUN, "--repo", REPO, check=False)
elif (plan or {}).get("kind") == "transient":
    say("Looks temporary (not a code bug). Re-running the failed run once.")
    notice("fixer", f"Temporary problem, re-running. {diag}")
    if int(run.get("run_attempt", 1)) < 2:
        sh("gh", "run", "rerun", RUN, "--repo", REPO, check=False)
else:
    say("This needs you (no safe code fix).")
    notice("fixer", f"Needs a human: {diag}")
