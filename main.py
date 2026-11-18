import os
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

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is missing")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

user_states = {}
report_states = {}


def get_db():
    return psycopg2.connect(DATABASE_URL, sslmode="require", cursor_factory=RealDictCursor)


def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            nickname TEXT, age INTEGER, gender TEXT, city TEXT, bio TEXT,
            lat DOUBLE PRECISION, lon DOUBLE PRECISION,
            stars INTEGER DEFAULT 0,
            profile_visible BOOLEAN DEFAULT TRUE,
            location_visible BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("CREATE TABLE IF NOT EXISTS likes (user_id BIGINT, target_id BIGINT, PRIMARY KEY (user_id, target_id))")
    cur.execute("CREATE TABLE IF NOT EXISTS passes (user_id BIGINT, target_id BIGINT, PRIMARY KEY (user_id, target_id))")
    cur.execute("CREATE TABLE IF NOT EXISTS matches (user1 BIGINT, user2 BIGINT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (user1, user2))")
    cur.execute("CREATE TABLE IF NOT EXISTS blocks (user_id BIGINT, blocked_id BIGINT, PRIMARY KEY (user_id, blocked_id))")
    cur.execute("CREATE TABLE IF NOT EXISTS reports (id SERIAL PRIMARY KEY, reporter_id BIGINT, target_id BIGINT, reason TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    cur.execute("CREATE TABLE IF NOT EXISTS chat_sessions (user1 BIGINT, user2 BIGINT, active BOOLEAN DEFAULT TRUE, PRIMARY KEY (user1, user2))")
    cur.execute("CREATE TABLE IF NOT EXISTS referrals (referrer_id BIGINT, referred_id BIGINT UNIQUE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    conn.commit()
    cur.close()
    conn.close()


def get_user(user_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE user_id=%s", (user_id,))
    user = cur.fetchone()
    cur.close()
    conn.close()
    return user


def is_registered(user_id):
    user = get_user(user_id)
    return bool(user and user["nickname"])


def is_admin(user_id):
    return bool(ADMIN_ID) and str(user_id) == str(ADMIN_ID)


def main_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("🔎 پیدا کردن افراد", "👤 پروفایل من")
    kb.row("❤️ مچ‌های من", "⭐ ستاره‌های من")
    kb.row("🔗 دعوت دوستان", "⚙️ تنظیمات")
    kb.row("📍 ارسال موقعیت", "☎️ پشتیبانی")
    return kb


def profile_keyboard(target_id):
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("❤️ لایک", callback_data=f"like:{target_id}"),
        types.InlineKeyboardButton("👎 رد", callback_data=f"pass:{target_id}")
    )
    kb.row(
        types.InlineKeyboardButton("🚫 مسدود", callback_data=f"block:{target_id}"),
        types.InlineKeyboardButton("⚠️ گزارش", callback_data=f"report:{target_id}")
    )
    return kb


def settings_keyboard():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("تغییر نمایش پروفایل", callback_data="privacy:profile"))
    kb.add(types.InlineKeyboardButton("تغییر نمایش موقعیت", callback_data="privacy:location"))
    kb.add(types.InlineKeyboardButton("🗑 حذف حساب", callback_data="delete:ask"))
    return kb


def start_registration(message, referral_id=None):
    user_states[message.from_user.id] = {"step": "nickname", "referral_id": referral_id}
    bot.send_message(message.chat.id, "سلام! به گپ‌میت خوش اومدی ❤️\n\nچه اسمی برات نمایش بدیم؟")


def finish_registration(user_id):
    data = user_states.get(user_id)
    if not data:
        return
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO users (user_id, nickname, age, gender, city, bio, stars)
        VALUES (%s, %s, %s, %s, %s, %s, 6)
        ON CONFLICT (user_id) DO UPDATE SET
            nickname=EXCLUDED.nickname, age=EXCLUDED.age, gender=EXCLUDED.gender,
            city=EXCLUDED.city, bio=EXCLUDED.bio
    """, (user_id, data["nickname"], data["age"], data["gender"], data["city"], data["bio"]))
    referrer_id = data.get("referral_id")
    if referrer_id and referrer_id != user_id:
        cur.execute("SELECT user_id FROM users WHERE user_id=%s", (referrer_id,))
        if cur.fetchone():
            cur.execute("""
                INSERT INTO referrals (referrer_id, referred_id) VALUES (%s, %s)
                ON CONFLICT (referred_id) DO NOTHING RETURNING referred_id
            """, (referrer_id, user_id))
            if cur.fetchone():
                cur.execute("UPDATE users SET stars = stars + 10 WHERE user_id=%s", (referrer_id,))
                try:
                    bot.send_message(referrer_id, "🎉 یک نفر با لینک دعوت تو ثبت‌نام کرد!\n۱۰ ستاره گرفتی.")
                except Exception:
                    pass
    conn.commit()
    cur.close()
    conn.close()
    user_states.pop(user_id, None)
    bot.send_message(user_id, "🎉 پروفایلت ساخته شد!\n۶ ستاره هدیه گرفتی.", reply_markup=main_menu())


def show_profile(chat_id, user_id):
    user = get_user(user_id)
    if not user:
        bot.send_message(chat_id, "هنوز ثبت‌نام نکردی.")
        return
    bot.send_message(chat_id,
        f"👤 نام: {user['nickname'] or ''}\n🎂 سن: {user['age']}\n"
        f"⚧ جنسیت: {user['gender'] or ''}\n📍 شهر: {user['city'] or 'نامشخص'}\n\n"
        f"📝 درباره من:\n{user['bio'] or 'بدون توضیحات'}")


def show_stars(chat_id, user_id):
    user = get_user(user_id)
    if not user:
        return
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("⭐ خرید ۱۰ ستاره", callback_data="buy:10"))
    kb.add(types.InlineKeyboardButton("⭐ خرید ۵۰ ستاره", callback_data="buy:50"))
    bot.send_message(chat_id, f"موجودی ستاره‌های تو: ⭐ {user['stars']}", reply_markup=kb)


def show_settings(chat_id, user_id):
    if not get_user(user_id):
        return
    bot.send_message(chat_id, "⚙️ تنظیمات:", reply_markup=settings_keyboard())


def show_referral(chat_id, user_id):
    me = bot.get_me()
    link = f"https://t.me/{me.username}?start=ref_{user_id}"
    bot.send_message(chat_id, f"🔗 لینک دعوت تو:\n{link}\n\nبا هر ثبت‌نام ۱۰ ستاره می‌گیری.")


def toggle_privacy(user_id, chat_id, field):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(f"SELECT {field} FROM users WHERE user_id=%s", (user_id,))
    row = cur.fetchone()
    if not row:
        cur.close(); conn.close(); return
    new_val = not bool(row[field])
    cur.execute(f"UPDATE users SET {field}=%s WHERE user_id=%s", (new_val, user_id))
    conn.commit()
    cur.close(); conn.close()
    bot.send_message(chat_id, f"وضعیت جدید: {'روشن' if new_val else 'خاموش'}")


def distance_km(lat1, lon1, lat2, lon2):
    r = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlon/2)**2
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def find_nearby(chat_id, user_id):
    user = get_user(user_id)
    if not user:
        return
    if user["lat"] is None or user["lon"] is None:
        bot.send_message(chat_id, "اول موقعیتت رو ارسال کن.", reply_markup=main_menu())
        return
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM users
        WHERE user_id != %s AND nickname IS NOT NULL AND profile_visible = TRUE
        AND lat IS NOT NULL AND lon IS NOT NULL
        AND user_id NOT IN (SELECT target_id FROM passes WHERE user_id=%s)
        AND user_id NOT IN (SELECT target_id FROM likes WHERE user_id=%s)
        AND user_id NOT IN (SELECT blocked_id FROM blocks WHERE user_id=%s)
        AND user_id NOT IN (SELECT user_id FROM blocks WHERE blocked_id=%s)
        AND user_id NOT IN (
            SELECT user2 FROM matches WHERE user1=%s
            UNION SELECT user1 FROM matches WHERE user2=%s
        )
    """, (user_id, user_id, user_id, user_id, user_id, user_id, user_id))
    candidates = cur.fetchall()
    cur.close(); conn.close()
    candidates = sorted(candidates, key=lambda p: distance_km(user["lat"], user["lon"], p["lat"], p["lon"]))
    if not candidates:
        bot.send_message(chat_id, "فعلاً فرد جدیدی پیدا نشد.")
        return
    show_person(chat_id, candidates[0])


