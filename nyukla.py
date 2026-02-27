import os
import asyncio
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import Update, FSInputFile
from aiogram.filters import Command
from yt_dlp import YoutubeDL

# Sozlamalar
BOT_TOKEN = os.getenv("8679344041:AAGVo6gwxoyjWOPCSb3ezdtfgwJ7PkhhQaM")
WEBHOOK_PATH = f"/bot/{BOT_TOKEN}"
RENDER_EXTERNAL_URL = os.getenv("https://nyukla.onrender.com") # Render avtomat beradi
WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}{WEBHOOK_PATH}"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
app = FastAPI()

# YouTube yuklovchi sozlamalari
YDL_OPTIONS = {
    'format': 'best[ext=mp4]/best',
    'outtmpl': 'downloads/%(id)s.%(ext)s',
    'max_filesize': 45 * 1024 * 1024, # 45MB (Telegram cheklovi uchun xavfsiz zona)
    'quiet': True,
    'no_warnings': True,
}

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.reply("Salom! Menga YouTube linkini yuboring, men uni tezda yuklab beraman. 🚀")

@dp.message(F.text.contains("youtube.com") | F.text.contains("youtu.be"))
async def handle_youtube(message: types.Message):
    status_msg = await message.answer("Video tahlil qilinmoqda... 📥")
    url = message.text
    
    try:
        if not os.path.exists('downloads'):
            os.makedirs('downloads')

        # Videoni yuklab olish (Blocking funksiyani asinxron ishga tushirish)
        loop = asyncio.get_event_loop()
        with YoutubeDL(YDL_OPTIONS) as ydl:
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=True))
            file_path = ydl.prepare_filename(info)

        await status_msg.edit_text("Video Telegramga yuklanmoqda... 📤")
        
        # Yuborish
        video = FSInputFile(file_path)
        await bot.send_video(chat_id=message.chat.id, video=video, caption=f"🎬 {info.get('title')}")
        
        # Tozalash
        os.remove(file_path)
        await status_msg.delete()

    except Exception as e:
        await status_msg.edit_text(f"Xatolik: Video juda katta yoki havola noto'g'ri. ❌")
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)

# Webhook sozlamalari
@app.on_event("startup")
async def on_startup():
    await bot.set_webhook(url=WEBHOOK_URL)

@app.on_event("shutdown")
async def on_shutdown():
    await bot.delete_webhook()

@app.post(WEBHOOK_PATH)
async def bot_webhook(request: Request):
    update = Update.model_validate(await request.json(), context={"bot": bot})
    await dp.feed_update(bot, update)