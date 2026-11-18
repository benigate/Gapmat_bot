import os
import math
import time
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

if not BOT_TOKEN: raise RuntimeError("BOT_TOKEN missing")
if not DATABASE_URL: raise RuntimeError("DATABASE_URL missing")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
states = {}

def db(): return psycopg2.connect(DATABASE_URL, sslmode="require", cursor_factory=RealDictCursor)

def init_db():
    conn = db(); cur = conn.cursor()
    try:
        cur.execute("CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY, nickname TEXT, age INTEGER, gender TEXT, city TEXT, bio TEXT, lat DOUBLE PRECISION, lon DOUBLE PRECISION, stars INTEGER DEFAULT 6, is_vip BOOLEAN DEFAULT FALSE, profile_visible BOOLEAN DEFAULT TRUE, location_visible BOOLEAN DEFAULT TRUE, photo_id TEXT)")
        cur.execute("CREATE TABLE IF NOT EXISTS likes (user_id BIGINT, target_id BIGINT, PRIMARY KEY (user_id, target_id))")
        cur.execute("CREATE TABLE IF NOT EXISTS passes (user_id BIGINT, target_id BIGINT, PRIMARY KEY (user_id, target_id))")
        cur.execute("CREATE TABLE IF NOT EXISTS blocks (user_id BIGINT, blocked_id BIGINT, PRIMARY KEY (user_id, blocked_id))")
        cur.execute("CREATE TABLE IF NOT EXISTS reports (id SERIAL PRIMARY KEY, reporter_id BIGINT, target_id BIGINT, reason TEXT)")
        cur.execute("CREATE TABLE IF NOT EXISTS chats (user1 BIGINT, user2 BIGINT, active BOOLEAN DEFAULT TRUE, PRIMARY KEY (user1, user2))")
        cur.execute("CREATE TABLE IF NOT EXISTS contacts (user_id BIGINT, contact_id BIGINT, PRIMARY KEY (user_id, contact_id))")
        cur.execute("CREATE TABLE IF NOT EXISTS direct_requests (id SERIAL PRIMARY KEY, sender_id BIGINT, receiver_id BIGINT, message TEXT, status TEXT DEFAULT 'pending')")
        cur.execute("UPDATE users SET stars = 6 WHERE stars = 250")
        conn.commit()
    except: conn.rollback()
    finally: cur.close(); conn.close()

def get_user(uid):
    conn = db(); cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM users WHERE user_id=%s", (uid,))
        return cur.fetchone()
    finally: cur.close(); conn.close()

def is_reg(uid):
    u = get_user(uid)
    return bool(u and u["nickname"])

def dist(a,b,c,d):
    R=6371; dl=math.radians(c-a); dn=math.radians(d-b)
    x=math.sin(dl/2)**2+math.cos(math.radians(a))*math.cos(math.radians(c))*math.sin(dn/2)**2
    return R*2*math.atan2(math.sqrt(x),math.sqrt(1-x))

def main_menu_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("🔍 جستجوی افراد", "👥 مخاطبین من")
    kb.row("👤 پروفایل من", "⚙️ تنظیمات")
    kb.row("🪙 کیف پول", "🔗 دعوت دوستان")
    return kb

def profile_kb(tid):
    kb = types.InlineKeyboardMarkup()
    kb.row(types.InlineKeyboardButton("❤️ لایک", callback_data=f"like:{tid}"), types.InlineKeyboardButton("👎 رد", callback_data=f"pass:{tid}"))
    kb.row(types.InlineKeyboardButton("✉️ دایرکت (۱ سکه)", callback_data=f"dir:{tid}"), types.InlineKeyboardButton("💬 درخواست چت (۲ سکه)", callback_data=f"req:{tid}"))
    kb.row(types.InlineKeyboardButton("➕ افزودن به مخاطبین", callback_data=f"add:{tid}"))
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

