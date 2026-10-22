"""
Telegram Join Request Message Bot + Broadcast

Install:  pip install "python-telegram-bot>=21,<22"

Railway Variables:
  BOT_TOKEN   = BotFather wala token
  ADMIN_IDS   = aap ki Telegram user id (bot ko /id bhej kar milti hai).
                Ek se zyada hon to comma se alag karein: 111,222
  PHOTO       = (optional) picture ka file_id ya URL

Users ki list SQLite mein save hoti hai. Redeploy par data na jaye is liye
Railway par ek Volume lagayein (RAILWAY_VOLUME_MOUNT_PATH khud use ho jata hai).
"""
import asyncio
import html
import logging
import os
import sqlite3
import time

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LinkPreviewOptions,
    Update,
)
from telegram.error import BadRequest, Forbidden, RetryAfter
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    ChatJoinRequestHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

BOT_TOKEN = os.environ["BOT_TOKEN"]  # Railway Variables mein set karein

ADMIN_IDS = {
    int(x) for x in os.environ.get("ADMIN_IDS", "").replace(" ", "").split(",") if x.isdigit()
}

# ====== YAHAN APNA MESSAGE LIKHEIN ======
# HTML chalta hai: <b>bold</b>, <i>italic</i>, <a href="URL">text</a>
# {name} = user ka naam, {channel} = channel ka naam
MESSAGE = """Hi {name}! 👋

Aap ne <b>{channel}</b> join karne ki request bheji hai.

Yahan apna data / links likhein:
https://example.com
https://t.me/your_public_channel

📊Daily FREE USD/BRL 🇧🇷 OTC Market Session 🚀

🚀10-15 NON - Martingale Insights📊

🚀Join USD/BRL🇧🇷OTC Session 👇
https://t.me/+P5lnLC47U8w4Zjhh
https://t.me/+P5lnLC47U8w4Zjhh
https://t.me/+P5lnLC47U8w4Zjhh
https://t.me/+P5lnLC47U8w4Zjhh
https://t.me/+P5lnLC47U8w4Zjhh

📣 Only 15 Seats Available 🎯 | Book Your Now👆👆👆
"""
# ========================================

# Jab koi user bot ko /start kare (ya Verify button dabaye) to ye message milta hai
# {name} = user ka naam. HTML chalta hai.
WELCOME = """Hi {name}! 👋

<b>Thank you for joining us.</b>

You are now subscribed. We will share regular trading updates and market insights with you right here.

Stay tuned for the next update. 📈

<i>Trading involves risk. Never trade more than you can afford to lose.</i>"""

# Join request wale message ke neeche wale button ka text
BUTTON_TEXT = "Verify I Am Not Robot 🤖"

# Picture bhejni ho to yahan likhein, warna None rehne dein:
#   - repo mein rakhi file ka naam, jaise "photo.jpg"
#   - ya picture ka direct URL (https://...)
#   - ya Telegram file_id
# Railway Variables mein PHOTO naam ka variable set karein to wo is se upar rahega
PHOTO_VAR = (os.environ.get("PHOTO") or "").strip().strip('"').strip("'")
PHOTO_CANDIDATES = [c for c in (PHOTO_VAR, "photo.jpg") if c]
PHOTO = bool(PHOTO_CANDIDATES)

# True = message bhejne ke baad user ko approve bhi kar do
# False = sirf message bhejo, approve/decline aap khud karein
AUTO_APPROVE = False

# ====== AUTO MESSAGE (har X ghante baad sab subscribers ko) ======
# Jin logon ne bot start kiya hai un sab ko ye messages bari bari jate hain.
# Pehli baar 6 ghante baad jayega, phir har 6 ghante baad, aur list ghoom kar dobara shuru.
# HTML chalta hai: <b>bold</b>, <i>italic</i>, <a href="URL">text</a>
# {name} yahan nahi chalta.
AUTO_MESSAGES = [
    """📊 <b>Market Update</b>

Stay tuned. We will share the next trading insights here shortly.""",
    """📈 <b>Reminder</b>

Keep notifications on so you do not miss the next update.""",
]
AUTO_INTERVAL_HOURS = float(os.environ.get("AUTO_INTERVAL_HOURS", "6"))
# =================================================================

logging.basicConfig(level=logging.INFO)

# ---------------------------------------------------------------- database
DATA_DIR = os.environ.get("DATA_DIR") or os.environ.get("RAILWAY_VOLUME_MOUNT_PATH") or "."
DB_PATH = os.path.join(DATA_DIR, "users.db")


def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS users ("
        "user_id INTEGER PRIMARY KEY, first_name TEXT, "
        "added TEXT DEFAULT CURRENT_TIMESTAMP)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)"
    )
    return conn


def save_user(user_id: int, first_name: str):
    with _db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (user_id, first_name) VALUES (?, ?)",
            (user_id, first_name),
        )


