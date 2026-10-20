#!/usr/bin/env python3
"""Post a video the creator uploaded from the dashboard.
usage: python scripts/upload_own.py video.mp4   (env: TITLE, DESCRIPTION, TAGS, PRIVACY, PUBLISH_AT)"""
import os, sys
from googleapiclient.http import MediaFileUpload
from yt_client import youtube

path = sys.argv[1]
title = (os.environ.get("TITLE") or "Bounce Bhai #shorts").strip()[:100]
desc = (os.environ.get("DESCRIPTION") or "").strip()[:4900]
tags = [t.strip() for t in (os.environ.get("TAGS") or "").split(",") if t.strip()][:15]
privacy = os.environ.get("PRIVACY") or "public"
status = {"privacyStatus": privacy, "selfDeclaredMadeForKids": False}
at = (os.environ.get("PUBLISH_AT") or "").strip()
if at:  # YouTube only schedules private videos
    status.update(privacyStatus="private", publishAt=at)
yt = youtube()
req = yt.videos().insert(part="snippet,status", body={
    "snippet": {"title": title, "description": desc, "tags": tags, "categoryId": "24"}, "status": status},
    media_body=MediaFileUpload(path, mimetype="video/mp4", resumable=True))
resp = None
while resp is None:
    _, resp = req.next_chunk()
print("Uploaded video id:", resp["id"])
print(f"::notice title=posted::https://youtube.com/shorts/{resp['id']}")