def wallet_kb():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🎁 معرفی به دوستان (سکه رایگان)", callback_data="wallet:invite"))
    kb.add(types.InlineKeyboardButton("💳 خرید با تومان", callback_data="wallet:buy_toman"))
    kb.add(types.InlineKeyboardButton("💫 پرداخت با ستاره تلگرام", callback_data="wallet:buy_stars"))
    kb.add(types.InlineKeyboardButton("👑 خرید VIP", callback_data="wallet:vip"))
    return kb

def finish_reg(uid, cid):
    d = states.pop(uid, None)
    conn = db(); cur = conn.cursor()
    try:
        cur.execute("INSERT INTO users (user_id, nickname, age, gender, city, bio, stars) VALUES (%s,%s,%s,%s,%s,%s,6) ON CONFLICT (user_id) DO UPDATE SET nickname=EXCLUDED.nickname, age=EXCLUDED.age, gender=EXCLUDED.gender, city=EXCLUDED.city, bio=EXCLUDED.bio", (uid, d["nickname"], d["age"], d["gender"], d["city"], d["bio"]))
        conn.commit()
    finally: cur.close(); conn.close()
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
    try:
        cur.execute("SELECT * FROM users WHERE user_id!=%s AND nickname IS NOT NULL AND profile_visible=TRUE AND lat IS NOT NULL AND user_id NOT IN (SELECT target_id FROM passes WHERE user_id=%s) AND user_id NOT IN (SELECT target_id FROM likes WHERE user_id=%s) AND user_id NOT IN (SELECT blocked_id FROM blocks WHERE user_id=%s)", (uid, uid, uid, uid))
        c = cur.fetchall()
    finally: cur.close(); conn.close()
    if not c: bot.send_message(cid, "کسی پیدا نشد."); return
    c.sort(key=lambda x: dist(u["lat"], u["lon"], x["lat"], x["lon"]))
    show_profile(cid, uid, target_id=c[0]["user_id"])

def like(uid, tid, cid):
    if uid == tid: return
    conn = db(); cur = conn.cursor()
    try:
        cur.execute("INSERT INTO likes (user_id, target_id) VALUES (%s,%s) ON CONFLICT DO NOTHING", (uid, tid))
        conn.commit()
        try: bot.send_message(tid, f"❤️ یک نفر پروفایل شما را پسندید!\nآیدی: `{uid}`", parse_mode="Markdown")
        except: pass
    except: conn.rollback()
    finally: cur.close(); conn.close()
    bot.send_message(cid, "❤️ لایک ثبت شد.")
    find(cid, uid)

def pass_user(uid, tid, cid):
    conn = db(); cur = conn.cursor()
    try: cur.execute("INSERT INTO passes (user_id, target_id) VALUES (%s,%s) ON CONFLICT DO NOTHING", (uid, tid)); conn.commit()
    finally: cur.close(); conn.close()
    find(cid, uid)

def show_contacts(cid, uid):
    conn = db(); cur = conn.cursor()
    try:
        cur.execute("SELECT u.* FROM contacts c JOIN users u ON u.user_id = c.contact_id WHERE c.user_id = %s", (uid,))
        p = cur.fetchall()
    finally: cur.close(); conn.close()
    if not p: bot.send_message(cid, "لیست مخاطبین خالی است."); return
    for x in p:
        kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("👤 مشاهده پروفایل", callback_data=f"view:{x['user_id']}"))
        bot.send_message(cid, f"👥 {x['nickname']}", reply_markup=kb)

def add_contact(uid, tid, cid):
    conn = db(); cur = conn.cursor()
    try:
        cur.execute("INSERT INTO contacts (user_id, contact_id) VALUES (%s,%s) ON CONFLICT DO NOTHING", (uid, tid))
        conn.commit(); bot.send_message(cid, "✅ به مخاطبین اضافه شد.")
    finally: cur.close(); conn.close()

