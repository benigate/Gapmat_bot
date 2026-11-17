
import os
import math
import logging
import psycopg2
from flask import Flask, request
import telebot
from telebot import types

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.environ["BOT_TOKEN"]
DATABASE_URL = os.environ["DATABASE_URL"]
WEBHOOK_URL = os.environ.get("RENDER_EXTERNAL_URL", "").rstrip("/")
PORT = int(os.environ.get("PORT", 10000))
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

registration = {}
waiting_location = set()


def get_db():
    return psycopg2.connect(DATABASE_URL, sslmode="require")


def init_db():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    telegram_id BIGINT PRIMARY KEY,
                    nickname TEXT,
                    age INTEGER,
                    city TEXT,
                    province TEXT,
                    gender TEXT,
                    photo_file_id TEXT,
                    bio TEXT,
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
                CREATE TABLE IF NOT EXISTS messages (
                    id BIGSERIAL PRIMARY KEY,
                    telegram_id BIGINT NOT NULL,
                    chat_id BIGINT,
                    message_id BIGINT,
                    content_type TEXT,
                    message_text TEXT,
                    file_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (chat_id, message_id)
                )
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
                    id BIGSERIAL PRIMARY KEY,
                    reporter_id BIGINT NOT NULL,
                    reported_id BIGINT NOT NULL,
                    reason TEXT,
                    status TEXT DEFAULT 'new',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)


def save_message(message):
    try:
        text = message.text or message.caption or ""
        file_id = None

        if message.photo:
            file_id = message.photo[-1].file_id

        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO messages
                    (telegram_id, chat_id, message_id,
                     content_type, message_text, file_id)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (chat_id, message_id) DO NOTHING
                """, (
                    message.from_user.id,
                    message.chat.id,
                    message.message_id,
                    message.content_type,
                    text,
                    file_id
                ))
    except Exception:
        app.logger.exception("Message save failed")


def save_profile(user_id, profile):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO users
                (telegram_id, nickname, age, city, province,
                 gender, photo_file_id, bio,
                 latitude, longitude, location_visible,
                 profile_visible)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, TRUE)
                ON CONFLICT (telegram_id) DO UPDATE SET
                    nickname = EXCLUDED.nickname,
                    age = EXCLUDED.age,
                    city = EXCLUDED.city,
                    province = EXCLUDED.province,
                    gender = EXCLUDED.gender,
                    photo_file_id = EXCLUDED.photo_file_id,
                    bio = EXCLUDED.bio,
                    latitude = COALESCE(
                        EXCLUDED.latitude, users.latitude
                    ),
                    longitude = COALESCE(
                        EXCLUDED.longitude, users.longitude
                    ),
                    location_visible = CASE
                        WHEN EXCLUDED.latitude IS NOT NULL
                        THEN TRUE
                        ELSE users.location_visible
                    END
            """, (
                user_id,
                profile["nickname"],
                profile["age"],
                profile["city"],
                profile["province"],
                profile["gender"],
                profile["photo"],
                profile["bio"],
                profile.get("latitude"),
                profile.get("longitude"),
                profile.get("location_visible", False)
            ))


def main_keyboard():
    keyboard = types.ReplyKeyboardMarkup(
        resize_keyboard=True
    )
    keyboard.row("/nearby", "/location")
    keyboard.row("/hide_location", "/show_location")
    keyboard.row("/hide_profile", "/show_profile")
    keyboard.row("/privacy", "/delete_account")
    return keyboard


def finish_registration(user_id, chat_id, profile):
    try:
        save_profile(user_id, profile)
    except Exception:
        app.logger.exception("Profile save failed")
        bot.send_message(
            chat_id,
            "❌ ذخیره پروفایل ناموفق بود. دوباره تلاش کن."
        )
        return

    registration.pop(user_id, None)

    bot.send_message(
        chat_id,
        "🎉 پروفایلت ذخیره شد!\n\n"
        "برای پیدا کردن افراد نزدیک از /nearby استفاده کن.\n"
        "برای مدیریت حریم خصوصی /privacy رو بزن.",
        reply_markup=main_keyboard()
    )


