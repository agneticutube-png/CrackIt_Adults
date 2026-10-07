#!/usr/bin/env python3
"""
Monthly compilation builder for Riddle o'Clock.

Collects the Shorts from the last N days, joins them into one consolidated
vertical video, and (optionally) uploads it to YouTube as PRIVATE for review +
manual publish. Reuses the normalize/concat/upload core from combine_weekly.py.

TWO SOURCES (pick with --source):

  drive  : pull clips from the "CrackIt Daily Videos" Google Drive folder that
           your daily pipeline already backs up to (upload_drive.py). Clean,
           lossless, authenticated. Best for future months once the folder has
           accumulated a full month of renders. Uses drive_token.json.

  ytdlp  : list your channel's PUBLISHED Shorts from the last N days via the
           YouTube Data API (token.json), then download each with yt-dlp.
           Retroactive — works right now for anything already public. Cannot
           fetch still-private videos (no cookies). ToS gray area (your own
           content). Requires yt-dlp installed:  pip install yt-dlp

USAGE (run locally on your Mac, inside the repo, .venv active):

    # See what would be collected, download/build nothing:
    python3 monthly_compile.py --source ytdlp --days 30 --dry-run
    python3 monthly_compile.py --source drive --days 30 --dry-run

    # Build the consolidated video only (review before uploading):
    python3 monthly_compile.py --source ytdlp --days 30

    # Build AND upload to YouTube as private:
    python3 monthly_compile.py --source ytdlp --days 30 --upload

Flags:
    --source {drive,ytdlp}   where to get the clips (default: drive)
    --days N                 look back N days (default: 30)
    --max-seconds S          treat clips longer than S as non-Shorts and skip
                             (default: 180; your riddles are ~20s)
    --output FILE            output path (default: Weekly_Compilation/output/CrackIt_Monthly_<date>.mp4)
    --dry-run                list what would be collected, do nothing else
    --upload                 after building, upload to YouTube (YT_PRIVACY, default private)
    --title "..."            override the video title
    --keep-temp              keep downloaded + normalized temp files
"""
import os, sys, json, re, subprocess, tempfile, shutil, datetime, argparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
import combine_weekly as CW   # reuse normalize/concat/build_chapters/probe/fmt

# Folder structure for the compilation lifecycle:
#   downloaded/<date>/  -> the individual source Shorts pulled for this run
#   created/            -> the assembled long compilation video (build output)
#   upload/             -> the long video staged for / sent to YouTube
DL_DIR = os.path.join(SCRIPT_DIR, "downloaded")
CREATED_DIR = os.path.join(SCRIPT_DIR, "created")
UPLOAD_DIR = os.path.join(SCRIPT_DIR, "upload")
DEFAULT_OUTDIR = CREATED_DIR


def _cutoff(days):
    return datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)


def _iso(dt):
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------- DRIVE source
def plan_from_drive(days):
    """List (no download) videos created in the last `days` from the daily-backup
    folder. Returns (plan, note) where plan is a list of dicts with id/name/when,
    already deduped by filename and sorted chronologically."""
    import upload_drive as UD
    service = UD.get_service()
    folder_id = UD.get_or_create_folder(service)
    cutoff = _cutoff(days)

    items, page = [], None
    q = (f"'{folder_id}' in parents and trashed = false and "
         "(mimeType contains 'video' or name contains '.mp4')")
    while True:
        resp = service.files().list(
            q=q, orderBy="createdTime",
            fields="nextPageToken, files(id,name,createdTime)",
            pageSize=100, pageToken=page).execute()
        items.extend(resp.get("files", []))
        page = resp.get("nextPageToken")
        if not page:
            break

    seen, plan = set(), []
    for f in items:
        ct = f.get("createdTime", "")
        try:
            when = datetime.datetime.fromisoformat(ct.replace("Z", "+00:00"))
        except ValueError:
            continue
        if when < cutoff or f["name"] in seen:
            continue
        seen.add(f["name"])
        plan.append({"id": f["id"], "name": f["name"], "when": when, "dur": None})
    plan.sort(key=lambda x: x["when"])
    note = f"Drive folder has {len(items)} videos; {len(plan)} unique within last {days} days."
    return plan, note


