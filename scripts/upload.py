"""Upload the finished Short to YouTube (Data API v3) with Hindi/English/Telugu
subtitles and translated titles/descriptions, then post a comment.
usage: python scripts/upload.py out/story.json
env: YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN  (see README "YouTube API setup")
Exits 0 without uploading if those secrets are missing.

This modified upload script checks which channels the provided credentials have access to
and validates an optional YT_CHANNEL_ID environment variable to prevent uploading to the
wrong channel when the same Google account controls multiple channels/brand accounts.
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

# Check accessible channels for this credential
try:
    ch_resp = yt.channels().list(part="id,snippet", mine=True).execute()
    channels = [(ch["id"], ch["snippet"].get("title", "")) for ch in ch_resp.get("items", [])]
    print("YouTube API: accessible channels:")
    for cid, title in channels:
        print("  ", cid, "-", title)
except Exception as e:
    print("Warning: couldn't list channels for this credential:", e)
    channels = []

# If a target channel ID is provided, validate that the credentials have access to it.
expected = os.environ.get("YT_CHANNEL_ID")
if expected:
    if not any(cid == expected for cid, _ in channels):
        print("ERROR: The provided credentials do not appear to have access to the expected channel ID:", expected)
        print("Accessible channels (if any):")
        for cid, title in channels:
            print(" ", cid, "-", title)
        print("How to fix: re-run scripts/get_refresh_token.py on your local machine and, when prompted by Google,
      choose the correct channel/brand account for your channel. Then store the new YT_REFRESH_TOKEN as a repo secret.")
        sys.exit(2)

FOOT = {"hi_roman": "3D cartoon animation banaya code se, Blender mein. No AI visuals.",
        "hi": "कोड से बना 3D कार्टून एनिमेशन (Blender)। कोई AI विज़ुअल नहीं।",
        "en": "3D cartoon animation made with code in Blender. No AI visuals.",
        "te": "కోడ్‌తో Blender లో తయారైన 3D కార్టూన్ యానిమేషన్. AI విజువల్స్ లేవు."}
tags_line = f"#shorts #animation #story {c.get('genre_tag', '#facts')}"
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

# Optionally post a comment (if credentials allow)
try:
    comment = c.get("question", {}).get("hi_roman", "")
    if comment:
        yt.commentThreads().insert(part="snippet", body={
            "snippet": {"videoId": resp["id"], "topLevelComment": {"snippet": {"textOriginal": comment}}}
        }).execute()
except Exception as e:
    print("Could not post comment:", e)

print("Uploaded video id:", resp.get("id"))
print("Done.")
