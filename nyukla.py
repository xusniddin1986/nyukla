import telebot
from telebot import types
import yt_dlp
import os
import time
import sqlite3
from flask import Flask, request

# ==========================================
#              SOZLAMALAR
# ==========================================
BOT_TOKEN = '8510711803:AAE3klDsgCCgQTaB0oY8IDL4u-GmK9D2yAc' 
ADMIN_ID = 8553997595 
CHANNEL_ID = '@aclubnc' 
CHANNEL_URL = 'https://t.me/aclubnc' 
WEBHOOK_URL = 'https://nyukla.onrender.com'

bot = telebot.TeleBot(BOT_TOKEN, parse_mode='HTML')
app = Flask(__name__)

# Fayllar uchun papka
if not os.path.exists('downloads'):
    os.makedirs('downloads')

# ==========================================
#           BAZA FUNKSIYALARI
# ==========================================
def init_db():
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, join_date TEXT)')
    conn.commit()
    conn.close()

def add_user(user_id):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    date = time.strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute('INSERT OR IGNORE INTO users (user_id, join_date) VALUES (?, ?)', (user_id, date))
    conn.commit()
    conn.close()

def get_stats():
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM users')
    count = cursor.fetchone()[0]
    conn.close()
    return count

# ==========================================
#         MAJBURIY OBUNA TEKSHIRUVCHI
# ==========================================
def is_subscribed(user_id):
    try:
        status = bot.get_chat_member(CHANNEL_ID, user_id).status
        if status in ['creator', 'administrator', 'member']:
            return True
        return False
    except:
        return False

def sub_keyboard():
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("➕ Kanalga obuna bo'lish", url=CHANNEL_URL))
    markup.add(types.InlineKeyboardButton("✅ Tekshirish", callback_data="recheck"))
    return markup

# ==========================================
#         YUKLASH VA QIDIRUV ENGINE
# ==========================================
def get_video_info(url):
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'format': 'best',
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download=False)

def download_media(url, mode='video'):
    ext = 'mp4' if mode == 'video' else 'm4a'
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]' if mode == 'video' else 'bestaudio[ext=m4a]/best',
        'outtmpl': 'downloads/%(id)s.%(ext)s',
        'quiet': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return ydl.prepare_filename(info), info.get('title', 'Media')

# ==========================================
#               ADMIN PANEL
# ==========================================
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.from_user.id == ADMIN_ID:
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add("📊 Statistika", "✉️ Xabar yuborish")
        markup.add("👤 Foydalanuvchi ID", "🔙 Chiqish")
        bot.send_message(message.chat.id, "<b>👑 Admin Panel</b>", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "📊 Statistika" and m.from_user.id == ADMIN_ID)
def admin_stats(message):
    count = get_stats()
    bot.send_message(message.chat.id, f"📊 Bot a'zolari: <b>{count} ta</b>")

@bot.message_handler(func=lambda m: m.text == "👤 Foydalanuvchi ID" and m.from_user.id == ADMIN_ID)
def admin_id(message):
    bot.send_message(message.chat.id, f"Sizning ID: <code>{message.from_user.id}</code>")

@bot.message_handler(func=lambda m: m.text == "✉️ Xabar yuborish" and m.from_user.id == ADMIN_ID)
def admin_broadcast(message):
    msg = bot.send_message(message.chat.id, "Yubormoqchi bo'lgan xabaringizni yozing (yoki rasm yuboring):")
    bot.register_next_step_handler(msg, send_broadcast)

def send_broadcast(message):
    conn = sqlite3.connect('users.db')
    users = conn.cursor().execute('SELECT user_id FROM users').fetchall()
    conn.close()
    
    success = 0
    for u in users:
        try:
            bot.copy_message(u[0], message.chat.id, message.message_id)
            success += 1
            time.sleep(0.05)
        except: continue
    bot.send_message(message.chat.id, f"✅ Xabar {success} kishiga yuborildi.")

