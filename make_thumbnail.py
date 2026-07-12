#!/usr/bin/env python3
"""
Dedicated Shorts THUMBNAIL generator (poster image, not a video frame).

Why this exists: the video's first frame reserves its lower half for the
countdown ring, so as a static grid/search tile the question floats small and
high with dead space below. This renders a separate 1080x1920 poster where the
QUESTION fills the frame (big, centered) — the question IS the thumbnail. It
reuses render_video's theme/background so the poster is visually consistent with
the matching video (same palette per seed).

Public API:
    make_thumb(riddle, seed, out_path) -> out_path   (writes a PNG/JPG)

CLI:
    python3 make_thumbnail.py <seed> "riddle text" [out.jpg]
"""
import os, sys, re
from PIL import ImageDraw
import render_video as rv


def make_thumb(riddle, seed, out_path):
    theme = rv.build_theme(int(seed))
    pal = theme["palette"]
    GOLD, CREAM, TOP = pal["accent"], pal["cream"], pal["top"]

    img = rv.base_bg(theme)                       # same bg/watermark as the video
    d = ImageDraw.Draw(img, "RGBA")

    # Kicker badge (top), identical placement to the video for brand continuity.
    kf = rv.SANS_B(38); kick = theme["kicker"]; kw = rv.spaced_w(d, kick, kf, 10)
    bx0 = (rv.W - (kw + 96)) / 2
    d.rounded_rectangle([bx0, 250, bx0 + kw + 96, 336], radius=42,
                        fill=(GOLD[0], GOLD[1], GOLD[2], 235))
    rv.spaced(d, kick, kf, bx0 + 48, 272, (TOP[0], TOP[1], TOP[2]), 10)

    # Persistent BRAND handle under the badge — matches the video for continuity.
    bf = rv.SANS_B(30)
    rv.spaced(d, rv.BRAND, bf, (rv.W - rv.spaced_w(d, rv.BRAND, bf, 8)) / 2, 368,
              (GOLD[0], GOLD[1], GOLD[2], 255), 8)

    # QUESTION — big and centered in the full frame below the badge. Auto-shrink
    # so even long riddles stay inside safe margins and never crowd the edges.
    riddle = re.sub(r'\s*what am i\s*\??\s*$', '', str(riddle), flags=re.I).strip()
    BAND_TOP, BAND_BOT = 336 + 120, rv.H - 300     # generous poster band
    BAND_H = BAND_BOT - BAND_TOP
    size = 110
    while True:
        f = rv.SERIF_B(size)
        lines = rv.wrap(d, riddle, f, rv.W - 160)
        asc, desc = f.getmetrics(); lh = int((asc + desc) * 1.22)
        if lh * len(lines) <= BAND_H or size <= 60:
            break
        size -= 4
    cy = BAND_TOP + BAND_H / 2
    rv.draw_block(d, lines, f, int(cy), (CREAM[0], CREAM[1], CREAM[2]), lh=1.22)

    # "What am I?" accent under the question — small, gold, ties it to the format.
    wf = rv.SERIF(58); wa = "What am I?"
    block_h = int((rv.SERIF_B(size).getmetrics()[0] + rv.SERIF_B(size).getmetrics()[1]) * 1.22) * len(lines)
    wy = int(cy + block_h / 2 + 40)
    d.text(((rv.W - d.textlength(wa, font=wf)) / 2, wy), wa,
           font=wf, fill=(GOLD[0], GOLD[1], GOLD[2], 255))

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    img.convert("RGB").save(out_path, quality=92)
    return out_path


if __name__ == "__main__":
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    riddle = sys.argv[2] if len(sys.argv) > 2 else \
        "I have keys but open no locks. I have space but no room. What am I?"
    out = sys.argv[3] if len(sys.argv) > 3 else \
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "Videos", f"THUMB_{seed}.jpg")
    print("SAVED:", make_thumb(riddle, seed, out))
