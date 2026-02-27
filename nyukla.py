import os
import asyncio
import logging
import aiosqlite
from datetime import datetime
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types, F, BaseMiddleware
from aiogram.types import (
    Update, FSInputFile, InlineKeyboardMarkup, 
    InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton,
    ReplyKeyboardRemove
)
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from yt_dlp import YoutubeDL

# --- LOGGING ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- CONFIG ---
BOT_TOKEN = "8679344041:AAGVo6gwxoyjWOPCSb3ezdtfgwJ7PkhhQaM"
RENDER_URL = "https://nyukla.onrender.com"
BOT_USERNAME = "NYuklaBot"
DEFAULT_ADMIN = 8553997595 # O'zingizning ID raqamingiz

WEBHOOK_PATH = f"/bot/{BOT_TOKEN}"
WEBHOOK_URL = f"{RENDER_URL}{WEBHOOK_PATH}"

# --- INITIALIZE ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
app = FastAPI()

# --- FSM STATES ---
class AdminStates(StatesGroup):
    waiting_for_ads = State()
    adding_channel = State()
    removing_channel = State()
    adding_admin = State()
    removing_admin = State()

# --- DATABASE MANAGER ---
class Database:
    def __init__(self, db_path):
        self.db_path = db_path

    async def connect(self):
        return await aiosqlite.connect(self.db_path)

    async def setup(self):
        async with await self.connect() as db:
            # Foydalanuvchilar jadvali
            await db.execute("""CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY, 
                username TEXT, 
                full_name TEXT, 
                joined_date TEXT)""")
            # Kanallar jadvali
            await db.execute("CREATE TABLE IF NOT EXISTS channels (url TEXT PRIMARY KEY, title TEXT)")
            # Adminlar jadvali
            await db.execute("CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)")
            # Kesh jadvali
            await db.execute("""CREATE TABLE IF NOT EXISTS cache (
                url TEXT PRIMARY KEY, 
                file_id TEXT, 
                type TEXT, 
                title TEXT, 
                size INTEGER)""")
            # Sozlamalar
            await db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
            
            # Boshlang'ich ma'lumotlar
            await db.execute("INSERT OR IGNORE INTO admins VALUES (?)", (DEFAULT_ADMIN,))
            await db.execute("INSERT OR IGNORE INTO settings VALUES ('bot_status', 'on')")
            await db.commit()

db_manager = Database("bot_master.db")

# --- MIDDLEWARES ---
class AdvancedMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if not isinstance(event, types.Message):
            return await handler(event, data)

        user_id = event.from_user.id
        username = event.from_user.username
        full_name = event.from_user.full_name
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        async with await db_manager.connect() as db:
            # User registration
            await db.execute(
                "INSERT OR IGNORE INTO users VALUES (?, ?, ?, ?)",
                (user_id, username, full_name, now)
            )
            await db.commit()

            # Bot status check
            async with db.execute("SELECT value FROM settings WHERE key='bot_status'") as c:
                status = await c.fetchone()
                if status and status[0] == 'off':
                    async with db.execute("SELECT user_id FROM admins WHERE user_id=?", (user_id,)) as adm:
                        if not await adm.fetchone():
                            return await event.answer("🚫 Bot texnik ishlar sababli vaqtincha to'xtatilgan.")

            # Admin check for forced sub bypass
            async with db.execute("SELECT user_id FROM admins WHERE user_id=?", (user_id,)) as adm:
                if await adm.fetchone():
                    return await handler(event, data)

            # Mandatory subscription check
            async with db.execute("SELECT url FROM channels") as c:
                channels = [row[0] for row in await c.fetchall()]
                missing = []
                for ch in channels:
                    try:
                        member = await event.bot.get_chat_member(ch, user_id)
                        if member.status in ['left', 'kicked', 'restricted']:
                            missing.append(ch)
                    except: continue
                
                if missing:
                    kb = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text=f"Kanal {i+1}", url=f"https://t.me/{c[1:]}")] for i, c in enumerate(missing)
                    ])
                    kb.inline_keyboard.append([InlineKeyboardButton(text="Obunani tekshirish ✅", callback_data="check_sub")])
                    return await event.answer("⚠️ Botdan foydalanish uchun kanallarga a'zo bo'ling:", reply_markup=kb)

        return await handler(event, data)

dp.message.middleware(AdvancedMiddleware())

# --- KEYBOARDS ---
def get_admin_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📊 Statistika"), KeyboardButton(text="👤 Foydalanuvchilar")],
        [KeyboardButton(text="📢 Kanallarni boshqarish"), KeyboardButton(text="🔑 Adminlar")],
        [KeyboardButton(text="✉️ Reklama tarqatish"), KeyboardButton(text="⚙️ Bot Holati")],
        [KeyboardButton(text="🔙 Chiqish")]
    ], resize_keyboard=True)

def get_channel_control_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Kanal qo'shish", callback_data="add_ch"),
         InlineKeyboardButton(text="❌ Kanalni o'chirish", callback_data="rem_ch")],
        [InlineKeyboardButton(text="📜 Ro'yxat", callback_data="list_ch")]
    ])

# --- ADMIN COMMANDS ---
@dp.message(Command("admin"))
async def admin_start(message: types.Message):
    async with await db_manager.connect() as db:
        async with db.execute("SELECT user_id FROM admins WHERE user_id=?", (message.from_user.id,)) as c:
            if await c.fetchone():
                await message.answer("🛠 Admin panelga xush kelibsiz!", reply_markup=get_admin_kb())

