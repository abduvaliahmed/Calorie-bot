#!/usr/bin/env python3
import logging
import sqlite3
import os
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
DB_NAME = "calorie_bot.db"

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

LANG, GENDER, AGE, WEIGHT, HEIGHT, STEPS, GOAL, DEFICIT_INPUT, SURPLUS_INPUT = range(9)

STEPS_COEFFICIENTS = [
    (3000,1.20),(5000,1.30),(7000,1.35),(10000,1.40),(13000,1.45),
    (15000,1.50),(17000,1.55),(20000,1.60),(23000,1.65),(27000,1.70),
]

def get_activity_coefficient(steps):
    for threshold, coeff in STEPS_COEFFICIENTS:
        if steps < threshold:
            return coeff
    return 1.70

T = {
    "uz": {
        "gender_q":"👤 <b>Jinsingizni tanlang:</b>","gender_m":"👨 Erkak","gender_f":"👩 Ayol",
        "age_q":"🎂 <b>Yoshingizni kiriting</b>\nMasalan: <code>25</code>","age_err":"❌ To'g'ri yosh kiriting (10–100).",
        "weight_q":"⚖️ <b>Vazningizni kiriting (kg)</b>\nMasalan: <code>70</code>","weight_err":"❌ To'g'ri vazn kiriting (20–300 kg).",
        "height_q":"📏 <b>Bo'yingizni kiriting (sm)</b>\nMasalan: <code>175</code>","height_err":"❌ To'g'ri bo'y kiriting (100–250 sm).",
        "steps_q":"🦶 <b>Kunlik o'rtacha qadamlar sonini kiriting</b>\nMasalan: <code>8000</code>","steps_err":"❌ Musbat son kiriting.",
        "goal_q":"🎯 <b>Maqsadingizni tanlang:</b>","goal_lose":"🔻 Vazn yo'qotish","goal_maintain":"⚖️ Vaznni saqlash","goal_muscle":"💪 Massa nabor",
        "deficit_q":"📉 <b>Kunlik kaloriya defitsitini kiriting (kkal)</b>\nMasalan: <code>300</code>",
        "surplus_q":"📈 <b>Kunlik kaloriya profitsitini kiriting (kkal)</b>\nMasalan: <code>300</code>",
        "num_err":"❌ Musbat son kiriting.","recalc":"🔄 Qayta hisoblash","cancelled":"❌ Bekor qilindi. /start bosing.",
        "gender_m_label":"Erkak","gender_f_label":"Ayol","goal_lose_label":"Vazn yo'qotish","goal_maintain_label":"Vaznni saqlash","goal_muscle_label":"Massa nabor",
    },
    "ru": {
        "gender_q":"👤 <b>Выберите ваш пол:</b>","gender_m":"👨 Мужчина","gender_f":"👩 Женщина",
        "age_q":"🎂 <b>Введите ваш возраст</b>\nНапример: <code>25</code>","age_err":"❌ Введите корректный возраст (10–100).",
        "weight_q":"⚖️ <b>Введите ваш вес (кг)</b>\nНапример: <code>70</code>","weight_err":"❌ Введите корректный вес (20–300 кг).",
        "height_q":"📏 <b>Введите ваш рост (см)</b>\nНапример: <code>175</code>","height_err":"❌ Введите корректный рост (100–250 см).",
        "steps_q":"🦶 <b>Введите среднее количество шагов в день</b>\nНапример: <code>8000</code>","steps_err":"❌ Введите положительное число.",
        "goal_q":"🎯 <b>Выберите вашу цель:</b>","goal_lose":"🔻 Похудение","goal_maintain":"⚖️ Поддержание веса","goal_muscle":"💪 Набор массы",
        "deficit_q":"📉 <b>Введите суточный дефицит калорий (ккал)</b>\nНапример: <code>300</code>",
        "surplus_q":"📈 <b>Введите суточный профицит калорий (ккал)</b>\nНапример: <code>300</code>",
        "num_err":"❌ Введите положительное число.","recalc":"🔄 Пересчитать","cancelled":"❌ Отменено. Нажмите /start.",
        "gender_m_label":"Мужчина","gender_f_label":"Женщина","goal_lose_label":"Похудение","goal_maintain_label":"Поддержание веса","goal_muscle_label":"Набор массы",
    }
}

