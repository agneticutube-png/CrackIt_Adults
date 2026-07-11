#!/usr/bin/env python3
"""
Production riddle-Short renderer with a VARIATION ENGINE.

Why this exists: posting visually-identical videos daily is exactly the
"mass-produced / templated" pattern YouTube's inauthentic-content policy
hard-enforces against. This module deterministically varies palette (weekly)
and layout (per-video) so the channel reads as a crafted series, not a stamp.

Public API:
    render(riddle, answer, seed, out_path, kind="adult", fps=30) -> out_path
    build_theme(seed, kind="adult") -> dict   (inspect a variant without rendering)

Locked format (do not change without product reason):
    1080x1920 vertical, 20s total: 2s hook, ~5s read, 10s countdown ring
    (7s->17s), answer reveal (17s), then a seamless-loop outro that fades all
    content back out so the final frame == frame 0 (bg + kicker only). This
    makes YouTube's auto-loop cut invisible and pulls viewers back into the
    hook instead of swiping away at the answer reveal.

CLI (for local testing):
    python3 render_video.py <seed> ["riddle text" "answer"]
"""
import os, sys, math, subprocess, shutil, re, hashlib, tempfile
from PIL import Image, ImageDraw, ImageFont

# ---------- locked config ----------
W, H = 1080, 1920
DUR = 20.0

FD = "/usr/share/fonts/truetype/dejavu"
def _font(name, size): return ImageFont.truetype(os.path.join(FD, name), size)
SERIF_B = lambda s: _font("DejaVuSerif-Bold.ttf", s)
SERIF   = lambda s: _font("DejaVuSerif.ttf", s)
SANS_B  = lambda s: _font("DejaVuSans-Bold.ttf", s)
SANS    = lambda s: _font("DejaVuSans.ttf", s)

# ---------- VARIATION ENGINE ----------
# Each palette: deep jewel background (top->bottom) + a metallic accent, a light
# "cream" for body text, and a muted "dim" for secondary text. Hand-tuned to
# stay premium and keep gold-family accents legible on dark grounds.
PALETTES = [
    {"name": "Midnight Indigo", "top": (20, 24, 50),  "bot": (39, 48, 92),
     "accent": (231, 183, 101), "cream": (243, 236, 221), "dim": (181, 188, 214)},
    {"name": "Deep Emerald",    "top": (8, 30, 28),   "bot": (20, 60, 52),
     "accent": (214, 186, 122), "cream": (240, 238, 224), "dim": (168, 196, 184)},
    {"name": "Royal Burgundy",  "top": (40, 14, 26),  "bot": (84, 30, 50),
     "accent": (226, 180, 152), "cream": (245, 233, 230), "dim": (206, 172, 184)},
    {"name": "Slate & Copper",  "top": (24, 26, 32),  "bot": (48, 52, 62),
     "accent": (210, 150, 108), "cream": (238, 236, 232), "dim": (176, 184, 196)},
    {"name": "Royal Purple",    "top": (28, 16, 48),  "bot": (60, 38, 96),
     "accent": (231, 196, 120), "cream": (242, 236, 246), "dim": (190, 176, 214)},
    {"name": "Deep Teal",       "top": (10, 32, 40),  "bot": (22, 64, 76),
     "accent": (228, 196, 140), "cream": (236, 240, 240), "dim": (164, 192, 200)},
    {"name": "Oxblood Navy",    "top": (16, 20, 40),  "bot": (58, 30, 42),
     "accent": (228, 206, 160), "cream": (244, 238, 230), "dim": (188, 184, 196)},
]

