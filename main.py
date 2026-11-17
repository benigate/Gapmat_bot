
import os
import math
import logging
from contextlib import contextmanager

import telebot
from telebot import types
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, request


# =========================
# تنظیمات اولیه
# =========================

BOT_TOKEN = os.environ["BOT_TOKEN"]
DATABASE_URL = os.environ["DATABASE_URL"]
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "").rstrip("/")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

registration = {}


# =========================
# اتصال دیتابیس
# =========================

@contextmanager
def get_db():
    conn = psycopg2.connect(
        DATABASE_URL,
        cursor_factory=RealDictCursor,
        sslmode="require"
    )
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        with conn.cursor() as cur:

            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    telegram_id BIGINT PRIMARY KEY,
                    nickname TEXT,
                    age INTEGER,
                    gender TEXT,
                    city TEXT,
                    latitude DOUBLE PRECISION,
                    longitude DOUBLE PRECISION,
                    location_visible BOOLEAN DEFAULT FALSE,
                    profile_visible BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cur.execute("""
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS latitude DOUBLE PRECISION
            """)
            cur.execute("""
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS longitude DOUBLE PRECISION
            """)
            cur.execute("""
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS location_visible BOOLEAN DEFAULT FALSE
            """)
            cur.execute("""
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS profile_visible BOOLEAN DEFAULT TRUE
            """)
            cur.execute("""
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS nickname TEXT
            """)
            cur.execute("""
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS age INTEGER
            """)
            cur.execute("""
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS gender TEXT
            """)
            cur.execute("""
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS city TEXT
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS blocks (
                    blocker_id BIGINT NOT NULL,
                    blocked_id BIGINT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (blocker_id, blocked_id)
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS reports (
                    id SERIAL PRIMARY KEY,
                    reporter_id BIGINT NOT NULL,
                    reported_id BIGINT NOT NULL,
                    reason TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS activity_logs (
                    id SERIAL PRIMARY KEY,
                    telegram_id BIGINT,
                    activity TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)


def log_activity(user_id, activity):
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO activity_logs (telegram_id, activity)
                    VALUES (%s, %s)
                """, (user_id, activity))
    except Exception:
        logger.exception("Activity logging failed")


def get_user(user_id):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM users
                WHERE telegram_id = %s
            """, (user_id,))
            return cur.fetchone()


def save_profile(user_id, profile):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO users
                (telegram_id, nickname, age, gender, city,
                 latitude, longitude, location_visible, profile_visible)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, TRUE)
                ON CONFLICT (telegram_id)
                DO UPDATE SET
                    nickname = EXCLUDED.nickname,
                    age = EXCLUDED.age,
                    gender = EXCLUDED.gender,
                    city = EXCLUDED.city,
                    latitude = EXCLUDED.latitude,
                    longitude = EXCLUDED.longitude,
                    location_visible = EXCLUDED.location_visible
            """, (
                user_id,
                profile.get("nickname"),
                profile.get("age"),
                profile.get("gender"),
                profile.get("city"),
                profile.get("latitude"),
                profile.get("longitude"),
                profile.get("location_visible", False)
            ))


# =========================
# صفحه اصلی و ابزارها
# =========================

def main_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row("🔎 افراد نزدیک", "👤 پروفایل من")
    keyboard.row("📍 ارسال موقعیت", "🔒 حریم خصوصی")
    keyboard.row("🚫 بلاک کاربر", "⚠️ گزارش کاربر")
    keyboard.row("🗑 حذف حساب", "❌ لغو")
    return keyboard


def privacy_keyboard():
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(
        types.InlineKeyboardButton(
            "مخفی کردن پروفایل",
            callback_data="hide_profile"
        )
    )
    keyboard.add(
        types.InlineKeyboardButton(
            "نمایش پروفایل",
            callback_data="show_profile"
        )
    )
    keyboard.add(
        types.InlineKeyboardButton(
            "مخفی کردن موقعیت",
            callback_data="hide_location"
        )
    )
    keyboard.add(
        types.InlineKeyboardButton(
            "نمایش موقعیت",
            callback_data="show_location"
        )
    )
    return keyboard


