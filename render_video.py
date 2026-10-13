#!/usr/bin/env python3
"""
Production riddle-Short renderer with a VARIATION ENGINE.

Why this exists: posting visually-identical videos daily is exactly the
"mass-produced / templated" pattern YouTube's inauthentic-content policy
hard-enforces against. This module deterministically varies palette (weekly)
and layout (per-video) so the channel reads as a crafted series, not a stamp.

FORMAT (riddle-only, comment-driven): the riddle + "What am I?" on screen with
one of 20 rotating comment prompts. NO countdown, NO answer reveal, NO music.
DEFAULT = STILL: a single image (.png/.jpg out_path) or, for YouTube (Shorts
need a video file), that image as a silent 7s still video. Set
RIDDLE_ANIMATED=1 for the old animated fade-in version.
The answer is NOT shown in the video, title or description; it is posted as a
pinned comment after publishing.

Public API:
    render(riddle, answer, seed, out_path, kind="adult", fps=30) -> out_path
    build_theme(seed, kind="adult") -> dict   (inspect a variant without rendering)

CLI (for local testing):
    python3 render_video.py <seed> ["riddle text" "answer"]
"""
import os, sys, math, subprocess, shutil, re, hashlib, tempfile
from PIL import Image, ImageDraw, ImageFont

# ---------- locked config ----------
W, H = 1080, 1920
DUR = 12.0   # default; render() sets a per-riddle duration (see _duration)

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
# Rotating CATEGORY chip in the badge (variety / anti-templating). The brand
# name itself is NOT here — it's a fixed handle drawn under the badge every frame
# (see BRAND), so the badge stays a category and never duplicates the brand line.
KICKERS     = ["DAILY RIDDLE", "BRAIN TEASER", "CAN YOU SOLVE IT?"]
BRAND       = "RIDDLE O'CLOCK"   # persistent on-screen brand handle (every frame)
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

# Rotating COMMENT PROMPTS (riddle-only format). Each is (headline, subline).
# Rules: honest (no fake stats like "99% fail"), low-stakes, one clear action,
# readable for an older audience. Picked deterministically per video by seed.
# NOTE "RIGHT ANSWERS GET A HEART" is a promise: heart correct guesses in Studio.
PROMPTS = [
    ("ONE WORD. GO.",              "Type your answer before you scroll"),
    ("DON'T SCROLL YET",           "Drop your guess first"),
    ("FIRST GUESS = FINAL ANSWER", "Comment it. No take-backs."),
    ("NO PEEKING AT THE COMMENTS", "Guess first, then check"),
    ("WRONG ANSWERS ONLY",         "Make us laugh in the comments"),
    ("TAG SOMEONE WHO'D GET THIS", "...or someone who never would"),
    ("RIGHT ANSWERS GET A \u2665", "Lock in your guess below"),
    ("EASY OR IMPOSSIBLE?",        "Guess it, then rate it"),
    ("GOT IT? PROVE IT.",          "Answer in the comments"),
    ("GUESS IN 3 WORDS OR LESS",   "Short answers only"),
    ("TOO EASY?",                  "Then answer it below"),
    ("YOUR FINAL ANSWER IS...?",   "Lock it in below"),
    ("STUMPED? SAY SO.",           "Or show off your answer"),
    ("BE THE FIRST TO CRACK IT",   "Comment your guess now"),
    ("WHAT WAS YOUR FIRST THOUGHT?", "Type it before you change your mind"),
    ("CHALLENGE A FRIEND",         "Send this to someone smart"),
    ("GUESS NOW, CHECK LATER",     "Answer's in the pinned comment"),
    ("NAILED IT OR NO IDEA?",      "Tell us below"),
    ("ONE CHANCE. ONE GUESS.",     "Make it count"),
    ("THINK YOU'VE GOT IT?",       "Drop it before anyone else"),
]

def draw_prompt(d, prompt, y, gold, cream, alpha=255):
    """Two-line comment prompt centred at x. Headline in gold, subline in cream."""
    head, sub = prompt
    MAXW = W - 2 * 100                       # stay clear of the frame/border
    hs = 44
    while hs > 30 and spaced_w(d, head, SANS_B(hs), 5) > MAXW:
        hs -= 2                              # auto-shrink long headlines
    hf = SANS_B(hs); sf = SANS(34)
    spaced(d, head, hf, W / 2 - spaced_w(d, head, hf, 5) / 2, y,
           (gold[0], gold[1], gold[2], alpha), 5)
    sw = d.textlength(sub, font=sf)
    d.text((W / 2 - sw / 2, y + 70), sub, font=sf,
           fill=(cream[0], cream[1], cream[2], int(alpha * 0.85)))

