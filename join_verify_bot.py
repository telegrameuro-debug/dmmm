"""
Telegram Join Request Message Bot
Join request aane par user ko aapka custom message bhejta hai.

Install:  pip install "python-telegram-bot>=21,<22"
"""
import html
import logging
import os

from telegram import LinkPreviewOptions, Update
from telegram.ext import (
    Application,
    ChatJoinRequestHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

BOT_TOKEN = os.environ["BOT_TOKEN"]  # Railway Variables mein set karein

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

# Picture bhejni ho to yahan likhein, warna None rehne dein:
#   - repo mein rakhi file ka naam, jaise "photo.jpg"
#   - ya picture ka direct URL (https://...)
#   - ya Telegram file_id
# Railway Variables mein PHOTO naam ka variable set karein to wo is se upar rahega
PHOTO = (os.environ.get("PHOTO") or "").strip().strip('"').strip("'") or (
    "photo.jpg" if os.path.isfile("photo.jpg") else None
)

# True = message bhejne ke baad user ko approve bhi kar do
# False = sirf message bhejo, approve/decline aap khud karein
AUTO_APPROVE = False

logging.basicConfig(level=logging.INFO)


async def on_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    req = update.chat_join_request
    user = req.from_user
    chat = req.chat

    text = MESSAGE.format(
        name=html.escape(user.first_name),
        channel=html.escape(chat.title or ""),
    )

    logging.info("Join request aayi: user=%s chat=%s", user.id, chat.id)

    sent = False
    if PHOTO:
        try:
            photo = open(PHOTO, "rb") if os.path.isfile(PHOTO) else PHOTO
            if len(text) <= 1024:  # Telegram caption limit
                await context.bot.send_photo(
                    chat_id=req.user_chat_id,
                    photo=photo,
                    caption=text,
                    parse_mode="HTML",
                )
            else:  # lamba message: pehle picture, phir message
                await context.bot.send_photo(chat_id=req.user_chat_id, photo=photo)
                await context.bot.send_message(
                    chat_id=req.user_chat_id,
                    text=text,
                    parse_mode="HTML",
                    link_preview_options=LinkPreviewOptions(is_disabled=True),
                )
            sent = True
        except Exception as e:
            logging.error("PICTURE bhejne mein error (PHOTO value check karein): %s", e)

    if not sent:  # picture na ho ya fail ho jaye to sirf message bhejo
        try:
            await context.bot.send_message(
                chat_id=req.user_chat_id,
                text=text,
                parse_mode="HTML",
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


async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bot ko picture bhejein to ye uska file_id bata deta hai."""
    file_id = update.message.photo[-1].file_id
    await update.message.reply_text(
        f"Is picture ka file_id:\n\n<code>{file_id}</code>\n\n"
        "Isay Railway Variables mein PHOTO ki value ke taur par daal dein.",
        parse_mode="HTML",
    )


def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(ChatJoinRequestHandler(on_join_request))
    app.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE, on_photo))
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
