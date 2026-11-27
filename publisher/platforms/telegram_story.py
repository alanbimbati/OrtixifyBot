import asyncio

from .. import config
from ..media import Video

# Channel stories are not in the Bot API (postStory is for business accounts only): they go through
# the author's own account, logged in once with `python -m publisher.tg_login`.
CAPTION_MAX = 200
MAX_SECONDS = 60


def available() -> bool:
    return bool(config.TELEGRAM_API_ID and config.TELEGRAM_API_HASH and config.TELEGRAM_USER_SESSION and config.TELEGRAM_CHANNEL)


async def _post(video: Video, caption: str) -> str:
    from telethon import TelegramClient, functions, types
    from telethon.sessions import StringSession

    async with TelegramClient(StringSession(config.TELEGRAM_USER_SESSION), int(config.TELEGRAM_API_ID), config.TELEGRAM_API_HASH) as client:
        channel = await client.get_entity(config.TELEGRAM_CHANNEL)
        if not await client(functions.stories.CanSendStoryRequest(peer=channel)):
            raise RuntimeError("il canale non può pubblicare storie adesso (boost o limite giornaliero)")
        uploaded = await client.upload_file(video.path)
        media = types.InputMediaUploadedDocument(
            file=uploaded, mime_type="video/mp4",
            attributes=[types.DocumentAttributeVideo(duration=video.duration, w=video.width, h=video.height, supports_streaming=True)])
        updates = await client(functions.stories.SendStoryRequest(
            peer=channel, media=media, privacy_rules=[types.InputPrivacyValueAllowAll()], caption=caption[:CAPTION_MAX], period=86400))
        story_id = next(u.id for u in updates.updates if isinstance(u, types.UpdateStoryID))
        return f"https://t.me/{channel.username}/s/{story_id}" if channel.username else f"storia {story_id}"


def post(video: Video, caption: str) -> str:
    if video.duration > MAX_SECONDS:
        raise RuntimeError(f"le storie durano al massimo {MAX_SECONDS} s, il video ne dura {video.duration:.0f}")
    return asyncio.run(_post(video, caption))