def start_chat(uid, tid, cid):
    a, b = sorted([uid, tid])
    conn = db(); cur = conn.cursor()
    try:
        cur.execute("INSERT INTO chats (user1, user2, active) VALUES (%s,%s,TRUE) ON CONFLICT (user1,user2) DO UPDATE SET active=TRUE", (a, b))
        conn.commit()
    finally: cur.close(); conn.close()
    bot.send_message(uid, "💬 چت شروع شد. /stop برای پایان.")
    try: bot.send_message(tid, "💬 چت شروع شد. /stop برای پایان.")
    except: pass

def stop_chat(uid, cid):
    conn = db(); cur = conn.cursor()
    try:
        cur.execute("UPDATE chats SET active=FALSE WHERE (user1=%s OR user2=%s) AND active=TRUE", (uid, uid))
        conn.commit()
        bot.send_message(cid, "چت بسته شد.")
    finally: cur.close(); conn.close()

def relay(msg):
    uid = msg.from_user.id
    conn = db(); cur = conn.cursor()
    try:
        cur.execute("SELECT user1,user2 FROM chats WHERE active=TRUE AND (user1=%s OR user2=%s) LIMIT 1", (uid, uid))
        s = cur.fetchone()
    finally: cur.close(); conn.close()
    if not s: return False
    o = s["user2"] if s["user1"] == uid else s["user1"]
    try: bot.copy_message(o, msg.chat.id, msg.message_id)
    except: bot.send_message(msg.chat.id, "ارسال نشد.")
    return True

def block(uid, tid, cid):
    conn = db(); cur = conn.cursor()
    try:
        cur.execute("INSERT INTO blocks (user_id, blocked_id) VALUES (%s,%s) ON CONFLICT DO NOTHING", (uid, tid))
        conn.commit(); bot.send_message(cid, "🚫 بلاک شد.")
    finally: cur.close(); conn.close()

def toggle_pv(uid, cid, field, mid):
    conn = db(); cur = conn.cursor()
    try:
        cur.execute(f"SELECT {field} FROM users WHERE user_id=%s", (uid,))
        r = cur.fetchone()
        if r:
            nv = not bool(r[field]); cur.execute(f"UPDATE users SET {field}=%s WHERE user_id=%s", (nv, uid)); conn.commit()
            bot.edit_message_reply_markup(cid, mid, reply_markup=settings_kb(uid))
    finally: cur.close(); conn.close()

def process_req(uid, tid, cid, rtype):
    cost = 1 if rtype == "direct" else 2
    conn = db(); cur = conn.cursor()
    try:
        cur.execute("SELECT stars FROM users WHERE user_id=%s", (uid,))
        r = cur.fetchone()
        if not r or r["stars"] < cost:
            bot.send_message(cid, f"❌ سکه کافی نداری. نیاز به {cost} سکه."); return
        cur.execute("UPDATE users SET stars = stars - %s WHERE user_id=%s", (cost, uid)); conn.commit()
        states[uid] = {"step": f"{rtype}_msg", "tid": tid}
        bot.send_message(cid, f"هزینه {cost} سکه کسر شد. پیامت رو بنویس:")
    finally: cur.close(); conn.close()

def send_req(uid, tid, cid, text, rtype):
    kb = types.InlineKeyboardMarkup().row(types.InlineKeyboardButton("✅ تایید", callback_data=f"appr:{uid}"), types.InlineKeyboardButton("❌ رد", callback_data=f"rej:{uid}"))
    if rtype == "direct": bot.send_message(tid, f"📩 دایرکت از {uid}:\n\n{text}", reply_markup=kb)
    else: bot.send_message(tid, f"💬 درخواست چت از {uid}:\n\n{text}", reply_markup=kb)
    bot.send_message(cid, "درخواست ارسال شد.")

