import os, logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO)
BOT_TOKEN = os.environ.get("BOT_TOKEN","")
WEBAPP_URL = os.environ.get("WEBAPP_URL","").rstrip("/")

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🥗 NutriBot ochish", web_app=WebAppInfo(url=WEBAPP_URL))
    ]])
    await update.message.reply_text(
        "Salom! 👋\n\n<b>NutriBot</b> — sizning shaxsiy ovqatlanish yordamchingiz.\n\nKaloriya, makronutrientlar, tana tarkibi — barchasi bir joyda.\n\nPastdagi tugmani bosing 👇",
        parse_mode="HTML", reply_markup=kb
    )

def main():
    if not BOT_TOKEN:
        logging.error("BOT_TOKEN not set")
        return
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    logging.info("Bot started")
    app.run_polling(allowed_updates=["message"])

if __name__ == "__main__":
    main()
