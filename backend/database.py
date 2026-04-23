import sqlite3, datetime, os

DB = os.environ.get("DB_NAME", "nutribot.db")

def conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    c = conn()
    cur = c.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY, lang TEXT DEFAULT 'uz',
        gender TEXT, age INTEGER, weight REAL, height REAL,
        waist REAL, neck REAL, hip REAL DEFAULT 0,
        fat_pct REAL, lean_mass REAL, fat_mass REAL,
        fat_zone TEXT, fat_icon TEXT, bmr REAL, activity REAL,
        tdee REAL, steps INTEGER, goal TEXT DEFAULT 'maintain',
        kcal_target REAL, protein_g REAL, fat_g REAL, carb_g REAL,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now')))""")
    cur.execute("""CREATE TABLE IF NOT EXISTS food_global (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, name_ru TEXT,
        protein REAL DEFAULT 0, fat REAL DEFAULT 0,
        carb REAL DEFAULT 0, kcal REAL DEFAULT 0,
        per_grams REAL DEFAULT 100, added_by INTEGER,
        created_at TEXT DEFAULT (datetime('now')))""")
    cur.execute("""CREATE TABLE IF NOT EXISTS food_personal (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL, name TEXT NOT NULL,
        protein REAL DEFAULT 0, fat REAL DEFAULT 0,
        carb REAL DEFAULT 0, kcal REAL DEFAULT 0,
        per_grams REAL DEFAULT 100,
        created_at TEXT DEFAULT (datetime('now')))""")
    cur.execute("""CREATE TABLE IF NOT EXISTS food_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL, log_date TEXT NOT NULL,
        food_name TEXT NOT NULL, grams REAL NOT NULL,
        protein REAL DEFAULT 0, fat REAL DEFAULT 0,
        carb REAL DEFAULT 0, kcal REAL DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now')))""")
    cur.execute("SELECT COUNT(*) FROM food_global")
    if cur.fetchone()[0] == 0:
        foods = [
            ("Tovuq ko'krak","Куриная грудка",23.0,1.8,0.0,110,100),
            ("Tuxum","Яйцо",13.0,11.0,1.0,155,100),
            ("Guruch (pishirilgan)","Рис варёный",2.5,0.3,28.0,130,100),
            ("Tvorog 5%","Творог 5%",17.0,5.0,3.0,121,100),
            ("Non (bug'doy)","Хлеб пшеничный",7.5,2.5,48.0,242,100),
            ("Banan","Банан",1.1,0.3,22.0,96,100),
            ("Olma","Яблоко",0.3,0.2,13.0,52,100),
            ("Sut 2.5%","Молоко 2.5%",2.8,2.5,4.8,52,100),
            ("Grek yogurti","Греческий йогурт",6.0,2.0,4.5,59,100),
            ("Yulaf bo'tqasi","Овсянка",11.0,7.0,50.0,389,100),
            ("Losos","Лосось",20.0,13.0,0.0,208,100),
            ("Tvorog 0%","Творог 0%",18.0,0.0,3.0,88,100),
            ("Kartoshka","Картофель",2.0,0.1,17.0,77,100),
            ("Makaron","Макароны варёные",3.0,0.5,23.0,112,100),
            ("Pechak","Гречка варёная",3.5,0.6,17.0,90,100),
            ("Pishloq","Сыр",24.0,30.0,0.0,364,100),
            ("Tarvuz","Арбуз",0.6,0.1,7.5,30,100),
            ("Qo'ziqorin","Грибы шампиньоны",3.0,0.3,1.0,22,100),
            ("Ton baliq (konserva)","Тунец консервы",25.0,1.0,0.0,108,100),
            ("Mol go'shti","Говядина",26.0,8.0,0.0,187,100),
        ]
        for f in foods:
            cur.execute("INSERT INTO food_global (name,name_ru,protein,fat,carb,kcal,per_grams) VALUES (?,?,?,?,?,?,?)", f)
    c.commit()
    c.close()

def get_user(uid):
    c = conn(); cur = c.cursor()
    cur.execute("SELECT * FROM users WHERE user_id=?", (uid,))
    r = cur.fetchone(); c.close()
    return dict(r) if r else None

