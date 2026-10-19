"""
Telegram Join Request Verification Bot

Install:  pip install "python-telegram-bot>=21"
Run:      python join_verify_bot.py
"""
import logging
import os
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    ChatJoinRequestHandler,
    ContextTypes,
)

BOT_TOKEN = os.environ["BOT_TOKEN"]  # Railway Variables mein set karein

# Wo links jo user ko bhejne hain (button ka naam, URL)
LINKS = [
    ("📢 Our Channel", "https://t.me/your_public_channel"),
    ("🌐 Website", "https://example.com"),
]

logging.basicConfig(level=logging.INFO)


async def on_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    req = update.chat_join_request
    user = req.from_user
    chat = req.chat

    keyboard = [[InlineKeyboardButton(text, url=url)] for text, url in LINKS]
    keyboard.append(
        [InlineKeyboardButton("✅ Verify Me", callback_data=f"verify:{chat.id}")]
    )

    try:
        await context.bot.send_message(
            chat_id=req.user_chat_id,
            text=(
                f"Hi {user.first_name}! 👋\n\n"
                f"Aap ne <b>{chat.title}</b> join karne ki request bheji hai.\n"
                "Pehle neeche diye gaye links check karein, phir "
                "<b>Verify Me</b> button dabayein."
            ),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    except Exception as e:
        logging.warning("DM nahi bheja ja saka: %s", e)


async def on_verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = int(query.data.split(":", 1)[1])
    user_id = query.from_user.id

    try:
        await context.bot.approve_chat_join_request(chat_id=chat_id, user_id=user_id)
        await query.answer("Verified ✅")
        await query.edit_message_text("✅ Verification complete! Aap ko channel mein add kar diya gaya hai.")
    except Exception as e:
        logging.warning("Approve fail: %s", e)
        await query.answer("Request nahi mili ya pehle hi approve/decline ho chuki hai.", show_alert=True)


def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(ChatJoinRequestHandler(on_join_request))
    app.add_handler(CallbackQueryHandler(on_verify, pattern=r"^verify:"))
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
