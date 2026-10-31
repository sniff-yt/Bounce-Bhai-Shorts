#!/usr/bin/env python3
"""Manual comment tool. list: print recent comments (with our replies) as ::notice lines. reply: answer one comment.
usage: comment_tool.py list | comment_tool.py reply <parent_comment_id> <text>"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from yt_client import youtube, CHANNEL

def clean(s): return " ".join(str(s).split())[:300].replace("::", ": :")

yt = youtube(check_channel=False)
if sys.argv[1] == "list":
    up = yt.channels().list(part="contentDetails", id=CHANNEL).execute()["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    items = yt.playlistItems().list(part="snippet,contentDetails", playlistId=up, maxResults=15).execute().get("items", [])
    for it in items:
        vid = it["contentDetails"]["videoId"]
        try:
            th = yt.commentThreads().list(part="snippet,replies", videoId=vid, maxResults=20, order="time", textFormat="plainText").execute().get("items", [])
        except Exception as e:
            continue
        for t in th:
            top = t["snippet"]["topLevelComment"]; sn = top["snippet"]
            print(f"::notice::C|{vid}|{top['id']}|{clean(sn.get('authorDisplayName'))}|{clean(sn.get('textDisplay'))}")
            for r in t.get("replies", {}).get("comments", []):
                print(f"::notice::R|{vid}|{top['id']}|{clean(r['snippet'].get('authorDisplayName'))}|{clean(r['snippet'].get('textDisplay'))}")
else:
    pid, text = sys.argv[2], sys.argv[3]
    yt.comments().insert(part="snippet", body={"snippet": {"parentId": pid, "textOriginal": text}}).execute()
    print("::notice::replied", pid)
