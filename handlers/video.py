import os
import asyncio
import tempfile
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import db

logger = logging.getLogger(__name__)


async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    user = update.effective_user
    msg = await update.message.reply_text("⏳ Video yuklanmoqda...")

    try:
        import yt_dlp

        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "%(title).50s.%(ext)s")

            def get_info():
                opts = {'quiet': True, 'no_warnings': True, 'skip_download': True}
                with yt_dlp.YoutubeDL(opts) as ydl:
                    return ydl.extract_info(url, download=False)

            loop = asyncio.get_event_loop()
            try:
                info = await loop.run_in_executor(None, get_info)
            except Exception as e:
                await msg.edit_text(f"❌ Link ochilmadi: {str(e)[:150]}")
                return

            title = info.get('title', 'Video')[:50]
            filesize = info.get('filesize') or info.get('filesize_approx') or 0
            if filesize > 50 * 1024 * 1024:
                await msg.edit_text(f"❌ Video hajmi katta ({filesize//(1024*1024)}MB). Max 50MB.")
                return

            def download():
                opts = {
                    'outtmpl': out,
                    'format': 'best[filesize<50M]/best[height<=720]/best',
                    'quiet': True,
                    'no_warnings': True,
                    'merge_output_format': 'mp4',
                }
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([url])
                for f in os.listdir(tmp):
                    fp = os.path.join(tmp, f)
                    if os.path.isfile(fp):
                        return fp
                return None

            await msg.edit_text("⬇️ Yuklanmoqda...")
            video_file = await loop.run_in_executor(None, download)

            if not video_file:
                await msg.edit_text("❌ Fayl topilmadi.")
                return

            if os.path.getsize(video_file) > 50 * 1024 * 1024:
                await msg.edit_text("❌ Fayl 50MB dan katta.")
                return

            await msg.edit_text("📤 Telegramga yuborilmoqda...")

            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("🎵 Musiqani yuklab olish", callback_data=f"music_from_video:{url}")
            ]])

            with open(video_file, 'rb') as f:
                await update.message.reply_video(
                    video=f,
                    caption=f"📥 @NyuklaBot orqali yuklab olindi\n\n🎬 {title}",
                    reply_markup=kb,
                    supports_streaming=True
                )
            await msg.delete()
            db.inc_download(user.id)

    except ImportError:
        await msg.edit_text("❌ yt-dlp o'rnatilmagan.")
    except Exception as e:
        logger.error(f"Video error: {e}")
        await msg.edit_text(f"❌ Xatolik: {str(e)[:150]}")
