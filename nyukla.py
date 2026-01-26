import telebot
from telebot import types
import yt_dlp
import os
import time
import sqlite3
from flask import Flask, request
import threading

# ==========================================
#              SOZLAMALAR
# ==========================================
BOT_TOKEN = '8510711803:AAE3klDsgCCgQTaB0oY8IDL4u-GmK9D2yAc'  
ADMIN_ID = 8553997595                  # O'zingizning ID raqamingiz (raqamda)
CHANNEL_ID = '@aclubnc'    # Kanal useri
CHANNEL_URL = 'https://t.me/aclubnc' 
WEBHOOK_URL = 'https://nyukla.onrender.com' # Render havolasi

# ==========================================
#              INITIALIZATION
# ==========================================
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# Papka yaratish
if not os.path.exists('downloads'):
    os.makedirs('downloads')

# ==========================================
#           BAZA BILAN ISHLASH
# ==========================================
def init_db():
    with sqlite3.connect('users.db') as conn:
        cursor = conn.cursor()
        cursor.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)')
        conn.commit()

def add_user(user_id):
    try:
        with sqlite3.connect('users.db') as conn:
            cursor = conn.cursor()
            cursor.execute('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (user_id,))
            conn.commit()
    except:
        pass

def get_users_count():
    with sqlite3.connect('users.db') as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM users')
        return cursor.fetchone()[0]

def get_all_users():
    with sqlite3.connect('users.db') as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT user_id FROM users')
        return [row[0] for row in cursor.fetchall()]

# ==========================================
#         MAJBURIY OBUNA TIZIMI
# ==========================================
def check_sub(user_id):
    try:
        member = bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ['creator', 'administrator', 'member']
    except:
        return False # Bot admin emas yoki xatolik

def sub_markup():
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("➕ Kanalga a'zo bo'lish", url=CHANNEL_URL))
    markup.add(types.InlineKeyboardButton("✅ Tasdiqlash", callback_data="check_subscription"))
    return markup

