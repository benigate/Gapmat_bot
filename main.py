nگزارش‌دهنده: {uid}\nکاربر: {target}\nدلیل: {text}")
                به جز استثنا: logger.exception("اعلان مدیر ناموفق بود")
            بازگشت
    # رله پیام در صورت فعال بودن چت
    اگر relay_message(message):
        بازگشت
    if text == "👤 پروفایل من": show_profile(message); بازگشت
    if text == "🔎 افراد نزدیک": nearby(message); بازگشت
    if text == "📍 ارسال پست": ask_location(message); بازگشت
    if text == "🔒 حریم خصوصی":
        bot.send_message(message.chat.id, "تنظیمات حریم خصوصی:", reply_markup=privacy_keyboard()); بازگشت
    if text == "🚫 بلاك کاربر":
        registration[uid]={"step":"block_user","profile":{}}
        bot.send_message(message.chat.id, "شناسه شمارهی تلگرام کاربر رو بفرست:"); بازگشت
    if text == "⚠️ گزارش کاربر":
        registration[uid]={"step":"report_user","profile":{}}
        bot.send_message(message.chat.id, "شناسه کاربر مورد نظر رو بفرست:"); بازگشت
    if text == "🗑 حذف حساب":
        k=types.InlineKeyboardMarkup()
        k.row(types.InlineKeyboardButton("بله، حذف شود",callback_data="confirm_delete"),
              types.InlineKeyboardButton("انصراف",callback_data="cancel_delete"))
        bot.send_message(message.chat.id, "⚠️ حذف حساب قابل بازگشت نیست.", reply_markup=k); بازگشت
    if text == "💚 مچ‌های من": show_matches(message); بازگشت
    if text == "⭐ ستاره‌های من":
        u=get_user(uid); bot.send_message(message.chat.id, f"⭐ موجودی ستاره‌ها: {u.get('stars',0) if you other 0}", reply_markup=main_keyboard()); بازگشت
    if text == "🎁 دعوت دوستان": send_referral_link(message); بازگشت
    if text == "🛍 خرید ستاره": send_star_invoice(message); بازگشت
    اگر متن == "/stopchat" باشد: stop_chat(message); برمی‌گرداند
    log_activity(uid, "other_text")

@bot.message_handler(content_types=["location"])
def receive_location(message):
    uid=message.from_user.id; loc=message.location
    امتحان کنید:
        اگر شناسه کاربری در حال ثبت نام باشد و registration[uid]["step"]=="waiting_location":
            p=registration[uid]["profile"]
            p.update(latitude=loc.latitude, longitude=loc.longitude, location_visible=True)
            پایان_ثبت_پیام؛ بازگشت
        با get_db() به عنوان conn:
            با conn.cursor() به عنوان تابع cur:
                cur.execute("به‌روزرسانی تنظیمات عرض جغرافیایی کاربران = %s، طول جغرافیایی = %s، مکان_قابل_مشاهده = درست، در جایی که telegram_id = %s است"،(loc.latitude، loc.longitude، uid))
        bot.send_message(message.chat.id, "✅ موقعیتت ذخیره شد.", reply_markup=main_keyboard())
    به جز استثنا:
        logger.exception("ذخیره موقعیت مکانی ناموفق بود")
        bot.send_message(message.chat.id, "خطا در مکان ذخیره.")

@bot.callback_query_handler(func=lambda c: c.data in ["hide_profile","show_profile","hide_location","show_location"])
def privacy_callback(call):
    uid=call.from_user.id
    mapping={"hide_profile":("profile_visible",False,"پروفایل مخفی شد."),
             "show_profile":("profile_visible",True,"پروفایل نمایش داده می‌شود."),
             "hide_location":("location_visible",False,"موقعیت مخفی شد."),
             "show_location":("location_visible",True,"موقعیت نمایش داده می‌شود.")}
    col,val,result=mapping[call.data]
    امتحان کنید:
        با get_db() به عنوان conn:
            با conn.cursor() به عنوان تابع cur:
                cur.execute(f"به‌روزرسانی تنظیمات کاربران {col}=%s WHERE telegram_id=%s",(val,uid))
        bot.answer_callback_query(call.id,result)
        bot.send_message(call.message.chat.id,result)
    به جز استثنا:
        logger.exception("به‌روزرسانی حریم خصوصی ناموفق بود")
        bot.answer_callback_query(call.id"خطا در تغییر تغییر.")

