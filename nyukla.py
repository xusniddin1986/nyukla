import logging
import asyncio
import os
import sqlite3
import re
import sys
from urllib.parse import urlparse

from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.dispatcher.webhook import SendMessage
from aiogram.utils.executor import start_webhook
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

import yt_dlp

# ==============================================================================
# KONFIGURATSIYA (SOZLAMALAR)
# ==============================================================================

API_TOKEN = os.getenv('BOT_TOKEN', '8510711803:AAE3klDsgCCgQTaB0oY8IDL4u-GmK9D2yAc')
ADMIN_ID = int(os.getenv('ADMIN_ID', '5767267885')) 
CHANNEL_ID = os.getenv('CHANNEL_ID', '@aclubnc') 
CHANNEL_URL = os.getenv('CHANNEL_URL', 'https://t.me/aclubnc')

PROJECT_NAME = os.getenv('RENDER_EXTERNAL_HOSTNAME', 'https://nyukla.onrender.com') 
WEBHOOK_HOST = f'https://{PROJECT_NAME}' 
WEBHOOK_PATH = f'/webhook/{API_TOKEN}'
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

WEBAPP_HOST = '0.0.0.0'
WEBAPP_PORT = int(os.getenv('PORT', 5000))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==============================================================================
# MA'LUMOTLAR BAZASI (SQLITE)
# ==============================================================================

class Database:
    def __init__(self, db_file):
        self.connection = sqlite3.connect(db_file)
        self.cursor = self.connection.cursor()
        self.create_tables()

    def create_tables(self):
        with self.connection:
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER UNIQUE,
                    username TEXT,
                    fullname TEXT,
                    joined_date DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

    def add_user(self, user_id, username, fullname):
        with self.connection:
            try:
                self.cursor.execute("INSERT INTO users (user_id, username, fullname) VALUES (?, ?, ?)", 
                                    (user_id, username, fullname))
                return True
            except sqlite3.IntegrityError:
                return False

    def get_users_count(self):
        with self.connection:
            return self.cursor.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    def get_all_users(self):
        with self.connection:
            return self.cursor.execute("SELECT user_id FROM users").fetchall()

    def user_exists(self, user_id):
        with self.connection:
            result = self.cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchall()
            return bool(len(result))

db = Database('bot_database.db')

# ==============================================================================
# BOT VA DISPATCHER
# ==============================================================================

bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# ==============================================================================
# STATES (HOLATLAR)
# ==============================================================================

class AdminState(StatesGroup):
    broadcasting = State()

class DownloadState(StatesGroup):
    waiting_for_music_choice = State()

# ==============================================================================
# YORDAMCHI FUNKSIYALAR (TOOLS)
# ==============================================================================

async def check_subscription(user_id):
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        if member.status in ['creator', 'administrator', 'member']:
            return True
        return False
    except Exception as e:
        logger.error(f"Obuna tekshirishda xatolik: {e}")
        return True 

def get_subscription_keyboard():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(text="📢 Kanalga a'zo bo'lish", url=CHANNEL_URL))
    markup.add(InlineKeyboardButton(text="✅ Tasdiqlash", callback_data="check_sub"))
    return markup

def clean_filename(title):
    return re.sub(r'[\\/*?:"<>|]', "", title)

# ==============================================================================
# ADMIN PANEL HANDLERS
# ==============================================================================

@dp.message_handler(commands=['admin'])
async def admin_start(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    count = db.get_users_count()
    text = (
        f"<b>👨‍💻 ADMIN PANEL</b>\n\n"
        f"👥 Foydalanuvchilar: <b>{count}</b> ta\n"
        f"🤖 Bot holati: <b>A'lo</b>\n"
        f"🚀 Server: <b>Render.com</b>"
    )
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("📨 Reklama yuborish", callback_data="admin_broadcast"),
        InlineKeyboardButton("📊 Statistika", callback_data="admin_stats"),
        InlineKeyboardButton("❌ Yopish", callback_data="admin_close")
    )
    await message.answer(text, reply_markup=markup, parse_mode='HTML')

@dp.callback_query_handler(text="admin_stats")
async def admin_stats(call: types.CallbackQuery):
    count = db.get_users_count()
    await call.answer(f"Hozirda {count} ta faol foydalanuvchi bor.", show_alert=True)

@dp.callback_query_handler(text="admin_close")
async def admin_close(call: types.CallbackQuery):
    await call.message.delete()

@dp.callback_query_handler(text="admin_broadcast")
async def admin_broadcast_ask(call: types.CallbackQuery):
    await AdminState.broadcasting.set()
    await call.message.answer("✍️ Foydalanuvchilarga yubormoqchi bo'lgan xabaringizni yozing (Rasm, Video yoki Matn):", 
                              reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("⬅️ Bekor qilish", callback_data="cancel_broadcast")))

