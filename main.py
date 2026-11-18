import os
import time
import math
import logging
import threading
import telebot
from telebot import types
from flask import Flask
import psycopg2
from psycopg2.extras import RealDictCursor

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_ID = os.getenv("ADMIN_ID")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
states = {}

def db():
    return psycopg2.connect(DATABASE_URL, sslmode="require", cursor_factory=RealDictCursor)

def init_db():
    conn = db(); cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY, nickname TEXT)")
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS age INTEGER, ADD COLUMN IF NOT EXISTS gender TEXT, ADD COLUMN IF NOT EXISTS city TEXT, ADD COLUMN IF NOT EXISTS bio TEXT, ADD COLUMN IF NOT EXISTS lat DOUBLE PRECISION, ADD COLUMN IF NOT EXISTS lon DOUBLE PRECISION, ADD COLUMN IF NOT EXISTS stars INTEGER DEFAULT 6, ADD COLUMN IF NOT EXISTS is_vip BOOLEAN DEFAULT FALSE, ADD COLUMN IF NOT EXISTS profile_visible BOOLEAN DEFAULT TRUE, ADD COLUMN IF NOT EXISTS location_visible BOOLEAN DEFAULT TRUE, ADD COLUMN IF NOT EXISTS photo_id TEXT")
    cur.execute("CREATE TABLE IF NOT EXISTS likes (user_id BIGINT, target_id BIGINT, PRIMARY KEY (user_id, target_id))")
    cur.execute("CREATE TABLE IF NOT EXISTS passes (user_id BIGINT, target_id BIGINT, PRIMARY KEY (user_id, target_id))")
    cur.execute("CREATE TABLE IF NOT EXISTS matches (user1 BIGINT, user2 BIGINT, PRIMARY KEY (user1, user2))")
    cur.execute("CREATE TABLE IF NOT EXISTS blocks (user_id BIGINT, blocked_id BIGINT, PRIMARY KEY (user_id, blocked_id))")
    cur.execute("CREATE TABLE IF NOT EXISTS reports (id SERIAL PRIMARY KEY, reporter_id BIGINT, target_id BIGINT, reason TEXT)")
    cur.execute("CREATE TABLE IF NOT EXISTS chats (user1 BIGINT, user2 BIGINT, active BOOLEAN DEFAULT TRUE, PRIMARY KEY (user1, user2))")
    cur.execute("UPDATE users SET stars = 6 WHERE stars = 250")
    conn.commit(); cur.close(); conn.close()

def get_user(uid):
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE user_id=%s", (uid,))
    u = cur.fetchone(); cur.close(); conn.close()
    return u

def is_reg(uid):
    u = get_user(uid)
    return bool(u and u["nickname"])

def main_menu_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("🔍 جستجوی افراد", "❤️ مچ‌های من")
    kb.row("👤 پروفایل من", "⚙️ تنظیمات")
    kb.row("🪙 کیف پول", "🔗 دعوت دوستان")
    return kb

def profile_kb(tid):
    kb = types.InlineKeyboardMarkup()
    kb.row(types.InlineKeyboardButton("❤️ لایک", callback_data=f"like:{tid}"), types.InlineKeyboardButton("👎 رد", callback_data=f"pass:{tid}"))
    kb.row(types.InlineKeyboardButton("✉️ دایرکت (۱ سکه)", callback_data=f"dir:{tid}"), types.InlineKeyboardButton("💬 درخواست چت (۲ سکه)", callback_data=f"req:{tid}"))
    kb.row(types.InlineKeyboardButton("🚫 بلاک", callback_data=f"block:{tid}"), types.InlineKeyboardButton("⚠️ گزارش", callback_data=f"report:{tid}"))
    return kb