@bot.callback_query_handler(func=lambda c: c.data in ["confirm_delete","cancel_delete"])
def delete_callback(call):
    uid=call.from_user.id
    اگر call.data=="cancel_delete":
        bot.answer_callback_query(call.id,"حذف لغو شد.")
        bot.send_message(call.message.chat.id,"حذف حساب لغو شد.",reply_markup=main_keyboard()); بازگشت
    امتحان کنید:
        با get_db() به عنوان conn:
            با conn.cursor() به عنوان تابع cur:
                برای جدول، ستون را در [
                    ("users"، "telegram_id")،("blocks"، "blocker_id")،("blocks"، "blocked_id")
                    ("گزارش‌ها"، "شناسه_گزارشگر")،("گزارش‌ها"، "شناسه_گزارش‌شده")،("گزارش‌ها"، "شناسه_فعالیت"، "شناسه_تلگرام")
                    ("لایک‌ها"، "شناسه لایک‌کننده")،("لایک‌ها"، "شناسه لایک‌شده")،("پذیرفته‌ها"، "شناسه عبورکننده")،("پذیرفته‌ها"، "شناسه عبورکرده")،
                    ("matches"، "user1_id"),("matches"، "user2_id"),("referrals"، "invited_id"),
                    ("referrals"، "referrer_id")،("chat_sessions"، "user_id")،("chat_sessions"، "partner_id")]:
                    cur.execute(f"حذف از {table} WHERE {col}=%s",(uid,))
        registration.pop(uid,None)
        bot.answer_callback_query(call.id,"حساب حذف شد.")
        bot.send_message(call.message.chat.id,"حساب و اطلاعات مرتبط حذف شد.")
    به جز استثنا:
        logger.exception("حذف ناموفق")
        bot.answer_callback_query(call.id"خطا در حذف حساب.")

# =============================
# لایک، رد کردن و مچ
# =============================
@bot.callback_query_handler(func=lambda c: c.data.startswith(("like:","pass:")))
def swipe_callback(call):
    uid=call.from_user.id
    امتحان کنید:
        action,target_s=call.data.split(":",1); target=int(target_s)
        اگر target==uid یا is_blocked(uid,target):
            bot.answer_callback_query(call.id,"این پروفایل در دسترس نیست."); بازگشت
        با get_db() به عنوان conn:
            با conn.cursor() به عنوان تابع cur:
                اگر action=="pass":
                    cur.execute("در صورت تداخل، مقادیر(%s،%s) را در passes(passer_id,passed_id) وارد کنید و هیچ کاری انجام ندهید",(uid,target))
                    bot.answer_callback_query(call.id,"رد شد.")
                    بازگشت
                cur.execute("در لایک‌ها(liker_id,liked_id) مقادیر(%s,%s) را در صورت تداخل وارد کن، کاری انجام نده",(uid,target))
                cur.execute("یکی از لایک‌ها را انتخاب کن، جایی که liker_id=%s و liked_id=%s",(target,uid))
                mutual=cur.fetchone() برابر با None نیست.
                اگر متقابل باشد:
                    a,b=get_match_pair(uid,target)
                    cur.execute("در صورت تداخل، مقادیر(%s،%s) را در تطابق‌های(user1_id,user2_id) وارد کن، کاری انجام نده",(a,b))
                    cur.execute("وارد کردن مقادیر(%s,%s) در chat_sessions(user_id,partner_id) ON CONFLICT(user_id) DO UPDATE SET partner_id=EXCLUDED.partner_id",(uid,target))
                    cur.execute("وارد کردن مقادیر(%s,%s) در chat_sessions(user_id,partner_id) ON CONFLICT(user_id) DO UPDATE SET partner_id=EXCLUDED.partner_id",(target,uid))
        bot.answer_callback_query(call.id,"❤️ مچ شدید!" if mutual else "💚 لایک ثبت شد.")
        اگر متقابل باشد:
            bot.send_message(uid,f"❤️ شما و طرف مقابل مچ شدید!\nبرای گفتگو پیام بفرستید. برای پایان چت /stopchat")
            bot.send_message(target,f"❤️ شما و طرف مقابل مچ شدید!\nبرای گفتگو پیام بفرستید. برای پایان چت /stopchat")
        این را امتحان کنید: bot.edit_message_reply_markup(call.message.chat.id,call.message.message_id,reply_markup=None)
        به جز استثنا: عبور
    به جز استثنا:
        logger.exception("کشیدن ناموفق")
        bot.answer_callback_query(call.id"خطا در ثبت انتخاب.")

