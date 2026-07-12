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
# Channel handle + one-tap subscribe link. The ?sub_confirmation=1 param makes
# YouTube pop the Subscribe dialog the moment the link is tapped (the closest
# thing to "auto-subscribe" that actually exists). Used in the description and
# the auto-pinned comment. If the handle ever changes, update it here only.
CHANNEL_URL = "https://www.youtube.com/@RiddleoClock-l7k"
SUBSCRIBE_LINK = f"{CHANNEL_URL}?sub_confirmation=1"

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
]

def _pick(lst, seed, salt):
    i = int(hashlib.sha256(f"{seed}:{salt}".encode()).hexdigest(), 16) % len(lst)
    return lst[i]

def generate(riddle, answer, seed, category=None, video_url=None):
    title_core = _pick(TITLE_PATTERNS, seed, "title")   # the distinctive hook

    # Title A/B test (deterministic by seed, ~50/50, fully reversible):
    #   arm "keyword" = legacy front-loaded search stack (the old fixed title)
    #   arm "hook"    = distinctive hook LEADS, with one rotating search phrase
    #                   appended so we don't sacrifice discoverability.
    # Hypothesis (from this channel's own data, small-n / directional): hook-led
    # titles earn more views/day than the keyword stack. Both arms run in the
    # SAME time window, which removes the video-age / algorithm-drift confound a
    # full flip would have introduced. Search indexing is preserved in BOTH arms
    # via the `tags` field below, so the hook arm doesn't lose SEO.
    # HOW TO READ IT: judge at a fixed 48h-views snapshot, NOT raw counts, once
    # each arm has ~10 videos (~3 weeks at 1/day). Keep the winner; if the gap
    # is inside noise, default back to "keyword" (better long-tail search).
    arm = "hook" if _pick([0, 1], seed, "abtest") else "keyword"
    kw = _pick(SEARCH_KEYWORDS, seed, "titlekw")        # one rotating phrase
    if arm == "hook":
        title = f"{title_core} | {kw}"
    else:
        title = f"{' | '.join(SEARCH_KEYWORDS[:3])} | {CHANNEL}"
    # Every title ends with the #shorts tag. Trim the CORE (never the tag) so we
    # stay within YouTube's 100-char limit and #shorts is never lost to truncation.
    TAG = " #shorts"
    if len(title) + len(TAG) > 100:
        title = title[:100 - len(TAG) - 3].rstrip() + "..."
    title += TAG

    opener = _pick(OPENERS, seed, "open")
    cat_tag = (category or "").strip().lower()
    hashtags = BASE_HASHTAGS + ([f"#{cat_tag.replace(' ', '')}"] if cat_tag else []) + ["#riddleoclock"]
    hashtags = list(dict.fromkeys(hashtags))  # dedupe, keep order

    description = (
        f"{opener}\n\n"
        f"\u2753 {riddle.strip()}\n\n"
        f"Comment your answer before the timer runs out \u2014 then watch again to reveal it.\n\n"
        f"\u23f0 {CHANNEL}: a new riddle every single day.\n"
        f"\U0001f514 Subscribe (one tap): {SUBSCRIBE_LINK}\n\n"
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
            "hashtags": hashtags, "category_id": "24",  # 24 = Entertainment
            "ab_arm": arm}  # which title arm this video used (for measurement)


def pinned_comment(seed=0):
    """Engagement seed + one-tap subscribe, to post (and pin) after upload."""
    prompts = [
        "Did you crack it before the timer? Drop your guess below \U0001f447",
        "Got it in time? Comment your answer \u2014 no scrolling ahead!",
        "Think you nailed it? Prove it in the comments \U0001f447",
        "How many can you solve in a row? Comment your streak!",
    ]
    seed_i = int(hashlib.sha256(f"{seed}pin".encode()).hexdigest(), 16) % len(prompts)
    return (f"{prompts[seed_i]}\n\n"
            f"\U0001f514 New riddle every day \u2014 subscribe in one tap: {SUBSCRIBE_LINK}")


if __name__ == "__main__":
    import json
    m = generate("You cannot see me, hold me, or hear me, yet the whole house "
                 "panics the second I vanish. What am I?", "Wi-Fi", 0, "Modern")
    print(json.dumps(m, indent=2, ensure_ascii=False))
