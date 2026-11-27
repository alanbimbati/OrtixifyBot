"""One-time login of the author's Telegram account for channel stories: writes TELEGRAM_USER_SESSION into .env.
Run from the repo root: python -m publisher.tg_login"""
import os

from telethon.sessions import StringSession
from telethon.sync import TelegramClient

ENV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")


def _read_env() -> dict:
    out = {}
    for line in open(ENV, encoding="utf-8"):
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"')
    return out


def main() -> None:
    env = _read_env()
    with TelegramClient(StringSession(), int(env["TELEGRAM_API_ID"]), env["TELEGRAM_API_HASH"]) as client:
        session = client.session.save()
        me = client.get_me()
    lines = [l for l in open(ENV, encoding="utf-8").read().splitlines() if not l.startswith("TELEGRAM_USER_SESSION=")]
    with open(ENV, "w", encoding="utf-8") as f:
        f.write("\n".join(lines + [f"TELEGRAM_USER_SESSION={session}"]) + "\n")
    print(f"Fatto: sessione di {me.first_name} salvata in {ENV} (non condividerla: dà accesso completo all'account).")


if __name__ == "__main__":
    main()