@dp.callback_query_handler(text="cancel_broadcast", state=AdminState.broadcasting)
async def cancel_broadcast(call: types.CallbackQuery, state: FSMContext):
    await state.finish()
    await call.message.edit_text("❌ Xabar yuborish bekor qilindi.")

@dp.message_handler(state=AdminState.broadcasting, content_types=types.ContentTypes.ANY)
async def admin_broadcasting_process(message: types.Message, state: FSMContext):
    users = db.get_all_users()
    count = 0
    blocked = 0
    
    status_msg = await message.answer("📨 Xabar yuborish boshlandi...")
    
    for user in users:
        user_id = user[0]
        try:
            await message.copy_to(user_id)
            count += 1
            await asyncio.sleep(0.05) 
        except Exception:
            blocked += 1
            
    await status_msg.edit_text(f"✅ Xabar yuborildi!\n\n✅ Qabul qildi: {count}\n🚫 Bloklaganlar: {blocked}")
    await state.finish()

# ==============================================================================
# USER HANDLERS (START & HELP)
# ==============================================================================

@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    if not db.user_exists(message.from_user.id):
        db.add_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
    
    is_subbed = await check_subscription(message.from_user.id)
    if not is_subbed:
        await message.answer(
            f"👋 Salom {message.from_user.first_name}!\n\n"
            "Botdan to'liq foydalanish uchun kanalimizga obuna bo'lishingiz shart.",
            reply_markup=get_subscription_keyboard()
        )
        return

    await message.answer(
        f"<b>👋 Assalomu alaykum!</b>\n\n"
        "Men universal media yuklovchi va musiqa qidiruvchi botman.\n\n"
        "🔻 <b>Imkoniyatlarim:</b>\n"
        "• YouTube, Instagram, TikTok, Facebook dan video yuklash.\n"
        "• Musiqa qidirish va yuklash.\n\n"
        "🚀 <i>Link yuboring yoki musiqa nomini yozing!</i>",
        parse_mode='HTML'
    )

@dp.callback_query_handler(text="check_sub")
async def callback_check_sub(call: types.CallbackQuery):
    if await check_subscription(call.from_user.id):
        await call.message.delete()
        await call.message.answer("✅ <b>Obuna tasdiqlandi!</b>\nEndi bemalol foydalanishingiz mumkin.", parse_mode='HTML')
    else:
        await call.answer("❌ Siz hali kanalga obuna bo'lmadingiz!", show_alert=True)

@dp.message_handler(commands=['help'])
async def cmd_help(message: types.Message):
    await message.answer(
        "🆘 <b>Yordam Bo'limi</b>\n\n"
        "1️⃣ <b>Video yuklash:</b> Instagram, TikTok, YouTube linkini yuboring.\n"
        "2️⃣ <b>Musiqa qidirish:</b> Qo'shiqchi ismi yoki musiqa nomini yozing.\n"
        "3️⃣ <b>Admin:</b> /admin (faqat admin uchun)",
        parse_mode='HTML'
    )

@dp.message_handler(commands=['about'])
async def cmd_about(message: types.Message):
    await message.answer("🤖 Bot versiyasi: 2.0 (Pro)\n👨‍💻 Dasturchi: @SizningProfilingiz")

# ==============================================================================
# CORE LOGIC: MUSIC SEARCH & DOWNLOAD
# ==============================================================================

async def search_and_send_list(query, message: types.Message):
    msg = await message.answer("🔍 <b>Qidirilmoqda...</b>\nIltimos kuting.", parse_mode='HTML')
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'noplaylist': True,
        'quiet': True,
        'default_search': 'ytsearch10',
        'extract_flat': True,
        'cookiefile': 'cookies.txt', # <--- COOKIE QO'SHILDI
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(query, download=False)
            
            if 'entries' not in info or not info['entries']:
                await msg.edit_text("❌ Hech narsa topilmadi.")
                return

            keyboard = InlineKeyboardMarkup(row_width=1)
            result_text = f"🎵 <b>'{query}' bo'yicha natijalar:</b>\n\n"
            
            for i, entry in enumerate(info['entries']):
                title = entry.get('title', 'Noma\'lum')
                vid_id = entry.get('id')
                duration = entry.get('duration', 0)
                
                m, s = divmod(duration, 60)
                time_str = f"{m:02d}:{s:02d}"
                
                result_text += f"{i+1}. {title} ({time_str})\n"
                keyboard.add(InlineKeyboardButton(
                    text=f"{i+1}. 📥 {title[:25]}...", 
                    callback_data=f"dl_m:{vid_id}"
                ))
            
            await msg.delete()
            await message.answer(result_text, reply_markup=keyboard, parse_mode='HTML')

    except Exception as e:
        logger.error(f"Search error: {e}")
        await msg.edit_text("❌ Qidiruvda xatolik yuz berdi.")