def show_matches(message):
    uid=message.from_user.id
    با get_db() به عنوان conn:
        با conn.cursor() به عنوان تابع cur:
            cur.execute("""انتخاب حالت زمانی که user1_id=%s آنگاه user2_id در غیر این صورت user1_id به عنوان شریک پایان می‌یابد
                از بین تطابق‌ها، جایی که user1_id=%s یا user2_id=%s مرتب‌سازی بر اساس created_at محدودیت DESC: 30""",(uid,uid,uid))
            rows=cur.fetchall()
    اگر ردیف نباشد:
        bot.send_message(message.chat.id,"هنوز مچی نداری.",reply_markup=main_keyboard()); بازگشت
    برای ردیف به ردیف:
        u=get_user(row["partner"])
        اگر شما:
            bot.send_message(message.chat.id,f"❤️ {u['nickname']}، {u['age']} ساله — {u['city']}\nبرای شروع گفتگو پیام بده یا /stopchat برای پایان چت.",reply_markup=main_keyboard())

def relay_message(message):
    uid=message.from_user.id
    امتحان کنید:
        با get_db() به عنوان conn:
            با conn.cursor() به عنوان تابع cur:
                cur.execute("SELECT partner_id FROM chat_sessions WHERE user_id=%s",(uid,))
                row=cur.fetchone()
        اگر ردیف نباشد: مقدار False را برمی‌گرداند
        partner=row["partner_id"]
        اگر is_blocked(uid,partner):
            stop_chat_by_id(uid)
            bot.send_message(message.chat.id,"این گفتگو به دلیل مسدود شده بود.")
            مقدار True را برمی‌گرداند
        اگر message.content_type=="text":
            bot.send_message(partner,f"💬 پیام از طرف مچت:\n{message.text}")
        در غیر این صورت:
            bot.send_message(message.chat.id,"فعلاً فقط پیام متنی در چت مچ پشتیبانی می‌شود.")
        مقدار True را برمی‌گرداند
    به جز استثنا:
        logger.exception("رله ناموفق بود")
        bot.send_message(message.chat.id,"ارسال پیام انجام نشد.")
        مقدار True را برمی‌گرداند

def stop_chat_by_id(uid):
    با get_db() به عنوان conn:
        با conn.cursor() به عنوان تابع cur:
            cur.execute("SELECT partner_id FROM chat_sessions WHERE user_id=%s",(uid,))
            row=cur.fetchone()
            cur.execute("حذف از chat_sessions جایی که user_id=%s",(uid,))
            اگر سطر: cur.execute("حذف از chat_sessions جایی که user_id=%s و partner_id=%s",(row["partner_id"],uid))

def stop_chat(message):
    stop_chat_by_id(message.from_user.id)
    bot.send_message(message.chat.id,"گفتگو پایان یافت.",reply_markup=main_keyboard())

# =============================
# دعوت و ستاره
# =============================
def send_referral_link(message):
    me=get_user(message.from_user.id)
    اگر من نباشم:
        bot.send_message(message.chat.id,"اول پروفایلت رو بساز."); بازگشت
    نام کاربری=bot.get_me().username
    link=f"https://t.me/{username}?start=ref_{message.from_user.id}"
    bot.send_message(message.chat.id,f"🎁 لینک اختصاصی تو:\n{link}\nبا تکمیل ثبت نام دوستت، ۱۰ ستاره می‌گیری.",reply_markup=main_keyboard())

