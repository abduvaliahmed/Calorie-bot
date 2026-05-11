import os, datetime
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import pool

DATABASE_URL = os.environ.get("DATABASE_URL", "")

_pool = None

def get_pool():
    global _pool
    if _pool is None:
        url = DATABASE_URL
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        _pool = pool.SimpleConnectionPool(1, 10, url, cursor_factory=RealDictCursor)
    return _pool

def conn():
    return get_pool().getconn()

def release(c):
    get_pool().putconn(c)

def init_db():
    c = conn(); cur = c.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id BIGINT PRIMARY KEY, lang TEXT DEFAULT 'uz',
        gender TEXT, age INTEGER, weight REAL, height REAL,
        waist REAL, neck REAL, hip REAL DEFAULT 0,
        fat_pct REAL, lean_mass REAL, fat_mass REAL,
        fat_zone TEXT, fat_icon TEXT, bmr REAL, activity REAL,
        tdee REAL, steps INTEGER, goal TEXT DEFAULT 'maintain',
        kcal_target REAL, protein_g REAL, fat_g REAL, carb_g REAL,
        first_name TEXT DEFAULT '',
        username TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW())""")
    cur.execute("""CREATE TABLE IF NOT EXISTS food_global (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL, name_ru TEXT,
        protein REAL DEFAULT 0, fat REAL DEFAULT 0,
        carb REAL DEFAULT 0, kcal REAL DEFAULT 0,
        per_grams REAL DEFAULT 100, added_by BIGINT,
        created_at TIMESTAMP DEFAULT NOW())""")
    cur.execute("""CREATE TABLE IF NOT EXISTS food_personal (
        id SERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL, name TEXT NOT NULL,
        protein REAL DEFAULT 0, fat REAL DEFAULT 0,
        carb REAL DEFAULT 0, kcal REAL DEFAULT 0,
        per_grams REAL DEFAULT 100,
        created_at TIMESTAMP DEFAULT NOW())""")
    cur.execute("""CREATE TABLE IF NOT EXISTS food_log (
        id SERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL, log_date DATE NOT NULL,
        food_name TEXT NOT NULL, grams REAL NOT NULL,
        protein REAL DEFAULT 0, fat REAL DEFAULT 0,
        carb REAL DEFAULT 0, kcal REAL DEFAULT 0,
        created_at TIMESTAMP DEFAULT NOW())""")
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS first_name TEXT DEFAULT ''")
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS username TEXT DEFAULT ''")
    cur.execute("ALTER TABLE food_global ADD COLUMN IF NOT EXISTS source TEXT DEFAULT ''")
    cur.execute("ALTER TABLE food_global ADD COLUMN IF NOT EXISTS store TEXT DEFAULT ''")
    cur.execute("ALTER TABLE food_global ADD COLUMN IF NOT EXISTS category TEXT DEFAULT ''")
    # Eski xato 'cached' entry'larni o'chirish (AI tomonidan noto'g'ri keshlangan)
    cur.execute("DELETE FROM food_global WHERE store='cached'")
    # Korzinka × USDA seed — yangi mahsulotlarni qo'shamiz (mavjudini tegmaymiz)
    import json as _json
    seed_path = os.path.join(os.path.dirname(__file__), "seed_korzinka.json")
    if os.path.exists(seed_path):
        with open(seed_path, encoding="utf-8") as _f:
            seed = _json.load(_f)
        cur.execute("SELECT LOWER(name) FROM food_global WHERE store='korzinka'")
        existing = {row[0] if isinstance(row, tuple) else row["lower"] for row in cur.fetchall()}
        added = 0
        for s in seed:
            if s["name"].lower() in existing:
                continue
            cur.execute(
                "INSERT INTO food_global (name,name_ru,kcal,protein,fat,carb,per_grams,source,store,category) "
                "VALUES (%s,%s,%s,%s,%s,%s,100,'USDA','korzinka',%s)",
                (s["name"], s["name_ru"], s["kcal"], s["protein"], s["fat"], s["carb"], s.get("category",""))
            )
            added += 1
        if added:
            import logging as _log
            _log.getLogger(__name__).info(f"Korzinka seed: +{added} mahsulot")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_food_log_user_date ON food_log(user_id, log_date)")
    cur.execute("DELETE FROM food_personal WHERE id NOT IN (SELECT MIN(id) FROM food_personal GROUP BY user_id, name)")
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_food_personal_user_name ON food_personal(user_id, name)")
    cur.execute("SELECT COUNT(*) as cnt FROM food_global")
    row = cur.fetchone()
    if row["cnt"] == 0:
        foods = [
            ("Tovuq kokrak","Kurinaya grudka",23.0,1.8,0.0,110,100),
            ("Tuxum","Yayco",13.0,11.0,1.0,155,100),
            ("Guruch pishirilgan","Ris varenyy",2.5,0.3,28.0,130,100),
            ("Tvorog 5%","Tvorog 5%",17.0,5.0,3.0,121,100),
            ("Non bugdoy","Xleb pshenichniy",7.5,2.5,48.0,242,100),
            ("Banan","Banan",1.1,0.3,22.0,96,100),
            ("Olma","Yabloko",0.3,0.2,13.0,52,100),
            ("Sut 2.5%","Moloko 2.5%",2.8,2.5,4.7,52,100),
            ("Grek yogurti","Grecheskiy yogurt",6.0,2.0,4.5,59,100),
            ("Yulaf botqasi","Ovsyanka",11.0,7.0,50.0,389,100),
            ("Losos","Losos",20.0,13.0,0.0,208,100),
            ("Tvorog 0%","Tvorog 0%",18.0,0.0,3.0,88,100),
            ("Kartoshka","Kartofel",2.0,0.1,17.0,77,100),
            ("Makaron","Makaroni varenie",3.0,0.5,23.0,112,100),
            ("Grechka","Grechka varenaya",3.5,0.6,17.0,90,100),
            ("Pishloq","Sir",24.0,30.0,0.0,364,100),
            ("Tarvuz","Arbuz",0.6,0.1,7.5,30,100),
            ("Qoziqorin","Gribi",3.0,0.3,1.0,22,100),
            ("Ton baliq","Tunec konservi",25.0,1.0,0.0,108,100),
            ("Mol goshti","Govyadina",26.0,8.0,0.0,187,100),
        ]
        for f in foods:
            cur.execute(
                "INSERT INTO food_global (name,name_ru,protein,fat,carb,kcal,per_grams) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                f
            )
    c.commit(); release(c)
    import logging
    logging.getLogger(__name__).info("DB initialized (PostgreSQL)")

def get_user(uid):
    c = conn(); cur = c.cursor()
    cur.execute("SELECT * FROM users WHERE user_id=%s", (uid,))
    r = cur.fetchone(); release(c)
    return dict(r) if r else None

def upsert_user(uid, data):
    c = conn(); cur = c.cursor()
    keys = list(data.keys())
    vals = list(data.values())
    cols = ",".join(keys)
    phs = ",".join(["%s"]*len(keys))
    upd = ",".join(f"{k}=%s" for k in keys)
    cur.execute(
        f"INSERT INTO users (user_id,{cols}) VALUES (%s,{phs}) ON CONFLICT(user_id) DO UPDATE SET {upd},updated_at=NOW()",
        [uid]+vals+vals
    )
    c.commit(); release(c)

def add_food_log(uid, data):
    c = conn(); cur = c.cursor()
    today = datetime.date.today()
    cur.execute(
        "INSERT INTO food_log (user_id,log_date,food_name,grams,protein,fat,carb,kcal) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        (uid,today,data["food_name"],data["grams"],data.get("protein",0),data.get("fat",0),data.get("carb",0),data.get("kcal",0))
    )
    c.commit(); release(c)

def delete_food_log(log_id, uid):
    c = conn(); cur = c.cursor()
    cur.execute("DELETE FROM food_log WHERE id=%s AND user_id=%s", (log_id, uid))
    c.commit(); release(c)

def get_today_log(uid):
    today = datetime.date.today()
    c = conn(); cur = c.cursor()
    cur.execute("SELECT * FROM food_log WHERE user_id=%s AND log_date=%s ORDER BY created_at ASC", (uid, today))
    rows = cur.fetchall(); release(c)
    return [dict(r) for r in rows]

def get_today_totals(uid):
    rows = get_today_log(uid)
    return {
        "kcal": round(sum(r["kcal"] for r in rows), 1),
        "protein": round(sum(r["protein"] for r in rows), 1),
        "fat": round(sum(r["fat"] for r in rows), 1),
        "carb": round(sum(r["carb"] for r in rows), 1),
    }

def search_food(uid, query, limit=20, offset=0):
    c = conn(); cur = c.cursor()
    like = f"%{query}%"
    cur.execute(
        "SELECT id,'personal' as source,name,name as name_ru,protein,fat,carb,kcal,per_grams FROM food_personal WHERE user_id=%s AND LOWER(name) LIKE LOWER(%s) LIMIT 5",
        (uid, like)
    )
    p = [dict(r) for r in cur.fetchall()]
    cur.execute(
        "SELECT id,'global' as source,name,name_ru,protein,fat,carb,kcal,per_grams,"
        "COALESCE(source,'') as data_source,COALESCE(store,'') as store,COALESCE(category,'') as category "
        "FROM food_global WHERE LOWER(name) LIKE LOWER(%s) OR LOWER(COALESCE(name_ru,'')) LIKE LOWER(%s) "
        "ORDER BY name LIMIT %s OFFSET %s",
        (like, like, limit, offset)
    )
    g = [dict(r) for r in cur.fetchall()]
    release(c)
    return p + g

def add_personal_food(uid, data):
    c = conn(); cur = c.cursor()
    cur.execute(
        "INSERT INTO food_personal (user_id,name,protein,fat,carb,kcal,per_grams) VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
        (uid,data["name"],data.get("protein",0),data.get("fat",0),data.get("carb",0),data.get("kcal",0),data.get("per_grams",100))
    )
    c.commit(); release(c)

def get_personal_foods(uid):
    c = conn(); cur = c.cursor()
    cur.execute("SELECT * FROM food_personal WHERE user_id=%s ORDER BY name", (uid,))
    rows = cur.fetchall(); release(c)
    return [dict(r) for r in rows]

def add_global_food(data, added_by):
    c = conn(); cur = c.cursor()
    cur.execute(
        "INSERT INTO food_global (name,name_ru,protein,fat,carb,kcal,per_grams,added_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        (data["name"],data.get("name_ru",""),data.get("protein",0),data.get("fat",0),data.get("carb",0),data.get("kcal",0),data.get("per_grams",100),added_by)
    )
    c.commit(); release(c)

def delete_global_food(food_id):
    c = conn(); cur = c.cursor()
    cur.execute("DELETE FROM food_global WHERE id=%s", (food_id,))
    c.commit(); release(c)

def get_global_foods():
    c = conn(); cur = c.cursor()
    cur.execute("SELECT * FROM food_global ORDER BY name")
    rows = cur.fetchall(); release(c)
    return [dict(r) for r in rows]

def get_all_users():
    c = conn(); cur = c.cursor()
    # Add last_seen column if not exists
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_seen TIMESTAMP")
    c.commit()
    cur.execute("SELECT user_id,first_name,username,lang,gender,age,weight,goal,kcal_target,fat_pct,is_blocked,created_at,updated_at,last_seen FROM users ORDER BY last_seen DESC NULLS LAST")
    rows = cur.fetchall(); release(c)
    return [dict(r) for r in rows]

def save_bot_user(uid, first_name, username):
    c = conn(); cur = c.cursor()
    cur.execute(
        """INSERT INTO users (user_id, first_name, username)
           VALUES (%s, %s, %s)
           ON CONFLICT(user_id) DO UPDATE SET first_name=%s, username=%s""",
        (uid, first_name, username, first_name, username)
    )
    c.commit(); release(c)

def edit_global_food(food_id, data):
    c = conn(); cur = c.cursor()
    cur.execute(
        "UPDATE food_global SET name=%s, name_ru=%s, kcal=%s, protein=%s, fat=%s, carb=%s WHERE id=%s",
        (data["name"], data.get("name_ru",""), data.get("kcal",0), data.get("protein",0), data.get("fat",0), data.get("carb",0), food_id)
    )
    c.commit(); release(c)

def get_users_needing_profile_update():
    c = conn(); cur = c.cursor()
    two_weeks_ago = datetime.datetime.now() - datetime.timedelta(days=14)
    cur.execute(
        "SELECT user_id, first_name FROM users WHERE updated_at < %s AND gender IS NOT NULL AND weight IS NOT NULL AND COALESCE(is_blocked, false) = false",
        (two_weeks_ago,)
    )
    rows = cur.fetchall(); release(c)
    return [dict(r) for r in rows]

def get_streak(uid):
    c = conn(); cur = c.cursor()
    cur.execute(
        "SELECT DISTINCT log_date FROM food_log WHERE user_id=%s ORDER BY log_date DESC",
        (uid,)
    )
    rows = cur.fetchall(); release(c)
    if not rows:
        return 0
    today = datetime.date.today()
    yesterday = today - datetime.timedelta(days=1)
    dates = [row["log_date"] for row in rows]
    if dates[0] not in (today, yesterday):
        return 0
    streak = 0
    expected = dates[0]
    for d in dates:
        if d == expected:
            streak += 1
            expected = expected - datetime.timedelta(days=1)
        else:
            break
    return streak