def finish_registration(message):
    user_id = message.from_user.id
    profile = registration.get(user_id, {}).get("profile", {})

    try:
        save_profile(user_id, profile)
        registration.pop(user_id, None)

        bot.send_message(
            message.chat.id,
            "✅ پروفایلت با موفقیت ذخیره شد!\n"
            "به GapMate خوش اومدی 🌱",
            reply_markup=main_keyboard()
        )
        log_activity(user_id, "registration_completed")

    except Exception:
        logger.exception("Registration save failed")
        bot.send_message(
            message.chat.id,
            "❌ ذخیره پروفایل انجام نشد. لطفاً دوباره تلاش کن."
        )


def is_blocked(user1, user2):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 1 FROM blocks
                WHERE (blocker_id = %s AND blocked_id = %s)
                   OR (blocker_id = %s AND blocked_id = %s)
                LIMIT 1
            """, (user1, user2, user2, user1))
            return cur.fetchone() is not None


# =========================
# شروع و ثبت نام
# =========================

@bot.message_handler(commands=["start"])
def start(message):
    user_id = message.from_user.id
    log_activity(user_id, "start")

    try:
        user = get_user(user_id)

        if user and user.get("nickname"):
            bot.send_message(
                message.chat.id,
                f"سلام {user['nickname']}! خوش برگشتی 🌱\n"
                "پروفایلت از قبل ذخیره شده.",
                reply_markup=main_keyboard()
            )
            return

        registration[user_id] = {
            "step": "nickname",
            "profile": {}
        }

        bot.send_message(
            message.chat.id,
            "سلام! به GapMate خوش اومدی 🌱\n"
            "برای ساخت پروفایل، یک نام مستعار وارد کن:"
        )

    except Exception:
        logger.exception("Start command failed")
        bot.send_message(
            message.chat.id,
            "❌ فعلاً اتصال به دیتابیس مشکل داره. دوباره تلاش کن."
        )


@bot.message_handler(commands=["cancel"])
def cancel(message):
    registration.pop(message.from_user.id, None)
    bot.send_message(
        message.chat.id,
        "عملیات لغو شد.",
        reply_markup=main_keyboard()
    )


# =========================
# بررسی دیتابیس
# =========================

@bot.message_handler(commands=["dbcheck"])
def dbcheck(message):
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) AS total FROM users")
                users_count = cur.fetchone()["total"]

                cur.execute("SELECT COUNT(*) AS total FROM activity_logs")
                logs_count = cur.fetchone()["total"]

        bot.send_message(
            message.chat.id,
            "✅ دیتابیس متصل است.\n"
            f"تعداد پروفایل‌ها: {users_count}\n"
            f"تعداد فعالیت‌های ثبت‌شده: {logs_count}"
        )

    except Exception:
        logger.exception("Database check failed")
        bot.send_message(message.chat.id, "❌ اتصال دیتابیس ناموفق بود.")


# =========================
# ثبت نام مرحله به مرحله
# =========================

@bot.message_handler(content_types=["text"])
def handle_text(message):
    user_id = message.from_user.id
    text = (message.text or "").strip()

    if text.startswith("/"):
        return

    if text == "❌ لغو":
        registration.pop(user_id, None)
        bot.send_message(
            message.chat.id,
            "عملیات لغو شد.",
            reply_markup=main_keyboard()
        )
        return

    if user_id in registration:
        step = registration[user_id]["step"]
        profile = registration[user_id]["profile"]

        if step == "nickname":
            if len(text) < 2 or len(text) > 30:
                bot.send_message(message.chat.id, "نام مستعار باید بین ۲ تا ۳۰ حرف باشد.")
                return

            profile["nickname"] = text
            registration[user_id]["step"] = "age"
            bot.send_message(message.chat.id, "چند سالته؟ فقط عدد وارد کن:")
            return

        if step == "age":
            try:
                age = int(text)
                if age < 18 or age > 100:
                    raise ValueError
            except ValueError:
                bot.send_message(message.chat.id, "سن باید عددی بین ۱۸ تا ۱۰۰ باشد.")
                return

            profile["age"] = age
            registration[user_id]["step"] = "gender"

            keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            keyboard.row("مرد", "زن", "سایر")

            bot.send_message(message.chat.id, "جنسیتت رو انتخاب کن:", reply_markup=keyboard)
            return

        if step == "gender":
            if text not in ["مرد", "زن", "سایر"]:
                bot.send_message(message.chat.id, "یکی از گزینه‌های موجود رو انتخاب کن.")
                return

            profile["gender"] = text
            registration[user_id]["step"] = "city"
            bot.send_message(message.chat.id, "اسم شهرت رو وارد کن:")
            return

        if step == "city":
            if len(text) < 2 or len(text) > 60:
                bot.send_message(message.chat.id, "اسم شهر معتبر نیست.")
                return

            profile["city"] = text
            registration[user_id]["step"] = "location_consent"

            keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            keyboard.row("📍 ارسال موقعیت", "رد کردن")

            bot.send_message(
                message.chat.id,
                "می‌تونی موقعیتت رو برای پیدا کردن افراد نزدیک بفرستی.\n"
                "موقعیتت فقط با اجازه خودت برای جست‌وجوی افراد نزدیک استفاده می‌شه.",
                reply_markup=keyboard
            )
            return

        if step == "location_consent":
            if text == "رد کردن":
                profile["location_visible"] = False
                finish_registration(message)
                return

            if text == "📍 ارسال موقعیت":
                registration[user_id]["step"] = "waiting_location"

                keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
                keyboard.add(
                    types.KeyboardButton(
                        "ارسال موقعیت من",
                        request_location=True
                    )
                )
                keyboard.add("رد کردن")

                bot.send_message(
                    message.chat.id,
                    "برای ارسال موقعیت، دکمه زیر رو بزن:",
                    reply_markup=keyboard
                )
                return

            bot.send_message(message.chat.id, "ارسال موقعیت یا رد کردن رو انتخاب کن.")
            return

        if step == "waiting_location":
            if text == "رد کردن":
                profile["location_visible"] = False
                finish_registration(message)
                return

            bot.send_message(
                message.chat.id,
                "لطفاً از دکمه ارسال موقعیت استفاده کن یا گزینه رد کردن رو بزن."
            )
            return

    # دستورات صفحه اصلی
    if text == "👤 پروفایل من":
        show_profile(message)
        return

    if text == "🔎 افراد نزدیک":
        nearby(message)
        return

    if text == "📍 ارسال موقعیت":
        ask_location(message)
        return

    if text == "🔒 حریم خصوصی":
        bot.send_message(
            message.chat.id,
            "تنظیمات حریم خصوصی:",
            reply_markup=privacy_keyboard()
        )
        return

    if text == "🚫 بلاک کاربر":
        bot.send_message(
            message.chat.id,
            "برای بلاک کردن، شناسه عددی تلگرام کاربر رو بفرست:"
        )
        registration[user_id] = {
            "step": "block_user",
            "profile": {}
        }
        return

    if text == "⚠️ گزارش کاربر":
        bot.send_message(
            message.chat.id,
            "شناسه عددی کاربر موردنظر رو بفرست:"
        )
        registration[user_id] = {
            "step": "report_user",
            "profile": {}
        }
        return

    if text == "🗑 حذف حساب":
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(
            types.InlineKeyboardButton(
                "بله، حسابم حذف شود",
                callback_data="confirm_delete"
            ),
            types.InlineKeyboardButton(
                "انصراف",
                callback_data="cancel_delete"
            )
        )
        bot.send_message(
            message.chat.id,
            "⚠️ با حذف حساب، پروفایل و اطلاعات مرتبط با آن حذف می‌شود.\n"
            "این کار قابل بازگشت نیست.",
            reply_markup=keyboard
        )
        return

    # مراحل بلاک و گزارش
    if user_id in registration:
        step = registration[user_id]["step"]

        if step in ["block_user", "report_user"]:
            try:
                target_id = int(text)
                if target_id == user_id:
                    bot.send_message(message.chat.id, "نمی‌تونی خودت رو انتخاب کنی.")
                    return
            except ValueError:
                bot.send_message(message.chat.id, "لطفاً شناسه عددی معتبر بفرست.")
                return

            registration.pop(user_id, None)

            if step == "block_user":
                try:
                    with get_db() as conn:
                        with conn.cursor() as cur:
                            cur.execute("""
                                INSERT INTO blocks (blocker_id, blocked_id)
                                VALUES (%s, %s)
                                ON CONFLICT DO NOTHING
                            """, (user_id, target_id))

                    bot.send_message(
                        message.chat.id,
                        "🚫 کاربر بلاک شد.",
                        reply_markup=main_keyboard()
                    )
                except Exception:
                    logger.exception("Block failed")
                    bot.send_message(message.chat.id, "خطا در بلاک کاربر.")

            else:
                registration[user_id] = {
                    "step": "report_reason",
                    "profile": {"reported_id": target_id}
                }
                bot.send_message(message.chat.id, "دلیل گزارش رو بنویس:")
            return

        if step == "report_reason":
            target_id = registration[user_id]["profile"]["reported_id"]

            try:
                with get_db() as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            INSERT INTO reports (reporter_id, reported_id, reason)
                            VALUES (%s, %s, %s)
                        """, (user_id, target_id, text))

                registration.pop(user_id, None)

                bot.send_message(
                    message.chat.id,
                    "✅ گزارش ثبت شد. ممنون که اطلاع دادی.",
                    reply_markup=main_keyboard()
                )

                if ADMIN_ID:
                    try:
                        bot.send_message(
                            ADMIN_ID,
                            "⚠️ گزارش جدید\n"
                            f"گزارش‌دهنده: {user_id}\n"
                            f"کاربر گزارش‌شده: {target_id}\n"
                            f"دلیل: {text}"
                        )
                    except Exception:
                        logger.exception("Admin notification failed")

            except Exception:
                logger.exception("Report failed")
                bot.send_message(message.chat.id, "خطا در ثبت گزارش.")
            return

    # ذخیره فعالیت، بدون ذخیره متن پیام خصوصی
    log_activity(user_id, "other_text")


