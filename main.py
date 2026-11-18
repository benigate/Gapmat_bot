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

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN missing")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL missing")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

states = {}

def db():
    return psycopg2.connect(DATABASE_URL, sslmode="require", cursor_factory=RealDictCursor)

def init_db():
    conn = db(); cur = conn.cursor()
    try:
        cur.execute("CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY, nickname TEXT, age INTEGER, gender TEXT, city TEXT, bio TEXT, lat DOUBLE PRECISION, lon DOUBLE PRECISION, stars INTEGER DEFAULT 6, profile_visible BOOLEAN DEFAULT TRUE, location_visible BOOLEAN DEFAULT TRUE)")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS stars INTEGER DEFAULT 6")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_visible BOOLEAN DEFAULT TRUE")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS location_visible BOOLEAN DEFAULT TRUE")
        cur.execute("CREATE TABLE IF NOT EXISTS likes (user_id BIGINT, target_id BIGINT, PRIMARY KEY (user_id, target_id))")
        cur.execute("CREATE TABLE IF NOT EXISTS passes (user_id BIGINT, target_id BIGINT, PRIMARY KEY (user_id, target_id))")
        cur.execute("CREATE TABLE IF NOT EXISTS matches (user1 BIGINT, user2 BIGINT, PRIMARY KEY (user1, user2))")
        cur.execute("CREATE TABLE IF NOT EXISTS blocks (user_id BIGINT, blocked_id BIGINT, PRIMARY KEY (user_id, blocked_id))")
        cur.execute("CREATE TABLE IF NOT EXISTS reports (id SERIAL PRIMARY KEY, reporter_id BIGINT, target_id BIGINT, reason TEXT)")
        cur.execute("CREATE TABLE IF NOT EXISTS chats (user1 BIGINT, user2 BIGINT, active BOOLEAN DEFAULT TRUE, PRIMARY KEY (user1, user2))")
        cur.execute("CREATE TABLE IF NOT EXISTS referrals (referrer_id BIGINT, referred_id BIGINT UNIQUE)")
        conn.commit()
        logger.info("DB ready")
    except Exception as e:
        conn.rollback(); logger.error("DB fail: %s", e)
    finally:
        cur.close(); conn.close()

def get_user(uid):
    conn = db(); cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM users WHERE user_id=%s", (uid,))
        return cur.fetchone()
    finally:
        cur.close(); conn.close()

def is_reg(uid):
    u = get_user(uid)
    return bool(u and u["nickname"])

def menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("🔎 جستجو", "👤 پروفایل")
    kb.row("❤️ مچ‌ها", "⭐ ستاره‌ها")
    kb.row("🔗 دعوت", "⚙️ تنظیمات")
    kb.row("📍 ارسال موقعیت", "☎️ پشتیبانی")
    return kb

def profile_kb(tid):
    kb = types.InlineKeyboardMarkup()
    kb.row(types.InlineKeyboardButton("❤️ لایک", callback_data=f"like:{tid}"),
           types.InlineKeyboardButton("👎 رد", callback_data=f"pass:{tid}"))
    kb.row(types.InlineKeyboardButton("🚫 بلاک", callback_data=f"block:{tid}"),
           types.InlineKeyboardButton("⚠️ گزارش", callback_data=f"report:{tid}"))
    return kb

def settings_kb():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("نمایش پروفایل", callback_data="pv:profile"))
    kb.add(types.InlineKeyboardButton("نمایش موقعیت", callback_data="pv:location"))
    kb.add(types.InlineKeyboardButton("🗑 حذف حساب", callback_data="del:ask"))
    return kb

def start_reg(msg):
    states[msg.from_user.id] = {"step": "nickname"}
    bot.send_message(msg.chat.id, "سلام! اسم نمایشی‌ت چیه؟")

def finish_reg(uid):
    d = states.pop(uid, None)
    if not d: return
    conn = db(); cur = conn.cursor()
    try:
        cur.execute("""INSERT INTO users (user_id, nickname, age, gender, city, bio, stars)
            VALUES (%s,%s,%s,%s,%s,%s,6)
            ON CONFLICT (user_id) DO UPDATE SET nickname=EXCLUDED.nickname,
            age=EXCLUDED.age, gender=EXCLUDED.gender, city=EXCLUDED.city, bio=EXCLUDED.bio""",
            (uid, d["nickname"], d["age"], d["gender"], d["city"], d["bio"]))
        conn.commit()
    except Exception as e:
        conn.rollback(); logger.error("reg fail: %s", e)
    finally:
        cur.close(); conn.close()
    bot.send_message(uid, "🎉 ثبت‌نام کامل شد!", reply_markup=menu())

