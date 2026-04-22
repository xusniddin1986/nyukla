import os
import asyncio
import tempfile
import logging
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import db

logger = logging.getLogger(__name__)

RESULTS_PER_PAGE = 5


async def search_youtube_music(query: str) -> list:
    """Search music on YouTube using yt-dlp."""
    try:
        import yt_dlp

        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'default_search': 'ytsearch10',
        }

        loop = asyncio.get_event_loop()

        def _search():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                result = ydl.extract_info(f"ytsearch10:{query}", download=False)
                return result.get('entries', [])[:10]

        entries = await loop.run_in_executor(None, _search)
        results = []
        for i, entry in enumerate(entries):
            if entry:
                duration = entry.get('duration', 0)
                mins = duration // 60 if duration else 0
                secs = duration % 60 if duration else 0
                results.append({
                    'id': entry.get('id', ''),
                    'title': entry.get('title', 'Noma\'lum')[:60],
                    'channel': entry.get('channel') or entry.get('uploader', 'Noma\'lum')[:30],
                    'duration': f"{mins}:{secs:02d}" if duration else "?:??",
                    'url': f"https://www.youtube.com/watch?v={entry.get('id', '')}"
                })
        return results
    except Exception as e:
        logger.error(f"Music search error: {e}")
        return []


def build_music_list(results: list, page: int = 0) -> tuple:
    """Build message text and keyboard for music results."""
    start = page * RESULTS_PER_PAGE
    end = start + RESULTS_PER_PAGE
    page_results = results[start:end]
    total_pages = (len(results) + RESULTS_PER_PAGE - 1) // RESULTS_PER_PAGE

    text = f"🎵 <b>Musiqa natijalari</b> (Sahifa {page + 1}/{total_pages}):\n\n"
    buttons = []

    for i, track in enumerate(page_results, start=start + 1):
        text += f"{i}. 🎶 <b>{track['title']}</b>\n"
        text += f"   👤 {track['channel']} | ⏱ {track['duration']}\n\n"
        buttons.append([InlineKeyboardButton(
            f"{i}. {track['title'][:35]}",
            callback_data=f"music_dl:{track['id']}"
        )])

    # Navigation buttons
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Oldingi", callback_data=f"page_{page - 1}"))
    if end < len(results):
        nav_buttons.append(InlineKeyboardButton("Keyingi ➡️", callback_data=f"page_{page + 1}"))
    if nav_buttons:
        buttons.append(nav_buttons)

    return text, InlineKeyboardMarkup(buttons)


async def music_search_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    if len(query) < 2:
        return

    user = update.effective_user
    searching_msg = await update.message.reply_text(f"🔍 <b>{query}</b> qidirilmoqda...", parse_mode='HTML')

    results = await search_youtube_music(query)

    if not results:
        await searching_msg.edit_text(
            "❌ Hech narsa topilmadi. Boshqa so'z bilan qidiring.",
            parse_mode='HTML'
        )
        return

    # Store results in user_data for pagination
    context.user_data['music_results'] = results
    context.user_data['music_query'] = query

    text, keyboard = build_music_list(results, 0)
    await searching_msg.edit_text(text, reply_markup=keyboard, parse_mode='HTML')
    db.increment_searches(user.id)


async def music_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("page_"):
        page = int(data.split("_")[1])
        results = context.user_data.get('music_results', [])
        if not results:
            await query.edit_message_text("❌ Qidiruv muddati tugadi. Qayta qidiring.")
            return
        text, keyboard = build_music_list(results, page)
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode='HTML')

    elif data.startswith("music_dl:"):
        video_id = data.split(":", 1)[1]
        await download_music(update, context, video_id)

    elif data.startswith("music_from_video:"):
        url = data.split(":", 1)[1]
        await query.edit_message_reply_markup(reply_markup=None)
        # Search music from video
        msg = await query.message.reply_text("🎵 Videodagi musiqa aniqlanmoqda...")
        results = await search_youtube_music(url)
        if not results:
            # Try direct extract
            results = await extract_music_info(url)

        if not results:
            await msg.edit_text("❌ Videoda musiqa topilmadi.")
            return

        context.user_data['music_results'] = results
        text, keyboard = build_music_list(results, 0)
        await msg.edit_text(text, reply_markup=keyboard, parse_mode='HTML')


async def extract_music_info(url: str) -> list:
    """Extract audio info from video URL."""
    try:
        import yt_dlp
        ydl_opts = {'quiet': True, 'no_warnings': True, 'skip_download': True}
        loop = asyncio.get_event_loop()

        def _get():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return info

        info = await loop.run_in_executor(None, _get)
        if info:
            duration = info.get('duration', 0)
            mins = duration // 60 if duration else 0
            secs = duration % 60 if duration else 0
            return [{
                'id': info.get('id', ''),
                'title': info.get('title', 'Noma\'lum')[:60],
                'channel': info.get('uploader', 'Noma\'lum')[:30],
                'duration': f"{mins}:{secs:02d}",
                'url': url
            }]
    except:
        pass
    return []


async def download_music(update: Update, context: ContextTypes.DEFAULT_TYPE, video_id: str):
    query = update.callback_query
    user = update.effective_user

    msg = await query.message.reply_text("🎵 Musiqa yuklanmoqda...")

    try:
        import yt_dlp
        url = f"https://www.youtube.com/watch?v={video_id}"

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "%(title).50s.%(ext)s")

            ydl_opts = {
                'outtmpl': output_path,
                'format': 'bestaudio/best',
                'quiet': True,
                'no_warnings': True,
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            }

            loop = asyncio.get_event_loop()

            # Get info
            info_opts = {**ydl_opts, 'skip_download': True, 'postprocessors': []}

            def get_info():
                with yt_dlp.YoutubeDL(info_opts) as ydl:
                    return ydl.extract_info(url, download=False)

            info = await loop.run_in_executor(None, get_info)
            title = info.get('title', 'Musiqa')[:50]
            artist = info.get('uploader') or info.get('artist', '')

            def download_audio():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                for f in os.listdir(tmpdir):
                    if f.endswith('.mp3'):
                        return os.path.join(tmpdir, f)
                # Find any audio file
                for f in os.listdir(tmpdir):
                    fp = os.path.join(tmpdir, f)
                    if os.path.isfile(fp):
                        return fp
                return None

            await msg.edit_text("⬇️ Audio yuklanmoqda...")
            audio_file = await loop.run_in_executor(None, download_audio)

            if not audio_file or not os.path.exists(audio_file):
                await msg.edit_text("❌ Musiqa yuklab bo'lmadi.")
                return

            fsize = os.path.getsize(audio_file)
            if fsize > 50 * 1024 * 1024:
                await msg.edit_text("❌ Audio fayl juda katta (50MB dan oshiq).")
                return

            await msg.edit_text("📤 Musiqa yuborilmoqda...")

            with open(audio_file, 'rb') as af:
                await query.message.reply_audio(
                    audio=af,
                    title=title,
                    performer=artist,
                    caption="@NyuklaBot orqali istagan musiqangizni tez va oson toping!"
                )

            await msg.delete()
            db.increment_downloads(user.id)

    except ImportError:
        await msg.edit_text("❌ yt-dlp o'rnatilmagan.")
    except Exception as e:
        logger.error(f"Music download error: {e}")
        await msg.edit_text(f"❌ Xatolik: {str(e)[:100]}")
