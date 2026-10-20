#!/usr/bin/env python3
"""Health guard + phone pings (ntfy.sh).
  python scripts/guard.py failed   -> ping the phone; if the previous run also failed, pause auto-posting
  python scripts/guard.py posted out/x.json -> ping the phone with the new Short's link
Phone: install the free 'ntfy' app and subscribe to the topic in NTFY_TOPIC.
Resume after a pause with Start on the dashboard (re-enables the workflow).
"""
import json, os, sys, urllib.request

REPO = os.environ.get("GITHUB_REPOSITORY", "sniff-yt/Bounce-Bhai-Shorts")
TOPIC = os.environ.get("NTFY_TOPIC", "bouncebhai-c4211392")
RUN = os.environ.get("GITHUB_RUN_ID", "")
TOKEN = os.environ.get("GITHUB_TOKEN", "")


def ping(title, msg, tags="", click=""):
    try:
        req = urllib.request.Request(f"https://ntfy.sh/{TOPIC}", data=msg.encode(), method="POST",
                                     headers={"Title": title.encode("ascii", "ignore").decode(), "Tags": tags,
                                              **({"Click": click} if click else {})})
        urllib.request.urlopen(req, timeout=15).read()
    except Exception as e:
        print("ntfy failed:", e)


def gh(path, method="GET"):
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}{path}", method=method,
                                 headers={"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        body = r.read()
        return json.loads(body) if body else {}


def failed():
    run_url = f"https://github.com/{REPO}/actions/runs/{RUN}"
    prev = None
    try:
        runs = gh("/actions/workflows/shorts.yml/runs?status=completed&per_page=5")["workflow_runs"]
        prev = next((r for r in runs if str(r["id"]) != RUN and r["conclusion"] != "cancelled"), None)
    except Exception as e:
        print("could not read past runs:", e)
    if prev and prev["conclusion"] == "failure":
        try:
            gh("/actions/workflows/shorts.yml/disable", "PUT")
            print("::warning title=guard::2 failed runs in a row: auto-posting PAUSED. Press Start on the dashboard to resume.")
            ping("Bounce Bhai paused", "2 runs failed in a row, so I paused auto-posting. Tap Start on the dashboard to resume.",
                 "rotating_light", run_url)
            return
        except Exception as e:
            print("could not pause:", e)
    ping("Bounce Bhai run failed", "This run failed. The fixer will look at it; the next run tries again.", "warning", run_url)


def posted(path):
    c = json.load(open(path, encoding="utf-8"))
    if c.get("video_id"):
        url = f"https://youtube.com/shorts/{c['video_id']}"
        ping("New Short posted", f"{c.get('yt_title', {}).get('hi_roman', c.get('title', ''))}\n{url}", "tada", url)


if __name__ == "__main__":
    {"failed": lambda: failed(), "posted": lambda: posted(sys.argv[2])}[sys.argv[1]]()
