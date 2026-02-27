import os
import asyncio
import logging
import aiosqlite
import subprocess
import re
import shutil
import uuid
from datetime import datetime
from typing import Union, List, Optional, Dict

import uvicorn
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types, F, BaseMiddleware
from aiogram.types import (
    Update, FSInputFile, InlineKeyboardMarkup, 
    InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton,
    ReplyKeyboardRemove, CallbackQuery, Message, InputMediaVideo, InputMediaAudio
)
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from yt_dlp import YoutubeDL

# FFmpeg static path (Render.com uchun maxsus)
try:
    import static_ffmpeg
    static_ffmpeg.add_paths()
except ImportError:
    pass

# --- 1. KONFIGURATSIYA VA LOGGING ---
BOT_TOKEN = "8679344041:AAGVo6gwxoyjWOPCSb3ezdtfgwJ7PkhhQaM"
RENDER_URL = "https://nyukla.onrender.com"
DEFAULT_ADMIN = 8553997595 
WEBHOOK_PATH = f"/bot/{BOT_TOKEN}"
WEBHOOK_URL = f"{RENDER_URL}{WEBHOOK_PATH}"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("bot.log"), logging.StreamHandler()]
)
logger = logging.getLogger("MegaBot")

# --- 2. FSM HOLATLARI ---
class AdminStates(StatesGroup):
    waiting_for_ads = State()
    adding_channel = State()
    removing_channel = State()
    adding_admin = State()
    removing_admin = State()
    setting_limit = State()

class UserStates(StatesGroup):
    searching_music = State()

