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

GIFT_STARS = 6
DIRECT_COST = 1
CHAT_COST = 2
DELETE_COST = 25
EDIT_COST = 100
REF_BONUS = int(os.getenv("REF_BONUS", "2") or 2)

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN missing")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
states = {}


def is_admin(uid):
    return ADMIN_ID is not None and uid == ADMIN_ID


def safe_answer(callback_id, text=None, show_alert=False):
    try:
        if text:
            bot.answer_callback_query(callback_id, text, show_alert=show_alert)
        else:
            bot.answer_callback_query(callback_id)
    except Exception:
        pass


def account_label(user):
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
    kb.row(types.InlineKeyboardButton(f"✉️ دایرکت ({DIRECT_COST} سکه)", callback_data=f"dir:{tid}"), types.InlineKeyboardButton(f"💬 درخواست چت ({CHAT_COST} سکه)", callback_data=f"req:{tid}"))
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
    try:
        cur.execute(
            "INSERT INTO users (user_id, nickname, age, gender, province, city, bio, stars, referred_by) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "ON CONFLICT (user_id) DO UPDATE SET nickname=EXCLUDED.nickname, age=EXCLUDED.age, "
            "gender=EXCLUDED.gender, province=EXCLUDED.province, city=EXCLUDED.city, bio=EXCLUDED.bio",
            (uid, d["nickname"], d["age"], d["gender"], d["province"], d["city"], d["bio"], GIFT_STARS, referred_by),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()
    bot.send_message(cid, f"🎉 ثبت‌نام کامل شد! {GIFT_STARS} سکه هدیه گرفتی.", reply_markup=main_menu_kb())
    if referred_by and referred_by != uid:
        try:
            referrer = get_user(referred_by)
        except Exception:
            referrer = None
        if referrer:
            try:
                conn = db()
                cur = conn.cursor()
                try:
                    if REF_BONUS > 0:
                        cur.execute("UPDATE users SET stars = stars + %s WHERE user_id = %s", (REF_BONUS, referred_by))
                        conn.commit()
                finally:
                    cur.close()
                    conn.close()
                bot.send_message(
                    referred_by,
                    f"🎉 یک نفر با لینک دعوت شما ثبت‌نام کرد! {REF_BONUS} سکه هدیه گرفتید." if REF_BONUS > 0 else "🎉 یک نفر با لینک دعوت شما ثبت‌نام کرد!",
                )
            except Exception:
                logger.exception("Referral reward failed")


def show_profile(cid, uid, target_id=None):
    tid = target_id or uid
    u = get_user(tid)
    if not u:
        return
    vip = " 👑" if u.get("is_vip") else ""
    account_id = u.get("account_id")
    account_line = f"\n🆔 آیدی اکانت: {account_id}" if account_id is not None else ""
    text = f"👤 {u['nickname']}{vip}{account_line}\n🎂 {u['age']} ساله\n⚧ {u['gender']}\n📍 {u['province']}، {u['city']}\n\n📝 {u['bio'] or 'بدون بیو'}\n⭐ {u['stars']}"
    photos = u.get("photos", "").split(",") if u.get("photos") else []
    photos = [p for p in photos if p]
    kb = profile_kb(tid) if target_id else my_profile_kb()
    if photos:
        if len(photos) == 1:
            bot.send_photo(cid, photos[0], caption=text, reply_markup=kb)
        else:
            bot.send_media_group(cid, [types.InputMediaPhoto(p) for p in photos])
            bot.send_message(cid, text, reply_markup=kb)
    else:
        bot.send_message(cid, text, reply_markup=kb)


def find(cid, uid):
    u = get_user(uid)
    if not u:
        return
    if u["lat"] is None:
        bot.send_message(cid, "اول موقعیت بفرست.", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add(types.KeyboardButton("📍 ارسال موقعیت", request_location=True)))
        return
    conn = db()
    cur = conn.cursor()
    try:
        q = (
            "SELECT * FROM users WHERE user_id!=%s AND nickname IS NOT NULL "
            "AND profile_visible=TRUE AND lat IS NOT NULL AND lon IS NOT NULL "
            "AND user_id NOT IN (SELECT target_id FROM passes WHERE user_id=%s) "
            "AND user_id NOT IN (SELECT target_id FROM likes WHERE user_id=%s) "
            "AND user_id NOT IN (SELECT blocked_id FROM blocks WHERE user_id=%s) "
            "AND user_id NOT IN (SELECT user_id FROM blocks WHERE blocked_id=%s)"
        )
        p = [uid, uid, uid, uid, uid]
        if u.get("req_gender") and u["req_gender"] != "any":
            q += " AND gender=%s"
            p.append(u["req_gender"])
        if u.get("req_province") and u.get("province"):
            q += " AND province=%s"
            p.append(u["province"])
        if u.get("req_city") and u.get("city"):
            q += " AND city=%s"
            p.append(u["city"])
        if u.get("req_min_age"):
            q += " AND age>=%s"
            p.append(u["req_min_age"])
        if u.get("req_max_age"):
            q += " AND age<=%s"
            p.append(u["req_max_age"])
        cur.execute(q, tuple(p))
        c = cur.fetchall()
    finally:
        cur.close()
        conn.close()
    if not c:
        bot.send_message(cid, "کسی پیدا نشد.")
        return
    c = [x for x in c if x.get("lat") is not None and x.get("lon") is not None]
    if not c:
        bot.send_message(cid, "کسی پیدا نشد.")
        return

    def _dist_key(x):
        try:
            return dist(u["lat"], u["lon"], x["lat"], x["lon"])
        except Exception:
            return float("inf")

    c.sort(key=_dist_key)
    show_profile(cid, uid, target_id=c[0]["user_id"])


def like(uid, tid, cid):
    if uid == tid:
        return
    try:
        if is_blocked_between(uid, tid):
            bot.send_message(cid, "❌ این کاربر در دسترس نیست.")
            return
    except Exception:
        logger.exception("Block check failed in like")
    target = get_user(tid)
    if target and is_silent(target):
        bot.send_message(cid, "❌ کاربر سایلنت است.")
        return
    sender = get_user(uid)
    conn = db()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO likes (user_id, target_id) VALUES (%s,%s) ON CONFLICT DO NOTHING", (uid, tid))
        conn.commit()
        try:
            bot.send_message(
                tid,
                f"❤️ یک نفر پروفایل شما را پسندید!\n👤 {account_label(sender)}",
            )
        except Exception:
            pass
    except Exception:
        conn.rollback()
        logger.exception("Like failed")
    finally:
        cur.close()
        conn.close()
    bot.send_message(cid, "❤️ لایک ثبت شد.")
    find(cid, uid)


def pass_user(uid, tid, cid):
    conn = db()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO passes (user_id, target_id) VALUES (%s,%s) ON CONFLICT DO NOTHING", (uid, tid))
        conn.commit()
    finally:
        cur.close()
        conn.close()
    find(cid, uid)


def show_contacts(cid, uid):
    conn = db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT u.* FROM contacts c JOIN users u ON u.user_id = c.contact_id WHERE c.user_id = %s", (uid,))
        p = cur.fetchall()
    finally:
        cur.close()
        conn.close()
    if not p:
        bot.send_message(cid, "لیست خالی است.")
        return
    for x in p:
        kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("👤 مشاهده", callback_data=f"view:{x['user_id']}"))
        bot.send_message(cid, f"👥 {x['nickname']}", reply_markup=kb)


