# CrackIt_Adults — daily riddle Shorts automation

Automated pipeline for the adult riddle channel: picks the next unposted riddle
from `Riddle_Content_Bank.xlsx`, renders an 18s vertical Short (with a variation
engine + cinematic countdown audio), uploads it to YouTube as **Private**, and
pings you on Telegram with a one-tap link to publish.

**Start here:** read `IMPLEMENTATION_PLAN.md` for the full one-time setup.

Daily run is driven by `.github/workflows/daily.yml` (schedule + manual trigger).