# =========================
# دریافت موقعیت
# =========================

@bot.message_handler(content_types=["location"])
def receive_location(message):
    user_id = message.from_user.id
    location = message.location

    try:
        if user_id in registration:
            profile = registration[user_id]["profile"]

            if registration[user_id]["step"] == "waiting_location":
                profile["latitude"] = location.latitude
                profile["longitude"] = location.longitude
                profile["location_visible"] = True
                finish_registration(message)
                return

        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE users
                    SET latitude = %s,
                        longitude = %s,
                        location_visible = TRUE
                    WHERE telegram_id = %s
                """, (location.latitude, location.longitude, user_id))

        bot.send_message(
            message.chat.id,
            "✅ موقعیتت ذخیره شد.",
            reply_markup=main_keyboard()
        )

    except Exception:
        logger.exception("Location save failed")
        bot.send_message(message.chat.id, "خطا در ذخیره موقعیت.")


def ask_location(message):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    keyboard.add(
        types.KeyboardButton(
            "ارسال موقعیت من",
            request_location=True
        )
    )
    keyboard.add("❌ لغو")

    bot.send_message(
        message.chat.id,
        "برای ذخیره موقعیت، دکمه زیر رو بزن:",
        reply_markup=keyboard
    )


# =========================
# پروفایل
# =========================

def show_profile(message):
    try:
        user = get_user(message.from_user.id)

        if not user:
            bot.send_message(message.chat.id, "هنوز پروفایلی نداری. /start رو بزن.")
            return

        bot.send_message(
            message.chat.id,
            "👤 پروفایل تو\n\n"
            f"نام مستعار: {user['nickname']}\n"
            f"سن: {user['age']}\n"
            f"جنسیت: {user['gender']}\n"
            f"شهر: {user['city']}\n"
            f"نمایش پروفایل: {'روشن' if user['profile_visible'] else 'خاموش'}\n"
            f"نمایش موقعیت: {'روشن' if user['location_visible'] else 'خاموش'}",
            reply_markup=main_keyboard()
        )

    except Exception:
        logger.exception("Profile display failed")
        bot.send_message(message.chat.id, "خطا در نمایش پروفایل.")


# =========================
# افراد نزدیک
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


def nearby(message):
    user_id = message.from_user.id

    try:
        me = get_user(user_id)

        if not me:
            bot.send_message(message.chat.id, "اول باید پروفایلت رو بسازی.")
            return

        if not me["latitude"] or not me["longitude"] or not me["location_visible"]:
            bot.send_message(
                message.chat.id,
                "برای پیدا کردن افراد نزدیک، اول موقعیتت رو ارسال و نمایش موقعیت رو فعال کن."
            )
            return

        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT * FROM users
                    WHERE telegram_id != %s
                    AND profile_visible = TRUE
                    AND location_visible = TRUE
                    AND latitude IS NOT NULL
                    AND longitude IS NOT NULL
                    AND age >= 18
                """, (user_id,))
                candidates = cur.fetchall()

        results = []

        for person in candidates:
            if is_blocked(user_id, person["telegram_id"]):
                continue

            distance = distance_km(
                me["latitude"],
                me["longitude"],
                person["latitude"],
                person["longitude"]
            )

            if distance <= 50:
                results.append((distance, person))

        results.sort(key=lambda item: item[0])

        if not results:
            bot.send_message(
                message.chat.id,
                "فعلاً کسی در نزدیکی تو پیدا نشد.",
                reply_markup=main_keyboard()
            )
            return

        bot.send_message(message.chat.id, "🔎 افراد نزدیک به تو:")

        for distance, person in results[:10]:
            bot.send_message(
                message.chat.id,
                "👤 یک پروفایل نزدیک\n\n"
                f"نام مستعار: {person['nickname']}\n"
                f"سن: {person['age']}\n"
                f"جنسیت: {person['gender']}\n"
                f"شهر: {person['city']}\n"
                f"فاصله تقریبی: {round(distance)} کیلومتر\n\n"
                f"شناسه برای گزارش یا بلاک: {person['telegram_id']}"
            )

    except Exception:
        logger.exception("Nearby search failed")
        bot.send_message(message.chat.id, "خطا در جست‌وجوی افراد نزدیک.")


