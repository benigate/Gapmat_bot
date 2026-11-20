import os
import time
import logging
import threading
import json
import telebot
from telebot import types
from flask import Flask

from db import (
    db, init_db, get_user, get_user_by_account_id, is_reg,
    is_blocked_between, is_silent, dist,
    create_direct_request_with_payment, expire_requests,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0") or 0)
GIFT_STARS = 6
DIRECT_COST = 1
CHAT_COST = 2
DELETE_COST = 25
EDIT_COST = 100
REF_BONUS = 2

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is not set")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
app = Flask(__name__)
logger = logging.getLogger("gapmate")
logging.basicConfig(level=logging.INFO)

states = {}
state_lock = threading.RLock()


# ---------------------------------------------------------------------------
# General helpers
# ---------------------------------------------------------------------------
def is_admin(uid):
    return bool(ADMIN_ID and int(uid) == ADMIN_ID)


def set_state(uid, state, **data):
    with state_lock:
        states[int(uid)] = {"state": state, **data}


def get_state(uid):
    with state_lock:
        return states.get(int(uid), {})


def clear_state(uid):
    with state_lock:
        states.pop(int(uid), None)


def safe_answer(call, text=None, alert=False):
    try:
        bot.answer_callback_query(call.id, text or "", show_alert=alert)
    except Exception:
        pass


def account_label(uid):
    u = get_user(uid) or {}
    return u.get("nickname") or str(uid)



def q(sql, params=(), fetchone=False, fetchall=False, commit=True):
    conn = db()
    cur = conn.cursor()
    try:
        cur.execute(sql, params)
        result = cur.fetchone() if fetchone else (cur.fetchall() if fetchall else None)
        if commit:
            conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()



def user_exists(uid):
    try:
        return bool(is_reg(uid))
    except Exception:
        return bool(get_user(uid))


def stars(uid):
    u = get_user(uid) or {}
    return int(u.get("stars") or 0)


def main_menu_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("🔎 پیدا کردن افراد", "👤 پروفایل من")
    kb.row("❤️ لایک‌ها", "📇 مخاطبین")
    kb.row("⚙️ تنظیمات", "❓ راهنما")
    return kb


def profile_kb(owner=False, target_id=None):
    kb = types.InlineKeyboardMarkup()
    if owner:
        kb.add(types.InlineKeyboardButton("✏️ ویرایش پروفایل", callback_data="edit:menu"))
        kb.add(types.InlineKeyboardButton("⚙️ تنظیمات", callback_data="settings:main"))
    elif target_id is not None:
        kb.row(
            types.InlineKeyboardButton("❤️ لایک", callback_data=f"like:{target_id}"),
            types.InlineKeyboardButton("⏭ رد کردن", callback_data=f"pass:{target_id}"),
        )
        kb.add(types.InlineKeyboardButton("✉️ درخواست پیام مستقیم", callback_data=f"dir:{target_id}"))
        kb.add(types.InlineKeyboardButton("💬 درخواست چت", callback_data=f"req:{target_id}"))
        kb.add(types.InlineKeyboardButton("🚫 مسدود کردن", callback_data=f"block:{target_id}"))
        kb.add(types.InlineKeyboardButton("⚠️ گزارش", callback_data=f"report:{target_id}"))
    return kb


def my_profile_kb():
    return profile_kb(owner=True)


def settings_main_kb():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔒 حریم خصوصی", callback_data="settings:privacy"))
    kb.add(types.InlineKeyboardButton("🔕 حالت بی‌صدا", callback_data="settings:silent"))
    kb.add(types.InlineKeyboardButton("🎯 فیلترها", callback_data="settings:filters"))
    kb.add(types.InlineKeyboardButton("📍 نمایش موقعیت", callback_data="settings:location"))
    kb.add(types.InlineKeyboardButton("⬅️ بازگشت", callback_data="settings:back"))
    return kb


def age_kb(prefix="reg:age"):
    kb = types.InlineKeyboardMarkup(row_width=5)
    btns = [types.InlineKeyboardButton(str(age), callback_data=f"{prefix}:{age}")
            for age in range(18, 81)]
    kb.add(*btns)
    return kb


def gender_kb(prefix="reg:gender"):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("مرد", callback_data=f"{prefix}:male"),
        types.InlineKeyboardButton("زن", callback_data=f"{prefix}:female"),
    )
    return kb


