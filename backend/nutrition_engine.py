"""
Nutrition Engine — Claude Haiku orqali kontekstli tahlil.

Claude:
  - "Osh qildim. Guruch 1000g..." → ingredientlar XOM, total kcal yig'iladi
  - "300g osh yedim" → tayyor ovqat, COOKED qiymat
  - "Tovuq qovurdim 200g" → COOKED tovuq
  - Determinizm: temperature=0
"""
import os, json, re, hashlib
from collections import OrderedDict
import httpx
from pathlib import Path
from difflib import SequenceMatcher
from database import conn, release

_USDA_PATH = Path(__file__).parent / "usda_data.json"
_USDA = None

# LRU cache — bir xil so'rov uchun bir xil natija + tezroq javob
_CACHE = OrderedDict()
_CACHE_MAX = 500

def _cache_key(msg: str) -> str:
    norm = re.sub(r"\s+", " ", msg.lower().strip())
    return hashlib.md5(norm.encode()).hexdigest()

def _cache_get(msg):
    k = _cache_key(msg)
    if k in _CACHE:
        _CACHE.move_to_end(k)
        return _CACHE[k]
    return None

def _cache_set(msg, value):
    k = _cache_key(msg)
    _CACHE[k] = value
    _CACHE.move_to_end(k)
    if len(_CACHE) > _CACHE_MAX:
        _CACHE.popitem(last=False)


def _similar(a, b):
    return SequenceMatcher(None, (a or "").lower(), (b or "").lower()).ratio()


def _db_search(query: str):
    """food_global jadvalida QAT'IY qidiruv.
    - 1 so'zli: faqat aniq moslik
    - 2+ so'zli (brand): prefix yoki so'z chegarasi bo'yicha
    - 'cached' store dan kelganlar hisobga olinmaydi (eski xatolar)"""
    if not query or len(query.strip()) < 3:
        return None
    q_low = query.lower().strip()
    # Apostrof variantlarini normallashtirish
    q_low = re.sub(r"[ʻ`´']", "'", q_low)
    q_words = [w for w in q_low.split() if w]
    if not q_words:
        return None

    c = conn(); cur = c.cursor()
    try:
        # 1. Aniq moslik (cached'larsiz)
        cur.execute(
            "SELECT name,kcal,protein,fat,carb FROM food_global "
            "WHERE COALESCE(store,'')<>'cached' AND "
            "(LOWER(name)=%s OR LOWER(COALESCE(name_ru,''))=%s) LIMIT 1",
            (q_low, q_low)
        )
        row = cur.fetchone()
        if row:
            return dict(row)

        # 2. Bir so'zli query — generic so'z, AI ga qoldiramiz
        # Faqat aniq match qaytaradi (yuqorida tekshirildi), aks holda None
        if len(q_words) < 2:
            return None

        # 3. 2+ so'zli — brand-kabi, prefix yoki so'z chegarasi bo'yicha
        # Prefix match
        cur.execute(
            "SELECT name,kcal,protein,fat,carb FROM food_global "
            "WHERE COALESCE(store,'')<>'cached' AND LOWER(name) LIKE %s "
            "ORDER BY length(name) LIMIT 5",
            (q_low + "%",)
        )
        row = cur.fetchone()
        if row:
            return dict(row)

        # Har bir so'z borligini tekshirish (brand ko'p so'zli)
        first_word = q_words[0]
        cur.execute(
            "SELECT name,kcal,protein,fat,carb FROM food_global "
            "WHERE COALESCE(store,'')<>'cached' AND LOWER(name) LIKE %s LIMIT 30",
            (f"%{first_word}%",)
        )
        candidates = [dict(r) for r in cur.fetchall()]
    finally:
        release(c)

    if not candidates:
        return None

    # Ko'p so'z mos kelganlarni afzal ko'ramiz
    def score(r):
        n_low = r["name"].lower()
        n_low_norm = re.sub(r"[ʻ`´']", "'", n_low)
        matched = sum(1 for w in q_words if w in n_low_norm)
        # Aniq prefix bonus
        if n_low_norm.startswith(q_low + " ") or n_low_norm == q_low:
            matched += 5
        return matched

    best = max(candidates, key=score)
    # 2+ so'zli query da kamida 2 ta so'z mos kelishi kerak
    matched_count = sum(1 for w in q_words if w in re.sub(r"[ʻ`´']", "'", best["name"].lower()))
    if matched_count >= max(2, len(q_words)):
        return best
    return None

def _load_usda():
    global _USDA
    if _USDA is None:
        try:
            with open(_USDA_PATH, encoding="utf-8") as f:
                _USDA = [(d["name"].lower(), d) for d in json.load(f)]
        except Exception:
            _USDA = []
    return _USDA