# =========================
# حریم خصوصی
# =========================

@bot.callback_query_handler(func=lambda call: call.data in [
    "hide_profile", "show_profile", "hide_location", "show_location"
])
def privacy_callback(call):
    user_id = call.from_user.id

    try:
        with get_db() as conn:
            with conn.cursor() as cur:

                if call.data == "hide_profile":
                    cur.execute("""
                        UPDATE users SET profile_visible = FALSE
                        WHERE telegram_id = %s
                    """, (user_id,))
                    result = "پروفایلت مخفی شد."

                elif call.data == "show_profile":
                    cur.execute("""
                        UPDATE users SET profile_visible = TRUE
                        WHERE telegram_id = %s
                    """, (user_id,))
                    result = "پروفایلت نمایش داده می‌شه."

                elif call.data == "hide_location":
                    cur.execute("""
                        UPDATE users SET location_visible = FALSE
                        WHERE telegram_id = %s
                    """, (user_id,))
                    result = "موقعیتت مخفی شد."

                else:
                    cur.execute("""
                        UPDATE users SET location_visible = TRUE
                        WHERE telegram_id = %s
                        AND latitude IS NOT NULL
                        AND longitude IS NOT NULL
                    """, (user_id,))
                    result = "نمایش موقعیت فعال شد، اگر قبلاً موقعیت ذخیره کرده باشی."

        bot.answer_callback_query(call.id, result)
        bot.send_message(call.message.chat.id, result)

    except Exception:
        logger.exception("Privacy update failed")
        bot.answer_callback_query(call.id, "خطا در تغییر تنظیمات.")


