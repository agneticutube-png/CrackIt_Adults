#!/usr/bin/env python3
"""
Publish today's riddle video to Instagram (Reel) and the Facebook Page (Reel)
via the Meta Graph API. Runs unattended in GitHub Actions right after
upload_drive.py in the daily pipeline loop.

Reads everything it needs from files the pipeline already produces -- no
VIDEO_URL/CAPTION env vars to wire up by hand:

    .last_drive_video.json   written by upload_drive.py -> {"video_url": ...}
    next_video.json          written by pipeline.py -> riddle/answer/category

Non-fatal by design: if the Drive video isn't public yet (upload_drive.py
failed or hasn't run), this script logs why and exits 0 instead of failing
the whole workflow run.

REQUIRED GITHUB ACTIONS SECRETS
--------------------------------
    IG_ACCESS_TOKEN       long-lived (60-day) User token with
                           instagram_basic + instagram_content_publish
    FB_PAGE_ACCESS_TOKEN  Page token for "Riddle o'Clock" (derived from the
                           same long-lived User token via /me/accounts)

Example daily.yml step (place right after the upload_drive.py line):

    - name: Cross-post to Instagram & Facebook
      env:
        IG_ACCESS_TOKEN: ${{ secrets.IG_ACCESS_TOKEN }}
        FB_PAGE_ACCESS_TOKEN: ${{ secrets.FB_PAGE_ACCESS_TOKEN }}
      run: python3 upload_meta.py --ig --fb || echo "Meta cross-post failed (non-fatal)"

IDs (not secrets, safe to keep here):
    Instagram Business Account ID : 17841412094714580  (riddleoclock)
    Facebook Page ID              : 1100749749798082    (Riddle o'Clock)
"""
import os
import sys
import time
import argparse
import urllib.request
import urllib.parse
import json

GRAPH = "https://graph.facebook.com/v21.0"

IG_USER_ID = os.environ.get("IG_USER_ID", "17841412094714580")
FB_PAGE_ID = os.environ.get("FB_PAGE_ID", "1100749749798082")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_ROOT = os.environ.get("RIDDLE_ROOT", SCRIPT_DIR)
LAST_VIDEO_CACHE = os.environ.get("DRIVE_LAST_VIDEO_CACHE", f"{DATA_ROOT}/.last_drive_video.json")
MANIFEST = f"{DATA_ROOT}/next_video.json"

BASE_HASHTAGS = "#shorts #riddle #brainteaser #puzzle #quiz #riddleoclock"


def load_video_url():
    if not os.path.exists(LAST_VIDEO_CACHE):
        print(f"  No {LAST_VIDEO_CACHE} found -- upload_drive.py hasn't produced a "
              "public video URL yet. Skipping Meta cross-post.")
        return None
    data = json.load(open(LAST_VIDEO_CACHE))
    url = data.get("video_url")
    if not url:
        print(f"  {LAST_VIDEO_CACHE} has no video_url. Skipping Meta cross-post.")
        return None
    return url


def build_caption():
    if not os.path.exists(MANIFEST):
        return "Can you solve today's riddle? " + BASE_HASHTAGS
    manifest = json.load(open(MANIFEST))
    riddle = manifest.get("riddle", "").strip()
    answer = manifest.get("answer", "").strip()
    category = manifest.get("category", "").strip()
    category_tag = "#" + category.lower().replace(" ", "") if category else ""
    lines = []
    if riddle:
        lines.append(riddle)
    lines.append("")
    lines.append("Drop your answer in the comments! \U0001F447")
    if answer:
        lines.append(f"(Answer: {answer})")
    lines.append("")
    tags = BASE_HASHTAGS
    if category_tag:
        tags += f" {category_tag}"
    lines.append(tags)
    return "\n".join(lines)


def _post(url, data):
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        err_body = e.read().decode()
        print(f"  HTTP {e.code} error:\n  {err_body}")
        sys.exit(1)


def _get(url, params):
    full = f"{url}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(full) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        err_body = e.read().decode()
        print(f"  HTTP {e.code} error:\n  {err_body}")
        sys.exit(1)