@dp.callback_query_handler(lambda c: c.data.startswith('dl_m:'))
async def process_music_download(call: types.CallbackQuery):
    vid_id = call.data.split(':')[1]
    url = f"https://www.youtube.com/watch?v={vid_id}"
    
    await call.answer("⏳ Yuklanmoqda... Biroz kuting.")
    wait_msg = await call.message.reply("🎵 Musiqa yuklanmoqda...")
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': 'downloads/%(id)s.%(ext)s',
        'quiet': True,
        'cookiefile': 'cookies.txt', # <--- COOKIE QO'SHILDI
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }

    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: download_audio_sync(url, ydl_opts, call.message.chat.id, wait_msg.message_id))
    except Exception as e:
        await wait_msg.edit_text(f"❌ Xatolik: {e}")

def download_audio_sync(url, opts, chat_id, msg_id):
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info).replace('.webm', '.mp3').replace('.m4a', '.mp3')
            title = info.get('title', 'Music')
            
            import requests
            files = {'audio': open(filename, 'rb')}
            data = {'chat_id': chat_id, 'title': title, 'caption': f"🤖 @{os.getenv('BOT_USERNAME', 'bot')} orqali yuklandi"}
            requests.post(f"https://api.telegram.org/bot{API_TOKEN}/sendAudio", data=data, files=files)
            requests.post(f"https://api.telegram.org/bot{API_TOKEN}/deleteMessage", data={'chat_id': chat_id, 'message_id': msg_id})
            
            os.remove(filename)
    except Exception as e:
        logger.error(f"Download error: {e}")

# ==============================================================================
# CORE LOGIC: VIDEO DOWNLOADER
# ==============================================================================

async def download_video_logic(url, message: types.Message):
    msg = await message.reply("⏳ <b>Video yuklanmoqda...</b>\n\n<i>Katta hajmli videolar biroz vaqt olishi mumkin.</i>", parse_mode='HTML')
    
    ydl_opts = {
        'format': 'best', 
        'outtmpl': 'downloads/%(id)s.%(ext)s',
        'quiet': True,
        'noplaylist': True,
        'cookiefile': 'cookies.txt', # <--- IZOHDAN OLINDI VA COOKIE QO'SHILDI
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            video_path = ydl.prepare_filename(info)
            title = info.get('title', 'Video')
            
            clean_title = clean_filename(title)[:30] 
            
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton(text="🎵 Musiqasini yuklash", callback_data=f"src_vid:{info['id']}"))
            
            with open(video_path, 'rb') as video:
                await message.reply_video(
                    video, 
                    caption=f"🎥 <b>{title}</b>\n\n🤖 Bot: @{os.getenv('BOT_USERNAME', 'bot')}", 
                    reply_markup=markup,
                    parse_mode='HTML'
                )
            
            os.remove(video_path)
            await msg.delete()

    except Exception as e:
        await msg.edit_text(f"❌ Yuklashda xatolik: {str(e)}\n\nLinkni tekshirib qayta yuboring.")

@dp.callback_query_handler(lambda c: c.data.startswith('src_vid:'))
async def callback_search_from_video(call: types.CallbackQuery):
    vid_id = call.data.split(':')[1]
    await call.answer("🔎 Musiqa qidirilmoqda...")
    await call.message.reply("Videodagi musiqa nomini yoki ijrochini yozib yuboring, men topib beraman.")

# ==============================================================================
# MAIN HANDLER (TEXT FILTER)
# ==============================================================================

@dp.message_handler(content_types=['text'])
async def handle_text(message: types.Message):
    if not await check_subscription(message.from_user.id):
        await message.answer("⚠️ Botdan foydalanish uchun kanalga obuna bo'ling!", reply_markup=get_subscription_keyboard())
        return

    text = message.text
    url_pattern = re.compile(r'https?://\S+')
    
    if url_pattern.match(text):
        await download_video_logic(text, message)
    else:
        await search_and_send_list(text, message)

# ==============================================================================
# STARTUP & SHUTDOWN (WEBHOOK)
# ==============================================================================

async def on_startup(dp):
    await bot.set_webhook(WEBHOOK_URL)
    if not os.path.exists('downloads'):
        os.makedirs('downloads')
    try:
        await bot.send_message(ADMIN_ID, "✅ Bot ishga tushdi (Webhook)!")
    except:
        pass

async def on_shutdown(dp):
    await bot.delete_webhook()
    await dp.storage.close()
    await dp.storage.wait_closed()

if __name__ == '__main__':
    start_webhook(
        dispatcher=dp,
        webhook_path=WEBHOOK_PATH,
        on_startup=on_startup,
        on_shutdown=on_shutdown,
        skip_updates=True,
        host=WEBAPP_HOST,
        port=WEBAPP_PORT,
    )