#!/usr/bin/env python3
"""
Upload the latest pipeline video to YouTube as PRIVATE, then print the Studio
link to the run log so you can publish it manually.

Why PRIVATE + manual publish: a new (unaudited) API project has its uploads
force-locked to private by YouTube, and scheduled auto-publish (publishAt) is
blocked until the project passes a compliance audit. So during the launch phase
the correct flow is: API uploads privately -> you get a ping -> you publish in
Studio. Once the audit clears, flip PRIVACY="public" (or wire publishAt) here
and the channel becomes fully hands-off.

One-time setup (see Adult_Channel_Setup_Kit / implementation plan):
  1. Google Cloud project -> enable "YouTube Data API v3".
  2. OAuth client (Desktop) -> download client_secret.json.
  3. Run authorize.py ONCE locally -> creates token.json (refresh token).
For GitHub Actions, store client_secret.json + token.json contents as secrets.

Run:  python3 upload_youtube.py            # uploads manifest video
      python3 upload_youtube.py --dry-run  # validate manifest, no upload
"""
import os, sys, json

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_ROOT = os.environ.get("RIDDLE_ROOT", SCRIPT_DIR)
MANIFEST = f"{DATA_ROOT}/next_video.json"
XLSX = os.environ.get("RIDDLE_XLSX", f"{DATA_ROOT}/Riddle_Content_Bank.xlsx")
CLIENT_SECRET = os.environ.get("YT_CLIENT_SECRET", f"{SCRIPT_DIR}/client_secret.json")
TOKEN = os.environ.get("YT_TOKEN", f"{SCRIPT_DIR}/token.json")
SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube"]

# Launch phase: keep PRIVATE and publish manually. After audit -> "public".
PRIVACY = os.environ.get("YT_PRIVACY", "private")

def get_service():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    creds = Credentials.from_authorized_user_file(TOKEN, SCOPES)
    if not creds.valid and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN, "w") as f:
            f.write(creds.to_json())
    return build("youtube", "v3", credentials=creds)

def upload(manifest, service):
    from googleapiclient.http import MediaFileUpload
    body = {
        "snippet": {
            "title": manifest["title"],
            "description": manifest["description"],
            "tags": manifest["tags"],
            "categoryId": manifest.get("category_id", "24"),
        },
        "status": {
            "privacyStatus": PRIVACY,
            "selfDeclaredMadeForKids": False,   # CRITICAL: adult channel, NOT for kids
            "madeForKids": False,
        },
    }
    media = MediaFileUpload(manifest["video_path"], chunksize=-1, resumable=True,
                            mimetype="video/mp4")
    req = service.videos().insert(part="snippet,status", body=body, media_body=media)
    resp = None
    while resp is None:
        status, resp = req.next_chunk()
        if status:
            print(f"  upload {int(status.progress()*100)}%")
    return resp["id"]

def main():
    if not os.path.exists(MANIFEST):
        sys.exit("No manifest. Run pipeline.py first.")
    manifest = json.load(open(MANIFEST))
    if not os.path.exists(manifest["video_path"]):
        sys.exit(f"Video missing: {manifest['video_path']}")
    print(f"Ready to upload: {manifest['title']}")
    print(f"  file: {manifest['video_path']}  privacy={PRIVACY}")

    if "--dry-run" in sys.argv:
        print("DRY RUN — not uploading.")
        return

    service = get_service()
    vid = upload(manifest, service)
    url = f"https://youtu.be/{vid}"
    print("UPLOADED:", url)

    # mark posted only AFTER successful upload
    import pipeline
    pipeline.mark_posted(XLSX, manifest["sheet"], manifest["row"],
                         manifest["posted_col"], manifest["link_col"], url)
    print("Marked posted in workbook.")

    # Manual-publish mode: print the link so it's captured in the run log.
    studio = f"https://studio.youtube.com/video/{vid}/edit"
    print("\nREADY TO PUBLISH (manual):")
    print(f"  Title : {manifest['title']}")
    print(f"  Studio: {studio}")
    print(f"  Watch : {url}")
    print("Open the Studio link, set visibility to Public, and publish.")

if __name__ == "__main__":
    main()
