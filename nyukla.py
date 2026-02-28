import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from yt_dlp import YoutubeDL

# Loggingni yoqish (Render loglarida xatolarni ko'rish uchun)
logging.basicConfig(level=logging.INFO)

# --- SOZLAMALAR ---
TOKEN = os.getenv("8679344041:AAGVo6gwxoyjWOPCSb3ezdtfgwJ7PkhhQaM")
WEBHOOK_HOST = os.getenv("https://nyukla.onrender.com") 
WEBHOOK_PATH = f"/webhook/{TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
PORT = int(os.getenv("PORT", 8080))

bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- VIDEO YUKLASH FUNKSIYASI ---
def download_video(url):
    # Render'da faqat /tmp papkasiga yozishga ruxsat bor
    file_template = '/tmp/%(title)s.%(ext)s'
    
    ydl_opts = {
        'format': 'best[ext=mp4]/best',
        'outtmpl': file_template,
        'max_filesize': 48 * 1024 * 1024, # 48MB (Telegram limiti 50MB)
        'quiet': True,
        'no_warnings': True,
    }
    
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return ydl.prepare_filename(info)

# --- HANDLERLAR ---
@dp.message(Command("start"))
async def start_handler(message: types.Message):
    await message.answer("Salom! Link yuboring, men uni yuklab beraman. 📥")

@dp.message(F.text.contains("instagram.com") | F.text.contains("youtube.com") | F.text.contains("youtu.be"))
async def handle_video_links(message: types.Message):
    status_msg = await message.answer("Video tahlil qilinmoqda, kuting... ⏳")
    
    try:
        # Bloklanib qolmaslik uchun yuklashni alohida oqimda bajaramiz
        loop = asyncio.get_event_loop()
        file_path = await loop.run_in_executor(None, download_video, message.text)

        if os.path.exists(file_path):
            video = types.FSInputFile(file_path)
            await message.answer_video(video=video, caption="Tayyor! ✅")
            os.remove(file_path) # Faylni darhol o'chiramiz
        
        await status_msg.delete()
        
    except Exception as e:
        logging.error(f"Xatolik: {e}")
        await status_msg.edit_text(f"Kechirasiz, videoni yuklab bo'lmadi. ❌\nSiz yuborgan link yoki video hajmi juda katta bo'lishi mumkin.")

# --- WEBHOOK VA SERVER ---
async def on_startup(bot: Bot):
    await bot.set_webhook(WEBHOOK_URL)
    logging.info(f"Webhook o'rnatildi: {WEBHOOK_URL}")

def main():
    dp.startup.register(on_startup)
    app = web.Application()
    
    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
    )
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)
    
    setup_application(app, dp, bot=bot)
    
    # Render uchun 0.0.0.0 manzili shart
    web.run_app(app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    main()