# O'zbek/Rus → USDA inglizcha tarjima
_UZ_TO_USDA = {
    "yog":"oil, vegetable, soybean, refined", "yog'":"oil, vegetable, soybean, refined", "yogi":"oil, vegetable, soybean, refined",
    "osimlik yogi":"oil, vegetable, soybean, refined", "osimlik yog'i":"oil, vegetable, soybean, refined",
    "kungaboqar yog'i":"oil, vegetable, soybean, refined", "zaytun yog'i":"oil, olive, salad or cooking",
    "масло":"oil, vegetable, soybean, refined", "растительное масло":"oil, vegetable, soybean, refined",
    "sariyog":"butter, salted", "sariyog'":"butter, salted",
    "maslo":"butter, salted", "сливочное масло":"butter, salted",
    "guruch":"rice, white, long-grain, regular",
    "guruch pishirilgan":"rice, white, long-grain, regular, enriched, cooked",
    "рис":"rice, white",
    "mol go'shti":"beef, ground, 85", "mol gosht":"beef, ground, 85",
    "говядина":"beef, ground, 85",
    "qo'y go'shti":"lamb, ground", "qoy goshti":"lamb, ground",
    "tovuq":"chicken, breast, meat only, cooked, roasted",
    "tovuq go'shti":"chicken, breast, meat only, cooked, roasted",
    "курица":"chicken, breast",
    "baliq":"fish, tuna, fresh, bluefin, raw",
    "tuxum":"egg, whole, raw, fresh", "яйцо":"egg, whole, raw, fresh",
    "sabzi":"carrots, raw", "морковь":"carrots, raw",
    "piyoz":"onions, raw", "лук":"onions, raw",
    "sarimsoq":"garlic, raw", "чеснок":"garlic, raw",
    "pomidor":"tomatoes, red, ripe, raw", "tomat":"tomatoes, red, ripe, raw",
    "помидор":"tomatoes, red, ripe, raw",
    "bodring":"cucumber, with peel, raw", "огурец":"cucumber, with peel, raw",
    "baqlajon":"eggplant, raw", "qalampir":"peppers, sweet, green, raw",
    "kartoshka":"potatoes, white, flesh and skin, raw",
    "картошка":"potatoes, white, flesh and skin, raw",
    "olma":"apples, raw, with skin", "яблоко":"apples, raw, with skin",
    "banan":"bananas, raw", "apelsin":"oranges, raw",
    "limon":"lemons, raw, without peel", "uzum":"grapes, red or green",
    "qulupnay":"strawberries, raw",
    "non":"bread, white, commercially prepared",
    "qatiq":"yogurt, plain, whole milk", "sut":"milk, whole, 3.25% milkfat",
    "smetana":"sour cream", "сметана":"sour cream",
    "qaymoq":"cream, fluid, heavy whipping", "pishloq":"cheese, cheddar",
    "tvorog":"cheese, cottage, creamed", "kefir":"yogurt, plain, low fat",
    "qand":"sugars, granulated", "сахар":"sugars, granulated",
    "asal":"honey", "shokolad":"candies, milk chocolate",
    "makaron":"pasta, cooked, enriched", "grechka":"buckwheat groats, roasted, cooked",
    "no'xat":"chickpeas, mature seeds, cooked, boiled",
    "loviya":"beans, snap, green, raw",
}


def _usda_search(query):
    """USDA bazadan qidirish. O'zbek/Rus nomlarni tarjima qiladi."""
    if not query:
        return None
    q_orig = query.lower().strip()
    q_norm = re.sub(r"[ʻ`´']", "'", q_orig)
    # Avval lug'atdan tarjima
    translated = _UZ_TO_USDA.get(q_norm) or _UZ_TO_USDA.get(q_orig)
    q = (translated or q_orig).lower()
    db = _load_usda()
    if not db: return None
    # Aniq moslik
    for name, item in db:
        if q == name:
            return {"name": item["name"], "kcal": item.get("kcal") or 0,
                    "protein": item.get("protein") or 0, "fat": item.get("fat") or 0,
                    "carb": item.get("carb") or 0}
    # Prefiks
    for name, item in db:
        if name.startswith(q):
            return {"name": item["name"], "kcal": item.get("kcal") or 0,
                    "protein": item.get("protein") or 0, "fat": item.get("fat") or 0,
                    "carb": item.get("carb") or 0}
    # Birinchi so'z bo'yicha
    first = q.split(",")[0].split()[0] if q else ""
    if first and len(first) > 3:
        for name, item in db:
            if name.startswith(first):
                return {"name": item["name"], "kcal": item.get("kcal") or 0,
                        "protein": item.get("protein") or 0, "fat": item.get("fat") or 0,
                        "carb": item.get("carb") or 0}
    return None


