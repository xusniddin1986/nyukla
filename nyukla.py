from flask import Flask, request
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from     import YoutubeDL
import os
import uuid

# --- Flask App ---
app = Flask(__name__)

# --- Token ---
BOT_TOKEN = "8679344041:AAGVo6gwxoyjWOPCSb3ezdtfgwJ7PkhhQaM"
bot = telebot.TeleBot(BOT_TOKEN)

CHANNEL_USERNAME = "@aclubnc"
CAPTION_TEXT = (
    "📥 @NYuklaBot orqali yuklab olindi"
)

# ---------------- ADMIN ID VA STATISTIKA -----------------
ADMIN_ID = 5767267885
users = set()
total_downloads = 0
today_downloads = 0

# ---------------- HOME PAGE -----------------
@app.route("/")
def home():
    return "Bot ishlayapti! 🔥"

# ---------------- TELEGRAM WEBHOOK ENDPOINT -----------------
@app.route("/telegram_webhook", methods=["POST"])
def telegram_webhook():
    json_str = request.get_data().decode("utf-8")
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "ok", 200

# ---------------- /start handler -----------------
@bot.message_handler(commands=["start"])
def start(message):
    user_id = message.from_user.id
    try:
        member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        if member.status in ["creator", "administrator", "member"]:
            bot.send_message(
                message.chat.id,
                "Siz kanalga obuna bo‘ldingiz ✅\n\nInstagramdan video linkini yuboring 🚀",
            )
            return
        else:
            raise Exception()
    except:
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton(
                "📢 Kanalga obuna bo‘ling",
                url=f"https://t.me/{CHANNEL_USERNAME.strip('@')}",
            )
        )
        markup.add(InlineKeyboardButton("✅ Obuna bo‘ldim", callback_data="subscribed"))
        bot.send_message(
            message.chat.id,
            f"❗ Botdan foydalanish uchun kanalga obuna bo‘ling: {CHANNEL_USERNAME}",
            reply_markup=markup,
        )

# ---------------- Callback handler -----------------
@bot.callback_query_handler(func=lambda call: True)
def callback_inline(call: CallbackQuery):
    if call.data == "subscribed":
        try:
            member = bot.get_chat_member(CHANNEL_USERNAME, call.from_user.id)
            if member.status in ["creator", "administrator", "member"]:
                bot.answer_callback_query(call.id, "Obuna tasdiqlandi! ✅")
                bot.send_message(
                    call.message.chat.id,
                    "Siz kanalga obuna bo‘ldingiz! ✅\n\nInstagramdan link yuboring 🚀",
                )
            else:
                bot.answer_callback_query(
                    call.id, "❌ Hali obuna bo‘lmadiz!", show_alert=True
                )
        except:
            bot.answer_callback_query(
                call.id, "❌ Xatolik! Qayta urinib ko‘ring.", show_alert=True
            )

# ---------------- /help handler -----------------
@bot.message_handler(commands=["help"])
def help_command(message):
    help_text = (
        "🛠️ Bot yordamchisi\n\n"
        "/start - Botni ishga tushurish\n"
        "/help - Yordam ma'lumotlari\n"
        "/about - Bot haqida ma'lumot\n"
        "/admin - Admin paneli (faqat admin)\n\n"
        "Instagramdan video linkini yuborib videoni yuklab olishingiz mumkin 🚀\n"
        "Bog‘lanish: @xamidovcore"
    )
    bot.send_message(message.chat.id, help_text)

# ---------------- /about handler (TO‘G‘RILANGAN) -----------------
@bot.message_handler(commands=["about"])
def about_command(message):
    about_text = (
        "🤖 NYuklaBot\n\n"
        "🔥 Assalomu alaykum! @NYuklaBot ga xush kelibsiz.\n\n"
        "Bot orqali siz quyidagilarni yuklab olishingiz mumkin:\n"
        "• Instagram postlar\n"
        "• Reels videolar\n"
        "• Stories (audio bilan)\n\n"
        "📢 Telegram kanalimiz: @aclubnc\n"
        "👨‍💻 Bot-Yaratuvchisi: Nabiyulloh.X\n"
    )
    bot.send_message(message.chat.id, about_text)