def show_person(chat_id, person):
    text = (f"👤 {person['nickname'] or ''}\n🎂 {person['age']} سال\n"
            f"📍 {person['city'] or 'نامشخص'}\n\n📝 {person['bio'] or 'بدون توضیحات'}")
    bot.send_message(chat_id, text, reply_markup=profile_keyboard(person["user_id"]))


def handle_like(user_id, target_id, chat_id):
    if user_id == target_id:
        bot.send_message(chat_id, "خودت رو نمی‌تونی لایک کنی.")
        return
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users WHERE user_id=%s", (target_id,))
    if not cur.fetchone():
        cur.close(); conn.close()
        bot.send_message(chat_id, "این کاربر وجود ندارد.")
        return
    cur.execute("""
        SELECT 1 FROM blocks
        WHERE (user_id=%s AND blocked_id=%s) OR (user_id=%s AND blocked_id=%s)
    """, (user_id, target_id, target_id, user_id))
    if cur.fetchone():
        cur.close(); conn.close()
        bot.send_message(chat_id, "امکان ارتباط نیست.")
        return
    cur.execute("INSERT INTO likes (user_id, target_id) VALUES (%s, %s) ON CONFLICT DO NOTHING", (user_id, target_id))
    cur.execute("SELECT 1 FROM likes WHERE user_id=%s AND target_id=%s", (target_id, user_id))
    matched = cur.fetchone() is not None
    if matched:
        first, second = sorted([user_id, target_id])
        cur.execute("INSERT INTO matches (user1, user2) VALUES (%s, %s) ON CONFLICT DO NOTHING", (first, second))
    conn.commit()
    cur.close(); conn.close()
    if matched:
        bot.send_message(user_id, "🎉 مچ شدین! هر دو همدیگه رو لایک کردین.")
        try:
            bot.send_message(target_id, "🎉 یک مچ جدید داری!")
        except Exception:
            pass
    else:
        bot.send_message(chat_id, "❤️ لایکت ثبت شد.")
    find_nearby(chat_id, user_id)


