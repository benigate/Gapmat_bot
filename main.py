import telebot
import os

# جایگزین کردن توکن (بعداً در تنظیمات Render انجام می‌دهیم)
TOKEN = os.getenv('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')

bot = telebot.TeleBot(TOKEN)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "سلام! من GapMate هستم. آماده‌ام تا دنیای جدیدی برای پیدا کردن آدم‌ها بسازم! 🚀")

@bot.message_handler(commands=['help'])
def send_help(message):
    bot.reply_to(message, "در حال ساخت هستم... به زودی قابلیت‌های Matchmaking را اضافه می‌کنم.")

print("GapMate is running...")
bot.infinity_polling()
