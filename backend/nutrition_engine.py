"""
Nutrition Engine — Claude Haiku orqali kontekstli tahlil.

Claude:
  - "Osh qildim. Guruch 1000g..." → ingredientlar XOM, total kcal yig'iladi
  - "300g osh yedim" → tayyor ovqat, COOKED qiymat
  - "Tovuq qovurdim 200g" → COOKED tovuq
  - Determinizm: temperature=0
"""
import os, json, re
import httpx
from pathlib import Path
from difflib import SequenceMatcher
from database import conn, release

_USDA_PATH = Path(__file__).parent / "usda_data.json"
_USDA = None


def _similar(a, b):
    return SequenceMatcher(None, (a or "").lower(), (b or "").lower()).ratio()


def _db_search(query: str):
    """food_global jadvalida fuzzy qidiruv — brand mahsulotlari uchun aniq qiymat."""
    if not query or len(query.strip()) < 3:
        return None
    c = conn(); cur = c.cursor()
    q_low = query.lower().strip()
    q = f"%{q_low}%"
    try:
        # 1. Aniq moslik
        cur.execute(
            "SELECT name,kcal,protein,fat,carb FROM food_global "
            "WHERE LOWER(name)=%s OR LOWER(COALESCE(name_ru,''))=%s LIMIT 1",
            (q_low, q_low)
        )
        row = cur.fetchone()
        if row:
            return dict(row)

        # 2. Substring (ILIKE)
        cur.execute(
            "SELECT name,kcal,protein,fat,carb FROM food_global "
            "WHERE LOWER(name) LIKE %s OR LOWER(COALESCE(name_ru,'')) LIKE %s "
            "ORDER BY length(name) LIMIT 10",
            (q, q)
        )
        rows = [dict(r) for r in cur.fetchall()]
        if not rows:
            # Brand bo'lakli qidiruv — har bir so'z bo'yicha
            words = [w for w in re.split(r"\s+", q_low) if len(w) >= 3]
            if not words:
                return None
            # Hech bo'lmaganda 2 so'z mos kelishi kerak (brand ehtimoli ko'p)
            for word in words:
                cur.execute(
                    "SELECT name,kcal,protein,fat,carb FROM food_global "
                    "WHERE LOWER(name) LIKE %s LIMIT 5",
                    (f"%{word}%",)
                )
                more = [dict(r) for r in cur.fetchall()]
                rows.extend(m for m in more if m not in rows)
            if not rows:
                return None
    finally:
        release(c)

    if not rows:
        return None

    # Eng yaxshi mosini topish
    first_word = q_low.split()[0] if q_low else ""

    def score(r):
        name_low = r["name"].lower()
        s = _similar(q_low, name_low)
        if name_low == q_low:
            s += 1.0
        elif name_low.startswith(q_low + " "):
            s += 0.6
        elif name_low.startswith(q_low):
            s += 0.4
        if first_word and (name_low.startswith(first_word + " ") or name_low == first_word):
            s += 0.3
        # Har bir so'z mos kelsa qo'shimcha bonus (brand uchun)
        q_words = set(q_low.split())
        n_words = set(name_low.split())
        matched_words = q_words & n_words
        if matched_words:
            s += 0.15 * len(matched_words)
        return s

    best = max(rows, key=score)
    final_score = score(best)
    return best if final_score >= 0.35 else None

def _load_usda():
    global _USDA
    if _USDA is None:
        try:
            with open(_USDA_PATH, encoding="utf-8") as f:
                _USDA = [(d["name"].lower(), d) for d in json.load(f)]
        except Exception:
            _USDA = []
    return _USDA


