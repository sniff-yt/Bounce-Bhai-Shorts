#!/usr/bin/env python3
"""Reply in Hinglish to new viewer comments on recent Bounce Bhai Shorts (early engagement helps Shorts spread).
usage: python scripts/reply_comments.py /tmp/data/replied.json
Skips the channel's own comments, comments it already answered, links, and anything the AI flags as spam/abuse.
At most BB_MAX_REPLIES (default 10) replies per run.
"""
import json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from yt_client import youtube, CHANNEL
import write_story as WS

MAX = int(os.environ.get("BB_MAX_REPLIES", "10"))
PROMPT = """You run the YouTube Shorts channel "Bounce Bhai" (fun Hinglish micro-stories and ball-escape physics clips).
A viewer commented on the Short titled: "{title}"
Comment: "{text}"

Write a short, warm, playful reply in Hinglish (Roman script), max 20 words, 0-1 emoji.
Match their language if they wrote in English or Telugu. Never ask for subscriptions in every reply; never argue.
If the comment is spam, abusive, sexual, political, or asks for personal info, set skip to true.
Return ONLY JSON: {{"skip": false, "reply": "..."}}"""


def main(path):
    try:
        done = set(json.load(open(path)))
    except Exception:
        done = set()
    yt = youtube(check_channel=False)
    ch = yt.channels().list(part="contentDetails", id=CHANNEL).execute()["items"][0]
    uploads = ch["contentDetails"]["relatedPlaylists"]["uploads"]
    items = yt.playlistItems().list(part="snippet,contentDetails", playlistId=uploads, maxResults=15).execute().get("items", [])
    sent = 0
    for it in items:
        vid, title = it["contentDetails"]["videoId"], it["snippet"]["title"]
        try:
            threads = yt.commentThreads().list(part="snippet,replies", videoId=vid, maxResults=50,
                                               order="time", textFormat="plainText").execute().get("items", [])
        except Exception as e:
            print("comments off?", vid, e); continue
        for th in threads:
            top = th["snippet"]["topLevelComment"]
            cid, sn = top["id"], top["snippet"]
            if cid in done or sn.get("authorChannelId", {}).get("value") == CHANNEL:
                continue
            replies = th.get("replies", {}).get("comments", [])
            if any(r["snippet"].get("authorChannelId", {}).get("value") == CHANNEL for r in replies):
                done.add(cid); continue
            text = sn.get("textDisplay", "")[:300]
            if re.search(r"https?://|www\.", text):
                done.add(cid); continue
            try:
                out = WS.post_story(PROMPT.format(title=title, text=text))
            except Exception as e:
                print("AI failed:", e); break
            done.add(cid)
            if out.get("skip") or not str(out.get("reply", "")).strip():
                print("skip:", text[:60]); continue
            reply = str(out["reply"]).strip()[:300]
            yt.comments().insert(part="snippet", body={"snippet": {"parentId": cid, "textOriginal": reply}}).execute()
            print(f"replied on {vid}: {text[:50]!r} -> {reply!r}")
            sent += 1
            if sent >= MAX:
                break
        if sent >= MAX:
            break
    json.dump(sorted(done)[-3000:], open(path, "w"))
    print("replies sent:", sent)


if __name__ == "__main__":
    main(sys.argv[1])
