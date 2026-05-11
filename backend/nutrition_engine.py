"""
Hybrid Nutrition Engine — deterministik AI + DB lookup.

Oqim:
  1. AI parse (Groq, temp=0, seed=42) → JSON ingredients
  2. Har mahsulot uchun: local DB (food_global) qidiruvi
  3. Topilmasa: USDA CSV (7793 mahsulot)
  4. Topilmasa: AI strict fallback (temp=0)
  5. Topilgan har bir narsa keshlanadi food_global'ga
"""
import os, json, re, hashlib
import httpx
from pathlib import Path
from difflib import SequenceMatcher

from database import conn, release

_USDA_PATH = Path(__file__).parent / "usda_data.json"
_USDA = None

def _load_usda():
    global _USDA
    if _USDA is None:
        with open(_USDA_PATH, encoding="utf-8") as f:
            data = json.load(f)
        # Indekslash — har bir mahsulot uchun lower-case nom
        _USDA = [(d["name"].lower(), d) for d in data]
    return _USDA


# Mahsulot nomlarini ingliz tiliga tarjima qilish (USDA so'rovi uchun)
PARSE_PROMPT = """You are a nutrition input parser. Extract food ingredients from the user message.
For each ingredient, output: original name (any language), English name (for USDA database), grams (number).

If grams not specified, estimate a typical single serving in grams (e.g., 1 apple = 180g, 1 egg = 50g).

Return ONLY this JSON, nothing else:
{"items":[{"name_orig":"...","name_en":"...","grams":NUMBER}]}

Examples:
Input: "300g qatiq va 100g olma"
Output: {"items":[{"name_orig":"qatiq","name_en":"yogurt, plain, whole milk","grams":300},{"name_orig":"olma","name_en":"apples, raw, with skin","grams":100}]}

Input: "2 tuxum"
Output: {"items":[{"name_orig":"tuxum","name_en":"egg, whole, raw, fresh","grams":100}]}

Input: "150g osh"
Output: {"items":[{"name_orig":"osh","name_en":"rice pilaf with lamb","grams":150}]}"""


FALLBACK_PROMPT = """You are a strict nutrition database. Given an English food name, return its nutrition per 100g.
Source: USDA FoodData Central averages. Be conservative and consistent.

Return ONLY this JSON:
{"kcal":NUMBER,"protein":NUMBER,"fat":NUMBER,"carb":NUMBER}"""


async def _groq_call(system, user, key, max_tokens=400):
    """Groq chatga deterministik (temp=0) so'rov."""
    async with httpx.AsyncClient() as client:
        r = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {"role":"system","content":system},
                    {"role":"user","content":user}
                ],
                "max_tokens": max_tokens,
                "temperature": 0,        # 100% deterministik
                "top_p": 1,
                "seed": 42,              # bir xil natija uchun
                "response_format": {"type":"json_object"}
            },
            timeout=30.0
        )
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"].strip()
        text = text.replace("```json","").replace("```","").strip()
        return json.loads(text)


def _similar(a, b):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _db_search(query):
    """food_global jadvalida fuzzy qidiruv."""
    c = conn(); cur = c.cursor()
    q = f"%{query.lower()}%"
    cur.execute(
        "SELECT name,kcal,protein,fat,carb,COALESCE(source,'') as source,"
        "COALESCE(store,'') as store "
        "FROM food_global WHERE LOWER(name) LIKE %s OR LOWER(COALESCE(name_ru,'')) LIKE %s "
        "ORDER BY length(name) LIMIT 5",
        (q, q)
    )
    rows = [dict(r) for r in cur.fetchall()]
    release(c)
    if not rows:
        return None
    # Eng yaqin nomli (length farq + similarity)
    best = max(rows, key=lambda r: _similar(query, r["name"]))
    if _similar(query, best["name"]) < 0.4:
        return None
    return best


def _usda_search(query_en):
    """USDA CSV ichidan qidirish."""
    if not query_en:
        return None
    db = _load_usda()
    q = query_en.lower()
    # 1. Aniq moslik
    for name, item in db:
        if q == name:
            return _format_usda(item)
    # 2. Boshlanish
    for name, item in db:
        if name.startswith(q):
            return _format_usda(item)
    # 3. Substring + similarity threshold
    candidates = [(name, item, _similar(q, name)) for name, item in db if q in name or name in q]
    if not candidates:
        # 4. Birinchi so'z bo'yicha qidirish
        first_word = q.split(",")[0].split()[0] if q else ""
        if first_word and len(first_word) > 3:
            candidates = [(name, item, _similar(q, name)) for name, item in db
                          if name.startswith(first_word)]
    if not candidates:
        return None
    best = max(candidates, key=lambda x: x[2])
    if best[2] < 0.3:
        return None
    return _format_usda(best[1])