def settings_kb(uid):
    u = get_user(uid)
    pv = "✅" if u["profile_visible"] else "❌"
    lv = "✅" if u["location_visible"] else "❌"
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(f"{pv} نمایش پروفایل", callback_data="pv:profile"))
    kb.add(types.InlineKeyboardButton(f"{lv} نمایش موقعیت", callback_data="pv:location"))
    kb.add(types.InlineKeyboardButton("📸 تغییر عکس پروفایل", callback_data="photo:ask"))
    kb.add(types.InlineKeyboardButton("🗑 حذف حساب", callback_data="del:ask"))
    return kb

def finish_reg(uid, cid):
    d = states.pop(uid, None)
    conn = db(); cur = conn.cursor()
    cur.execute("INSERT INTO users (user_id, nickname, age, gender, city, bio, stars) VALUES (%s,%s,%s,%s,%s,%s,6) ON CONFLICT (user_id) DO UPDATE SET nickname=EXCLUDED.nickname, age=EXCLUDED.age, gender=EXCLUDED.gender, city=EXCLUDED.city, bio=EXCLUDED.bio", (uid, d["nickname"], d["age"], d["gender"], d["city"], d["bio"]))
    conn.commit(); cur.close(); conn.close()
    bot.send_message(cid, "🎉 ثبت‌نام کامل شد! ۶ سکه هدیه گرفتی.", reply_markup=main_menu_kb())

def show_profile(cid, uid, target_id=None):
    tid = target_id or uid
    u = get_user(tid)
    if not u: return
    vip = " 👑" if u.get("is_vip") else ""
    text = f"👤 {u['nickname']}{vip}\n🎂 {u['age']} ساله\n⚧ {u['gender']}\n📍 {u['city']}\n\n📝 {u['bio'] or 'بدون بیو'}\n⭐ {u['stars']}"
    kb = profile_kb(tid) if target_id else None
    if u.get("photo_id"): bot.send_photo(cid, u["photo_id"], caption=text, reply_markup=kb)
    else: bot.send_message(cid, text, reply_markup=kb)

def find(cid, uid):
    u = get_user(uid)
    if not u: return
    if u["lat"] is None:
        bot.send_message(cid, "اول موقعیت بفرست.", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add(types.KeyboardButton("📍 ارسال موقعیت", request_location=True)))
        return
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE user_id!=%s AND nickname IS NOT NULL AND profile_visible=TRUE AND lat IS NOT NULL AND user_id NOT IN (SELECT target_id FROM passes WHERE user_id=%s) AND user_id NOT IN (SELECT target_id FROM likes WHERE user_id=%s) AND user_id NOT IN (SELECT blocked_id FROM blocks WHERE user_id=%s)", (uid, uid, uid, uid))
    c = cur.fetchall(); cur.close(); conn.close()
    if not c: bot.send_message(cid, "کسی پیدا نشد."); return
    show_profile(cid, uid, target_id=c[0]["user_id"])

def like(uid, tid, cid):
    conn = db(); cur = conn.cursor(); m = False
    cur.execute("INSERT INTO likes (user_id, target_id) VALUES (%s,%s) ON CONFLICT DO NOTHING", (uid, tid))
    cur.execute("SELECT 1 FROM likes WHERE user_id=%s AND target_id=%s", (tid, uid))
    if cur.fetchone():
        a, b = sorted([uid, tid]); cur.execute("INSERT INTO matches (user1, user2) VALUES (%s,%s) ON CONFLICT DO NOTHING", (a, b)); m = True
    conn.commit(); cur.close(); conn.close()
    if m:
        bot.send_message(uid, "🎉 مچ شدین!")
        try: bot.send_message(tid, "🎉 مچ جدید!")
        except: pass
    else: bot.send_message(cid, "❤️ ثبت شد.")
    find(cid, uid)

def pass_user(uid, tid, cid):
    conn = db(); cur = conn.cursor()
    cur.execute("INSERT INTO passes (user_id, target_id) VALUES (%s,%s) ON CONFLICT DO NOTHING", (uid, tid))
    conn.commit(); cur.close(); conn.close()
    find(cid, uid)