def send_star_invoice(message):
    # پرداخت تلگرام استارز مستقل از پرداخت تومانی است.
    امتحان کنید:
        prices=[types.LabeledPrice(label="۱۰۰ ستاره GapMate",amount=100)]
        bot.send_invoice(message.chat.id,title="100 ستاره GapMate",description="افزایش موجودی ۱۰۰ ستاره در GapMate",
            invoice_payload=f"gapmate_stars_100_{message.from_user.id}",provider_token="",currency="XTR",prices=prices)
    به جز استثنا:
        logger.exception("ارسال فاکتور ناموفق بود")
        bot.send_message(message.chat.id,"ارسال فاکتور ممکن است. کمی بعد دوباره جستجو کن.")

@bot.pre_checkout_query_handler(func=lambda q: True)
def pre_checkout(pre):
    امتحان کنید:
        bot.answer_pre_checkout_query(pre.id,ok=True)
    به جز استثنا:
        logger.exception("پیش پرداخت ناموفق")

@bot.message_handler(content_types=["successful_payment"])
تعریف پرداخت موفق(پیام):
    پرداخت=پیام.پرداخت_موفق
    امتحان کنید:
        اگر payment.currency!="XTR" باشد یا نباشد payment.invoice_payload.startswith("gapmate_stars_100_"):
            bot.send_message(message.chat.id,"پرداخت شد، اما اطلاعات سفارش قابل تشخیص نیست. با پشتیبانی تماس بگیر.")
            بازگشت
        uid=message.from_user.id
        با get_db() به عنوان conn:
            با conn.cursor() به عنوان تابع cur:
                cur.execute("به‌روزرسانی تنظیمات کاربران stars=COALESCE(stars,0)+100 WHERE telegram_id=%s",(uid,))
        bot.send_message(message.chat.id,"✅ پرداخت موفق بود؛ صد ستاره به حسابت اضافه شد.",reply_markup=main_keyboard())
    به جز استثنا:
        logger.exception("پرداخت با اعتبار ناموفق بود")
        bot.send_message(message.chat.id,"پرداخت ثبت شد اما افزودن ستاره با خطا روبه‌رو شد. با پشتیبانی تماس بگیرید.")

# =============================
#گزارش‌های_مدیر
# =============================
@bot.message_handler(commands=["reports"])
گزارش‌های تعریف‌شده (پیام):
    اگر ADMIN_ID یا message.from_user.id!=ADMIN_ID نباشد:
        bot.send_message(message.chat.id,"اجازه دسترسی نداری."); بازگشت
    امتحان کنید:
        با get_db() به عنوان conn:
            با conn.cursor() به عنوان تابع cur:
                cur.execute("SELECT * FROM reports ORDER BY created_at DESC LIMIT 30")
                rows=cur.fetchall()
        اگر ردیف نباشد:
            bot.send_message(message.chat.id,"گزارشی ثبت نشده."); بازگشت
        برای r در سطرها:
            bot.send_message(message.chat.id,f"گزارش شماره {r['id']}\nگزارش‌دهنده: {r['reporter_id']}\nکاربر: {r['reported_id']}\nدلیل: {r['reason']}")
    به جز استثنا:
        logger.exception("گزارش‌ها ناموفق بودند")
        bot.send_message(message.chat.id,"خطا در دریافت گزارش‌ها.")

# =============================
# وب‌هوک و رندر
# =============================
@app.route("/",methods=["GET"])
تعریف خانه():
    مقدار "GapMate در حال اجرا است" را برمی‌گرداند، ۲۰۰

@app.route("/health",methods=["GET"])
تعریف سلامت():
    return "OK",200

@app.route("/"+BOT_TOKEN,methods=["POST"])
تعریف وب‌هوک():
    اگر request.headers.get("content-type","") با ("application/json") شروع شود:
        update=telebot.types.Update.de_json(request.get_data().decode("utf-8"))
        bot.process_new_updates([update])
        return "OK",200
    "نوع محتوای نامعتبر" را برگردانید، 403