BG_STYLES   = ["vertical", "diagonal", "radial"]
ACCENTS     = ["frame", "brackets", "rules", "none"]
WM_POS      = ["center", "upper", "lower"]
RING_STYLES = ["solid", "ticks"]
KICKERS     = ["DAILY RIDDLE", "RIDDLE O'CLOCK", "BRAIN TEASER", "CAN YOU SOLVE IT?"]
HOOKS = [
    (["Can you", "solve this?"], "Most people get it wrong"),
    (["There's a", "hidden twist"], "The answer isn't what you think"),
    (["Think you're", "sharp enough?"], "Prove it before time runs out"),
    (["A riddle", "for the bold"], "How fast can you crack it?"),
]
# On-screen prompt shown under the timer. Rotated per video for variety AND to
# turn silent views into comment engagement. Challenge/deadline-framed and using
# "guess" (lower stakes than "answer" = more lurkers comment). No stats by design.
TIPS = ["GUESS BEFORE THE TIMER", "THINK YOU KNOW? PROVE IT",
        "COMMENT YOUR GUESS", "FIRST TO GUESS WINS",
        "CAN YOU CRACK IT? COMMENT", "DROP YOUR GUESS BELOW"]

def _h(seed, salt):
    return int(hashlib.sha256(f"{seed}:{salt}".encode()).hexdigest(), 16)

def build_theme(seed, kind="adult"):
    """Deterministic variant. Palette rotates WEEKLY (every 7 seeds);
    layout varies PER video."""
    seed = int(seed); week = seed // 7
    pal = PALETTES[week % len(PALETTES)]
    return {
        "palette":  pal,
        "bg_style": BG_STYLES[_h(seed, "bg") % len(BG_STYLES)],
        "accent":   ACCENTS[_h(seed, "ac") % len(ACCENTS)],
        "wm_pos":   WM_POS[_h(seed, "wm") % len(WM_POS)],
        "ring":     RING_STYLES[_h(seed, "rg") % len(RING_STYLES)],
        "kicker":   KICKERS[_h(seed, "ki") % len(KICKERS)],
        "hook":     HOOKS[_h(seed, "hk") % len(HOOKS)],
        "tip":      TIPS[_h(seed, "tip") % len(TIPS)],
        "q_cy":     520 + (_h(seed, "qy") % 90),
        "week":     week,
    }

# ---------- helpers ----------
def smooth(t):
    t = max(0.0, min(1.0, t)); return t * t * (3 - 2 * t)

def lerp(a, b, t): return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))

def wrap(draw, text, fnt, maxw):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=fnt) <= maxw: cur = t
        else:
            if cur: lines.append(cur)
            cur = w
    if cur: lines.append(cur)
    return lines

