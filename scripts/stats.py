#!/usr/bin/env python3
"""Write real channel numbers for the dashboard: python scripts/stats.py out/stats.json"""
import json, os, sys, time, datetime
from google.auth.exceptions import RefreshError
from yt_client import youtube, CHANNEL

try:
    yt = youtube(check_channel=False)
    yt.channels().list(part="id", id=CHANNEL).execute()
except RefreshError as e:
    # Expired/revoked YouTube sign-in: no code change can fix this, it needs a new Google consent
    # (run the "YouTube sign-in (phone friendly)" workflow). Keep the old numbers, flag it, don't fail
    # (a failure here only makes the Fixer agent rewrite the auth code).
    try:
        old = json.load(open(sys.argv[1]))
    except Exception:
        old = {}
    old["auth_error"] = "YouTube sign-in expired or revoked (" + str(e)[:120] + "). Re-run the YouTube sign-in workflow."
    old["auth_error_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    os.makedirs(os.path.dirname(sys.argv[1]) or ".", exist_ok=True)
    json.dump(old, open(sys.argv[1], "w"), ensure_ascii=False, indent=1)
    print("::error title=youtube_signin_expired::YouTube refresh token expired or revoked - run the 'YouTube sign-in (phone friendly)' workflow (step 1, then step 2 with the code).")
    sys.exit(0)
ch = yt.channels().list(part="statistics,snippet,contentDetails", id=CHANNEL).execute()["items"][0]
st = ch["statistics"]
uploads = ch["contentDetails"]["relatedPlaylists"]["uploads"]
items = yt.playlistItems().list(part="contentDetails", playlistId=uploads, maxResults=50).execute().get("items", [])
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
       "recent": vids[:12], "videos": vids, "updated": time.time(),
       "updated_iso": datetime.datetime.now(datetime.timezone.utc).isoformat()}
# keep a small history for the growth chart
try:
    old = json.load(open(sys.argv[1]))
    hist = old.get("history", [])
except Exception:
    hist = []
hist.append({"t": int(time.time()), "subs": out["channel"]["subscribers"], "views": out["channel"]["views"]})
out["history"] = hist[-500:]
os.makedirs(os.path.dirname(sys.argv[1]) or ".", exist_ok=True)
json.dump(out, open(sys.argv[1], "w"), ensure_ascii=False, indent=1)
print(out["channel"])
