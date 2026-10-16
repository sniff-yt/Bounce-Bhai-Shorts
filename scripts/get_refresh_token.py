#!/usr/bin/env python3
"""One-time helper: run on your own computer to get YT_REFRESH_TOKEN.
pip install google-auth-oauthlib
python scripts/get_refresh_token.py client_secret.json
Sign in with sniffapp.official@gmail.com and pick the Bounce Bhai channel.
"""
import sys
from google_auth_oauthlib.flow import InstalledAppFlow
flow = InstalledAppFlow.from_client_secrets_file(sys.argv[1], ["https://www.googleapis.com/auth/youtube.force-ssl"])
creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
print("\nYT_CLIENT_ID     =", creds.client_id)
print("YT_CLIENT_SECRET =", creds.client_secret)
print("YT_REFRESH_TOKEN =", creds.refresh_token)
