import os
import asyncio
import logging
import aiosqlite
from aiogram import Bot, Dispatcher, F, types, BaseMiddleware
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.types import FSInputFile, CallbackQuery, Message, ReplyKeyboardRemove
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
import yt_dlp

# --- KONFIGURATSIYA (To'g'rilangan) ---
# Muhim: os.getenv ichida o'zgaruvchi nomi bo'ladi, qiymatning o'zi emas!
BOT_TOKEN = "8679344041:AAGS9_ugLxpyW2tFlPju5d7ZmEdiQ3qDIBM"
ADMIN_ID = 8553997595
RENDER_EXTERNAL_URL = "https://nyukla.onrender.com" 

WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}{WEBHOOK_PATH}"
PORT = int(os.getenv("PORT", 8080))

DB_FILE = "nyukla.db"
COOKIES_FILE = "cookies.txt"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# --- DATABASE (Mantiqiy optimallashtirildi) ---
async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT, full_name TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS channels (channel_id TEXT PRIMARY KEY, url TEXT, title TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('bot_active', '1')")
        await db.commit()

async def add_user(user_id, username, full_name):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("INSERT OR IGNORE INTO users (id, username, full_name) VALUES (?, ?, ?)", 
                         (user_id, username, full_name))
        await db.commit()

# --- UTILS (yt-dlp optimallash) ---
def get_ydl_opts(is_audio=False):
    opts = {
        'outtmpl': 'downloads/%(id)s.%(ext)s', 
        'quiet': True, 
        'no_warnings': True,
        'ignoreerrors': True,
        'no_check_certificate': True,
    }
    if os.path.exists(COOKIES_FILE):
        opts['cookiefile'] = COOKIES_FILE
    
    if is_audio:
        opts['format'] = 'bestaudio/best'
        opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]
    else:
        # Telegram 50MB limitini hisobga olgan holda format tanlash
        opts['format'] = 'best[filesize<50M]/bestvideo[height<=720]+bestaudio/best[height<=720]'
    return opts

async def download_media(url, is_audio=False):
    def sync_download():
        with yt_dlp.YoutubeDL(get_ydl_opts(is_audio)) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info: return None, None
            filename = ydl.prepare_filename(info)
            if is_audio:
                filename = filename.rsplit('.', 1)[0] + '.mp3'
            return filename, info.get('title', 'Media')
    return await asyncio.to_thread(sync_download)

# --- MIDDLEWARE (To'g'rilangan) ---
class CheckMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = event.from_user
        if not user: return await handler(event, data)
        
        await add_user(user.id, user.username, user.full_name)
        if user.id == ADMIN_ID: return await handler(event, data)

        # Bot holati
        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute("SELECT value FROM settings WHERE key='bot_active'") as c:
                row = await c.fetchone()
                if row and row[0] == '0':
                    await (event.answer("🔴 Bot vaqtinchalik o'chirilgan.") if isinstance(event, Message) else event.answer())
                    return

        # Obuna tekshiruvi
        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute("SELECT channel_id, url, title FROM channels") as c:
                channels = await c.fetchall()
        
        unsubbed = []
        for ch_id, url, title in channels:
            try:
                member = await bot.get_chat_member(chat_id=ch_id, user_id=user.id)
                if member.status in ['left', 'kicked', 'None']:
                    unsubbed.append((url, title))
            except:
                continue

        if unsubbed:
            builder = InlineKeyboardBuilder()
            for url, title in unsubbed:
                builder.button(text=f"📢 {title}", url=url)
            builder.button(text="✅ Tekshirish", callback_data="check_sub")
            builder.adjust(1)
            msg = "Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling!"
            if isinstance(event, Message):
                await event.answer(msg, reply_markup=builder.as_markup())
            return
        
        return await handler(event, data)

dp.message.middleware(CheckMiddleware())
dp.callback_query.middleware(CheckMiddleware())

# --- ADMIN STATES ---
class AdminStates(StatesGroup):
    broadcasting = State()
    add_ch_id = State()
    add_ch_url = State()
    add_ch_title = State()

# --- ADMIN KEYBOARDS ---
def admin_kb():
    b = ReplyKeyboardBuilder()
    b.button(text="👥 Foydalanuvchilar")
    b.button(text="📢 Xabar yuborish")
    b.button(text="⚙️ Kanallar")
    b.button(text="🔴/🟢 Bot Status")
    b.button(text="🏠 Asosiy menyu")
    b.adjust(2, 2, 1)
    return b.as_markup(resize_keyboard=True)

# --- HANDLERS ---
@dp.message(Command("admin"), F.from_user.id == ADMIN_ID)
async def admin_panel(m: Message):
    await m.answer("👑 Admin panel", reply_markup=admin_kb())

@dp.message(F.text == "🔴/🟢 Bot Status", F.from_user.id == ADMIN_ID)
async def toggle_status(m: Message):
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT value FROM settings WHERE key='bot_active'") as c:
            current = (await c.fetchone())[0]
        new = '0' if current == '1' else '1'
        await db.execute("UPDATE settings SET value=? WHERE key='bot_active'", (new,))
        await db.commit()
    await m.answer(f"Holat: {'🟢 Yoqildi' if new == '1' else '🔴 O`chirildi'}")

@dp.message(CommandStart())
async def start(m: Message):
    await m.answer("👋 Salom! Link yuboring yoki musiqa nomini yozing.")

@dp.message(F.text.regexp(r'(https?://[^\s]+)'))
async def video_dl(m: Message):
    wait = await m.answer("⏳ Yuklanmoqda...")
    try:
        os.makedirs("downloads", exist_ok=True)
        path, title = await download_media(m.text)
        if path and os.path.exists(path):
            await m.answer_video(FSInputFile(path), caption=f"🎬 {title}\n\n@NyuklaBot")
            os.remove(path)
        else:
            await m.answer("❌ Videoni yuklab bo'lmadi (Hajmi juda katta yoki link xato).")
    except Exception as e:
        logging.error(e)
        await m.answer("❌ Xatolik yuz berdi.")
    finally:
        await wait.delete()

# --- WEBHOOK & STARTUP ---
async def on_startup(bot: Bot):
    await init_db()
    await bot.set_webhook(url=WEBHOOK_URL, drop_pending_updates=True)

def main():
    app = web.Application()
    async def home(request): return web.Response(text="Bot Active!")
    app.router.add_get("/", home)
    
    handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    app.on_startup.append(on_startup)
    web.run_app(app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    main()