def show_matches(cid, uid):
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT u.* FROM matches m JOIN users u ON u.user_id = CASE WHEN m.user1=%s THEN m.user2 ELSE m.user1 END WHERE m.user1=%s OR m.user2=%s", (uid, uid, uid))
    p = cur.fetchall(); cur.close(); conn.close()
    if not p: bot.send_message(cid, "مچی نداری ❤️"); return
    for x in p:
        kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("💬 چت", callback_data=f"chat:{x['user_id']}"))
        bot.send_message(cid, f"❤️ {x['nickname']}", reply_markup=kb)

def start_chat(uid, tid, cid):
    a, b = sorted([uid, tid])
    conn = db(); cur = conn.cursor()
    cur.execute("INSERT INTO chats (user1, user2, active) VALUES (%s,%s,TRUE) ON CONFLICT (user1,user2) DO UPDATE SET active=TRUE", (a, b))
    conn.commit(); cur.close(); conn.close()
    bot.send_message(uid, "💬 چت شروع شد. /stop برای پایان.")
    try: bot.send_message(tid, "💬 چت شروع شد. /stop برای پایان.")
    except: pass

def stop_chat(uid, cid):
    conn = db(); cur = conn.cursor()
    cur.execute("UPDATE chats SET active=FALSE WHERE (user1=%s OR user2=%s) AND active=TRUE RETURNING user1,user2", (uid, uid))
    s = cur.fetchall(); conn.commit(); cur.close(); conn.close()
    if not s: bot.send_message(cid, "چت فعالی نداری."); return
    bot.send_message(cid, "چت بسته شد.")
    for x in s:
        o = x["user2"] if x["user1"] == uid else x["user1"]
        try: bot.send_message(o, "چت بسته شد.")
        except: pass

def relay(msg):
    uid = msg.from_user.id
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT user1,user2 FROM chats WHERE active=TRUE AND (user1=%s OR user2=%s) LIMIT 1", (uid, uid))
    s = cur.fetchone(); cur.close(); conn.close()
    if not s: return False
    o = s["user2"] if s["user1"] == uid else s["user1"]
    try: bot.copy_message(o, msg.chat.id, msg.message_id)
    except: bot.send_message(msg.chat.id, "ارسال نشد.")
    return True

def block(uid, tid, cid):
    conn = db(); cur = conn.cursor()
    cur.execute("INSERT INTO blocks (user_id, blocked_id) VALUES (%s,%s) ON CONFLICT DO NOTHING", (uid, tid))
    a, b = sorted([uid, tid]); cur.execute("UPDATE chats SET active=FALSE WHERE user1=%s AND user2=%s", (a, b))
    conn.commit(); cur.close(); conn.close()
    bot.send_message(cid, "🚫 بلاک شد.")

def toggle_pv(uid, cid, field, mid):
    conn = db(); cur = conn.cursor()
    cur.execute(f"SELECT {field} FROM users WHERE user_id=%s", (uid,))
    r = cur.fetchone()
    if r:
        nv = not bool(r[field]); cur.execute(f"UPDATE users SET {field}=%s WHERE user_id=%s", (nv, uid)); conn.commit()
        bot.edit_message_reply_markup(cid, mid, reply_markup=settings_kb(uid))
    cur.close(); conn.close()

def del_account(uid, cid):
    conn = db(); cur = conn.cursor()
    for t, a, b in [("likes","user_id","target_id"),("passes","user_id","target_id"),("matches","user1","user2"),("blocks","user_id","blocked_id"),("chats","user1","user2")]:
        cur.execute(f"DELETE FROM {t} WHERE {a}=%s OR {b}=%s", (uid, uid))
    cur.execute("DELETE FROM reports WHERE reporter_id=%s OR target_id=%s", (uid, uid))
    cur.execute("DELETE FROM users WHERE user_id=%s", (uid,))
    conn.commit(); cur.close(); conn.close()
    states.pop(uid, None); bot.send_message(cid, "حساب حذف شد.", reply_markup=types.ReplyKeyboardRemove())