def is_blocked(first_id, second_id):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM blocks
                    WHERE (blocker_id = %s AND blocked_id = %s)
                       OR (blocker_id = %s AND blocked_id = %s)
                )
            """, (first_id, second_id, second_id, first_id))
            return cur.fetchone()[0]


try:
    init_db()
    logging.info("Database tables are ready.")
except Exception:
    logging.exception("Database initialization failed")
    raise


@bot.message_handler(commands=["start"])
def start(message):
    save_message(message)

    registration[message.from_user.id] = {
        "step": "nickname",
        "profile": {}
    }

    bot.send_message(
        message.chat.id,
        "سلام! به GapMate خوش اومدی 🌱\n"
        "برای ساخت پروفایل، یک نام مستعار وارد کن:"
    )


@bot.message_handler(commands=["cancel"])
def cancel(message):
    save_message(message)
    registration.pop(message.from_user.id, None)
    waiting_location.discard(message.from_user.id)

    bot.send_message(
        message.chat.id,
        "عملیات لغو شد. برای شروع دوباره /start رو بزن."
    )


@bot.message_handler(commands=["dbcheck"])
def dbcheck(message):
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM users")
                users_count = cur.fetchone()[0]

                cur.execute("SELECT COUNT(*) FROM messages")
                messages_count = cur.fetchone()[0]

                cur.execute("SELECT COUNT(*) FROM reports")
                reports_count = cur.fetchone()[0]

        bot.send_message(
            message.chat.id,
            "✅ دیتابیس متصل است.\n"
            f"پروفایل‌ها: {users_count}\n"
            f"پیام‌های ذخیره‌شده: {messages_count}\n"
            f"گزارش‌ها: {reports_count}"
        )
    except Exception:
        app.logger.exception("Database check failed")
        bot.send_message(message.chat.id, "❌ خطا در دیتابیس.")


@bot.message_handler(commands=["privacy"])
def privacy(message):
    bot.send_message(
        message.chat.id,
        "🔐 تنظیمات حریم خصوصی GapMate\n\n"
        "/hide_location - مخفی‌کردن لوکیشن\n"
        "/show_location - فعال‌کردن نمایش در جستجوی نزدیک‌ها\n"
        "/hide_profile - مخفی‌کردن پروفایل\n"
        "/show_profile - نمایش پروفایل\n"
        "/delete_location - حذف مختصات ذخیره‌شده\n"
        "/delete_account - حذف حساب و اطلاعات شخصی\n\n"
        "لوکیشن دقیق به کاربران دیگر نمایش داده نمی‌شود."
    )


@bot.message_handler(commands=["location"])
def ask_location(message):
    user_id = message.from_user.id

    waiting_location.add(user_id)

    keyboard = types.ReplyKeyboardMarkup(
        resize_keyboard=True,
        one_time_keyboard=True
    )
    keyboard.add(types.KeyboardButton(
        "📍 ارسال موقعیت مکانی",
        request_location=True
    ))
    keyboard.add("لغو")

    bot.send_message(
        message.chat.id,
        "اگر مایل هستی افراد نزدیکت تو رو پیدا کنند، "
        "موقعیت مکانی‌ات رو ارسال کن.\n\n"
        "مختصات دقیق فقط برای محاسبه فاصله استفاده می‌شه "
        "و به دیگران نمایش داده نمی‌شه.",
        reply_markup=keyboard
    )


@bot.message_handler(commands=["hide_location"])
def hide_location(message):
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE users
                    SET location_visible = FALSE
                    WHERE telegram_id = %s
                """, (message.from_user.id,))

                if cur.rowcount == 0:
                    bot.send_message(
                        message.chat.id,
                        "اول باید پروفایل بسازی."
                    )
                    return

        bot.send_message(
            message.chat.id,
            "✅ لوکیشنت از جستجوی دیگران مخفی شد."
        )
    except Exception:
        app.logger.exception("Hide location failed")
        bot.send_message(message.chat.id, "❌ خطا در دیتابیس.")


@bot.message_handler(commands=["show_location"])
def show_location(message):
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE users
                    SET location_visible = TRUE
                    WHERE telegram_id = %s
                      AND latitude IS NOT NULL
                      AND longitude IS NOT NULL
                """, (message.from_user.id,))

                changed = cur.rowcount

        if changed:
            bot.send_message(
                message.chat.id,
                "✅ لوکیشن در جستجوی افراد نزدیک فعال شد."
            )
        else:
            bot.send_message(
                message.chat.id,
                "لوکیشنی ثبت نشده. اول /location رو بزن."
            )
    except Exception:
        app.logger.exception("Show location failed")
        bot.send_message(message.chat.id, "❌ خطا در دیتابیس.")


@bot.message_handler(commands=["delete_location"])
def delete_location(message):
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE users
                    SET latitude = NULL,
                        longitude = NULL,
                        location_visible = FALSE
                    WHERE telegram_id = %s
                """, (message.from_user.id,))

        waiting_location.discard(message.from_user.id)

        bot.send_message(
            message.chat.id,
            "✅ مختصات ذخیره‌شده حذف شد."
        )
    except Exception:
        app.logger.exception("Delete location failed")
        bot.send_message(message.chat.id, "❌ خطا در دیتابیس.")


