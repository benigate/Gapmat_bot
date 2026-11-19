import os
import time
import logging
import threading
import telebot
from telebot import types
from flask import Flask
from db import (
db,
init_db,
get_user,
get_user_by_account_id,
is_reg,
is_blocked_between,
is_silent,
dist,
create_direct_request_with_payment,
expire_requests,
)
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID_RAW = os.getenv("ADMIN_ID")
try:
ADMIN_ID = int(ADMIN_ID_RAW) if ADMIN_ID_RAW else None
except ValueError:
ADMIN_ID = None
Coin amounts — keep exactly as in the original. Do not change prices.
GIFT_STARS = 6
DIRECT_COST = 1
CHAT_COST = 2
DELETE_COST = 25
EDIT_COST = 100
Referral bonus (stars given to the referrer), configurable via env.
REF_BONUS = int(os.getenv("REF_BONUS", "2") or 2)
if not BOT_TOKEN:
raise RuntimeError("BOT_TOKEN missing")
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(name)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(name)
states = {}
def is_admin(uid):
return ADMIN_ID is not None and uid == ADMIN_ID
def safe_answer(callback_id, text=None, show_alert=False):
"""Answer a callback query without raising if it was already answered."""
try:
if text:
bot.answer_callback_query(callback_id, text, show_alert=show_alert)
else:
bot.answer_callback_query(callback_id)
except Exception:
pass
def account_label(user):
"""Public label for a user: nickname + internal bot account_id.
Never expose the Telegram user_id to other users.
"""
if not user:
    return "کاربر ناشناس"
nickname = user.get("nickname") or "کاربر"
account_id = user.get("account_id")
if account_id is not None:
    return f"{nickname} (آیدی اکانت: {account_id})"
return nickname
def main_menu_kb():
kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
kb.row("🔍 جستجوی افراد", "👥 مخاطبین من")
kb.row("👤 پروفایل من", "🪙 کیف پول")
kb.row("🔗 دعوت دوستان")
return kb
def profile_kb(tid):
kb = types.InlineKeyboardMarkup()
kb.row(types.InlineKeyboardButton("❤️ لایک", callback_data=f"like:{tid}"), types.InlineKeyboardButton("👎 رد", callback_data=f"pass:{tid}"))
kb.row(types.InlineKeyboardButton("✉️ دایرکت (۱ سکه)", callback_data=f"dir:{tid}"), types.InlineKeyboardButton("💬 درخواست چت (۲ سکه)", callback_data=f"req:{tid}"))
kb.row(types.InlineKeyboardButton("➕ افزودن به مخاطبین", callback_data=f"add:{tid}"))
kb.row(types.InlineKeyboardButton("🚫 بلاک", callback_data=f"block:{tid}"), types.InlineKeyboardButton("⚠️ گزارش", callback_data=f"report:{tid}"))
return kb
def my_profile_kb():
kb = types.InlineKeyboardMarkup()
kb.row(types.InlineKeyboardButton("✏️ ویرایش پروفایل", callback_data="edit:menu"), types.InlineKeyboardButton("⚙️ تنظیمات", callback_data="settings:main"))
return kb
def settings_main_kb():
kb = types.InlineKeyboardMarkup()
kb.add(types.InlineKeyboardButton("👤 حریم خصوصی", callback_data="set:privacy"))
kb.add(types.InlineKeyboardButton("📍 تغییر موقعیت جغرافیایی", callback_data="set:loc"))
kb.add(types.InlineKeyboardButton("🗑 حذف حساب", callback_data="set:del"))
return kb
def age_kb(prefix):
kb = types.InlineKeyboardMarkup(row_width=5)
btns = [types.InlineKeyboardButton(str(i), callback_data=f"{prefix}:{i}") for i in range(18, 81)]
kb.add(*btns)
return kb
def finish_reg(uid, cid):
d = states.pop(uid, None)
if not d:
return
referred_by = d.get("referred_by")
conn = db()
cur = conn.cursor()