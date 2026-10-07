#!/usr/bin/env python3
"""Generate a 1920x1080 YouTube end-screen (end card) background for Riddle
o'Clock — same brand system as the thumbnail (navy, gold, cream Playfair, "?"
marks). Leaves clearly labelled zones for YouTube's end-screen elements: a
subscribe circle (bottom-left) and two "watch next" video boxes (right).

Usage:  python3 make_endcard.py [out.png]
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import combine_weekly as C
from PIL import Image, ImageDraw

W, H = 1920, 1080
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

NAVY_TOP = (26, 35, 72)
NAVY_BOT = (12, 18, 42)
CREAM = (242, 236, 218, 255)
GOLD = (216, 180, 106, 255)
SUBT = (146, 156, 192, 255)


def _play(draw, cx, cy, r, color):
    draw.polygon([(cx - r * 0.45, cy - r * 0.7), (cx - r * 0.45, cy + r * 0.7),
                  (cx + r * 0.75, cy)], fill=color)


def generate(out=None):
    if out is None:
        out = os.path.join(SCRIPT_DIR, "created", "endcard.png")
    img = C._gradient(W, H, NAVY_TOP, NAVY_BOT).convert("RGBA")

    # symmetric faint "?" side marks
    qf = C._name_font(820)
    L = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(L).text((-230, 150), "?", font=qf, fill=(255, 255, 255, 26))
    img = Image.alpha_composite(img, L)
    img = Image.alpha_composite(img, L.transpose(Image.Transpose.FLIP_LEFT_RIGHT))
    d = ImageDraw.Draw(img)

    # top-left: logo + name
    logo_p = os.path.join(SCRIPT_DIR, "channel_avatar.png")
    x = 96
    if os.path.exists(logo_p):
        lg = C._circle_logo(logo_p, 104)
        img.paste(lg, (96, 80), lg)
        d = ImageDraw.Draw(img)
        x = 96 + 104 + 24
    d.text((x, 96), "Riddle o'Clock", font=C._name_font(58), fill=CREAM)

    # headline + underline
    d.text((96, 250), "Thanks for", font=C._name_font(104), fill=CREAM)
    hw = d.textlength("Watching!", font=C._name_font(104))
    d.text((96, 372), "Watching!", font=C._name_font(104), fill=CREAM)
    d.rounded_rectangle([100, 500, 100 + min(hw, 620), 507], radius=4, fill=GOLD)
    C._spaced(d, (100, 536), "NEW RIDDLES EVERY DAY  ·  BEAT THE CLOCK",
              C._sans_bold(30), SUBT, spacing=3)

    # subscribe circle zone (bottom-left): bell centered in the ring, label below
    scx, scy, sr = 250, 770, 120
    d.ellipse([scx - sr, scy - sr, scx + sr, scy + sr], outline=GOLD, width=5)
    bsz = 104
    bell = C._bell_icon(bsz, GOLD)
    img.paste(bell, (scx - bsz // 2, scy - bsz // 2 - 6), bell)
    d = ImageDraw.Draw(img)
    sf = C._sans_bold(30)
    stot = sum(d.textlength(c, font=sf) for c in "SUBSCRIBE") + 3 * (len("SUBSCRIBE") - 1)
    C._spaced(d, (scx - stot / 2, scy + sr + 22), "SUBSCRIBE", sf, CREAM, spacing=3)
    # arrow prompt, vertically centered on the circle
    af = C._sans_bold(28)
    C._spaced(d, (scx + sr + 44, scy - 34), "← TAP TO", af, GOLD, spacing=2)
    C._spaced(d, (scx + sr + 44, scy + 8), "SUBSCRIBE", af, GOLD, spacing=2)

    # "WATCH NEXT" video boxes (right) — two 16:9 placeholders
    C._spaced(d, (1230, 118), "WATCH NEXT", C._sans_bold(34), GOLD, spacing=4)
    for i, (bx, by) in enumerate([(1230, 180), (1230, 560)]):
        bw, bh = 590, 332
        d.rounded_rectangle([bx, by, bx + bw, by + bh], radius=20,
                            fill=(255, 255, 255, 16), outline=GOLD, width=3)
        pcx, pcy = bx + bw // 2, by + bh // 2 - 10
        d.ellipse([pcx - 42, pcy - 42, pcx + 42, pcy + 42], outline=CREAM, width=4)
        _play(d, pcx + 4, pcy, 34, CREAM)
        label = "NEXT RIDDLE VIDEO" if i == 0 else "MORE BRAIN TEASERS"
        lw = d.textlength(label, font=C._sans_bold(26))
        C._spaced(d, (pcx - lw // 2 - 12, by + bh - 52), label, C._sans_bold(26),
                  SUBT, spacing=1)

    os.makedirs(os.path.dirname(out), exist_ok=True)
    img.convert("RGB").save(out, quality=92)
    print("endcard:", out)
    return out


if __name__ == "__main__":
    generate(sys.argv[1] if len(sys.argv) > 1 else None)