def handle_pass(user_id, target_id, chat_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("INSERT INTO passes (user_id, target_id) VALUES (%s, %s) ON CONFLICT DO NOTHING", (user_id, target_id))
    conn.commit()
    cur.close(); conn.close()
    bot.send_message(chat_id, "این پروفایل رد شد.")
    find_nearby(chat_id, user_id)


def show_matches(chat_id, user_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT u.* FROM matches m
        JOIN users u ON u.user_id = CASE WHEN m.user1=%s THEN m.user2 ELSE m.user1 END
        WHERE m.user1=%s OR m.user2=%s
    """, (user_id, user_id, user_id))
    people = cur.fetchall()
    cur.close(); conn.close()
    if not people:
        bot.send_message(chat_id, "هنوز مچی نداری ❤️")
        return
    for person in people:
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("💬 شروع چت", callback_data=f"chat:{person['user_id']}"))
        bot.send_message(chat_id, f"❤️ {person['nickname'] or ''} ({person['age']} سال)", reply_markup=kb)


def start_chat(user_id, target_id, chat_id):
    first, second = sorted([user_id, target_id])
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM matches WHERE user1=%s AND user2=%s", (first, second))
    if not cur.fetchone():
        cur.close(); conn.close()
        bot.send_message(chat_id, "ابتدا باید مچ شده باشی.")
        return
    cur.execute("""
        SELECT 1 FROM blocks
        WHERE (user_id=%s AND blocked_id=%s) OR (user_id=%s AND blocked_id=%s)
    """, (user_id, target_id, target_id, user_id))
    if cur.fetchone():
        cur.close(); conn.close()
        bot.send_message(chat_id, "امکان شروع چت نیست.")
        return
    cur.execute("""
        SELECT user1, user2 FROM chat_sessions
        WHERE active=TRUE AND (user1 IN (%s, %s) OR user2 IN (%s, %s))
    """, (user_id, target_id, user_id, target_id))
    existing = cur.fetchone()
    if existing and (existing["user1"], existing["user2"]) != (first, second):
        cur.close(); conn.close()
        bot.send_message(chat_id, "یکی از طرفین چت فعال دیگری دارد.")
        return
    cur.execute("""
        INSERT INTO chat_sessions (user1, user2, active) VALUES (%s, %s, TRUE)
        ON CONFLICT (user1, user2) DO UPDATE SET active=TRUE
    """, (first, second))
    conn.commit()
    cur.close(); conn.close()
    bot.send_message(user_id, "💬 چت شروع شد! برای پایان /stopchat بزن.")
    try:
        bot.send_message(target_id, "💬 چت شروع شد! برای پایان /stopchat بزن.")
    except Exception:
        pass


def stop_chat(user_id, chat_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE chat_sessions SET active=FALSE
        WHERE (user1=%s OR user2=%s) AND active=TRUE
        RETURNING user1, user2
    """, (user_id, user_id))
    sessions = cur.fetchall()
    conn.commit()
    cur.close(); conn.close()
    if not sessions:
        bot.send_message(chat_id, "چت فعالی نداری.")
        return
    bot.send_message(chat_id, "چت پایان یافت.")
    for s in sessions:
        other = s["user2"] if s["user1"] == user_id else s["user1"]
        try:
            bot.send_message(other, "چت توسط طرف مقابل پایان یافت.")
        except Exception:
            pass


def relay_message(message):
    user_id = message.from_user.id
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT user1, user2 FROM chat_sessions
        WHERE active=TRUE AND (user1=%s OR user2=%s) LIMIT 1
    """, (user_id, user_id))
    session = cur.fetchone()
    cur.close(); conn.close()
    if not session:
        return False
    other = session["user2"] if session["user1"] == user_id else session["user1"]
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT 1 FROM blocks
        WHERE (user_id=%s AND blocked_id=%s) OR (user_id=%s AND blocked_id=%s)
    """, (user_id, other, other, user_id))
    blocked = cur.fetchone() is not None
    cur.close(); conn.close()
    if blocked:
        bot.send_message(message.chat.id, "امکان ارسال پیام نیست.")
        return True
    try:
        bot.copy_message(other, message.chat.id, message.message_id)
        return True
    except Exception:
        bot.send_message(message.chat.id, "ارسال نشد. ممکنه طرف ربات رو مسدود کرده باشه.")
        return True