def wallet_toman_kb():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🪙 ۵۰ سکه | ۱۰۰,۰۰۰ تومان", callback_data="pay:toman:50"))
    kb.add(types.InlineKeyboardButton("🪙 ۱۰۰ سکه | ۲۰۰,۰۰۰ تومان", callback_data="pay:toman:100"))
    kb.add(types.InlineKeyboardButton("🪙 ۵۰۰ سکه | ۵۰۰,۰۰۰ تومان", callback_data="pay:toman:500"))
    kb.add(types.InlineKeyboardButton("🪙 ۷۰۰ سکه | ۷۰۰,۰۰۰ تومان", callback_data="pay:toman:700"))
    kb.add(types.InlineKeyboardButton("🪙 ۱۰۰۰ سکه | ۱,۵۰۰,۰۰۰ تومان", callback_data="pay:toman:1000"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="wallet:home"))
    return kb

def wallet_stars_kb():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("✨ ۵۰ سکه | ۵۰ ستاره", callback_data="pay:stars:50"))
    kb.add(types.InlineKeyboardButton("✨ ۱۰۰ سکه | ۷۰ ستاره", callback_data="pay:stars:100"))
    kb.add(types.InlineKeyboardButton("✨ ۵۰۰ سکه | ۲۰۰ ستاره", callback_data="pay:stars:500"))
    kb.add(types.InlineKeyboardButton("✨ ۷۰۰ سکه | ۳۵۰ ستاره", callback_data="pay:stars:700"))
    kb.add(types.InlineKeyboardButton("✨ ۱۰۰۰ سکه | ۵۰۰ ستاره", callback_data="pay:stars:1000"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="wallet:home"))
    return kb

@bot.message_handler(commands=["start"])
def c_start(m):
    uid = m.from_user.id
    if is_reg(uid): bot.send_message(m.chat.id, "خوش برگشتی ❤️", reply_markup=main_menu_kb()); return
    states[uid] = {"step": "nickname"}; bot.send_message(m.chat.id, "اسم نمایشی‌ت چیه؟")

@bot.message_handler(commands=["stop"])
def c_stop(m): stop_chat(m.from_user.id, m.chat.id)

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
        cur.execute("UPDATE users SET photo_id=%s WHERE user_id=%s", (m.photo[-1].file_id, uid)); conn.commit(); cur.close(); conn.close()
        states.pop(uid, None); bot.send_message(m.chat.id, "✅ عکس ذخیره شد.", reply_markup=main_menu_kb())

@bot.message_handler(content_types=["text"])
def c_text(m):
    uid = m.from_user.id; t = (m.text or "").strip(); s = states.get(uid)
    if not is_reg(uid) and not s: bot.send_message(m.chat.id, "برای شروع /start را بزنید."); return
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
    elif t == "👥 مخاطبین من": show_contacts(m.chat.id, uid)
    elif t == "👤 پروفایل من": show_profile(m.chat.id, uid)
    elif t == "⚙️ تنظیمات": bot.send_message(m.chat.id, "⚙️ تنظیمات:", reply_markup=settings_kb(uid))
    elif t == "🪙 کیف پول":
        u = get_user(uid)
        text = f"💰 شما {u['stars']} سکه در حساب خود دارید.\n\nراه‌های زیادی برای دریافت سکه بیشتر وجود داره. می‌تونی از لیست زیر یکی رو انتخاب کنی:"
        bot.send_message(m.chat.id, text, reply_markup=wallet_kb())
    elif t == "🔗 دعوت دوستان":
        try: bot.send_message(m.chat.id, f"https://t.me/{bot.get_me().username}?start=ref_{uid}")
        except: pass
    else: bot.send_message(m.chat.id, "متوجه نشدم! از منو استفاده کن.", reply_markup=main_menu_kb())

