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
    """Asosiy entry-point: Gemini (bepul) → Claude → Groq fallback."""
    gemini_key    = os.environ.get("GEMINI_API_KEY", "")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    import logging
    log = logging.getLogger(__name__)

    parsed = None
    # 1) Gemini (bepul, asosiy)
    if gemini_key:
        try:
            parsed = await _gemini_call(user_message, gemini_key)
        except Exception as e:
            log.warning(f"Gemini failed: {e}")

    # 2) Claude (pullik, fallback)
    if parsed is None and anthropic_key:
        try:
            parsed = await _claude_call(user_message, anthropic_key)
        except Exception as e:
            log.warning(f"Claude failed: {e}")

    # 3) Groq (eng oxirgi chora)
    if parsed is None:
        if not groq_key:
            raise ValueError("GEMINI_API_KEY, ANTHROPIC_API_KEY yoki GROQ_API_KEY zarur")
        parsed = await _groq_call(user_message, groq_key)

    # AI javobini standart format ga keltirish
    items = parsed.get("items", [])
    if not items:
        return {"ok": False, "error": "Mahsulot aniqlanmadi"}

    result_items = []
    for it in items:
        result_items.append({
            "name_orig": it.get("name", ""),
            "matched":   it.get("name", ""),
            "grams":     float(it.get("grams") or 0),
            "source":    "AI",
            "kcal":      round(float(it.get("kcal") or 0), 1),
            "protein":   round(float(it.get("protein") or 0), 1),
            "fat":       round(float(it.get("fat") or 0), 1),
            "carb":      round(float(it.get("carb") or 0), 1),
        })

    total_g = float(parsed.get("total_g_cooked") or parsed.get("total_g_raw") or
                    sum(r["grams"] for r in result_items) or 1)

    return {
        "ok": True,
        "result": {
            "name":         parsed.get("name", user_message[:40]),
            "is_recipe":    bool(parsed.get("is_recipe", False)),
            "total_g":      round(total_g, 1),
            "total_g_raw":  parsed.get("total_g_raw"),
            "kcal":         round(float(parsed.get("kcal") or 0), 1),
            "protein":      round(float(parsed.get("protein") or 0), 1),
            "fat":          round(float(parsed.get("fat") or 0), 1),
            "carb":         round(float(parsed.get("carb") or 0), 1),
            "per100_kcal":  round(float(parsed.get("per100_kcal") or 0), 1),
            "per100_p":     round(float(parsed.get("per100_p") or 0), 1),
            "per100_f":     round(float(parsed.get("per100_f") or 0), 1),
            "per100_c":     round(float(parsed.get("per100_c") or 0), 1),
            "items":        result_items,
        },
    }
