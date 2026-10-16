#!/usr/bin/env python3
"""Upload the finished Short to YouTube (Data API v3) with Hindi/English/Telugu
subtitles and translated titles/descriptions, then post a comment.
usage: python scripts/upload.py out/story.json
env: YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN  (see README "YouTube API setup")
Exits 0 without uploading if those secrets are missing.
"""
import json, os, sys
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

need = ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN")
if not all(os.environ.get(k) for k in need):
    print("YouTube secrets not set: skipping upload (video kept as a workflow artifact)."); sys.exit(0)

c = json.load(open(sys.argv[1]))
final = c["out"].replace(".mp4", "_final.mp4")
creds = Credentials(None, refresh_token=os.environ["YT_REFRESH_TOKEN"], token_uri="https://oauth2.googleapis.com/token",
                    client_id=os.environ["YT_CLIENT_ID"], client_secret=os.environ["YT_CLIENT_SECRET"],
                    scopes=["https://www.googleapis.com/auth/youtube.force-ssl"])
yt = build("youtube", "v3", credentials=creds, cache_discovery=False)

FOOT = {"hi_roman": "Real physics simulation, made with code. No AI visuals.",
        "hi": "असली फ़िज़िक्स सिम्युलेशन, कोड से बना। कोई AI विज़ुअल नहीं।",
        "en": "Real physics simulation, made with code. No AI visuals.",
        "te": "నిజమైన ఫిజిక్స్ సిమ్యులేషన్, కోడ్‌తో తయారు. AI విజువల్స్ లేవు."}
tags_line = f"#shorts #satisfying #story {c.get('genre_tag', '#facts')}"
desc = lambda k: f"{c['question'][k]} 👇\n{FOOT[k]}\n{tags_line}"
yt_t = c["yt_title"]

body = {
    "snippet": {"title": yt_t["hi_roman"][:95], "description": desc("hi_roman"), "tags": c.get("tags", [])[:12],
                "categoryId": "24", "defaultLanguage": "hi", "defaultAudioLanguage": "hi"},
    "status": {"privacyStatus": os.environ.get("YT_PRIVACY", "public"), "selfDeclaredMadeForKids": False,
               "containsSyntheticMedia": False},  # own-voice clone is exempt from AI disclosure
    "localizations": {"en": {"title": yt_t["en"][:95], "description": desc("en")},
                      "te": {"title": yt_t["te"][:95], "description": desc("te")}},
}
req = yt.videos().insert(part="snippet,status,localizations", body=body,
                         media_body=MediaFileUpload(final, mimetype="video/mp4", resumable=True))
resp = None
while resp is None:
    _, resp = req.next_chunk()
vid = resp["id"]
print("uploaded https://youtube.com/shorts/" + vid, "privacy:", resp["status"].get("privacyStatus"))

for lang, name in (("hi", "Hindi"), ("en", "English"), ("te", "Telugu")):
    srt = c["out"].replace(".mp4", f".{'hd' if lang == 'hi' else lang}.srt")
    try:
        yt.captions().insert(part="snippet", body={"snippet": {"videoId": vid, "language": lang, "name": name}},
                             media_body=MediaFileUpload(srt, mimetype="application/octet-stream")).execute()
        print("captions", lang)
    except Exception as e:
        print("captions failed", lang, e)
try:
    yt.commentThreads().insert(part="snippet", body={"snippet": {"videoId": vid, "topLevelComment": {
        "snippet": {"textOriginal": c["question"]["hi_roman"] + " 👇"}}}}).execute()
except Exception as e:
    print("comment failed", e)
open(os.environ.get("GITHUB_OUTPUT", os.devnull), "a").write(f"video_id={vid}\n")
c["video_id"] = vid
json.dump(c, open(sys.argv[1], "w"), ensure_ascii=False, indent=1)
