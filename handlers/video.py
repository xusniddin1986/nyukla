import os
import asyncio
import tempfile
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import db

logger = logging.getLogger(__name__)

MAX_VIDEO_SIZE = 50 * 1024 * 1024  # 50MB Telegram limit


async def video_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    user = update.effective_user

    processing_msg = await update.message.reply_text("⏳ yuklanmoqda...")

    try:
        import yt_dlp

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "%(title).50s.%(ext)s")

            ydl_opts = {
                'outtmpl': output_path,
                'format': 'best[filesize<50M]/best[height<=720]/best',
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
                'merge_output_format': 'mp4',
            }

            # Get info first
            info_opts = {**ydl_opts, 'skip_download': True}
            loop = asyncio.get_event_loop()

            def get_info():
                with yt_dlp.YoutubeDL(info_opts) as ydl:
                    return ydl.extract_info(url, download=False)

            try:
                info = await loop.run_in_executor(None, get_info)
            except Exception as e:
                await processing_msg.edit_text(f"❌ Video ma'lumotlarini olishda xatolik: {str(e)[:100]}")
                return

            title = info.get('title', 'Video')[:50]
            duration = info.get('duration', 0)
            filesize = info.get('filesize') or info.get('filesize_approx') or 0

            if filesize > MAX_VIDEO_SIZE:
                await processing_msg.edit_text(
                    f"❌ Video hajmi juda katta ({filesize // (1024*1024)}MB).\n"
                    "Telegram 50MB gacha ruxsat beradi."
                )
                return

            # Download
            def download_video():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                # Find downloaded file
                for f in os.listdir(tmpdir):
                    fp = os.path.join(tmpdir, f)
                    if os.path.isfile(fp) and not f.endswith('.json'):
                        return fp
                return None

            await processing_msg.edit_text("⬇️ Video yuklanmoqda...")
            video_file = await loop.run_in_executor(None, download_video)

            if not video_file or not os.path.exists(video_file):
                await processing_msg.edit_text("❌ Video yuklab bo'lmadi.")
                return

            fsize = os.path.getsize(video_file)
            if fsize > MAX_VIDEO_SIZE:
                await processing_msg.edit_text(
                    f"❌ Yuklangan video hajmi katta ({fsize // (1024*1024)}MB). "
                    "50MB dan kichik videolarni yuboring."
                )
                return

            await processing_msg.edit_text("📤 Video Telegramga yuborilmoqda...")

            # Inline button for music extraction
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🎵 Musiqani yuklab olish", callback_data=f"music_from_video:{url}")]
            ])

            with open(video_file, 'rb') as vf:
                sent = await update.message.reply_video(
                    video=vf,
                    caption=f"📥 @NyuklaBot orqali yuklab olindi\n\n🎬 {title}",
                    reply_markup=keyboard,
                    supports_streaming=True
                )

            await processing_msg.delete()
            db.increment_downloads(user.id)

    except ImportError:
        await processing_msg.edit_text(
            "❌ yt-dlp o'rnatilmagan. "
            "Server administratoriga murojaat qiling."
        )
    except Exception as e:
        logger.error(f"Video download error: {e}")
        await processing_msg.edit_text(
            f"❌ Xatolik yuz berdi: {str(e)[:150]}\n\n"
            "Boshqa video linki bilan urinib ko'ring."
        )