def _format_usda(item):
    return {
        "name":    item["name"],
        "kcal":    item.get("kcal") or 0,
        "protein": item.get("protein") or 0,
        "fat":     item.get("fat") or 0,
        "carb":    item.get("carb") or 0,
    }


def _cache_to_db(name_orig, data, source):
    """Yangi topilgan mahsulotni food_global ga keshlash."""
    c = conn(); cur = c.cursor()
    try:
        cur.execute(
            "INSERT INTO food_global (name,name_ru,kcal,protein,fat,carb,per_grams,source,store,category) "
            "VALUES (%s,'',%s,%s,%s,%s,100,%s,'cached','') ON CONFLICT DO NOTHING",
            (name_orig.title(), float(data["kcal"]), float(data["protein"]),
             float(data["fat"]), float(data["carb"]), source)
        )
        c.commit()
    except Exception:
        c.rollback()
    finally:
        release(c)


async def calc_nutrition(user_message: str, groq_key: str) -> dict:
    """Asosiy entry-point. Foydalanuvchi xabarini hybrid pipeline orqali tahlil qiladi."""
    if not groq_key:
        raise ValueError("GROQ_API_KEY o'rnatilmagan")

    # 1. AI parse
    parsed = await _groq_call(PARSE_PROMPT, user_message, groq_key)
    items = parsed.get("items", [])
    if not items:
        return {"ok": False, "error": "Mahsulot aniqlanmadi"}

    # 2. Har bir ingredient uchun ma'lumot olish
    results = []
    total = {"kcal":0,"protein":0,"fat":0,"carb":0}
    name_parts = []

    for it in items:
        name_orig = (it.get("name_orig") or "").strip()
        name_en   = (it.get("name_en") or "").strip()
        grams     = float(it.get("grams") or 0)
        if not name_orig or grams <= 0:
            continue

        # 2a. Local DB
        food = _db_search(name_orig)
        source = "DB"

        # 2b. USDA
        if not food:
            usda = _usda_search(name_en)
            if usda:
                food = usda
                source = "USDA"
                _cache_to_db(name_orig, usda, "USDA")

        # 2c. Fallback — AI strict (faqat eng oxirgi chora)
        if not food:
            try:
                ai = await _groq_call(FALLBACK_PROMPT, name_en or name_orig, groq_key, max_tokens=120)
                food = {
                    "name":    name_orig,
                    "kcal":    float(ai.get("kcal") or 0),
                    "protein": float(ai.get("protein") or 0),
                    "fat":     float(ai.get("fat") or 0),
                    "carb":    float(ai.get("carb") or 0),
                }
                source = "AI"
                _cache_to_db(name_orig, food, "AI")
            except Exception:
                continue

        # 3. Matematik hisoblash (deterministik)
        ratio = grams / 100.0
        item_macro = {
            "kcal":    round(food["kcal"]    * ratio, 1),
            "protein": round(food["protein"] * ratio, 1),
            "fat":     round(food["fat"]     * ratio, 1),
            "carb":    round(food["carb"]    * ratio, 1),
        }
        for k in total:
            total[k] = round(total[k] + item_macro[k], 1)

        results.append({
            "name_orig": name_orig,
            "matched":   food.get("name", name_orig),
            "grams":     grams,
            "source":    source,
            **item_macro
        })
        name_parts.append(name_orig)

    # 4. 100g uchun ko'rsatkichlar
    total_g = sum(r["grams"] for r in results) or 1
    per100 = {
        "kcal":    round(total["kcal"]    / total_g * 100, 1),
        "protein": round(total["protein"] / total_g * 100, 1),
        "fat":     round(total["fat"]     / total_g * 100, 1),
        "carb":    round(total["carb"]    / total_g * 100, 1),
    }

    return {
        "ok": True,
        "result": {
            "name":       " + ".join(name_parts),
            "total_g":    total_g,
            "kcal":       total["kcal"],
            "protein":    total["protein"],
            "fat":        total["fat"],
            "carb":       total["carb"],
            "per100_kcal": per100["kcal"],
            "per100_p":    per100["protein"],
            "per100_f":    per100["fat"],
            "per100_c":    per100["carb"],
            "items":       results,
        }
    }
