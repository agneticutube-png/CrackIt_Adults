# Riddle o'Clock — Automation Implementation Plan (Adult channel)

This is the concrete, step-by-step path from "channel created" to "a riddle goes
up every day and I just tap Publish." It reflects the real constraints of the
YouTube API in 2026, not the ideal-world version.

---

## What's already built (in this folder)

| File | Job |
|------|-----|
| `render_video.py` | Renders the 18s vertical Short. **Variation engine**: palette rotates weekly, layout (background, accent, watermark, ring, kicker, hook) varies per video so no two look stamped. |
| `add_audio.py` | Adds the cinematic Interstellar-style countdown audio (silent until the question, ticking through the 10s countdown, resolve at the answer). |
| `metadata.py` | Generates a varied title, description, tags and hashtags per video. Answer is never spoiled in the title. |
| `pipeline.py` | Picks the **next unposted** riddle (Originals first, then the main bank), renders + adds audio, writes `next_video.json`. |
| `upload_youtube.py` | Uploads that video as **Private**, marks the row posted, sends the Telegram ping. |
| `authorize.py` | One-time local Google login → `token.json`. |
| `verify_setup.py` | Pre-flight check: confirms ffmpeg/fonts, workbook, YouTube auth, and Telegram all work before your first real run. |
| `notify.py` | Telegram "ready to publish" notification. |
| `.github/workflows/daily.yml` | Runs the whole thing daily on GitHub Actions. |
| `requirements.txt` | Python dependencies. |

---

## The one hard constraint you must design around

A brand-new YouTube API project is **unaudited**. YouTube **force-locks every
API upload to Private**, and the scheduled auto-publish (`publishAt`) is also
blocked until the project passes a compliance audit (typically weeks). There is
no way around this — it is not a settings toggle.

**So the launch flow is deliberately semi-manual:**

```
GitHub Actions (daily)
  → pipeline.py        : pick next riddle, render + audio
  → upload_youtube.py  : upload as PRIVATE, mark posted, ping you
  → Telegram ping      : "New riddle uploaded" + one-tap Studio link
  → YOU                : tap link, set Public, Publish  (~10 seconds/day)
```

Once the audit clears, you flip a single switch (`YT_PRIVACY: public` in the
workflow, or wire `publishAt`) and it becomes fully hands-off. **Do not apply
for the audit until you have ~15–30 real public videos and a finished channel** —
auditors reject empty/incomplete channels.

---

## Step-by-step setup (do once)

### 1. Make the GitHub repo
Create a **private** repo. Put all the files from this `automation/` folder at
the repo root, plus:
- `render_video.py`, `add_audio.py`, `metadata.py`, `pipeline.py`,
  `upload_youtube.py`, `notify.py`, `authorize.py`
- `Riddle_Content_Bank.xlsx` (the workbook — it's the source of truth)

> The workbook lives in the repo so Actions can read it and commit the updated
> "Posted?" column back each day. Edit riddles locally and `git push`.

### 2. Google Cloud / YouTube API
1. console.cloud.google.com → new project.
2. Enable **YouTube Data API v3**.
3. OAuth consent screen → External → add yourself as a Test user.
4. Credentials → Create OAuth client → **Desktop app** → download
   `client_secret.json`.

### 3. Authorize once (on your computer)
```bash
pip install -r requirements.txt
python3 authorize.py        # opens browser; log in with the channel's Google account
```
This writes `token.json`. **Keep `client_secret.json` and `token.json` private —
never commit them.** (Add both to `.gitignore`.)

### 4. Telegram notifications
1. In Telegram, message **@BotFather** → `/newbot` → copy the **bot token**.
2. Message **@userinfobot** → copy your numeric **chat id**.
3. Send your new bot any message once (so it's allowed to message you).

### 5. GitHub repo secrets
Repo → Settings → Secrets and variables → Actions → New repository secret:

| Secret | Value |
|--------|-------|
| `YT_CLIENT_SECRET_JSON` | full contents of `client_secret.json` |
| `YT_TOKEN_JSON` | full contents of `token.json` |
| `TELEGRAM_BOT_TOKEN` | the BotFather token |
| `TELEGRAM_CHAT_ID` | your chat id |

### 6. Set the posting time
Edit the `cron` line in `.github/workflows/daily.yml` (it's in **UTC**). Pick a
slot that lands in your audience's evening. GitHub may delay scheduled runs by a
few minutes — fine for daily content.

### 7. Pre-flight check (recommended)
Locally, with your env vars set:
```bash
python3 verify_setup.py
```
It confirms ffmpeg/fonts, the workbook, your YouTube auth (prints the channel it
will post to), and sends a real Telegram test message. Fix any `FAIL` before going live.

### 8. Test it
- Actions tab → **Daily Riddle Short** → **Run workflow** (manual trigger).
- You should get a Telegram ping with a Studio link. Open it, confirm the video
  looks right, set Public, Publish.
- Check the workbook commit marked that riddle `Posted? = Yes`.

---

## How the daily run picks content
- Order: all **Adult – Original** riddles first (your owned IP, lowest policy
  exposure — lead with these), then the main **Adult Riddles** bank.
- `seed` = number already posted → drives the **weekly palette rotation**
  (7 videos per palette, then it shifts to the next jewel tone).
- A riddle is only marked posted **after** a successful upload, so a failed run
  never wastes one.

---

## Channel settings that are not optional
- **Audience: "No, it's not made for kids."** The uploader already sets
  `selfDeclaredMadeForKids = false`. Also set it once at the **channel** level in
  Studio → Settings → Channel → Advanced. Getting this wrong on an adult channel
  caps your RPM and disables key features.
- Upload a finished **icon** (the clock + "?" you approved) and **banner** before
  applying for the audit or monetization.

---

## Honest risks & tradeoffs (read this)
1. **Identical-looking output is the #1 termination risk.** The variation engine
   addresses the *visual* side. The *content* side matters too: the riddles
   themselves are your real moat. Keep writing originals — a 120-riddle bank is
   ~4 months; plan to replenish before it runs dry, and rotate phrasing.
2. **Semi-manual by necessity.** Until the audit clears you tap Publish daily.
   That's ~10 seconds, and it's actually a feature early on: it's a human
   checkpoint that keeps you compliant while the channel is most fragile.
3. **Quota:** an upload costs 1600 of 10,000 daily units → ~6 uploads/day max.
   Daily posting is comfortably within budget.
4. **GitHub Actions is free but not SLA'd.** Scheduled runs can be delayed or
   (rarely) skipped. For daily content that's acceptable; if a day is missed the
   next run just picks up the next riddle.
5. **Monetization is never permanently "safe."** It's continuously conditional.
   Don't build the business model on assuming the channel can't be demonetized.

---

## After the audit passes (full automation)
- Set `YT_PRIVACY: public` in the workflow → uploads go straight live, no tap.
- Or keep it private + set `publishAt` for true scheduled drops.
- Consider adding the long-form weekly compilation funnel (the monetization
  lever) and only then the Kids channel (which needs its own COPPA-aware setup).
