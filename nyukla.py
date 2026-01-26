import telebot
from telebot import types
import yt_dlp
import os
import time
import sqlite3
import threading
from flask import Flask
import shutil

# --- SOZLAMALAR ---
BOT_TOKEN = '8510711803:AAE3klDsgCCgQTaB0oY8IDL4u-GmK9D2yAc' # @BotFather dan olingan token
ADMIN_ID = 8553997595 # O'zingizning Telegram ID raqamingiz
CHANNEL_ID = '@aclubnc' # Kanal useri (@ bilan) yoki ID si (-100...)
CHANNEL_URL = 'https://t.me/aclubnc' # Kanal havolasi

WEBHOOK_URL = 'https://nyukla.onrender.com'

bot = telebot.TeleBot(BOT_TOKEN)

# --- SERVER (RENDER UCHUN) ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot ishlmoqda!"

def run_server():
    app.run(host="0.0.0.0", port=8080)

# --- BAZA BILAN ISHLASH (ADMIN PANEL UCHUN) ---
def init_db():
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY
        )
    ''')
    conn.commit()
    conn.close()

def add_user(user_id):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT INTO users (user_id) VALUES (?)', (user_id,))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()

def get_users_count():
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM users')
    count = cursor.fetchone()[0]
    conn.close()
    return count

def get_all_users():
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM users')
    users = cursor.fetchall()
    conn.close()
    return [user[0] for user in users]

# --- MAJBURIY OBUNA TEKSHIRUVI ---
def check_subscription(user_id):
    try:
        member = bot.get_chat_member(CHANNEL_ID, user_id)
        if member.status in ['creator', 'administrator', 'member']:
            return True
        return False
    except Exception as e:
        # Agar bot kanal admini bo'lmasa yoki xato bo'lsa
        return False

def subscription_markup():
    markup = types.InlineKeyboardMarkup()
    btn1 = types.InlineKeyboardButton("➕ Kanalga obuna bo'lish", url=CHANNEL_URL)
    btn2 = types.InlineKeyboardButton("✅ Tekshirish", callback_data="check_sub")
    markup.add(btn1)
    markup.add(btn2)
    return markup

# --- YORDAMCHI FUNKSIYALAR ---
def download_video(url):
    ydl_opts = {
        'format': 'best[ext=mp4]',
        'outtmpl': 'downloads/%(id)s.%(ext)s',
        'quiet': True,
        'max_filesize': 50 * 1024 * 1024  # 50MB limit
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return ydl.prepare_filename(info), info.get('title', 'Video')

def search_music_list(query):
    ydl_opts = {
        'format': 'bestaudio/best',
        'noplaylist': True,
        'quiet': True,
        'default_search': 'ytsearch10', # Top 10 ta qidiruv
        'extract_flat': True, # Faqat ma'lumotni olish, yuklamaslik
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(query, download=False)
        return info['entries']

def download_audio_by_id(video_id):
    url = f"https://www.youtube.com/watch?v={video_id}"
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': 'downloads/%(title)s.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'quiet': True,
        'max_filesize': 50 * 1024 * 1024
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        final_filename = filename.rsplit('.', 1)[0] + '.mp3'
        return final_filename, info.get('title', 'Music')

# --- BOT HANDLERS ---

@bot.message_handler(commands=['start'])
def send_welcome(message):
    add_user(message.from_user.id)
    if check_subscription(message.from_user.id):
        bot.send_message(message.chat.id, "👋 Assalomu alaykum! Men media yuklovchi va musiqa qidiruvchi botman.\n\n"
                                          "🔹 Video yuklash uchun link yuboring.\n"
                                          "🔹 Musiqa uchun qo'shiq nomini yozing.\n"
                                          "🔹 Buyruqlar: /help, /about")
    else:
        bot.send_message(message.chat.id, "⚠️ Bot ishlashi uchun kanalimizga obuna bo'ling!", reply_markup=subscription_markup())

@bot.callback_query_handler(func=lambda call: call.data == "check_sub")
def callback_check_sub(call):
    if check_subscription(call.from_user.id):
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.answer_callback_query(call.id, "Obuna tasdiqlandi! ✅")
        bot.send_message(call.message.chat.id, "Xush kelibsiz! Link yuboring yoki musiqa nomini yozing.")
    else:
        bot.answer_callback_query(call.id, "Siz hali obuna bo'lmadingiz! ❌", show_alert=True)

@bot.message_handler(commands=['help'])
def send_help(message):
    bot.send_message(message.chat.id, "🤖 **Bot bo'yicha yordam:**\n\n"
                                      "1. Instagram, TikTok, YouTube, Pinterest linkini yuborsangiz videoni yuklab beraman.\n"
                                      "2. Musiqa nomini yozsangiz (masalan: 'Konsta') 10 ta variant chiqaraman.\n"
                                      "3. /admin - Admin paneli (faqat admin uchun).", parse_mode="Markdown")

@bot.message_handler(commands=['about'])
def send_about(message):
    bot.send_message(message.chat.id, "👨‍💻 **Dasturchi:** @SizningUseringiz\n"
                                      "📅 **Versiya:** 1.0\n"
                                      "Ushbu bot ochiq kodli loyiha asosida yaratildi.")

# --- ADMIN PANEL ---
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.from_user.id == ADMIN_ID:
        count = get_users_count()
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add("📊 Statistika", "✉️ Xabar yuborish")
        markup.add("🔙 Chiqish")
        bot.send_message(message.chat.id, f"👑 Admin Panelga xush kelibsiz.\n👥 Foydalanuvchilar: {count}", reply_markup=markup)
    else:
        pass # Admin bo'lmasa javob bermaymiz

@bot.message_handler(func=lambda message: message.text == "📊 Statistika" and message.from_user.id == ADMIN_ID)
def admin_stats(message):
    count = get_users_count()
    bot.send_message(message.chat.id, f"📊 Bot statistikasi:\n\n👤 Jami foydalanuvchilar: {count} ta")

@bot.message_handler(func=lambda message: message.text == "✉️ Xabar yuborish" and message.from_user.id == ADMIN_ID)
def admin_broadcast_step1(message):
    msg = bot.send_message(message.chat.id, "Foydalanuvchilarga yuboriladigan xabarni kiriting (yoki /cancel):")
    bot.register_next_step_handler(msg, admin_broadcast_step2)

def admin_broadcast_step2(message):
    if message.text == '/cancel':
        bot.send_message(message.chat.id, "Bekor qilindi.")
        return
    
    users = get_all_users()
    sent_count = 0
    bot.send_message(message.chat.id, "Xabar yuborish boshlandi... ⏳")
    
    for user_id in users:
        try:
            bot.copy_message(user_id, message.chat.id, message.message_id)
            sent_count += 1
            time.sleep(0.05) # Spamdan saqlanish uchun
        except:
            pass
            
    bot.send_message(message.chat.id, f"✅ Xabar {sent_count} ta foydalanuvchiga yuborildi.")

@bot.message_handler(func=lambda message: message.text == "🔙 Chiqish" and message.from_user.id == ADMIN_ID)
def admin_exit(message):
    bot.send_message(message.chat.id, "Admin paneldan chiqildi.", reply_markup=types.ReplyKeyboardRemove())

# --- MATN (MUSIQA QIDIRISH) ---
@bot.message_handler(func=lambda message: not message.text.startswith('/') and not message.text.startswith('http'))
def search_music_handler(message):
    if not check_subscription(message.from_user.id):
        bot.send_message(message.chat.id, "⚠️ Botdan foydalanish uchun kanalga obuna bo'ling!", reply_markup=subscription_markup())
        return

    msg = bot.send_message(message.chat.id, "🔎 Qidirilmoqda...")
    try:
        results = search_music_list(message.text)
        markup = types.InlineKeyboardMarkup()
        
        for i, entry in enumerate(results):
            title = entry.get('title', 'Noma\'lum')[:30] # Uzun nomlarni qisqartirish
            vid_id = entry.get('id')
            markup.add(types.InlineKeyboardButton(f"{i+1}. {title}", callback_data=f"dl_music:{vid_id}"))
            
        bot.edit_message_text(f"🎵 '{message.text}' bo'yicha natijalar:", chat_id=message.chat.id, message_id=msg.message_id, reply_markup=markup)
    except Exception as e:
        bot.edit_message_text(f"Xatolik yuz berdi: {e}", chat_id=message.chat.id, message_id=msg.message_id)

# --- MUSIQA YUKLASH (CALLBACK) ---
@bot.callback_query_handler(func=lambda call: call.data.startswith('dl_music:'))
def callback_download_music(call):
    if not check_subscription(call.from_user.id):
        bot.answer_callback_query(call.id, "Avval kanalga obuna bo'ling!", show_alert=True)
        return

    vid_id = call.data.split(':')[1]
    bot.answer_callback_query(call.id, "Yuklanmoqda... ⏳")
    bot.send_message(call.message.chat.id, "🎧 Musiqa yuklanmoqda, kuting...")
    
    try:
        file_path, title = download_audio_by_id(vid_id)
        with open(file_path, 'rb') as audio:
            bot.send_audio(call.message.chat.id, audio, caption=f"🎵 {title}\n🤖 @{bot.get_me().username}")
        os.remove(file_path) # Faylni o'chirish
    except Exception as e:
        bot.send_message(call.message.chat.id, "Musiqani yuklashda xatolik bo'ldi.")

# --- LINK (VIDEO YUKLASH) ---
@bot.message_handler(func=lambda message: message.text and (message.text.startswith('http') or 'instagram.com' in message.text or 'tiktok.com' in message.text or 'youtube.com' in message.text))
def download_video_handler(message):
    if not check_subscription(message.from_user.id):
        bot.send_message(message.chat.id, "⚠️ Botdan foydalanish uchun kanalga obuna bo'ling!", reply_markup=subscription_markup())
        return

    url = message.text
    msg = bot.send_message(message.chat.id, "📥 Video yuklanmoqda... Kuting.")
    
    try:
        file_path, title = download_video(url)
        
        # Tugma qo'shish (Videodagi musiqani topish)
        markup = types.InlineKeyboardMarkup()
        # Videoni nomini qidiruvga beramiz
        search_query = title[:20] # Juda uzun bo'lmasligi uchun
        markup.add(types.InlineKeyboardButton("🎵 Videodagi musiqani topish/yuklash", callback_data=f"find_music_from_vid:{search_query}"))

        with open(file_path, 'rb') as video:
            bot.send_video(message.chat.id, video, caption=f"🎬 {title}\n🤖 @{bot.get_me().username}", reply_markup=markup)
        
        bot.delete_message(message.chat.id, msg.message_id)
        os.remove(file_path)
    except Exception as e:
        bot.edit_message_text(f"Videoni yuklab bo'lmadi. Havola to'g'riligini tekshiring.\nXato: {str(e)[:50]}", chat_id=message.chat.id, message_id=msg.message_id)

# --- VIDEO OSTIDAGI TUGMA BOSILGANDA ---
@bot.callback_query_handler(func=lambda call: call.data.startswith('find_music_from_vid:'))
def callback_find_music_from_vid(call):
    if not check_subscription(call.from_user.id):
        bot.answer_callback_query(call.id, "Obuna bo'ling!", show_alert=True)
        return

    query = call.data.split(':')[1]
    bot.answer_callback_query(call.id, "Qidirilmoqda...")
    
    # Huddi musiqa qidirgandek ishlaydi
    try:
        results = search_music_list(query)
        markup = types.InlineKeyboardMarkup()
        for i, entry in enumerate(results):
            title = entry.get('title', 'Noma\'lum')[:30]
            vid_id = entry.get('id')
            markup.add(types.InlineKeyboardButton(f"{i+1}. {title}", callback_data=f"dl_music:{vid_id}"))
        
        bot.send_message(call.message.chat.id, f"🎵 Video nomi bo'yicha topilgan musiqalar ({query}):", reply_markup=markup)
    except:
        bot.send_message(call.message.chat.id, "Musiqa topilmadi.")

# --- WEBHOOK QISMI ---
@app.route('/' + BOT_TOKEN, methods=['POST'])
def getMessage():
    json_string = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return "!", 200

@app.route("/")
def webhook():
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL + '/' + BOT_TOKEN)
    return "Webhook o'rnatildi va bot ishlamoqda!", 200

# --- BAZA VA YUKLASH FUNKSIYALARI (O'ZGARISHSIZ QOLADI) ---
# [Yuqoridagi javobdagi init_db, add_user, download_video, download_audio va barcha @bot.message_handler qismlarini aynan shu yerga qo'ying]

# --- ASOSIY QISM ---
if __name__ == "__main__":
    init_db()
    if not os.path.exists('downloads'):
        os.makedirs('downloads')
    
    # Render avtomatik port tayinlaydi (odatda 10000 yoki 8080)
    port = int(os.environ.get('PORT', 8080))
    app.run(host="0.0.0.0", port=port)