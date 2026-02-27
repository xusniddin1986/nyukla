import os
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from yt_dlp import YoutubeDL

# Bot tokeningizni shu yerga yozing
BOT_TOKEN = '8679344041:AAGVo6gwxoyjWOPCSb3ezdtfgwJ7PkhhQaM'

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Video yuklash funksiyasi
def download_video(url):
    ydl_opts = {
        'format': 'best[ext=mp4]/best',  # Eng yaxshi sifatli mp4 format
        'outtmpl': 'downloads/%(title)s.%(ext)s',  # Yuklash manzili
        'max_filesize': 50 * 1024 * 1024,  # Maksimal 50MB (Telegram limiti uchun)
    }
    
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return ydl.prepare_filename(info)

@dp.message(Command("start"))
async def start_handler(message: types.Message):
    await message.answer("Salom! Menga YouTube linkini yuboring va men uni yuklab beraman. 📥")

@dp.message(F.text.contains("youtube.com") | F.text.contains("youtu.be"))
async def handle_youtube_link(message: types.Message):
    wait_msg = await message.answer("Video qayta ishlanmoqda, kuting... ⏳")
    url = message.text

    try:
        # Faylni yuklab olish (alohida thread'da bajarish tavsiya etiladi)
        loop = asyncio.get_event_loop()
        file_path = await loop.run_in_executor(None, download_video, url)

        # Videoni Telegramga yuborish
        video_file = types.FSInputFile(file_path)
        await bot.send_video(chat_id=message.chat.id, video=video_file, caption="Mana sizning videongiz! ✅")
        
        # Xabarni o'chirish va faylni tozalash
        await wait_msg.delete()
        os.remove(file_path)

    except Exception as e:
        await wait_msg.edit_text(f"Xatolik yuz berdi: {str(e)}")

async def main():
    if not os.path.exists('downloads'):
        os.makedirs('downloads')
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())