def invite(cid, uid):
    try:
        me = bot.get_me(); bot.send_message(cid, f"🔗 لینک دعوت:\nhttps://t.me/{me.username}?start=ref_{uid}\n\nهر ثبت‌نام ۱۰ ستاره.")
    except: bot.send_message(cid, "خطا.")

def process_req(uid, tid, cid, rtype):
    cost = 1 if rtype == "direct" else 2
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT stars FROM users WHERE user_id=%s", (uid,))
    r = cur.fetchone()
    if not r or r["stars"] < cost:
        bot.send_message(cid, f"❌ سکه کافی نداری. نیاز به {cost} سکه.")
        cur.close(); conn.close(); return
    cur.execute("UPDATE users SET stars = stars - %s WHERE user_id=%s", (cost, uid))
    conn.commit(); cur.close(); conn.close()
    states[uid] = {"step": f"{rtype}_msg", "tid": tid}
    bot.send_message(cid, f"هزینه {cost} سکه کسر شد. پیامت رو بنویس:")

def send_req(uid, tid, cid, text, rtype):
    kb = types.InlineKeyboardMarkup().row(types.InlineKeyboardButton("✅ تایید", callback_data=f"appr:{uid}"), types.InlineKeyboardButton("❌ رد", callback_data=f"rej:{uid}"))
    if rtype == "direct": bot.send_message(tid, f"📩 دایرکت از {uid}:\n\n{text}", reply_markup=kb)
    else: bot.send_message(tid, f"💬 درخواست چت از {uid}:\n\n{text}", reply_markup=kb)
    bot.send_message(cid, "ارسال شد. منتظر تایید باشید.")

@bot.message_handler(commands=["start"])
def c_start(m):
    uid = m.from_user.id
    if is_reg(uid):
        bot.send_message(m.chat.id, "خوش برگشتی ❤️", reply_markup=main_menu_kb()); return
    states[uid] = {"step": "nickname"}; bot.send_message(m.chat.id, "اسم نمایشی‌ت چیه؟")

@bot.message_handler(commands=["stop"])
def c_stop(m):
    stop_chat(m.from_user.id, m.chat.id)

@bot.message_handler(content_types=["location"])
def c_loc(m):
    uid = m.from_user.id
    if not is_reg(uid): return
    conn = db(); cur = conn.cursor()
    cur.execute("UPDATE users SET lat=%s, lon=%s WHERE user_id=%s", (m.location.latitude, m.location.longitude, uid))
    conn.commit(); cur.close(); conn.close()
    bot.send_message(m.chat.id, "📍 ثبت شد.", reply_markup=main_menu_kb()); find(m.chat.id, uid)

@bot.message_handler(content_types=["photo"])
def c_photo(m):
    uid = m.from_user.id; s = states.get(uid)
    if s and s.get("step") == "photo":
        conn = db(); cur = conn.cursor()
        cur.execute("UPDATE users SET photo_id=%s WHERE user_id=%s", (m.photo[-1].file_id, uid))
        conn.commit(); cur.close(); conn.close()
        states.pop(uid, None); bot.send_message(m.chat.id, "✅ ذخیره شد.", reply_markup=main_menu_kb())

