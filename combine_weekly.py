#!/usr/bin/env python3
"""
Weekly compilation builder for Riddle o'Clock.

Takes a folder of finished vertical reels (the Shorts you already produced),
normalizes them all to one uniform format, joins them into a single ~10-min
vertical video, and (optionally) uploads it to YouTube as PRIVATE so you can
review + publish from Studio.

WHY NORMALIZE FIRST: reels re-downloaded from YouTube (or from mixed tools)
often differ in codec / resolution / fps / audio layout. ffmpeg's fast concat
requires identical streams, so we re-encode every clip to a common spec first,
THEN join. That's the difference between "works every week" and "randomly fails
on one odd file."

Common spec: 1080x1920, 30fps, H.264, AAC 44.1kHz stereo. Clips that aren't
exactly vertical are scaled to fit and padded with black (never stretched).

USAGE (run locally on your Mac, inside the repo, with .venv active):

    # 1) Drop your ~24 reels into Weekly_Compilation/input/
    #    Order = filename order. Prefix with 01_, 02_, ... to control it.

    # 2) See the running order + total duration WITHOUT building anything:
    python3 combine_weekly.py --dry-run

    # 3) Build the combined video only (no upload) so you can watch it first:
    python3 combine_weekly.py

    # 4) Build AND upload to YouTube as private:
    python3 combine_weekly.py --upload

Flags:
    --input DIR     input folder (default: Weekly_Compilation/input)
    --output FILE   output path (default: Weekly_Compilation/output/CrackIt_Weekly_<date>.mp4)
    --dry-run       list the running order + total duration, build nothing
    --upload        after building, upload to YouTube (privacy from YT_PRIVACY, default private)
    --title "..."   override the video title
    --keep-temp     keep the normalized per-clip temp files (for debugging)
"""
import os, sys, json, glob, re, subprocess, tempfile, shutil, datetime, argparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_INPUT = os.path.join(SCRIPT_DIR, "Weekly_Compilation", "input")
DEFAULT_OUTDIR = os.path.join(SCRIPT_DIR, "Weekly_Compilation", "output")
VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi")

# Target spec — must match across all clips for a clean join.
W, H, FPS, AR, AC = 1080, 1920, 30, 44100, 2


def natural_key(s):
    """Sort so 2_ comes before 10_ (human order, not ASCII order)."""
    return [int(t) if t.isdigit() else t.lower()
            for t in re.split(r"(\d+)", os.path.basename(s))]


def probe_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True)
    try:
        return float(out.stdout.strip())
    except ValueError:
        return 0.0