def remove_user(user_id: int):
    with _db() as conn:
        conn.execute("DELETE FROM users WHERE user_id = ?", (user_id,))


def get_users():
    with _db() as conn:
        return [r[0] for r in conn.execute("SELECT user_id FROM users")]


def get_setting(key: str, default: str = "") -> str:
    with _db() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row[0] if row else default


def set_setting(key: str, value: str):
    with _db() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


# ----------------------------------------------------------- join requests
async def _send_photo_msg(context, chat_id, photo, text, markup=None):
    if len(text) <= 1024:  # Telegram caption limit
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=photo,
            caption=text,
            parse_mode="HTML",
            reply_markup=markup,
        )
    else:  # lamba message: pehle picture, phir message
        await context.bot.send_photo(chat_id=chat_id, photo=photo)
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="HTML",
            reply_markup=markup,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
    return True


async def on_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    req = update.chat_join_request
    user = req.from_user
    chat = req.chat

    text = MESSAGE.format(
        name=html.escape(user.first_name),
        channel=html.escape(chat.title or ""),
    )

    logging.info("Join request aayi: user=%s chat=%s", user.id, chat.id)

    # Verify button: bot ko open karke /start chalata hai
    markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton(BUTTON_TEXT, url=f"https://t.me/{context.bot.username}?start=join")]]
    )

    sent = False
    for candidate in PHOTO_CANDIDATES:
        try:
            if os.path.isfile(candidate):
                with open(candidate, "rb") as f:
                    sent = await _send_photo_msg(context, req.user_chat_id, f, text, markup)
            else:
                sent = await _send_photo_msg(context, req.user_chat_id, candidate, text, markup)
            if sent:
                break
        except Exception as e:
            logging.error("PICTURE bhejne mein error (%s): %s", candidate[:40], e)

    if not sent:  # picture na ho ya fail ho jaye to sirf message bhejo
        try:
            await context.bot.send_message(
                chat_id=req.user_chat_id,
                text=text,
                parse_mode="HTML",
                reply_markup=markup,
                link_preview_options=LinkPreviewOptions(is_disabled=True),
            )
            sent = True
        except Exception as e:
            logging.error("MESSAGE bhejne mein error: %s", e)

    if AUTO_APPROVE:
        try:
            await context.bot.approve_chat_join_request(chat_id=chat.id, user_id=user.id)
        except Exception as e:
            logging.warning("Approve fail: %s", e)


# ------------------------------------------------------------- user tracking
async def track_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Jo bhi bot ko private mein message/start bheje, usay list mein save karo."""
    u = update.effective_user
    if u and not u.is_bot:
        save_user(u.id, u.first_name or "")


async def on_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    save_user(u.id, u.first_name or "")
    await update.message.reply_text(
        WELCOME.format(name=html.escape(u.first_name or "")), parse_mode="HTML"
    )


async def on_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Aap ki user id: {update.effective_user.id}")


# ----------------------------------------------------------------- broadcast
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


async def on_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await update.message.reply_text(f"Total subscribers: {len(get_users())}")


async def on_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /broadcast Yahan text likhein      -> text sab ko jayega
    (kisi bhi message par reply karke) /broadcast  -> wo message (picture/video/text) sab ko jayega
    """
    msg = update.message
    if not ADMIN_IDS:
        await msg.reply_text("ADMIN_IDS variable set nahi hai. Pehle /id se apni id lein aur Railway Variables mein ADMIN_IDS set karein.")
        return
    if not is_admin(update.effective_user.id):
        return

    if msg.reply_to_message:
        source = ("copy", msg.chat_id, msg.reply_to_message.message_id)
    else:
        parts = (msg.text_html or "").split(None, 1)
        if len(parts) < 2:
            await msg.reply_text(
                "Istemal:\n"
                "/broadcast apna message\n\n"
                "ya kisi message (picture/video/text) par reply karke /broadcast likhein."
            )
            return
        source = ("text", parts[1])

    context.bot_data.setdefault("pending", {})[update.effective_user.id] = source
    total = len(get_users())
    keyboard = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton(f"✅ {total} users ko bhejo", callback_data="bc:yes"),
            InlineKeyboardButton("❌ Cancel", callback_data="bc:no"),
        ]]
    )
    await msg.reply_text("Broadcast confirm karein:", reply_markup=keyboard)


async def on_broadcast_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        await q.answer("Sirf admin.", show_alert=True)
        return

    source = context.bot_data.get("pending", {}).pop(q.from_user.id, None)
    if q.data == "bc:no" or source is None:
        await q.answer()
        await q.edit_message_text("Broadcast cancel / expire ho gaya.")
        return

    await q.answer()
    await q.edit_message_text("Broadcast shuru ho gaya... khatam hone par report milegi.")
    # background task: bot baqi kaam (join requests) karta rahe
    context.application.create_task(
        run_broadcast(context.bot, q.message.chat_id, source)
    )