# ==========================================
#      YUKLASH VA QIDIRUV (ENGINE)
# ==========================================
def search_music(query):
    # Youtube'dan 10 ta musiqa qidiradi
    ydl_opts = {
        'format': 'bestaudio/best',
        'noplaylist': True,
        'quiet': True,
        'default_search': 'ytsearch10',
        'extract_flat': True, # Faqat ma'lumot oladi, yuklamaydi
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(query, download=False)
        return info.get('entries', [])

def download_audio(video_id):
    url = f"https://www.youtube.com/watch?v={video_id}"
    # Renderda FFmpeg muammosi bo'lmasligi uchun m4a format
    ydl_opts = {
        'format': 'bestaudio[ext=m4a]/bestaudio',
        'outtmpl': 'downloads/%(title)s.%(ext)s',
        'quiet': True,
        'max_filesize': 50 * 1024 * 1024
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return ydl.prepare_filename(info), info.get('title', 'Music')

def download_video_func(url):
    ydl_opts = {
        'format': 'best[ext=mp4]', # Eng yaxshi mp4
        'outtmpl': 'downloads/%(id)s.%(ext)s',
        'quiet': True,
        'max_filesize': 50 * 1024 * 1024
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return ydl.prepare_filename(info), info.get('title', 'Video')

# ==========================================
#               BOT HANDLERS
# ==========================================

# 1. /start komandasi
@bot.message_handler(commands=['start'])
def welcome(message):
    add_user(message.chat.id)
    if check_sub(message.chat.id):
        bot.send_message(message.chat.id, 
                         "👋 <b>Assalomu alaykum!</b>\n\n"
                         "📥 Men Instagram, TikTok, YouTube, Pinterest dan video yuklayman.\n"
                         "🔎 Yoki musiqa nomini yozing, men topib beraman.", 
                         parse_mode='HTML')
    else:
        bot.send_message(message.chat.id, "⚠️ <b>Botdan foydalanish uchun kanalga a'zo bo'ling!</b>", 
                         parse_mode='HTML', reply_markup=sub_markup())

# 2. Obunani tekshirish tugmasi
@bot.callback_query_handler(func=lambda call: call.data == "check_subscription")
def check_sub_callback(call):
    if check_sub(call.message.chat.id):
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.answer_callback_query(call.id, "✅ Obuna tasdiqlandi!")
        bot.send_message(call.message.chat.id, "Marhamat, link yuboring yoki musiqa nomini yozing.")
    else:
        bot.answer_callback_query(call.id, "❌ Siz hali a'zo bo'lmadingiz!", show_alert=True)

# 3. /help va /about
@bot.message_handler(commands=['help'])
def help_cmd(message):
    bot.send_message(message.chat.id, "Video link yuboring (Insta/TikTok/YouTube) yoki musiqa nomini yozing.")

@bot.message_handler(commands=['about'])
def about_cmd(message):
    bot.send_message(message.chat.id, "Versiya: 2.0. \nDasturchi: @Useringiz")

# 4. ADMIN PANEL (/admin)
@bot.message_handler(commands=['admin'])
def admin_menu(message):
    if message.chat.id == ADMIN_ID:
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        markup.add("📊 Statistika", "📤 Xabar yuborish")
        markup.add("🔙 Chiqish")
        bot.send_message(message.chat.id, "👑 Admin panelga xush kelibsiz", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "📊 Statistika" and m.chat.id == ADMIN_ID)
def stats(message):
    cnt = get_users_count()
    bot.send_message(message.chat.id, f"👥 Jami foydalanuvchilar: {cnt} ta")

@bot.message_handler(func=lambda m: m.text == "📤 Xabar yuborish" and m.chat.id == ADMIN_ID)
def broadcast_start(message):
    msg = bot.send_message(message.chat.id, "Xabarni yuboring (Rasm, matn, video...):")
    bot.register_next_step_handler(msg, broadcast_process)

def broadcast_process(message):
    if message.text == "🔙 Chiqish":
        bot.send_message(message.chat.id, "Bekor qilindi.")
        return
    
    users = get_all_users()
    bot.send_message(message.chat.id, f"⏳ Xabar {len(users)} kishiga yuborilmoqda...")
    count = 0
    for uid in users:
        try:
            bot.copy_message(uid, message.chat.id, message.message_id)
            count += 1
            time.sleep(0.05)
        except: pass
    bot.send_message(message.chat.id, f"✅ Xabar {count} kishiga yetib bordi.")

@bot.message_handler(func=lambda m: m.text == "🔙 Chiqish" and m.chat.id == ADMIN_ID)
def back_admin(message):
    bot.send_message(message.chat.id, "Admin panel yopildi.", reply_markup=types.ReplyKeyboardRemove())

# 5. MUSIQA QIDIRISH (TEXT orqali)
@bot.message_handler(func=lambda m: not m.text.startswith('/') and not m.text.startswith('http'))
def text_search(message):
    if not check_sub(message.chat.id):
        bot.send_message(message.chat.id, "⚠️ Avval kanalga a'zo bo'ling!", reply_markup=sub_markup())
        return

    msg = bot.send_message(message.chat.id, "🔎 <b>Musiqa qidirilmoqda...</b>", parse_mode='HTML')
    try:
        results = search_music(message.text)
        if not results:
            bot.edit_message_text("❌ Hech narsa topilmadi.", message.chat.id, msg.message_id)
            return

        # Ro'yxat matni va tugmalar
        text_response = f"🎵 <b>'{message.text}' bo'yicha natijalar:</b>\n\n"
        markup = types.InlineKeyboardMarkup(row_width=2) # 2 qator qilib chiroyli chiqarish
        
        for i, item in enumerate(results):
            title = item.get('title', 'Noma\'lum')
            # Matnga qo'shish
            text_response += f"{i+1}. {title}\n"
            # Tugma qo'shish (callbackda ID ketadi)
            vid_id = item['id']
            markup.add(types.InlineKeyboardButton(f"{i+1}. 📥 Yuklash", callback_data=f"dl:{vid_id}"))

        bot.edit_message_text(text_response, message.chat.id, msg.message_id, reply_markup=markup, parse_mode='HTML')
        
    except Exception as e:
        bot.edit_message_text(f"Xatolik: {e}", message.chat.id, msg.message_id)

# 6. VIDEO YUKLASH HANDLER
@bot.message_handler(func=lambda m: m.text and (m.text.startswith('http') or 'instagram' in m.text or 'tiktok' in m.text))
def video_dl(message):
    if not check_sub(message.chat.id):
        bot.send_message(message.chat.id, "⚠️ Avval kanalga a'zo bo'ling!", reply_markup=sub_markup())
        return

    url = message.text
    msg = bot.send_message(message.chat.id, "📥 <b>Video yuklanmoqda...</b>", parse_mode='HTML')

    try:
        path, title = download_video_func(url)
        
        # Video tagiga musiqa qidirish tugmasi
        markup = types.InlineKeyboardMarkup()
        # Qidiruv so'zi sifatida video nomini olamiz (faqat birinchi 30 harfi)
        search_query = title[:30] 
        markup.add(types.InlineKeyboardButton("🎹 Musiqasini topish", callback_data=f"find_music:{search_query}"))

        with open(path, 'rb') as video:
            bot.send_video(message.chat.id, video, caption=f"🎬 {title}", reply_markup=markup)
        
        bot.delete_message(message.chat.id, msg.message_id)
        os.remove(path)
    except Exception as e:
        bot.edit_message_text(f"❌ Yuklab bo'lmadi yoki havola xato.\nSabab: {e}", message.chat.id, msg.message_id)

# 7. CALLBACKS (Musiqa yuklash va Video ichidan qidirish)

# Video tagidagi "Musiqasini topish" tugmasi bosilganda
@bot.callback_query_handler(func=lambda call: call.data.startswith('find_music:'))
def find_music_callback(call):
    if not check_sub(call.message.chat.id):
        bot.answer_callback_query(call.id, "Kanalga a'zo bo'ling!", show_alert=True)
        return

    query = call.data.split(':', 1)[1] # "find_music:Title" dan Title ni ajratib olish
    bot.answer_callback_query(call.id, "🔍 Qidirilmoqda...")
    
    # Text search funksiyasini chaqiramiz, faqat message obyektini sun'iy yasaymiz
    # Yoki kodni qaytaramiz:
    try:
        results = search_music(query)
        text_response = f"🎹 <b>Videodan olingan nom bo'yicha ({query}):</b>\n\n"
        markup = types.InlineKeyboardMarkup(row_width=1)
        
        for i, item in enumerate(results):
            title = item.get('title', 'Noma\'lum')
            text_response += f"{i+1}. {title}\n"
            markup.add(types.InlineKeyboardButton(f"{i+1}. {title}", callback_data=f"dl:{item['id']}"))
            
        bot.send_message(call.message.chat.id, text_response, reply_markup=markup, parse_mode='HTML')
    except:
        bot.send_message(call.message.chat.id, "Musiqa topilmadi.")

# Musiqa yuklash tugmasi bosilganda (1-10 ro'yxatdan)
@bot.callback_query_handler(func=lambda call: call.data.startswith('dl:'))
def download_music_callback(call):
    if not check_sub(call.message.chat.id):
        bot.answer_callback_query(call.id, "Kanalga a'zo bo'ling!", show_alert=True)
        return

    vid_id = call.data.split(':')[1]
    bot.answer_callback_query(call.id, "Yuklanmoqda... ⏳")
    bot.send_message(call.message.chat.id, "🎧 Musiqa fayli tayyorlanmoqda...")

    try:
        path, title = download_audio(vid_id)
        with open(path, 'rb') as audio:
            bot.send_audio(call.message.chat.id, audio, caption=f"🎵 {title}\n🤖 @{bot.get_me().username}")
        os.remove(path)
    except Exception as e:
        bot.send_message(call.message.chat.id, "Musiqa yuklashda xatolik.")

# ==========================================
#              WEBHOOK SERVER
# ==========================================
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
    return "Webhook ishladi!", 200

if __name__ == "__main__":
    init_db()
    # Render PORT ni oladi
    port = int(os.environ.get('PORT', 8080))
    app.run(host="0.0.0.0", port=port)