def fmt_ts(seconds):
    seconds = int(round(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def gather(input_dir):
    files = [p for p in glob.glob(os.path.join(input_dir, "*"))
             if p.lower().endswith(VIDEO_EXTS)]
    files.sort(key=natural_key)
    return files


# --- brand palette -----------------------------------------------------------
GOLD = (214, 178, 104, 255)
GOLD_L = (233, 205, 142, 255)
CREAM = (240, 234, 220, 255)
TEAL_TOP = (16, 50, 46)
NAVY_BOT = (7, 16, 28)
PILL_DARK = (10, 28, 26, 235)
YT_RED = (222, 40, 40, 255)


def _font(names, size, index=0):
    """First existing font from `names`, searched in macOS + DejaVu dirs."""
    from PIL import ImageFont
    roots = ["/System/Library/Fonts/Supplemental/", "/System/Library/Fonts/",
             "/Library/Fonts/", "/usr/share/fonts/truetype/dejavu/"]
    for n in names:
        for r in roots:
            p = r + n
            if os.path.exists(p):
                try:
                    return ImageFont.truetype(p, size, index=index)
                except Exception:
                    pass
    return ImageFont.load_default()


def _name_font(size):   # Playfair Display (matches the channel banner), Bold
    from PIL import ImageFont
    for p in (os.path.join(SCRIPT_DIR, "assets", "PlayfairDisplay-VF.ttf"),
              os.path.expanduser("~/Library/Fonts/PlayfairDisplay-VF.ttf")):
        if os.path.exists(p):
            f = ImageFont.truetype(p, size)
            try:
                f.set_variation_by_axes([700])          # Bold
            except Exception:
                try:
                    f.set_variation_by_name("Bold")
                except Exception:
                    pass
            return f
    return _font(["Georgia Bold.ttf", "Baskerville.ttc", "Didot.ttc",
                  "DejaVuSerif-Bold.ttf"], size)


def _serif_bold(size):
    return _font(["Georgia Bold.ttf", "Georgia.ttf", "Times New Roman.ttf",
                  "DejaVuSerif-Bold.ttf"], size)


def _sans_bold(size):
    return _font(["Arial Bold.ttf", "Arialbd.ttf", "Arial.ttf", "Helvetica.ttc",
                  "DejaVuSans-Bold.ttf"], size)


def _spaced(draw, xy, text, font, fill, spacing=2, right=False):
    """Letter-spaced text; returns total width. right=True right-aligns to x."""
    widths = [draw.textlength(c, font=font) for c in text]
    total = sum(widths) + spacing * max(0, len(text) - 1)
    x, y = xy
    if right:
        x -= total
    for c, w in zip(text, widths):
        draw.text((x, y), c, font=font, fill=fill)
        x += w + spacing
    return total


def _circle_logo(path, size):
    from PIL import Image, ImageDraw
    logo = Image.open(path).convert("RGBA").resize((size, size))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size - 1, size - 1], fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(logo, (0, 0), mask)
    ring = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(ring).ellipse([2, 2, size - 3, size - 3], outline=GOLD, width=5)
    return Image.alpha_composite(out, ring)


def _clock_icon(size, color):
    from PIL import Image, ImageDraw
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse([2, 2, size - 3, size - 3], outline=color, width=3)
    c = size // 2
    d.line([c, c, c, c - size // 3], fill=color, width=3)
    d.line([c, c, c + size // 4, c + 2], fill=color, width=3)
    return im


def _bell_icon(size, color):
    """A simple notification-bell glyph (dome + flared body + rim + clapper)."""
    from PIL import Image, ImageDraw
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    w = h = size
    cx = w // 2
    top = int(h * 0.20)
    bot = int(h * 0.70)
    # top knob
    kr = max(2, int(h * 0.055))
    d.ellipse([cx - kr, top - kr, cx + kr, top + kr], fill=color)
    # dome + body (rounded shoulders flaring to a wider base)
    d.pieslice([int(w * 0.28), top, int(w * 0.72), int(h * 0.55)], 180, 360, fill=color)
    d.polygon([(int(w * 0.30), int(h * 0.36)), (int(w * 0.70), int(h * 0.36)),
               (int(w * 0.80), bot), (int(w * 0.20), bot)], fill=color)
    # rim
    d.rounded_rectangle([int(w * 0.16), bot - 3, int(w * 0.84), bot + 4],
                        radius=4, fill=color)
    # clapper
    r = max(2, int(h * 0.075))
    d.ellipse([cx - r, bot + 3, cx + r, bot + 3 + 2 * r], fill=color)
    return im


def _gradient(W, H, top, bot):
    from PIL import Image
    col = Image.new("RGB", (1, H))
    px = col.load()
    for y in range(H):
        t = y / (H - 1)
        px[0, y] = (int(top[0] * (1 - t) + bot[0] * t),
                    int(top[1] * (1 - t) + bot[1] * t),
                    int(top[2] * (1 - t) + bot[2] * t))
    return col.resize((W, H)).convert("RGBA")


def _make_canvas(index, total, W, H, out_png):
    """Full 1920x1080 background + branding, rendered with Pillow (no video blur):
    brand-gradient backdrop, a framed center window (soft shadow + gold border)
    where the vertical clip will sit, elegant serif channel name + logo top-left,
    a gold 'RIDDLE n / N' counter pill with a clock icon bottom-left, and a red
    YouTube-style subscribe button bottom-right."""
    from PIL import Image, ImageDraw, ImageFilter
    img = _gradient(W, H, TEAL_TOP, NAVY_BOT)

    # framed center window (must match the ffmpeg overlay: h=1000, centered)
    vh = 1000
    vw = 562  # 1000 * 1080/1920 rounded to even (matches scale=-2:1000)
    vx, vy = (W - vw) // 2, (H - vh) // 2
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        [vx - 16, vy - 16, vx + vw + 16, vy + vh + 16], radius=30, fill=(0, 0, 0, 170))
    img = Image.alpha_composite(img, shadow.filter(ImageFilter.GaussianBlur(20)))
    d = ImageDraw.Draw(img)
    # NOTE: no gold frame here — the Shorts already carry their own border, so a
    # second one would double up. The soft shadow alone gives depth.

    # top-left: logo + Playfair name, with the tagline letter-spaced to align
    # exactly to the name's width and sit a clean gap below it.
    x = 46
    logo_p = os.path.join(SCRIPT_DIR, "channel_avatar.png")
    if os.path.exists(logo_p):
        sz = 112
        logo = _circle_logo(logo_p, sz)
        img.paste(logo, (46, 32), logo)
        x = 46 + sz + 26
    nf = _name_font(54)
    ny = 34
    d.text((x, ny), "Riddle o'Clock", font=nf, fill=GOLD_L)
    nb = d.textbbox((x, ny), "Riddle o'Clock", font=nf)
    name_w = nb[2] - nb[0]
    tag, tf = "DAILY BRAIN TEASERS", _sans_bold(19)
    base = sum(d.textlength(c, font=tf) for c in tag)
    sp = max(2.0, (name_w - base) / (len(tag) - 1))
    _spaced(d, (x, nb[3] + 14), tag, tf, GOLD, spacing=sp)

    # bottom-left: gold counter pill with clock icon
    if index and total:
        txt = f"RIDDLE {index:02d} / {total}"
        cf = _serif_bold(34)
        tw = int(sum(d.textlength(c, font=cf) for c in txt) + 3 * (len(txt) - 1))
        ic = 40
        pad = 22
        pw = pad + ic + 14 + tw + pad
        ph = 68
        px0, py0 = 46, H - 46 - ph
        d.rounded_rectangle([px0, py0, px0 + pw, py0 + ph], radius=ph // 2,
                            fill=PILL_DARK, outline=GOLD, width=2)
        clk = _clock_icon(ic, GOLD)
        img.paste(clk, (px0 + pad, py0 + (ph - ic) // 2), clk)
        d = ImageDraw.Draw(img)
        _spaced(d, (px0 + pad + ic + 14, py0 + (ph - 34) // 2 - 2), txt, cf, GOLD_L, spacing=3)

    # bottom-right: YouTube-style red subscribe button (play glyph + text)
    label = "SUBSCRIBE"
    sf = _sans_bold(32)
    tw = int(sum(d.textlength(c, font=sf) for c in label) + 2 * (len(label) - 1))
    play_w = 44
    padx = 26
    gap = 16
    bw = padx + play_w + gap + tw + padx
    bh = 70
    bx, by = W - 46 - bw, H - 46 - bh
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle([bx, by + 4, bx + bw, by + bh + 4],
                                         radius=bh // 2, fill=(0, 0, 0, 150))
    img = Image.alpha_composite(img, sh.filter(ImageFilter.GaussianBlur(9)))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([bx, by, bx + bw, by + bh], radius=bh // 2, fill=YT_RED)
    # white bell glyph
    bell = _bell_icon(play_w, (255, 255, 255, 255))
    img.paste(bell, (bx + padx, by + (bh - play_w) // 2), bell)
    d = ImageDraw.Draw(img)
    _spaced(d, (bx + padx + play_w + gap, by + (bh - 32) // 2 - 2), label, sf,
            (255, 255, 255, 255), spacing=2)

    img.convert("RGB").save(out_png)


def _enc_tail(dst):
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-pix_fmt", "yuv420p", "-video_track_timescale", "30000",
            "-c:a", "aac", "-ar", str(AR), "-ac", str(AC), "-b:a", "192k", dst]


def normalize(src, dst, canvas="vertical", index=None, total=None):
    """Re-encode one clip to the common spec so concat -c copy is safe.

    canvas="vertical" -> 1080x1920 (scale-to-fit + black pad).
    canvas="wide"     -> 1920x1080 for long-form YouTube: the sharp vertical clip
                         centered over a blurred, darkened, zoomed copy of itself,
                         with light branding in the side space (channel logo, a
                         'Riddle i of n' counter, and a SUBSCRIBE tag). Branding
                         degrades gracefully if the font/logo aren't found."""
    ov_png = None
    if canvas == "wide":
        WO, HO = 1920, 1080
        ov_png = dst + ".canvas.png"
        _make_canvas(index, total, WO, HO, ov_png)
        # input 0 = static canvas (looped), input 1 = the vertical clip
        fc = (f"[1:v]scale=-2:1000,setsar=1[fg];"
              f"[0:v][fg]overlay=(W-w)/2:(H-h)/2:shortest=1,fps={FPS}[v]")
        cmd = ["ffmpeg", "-y", "-loop", "1", "-i", ov_png, "-i", src,
               "-filter_complex", fc, "-map", "[v]", "-map", "1:a:0?",
               "-shortest"] + _enc_tail(dst)
    else:
        vf = (f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
              f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:black,setsar=1,fps={FPS}")
        cmd = ["ffmpeg", "-y", "-i", src, "-vf", vf,
               "-map", "0:v:0", "-map", "0:a:0?"] + _enc_tail(dst)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if ov_png and os.path.exists(ov_png):
        os.remove(ov_png)
    if r.returncode != 0:
        raise RuntimeError(f"normalize failed for {os.path.basename(src)}:\n{r.stderr[-800:]}")


def image_to_segment(img_path, dst, seconds, w=1920, h=1080):
    """Turn a still image into a `seconds`-long silent video segment encoded to
    the SAME spec as normalize(), so it concats cleanly with the clips."""
    vf = (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
          f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black,setsar=1,fps={FPS}")
    cmd = ["ffmpeg", "-y", "-loop", "1", "-i", img_path,
           "-f", "lavfi", "-i", f"anullsrc=r={AR}:cl=stereo",
           "-t", str(seconds), "-vf", vf,
           "-map", "0:v:0", "-map", "1:a:0"] + _enc_tail(dst)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"segment build failed for {os.path.basename(img_path)}:\n{r.stderr[-800:]}")


def concat(norm_files, out_path):
    """Join the already-uniform clips with the concat demuxer (no re-encode)."""
    listfile = out_path + ".concat.txt"
    with open(listfile, "w") as f:
        for p in norm_files:
            f.write(f"file '{p}'\n")
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listfile,
           "-c", "copy", out_path]
    r = subprocess.run(cmd, capture_output=True, text=True)
    os.remove(listfile)
    if r.returncode != 0:
        raise RuntimeError(f"concat failed:\n{r.stderr[-800:]}")


def build_chapters(files, offset=0.0):
    """YouTube chapter list: first must be 00:00, each >= 10s. `offset` shifts all
    timestamps (e.g. by the intro length). The first chapter is always 00:00."""
    lines, t = [], float(offset)
    for i, p in enumerate(files, 1):
        lines.append(f"{fmt_ts(t)} Riddle {i}")
        t += probe_duration(p)
    return "\n".join(lines), t


def do_upload(out_path, title, description):
    """Reuse the existing OAuth (token.json) from upload_youtube.py."""
    sys.path.insert(0, SCRIPT_DIR)
    import upload_youtube as U
    from googleapiclient.http import MediaFileUpload
    privacy = os.environ.get("YT_PRIVACY", "private")
    service = U.get_service()
    body = {
        "snippet": {"title": title, "description": description,
                    "tags": ["riddles", "brain teasers", "riddles with answers",
                             "compilation", "puzzles"], "categoryId": "24"},
        "status": {"privacyStatus": privacy,
                   "selfDeclaredMadeForKids": False, "madeForKids": False},
    }
    media = MediaFileUpload(out_path, chunksize=-1, resumable=True, mimetype="video/mp4")
    req = service.videos().insert(part="snippet,status", body=body, media_body=media)
    resp = None
    while resp is None:
        status, resp = req.next_chunk()
        if status:
            print(f"  upload {int(status.progress()*100)}%")
    vid = resp["id"]
    print("UPLOADED:", f"https://youtu.be/{vid}")
    print("Studio  :", f"https://studio.youtube.com/video/{vid}/edit")
    print(f"Privacy = {privacy}. Open Studio to review and publish.")
    return vid


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=DEFAULT_INPUT)
    ap.add_argument("--output", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--upload", action="store_true")
    ap.add_argument("--title", default=None)
    ap.add_argument("--keep-temp", action="store_true")
    args = ap.parse_args()

    files = gather(args.input)
    if not files:
        sys.exit(f"No videos found in {args.input}\n"
                 f"Drop your reels there (mp4/mov/mkv/webm) and re-run.")

    print(f"Found {len(files)} clips in {args.input}\nRunning order:")
    total = 0.0
    for i, p in enumerate(files, 1):
        d = probe_duration(p)
        total += d
        print(f"  {i:2d}. [{fmt_ts(d):>5}] {os.path.basename(p)}")
    print(f"\nTotal duration: {fmt_ts(total)} ({total:.0f}s) across {len(files)} clips")

    if args.dry_run:
        print("\nDRY RUN — nothing built. Adjust filenames to reorder, then re-run without --dry-run.")
        return

    date = datetime.date.today().isoformat()
    out_path = args.output or os.path.join(DEFAULT_OUTDIR, f"CrackIt_Weekly_{date}.mp4")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    tmp = tempfile.mkdtemp(prefix="weekly_norm_")
    try:
        norm_files = []
        for i, p in enumerate(files, 1):
            dst = os.path.join(tmp, f"{i:03d}.mp4")
            print(f"  normalizing {i}/{len(files)}: {os.path.basename(p)}")
            normalize(p, dst)
            norm_files.append(dst)
        print("  joining...")
        concat(norm_files, out_path)
    finally:
        if not args.keep_temp:
            shutil.rmtree(tmp, ignore_errors=True)
        else:
            print(f"  (kept temp clips in {tmp})")

    final_dur = probe_duration(out_path)
    size_mb = os.path.getsize(out_path) / 1e6
    print(f"\nBUILT: {out_path}")
    print(f"  duration {fmt_ts(final_dur)} | size {size_mb:.1f} MB")

    chapters, _ = build_chapters(files)
    title = args.title or f"Riddle o'Clock Weekly — {len(files)} Riddles with Answers | {date}"
    description = (
        f"{len(files)} tricky riddles and brain teasers with answers — how many can you crack?\n\n"
        f"Chapters:\n{chapters}\n\n"
        f"New riddles daily on Riddle o'Clock. Subscribe and beat the clock!\n"
        f"#riddles #brainteasers #puzzles"
    )
    # Stash metadata next to the video so you can copy it into Studio if needed.
    meta_path = os.path.splitext(out_path)[0] + "_metadata.txt"
    with open(meta_path, "w") as f:
        f.write(f"TITLE:\n{title}\n\nDESCRIPTION:\n{description}\n")
    print(f"  metadata written: {meta_path}")

    if args.upload:
        print("\nUploading to YouTube...")
        do_upload(out_path, title, description)
    else:
        print("\nReview the file above. To upload it as private, re-run with --upload")


if __name__ == "__main__":
    main()