def show_profile(cid, uid):
    u = get_user(uid)
    if not u:
        bot.send_message(cid, "هنوز ثبت‌نام نکردی. /start بزن.")
        return
    bot.send_message(cid, f"👤 {u['nickname']}\n🎂 {u['age']}\n⚧ {u['gender']}\n📍 {u['city']}\n📝 {u['bio']}\n⭐ {u['stars']}")

def show_stars(cid, uid):
    u = get_user(uid)
    if not u: return
    bot.send_message(cid, f"⭐ موجودی: {u['stars']}")

def show_settings(cid, uid):
    u = get_user(uid)
    if not u: return
    bot.send_message(cid, "⚙️ تنظیمات:", reply_markup=settings_kb())

def toggle_pv(uid, cid, field):
    if field not in ("profile_visible", "location_visible"): return
    conn = db(); cur = conn.cursor()
    try:
        cur.execute(f"SELECT {field} FROM users WHERE user_id=%s", (uid,))
        r = cur.fetchone()
        if not r: return
        nv = not bool(r[field])
        cur.execute(f"UPDATE users SET {field}=%s WHERE user_id=%s", (nv, uid))
        conn.commit()
        bot.send_message(cid, f"{'روشن' if nv else 'خاموش'} شد.")
    except Exception as e:
        conn.rollback(); logger.error("pv fail: %s", e)
    finally:
        cur.close(); conn.close()

def dist(a,b,c,d):
    R=6371; dl=math.radians(c-a); dn=math.radians(d-b)
    x=math.sin(dl/2)**2+math.cos(math.radians(a))*math.cos(math.radians(c))*math.sin(dn/2)**2
    return R*2*math.atan2(math.sqrt(x),math.sqrt(1-x))

def find(cid, uid):
    u = get_user(uid)
    if not u: return
    if u["lat"] is None:
        bot.send_message(cid, "اول موقعیت بفرست.", reply_markup=menu()); return
    conn = db(); cur = conn.cursor()
    try:
        cur.execute("""SELECT * FROM users WHERE user_id!=%s AND nickname IS NOT NULL
            AND profile_visible=TRUE AND lat IS NOT NULL
            AND user_id NOT IN (SELECT target_id FROM passes WHERE user_id=%s)
            AND user_id NOT IN (SELECT target_id FROM likes WHERE user_id=%s)
            AND user_id NOT IN (SELECT blocked_id FROM blocks WHERE user_id=%s)
            AND user_id NOT IN (SELECT user_id FROM blocks WHERE blocked_id=%s)""",
            (uid, uid, uid, uid, uid))
        c = cur.fetchall()
    finally:
        cur.close(); conn.close()
    if not c:
        bot.send_message(cid, "کسی پیدا نشد."); return
    c.sort(key=lambda p: dist(u["lat"], u["lon"], p["lat"], p["lon"]))
    p = c[0]
    bot.send_message(cid, f"👤 {p['nickname']}\n🎂 {p['age']}\n📍 {p['city']}\n📝 {p['bio']}",
                     reply_markup=profile_kb(p["user_id"]))

def like(uid, tid, cid):
    if uid == tid: return
    conn = db(); cur = conn.cursor()
    m = False
    try:
        cur.execute("INSERT INTO likes (user_id, target_id) VALUES (%s,%s) ON CONFLICT DO NOTHING", (uid, tid))
        cur.execute("SELECT 1 FROM likes WHERE user_id=%s AND target_id=%s", (tid, uid))
        if cur.fetchone():
            a, b = sorted([uid, tid])
            cur.execute("INSERT INTO matches (user1, user2) VALUES (%s,%s) ON CONFLICT DO NOTHING", (a, b))
            m = True
        conn.commit()
    except Exception as e:
        conn.rollback(); logger.error("like fail: %s", e)
    finally:
        cur.close(); conn.close()
    if m:
        bot.send_message(uid, "🎉 مچ شدین!")
        try: bot.send_message(tid, "🎉 مچ جدید!")
        except: pass
    else:
        bot.send_message(cid, "❤️ ثبت شد.")
    find(cid, uid)

