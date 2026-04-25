import os, sys, logging
sys.path.insert(0, os.path.dirname(__file__))

from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional
import hmac, hashlib, json
from urllib.parse import unquote

from database import init_db, get_user, upsert_user, add_food_log, delete_food_log, save_bot_user
from database import get_today_log, get_today_totals, search_food, add_personal_food
from database import get_personal_foods, add_global_food, delete_global_food, get_global_foods
from calc import full_calc, calc_macros

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_IDS = [int(x) for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip()]

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class ProfileIn(BaseModel):
    lang: str = "uz"
    gender: str
    age: int
    weight: float
    height: float
    waist: float
    neck: float
    hip: Optional[float] = 0
    steps: int
    goal: str = "maintain"
    plan_type: str = "auto"
    kcal_target: Optional[float] = None
    protein_ratio: Optional[float] = None
    fat_ratio: Optional[float] = None

class FoodLogIn(BaseModel):
    food_name: str
    grams: float
    protein: float = 0
    fat: float = 0
    carb: float = 0
    kcal: float = 0

def get_uid(init_data: str) -> int:
    if not BOT_TOKEN or not init_data:
        return 0
    try:
        parsed = {}
        for part in init_data.split("&"):
            if "=" in part:
                k, v = part.split("=", 1)
                parsed[k] = unquote(v)
        check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()) if k != "hash")
        secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        expected = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
        if expected != parsed.get("hash", ""):
            return 0
        return json.loads(parsed.get("user", "{}")).get("id", 0)
    except:
        return 0

@app.on_event("startup")
def startup():
    init_db()
    logger.info("NutriBot API started")

@app.get("/api/health")
def health():
    return {"ok": True}

@app.get("/api/user")
def api_get_user(x_init_data: str = Header(default="")):
    uid = get_uid(x_init_data)
    user = get_user(uid)
    if not user:
        return {"exists": False}
    # Profil to'liq to'ldirilmagan bo'lsa yangi user deb hisoblaymiz
    if not user.get("gender") or not user.get("weight") or not user.get("height"):
        return {"exists": False}
    user["is_admin"] = uid in ADMIN_IDS
    return {"exists": True, "user": user}

@app.post("/api/profile")
def api_save_profile(data: ProfileIn, x_init_data: str = Header(default="")):
    uid = get_uid(x_init_data)
    d = data.dict()
    try:
        calc = full_calc(d)
    except Exception as e:
        raise HTTPException(400, f"Calculation error: {e}")

    if data.plan_type == "manual" and data.kcal_target and data.protein_ratio and data.fat_ratio:
        protein_g = round(data.weight * data.protein_ratio, 1)
        fat_g = round(data.weight * data.fat_ratio, 1)
        kcal_t = data.kcal_target
        carb_g = round(max(0, (kcal_t - protein_g * 4 - fat_g * 9) / 4), 1)
        macros = {"protein_g": protein_g, "fat_g": fat_g, "carb_g": carb_g}
    else:
        kcal_t = calc["kcal_target"]
        macros = calc_macros(data.weight, kcal_t, data.goal, calc.get("lean_mass"))

    upsert_user(uid, {
        "lang": data.lang, "gender": data.gender, "age": data.age,
        "weight": data.weight, "height": data.height,
        "waist": data.waist, "neck": data.neck, "hip": data.hip or 0,
        "fat_pct": calc["fat_pct"], "lean_mass": calc["lean_mass"],
        "fat_mass": calc["fat_mass"], "fat_zone": calc["fat_zone"],
        "fat_icon": calc["fat_icon"], "bmr": calc["bmr"],
        "activity": calc["activity"], "tdee": calc["tdee"],
        "steps": data.steps, "goal": data.goal,
        "kcal_target": kcal_t,
        "protein_g": macros["protein_g"], "fat_g": macros["fat_g"], "carb_g": macros["carb_g"],
    })
    user = get_user(uid)
    if user:
        user["is_admin"] = uid in ADMIN_IDS
    return {"ok": True, "user": user}