def finish_reg(uid, cid):
    st = get_state(uid)
    data = st.get("data", {})
    required = ("nickname", "age", "gender", "province", "city")
    if any(not data.get(k) for k in required):
        bot.send_message(cid, "اطلاعات ثبت‌نام کامل نیست. از /start دوباره شروع کن.")
        clear_state(uid)
        return
    try:
        q("""
            INSERT INTO users
                (user_id, nickname, age, gender, province, city, bio, stars,
                 profile_visible, location_visible)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,TRUE,TRUE)
            ON CONFLICT (user_id) DO UPDATE SET
                nickname=EXCLUDED.nickname, age=EXCLUDED.age,
                gender=EXCLUDED.gender, province=EXCLUDED.province,
                city=EXCLUDED.city
        """, (uid, data["nickname"], int(data["age"]), data["gender"],
              data["province"], data["city"], data.get("bio", ""), GIFT_STARS))
        clear_state(uid)
        bot.send_message(cid, f"ثبت‌نام انجام شد 🌷\n🎁 {GIFT_STARS} سکه هدیه گرفتی.", reply_markup=main_menu_kb())
    except Exception:
        logger.exception("finish_reg failed")
        bot.send_message(cid, "ثبت‌نام انجام نشد. کمی بعد دوباره تلاش کن.")


def show_profile(cid, uid, owner=False):
    u = get_user(uid)
    if not u:
        bot.send_message(cid, "پروفایلی پیدا نشد.")
        return
    text = (
        f"👤 <b>{u.get('nickname') or 'بدون نام'}</b>\n"
        f"سن: {u.get('age') or '—'}\n"
        f"جنسیت: {u.get('gender') or '—'}\n"
        f"استان: {u.get('province') or '—'}\n"
        f"شهر: {u.get('city') or '—'}\n"
        f"درباره من: {u.get('bio') or '—'}"
    )
    if owner:
        text += f"\n\n🪙 موجودی: {stars(uid)}"
    photos = u.get("photos") or []
    if isinstance(photos, str):
        try:
            photos = json.loads(photos)
        except Exception:
            photos = []
    if photos:
        try:
            media = [types.InputMediaPhoto(p) for p in photos[:3]]
            bot.send_media_group(cid, media)
        except Exception:
            logger.exception("sending profile photos failed")
    bot.send_message(cid, text, reply_markup=my_profile_kb() if owner else profile_kb(False, uid))


def find(cid, uid):
    u = get_user(uid) or {}
    clauses = ["user_id <> %s", "COALESCE(profile_visible, TRUE)=TRUE"]
    params = [uid]
    if u.get("req_gender"):
        clauses.append("gender=%s")
        params.append(u["req_gender"])
    if u.get("req_province") and u.get("province"):
        clauses.append("province=%s")
        params.append(u["province"])
    if u.get("req_city") and u.get("city"):
        clauses.append("city=%s")
        params.append(u["city"])
    clauses.append("user_id NOT IN (SELECT target_id FROM passes WHERE user_id=%s)")
    params.append(uid)
    clauses.append("user_id NOT IN (SELECT target_id FROM likes WHERE user_id=%s)")
    params.append(uid)
    clauses.append("""user_id NOT IN (
        SELECT blocked_id FROM blocks WHERE blocker_id=%s
        UNION SELECT blocker_id FROM blocks WHERE blocked_id=%s
    )""")
    params.extend([uid, uid])
    row = q("SELECT user_id FROM users WHERE " + " AND ".join(clauses) + " ORDER BY RANDOM() LIMIT 1",
            tuple(params), fetchone=True)
    if not row:
        bot.send_message(cid, "فعلاً فرد جدیدی برای نمایش پیدا نشد.", reply_markup=main_menu_kb())
        return
    show_profile(cid, int(row[0]), owner=False)