@bot.message_handler(commands=["hide_profile"])
def hide_profile(message):
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE users
                    SET profile_visible = FALSE
                    WHERE telegram_id = %s
                """, (message.from_user.id,))

        bot.send_message(
            message.chat.id,
            "✅ پروفایلت از جستجوی دیگران مخفی شد."
        )
    except Exception:
        app.logger.exception("Hide profile failed")
        bot.send_message(message.chat.id, "❌ خطا در دیتابیس.")


@bot.message_handler(commands=["show_profile"])
def show_profile(message):
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE users
                    SET profile_visible = TRUE
                    WHERE telegram_id = %s
                """, (message.from_user.id,))

        bot.send_message(
            message.chat.id,
            "✅ پروفایلت دوباره قابل مشاهده شد."
        )
    except Exception:
        app.logger.exception("Show profile failed")
        bot.send_message(message.chat.id, "❌ خطا در دیتابیس.")


@bot.message_handler(commands=["nearby"])
def nearby(message):
    user_id = message.from_user.id

    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT latitude, longitude, age
                    FROM users
                    WHERE telegram_id = %s
                """, (user_id,))
                own = cur.fetchone()

                if not own or own[0] is None or own[1] is None:
                    bot.send_message(
                        message.chat.id,
                        "اول لوکیشنت رو ثبت کن: /location"
                    )
                    return

                if not own[2]:
                    bot.send_message(
                        message.chat.id,
                        "سن پروفایلت ثبت نشده."
                    )
                    return

                my_lat, my_lon, my_age = own

                if my_age < 18:
                    age_condition = "age BETWEEN 16 AND 17"
                else:
                    age_condition = "age >= 18"

                cur.execute(f"""
                    SELECT telegram_id, nickname, age, city,
                           latitude, longitude
                    FROM users
                    WHERE telegram_id != %s
                      AND location_visible = TRUE
                      AND profile_visible = TRUE
                      AND latitude IS NOT NULL
                      AND longitude IS NOT NULL
                      AND {age_condition}
                      AND NOT EXISTS (
                          SELECT 1 FROM blocks b
                          WHERE
                            (b.blocker_id = %s
                             AND b.blocked_id = users.telegram_id)
                            OR
                            (b.blocker_id = users.telegram_id
                             AND b.blocked_id = %s)
                      )
                """, (user_id, user_id, user_id))

                candidates = cur.fetchall()

        results = []

        for other_id, nickname, age, city, lat, lon in candidates:
            lat1 = math.radians(my_lat)
            lat2 = math.radians(lat)
            delta_lat = math.radians(lat - my_lat)
            delta_lon = math.radians(lon - my_lon)

            a = (
                math.sin(delta_lat / 2) ** 2
                + math.cos(lat1) * math.cos(lat2)
                * math.sin(delta_lon / 2) ** 2
            )

            distance = 6371 * 2 * math.asin(
                min(1, math.sqrt(a))
            )

            if distance <= 5:
                results.append(
                    (distance, other_id, nickname, age, city)
                )

        results.sort(key=lambda item: item[0])

        if not results:
            bot.send_message(
                message.chat.id,
                "فعلاً کسی در شعاع ۵ کیلومتری تو پیدا نشد."
            )
            return

        for distance, other_id, nickname, age, city in results[:10]:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.row(
                types.InlineKeyboardButton(
                    "🚫 بلاک",
                    callback_data=f"block:{other_id}"
                ),
                types.InlineKeyboardButton(
                    "⚠️ گزارش",
                    callback_data=f"report:{other_id}"
                )
            )

            bot.send_message(
                message.chat.id,
                f"👤 {nickname}\n"
                f"سن: {age}\n"
                f"شهر: {city}\n"
                f"فاصله تقریبی: {distance:.1f} کیلومتر",
                reply_markup=keyboard
            )

    except Exception:
        app.logger.exception("Nearby search failed")
        bot.send_message(
            message.chat.id,
            "❌ در جستجوی افراد نزدیک خطایی رخ داد."
        )


@bot.callback_query_handler(
    func=lambda call: call.data.startswith("block:")
)
def block_user(call):
    try:
        target_id = int(call.data.split(":")[1])
        user_id = call.from_user.id

        if target_id == user_id:
            bot.answer_callback_query(
                call.id,
                "نمی‌تونی خودت رو بلاک کنی."
            )
            return

        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO blocks (blocker_id, blocked_id)
                    VALUES (%s, %s)
                    ON CONFLICT DO NOTHING
                """, (user_id, target_id))

        bot.answer_callback_query(
            call.id,
            "این کاربر بلاک شد."
        )
        bot.edit_message_reply_markup(
            call.message.chat.id,
            call.message.message_id,
            reply_markup=None
        )
    except Exception:
        app.logger.exception("Block failed")
        bot.answer_callback_query(
            call.id,
            "خطا در ثبت بلاک."
        )