# =========================
# حذف حساب
# =========================

@bot.callback_query_handler(func=lambda call: call.data in [
    "confirm_delete", "cancel_delete"
])
def delete_callback(call):
    user_id = call.from_user.id

    if call.data == "cancel_delete":
        bot.answer_callback_query(call.id, "حذف حساب لغو شد.")
        bot.send_message(
            call.message.chat.id,
            "حذف حساب لغو شد.",
            reply_markup=main_keyboard()
        )
        return

    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM users WHERE telegram_id = %s", (user_id,))
                cur.execute("""
                    DELETE FROM blocks
                    WHERE blocker_id = %s OR blocked_id = %s
                """, (user_id, user_id))
                cur.execute("""
                    DELETE FROM reports
                    WHERE reporter_id = %s OR reported_id = %s
                """, (user_id, user_id))
                cur.execute("""
                    DELETE FROM activity_logs
                    WHERE telegram_id = %s
                """, (user_id,))

        registration.pop(user_id, None)

        bot.answer_callback_query(call.id, "حساب حذف شد.")
        bot.send_message(
            call.message.chat.id,
            "حساب و اطلاعات مرتبط با آن حذف شد.\n"
            "هر زمان خواستی می‌تونی دوباره /start رو بزنی."
        )

    except Exception:
        logger.exception("Account deletion failed")
        bot.answer_callback_query(call.id, "خطا در حذف حساب.")
        bot.send_message(call.message.chat.id, "حذف حساب انجام نشد.")