def like(uid, tid, cid):
    if uid == tid:
        return
    q("INSERT INTO likes(user_id,target_id) VALUES(%s,%s) ON CONFLICT DO NOTHING", (uid, tid))
    bot.send_message(cid, "لایک ثبت شد ❤️")
    try:
        bot.send_message(tid, f"❤️ {account_label(uid)} از پروفایلت خوشش آمده.")
    except Exception:
        pass
    find(cid, uid)


def pass_user(uid, tid, cid):
    q("INSERT INTO passes(user_id,target_id) VALUES(%s,%s) ON CONFLICT DO NOTHING", (uid, tid))
    find(cid, uid)


def show_contacts(cid, uid):
    rows = q("""
        SELECT u.user_id,u.nickname FROM contacts c
        JOIN users u ON u.user_id=c.contact_id
        WHERE c.user_id=%s ORDER BY u.nickname
    """, (uid,), fetchall=True) or []
    if not rows:
        bot.send_message(cid, "هنوز مخاطبی نداری.")
        return
    kb = types.InlineKeyboardMarkup()
    for tid, name in rows:
        kb.add(types.InlineKeyboardButton(name or str(tid), callback_data=f"view:{tid}"))
    bot.send_message(cid, "📇 مخاطبین:", reply_markup=kb)


def add_contact(uid, tid):
    q("INSERT INTO contacts(user_id,contact_id) VALUES(%s,%s) ON CONFLICT DO NOTHING", (uid, tid))


def block_user(uid, tid, cid):
    q("INSERT INTO blocks(blocker_id,blocked_id) VALUES(%s,%s) ON CONFLICT DO NOTHING", (uid, tid))
    bot.send_message(cid, "کاربر مسدود شد.")
    try:
        q("DELETE FROM contacts WHERE (user_id=%s AND contact_id=%s) OR (user_id=%s AND contact_id=%s)",
          (uid, tid, tid, uid))
    except Exception:
        pass


def start_chat(uid, tid):
    if is_blocked_between(uid, tid):
        return False
    row = q("""
        INSERT INTO chats(user1_id,user2_id,active,created_at)
        VALUES(%s,%s,TRUE,NOW()) RETURNING id
    """, (uid, tid), fetchone=True)
    return bool(row)



def start_chat(uid, tid):
    if is_blocked_between(uid, tid):
        return False

    user1, user2 = sorted((uid, tid))

    row = q("""
        INSERT INTO chats(user1, user2, active, created_at)
        VALUES(%s, %s, TRUE, NOW())
        ON CONFLICT (user1, user2)
        DO UPDATE SET active = TRUE
        RETURNING user1
    """, (user1, user2), fetchone=True)

    return bool(row)
    
    try:
        bot.copy_message(int(row[0]), message.chat.id, message.message_id)
        return True
    except Exception:
        logger.exception("relay failed")
        return False


def process_req(uid, tid, cid, rtype):
    if uid == tid or is_blocked_between(uid, tid):
        bot.send_message(cid, "امکان ارسال درخواست وجود ندارد.")
        return
    cost = DIRECT_COST if rtype == "direct" else CHAT_COST
    if stars(uid) < cost:
        bot.send_message(cid, f"سکه کافی نداری. هزینه این درخواست {cost} سکه است.")
        return
    set_state(uid, "request_message", target_id=tid, request_type=rtype)
    bot.send_message(cid, "متن درخواستت را بنویس؛ برای لغو /cancel را بفرست.")


