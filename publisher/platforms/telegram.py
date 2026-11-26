import re

import requests

from .. import config
from ..media import Video

CAPTION_MAX = 1024


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
    head, cred = [title, "\n".join(intro).strip()], _credits(credits)
    text = "\n\n".join(p for p in head + [cred, tags] if p)
    if len(text) <= CAPTION_MAX:
        return text, ""
    return "\n\n".join(p for p in head + [tags] if p)[:CAPTION_MAX], cred[:4000]


def post(video: Video, text: str, follow_up: str = "") -> str:
    with open(video.path, "rb") as f:
        r = requests.post(f"{config.API_BASE_URL}/bot{config.BOT_TOKEN}/sendVideo", timeout=600, data={
            "chat_id": config.TELEGRAM_CHANNEL, "caption": text, "width": video.width, "height": video.height,
            "duration": round(video.duration), "supports_streaming": "true",
        }, files={"video": f})
    body = r.json()
    if not body.get("ok"):
        raise RuntimeError(f"Telegram: {body.get('description') or r.text[:300]}")
    chat = body["result"]["chat"]
    if follow_up:
        r = requests.post(f"{config.API_BASE_URL}/bot{config.BOT_TOKEN}/sendMessage", timeout=60, data={
            "chat_id": config.TELEGRAM_CHANNEL, "text": follow_up, "disable_web_page_preview": "true",
            "reply_to_message_id": body["result"]["message_id"],
        })
        if not r.json().get("ok"):
            raise RuntimeError(f"Telegram, crediti: {r.text[:300]}")
    return f"https://t.me/{chat.get('username') or 'c/' + str(chat['id'])[4:]}/{body['result']['message_id']}"