def draw_block(draw, lines, fnt, cy, fill, lh=1.28, center_x=W // 2):
    asc, desc = fnt.getmetrics(); line_h = int((asc + desc) * lh)
    y = cy - (line_h * len(lines)) / 2
    for ln in lines:
        wln = draw.textlength(ln, font=fnt)
        draw.text((center_x - wln / 2, y), ln, font=fnt, fill=fill); y += line_h

def spaced(draw, text, fnt, x, y, fill, sp=8):
    for ch in text:
        draw.text((x, y), ch, font=fnt, fill=fill); x += draw.textlength(ch, font=fnt) + sp

def spaced_w(draw, text, fnt, sp=8):
    return sum(draw.textlength(c, font=fnt) + sp for c in text) - sp

def _radial(top, bot):
    img = Image.new("RGB", (W, H), bot); px = img.load()
    cx, cy = W / 2, H * 0.42
    maxd = math.hypot(max(cx, W - cx), max(cy, H - cy))
    for y in range(0, H, 2):
        for x in range(0, W, 2):
            c = lerp(top, bot, smooth(math.hypot(x - cx, y - cy) / maxd))
            for dy in range(2):
                for dx in range(2):
                    if x + dx < W and y + dy < H: px[x + dx, y + dy] = c
    return img

def base_bg(theme):
    pal = theme["palette"]; top, bot, acc = pal["top"], pal["bot"], pal["accent"]
    style = theme["bg_style"]
    if style == "radial":
        img = _radial(top, bot)
    else:
        img = Image.new("RGB", (W, H), top); d = ImageDraw.Draw(img)
        for y in range(H):
            d.line([(0, y), (W, y)], fill=lerp(top, bot, y / H))
        if style == "diagonal":
            sh = Image.new("RGBA", (W, H), (0, 0, 0, 0)); ds = ImageDraw.Draw(sh)
            ds.polygon([(0, 0), (W, 0), (0, H)], fill=(acc[0], acc[1], acc[2], 10))
            img = Image.alpha_composite(img.convert("RGBA"), sh).convert("RGB")

    wm = Image.new("RGBA", (W, H), (0, 0, 0, 0)); dw = ImageDraw.Draw(wm)
    f = SERIF_B(1150); bb = dw.textbbox((0, 0), "?", font=f)
    qw, qh = bb[2] - bb[0], bb[3] - bb[1]
    wy = {"center": (H - qh) / 2 - 60, "upper": 60, "lower": H - qh - 120}[theme["wm_pos"]]
    dw.text(((W - qw) / 2 - bb[0], wy - bb[1]), "?", font=f, fill=(255, 255, 255, 15))
    img = Image.alpha_composite(img.convert("RGBA"), wm)

    d = ImageDraw.Draw(img, "RGBA"); ga = (acc[0], acc[1], acc[2], 150); m = 46
    if theme["accent"] == "frame":
        d.rounded_rectangle([m, m, W - m, H - m], radius=34, outline=ga, width=3)
    elif theme["accent"] == "brackets":
        L = 150
        for (x0, y0, x1, y1) in [(m, m, m + L, m), (m, m, m, m + L),
                                 (W - m - L, m, W - m, m), (W - m, m, W - m, m + L),
                                 (m, H - m, m + L, H - m), (m, H - m - L, m, H - m),
                                 (W - m - L, H - m, W - m, H - m), (W - m, H - m - L, W - m, H - m)]:
            d.line([(x0, y0), (x1, y1)], fill=ga, width=5)
    elif theme["accent"] == "rules":
        d.line([(m + 30, 250), (W - m - 30, 250)], fill=ga, width=3)
        d.line([(m + 30, H - 250), (W - m - 30, H - 250)], fill=ga, width=3)
    return img

# ---------- render ----------
def render(riddle, answer, seed, out_path, kind="adult", fps=30):
    theme = build_theme(seed, kind); pal = theme["palette"]
    TOP, BOT, GOLD = pal["top"], pal["bot"], pal["accent"]
    CREAM, DIM = pal["cream"], pal["dim"]
    nframes = int(fps * DUR)

    riddle = re.sub(r'\s*what am i\s*\??\s*$', '', str(riddle), flags=re.I).strip()
    framedir = tempfile.mkdtemp(prefix=f"riddle_frames_{seed}_")

    BG = base_bg(theme)
    # --- Dynamic riddle fit ---------------------------------------------------
    # The riddle must ALWAYS sit in the band BETWEEN the header badge and the
    # countdown ring, with padding on both sides, no matter how many lines it
    # wraps to (the sheet feeds variable-length riddles). We center the
    # (riddle + "What am I?") block in that band, and auto-shrink the font a step
    # at a time if a long riddle would otherwise crowd either edge — so it can
    # never overlap the template.
    md = ImageDraw.Draw(BG.copy())                  # measuring surface
    HEADER_BOT = 326                                # badge bottom (safe-area)
    RING_TOP   = 1230 - 150                         # countdown ring top edge (1080)
    TOP_PAD, BOT_PAD = 120, 90                      # breathing room above/below
    BAND_TOP, BAND_BOT = HEADER_BOT + TOP_PAD, RING_TOP - BOT_PAD
    BAND_H = BAND_BOT - BAND_TOP
    wa_font = SERIF(50); _wa = wa_font.getmetrics(); WA_H = _wa[0] + _wa[1]
    WA_GAP = 46                                     # gap: riddle block -> "What am I?"
    rf_size = 64
    while True:
        riddle_font = SERIF_B(rf_size)
        rlines = wrap(md, riddle, riddle_font, W - 230)
        asc, desc = riddle_font.getmetrics(); lh_px = int((asc + desc) * 1.3)
        block_h = lh_px * len(rlines)
        total_h = block_h + WA_GAP + WA_H
        if total_h <= BAND_H or rf_size <= 44:
            break
        rf_size -= 4
    block_top = BAND_TOP + (BAND_H - total_h) / 2   # center block within the band
    q_cy = block_top + block_h / 2                  # draw_block center for the riddle
    wa_y = block_top + block_h + WA_GAP             # top of the "What am I?" line
    hook_lines, hook_sub = theme["hook"]
    HOLD = {"f0": None}  # cached frame 0, filled after frame() is defined

    def frame(i):
        t = i / fps; img = BG.copy(); d = ImageDraw.Draw(img, "RGBA")
        # Rec 2 (seamless loop): in the final second, fade ALL content (riddle +
        # answer card) back out so the last frame matches frame 0 (bg + kicker
        # only, hook still at alpha 0). The YouTube auto-loop then has no visible
        # cut, so viewers fall back into the hook instead of swiping at reveal.
        outro = 1.0 - smooth((t - 19.0) / 1.0) if t >= 19.0 else 1.0
        kf = SANS_B(34); kick = theme["kicker"]; kw = spaced_w(d, kick, kf, 10)
        # Safe-area: keep the badge below the platform top-nav band (~12% on
        # IG/Shorts). Sits at ~13-17% so Reels/Friends tabs don't cover it.
        bx0 = (W - (kw + 84)) / 2
        d.rounded_rectangle([bx0, 250, bx0 + kw + 84, 326], radius=38,
                            fill=(GOLD[0], GOLD[1], GOLD[2], 235))
        spaced(d, kick, kf, bx0 + 42, 270, (TOP[0], TOP[1], TOP[2]), 10)

        # HOOK = CONTENT. The riddle is on-screen from frame 0 (fast 0.4s fade-in)
        # so a scroller sees real substance immediately, not a content-free hook
        # card. (Data: avg view duration ~4.7s on a 20s video meant most viewers
        # swiped during the old 2s generic hook, before the riddle ever appeared.)
        a = 255 if t >= 0.4 else int(255 * smooth(t / 0.4))
        draw_block(d, rlines, riddle_font, q_cy, (CREAM[0], CREAM[1], CREAM[2], a), lh=1.3)
        if t >= 0.8:
            wa_a = int(255 * smooth((t - 0.8) / 0.4)); wa = "What am I?"
            d.text(((W - d.textlength(wa, font=wa_font)) / 2, wa_y),
                   wa, font=wa_font, fill=(GOLD[0], GOLD[1], GOLD[2], wa_a))
        # Brief attention sub-line just under the badge, fades out by ~2s — keeps
        # the "hook" energy without ever hiding the riddle.
        if t < 2.1:
            sa = int(255 * (smooth(t / 0.3) if t < 0.3 else max(0.0, 1 - smooth((t - 1.4) / 0.7))))
            sf = SANS(34)
            d.text(((W - d.textlength(hook_sub, font=sf)) / 2, 360),
                   hook_sub, font=sf, fill=(DIM[0], DIM[1], DIM[2], sa))

        cx, cy, R = W // 2, 1230, 150
        if 7.0 <= t < 17.0:
            remain = 17.0 - t; secs = int(math.ceil(remain)); frac = remain / 10.0
            if theme["ring"] == "ticks":
                for k in range(60):
                    ang = math.radians(k * 6 - 90); big = (k % 5 == 0)
                    r0 = R - (26 if big else 14); r1 = R
                    lit = (k / 60.0) <= frac
                    col = (GOLD[0], GOLD[1], GOLD[2], 255) if lit else (255, 255, 255, 40)
                    d.line([(cx + r0 * math.cos(ang), cy + r0 * math.sin(ang)),
                            (cx + r1 * math.cos(ang), cy + r1 * math.sin(ang))],
                           fill=col, width=6 if big else 3)
            else:
                d.ellipse([cx - R, cy - R, cx + R, cy + R], outline=(255, 255, 255, 45), width=14)
                d.arc([cx - R, cy - R, cx + R, cy + R], -90, -90 + 360 * frac,
                      fill=(GOLD[0], GOLD[1], GOLD[2], 255), width=14)
            nf = SERIF_B(150); ns = str(secs); bb = d.textbbox((0, 0), ns, font=nf)
            d.text((cx - (bb[2] - bb[0]) / 2 - bb[0], cy - (bb[3] - bb[1]) / 2 - bb[1]),
                   ns, font=nf, fill=(CREAM[0], CREAM[1], CREAM[2], 255))
            tf = SANS_B(30); tip = theme["tip"]
            spaced(d, tip, tf, cx - spaced_w(d, tip, tf, 6) / 2, cy + R + 90,
                   (GOLD[0], GOLD[1], GOLD[2], 255), 6)
            # NOTE: the old "Follow for a new riddle every day" line at y=1740
            # (~91%) was removed — it fell inside the platform bottom band
            # (IG username + caption + comment bar) and was always buried. The
            # follow CTA now lives in the caption/description, not baked in.

        if t >= 17.0:
            p = smooth((t - 17.0) / 0.45)
            cardw, cardh = int(W - 200), int(560 * (0.8 + 0.2 * p)); cx0, cy0 = 100, 1010
            d.rounded_rectangle([cx0, cy0, cx0 + cardw, cy0 + cardh], radius=40,
                                fill=(248, 245, 238, int(240 * p)),
                                outline=(GOLD[0], GOLD[1], GOLD[2], int(235 * p)), width=4)
            lf = SANS_B(34); lab = "THE ANSWER"
            spaced(d, lab, lf, cx0 + cardw / 2 - spaced_w(d, lab, lf, 8) / 2, cy0 + 60,
                   (150, 102, 24, int(255 * p)), 8)
            af = SERIF_B(86); alines = wrap(d, str(answer), af, cardw - 120)
            draw_block(d, alines, af, cy0 + cardh / 2 + 30, (24, 28, 56, int(255 * p)), lh=1.2)

        # Rec 2 (seamless loop): PIL ignores per-fill alpha on this draw surface,
        # so fade-out must be done by pixel blending whole frames. In the final
        # second, cross-dissolve toward a cached copy of frame 0 (the hook frame)
        # so the last frame == the first frame. YouTube's auto-loop cut is then
        # invisible and the dissolve re-presents the hook to pull viewers back in.
        if t >= 19.0 and HOLD["f0"] is not None:
            img = Image.blend(img, HOLD["f0"], 1.0 - outro)
        return img

    HOLD["f0"] = frame(0)  # cache frame 0 (hook frame) as the loop target

    for i in range(nframes):
        frame(i).convert("RGB").save(os.path.join(framedir, f"f_{i:05d}.png"))

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-framerate", str(fps),
                    "-i", os.path.join(framedir, "f_%05d.png"),
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(fps),
                    "-movflags", "+faststart", out_path],
                   check=True, capture_output=True)
    shutil.rmtree(framedir)
    return out_path

# ---------- CLI ----------
if __name__ == "__main__":
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    if len(sys.argv) > 3:
        r, a = sys.argv[2], sys.argv[3]
    else:
        r, a = "I have keys but open no locks. I have space but no room. What am I?", "A keyboard"
    th = build_theme(seed)
    print(f"seed {seed}: palette={th['palette']['name']} bg={th['bg_style']} "
          f"accent={th['accent']} wm={th['wm_pos']} ring={th['ring']} kicker={th['kicker']!r}")
    out = render(r, a, seed, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                          "Videos", f"VARTEST_{seed}.mp4"))
    print("SAVED:", out)
