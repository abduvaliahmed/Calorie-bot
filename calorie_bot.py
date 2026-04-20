# ══════════════════════════════════════════════
(
    LANG, GENDER, AGE, WEIGHT, HEIGHT, STEPS, GOAL,
    DEFICIT_INPUT, SURPLUS_INPUT
) = range(9)

# ══════════════════════════════════════════════
#  QADAMLAR → FAOLLIK KOEFFITSIENTLARI
# ══════════════════════════════════════════════
STEPS_COEFFICIENTS = [
    (3_000,  1.20),
    (5_000,  1.30),
    (7_000,  1.35),
    (10_000, 1.40),
    (13_000, 1.45),
    (15_000, 1.50),
    (17_000, 1.55),
    (20_000, 1.60),
    (23_000, 1.65),
    (27_000, 1.70),
]

def get_activity_coefficient(steps: int) -> float:
    for threshold, coeff in STEPS_COEFFICIENTS:
        if steps < threshold:
            return coeff
    return 1.70  # 27,000 dan yuqori

# ══════════════════════════════════════════════
#  MATNLAR (O'Z / RU)
# ══════════════════════════════════════════════
T = {
    "uz": {
        "welcome": (
            "👋 Assalomu alaykum!\n\n"
            "🔥 <b>Kaloriya Hisoblagich Bot</b>ga xush kelibsiz!\n\n"
            "Men sizga kunlik kaloriya va makronutrientlarni "
            "aniq hisoblab beraman.\n\n"
            "Boshlash uchun ma'lumotlaringizni kiritamiz 👇"
        ),
        "gender_q": "👤 <b>Jinsingizni tanlang:</b>",
        "gender_m": "👨 Erkak",
        "gender_f": "👩 Ayol",
        "age_q": "🎂 <b>Yoshingizni kiriting</b>\n\nMasalan: <code>25</code>",
        "age_err": "❌ Iltimos, to'g'ri yosh kiriting (10–100 oralig'ida).",
        "weight_q": "⚖️ <b>Vazningizni kiriting (kg)</b>\n\nMasalan: <code>70.5</code>",
        "weight_err": "❌ Iltimos, to'g'ri vazn kiriting (20–300 kg oralig'ida).",
        "height_q": "📏 <b>Bo'yingizni kiriting (sm)</b>\n\nMasalan: <code>175</code>",
        "height_err": "❌ Iltimos, to'g'ri bo'y kiriting (100–250 sm oralig'ida).",
        "steps_q": (
            "🦶 <b>Kunlik o'rtacha qadamlar sonini kiriting</b>\n\n"
            "Masalan: <code>8000</code>\n\n"
            "📌 Bilmasangiz, taxminiy kiriting:\n"
            "• Kam harakat → 3000–5000\n"
            "• O'rta harakat → 7000–10000\n"
            "• Faol → 13000–17000\n"
            "• Juda faol → 20000+"
        ),
        "steps_err": "❌ Iltimos, musbat son kiriting.",
        "goal_q": "🎯 <b>Maqsadingizni tanlang:</b>",
        "goal_lose": "🔻 Vazn yo'qotish",
        "goal_maintain": "⚖️ Vaznni saqlash",
        "goal_muscle": "💪 Massa nabor",
        "deficit_q": (
            "📉 <b>Kunlik kaloriya defitsitini kiriting (kkal)</b>\n\n"
            "Masalan: <code>300</code>\n\n"
            "💡 Tavsiya: 300–500 kkal (xavfsiz va samarali)"
        ),
        "surplus_q": (
            "📈 <b>Kunlik kaloriya profitsitini kiriting (kkal)</b>\n\n"
            "Masalan: <code>300</code>\n\n"
            "💡 Tavsiya: 200–400 kkal (sifatli massa uchun)"
        ),
        "deficit_err": "❌ Iltimos, musbat son kiriting.",
        "result_title": "📊 <b>Sizning natijalaringiz:</b>",
        "saved": "✅ Ma'lumotlaringiz saqlandi!",
        "my_data_empty": "ℹ️ Siz hali ma'lumot kiritmadingiz. /start ni bosing.",
        "recalc": "🔄 Qayta hisoblash",
        "cancel": "❌ Bekor qilish",
        "cancelled": "❌ Amal bekor qilindi. /start orqali qayta boshlashingiz mumkin.",
        "goal_lose_label": "Vazn yo'qotish",
        "goal_maintain_label": "Vaznni saqlash",
        "goal_muscle_label": "Massa nabor",
        "gender_m_label": "Erkak",
        "gender_f_label": "Ayol",
    },
    "ru": {
        "welcome": (
            "👋 Привет!\n\n"
            "🔥 Добро пожаловать в <b>Калькулятор Калорий</b>!\n\n"
            "Я точно рассчитаю ваши суточные калории и макронутриенты.\n\n"
            "Начнём вводить ваши данные 👇"
        ),
        "gender_q": "👤 <b>Выберите ваш пол:</b>",
        "gender_m": "👨 Мужчина",
        "gender_f": "👩 Женщина",
        "age_q": "🎂 <b>Введите ваш возраст</b>\n\nНапример: <code>25</code>",
        "age_err": "❌ Пожалуйста, введите корректный возраст (от 10 до 100).",
        "weight_q": "⚖️ <b>Введите ваш вес (кг)</b>\n\nНапример: <code>70.5</code>",
        "weight_err": "❌ Пожалуйста, введите корректный вес (20–300 кг).",
        "height_q": "📏 <b>Введите ваш рост (см)</b>\n\nНапример: <code>175</code>",
        "height_err": "❌ Пожалуйста, введите корректный рост (100–250 см).",
        "steps_q": (
            "🦶 <b>Введите среднее количество шагов в день</b>\n\n"
            "Например: <code>8000</code>\n\n"
            "📌 Если не знаете, введите приблизительно:\n"
            "• Малоподвижный → 3000–5000\n"
            "• Умеренный → 7000–10000\n"
            "• Активный → 13000–17000\n"
            "• Очень активный → 20000+"
        ),
        "steps_err": "❌ Пожалуйста, введите положительное число.",
        "goal_q": "🎯 <b>Выберите вашу цель:</b>",
        "goal_lose": "🔻 Похудение",
        "goal_maintain": "⚖️ Поддержание веса",
        "goal_muscle": "💪 Набор массы",
        "deficit_q": (
            "📉 <b>Введите суточный дефицит калорий (ккал)</b>\n\n"
            "Например: <code>300</code>\n\n"
            "💡 Рекомендация: 300–500 ккал (безопасно и эффективно)"
        ),
        "surplus_q": (
            "📈 <b>Введите суточный профицит калорий (ккал)</b>\n\n"
            "Например: <code>300</code>\n\n"
            "💡 Рекомендация: 200–400 ккал (для качественной массы)"
        ),
        "deficit_err": "❌ Пожалуйста, введите положительное число.",
        "result_title": "📊 <b>Ваши результаты:</b>",
        "saved": "✅ Ваши данные сохранены!",
        "my_data_empty": "ℹ️ Вы ещё не вводили данные. Нажмите /start.",
        "recalc": "🔄 Пересчитать",
        "cancel": "❌ Отмена",
        "cancelled": "❌ Действие отменено. Вы можете начать заново с /start.",
        "goal_lose_label": "Похудение",
        "goal_maintain_label": "Поддержание веса",
        "goal_muscle_label": "Набор массы",
        "gender_m_label": "Мужчина",
        "gender_f_label": "Женщина",
    }
}