def download_drive(plan, dest_dir):
    from googleapiclient.http import MediaIoBaseDownload
    import upload_drive as UD
    service = UD.get_service()
    paths = []
    for i, f in enumerate(plan, 1):
        safe = re.sub(r"[^\w.\-]+", "_", f["name"]) or f"clip_{i}.mp4"
        out = os.path.join(dest_dir, f"{i:03d}_{safe}")
        if not out.lower().endswith((".mp4", ".mov", ".mkv", ".webm", ".m4v")):
            out += ".mp4"
        print(f"  downloading {i}/{len(plan)}: {f['name']}")
        req = service.files().get_media(fileId=f["id"])
        with open(out, "wb") as fh:
            dl = MediaIoBaseDownload(fh, req)
            done = False
            while not done:
                _, done = dl.next_chunk()
        paths.append(out)
    return paths


# ---------------------------------------------------------------- YTDLP source
def plan_from_ytdlp(days, max_seconds):
    """List (no download) the channel's PUBLISHED Shorts in the window via the
    Data API. Returns (plan, note); plan deduped by video id, chronological,
    each dict carrying id/title/when/dur. Also prints what it skips and why."""
    import upload_youtube as U
    service = U.get_service()

    ch = service.channels().list(part="contentDetails", mine=True).execute()
    uploads = ch["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

    cutoff = _cutoff(days)
    vids, seen_ids, page = [], set(), None
    while True:
        resp = service.playlistItems().list(
            part="contentDetails", playlistId=uploads,
            maxResults=50, pageToken=page).execute()
        for it in resp["items"]:
            cd = it["contentDetails"]
            vid = cd["videoId"]
            if vid in seen_ids:
                continue
            seen_ids.add(vid)
            pub = cd.get("videoPublishedAt") or cd.get("publishedAt")
            if not pub:
                continue
            when = datetime.datetime.fromisoformat(pub.replace("Z", "+00:00"))
            if when >= cutoff:
                vids.append((vid, when))
        page = resp.get("nextPageToken")
        if not page:
            break
    vids.sort(key=lambda x: x[1])

    plan, skipped = [], 0
    for i in range(0, len(vids), 50):
        chunk = vids[i:i + 50]
        meta = service.videos().list(
            part="contentDetails,status,snippet",
            id=",".join(v for v, _ in chunk)).execute()
        by_id = {m["id"]: m for m in meta["items"]}
        for vid, when in chunk:
            m = by_id.get(vid)
            if not m:
                continue
            dur = _parse_iso8601_duration(m["contentDetails"]["duration"])
            priv = m["status"]["privacyStatus"]
            title = m["snippet"]["title"]
            if priv != "public":
                print(f"  skip (not public: {priv}): {title[:60]}")
                skipped += 1
                continue
            if dur > max_seconds:
                print(f"  skip (>{max_seconds}s, not a Short): {title[:60]}")
                skipped += 1
                continue
            plan.append({"id": vid, "title": title, "when": when, "dur": dur})
    note = (f"{len(vids)} uploads in last {days} days; "
            f"{len(plan)} public Shorts to include ({skipped} skipped).")
    return plan, note


def _ytdlp_cmd():
    """Prefer the yt-dlp module under THIS interpreter (works inside a venv even
    when the yt-dlp console script isn't on PATH); fall back to the CLI."""
    import importlib.util
    if importlib.util.find_spec("yt_dlp") is not None:
        return [sys.executable, "-m", "yt_dlp"]
    if shutil.which("yt-dlp"):
        return ["yt-dlp"]
    sys.exit("yt-dlp not found. Install it first:  pip install yt-dlp")


def download_ytdlp(plan, dest_dir):
    base = _ytdlp_cmd()
    paths = []
    for i, f in enumerate(plan, 1):
        out = os.path.join(dest_dir, f"{i:03d}_{f['id']}.mp4")
        url = f"https://www.youtube.com/watch?v={f['id']}"
        print(f"  downloading {i}/{len(plan)}: {f['title'][:60]}")
        r = subprocess.run(
            base + ["-f", "bv*+ba/b", "--merge-output-format", "mp4",
                    "-o", out, url],
            capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(out):
            print(f"    download failed, skipping: {r.stderr[-300:]}")
            continue
        paths.append(out)
    return paths


def _plan_label(f):
    return f.get("title") or f.get("name") or f.get("id", "?")


def _parse_iso8601_duration(s):
    """PT#H#M#S -> seconds."""
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", s or "")
    if not m:
        return 0
    h, mi, se = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mi * 60 + se


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["drive", "ytdlp"], default="drive")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--limit", type=int, default=0,
                    help="cap to the most recent N clips (0 = no cap). ~28 ≈ 10 min.")
    ap.add_argument("--skip", type=int, default=0,
                    help="skip the most recent N clips first (coarse batch offset).")
    ap.add_argument("--exclude-file", default=os.path.join(SCRIPT_DIR, "used_clip_ids.txt"),
                    help="ledger of already-used clip ids; these are excluded and new "
                         "ones are appended after a build. Guarantees no cross-batch dupes.")
    ap.add_argument("--no-ledger", action="store_true",
                    help="don't read or update the used-clip ledger.")
    ap.add_argument("--tag", default="",
                    help="label added to the output filename + download subfolder "
                         "(e.g. 'batch2') so batches don't overwrite each other.")
    ap.add_argument("--orientation", choices=["vertical", "wide"], default="vertical",
                    help="wide = 16:9 landscape for long-form YouTube (blurred fill + branding)")
    ap.add_argument("--max-seconds", type=int, default=180)
    ap.add_argument("--from-folder", default=None,
                    help="skip API+download; build from clips already in this folder "
                         "(e.g. downloaded/<date>). Lets you re-render vertical/wide fast.")
    ap.add_argument("--output", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--upload", action="store_true")
    ap.add_argument("--title", default=None)
    ap.add_argument("--intro-seconds", type=float, default=4.0,
                    help="branded intro (thumbnail) length; 0 disables (wide only)")
    ap.add_argument("--outro-seconds", type=float, default=15.0,
                    help="branded end-card outro length; 0 disables (wide only)")
    ap.add_argument("--keep-temp", action="store_true")
    args = ap.parse_args()

    date = datetime.date.today().isoformat()
    for d in (DL_DIR, CREATED_DIR, UPLOAD_DIR):
        os.makedirs(d, exist_ok=True)
    suffix = "_16x9" if args.orientation == "wide" else ""
    tagpart = f"_{args.tag}" if args.tag else ""
    out_path = args.output or os.path.join(
        CREATED_DIR, f"CrackIt_Monthly_{date}{tagpart}{suffix}.mp4")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    # --- FROM-FOLDER: skip API+download, build from existing local clips ----
    if args.from_folder:
        clips = CW.gather(args.from_folder)
        if not clips:
            sys.exit(f"No videos found in {args.from_folder}")
        print(f"Using {len(clips)} local clips from {args.from_folder} "
              f"(orientation={args.orientation})")
        _render_and_finalize(clips, out_path, args, f"local folder {args.from_folder}")
        return

    # --- PLAN (list only, no download) -------------------------------------
    if args.source == "drive":
        plan, note = plan_from_drive(args.days)
    else:
        plan, note = plan_from_ytdlp(args.days, args.max_seconds)

    print("\n" + note)
    if not plan:
        sys.exit("No clips to include — nothing to build.")

    # exclude any clips already used in a previous batch (ledger of ids/names)
    if not args.no_ledger and os.path.exists(args.exclude_file):
        excl = {l.strip() for l in open(args.exclude_file) if l.strip()}
        before = len(plan)
        plan = [f for f in plan if (f.get("id") or f.get("name")) not in excl]
        print(f"Excluded {before - len(plan)} already-used clips (ledger: "
              f"{os.path.basename(args.exclude_file)}, {len(excl)} known).")
        if not plan:
            sys.exit("Every candidate clip was already used — nothing new to build.")

    # skip the most recent N first (non-overlapping batches), then cap to N
    if args.skip and len(plan) > args.skip:
        plan = plan[:-args.skip]
        print(f"Skipped the {args.skip} most-recent clips (--skip) — batch offset.")
    if args.limit and len(plan) > args.limit:
        plan = plan[-args.limit:]
        print(f"Capped to most recent {args.limit} of the remaining clips (--limit).")

    # duplicate audit on the planned set (defensive; planners already dedupe)
    keys = [f.get("id") or f.get("name") for f in plan]
    dupes = {k for k in keys if keys.count(k) > 1}

    known = [f["dur"] for f in plan if f.get("dur")]
    if args.source == "ytdlp":
        est = sum(known)
        est_str = f"{CW.fmt_ts(est)} ({est:.0f}s exact from API)"
    else:
        est = len(plan) * 20  # Drive durations unknown until download; ~20s each
        est_str = f"~{CW.fmt_ts(est)} (estimated at 20s/clip)"
    print(f"Planned {len(plan)} clips | total {est_str} | duplicates: "
          f"{'NONE' if not dupes else sorted(dupes)}")
    for i, f in enumerate(plan, 1):
        d = f"{CW.fmt_ts(f['dur']):>5}" if f.get("dur") else "  ?  "
        print(f"  {i:2d}. [{d}] {_plan_label(f)[:70]}")

    if args.dry_run:
        print("\nDRY RUN — planned clips listed above, nothing downloaded or built.")
        return

    # --- BUILD: download into downloaded/<date[_tag]>/, then render + finalize
    dl_dir = os.path.join(DL_DIR, date + tagpart)
    os.makedirs(dl_dir, exist_ok=True)
    print(f"\nDownloading {len(plan)} shorts into {dl_dir} ...")
    clips = download_drive(plan, dl_dir) if args.source == "drive" \
        else download_ytdlp(plan, dl_dir)
    if not clips:
        sys.exit("Nothing downloaded — aborting.")
    print(f"DOWNLOADED (shorts) : {dl_dir}  ({len(clips)} clips)")
    _render_and_finalize(clips, out_path, args, note)

    # record the clips we just used so future batches never repeat them
    if not args.no_ledger:
        with open(args.exclude_file, "a") as f:
            for p in plan:
                f.write((p.get("id") or p.get("name", "")) + "\n")
        print(f"Ledger updated: +{len(plan)} ids -> {os.path.basename(args.exclude_file)}")


def _render_and_finalize(clips, out_path, args, source_note):
    """Normalize each clip to the chosen orientation, join, stage into upload/,
    write metadata, and optionally upload. Shared by the download and
    --from-folder paths."""
    n = len(clips)
    bookend = args.orientation == "wide"
    base = os.path.splitext(out_path)[0]

    # branded thumbnail + end card first (the thumbnail doubles as the intro).
    thumb = base + "_thumbnail.png"
    endcard = base + "_endcard.png"
    try:
        import make_monthly_thumbnail as MT
        MT.generate(thumb, n)
        print(f"THUMBNAIL           : {thumb}")
    except Exception as e:
        thumb = None
        print(f"thumbnail skipped: {e}")
    if bookend:
        try:
            import make_endcard as EC
            EC.generate(endcard)
            print(f"END CARD            : {endcard}")
        except Exception as e:
            endcard = None
            print(f"endcard skipped: {e}")

    intro_sec = args.intro_seconds if (bookend and thumb) else 0
    outro_sec = args.outro_seconds if (bookend and endcard) else 0

    tmp = tempfile.mkdtemp(prefix="monthly_norm_")
    try:
        segs = []
        if intro_sec > 0:
            iseg = os.path.join(tmp, "intro.mp4")
            print(f"  building intro ({intro_sec:.0f}s)")
            CW.image_to_segment(thumb, iseg, intro_sec)
            segs.append(iseg)
        for i, p in enumerate(clips, 1):
            dst = os.path.join(tmp, f"norm_{i:03d}.mp4")
            print(f"  normalizing {i}/{n} ({args.orientation})")
            CW.normalize(p, dst, canvas=args.orientation, index=i, total=n)
            segs.append(dst)
        if outro_sec > 0:
            oseg = os.path.join(tmp, "outro.mp4")
            print(f"  building outro ({outro_sec:.0f}s)")
            CW.image_to_segment(endcard, oseg, outro_sec)
            segs.append(oseg)
        print("  joining...")
        CW.concat(segs, out_path)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    final_dur = CW.probe_duration(out_path)
    size_mb = os.path.getsize(out_path) / 1e6
    print(f"\nCREATED (long video): {out_path}\n  duration {CW.fmt_ts(final_dur)} | size {size_mb:.1f} MB")

    staged = os.path.join(UPLOAD_DIR, os.path.basename(out_path))
    shutil.copy2(out_path, staged)
    print(f"STAGED for upload   : {staged}")
    for asset in (thumb, endcard):
        if asset and os.path.exists(asset):
            shutil.copy2(asset, os.path.join(UPLOAD_DIR, os.path.basename(asset)))

    # chapters offset by the intro length so timestamps stay accurate
    chapters, _ = CW.build_chapters(clips, offset=intro_sec)
    if intro_sec > 0:
        chapters = "00:00 Intro\n" + chapters
    month_label = datetime.date.today().strftime("%B %Y")
    title = args.title or f"Riddle o'Clock — Monthly Riddle Marathon | {month_label}"
    description = (
        f"{len(clips)} tricky riddles and brain teasers with answers — how many can you crack?\n\n"
        f"Chapters:\n{chapters}\n\n"
        f"New riddles daily on Riddle o'Clock. Subscribe and beat the clock!\n"
        f"#riddles #brainteasers #puzzles"
    )
    for base in (out_path, staged):
        with open(os.path.splitext(base)[0] + "_metadata.txt", "w") as f:
            f.write(f"TITLE:\n{title}\n\nDESCRIPTION:\n{description}\n")
    print("  metadata written next to created + upload copies")

    if args.upload:
        print("\nUploading staged video to YouTube...")
        CW.do_upload(staged, title, description)
    else:
        print(f"\nReview {staged} — to upload it as private, re-run with --upload")


if __name__ == "__main__":
    main()
