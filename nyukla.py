import asyncio
import logging
import sqlite3
import os
import yt_dlp
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, FSInputFile, ReplyKeyboardMarkup, KeyboardButton
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

# --- KONFIGURATSIYA ---
BOT_TOKEN = "8679344041:AAFPAOq1vlF7EXUNvN-3KdiAbA8z0LORINc"
ADMIN_ID = 8553997595 
PORT = int(os.environ.get("PORT", 8080))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "https://nyukla.onrender.com")

DOWNLOAD_DIR = "downloads"
COOKIE_FILE = "cookies.txt" # Cookies fayli nomi

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- BAZA (SQLITE) ---
conn = sqlite3.connect("bot_users.db")
cursor = conn.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, full_name TEXT)")
conn.commit()

def add_user(user_id, username, full_name):
    cursor.execute("INSERT OR IGNORE INTO users VALUES (?, ?, ?)", (user_id, username, full_name))
    conn.commit()

def get_users():
    cursor.execute("SELECT user_id, username, full_name FROM users")
    return cursor.fetchall()

# --- YARDAMCHI FUNKSIYALAR ---
async def download_media(url: str):
    # Cookies mavjudligini tekshiramiz
    cookie_args = {"cookiefile": COOKIE_FILE} if os.path.exists(COOKIE_FILE) else {}
    
    ydl_opts = {
        "format": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": f"{DOWNLOAD_DIR}/%(id)s.%(ext)s",
        "quiet": True,
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        **cookie_args # Cookies qo'shiladi
    }
    def _download():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            return ydl.prepare_filename(info)
    return await asyncio.to_thread(_download)

# --- HANDLERLAR ---
@dp.message(CommandStart())
async def cmd_start(message: Message):
    add_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
    if message.from_user.id == ADMIN_ID:
        await message.answer("Admin xush kelibsiz!", reply_markup=ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="📊 Statistika")],
            [KeyboardButton(text="📢 Xabar yuborish")]
        ], resize_keyboard=True))
    else:
        await message.answer("Salom! Menga YouTube yoki Instagram havolasini yuboring.")

@dp.message(F.text == "📊 Statistika")
async def show_stats(message: Message):
    if message.from_user.id == ADMIN_ID:
        users = get_users()
        await message.answer(f"👥 Jami foydalanuvchilar: {len(users)}")

@dp.message(F.text == "📢 Xabar yuborish")
async def start_broadcast(message: Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("Yubormoqchi bo'lgan xabaringizni yuboring (reply qiling):")

@dp.message(F.video | F.photo | F.text | F.audio)
async def handle_everything(message: Message):
    # Broadcast logikasi
    if message.from_user.id == ADMIN_ID and message.reply_to_message:
        users = get_users()
        for user in users:
            try:
                if message.text: await bot.send_message(user[0], message.text)
                elif message.video: await bot.send_video(user[0], message.video.file_id, caption=message.caption)
                elif message.photo: await bot.send_photo(user[0], message.photo[-1].file_id, caption=message.caption)
                elif message.audio: await bot.send_audio(user[0], message.audio.file_id, caption=message.caption)
            except: continue
        await message.answer("✅ Xabar yuborildi.")
        return

    # Yuklash logikasi (Linklar)
    if any(site in message.text for site in ["youtube.com", "youtu.be", "instagram.com"]):
        status_msg = await message.answer("⏳ Yuklanmoqda...")
        try:
            file_path = await download_media(message.text)
            await bot.send_video(message.chat.id, video=FSInputFile(file_path))
            await status_msg.delete()
            if os.path.exists(file_path): os.remove(file_path)
        except Exception as e:
            await status_msg.edit_text(f"❌ Xatolik yuz berdi. \n\nEhtimol `cookies.txt` fayli yo'q yoki video cheklangan.\n\nTexnik xato: {e}")

# --- WEBHOOK ---
async def main():
    bot_info = await bot.get_me()
    logging.info(f"Bot ishga tushdi: {bot_info.username}")
    
    app = web.Application()
    webhook_requests_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_requests_handler.register(app, path="/webhook")
    setup_application(app, dp, bot=bot)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    
    # Webhookni o'rnatish
    await bot.set_webhook(f"{WEBHOOK_URL}/webhook")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())