# ---------------- ADMIN PANEL HANDLER (TO‘G‘RILANGAN) -----------------
@bot.message_handler(commands=["admin", "panel"])
def admin_panel(message):
    if message.from_user.id != ADMIN_ID:
        return bot.send_message(message.chat.id, "❌ Siz admin emassiz!")

    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("📊 Umumiy statistika", callback_data="total_stats"))
    kb.add(InlineKeyboardButton("📅 Bugungi statistika", callback_data="today_stats"))
    kb.add(InlineKeyboardButton("🏆 TOP foydalanuvchilar", callback_data="top_users"))
    kb.add(InlineKeyboardButton("👤 Foydalanuvchilar ro‘yxati", callback_data="user_list"))
    
    bot.send_message(message.chat.id, "🛠 Admin Panel", reply_markup=kb)

# ---------------- CALLBACK FOR ADMIN PANEL (TO‘G‘RILANGAN) -----------------
@bot.callback_query_handler(func=lambda call: call.data in ["total_stats", "today_stats", "top_users", "user_list"])
def admin_stats(call):
    if call.from_user.id != ADMIN_ID:
        return bot.answer_callback_query(call.id, "⛔ Ruxsat yo‘q!", show_alert=True)

    if call.data == "total_stats":
        text = (
            "📊 Umumiy statistika\n\n"
            f"👤 Foydalanuvchilar: {len(users)} ta\n"
            f"📥 Yuklangan videolar: {total_downloads} ta"
        )
        bot.send_message(call.message.chat.id, text)

    elif call.data == "today_stats":
        text = (
            "📅 Bugungi statistika\n\n"
            f"📥 Bugun yuklangan videolar: {today_downloads} ta"
        )
        bot.send_message(call.message.chat.id, text)

    elif call.data == "top_users":
        bot.send_message(
            call.message.chat.id,
            "🏆 TOP foydalanuvchilar\n\n"
            "Hozircha mavjud emas 😅"
        )

    elif call.data == "user_list":
        if len(users) == 0:
            bot.send_message(call.message.chat.id, "👤 Foydalanuvchilar yo‘q.")
        else:
            text = "👤 Foydalanuvchilar ro‘yxati:\n\n"
            for uid in users:
                text += f"- {uid}\n"
            bot.send_message(call.message.chat.id, text)

# ---------------- VIDEO DOWNLOAD HANDLER -----------------
@bot.message_handler(func=lambda m: True)
def download_instagram_video(message):
    global total_downloads, today_downloads
    users.add(message.from_user.id)

    url = message.text.strip()
    if "instagram.com" not in url:
        bot.reply_to(message, "❌ Instagramdan video linkini yuboring!")
        return

    loading_msg = bot.send_message(message.chat.id, "⏳ Video yuklanmoqda...")
    filename = f"{uuid.uuid4()}.mp4"
    ydl_opts = {"format": "mp4", "outtmpl": filename, "quiet": True}

    try:
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        bot.delete_message(message.chat.id, loading_msg.message_id)

        with open(filename, "rb") as video:
            bot.send_video(message.chat.id, video, caption=CAPTION_TEXT)

        total_downloads += 1
        today_downloads += 1
        os.remove(filename)

    except Exception as e:
        bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=loading_msg.message_id,
            text=f"❌ Xatolik yoki noto‘g‘ri link!\n{e}",
        )

# ---------------- WEBHOOK -----------------
WEBHOOK_URL = "https://nyukla.onrender.com/telegram_webhook"
bot.remove_webhook()
bot.set_webhook(url=WEBHOOK_URL)

# ---------------- RUN FLASK -----------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