SYSTEM_PROMPT = """You are a precise nutrition calculator for Uzbek/Russian-speaking users.

═══ CONTEXT DETECTION (most important!) ═══
1. RAW INGREDIENTS being LISTED to cook:
   Triggers: "Osh qildim/qilaman", "Lagman pishirdim", "Pishirdim", "Qilaman", "Tayyorladim",
             "Qovurdim", "Qaynatdim", "Yopdim", "Dimladim",
             multiple ingredients with weights/volumes.
   Action: Use RAW USDA values. Total kcal = sum (water doesn't add calories).

2. COOKED FOOD eaten:
   Triggers: "yedim/yeyman", "ichdim/ichaman", single dish name + portion.
   Action: Use COOKED/PREPARED USDA values.

3. Single product (e.g. "Sut Lactel 200ml", "1 olma"):
   Action: Use product-as-is values.

═══ UZBEK FOOD VOCABULARY (translate & normalize) ═══
Cyrillic ↔ Latin: гўшт=go'sht, гуруч=guruch, сабзи=sabzi, пиёз=piyoz, тухум=tuxum,
сут=sut, қатиқ=qatiq, ёғ=yog', нон=non, мош=mosh, чой=choy.

Dishes (cooked): osh/plov, lagman, manti, sho'rva, mastava, dimlama, qovurma,
chuchvara, samsa, somsa, kabob/shashlik, dolma, norin, beshbarmoq,
kotlet, pelmeni, vareniki, blinchik, syrniki, omlet, glazunya.

Meats: mol go'shti=beef, qo'y go'shti=lamb, tovuq go'shti=chicken,
ot go'shti=horse meat, baliq=fish, kazi=horse sausage, kolbasa=sausage,
hot-dog, jambon=ham, salami, sosiska, farsh=mince.

Dairy: sut=milk, qatiq=yogurt, qaymoq=cream, smetana=sour cream,
suzma/tvorog=cottage cheese, ayron=ayran/kefir drink, kefir, ryajenka,
brinza/feta, suluguni, pishloq=cheese, sariyog'/maslo=butter, qaymoqli yog'.

Grains: guruch=rice (oq/jasmin/uzun donli), grechka=buckwheat, oviyolka=oats,
arpa=barley, makaron/spagetti/lapsha/vermishel=pasta, lapsha=noodle,
no'xat=chickpea, mosh=mung bean, loviya=bean, yasmiq=lentil,
kraxmal=starch, manniy yorma=semolina, kus-kus=couscous.

Vegetables: kartoshka=potato, sabzi=carrot, piyoz=onion, sarimsoq=garlic,
pomidor/tomat=tomato, bodring=cucumber, baqlajon=eggplant,
qalampir bulg'or=bell pepper, achchiq qalampir=chili, oshqovoq=pumpkin,
lavlagi/свёкла=beet, sholg'om=turnip, turp=radish, redis=radish,
karam/kapusta=cabbage, ismaloq/shpinat=spinach, kinza=cilantro,
ukrop=dill, rayhon=basil, jambil=thyme, yalpiz=mint, jusay=chives.

Bread: non=bread (patir, lochira, obi non, qatlama, gaza), lavash, batan.

Fruits: olma=apple, nok=pear, banan, apelsin=orange, mandarin,
limon=lemon, anor=pomegranate, uzum=grapes (ko'k sulton),
shaftoli=peach, o'rik=apricot, gilos=cherry, olcha=sour cherry,
qulupnay=strawberry, malina=raspberry, maymunjon=blackberry,
smorodina=currant, anjir=fig, hurma=date, ananas, kivi, ajdarho meva=pitaya,
mangustin, avokado, papayya, mango.

Drinks: choy=tea, qahva=coffee, sok=juice, sharbat=juice,
gazlangan suv=soda, mineral suv=mineral water, kompot, ayron.

Sweets: shokolad=chocolate, pechenye=cookie, tort=cake, bulochka=bun,
vafli=wafer, qand=sugar, asal=honey, varenye/jem=jam, halva,
parvarda=traditional sweet, naboit=rock sugar, marmelad, marshmallow.

Cooking verbs: qovur=fry, pishir=cook, qaynat=boil, dimla=stew,
yop=bake, panjarada=grill, fritura=deep fry, bug'da=steam.

Units: g/gr=grams, kg=kilograms, ml=milliliters, l=liters,
dona/sht=piece, kosa=bowl (200g), stakan=glass (250ml), choy qoshiq=teaspoon (5g),
osh qoshiq/lozhka=tablespoon (15g), kichik tarelka=small plate (200g), katta tarelka=300g,
porsiya=portion.

═══ REFERENCE VALUES (per 100g, USDA — be consistent!) ═══
RAW rice white:    360 kcal, 7 P, 0.6 F, 79 C
COOKED rice:       130 kcal, 2.7 P, 0.3 F, 28 C
RAW beef (lean):   185 kcal, 19 P, 12 F, 0 C
COOKED beef:       250 kcal, 26 P, 15 F, 0 C
RAW chicken breast: 120 kcal, 23 P, 2.6 F, 0 C
COOKED chicken:    165 kcal, 31 P, 3.6 F, 0 C
RAW lamb (mol go'sht): 270 kcal, 17 P, 22 F, 0 C
RAW carrots:       41 kcal, 0.9 P, 0.2 F, 9.6 C
RAW onion:         40 kcal, 1.1 P, 0.1 F, 9.3 C
RAW potato:        77 kcal, 2 P, 0.1 F, 17 C
OILS — ALL OILS ARE ~884 kcal/100g (100% fat):
  Vegetable oil (sunflower/kungaboqar): 884 kcal, 0 P, 100 F, 0 C
  Olive oil (zaytun yog'i):              884 kcal, 0 P, 100 F, 0 C
  Corn oil / soybean oil:                884 kcal, 0 P, 100 F, 0 C
  Coconut oil:                           862 kcal, 0 P, 100 F, 0 C
  Sesame oil (kunjut yog'i):             884 kcal, 0 P, 100 F, 0 C
  1 ml of oil ≈ 0.92g (so 1ml oil ≈ 8.1 kcal, 250ml ≈ 230g ≈ 2070 kcal)
Butter (sariyog'/maslo):                 717 kcal, 0.9 P, 81 F, 0.1 C
Ghee/clarified butter:                   876 kcal, 0 P, 99 F, 0 C
Margarine:                               717 kcal, 0.2 P, 81 F, 0.7 C
White bread:       265 kcal, 9 P, 3.2 F, 49 C
Yogurt plain:      61 kcal, 3.5 P, 3.3 F, 4.7 C
Apple:             52 kcal, 0.3 P, 0.2 F, 14 C
Banana:            89 kcal, 1.1 P, 0.3 F, 23 C
Egg whole:         155 kcal, 13 P, 11 F, 1.1 C
Pasta cooked:      158 kcal, 5.8 P, 0.9 F, 31 C
Buckwheat cooked:  92 kcal, 3.4 P, 0.6 F, 20 C
Potato boiled:     87 kcal, 1.9 P, 0.1 F, 20 C
Sugar:             387 kcal, 0 P, 0 F, 100 C
Honey:             304 kcal, 0.3 P, 0 F, 82 C
Whole milk:        61 kcal, 3.2 P, 3.3 F, 4.8 C

═══ OUTPUT JSON FORMAT (no other text, just JSON!) ═══
{
  "name": "Short dish name in Uzbek (e.g., 'Osh', 'Sut Lactel')",
  "is_recipe": true if user listed raw ingredients to cook a dish,
  "cooked_weight_factor": 1.0 for simple foods OR 1.5-2.5 if cooking rice/pasta absorbs water,
  "items": [
    {
      "name": "Original name as user wrote it (preserve language)",
      "grams": NUMBER (convert ml to grams if needed: oil 1ml=0.92g, water 1ml=1g, milk 1ml=1.03g),
      "form": "raw" or "cooked",
      "kcal": NUMBER (total for this ingredient),
      "protein": NUMBER (total grams),
      "fat": NUMBER (total grams),
      "carb": NUMBER (total grams)
    }
  ],
  "total_g_raw": sum of all item grams,
  "total_g_cooked": approximate after-cooking weight,
  "kcal": TOTAL_KCAL (sum of items),
  "protein": TOTAL_PROTEIN (sum),
  "fat": TOTAL_FAT (sum),
  "carb": TOTAL_CARB (sum),
  "per100_kcal": kcal per 100g of cooked weight,
  "per100_p": protein per 100g cooked,
  "per100_f": fat per 100g cooked,
  "per100_c": carb per 100g cooked
}

═══ CRITICAL RULES ═══
1. EACH ingredient in items[] must have TOTAL values (kcal/p/f/c for the given grams, NOT per 100g).
2. Grand totals must EQUAL the sum of items[].
3. If [DATABASE BRAND PRODUCTS] hint is provided, MATCH user mentions to EXACT names from the list.
4. Numbers must be consistent — same input always gives same output.
5. Round all numbers to 1 decimal place."""


