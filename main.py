import os
import math
import logging
import threading
from html import escape

import telebot
from telebot import types
from flask import Flask, request
import psycopg2
from psycopg2.extras import RealDictCursor


# =========================
# SETTINGS
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_ID = os.getenv("ADMIN_ID")
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")

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

# وضعیت چت: هر کاربر فقط یک چت فعال (برای جلوگیری از ارسال به مخاطب اشتباه)
# این تصمیم معماری است؛ اگر می‌خواهی چند چت هم‌زمان باشد، باید تغییر کند.
# فعلاً: هر کاربر فقط یک سشن فعال.


# =========================
# DATABASE
# =========================

def get_db():
    return psycopg2.connect(
        DATABASE_URL,
        sslmode="require",
        cursor_factory=RealDictCursor
    )


def ensure_columns(cur):
    """
    ستون‌های گم‌شده را فقط اضافه می‌کند. هیچ ستونی را حذف یا نوعش را تغییر نمی‌دهد.
    این تابع برای سازگاری با دیتابیس قدیمی است.
    """
    additions = [
        ("users", "nickname", "TEXT"),
        ("users", "age", "INTEGER"),
        ("users", "gender", "TEXT"),
        ("users", "city", "TEXT"),
        ("users", "bio", "TEXT"),
        ("users", "lat", "DOUBLE PRECISION"),
        ("users", "lon", "DOUBLE PRECISION"),
        ("users", "stars", "INTEGER DEFAULT 0"),
        ("users", "profile_visible", "BOOLEAN DEFAULT TRUE"),
        ("users", "location_visible", "BOOLEAN DEFAULT TRUE"),
        ("users", "created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
    ]
    for table, col, coltype in additions:
        try:
            cur.execute(
                f'ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {coltype}'
            )
        except Exception as e:
            logger.warning("ALTER TABLE %s ADD COLUMN %s failed: %s", table, col, e)


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            nickname TEXT,
            age INTEGER,
            gender TEXT,
            city TEXT,
            bio TEXT,
            lat DOUBLE PRECISION,
            lon DOUBLE PRECISION,
            stars INTEGER DEFAULT 0,
            profile_visible BOOLEAN DEFAULT TRUE,
            location_visible BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS likes (
            user_id BIGINT,
            target_id BIGINT,
            PRIMARY KEY (user_id, target_id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS passes (
            user_id BIGINT,
            target_id BIGINT,
            PRIMARY KEY (user_id, target_id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS matches (
            user1 BIGINT,
            user2 BIGINT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user1, user2)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS blocks (
            user_id BIGINT,
            blocked_id BIGINT,
            PRIMARY KEY (user_id, blocked_id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id SERIAL PRIMARY KEY,
            reporter_id BIGINT,
            target_id BIGINT,
            reason TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS chat_sessions (
            user1 BIGINT,
            user2 BIGINT,
            active BOOLEAN DEFAULT TRUE,
            PRIMARY KEY (user1, user2)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS referrals (
            referrer_id BIGINT,
            referred_id BIGINT UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS star_payments (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            amount INTEGER,
            currency TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    ensure_columns(cur)

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


# =========================
# KEYBOARDS
# =========================

def main_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("🔎 پیدا کردن افراد", "👤 پروفایل من")
    kb.row("❤️ مچ‌های من", "⭐ ستاره‌های من")
    kb.row("🔗 دعوت دوستان", "⚙️ تنظیمات")
    kb.row("📍 ارسال موقعیت", "☎️ پشتیبانی")
    return kb


def send_home(chat_id, text="به گپ‌میت خوش اومدی ❤️"):
    bot.send_message(chat_id, text, reply_markup=main_menu())


def profile_keyboard(target_id):
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("❤️ لایک", callback_data=f"like:{target_id}"),
        types.InlineKeyboardButton("👎 رد", callback_data=f"pass:{target_id}")
    )
    kb.row(
        types.InlineKeyboardButton("🚫 مسدود کردن", callback_data=f"block:{target_id}"),
        types.InlineKeyboardButton("⚠️ گزارش", callback_data=f"report:{target_id}")
    )
    return kb


def settings_keyboard():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("تغییر نمایش پروفایل", callback_data="privacy:profile"))
    kb.add(types.InlineKeyboardButton("تغییر نمایش موقعیت", callback_data="privacy:location"))
    kb.add(types.InlineKeyboardButton("🗑 حذف حساب کاربری", callback_data="delete:ask"))
    return kb


# =========================
# REGISTRATION
# =========================

def start_registration(message, referral_id=None):
    user_id = message.from_user.id

    user_states[user_id] = {
        "step": "nickname",
        "referral_id": referral_id
    }

    bot.send_message(
        message.chat.id,
        "سلام! به گپ‌میت خوش اومدی ❤️\n\n"
        "برای شروع، چه اسمی برات نمایش بدیم؟"
    )


def finish_registration(user_id):
    data = user_states.get(user_id)
    if not data:
        return

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO users (
            user_id, nickname, age, gender, city, bio, stars
        )
        VALUES (%s, %s, %s, %s, %s, %s, 6)
        ON CONFLICT (user_id) DO UPDATE SET
            nickname=EXCLUDED.nickname,
            age=EXCLUDED.age,
            gender=EXCLUDED.gender,
            city=EXCLUDED.city,
            bio=EXCLUDED.bio
    """, (
        user_id,
        data["nickname"],
        data["age"],
        data["gender"],
        data["city"],
        data["bio"]
    ))

    referrer_id = data.get("referral_id")

    if referrer_id and referrer_id != user_id:
        cur.execute("SELECT user_id FROM users WHERE user_id=%s", (referrer_id,))
        referrer = cur.fetchone()

        if referrer:
            cur.execute("""
                INSERT INTO referrals (referrer_id, referred_id)
                VALUES (%s, %s)
                ON CONFLICT (referred_id) DO NOTHING
                RETURNING referred_id
            """, (referrer_id, user_id))

            if cur.fetchone():
                cur.execute("""
                    UPDATE users SET stars = stars + 10 WHERE user_id=%s
                """, (referrer_id,))

                try:
                    bot.send_message(
                        referrer_id,
                        "🎉 یک نفر با لینک دعوت تو ثبت‌نام کرد!\n"
                        "۱۰ ستاره به حسابت اضافه شد."
                    )
                except Exception:
                    pass

    conn.commit()
    cur.close()
    conn.close()

    user_states.pop(user_id, None)

    bot.send_message(
        user_id,
        "🎉 پروفایلت ساخته شد!\n"
        "۶ ستاره هدیه ثبت‌نام بهت تعلق گرفت.",
        reply_markup=main_menu()
    )


# =========================
# PROFILE / SETTINGS / STARS / REFERRAL
# =========================

def show_profile(chat_id, user_id):
    user = get_user(user_id)
    if not user:
        bot.send_message(chat_id, "هنوز ثبت‌نام نکردی.")
        return

    text = (
        f"👤 نام: {escape(user['nickname'] or '')}\n"
        f"🎂 سن: {user['age']}\n"
        f"⚧ جنسیت: {escape(user['gender'] or '')}\n"
        f"📍 شهر: {escape(user['city'] or 'نامشخص')}\n\n"
        f"📝 درباره من:\n{escape(user['bio'] or 'بدون توضیحات')}"
    )
    bot.send_message(chat_id, text)


def show_stars(chat_id, user_id):
    user = get_user(user_id)
    if not user:
        return

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("⭐ خرید ۱۰ ستاره", callback_data="buy:10"))
    kb.add(types.InlineKeyboardButton("⭐ خرید ۵۰ ستاره", callback_data="buy:50"))

    bot.send_message(
        chat_id,
        f"موجودی ستاره‌های تو: ⭐ {user['stars']}",
        reply_markup=kb
    )


def show_settings(chat_id, user_id):
    if not get_user(user_id):
        return
    bot.send_message(chat_id, "⚙️ تنظیمات حریم خصوصی:", reply_markup=settings_keyboard())


def show_referral(chat_id, user_id):
    me = bot.get_me()
    link = f"https://t.me/{me.username}?start=ref_{user_id}"
    bot.send_message(
        chat_id,
        "🔗 لینک دعوت اختصاصی تو:\n"
        f"{link}\n\n"
        "با ثبت‌نام هر دوست از طریق لینک تو، ۱۰ ستاره هدیه می‌گیری."
    )


# =========================
# DISTANCE AND SEARCH
# =========================

def distance_km(lat1, lon1, lat2, lon2):
    radius = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def find_nearby(chat_id, user_id):
    user = get_user(user_id)
    if not user:
        return

    if user["lat"] is None or user["lon"] is None:
        bot.send_message(
            chat_id,
            "برای پیدا کردن افراد نزدیک، اول موقعیتت رو ارسال کن.",
            reply_markup=main_menu()
        )
        return

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM users
        WHERE user_id != %s
        AND nickname IS NOT NULL
        AND profile_visible = TRUE
        AND lat IS NOT NULL
        AND lon IS NOT NULL
        AND user_id NOT IN (SELECT target_id FROM passes WHERE user_id=%s)
        AND user_id NOT IN (SELECT target_id FROM likes WHERE user_id=%s)
        AND user_id NOT IN (SELECT blocked_id FROM blocks WHERE user_id=%s)
        AND user_id NOT IN (SELECT user_id FROM blocks WHERE blocked_id=%s)
        AND user_id NOT IN (
            SELECT user2 FROM matches WHERE user1=%s
            UNION
            SELECT user1 FROM matches WHERE user2=%s
        )
    """, (user_id, user_id, user_id, user_id, user_id, user_id, user_id))

    candidates = cur.fetchall()
    cur.close()
    conn.close()

    candidates = sorted(
        candidates,
        key=lambda p: distance_km(user["lat"], user["lon"], p["lat"], p["lon"])
    )

    if not candidates:
        bot.send_message(chat_id, "فعلاً فرد جدیدی پیدا نشد. بعداً دوباره امتحان کن.")
        return

    show_person(chat_id, candidates[0])


def show_person(chat_id, person):
    text = (
        f"👤 {escape(person['nickname'] or '')}\n"
        f"🎂 {person['age']} سال\n"
        f"📍 {escape(person['city'] or 'نامشخص')}\n\n"
        f"📝 {escape(person['bio'] or 'بدون توضیحات')}"
    )
    bot.send_message(chat_id, text, reply_markup=profile_keyboard(person["user_id"]))


# =========================
# LIKE / PASS / MATCH
# =========================

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
        WHERE (user_id=%s AND blocked_id=%s)
        OR (user_id=%s AND blocked_id=%s)
    """, (user_id, target_id, target_id, user_id))
    if cur.fetchone():
        cur.close(); conn.close()
        bot.send_message(chat_id, "امکان ارتباط با این کاربر وجود ندارد.")
        return

    cur.execute("""
        INSERT INTO likes (user_id, target_id)
        VALUES (%s, %s) ON CONFLICT DO NOTHING
    """, (user_id, target_id))

    cur.execute("SELECT 1 FROM likes WHERE user_id=%s AND target_id=%s",
                (target_id, user_id))
    matched = cur.fetchone() is not None

    if matched:
        first, second = sorted([user_id, target_id])
        cur.execute("""
            INSERT INTO matches (user1, user2)
            VALUES (%s, %s) ON CONFLICT DO NOTHING
        """, (first, second))

    conn.commit()
    cur.close()
    conn.close()

    if matched:
        bot.send_message(user_id, "🎉 مچ شدین! هر دو نفر همدیگه رو لایک کردین.")
        try:
            bot.send_message(target_id, "🎉 یک مچ جدید داری! هر دو نفر همدیگه رو لایک کردین.")
        except Exception:
            pass
    else:
        bot.send_message(chat_id, "❤️ لایکت ثبت شد.")

    find_nearby(chat_id, user_id)


def handle_pass(user_id, target_id, chat_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO passes (user_id, target_id)
        VALUES (%s, %s) ON CONFLICT DO NOTHING
    """, (user_id, target_id))
    conn.commit()
    cur.close()
    conn.close()

    bot.send_message(chat_id, "این پروفایل رد شد.")
    find_nearby(chat_id, user_id)


# =========================
# MATCHES AND CHAT
# =========================

def show_matches(chat_id, user_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT u.* FROM matches m
        JOIN users u ON u.user_id = CASE
            WHEN m.user1=%s THEN m.user2 ELSE m.user1 END
        WHERE m.user1=%s OR m.user2=%s
    """, (user_id, user_id, user_id))
    people = cur.fetchall()
    cur.close()
    conn.close()

    if not people:
        bot.send_message(chat_id, "هنوز مچی نداری ❤️")
        return

    for person in people:
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton(
            "💬 شروع چت", callback_data=f"chat:{person['user_id']}"
        ))
        bot.send_message(
            chat_id,
            f"❤️ {escape(person['nickname'] or '')} ({person['age']} سال)",
            reply_markup=kb
        )


def start_chat(user_id, target_id, chat_id):
    first, second = sorted([user_id, target_id])

    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT 1 FROM matches WHERE user1=%s AND user2=%s", (first, second))
    if not cur.fetchone():
        cur.close(); conn.close()
        bot.send_message(chat_id, "ابتدا باید با این شخص مچ شده باشی.")
        return

    cur.execute("""
        SELECT 1 FROM blocks
        WHERE (user_id=%s AND blocked_id=%s)
        OR (user_id=%s AND blocked_id=%s)
    """, (user_id, target_id, target_id, user_id))
    if cur.fetchone():
        cur.close(); conn.close()
        bot.send_message(chat_id, "امکان شروع چت وجود ندارد.")
        return

    # چک: آیا هر یک از دو طرف از قبل چت فعال دیگری دارد؟
    cur.execute("""
        SELECT user1, user2 FROM chat_sessions
        WHERE active=TRUE
        AND (user1 IN (%s, %s) OR user2 IN (%s, %s))
    """, (user_id, target_id, user_id, target_id))
    existing = cur.fetchone()
    if existing and (existing["user1"], existing["user2"]) != (first, second):
        cur.close(); conn.close()
        bot.send_message(
            chat_id,
            "یکی از طرفین چت فعال دیگری دارد. اول آن را پایان دهید."
        )
        return

    cur.execute("""
        INSERT INTO chat_sessions (user1, user2, active)
        VALUES (%s, %s, TRUE)
        ON CONFLICT (user1, user2) DO UPDATE SET active=TRUE
    """, (first, second))

    conn.commit()
    cur.close()
    conn.close()

    bot.send_message(
        user_id,
        "💬 چت شروع شد! پیام‌هات رو بفرست.\nبرای پایان چت /stopchat رو بزن."
    )
    try:
        bot.send_message(
            target_id,
            "💬 چت شروع شد! پیام‌هات رو بفرست.\nبرای پایان چت /stopchat رو بزن."
        )
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
    cur.close()
    conn.close()

    if not sessions:
        bot.send_message(chat_id, "چت فعالی نداری.")
        return

    bot.send_message(chat_id, "چت پایان یافت.")

    for session in sessions:
        other = session["user2"] if session["user1"] == user_id else session["user1"]
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
        WHERE active=TRUE AND (user1=%s OR user2=%s)
        LIMIT 1
    """, (user_id, user_id))
    session = cur.fetchone()
    cur.close()
    conn.close()

    if not session:
        return False

    other = session["user2"] if session["user1"] == user_id else session["user1"]

    # چک بلاک قبل از ارسال
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT 1 FROM blocks
        WHERE (user_id=%s AND blocked_id=%s)
        OR (user_id=%s AND blocked_id=%s)
    """, (user_id, other, other, user_id))
    blocked = cur.fetchone() is not None
    cur.close()
    conn.close()

    if blocked:
        bot.send_message(message.chat.id, "امکان ارسال پیام به این کاربر وجود ندارد.")
        return True

    try:
        bot.copy_message(other, message.chat.id, message.message_id)
        return True
    except Exception:
        bot.send_message(
            message.chat.id,
            "ارسال پیام انجام نشد. ممکنه طرف مقابل ربات رو مسدود کرده باشه."
        )
        return True


# =========================
# BLOCK / REPORT / DELETE
# =========================

def block_user(user_id, target_id, chat_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO blocks (user_id, blocked_id)
        VALUES (%s, %s) ON CONFLICT DO NOTHING
    """, (user_id, target_id))

    first, second = sorted([user_id, target_id])
    cur.execute("""
        UPDATE chat_sessions SET active=FALSE
        WHERE user1=%s AND user2=%s
    """, (first, second))

    conn.commit()
    cur.close()
    conn.close()
    bot.send_message(chat_id, "🚫 این کاربر مسدود شد.")


def report_user(user_id, target_id, reason, chat_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO reports (reporter_id, target_id, reason)
        VALUES (%s, %s, %s)
    """, (user_id, target_id, reason))
    conn.commit()
    cur.close()
    conn.close()

    bot.send_message(chat_id, "گزارش تو ثبت شد. ممنون از اطلاعت.")

    if is_admin_allowed():
        try:
            bot.send_message(
                ADMIN_ID,
                f"⚠️ گزارش جدید:\n"
                f"از: {user_id}\nبه: {target_id}\nدلیل: {escape(reason)}"
            )
        except Exception:
            pass


def is_admin_allowed():
    return bool(ADMIN_ID)


def delete_user_account(user_id, chat_id):
    conn = get_db()
    cur = conn.cursor()

    tables = [
        ("likes", "user_id", "target_id"),
        ("passes", "user_id", "target_id"),
        ("matches", "user1", "user2"),
        ("blocks", "user_id", "blocked_id"),
        ("chat_sessions", "user1", "user2"),
        ("referrals", "referrer_id", "referred_id"),
    ]
    for table, col1, col2 in tables:
        cur.execute(
            f"DELETE FROM {table} WHERE {col1}=%s OR {col2}=%s",
            (user_id, user_id)
        )

    cur.execute(
        "DELETE FROM reports WHERE reporter_id=%s OR target_id=%s",
        (user_id, user_id)
    )
    cur.execute("DELETE FROM users WHERE user_id=%s", (user_id,))

    conn.commit()
    cur.close()
    conn.close()

    user_states.pop(user_id, None)
    report_states.pop(user_id, None)

    bot.send_message(
        chat_id,
        "حساب کاربری و اطلاعات پروفایلت حذف شد.",
        reply_markup=types.ReplyKeyboardRemove()
    )


def show_admin_reports(chat_id, user_id):
    if not is_admin(user_id):
        bot.send_message(chat_id, "اجازه دسترسی نداری.")
        return

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM reports ORDER BY created_at DESC LIMIT 30
    """)
    reports = cur.fetchall()
    cur.close()
    conn.close()

    if not reports:
        bot.send_message(chat_id, "گزارشی ثبت نشده.")
        return

    for r in reports:
        bot.send_message(
            chat_id,
            f"#{r['id']} | از {r['reporter_id']} به {r['target_id']}\n"
            f"دلیل: {escape(r['reason'] or '')}\n"
            f"زمان: {r['created_at']}"
        )


# =========================
# SUPPORT
# =========================

def start_support(user_id, chat_id):
    report_states[user_id] = {"step": "support"}
    bot.send_message(chat_id, "☎️ پیامت برای پشتیبانی رو بنویس. برای انصراف /cancel رو بزن.")


def forward_support(message):
    user_id = message.from_user.id
    if not is_admin_allowed():
        bot.send_message(message.chat.id, "پشتیبانی فعلاً فعال نیست.")
        report_states.pop(user_id, None)
        return
    try:
        bot.send_message(
            ADMIN_ID,
            f"📩 پیام پشتیبانی از {user_id}:\n{escape(message.text or '')}"
        )
        bot.send_message(message.chat.id, "پیامت برای پشتیبانی ارسال شد.")
    except Exception:
        bot.send_message(message.chat.id, "ارسال نشد.")
    report_states.pop(user_id, None)


# =========================
# HANDLERS
# =========================

@bot.message_handler(commands=["start"])
def cmd_start(message):
    user_id = message.from_user.id
    text = message.text or ""
    parts = text.split()
    referral_id = None
    if len(parts) > 1 and parts[1].startswith("ref_"):
        try:
            referral_id = int(parts[1][4:])
        except ValueError:
            referral_id = None

    if is_registered(user_id):
        send_home(message.chat.id, "خوش برگشتی ❤️")
        return

    start_registration(message, referral_id)


@bot.message_handler(commands=["stopchat"])
def cmd_stopchat(message):
    stop_chat(message.from_user.id, message.chat.id)


@bot.message_handler(commands=["cancel"])
def cmd_cancel(message):
    user_id = message.from_user.id
    user_states.pop(user_id, None)
    report_states.pop(user_id, None)
    send_home(message.chat.id, "لغو شد.")


@bot.message_handler(commands=["admin"])
def cmd_admin(message):
    show_admin_reports(message.chat.id, message.from_user.id)


@bot.message_handler(content_types=["location"])
def on_location(message):
    user_id = message.from_user.id
    if not is_registered(user_id):
        bot.send_message(message.chat.id, "اول ثبت‌نام کن.")
        return
    lat = message.location.latitude
    lon = message.location.longitude
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET lat=%s, lon=%s WHERE user_id=%s", (lat, lon, user_id))
    conn.commit()
    cur.close()
    conn.close()
    bot.send_message(message.chat.id, "📍 موقعیتت ثبت شد.")
    find_nearby(message.chat.id, user_id)


@bot.message_handler(content_types=["text"])
def on_text(message):
    user_id = message.from_user.id
    text = (message.text or "").strip()

    # ثبت‌نام در جریان
    state = user_states.get(user_id)
    if state:
        step = state["step"]
        if step == "nickname":
            state["nickname"] = text[:50]
            state["step"] = "age"
            bot.send_message(message.chat.id, "چند سالته؟ (۱۸ سال به بالا)")
            return
        if step == "age":
            try:
                age = int(text)
            except ValueError:
                bot.send_message(message.chat.id, "لطفاً سن رو عدد بنویس.")
                return
            if age < 18:
                bot.send_message(message.chat.id, "ورود فقط برای ۱۸ سال به بالا مجازه.")
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
            bot.send_message(message.chat.id, "یک بیو کوتاه بنویس:")
            return
        if step == "bio":
            state["bio"] = text[:300]
            finish_registration(user_id)
            return

    # پشتیبانی در جریان
    if report_states.get(user_id, {}).get("step") == "support":
        forward_support(message)
        return

    # دکمه‌های منو
    if text == "🔎 پیدا کردن افراد":
        find_nearby(message.chat.id, user_id)
        return
    if text == "👤 پروفایل من":
        show_profile(message.chat.id, user_id)
        return
    if text == "❤️ مچ‌های من":
        show_matches(message.chat.id, user_id)
        return
    if text == "⭐ ستاره‌های من":
        show_stars(message.chat.id, user_id)
        return
    if text == "🔗 دعوت دوستان":
        show_referral(message.chat.id, user_id)
        return
    if text == "⚙️ تنظیمات":
        show_settings(message.chat.id, user_id)
        return
    if text == "☎️ پشتیبانی":
        start_support(user_id, message.chat.id)
        return

    # پیام چت
    if relay_message(message):
        return

    send_home(message.chat.id, "از منو یکی رو انتخاب کن یا /start رو بزن.")


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
    elif data == "privacy:profile":
        toggle_privacy(user_id, chat_id, "profile_visible")
    elif data == "privacy:location":
        toggle_privacy(user_id, chat_id, "location_visible")
    elif data == "delete:ask":
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("✅ بله، حذف کن", callback_data="delete:yes"))
        kb.add(types.InlineKeyboardButton("❌ انصراف", callback_data="delete:no"))
        bot.send_message(chat_id, "مط
