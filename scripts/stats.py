#!/usr/bin/env python3
"""Write real channel numbers for the dashboard: python scripts/stats.py out/stats.json"""
import json, sys, time, datetime
from yt_client import youtube, CHANNEL

yt = youtube(check_channel=False)
ch = yt.channels().list(part="statistics,snippet,contentDetails", id=CHANNEL).execute()["items"][0]
st = ch["statistics"]
uploads = ch["contentDetails"]["relatedPlaylists"]["uploads"]
items = yt.playlistItems().list(part="contentDetails", playlistId=uploads, maxResults=12).execute().get("items", [])
ids = [i["contentDetails"]["videoId"] for i in items]
vids = []
if ids:
    for v in yt.videos().list(part="snippet,statistics,status", id=",".join(ids)).execute().get("items", []):
        s = v.get("statistics", {})
        vids.append({"id": v["id"], "title": v["snippet"]["title"], "published": v["snippet"]["publishedAt"],
                     "thumb": v["snippet"].get("thumbnails", {}).get("medium", {}).get("url"),
                     "views": int(s.get("viewCount", 0)), "likes": int(s.get("likeCount", 0)),
                     "comments": int(s.get("commentCount", 0)), "privacy": v["status"]["privacyStatus"]})
vids.sort(key=lambda v: v["published"], reverse=True)
out = {"channel": {"id": CHANNEL, "title": ch["snippet"]["title"], "handle": ch["snippet"].get("customUrl"),
                   "avatar": ch["snippet"]["thumbnails"].get("default", {}).get("url"),
                   "subscribers": int(st.get("subscriberCount", 0)), "hidden_subs": st.get("hiddenSubscriberCount"),
                   "views": int(st.get("viewCount", 0)), "videos": int(st.get("videoCount", 0))},
       "recent": vids, "updated": time.time(),
       "updated_iso": datetime.datetime.now(datetime.timezone.utc).isoformat()}
# keep a small history for the growth chart
try:
    old = json.load(open(sys.argv[1]))
    hist = old.get("history", [])
except Exception:
    hist = []
hist.append({"t": int(time.time()), "subs": out["channel"]["subscribers"], "views": out["channel"]["views"]})
out["history"] = hist[-500:]
json.dump(out, open(sys.argv[1], "w"), ensure_ascii=False, indent=1)
print(out["channel"])