def pass_user(uid, tid, cid):
    conn = db(); cur = conn.cursor()
    try:
        cur.execute("INSERT INTO passes (user_id, target_id) VALUES (%s,%s) ON CONFLICT DO NOTHING", (uid, tid))
        conn.commit()
    finally:
        cur.close(); conn.close()
    find(cid, uid)

def show_matches(cid, uid):
    conn = db(); cur = conn.cursor()
    try:
        cur.execute("""SELECT u.* FROM matches m JOIN users u
            ON u.user_id = CASE WHEN m.user1=%s THEN m.user2 ELSE m.user1 END
            WHERE m.user1=%s OR m.user2=%s""", (uid, uid, uid))
        p = cur.fetchall()
    finally:
        cur.close(); conn.close()
    if not p:
        bot.send_message(cid, "مچی نداری ❤️"); return
    for x in p:
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("💬 چت", callback_data=f"chat:{x['user_id']}"))
        bot.send_message(cid, f"❤️ {x['nickname']}", reply_markup=kb)

def start_chat(uid, tid, cid):
    a, b = sorted([uid, tid])
    conn = db(); cur = conn.cursor()
    try:
        cur.execute("SELECT 1 FROM matches WHERE user1=%s AND user2=%s", (a, b))
        if not cur.fetchone():
            bot.send_message(cid, "اول باید مچ بشین."); return
        cur.execute("INSERT INTO chats (user1, user2, active) VALUES (%s,%s,TRUE) ON CONFLICT (user1,user2) DO UPDATE SET active=TRUE", (a, b))
        conn.commit()
    finally:
        cur.close(); conn.close()
    bot.send_message(uid, "💬 چت شروع شد. /stop برای پایان.")
    try: bot.send_message(tid, "💬 چت شروع شد. /stop برای پایان.")
    except: pass

def stop_chat(uid, cid):
    conn = db(); cur = conn.cursor()
    s = []
    try:
        cur.execute("UPDATE chats SET active=FALSE WHERE (user1=%s OR user2=%s) AND active=TRUE RETURNING user1,user2", (uid, uid))
        s = cur.fetchall(); conn.commit()
    finally:
        cur.close(); conn.close()
    if not s:
        bot.send_message(cid, "چت فعالی نداری."); return
    bot.send_message(cid, "چت بسته شد.")
    for x in s:
        o = x["user2"] if x["user1"] == uid else x["user1"]
        try: bot.send_message(o, "چت بسته شد.")
        except: pass

def relay(msg):
    uid = msg.from_user.id
    conn = db(); cur = conn.cursor()
    s = None
    try:
        cur.execute("SELECT user1,user2 FROM chats WHERE active=TRUE AND (user1=%s OR user2=%s) LIMIT 1", (uid, uid))
        s = cur.fetchone()
    finally:
        cur.close(); conn.close()
    if not s: return False
    o = s["user2"] if s["user1"] == uid else s["user1"]
    try:
        bot.copy_message(o, msg.chat.id, msg.message_id)
    except:
        bot.send_message(msg.chat.id, "ارسال نشد.")
    return True

def block(uid, tid, cid):
    conn = db(); cur = conn.cursor()
    try:
        cur.execute("INSERT INTO blocks (user_id, blocked_id) VALUES (%s,%s) ON CONFLICT DO NOTHING", (uid, tid))
        a, b = sorted([uid, tid])
        cur.execute("UPDATE chats SET active=FALSE WHERE user1=%s AND user2=%s", (a, b))
        conn.commit()
    finally:
        cur.close(); conn.close()
    bot.send_message(cid, "🚫 بلاک شد.")

def report(uid, tid, reason, cid):
    conn = db(); cur = conn.cursor()
    try:
        cur.execute("INSERT INTO reports (reporter_id, target_id, reason) VALUES (%s,%s,%s)", (uid, tid, reason))
        conn.commit()
    finally:
        cur.close(); conn.close()
    bot.send_message(cid, "گزارش ثبت شد.")
    if ADMIN_ID:
        try: bot.send_message(ADMIN_ID, f"⚠️ گزارش از {uid} به {tid}\n{reason}")
        except: pass