async def _gemini_call_audio(audio_b64: str, mime: str, api_key: str) -> dict:
    """Gemini multimodal — ovoz faylni eshitib tahlil qiladi."""
    # Gemini qo'llab-quvvatlaydigan formatga moslashtirish
    mime_clean = mime.lower().split(";")[0].strip()
    gemini_mime = "audio/wav"
    if mime_clean in ("audio/wav","audio/wave","audio/x-wav"): gemini_mime = "audio/wav"
    elif "mp3" in mime_clean or "mpeg" in mime_clean: gemini_mime = "audio/mp3"
    elif "ogg" in mime_clean: gemini_mime = "audio/ogg"
    elif "aac" in mime_clean or "mp4" in mime_clean or "m4a" in mime_clean: gemini_mime = "audio/aac"
    elif "flac" in mime_clean: gemini_mime = "audio/flac"
    # webm fallback — WAV ga keladi (frontend convert qiladi)

    voice_prompt = (
        "Listen to this audio carefully. The user is speaking in Uzbek, Russian, or English about food they ate or cooked. "
        "Extract every ingredient mentioned with quantities (grams, ml, pieces, etc). "
        "Then calculate KBJU exactly like in the system prompt. "
        "Also include in the response: 'transcript' field with the user's spoken text (in the original language).\n\n"
        "Return the EXACT JSON format from system instructions PLUS one extra field: 'transcript' (string)."
    )

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    async with httpx.AsyncClient() as client:
        r = await client.post(
            url,
            headers={"Content-Type": "application/json"},
            json={
                "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
                "contents": [{
                    "parts": [
                        {"text": voice_prompt},
                        {"inline_data": {"mime_type": gemini_mime, "data": audio_b64}}
                    ],
                    "role": "user"
                }],
                "generationConfig": {
                    "temperature": 0,
                    "topP": 1,
                    "topK": 1,
                    "maxOutputTokens": 1024,
                    "responseMimeType": "application/json",
                },
            },
            timeout=60.0,
        )
        r.raise_for_status()
        data = r.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        text = re.sub(r"```(?:json)?\s*", "", text).replace("```", "").strip()
        m = re.search(r"\{.*\}", text, re.S)
        if m: text = m.group(0)
        return json.loads(text)