# ==========================================
#             ASOSIY LOGIKA
# ==========================================
@bot.message_handler(commands=['start', 'help', 'about'])
def commands(message):
    add_user(message.from_user.id)
    if message.text == '/start':
        if not is_subscribed(message.from_user.id):
            return bot.send_message(message.chat.id, "<b>Bot ishlashi uchun kanalga obuna bo'ling!</b>", reply_markup=sub_keyboard())
        bot.send_message(message.chat.id, "👋 <b>Xush kelibsiz!</b>\n\nLink yuboring yoki musiqa nomini yozing.")
    elif message.text == '/help':
        bot.send_message(message.chat.id, "Instagram, YouTube, TikTok va Pinterestdan video yuklash uchun link yuboring.")
    elif message.text == '/about':
        bot.send_message(message.chat.id, "Ushbu bot ijtimoiy tarmoqlardan video yuklash uchun yaratildi.")

@bot.callback_query_handler(func=lambda call: call.data == "recheck")
def recheck(call):
    if is_subscribed(call.from_user.id):
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.send_message(call.message.chat.id, "✅ Rahmat! Endi botdan foydalanishingiz mumkin.")
    else:
        bot.answer_callback_query(call.id, "❌ Hali obuna bo'lmagansiz!", show_alert=True)

# 1-10 RO'YXAT VA MUSIQA QIDIRISH
@bot.message_handler(func=lambda m: not m.text.startswith('http') and not m.text.startswith('/'))
def search_music_list(message):
    if not is_subscribed(message.from_user.id):
        return bot.send_message(message.chat.id, "Obuna bo'ling!", reply_markup=sub_keyboard())
    
    m = bot.send_message(message.chat.id, "🔎 Qidirilmoqda...")
    try:
        ydl_opts = {'default_search': 'ytsearch10', 'quiet': True, 'extract_flat': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            results = ydl.extract_info(message.text, download=False).get('entries', [])
        
        if not results:
            return bot.edit_message_text("❌ Musiqa topilmadi.", message.chat.id, m.message_id)
        
        res_text = f"🎵 <b>'{message.text}' bo'yicha topilganlar:</b>\n\n"
        markup = types.InlineKeyboardMarkup()
        for i, item in enumerate(results):
            res_text += f"{i+1}. {item['title'][:50]}...\n"
            markup.add(types.InlineKeyboardButton(f"{i+1}", callback_data=f"ms:{item['id']}"))
        
        bot.edit_message_text(res_text, message.chat.id, m.message_id, reply_markup=markup)
    except:
        bot.edit_message_text("❌ Qidiruvda xatolik.", message.chat.id, m.message_id)

# VIDEO YUKLASH
@bot.message_handler(func=lambda m: m.text.startswith('http'))
def handle_video(message):
    if not is_subscribed(message.from_user.id):
        return bot.send_message(message.chat.id, "Obuna bo'ling!", reply_markup=sub_keyboard())
    
    m = bot.send_message(message.chat.id, "⏳ Video tahlil qilinmoqda...")
    try:
        path, title = download_media(message.text, mode='video')
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🎵 Musiqasini yuklash", callback_data=f"get_m:{title[:20]}"))
        
        with open(path, 'rb') as v:
            bot.send_video(message.chat.id, v, caption=f"🎬 <b>{title}</b>", reply_markup=markup)
        
        os.remove(path)
        bot.delete_message(message.chat.id, m.message_id)
    except Exception as e:
        bot.edit_message_text(f"❌ Xato: Videoni yuklab bo'lmadi. {str(e)[:50]}", message.chat.id, m.message_id)

# CALLBACKLAR
@bot.callback_query_handler(func=lambda call: True)
def calls(call):
    if call.data.startswith('ms:'): # Ro'yxatdan musiqa tanlanganda
        vid_id = call.data.split(':')[1]
        bot.answer_callback_query(call.id, "Yuklanmoqda...")
        try:
            path, title = download_media(f"https://www.youtube.com/watch?v={vid_id}", mode='audio')
            with open(path, 'rb') as a:
                bot.send_audio(call.message.chat.id, a, caption=f"🎵 {title}")
            os.remove(path)
        except: bot.send_message(call.message.chat.id, "Musiqani yuklashda xato.")
    
    elif call.data.startswith('get_m:'): # Video tagidagi tugma bosilganda
        title = call.data.split(':')[1]
        call.message.text = title
        search_music_list(call.message)

# ==========================================
#              WEBHOOK & SERVER
# ==========================================
@app.route('/' + BOT_TOKEN, methods=['POST'])
def getMessage():
    bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode('utf-8'))])
    return "!", 200

@app.route("/")
def webhook():
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL + '/' + BOT_TOKEN)
    return "Bot status: Running", 200

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get('PORT', 8080)))