@bot.message_handler(content_types=["text"])
def c_text(m):
    uid = m.from_user.id; t = (m.text or "").strip(); s = states.get(uid)
    
    if not is_reg(uid) and not s:
        bot.send_message(m.chat.id, "سلام! برای شروع /start رو بزن.")
        return
        
    if s:
        st = s["step"]
        if st == "nickname": s["nickname"] = t[:50]; s["step"] = "age"; bot.send_message(m.chat.id, "سن (۱۸+):"); return
        if st == "age":
            try: a = int(t)
            except: return
            if a < 18: return
            s["age"] = a; s["step"] = "gender"
            kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True).row("پسر","دختر")
            bot.send_message(m.chat.id, "جنسیت؟", reply_markup=kb); return
        if st == "gender": s["gender"] = t; s["step"] = "city"; bot.send_message(m.chat.id, "شهر؟", reply_markup=types.ReplyKeyboardRemove()); return
        if st == "city": s["city"] = t[:50]; s["step"] = "bio"; bot.send_message(m.chat.id, "بیو:"); return
        if st == "bio": s["bio"] = t[:300]; finish_reg(uid, m.chat.id); return
        if st == "direct_msg": tid = s.get("tid"); states.pop(uid, None); send_req(uid, tid, m.chat.id, t, "direct"); return
        if st == "req_msg": tid = s.get("tid"); states.pop(uid, None); send_req(uid, tid, m.chat.id, t, "chat"); return
    
    if relay(m): return
    
    if t == "🔍 جستجوی افراد": find(m.chat.id, uid)
    elif t == "❤️ مچ‌های من": show_matches(m.chat.id, uid)
    elif t == "👤 پروفایل من": show_profile(m.chat.id, uid)
    elif t == "⚙️ تنظیمات": bot.send_message(m.chat.id, "⚙️ تنظیمات:", reply_markup=settings_kb(uid))
    elif t == "🪙 کیف پول":
        kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("➕ ۱۰۰ سکه", callback_data="buy:100"))
        bot.send_message(m.chat.id, f"🪙 موجودی: {get_user(uid)['stars']}", reply_markup=kb)
    elif t == "🔗 دعوت دوستان": invite(m.chat.id, uid)
    else: bot.send_message(m.chat.id, "متوجه نشدم! از منو استفاده کن.", reply_markup=main_menu_kb())

@bot.callback_query_handler(func=lambda c: True)
def c_cb(c):
    d = c.data or ""; uid = c.from_user.id; cid = c.message.chat.id if c.message else uid; mid = c.message.message_id if c.message else None
    try:
        if d.startswith("like:"): like(uid, int(d.split(":")[1]), cid)
        elif d.startswith("pass:"): pass_user(uid, int(d.split(":")[1]), cid)
        elif d.startswith("block:"): block(uid, int(d.split(":")[1]), cid)
        elif d.startswith("chat:"): start_chat(uid, int(d.split(":")[1]), cid)
        elif d.startswith("dir:"): process_req(uid, int(d.split(":")[1]), cid, "direct")
        elif d.startswith("req:"): process_req(uid, int(d.split(":")[1]), cid, "chat")
        elif d.startswith("appr:"):
            start_chat(uid, int(d.split(":")[1]), cid)
            bot.edit_message_text("✅ تایید شد.", chat_id=cid, message_id=mid)
        elif d.startswith("rej:"): bot.edit_message_text("❌ رد شد.", chat_id=cid, message_id=mid)
        elif d == "buy:100":
            conn = db(); cur = conn.cursor(); cur.execute("UPDATE users SET stars = stars + 100 WHERE user_id=%s", (uid,)); conn.commit(); cur.close(); conn.close()
            bot.answer_callback_query(c.id, "۱۰۰ سکه اضافه شد!")
        elif d == "pv:profile": toggle_pv(uid, cid, "profile_visible", mid)
        elif d == "pv:location": toggle_pv(uid, cid, "location_visible", mid)
        elif d == "photo:ask": states[uid] = {"step": "photo"}; bot.send_message(cid, "📸 عکس بفرست:")
        elif d == "del:ask":
            kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("✅ بله", callback_data="del:yes"))
            bot.edit_message_text("مطمئنی؟", chat_id=cid, message_id=mid, reply_markup=kb)
        elif d == "del:yes": del_account(uid, cid)
        bot.answer_callback_query(c.id)
    except: pass

@app.route("/")
def health(): return "OK", 200

def run():
    init_db()
    try: bot.delete_webhook(drop_pending_updates=True)
    except: pass
    while True:
        try: bot.infinity_polling(timeout=30, long_polling_timeout=25)
        except: time.sleep(5)

if __name__ == "__main__":
    threading.Thread(target=run, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))