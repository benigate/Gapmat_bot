import osfrom flask import Flask
import telebot
from telebot import types
import psycopg2
from psycopg2.extras import RealDictCursor

TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0") or 0)
if not TOKEN or not DATABASE_URL:
    raise RuntimeError("BOT_TOKEN and DATABASE_URL are required")

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

TOMAN = {
    50: "۱۰۰,۰۰۰ تومان", 100: "۲۰۰,۰۰۰ تومان",
    500: "۵۰۰,۰۰۰ تومان", 700: "۷۰۰,۰۰۰ تومان",
    1000: "۱,۵۰۰,۰۰۰ تومان", "VIP": "۲,۵۰۰,۰۰۰ تومان"
}
STARS = {
    50: "۵۰ ستاره", 100: "۷۰ ستاره", 500: "۲۰۰ ستاره",
    700: "۳۵۰ ستاره", 1000: "۵۰۰ ستاره", "VIP": "۷۰۰ ستاره"
}
states = {}

def db():
    return psycopg2.connect(DATABASE_URL, sslmode="require",
                             cursor_factory=RealDictCursor)

def init_db():
    conn = db()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                  user_id BIGINT PRIMARY KEY, nickname TEXT,
                  age INTEGER, gender TEXT, province TEXT, city TEXT,
                  bio TEXT DEFAULT '', photos TEXT[] DEFAULT '{}',
                  coins INTEGER NOT NULL DEFAULT 6,
                  is_vip BOOLEAN DEFAULT FALSE,
                  profile_visible BOOLEAN DEFAULT TRUE,
                  req_min_age INTEGER DEFAULT 18,
                  req_max_age INTEGER DEFAULT 99,
                  created_at TIMESTAMPTZ DEFAULT NOW()
                );
                CREATE TABLE IF NOT EXISTS likes (
                  user_id BIGINT, target_id BIGINT, created_at TIMESTAMPTZ DEFAULT NOW(),
                  PRIMARY KEY(user_id,target_id)
                );
                CREATE TABLE IF NOT EXISTS blocks (
                  user_id BIGINT, blocked_id BIGINT, PRIMARY KEY(user_id,blocked_id)
                );
                CREATE TABLE IF NOT EXISTS reports (
                  id BIGSERIAL PRIMARY KEY, reporter_id BIGINT,
                  target_id BIGINT, reason TEXT, created_at TIMESTAMPTZ DEFAULT NOW()
                );
                CREATE TABLE IF NOT EXISTS chat_requests (
                  id BIGSERIAL PRIMARY KEY, sender_id BIGINT, receiver_id BIGINT,
                  status TEXT DEFAULT 'pending', created_at TIMESTAMPTZ DEFAULT NOW(),
                  expires_at TIMESTAMPTZ DEFAULT NOW()+INTERVAL '5 minutes'
                );
                CREATE TABLE IF NOT EXISTS chats (
                  id BIGSERIAL PRIMARY KEY, user1 BIGINT, user2 BIGINT,
                  active BOOLEAN DEFAULT TRUE, started_at TIMESTAMPTZ DEFAULT NOW(),
                  ended_at TIMESTAMPTZ
                );
                CREATE TABLE IF NOT EXISTS contacts (
                  user_id BIGINT, contact_id BIGINT, PRIMARY KEY(user_id,contact_id)
                );
                """)
    finally:
        conn.close()

def get_user(uid):
    conn = db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM users WHERE user_id=%s", (uid,))
            return cur.fetchone()
    finally:
        conn.close()

def main_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("🔍 جستجوی افراد", "👥 مخاطبین من")
    kb.row("👤 پروفایل من", "🪙 کیف پول")
    kb.row("📞 پشتیبانی", "🔗 دعوت دوستان")
    return kb

def age_keyboard():
    kb = types.InlineKeyboardMarkup(row_width=5)
    kb.add(*[types.InlineKeyboardButton(str(n), callback_data=f"age:{n}")
             for n in range(18, 81)])
    return kb

@app.get("/")
def health():
    return "GapMate OK", 200

@bot.message_handler(commands=["start"])
def start(m):
    u = get_user(m.from_user.id)
    if u and u.get("nickname"):
        bot.send_message(m.chat.id, "خوش برگشتی ❤️", reply_markup=main_menu())
    else:
        states[m.from_user.id] = {"step": "nickname"}
        bot.send_message(m.chat.id, "به GapMate خوش آمدی ❤️ اسم نمایشی‌ات را بفرست.")

@bot.message_handler(content_types=["text"])
def text_handler(m):
    uid, txt = m.from_user.id, (m.text or "").strip()
    st = states.get(uid, {})
    step = st.get("step")
    if step == "nickname":
        st["nickname"] = txt[:50]
        st["step"] = "age"
        bot.send_message(m.chat.id,
            "⚠️ در ثبت سن و جنسیت دقت کن؛ تغییر هرکدام بعداً طبق قوانین سخت‌گیرانه و با هزینه ۱۰۰ سکه انجام می‌شود. سن را انتخاب کن:",
            reply_markup=age_keyboard())
        return
    if step == "province":
        st["province"] = txt[:60]; st["step"] = "city"
        bot.send_message(m.chat.id, "استان ثبت شد. شهرت را بنویس."); return
    if step == "city":
        st["city"] = txt[:60]; st["step"] = "bio"
        bot.send_message(m.chat.id, "یک بیوی کوتاه بنویس (یا -)."); return
    if step == "bio":
        conn = db()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute("""INSERT INTO users(user_id,nickname,age,gender,province,city,bio)
                    VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(user_id) DO UPDATE SET
                    nickname=EXCLUDED.nickname,age=EXCLUDED.age,gender=EXCLUDED.gender,
                    province=EXCLUDED.province,city=EXCLUDED.city,bio=EXCLUDED.bio""",
                    (uid,st["nickname"],st["age"],st["gender"],st["province"],st["city"],"" if txt=="-" else txt[:300]))
        finally:
            conn.close()
        states.pop(uid,None)
        bot.send_message(m.chat.id, "ثبت‌نام کامل شد؛ ۶ سکه هدیه گرفتی.", reply_markup=main_menu())
        return
    if step == "support":
        if ADMIN_ID:
            bot.send_message(ADMIN_ID, f"پیام پشتیبانی از {uid}:\n{txt}")
            bot.send_message(m.chat.id, "پیام به پشتیبانی ارسال شد.")
        else:
            bot.send_message(m.chat.id, "پشتیبانی هنوز تنظیم نشده است.")
        states.pop(uid,None); return
    if txt == "📞 پشتیبانی":
        states[uid] = {"step":"support"}
        bot.send_message(m.chat.id, "پیام خود را برای پشتیبانی بنویس.")
    elif txt == "🪙 کیف پول":
        bot.send_message(m.chat.id, "خرید با تومان:\n" + "\n".join(f"{k} سکه: {v}" for k,v in TOMAN.items()) +
                         "\n\nپرداخت با ستاره:\n" + "\n".join(f"{k} سکه: {v}" for k,v in STARS.items()) +
                         "\n\nبه‌زودی این بخش فعال خواهد شد.")
    elif txt == "👤 پروفایل من":
        u = get_user(uid)
        if u:
            bot.send_message(m.chat.id, f"{u['nickname']} | {u['age']} سال | {u['gender']}\n{u['bio'] or ''}")
    else:
        bot.send_message(m.chat.id, "از منوی اصلی استفاده کن.", reply_markup=main_menu())

@bot.message_handler(content_types=["photo"])
def photos(m):
    uid = m.from_user.id
    if states.get(uid, {}).get("step") == "support":
        if ADMIN_ID:
            bot.send_photo(ADMIN_ID, m.photo[-1].file_id, caption=f"پشتیبانی از کاربر {uid}")
            bot.send_message(m.chat.id, "عکس برای پشتیبانی ارسال شد.")
        states.pop(uid,None); return
    u = get_user(uid)
    if not u: return
    conn = db()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT cardinality(photos) AS n FROM users WHERE user_id=%s FOR UPDATE", (uid,))
                row = cur.fetchone()
                if row["n"] >= 3:
                    bot.send_message(m.chat.id, "حداکثر ۳ عکس رایگان مجاز است."); return
                cur.execute("UPDATE users SET photos=array_append(photos,%s) WHERE user_id=%s",
                            (m.photo[-1].file_id,uid))
    finally:
        conn.close()
    bot.send_message(m.chat.id, "عکس پروفایل ذخیره شد.")

@bot.callback_query_handler(func=lambda c: True)
def callbacks(c):
    uid, data = c.from_user.id, c.data or ""
    try:
        if data.startswith("age:"):
            states[uid]["age"] = int(data.split(":")[1])
            states[uid]["step"] = "gender"
            kb = types.InlineKeyboardMarkup()
            kb.row(types.InlineKeyboardButton("پسر",callback_data="gender:پسر"),
                   types.InlineKeyboardButton("دختر",callback_data="gender:دختر"))
            bot.send_message(c.message.chat.id, "جنسیت را انتخاب کن:", reply_markup=kb)
        elif data.startswith("gender:"):
            states[uid]["gender"] = data.split(":",1)[1]
            states[uid]["step"] = "province"
            bot.send_message(c.message.chat.id, "استانت را بنویس.")
        bot.answer_callback_query(c.id)
    except Exception:
        bot.answer_callback_query(c.id, "خطا رخ داد؛ دوباره تلاش کن.", show_alert=True)

def run_web():
    app.run(host="0.0.0.0", port=int(os.getenv("PORT","10000")))

if __name__ == "__main__":
    init_db()
    import threading
    threading.Thread(target=run_web, daemon=True).start()
    bot.infinity_polling(skip_pending=True)