def add_contact(uid, tid, cid):
    if uid == tid:
        return
    try:
        if is_blocked_between(uid, tid):
            bot.send_message(cid, "❌ این کاربر در دسترس نیست.")
            return
    except Exception:
        logger.exception("Block check failed in add_contact")
    conn = db()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO contacts (user_id, contact_id) VALUES (%s,%s) ON CONFLICT DO NOTHING", (uid, tid))
        conn.commit()
        bot.send_message(cid, "✅ اضافه شد.")
    finally:
        cur.close()
        conn.close()


def block_user(uid, tid, cid):
    if uid == tid:
        return
    conn = db()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO blocks (user_id, blocked_id) VALUES (%s,%s) ON CONFLICT DO NOTHING", (uid, tid))
        cur.execute("UPDATE chats SET active=FALSE WHERE (user1=%s AND user2=%s) OR (user1=%s AND user2=%s)", (min(uid, tid), max(uid, tid), min(uid, tid), max(uid, tid)))
        cur.execute("DELETE FROM contacts WHERE user_id=%s AND contact_id=%s", (uid, tid))
        conn.commit()
        bot.send_message(cid, "🚫 کاربر بلاک شد. چت فعال (اگر بود) بسته شد.")
    except Exception:
        conn.rollback()
        logger.exception("Block failed")
        bot.send_message(cid, "❌ بلاک انجام نشد.")
    finally:
        cur.close()
        conn.close()