async def _send_one(bot, uid, source):
    if source[0] == "copy":
        await bot.copy_message(chat_id=uid, from_chat_id=source[1], message_id=source[2])
    else:
        await bot.send_message(
            chat_id=uid,
            text=source[1],
            parse_mode="HTML",
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )


async def run_broadcast(bot, admin_chat_id, source):  # admin_chat_id None = auto
    users = get_users()
    ok = blocked = failed = 0

    for uid in users:
        try:
            try:
                await _send_one(bot, uid, source)
            except RetryAfter as e:  # Telegram ne rokha, thora ruk kar dobara
                await asyncio.sleep(e.retry_after + 1)
                await _send_one(bot, uid, source)
            ok += 1
        except (Forbidden, BadRequest) as e:
            # user ne bot block kiya / account delete / chat nahi mili
            blocked += 1
            remove_user(uid)
            logging.info("Removed %s: %s", uid, e)
        except Exception as e:
            failed += 1
            logging.warning("Broadcast fail %s: %s", uid, e)
        await asyncio.sleep(0.05)  # ~20 msg/second, Telegram limit se neeche

    logging.info("Broadcast done: ok=%s blocked=%s failed=%s", ok, blocked, failed)
    if admin_chat_id is None:
        return
    await bot.send_message(
        admin_chat_id,
        f"✅ Broadcast khatam\n\nBheje gaye: {ok}\nBlock/band (list se hata diye): {blocked}\nFail: {failed}",
    )


# ------------------------------------------------------------ auto broadcast
async def auto_loop(app):
    """Har minute check karta hai; AUTO_INTERVAL_HOURS guzar jayen to sab ko message bhejta hai."""
    while True:
        await asyncio.sleep(60)
        try:
            if get_setting("auto", "on") != "on" or not AUTO_MESSAGES:
                continue
            now = time.time()
            last = float(get_setting("auto_last", "0"))
            if last == 0:  # pehli baar: abhi se timer shuru (deploy par foran nahi bhejta)
                set_setting("auto_last", str(now))
                continue
            if now - last < AUTO_INTERVAL_HOURS * 3600:
                continue
            idx = int(get_setting("auto_idx", "0"))
            text = AUTO_MESSAGES[idx % len(AUTO_MESSAGES)]
            set_setting("auto_idx", str((idx + 1) % len(AUTO_MESSAGES)))
            set_setting("auto_last", str(now))
            await run_broadcast(app.bot, None, ("text", text))
        except Exception as e:
            logging.error("Auto broadcast error: %s", e)


async def post_init(app):
    app.bot_data["auto_task"] = asyncio.create_task(auto_loop(app))


async def on_auto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/auto  (status) | /auto on | /auto off"""
    if not is_admin(update.effective_user.id):
        return
    arg = (context.args[0].lower() if context.args else "")
    if arg in ("on", "off"):
        set_setting("auto", arg)
        if arg == "on":  # on karte hi timer dobara shuru
            set_setting("auto_last", str(time.time()))
    state = get_setting("auto", "on")
    last = float(get_setting("auto_last", "0"))
    if state == "on" and last:
        left = max(0, AUTO_INTERVAL_HOURS * 3600 - (time.time() - last))
        nxt = f"{int(left // 3600)} ghante {int(left % 3600 // 60)} minute baad"
    else:
        nxt = "-"
    await update.message.reply_text(
        f"Auto message: {state.upper()}\n"
        f"Har {AUTO_INTERVAL_HOURS:g} ghante baad\n"
        f"Agla message: {nxt}\n"
        f"Subscribers: {len(get_users())}\n\n"
        "Control: /auto on  |  /auto off"
    )


# --------------------------------------------------------------- file_id tool
async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin picture bhej kar caption mein /fileid likhe to uska file_id milta hai."""
    if not is_admin(update.effective_user.id):
        return
    file_id = update.message.photo[-1].file_id
    await update.message.reply_text(
        f"Is picture ka file_id:\n\n<code>{file_id}</code>\n\n"
        "Isay Railway Variables mein PHOTO ki value ke taur par daal dein.",
        parse_mode="HTML",
    )


def main():
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_handler(ChatJoinRequestHandler(on_join_request))

    # har private message par user save (alag group taake commands bhi chalen)
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE, track_user), group=-1)

    app.add_handler(CommandHandler("start", on_start, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("id", on_id, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("stats", on_stats, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("auto", on_auto, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("broadcast", on_broadcast, filters=filters.ChatType.PRIVATE))
    app.add_handler(CallbackQueryHandler(on_broadcast_confirm, pattern=r"^bc:"))
    app.add_handler(
        MessageHandler(
            filters.PHOTO & filters.CaptionRegex(r"^/fileid") & filters.ChatType.PRIVATE,
            on_photo,
        )
    )

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