async def calc_from_voice(audio_b64: str, mime: str) -> dict:
    """Ovoz xabar → Gemini multimodal → standart format."""
    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    if not gemini_key:
        return {"ok": False, "error": "Gemini API key kerak"}
    try:
        parsed = await _gemini_call_audio(audio_b64, mime, gemini_key)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Voice Gemini failed: {e}")
        return {"ok": False, "error": f"AI ovozni eshita olmadi: {e}"}

    transcript = parsed.get("transcript", "")

    items = parsed.get("items", [])
    if not items:
        return {"ok": False, "error": "Mahsulot aniqlanmadi", "transcript": transcript}

    # Hybrid: DB lookup
    result_items = []
    total = {"kcal":0,"protein":0,"fat":0,"carb":0}
    for it in items:
        name_orig = (it.get("name") or "").strip()
        grams = float(it.get("grams") or 0)
        if not name_orig or grams <= 0: continue
        ai_kcal = float(it.get("kcal") or 0)
        ai_p    = float(it.get("protein") or 0)
        ai_f    = float(it.get("fat") or 0)
        ai_c    = float(it.get("carb") or 0)
        source = "AI"
        matched = name_orig
        db_food = _db_search(name_orig)
        if db_food:
            ratio = grams / 100.0
            ai_kcal = round(float(db_food.get("kcal") or 0) * ratio, 1)
            ai_p    = round(float(db_food.get("protein") or 0) * ratio, 1)
            ai_f    = round(float(db_food.get("fat") or 0) * ratio, 1)
            ai_c    = round(float(db_food.get("carb") or 0) * ratio, 1)
            source = "DB"
            matched = db_food.get("name", name_orig)
        result_items.append({
            "name_orig": name_orig, "matched": matched, "grams": grams,
            "source": source,
            "kcal": round(ai_kcal,1), "protein": round(ai_p,1),
            "fat": round(ai_f,1), "carb": round(ai_c,1)
        })
        total["kcal"] += ai_kcal; total["protein"] += ai_p
        total["fat"] += ai_f; total["carb"] += ai_c

    has_db = any(r["source"]=="DB" for r in result_items)
    if has_db:
        final_kcal = round(total["kcal"],1)
        final_p    = round(total["protein"],1)
        final_f    = round(total["fat"],1)
        final_c    = round(total["carb"],1)
    else:
        final_kcal = round(float(parsed.get("kcal") or 0),1)
        final_p    = round(float(parsed.get("protein") or 0),1)
        final_f    = round(float(parsed.get("fat") or 0),1)
        final_c    = round(float(parsed.get("carb") or 0),1)

    total_g = float(parsed.get("total_g_cooked") or parsed.get("total_g_raw") or sum(r["grams"] for r in result_items) or 1)

    return {
        "ok": True,
        "transcript": transcript,
        "result": {
            "name": parsed.get("name") or transcript[:40] or "Ovozli",
            "is_recipe": bool(parsed.get("is_recipe", False)),
            "total_g": round(total_g, 1),
            "kcal": final_kcal, "protein": final_p,
            "fat": final_f, "carb": final_c,
            "per100_kcal": round(final_kcal/total_g*100,1) if total_g else 0,
            "per100_p": round(final_p/total_g*100,1) if total_g else 0,
            "per100_f": round(final_f/total_g*100,1) if total_g else 0,
            "per100_c": round(final_c/total_g*100,1) if total_g else 0,
            "items": result_items,
        }
    }


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


