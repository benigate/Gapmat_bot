import os
import time
import logging
import threading
import telebot
from telebot import types
from flask import Flask
from db import db, init_db, get_user, is_reg, dist

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")

if not BOT_TOKEN: raise RuntimeError("BOT_TOKEN missing")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
states = {}

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
    conn = db(); cur = conn.cursor()
    try:
        cur.execute("INSERT INTO users (user_id, nickname, age, gender, province, city, bio, stars) VALUES (%s,%s,%s,%s,%s,%s,%s,6) ON CONFLICT (user_id) DO UPDATE SET nickname=EXCLUDED.nickname, age=EXCLUDED.age, gender=EXCLUDED.gender, province=EXCLUDED.province, city=EXCLUDED.city, bio=EXCLUDED.bio", (uid, d["nickname"], d["age"], d["gender"], d["province"], d["city"], d["bio"]))
        conn.commit()
    finally: cur.close(); conn.close()
    bot.send_message(cid, "🎉 ثبت‌نام کامل شد! ۶ سکه هدیه گرفتی.", reply_markup=main_menu_kb())

def show_profile(cid, uid, target_id=None):
    tid = target_id or uid
    u = get_user(tid)
    if not u: return
    vip = " 👑" if u.get("is_vip") else ""
    text = f"👤 {u['nickname']}{vip}\n🎂 {u['age']} ساله\n⚧ {u['gender']}\n📍 {u['province']}، {u['city']}\n\n📝 {u['bio'] or 'بدون بیو'}\n⭐ {u['stars']}"
    photos = u.get("photos", "").split(",") if u.get("photos") else []
    photos = [p for p in photos if p]
    kb = profile_kb(tid) if target_id else my_profile_kb()
    if photos:
        if len(photos) == 1: bot.send_photo(cid, photos[0], caption=text, reply_markup=kb)
        else:
            bot.send_media_group(cid, [types.InputMediaPhoto(p) for p in photos])
            bot.send_message(cid, text, reply_markup=kb)
    else: bot.send_message(cid, text, reply_markup=kb)

def find(cid, uid):
    u = get_user(uid)
    if not u: return
    if u["lat"] is None:
        bot.send_message(cid, "اول موقعیت بفرست.", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add(types.KeyboardButton("📍 ارسال موقعیت", request_location=True))); return
    conn = db(); cur = conn.cursor()
    try:
        q = "SELECT * FROM users WHERE user_id!=%s AND nickname IS NOT NULL AND profile_visible=TRUE AND lat IS NOT NULL AND user_id NOT IN (SELECT target_id FROM passes WHERE user_id=%s) AND user_id NOT IN (SELECT target_id FROM likes WHERE user_id=%s) AND user_id NOT IN (SELECT blocked_id FROM blocks WHERE user_id=%s)"
        p = [uid, uid, uid, uid]
        if u.get("req_gender") and u["req_gender"] != "any": q += " AND gender=%s"; p.append(u["req_gender"])
        if u.get("req_province") and u.get("province"): q += " AND province=%s"; p.append(u["province"])
        if u.get("req_city") and u.get("city"): q += " AND city=%s"; p.append(u["city"])
        if u.get("req_min_age"): q += " AND age>=%s"; p.append(u["req_min_age"])
        if u.get("req_max_age"): q += " AND age<=%s"; p.append(u["req_max_age"])
        cur.execute(q, tuple(p)); c = cur.fetchall()
    finally: cur.close(); conn.close()
    if not c: bot.send_message(cid, "کسی پیدا نشد."); return
    c.sort(key=lambda x: dist(u["lat"], u["lon"], x["lat"], x["lon"]))
    show_profile(cid, uid, target_id=c[0]["user_id"])

def like(uid, tid, cid):
    conn = db(); cur = conn.cursor()
    try:
        cur.execute("INSERT INTO likes (user_id, target_id) VALUES (%s,%s) ON CONFLICT DO NOTHING", (uid, tid)); conn.commit()
        try: bot.send_message(tid, f"❤️ یک نفر پروفایل شما را پسندید!\nآیدی: `{uid}`", parse_mode="Markdown")
        except: pass
    except: conn.rollback()
    finally: cur.close(); conn.close()
    bot.send_message(cid, "❤️ لایک ثبت شد."); find(cid, uid)