اگر __name__=="__main__":
    init_db()
    اگر RENDER_EXTERNAL_URL:
        bot.remove_webhook()
        bot.set_webhook(url=RENDER_EXTERNAL_URL+"/"+BOT_TOKEN)
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT",10000)))
    def block_user(user_id, target_id):
    first, second = sorted([user_id, target_id])

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO blocks (blocker, blocked)
                VALUES (%s, %s)
                ON CONFLICT DO NOTHING
            """, (user_id, target_id))

            cur.execute("""
                UPDATE chat_sessions
                SET active = FALSE
                WHERE user1 = %s AND user2 = %s
            """, (first, second))

    if user_states.get(user_id) == f"chat:{target_id}":
        user_states.pop(user_id, None)

    if user_states.get(target_id) == f"chat:{user_id}":
        user_states.pop(target_id, None)

    bot.send_message(
        user_id,
        "🚫 این کاربر مسدود شد.",
        reply_markup=main_menu()
    )


def report_user(user_id, target_id, reason):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO reports (reporter, reported, reason)
                VALUES (%s, %s, %s)
            """, (user_id, target_id, reason))

    bot.send_message(
        user_id,
        "گزارش تو ثبت شد. ممنون که کمک می‌کنی محیط امن‌تری داشته باشیم. ❤️",
        reply_markup=main_menu()
    )

    if ADMIN_ID:
        try:
            bot.send_message(
                int(ADMIN_ID),
                f"⚠️ <b>گزارش جدید</b>\n"
                f"گزارش‌دهنده: {user_id}\n"
                f"کاربر گزارش‌شده: {target_id}\n"
                f"دلیل: {escape(reason)}"
            )
        except Exception:
            logger.exception("Could not send report to admin")


def delete_user_account(user_id):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                DELETE FROM likes
                WHERE from_user = %s OR to_user = %s
            """, (user_id, user_id))

            cur.execute("""
                DELETE FROM passes
                WHERE from_user = %s OR to_user = %s
            """, (user_id, user_id))

            cur.execute("""
                DELETE FROM matches
                WHERE user1 = %s OR user2 = %s
            """, (user_id, user_id))

            cur.execute("""
                DELETE FROM blocks
                WHERE blocker = %s OR blocked = %s
            """, (user_id, user_id))

            cur.execute("""
                DELETE FROM reports
                WHERE reporter = %s OR reported = %s
            """, (user_id, user_id))

            cur.execute("""
                DELETE FROM chat_sessions
                WHERE user1 = %s OR user2 = %s
            """, (user_id, user_id))

            cur.execute("""
                DELETE FROM referrals
                WHERE referrer = %s OR referred = %s
            """, (user_id, user_id))

            cur.execute("""
                DELETE FROM star_payments
                WHERE user_id = %s
            """, (user_id,))

            cur.execute("""
                DELETE FROM users
                WHERE user_id = %s
            """, (user_id,))

    user_states.pop(user_id, None)
    registration_data.pop(user_id, None)

    bot.send_message(
        user_id,
        "حساب کاربری تو حذف شد. هر وقت خواستی می‌تونی دوباره ثبت‌نام کنی.",
        reply_markup=types.ReplyKeyboardRemove()
    )


def show_admin_reports(chat_id):
    if not ADMIN_ID or str(chat_id) != str(ADMIN_ID):
        bot.send_message(chat_id, "⛔ دسترسی نداری.")
        return

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT reporter, reported, reason, created_at
                FROM reports
                ORDER BY id DESC
                LIMIT 30
            """)

            reports_list = cur.fetchall()

    if not reports_list:
        bot.send_message(chat_id, "گزارشی ثبت نشده.")
        return

    for report in reports_list:
        bot.send_message(
            chat_id,
            f"⚠️ <b>گزارش</b>\n"
            f"از طرف: {report['reporter']}\n"
            f"علیه: {report['reported']}\n"
            f"دلیل: {escape(report['reason'] or '')}\n"
            f"زمان: {report['created_at']}"
        )


