import html
import json
import re

import requests

from .. import config
from ..media import Video

CAPTION_MAX = 1024
CHANNEL_URL = "https://t.me/AlanBimbatiBlog"
YOUTUBE_LINK = re.compile(r"https://(?:youtu\.be/|(?:www\.)?youtube\.com/(?:watch\?v=|shorts/))[\w-]+")


def available() -> bool:
    return bool(config.BOT_TOKEN and config.TELEGRAM_CHANNEL)


def _credits(lines: list[str]) -> str:
    # CC licences need attribution even in a channel post; public domain does not, and the YouTube block is too long.
    photos, music = [], ""
    for line in lines:
        m = re.match(r"-\s*(.+?)\s+–\s+(.+?)\s+–\s+(.+)$", line.strip())
        if m and not re.search(r"public domain|pubblico dominio|cc0", m.group(3), re.I):
            author = re.sub(r" \(.*\)$", "", m.group(2))
            if f"{author} ({m.group(3)})" not in photos:
                photos.append(f"{author} ({m.group(3)})")
        elif line.lower().startswith("musica:"):
            music = "🎵 Musica: " + line.split(":", 1)[1].strip()
    return "\n".join(x for x in (music, "📷 Foto (Wikimedia Commons): " + ", ".join(photos) if photos else "") if x)


def caption(title: str, description: str) -> tuple[str, str]:
    """The Shorts text reshaped for the channel, plus the credits on their own when they push it past Telegram's limit."""
    lines = description.splitlines()
    intro = []
    for line in lines:
        if line.startswith(("🔗", "Fonti", "Crediti")):
            break
        intro.append(line)
    credits = lines[lines.index("Crediti") + 1:] if "Crediti" in lines else []
    tags = " ".join(t for t in (lines[-1].split() if lines and lines[-1].startswith("#") else []) if t.lower() != "#shorts")
    title = re.sub(r"\s*#shorts\b", "", title, flags=re.I).strip()
    head = [f"<b>{html.escape(title)}</b>", html.escape("\n".join(intro).strip())]
    cred = _credits(credits)
    cred = f"<i>{html.escape(cred)}</i>" if cred else ""
    text = "\n\n".join(p for p in head + [cred, tags] if p)
    if len(text) <= CAPTION_MAX:
        return text, ""
    return "\n\n".join(p for p in head + [tags] if p)[:CAPTION_MAX], cred[:4000]


_LABELLED = re.compile(r"^([^\w\n]*)([^\n:<>]*\w[^\n:<>]*?):\s*(https?://[^\s<]+)[ \t]*$", re.M)
_BARE = re.compile(r"(?<![\"'>=])(https?://[^\s<]+)")


def _label(url: str) -> str:
    if YOUTUBE_LINK.match(url):
        return "Guarda su YouTube"
    host = re.sub(r"^https?://(www\.)?", "", url).split("/")[0]
    return host


def linkify(text: str) -> str:
    """Never a raw URL in a channel post: «Label: URL» becomes a linked label, any other URL a linked site name."""
    text = _LABELLED.sub(lambda m: f'{m.group(1)}<a href="{m.group(3)}">{m.group(2).strip()}</a>', text)
    return _BARE.sub(lambda m: f'<a href="{m.group(1)}">{_label(m.group(1))}</a>', text)


def with_youtube(text: str, youtube_url: str) -> tuple[str, str]:
    """The caption with the YouTube link in it, and the link the button opens (the long video when the text names it)."""
    found = YOUTUBE_LINK.search(text)
    if found:
        return text, found.group(0)
    if not youtube_url:
        return text, ""
    return f'{text}\n\n▶️ <a href="{youtube_url}">Guarda il video completo su YouTube</a>', youtube_url


def _buttons(youtube_url: str) -> str:
    rows = [[{"text": "▶️ Guarda su YouTube", "url": youtube_url}]] if youtube_url else []
    return json.dumps({"inline_keyboard": rows + [[{"text": "📲 Seguimi sul canale", "url": CHANNEL_URL}]]})


def post(video: Video, text: str, follow_up: str = "", youtube_url: str = "") -> str:
    """`text` is Telegram HTML: bold title, links; a button row opens YouTube and the channel."""
    text, button_url = with_youtube(text, youtube_url)
    text, follow_up = linkify(text), linkify(follow_up)
    with open(video.path, "rb") as f:
        r = requests.post(f"{config.API_BASE_URL}/bot{config.BOT_TOKEN}/sendVideo", timeout=600, data={
            "chat_id": config.TELEGRAM_CHANNEL, "caption": text, "parse_mode": "HTML", "reply_markup": _buttons(button_url),
            "width": video.width, "height": video.height, "duration": round(video.duration), "supports_streaming": "true",
        }, files={"video": f})
    body = r.json()
    if not body.get("ok"):
        raise RuntimeError(f"Telegram: {body.get('description') or r.text[:300]}")
    chat = body["result"]["chat"]
    if follow_up:
        r = requests.post(f"{config.API_BASE_URL}/bot{config.BOT_TOKEN}/sendMessage", timeout=60, data={
            "chat_id": config.TELEGRAM_CHANNEL, "text": follow_up, "parse_mode": "HTML", "disable_web_page_preview": "true",
            "reply_to_message_id": body["result"]["message_id"],
        })
        if not r.json().get("ok"):
            raise RuntimeError(f"Telegram, crediti: {r.text[:300]}")
    return f"https://t.me/{chat.get('username') or 'c/' + str(chat['id'])[4:]}/{body['result']['message_id']}"
