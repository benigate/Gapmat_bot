
import os
import telebot

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN تنظیم نشده است.")

bot = telebot.TeleBot(TOKEN)

@bot.message_handler(commands=["start"])
def start(message):
    keyboard = telebot.types.ReplyKeyboardMarkup(
        resize_keyboard=True
    )
    keyboard.row("👤 ساخت پروفایل", "🔎 پیدا کردن افراد")
    keyboard.row("📩 درخواست‌های من", "⚙️ تنظیمات")

    bot.send_message(
        message.chat.id,
        "سلام! به GapMate خوش اومدی! ❤️\n\n"
        "اینجا می‌تونی آدم‌های جدید پیدا کنی و ارتباط بسازی.\n"
        "برای شروع یکی از گزینه‌ها رو انتخاب کن.",
        reply_markup=keyboard
    )

@bot.message_handler(func=lambda message: True)
def menu(message):
    if message.text == "👤 ساخت پروفایل":
        bot.reply_to(message, "به‌زودی ثبت‌نام و ساخت پروفایلت رو شروع می‌کنیم! ❤️")
    elif message.text == "🔎 پیدا کردن افراد":
        bot.reply_to(message, "بخش پیدا کردن افراد در حال آماده‌سازیه.")
    elif message.text == "📩 درخواست‌های من":
        bot.reply_to(message, "هنوز درخواستی نداری.")
    elif message.text == "⚙️ تنظیمات":
        bot.reply_to(message, "تنظیمات GapMate به‌زودی آماده می‌شه.")
    else:
        bot.reply_to(message, "برای شروع دستور /start رو بفرست.")

print("GapMate is running...")
bot.infinity_polling()

