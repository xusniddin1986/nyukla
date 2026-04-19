import logging
import os
import asyncio
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.filters import CommandStart
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiogram.exceptions import TelegramAPIError
from aiohttp import web
import yt_dlp

# --- KONFIGURATSIYA VA O'ZGARUVCHILAR ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "8679344041:AAGS9_ugLxpyW2tFlPju5d7ZmEdiQ3qDIBM")
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "https://nyukla.onrender.com") # Render.com bergan manzil
WEBHOOK_PATH = f"/webhook/{8679344041:AAGS9_ugLxpyW2tFlPju5d7ZmEdiQ3qDIBM}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

# Render.com tomonidan avtomatik taqdim etiladigan port
WEBAPP_HOST = "0.0.0.0"
WEBAPP_PORT = int(os.getenv("PORT", 10000))

# Kelajakda obuna tekshiruvi va admin nazorati uchun o'zgaruvchilar
REQUIRED_CHANNEL = os.getenv("REQUIRED_CHANNEL", "-1002980992642") 
ADMIN_ID = os.getenv("ADMIN_ID", "8553997595")

# Loglarni sozlash
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()

# Yuklab olingan fayllar uchun papka
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Cookie faylni tekshirish
COOKIE_FILE = "cookies.txt" if os.path.exists("cookies.txt") else None

# --- YARDAMCHI ASINXRON FUNKSIYALAR (DRY Yondashuv) ---
async def fetch_media_info(query: str, search_type: str = 'video'):
    """yt-dlp yordamida media ma'lumotlarini asinxron tarzda olish"""
    ydl_opts = {
        'format': 'best',
        'quiet': True,
        'cookiefile': COOKIE_FILE,
        'noplaylist': True,
    }
    
    if search_type == 'music_search':
        ydl_opts.update({
            'extract_flat': 'in_playlist',
            'default_search': 'ytsearch5',
        })
        
    def _extract():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(query, download=False)
            
    return await asyncio.to_thread(_extract)

async def download_media(url: str, is_audio: bool = False):
    """Media faylni yuklab olish va fayl nomini qaytarish"""
    filename_template = f"{DOWNLOAD_DIR}/%(id)s.%(ext)s"
    
    ydl_opts = {
        'outtmpl': filename_template,
        'quiet': True,
        'cookiefile': COOKIE_FILE,
    }
    
    if is_audio:
        ydl_opts.update({
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        })
    else:
        # Video hajmi Telegram limitiga tushishi uchun (max 50MB)
        ydl_opts.update({'format': 'best[filesize<50M]/best'})

    def _download():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            # Fayl nomini olish
            return ydl.prepare_filename(info).rsplit('.', 1)[0] + ('.mp3' if is_audio else f".{info['ext']}")

    return await asyncio.to_thread(_download)

# --- HANDLERLAR ---

@router.message(CommandStart())
async def cmd_start(message: Message):
    welcome_text = (
        "👋 Salom! Men Nyukla botman.\n\n"
        "🔗 *Instagram yoki YouTube* havolasini yuboring (video yuklab beraman).\n"
        "🎵 Yoki *musiqa/qo'shiqchi nomini* yozing (musiqa topib beraman)."
    )
    await message.answer(welcome_text, parse_mode="Markdown")

# Havolalarni ushlab qoluvchi (Video yuklash)
@router.message(F.text.regexp(r"(https?://)?(www\.)?(youtube\.com|youtu\.be|instagram\.com)/.+"))
async def handle_video_link(message: Message):
    wait_msg = await message.answer("⏳ Video qidirilmoqda, kuting...")
    try:
        file_path = await download_media(message.text, is_audio=False)
        video = FSInputFile(file_path)
        caption = "📥 @NyuklaBot orqali yuklab olindi"
        
        await bot.send_video(
            chat_id=message.chat.id,
            video=video,
            caption=caption
        )
        os.remove(file_path) # Server joyini tejash uchun
    except Exception as e:
        logger.error(f"Video yuklashda xatolik: {e}")
        await message.answer("❌ Videoni yuklab olishda xatolik yuz berdi. Fayl hajmi juda katta bo'lishi mumkin.")
    finally:
        await wait_msg.delete()

# Musiqa qidiruv (Matn yozilganda)
@router.message(F.text & ~F.text.startswith("/"))
async def handle_music_search(message: Message):
    wait_msg = await message.answer("🔍 Musiqa qidirilmoqda...")
    try:
        results = await fetch_media_info(message.text, search_type='music_search')
        entries = results.get('entries', [])
        
        if not entries:
            await wait_msg.edit_text("❌ Hech narsa topilmadi.")
            return

        keyboard = []
        for entry in entries[:5]: # Eng yaxshi 5 ta natija
            title = entry.get('title', 'Noma\'lum')
            video_id = entry.get('id')
            # Callback data ga faqat ID saqlaymiz (limit sababli)
            keyboard.append([InlineKeyboardButton(text=f"🎵 {title}", callback_data=f"dl_audio:{video_id}")])
            
        markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        await wait_msg.edit_text(
            "👇 Quyidagilardan birini tanlang:",
            reply_markup=markup
        )
    except Exception as e:
        logger.error(f"Qidiruvda xatolik: {e}")
        await wait_msg.edit_text("❌ Qidiruv tizimida xatolik yuz berdi.")

# Musiqa yuklash tugmasi bosilganda
@router.callback_query(F.data.startswith("dl_audio:"))
async def process_audio_download(callback: CallbackQuery):
    video_id = callback.data.split(":")[1]
    url = f"https://www.youtube.com/watch?v={video_id}"
    
    await callback.message.edit_text("⏳ Musiqa yuklanmoqda, iltimos kuting...")
    
    try:
        file_path = await download_media(url, is_audio=True)
        audio = FSInputFile(file_path)
        caption = "@NyuklaBot orqali istagan musiqangizni tez va oson toping!"
        
        await bot.send_audio(
            chat_id=callback.message.chat.id,
            audio=audio,
            caption=caption
        )
        os.remove(file_path) # Tozalash
        await callback.message.delete()
    except Exception as e:
        logger.error(f"Audio yuklashda xatolik: {e}")
        await callback.message.edit_text("❌ Musiqani yuklab olishda xatolik yuz berdi.")

# --- WEBHOOK SETUP (Render.com uchun) ---
async def on_startup(bot: Bot):
    await bot.set_webhook(WEBHOOK_URL)
    logger.info(f"Webhook o'rnatildi: {WEBHOOK_URL}")

def main():
    dp.include_router(router)
    dp.startup.register(on_startup)
    
    app = web.Application()
    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
    )
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)
    
    setup_application(app, dp, bot=bot)
    
    logger.info(f"Server {WEBAPP_HOST}:{WEBAPP_PORT} da ishga tushirilmoqda...")
    web.run_app(app, host=WEBAPP_HOST, port=WEBAPP_PORT)

if __name__ == "__main__":
    main()