# --- 3. DATABASE MODULE (AIOSQLITE) ---
class Database:
    def __init__(self, path: str):
        self.path = path

    async def execute(self, sql: str, params: tuple = (), commit: bool = False):
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(sql, params)
            if commit:
                await db.commit()
            return cursor

    async def fetch_one(self, sql: str, params: tuple = ()):
        cursor = await self.execute(sql, params)
        return await cursor.fetchone()

    async def fetch_all(self, sql: str, params: tuple = ()):
        cursor = await self.execute(sql, params)
        return await cursor.fetchall()

    async def setup(self):
        # Foydalanuvchilar jadvali
        await self.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, 
            username TEXT, 
            full_name TEXT, 
            status TEXT DEFAULT 'active',
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""", commit=True)
        
        # Kanallar (Majburiy obuna)
        await self.execute("""CREATE TABLE IF NOT EXISTS channels (
            channel_id TEXT PRIMARY KEY,
            title TEXT,
            invite_link TEXT
        )""", commit=True)

        # Adminlar
        await self.execute("""CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY,
            level INTEGER DEFAULT 1
        )""", commit=True)

        # Kesh tizimi (Takroriy yuklamaslik uchun)
        await self.execute("""CREATE TABLE IF NOT EXISTS cache (
            file_key TEXT PRIMARY KEY,
            file_id TEXT,
            file_type TEXT,
            title TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""", commit=True)

        # Ilk adminni qo'shish
        await self.execute("INSERT OR IGNORE INTO admins (user_id, level) VALUES (?, 2)", (DEFAULT_ADMIN,), commit=True)
        logger.info("Database sozlari yakunlandi.")

db = Database("mega_storage.db")

# --- 4. MEDIA ENGINE (YT-DLP) ---
class MediaEngine:
    def __init__(self):
        self.base_opts = {
            'quiet': True,
            'no_warnings': True,
            'ignoreerrors': True,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        }

    async def search_yt(self, query: str):
        opts = {**self.base_opts, 'extract_flat': True, 'force_generic_extractor': False}
        with YoutubeDL(opts) as ydl:
            loop = asyncio.get_event_loop()
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(f"ytsearch5:{query}", download=False))
            return info.get('entries', [])

    async def download(self, url: str, mode: str = "video") -> Dict:
        folder = "temp_media"
        if not os.path.exists(folder): os.makedirs(folder)
        
        file_name = f"{uuid.uuid4()}"
        out_tmpl = f"{folder}/{file_name}.%(ext)s"
        
        opts = {
            **self.base_opts,
            'outtmpl': out_tmpl,
            'max_filesize': 50 * 1024 * 1024, # 50MB cheklovi
        }

        if mode == "audio":
            opts.update({
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            })
        else:
            # Render uchun 720p dan yuqori bo'lmagan video (limitdan oshmaslik uchun)
            opts['format'] = 'best[height<=720][ext=mp4]/bestvideo[height<=720]+bestaudio/best'

        with YoutubeDL(opts) as ydl:
            loop = asyncio.get_event_loop()
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=True))
            if not info: return None
            
            actual_path = ydl.prepare_filename(info)
            if mode == "audio":
                actual_path = actual_path.rsplit('.', 1)[0] + ".mp3"
                
            return {
                'path': actual_path,
                'title': info.get('title', 'Noma\'lum nom'),
                'duration': info.get('duration', 0),
                'thumbnail': info.get('thumbnail', None)
            }

engine = MediaEngine()

# --- 5. MIDDLEWARE (XAVFSIZLIK VA OBUNA) ---
class AccessMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: Union[Message, CallbackQuery], data: dict):
        user = event.from_user
        if not user: return await handler(event, data)

        # Userni DBga qo'shish
        await db.execute("INSERT OR IGNORE INTO users (user_id, username, full_name) VALUES (?, ?, ?)", 
                        (user.id, user.username, user.full_name), commit=True)

        # Adminni tekshirish
        is_admin = await db.fetch_one("SELECT * FROM admins WHERE user_id=?", (user.id,))
        if is_admin:
            data['is_admin'] = True
            return await handler(event, data)
        
        data['is_admin'] = False
        
        # Start buyrug'ida obuna tekshirmaymiz
        if isinstance(event, Message) and event.text == "/start":
            return await handler(event, data)

        # Majburiy obuna tekshiruvi
        channels = await db.fetch_all("SELECT * FROM channels")
        not_joined = []
        for ch in channels:
            try:
                member = await data['bot'].get_chat_member(ch['channel_id'], user.id)
                if member.status in ['left', 'kicked', 'left']:
                    not_joined.append(ch)
            except Exception:
                continue

        if not_joined:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=f"➕ {c['title']}", url=c['invite_link'])] for c in not_joined
            ])
            kb.inline_keyboard.append([InlineKeyboardButton(text="🔄 Tekshirish", callback_data="recheck")])
            
            msg_text = "⚠️ **Botdan foydalanish uchun quyidagi kanallarga a'zo bo'ling!**"
            if isinstance(event, CallbackQuery):
                await event.answer("Obuna bo'lmagansiz!", show_alert=True)
            else:
                await event.answer(msg_text, reply_markup=kb)
            return

        return await handler(event, data)

# --- 6. ASOSIY BOT LOGIKASI ---
bot = Bot(token=BOT_TOKEN, parse_mode="Markdown")
dp = Dispatcher(storage=MemoryStorage())
dp.update.outer_middleware(AccessMiddleware())
app = FastAPI()

# Keyboardlar
def get_main_kb(is_admin=False):
    kb = [
        [KeyboardButton(text="🎵 Musiqa qidirish"), KeyboardButton(text="🎬 Video yuklash")],
        [KeyboardButton(text="ℹ️ Ma'lumot"), KeyboardButton(text="🌟 Premium")]
    ]
    if is_admin:
        kb.append([KeyboardButton(text="🛠 Admin Panel")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_admin_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📊 Statistika"), KeyboardButton(text="📢 Kanallar")],
        [KeyboardButton(text="🔑 Adminlar"), KeyboardButton(text="✉️ Reklama")],
        [KeyboardButton(text="🔙 Chiqish")]
    ], resize_keyboard=True)

# Handlerlar
@dp.message(Command("start"))
async def start_handler(m: Message, is_admin: bool):
    await m.answer(f"Xush kelibsiz, {m.from_user.full_name}! 🔥\nLink yuboring yoki quyidagi menyudan foydalaning.", 
                  reply_markup=get_main_kb(is_admin))

@dp.callback_query(F.data == "recheck")
async def recheck_handler(call: CallbackQuery):
    await call.message.delete()
    await call.message.answer("✅ Obuna tasdiqlandi! Havola yuborishingiz mumkin.")

# Musiqa qidirish boshlanishi
@dp.message(F.text == "🎵 Musiqa qidirish")
async def search_start(m: Message, state: FSMContext):
    await m.answer("🔍 Musiqa yoki ijrochi nomini yozing:")
    await state.set_state(UserStates.searching_music)

@dp.message(UserStates.searching_music)
async def search_process(m: Message, state: FSMContext):
    if m.text.startswith("/"): return await state.clear()
    
    wait = await m.answer("🔎 Qidirilmoqda, kuting...")
    results = await engine.search_yt(m.text)
    
    if not results:
        return await wait.edit_text("❌ Hech narsa topilmadi.")
    
    kb = []
    text = "🎵 **Qidiruv natijalari:**\n\n"
    for i, res in enumerate(results, 1):
        text += f"{i}. {res['title'][:50]}\n"
        kb.append([InlineKeyboardButton(text=f"{i}-ni yuklash", callback_data=f"yt_dl_audio:{res['id']}")])
    
    await wait.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await state.clear()

# Media yuklash (Direct Link)
@dp.message(F.text.regexp(r'(https?://[^\s]+)'))
async def link_handler(m: Message):
    url = m.text
    # Keshni tekshirish
    cached = await db.fetch_one("SELECT file_id, title FROM cache WHERE file_key=?", (url,))
    if cached:
        return await m.answer_video(cached['file_id'], caption=f"✅ {cached['title']}\n\n📥 @{bot.get_me().username}")

    wait = await m.answer("⚡️ Yuklanmoqda, bu biroz vaqt olishi mumkin...")
    try:
        data = await engine.download(url, mode="video")
        if not data: raise Exception("Download failed")

        video = FSInputFile(data['path'])
        sent = await m.answer_video(video, caption=f"🎬 **{data['title']}**\n\n📥 @{bot.get_me().username}")
        
        # Keshga saqlash
        await db.execute("INSERT OR REPLACE INTO cache (file_key, file_id, file_type, title) VALUES (?, ?, ?, ?)",
                        (url, sent.video.file_id, "video", data['title']), commit=True)
        
        if os.path.exists(data['path']): os.remove(data['path'])
        await wait.delete()
    except Exception as e:
        logger.error(f"Media Error: {e}")
        await wait.edit_text("❌ Xatolik! Link noto'g'ri, video o'chirilgan yoki hajmi 50MB dan katta.")

# Callback orqali audio yuklash
@dp.callback_query(F.data.startswith("yt_dl_audio:"))
async def dl_audio_callback(call: CallbackQuery):
    video_id = call.data.split(":")[1]
    url = f"https://www.youtube.com/watch?v={video_id}"
    
    # Audio keshni tekshirish
    cached = await db.fetch_one("SELECT file_id, title FROM cache WHERE file_key=?", (f"audio_{video_id}",))
    if cached:
        return await call.message.answer_audio(cached['file_id'], caption=f"🎵 {cached['title']}")

    wait = await call.message.answer("🎵 Audio tayyorlanmoqda...")
    try:
        data = await engine.download(url, mode="audio")
        audio = FSInputFile(data['path'])
        sent = await call.message.answer_audio(audio, caption=f"🎵 **{data['title']}**\n📥 @{bot.get_me().username}")
        
        await db.execute("INSERT OR REPLACE INTO cache (file_key, file_id, file_type, title) VALUES (?, ?, ?, ?)",
                        (f"audio_{video_id}", sent.audio.file_id, "audio", data['title']), commit=True)
        
        if os.path.exists(data['path']): os.remove(data['path'])
        await wait.delete()
    except:
        await wait.edit_text("❌ Audioni yuklab bo'lmadi.")

# --- 7. ADMIN PANEL FUNKSIYALARI ---
@dp.message(F.text == "🛠 Admin Panel")
async def admin_panel_enter(m: Message, is_admin: bool):
    if is_admin:
        await m.answer("🛠 Xush kelibsiz, Admin!", reply_markup=get_admin_kb())

@dp.message(F.text == "📊 Statistika")
async def admin_stats(m: Message, is_admin: bool):
    if not is_admin: return
    users = await db.fetch_one("SELECT COUNT(*) as cnt FROM users")
    chans = await db.fetch_one("SELECT COUNT(*) as cnt FROM channels")
    cache = await db.fetch_one("SELECT COUNT(*) as cnt FROM cache")
    
    text = f"📈 **Bot statistikasi:**\n\n"
    text += f"👤 Foydalanuvchilar: {users['cnt']}\n"
    text += f"📢 Kanallar: {chans['cnt']}\n"
    text += f"💾 Keshdagi media: {cache['cnt']}\n"
    await m.answer(text)

@dp.message(F.text == "📢 Kanallar")
async def admin_channels(m: Message, is_admin: bool):
    if not is_admin: return
    chans = await db.fetch_all("SELECT * FROM channels")
    text = "📋 **Majburiy kanallar:**\n\n"
    kb = []
    for c in chans:
        text += f"🔹 {c['title']} ({c['channel_id']})\n"
        kb.append([InlineKeyboardButton(text=f"❌ {c['title']}-ni o'chirish", callback_data=f"rem_ch:{c['channel_id']}")])
    
    kb.append([InlineKeyboardButton(text="➕ Kanal qo'shish", callback_data="add_ch_start")])
    await m.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data == "add_ch_start")
async def add_ch_call(call: CallbackQuery, state: FSMContext):
    await call.message.answer("Kanal ma'lumotlarini quyidagi formatda yuboring:\n`ID | NOMI | LINK` \n\nMasalan: `-1001234567 | Mening Kanalim | https://t.me/kanal` ")
    await state.set_state(AdminStates.adding_channel)

@dp.message(AdminStates.adding_channel)
async def add_ch_process(m: Message, state: FSMContext):
    try:
        cid, title, link = m.text.split("|")
        await db.execute("INSERT INTO channels VALUES (?, ?, ?)", (cid.strip(), title.strip(), link.strip()), commit=True)
        await m.answer("✅ Kanal muvaffaqiyatli qo'shildi.")
    except:
        await m.answer("❌ Xato! Formatga rioya qiling.")
    await state.clear()

@dp.callback_query(F.data.startswith("rem_ch:"))
async def rem_ch_call(call: CallbackQuery):
    cid = call.data.split(":")[1]
    await db.execute("DELETE FROM channels WHERE channel_id=?", (cid,), commit=True)
    await call.answer("O'chirildi!", show_alert=True)
    await call.message.delete()

@dp.message(F.text == "✉️ Reklama")
async def ads_start(m: Message, state: FSMContext, is_admin: bool):
    if not is_admin: return
    await m.answer("Xabarni yuboring (Rasm, Video, Text hammasi bo'ladi):")
    await state.set_state(AdminStates.waiting_for_ads)

@dp.message(AdminStates.waiting_for_ads)
async def ads_process(m: Message, state: FSMContext):
    users = await db.fetch_all("SELECT user_id FROM users")
    await m.answer(f"🚀 {len(users)} ta foydalanuvchiga yuborish boshlandi...")
    
    count, fail = 0, 0
    for u in users:
        try:
            await m.copy_to(u['user_id'])
            count += 1
            await asyncio.sleep(0.05) # Spamdan himoya
        except (TelegramForbiddenError, Exception):
            fail += 1
            
    await m.answer(f"✅ Tugadi!\n\nYuborildi: {count}\nBloklangan: {fail}")
    await state.clear()

@dp.message(F.text == "🔙 Chiqish")
async def exit_admin(m: Message, is_admin: bool):
    await m.answer("Bosh menyu", reply_markup=get_main_kb(is_admin))

# --- 8. WEBHOOK VA STARTUP ---
@app.on_event("startup")
async def on_startup():
    await db.setup()
    await bot.set_webhook(url=WEBHOOK_URL, drop_pending_updates=True)
    logger.info("Bot ishga tushdi!")

@app.post(WEBHOOK_PATH)
async def bot_webhook(request: Request):
    update = Update.model_validate(await request.json(), context={"bot": bot})
    await dp.feed_update(bot, update)

@app.get("/")
async def root():
    return {"status": "MegaBot is running", "db": "Connected"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)