def _parse_locally(msg: str):
    """Foydalanuvchi xabarini lokal parse qilish — AI'siz.
    Pattern: 'Nom Xg' yoki 'Xg Nom' yoki 'Nom X ml' va h.k."""
    msg_clean = re.sub(r"[.,;]", " ", msg)
    # ml ni gramga aylantirish — yog' uchun 0.92, suv/sut 1.0
    # Patternlar: "olma 100g", "100g olma", "100 g olma", "olma 100"
    pattern = re.compile(
        r"(?:([a-zA-Zа-яА-ЯёЁ'ʻ\s]{2,40}?)\s*(\d+(?:[.,]\d+)?)\s*(гр?|kg|ml|мл|л|l|кг|g|г|шт|штук|dona)?)|"
        r"(?:(\d+(?:[.,]\d+)?)\s*(гр?|kg|ml|мл|л|l|кг|g|г|шт|штук|dona)?\s+([a-zA-Zа-яА-ЯёЁ'ʻ\s]{2,40}?)(?=$|\s\d|\s+va\s|\s+и\s|,))",
        re.I
    )
    items = []
    seen_names = set()
    for m in pattern.finditer(msg_clean):
        name1, num1, unit1, num2, unit2, name2 = m.groups()
        if name1 and num1:
            name = name1.strip(); num = num1; unit = unit1
        elif name2 and num2:
            name = name2.strip(); num = num2; unit = unit2
        else:
            continue
        # Tozalash
        name = re.sub(r"\s+", " ", name).strip()
        name = re.sub(r"^(va|и|и т.?д.?|ham)\s+", "", name, flags=re.I).strip()
        if len(name) < 2 or name.lower() in {"va","i","и","da","na"}: continue
        if name.lower() in seen_names: continue
        seen_names.add(name.lower())
        try:
            grams = float(num.replace(",", "."))
        except:
            continue
        # Birlikni gramga aylantirish
        u = (unit or "g").lower()
        if u in ("kg", "кг"): grams *= 1000
        elif u in ("l", "л"): grams *= 1000  # 1l ~ 1000g
        elif u in ("ml", "мл"): grams *= 0.92 if "yog" in name.lower() or "масл" in name.lower() or "ёг" in name.lower() else 1.0
        elif u in ("шт","штук","dona","sht"):
            # Donalar uchun taxminiy gramm
            n_low = name.lower()
            if "olma" in n_low or "ябл" in n_low: grams *= 180
            elif "tuxum" in n_low or "яйц" in n_low: grams *= 50
            elif "banan" in n_low: grams *= 120
            else: grams *= 100
        if grams > 0 and grams < 10000:
            items.append({"name": name, "grams": grams})
    return items