def post_instagram_reel(video_url, caption, token):
    print("=== Instagram: creating media container (Reel) ===")
    create = _post(f"{GRAPH}/{IG_USER_ID}/media", {
        "media_type": "REELS",
        "video_url": video_url,
        "caption": caption,
        "access_token": token,
    })
    creation_id = create.get("id")
    if not creation_id:
        print("  Failed to create container:", create)
        sys.exit(1)
    print(f"  container id: {creation_id}")

    print("  waiting for Instagram to finish processing the video...")
    for attempt in range(30):  # up to ~5 minutes
        status = _get(f"{GRAPH}/{creation_id}", {
            "fields": "status_code",
            "access_token": token,
        })
        code = status.get("status_code")
        print(f"    [{attempt + 1}/30] status: {code}")
        if code == "FINISHED":
            break
        if code == "ERROR":
            print("  Instagram reported an error processing the video:", status)
            sys.exit(1)
        time.sleep(10)
    else:
        print("  Timed out waiting for processing.")
        sys.exit(1)

    print("=== Instagram: publishing ===")
    publish = _post(f"{GRAPH}/{IG_USER_ID}/media_publish", {
        "creation_id": creation_id,
        "access_token": token,
    })
    media_id = publish.get("id")
    if not media_id:
        print("  Publish call did not return an id:", publish)
        sys.exit(1)
    print(f"  PUBLISHED. media id: {media_id}")

    permalink = _get(f"{GRAPH}/{media_id}", {
        "fields": "permalink",
        "access_token": token,
    })
    print(f"  view: {permalink.get('permalink', '(permalink lookup failed)')}")


def post_facebook_reel(video_url, caption, token):
    print("=== Facebook Page: starting Reel upload ===")
    start = _post(f"{GRAPH}/{FB_PAGE_ID}/video_reels", {
        "upload_phase": "start",
        "access_token": token,
    })
    video_id = start.get("video_id")
    upload_url = start.get("upload_url")
    if not video_id or not upload_url:
        print("  Failed to start upload session:", start)
        sys.exit(1)
    print(f"  video_id: {video_id}")

    print("  handing the public video URL to Meta for server-side fetch...")
    req = urllib.request.Request(upload_url, method="POST", headers={
        "Authorization": f"OAuth {token}",
        "file_url": video_url,
    })
    try:
        with urllib.request.urlopen(req) as resp:
            upload_resp = json.loads(resp.read().decode())
            print("  upload response:", upload_resp)
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code} error during upload:\n  {e.read().decode()}")
        sys.exit(1)

    print("=== Facebook Page: publishing Reel ===")
    finish = _post(f"{GRAPH}/{FB_PAGE_ID}/video_reels", {
        "upload_phase": "finish",
        "video_id": video_id,
        "description": caption,
        "video_state": "PUBLISHED",
        "access_token": token,
    })
    if finish.get("success"):
        print(f"  PUBLISHED. video id: {video_id}")
        print(f"  view: https://www.facebook.com/{FB_PAGE_ID}/videos/{video_id}/")
    else:
        print("  Finish call did not report success:", finish)
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ig", action="store_true", help="post to Instagram")
    ap.add_argument("--fb", action="store_true", help="post to the Facebook Page")
    args = ap.parse_args()

    if not args.ig and not args.fb:
        ap.error("pass --ig and/or --fb")

    video_url = load_video_url()
    if not video_url:
        print("Nothing to cross-post today. Exiting cleanly.")
        return

    caption = build_caption()
    print(f"Cross-posting: {video_url}")
    print(f"Caption:\n{caption}\n")

    if args.ig:
        token = os.environ.get("IG_ACCESS_TOKEN")
        if not token:
            print("  IG_ACCESS_TOKEN not set -- skipping Instagram.")
        else:
            post_instagram_reel(video_url, caption, token)

    if args.fb:
        token = os.environ.get("FB_PAGE_ACCESS_TOKEN")
        if not token:
            print("  FB_PAGE_ACCESS_TOKEN not set -- skipping Facebook.")
        else:
            post_facebook_reel(video_url, caption, token)


if __name__ == "__main__":
    main()