SYSTEM_PROMPT = """You are a precise nutrition calculator. The user describes food in Uzbek or Russian.

KEY TASK: Read the user's message and determine:
1. Are they LISTING RAW INGREDIENTS to cook a dish? (e.g., "Osh qildim. Guruch 1000g, sabzi 1200g, go'sht 400g, yog' 250ml")
   → Use RAW nutrition values for each ingredient
   → Total = sum of all (water doesn't add calories during cooking)
2. Are they reporting cooked food they ATE? (e.g., "300g osh yedim", "200g tovuq kabob")
   → Use COOKED/PREPARED nutrition values
3. Default: if quantity is given for a raw-looking item (e.g., "Guruch 1000g"), it's typically RAW for cooking.

NUTRITION SOURCE: USDA FoodData Central values per 100g. Be consistent — same input must give same numbers.

REFERENCE VALUES (per 100g, USDA):
  Raw rice (white):     360 kcal, 7g P, 0.6g F, 79g C
  Cooked rice (white):  130 kcal, 2.7g P, 0.3g F, 28g C
  Raw beef (lean):      185 kcal, 19g P, 12g F, 0g C
  Cooked beef:          250 kcal, 26g P, 15g F, 0g C
  Raw chicken breast:   120 kcal, 23g P, 2.6g F, 0g C
  Cooked chicken breast: 165 kcal, 31g P, 3.6g F, 0g C
  Raw carrots:          41 kcal, 0.9g P, 0.2g F, 9.6g C
  Vegetable oil:        884 kcal, 0g P, 100g F, 0g C  (1ml ≈ 0.92g)
  Butter:               717 kcal, 0.9g P, 81g F, 0.1g C
  Wheat bread:          265 kcal, 9g P, 3.2g F, 49g C
  Plain yogurt (whole): 61 kcal, 3.5g P, 3.3g F, 4.7g C
  Apple:                52 kcal, 0.3g P, 0.2g F, 14g C
  Banana:               89 kcal, 1.1g P, 0.3g F, 23g C
  Egg (whole):          155 kcal, 13g P, 11g F, 1.1g C
  Pasta cooked:         158 kcal, 5.8g P, 0.9g F, 31g C
  Buckwheat cooked:     92 kcal, 3.4g P, 0.6g F, 20g C
  Potato boiled:        87 kcal, 1.9g P, 0.1g F, 20g C
  Onion raw:            40 kcal, 1.1g P, 0.1g F, 9.3g C

OUTPUT JSON FORMAT (no other text):
{
  "name": "short dish name (Uzbek)",
  "is_recipe": true if user listed raw ingredients to cook,
  "cooked_weight_factor": 1.0 for simple foods OR ~1.5-2.5 if user is cooking (rice absorbs water etc),
  "items": [
    {"name": "Mahsulot nomi", "grams": NUMBER, "form": "raw"|"cooked",
     "kcal": NUMBER, "protein": NUMBER, "fat": NUMBER, "carb": NUMBER}
  ],
  "total_g_raw": SUM_OF_RAW_GRAMS,
  "total_g_cooked": APPROXIMATE_COOKED_WEIGHT,
  "kcal": TOTAL_KCAL,
  "protein": TOTAL_PROTEIN_G,
  "fat": TOTAL_FAT_G,
  "carb": TOTAL_CARB_G,
  "per100_kcal": kcal_per_100g_of_cooked_weight,
  "per100_p": protein_per_100g_of_cooked_weight,
  "per100_f": fat_per_100g_of_cooked_weight,
  "per100_c": carb_per_100g_of_cooked_weight
}

CRITICAL: For each item, kcal/protein/fat/carb are the TOTAL for that ingredient (not per 100g).
The grand total (kcal/protein/...) must equal the sum of items'."""