@bot.callback_query_handler(
    func=lambda call: call.data.startswith("report:")
)
def report_user(call):
    try:
        target_id = int(call.data.split(":")[1])
        user_id = call.from_user.id

        if target_id == user_id:
            bot.answer_callback_query(
                call.id,
                "نمی‌تونی خودت رو گزارش کنی."
            )
            return

        keyboard = types.InlineKeyboardMarkup()
        reasons = [
            ("رفتار آزاردهنده", "آزار"),
            ("پروفایل جعلی", "جعلی"),
            ("محتوای نامناسب", "محتوا"),
            ("مورد دیگر", "سایر")
        ]

        for label, reason in reasons:
            keyboard.add(types.InlineKeyboardButton(
                label,
                callback_data=f"reason:{target_id}:{reason}"
            ))

        bot.answer_callback_query(call.id)
        bot.send_message(
            call.message.chat.id,
            "دلیل گزارش رو انتخاب کن:",
            reply_markup=keyboard
        )
    except Exception:
        app.logger.exception("Report setup failed")
        bot.answer_callback_query(
            call.id,
            "خطا در ثبت گزارش."
        )


@bot.callback_query_handler(
    func=lambda call: call.data.startswith("reason:")
)
def report_reason(call):
    try:
        parts = call.data.split(":", 2)
        target_id = int(parts[1])
        reason = parts[2]
        user_id = call.from_user.id

        if target_id == user_id:
            bot.answer_callback_query(
                call.id,
                "گزارش نامعتبره."
            )
            return

        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO reports
                    (reporter_id, reported_id, reason)
                    VALUES (%s, %s, %s)
                """, (user_id, target_id, reason))

        if ADMIN_ID:
            try:
                bot.send_message(
                    ADMIN_ID,
                    "⚠️ گزارش جدید در GapMate\n"
                    f"گزارش‌دهنده: {user_id}\n"
                    f"کاربر گزارش‌شده: {target_id}\n"
                    f"دلیل: {reason}"
                )
            except Exception:
                app.logger.exception("Admin notification failed")

        bot.answer_callback_query(
            call.id,
            "گزارش ثبت شد. ممنون."
        )
        bot.edit_message_reply_markup(
            call.message.chat.id,
            call.message.message_id,
            reply_markup=None
        )
    except Exception:
        app.logger.exception("Report save failed")
        bot.answer_callback_query(
            call.id,
            "ثبت گزارش ناموفق بود."
        )


@bot.message_handler(commands=["reports"])
def list_reports(message):
    if not ADMIN_ID or message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "اجازه دسترسی نداری.")
        return

    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, reporter_id, reported_id,
                           reason, created_at
                    FROM reports
                    WHERE status = 'new'
                    ORDER BY created_at DESC
                    LIMIT 20
                """)
                rows = cur.fetchall()

        if not rows:
            bot.send_message(message.chat.id, "گزارش جدیدی وجود نداره.")
            return

        for report_id, reporter, reported, reason, created in rows:
            bot.send_message(
                message.chat.id,
                f"گزارش #{report_id}\n"
                f"گزارش‌دهنده: {reporter}\n"
                f"کاربر گزارش‌شده: {reported}\n"
                f"دلیل: {reason}\n"
                f"زمان: {created}"
            )
    except Exception:
        app.logger.exception("Reports listing failed")
        bot.send_message(message.chat.id, "خطا در دریافت گزارش‌ها.")


