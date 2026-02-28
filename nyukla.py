import os
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.webhook.urls import TokenWebhookProjection
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from yt_dlp import YoutubeDL

# --- SOZLAMALAR ---
TOKEN = os.getenv("8679344041:AAGVo6gwxoyjWOPCSb3ezdtfgwJ7PkhhQaM")  # Render Env Variables'dan oladi
WEBHOOK_HOST = os.getenv("https://nyukla.onrender.com")  # Render avtomat beradi
WEBHOOK_PATH = f"/webhook/{TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

# Port Render tomonidan beriladi, bo'lmasa 8080 ishlatiladi
PORT = int(os.getenv("PORT", 8080))

bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- VIDEO YUKLASH FUNKSIYASI ---
def download_video(url):
    ydl_opts = {
        'format': 'best[ext=mp4]/best',
        'outtmpl': '/tmp/%(title)s.%(ext)s', # Renderda faqat /tmp papkasiga yozish mumkin
        'max_filesize': 45 * 1024 * 1024,
    }
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return ydl.prepare_filename(info)

@dp.message(Command("start"))
async def start_handler(message: types.Message):
    await message.answer("Salom! Render'da ishlayotgan botga link yuboring.")

@dp.message()
async def handle_message(message: types.Message):
    url = message.text
    if "youtube.com" in url or "youtu.be" in url or "instagram.com" in url:
        msg = await message.answer("Yuklanmoqda...")
        try:
            loop = asyncio.get_event_loop()
            file_path = await loop.run_in_executor(None, download_video, url)
            
            video_file = types.FSInputFile(file_path)
            await message.answer_video(video=video_file)
            
            os.remove(file_path)
            await msg.delete()
        except Exception as e:
            await message.answer(f"Xato: {str(e)}")

# --- WEBHOOK SOZLAMALARI ---
async def on_startup(bot: Bot):
    await bot.set_webhook(WEBHOOK_URL)

def main():
    dp.startup.register(on_startup)
    app = web.Application()
    
    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
    )
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)
    
    setup_application(app, dp, bot=bot)
    web.run_app(app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    main()