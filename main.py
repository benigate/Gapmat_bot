
       
import os
import json
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, request
import telebot
from telebot import types

BOT_TOKEN = os.environ["BOT_TOKEN"]
DATABASE_URL = os.environ["DATABASE_URL"]
WEBHOOK_URL = os.environ.get("RENDER_EXTERNAL_URL", "").rstrip("/")
PORT = int(os.environ.get("PORT", 10000))

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# اتصال به دیتابیس
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

init_db()

# وضعیت ثبت‌نام کاربران
registration = {}

def save_profile(user_id, profile):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO users
                (telegram_id, nickname, age, city, province,
                 gender, photo_file_id, bio)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (telegram_id) DO UPDATE SET
                    nickname = EXCLUDED.nickname,
                    age = EXCLUDED.age,
                    city = EXCLUDED.city,
                    province = EXCLUDED.province,
                    gender = EXCLUDED.gender,
                    photo_file_id = EXCLUDED.photo_file_id,
                    bio = EXCLUDED.bio
            """, (
                user_id,
                profile["nickname"],
                profile["age"],
                profile["city"],
                profile["province"],
                profile["gender"],
                profile["photo"],
                profile["bio"]
            ))

@bot.message_handler(commands=["start"])
def start(message):
    user_id = message.from_user.id
    registration[user_id] = {"step": "nickname", "profile": {}}
    bot.send_message(
        message.chat.id,
        "سلام! به GapMate خوش اومدی 🌱\n\n"
        "برای ساخت پروفایلت، اول یک نام مستعار وارد کن:"
    )

@bot.message_handler(commands=["cancel"])
def cancel(message):
    registration.pop(message.from_user.id, None)
    bot.send_message(message.chat.id, "ثبت‌نام لغو شد. هر وقت خواستی /start رو بزن.")

@bot.message_handler(content_types=["text", "photo"])
def handle_registration(message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    if user_id not in registration:
        return

    data = registration[user_id]
    step = data["step"]
    profile = data["profile"]

    if step == "nickname":
        if not message.text or len(message.text.strip()) < 2:
            bot.send_message(chat_id, "یک نام مستعار حداقل دو حرفی وارد کن.")
            return
        profile["nickname"] = message.text.strip()
        data["step"] = "age"
        bot.send_message(chat_id, "چند سالته؟ (حداقل ۱۶ سال)")

    elif step == "age":
        try:
            age = int(message.text.strip())
            if age < 16 or age > 99:
                raise ValueError
        except (ValueError, AttributeError):
            bot.send_message(chat_id, "لطفاً سن معتبر بین ۱۶ تا ۹۹ وارد کن.")
            return
        profile["age"] = age
        data["step"] = "city"
        bot.send_message(chat_id, "در کدوم شهری زندگی می‌کنی؟")

    elif step == "city":
        profile["city"] = message.text.strip()
        data["step"] = "province"
        bot.send_message(chat_id, "استان یا ایالتت رو وارد کن:")

    elif step == "province":
        profile["province"] = message.text.strip()
        data["step"] = "gender"

        keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        keyboard.add("مرد", "زن", "ترجیح می‌دهم نگویم")
        bot.send_message(chat_id, "جنسیتت رو انتخاب کن:", reply_markup=keyboard)

    elif step == "gender":
        if message.text not in ["مرد", "زن", "ترجیح می‌دهم نگویم"]:
            bot.send_message(chat_id, "یکی از گزینه‌های صفحه‌کلید رو انتخاب کن.")
            return
        profile["gender"] = message.text
        data["step"] = "photo"
        bot.send_message(chat_id, "یک عکس پروفایل بفرست:")

    elif step == "photo":
        if not message.photo:
            bot.send_message(chat_id, "لطفاً یک عکس ارسال کن.")
            return
        profile["photo"] = message.photo[-1].file_id
        data["step"] = "bio"
        bot.send_message(chat_id, "حالا یک معرفی کوتاه از خودت بنویس:")

    elif step == "bio":
        if not message.text or len(message.text.strip()) < 5:
            bot.send_message(chat_id, "معرفی‌ات حداقل پنج حرف داشته باشه.")
            return
        profile["bio"] = message.text.strip()[:500]

        try:
            save_profile(user_id, profile)
        except Exception:
            bot.send_message(chat_id, "ذخیره اطلاعات با خطا مواجه شد. کمی بعد دوباره تلاش کن.")
            app.logger.exception("Database save failed")
            return

        registration.pop(user_id, None)
        bot.send_message(
            chat_id,
            "🎉 پروفایلت با موفقیت در دیتابیس ذخیره شد!",
            reply_markup=types.ReplyKeyboardRemove()
        )
@bot.message_handler(commands=["dbcheck"])
def dbcheck(message):
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM users")
                count = cur.fetchone()[0]
        bot.send_message(
            message.chat.id,
            f"✅ اتصال دیتابیس برقرار است.\nتعداد پروفایل‌های ذخیره‌شده: {count}"
        )
    except Exception:
        app.logger.exception("Database check failed")
        bot.send_message(message.chat.id, "❌ اتصال دیتابیس مشکل دارد.")
@app.route("/", methods=["GET"])
def home():
    return "GapMate is running!"

@app.route("/webhook", methods=["POST"])
def webhook():
    if request.headers.get("content-type") == "application/json":
        update = telebot.types.Update.de_json(request.get_data().decode("utf-8"))
        bot.process_new_updates([update])
        return "OK", 200
    return "Invalid content type", 400

if WEBHOOK_URL:
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
 
