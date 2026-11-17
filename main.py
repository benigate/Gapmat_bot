


import os
import telebot
from flask import Flask, request

TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", 10000))
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN is missing")

if not RENDER_URL:
    raise RuntimeError("RENDER_EXTERNAL_URL is missing")

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

@bot.message_handler(commands=["start"])
def start(message):
    keyboard = telebot.types.ReplyKeyboardMarkup(
        resize_keyboard=True
    )
    keyboard.row("👤 ساخت پروفایل", "🔎 پیدا کردن افراد")
    keyboard.row("📩 درخواست‌های من", "⚙️ تنظیمات")

    bot.send_message(
        message.chat.id,
        "سلام! به GapMate خوش اومدی! ❤️\n"
        "برای شروع یکی از گزینه‌ها رو انتخاب کن.",
        reply_markup=keyboard
    )

@bot.message_handler(func=lambda message: True)
def menu(message):
    answers = {
        "👤 ساخت پروفایل": "بخش ساخت پروفایل به‌زودی آماده می‌شه ❤️",
        "🔎 پیدا کردن افراد": "بخش پیدا کردن افراد به‌زودی آماده می‌شه.",
        "📩 درخواست‌های من": "هنوز درخواستی نداری.",
        "⚙️ تنظیمات": "تنظیمات به‌زودی آماده می‌شه."
    }
    bot.reply_to(
        message,
        answers.get(message.text, "برای شروع /start رو بفرست.")
    )

@app.route("/", methods=["GET"])
def home():
    return "GapMate is running!", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    if request.headers.get("content-type") == "application/json":
        update = telebot.types.Update.de_json(
            request.get_data().decode("utf-8")
        )
        bot.process_new_updates([update])
        return "OK", 200
    return "Invalid content type", 400

bot.remove_webhook()
bot.set_webhook(url=RENDER_URL + "/webhook")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