@dp.message(F.text == "📊 Statistika")
async def admin_stats(message: types.Message):
    async with await db_manager.connect() as db:
        async with db.execute("SELECT COUNT(*) FROM users") as c:
            total_users = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM cache") as c:
            total_cache = (await c.fetchone())[0]
        await message.answer(f"📈 **Bot statistikasi:**\n\n👤 Jami userlar: {total_users}\n💾 Keshlangan fayllar: {total_cache}\n📅 Sana: {datetime.now().date()}")

@dp.message(F.text == "👤 Foydalanuvchilar")
async def admin_users(message: types.Message):
    async with await db_manager.connect() as db:
        async with db.execute("SELECT user_id, username FROM users ORDER BY joined_date DESC LIMIT 20") as c:
            users = await c.fetchall()
            text = "🆔 **Oxirgi 20 ta foydalanuvchi:**\n\n"
            for i, u in enumerate(users, 1):
                user_tag = f"@{u[1]}" if u[1] else "Noma'lum"
                text += f"{i}. {user_tag} (ID: `{u[0]}`)\n"
            await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "⚙️ Bot Holati")
async def admin_status(message: types.Message):
    async with await db_manager.connect() as db:
        async with db.execute("SELECT value FROM settings WHERE key='bot_status'") as c:
            current = (await c.fetchone())[0]
            new_status = "off" if current == "on" else "on"
            await db.execute("UPDATE settings SET value=? WHERE key='bot_status'", (new_status,))
            await db.commit()
            await message.answer(f"🔄 Bot holati o'zgartirildi: **{new_status.upper()}**")

# --- REKLAMA TIZIMI ---
@dp.message(F.text == "✉️ Reklama tarqatish")
async def ads_init(message: types.Message, state: FSMContext):
    await message.answer("📣 Reklama xabarini yuboring. Bu xabar barcha userlarga boradi (Matn, rasm, video...):")
    await state.set_state(AdminStates.waiting_for_ads)

@dp.message(AdminStates.waiting_for_ads)
async def ads_handler(message: types.Message, state: FSMContext):
    await message.answer("🚀 Reklama tarqatish boshlandi...")
    async with await db_manager.connect() as db:
        async with db.execute("SELECT user_id FROM users") as c:
            users = await c.fetchall()
            success, fail = 0, 0
            for u in users:
                try:
                    await message.copy_to(u[0])
                    success += 1
                    if success % 50 == 0: await asyncio.sleep(1) # Flood limit protection
                except: fail += 1
            await message.answer(f"✅ Tugadi!\n\nYetkazildi: {success}\nBloklangan: {fail}")
    await state.clear()

# --- YUKLASH LOGIKASI ---
class Downloader:
    def __init__(self):
        self.common_opts = {
            'cookiefile': 'cookies.txt',
            'quiet': True,
            'no_warnings': True,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
        }

    async def download_video(self, url):
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

    async def download_audio(self, url):
        path = f"downloads/{int(datetime.now().timestamp())}.mp3"
        opts = {
            'format': 'bestaudio/best',
            'outtmpl': path[:-4],
            'postprocessors': [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3','preferredquality': '192'}],
            **self.common_opts
        }
        loop = asyncio.get_event_loop()
        with YoutubeDL(opts) as ydl:
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=True))
            return path, info.get('title', 'Audio')

downloader = Downloader()

@dp.message(F.text.contains("youtube.com") | F.text.contains("youtu.be") | F.text.contains("instagram.com"))
async def video_process(message: types.Message):
    url = message.text
    async with await db_manager.connect() as db:
        async with db.execute("SELECT file_id, title FROM cache WHERE url=?", (url,)) as c:
            cached = await c.fetchone()
            if cached:
                kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📥 Musiqani yuklash", callback_data=f"aud_dl_{url}")]])
                return await bot.send_video(message.chat.id, video=cached[0], caption=f"🎬 {cached[1]}\n\n📥 @{BOT_USERNAME} orqali yuklab olindi", reply_markup=kb)

    status_msg = await message.answer("🔍 Havola tekshirilmoqda...")
    try:
        if not os.path.exists('downloads'): os.makedirs('downloads')
        await status_msg.edit_text("📥 Video yuklab olinmoqda (hajmga qarab vaqt olishi mumkin)...")
        
        file_path, title = await downloader.download_video(url)
        await status_msg.edit_text("📤 Telegram serveriga yuklanmoqda...")
        
        sent = await bot.send_video(
            message.chat.id, 
            video=FSInputFile(file_path), 
            caption=f"🎬 {title}\n\n📥 @{BOT_USERNAME} orqali yuklab olindi",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📥 Musiqani yuklash", callback_data=f"aud_dl_{url}")]])
        )
        
        async with await db_manager.connect() as db:
            await db.execute("INSERT OR REPLACE INTO cache VALUES (?,?,?,?,?)", (url, sent.video.file_id, "video", title, 0))
            await db.commit()
        
        os.remove(file_path)
        await status_msg.delete()
    except Exception as e:
        logger.error(f"Download Error: {e}")
        await status_msg.edit_text("❌ Xatolik: Video juda katta yoki havola noto'g'ri.")

# --- CALLBACKS & STARTUP ---
@app.on_event("startup")
async def on_startup():
    await db_manager.setup()
    await bot.set_webhook(url=WEBHOOK_URL, drop_pending_updates=True)

@app.post(WEBHOOK_PATH)
async def bot_webhook(request: Request):
    update = Update.model_validate(await request.json(), context={"bot": bot})
    await dp.feed_update(bot, update)

@app.get("/")
async def index():
    return {"status": "Bot is flying 🚀"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)