def start_chat(uid, tid, cid):
    a, b = sorted([uid, tid])
    conn = db()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO chats (user1, user2, active) VALUES (%s,%s,TRUE) ON CONFLICT (user1,user2) DO UPDATE SET active=TRUE", (a, b))
        conn.commit()
    finally:
        cur.close()
        conn.close()
    bot.send_message(uid, "💬 چت شروع شد. /stop")
    try:
        bot.send_message(tid, "💬 چت شروع شد. /stop")
    except Exception:
        pass


def stop_chat(uid, cid):
    conn = db()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE chats SET active=FALSE WHERE (user1=%s OR user2=%s) AND active=TRUE", (uid, uid))
        conn.commit()
        bot.send_message(cid, "چت بسته شد.")
    finally:
        cur.close()
        conn.close()


def relay(msg):
    uid = msg.from_user.id
    conn = db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT user1,user2 FROM chats WHERE active=TRUE AND (user1=%s OR user2=%s) LIMIT 1", (uid, uid))
        s = cur.fetchone()
    finally:
        cur.close()
        conn.close()
    if not s:
        return False
    o = s["user2"] if s["user1"] == uid else s["user1"]
    try:
        bot.copy_message(o, msg.chat.id, msg.message_id)
    except Exception:
        bot.send_message(msg.chat.id, "ارسال نشد.")
    return True


def process_req(uid, tid, cid, rtype):
    cost = DIRECT_COST if rtype == "direct" else CHAT_COST
    if uid == tid:
        return
    target = get_user(tid)
    if not target:
        bot.send_message(cid, "❌ کاربر پیدا نشد.")
        return
    try:
        if is_blocked_between(uid, tid):
            bot.send_message(cid, "❌ این کاربر در دسترس نیست.")
            return
    except Exception:
        logger.exception("Block check failed in process_req")
    if is_silent(target):
        bot.send_message(cid, "❌ کاربر سایلنت است.")
        return
    if rtype == "direct" and target.get("direct_messages_allowed") is False:
        bot.send_message(cid, "❌ این کاربر دایرکت دریافت نمی‌کند.")
        return
    if rtype == "chat" and target.get("chat_requests_allowed") is False:
        bot.send_message(cid, "❌ این کاربر درخواست چت دریافت نمی‌کند.")
        return
    me = get_user(uid)
    if not me or me.get("stars") is None or me["stars"] < cost:
        bot.send_message(cid, f"❌ نیاز به {cost} سکه.")
        return
    states[uid] = {"step": f"{rtype}_msg", "tid": tid, "cost": cost}
    bot.send_message(cid, f"هزینه {cost} سکه هنگام ارسال کسر می‌شود. متن پیام را بفرستید:")


def send_req(uid, tid, cid, text, rtype):
    cost = DIRECT_COST if rtype == "direct" else CHAT_COST
    try:
        result = create_direct_request_with_payment(uid, tid, text, cost)
    except Exception:
        logger.exception("Creating direct request failed")
        bot.send_message(cid, "❌ ارسال درخواست انجام نشد. سکه‌ای کسر نشد.")
        return
    if not result.get("ok"):
        reason = result.get("reason")
        if reason == "hourly_limit":
            bot.send_message(cid, "❌ در یک ساعت اخیر بیش از حد درخواست فرستادید. بعداً تلاش کنید.")
        elif reason == "insufficient_stars":
            bot.send_message(cid, f"❌ نیاز به {cost} سکه.")
        else:
            bot.send_message(cid, "❌ ارسال درخواست انجام نشد. سکه‌ای کسر نشد.")
        return
    request_id = result["request_id"]
    kind = "دایرکت" if rtype == "direct" else "چت"
    sender = get_user(uid)
    kb = types.InlineKeyboardMarkup().row(
        types.InlineKeyboardButton("✅", callback_data=f"appr:{request_id}"),
        types.InlineKeyboardButton("❌", callback_data=f"rej:{request_id}"),
    )
    bot.send_message(tid, f"📩 درخواست {kind} از {account_label(sender)}:\n{text}", reply_markup=kb)
    bot.send_message(cid, "ارسال شد.")


def delete_account(uid, cid):
    conn = db()
    cur = conn.cursor()
    try:
        for tbl, cl1, cl2 in [
            ("likes", "user_id", "target_id"),
            ("passes", "user_id", "target_id"),
            ("blocks", "user_id", "blocked_id"),
            ("chats", "user1", "user2"),
            ("contacts", "user_id", "contact_id"),
            ("direct_requests", "sender_id", "receiver_id"),
            ("reports", "reporter_id", "target_id"),
        ]:
            cur.execute(f"DELETE FROM {tbl} WHERE {cl1}=%s OR {cl2}=%s", (uid, uid))
        cur.execute("DELETE FROM users WHERE user_id=%s", (uid,))
        conn.commit()
        bot.send_message(cid, "حساب حذف شد.", reply_markup=types.ReplyKeyboardRemove())
    except Exception:
        conn.rollback()
        logger.exception("Delete account failed")
        bot.send_message(cid, "❌ حذف حساب انجام نشد.")
    finally:
        cur.close()
        conn.close()


