)
        except Exception:
            app.logger.exception("Database save failed")
            bot.send_message(chat_id, "❌ ذخیره در دیتابیس ناموفق بود.")
            return

        registration.pop(user_id, None)
        bot.send_message(
            chat_id,
            "🎉 پروفایلت با موفقیت در دیتابیس ذخیره شد!",
            reply_markup=types.ReplyKeyboardRemove()
        )

@app.route("/", methods=["GET"])
def home():
    return "GapMate is running!"

@app.route("/webhook", methods=["POST"])
def webhook():
    if request.headers.get("content-type", "").startswith("application/json"):
        update = telebot.types.Update.de_json(request.get_data().decode("utf-8"))
        bot.process_new_updates([update])
        return "OK", 200
    return "Invalid content type", 400

if WEBHOOK_URL:
    bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)

