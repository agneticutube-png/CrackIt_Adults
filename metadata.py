#!/usr/bin/env python3
"""
Metadata generator for each riddle Short.

Produces a varied (non-templated) title, description, tag list and hashtags.
Variation matters here too: identical titles/descriptions across uploads are a
signal of mass-produced content. Patterns rotate deterministically by seed so
the series feels authored, and titles never make false/fraudulent claims.

API:
    generate(riddle, answer, seed, category=None, video_url=None) -> dict
"""
import hashlib

CHANNEL = "Riddle o'Clock"

# Title patterns. {a}=answer is intentionally NEVER in the title (no spoiler).
TITLE_PATTERNS = [
    "Can You Solve This in 10 Seconds?",
    "Beat the Clock: 10-Second Riddle",
    "Most People Get This Wrong \u23f3",
    "This Riddle Has a Hidden Twist",
    "How Fast Can You Crack It?",
    "A Riddle Worth 10 Seconds of Your Day",
    "Think You're Sharp Enough?",
    "Quick \u2014 The Clock Is Ticking \u23f1\ufe0f",
]

OPENERS = [
    "Here's today's riddle. You've got 10 seconds.",
    "Can you beat the clock on this one?",
    "Most people miss this. Can you get it?",
    "A quick brain teaser for your day.",
    "Read carefully \u2014 the answer hides in plain sight.",
]

BASE_TAGS = [
    "riddles", "riddle", "brain teaser", "riddle of the day", "riddles with answers",
    "quiz", "puzzle", "shorts", "riddle shorts", "logic puzzle", "think fast",
    "can you solve this", "daily riddle", "riddle o'clock",
]

BASE_HASHTAGS = ["#shorts", "#riddle", "#brainteaser", "#puzzle", "#quiz"]

# Vetted, on-niche search phrases (ranked by real vidiq search volume, India + global).
# Rotated into the title to lift search indexing. Refresh ~quarterly in Cowork via
# vidiq_keyword_research — keep ONLY high/medium-volume phrases that literally describe
# this channel's content. No brand names, no "for kids", no false claims.
SEARCH_KEYWORDS = [
    "Riddles with Answers",              # ~18.9k/mo
    "Tricky Riddles",                    # ~15.3k/mo
    "Brain Teasers with Answers",        # ~12.2k/mo
    "Riddles in English with Answers",   # ~4.9k/mo (your manual pick)
    "Mystery Riddles",                   # ~4.1k/mo (India)
    "Riddles That Will Blow Your Mind",  # ~4.2k/mo
]

def _pick(lst, seed, salt):
    i = int(hashlib.sha256(f"{seed}:{salt}".encode()).hexdigest(), 16) % len(lst)
    return lst[i]

def generate(riddle, answer, seed, category=None, video_url=None):
    title_core = _pick(TITLE_PATTERNS, seed, "title")
    kw = _pick(SEARCH_KEYWORDS, seed, "kw")
    full = f"{title_core} | {kw} | {CHANNEL} #shorts"
    base = f"{title_core} | {CHANNEL} #shorts"
    title = full if len(full) <= 100 else base
    if len(title) > 100:
        title = title[:97].rstrip() + "..."

    opener = _pick(OPENERS, seed, "open")
    cat_tag = (category or "").strip().lower()
    hashtags = BASE_HASHTAGS + ([f"#{cat_tag.replace(' ', '')}"] if cat_tag else []) + ["#riddleoclock"]
    hashtags = list(dict.fromkeys(hashtags))  # dedupe, keep order

    description = (
        f"{opener}\n\n"
        f"\u2753 {riddle.strip()}\n\n"
        f"Comment your answer before the timer runs out \u2014 then watch again to reveal it.\n\n"
        f"\u23f0 {CHANNEL}: a new riddle every single day. Follow so you never miss one.\n\n"
        f"{' '.join(hashtags)}"
    )
    if video_url:
        description += f"\n\nWatch: {video_url}"

    tags = list(dict.fromkeys(BASE_TAGS + ([cat_tag] if cat_tag else [])))
    # YouTube tag field cap is 500 chars total; trim defensively
    out, total = [], 0
    for t in tags:
        if total + len(t) + 1 > 480:
            break
        out.append(t); total += len(t) + 1

    return {"title": title, "description": description, "tags": out,
            "hashtags": hashtags, "category_id": "24"}  # 24 = Entertainment

if __name__ == "__main__":
    import json
    m = generate("You cannot see me, hold me, or hear me, yet the whole house "
                 "panics the second I vanish. What am I?", "Wi-Fi", 0, "Modern")
    print(json.dumps(m, indent=2, ensure_ascii=False))
