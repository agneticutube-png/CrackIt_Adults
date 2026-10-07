#!/usr/bin/env python3
"""Generate a 1280x720 YouTube thumbnail for the monthly riddle marathon.

Design language mirrors the channel's own banner + profile (brand cohesion):
navy background, cream Playfair headline, a gold "pill" label, a gold underline,
faint white "?" corner marks, and the clock-"?" mascot — centered, elegant, and
minimal. Everything sits inside a cross-device safe margin.

Usage:  python3 make_monthly_thumbnail.py [out.png] [count]
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import combine_weekly as C
from PIL import Image, ImageDraw

W, H = 1280, 720
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

NAVY_TOP = (26, 35, 72)
NAVY_BOT = (12, 18, 42)
CREAM = (242, 236, 218, 255)
GOLD = (216, 180, 106, 255)
PILL_TXT = (18, 26, 54, 255)
SUBT = (146, 156, 192, 255)


def ctext(d, cy, text, font, fill):
    w = d.textlength(text, font=font)
    d.text(((W - w) / 2, cy), text, font=font, fill=fill)
    return w


def cspaced(d, cy, text, font, fill, spacing):
    total = sum(d.textlength(c, font=font) for c in text) + spacing * (len(text) - 1)
    C._spaced(d, ((W - total) / 2, cy), text, font, fill, spacing=spacing)
    return total


def generate(out=None, count="31"):
    """Render the monthly thumbnail (1280x720) to `out`. Reusable from the
    monthly pipeline; `count` is the number of riddles in the compilation."""
    count = str(count)
    if out is None:
        out = os.path.join(SCRIPT_DIR, "created", "thumbnail.png")
    img = C._gradient(W, H, NAVY_TOP, NAVY_BOT).convert("RGBA")

    # faint white "?" side marks (banner motif): symmetric, mirrored, same height,
    # partially off each edge.
    qf = C._name_font(560)
    lx, ly, qa = -150, 92, 32
    L = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(L).text((lx, ly), "?", font=qf, fill=(255, 255, 255, qa))
    img = Image.alpha_composite(img, L)                       # left
    img = Image.alpha_composite(img, L.transpose(Image.Transpose.FLIP_LEFT_RIGHT))  # right (mirror)
    d = ImageDraw.Draw(img)

    # mascot logo, centered top
    logo_p = os.path.join(SCRIPT_DIR, "channel_avatar.png")
    y = 44
    if os.path.exists(logo_p):
        sz = 92
        lg = C._circle_logo(logo_p, sz)
        img.paste(lg, ((W - sz) // 2, y), lg)
        d = ImageDraw.Draw(img)
        y += sz + 22

    # gold pill label
    pill = "MONTHLY RIDDLE MARATHON"
    pf = C._sans_bold(26)
    ptw = int(sum(d.textlength(c, font=pf) for c in pill) + 5 * (len(pill) - 1))
    pw, ph = ptw + 60, 52
    d.rounded_rectangle([(W - pw) // 2, y, (W + pw) // 2, y + ph], radius=ph // 2, fill=GOLD)
    cspaced(d, y + 11, pill, pf, PILL_TXT, 5)
    y += ph + 40

    # cream Playfair headline (two centered lines)
    ctext(d, y, "Can You Solve", C._name_font(78), CREAM)
    y += 92
    hw = ctext(d, y, f"All {count} Riddles?", C._name_font(120), CREAM)
    y += 150

    # gold underline (banner motif)
    ux = (W - min(hw, 720)) / 2
    d.rounded_rectangle([ux, y, W - ux, y + 6], radius=3, fill=GOLD)
    y += 34

    # muted subtitle
    cspaced(d, y, "10 SECONDS EACH  ·  ANSWERS REVEALED", C._sans_bold(24), SUBT, 3)

    os.makedirs(os.path.dirname(out), exist_ok=True)
    img.convert("RGB").save(out, quality=92)
    print("thumbnail:", out)
    return out


if __name__ == "__main__":
    _out = sys.argv[1] if len(sys.argv) > 1 else None
    _count = sys.argv[2] if len(sys.argv) > 2 else "31"
    generate(_out, _count)
