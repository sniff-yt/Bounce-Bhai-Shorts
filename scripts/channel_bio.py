#!/usr/bin/env python3
"""Make sure the Bounce Bhai channel description carries the Bhai Drive game link (idempotent).
Shorts descriptions don't make links clickable; the channel's About text does."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from yt_client import youtube, CHANNEL

URL = os.environ.get("BB_GAME_URL", "https://sniff-yt.github.io/Bounce-Bhai-Shorts/game/")
LINE = f"🎮 Play our FREE game Bhai Drive (Android + browser): {URL}"

yt = youtube(check_channel=True)
ch = yt.channels().list(part="brandingSettings", id=CHANNEL).execute()["items"][0]
bs = ch["brandingSettings"]
desc = bs.get("channel", {}).get("description", "") or ""
if URL in desc:
    print("bio already has the game link"); sys.exit(0)
bs.setdefault("channel", {})["description"] = (LINE + "\n\n" + desc).strip()[:1000]
yt.channels().update(part="brandingSettings", body={"id": CHANNEL, "brandingSettings": bs}).execute()
print("bio updated:", bs["channel"]["description"][:200])
