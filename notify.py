#!/usr/bin/env python3
"""
Notification layer. Default channel = Telegram (free, instant mobile push,
clean clickable links, trivial to run inside GitHub Actions).

To swap to WhatsApp later: implement send_whatsapp() (e.g. CallMeBot) and point
notify() at it. The rest of the pipeline is unaffected.

Env vars required for Telegram:
    TELEGRAM_BOT_TOKEN   (from @BotFather)
    TELEGRAM_CHAT_ID     (your numeric chat id; get it from @userinfobot)
"""
import os, json, urllib.request, urllib.parse

def send_telegram(text):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        raise RuntimeError("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": chat, "text": text,
        "parse_mode": "HTML", "disable_web_page_preview": "false",
    }).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=30) as r:
        return json.load(r)

def notify_ready(video_id, title, riddle):
    """Send the 'ready to publish' ping with a one-tap Studio link."""
    studio = f"https://studio.youtube.com/video/{video_id}/edit"
    watch  = f"https://youtu.be/{video_id}"
    text = (
        "\u2705 <b>New riddle uploaded (Private)</b>\n\n"
        f"<b>{title}</b>\n"
        f"\u2753 {riddle}\n\n"
        f"\u25b6\ufe0f <a href=\"{studio}\">Open in Studio to publish</a>\n"
        f"\U0001f517 {watch}\n\n"
        "Tap the Studio link, set visibility to <b>Public</b>, and publish."
    )
    return send_telegram(text)

if __name__ == "__main__":
    # smoke test: requires env vars set
    print(notify_ready("TEST12345", "Sample title | Riddle o'Clock", "A test riddle?"))
