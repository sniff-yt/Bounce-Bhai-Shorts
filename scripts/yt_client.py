"""Shared YouTube client for stats.py / upload_own.py (same auth rules as upload.py)."""
import os, subprocess, sys
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

CHANNEL = os.environ.get("YT_CHANNEL_ID", "UCn8j185kE4GH44U8b6n7Qgw")   # @bouncebhaiofficial
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def youtube(check_channel=True):
    enc = os.path.join(ROOT, "secrets", "yt_token.enc")
    if os.path.exists(enc) and os.environ.get("MY_VOICE_KEY"):
        r = subprocess.run(["openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2", "-in", enc, "-pass", "env:MY_VOICE_KEY"],
                           capture_output=True)
        if r.returncode == 0 and r.stdout.strip():
            os.environ["YT_REFRESH_TOKEN"] = r.stdout.decode().strip()
    for k in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN"):
        if not os.environ.get(k):
            raise SystemExit(f"Missing {k}")
    creds = Credentials(None, refresh_token=os.environ["YT_REFRESH_TOKEN"], token_uri="https://oauth2.googleapis.com/token",
                        client_id=os.environ["YT_CLIENT_ID"], client_secret=os.environ["YT_CLIENT_SECRET"],
                        scopes=["https://www.googleapis.com/auth/youtube.force-ssl"])
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    if check_channel:
        mine = [c["id"] for c in yt.channels().list(part="id", mine=True).execute().get("items", [])]
        if CHANNEL not in mine:
            raise SystemExit(f"Token is not for {CHANNEL} (has {mine}); refusing.")
    return yt