# =========================
# پنل گزارش‌های مدیر
# =========================

@bot.message_handler(commands=["reports"])
def reports(message):
    if not ADMIN_ID or message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "اجازه دسترسی نداری.")
        return

    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT * FROM reports
                    ORDER BY created_at DESC
                    LIMIT 30
                """)
                rows = cur.fetchall()

        if not rows:
            bot.send_message(message.chat.id, "گزارشی ثبت نشده.")
            return

        for row in rows:
            bot.send_message(
                message.chat.id,
                f"گزارش شماره {row['id']}\n"
                f"گزارش‌دهنده: {row['reporter_id']}\n"
                f"کاربر: {row['reported_id']}\n"
                f"دلیل: {row['reason']}"
            )

    except Exception:
        logger.exception("Reports command failed")
        bot.send_message(message.chat.id, "خطا در دریافت گزارش‌ها.")


# =========================
# وب‌هوک تلگرام و Render
# =========================

@app.route("/", methods=["GET"])
def home():
    return "GapMate is running", 200


@app.route("/" + BOT_TOKEN, methods=["POST"])
def webhook():
    if request.headers.get("content-type") == "application/json":
        json_string = request.get_data().decode("utf-8")
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return "OK", 200

    return "Invalid content type", 403


@app.route("/health", methods=["GET"])
def health():
    return "OK", 200


# =========================
# راه‌اندازی
# =========================

if __name__ == "__main__":
    init_db()

    if RENDER_EXTERNAL_URL:
        bot.remove_webhook()
        bot.set_webhook(
            url=RENDER_EXTERNAL_URL + "/" + BOT_TOKEN
        )

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
