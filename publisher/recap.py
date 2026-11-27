"""Weekly recap on the Telegram channel: one post linking every post of the week, Sunday evening."""
import html
import json
import os
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from . import config
from .platforms.telegram import CHANNEL_URL

HEADER = "📌 Riepilogo della settimana"
STATE = os.path.join(os.path.dirname(config.WORK_DIR), "recap_last_week.txt")
MONTHS = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"]
KIND = {"video": "📹 Video", "photo": "🖼 Foto", "document": "📎 File", "poll": "📊 Sondaggio", "voice": "🎙 Audio"}


def _channel() -> str:
    return config.TELEGRAM_CHANNEL.lstrip("@")


def _page(before: int | None) -> str:
    # Bots cannot read a channel's history; the public web preview of the channel can.
    url = f"https://t.me/s/{_channel()}" + (f"?before={before}" if before else "")
    return requests.get(url, timeout=60, headers={"User-Agent": "Mozilla/5.0"}).text


def _title(text: str, kind: str) -> str:
    line = next((l.strip() for l in text.splitlines() if l.strip()), "") or KIND.get(kind, "Post")
    return line if len(line) <= 70 else line[:70].rsplit(" ", 1)[0] + "…"


def posts_since(start: datetime) -> list[tuple[int, datetime, str]]:
    out, before = {}, None
    while True:
        page = _page(before)
        blocks = re.split(r'(?=<div class="tgme_widget_message_wrap)', page)[1:]
        ids = []
        for b in blocks:
            pid, when = re.search(rf'data-post="{_channel()}/(\d+)"', b), re.search(r'<time datetime="([^"]+)"', b)
            if not (pid and when):
                continue
            ids.append(int(pid.group(1)))
            at = datetime.fromisoformat(when.group(1))
            body = re.search(r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', b, re.S)
            text = html.unescape(re.sub(r"<[^>]+>", "", re.sub(r"<br\s*/?>", "\n", body.group(1)))) if body else ""
            kind = next((k for k in KIND if f"tgme_widget_message_{k}" in b), "")
            if at >= start and (text.strip() or kind) and not text.startswith(HEADER):
                out[int(pid.group(1))] = (at, _title(text, kind))
        times = [datetime.fromisoformat(t) for t in re.findall(r'<time datetime="([^"]+)"', page)]
        if not ids or min(ids) <= 1 or not times or min(times) < start:
            break
        before = min(ids)
    return [(pid, at, title) for pid, (at, title) in sorted(out.items())]


def _range(start: datetime, end: datetime) -> str:
    if start.month == end.month:
        return f"{start.day}–{end.day} {MONTHS[end.month - 1]}"
    return f"{start.day} {MONTHS[start.month - 1]} – {end.day} {MONTHS[end.month - 1]}"


def message(posts: list[tuple[int, datetime, str]], start: datetime, end: datetime) -> str:
    lines = [f"<b>{HEADER}</b> ({_range(start, end)})", "", "Te li sei persi? Ecco tutti i post di questa settimana:", ""]
    lines += [f'• <a href="https://t.me/{_channel()}/{pid}">{html.escape(title)}</a>' for pid, _, title in posts]
    return "\n".join(lines)


def maybe_post(now: datetime | None = None) -> str:
    """Sunday from 19:00 (Italian time), once a week; returns the post link or ''."""
    if not (config.BOT_TOKEN and config.TELEGRAM_CHANNEL):
        return ""
    tz = ZoneInfo(config.TIMEZONE)
    now = now or datetime.now(tz)
    week = now.strftime("%G-W%V")
    if now.weekday() != 6 or now.hour < 19 or (os.path.exists(STATE) and open(STATE).read().strip() == week):
        return ""
    start = (now - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
    posts = posts_since(start)
    with open(STATE, "w") as f:
        f.write(week)
    if not posts:
        return ""
    r = requests.post(f"{config.API_BASE_URL}/bot{config.BOT_TOKEN}/sendMessage", timeout=60, data={
        "chat_id": config.TELEGRAM_CHANNEL, "text": message(posts, start, now), "parse_mode": "HTML",
        "link_preview_options": json.dumps({"is_disabled": True}),
        "reply_markup": json.dumps({"inline_keyboard": [[{"text": "📲 Seguimi sul canale", "url": CHANNEL_URL}]]}),
    })
    body = r.json()
    if not body.get("ok"):
        raise RuntimeError(f"riepilogo settimanale: {body.get('description') or r.text[:300]}")
    return f"https://t.me/{_channel()}/{body['result']['message_id']}"
