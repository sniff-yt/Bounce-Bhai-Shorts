#!/usr/bin/env python3
"""Check the Bounce Bhai YouTube token (secrets/yt_token.enc via MY_VOICE_KEY, or YT_REFRESH_TOKEN) before a long upload:
it must belong to the channel and carry a scope that allows videos.insert + thumbnails.set. exit 0 ok, 1 not usable."""
import os, sys
import requests
from google.auth.transport.requests import Request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from yt_client import youtube  # noqa: E402

OK = {"https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube",
      "https://www.googleapis.com/auth/youtube.force-ssl"}
try:
    yt = youtube(check_channel=True)            # refuses a token for any other channel
    creds = yt._http.credentials
    if not creds.token:
        creds.refresh(Request())
    info = requests.get("https://oauth2.googleapis.com/tokeninfo", params={"access_token": creds.token}, timeout=30).json()
    scopes = set((info.get("scope") or "").split())
except SystemExit as e:
    print(f"::error title=youtube token::{e}"); sys.exit(1)
except Exception as e:
    print(f"::error title=youtube token::{type(e).__name__}: {str(e)[:300]}"); sys.exit(1)
good = scopes & OK
print(f"::notice title=youtube token::channel ok, scopes: {' '.join(sorted(s.rsplit('/', 1)[-1] for s in scopes))}")
if not good:
    print("::error title=youtube token::token has no upload scope (youtube.upload / youtube / youtube.force-ssl)")
    sys.exit(1)