@bot.message_handler(commands=["resolve_report"])
def resolve_report(message):
    if not ADMIN_ID or message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "اجازه دسترسی نداری.")
        return

    parts = (message.text or "").split()

    if len(parts) != 2 or not parts[1].isdigit():
        bot.send_message(
            message.chat.id,
            "روش استفاده: /resolve_report شماره_گزارش"
        )
        return

    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE reports
                    SET status = 'reviewed'
                    WHERE id = %s
                """, (int(parts[1]),))

        bot.send_message(message.chat.id, "گزارش بررسی‌شده علامت خورد.")
    except Exception:
        app.logger.exception("Resolve report failed")
        bot.send_message(message.chat.id, "خطا در به‌روزرسانی گزارش.")


@bot.message_handler(commands=["delete_account"])
def delete_account(message):
    keyboard = types.InlineKeyboardMarkup()
    keyboard.row(
        types.InlineKeyboardButton(
            "بله، حسابم حذف شود",
            callback_data="delete:confirm"
        ),
        types.InlineKeyboardButton(
            "انصراف",
            callback_data="delete:cancel"
        )
    )

    bot.send_message(
        message.chat.id,
        "⚠️ با تأیید، پروفایل، لوکیشن، پیام‌های ذخیره‌شده "
        "و فهرست بلاک‌های مربوط به حساب تو حذف می‌شوند.\n"
        "این کار قابل بازگشت نیست. مطمئنی؟",
        reply_markup=keyboard
    )


@bot.callback_query_handler(
    func=lambda call: call.data.startswith("delete:")
)
def delete_account_callback(call):
    if call.data == "delete:cancel":
        bot.answer_callback_query(call.id, "حذف حساب لغو شد.")
        bot.edit_message_text(
            "حذف حساب لغو شد.",
            call.message.chat.id,
            call.message.message_id
        )
        return

    if call.data != "delete:confirm":
        return

    user_id = call.from_user.id

    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM users WHERE telegram_id = %s",
                    (user_id,)
                )
                cur.execute(
                    "DELETE FROM messages WHERE telegram_id = %s",
                    (user_id,)
                )
                cur.execute("""
                    DELETE FROM blocks
                    WHERE blocker_id = %s OR blocked_id = %s
                """, (user_id, user_id))
                cur.execute("""
                    DELETE FROM reports
                    WHERE reporter_id = %s OR reported_id = %s
                """, (user_id, user_id))

        registration.pop(user_id, None)
        waiting_location.discard(user_id)

        bot.answer_callback_query(call.id, "حساب حذف شد.")
        bot.edit_message_text(
            "حساب و اطلاعات شخصی ذخیره‌شده‌ات حذف شد.\n"
            "برای ساخت حساب جدید /start رو بزن.",
            call.message.chat.id,
            call.message.message_id
        )
    except Exception:
        app.logger.exception("Account deletion failed")
        bot.answer_callback_query(
            call.id,
            "حذف حساب ناموفق بود."
        )


@bot.message_handler(
    content_types=["text", "photo", "location"],
    func=lambda message: (
        message.from_user.id in registration
        and not (message.text or "").startswith("/")
    )
)
def handle_registration(message):
    save_message(message)

    user_id = message.from_user.id
    chat_id = message.chat.id
    data = registration[user_id]
    profile = data["profile"]
    step = data["step"]

    if step == "nickname":
        if not message.text or len(message.text.strip()) < 2:
            bot.send_message(chat_id, "نام مستعار باید حداقل دو حرف باشه.")
            return

        profile["nickname"] = message.text.strip()[:50]
        data["step"] = "age"
        bot.send_message(chat_id, "چند سالته؟ (۱۶ تا ۹۹)")

    elif step == "age":
        try:
            age = int(message.text.strip())
            if not 16 <= age <= 99:
                raise ValueError
        except (ValueError, AttributeError):
            bot.send_message(chat_id, "سن معتبر بین ۱۶ تا ۹۹ وارد کن.")
            return

        profile["age"] = age
        data["step"] = "city"
        bot.send_message(chat_id, "در کدوم شهری؟")

    elif step == "city":
        if not message.text:
            bot.send_message(chat_id, "اسم شهر رو متنی بفرست.")
            return

        profile["city"] = message.text.strip()[:100]
        data["step"] = "province"
        bot.send_message(chat_id, "استان یا ایالتت رو وارد کن:")

    elif step == "province":
        if not message.text:
            bot.send_message(chat_id, "استان یا ایالت رو متنی بفرست.")
            return

        profile["province"] = message.text.strip()[:100]
        data["step"] = "gender"

        keyboard = types.ReplyKeyboardMarkup(
            resize_keyboard=True,
            one_time_keyboard=True
        )
        keyboard.add("مرد", "زن", "ترجیح می‌دهم نگویم")

        bot.send_message(
            chat_id,
            "جنسیتت رو انتخاب کن:",
            reply_markup=keyboard
        )

    elif step == "gender":
        if message.text not in [
            "مرد", "زن", "ترجیح می‌دهم نگویم"
        ]:
            bot.send_message(chat_id, "یکی از گزینه‌ها رو انتخاب کن.")
            return

        profile["gender"] = message.text
        data["step"] = "photo"
        bot.send_message(chat_id, "یک عکس پروفایل بفرست:")

    elif step == "photo":
        if not message.photo:
            bot.send_message(chat_id, "لطفاً عکس ارسال کن.")
            return

        profile["photo"] = message.photo[-1].file_id
        data["step"] = "bio"
        bot.send_message(chat_id, "یک معرفی کوتاه از خودت بنویس:")

    elif step == "bio":
        if not message.text or len(message.text.strip()) < 5:
            bot.send_message(
                chat_id,
                "معرفی باید حداقل پنج حرف داشته باشه."
            )
            return

        profile["bio"] = message.text.strip()[:500]
        data["step"] = "location"

        keyboard = types.ReplyKeyboardMarkup(
            resize_keyboard=True,
            one_time_keyboard=True
        )
        keyboard.add(types.KeyboardButton(
            "📍 ارسال موقعیت مکانی",
            request_location=True
        ))
        keyboard.add("رد کردن")

        bot.send_message(
            chat_id,
            "اگر می‌خوای افراد نزدیکت رو پیدا کنی، "
            "می‌تونی لوکیشنت رو ارسال کنی.\n"
            "مختصات دقیق به دیگران نمایش داده نمی‌شه.\n"
            "ارسال لوکیشن اختیاریه.",
            reply_markup=keyboard
        )

    elif step == "location":
        if message.location:
            profile["latitude"] = message.location.latitude
            profile["longitude"] = message.location.longitude
            profile["location_visible"] = True
            finish_registration(user_id, chat_id, profile)

        elif message.text == "رد کردن":
            profile["latitude"] = None
            profile["longitude"] = None
            profile["location_visible"] = False
            finish_registration(user_id, chat_id, profile)

        else:
            bot.send_message(
                chat_id,
                "لوکیشن رو بفرست یا گزینه «رد کردن» رو انتخاب کن."
            )


@bot.message_handler(
    content_types=["location"],
    func=lambda message: message.from_user.id in waiting_location
)
def receive_location(message):
    user_id = message.from_user.id
    waiting_location.discard(user_id)

    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE users
                    SET latitude = %s,
                        longitude = %s,
                        location_visible = TRUE
                    WHERE telegram_id = %s
                """, (
                    message.location.latitude,
                    message.location.longitude,
                    user_id
                ))

                changed = cur.rowcount

        if not changed:
            bot.send_message(
                message.chat.id,
                "اول پروفایلت رو بساز: /start"
            )
            return

        bot.send_message(
            message.chat.id,
            "✅ لوکیشن ثبت شد. برای دیدن افراد نزدیک /nearby رو بزن.",
            reply_markup=main_keyboard()
        )

    except Exception:
        app.logger.exception("Location save failed")
        bot.send_message(
            message.chat.id,
            "❌ ذخیره لوکیشن ناموفق بود."
        )


@bot.message_handler(
    content_types=["text"],
    func=lambda message: (
        message.from_user.id in waiting_location
        and message.text == "لغو"
    )
)
def cancel_location(message):
    waiting_location.discard(message.from_user.id)
    bot.send_message(
        message.chat.id,
        "ارسال لوکیشن لغو شد."
    )


@bot.message_handler(content_types=["text", "photo", "location"])
def save_other_messages(message):
    save_message(message)


@app.route("/", methods=["GET"])
def home():
    return "GapMate is running!", 200


@app.route("/webhook", methods=["POST"])
def webhook():
    if request.headers.get("content-type", "").startswith(
        "application/json"
    ):
        update = telebot.types.Update.de_json(
            request.get_data().decode("utf-8")
        )
        bot.process_new_updates([update])
        return "OK", 200

    return "Invalid content type", 400


if WEBHOOK_URL:
    bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