def del_account(uid, cid):
    conn = db(); cur = conn.cursor()
    try:
        for t, a, b in [("likes","user_id","target_id"),("passes","user_id","target_id"),
                        ("matches","user1","user2"),("blocks","user_id","blocked_id"),
                        ("chats","user1","user2"),("referrals","referrer_id","referred_id")]:
            cur.execute(f"DELETE FROM {t} WHERE {a}=%s OR {b}=%s", (uid, uid))
        cur.execute("DELETE FROM reports WHERE reporter_id=%s OR target_id=%s", (uid, uid))
        cur.execute("DELETE FROM users WHERE user_id=%s", (uid,))
        conn.commit()
    except Exception as e:
        conn.rollback(); logger.error("del fail: %s", e)
        bot.send_message(cid, "حذف ناموفق."); return
    finally:
        cur.close(); conn.close()
    states.pop(uid, None)
    bot.send_message(cid, "حساب حذف شد.", reply_markup=types.ReplyKeyboardRemove())

def invite(cid, uid):
    try:
        me = bot.get_me()
        bot.send_message(cid, f"🔗 لینک دعوت:\nhttps://t.me/{me.username}?start=ref_{uid}\n\nهر ثبت‌نام ۱۰ ستاره.")
    except Exception as e:
        logger.error("invite fail: %s", e)
        bot.send_message(cid, "خطا در ساخت لینک.")

def support_start(uid, cid):
    states[uid] = {"step": "support"}
    bot.send_message(cid, "پیامت رو بنویس. /cancel برای انصراف.")

def support_send(msg):
    uid = msg.from_user.id
    if not ADMIN_ID:
        bot.send_message(msg.chat.id, "پشتیبانی فعال نیست.")
        states.pop(uid, None); return
    try:
        bot.send_message(ADMIN_ID, f"📩 پشتیبانی از {uid}:\n{msg.text or ''}")
        bot.send_message(msg.chat.id, "ارسال شد.")
    except:
        bot.send_message(msg.chat.id, "ارسال نشد.")
    states.pop(uid, None)

def loc_request(cid):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(types.KeyboardButton("📍 ارسال موقعیت", request_location=True))
    bot.send_message(cid, "دکمه زیر رو بزن:", reply_markup=kb)

@bot.message_handler(commands=["start"])
def c_start(m):
    try:
        uid = m.from_user.id
        ref = None
        parts = (m.text or "").split()
        if len(parts) > 1 and parts[1].startswith("ref_"):
            try: ref = int(parts[1][4:])
            except: pass
        if is_reg(uid):
            bot.send_message(m.chat.id, "خوش برگشتی ❤️", reply_markup=menu()); return
        states[uid] = {"step": "nickname", "ref": ref}
        bot.send_message(m.chat.id, "سلام! اسم نمایشی‌ت چیه؟")
    except Exception as e:
        logger.error("start fail: %s", e)

@bot.message_handler(commands=["myid"])
def c_myid(m):
    try:
        bot.send_message(m.chat.id, f"chat_id: {m.chat.id}\nuser_id: {m.from_user.id}")
    except Exception as e:
        logger.error("myid fail: %s", e)

@bot.message_handler(commands=["stop"])
def c_stop(m):
    try: stop_chat(m.from_user.id, m.chat.id)
    except Exception as e: logger.error("stop fail: %s", e)

@bot.message_handler(commands=["cancel"])
def c_cancel(m):
    try:
        states.pop(m.from_user.id, None)
        bot.send_message(m.chat.id, "لغو شد.", reply_markup=menu())
    except Exception as e: logger.error("cancel fail: %s", e)

@bot.message_handler(content_types=["location"])
def c_loc(m):
    try:
        uid = m.from_user.id
        if not is_reg(uid):
            bot.send_message(m.chat.id, "اول ثبت‌نام کن."); return
        conn = db(); cur = conn.cursor()
        try:
            cur.execute("UPDATE users SET lat=%s, lon=%s WHERE user_id=%s",
                        (m.location.latitude, m.location.longitude, uid))
            conn.commit()
        finally:
            cur.close(); conn.close()
        bot.send_message(m.chat.id, "📍 ثبت شد.", reply_markup=menu())
        find(m.chat.id, uid)
    except Exception as e:
        logger.error("loc fail: %s", e)

