#!/usr/bin/env python3
"""Fan-named balls: put 3 recent commenters' names on the race balls (or the escape ball).
Reads the latest comments on the channel (YouTube Data API, same token as upload.py) and writes cfg["names"].
Prefers people whose name wasn't on a ball recently. Never fails the run: on any error the balls keep their colours.
usage: python scripts/fan_names.py out/short_x.json
"""
import json, os, random, re, sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
BAD = re.compile(r"(http|www\.|\.com|sex|porn|fuck|bitch|chut|madar|bhosd|lund|gand|randi|nigg)", re.I)


def clean(name):
    n = re.sub(r"^@", "", name or "").strip()
    n = re.sub(r"-[a-z0-9]{2,5}$", "", n)            # auto handles like @user-xy7k -> user
    n = re.sub(r"[^A-Za-z0-9_ .]", "", n).strip(" ._")
    if not n or BAD.search(n) or len(n) < 3: return None
    n = n.split(" ")[0] if len(n) > 12 else n
    return n[:12].upper()


def main(path):
    cfg = json.load(open(path, encoding="utf-8"))
    need = 3 if cfg.get("format") == "race" else 1
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from yt_client import youtube, CHANNEL
        yt = youtube(check_channel=False)
        r = yt.commentThreads().list(part="snippet", allThreadsRelatedToChannelId=CHANNEL, maxResults=100,
                                     order="time", textFormat="plainText").execute()
        names = []
        for it in r.get("items", []):
            s = it["snippet"]["topLevelComment"]["snippet"]
            if s.get("authorChannelId", {}).get("value") == CHANNEL: continue
            n = clean(s.get("authorDisplayName"))
            if n and n not in names: names.append(n)
        hist = json.load(open(os.path.join(ROOT, "data", "history.json"), encoding="utf-8"))
        used = {n for h in hist[-12:] for n in (h.get("names") or [])}
        fresh = [n for n in names if n not in used]
        pool = fresh if len(fresh) >= need else []
        if not pool:
            print(f"fan names: only {len(fresh)} new commenters, balls keep their colours"); return
        pick = random.sample(pool[:30], need)
        cfg["names"] = pick
        tag = ", ".join(pick)
        cfg["comment"] = (cfg.get("comment", "") + f"\n🏷️ Aaj ki balls: {tag}! Comment karo, agli baar tumhara naam ball pe hoga 👇").strip()
        json.dump(cfg, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("fan names:", tag)
    except Exception as e:
        print("fan names skipped:", str(e)[:200])


if __name__ == "__main__":
    main(sys.argv[1])