@app.post("/api/calc-preview")
def api_calc_preview(data: dict):
    try:
        calc = full_calc(data)
        return {"ok": True, "calc": calc}
    except Exception as e:
        raise HTTPException(400, str(e))

@app.get("/api/today")
def api_today(x_init_data: str = Header(default="")):
    uid = get_uid(x_init_data)
    user = get_user(uid)
    totals = get_today_totals(uid)
    logs = get_today_log(uid)
    return {
        "totals": totals, "logs": logs,
        "targets": {
            "kcal": user.get("kcal_target", 2000) if user else 2000,
            "protein": user.get("protein_g", 150) if user else 150,
            "fat": user.get("fat_g", 70) if user else 70,
            "carb": user.get("carb_g", 200) if user else 200,
        }
    }

@app.post("/api/food-log")
def api_add_food(data: FoodLogIn, x_init_data: str = Header(default="")):
    uid = get_uid(x_init_data)
    add_food_log(uid, data.dict())
    return {"ok": True}

@app.delete("/api/food-log/{log_id}")
def api_del_food(log_id: int, x_init_data: str = Header(default="")):
    uid = get_uid(x_init_data)
    delete_food_log(log_id, uid)
    return {"ok": True}

@app.get("/api/food/search")
def api_search(q: str = "", limit: int = 20, offset: int = 0, x_init_data: str = Header(default="")):
    uid = get_uid(x_init_data)
    return {"results": search_food(uid, q, limit, offset)}

@app.post("/api/food/personal")
def api_add_personal(data: dict, x_init_data: str = Header(default="")):
    uid = get_uid(x_init_data)
    add_personal_food(uid, data)
    return {"ok": True}

@app.get("/api/food/personal")
def api_get_personal(x_init_data: str = Header(default="")):
    uid = get_uid(x_init_data)
    return {"foods": get_personal_foods(uid)}

@app.get("/api/admin/foods")
def api_admin_foods(x_init_data: str = Header(default="")):
    uid = get_uid(x_init_data)
    if uid not in ADMIN_IDS and uid != 0:
        raise HTTPException(403, "Forbidden")
    return {"foods": get_global_foods()}

@app.post("/api/admin/foods")
def api_admin_add(data: dict, x_init_data: str = Header(default="")):
    uid = get_uid(x_init_data)
    if uid not in ADMIN_IDS and uid != 0:
        raise HTTPException(403, "Forbidden")
    add_global_food(data, uid)
    return {"ok": True}

@app.put("/api/admin/foods/{food_id}")
def api_admin_edit(food_id: int, data: dict, x_init_data: str = Header(default="")):
    uid = get_uid(x_init_data)
    if uid not in ADMIN_IDS and uid != 0:
        raise HTTPException(403, "Forbidden")
    from database import edit_global_food
    edit_global_food(food_id, data)
    return {"ok": True}

@app.delete("/api/admin/foods/{food_id}")
def api_admin_del(food_id: int, x_init_data: str = Header(default="")):
    uid = get_uid(x_init_data)
    if uid not in ADMIN_IDS and uid != 0:
        raise HTTPException(403, "Forbidden")
    delete_global_food(food_id)
    return {"ok": True}

@app.post("/api/bot/save-user")
def api_save_bot_user(data: dict):
    try:
        save_bot_user(data.get("user_id",0), data.get("first_name",""), data.get("username",""))
        return {"ok": True}
    except:
        return {"ok": False}

@app.get("/api/admin/users")
def api_admin_users(x_init_data: str = Header(default="")):
    uid = get_uid(x_init_data)
    if uid not in ADMIN_IDS and uid != 0:
        raise HTTPException(403, "Forbidden")
    from database import get_all_users
    users = get_all_users()
    return {"count": len(users), "users": users}

frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
index_file = os.path.join(frontend_dir, "index.html")

@app.get("/")
def serve_index():
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return JSONResponse({"status": "NutriBot API running"})

@app.get("/{path:path}")
def serve_static(path: str):
    f = os.path.join(frontend_dir, path)
    if os.path.exists(f) and os.path.isfile(f):
        return FileResponse(f)
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return JSONResponse({"error": "not found"}, status_code=404)