def send_req(uid, tid, cid, rtype, message_text=""):
    try:
        result = create_direct_request_with_payment(uid, tid, rtype, message_text)
        if not result:
            bot.send_message(cid, "درخواست ارسال نشد؛ محدودیت ساعتی یا موجودی سکه را بررسی کن.")
            return
        request_id = result.get("id") if isinstance(result, dict) else result
        kb = types.InlineKeyboardMarkup()
        kb.row(
            types.InlineKeyboardButton("پذیرفتن", callback_data=f"appr:{request_id}"),
            types.InlineKeyboardButton("رد کردن", callback_data=f"rej:{request_id}"),
        )
        bot.send_message(tid, f"📩 درخواست جدید از {account_label(uid)}\n{message_text or ''}",
                         reply_markup=kb)
        bot.send_message(cid, "درخواستت ارسال شد.")
    except Exception:
        logger.exception("send request failed")
        bot.send_message(cid, "ارسال درخواست با خطا روبه‌رو شد.")


def delete_account(uid, cid):
    if stars(uid) < DELETE_COST:
        bot.send_message(cid, f"برای حذف حساب به {DELETE_COST} سکه نیاز داری.")
        return
    try:
        q("BEGIN", commit=False)
        q("UPDATE users SET stars=stars-%s WHERE user_id=%s", (DELETE_COST, uid), commit=False)
        for table, col in [
            ("likes", "user_id"), ("likes", "target_id"),
            ("passes", "user_id"), ("passes", "target_id"),
            ("blocks", "blocker_id"), ("blocks", "blocked_id"),
            ("contacts", "user_id"), ("contacts", "contact_id"),
            ("chats", "user1_id"), ("chats", "user2_id"),
        ]:
            q(f"DELETE FROM {table} WHERE {col}=%s", (uid,), commit=False)
        q("DELETE FROM users WHERE user_id=%s", (uid,), commit=False)
        db.commit()
        clear_state(uid)
        bot.send_message(cid, "حسابت حذف شد.")
    except Exception:
        db.rollback()
        logger.exception("delete account failed")
        bot.send_message(cid, "حذف حساب انجام نشد؛ هیچ تغییری ثبت نشد.")


# ---------------------------------------------------------------------------
# Commands and message handlers
# ---------------------------------------------------------------------------
@bot.message_handler(commands=["start"])
def c_start(m):
    uid, cid = m.from_user.id, m.chat.id
    if user_exists(uid):
        bot.send_message(cid, "خوش برگشتی 🌷", reply_markup=main_menu_kb())
        return
    set_state(uid, "reg_name", data={})
    bot.send_message(cid, "سلام! برای شروع، نام نمایشی‌ات را بفرست.")


@bot.message_handler(commands=["cancel"])
def c_cancel(m):
    clear_state(m.from_user.id)
    bot.send_message(m.chat.id, "لغو شد.", reply_markup=main_menu_kb())


@bot.message_handler(commands=["admin"])
def c_admin(m):
    if not is_admin(m.from_user.id):
        return
    row = q("SELECT COUNT(*) FROM users", fetchone=True)
    bot.send_message(m.chat.id, f"تعداد کاربران: {row[0] if row else 0}")


@bot.message_handler(commands=["stop"])
def c_stop(m):
    stop_chat(m.from_user.id)
    bot.send_message(m.chat.id, "گفت‌وگو متوقف شد.", reply_markup=main_menu_kb())


@bot.message_handler(content_types=["location"])
def c_loc(m):
    uid = m.from_user.id
    st = get_state(uid)
    if st.get("state") == "edit_location":
        q("UPDATE users SET lat=%s,lon=%s WHERE user_id=%s",
          (m.location.latitude, m.location.longitude, uid))
        clear_state(uid)
        bot.send_message(m.chat.id, "موقعیت ذخیره شد.")
    else:
        bot.send_message(m.chat.id, "برای ذخیره موقعیت، از بخش ویرایش پروفایل اقدام کن.")


