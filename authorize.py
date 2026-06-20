#!/usr/bin/env python3
"""
ONE-TIME local authorization. Run this on your own computer once, after you
download client_secret.json from Google Cloud (OAuth client, type=Desktop).

    pip install google-auth-oauthlib google-api-python-client
    python3 authorize.py

It opens a browser, you log in with the Google account that OWNS the YouTube
channel, and it writes token.json (contains the refresh token). Keep token.json
private. For GitHub Actions, paste its contents into a repo secret.
"""
import os
from google_auth_oauthlib.flow import InstalledAppFlow

ROOT = os.path.dirname(os.path.abspath(__file__))
CLIENT_SECRET = os.environ.get("YT_CLIENT_SECRET", os.path.join(ROOT, "client_secret.json"))
TOKEN = os.environ.get("YT_TOKEN", os.path.join(ROOT, "token.json"))
SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube"]

if __name__ == "__main__":
    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET, SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")
    with open(TOKEN, "w") as f:
        f.write(creds.to_json())
    print("Wrote", TOKEN)
