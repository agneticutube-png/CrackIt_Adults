#!/usr/bin/env python3
"""
Back up the latest pipeline video to Google Drive. This is the missing link
that lets other tools (e.g. cross-posting to Meta Business Suite) pick the
video up right after it's rendered, instead of only existing transiently on
the GitHub Actions runner and then disappearing once it's uploaded to YouTube.

Runs independently of upload_youtube.py — call it right after pipeline.py so
the video is safely backed up even if the YouTube upload step later fails.
Never marks anything "posted" in the workbook; that stays upload_youtube.py's
job.

One-time setup:
  1. Same Google Cloud project as the YouTube setup -> also enable the
     "Google Drive API" (APIs & Services -> Library -> Google Drive API).
  2. Run authorize_drive.py ONCE locally -> creates drive_token.json.
  3. For GitHub Actions, store client_secret.json (already have it) and
     drive_token.json contents as secrets (DRIVE_TOKEN_JSON).

On first run this creates a "CrackIt Daily Videos" folder in the authorizing
account's Drive (scope is drive.file, so it can only see files/folders it
creates itself — nothing else in your Drive is touched). Subsequent runs
reuse the same folder by searching for its name + storing the id in
.drive_folder_id.json next to this script (committed to Actions cache, not
git — see .gitignore).

Run:  python3 upload_drive.py            # uploads manifest video to Drive
      python3 upload_drive.py --dry-run  # validate manifest, no upload
"""
import os, sys, json

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_ROOT = os.environ.get("RIDDLE_ROOT", SCRIPT_DIR)
MANIFEST = f"{DATA_ROOT}/next_video.json"
CLIENT_SECRET = os.environ.get("DRIVE_CLIENT_SECRET", f"{SCRIPT_DIR}/client_secret.json")
TOKEN = os.environ.get("DRIVE_TOKEN", f"{SCRIPT_DIR}/drive_token.json")
SCOPES = ["https://www.googleapis.com/auth/drive.file"]

FOLDER_NAME = os.environ.get("DRIVE_FOLDER_NAME", "CrackIt Daily Videos")
FOLDER_CACHE = os.environ.get("DRIVE_FOLDER_CACHE", f"{DATA_ROOT}/.drive_folder_id.json")


def get_service():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    creds = Credentials.from_authorized_user_file(TOKEN, SCOPES)
    if not creds.valid and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN, "w") as f:
            f.write(creds.to_json())
    return build("drive", "v3", credentials=creds)


def get_or_create_folder(service):
    """Reuse the cached folder id if it still resolves, else search by name
    (within files this app can see), else create a fresh folder."""
    if os.path.exists(FOLDER_CACHE):
        cached = json.load(open(FOLDER_CACHE)).get("id")
        if cached:
            try:
                f = service.files().get(fileId=cached, fields="id,trashed").execute()
                if not f.get("trashed"):
                    return cached
            except Exception:
                pass  # fall through and re-resolve

    q = (f"name = '{FOLDER_NAME}' and mimeType = 'application/vnd.google-apps.folder' "
         "and trashed = false")
    res = service.files().list(q=q, fields="files(id,name)", pageSize=1).execute()
    files = res.get("files", [])
    if files:
        folder_id = files[0]["id"]
    else:
        meta = {"name": FOLDER_NAME, "mimeType": "application/vnd.google-apps.folder"}
        folder = service.files().create(body=meta, fields="id").execute()
        folder_id = folder["id"]
        print(f"  created Drive folder '{FOLDER_NAME}' ({folder_id})")

    with open(FOLDER_CACHE, "w") as f:
        json.dump({"id": folder_id}, f)
    return folder_id


def upload(manifest, service, folder_id):
    from googleapiclient.http import MediaFileUpload
    date_prefix = manifest.get("date") or __import__("datetime").date.today().isoformat()
    name = f"{date_prefix} - {manifest['title']}.mp4"
    meta = {"name": name, "parents": [folder_id]}
    media = MediaFileUpload(manifest["video_path"], mimetype="video/mp4", resumable=True)
    req = service.files().create(body=meta, media_body=media,
                                  fields="id,webViewLink")
    resp = None
    while resp is None:
        status, resp = req.next_chunk()
        if status:
            print(f"  upload {int(status.progress() * 100)}%")
    return resp


def main():
    if not os.path.exists(MANIFEST):
        sys.exit("No manifest. Run pipeline.py first.")
    manifest = json.load(open(MANIFEST))
    if not os.path.exists(manifest["video_path"]):
        sys.exit(f"Video missing: {manifest['video_path']}")
    print(f"Ready to back up to Drive: {manifest['title']}")
    print(f"  file: {manifest['video_path']}")

    if "--dry-run" in sys.argv:
        print("DRY RUN — not uploading.")
        return

    service = get_service()
    folder_id = get_or_create_folder(service)
    resp = upload(manifest, service, folder_id)
    print("DRIVE BACKUP OK:", resp.get("webViewLink", resp.get("id")))


if __name__ == "__main__":
    main()