@bot.message_handler(commands=["start"])
def c_start(m):
    uid = m.from_user.id
    if is_reg(uid):
        bot.send_message(m.chat.id, "خوش برگشتی ❤️", reply_markup=main_menu_kb())
        return
    referred_by = None
    parts = (m.text or "").split()
    if len(parts) > 1 and parts[1].startswith("ref_"):
        try:
            ref_uid = int(parts[1][4:])
            if ref_uid != uid:
                referred_by = ref_uid
        except ValueError:
            referred_by = None
    states[uid] = {"step": "nickname", "referred_by": referred_by}
    bot.send_message(m.chat.id, "اسمت چیه؟")


@bot.message_handler(commands=["admin"])
def c_admin(m):
    uid = m.from_user.id
    if not is_admin(uid):
        bot.send_message(m.chat.id, "⛔ دسترسی ندارید.")
        return
    conn = db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) AS n FROM users")
        users_n = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) AS n FROM direct_requests WHERE status='pending'")
        pending_n = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) AS n FROM reports")
        reports_n = cur.fetchone()["n"]
    finally:
        cur.close()
        conn.close()
    bot.send_message(
        m.chat.id,
        f"📊 آمار ربات\n\n👥 کاربران: {users_n}\n📩 درخواست‌های در انتظار: {pending_n}\n⚠️ گزارش‌ها: {reports_n}",
    )


@bot.message_handler(commands=["stop"])
def c_stop(m):
    stop_chat(m.from_user.id, m.chat.id)


@bot.message_handler(content_types=["location"])
def c_loc(m):
    uid = m.from_user.id
    if not is_reg(uid):
        return
    conn = db()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE users SET lat=%s, lon=%s WHERE user_id=%s", (m.location.latitude, m.location.longitude, uid))
        conn.commit()
    finally:
        cur.close()
        conn.close()
    bot.send_message(m.chat.id, "📍 ثبت شد.", reply_markup=main_menu_kb())
    find(m.chat.id, uid)


@bot.message_handler(content_types=["photo"])
def c_photo(m):
    uid = m.from_user.id
    if relay(m):
        return
    s = states.get(uid)
    if s and s.get("step") == "photo":
        conn = db()
        cur = conn.cursor()
        try:
            cur.execute("SELECT photos FROM users WHERE user_id=%s", (uid,))
            row = cur.fetchone()
            current = row["photos"].split(",") if row and row["photos"] else []
            current = [p for p in current if p]
            if len(current) >= 3:
                states.pop(uid, None)
                bot.send_message(m.chat.id, "❌ حداکثر ۳ عکس.")
                return
            current.append(m.photo[-1].file_id)
            cur.execute("UPDATE users SET photos=%s WHERE user_id=%s", (",".join(current), uid))
            conn.commit()
        finally:
            cur.close()
            conn.close()
        states.pop(uid, None)
        bot.send_message(m.chat.id, "✅ عکس ذخیره شد.", reply_markup=main_menu_kb())


@bot.message_handler(content_types=["video", "voice", "audio", "sticker", "document", "animation", "video_note"])
def c_media(m):
    relay(m)


@bot.message_handler(content_types=["text"])
def c_text(m):
    uid = m.from_user.id
    t = (m.text or "").strip()
    s = states.get(uid)
    if not is_reg(uid) and not s:
        bot.send_message(m.chat.id, "برای شروع /start را بزنید.")
        return
    if s:
        st = s["step"]
        if st == "nickname":
            s["nickname"] = t[:50]
            s["step"] = "age"
            bot.send_message(m.chat.id, "⚠️ سن و جنسیت بعد از ثبت‌نام قابل تغییر نیست!\nسن:", reply_markup=age_kb("reg_age"))
            return
        if st == "gender":
            if t not in ["پسر", "دختر"]:
                return
            s["gender"] = t
            s["step"] = "province"
            bot.send_message(m.chat.id, "استان؟", reply_markup=types.ReplyKeyboardRemove())
            return
        if st == "province":
            s["province"] = t[:50]
            s["step"] = "city"
            bot.send_message(m.chat.id, "شهر؟")
            return
        if st == "city":
            s["city"] = t[:50]
            s["step"] = "bio"
            bot.send_message(m.chat.id, "بیو:")
            return
        if st == 