def pass_user(uid, tid, cid):
    conn = db(); cur = conn.cursor()
    try: cur.execute("INSERT INTO passes (user_id, target_id) VALUES (%s,%s) ON CONFLICT DO NOTHING", (uid, tid)); conn.commit()
    finally: cur.close(); conn.close()
    find(cid, uid)

def show_contacts(cid, uid):
    conn = db(); cur = conn.cursor()
    try:
        cur.execute("SELECT u.* FROM contacts c JOIN users u ON u.user_id = c.contact_id WHERE c.user_id = %s", (uid,))
        p = cur.fetchall()
    finally: cur.close(); conn.close()
    if not p: bot.send_message(cid, "لیست خالی است."); return
    for x in p:
        kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("👤 مشاهده", callback_data=f"view:{x['user_id']}"))
        bot.send_message(cid, f"👥 {x['nickname']}", reply_markup=kb)

def add_contact(uid, tid, cid):
    conn = db(); cur = conn.cursor()
    try: cur.execute("INSERT INTO contacts (user_id, contact_id) VALUES (%s,%s) ON CONFLICT DO NOTHING", (uid, tid)); conn.commit(); bot.send_message(cid, "✅ اضافه شد.")
    finally: cur.close(); conn.close()

def start_chat(uid, tid, cid):
    a, b = sorted([uid, tid])
    conn = db(); cur = conn.cursor()
    try: cur.execute("INSERT INTO chats (user1, user2, active) VALUES (%s,%s,TRUE) ON CONFLICT (user1,user2) DO UPDATE SET active=TRUE", (a, b)); conn.commit()
    finally: cur.close(); conn.close()
    bot.send_message(uid, "💬 چت شروع شد. /stop")
    try: bot.send_message(tid, "💬 چت شروع شد. /stop")
    except: pass

def stop_chat(uid, cid):
    conn = db(); cur = conn.cursor()
    try: cur.execute("UPDATE chats SET active=FALSE WHERE (user1=%s OR user2=%s) AND active=TRUE", (uid, uid)); conn.commit(); bot.send_message(cid, "چت بسته شد.")
    finally: cur.close(); conn.close()

def relay(msg):
    uid = msg.from_user.id
    conn = db(); cur = conn.cursor()
    try:
        cur.execute("SELECT user1,user2 FROM chats WHERE active=TRUE AND (user1=%s OR user2=%s) LIMIT 1", (uid, uid)); s = cur.fetchone()
    finally: cur.close(); conn.close()
    if not s: return False
    o = s["user2"] if s["user1"] == uid else s["user1"]
    try: bot.copy_message(o, msg.chat.id, msg.message_id)
    except: bot.send_message(msg.chat.id, "ارسال نشد.")
    return True

def process_req(uid, tid, cid, rtype):
    cost = 1 if rtype == "direct" else 2
    conn = db(); cur = conn.cursor()
    try:
        cur.execute("SELECT stars FROM users WHERE user_id=%s", (uid,)); r = cur.fetchone()
        if not r or r["stars"] < cost: bot.send_message(cid, f"❌ نیاز به {cost} سکه."); return
        cur.execute("SELECT silent_until FROM users WHERE user_id=%s", (tid,)); t = cur.fetchone()
        if t.get("silent_until") and t["silent_until"].timestamp() > time.time(): bot.send_message(cid, "❌ کاربر سایلنت است."); return
        cur.execute("UPDATE users SET stars = stars - %s WHERE user_id=%s", (cost, uid)); conn.commit()
        states[uid] = {"step": f"{rtype}_msg", "tid": tid}; bot.send_message(cid, f"هزینه {cost} سکه کسر شد. متن:")
    finally: cur.close(); conn.close()

def send_req(uid, tid, cid, text, rtype):
    kb = types.InlineKeyboardMarkup().row(types.InlineKeyboardButton("✅", callback_data=f"appr:{uid}"), types.InlineKeyboardButton("❌", callback_data=f"rej:{uid}"))
    bot.send_message(tid, f"📩 از {uid}:\n{text}", reply_markup=kb); bot.send_message(cid, "ارسال شد.")

