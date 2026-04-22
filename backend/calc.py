import math

STEPS = [(3000,1.20),(5000,1.30),(7000,1.35),(10000,1.40),(13000,1.45),(15000,1.50),(17000,1.55),(20000,1.60),(23000,1.65),(27000,1.70)]
FAT_M = [(6,"Atletik min","⚡"),(13,"Atletik","💪"),(17,"Fit","✅"),(20,"Norma","👍"),(25,"Yuqori norma","⚠️"),(100,"Semizlik","🔴")]
FAT_F = [(14,"Atletik min","⚡"),(21,"Atletik","💪"),(25,"Fit","✅"),(32,"Norma","👍"),(38,"Yuqori norma","⚠️"),(100,"Semizlik","🔴")]
MP = {"lose":2.3,"maintain":1.8,"muscle":1.8}
MF = {"lose":0.7,"maintain":0.9,"muscle":1.2}

def get_activity(steps):
    for thr, coeff in STEPS:
        if steps < thr: return coeff
    return 1.70

def fat_pct(gender, waist, neck, height, hip=0):
    if gender == "male":
        v = 495/(1.0324 - 0.19077*math.log10(waist-neck) + 0.15456*math.log10(height)) - 450
    else:
        v = 495/(1.29579 - 0.35004*math.log10(waist+hip-neck) + 0.22100*math.log10(height)) - 450
    return round(max(3.0, min(60.0, v)), 1)

def fat_zone(gender, fp):
    zones = FAT_M if gender == "male" else FAT_F
    for limit, name, icon in zones:
        if fp <= limit: return name, icon
    return "Semizlik", "🔴"

def calc_macros(weight, kcal, goal):
    p = round(weight * MP.get(goal,1.8), 1)
    f = round(weight * MF.get(goal,0.9), 1)
    c = round(max(0,(kcal - p*4 - f*9)/4), 1)
    return {"protein_g":p,"fat_g":f,"carb_g":c}

def full_calc(data):
    gender = data["gender"]
    weight = float(data["weight"])
    height = float(data["height"])
    waist = float(data["waist"])
    neck = float(data["neck"])
    hip = float(data.get("hip") or 0)
    steps = int(data["steps"])
    goal = data.get("goal","maintain")

    fp = fat_pct(gender, waist, neck, height, hip)
    lean = round(weight*(1-fp/100), 1)
    fat_m = round(weight - lean, 1)
    bmr = round(370 + 21.6*lean, 1)
    act = get_activity(steps)
    tdee = round(bmr*act, 1)

    custom = float(data.get("kcal_target") or 0)
    if custom > 0:
        kcal_t = custom
    elif goal == "lose":
        kcal_t = round(tdee*0.85)
    elif goal == "muscle":
        kcal_t = round(tdee*1.10)
    else:
        kcal_t = round(tdee)

    zone, icon = fat_zone(gender, fp)
    return {
        "fat_pct":fp,"lean_mass":lean,"fat_mass":fat_m,
        "fat_zone":zone,"fat_icon":icon,
        "bmr":bmr,"activity":act,"tdee":tdee,"kcal_target":kcal_t,
    }
