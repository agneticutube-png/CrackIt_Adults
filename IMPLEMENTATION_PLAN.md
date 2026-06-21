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
| `upload_youtube.py` | Uploads that video as **Private**, marks the row posted, and prints the Studio link to the run log. |
| `authorize.py` | One-time local Google login → `token.json`. |
| `verify_setup.py` | Pre-flight check: confirms ffmpeg/fonts, workbook, and YouTube auth all work before your first real run. |
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
  → upload_youtube.py  : upload as PRIVATE, mark posted, print Studio link to log
  → YOU                : open YouTube Studio, set the new private Short to Public,
                         Publish  (~30 seconds/day)
```

Once the audit clears, you flip a single switch (`YT_PRIVACY: public` in the
workflow, or wire `publishAt`) and it becomes fully hands-off. **Do not apply
for the audit until you have ~15–30 real public videos and a finished channel** —
auditors reject empty/incomplete channels.

---

## Do these in exactly this order

Each gate confirms the previous one worked, so don't skip ahead:

1. Push the repo to GitHub.
2. Google Cloud: project → enable API → consent screen (add yourself as test user) → Desktop OAuth client → download `client_secret.json`.
3. Run `authorize.py` locally → produces `token.json`.
4. Add the two GitHub secrets.
5. Set the posting time (cron).
6. Run `verify_setup.py` locally — all green.
7. Trigger one manual workflow run; confirm the private upload.

---

## Step-by-step setup (do once)

### 1. Push the repo to GitHub
All files already exist in this `CrackIt_Adults` folder. The local `.git` was
created in a sandboxed environment and may carry stale lock files, so the most
reliable path is to re-initialize fresh on your own machine. Open Terminal:

```bash
cd "/path/to/CrackIt_Adults"        # drag the folder into Terminal to autofill the path
rm -rf .git                          # discard the sandbox git metadata
git init -b main
git add -A
git commit -m "Initial commit: riddle Shorts automation pipeline"
git remote add origin https://github.com/agneticutube-png/CrackIt_Adults.git
git push -u origin main
```

When it prompts for a password on push, use a **GitHub Personal Access Token**
(Settings → Developer settings → Fine-grained tokens → repo-scoped), not your
account password — GitHub blocks passwords for git over HTTPS.

> The workbook `Riddle_Content_Bank.xlsx` lives in the repo so Actions can read
> it and commit the updated "Posted?" column back each day. Secrets
> (`client_secret.json`, `token.json`) are gitignored and must NEVER be committed
> — they go in as GitHub *secrets* in step 5.

### 2. Google Cloud / YouTube API
Logged in as the Google account that owns the channel, at console.cloud.google.com:
1. **New project** (top bar → project dropdown → New Project). Make sure it's the
   selected project before continuing.
2. APIs & Services → Library → **YouTube Data API v3** → **Enable**.
3. APIs & Services → **OAuth consent screen** → User type **External**. Fill app
   name + your email for support/developer contact. You can skip the scopes page.
   On **Test users**, add `agneticutube@gmail.com`. Leave status as **Testing** —
   do NOT click "Publish app."
4. Credentials → Create Credentials → OAuth client ID → application type
   **Desktop app** → Create → **Download JSON**.
5. Rename the file to exactly `client_secret.json` and put it in your
   `CrackIt_Adults` folder, next to `authorize.py`.

> The UI was rebranded "Google Auth Platform" in 2025; labels may differ slightly
> but the four objects (project, enabled API, consent screen + test user, Desktop
> OAuth client) are unchanged.

### 3. Authorize once (on your computer)
In Terminal, inside the `CrackIt_Adults` folder:
```bash
python3 -m venv .venv             # isolated environment (already gitignored)
source .venv/bin/activate          # prompt now shows (.venv)
pip install -r requirements.txt
python3 authorize.py               # opens your browser
```
Log in with the Google account that owns the channel. You'll see **"Google hasn't
verified this app"** — this is expected in Testing mode. Click **Advanced → Go to
[app] (unsafe)**, then allow the two YouTube permissions. The browser shows
"authentication flow has completed" and `authorize.py` writes `token.json`.

**Common failures:**
- *Error 403: access_denied* → you didn't add yourself as a Test user (step 2.3). Fix and re-run.
- *redirect_uri_mismatch* → your OAuth client isn't **Desktop app** type. Recreate it as Desktop.
- *Wrong channel* → if your channel is a Brand Account, make sure the token ties to it. `verify_setup.py` (step 7) prints the channel name it authenticated as — confirm it says the right channel; if not, re-run `authorize.py` and pick the brand account.

**Keep `client_secret.json` and `token.json` private — never commit them**
(both are already in `.gitignore`). When done, run `deactivate`.

### 4. GitHub repo secrets
Repo → Settings → Secrets and variables → Actions → New repository secret:

| Secret | Value |
|--------|-------|
| `YT_CLIENT_SECRET_JSON` | full contents of `client_secret.json` |
| `YT_TOKEN_JSON` | full contents of `token.json` |

### 5. Set the posting time
Edit the `cron` line in `.github/workflows/daily.yml` (it's in **UTC**). Pick a
slot that lands in your audience's evening. GitHub may delay scheduled runs by a
few minutes — fine for daily content.

### 6. Pre-flight check (recommended)
Locally, with your env vars set:
```bash
python3 verify_setup.py
```
It confirms ffmpeg/fonts, the workbook, and your YouTube auth (prints the channel
it will post to). Fix any `FAIL` before going live.

### 7. Test it
- Actions tab → **Daily Riddle Short** → **Run workflow** (manual trigger).
- Open the run log → the upload step prints the **Studio link** for the new
  private Short. Open it, confirm the video looks right, set Public, Publish.
- Check the workbook commit marked that riddle `Posted? = Yes`.

> **No notifications by design.** You publish manually, so the daily flow is:
> the workflow uploads privately, then you open YouTube Studio (Content → filter
> by *Private*) and publish the new Short. The Studio link is also printed in the
> Actions run log if you'd rather grab it there.

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