def t(lang: str, key: str) -> str:
    return T.get(lang, T["uz"]).get(key, key)

# ══════════════════════════════════════════════
#  DATABASE
# ══════════════════════════════════════════════
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id     INTEGER PRIMARY KEY,
            lang        TEXT    DEFAULT 'uz',
            gender      TEXT,
            age         INTEGER,
            weight      REAL,
            height      REAL,
            steps       INTEGER,
            goal        TEXT,
            deficit     REAL,
            surplus     REAL,
            updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def save_user(user_id: int, data: dict):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
        INSERT OR REPLACE INTO users
        (user_id, lang, gender, age, weight, height, steps, goal, deficit, surplus, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    """, (
        user_id,
        data.get("lang", "uz"),
        data.get("gender"),
        data.get("age"),
        data.get("weight"),
        data.get("height"),
        data.get("steps"),
        data.get("goal"),
        data.get("deficit", 0),
        data.get("surplus", 0),
    ))
    conn.commit()
    conn.close()

def get_user(user_id: int):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {
            "user_id": row[0], "lang": row[1], "gender": row[2],
            "age": row[3], "weight": row[4], "height": row[5],
            "steps": row[6], "goal": row[7],
            "deficit": row[8], "surplus": row[9],
        }
    return None

# ══════════════════════════════════════════════
#  HISOBLASH
# ══════════════════════════════════════════════
def calculate(data: dict) -> dict:
    gender  = data["gender"]
    age     = float(data["age"])
    weight  = float(data["weight"])
    height  = float(data["height"])
    steps   = int(data["steps"])
    goal    = data["goal"]
    deficit = float(data.get("deficit") or 0)
    surplus = float(data.get("surplus") or 0)

    # BMR — Mifflin-St Jeor
    if gender == "male":
        bmr = 10 * weight + 6.25 * height - 5 * age + 5
    else:
        bmr = 10 * weight + 6.25 * height - 5 * age - 161

    # TDEE
    coeff = get_activity_coefficient(steps)
    tdee  = bmr * coeff

    # Maqsadga qarab kaloriya
    if goal == "lose":
        calories = tdee - deficit
        protein  = round(weight * 2.3, 1)
        fat      = round(weight * 0.7, 1)
    elif goal == "muscle":
        calories = tdee + surplus
        protein  = round(weight * 1.8, 1)
        fat      = round(weight * 1.2, 1)
    else:  # maintain
        calories = tdee
        protein  = round(weight * 1.8, 1)
        fat      = round(weight * 0.9, 1)

    # Uglevod — qolgan kaloriyalar
    calories = round(calories, 1)
    carbs    = round((calories - protein * 4 - fat * 9) / 4, 1)
    if carbs < 0:
        carbs = 0.0

    return {
        "bmr":      round(bmr, 1),
        "tdee":     round(tdee, 1),
        "calories": calories,
        "protein":  protein,
        "fat":      fat,
        "carbs":    carbs,
        "coeff":    coeff,
        "steps":    steps,
    }

def format_result(data: dict, calc: dict, lang: str) -> str:
    goal = data["goal"]
    gender = data["gender"]

    if lang == "uz":
        goal_label   = t(lang, f"goal_{goal}_label")
        gender_label = t(lang, f"gender_{gender[0]}_label")
        activity_label = f"{calc['steps']:,} qadam/kun (×{calc['coeff']})"
    else:
        goal_label   = t(lang, f"goal_{goal}_label")
        gender_label = t(lang, f"gender_{gender[0]}_label")
        activity_label = f"{calc['steps']:,} шагов/день (×{calc['coeff']})"

    if lang == "uz":
        extra = ""
        if goal == "lose":
            extra = f"\n📉 Kaloriya defitsiti: <b>−{data['deficit']} kkal</b>"
        elif goal == "muscle":
            extra = f"\n📈 Kaloriya profitsiti: <b>+{data['surplus']} kkal</b>"

        return (
            f"📊 <b>Sizning natijalaringiz:</b>\n"
            f"{'─' * 28}\n"
            f"👤 Jins: <b>{gender_label}</b>\n"
            f"🎂 Yosh: <b>{data['age']} yosh</b>\n"
            f"⚖️ Vazn: <b>{data['weight']} kg</b>\n"
            f"📏 Bo'y: <b>{data['height']} sm</b>\n"
            f"🦶 Faollik: <b>{activity_label}</b>\n"
            f"🎯 Maqsad: <b>{goal_label}</b>\n"
            f"{'─' * 28}\n"
            f"🔥 BMR: <b>{calc['bmr']} kkal</b>\n"
            f"⚡️ TDEE: <b>{calc['tdee']} kkal</b>\n"
            f"{extra}"
            f"\n🍽 <b>Kunlik me'yor:</b>\n"
            f"🔥 Kaloriya: <b>{calc['calories']} kkal</b>\n"
            f"💪 Oqsil: <b>{calc['protein']} g</b>\n"
            f"🥑 Yog': <b>{calc['fat']} g</b>\n"
            f"🍞 Uglevod: <b>{calc['carbs']} g</b>\n"
            f"{'─' * 28}\n"
            f"📌 <i>Mifflin-St Jeor formulasi asosida</i>"
        )
    else:
        extra = ""
        if goal == "lose":
            extra = f"\n📉 Дефицит калорий: <b>−{data['deficit']} ккал</b>"
        elif goal == "muscle":
            extra = f"\n📈 Профицит калорий: <b>+{data['surplus']} ккал</b>"

        return (
            f"📊 <b>Ваши результаты:</b>\n"
            f"{'─' * 28}\n"
            f"👤 Пол: <b>{gender_label}</b>\n"
            f"🎂 Возраст: <b>{data['age']} лет</b>\n"
            f"⚖️ Вес: <b>{data['weight']} кг</b>\n"
            f"📏 Рост: <b>{data['height']} см</b>\n"
            f"🦶 Активность: <b>{activity_label}</b>\n"
            f"🎯 Цель: <b>{goal_label}</b>\n"
            f"{'─' * 28}\n"
            f"🔥 BMR: <b>{calc['bmr']} ккал</b>\n"
            f"⚡️ TDEE: <b>{calc['tdee']} ккал</b>\n"
            f"{extra}"
            f"\n🍽 <b>Суточная норма:</b>\n"
            f"🔥 Калории: <b>{calc['calories']} ккал</b>\n"
            f"💪 Белок: <b>{calc['protein']} г</b>\n"
            f"🥑 Жир: <b>{calc['fat']} г</b>\n"
            f"🍞 Углеводы: <b>{calc['carbs']} г</b>\n"
            f"{'─' * 28}\n"
            f"📌 <i>По формуле Mifflin-St Jeor</i>"
        )

# ══════════════════════════════════════════════
#  KLAVIATURA YORDAMCHILARI
# ══════════════════════════════════════════════
def kb(buttons: list, one_time: bool = True) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        buttons,
        one_time_keyboard=one_time,
        resize_keyboard=True
    )

def remove_kb() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()

# ══════════════════════════════════════════════
#  HANDLERS
# ══════════════════════════════════════════════
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    keyboard = kb([["🇺🇿 O'zbekcha", "🇷🇺 Русский"]])
    await update.message.reply_text(
        "🌐 <b>Tilni tanlang / Выберите язык:</b>",
        parse_mode="HTML",
        reply_markup=keyboard
    )
    return LANG

async def lang_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    if "Русский" in text or "RU" in text.upper():
        lang = "ru"
    else:
        lang = "uz"
    context.user_data["lang"] = lang

    await update.message.reply_text(
        t(lang, "welcome"),
        parse_mode="HTML",
        reply_markup=remove_kb()
    )
    keyboard = kb([[t(lang, "gender_m"), t(lang, "gender_f")]])
    await update.message.reply_text(
        t(lang, "gender_q"),
        parse_mode="HTML",
        reply_markup=keyboard
    )
    return GENDER

async def gender_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get("lang", "uz")
    text = update.message.text
    if "Erkak" in text or "Мужчина" in text:
        context.user_data["gender"] = "male"
    else:
        context.user_data["gender"] = "female"

    await update.message.reply_text(
        t(lang, "age_q"),
        parse_mode="HTML",
        reply_markup=remove_kb()
    )
    return AGE

async def age_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get("lang", "uz")
    try:
        age = int(update.message.text.strip())
        if not (10 <= age <= 100):
            raise ValueError
        context.user_data["age"] = age
    except ValueError:
        await update.message.reply_text(t(lang, "age_err"), parse_mode="HTML")
        return AGE

    await update.message.reply_text(t(lang, "weight_q"), parse_mode="HTML")
    return WEIGHT

async def weight_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get("lang", "uz")
    try:
        weight = float(update.message.text.strip().replace(",", "."))
        if not (20 <= weight <= 300):
            raise ValueError
        context.user_data["weight"] = weight
    except ValueError:
        await update.message.reply_text(t(lang, "weight_err"), parse_mode="HTML")
        return WEIGHT

    await update.message.reply_text(t(lang, "height_q"), parse_mode="HTML")
    return HEIGHT

async def height_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get("lang", "uz")
    try:
        height = float(update.message.text.strip().replace(",", "."))
        if not (100 <= height <= 250):
            raise ValueError
        context.user_data["height"] = height
    except ValueError:
        await update.message.reply_text(t(lang, "height_err"), parse_mode="HTML")
        return HEIGHT

    await update.message.reply_text(t(lang, "steps_q"), parse_mode="HTML")
    return STEPS

async def steps_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get("lang", "uz")
    try:
        steps = int(update.message.text.strip().replace(",", "").replace(" ", ""))
        if steps <= 0:
            raise ValueError
        context.user_data["steps"] = steps
    except ValueError:
        await update.message.reply_text(t(lang, "steps_err"), parse_mode="HTML")
        return STEPS

    keyboard = kb([
        [t(lang, "goal_lose")],
        [t(lang, "goal_maintain")],
        [t(lang, "goal_muscle")],
    ])
    await update.message.reply_text(
        t(lang, "goal_q"),
        parse_mode="HTML",
        reply_markup=keyboard
    )
    return GOAL

async def goal_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get("lang", "uz")
    text = update.message.text

    if "yo'qotish" in text.lower() or "похудение" in text.lower() or "🔻" in text:
        context.user_data["goal"] = "lose"
        context.user_data["surplus"] = 0
        await update.message.reply_text(
            t(lang, "deficit_q"),
            parse_mode="HTML",
            reply_markup=remove_kb()
        )
        return DEFICIT_INPUT

    elif "massa" in text.lower() or "набор" in text.lower() or "💪" in text:
        context.user_data["goal"] = "muscle"
        context.user_data["deficit"] = 0
        await update.message.reply_text(
            t(lang, "surplus_q"),
            parse_mode="HTML",
            reply_markup=remove_kb()
        )
        return SURPLUS_INPUT

    else:  # maintain
        context.user_data["goal"] = "maintain"
        context.user_data["deficit"] = 0
        context.user_data["surplus"] = 0
        return await show_result(update, context)

async def deficit_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get("lang", "uz")
    try:
        val = float(update.message.text.strip().replace(",", "."))
        if val <= 0:
            raise ValueError
        context.user_data["deficit"] = val
    except ValueError:
        await update.message.reply_text(t(lang, "deficit_err"), parse_mode="HTML")
        return DEFICIT_INPUT

    return await show_result(update, context)

async def surplus_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get("lang", "uz")
    try:
        val = float(update.message.text.strip().replace(",", "."))
        if val <= 0:
            raise ValueError
        context.user_data["surplus"] = val
    except ValueError:
        await update.message.reply_text(t(lang, "deficit_err"), parse_mode="HTML")
        return SURPLUS_INPUT

    return await show_result(update, context)

async def show_result(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get("lang", "uz")
    user_id = update.effective_user.id
    data = context.user_data.copy()

    # Saqlash
    save_user(user_id, data)

    # Hisoblash
    calc = calculate(data)

    # Natijani yuborish
    result_text = format_result(data, calc, lang)

    keyboard = kb([[t(lang, "recalc")]], one_time=False)
    await update.message.reply_text(
        result_text,
        parse_mode="HTML",
        reply_markup=keyboard
    )
    return ConversationHandler.END

async def my_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    data = get_user(user_id)

    if not data:
        await update.message.reply_text(
            "ℹ️ Ma'lumot topilmadi / Данные не найдены.\n\n/start",
            parse_mode="HTML"
        )
        return

    lang = data.get("lang", "uz")
    calc = calculate(data)
    result_text = format_result(data, calc, lang)
    keyboard = kb([[t(lang, "recalc")]], one_time=False)
    await update.message.reply_text(
        result_text,
        parse_mode="HTML",
        reply_markup=keyboard
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get("lang", "uz")
    await update.message.reply_text(
        t(lang, "cancelled"),
        parse_mode="HTML",
        reply_markup=remove_kb()
    )
    context.user_data.clear()
    return ConversationHandler.END

async def recalc_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Qayta hisoblash tugmasi"""
    return await start(update, context)

# ══════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════
def main():
    init_db()
    logger.info("Bot ishga tushmoqda...")

    app = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            MessageHandler(filters.Regex("^(🔄|Qayta hisoblash|Пересчитать)"), recalc_handler),
        ],
        states={
            LANG:          [MessageHandler(filters.TEXT & ~filters.COMMAND, lang_handler)],
            GENDER:        [MessageHandler(filters.TEXT & ~filters.COMMAND, gender_handler)],
            AGE:           [MessageHandler(filters.TEXT & ~filters.COMMAND, age_handler)],
            WEIGHT:        [MessageHandler(filters.TEXT & ~filters.COMMAND, weight_handler)],
            HEIGHT:        [MessageHandler(filters.TEXT & ~filters.COMMAND, height_handler)],
            STEPS:         [MessageHandler(filters.TEXT & ~filters.COMMAND, steps_handler)],
            GOAL:          [MessageHandler(filters.TEXT & ~filters.COMMAND, goal_handler)],
            DEFICIT_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, deficit_handler)],
            SURPLUS_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, surplus_handler)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("mening", my_data))
    app.add_handler(CommandHandler("my", my_data))

    logger.info("✅ Bot muvaffaqiyatli ishga tushdi!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