@bot.callback_query_handler(func=lambda c: True)
def c_cb(c):
    d = c.data or ""; uid = c.from_user.id; cid = c.message.chat.id if c.message else uid; mid = c.message.message_id if c.message else None
    try:
        if d.startswith("like:"): like(uid, int(d.split(":")[1]), cid)
        elif d.startswith("pass:"): pass_user(uid, int(d.split(":")[1]), cid)
        elif d.startswith("block:"): block(uid, int(d.split(":")[1]), cid)
        elif d.startswith("add:"): add_contact(uid, int(d.split(":")[1]), cid)
        elif d.startswith("view:"): show_profile(cid, uid, target_id=int(d.split(":")[1]))
        elif d.startswith("dir:"): process_req(uid, int(d.split(":")[1]), cid, "direct")
        elif d.startswith("req:"): process_req(uid, int(d.split(":")[1]), cid, "chat")
        elif d.startswith("appr:"):
            start_chat(uid, int(d.split(":")[1]), cid)
            bot.edit_message_text("✅ تایید شد.", chat_id=cid, message_id=mid)
        elif d.startswith("rej:"): bot.edit_message_text("❌ رد شد.", chat_id=cid, message_id=mid)
        
        # Wallet Callbacks
        elif d == "wallet:home":
            u = get_user(uid)
            text = f"💰 شما {u['stars']} سکه در حساب خود دارید.\n\nراه‌های زیادی برای دریافت سکه بیشتر وجود داره. می‌تونی از لیست زیر یکی رو انتخاب کنی:"
            bot.edit_message_text(text, chat_id=cid, message_id=mid, reply_markup=wallet_kb())
        elif d == "wallet:invite":
            try: bot.send_message(cid, f"https://t.me/{bot.get_me().username}?start=ref_{uid}")
            except: pass
        elif d == "wallet:buy_toman":
            bot.edit_message_text("💳 لطفاً یکی از بسته‌های زیر را انتخاب کنید:", chat_id=cid, message_id=mid, reply_markup=wallet_toman_kb())
        elif d == "wallet:buy_stars":
            bot.edit_message_text("💫 لطفاً یکی از بسته‌های زیر را انتخاب کنید:", chat_id=cid, message_id=mid, reply_markup=wallet_stars_kb())
        elif d == "wallet:vip":
            bot.edit_message_text("👑 خرید VIP\n\nبا خرید VIP، امکانات ویژه‌ای دریافت می‌کنید.\n\nقیمت: ۲,۵۰۰,۰۰۰ تومان یا ۷۰۰ ستاره\n\n(درگاه پرداخت در حال راه‌اندازی است)", chat_id=cid, message_id=mid)
        elif d.startswith("pay:"):
            bot.answer_callback_query(c.id, "درگاه پرداخت در حال راه‌اندازی است. به زودی...", show_alert=True)
            
        elif d == "pv:profile": toggle_pv(uid, cid, "profile_visible", mid)
        elif d == "pv:location": toggle_pv(uid, cid, "location_visible", mid)
        elif d == "photo:ask": states[uid] = {"step": "photo"}; bot.send_message(cid, "📸 عکس بفرست:")
        elif d == "del:ask":
            kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("✅ بله", callback_data="del:yes"))
            bot.edit_message_text("مطمئنی؟", chat_id=cid, message_id=mid, reply_markup=kb)
        elif d == "del:yes":
            conn = db(); cur = conn.cursor()
            for tbl, cl1, cl2 in [("likes","user_id","target_id"),("passes","user_id","target_id"),("blocks","user_id","blocked_id"),("chats","user1","user2"),("contacts","user_id","contact_id"),("direct_requests","sender_id","receiver_id")]:
                cur.execute(f"DELETE FROM {tbl} WHERE {cl1}=%s OR {cl2}=%s", (uid, uid))
            cur.execute("DELETE FROM users WHERE user_id=%s", (uid,)); conn.commit(); cur.close(); conn.close()
            bot.send_message(cid, "حساب حذف شد.", reply_markup=types.ReplyKeyboardRemove())
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