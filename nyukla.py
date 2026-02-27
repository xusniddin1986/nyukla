import os
import asyncio
import logging
import aiosqlite
import subprocess
from datetime import datetime
from typing import Union, List, Optional

from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types, F, BaseMiddleware
from aiogram.types import (
    Update, FSInputFile, InlineKeyboardMarkup, 
    InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton,
    ReplyKeyboardRemove, CallbackQuery, Message
)
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from yt_dlp import YoutubeDL

# --- KONFIGURATSIYA VA LOGGING ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='bot_errors.log'
)
logger = logging.getLogger(__name__)

BOT_TOKEN = "8679344041:AAGVo6gwxoyjWOPCSb3ezdtfgwJ7PkhhQaM"
RENDER_URL = "https://nyukla.onrender.com"
BOT_USERNAME = "NYuklaBot"
DEFAULT_ADMIN = 8553997595 

WEBHOOK_PATH = f"/bot/{BOT_TOKEN}"
WEBHOOK_URL = f"{RENDER_URL}{WEBHOOK_PATH}"

# --- FSM HOLATLARI ---
class AdminStates(StatesGroup):
    waiting_for_ads = State()
    adding_channel = State()
    removing_channel = State()
    adding_admin = State()
    removing_admin = State()

# --- DATABASE INTEGRATSIYASI (Professional Wrapper) ---
class AsyncDatabase:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def _execute(self, query: str, params: tuple = (), commit: bool = False, fetch: str = None):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(query, params)
            if commit:
                await db.commit()
            if fetch == "one":
                return await cursor.fetchone()
            if fetch == "all":
                return await cursor.fetchall()
            return cursor

    async def setup(self):
        # Userlar
        await self._execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, username TEXT, full_name TEXT, joined_date TEXT)""", commit=True)
        # Kanallar
        await self._execute("CREATE TABLE IF NOT EXISTS channels (url TEXT PRIMARY KEY)", commit=True)
        # Adminlar
        await self._execute("CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)", commit=True)
        # Kesh tizimi (Video & Audio)
        await self._execute("""CREATE TABLE IF NOT EXISTS cache (
            url TEXT PRIMARY KEY, file_id TEXT, type TEXT, title TEXT)""", commit=True)
        # Sozlamalar (Bot on/off)
        await self._execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)", commit=True)
        
        # Default sozlamalar
        await self._execute("INSERT OR IGNORE INTO admins VALUES (?)", (DEFAULT_ADMIN,), commit=True)
        await self._execute("INSERT OR IGNORE INTO settings VALUES ('bot_status', 'on')", commit=True)
        logger.info("Database arxitekturasi muvaffaqiyatli qurildi.")

db = AsyncDatabase("nyukla_core.db")

# --- MULTIMEDIA BOSHQARUVI (FFmpeg & yt-dlp) ---
class MediaManager:
    def __init__(self):
        self.common_opts = {
            'cookiefile': 'cookies.txt',
            'quiet': True,
            'no_warnings': True,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
        }

    def check_ffmpeg(self) -> bool:
        try:
            subprocess.run(["ffmpeg", "-version"], capture_output=True)
            return True
        except FileNotFoundError:
            return False

    async def download_video(self, url: str):
        opts = {
            'format': 'best[ext=mp4]/best',
            'outtmpl': 'downloads/%(id)s.%(ext)s',
            'max_filesize': 48 * 1024 * 1024, # 48MB Telegram limiti
            **self.common_opts
        }
        loop = asyncio.get_event_loop()
        with YoutubeDL(opts) as ydl:
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=True))
            return ydl.prepare_filename(info), info.get('title', 'Video')

    async def download_audio(self, url: str):
        if not self.check_ffmpeg():
            return None, "FFmpeg o'rnatilmagan!"
        
        file_id = str(int(datetime.now().timestamp()))
        path = f"downloads/{file_id}.mp3"
        opts = {
            'format': 'bestaudio/best',
            'outtmpl': f"downloads/{file_id}",
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            **self.common_opts
        }
        loop = asyncio.get_event_loop()
        with YoutubeDL(opts) as ydl:
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=True))
            return path, info.get('title', 'Audio')

media = MediaManager()

# --- MIDDLEWARE (Xavfsizlik & Majburiy Obuna) ---
class CoreMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: Message, data: dict):
        if not isinstance(event, Message):
            return await handler(event, data)

        uid = event.from_user.id
        # Foydalanuvchini qayd etish
        await db._execute("INSERT OR IGNORE INTO users VALUES (?, ?, ?, ?)", 
                         (uid, event.from_user.username, event.from_user.full_name, datetime.now().isoformat()), commit=True)

        # Admin tekshiruvi (bypass)
        is_admin = await db._execute("SELECT user_id FROM admins WHERE user_id=?", (uid,), fetch="one")
        if is_admin:
            return await handler(event, data)

        # Bot holati
        status = await db._execute("SELECT value FROM settings WHERE key='bot_status'", fetch="one")
        if status and status[0] == 'off':
            return await event.answer("⚠️ Bot vaqtincha faolsizlantirilgan (Texnik ishlar).")

        # Majburiy obuna
        channels = await db._execute("SELECT url FROM channels", fetch="all")
        not_joined = []
        for ch in channels:
            try:
                member = await event.bot.get_chat_member(ch[0], uid)
                if member.status in ["left", "kicked"]:
                    not_joined.append(ch[0])
            except: continue

        if not_joined:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=f"A'zo bo'lish ✅", url=f"https://t.me/{c[1:]}")] for c in not_joined
            ])
            kb.inline_keyboard.append([InlineKeyboardButton(text="Obunani tekshirish 🔄", callback_data="check_sub")])
            return await event.answer("🚨 Botdan foydalanish uchun quyidagi kanallarga a'zo bo'lishingiz shart:", reply_markup=kb)

        return await handler(event, data)

# --- KEYBOARD FABRIKALARI ---
def admin_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📊 Statistika"), KeyboardButton(text="👤 Foydalanuvchilar")],
        [KeyboardButton(text="📢 Kanallarni boshqarish"), KeyboardButton(text="🔑 Adminlarni boshqarish")],
        [KeyboardButton(text="✉️ Reklama tarqatish"), KeyboardButton(text="⚙️ Bot Holati")],
        [KeyboardButton(text="🔙 Chiqish")]
    ], resize_keyboard=True)

# --- BOT HANDLERLARI (ASOSIY LOGIKA) ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
dp.message.middleware(CoreMiddleware())
app = FastAPI()

@dp.message(Command("start"))
async def start_cmd(message: Message):
    await message.answer(f"Salom {message.from_user.full_name}! 👋\n\nMen orqali **YouTube** va **Instagram**dan video/musiqa yuklab olishingiz mumkin.\nLink yuboring:", reply_markup=ReplyKeyboardRemove())

@dp.message(F.text.contains("youtube.com") | F.text.contains("youtu.be") | F.text.contains("instagram.com"))
async def process_media_request(message: Message):
    url = message.text
    # Keshdan tekshirish
    cached = await db._execute("SELECT file_id, title FROM cache WHERE url=? AND type='video'", (url,), fetch="one")
    if cached:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🎵 MP3 formatda yuklash", callback_data=f"convert_{url}")]])
        return await bot.send_video(message.chat.id, video=cached[0], caption=f"🎬 {cached[1]}\n\n📥 @{BOT_USERNAME}", reply_markup=kb)

    wait = await message.answer("🔍 Havola tahlil qilinmoqda...")
    try:
        if not os.path.exists('downloads'): os.makedirs('downloads')
        file_path, title = await media.download_video(url)
        
        await wait.edit_text("📤 Telegramga yuklanmoqda...")
        sent = await bot.send_video(
            message.chat.id, 
            video=FSInputFile(file_path), 
            caption=f"🎬 {title}\n\n📥 @{BOT_USERNAME}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🎵 MP3 formatda yuklash", callback_data=f"convert_{url}")]])
        )
        
        await db._execute("INSERT OR REPLACE INTO cache VALUES (?, ?, ?, ?)", (url, sent.video.file_id, "video", title), commit=True)
        os.remove(file_path)
        await wait.delete()
    except Exception as e:
        logger.error(f"DL Error: {e}")
        await wait.edit_text("❌ Yuklashda xatolik! Video hajmi 50MB dan katta bo'lishi mumkin.")

@dp.callback_query(F.data.startswith("convert_"))
async def convert_audio(call: CallbackQuery):
    url = call.data.replace("convert_", "")
    
    cached = await db._execute("SELECT file_id, title FROM cache WHERE url=? AND type='audio'", (url,), fetch="one")
    if cached:
        return await bot.send_audio(call.message.chat.id, audio=cached[0], caption=f"🎵 {cached[1]}\n\n📥 @{BOT_USERNAME}")

    wait = await call.message.answer("🎵 Musiqa ajratib olinmoqda (FFmpeg)...")
    try:
        path, title = await media.download_audio(url)
        if not path: return await wait.edit_text(title)
        
        sent = await bot.send_audio(call.message.chat.id, audio=FSInputFile(path), caption=f"🎵 {title}\n\n📥 @{BOT_USERNAME}")
        await db._execute("INSERT OR REPLACE INTO cache VALUES (?, ?, ?, ?)", (url, sent.audio.file_id, "audio", title), commit=True)
        os.remove(path)
        await wait.delete()
    except:
        await wait.edit_text("❌ Audio yuklashda xatolik.")

# --- ADMIN PANEL FUNKSIYALARI ---
@dp.message(Command("admin"))
async def admin_panel(message: Message):
    is_adm = await db._execute("SELECT user_id FROM admins WHERE user_id=?", (message.from_user.id,), fetch="one")
    if is_adm:
        await message.answer("🛠 Admin panelga xush kelibsiz. Kerakli bo'limni tanlang:", reply_markup=admin_keyboard())

@dp.message(F.text == "📊 Statistika")
async def show_stats(message: Message):
    users = await db._execute("SELECT COUNT(*) FROM users", fetch="one")
    cache = await db._execute("SELECT COUNT(*) FROM cache", fetch="one")
    ffmpeg = "✅ Faol" if media.check_ffmpeg() else "❌ O'rnatilmagan"
    await message.answer(f"📈 **Bot Statistikasi:**\n\n👤 Foydalanuvchilar: {users[0]}\n💾 Keshdagi fayllar: {cache[0]}\n⚙️ FFmpeg holati: {ffmpeg}")

@dp.message(F.text == "✉️ Reklama tarqatish")
async def ads_start(message: Message, state: FSMContext):
    await message.answer("📣 Reklama xabarini yuboring (Rasm, Video, Audio yoki Matn):")
    await state.set_state(AdminStates.waiting_for_ads)

@dp.message(AdminStates.waiting_for_ads)
async def ads_send(message: Message, state: FSMContext):
    users = await db._execute("SELECT user_id FROM users", fetch="all")
    await message.answer(f"🚀 {len(users)} ta userga tarqatish boshlandi...")
    count = 0
    for u in users:
        try:
            await message.copy_to(u[0])
            count += 1
            if count % 30 == 0: await asyncio.sleep(1)
        except: continue
    await message.answer(f"✅ Tugadi. {count} ta userga yetkazildi.")
    await state.clear()

@dp.message(F.text == "⚙️ Bot Holati")
async def toggle_status(message: Message):
    res = await db._execute("SELECT value FROM settings WHERE key='bot_status'", fetch="one")
    new = 'off' if res[0] == 'on' else 'on'
    await db._execute("UPDATE settings SET value=? WHERE key='bot_status'", (new,), commit=True)
    await message.answer(f"🔄 Bot holati: {new.upper()}")

# --- KANAL BOSHQARUVI ---
@dp.message(F.text == "📢 Kanallarni boshqarish")
async def channel_mgmt(message: Message):
    channels = await db._execute("SELECT url FROM channels", fetch="all")
    text = "📋 **Majburiy obuna kanallari:**\n\n"
    for c in channels: text += f"• {c[0]}\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Qo'shish", callback_data="add_ch"), InlineKeyboardButton(text="❌ O'chirish", callback_data="rem_ch")]
    ])
    await message.answer(text, reply_markup=kb)

@dp.callback_query(F.data == "add_ch")
async def add_ch_cb(call: CallbackQuery, state: FSMContext):
    await call.message.answer("Kanal username-ini yuboring (masalan: @kanalim):")
    await state.set_state(AdminStates.adding_channel)

@dp.message(AdminStates.adding_channel)
async def add_ch_final(message: Message, state: FSMContext):
    if message.text.startswith("@"):
        await db._execute("INSERT OR IGNORE INTO channels VALUES (?)", (message.text,), commit=True)
        await message.answer("✅ Kanal qo'shildi.")
    else: await message.answer("❌ Xato! @ bilan boshlang.")
    await state.clear()

# --- WEBHOOK VA SERVER ---
@app.on_event("startup")
async def on_startup():
    await db.setup()
    await bot.set_webhook(url=WEBHOOK_URL, drop_pending_updates=True)

@app.post(WEBHOOK_PATH)
async def bot_webhook(request: Request):
    update = Update.model_validate(await request.json(), context={"bot": bot})
    await dp.feed_update(bot, update)

@app.get("/")
async def root(): return {"status": "Bot is active", "version": "4.0.0 Pro"}