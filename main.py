
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


# =========================
# DATABASE
# =========================

def get_db():
    return psycopg2.connect(
        DATABASE_URL,
        sslmode="require",
        cursor_factory=RealDictCursor
    )


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


# =========================
# KEYBOARDS
# =========================

def main_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("🔎 پیدا کردن افراد", "👤 پروفایل من")
    kb.row("❤️ مچ‌های من", "⭐ ستاره‌های من")
    kb.row("🔗 دعوت دوستان", "⚙️ تنظیمات")
    kb.row("📍 ارسال موقعیت")
    return kb


def send_home(chat_id, text="به گپ‌میت خوش اومدی ❤️"):
    bot.send_message(chat_id, text, reply_markup=main_menu())


def profile_keyboard(target_id):
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton(
            "❤️ لایک",
            callback_data=f"like:{target_id}"
        ),
        types.InlineKeyboardButton(
            "👎 رد",
            callback_data=f"pass:{target_id}"
        )
    )
    kb.row(
        types.InlineKeyboardButton(
            "🚫 مسدود کردن",
            callback_data=f"block:{target_id}"
        ),
        types.InlineKeyboardButton(
            "⚠️ گزارش",
            callback_data=f"report:{target_id}"
        )
    )
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
        cur.execute("""
            SELECT user_id FROM users WHERE user_id=%s
        """, (referrer_id,))
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
                    UPDATE users
                    SET stars = stars + 10
                    WHERE user_id=%s
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
# PROFILE
# =========================

def show_profile(chat_id, user_id):
    user = get_user(user_id)

    if not user:
        bot.send_message(chat_id, "هنوز ثبت‌نام نکردی.")
        return

    nickname = escape(user["nickname"] or "")
    city = escape(user["city"] or "نامشخص")
    bio = escape(user["bio"] or "بدون توضیحات")

    text = (
        f"👤 نام: {nickname}\n"
        f"🎂 سن: {user['age']}\n"
        f"⚧ جنسیت: {escape(user['gender'] or '')}\n"
        f"📍 شهر: {city}\n\n"
        f"📝 درباره من:\n{bio}"
    )

    bot.send_message(chat_id, text)


def show_stars(chat_id, user_id):
    user = get_user(user_id)
    if not user:
        return

    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton(
            "⭐ خرید ۱۰ ستاره",
            callback_data="buy:10"
        )
    )
    kb.add(
        types.InlineKeyboardButton(
            "⭐ خرید ۵۰ ستاره",
            callback_data="buy:50"
        )
    )

    bot.send_message(
        chat_id,
        f"موجودی ستاره‌های تو: ⭐ {user['stars']}",
        reply_markup=kb
    )


def show_settings(chat_id, user_id):
    user = get_user(user_id)
    if not user:
        return

    kb = types.InlineKeyboardMarkup()

    kb.add(types.InlineKeyboardButton(
        "تغییر نمایش پروفایل",
        callback_data="privacy:profile"
    ))

    kb.add(types.InlineKeyboardButton(
        "تغییر نمایش موقعیت",
        callback_data="privacy:location"
    ))

    kb.add(types.InlineKeyboardButton(
        "🗑 حذف حساب کاربری",
        callback_data="delete:account"
    ))

    bot.send_message(
        chat_id,
        "⚙️ تنظیمات حریم خصوصی:",
        reply_markup=kb
    )