def t(lang, key):
    return T.get(lang, T["uz"]).get(key, key)

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY, lang TEXT, gender TEXT, age INTEGER,
        weight REAL, height REAL, steps INTEGER, goal TEXT, deficit REAL, surplus REAL)""")
    conn.commit()
    conn.close()

def save_user(user_id, data):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO users (user_id,lang,gender,age,weight,height,steps,goal,deficit,surplus) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (user_id,data.get("lang","uz"),data.get("gender"),data.get("age"),data.get("weight"),
         data.get("height"),data.get("steps"),data.get("goal"),data.get("deficit",0),data.get("surplus",0)))
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {"user_id":row[0],"lang":row[1],"gender":row[2],"age":row[3],"weight":row[4],"height":row[5],"steps":row[6],"goal":row[7],"deficit":row[8],"surplus":row[9]}
    return None

def calculate(data):
    gender=data["gender"]; age=float(data["age"]); weight=float(data["weight"])
    height=float(data["height"]); steps=int(data["steps"]); goal=data["goal"]
    deficit=float(data.get("deficit") or 0); surplus=float(data.get("surplus") or 0)
    bmr = 10*weight+6.25*height-5*age+(5 if gender=="male" else -161)
    coeff = get_activity_coefficient(steps)
    tdee = bmr * coeff
    if goal=="lose":
        calories=tdee-deficit; protein=round(weight*2.3,1); fat=round(weight*0.7,1)
    elif goal=="muscle":
        calories=tdee+surplus; protein=round(weight*1.8,1); fat=round(weight*1.2,1)
    else:
        calories=tdee; protein=round(weight*1.8,1); fat=round(weight*0.9,1)
    calories=round(calories,1)
    carbs=round((calories-protein*4-fat*9)/4,1)
    if carbs<0: carbs=0.0
    return {"bmr":round(bmr,1),"tdee":round(tdee,1),"calories":calories,"protein":protein,"fat":fat,"carbs":carbs,"coeff":coeff}

def format_result(data, calc, lang):
    goal=data["goal"]; gender=data["gender"]
    gl=t(lang,f"gender_{'m' if gender=='male' else 'f'}_label")
    ql=t(lang,f"goal_{goal}_label")
    if lang=="uz":
        ex=""
        if goal=="lose": ex=f"\n📉 Defitsit: <b>−{data['deficit']} kkal</b>"
        elif goal=="muscle": ex=f"\n📈 Profitsit: <b>+{data['surplus']} kkal</b>"
        return (f"📊 <b>Sizning natijalaringiz:</b>\n{'─'*28}\n"
                f"👤 Jins: <b>{gl}</b>\n🎂 Yosh: <b>{data['age']} yosh</b>\n"
                f"⚖️ Vazn: <b>{data['weight']} kg</b>\n📏 Bo'y: <b>{data['height']} sm</b>\n"
                f"🦶 Qadamlar: <b>{data['steps']:,}/kun (×{calc['coeff']})</b>\n🎯 Maqsad: <b>{ql}</b>\n"
                f"{'─'*28}\n🔥 BMR: <b>{calc['bmr']} kkal</b>\n⚡️ TDEE: <b>{calc['tdee']} kkal</b>\n{ex}\n"
                f"🍽 <b>Kunlik me'yor:</b>\n🔥 Kaloriya: <b>{calc['calories']} kkal</b>\n"
                f"💪 Oqsil: <b>{calc['protein']} g</b>\n🥑 Yog': <b>{calc['fat']} g</b>\n"
                f"🍞 Uglevod: <b>{calc['carbs']} g</b>\n{'─'*28}\n📌 <i>Mifflin-St Jeor formulasi</i>")
    else:
        ex=""
        if goal=="lose": ex=f"\n📉 Дефицит: <b>−{data['deficit']} ккал</b>"
        elif goal=="muscle": ex=f"\n📈 Профицит: <b>+{data['surplus']} ккал</b>"
        return (f"📊 <b>Ваши результаты:</b>\n{'─'*28}\n"
                f"👤 Пол: <b>{gl}</b>\n🎂 Возраст: <b>{data['age']} лет</b>\n"
                f"⚖️ Вес: <b>{data['weight']} кг</b>\n📏 Рост: <b>{data['height']} см</b>\n"
                f"🦶 Шаги: <b>{data['steps']:,}/день (×{calc['coeff']})</b>\n🎯 Цель: <b>{ql}</b>\n"
                f"{'─'*28}\n🔥 BMR: <b>{calc['bmr']} ккал</b>\n⚡️ TDEE: <b>{calc['tdee']} ккал</b>\n{ex}\n"
                f"🍽 <b>Суточная норма:</b>\n🔥 Калории: <b>{calc['calories']} ккал</b>\n"
                f"💪 Белок: <b>{calc['protein']} г</b>\n🥑 Жир: <b>{calc['fat']} г</b>\n"
                f"🍞 Углеводы: <b>{calc['carbs']} г</b>\n{'─'*28}\n📌 <i>Формула Mifflin-St Jeor</i>")

def kb(buttons, one_time=True):
    return ReplyKeyboardMarkup(buttons, one_time_keyboard=one_time, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("🌐 <b>Tilni tanlang / Выберите язык:</b>", parse_mode="HTML",
        reply_markup=kb([["🇺🇿 O'zbekcha","🇷🇺 Русский"]]))
    return LANG

async def lang_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = "ru" if "Русский" in update.message.text else "uz"
    context.user_data["lang"] = lang
    await update.message.reply_text(t(lang,"gender_q"), parse_mode="HTML",
        reply_markup=kb([[t(lang,"gender_m"),t(lang,"gender_f")]]))
    return GENDER

async def gender_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang","uz")
    text = update.message.text
    context.user_data["gender"] = "male" if ("Erkak" in text or "Мужчина" in text) else "female"
    await update.message.reply_text(t(lang,"age_q"), parse_mode="HTML", reply_markup=ReplyKeyboardRemove())
    return AGE

async def age_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang","uz")
    try:
        age = int(update.message.text.strip())
        assert 10<=age<=100
        context.user_data["age"] = age
    except:
        await update.message.reply_text(t(lang,"age_err"), parse_mode="HTML")
        return AGE
    await update.message.reply_text(t(lang,"weight_q"), parse_mode="HTML")
    return WEIGHT

async def weight_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang","uz")
    try:
        w = float(update.message.text.strip().replace(",","."))
        assert 20<=w<=300
        context.user_data["weight"] = w
    except:
        await update.message.reply_text(t(lang,"weight_err"), parse_mode="HTML")
        return WEIGHT
    await update.message.reply_text(t(lang,"height_q"), parse_mode="HTML")
    return HEIGHT

async def height_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang","uz")
    try:
        h = float(update.message.text.strip().replace(",","."))
        assert 100<=h<=250
        context.user_data["height"] = h
    except:
        await update.message.reply_text(t(lang,"height_err"), parse_mode="HTML")
        return HEIGHT
    await update.message.reply_text(t(lang,"steps_q"), parse_mode="HTML")
    return STEPS

async def steps_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang","uz")
    try:
        s = int(update.message.text.strip().replace(",","").replace(" ",""))
        assert s>0
        context.user_data["steps"] = s
    except:
        await update.message.reply_text(t(lang,"steps_err"), parse_mode="HTML")
        return STEPS
    await update.message.reply_text(t(lang,"goal_q"), parse_mode="HTML",
        reply_markup=kb([[t(lang,"goal_lose")],[t(lang,"goal_maintain")],[t(lang,"goal_muscle")]]))
    return GOAL

async def goal_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang","uz")
    text = update.message.text
    if "yo'qotish" in text.lower() or "похудение" in text.lower() or "🔻" in text:
        context.user_data["goal"]="lose"; context.user_data["surplus"]=0
        await update.message.reply_text(t(lang,"deficit_q"), parse_mode="HTML", reply_markup=ReplyKeyboardRemove())
        return DEFICIT_INPUT
    elif "massa" in text.lower() or "набор" in text.lower() or "💪" in text:
        context.user_data["goal"]="muscle"; context.user_data["deficit"]=0
        await update.message.reply_text(t(lang,"surplus_q"), parse_mode="HTML", reply_markup=ReplyKeyboardRemove())
        return SURPLUS_INPUT
    else:
        context.user_data["goal"]="maintain"; context.user_data["deficit"]=0; context.user_data["surplus"]=0
        return await show_result(update, context)

async def deficit_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang","uz")
    try:
        v = float(update.message.text.strip().replace(",",".")); assert v>0
        context.user_data["deficit"] = v
    except:
        await update.message.reply_text(t(lang,"num_err"), parse_mode="HTML")
        return DEFICIT_INPUT
    return await show_result(update, context)

async def surplus_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang","uz")
    try:
        v = float(update.message.text.strip().replace(",",".")); assert v>0
        context.user_data["surplus"] = v
    except:
        await update.message.reply_text(t(lang,"num_err"), parse_mode="HTML")
        return SURPLUS_INPUT
    return await show_result(update, context)

async def show_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang","uz")
    data = context.user_data.copy()
    save_user(update.effective_user.id, data)
    calc = calculate(data)
    await update.message.reply_text(format_result(data,calc,lang), parse_mode="HTML",
        reply_markup=kb([[t(lang,"recalc")]], one_time=False))
    return ConversationHandler.END

async def my_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = get_user(update.effective_user.id)
    if not data:
        await update.message.reply_text("ℹ️ Ma'lumot topilmadi. /start"); return
    lang = data.get("lang","uz")
    calc = calculate(data)
    await update.message.reply_text(format_result(data,calc,lang), parse_mode="HTML",
        reply_markup=kb([[t(lang,"recalc")]], one_time=False))

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang","uz")
    await update.message.reply_text(t(lang,"cancelled"), parse_mode="HTML", reply_markup=ReplyKeyboardRemove())
    context.user_data.clear()
    return ConversationHandler.END

async def recalc_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await start(update, context)

def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CommandHandler("start",start),
                      MessageHandler(filters.Regex("^(🔄|Qayta hisoblash|Пересчитать)"),recalc_handler)],
        states={
            LANG:[MessageHandler(filters.TEXT&~filters.COMMAND,lang_handler)],
            GENDER:[MessageHandler(filters.TEXT&~filters.COMMAND,gender_handler)],
            AGE:[MessageHandler(filters.TEXT&~filters.COMMAND,age_handler)],
            WEIGHT:[MessageHandler(filters.TEXT&~filters.COMMAND,weight_handler)],
            HEIGHT:[MessageHandler(filters.TEXT&~filters.COMMAND,height_handler)],
            STEPS:[MessageHandler(filters.TEXT&~filters.COMMAND,steps_handler)],
            GOAL:[MessageHandler(filters.TEXT&~filters.COMMAND,goal_handler)],
            DEFICIT_INPUT:[MessageHandler(filters.TEXT&~filters.COMMAND,deficit_handler)],
            SURPLUS_INPUT:[MessageHandler(filters.TEXT&~filters.COMMAND,surplus_handler)],
        },
        fallbacks=[CommandHandler("cancel",cancel)],
        allow_reentry=True,
    )
    app.add_handler(conv)
    app.add_handler(CommandHandler("mening",my_data))
    app.add_handler(CommandHandler("my",my_data))
    logger.info("✅ Bot muvaffaqiyatli ishga tushdi!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