@bot.message_handler(commands=["start"])
def c_start(m):
    uid = m.from_user.id
    if is_reg(uid): bot.send_message(m.chat.id, "خوش برگشتی ❤️", reply_markup=main_menu_kb()); return
    states[uid] = {"step": "nickname"}; bot.send_message(m.chat.id, "اسمت چیه؟")

@bot.message_handler(commands=["stop"])
def c_stop(m): stop_chat(m.from_user.id, m.chat.id)

@bot.message_handler(content_types=["location"])
def c_loc(m):
    uid = m.from_user.id
    if not is_reg(uid): return
    conn = db(); cur = conn.cursor()
    cur.execute("UPDATE users SET lat=%s, lon=%s WHERE user_id=%s", (m.location.latitude, m.location.longitude, uid)); conn.commit(); cur.close(); conn.close()
    bot.send_message(m.chat.id, "📍 ثبت شد.", reply_markup=main_menu_kb()); find(m.chat.id, uid)

@bot.message_handler(content_types=["photo"])
def c_photo(m):
    uid = m.from_user.id; s = states.get(uid)
    if s and s.get("step") == "photo":
        conn = db(); cur = conn.cursor()
        cur.execute("SELECT photos FROM users WHERE user_id=%s", (uid,)); row = cur.fetchone()
        current = row["photos"].split(",") if row and row["photos"] else []
        current = [p for p in current if p]
        if len(current) >= 3: states.pop(uid, None); bot.send_message(m.chat.id, "❌ حداکثر ۳ عکس."); return
        current.append(m.photo[-1].file_id)
        cur.execute("UPDATE users SET photos=%s WHERE user_id=%s", (",".join(current), uid)); conn.commit(); cur.close(); conn.close()
        states.pop(uid, None); bot.send_message(m.chat.id, "✅ عکس ذخیره شد.", reply_markup=main_menu_kb())

