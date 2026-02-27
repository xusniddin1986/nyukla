import uvicorn
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
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
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
        await self._execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, username TEXT, full_name TEXT, joined_date TEXT)""", commit=True)
        await self._execute("CREATE TABLE IF NOT EXISTS channels (url TEXT PRIMARY KEY)", commit=True)
        await self._execute("CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)", commit=True)
        await self._execute("""CREATE TABLE IF NOT EXISTS cache (
            url TEXT PRIMARY KEY, file_id TEXT, type TEXT, title TEXT)""", commit=True)
        await self._execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)", commit=True)
        
        await self._execute("INSERT OR IGNORE INTO admins VALUES (?)", (DEFAULT_ADMIN,), commit=True)
        await self._execute("INSERT OR IGNORE INTO settings VALUES ('bot_status', 'on')", commit=True)
        logger.info("Database muvaffaqiyatli qurildi.")

db = AsyncDatabase("nyukla_core.db")

# --- MULTIMEDIA BOSHQARUVI (FFmpeg & yt-dlp) ---
class MediaManager:
    def __init__(self):
        self.common_opts = {
            'cookiefile': 'cookies.txt', # Agar ishlamasa, shu faylni qo'shishingiz kerak
            'quiet': True,
            'no_warnings': True,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
        }

    def check_ffmpeg(self) -> bool:
        try:
            # static-ffmpeg orqali izlaydi (agar o'rnatilgan bo'lsa)
            try:
                import static_ffmpeg
                static_ffmpeg.add_paths()
            except ImportError:
                pass
            
            subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
            return True
        except (FileNotFoundError, subprocess.CalledProcessError):
            return False

    async def download_video(self, url: str):
        opts = {
            'format': 'best[ext=mp4]/best',
            'outtmpl': 'downloads/%(id)s.%(ext)s',
            'max_filesize': 49 * 1024 * 1024,
            **self.common_opts
        }
        loop = asyncio.get_event_loop()
        with YoutubeDL(opts) as ydl:
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=True))
            return ydl.prepare_filename(info), info.get('title', 'Video')

    async def download_audio(self, url: str):
        if not self.check_ffmpeg():
            return None, "FFmpeg topilmadi. Admin bilan bog'laning."
        
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
    async def __call__(self, handler, event: Union[Message, CallbackQuery], data: dict):
        user = event.from_user
        uid = user.id
        is_callback = isinstance(event, CallbackQuery)
        message = event.message if is_callback else event

        if not message:
            return await handler(event, data)

        await db._execute("INSERT OR IGNORE INTO users VALUES (?, ?, ?, ?)", 
                         (uid, user.username, user.full_name, datetime.now().isoformat()), commit=True)

        is_admin = await db._execute("SELECT user_id FROM admins WHERE user_id=?", (uid,), fetch="one")
        if is_admin:
            return await handler(event, data)

        status = await db._execute("SELECT value FROM settings WHERE key='bot_status'", fetch="one")
        if status and status[0] == 'off':
            text = "⚠️ Bot vaqtincha faolsizlantirilgan (Texnik ishlar)."
            return await event.answer(text, show_alert=True) if is_callback else await message.answer(text)

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
            
            text = "🚨 Botdan foydalanish uchun quyidagi kanallarga a'zo bo'lishingiz shart:"
            if is_callback:
                if event.data == "check_sub":
                    return await event.answer("❌ Hali hamma kanallarga a'zo bo'lmadingiz!", show_alert=True)
                return await event.answer("Kanallarga a'zo bo'ling!", show_alert=True)
            else:
                return await message.answer(text, reply_markup=kb)

        if is_callback and event.data == "check_sub":
            await event.message.delete()
            await event.answer("✅ Obuna tasdiqlandi. Rahmat!", show_alert=True)
            return

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
dp.callback_query.middleware(CoreMiddleware())
app = FastAPI()

@dp.message(Command("start"))
async def start_cmd(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(f"Salom {message.from_user.full_name}! 👋\n\nMen orqali **YouTube**, **TikTok** va **Instagram**dan video/musiqa yuklab olishingiz mumkin.\nLink yuboring:", reply_markup=ReplyKeyboardRemove())

@dp.message(F.text.contains("http"))
async def process_media_request(message: Message):
    url = message.text
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
        await wait.edit_text("❌ Yuklashda xatolik! Link xato yoki video juda katta (50MB+).")

@dp.callback_query(F.data.startswith("convert_"))
async def convert_audio(call: CallbackQuery):
    url = call.data.replace("convert_", "")
    
    cached = await db._execute("SELECT file_id, title FROM cache WHERE url=? AND type='audio'", (url,), fetch="one")
    if cached:
        return await bot.send_audio(call.message.chat.id, audio=cached[0], caption=f"🎵 {cached[1]}\n\n📥 @{BOT_USERNAME}")

    wait = await call.message.answer("🎵 Musiqa ajratib olinmoqda kuting...")
    try:
        path, title = await media.download_audio(url)
        if not path: return await wait.edit_text(title)
        
        sent = await bot.send_audio(call.message.chat.id, audio=FSInputFile(path), caption=f"🎵 {title}\n\n📥 @{BOT_USERNAME}")
        await db._execute("INSERT OR REPLACE INTO cache VALUES (?, ?, ?, ?)", (url, sent.audio.file_id, "audio", title), commit=True)
        os.remove(path)
        await wait.delete()
    except Exception as e:
        logger.error(f"Audio Error: {e}")
        await wait.edit_text("❌ Audio yuklashda xatolik.")

# --- ADMIN PANEL FUNKSIYALARI ---
@dp.message(Command("admin"))
async def admin_panel(message: Message, state: FSMContext):
    await state.clear()
    is_adm = await db._execute("SELECT user_id FROM admins WHERE user_id=?", (message.from_user.id,), fetch="one")
    if is_adm:
        await message.answer("🛠 Admin panelga xush kelibsiz. Kerakli bo'limni tanlang:", reply_markup=admin_keyboard())

@dp.message(F.text == "🔙 Chiqish")
async def admin_exit(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Bosh menyu", reply_markup=ReplyKeyboardRemove())

@dp.message(F.text == "📊 Statistika")
async def show_stats(message: Message):
    is_adm = await db._execute("SELECT user_id FROM admins WHERE user_id=?", (message.from_user.id,), fetch="one")
    if not is_adm: return

    users = await db._execute("SELECT COUNT(*) FROM users", fetch="one")
    cache = await db._execute("SELECT COUNT(*) FROM cache", fetch="one")
    ffmpeg = "✅ Faol" if media.check_ffmpeg() else "❌ O'rnatilmagan"
    await message.answer(f"📈 **Bot Statistikasi:**\n\n👤 Foydalanuvchilar: {users[0]}\n💾 Keshdagi fayllar: {cache[0]}\n⚙️ FFmpeg holati: {ffmpeg}")

@dp.message(F.text == "👤 Foydalanuvchilar")
async def show_users(message: Message):
    is_adm = await db._execute("SELECT user_id FROM admins WHERE user_id=?", (message.from_user.id,), fetch="one")
    if not is_adm: return
    
    users = await db._execute("SELECT user_id, full_name FROM users ORDER BY joined_date DESC LIMIT 15", fetch="all")
    text = "👥 Oxirgi 15 ta foydalanuvchi:\n\n"
    for u in users:
        text += f"ID: `{u[0]}` | Ism: {u[1]}\n"
    await message.answer(text)

@dp.message(F.text == "⚙️ Bot Holati")
async def toggle_status(message: Message):
    is_adm = await db._execute("SELECT user_id FROM admins WHERE user_id=?", (message.from_user.id,), fetch="one")
    if not is_adm: return

    res = await db._execute("SELECT value FROM settings WHERE key='bot_status'", fetch="one")
    new = 'off' if res[0] == 'on' else 'on'
    await db._execute("UPDATE settings SET value=? WHERE key='bot_status'", (new,), commit=True)
    await message.answer(f"🔄 Bot holati o'zgardi. Hozir: **{new.upper()}**")

@dp.message(F.text == "✉️ Reklama tarqatish")
async def ads_start(message: Message, state: FSMContext):
    is_adm = await db._execute("SELECT user_id FROM admins WHERE user_id=?", (message.from_user.id,), fetch="one")
    if not is_adm: return

    await message.answer("📣 Reklama xabarini yuboring (Bekor qilish uchun /cancel):")
    await state.set_state(AdminStates.waiting_for_ads)

@dp.message(Command("cancel"), StateFilter(AdminStates.waiting_for_ads, AdminStates.adding_channel, AdminStates.removing_channel, AdminStates.adding_admin, AdminStates.removing_admin))
async def cancel_state(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Amal bekor qilindi.")

@dp.message(AdminStates.waiting_for_ads)
async def ads_send(message: Message, state: FSMContext):
    users = await db._execute("SELECT user_id FROM users", fetch="all")
    await message.answer(f"🚀 {len(users)} ta userga tarqatish boshlandi...")
    count, fail = 0, 0
    for u in users:
        try:
            await message.copy_to(u[0])
            count += 1
            if count % 30 == 0: await asyncio.sleep(1)
        except: 
            fail += 1
    await message.answer(f"✅ Tugadi.\nYetkazildi: {count}\nBloklangan: {fail}")
    await state.clear()

# --- ADMINLAR BOSHQARUVI ---
@dp.message(F.text == "🔑 Adminlarni boshqarish")
async def admin_mgmt(message: Message):
    if message.from_user.id != DEFAULT_ADMIN:
        return await message.answer("Bunga faqat Bosh Admin huquqiga ega.")
    
    admins = await db._execute("SELECT user_id FROM admins", fetch="all")
    text = "👮‍♂️ **Adminlar ro'yxati:**\n\n"
    for a in admins: text += f"• `{a[0]}`\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Admin qo'shish", callback_data="add_adm"), InlineKeyboardButton(text="❌ Admin olish", callback_data="rem_adm")]
    ])
    await message.answer(text, reply_markup=kb)

@dp.callback_query(F.data == "add_adm")
async def add_adm_cb(call: CallbackQuery, state: FSMContext):
    await call.message.answer("Yangi adminning ID raqamini yuboring:")
    await state.set_state(AdminStates.adding_admin)

@dp.message(AdminStates.adding_admin)
async def add_adm_final(message: Message, state: FSMContext):
    if message.text.isdigit():
        await db._execute("INSERT OR IGNORE INTO admins VALUES (?)", (int(message.text),), commit=True)
        await message.answer("✅ Admin qo'shildi.")
    else: await message.answer("❌ Xato! Faqat raqam yuboring.")
    await state.clear()

@dp.callback_query(F.data == "rem_adm")
async def rem_adm_cb(call: CallbackQuery, state: FSMContext):
    await call.message.answer("O'chiriladigan adminning ID raqamini yuboring:")
    await state.set_state(AdminStates.removing_admin)

@dp.message(AdminStates.removing_admin)
async def rem_adm_final(message: Message, state: FSMContext):
    uid = int(message.text) if message.text.isdigit() else 0
    if uid == DEFAULT_ADMIN:
        await message.answer("❌ Bosh adminni o'chirib bo'lmaydi.")
    elif uid > 0:
        await db._execute("DELETE FROM admins WHERE user_id=?", (uid,), commit=True)
        await message.answer("✅ Admin o'chirildi.")
    else:
        await message.answer("❌ Xato! ID ni to'g'ri kiriting.")
    await state.clear()

# --- KANAL BOSHQARUVI ---
@dp.message(F.text == "📢 Kanallarni boshqarish")
async def channel_mgmt(message: Message):
    is_adm = await db._execute("SELECT user_id FROM admins WHERE user_id=?", (message.from_user.id,), fetch="one")
    if not is_adm: return

    channels = await db._execute("SELECT url FROM channels", fetch="all")
    text = "📋 **Majburiy obuna kanallari:**\n\n"
    if not channels: text += "Hozircha kanallar yo'q."
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

@dp.callback_query(F.data == "rem_ch")
async def rem_ch_cb(call: CallbackQuery, state: FSMContext):
    channels = await db._execute("SELECT url FROM channels", fetch="all")
    if not channels: return await call.message.answer("O'chirish uchun kanallar yo'q.")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"❌ {c[0]}", callback_data=f"delch_{c[0]}")] for c in channels
    ])
    await call.message.edit_text("O'chiriladigan kanalni tanlang:", reply_markup=kb)

@dp.callback_query(F.data.startswith("delch_"))
async def del_ch_final(call: CallbackQuery):
    ch_url = call.data.replace("delch_", "")
    await db._execute("DELETE FROM channels WHERE url=?", (ch_url,), commit=True)
    await call.message.edit_text(f"✅ Kanal o'chirildi: {ch_url}")

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
async def root(): return {"status": "Bot is active", "version": "4.1.0 Enterprise"}
if __name__ == "__main__":
    import uvicorn
    import os
    # Render bergan portni avtomatik oladi
    port = int(os.environ.get("PORT", 8000)) 
    uvicorn.run(app, host="0.0.0.0", port=port)