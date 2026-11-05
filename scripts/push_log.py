#!/usr/bin/env python3
"""Commit + push appended JSON-array log files (data/history.json, data/long_topics.json) without merge conflicts.

  python scripts/push_log.py "log: NAME" data/history.json [data/long_topics.json ...]

Shorts and long-form runs both append to data/history.json; a plain `git pull --rebase` then conflicts on the array
tail. Instead: the entries this run added (present in the working file, absent from HEAD) are kept in memory, the
checkout is reset to the newest origin/main, the entries are appended to the fresh files, and the push is retried.
"""
import json, subprocess, sys, time


def git(*a, check=True):
    return subprocess.run(["git", *a], check=check, capture_output=True, text=True)


def load_head(path):
    r = git("show", f"HEAD:{path}", check=False)
    try:
        return json.loads(r.stdout) if r.returncode == 0 else []
    except Exception:
        return []


def key(e):
    return json.dumps(e, sort_keys=True, ensure_ascii=False)


def main(msg, files):
    new = {}
    for f in files:
        try:
            cur = json.load(open(f, encoding="utf-8"))
        except Exception:
            cur = []
        old = {key(e) for e in load_head(f)}
        new[f] = [e for e in cur if key(e) not in old]
    if not any(new.values()):
        print("nothing new to log")
        return 0
    for attempt in range(6):
        git("fetch", "-q", "origin", "main")
        git("reset", "-q", "--hard", "origin/main")
        for f, ents in new.items():
            try:
                cur = json.load(open(f, encoding="utf-8"))
            except Exception:
                cur = []
            have = {key(e) for e in cur}
            cur += [e for e in ents if key(e) not in have]
            with open(f, "w", encoding="utf-8") as fh:
                json.dump(cur, fh, ensure_ascii=False, indent=1)
                fh.write("\n")
        git("add", *files)
        if git("commit", "-q", "-m", msg, check=False).returncode != 0:
            print("nothing to commit")
            return 0
        r = git("push", "-q", "origin", "HEAD:main", check=False)
        if r.returncode == 0:
            print(f"pushed {msg} (attempt {attempt + 1})")
            return 0
        print(f"push rejected (attempt {attempt + 1}): {r.stderr.strip()[:200]}")
        time.sleep(4 + attempt * 6)
    print(f"::warning title=log push::could not push {msg} after 6 tries")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2:]))
