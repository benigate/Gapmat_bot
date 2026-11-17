

import os
import telebot
from flask import Flask, request

TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", 10000))
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL")

if not TOKEN or not RENDER_URL:
    raise RuntimeError("Missing BOT_TOKEN or RENDER_EXTERNAL_URL")

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

users = {}

def ask_next(chat_id, user_id):
    profile = users[user_id]
    step = profile["step"]

    questions = {
        "nickname": "چه نام مستعاری دوست داری داشته باشی؟",
        "age": "چند سالته؟ (حداقل ۱۶ سال)",
        "city": "در کدام شهر زندگی می‌کنی؟",
        "province": "استان محل زندگی‌ات کجاست؟",
        "gender": "جنسیتت رو انتخاب کن:",
        "photo": "یک عکس پروفایل بفرست.",
        "bio": "یک معرفی کوتاه از خودت بنویس."
    }

    if step == "gender":
        keyboard = telebot.types.ReplyKeyboardMarkup(
            resize_keyboard=True,
            one_time_keyboard=True
        )
        keyboard.row("مرد", "زن", "ترجیح می‌دم نگم")
        bot.send_message(chat_id, questions[step], reply_markup=keyboard)
    else:
        bot.send_message(chat_id, questions[step])

@bot.message_handler(commands=["start"])
def start(message):
    keyboard = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row("👤 ساخت پروفایل", "🔎 پیدا کردن افراد")
    keyboard.row("📩 درخواست‌های من", "⚙️ تنظیمات")
    bot.send_message(
        message.chat.id,
        "سلام! به GapMate خوش اومدی ❤️",
        reply_markup=keyboard
    )

@bot.message_handler(func=lambda m: m.text == "👤 ساخت پروفایل")
def create_profile(message):
    user_id = message.from_user.id
    users[user_id] = {
        "step": "nickname",
        "age": None,
        "nickname": None,
        "city": None,
        "province": None,
        "gender": None,
        "photo": None,
        "bio": None
    }
    ask_next(message.chat.id, user_id)

@bot.message_handler(content_types=["text", "photo"])
def registration(message):
    user_id = message.from_user.id
    if user_id not in users or users[user_id]["step"] == "done":
        bot.reply_to(message, "برای شروع /start رو بفرست.")
        return

    profile = users[user_id]
    step = profile["step"]

    if step == "photo":
        if not message.photo:
            bot.reply_to(message, "لطفاً یک عکس ارسال کن.")
            return
        profile["photo"] = message.photo[-1].file_id
        profile["step"] = "bio"

    elif step == "nickname":
        if not message.text or len(message.text.strip()) < 2:
            bot.reply_to(message, "یک نام مستعار معتبر وارد کن.")
            return
        profile["nickname"] = message.text.strip()[:30]
        profile["step"] = "age"

    elif step == "age":
        if not message.text or not message.text.isdigit():
            bot.reply_to(message, "سن رو فقط با عدد وارد کن.")
            return
        age = int(message.text)
        if age < 16 or age > 99:
            bot.reply_to(message, "ثبت‌نام برای افراد ۱۶ تا ۹۹ ساله است.")
            return
        profile["age"] = age
        profile["step"] = "city"

    elif step == "city":
        if not message.text or len(message.text.strip()) < 2:
            bot.reply_to(message, "نام شهر رو وارد کن.")
            return
        profile["city"] = message.text.strip()[:50]
        profile["step"] = "province"

    elif step == "province":
        if not message.text or len(message.text.strip()) < 2:
            bot.reply_to(message, "نام استان رو وارد کن.")
            return
        profile["province"] = message.text.strip()[:50]
        profile["step"] = "gender"

    elif step == "gender":
        if message.text not in ["مرد", "زن", "ترجیح می‌دم نگم"]:
            bot.reply_to(message, "یکی از گزینه‌های نمایش داده شده رو انتخاب کن.")
            return
        profile["gender"] = message.text
        profile["step"] = "photo"

    elif step == "bio":
        if not message.text or len(message.text.strip()) < 5:
            bot.reply_to(message, "معرفی کوتاه‌تری از خودت بنویس (حداقل ۵ حرف).")
            return
        profile["bio"] = message.text.strip()[:300]
        profile["step"] = "done"

        bot.send_message(
            message.chat.id,
            "پروفایلت با موفقیت تکمیل شد! ❤️\n"
            f"نام مستعار: {profile['nickname']}\n"
            f"سن: {profile['age']}\n"
            f"شهر: {profile['city']}\n"
            f"استان: {profile['province']}\n"
            f"جنسیت: {profile['gender']}\n"
            f"معرفی: {profile['bio']}"
        )
        return

    ask_next(message.chat.id, user_id)

@app.route("/", methods=["GET"])
def home():
    return "GapMate is running!", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    update = telebot.types.Update.de_json(
        request.get_data().decode("utf-8")
    )
    bot.process_new_updates([update])
    return "OK", 200

bot.set_webhook(url=RENDER_URL + "/webhook")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