@bot.message_handler(content_types=["text"])
def c_text(m):
    try:
        uid = m.from_user.id
        t = (m.text or "").strip()
        s = states.get(uid)
        if s:
            st = s["step"]
            if st == "nickname":
                s["nickname"] = t[:50]; s["step"] = "age"
                bot.send_message(m.chat.id, "چند سالته؟ (۱۸+)"); return
            if st == "age":
                try: a = int(t)
                except: bot.send_message(m.chat.id, "عدد بنویس."); return
                if a < 18: bot.send_message(m.chat.id, "فقط ۱۸+."); return
                s["age"] = a; s["step"] = "gender"
                kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
                kb.row("پسر","دختر")
                bot.send_message(m.chat.id, "جنسیت؟", reply_markup=kb); return
            if st == "gender":
                s["gender"] = t; s["step"] = "city"
                bot.send_message(m.chat.id, "شهر؟", reply_markup=types.ReplyKeyboardRemove()); return
            if st == "city":
                s["city"] = t[:50]; s["step"] = "bio"
                bot.send_message(m.chat.id, "بیو:"); return
            if st == "bio":
                s["bio"] = t[:300]
                finish_reg(uid); return
            if st == "support":
                support_send(m); return
            if st == "report":
                tid = s.get("tid"); states.pop(uid, None)
                report(uid, tid, t[:300], m.chat.id); return
        if t == "🔎 جستجو": find(m.chat.id, uid)
        elif t == "👤 پروفایل": show_profile(m.chat.id, uid)
        elif t == "❤️ مچ‌ها": show_matches(m.chat.id, uid)
        elif t == "⭐ ستاره‌ها": show_stars(m.chat.id, uid)
        elif t == "🔗 دعوت": invite(m.chat.id, uid)
        elif t == "⚙️ تنظیمات": show_settings(m.chat.id, uid)
        elif t == "📍 ارسال موقعیت": loc_request(m.chat.id)
        elif t == "☎️ پشتیبانی": support_start(uid, m.chat.id)
        elif relay(m): return
        else: bot.send_message(m.chat.id, "از منو انتخاب کن.", reply_markup=menu())
    except Exception as e:
        logger.error("text fail: %s", e)

@bot.callback_query_handler(func=lambda c: True)
def c_cb(c):
    try:
        d = c.data or ""; uid = c.from_user.id
        cid = c.message.chat.id if c.message else uid
        if d.startswith("like:"): like(uid, int(d.split(":")[1]), cid)
        elif d.startswith("pass:"): pass_user(uid, int(d.split(":")[1]), cid)
        elif d.startswith("block:"): block(uid, int(d.split(":")[1]), cid)
        elif d.startswith("report:"):
            states[uid] = {"step": "report", "tid": int(d.split(":")[1])}
            bot.send_message(cid, "دلیل گزارش:")
        elif d.startswith("chat:"): start_chat(uid, int(d.split(":")[1]), cid)
        elif d == "pv:profile": toggle_pv(uid, cid, "profile_visible")
        elif d == "pv:location": toggle_pv(uid, cid, "location_visible")
        elif d == "del:ask":
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton("✅ بله", callback_data="del:yes"))
            kb.add(types.InlineKeyboardButton("❌ انصراف", callback_data="del:no"))
            bot.send_message(cid, "همه‌ی داده‌هات پاک می‌شه. مطمئنی؟", reply_markup=kb)
        elif d == "del:yes": del_account(uid, cid)
        elif d == "del:no": bot.send_message(cid, "لغو شد.")
        bot.answer_callback_query(c.id)
    except Exception as e:
        logger.error("cb fail: %s", e)

@app.route("/")
@app.route("/health")
def health(): return "OK", 200

def run():
    try: init_db()
    except Exception as e: logger.error("init fail: %s", e)
    try:
        bot.delete_webhook(drop_pending_updates=True)
        logger.info("Webhook deleted")
    except Exception as e:
        logger.error("delete_webhook fail: %s", e)
    while True:
        try: bot.infinity_polling(timeout=30, long_polling_timeout=25)
        except Exception as e:
            logger.error("poll fail: %s", e); time.sleep(5)

if __name__ == "__main__":
    threading.Thread(target=run, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))