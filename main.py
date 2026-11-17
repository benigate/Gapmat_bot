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