@bot.message_handler(content_types=["photo"])
def c_photo(m):
    uid = m.from_user.id
    st = get_state(uid)
    if st.get("state") != "edit_photo":
        if relay(m):
            return
        bot.send_message(m.chat.id, "برای افزودن عکس از ویرایش پروفایل استفاده کن.")
        return
    u = get_user(uid) or {}
    photos = u.get("photos") or []
    if isinstance(photos, str):
        try:
            photos = json.loads(photos)
        except Exception:
            photos = []
    if len(photos) >= 3:
        bot.send_message(m.chat.id, "حداکثر ۳ عکس می‌توانی داشته باشی.")
        return
    fid = m.photo[-1].file_id
    photos.append(fid)
    q("UPDATE users SET photos=%s WHERE user_id=%s", (json.dumps(photos), uid))
    clear_state(uid)
    bot.send_message(m.chat.id, "عکس ذخیره شد. برای افزودن عکس بعدی دوباره همین گزینه را بزن.")


@bot.message_handler(content_types=["text"])
def c_text(m):
    uid, cid = m.from_user.id, m.chat.id
    text = (m.text or "").strip()
    if text.startswith("/"):
        return
    st = get_state(uid)
    state = st.get("state")

    if state == "reg_name":
        data = st.get("data", {})
        data["nickname"] = text[:40]
        set_state(uid, "reg_age", data=data)
        bot.send_message(cid, "سن را انتخاب کن:", reply_markup=age_kb())
        return
    if state == "reg_age":
        return
    if state == "reg_province":
        data = st.get("data", {})
        data["province"] = text[:60]
        set_state(uid, "reg_city", data=data)
        bot.send_message(cid, "نام شهرت را بفرست.")
        return
    if state == "reg_city":
        data = st.get("data", {})
        data["city"] = text[:60]
        data["bio"] = ""
        set_state(uid, "reg_gender", data=data)
        bot.send_message(cid, "جنسیت را انتخاب کن:", reply_markup=gender_kb())
        return
    if state == "request_message":
        send_req(uid, int(st["target_id"]), cid, st["request_type"], text[:1000])
        clear_state(uid)
        return
    if state and state.startswith("edit_"):
        field = state[5:]
        columns = {"name": "nickname", "bio": "bio", "province": "province", "city": "city"}
        if field in columns:
            q(f"UPDATE users SET {columns[field]}=%s WHERE user_id=%s", (text[:500], uid))
            clear_state(uid)
            bot.send_message(cid, "تغییرات ذخیره شد.")
            return
    if relay(m):
        return

    if not user_exists(uid):
        bot.send_message(cid, "برای شروع /start را بزن.")
        return
    if text in ("🔎 پیدا کردن افراد", "پیدا کردن افراد"):
        find(cid, uid)
    elif text in ("👤 پروفایل من", "پروفایل من"):
        show_profile(cid, uid, owner=True)
    elif text in ("❤️ لایک‌ها", "لایک‌ها"):
        rows = q("""SELECT u.user_id,u.nickname FROM likes l JOIN users u
                    ON u.user_id=l.user_id WHERE l.target_id=%s""", (uid,), fetchall=True) or []
        if not rows:
            bot.send_message(cid, "هنوز لایکی نداری.")
        else:
            kb = types.InlineKeyboardMarkup()
            for tid, name in rows:
                kb.add(types.InlineKeyboardButton(name or str(tid), callback_data=f"view:{tid}"))
            bot.send_message(cid, "افرادی که لایکت کرده‌اند:", reply_markup=kb)
    elif text in ("📇 مخاطبین", "مخاطبین"):
        show_contacts(cid, uid)
    elif text in ("⚙️ تنظیمات", "تنظیمات"):
        bot.send_message(cid, "⚙️ تنظیمات:", reply_markup=settings_main_kb())
    elif text in ("❓ راهنما", "راهنما"):
        bot.send_message(cid, "برای دیدن افراد «پیدا کردن افراد» را بزن. برای توقف چت /stop و برای لغو عملیات /cancel را بفرست.")