def toggle_privacy(user_id, column):
    allowed = {
        "profile_visible",
        "location_visible"
    }

    if column not in allowed:
        return

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT {column} FROM users WHERE user_id = %s",
                (user_id,)
            )

            user = cur.fetchone()

            if not user:
                return

            new_value = not user[column]

            cur.execute(
                f"UPDATE users SET {column} = %s WHERE user_id = %s",
                (new_value, user_id)
            )

    return new_value
    @bot.message_handler(commands=["start"])
def start_command(message):
    user_id = message.from_user.id
    parts = message.text.split(maxsplit=1)

    if len(parts) > 1 and parts[1].startswith("ref_"):
        try:
            referrer_id = int(parts[1][4:])

            if referrer_id != user_id and get_user(referrer_id):
                with get_db() as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            INSERT INTO referrals (referrer, referred)
                            VALUES (%s, %s)
                            ON CONFLICT (referred) DO NOTHING
                        """, (referrer_id, user_id))
        except ValueError:
            pass

    user = get_user(user_id)

    if user:
        send_home(message.chat.id)
    else:
        bot.send_message(
            message.chat.id,
            "سلام! به گپ‌میت خوش اومدی ❤️\n"
            "برای آشنایی با افراد جدید، اول پروفایلت رو بساز."
        )
        start_registration(user_id)


@bot.message_handler(commands=["stopchat"])
def stopchat_command(message):
    stop_chat(message.from_user.id)


@bot.message_handler(commands=["reports"])
def reports_command(message):
    show_admin_reports(message.chat.id)


@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id
    data = call.data

    try:
        if data == "edit_profile":
            user = get_user(user_id)

            if not user:
                bot.answer_callback_query(
                    call.id,
                    "ابتدا ثبت‌نام کن."
                )
                return

            registration_data[user_id] = {
                "nickname": user["nickname"],
                "age": user["age"],
                "gender": user["gender"],
                "city": user["city"],
                "bio": user["bio"]
            }

            user_states[user_id] = "nickname"

            bot.send_message(
                user_id,
                "نام یا لقب جدیدت رو وارد کن:"
            )

        elif data == "toggle_profile":
            value = toggle_privacy(
                user_id,
                "profile_visible"
            )

            if value is not None:
                status = "نمایش داده می‌شود" if value else "مخفی است"
                bot.answer_callback_query(
                    call.id,
                    f"پروفایل تو اکنون {status}."
                )

        elif data == "toggle_location":
            value = toggle_privacy(
                user_id,
                "location_visible"
            )

            if value is not None:
                status = "نمایش داده می‌شود" if value else "مخفی است"
                bot.answer_callback_query(
                    call.id,
                    f"موقعیت تو اکنون {status}."
                )

        elif data == "delete_account":
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(
                types.InlineKeyboardButton(
                    "بله، حذف کن",
                    callback_data="confirm_delete"
                ),
                types.InlineKeyboardButton(
                    "انصراف",
                    callback_data="cancel_delete"
                )
            )

            bot.send_message(
                user_id,
                "⚠️ مطمئنی؟ با حذف حساب، پروفایل و اطلاعات مرتبطت پاک می‌شه.",
                reply_markup=keyboard
            )

        elif data == "confirm_delete":
            delete_user_account(user_id)

        elif data == "cancel_delete":
            bot.send_message(
                user_id,
                "حذف حساب لغو شد.",
                reply_markup=main_menu()
            )

        elif data == "buy_stars":
            bot.answer_callback_query(call.id)

            bot.send_invoice(
                user_id,
                title="خرید ۱۰۰ ستاره گپ‌میت",
                description="۱۰۰ ستاره برای استفاده از امکانات گپ‌میت",
                invoice_payload=f"stars_100_{user_id}",
                provider_token="",
                currency="XTR",
                prices=[
                    types.LabeledPrice(
                        label="۱۰۰ ستاره",
                        amount=100
                    )
                ]
            )

        elif data.startswith("like_"):
            target_id = int(data.split("_", 1)[1])
            handle_like(user_id, target_id)
            bot.answer_callback_query(call.id)
            find_nearby(user_id, user_id)

        elif data.startswith("pass_"):
            target_id = int(data.split("_", 1)[1])
            handle_pass(user_id, target_id)
            bot.answer_callback_query(call.id)

        elif data.startswith("block_"):
            target_id = int(data.split("_", 1)[1])
            block_user(user_id, target_id)
            bot.answer_callback_query(call.id)

        elif data.startswith("report_"):
            target_id = int(data.split("_", 1)[1])

            user_states[user_id] = f"report:{target_id}"

            bot.send_message(
                user_id,
                "لطفاً دلیل گزارشت رو بنویس:"
            )
            bot.answer_callback_query(call.id)

        elif data.startswith("chat_"):
            target_id = int(data.split("_", 1)[1])
            start_chat(user_id, target_id)
            bot.answer_callback_query(call.id)

        else:
            bot.answer_callback_query(call.id)

    except Exception:
        logger.exception("Callback error")
        bot.answer_callback_query(
            call.id,
            "مشکلی پیش اومد. دوباره تلاش کن."
        ) 
@bot.pre_checkout_query_handler(func=lambda query: True)
def pre_checkout_handler(query):
    try:
        bot.answer_pre_checkout_query(
            query.id,
            ok=True
        )
    except Exception:
        logger.exception("Pre-checkout error")


@bot.message_handler(content_types=["successful_payment"])
def successful_payment_handler(message):
    user_id = message.from_user.id
    payment = message.successful_payment

    expected_payload = f"stars_100_{user_id}"

    if payment.invoice_payload != expected_payload:
        bot.send_message(
            user_id,
            "پرداخت تأیید نشد. لطفاً با پشتیبانی تماس بگیر."
        )
        return

    charge_id = payment.telegram_payment_charge_id

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO star_payments
                (user_id, charge_id, amount)
                VALUES (%s, %s, %s)
                ON CONFLICT (charge_id) DO NOTHING
                RETURNING id
            """, (user_id, charge_id, payment.total_amount))

            inserted = cur.fetchone()

            if inserted:
                cur.execute("""
                    UPDATE users
                    SET stars = stars + 100
                    WHERE user_id = %s
                """, (user_id,))

    if inserted:
        bot.send_message(
            user_id,
            "پرداخت با موفقیت انجام شد! 🎉\n"
            "۱۰۰ ستاره به حسابت اضافه شد. ⭐",
            reply_markup=main_menu()
        )
    else:
        bot.send_message(
            user_id,
            "این پرداخت قبلاً ثبت شده است."
        )


