#!/usr/bin/env python3
"""
ONE-TIME local authorization for Google Drive backup uploads. Run this on your
own computer once, using the SAME client_secret.json you already downloaded
for YouTube (OAuth client, type=Desktop) — just make sure the "Google Drive
API" is also enabled on that same Google Cloud project (APIs & Services ->
Library -> Google Drive API -> Enable).

    pip install google-auth-oauthlib google-api-python-client
    python3 authorize_drive.py

It opens a browser, you log in with the Google account that owns the target
Drive, and it writes drive_token.json (contains the refresh token). Keep it
private. For GitHub Actions, paste its contents into a repo secret named
DRIVE_TOKEN_JSON (same pattern as YT_TOKEN_JSON).

Scope is drive.file (least privilege): this app can only see/write files and
folders that IT creates. On first run, upload_drive.py will create a fresh
"CrackIt Daily Videos" folder in your Drive automatically — you don't need to
create or share anything by hand.
"""
import os
from google_auth_oauthlib.flow import InstalledAppFlow

ROOT = os.path.dirname(os.path.abspath(__file__))
CLIENT_SECRET = os.environ.get("DRIVE_CLIENT_SECRET", os.path.join(ROOT, "client_secret.json"))
TOKEN = os.environ.get("DRIVE_TOKEN", os.path.join(ROOT, "drive_token.json"))
SCOPES = ["https://www.googleapis.com/auth/drive.file"]

if __name__ == "__main__":
    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET, SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")
    with open(TOKEN, "w") as f:
        f.write(creds.to_json())
    print("Wrote", TOKEN)