async def calc_nutrition(user_message: str, groq_key: str = "") -> dict:
    """Asosiy entry-point. Tartib:
    1) In-memory cache
    2) Lokal parse + DB qidiruv (AI'siz, eng tez)
    3) AI fallback (Gemini → Claude → Groq)
    """
    gemini_key    = os.environ.get("GEMINI_API_KEY", "")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    import logging
    log = logging.getLogger(__name__)

    # In-memory cache — bir xil so'rov, bir xil javob (0 ms)
    cached = _cache_get(user_message)
    if cached:
        log.info(f"Cache hit: {user_message[:50]}")
        return cached

    # Lokal parse — DB yoki USDA dan qidirish (AI chaqirmasdan)
    local_items = _parse_locally(user_message)
    if local_items:
        resolved = []
        for li in local_items:
            db_food = _db_search(li["name"])
            if db_food:
                resolved.append((li, db_food, "DB"))
                continue
            usda = _usda_search(li["name"])
            if usda:
                resolved.append((li, usda, "USDA"))
                continue
            # Lokal lookup uzulgan
            resolved = None
            break
        if resolved is not None and len(resolved) == len(local_items):
            log.info(f"Local match for all items: {[i['name'] for i in local_items]}")
            result_items = []
            total = {"kcal":0,"protein":0,"fat":0,"carb":0}
            for li, food, src in resolved:
                g = li["grams"]
                ratio = g / 100.0
                k = round(float(food.get("kcal") or 0) * ratio, 1)
                p = round(float(food.get("protein") or 0) * ratio, 1)
                f = round(float(food.get("fat") or 0) * ratio, 1)
                c = round(float(food.get("carb") or 0) * ratio, 1)
                total["kcal"] += k; total["protein"] += p; total["fat"] += f; total["carb"] += c
                result_items.append({
                    "name_orig": li["name"], "matched": food.get("name", li["name"]),
                    "grams": g, "source": src,
                    "kcal": k, "protein": p, "fat": f, "carb": c
                })
            total_g = sum(r["grams"] for r in result_items) or 1
            response = {
                "ok": True,
                "result": {
                    "name": " + ".join(r["name_orig"] for r in result_items[:3]),
                    "is_recipe": len(result_items) > 1,
                    "total_g": round(total_g, 1),
                    "kcal": round(total["kcal"], 1),
                    "protein": round(total["protein"], 1),
                    "fat": round(total["fat"], 1),
                    "carb": round(total["carb"], 1),
                    "per100_kcal": round(total["kcal"]/total_g*100, 1),
                    "per100_p": round(total["protein"]/total_g*100, 1),
                    "per100_f": round(total["fat"]/total_g*100, 1),
                    "per100_c": round(total["carb"]/total_g*100, 1),
                    "items": result_items,
                }
            }
            _cache_set(user_message, response)
            return response

    # AI ga DB dan FAQAT foydalanuvchining xabariga mos keluvchi mahsulot nomlarini hint sifatida beramiz (RAG)
    db_hint_names = []
    try:
        words = [w for w in re.findall(r"[a-zA-Zа-яА-ЯёЁ'ʻ]{3,}", user_message.lower()) if len(w) >= 3]
        if words:
            c = conn(); cur = c.cursor()
            # Har bir so'z bo'yicha qidirish
            seen = set()
            for w in words[:10]:
                cur.execute(
                    "SELECT name FROM food_global WHERE LOWER(name) LIKE %s ORDER BY length(name) LIMIT 8",
                    (f"%{w}%",)
                )
                for row in cur.fetchall():
                    nm = row[0] if isinstance(row, tuple) else row["name"]
                    if nm not in seen:
                        seen.add(nm)
                        db_hint_names.append(nm)
            release(c)
    except Exception:
        pass

    db_hint = ""
    if db_hint_names:
        # Maks 30 ta nom — Gemini tokenini ortiqcha to'ldirmaslik uchun
        db_hint = ("\n\n[DATABASE BRAND PRODUCTS — if user mentions any of these, "
                   "use this EXACT name and the values for this exact product]:\n"
                   + " | ".join(db_hint_names[:30]))
    enriched_message = user_message + db_hint

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

    response = {
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
    _cache_set(user_message, response)
    return response


async def recalc_from_items(items_list: list) -> dict:
    """Foydalanuvchi tahrir qilgan/qo'shgan ingredientlar bo'yicha qaytadan hisoblash."""
    if not items_list:
        return {"ok": False, "error": "Mahsulot yo'q"}

    # AI ga ehtiyoj bor mahsulotlar (DBda yo'q, per100 ham yo'q)
    needs_ai = []
    for it in items_list:
        name = (it.get("name") or "").strip()
        grams = float(it.get("grams") or 0)
        if not name or grams <= 0:
            continue
        p100 = it.get("per100_kcal")
        has_p100 = (p100 is not None) and (float(p100 or 0) > 0)
        if not has_p100:
            db_food = _db_search(name)
            if not db_food:
                kcal_total = float(it.get("kcal") or 0)
                if kcal_total <= 0:
                    needs_ai.append(name)

    # AI ga so'rov: faqat zarur bo'lgan mahsulotlar uchun
    ai_lookup = {}
    if needs_ai:
        # Avval USDA dan qidirib ko'ramiz (lokal)
        for n in needs_ai:
            usda = _usda_search(n.lower())
            if usda:
                ai_lookup[n.lower()] = {
                    "kcal": float(usda.get("kcal") or 0),
                    "protein": float(usda.get("protein") or 0),
                    "fat": float(usda.get("fat") or 0),
                    "carb": float(usda.get("carb") or 0),
                }
        # Qolganlari uchun AI
        still_need = [n for n in needs_ai if n.lower() not in ai_lookup]
        if still_need:
            try:
                ai_msg = "Hisobla har bir mahsulot uchun 100g uchun KBJU (xom/asl holatda):\n" + \
                         "\n".join(f"- {n}" for n in still_need)
                gemini_key = os.environ.get("GEMINI_API_KEY", "")
                anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
                parsed = None
                if gemini_key:
                    try: parsed = await _gemini_call(ai_msg, gemini_key)
                    except: pass
                if parsed is None and anthropic_key:
                    try: parsed = await _claude_call(ai_msg, anthropic_key)
                    except: pass
                if parsed and parsed.get("items"):
                    for it in parsed["items"]:
                        nm = (it.get("name") or "").lower().strip()
                        g = float(it.get("grams") or 100) or 1
                        ai_lookup[nm] = {
                            "kcal":    float(it.get("kcal") or 0) * 100 / g,
                            "protein": float(it.get("protein") or 0) * 100 / g,
                            "fat":     float(it.get("fat") or 0) * 100 / g,
                            "carb":    float(it.get("carb") or 0) * 100 / g,
                        }
            except Exception:
                pass

    result_items = []
    total = {"kcal":0,"protein":0,"fat":0,"carb":0}
    name_parts = []

    for it in items_list:
        name  = (it.get("name") or "").strip()
        grams = float(it.get("grams") or 0)
        if not name or grams <= 0:
            continue

        # Foydalanuvchi qiymatlarini birinchi olamiz (agar tahrir qilgan bo'lsa)
        per100_kcal = it.get("per100_kcal")
        per100_p    = it.get("per100_p")
        per100_f    = it.get("per100_f")
        per100_c    = it.get("per100_c")

        source = it.get("source", "USER")

        # Agar per100 qiymat yo'q yoki 0 bo'lsa, DBdan qidiramiz
        has_p100 = (per100_kcal is not None) and (float(per100_kcal or 0) > 0)
        if not has_p100:
            db_food = _db_search(name)
            if db_food:
                per100_kcal = float(db_food.get("kcal") or 0)
                per100_p    = float(db_food.get("protein") or 0)
                per100_f    = float(db_food.get("fat") or 0)
                per100_c    = float(db_food.get("carb") or 0)
                source      = "DB"
            elif name.lower() in ai_lookup:
                ai = ai_lookup[name.lower()]
                per100_kcal = ai["kcal"]
                per100_p    = ai["protein"]
                per100_f    = ai["fat"]
                per100_c    = ai["carb"]
                source      = "AI"
            else:
                # Agar AI qiymat berilgan bo'lsa item ichida (kcal, protein...)
                kcal_total = float(it.get("kcal") or 0)
                p_total    = float(it.get("protein") or 0)
                f_total    = float(it.get("fat") or 0)
                c_total    = float(it.get("carb") or 0)
                if grams > 0 and (kcal_total > 0 or p_total > 0 or f_total > 0 or c_total > 0):
                    per100_kcal = kcal_total * 100.0 / grams
                    per100_p    = p_total    * 100.0 / grams
                    per100_f    = f_total    * 100.0 / grams
                    per100_c    = c_total    * 100.0 / grams
                else:
                    continue  # Hech narsa yo'q

        ratio = grams / 100.0
        item_kcal = round(float(per100_kcal) * ratio, 1)
        item_p    = round(float(per100_p) * ratio, 1)
        item_f    = round(float(per100_f) * ratio, 1)
        item_c    = round(float(per100_c) * ratio, 1)

        result_items.append({
            "name_orig": name,
            "matched":   name,
            "grams":     grams,
            "source":    source,
            "kcal":      item_kcal,
            "protein":   item_p,
            "fat":       item_f,
            "carb":      item_c,
        })
        total["kcal"]    += item_kcal
        total["protein"] += item_p
        total["fat"]     += item_f
        total["carb"]    += item_c
        name_parts.append(name)

    total_g = sum(r["grams"] for r in result_items) or 1
    final_kcal = round(total["kcal"], 1)
    final_p    = round(total["protein"], 1)
    final_f    = round(total["fat"], 1)
    final_c    = round(total["carb"], 1)

    return {
        "ok": True,
        "result": {
            "name":         " + ".join(name_parts[:3]) + (" + ..." if len(name_parts) > 3 else ""),
            "is_recipe":    len(result_items) > 1,
            "total_g":      round(total_g, 1),
            "kcal":         final_kcal,
            "protein":      final_p,
            "fat":          final_f,
            "carb":         final_c,
            "per100_kcal":  round(final_kcal/total_g*100, 1) if total_g else 0,
            "per100_p":     round(final_p/total_g*100, 1) if total_g else 0,
            "per100_f":     round(final_f/total_g*100, 1) if total_g else 0,
            "per100_c":     round(final_c/total_g*100, 1) if total_g else 0,
            "items":        result_items,
        },
    }