@bot.message_handler(content_types=["location"])
def location_handler(message):
    user_id = message.from_user.id

    if not get_user(user_id):
        bot.send_message(
            user_id,
            "اول ثبت‌نامت رو کامل کن."
        )
        return

    location = message.location

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE users
                SET latitude = %s,
                    longitude = %s
                WHERE user_id = %s
            """, (
                location.latitude,
                location.longitude,
                user_id
            ))

    bot.send_message(
        user_id,
        "📍 موقعیتت ثبت شد.",
        reply_markup=main_menu()
    )


@bot.message_handler(content_types=["text"])
def text_handler(message):
    user_id = message.from_user.id
    text = message.text.strip()

    if text.startswith("/"):
        return

    state = user_states.get(user_id)

    if state and state.startswith("report:"):
        try:
            target_id = int(state.split(":")[1])
            report_user(user_id, target_id, text)
            user_states.pop(user_id, None)
        except Exception:
            logger.exception("Report handling error")
            bot.send_message(
                user_id,
                "ثبت گزارش انجام نشد. دوباره تلاش کن."
            )
        return

    if state == "nickname":
        if len(text) < 2 or len(text) > 30:
            bot.send_message(
                user_id,
                "نام باید بین ۲ تا ۳۰ حرف باشه."
            )
            return

        registration_data.setdefault(user_id, {})
        registration_data[user_id]["nickname"] = text
        user_states[user_id] = "age"

        bot.send_message(
            user_id,
            "چند سالته؟ فقط عدد سن رو وارد کن:"
        )
        return

    if state == "age":
        try:
            age = int(text)
        except ValueError:
            bot.send_message(
                user_id,
                "سن رو فقط به صورت عدد وارد کن."
            )
            return

        if age < 18 or age > 99:
            bot.send_message(
                user_id,
                "برای استفاده از گپ‌میت باید حداقل ۱۸ سال داشته باشی."
            )
            return

        registration_data[user_id]["age"] = age
        user_states[user_id] = "gender"

        keyboard = types.ReplyKeyboardMarkup(
            resize_keyboard=True,
            one_time_keyboard=True
        )
        keyboard.row("آقا", "خانم")
        keyboard.row("ترجیح می‌دم نگم")

        bot.send_message(
            user_id,
            "جنسیتت رو انتخاب کن:",
            reply_markup=keyboard
        )
        return

    if state == "gender":
        if text not in ["آقا", "خانم", "ترجیح می‌دم نگم"]:
            bot.send_message(
                user_id,
                "یکی از گزینه‌های نمایش داده شده رو انتخاب کن."
            )
            return

        registration_data[user_id]["gender"] = text
        user_states[user_id] = "city"

        bot.send_message(
            user_id,
            "در کدوم شهر زندگی می‌کنی؟"
        )
        return

    if state == "city":
        if len(text) > 60:
            bot.send_message(
                user_id,
                "اسم شهر خیلی طولانیه. دوباره بنویس."
            )
            return

        registration_data[user_id]["city"] = text
        user_states[user_id] = "bio"

        bot.send_message(
            user_id,
            "یک توضیح کوتاه درباره خودت بنویس.\n"
            "اگر نمی‌خوای، فقط بنویس: رد کردن"
        )
        return

    if state == "bio":
        if text == "رد کردن":
            text = ""

        if len(text) > 300:
            bot.send_message(
                user_id,
                "توضیحت باید حداکثر ۳۰۰ حرف باشه."
            )
            return

        registration_data[user_id]["bio"] = text
        finish_registration(user_id)
        return

    if state and state.startswith("chat:"):
        if text in ["🔎 پیدا کردن افراد", "❤️ علاقه‌مندی‌ها",
                    "👤 پروفایل من", "⭐ موجودی ستاره",
                    "⚙️ تنظیمات", "📨 دعوت از دوستان"]:
            user_states.pop(user_id, None)
        else:
            if relay_message(message):
                return

    if text == "🔎 پیدا کردن افراد":
        find_nearby(user_id, user_id)

    elif text == "❤️ علاقه‌مندی‌ها":
        show_matches(user_id, user_id)

    elif text == "👤 پروفایل من":
        show_profile(user_id, user_id)

    elif text == "⭐ موجودی ستاره":
        show_stars(user_id, user_id)

    elif text == "⚙️ تنظیمات":
        show_settings(user_id)

    elif text == "📨 دعوت از دوستان":
        show_referral(user_id, user_id)

    else:
        if not get_user(user_id):
            start_registration(user_id)
        else:
            send_home(
                user_id,
                "از دکمه‌های منو استفاده کن. 😊"
            )@app.route("/", methods=["GET"])
def health_check():
    return "GapMate is running!", 200


@app.route("/webhook", methods=["POST"])
def webhook():
    if request.headers.get("content-type") == "application/json":
        json_string = request.get_data().decode("utf-8")
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return "OK", 200

    return "Invalid content type", 403


def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(
        host="0.0.0.0",
        port=port
    )


def setup_webhook():
    external_url = os.getenv("RENDER_EXTERNAL_URL")

    if external_url:
        webhook_url = external_url.rstrip("/") + "/webhook"

        try:
            bot.remove_webhook()
            bot.set_webhook(url=webhook_url)
            logger.info("Webhook configured")
        except Exception:
            logger.exception("Webhook setup failed")
    else:
        logger.info("RENDER_EXTERNAL_URL not configured")


if __name__ == "__main__":
    try:
        init_db()
        setup_webhook()

        flask_thread = threading.Thread(
            target=run_flask,
            daemon=True
        )
        flask_thread.start()

        logger.info("GapMate started")

        if not os.getenv("RENDER_EXTERNAL_URL"):
            bot.infinity_polling(
                skip_pending=True,
                timeout=30,
                long_polling_timeout=30
            )

    except Exception:
        logger.exception("GapMate startup failed")
        raise
