ایمپورت کردن سیستم عامل
وارد کردن ریاضی
ورود اطلاعات
از contextlib، contextmanager را وارد کنید

وارد کردن تله‌بات
از انواع واردات telebot
وارد کردن psycopg2
از psycopg2.extras، RealDictCursor را وارد کنید
از فلاسک، فلاسک را وارد کنید، درخواست دهید

# =============================
# تنظمات
# =============================
BOT_TOKEN = os.environ["BOT_TOKEN"]
آدرس پایگاه داده = os.environ["آدرس پایگاه داده"]
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "")).rstrip("/")
STAR_PRICE_IRR = 100 # قیمت پایه در صورت استفاده از Telegram Stars، واحد XTR است
ربات = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
ثبت نام = {}
# وضعیت چت در دیتابیس نگهداری می‌شود تا با ریاستارت رندر از بین نرود.

@contextmanager
def get_db():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor, sslmode="require")
    امتحان کنید:
        اتصال yield
        conn.commit()
    به جز استثنا:
        conn.rollback()
        افزایش
    در نهایت:
        conn.close()

تعریف init_db():
    با get_db() به عنوان conn:
        با conn.cursor() به عنوان تابع cur:
            cur.execute("""
                ایجاد جدول در صورت عدم وجود کاربران (
                    telegram_id کلید اصلی بزرگ،
                    متن نام مستعار، سن عدد صحیح، متن جنسیت، متن شهر،
                    دقت مضاعف عرض جغرافیایی، دقت مضاعف طول جغرافیایی،
                    location_visible مقدار پیش‌فرض بولی False
                    profile_visible مقدار پیش‌فرض بولی، درست
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # افزودن ستون‌ها به دیتابیس موجود بدون حذف اطلاعات قبلی
            برای stmt در [
                «کاربران جدول را تغییر دهید، اگر عرض جغرافیایی وجود نداشت، ستون را اضافه کنید، با دقت دو برابر»
                «کاربران جدول را تغییر دهید، اگر ستونی وجود نداشت، طول جغرافیایی را با دقت مضاعف اضافه کنید.»
                "کاربران جدول را تغییر دهید، ستون را اضافه کنید اگر وجود نداشته باشد location_visible مقدار بولی پیش‌فرض نادرست",
                "کاربران جدول را تغییر دهید، ستون را اضافه کنید اگر وجود ندارد profile_visible مقدار بولی پیش‌فرض درست است",
                «کاربران جدول را تغییر دهید، اگر ستونی وجود نداشت، نام مستعار را اضافه کنید»
                "کاربران جدول را تغییر دهید، اگر ستونی وجود نداشت، عدد صحیح سن را اضافه کنید."
                "کاربران جدول را تغییر دهید، اگر ستونی وجود نداشت، متن جنسیت را اضافه کنید."
                "کاربران جدول را تغییر دهید، اگر ستونی وجود نداشت، متن شهر را اضافه کنید."
                «کاربران جدول را تغییر دهید، اگر ستونی وجود نداشت، ستاره اضافه کنید. عدد صحیح، پیش‌فرض ۰»
            ]:
                cur.execute(stmt)
            cur.execute("""
                ایجاد جدول در صورت عدم وجود بلوک‌ها (
                    ‎blocker_id مقدار بزرگ تهی نیست، blocked_id مقدار بزرگ تهی نیست،
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    کلید اصلی (شناسه مسدودکننده، شناسه مسدودشده)
                )
            """)
            cur.execute("""
                ایجاد جدول در صورت عدم وجود گزارش‌ها (
                    کلید اصلی سریال شناسه، شناسه گزارشگر مقدار بزرگ NULL ندارد،
                    ‎reported_id ‎مقدار بزرگ NULL نیست، دلیل متن،
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute("""
                ایجاد جدول در صورت عدم وجود activity_logs (
                    شناسه سریال کلید اصلی، telegram_id BIGINT،
                    متن فعالیت، created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute("""
                ایجاد جدول در صورت عدم وجود لایک (
                    liker_id مقدار بزرگ تهی نیست، liked_id مقدار بزرگ تهی نیست،
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    کلید اصلی (liker_id، liked_id)
                )
            """)
            cur.execute("""
                ایجاد جدول در صورت عدم وجود (
                    شناسه عبور مقدار بزرگ تهی نیست، شناسه عبور مقدار بزرگ تهی نیست،
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    کلید اصلی (شناسه عبور، شناسه عبور)
                )
            """)
            cur.execute("""
                ایجاد جدول در صورت عدم وجود تطابق‌ها (
                    user1_id مقدار بزرگ NULL نیست، user2_id مقدار بزرگ NULL نیست،
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    کلید اصلی (شناسه کاربر ۱، شناسه کاربر ۲)
                )
            """)
            cur.execute("""
                ایجاد جدول در صورت عدم وجود ارجاعات (
                    invite_id کلید اصلی بزرگ است، referrer_id کلید اصلی بزرگ نیست،
                    مقدار پیش‌فرض بولی (BOOLEAN) با پاداش، نادرست
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute("""
                ایجاد جدول در صورت عدم وجود chat_sessions (
                    شناسه کاربر، کلید اصلی بزرگ، شناسه شریک، مقدار بزرگ تهی نیست،
                    شروع شده در TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

تعریف log_activity(user_id, activity):
    امتحان کنید:
        با get_db() به عنوان conn:
            با conn.cursor() به عنوان تابع cur:
                cur.execute("وارد کردن مقادیر (%s، %s) در activity_logs (telegram_id, activity)", (user_id, activity))
    به جز استثنا:
        logger.exception("ثبت فعالیت ناموفق بود")

def get_user(user_id):
    با get_db() به عنوان conn:
        با conn.cursor() به عنوان تابع cur:
            cur.execute("SELECT * FROM users WHERE telegram_id=%s", (user_id,))
            return cur.fetchone()

def save_profile(user_id, profile):
    با get_db() به عنوان conn:
        با conn.cursor() به عنوان تابع cur:
            cur.execute("""
                وارد کردن به کاربران
                (شناسه_تلگرام، نام مستعار، سن، جنسیت، شهر، عرض جغرافیایی، طول جغرافیایی، مکان_قابل_مشاهده، پروفایل_قابل_مشاهده، ستاره‌ها)
                مقادیر (%s،%s،%s،%s،%s،%s،%s،%s،%s، درست، 0)
                در مورد تداخل (telegram_id) تنظیمات را به‌روزرسانی کنید
                  نام مستعار=EXCLUDED.nickname، سن=EXCLUDED.age، جنسیت=EXCLUDED.gender،
                  city=EXCLUDED.city, latitude=EXCLUDED.latitude, longitude=EXCLUDED.longitude,
                  location_visible=EXCLUDED.location_visible
            """, (شناسه_کاربر, profile.get("نام مستعار"), profile.get("سن"), profile.get("جنسیت"),
                  profile.get("city"), profile.get("latitude"), profile.get("longitude"),
                  profile.get("location_visible", False)))

تعریف main_keyboard():
    k = types.ReplyKeyboardMarkup(resize_keyboard=True)
    k.row("🔎 افراد نزدیک", "👤 پروفایل من")
    k.row("💚 مچ‌های من"، "⭐ ستاره‌های من")
    k.row("🎁 دعوت دوستان", "🛍 خرید ستاره")
    k.row("📍 ارسال موقعیت", "🔒 حریم خصوصی")
    k.row("🚫 بلاك کاربر", "⚠️ گزارش کاربر")
    k.row("🗑 حذف حساب", "❌ لغو")
    برگرداندن k

تعریف privacy_keyboard():
    k = types.InlineKeyboardMarkup()
    k.add(types.InlineKeyboardButton("مخفی کردن پروفایل", callback_data="hide_profile"))
    k.add(types.InlineKeyboardButton("نمایش پروفایل", callback_data="show_profile"))
    k.add(types.InlineKeyboardButton("مخفی کردن موقعیت", callback_data="hide_location"))
    k.add(types.InlineKeyboardButton("نمایش موقعیت", callback_data="show_location"))
    برگرداندن k

def is_blocked(a, b):
    با get_db() به عنوان conn:
        با conn.cursor() به عنوان تابع cur:
            cur.execute("""انتخاب ۱ از بلوک‌ها از کجا
                (blocker_id=%s و blocked_id=%s) یا (blocker_id=%s و blocked_id=%s) محدودیت ۱""",
                (الف، ب، ب، الف))
            مقدار return cur.fetchone() برابر با None نیست.

def finish_registration(message):
    شناسه کاربری = message.from_user.id
    profile = registration.get(uid, {}).get("profile", {})
    امتحان کنید:
        موجود = get_user(uid)
        save_profile(uid, profile)
        با get_db() به عنوان conn:
            با conn.cursor() به عنوان تابع cur:
                اگر موجود نباشد:
                    cur.execute("به‌روزرسانی تنظیمات کاربران stars=COALESCE(stars,0)+6 WHERE telegram_id=%s", (uid,))
                cur.execute("شناسه ارجاع‌دهنده را از بین ارجاعات انتخاب کنید، جایی که شناسه دعوت‌شده=%s و پاداش داده‌شده=FALSE", (شناسه کاربری,))
                ref = cur.fetchone()
                اگر ref و ref["referrer_id"] != uid:
                    cur.execute("به‌روزرسانی تنظیمات کاربران stars=COALESCE(stars,0)+10 WHERE telegram_id=%s", (ref["referrer_id"],))
                    cur.execute("به‌روزرسانی ارجاعات، مقدار پاداش داده شده را برابر با TRUE قرار بده، در جایی که invite_id=%s", (uid,))
        registration.pop(uid, None)
        bot.send_message(message.chat.id, "✅ پروفایلت ذخیره شد!\nبه GapMate خوش اومدی 🌱", reply_markup=main_keyboard())
        اگر موجود نباشد:
            bot.send_message(message.chat.id, "🎉 ۶ ستاره هدیه ثبت‌نام به اضافه شد.")
        log_activity(uid, "registration_completed")
    به جز استثنا:
        logger.exception("ثبت نام ناموفق")
        bot.send_message(message.chat.id, "❌ ذخیره پروفایل انجام نشد. دوباره جستجو کن.")

تعریف distance_km(lat1، lon1، lat2، lon2):
    r = 6371
    dlat، dlon = math.radians(lat2-lat1)، math.radians(lon2-lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlon/2)**2
    تابع ()r * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a)) را برمی‌گرداند.

def show_profile(message):
    امتحان کنید:
        u = get_user(message.from_user.id)
        اگر نه:
            bot.send_message(message.chat.id, "هنوز پروفایلی نداری. /start رو ​​بزن.")
            بازگشت
        bot.send_message(message.chat.id,
            "👤 پروفایل تو\n\n"
            f"نام مستعار: {u['nickname']}\nسن: {u['age']}\nجنسیت: {u['gender']}\nشهر: {u['city']}\n"
            f"نمایش پروفایل: {'روشن' if u['profile_visible'] else 'خاموش'}\n"
            f"نمایش موقعیت: {'روشن' if u['location_visible'] else 'خاموش'}\n⭐ ستاره‌ها: {u.get('stars') or 0}",
            reply_markup=main_keyboard())
    به جز استثنا:
        logger.exception("نمایش پروفایل ناموفق بود")
        bot.send_message(message.chat.id, "خطا در نمایش پروفایل.")

تعریف در نزدیکی (پیام):
    شناسه کاربری = message.from_user.id
    امتحان کنید:
        me = get_user(uid)
        اگر من نباشم:
            bot.send_message(message.chat.id, "اول باید پروفایلت رو بسازی.")
            بازگشت
        اگر me["latitude"] برابر با None باشد یا me["longitude"] برابر با None باشد یا me["location_visible"] نباشد:
            bot.send_message(message.chat.id, "برای پیدا کردن افراد نزدیک، موقعیت رو ارسال و نمایش موقعیت رو فعال کن.")
            بازگشت
        با get_db() به عنوان conn:
            با conn.cursor() به عنوان تابع cur:
                cur.execute("""SELECT * از کاربرانی که telegram_id<>%s و profile_visible=TRUE هستند
                    و سن>=18 و نام مستعار NULL""", (uid,)) نیست.
                people = cur.fetchall()
                cur.execute("SELECT liked_id FROM likes WHERE liker_id=%s UNION SELECT passed_id FROM passes WHERE passer_id=%s", (uid, uid))
                seen = {x["liked_id"] اگر x.get("liked_id") برابر با None نباشد، در غیر این صورت x["passed_id"] برای x در cur.fetchall()}
        نامزدها = []
        برای p در افراد:
            اگر p["telegram_id"] در شناسه کاربری دیده شده یا مسدود شده باشد (uid، p["telegram_id"]):
                ادامه
            اگر p["latitude"] برابر با None نباشد و p["longitude"] نیز برابر با None نباشد:
                d = distance_km(me["latitude"], me["longitude"], p["latitude"], p["longitude"])
                اگر d <= 50 باشد:
                    candidate.append((d, p))
        candidate.sort(key=lambda x: x[0])
        اگر نامزد نباشد:
            bot.send_message(message.chat.id, "فعلاً پروفایل قدیمی در نزدیکی تو پیدا نشد.", reply_markup=main_keyboard())
            بازگشت
        برای d و p در کاندیدها[:10]:
            kb = types.InlineKeyboardMarkup()
            kb.row(types.InlineKeyboardButton("💚 لایک", callback_data=f"like:{p['telegram_id']}"),
                   type.InlineKeyboardButton("👎 رد کردن", callback_data=f"pass:{p['telegram_id']}"))
            bot.send_message(message.chat.id,
                f"👤 پروفایل پیشنهادی\n\nنام: {p['nickname']}\nسن: {p['age']}\nجنسیت: {p['gender']}\nشهر: {p['city']}\nفاصله تقریبی: {round(d)} کیلومتر",
                reply_markup=kb)
    به جز استثنا:
        logger.exception("در نزدیکی ناموفق بود")
        bot.send_message(message.chat.id, "خطا در جست‌وجوی افراد نزدیک.")

def ask_location(message):
    k = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    k.add(types.KeyboardButton("ارسال موقعیت من", request_location=True))
    k.add("❌ لغو")
    bot.send_message(message.chat.id, "برای ذخیره موقعیت، دکمه زیر رو بزن:"، reply_markup=k)

def get_match_pair(a, b):
    return (min(a,b), max(a,b))

# =============================
# شروع و ترتیب
# =============================
@bot.message_handler(commands=["start"])
تعریف شروع(پیام):
    شناسه کاربری = message.from_user.id
    log_activity(uid, "start")
    امتحان کنید:
        parts = (message.text یا "").split(maxsplit=1)
        اگر len(parts) > 1 باشد، payload = parts[1] در غیر این صورت ""
        موجود = get_user(uid)
        اگر payload.startswith("ref_") باشد:
            امتحان کنید:
                referrer = int(payload[4:])
                اگر شناسه ارجاع دهنده != باشد و شناسه موجود None باشد:
                    با get_db() به عنوان conn:
                        با conn.cursor() به عنوان تابع cur:
                            cur.execute("درج در ارجاعات(invited_id,referrer_id) مقادیر(%s,%s) در تداخل(invited_id) کاری انجام نده", (uid, referrer))
            به جز ValueError:
                عبور
        اگر موجود باشد و existing.get("nickname"):
            bot.send_message(message.chat.id, f"سلام {existing['nickname']}! خوش برگشتی 🌱", reply_markup=main_keyboard())
            بازگشت
        ثبت نام[uid] = {"مرحله":"نام مستعار", "پروفایل":{}}
        bot.send_message(message.chat.id, "سلام! به GapMate خوش اومدی 🌱\nبرای ساخت پروفایل، یک نام مستعار وارد کن:")
    به جز استثنا:
        logger.exception("شروع ناموفق")
        bot.send_message(message.chat.id, "❌ فعلاً اتصال به دیتابیس مشکل دارد. دوباره جستجو کن.")

@bot.message_handler(commands=["cancel"])
def cancel(message):
    registration.pop(message.from_user.id, None)
    bot.send_message(message.chat.id, "عملیات لغو شد.", reply_markup=main_keyboard())

@bot.message_handler(commands=["dbcheck"])
def dbcheck(message):
    امتحان کنید:
        با get_db() به عنوان conn:
            با conn.cursor() به عنوان تابع cur:
                cur.execute("SELECT COUNT(*) AS n FROM users"); n=cur.fetchone()["n"]
                تابع cur.execute("SELECT COUNT(*) AS n FROM activity_logs"); تابع logs=cur.fetchone()["n"]
        bot.send_message(message.chat.id, f"✅ دیتابیس متصل است.\nتعداد پروفایل‌ها: {n}\nتعداد فعالیت‌ها: {logs}")
    به جز استثنا:
        logger.exception("بررسی پایگاه داده ناموفق بود")
        bot.send_message(message.chat.id, "❌ اتصال دیتابیس ناموفق بود.")

@bot.message_handler(content_types=["text"])
تعریف handle_text(message):
    شناسه کاربری، متن = message.from_user.id، (message.text یا "").strip()
    اگر text.startswith("/") باشد:
        بازگشت
    اگر متن == "❌ لغو" باشد:
        registration.pop(uid, None)
        bot.send_message(message.chat.id, "عملیات لغو شد.", reply_markup=main_keyboard())
        بازگشت
    اگر شناسه کاربری در ثبت نام باشد:
        مرحله، نمایه = ثبت نام[uid]["مرحله"]، ثبت نام[uid]["پروفایل"]
        اگر مرحله == "نام مستعار" باشد:
            اگر 2 <= len(text) <= 30 نباشد:
                bot.send_message(message.chat.id, "نام مستعار باید بین ۲ تا ۳۰ حرف باشد."); بازگشت
            profile["nickname"]=text; registration[uid]["step"]="age"
            bot.send_message(message.chat.id, "چند سالته؟ فقط عدد وارد کن:"); بازگشت
        اگر مرحله == "سن" باشد:
            امتحان کنید:
                سن=int(text)
                اگر سن کمتر از ۱۸ سال یا بیشتر از ۱۰۰ سال باشد: خطای ValueError رخ می‌دهد.
            به جز ValueError:
                bot.send_message(message.chat.id, "سن باید عددی بین ۱۸ تا ۱۰۰ باشد."); بازگشت
            profile["age"]=age; registration[uid]["step"]="gender"
            k=types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True); k.row("مرد"، "زن"، "سایر")
            bot.send_message(message.chat.id, "جنسیت رو انتخاب کن:", reply_markup=k); بازگشت
        اگر مرحله == "جنسیت" باشد:
            اگر متن در ["مرد"، "زن"، "سایر"] نباشد:
                bot.send_message(message.chat.id, "یکی از گزینه های موجود رو انتخاب کن."); بازگشت
            profile["gender"]=text; registration[uid]["step"]="city"
            bot.send_message(message.chat.id, "اسم شهرت رو وارد کن:"); بازگشت
        اگر مرحله == "شهر" باشد:
            اگر نه ۲ <= len(text) <= ۶۰:
                bot.send_message(message.chat.id, "اسم شهر معتبر نیست."); بازگشت
            profile["city"]=text; registration[uid]["step"]="location_consent"
            k=types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True); k.row("📍 ارسال موقعیت","رد کردن")
            bot.send_message(message.chat.id, "می‌تونی موقعیت رو برای پیدا کردن افراد نزدیک بفرستی.\nموقعیت فقط با اجازه خودت استفاده می‌شه.", reply_markup=k); بازگشت
        اگر مرحله == "location_consent" باشد:
            اگر متن == "رد کردن" باشد:
                profile["location_visible"]=False; finish_registration(message); return
            if text == "📍 ارسال پست":
                ثبت نام[uid]["step"]="waiting_location"
                k=types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
                k.add(types.KeyboardButton("ارسال موقعیت من", request_location=True)); k.add("رد کردن")
                bot.send_message(message.chat.id, "برای ارسال پست، دکمه زیر رو بزن:", reply_markup=k); بازگشت
            bot.send_message(message.chat.id, "ارسال موقعیت یا رد کردن رو انتخاب کن."); بازگشت
        اگر مرحله == "مکان_انتظار" باشد:
            اگر متن == "رد کردن" باشد:
                profile["location_visible"]=False; finish_registration(message); return
            bot.send_message(message.chat.id, "لطفاً از دکمه ارسال موقعیت استفاده کن یا رد کردن رو بزن."); بازگشت
        اگر در ["block_user","report_user"] مرحله‌ای را وارد کنید:
            امتحان کنید:
                target=int(text)
                اگر target == uid: خطای ValueError رخ دهد
            به جز ValueError:
                bot.send_message(message.chat.id, "شناسه عددی معتبر بفرست و خودت رو انتخاب نکن."); بازگشت
            registration.pop(uid,None)
            اگر مرحله == "block_user" باشد:
                با get_db() به عنوان conn:
                    با conn.cursor() به عنوان تابع cur:
                        cur.execute("در صورت تداخل، مقادیر(%s،%s) را در بلوک‌ها(blocker_id,blocked_id) وارد کنید و هیچ کاری انجام ندهید",(uid,target))
                bot.send_message(message.chat.id, "🚫 کاربر بلاک شد.", reply_markup=main_keyboard())
            در غیر این صورت:
                registration[uid]={"step":"report_reason","profile":{"reported_id":target}}
                bot.send_message(message.chat.id, "دلیل گزارش رو بنویس:")
            بازگشت
        اگر مرحله == "report_reason" باشد:
            target=profile["reported_id"]
            با get_db() به عنوان conn:
                با conn.cursor() به عنوان تابع cur:
                    cur.execute("وارد کردن در گزارش‌ها(شناسه_گزارشگر،شناسه_گزارش‌شده،دلیل) مقادیر(%s،%s،%s)",(uid،target،text))
            registration.pop(uid,None)
            bot.send_message(message.chat.id, "✅ گزارش ثبت شد.", reply_markup=main_keyboard())
            اگر ADMIN_ID:
                try: bot.send_message(ADMIN_ID, f"⚠️ گزارش جدید\nگزارش‌دهنده: {uid}\nکاربر: {target}\nدلیل: {text}")
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