async def _gemini_call(user_msg: str, api_key: str) -> dict:
    """Google Gemini 2.0 Flash — bepul, kontekstli, deterministik."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    async with httpx.AsyncClient() as client:
        r = await client.post(
            url,
            headers={"Content-Type": "application/json"},
            json={
                "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
                "contents": [{"parts": [{"text": user_msg}], "role": "user"}],
                "generationConfig": {
                    "temperature": 0,
                    "topP": 1,
                    "topK": 1,
                    "maxOutputTokens": 1024,
                    "responseMimeType": "application/json",
                },
            },
            timeout=30.0,
        )
        r.raise_for_status()
        data = r.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        text = re.sub(r"```(?:json)?\s*", "", text).replace("```", "").strip()
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            text = m.group(0)
        return json.loads(text)


async def _claude_call(user_msg: str, api_key: str) -> dict:
    """Anthropic Claude Haiku — deterministik, kontekstli (pullik)."""
    async with httpx.AsyncClient() as client:
        r = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 1024,
                "temperature": 0,
                "system": SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": user_msg}],
            },
            timeout=30.0,
        )
        r.raise_for_status()
        data = r.json()
        text = data["content"][0]["text"].strip()
        text = re.sub(r"```(?:json)?\s*", "", text).replace("```", "").strip()
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            text = m.group(0)
        return json.loads(text)


# === Eski Groq fallback (Claude API mavjud bo'lmasa) ===
async def _groq_call(user_msg: str, api_key: str) -> dict:
    async with httpx.AsyncClient() as client:
        r = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                "max_tokens": 800,
                "temperature": 0,
                "top_p": 1,
                "seed": 42,
                "response_format": {"type": "json_object"},
            },
            timeout=30.0,
        )
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"].strip()
        text = text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)


async def calc_nutrition(user_message: str, groq_key: str = "") -> dict:
    """Asosiy entry-point: Gemini (bepul) → Claude → Groq fallback.
    Hybrid: AI ajratadi, DB'dagi mahsulot bo'lsa uning aniq qiymati ishlatiladi."""
    gemini_key    = os.environ.get("GEMINI_API_KEY", "")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    import logging
    log = logging.getLogger(__name__)

    # AI ga DB dagi brand mahsulotlarining qisqacha ro'yxatini hint sifatida beramiz
    # Shunda u foydalanuvchi yozgan "Sut Lactel" deganini "Sut Lactel 1%" bilan moslashtiradi
    db_hint = ""
    try:
        c = conn(); cur = c.cursor()
        cur.execute("SELECT name FROM food_global ORDER BY id LIMIT 500")
        db_names = [r[0] if isinstance(r, tuple) else r["name"] for r in cur.fetchall()]
        release(c)
        if db_names:
            db_hint = "\n\nKNOWN BRAND PRODUCTS IN DATABASE — if user mentions any of these (even partially), use the EXACT name from this list:\n" + ", ".join(db_names[:300])
    except Exception:
        pass
    enriched_message = user_message + (("\n\n" + db_hint) if db_hint else "")

    parsed = None
    # 1) Gemini (bepul, asosiy)
    if gemini_key:
        try:
            parsed = await _gemini_call(enriched_message, gemini_key)
        except Exception as e:
            log.warning(f"Gemini failed: {e}")

    # 2) Claude (pullik, fallback)
    if parsed is None and anthropic_key:
        try:
            parsed = await _claude_call(enriched_message, anthropic_key)
        except Exception as e:
            log.warning(f"Claude failed: {e}")

    # 3) Groq (eng oxirgi chora)
    if parsed is None:
        if not groq_key:
            raise ValueError("GEMINI_API_KEY, ANTHROPIC_API_KEY yoki GROQ_API_KEY zarur")
        parsed = await _groq_call(enriched_message, groq_key)

    # AI javobini standart format ga keltirish
    items = parsed.get("items", [])
    if not items:
        return {"ok": False, "error": "Mahsulot aniqlanmadi"}

    # HYBRID: agar DBda mahsulot bor bo'lsa, AI qiymatini DB qiymatiga almashtiramiz
    result_items = []
    total = {"kcal":0,"protein":0,"fat":0,"carb":0}

    for it in items:
        name_orig = (it.get("name") or "").strip()
        grams     = float(it.get("grams") or 0)
        if not name_orig or grams <= 0:
            continue

        # AI qiymatini olamiz
        ai_kcal = float(it.get("kcal") or 0)
        ai_p    = float(it.get("protein") or 0)
        ai_f    = float(it.get("fat") or 0)
        ai_c    = float(it.get("carb") or 0)
        source  = "AI"
        matched = name_orig

        # DBdan qidirish
        db_food = _db_search(name_orig)
        if db_food:
            # DB qiymatlari 100g uchun, item uchun grams'ga ko'paytiramiz
            ratio = grams / 100.0
            ai_kcal = round(float(db_food.get("kcal") or 0) * ratio, 1)
            ai_p    = round(float(db_food.get("protein") or 0) * ratio, 1)
            ai_f    = round(float(db_food.get("fat") or 0) * ratio, 1)
            ai_c    = round(float(db_food.get("carb") or 0) * ratio, 1)
            source  = "DB"
            matched = db_food.get("name", name_orig)
            log.info(f"DB match: '{name_orig}' → '{matched}' ({ai_kcal} kcal)")

        result_items.append({
            "name_orig": name_orig,
            "matched":   matched,
            "grams":     grams,
            "source":    source,
            "kcal":      round(ai_kcal, 1),
            "protein":   round(ai_p, 1),
            "fat":       round(ai_f, 1),
            "carb":      round(ai_c, 1),
        })
        total["kcal"]    += ai_kcal
        total["protein"] += ai_p
        total["fat"]     += ai_f
        total["carb"]    += ai_c

    # Agar DB dan biror mahsulot olingan bo'lsa — jami summa qaytadan hisoblanadi
    has_db_match = any(r["source"] == "DB" for r in result_items)
    if has_db_match:
        final_kcal    = round(total["kcal"], 1)
        final_protein = round(total["protein"], 1)
        final_fat     = round(total["fat"], 1)
        final_carb    = round(total["carb"], 1)
    else:
        final_kcal    = round(float(parsed.get("kcal") or 0), 1)
        final_protein = round(float(parsed.get("protein") or 0), 1)
        final_fat     = round(float(parsed.get("fat") or 0), 1)
        final_carb    = round(float(parsed.get("carb") or 0), 1)

    total_g = float(parsed.get("total_g_cooked") or parsed.get("total_g_raw") or
                    sum(r["grams"] for r in result_items) or 1)

    return {
        "ok": True,
        "result": {
            "name":         parsed.get("name", user_message[:40]),
            "is_recipe":    bool(parsed.get("is_recipe", False)),
            "total_g":      round(total_g, 1),
            "total_g_raw":  parsed.get("total_g_raw"),
            "kcal":         final_kcal,
            "protein":      final_protein,
            "fat":          final_fat,
            "carb":         final_carb,
            "per100_kcal":  round(final_kcal/total_g*100, 1) if total_g else 0,
            "per100_p":     round(final_protein/total_g*100, 1) if total_g else 0,
            "per100_f":     round(final_fat/total_g*100, 1) if total_g else 0,
            "per100_c":     round(final_carb/total_g*100, 1) if total_g else 0,
            "items":        result_items,
        },
    }