@bot.message_handler(content_types=["text"])
def c_text(m):
    uid = m.from_user.id; t = (m.text or "").strip(); s = states.get(uid)
    if not is_reg(uid) and not s: bot.send_message(m.chat.id, "برای شروع /start را بزنید."); return
    if s:
        st = s["step"]
        if st == "nickname": s["nickname"] = t[:50]; s["step"] = "age"; bot.send_message(m.chat.id, "⚠️ سن و جنسیت بعد از ثبت‌نام قابل تغییر نیست!\nسن:", reply_markup=age_kb("reg_age")); return
        if st == "gender":
            if t not in ["پسر", "دختر"]: return
            s["gender"] = t; s["step"] = "province"; bot.send_message(m.chat.id, "استان؟", reply_markup=types.ReplyKeyboardRemove()); return
        if st == "province": s["province"] = t[:50]; s["step"] = "city"; bot.send_message(m.chat.id, "شهر؟"); return
        if st == "city": s["city"] = t[:50]; s["step"] = "bio"; bot.send_message(m.chat.id, "بیو:"); return
        if st == "bio": s["bio"] = t[:300]; finish_reg(uid, m.chat.id); return
        if st in ["direct_msg", "req_msg"]: tid = s.get("tid"); rtype = "direct" if st == "direct_msg" else "chat"; states.pop(uid, None); send_req(uid, tid, m.chat.id, t, rtype); return
        if st == "edit_province": conn = db(); cur = conn.cursor(); cur.execute("UPDATE users SET province=%s WHERE user_id=%s", (t[:50], uid)); conn.commit(); cur.close(); conn.close(); states.pop(uid, None); bot.send_message(m.chat.id, "✅ استان تغییر کرد."); return
        if st == "edit_city": conn = db(); cur = conn.cursor(); cur.execute("UPDATE users SET city=%s WHERE user_id=%s", (t[:50], uid)); conn.commit(); cur.close(); conn.close(); states.pop(uid, None); bot.send_message(m.chat.id, "✅ شهر تغییر کرد."); return
    if relay(m): return
    if t == "🔍 جستجوی افراد": find(m.chat.id, uid)
    elif t == "👥 مخاطبین من": show_contacts(m.chat.id, uid)
    elif t == "👤 پروفایل من": show_profile(m.chat.id, uid)
    elif t == "🪙 کیف پول": u = get_user(uid); bot.send_message(m.chat.id, "💰 شما " + str(u['stars']) + " سکه دارید.", reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🛒 خرید سکه (به زودی)", callback_data="noop")))
    elif t == "🔗 دعوت دوستان":
        try:
            bot.send_message(
                m.chat.id,
                f"https://t.me/{bot.get_me().username}?start=ref_{uid}"
            )
        except Exception:
            pass
        logging.exception("Callback error")
    else: bot.send_message(m.chat.id, "متوجه نشدم! از منو استفاده کن.", reply_markup=main_menu_kb())

@bot.callback_query_handler(func=lambda c: True)
def c_cb(c):
    d = c.data or ""; uid = c.from_user.id; cid = c.message.chat.id if c.message else uid; mid = c.message.message_id if c.message else None
    try:
        if d.startswith("reg_age:"): age = int(d.split(":")[1]); states[uid]["age"] = age; states[uid]["step"] = "gender"; bot.edit_message_text(f"سن: {age}. جنسیت:", chat_id=cid, message_id=mid, reply_markup=types.InlineKeyboardMarkup().row(types.InlineKeyboardButton("پسر", callback_data="reg_gen:پسر"), types.InlineKeyboardButton("دختر", callback_data="reg_gen:دختر")))
        elif d.startswith("reg_gen:"): states[uid]["gender"] = d.split(":")[1]; states[uid]["step"] = "province"; bot.edit_message_text("استان:", chat_id=cid, message_id=mid)
        elif d.startswith("like:"): like(uid, int(d.split(":")[1]), cid)
        elif d.startswith("pass:"): pass_user(uid, int(d.split(":")[1]), cid)
        elif d.startswith("add:"): add_contact(uid, int(d.split(":")[1]), cid)
        elif d.startswith("view:"): show_profile(cid, uid, target_id=int(d.split(":")[1]))
        elif d.startswith("dir:"): process_req(uid, int(d.split(":")[1]), cid, "direct")
        elif d.startswith("req:"): process_req(uid, int(d.split(":")[1]), cid, "chat")
                elif d.startswith("appr:") or d.startswith("rej:"):
            conn = None
            cur = None

            try:
                request_id = int(d.split(":")[1])

                conn = db()
                cur = conn.cursor()

                cur.execute("""
                    SELECT *
                    FROM direct_requests
                    WHERE id = %s
                    FOR UPDATE
                """, (request_id,))

                req = cur.fetchone()

                if not req:
                    bot.answer_callback_query(
                        c.id, "درخواست پیدا نشد.", show_alert=True
                    )

                elif req["receiver_id"] != uid:
                    bot.answer_callback_query(
                        c.id, "این درخواست برای شما نیست.", show_alert=True
                    )

                elif req["status"] != "pending":
                    bot.answer_callback_query(
                        c.id, "این درخواست قبلاً بررسی شده.", show_alert=True
                    )

                else:
                    cur.execute("""
                        UPDATE direct_requests
                        SET status = 'expired'
                        WHERE id = %s
                          AND status = 'pending'
                          AND expires_at <= CURRENT_TIMESTAMP
                    """, (request_id,))

                    if cur.rowcount:
                        conn.commit()
                        bot.answer_callback_query(
                            c.id, "⏰ مهلت درخواست تمام شده.",
                            show_alert=True
                        )

                    elif d.startswith("appr:"):
                        cur.execute("""
                            UPDATE direct_requests
                            SET status = 'accepted'
                            WHERE id = %s
                              AND status = 'pending'
                              AND expires_at > CURRENT_TIMESTAMP
                        """, (request_id,))

                        if cur.rowcount:
                            sender = req["sender_id"]

                            cur.execute("""
                                INSERT INTO chats (user1, user2, active)
                                VALUES (%s, %s, TRUE)
                                ON CONFLICT (user1, user2)
                                DO UPDATE SET active = TRUE
                            """, (min(sender, uid), max(sender, uid)))

                            conn.commit()

                            bot.send_message(
                                sender, "✅ درخواست چت پذیرفته شد."
                            )
                            bot.send_message(
                                uid, "✅ درخواست را پذیرفتید."
                            )
                            bot.answer_callback_query(c.id, "پذیرفته شد.")

                        else:
                            conn.commit()
                            bot.answer_callback_query(
                                c.id, "درخواست منقضی شده.",
                                show_alert=True
                            )

                    else:
                        cur.execute("""
                            UPDATE direct_requests
                            SET status = 'rejected'
                            WHERE id = %s
                              AND status = 'pending'
                              AND expires_at > CURRENT_TIMESTAMP
                        """, (request_id,))

                        if cur.rowcount:
                            conn.commit()
                            bot.send_message(
                                req["sender_id"],
                                "❌ درخواست چت رد شد."
                            )
                            bot.answer_callback_query(c.id, "رد شد.")
                        else:
                            conn.commit()
                            bot.answer_callback_query(
                                c.id, "درخواست منقضی شده.",
                                show_alert=True
                            )

            except Exception:
                if conn:
                    conn.rollback()

                logging.exception("Request processing error")

                bot.answer_callback_query(
                    c.id,
                    "خطا در پردازش درخواست.",
                    show_alert=True
                )

            finally:
                if cur:
                    cur.close()
                if conn:
                    conn.close()
        elif d == "edit:menu":
            kb = types.InlineKeyboardMarkup()
            kb.row(
                types.InlineKeyboardButton("تغییر سن (۱۰۰ سکه)", callback_data="edit:age"),
                types.InlineKeyboardButton("تغییر جنسیت (۱۰۰ سکه)", callback_data="edit:gender")
            )
            kb.row(
                types.InlineKeyboardButton("تغییر استان", callback_data="edit:prov"),
                types.InlineKeyboardButton("تغییر شهر", callback_data="edit:city")
            )
            kb.add(types.InlineKeyboardButton("📸 افزودن عکس (رایگان)", callback_data="photo:ask"))
            kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="menu:profile"))

            bot.answer_callback_query(c.id)
            bot.send_message(cid, "✏️ ویرایش پروفایل:", reply_markup=kb)
    bot.answer_callback_query(c.id)
    bot.send_message(cid, "✏️ ویرایش پروفایل:", reply_markup=kb)
        elif d == "settings:main": bot.send_message(cid, "⚙️ تنظیمات:", reply_markup=settings_main_kb())
        elif d == "set:privacy":
            u = get_user(uid); pv = "✅" if u["profile_visible"] else "❌"; als = "✅" if u.get("alarm_seen") else "❌"; sil = "✅" if u.get("silent_until") and u["silent_until"].timestamp() > time.time() else "❌"
            kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton(f"{pv} نمایش پروفایل", callback_data="pv:profile")).add(types.InlineKeyboardButton(f"{als} آلارم بازدید", callback_data="pv:alarm")).add(types.InlineKeyboardButton("📩 فیلتر درخواست‌ها", callback_data="set:filter")).add(types.InlineKeyboardButton(f"{sil} حالت سایلنت", callback_data="set:silent")).add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="settings:main"))
            bot.edit_message_text("👤 حریم خصوصی:", chat_id=cid, message_id=mid, reply_markup=kb)
        elif d == "set:filter":
            u = get_user(uid); g = "همه" if u['req_gender']=="any" else u['req_gender']; p = "✅" if u['req_province'] else "❌"; c = "✅" if u['req_city'] else "❌"
            kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton(f"جنسیت: {g}", callback_data="filt:gender")).row(types.InlineKeyboardButton(f"{p} هم‌استانی", callback_data="filt:prov"), types.InlineKeyboardButton(f"{c} هم‌شهری", callback_data="filt:city")).row(types.InlineKeyboardButton(f"حداقل سن: {u['req_min_age']}", callback_data="filt:minage"), types.InlineKeyboardButton(f"حداکثر سن: {u['req_max_age']}", callback_data="filt:maxage")).add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="set:privacy"))
            bot.edit_message_text("📩 فیلترها:", chat_id=cid, message_id=mid, reply_markup=kb)
        elif d == "set:silent":
            kb = types.InlineKeyboardMarkup().row(types.InlineKeyboardButton("۱ ساعت", callback_data="sil:1h"), types.InlineKeyboardButton("۲۴ ساعت", callback_data="sil:24h")).row(types.InlineKeyboardButton("دائم", callback_data="sil:forever"), types.InlineKeyboardButton("❌ غیرفعال", callback_data="sil:off")).add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="set:privacy"))
            bot.edit_message_text("🔕 سایلنت:", chat_id=cid, message_id=mid, reply_markup=kb)
        elif d == "set:loc": bot.send_message(cid, "📍 موقعیت جدید:", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add(types.KeyboardButton("📍 ارسال موقعیت", request_location=True)))
        elif d == "set:del":
            kb = types.InlineKeyboardMarkup().row(types.InlineKeyboardButton("💳 ۲۰۰,۰۰۰ تومان", callback_data="del:toman"), types.InlineKeyboardButton("⭐ ۲۵ ستاره", callback_data="del:star")).add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="settings:main"))
            bot.edit_message_text("🗑 حذف حساب:\n(درگاه تومان به زودی)", chat_id=cid, message_id=mid, reply_markup=kb)
        elif d == "del:star":
            u = get_user(uid)
            if u["stars"] >= 25:
                conn = db(); cur = conn.cursor(); cur.execute("UPDATE users SET stars = stars - 25 WHERE user_id=%s", (uid,)); conn.commit()
                for tbl, cl1, cl2 in [("likes","user_id","target_id"),("passes","user_id","target_id"),("blocks","user_id","blocked_id"),("chats","user1","user2"),("contacts","user_id","contact_id"),("direct_requests","sender_id","receiver_id")]: cur.execute(f"DELETE FROM {tbl} WHERE {cl1}=%s OR {cl2}=%s", (uid, uid))
                cur.execute("DELETE FROM users WHERE user_id=%s", (uid,)); conn.commit(); cur.close(); conn.close()
                bot.send_message(cid, "حساب حذف شد.", reply_markup=types.ReplyKeyboardRemove())
            else: bot.answer_callback_query(c.id, "❌ ۲۵ ستاره ندارید.", show_alert=True)
        elif d == "del:toman": bot.answer_callback_query(c.id, "به زودی.", show_alert=True)
        elif d == "pv:profile": conn = db(); cur = conn.cursor(); cur.execute("UPDATE users SET profile_visible = NOT profile_visible WHERE user_id=%s", (uid,)); conn.commit(); cur.close(); conn.close(); bot.answer_callback_query(c.id, "تغییر کرد.")
        elif d == "pv:alarm": conn = db(); cur = conn.cursor(); cur.execute("UPDATE users SET alarm_seen = NOT alarm_seen WHERE user_id=%s", (uid,)); conn.commit(); cur.close(); conn.close(); bot.answer_callback_query(c.id, "تغییر کرد.")
        elif d == "filt:gender":
            u = get_user(uid); curr = u["req_gender"]; new_g = "دختر" if curr=="any" else ("پسر" if curr=="دختر" else "any")
            conn = db(); cur = conn.cursor(); cur.execute("UPDATE users SET req_gender=%s WHERE user_id=%s", (new_g, uid)); conn.commit(); cur.close(); conn.close(); bot.answer_callback_query(c.id, "تغییر کرد.")
        elif d == "filt:prov": conn = db(); cur = conn.cursor(); cur.execute("UPDATE users SET req_province = NOT req_province WHERE user_id=%s", (uid,)); conn.commit(); cur.close(); conn.close(); bot.answer_callback_query(c.id, "تغییر کرد.")
        elif d == "filt:city": conn = db(); cur = conn.cursor(); cur.execute("UPDATE users SET req_city = NOT req_city WHERE user_id=%s", (uid,)); conn.commit(); cur.close(); conn.close(); bot.answer_callback_query(c.id, "تغییر کرد.")
        elif d == "filt:minage": states[uid] = {"step": "filt_min_age"}; bot.send_message(cid, "حداقل سن:")
        elif d == "filt:maxage": states[uid] = {"step": "filt_max_age"}; bot.send_message(cid, "حداکثر سن:")
        elif d.startswith("sil:"):
            val = d.split(":")[1]; conn = db(); cur = conn.cursor()
            if val == "1h": cur.execute("UPDATE users SET silent_until = CURRENT_TIMESTAMP + interval '1 hour' WHERE user_id=%s", (uid,))
            elif val == "24h": cur.execute("UPDATE users SET silent_until = CURRENT_TIMESTAMP + interval '1 day' WHERE user_id=%s", (uid,))
            elif val == "forever": cur.execute("UPDATE users SET silent_until = '2099-01-01' WHERE user_id=%s", (uid,))
            elif val == "off": cur.execute("UPDATE users SET silent_until = NULL WHERE user_id=%s", (uid,))
            conn.commit(); cur.close(); conn.close(); bot.answer_callback_query(c.id, "اعمال شد.")
        elif d == "edit:age":
            u = get_user(uid)
            if u["stars"] >= 100:
                conn = db(); cur = conn.cursor(); cur.execute("UPDATE users SET stars = stars - 100 WHERE user_id=%s", (uid,)); conn.commit(); cur.close(); conn.close()
                states[uid] = {"step": "edit_age"}; bot.send_message(cid, "✅ ۱۰۰ سکه کسر شد. سن جدید:", reply_markup=age_kb("edit_age_do"))
            else: bot.answer_callback_query(c.id, "❌ ۱۰۰ سکه ندارید.", show_alert=True)
        elif d == "edit:gender":
            u = get_user(uid)
            if u["stars"] >= 100:
                conn = db(); cur = conn.cursor(); cur.execute("UPDATE users SET stars = stars - 100 WHERE user_id=%s", (uid,)); conn.commit(); cur.close(); conn.close()
                kb = types.InlineKeyboardMarkup().row(types.InlineKeyboardButton("پسر", callback_data="edit_gen_do:پسر"), types.InlineKeyboardButton("دختر", callback_data="edit_gen_do:دختر"))
                bot.send_message(cid, "✅ ۱۰۰ سکه کسر شد. جنسیت:", reply_markup=kb)
            else: bot.answer_callback_query(c.id, "❌ ۱۰۰ سکه ندارید.", show_alert=True)
        elif d.startswith("edit_age_do:"):
            val = int(d.split(":")[1]); conn = db(); cur = conn.cursor(); cur.execute("UPDATE users SET age=%s WHERE user_id=%s", (val, uid)); conn.commit(); cur.close(); conn.close(); states.pop(uid, None); bot.edit_message_text(f"✅ سن به {val} تغییر کرد.", chat_id=cid, message_id=mid)
        elif d.startswith("edit_gen_do:"):
            val = d.split(":")[1]; conn = db(); cur = conn.cursor(); cur.execute("UPDATE users SET gender=%s WHERE user_id=%s", (val, uid)); conn.commit(); cur.close(); conn.close(); bot.edit_message_text(f"✅ جنسیت به {val} تغییر کرد.", chat_id=cid, message_id=mid)
        elif d == "edit:prov": states[uid] = {"step": "edit_province"}; bot.send_message(cid, "استان جدید:")
        elif d == "edit:city": states[uid] = {"step": "edit_city"}; bot.send_message(cid, "شهر جدید:")
        elif d == "photo:ask": states[uid] = {"step": "photo"}; bot.send_message(cid, "📸 عکس بفرست (تا ۳ عکس):")
        bot.answer_callback_query(c.id)
    except: pass

@app.route("/")
def health():
    return "OK", 200
def run():
    init_db()

    try:
        bot.delete_webhook(drop_pending_updates=True)
    except Exception as e:
        print(f"Webhook error: {e}", flush=True)

    while True:
        try:
            bot.infinity_polling(
                timeout=30,
                long_polling_timeout=25
            )
        except Exception as e:
            print(f"Polling error: {e}", flush=True)
            time.sleep(5)


if __name__ == "__main__":
    threading.Thread(target=run, daemon=True).start()
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", 10000))
    )