def upsert_user(uid, data):
    c = conn(); cur = c.cursor()
    keys = list(data.keys()); vals = list(data.values())
    ph = ",".join("?" for _ in keys)
    upd = ",".join(f"{k}=?" for k in keys)
    cur.execute(f"INSERT INTO users (user_id,{','.join(keys)}) VALUES (?,{ph}) ON CONFLICT(user_id) DO UPDATE SET {upd},updated_at=datetime('now')", [uid]+vals+vals)
    c.commit(); c.close()

def add_food_log(uid, data):
    c = conn(); cur = c.cursor()
    today = datetime.date.today().isoformat()
    cur.execute("INSERT INTO food_log (user_id,log_date,food_name,grams,protein,fat,carb,kcal) VALUES (?,?,?,?,?,?,?,?)",
        (uid,today,data["food_name"],data["grams"],data.get("protein",0),data.get("fat",0),data.get("carb",0),data.get("kcal",0)))
    c.commit(); c.close()

def delete_food_log(log_id, uid):
    c = conn(); cur = c.cursor()
    cur.execute("DELETE FROM food_log WHERE id=? AND user_id=?", (log_id,uid))
    c.commit(); c.close()

def get_today_log(uid):
    today = datetime.date.today().isoformat()
    c = conn(); cur = c.cursor()
    cur.execute("SELECT * FROM food_log WHERE user_id=? AND log_date=? ORDER BY created_at ASC", (uid,today))
    rows = cur.fetchall(); c.close()
    return [dict(r) for r in rows]

def get_today_totals(uid):
    rows = get_today_log(uid)
    return {
        "kcal": round(sum(r["kcal"] for r in rows),1),
        "protein": round(sum(r["protein"] for r in rows),1),
        "fat": round(sum(r["fat"] for r in rows),1),
        "carb": round(sum(r["carb"] for r in rows),1),
    }

def search_food(uid, query):
    c = conn(); cur = c.cursor()
    like = f"%{query}%"
    cur.execute("SELECT id,'global' as source,name,name_ru,protein,fat,carb,kcal,per_grams FROM food_global WHERE LOWER(name) LIKE LOWER(?) OR LOWER(COALESCE(name_ru,'')) LIKE LOWER(?) LIMIT 10", (like,like))
    g = [dict(r) for r in cur.fetchall()]
    cur.execute("SELECT id,'personal' as source,name,name as name_ru,protein,fat,carb,kcal,per_grams FROM food_personal WHERE user_id=? AND LOWER(name) LIKE LOWER(?) LIMIT 5", (uid,like))
    p = [dict(r) for r in cur.fetchall()]
    c.close()
    return p + g

def add_personal_food(uid, data):
    c = conn(); cur = c.cursor()
    cur.execute("INSERT INTO food_personal (user_id,name,protein,fat,carb,kcal,per_grams) VALUES (?,?,?,?,?,?,?)",
        (uid,data["name"],data.get("protein",0),data.get("fat",0),data.get("carb",0),data.get("kcal",0),data.get("per_grams",100)))
    c.commit(); c.close()

def get_personal_foods(uid):
    c = conn(); cur = c.cursor()
    cur.execute("SELECT * FROM food_personal WHERE user_id=? ORDER BY name", (uid,))
    rows = cur.fetchall(); c.close()
    return [dict(r) for r in rows]

def add_global_food(data, added_by):
    c = conn(); cur = c.cursor()
    cur.execute("INSERT INTO food_global (name,name_ru,protein,fat,carb,kcal,per_grams,added_by) VALUES (?,?,?,?,?,?,?,?)",
        (data["name"],data.get("name_ru",""),data.get("protein",0),data.get("fat",0),data.get("carb",0),data.get("kcal",0),data.get("per_grams",100),added_by))
    c.commit(); c.close()

def delete_global_food(food_id):
    c = conn(); cur = c.cursor()
    cur.execute("DELETE FROM food_global WHERE id=?", (food_id,))
    c.commit(); c.close()

def get_global_foods():
    c = conn(); cur = c.cursor()
    cur.execute("SELECT * FROM food_global ORDER BY name")
    rows = cur.fetchall(); c.close()
    return [dict(r) for r in rows]

def get_all_users():
    c = conn(); cur = c.cursor()
    cur.execute("SELECT user_id, lang, gender, age, weight, goal, kcal_target, fat_pct, created_at, updated_at FROM users ORDER BY created_at DESC")
    rows = cur.fetchall(); c.close()
    return [dict(r) for r in rows]