def _h(seed, salt):
    return int(hashlib.sha256(f"{seed}:{salt}".encode()).hexdigest(), 16)

def _duration(riddle):
    """Riddle-only format: just long enough to read, plus a beat to think.
    ~0.35s per word + 5s, clamped to 10-16s."""
    words = len(str(riddle).split())
    return float(max(10, min(16, round(5 + 0.35 * words))))

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
        "prompt":   PROMPTS[_h(seed, "pr") % len(PROMPTS)],
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
def render(riddle, answer, seed, out_path, kind="adult", fps=30, still_secs=None):
    theme = build_theme(seed, kind); pal = theme["palette"]
    TOP, BOT, GOLD = pal["top"], pal["bot"], pal["accent"]
    CREAM, DIM = pal["cream"], pal["dim"]
    riddle_txt = re.sub(r'\s*what am i\s*\??\s*$', '', str(riddle), flags=re.I).strip()
    DURV = _duration(riddle_txt)
    nframes = int(fps * DURV)
    OUT0 = DURV - 1.0   # seamless-loop fade starts 1s before the end

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
        outro = 1.0 - smooth((t - OUT0) / 1.0) if t >= OUT0 else 1.0
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
        # Persistent BRAND handle just under the badge — drawn on EVERY frame
        # (incl. frame 0 / the poster and the answer-reveal frame) so the brand
        # travels with screenshots and re-uploads. Sits in the safe top zone,
        # clear of the platform top-nav and bottom caption/action bands. Small,
        # gold, letter-spaced; the badge above stays the rotating category chip.
        bf = SANS_B(30)
        spaced(d, BRAND, bf, (W - spaced_w(d, BRAND, bf, 8)) / 2, 356,
               (GOLD[0], GOLD[1], GOLD[2], 255), 8)

        # Riddle-only format: no countdown, no answer, no music. One quiet prompt
        # inviting a guess, fading in after a beat so the riddle leads.
        if t >= 2.0:
            ta = int(255 * smooth((t - 2.0) / 0.6))
            draw_prompt(d, theme["prompt"], 1200, GOLD, CREAM, ta)

        # Rec 2 (seamless loop): PIL ignores per-fill alpha on this draw surface,
        # so fade-out must be done by pixel blending whole frames. In the final
        # second, cross-dissolve toward a cached copy of frame 0 (the hook frame)
        # so the last frame == the first frame. YouTube's auto-loop cut is then
        # invisible and the dissolve re-presents the hook to pull viewers back in.
        if t >= OUT0 and HOLD["f0"] is not None:
            img = Image.blend(img, HOLD["f0"], 1.0 - outro)
        return img

    # STILL MODE (default): one finished frame (riddle + prompt fully shown).
    #  - out_path ending .png/.jpg -> save the image only.
    #  - otherwise -> wrap that image in a short SILENT still video, because
    #    YouTube Shorts only accept video files (an image can't be a Short).
    #    Length: still_secs, or env RIDDLE_STILL_SECS, default 7s.
    if os.environ.get("RIDDLE_ANIMATED") != "1":
        poster = frame(int(fps * 3.0)).convert("RGB")
        shutil.rmtree(framedir, ignore_errors=True)
        d = os.path.dirname(out_path)
        if d: os.makedirs(d, exist_ok=True)
        if out_path.lower().endswith((".png", ".jpg", ".jpeg")):
            poster.save(out_path); return out_path
        secs = float(still_secs or os.environ.get("RIDDLE_STILL_SECS", 7))
        png = os.path.splitext(out_path)[0] + "_poster.png"
        poster.save(png)
        subprocess.run(["ffmpeg", "-y", "-loop", "1", "-framerate", str(fps), "-i", png,
                        "-t", f"{secs}", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        "-r", str(fps), "-movflags", "+faststart", out_path],
                       check=True, capture_output=True)
        return out_path

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
          f"accent={th['accent']} wm={th['wm_pos']} ring={th['ring']} kicker={th['kicker']!r} "
          f"dur={_duration(r)}s prompt={th['prompt'][0]!r}")
    out = render(r, a, seed, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                          "Videos", f"VARTEST_{seed}.mp4"))
    print("SAVED:", out)