# ---------------------------------------------------------------------------
# Callback handlers
# ---------------------------------------------------------------------------
@bot.callback_query_handler(func=lambda c: True)
def callback_handler(c):
    uid, cid, mid = c.from_user.id, c.message.chat.id, c.message.message_id
    d = c.data or ""
    try:
        if d.startswith("reg:age:"):
            age = int(d.split(":")[-1])
            if not 18 <= age <= 80:
                safe_answer(c, "سن نامعتبر است.", True)
                return
            st = get_state(uid)
            data = st.get("data", {})
            data["age"] = age
            set_state(uid, "reg_province", data=data)
            safe_answer(c)
            bot.send_message(cid, "استان محل سکونتت را بنویس.")
        elif d.startswith("reg:gender:"):
            gender = d.split(":")[-1]
            if gender not in ("male", "female"):
                safe_answer(c, "گزینه نامعتبر است.", True)
                return
            st = get_state(uid)
            data = st.get("data", {})
            data["gender"] = gender
            set_state(uid, "reg_province", data=data)
            safe_answer(c)
            bot.send_message(cid, "استان محل سکونتت را بنویس.")
        elif d.startswith("like:"):
            safe_answer(c)
            like(uid, int(d.split(":")[1]), cid)
        elif d.startswith("pass:"):
            safe_answer(c)
            pass_user(uid, int(d.split(":")[1]), cid)
        elif d.startswith("dir:"):
            safe_answer(c)
            process_req(uid, int(d.split(":")[1]), cid, "direct")
        elif d.startswith("req:"):
            safe_answer(c)
            process_req(uid, int(d.split(":")[1]), cid, "chat")
        elif d.startswith("block:"):
            safe_answer(c)
            block_user(uid, int(d.split(":")[1]), cid)
        elif d.startswith("report:"):
            tid = int(d.split(":")[1])
            q("INSERT INTO reports(reporter_id,reported_id,created_at) VALUES(%s,%s,NOW())",
              (uid, tid))
            safe_answer(c, "گزارش ثبت شد.")
        elif d.startswith("view:"):
            safe_answer(c)
            show_profile(cid, int(d.split(":")[1]), owner=False)
        elif d.startswith("appr:") or d.startswith("rej:"):
            request_id = int(d.split(":")[1])
            approved = d.startswith("appr:")
            row = q("""SELECT sender_id,receiver_id,request_type,expires_at,status
                       FROM direct_requests WHERE id=%s""", (request_id,), fetchone=True)
            if not row or int(row[1]) != uid or row[4] != "pending":
                safe_answer(c, "این درخواست معتبر یا فعال نیست.", True)
                return
            sender_id, receiver_id, rtype, expires_at, status = row
            if expires_at and expires_at < __import__("datetime").datetime.now(expires_at.tzinfo):
                q("UPDATE direct_requests SET status='expired' WHERE id=%s", (request_id,))
                safe_answer(c, "مهلت درخواست تمام شده است.", True)
                return
            q("UPDATE direct_requests SET status=%s WHERE id=%s AND receiver_id=%s AND status='pending'",
              ("accepted" if approved else "rejected", request_id, uid))
            safe_answer(c, "ثبت شد.")
            if approved:
                add_contact(uid, int(sender_id))
                add_contact(int(sender_id), uid)
                if rtype == "chat":
                    start_chat(uid, int(sender_id))
                    bot.send_message(int(sender_id), "درخواست چت پذیرفته شد. می‌توانید گفتگو کنید.")
                    bot.send_message(uid, "درخواست پذیرفته شد. گفتگو آغاز شد.")
                else:
                    bot.send_message(int(sender_id), "درخواست پیام مستقیم پذیرفته شد.")
            else:
                bot.send_message(int(sender_id), "درخواستت پذیرفته نشد.")
        elif d == "settings:main":
            safe_answer(c)
            bot.send_message(cid, "⚙️ تنظیمات:", reply_markup=settings_main_kb())
        elif d == "settings:back":
            safe_answer(c)
            bot.send_message(cid, "منوی اصلی:", reply_markup=main_menu_kb())
        elif d == "settings:privacy":
            safe_answer(c)
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton("تغییر نمایش پروفایل", callback_data="privacy:profile"))
            kb.add(types.InlineKeyboardButton("تغییر نمایش موقعیت", callback_data="privacy:location"))
            bot.send_message(cid, "🔒 حریم خصوصی:", reply_markup=kb)
        elif d == "privacy:profile":
            q("UPDATE users SET profile_visible=NOT COALESCE(profile_visible,TRUE) WHERE user_id=%s", (uid,))
            safe_answer(c, "تنظیم ذخیره شد.")
        elif d == "privacy:location":
            q("UPDATE users SET location_visible=NOT COALESCE(location_visible,TRUE) WHERE user_id=%s", (uid,))
            safe_answer(c, "تنظیم ذخیره شد.")
        elif d == "settings:silent":
            kb = types.InlineKeyboardMarkup()
            for label, val in [("۱ ساعت", "1 hour"), ("۲۴ ساعت", "24 hours"), ("دائمی", "permanent"), ("خاموش", "off")]:
                kb.add(types.InlineKeyboardButton(label, callback_data=f"silent:{val}"))
            safe_answer(c)
            bot.send_message(cid, "مدت حالت بی‌صدا را انتخاب کن:", reply_markup=kb)
        elif d.startswith("silent:"):
            val = d.split(":", 1)[1]
            if val == "off":
                q("UPDATE users SET silent_until=NULL WHERE user_id=%s", (uid,))
            elif val == "permanent":
                q("UPDATE users SET silent_until='infinity'::timestamp WHERE user_id=%s", (uid,))
            else:
                q("UPDATE users SET silent_until=NOW()+(%s)::interval WHERE user_id=%s", (val, uid))
            safe_answer(c, "ذخیره شد.")
        elif d == "settings:filters":
            u = get_user(uid) or {}
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton(
                "فیلتر استان: " + ("روشن" if u.get("req_province") else "خاموش"),
                callback_data="filt:prov"))
            kb.add(types.InlineKeyboardButton(
                "فیلتر شهر: " + ("روشن" if u.get("req_city") else "خاموش"),
                callback_data="filt:city"))
            safe_answer(c)
            bot.send_message(cid, "🎯 فیلترها:", reply_markup=kb)
        elif d == "filt:prov":
            q("UPDATE users SET req_province=NOT COALESCE(req_province,FALSE) WHERE user_id=%s", (uid,))
            safe_answer(c, "ذخیره شد.")
        elif d == "filt:city":
            q("UPDATE users SET req_city=NOT COALESCE(req_city,FALSE) WHERE user_id=%s", (uid,))
            safe_answer(c, "ذخیره شد.")
        elif d == "settings:location":
            safe_answer(c)
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton("ارسال موقعیت", callback_data="location:ask"))
            bot.send_message(cid, "برای ذخیره موقعیت، دکمه زیر را بزن و موقعیتت را ارسال کن.", reply_markup=kb)
        elif d == "location:ask":
            safe_answer(c)
            set_state(uid, "edit_location")
            bot.send_message(cid, "از گیره کاغذ تلگرام، Location را ارسال کن.")
        elif d == "edit:menu":
            safe_answer(c)
            kb = types.InlineKeyboardMarkup()
            for label, key in [
                ("نام", "name"), ("سن", "age"), ("جنسیت", "gender"),
                ("استان", "province"), ("شهر", "city"), ("بیو", "bio"),
                ("افزودن عکس", "photo"), ("موقعیت", "location"),
            ]:
                kb.add(types.InlineKeyboardButton(label, callback_data=f"edit:{key}"))
            bot.send_message(cid, "چه بخشی را می‌خواهی ویرایش کنی؟", reply_markup=kb)
        elif d == "edit:name":
            set_state(uid, "edit_name")
            safe_answer(c)
            bot.send_message(cid, "نام جدید را بفرست. هزینه: ۵۰ سکه.")
        elif d == "edit:bio":
            set_state(uid, "edit_bio")
            safe_answer(c)
            bot.send_message(cid, "متن جدید درباره من را بفرست.")
        elif d == "edit:province":
            set_state(uid, "edit_province")
            safe_answer(c)
            bot.send_message(cid, "استان جدید را بفرست.")
        elif d == "edit:city":
            set_state(uid, "edit_city")
            safe_answer(c)
            bot.send_message(cid, "شهر جدید را بفرست.")
        elif d == "edit:photo":
            set_state(uid, "edit_photo")
            safe_answer(c)
            bot.send_message(cid, "عکس را ارسال کن؛ حداکثر ۳ عکس.")
        elif d == "edit:location":
            set_state(uid, "edit_location")
            safe_answer(c)
            bot.send_message(cid, "موقعیتت را از طریق Location ارسال کن.")
        elif d == "edit:age":
            safe_answer(c)
            bot.send_message(cid, "سن جدید را انتخاب کن:", reply_markup=age_kb("edit:ageval"))
        elif d.startswith("edit:ageval:"):
            age = int(d.split(":")[-1])
            if not 18 <= age <= 80:
                safe_answer(c, "سن نامعتبر است.", True)
                return
            if stars(uid) < EDIT_COST:
                safe_answer(c, "سکه کافی نیست.", True)
                return
            q("UPDATE users SET age=%s,stars=stars-%s WHERE user_id=%s AND stars>=%s",
              (age, EDIT_COST, uid, EDIT_COST))
            safe_answer(c, "سن ذخیره شد.")
            bot.send_message(cid, "سن به‌روزرسانی شد.")
        elif d == "edit:gender":
            safe_answer(c)
            bot.send_message(cid, "جنسیت جدید را انتخاب کن:", reply_markup=gender_kb("edit:genderval"))
        elif d.startswith("edit:genderval:"):
            gender = d.split(":")[-1]
            if gender not in ("male", "female"):
                safe_answer(c, "گزینه نامعتبر.", True)
                return
            if stars(uid) < EDIT_COST:
                safe_answer(c, "سکه کافی نیست.", True)
                return
            q("UPDATE users SET gender=%s,stars=stars-%s WHERE user_id=%s AND stars>=%s",
              (gender, EDIT_COST, uid, EDIT_COST))
            safe_answer(c, "جنسیت ذخیره شد.")
            bot.send_message(cid, "جنسیت به‌روزرسانی شد.")
        elif d == "account:delete":
            safe_answer(c)
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton("تأیید حذف", callback_data="account:delete:confirm"))
            bot.send_message(cid, f"حذف حساب {DELETE_COST} سکه هزینه دارد. مطمئنی؟", reply_markup=kb)
        elif d == "account:delete:confirm":
            safe_answer(c)
            delete_account(uid, cid)
        else:
            safe_answer(c)
    except Exception:
        logger.exception("callback error: %s", d)
        safe_answer(c, "خطایی رخ داد. دوباره تلاش کن.", True)


# ---------------------------------------------------------------------------
# Background tasks / web service
# ---------------------------------------------------------------------------
@app.get("/")
def health():
    return "GapMate bot is running", 200


def expire_loop():
    while True:
        try:
            expire_requests()
        except Exception:
            logger.exception("expire_requests failed")
        time.sleep(60)


def run():
    init_db()
    threading.Thread(target=expire_loop, daemon=True).start()

    port = int(os.environ.get("PORT", 10000))

    threading.Thread(
        target=lambda: app.run(
            host="0.0.0.0",
            port=port,
            use_reloader=False
        ),
        daemon=True
    ).start()

    bot.infinity_polling(
        skip_pending=True,
        timeout=30,
        long_polling_timeout=30
    )


if __name__ == "__main__":
    run()
