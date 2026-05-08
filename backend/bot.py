import os, sys, logging, datetime, aiohttp
sys.path.insert(0, os.path.dirname(__file__))

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler

from database import get_users_needing_profile_update

logging.basicConfig(level=logging.INFO)
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
WEBAPP_URL = os.environ.get("WEBAPP_URL", "").rstrip("/")
WEBAPP_URL_V = WEBAPP_URL + "/app?v=46"
API_URL = os.environ.get("WEBAPP_URL", "").rstrip("/")

WAIT_CODE = 1

UNLIMITED_CODES = {"AKA01"}

PROMO_CODES = {
    "NB-Y49CFXF6": True,
    "NB-948OK6C4": True,
    "NB-IOB9PS83": True,
    "NB-3PIV2I02": True,
    "NB-FV9ZDGK2": True,
    "NB-0WP5WGFR": True,
    "NB-3DAL5IQ5": True,
    "NB-OY0MLWF1": True,
    "NB-L4VCFBOJ": True,
    "NB-H9B7RUSR": True,
    "NB-R8BPEZ3H": True,
    "NB-WKUM7BDM": True,
    "NB-RZREBQDH": True,
    "NB-05FJXJNJ": True,
    "NB-JFOM8ICL": True,
    "OTAM-UCHUN": True,
}

allowed_users = set()

async def save_user_info(uid, first_name, username):
    try:
        async with aiohttp.ClientSession() as session:
            await session.post(
                f"{API_URL}/api/bot/save-user",
                json={"user_id": uid, "first_name": first_name or "", "username": username or ""}
            )
    except Exception as e:
        logging.warning(f"Could not save user info: {e}")

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    first_name = update.effective_user.first_name or ""
    username = update.effective_user.username or ""
    await save_user_info(uid, first_name, username)
    if uid in allowed_users:
        await send_app(update)
        return ConversationHandler.END
    await update.message.reply_text(
        "Salom! 👋\n\n<b>BARG</b> ga xush kelibsiz!\n\n"
        "Ilovadan foydalanish uchun <b>promo kod</b> kiriting:",
        parse_mode="HTML"
    )
    return WAIT_CODE

async def check_code(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    first_name = update.effective_user.first_name or ""
    username = update.effective_user.username or ""
    code = update.message.text.strip().upper()

    if code in UNLIMITED_CODES or (code in PROMO_CODES and PROMO_CODES[code]):
        if code not in UNLIMITED_CODES:
            PROMO_CODES[code] = False
        allowed_users.add(uid)
        await save_user_info(uid, first_name, username)
        await update.message.reply_text(
            "Kod tasdiqlandi! BARG ga xush kelibsiz!",
            reply_markup=ReplyKeyboardRemove()
        )
        await send_app(update)
        return ConversationHandler.END
    elif code in PROMO_CODES and not PROMO_CODES[code]:
        await update.message.reply_text("Bu kod allaqachon ishlatilgan. Boshqa kod kiriting:")
        return WAIT_CODE
    else:
        await update.message.reply_text("Noto'g'ri kod. Qayta kiriting:")
        return WAIT_CODE

async def send_app(update: Update):
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("BARG ochish", web_app=WebAppInfo(url=WEBAPP_URL_V))
    ]])
    await update.message.reply_text("Pastdagi tugmani bosib ilovani oching!", reply_markup=kb)

async def remind_profile_update(context: ContextTypes.DEFAULT_TYPE):
    try:
        users = get_users_needing_profile_update()
        logging.info(f"Profile update reminder: {len(users)} users to notify")
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("Profilni yangilash", web_app=WebAppInfo(url=WEBAPP_URL_V))
        ]])
        for user in users:
            try:
                name = user.get("first_name") or ""
                greeting = f"Salom, {name}!" if name else "Salom!"
                await context.bot.send_message(
                    chat_id=user["user_id"],
                    text=(
                        f"👋 {greeting}\n\n"
                        "⚖️ <b>Profil yangilash vaqti keldi!</b>\n\n"
                        "2 hafta o'tdi. Vazniz o'zgangan bo'lishi mumkin.\n\n"
                        "• Ozayotgan bo'lsangiz — yangi maqsad kamroq kaloriya\n"
                        "• Semirgan bo'lsangiz — qayta hisoblash kerak\n"
                        "• Vazn ushlamoqchi bo'lsangiz — nazorat qiling\n\n"
                        "Aniq natija uchun profilingizni yangilang 👇"
                    ),
                    parse_mode="HTML",
                    reply_markup=kb
                )
            except Exception as e:
                logging.warning(f"Could not send reminder to {user.get('user_id')}: {e}")
    except Exception as e:
        logging.error(f"Profile update reminder job error: {e}")

def main():
    if not BOT_TOKEN:
        logging.error("BOT_TOKEN not set")
        return
    app = Application.builder().token(BOT_TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={WAIT_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, check_code)]},
        fallbacks=[CommandHandler("start", start)],
    )
    app.add_handler(conv)

    # Har 2 haftada eslatma — har kuni soat 10:00 da tekshiradi (DB o'zi 14 kundan eski filter qiladi)
    app.job_queue.run_daily(
        remind_profile_update,
        time=datetime.time(10, 0, 0)
    )

    logging.info("Bot started with profile update reminder job")
    app.run_polling(allowed_updates=["message"])

if __name__ == "__main__":
    main()