def block_user(user_id, target_id, chat_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("INSERT INTO blocks (user_id, blocked_id) VALUES (%s, %s) ON CONFLICT DO NOTHING", (user_id, target_id))
    first, second = sorted([user_id, target_id])
    cur.execute("UPDATE chat_sessions SET active=FALSE WHERE user1=%s AND user2=%s", (first, second))
    conn.commit()
    cur.close(); conn.close()
    bot.send_message(chat_id, "🚫 این کاربر مسدود شد.")


def report_user(user_id, target_id, reason, chat_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("INSERT INTO reports (reporter_id, target_id, reason) VALUES (%s, %s, %s)", (user_id, target_id, reason))
    conn.commit()
    cur.close(); conn.close()
    bot.send_message(chat_id, "گزارش ثبت شد.")
    if ADMIN_ID:
        try:
            bot.send_message(ADMIN_ID, f"⚠️ گزارش از {user_id} به {target_id}\nدلیل: {reason}")
        except Exception:
            pass


def delete_user_account(user_id, chat_id):
    conn = get_db()
    cur = conn.cursor()
    for table, c1, c2 in [("likes","user_id","target_id"),("passes","user_id","target_id"),
                          ("matches","user1","user2"),("blocks","user_id","blocked_id"),
                          ("chat_sessions","user1","user2"),("referrals","referrer_id","referred_id")]:
        cur.execute(f"DELETE FROM {table} WHERE {c1}=%s OR {c2}=%s", (user_id, user_id))
    cur.execute("DELETE FROM reports WHERE reporter_id=%s OR target_id=%s", (user_id, user_id))
    cur.execute("DELETE FROM users WHERE user_id=%s", (user_id,))
    conn.commit()
    cur.close(); conn.close()
    user_states.pop(user_id, None)
    report_states.pop(user_id, None)
    bot.send_message(chat_id, "حساب حذف شد.", reply_markup=types.ReplyKeyboardRemove())


def show_admin_reports(chat_id, user_id):
    if not is_admin(user_id):
        bot.send_message(chat_id, "اجازه نداری.")
        return
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM reports ORDER BY created_at DESC LIMIT 30")
    reports = cur.fetchall()
    cur.close(); conn.close()
    if not reports:
        bot.send_message(chat_id, "گزارشی نیست.")
        return
    for r in reports:
        bot.send_message(chat_id, f"#{r['id']} از {r['reporter_id']} به {r['target_id']}\nدلیل: {r['reason'] or ''}")


def start_support(user_id, chat_id):
    report_states[user_id] = {"step": "support"}
    bot.send_message(chat_id, "☎️ پیامت رو بنویس. برای انصراف /cancel.")


def forward_support(message):
    user_id = message.from_user.id
    if not ADMIN_ID:
        bot.send_message(message.chat.id, "پشتیبانی فعال نیست.")
        report_states.pop(user_id, None)
        return
    try:
        bot.send_message(ADMIN_ID, f"📩 پشتیبانی از {user_id}:\n{message.text or ''}")
        bot.send_message(message.chat.id, "پیامت ارسال شد.")
    except Exception:
        bot.send_message(message.chat.id, "ارسال نشد.")
    report_states.pop(user_id, None)


@bot.message_handler(commands=["start"])
def cmd_start(message):
    user_id = message.from_user.id
    parts = (message.text or "").split()
    referral_id = None
    if len(parts) > 1 and parts[1].startswith("ref_"):
        try:
            referral_id = int(parts[1][4:])
        except ValueError:
            referral_id = None
    if is_registered(user_id):
        bot.send_message(message.chat.id, "خوش برگشتی ❤️", reply_markup=main_menu())
        return
    start_registration(message, referral_id)


@bot.message_handler(commands=["stopchat"])
def cmd_stopchat(message):
    stop_chat(message.from_user.id, message.chat.id)


@bot.message_handler(commands=["cancel"])
def cmd_cancel(message):
    user_states.pop(message.from_user.id, None)
    report_states.pop(message.from_user.id, None)
    bot.send_message(message.chat.id, "لغو شد.", reply_markup=main_menu())


@bot.message_handler(commands=["admin"])
def cmd_admin(message):
    show_admin_reports(message.chat.id, message.from_user.id)


@bot.message_handler(content_types=["location"])
def on_location(message):
    user_id = message.from_user.id
    if not is_registered(user_id):
        bot.send_message(message.chat.id, "اول ثبت‌نام کن.")
        return
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET lat=%s, lon=%s WHERE user_id=%s",
                (message.location.latitude, message.location.longitude, user_id))
    conn.commit()
    cur.close(); conn.close()
    bot.send_message(message.chat.id, "📍 موقعیت ثبت شد.")
    find_nearby(message.chat.id, user_id)


@bot.message_handler(content_types=["text"])
def on_text(message):
    user_id = message.from_user.id
    text = (message.text or "").strip()
    state = user_states.get(user_id)
    if state:
        step = state["step"]
        if step == "nickname":
            state["nickname"] = text[:50]
            state["step"] = "age"
            bot.send_message(message.chat.id, "چند سالته؟ (۱۸+)")
            return
        if step == "age":
            try:
                age = int(text)
            except ValueError:
                bot.send_message(message.chat.id, "سن رو عدد بنویس.")
                return
            if age < 18:
                bot.send_message(message.chat.id, "فقط ۱۸ سال به بالا.")
                return
            state["age"] = age
            state["step"] = "gender"
            kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            kb.row("پسر", "دختر")
            bot.send_message(message.chat.id, "جنسیتت؟", reply_markup=kb)
            return
        if step == "gender":
            state["gender"] = text
            state["step"] = "city"
            bot.send_message(message.chat.id, "شهرت؟", reply_markup=types.ReplyKeyboardRemove())
            return
        if step == "city":
            state["city"] = text[:50]
            state["step"] = "bio"
            bot.send_message(message.chat.id, "بیو کوتاه:")
            return
        if step == "bio":
            state["bio"] = text[:300]
            finish_registration(user_id)
            return
    if report_states.get(user_id, {}).get("step") == "support":
        forward_support(message)
        return
    if text == "🔎 پیدا کردن افراد":
        find_nearby(message.chat.id, user_id)
    elif text == "👤 پروفایل من":
        show_profile(message.chat.id, user_id)
    elif text == "❤️ مچ‌های من":
        show_matches(message.chat.id, user_id)
    elif text == "⭐ ستاره‌های من":
        show_stars(message.chat.id, user_id)
    elif text == "🔗 دعوت دوستان":
        show_referral(message.chat.id, user_id)
    elif text == "⚙️ تنظیمات":
        show_settings(message.chat.id, user_id)
    elif text == "☎️ پشتیبانی":
        start_support(user_id, message.chat.id)
    elif relay_message(message):
        return
    else:
        bot.send_message(message.chat.id, "از منو انتخاب کن یا /start.", reply_markup=main_menu())


@bot.callback_query_handler(func=lambda call: True)
def on_callback(call):
    data = call.data or ""
    user_id = call.from_user.id
    chat_id = call.message.chat.id if call.message else user_id
    if data.startswith("like:"):
        handle_like(user_id, int(data.split(":")[1]), chat_id)
    elif data.startswith("pass:"):
        handle_pass(user_id, int(data.split(":")[1]), chat_id)
    elif data.startswith("block:"):
        block_user(user_id, int(data.split(":")[1]), chat_id)
    elif data.startswith("report:"):
        target_id = int(data.split(":")[1])
        report_states[user_id] = {"step": "report", "target_id": target_id}
        bot.send_message(chat_id, "دلیل گزارش رو بنویس:")
    elif data.startswith("chat:"):
        start_chat(user_id, int(data.split(":")[1]), chat_id)
    elif data.startswith("buy:"):
        bot.send_message(chat_id, "خرید ستاره فعلاً فعال نیست.")
    elif data == "privacy:profile":
        toggle_privacy(user_id, chat_id, "profile_visible")
    elif data == "privacy:location":
        toggle_privacy(user_id, chat_id, "location_visible")
    elif data == "delete:ask":
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("✅ بله", callback_data="delete:yes"))
        kb.add(types.InlineKeyboardButton("❌ انصراف", callback_data="delete:no"))
        bot.send_message(chat_id, "مطمئنی می‌خوای حسابت حذف بشه؟", reply_markup=kb)
    elif data == "delete:yes":
        delete_user_account(user_id, chat_id)
    elif data == "delete:no":
        bot.send_message(chat_id, "لغو شد.")


@app.route("/")
@app.route("/health")
def health():
    return "OK", 200


def run_bot():
    try:
        init_db()
        logger.info("DB initialized")
    except Exception as e:
        logger.error("DB init failed: %s", e)
    while True:
        try:
            bot.infinity_polling(timeout=30, long_polling_timeout=25)
        except Exception as e:
            logger.error("Polling error: %s", e)
            import time
            time.sleep(5)


if __name__ == "__main__":
    t = threading.Thread(target=run_bot, daemon=True)
    t.start()
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