def show_referral(chat_id, user_id):
    me = bot.get_me()
    link = f"https://t.me/{me.username}?start=ref_{user_id}"

    bot.send_message(
        chat_id,
        "🔗 لینک دعوت اختصاصی تو:\n"
        f"{link}\n\n"
        "با ثبت‌نام هر دوست از طریق لینک تو، "
        "۱۰ ستاره هدیه می‌گیری."
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

    return radius * 2 * math.atan2(
        math.sqrt(a),
        math.sqrt(1 - a)
    )


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
        AND (
            lat IS NOT NULL
            AND lon IS NOT NULL
        )
        AND user_id NOT IN (
            SELECT target_id FROM passes WHERE user_id=%s
        )
        AND user_id NOT IN (
            SELECT target_id FROM likes WHERE user_id=%s
        )
        AND user_id NOT IN (
            SELECT blocked_id FROM blocks WHERE user_id=%s
        )
        AND user_id NOT IN (
            SELECT user_id FROM blocks WHERE blocked_id=%s
        )
        AND user_id NOT IN (
            SELECT user2 FROM matches WHERE user1=%s
            UNION
            SELECT user1 FROM matches WHERE user2=%s
        )
    """, (
        user_id,
        user_id,
        user_id,
        user_id,
        user_id,
        user_id,
        user_id
    ))

    candidates = cur.fetchall()
    cur.close()
    conn.close()

    candidates = sorted(
        candidates,
        key=lambda person: distance_km(
            user["lat"],
            user["lon"],
            person["lat"],
            person["lon"]
        )
    )

    if not candidates:
        bot.send_message(
            chat_id,
            "فعلاً فرد جدیدی پیدا نشد. بعداً دوباره امتحان کن."
        )
        return

    person = candidates[0]
    show_person(chat_id, person)


def show_person(chat_id, person):
    nickname = escape(person["nickname"] or "")
    city = escape(person["city"] or "نامشخص")
    bio = escape(person["bio"] or "بدون توضیحات")

    text = (
        f"👤 {nickname}\n"
        f"🎂 {person['age']} سال\n"
        f"📍 {city}\n\n"
        f"📝 {bio}"
    )

    bot.send_message(
        chat_id,
        text,
        reply_markup=profile_keyboard(person["user_id"])
    )


# =========================
# LIKE / PASS / MATCH
# =========================

def handle_like(user_id, target_id, chat_id):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT 1 FROM blocks
        WHERE (user_id=%s AND blocked_id=%s)
        OR (user_id=%s AND blocked_id=%s)
    """, (user_id, target_id, target_id, user_id))

    if cur.fetchone():
        conn.close()
        bot.send_message(chat_id, "امکان ارتباط با این کاربر وجود ندارد.")
        return

    cur.execute("""
        INSERT INTO likes (user_id, target_id)
        VALUES (%s, %s)
        ON CONFLICT DO NOTHING
    """, (user_id, target_id))

    cur.execute("""
        SELECT 1 FROM likes
        WHERE user_id=%s AND target_id=%s
    """, (target_id, user_id))

    matched = cur.fetchone() is not None

    if matched:
        first, second = sorted([user_id, target_id])

        cur.execute("""
            INSERT INTO matches (user1, user2)
            VALUES (%s, %s)
            ON CONFLICT DO NOTHING
        """, (first, second))

    conn.commit()
    cur.close()
    conn.close()

    if matched:
        bot.send_message(
            user_id,
            "🎉 مچ شدین! هر دو نفر همدیگه رو لایک کردین."
        )
        try:
            bot.send_message(
                target_id,
                "🎉 یک مچ جدید داری! هر دو نفر همدیگه رو لایک کردین."
            )
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
        VALUES (%s, %s)
        ON CONFLICT DO NOTHING
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
        SELECT u.*
        FROM matches m
        JOIN users u
        ON u.user_id = CASE
            WHEN m.user1=%s THEN m.user2
            ELSE m.user1
        END
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
            "💬 شروع چت",
            callback_data=f"chat:{person['user_id']}"
        ))

        bot.send_message(
            chat_id,
            f"❤️ {escape(person['nickname'] or '')} "
            f"({person['age']} سال)",
            reply_markup=kb
        )


def start_chat(user_id, target_id, chat_id):
    first, second = sorted([user_id, target_id])

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT 1 FROM matches
        WHERE user1=%s AND user2=%s
    """, (first, second))

    if not cur.fetchone():
        cur.close()
        conn.close()
        bot.send_message(chat_id, "ابتدا باید با این شخص مچ شده باشی.")
        return

    cur.execute("""
        SELECT 1 FROM blocks
        WHERE (user_id=%s AND blocked_id=%s)
        OR (user_id=%s AND blocked_id=%s)
    """, (user_id, target_id, target_id, user_id))

    if cur.fetchone():
        cur.close()
        conn.close()
        bot.send_message(chat_id, "امکان شروع چت وجود ندارد.")
        return

    cur.execute("""
        INSERT INTO chat_sessions (user1, user2, active)
        VALUES (%s, %s, TRUE)
        ON CONFLICT (user1, user2)
        DO UPDATE SET active=TRUE
    """, (first, second))

    conn.commit()
    cur.close()
    conn.close()

    bot.send_message(
        user_id,
        "💬 چت شروع شد! پیام‌هات رو بفرست.\n"
        "برای پایان چت /stopchat رو بزن."
    )

    try:
        bot.send_message(
            target_id,
            "💬 چت شروع شد! پیام‌هات رو بفرست.\n"
            "برای پایان چت /stopchat رو بزن."
        )
    except Exception:
        pass


def stop_chat(user_id, chat_id):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        UPDATE chat_sessions
        SET active=FALSE
        WHERE (user1=%s OR user2=%s)
        AND active=TRUE
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
        other = (
            session["user2"]
            if session["user1"] == user_id
            else session["user1"]
        )

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
        WHERE active=TRUE
        AND (user1=%s OR user2=%s)
        LIMIT 1
    """, (user_id, user_id))

    session = cur.fetchone()
    cur.close()
    conn.close()

    if not session:
        return False

    other = (
        session["user2"]
        if session["user1"] == user_id
        else session["user1"]
    )

    try:
        bot.copy_message(
            other,
            message.chat.id,
            message.message_id
        )
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
        VALUES (%s, %s)
        ON CONFLICT DO NOTHING
    """, (user_id, target_id))

    first, second = sorted([user_id, target_id])

    cur.execute("""
        UPDATE chat_sessions
        SET active=FALSE
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


def delete_user_account(user_id, chat_id):
    conn = get_db()
    cur = conn.cursor()

    tables = [
        ("likes", "user_id", "target_id"),
        ("passes", "user_id", "target_id"),
        ("matches", "user1", "user2"),
        ("blocks", "user_id", "blocked_id"),
        ("chat_sessions", "user1", "user2"),
        ("referrals", "referrer_id", "referred_id")
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
    if not ADMIN_ID or str(user_id) != str(ADMIN_ID):
        bot.send_message(chat_id, "اجازه دسترسی نداری.")
        return

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT * FROM reports
        ORDER BY created_at DESC
        LIMIT 30
    """)

    reports = cur.fetchall()
    cur.close()
    conn.close()

    if not reports:
        bo
