"""The old bot, kept only to point its users to the new one: a full second copy cost the Pi ~250 MB."""
import os
import re
import sqlite3
import threading
import time
from datetime import datetime

import telebot
from telebot import apihelper, types

MOVED_TO = os.environ["MOVED_TO"]
API_BASE_URL = os.getenv("API_BASE_URL", "https://api.telegram.org").rstrip("/")
DB_PATH = os.getenv("DB_PATH", "bot_cache.sqlite3")
NEW_BOT_DB = os.getenv("NEW_BOT_DB", "")
SHUTDOWN_AT = datetime.fromisoformat(os.environ["SHUTDOWN_AT"]) if os.getenv("SHUTDOWN_AT") else None
FAREWELL_AT = [datetime.fromisoformat(t) for t in os.getenv("FAREWELL_AT", "").split(",") if t.strip()]
TEXT = (f"📢 Questo bot ora è {MOVED_TO}.\n\n"
        f"Apri {MOVED_TO}, premi Avvia e mandagli i tuoi link: video in massima qualità, articoli puliti, iscrizioni a canali e siti.")
GROUP_TEXT = (f"📢 Questo bot ora è {MOVED_TO}: aggiungetelo al gruppo al posto mio "
              "per continuare a scaricare video e leggere articoli.")
LINK_RE = re.compile(r"https?://|www\.", re.IGNORECASE)

apihelper.API_URL = f"{API_BASE_URL}/bot{{0}}/{{1}}"
apihelper.FILE_URL = f"{API_BASE_URL}/file/bot{{0}}/{{1}}"
bot = telebot.TeleBot(os.environ["BOT_TOKEN"])


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("CREATE TABLE IF NOT EXISTS moved_notices (chat_id INTEGER PRIMARY KEY, sent_at INTEGER NOT NULL)")
    return conn


def _first_notice(chat_id: int) -> bool:
    # A group is told once: repeating it at every link would be the spam this bot is meant to stop.
    with _db() as conn:
        return conn.execute("INSERT OR IGNORE INTO moved_notices VALUES (?, ?)", (chat_id, int(time.time()))).rowcount > 0


def _farewell_text(is_last: bool, private: bool) -> str:
    when = "Tra un'ora" if is_last else f"Il {SHUTDOWN_AT:%d/%m} alle {SHUTDOWN_AT:%H:%M}"
    go = (f"Apri {MOVED_TO}, premi Avvia e continua da lì: video in massima qualità, articoli puliti, iscrizioni a canali e siti."
          if private else f"Aggiungete {MOVED_TO} al gruppo al posto mio per continuare a scaricare video e leggere articoli.")
    return f"⏳ {when} questo bot si spegne per sempre.\n\n{go}"


def _farewell_recipients() -> list[tuple[int, bool]]:
    with _db() as conn:
        users = {r[0] for r in conn.execute("SELECT user_id FROM users")}
        groups = {r[0] for r in conn.execute(
            "SELECT DISTINCT chat_id FROM downloads_log WHERE chat_type != 'private' AND chat_id IS NOT NULL")}
        groups |= {r[0] for r in conn.execute("SELECT chat_id FROM moved_notices")}
    moved = set()
    if NEW_BOT_DB and os.path.exists(NEW_BOT_DB):
        # Read again before every round: whoever moved after the previous notice is left alone.
        with sqlite3.connect(NEW_BOT_DB, timeout=30) as new:
            moved = {r[0] for r in new.execute("SELECT user_id FROM users UNION SELECT chat_id FROM downloads_log")}
    return [(c, True) for c in sorted(users - moved)] + [(c, False) for c in sorted(groups - moved)]


def _send_farewell(stage: int) -> None:
    is_last = stage == len(FAREWELL_AT) - 1
    with _db() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS farewell_sent (stage INTEGER, chat_id INTEGER, PRIMARY KEY (stage, chat_id))")
        done = {r[0] for r in conn.execute("SELECT chat_id FROM farewell_sent WHERE stage = ?", (stage,))}
    sent = failed = 0
    for chat_id, private in _farewell_recipients():
        if chat_id in done:
            continue
        try:
            bot.send_message(chat_id, _farewell_text(is_last, private))
            sent += 1
        except Exception as e:
            # Blocked the bot or left the group: retrying would fail the same way.
            print(f"Farewell {stage} to {chat_id} failed: {e}")
            failed += 1
        with _db() as conn:
            conn.execute("INSERT OR IGNORE INTO farewell_sent VALUES (?, ?)", (stage, chat_id))
        time.sleep(0.1)
    if sent or failed:
        print(f"Farewell {stage}: {sent} sent, {failed} failed")


def _farewell_loop() -> None:
    while True:
        now = datetime.now().astimezone()
        if SHUTDOWN_AT and now >= SHUTDOWN_AT:
            print("Shutdown time reached, stopping for good")
            # Exit code 0 under "restart: on-failure" keeps the container down.
            os._exit(0)
        due = [i for i, t in enumerate(FAREWELL_AT) if t <= now]
        if due:
            # After downtime only the latest notice goes out, not every missed one.
            try:
                _send_farewell(due[-1])
            except Exception as e:
                print(f"Farewell round failed: {e}")
        time.sleep(60)


def _has_link(message: types.Message) -> bool:
    return bool(LINK_RE.search(message.text or message.caption or ""))


@bot.message_handler(func=lambda m: m.chat.type == "private",
                     content_types=["text", "photo", "video", "animation", "document", "audio", "voice"])
def private(message: types.Message) -> None:
    bot.send_message(message.chat.id, TEXT, reply_markup=types.ReplyKeyboardRemove())


@bot.message_handler(func=lambda m: m.chat.type != "private" and _has_link(m),
                     content_types=["text", "photo", "video", "animation", "document"])
def group(message: types.Message) -> None:
    if _first_notice(message.chat.id):
        bot.reply_to(message, GROUP_TEXT)


@bot.channel_post_handler(func=_has_link, content_types=["text", "photo", "video", "animation", "document"])
def channel(message: types.Message) -> None:
    if _first_notice(message.chat.id):
        bot.send_message(message.chat.id, GROUP_TEXT)


if __name__ == "__main__":
    print(f"Redirect to {MOVED_TO} running, shutdown at {SHUTDOWN_AT}")
    threading.Thread(target=_farewell_loop, daemon=True).start()
    bot.infinity_polling(skip_pending=False, timeout=20, long_polling_timeout=20)
