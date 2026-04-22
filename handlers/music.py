import os
import asyncio
import tempfile
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import db

logger = logging.getLogger(__name__)
PER_PAGE = 5


async def yt_search(query: str) -> list:
    try:
        import yt_dlp
        loop = asyncio.get_event_loop()

        def _do():
            opts = {'quiet': True, 'no_warnings': True, 'extract_flat': True}
            with yt_dlp.YoutubeDL(opts) as ydl:
                res = ydl.extract_info(f"ytsearch10:{query}", download=False)
                return res.get('entries', [])

        entries = await loop.run_in_executor(None, _do)
        out = []
        for e in entries:
            if not e:
                continue
            dur = e.get('duration', 0) or 0
            out.append({
                'id': e.get('id', ''),
                'title': (e.get('title') or 'Noma\'lum')[:60],
                'channel': (e.get('channel') or e.get('uploader') or 'Noma\'lum')[:30],
                'duration': f"{dur//60}:{dur%60:02d}" if dur else "?",
            })
        return out
    except Exception as e:
        logger.error(f"Search error: {e}")
        return []


def build_list(results, page):
    start = page * PER_PAGE
    items = results[start:start + PER_PAGE]
    total = (len(results) + PER_PAGE - 1) // PER_PAGE

    text = f"🎵 <b>Natijalar</b> ({page+1}/{total}):\n\n"
    btns = []
    for i, t in enumerate(items, start=start + 1):
        text += f"{i}. 🎶 <b>{t['title']}</b>\n   👤 {t['channel']} | ⏱ {t['duration']}\n\n"
        btns.append([InlineKeyboardButton(f"{i}. {t['title'][:40]}", callback_data=f"music_dl:{t['id']}")])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"page_{page-1}"))
    if start + PER_PAGE < len(results):
        nav.append(InlineKeyboardButton("➡️", callback_data=f"page_{page+1}"))
    if nav:
        btns.append(nav)

    return text, InlineKeyboardMarkup(btns)


async def handle_music_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    if len(query) < 2:
        return
    msg = await update.message.reply_text(f"🔍 <b>{query}</b> qidirilmoqda...", parse_mode='HTML')
    results = await yt_search(query)
    if not results:
        await msg.edit_text("❌ Hech narsa topilmadi.")
        return
    context.user_data['music'] = results
    text, kb = build_list(results, 0)
    await msg.edit_text(text, reply_markup=kb, parse_mode='HTML')
    db.inc_search(update.effective_user.id)


async def handle_music_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data

    if data.startswith("page_"):
        page = int(data.split("_")[1])
        results = context.user_data.get('music', [])
        if not results:
            await q.edit_message_text("❌ Qayta qidiring.")
            return
        text, kb = build_list(results, page)
        await q.edit_message_text(text, reply_markup=kb, parse_mode='HTML')

    elif data.startswith("music_dl:"):
        vid_id = data.split(":", 1)[1]
        await download_music(update, context, vid_id)

    elif data.startswith("music_from_video:"):
        url = data.split(":", 1)[1]
        try:
            await q.edit_message_reply_markup(reply_markup=None)
        except:
            pass
        msg = await q.message.reply_text("🎵 Videodagi musiqa aniqlanmoqda...")
        results = await yt_search(url)
        if not results:
            await msg.edit_text("❌ Musiqa topilmadi.")
            return
        context.user_data['music'] = results
        text, kb = build_list(results, 0)
        await msg.edit_text(text, reply_markup=kb, parse_mode='HTML')


async def download_music(update: Update, context: ContextTypes.DEFAULT_TYPE, vid_id: str):
    q = update.callback_query
    user = q.from_user
    msg = await q.message.reply_text("🎵 Musiqa yuklanmoqda...")

    try:
        import yt_dlp
        url = f"https://www.youtube.com/watch?v={vid_id}"

        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "%(title).50s.%(ext)s")

            def get_info():
                with yt_dlp.YoutubeDL({'quiet': True, 'skip_download': True}) as ydl:
                    return ydl.extract_info(url, download=False)

            loop = asyncio.get_event_loop()
            info = await loop.run_in_executor(None, get_info)
            title = (info.get('title') or 'Musiqa')[:50]
            artist = info.get('uploader') or info.get('artist') or ''

            def dl():
                opts = {
                    'outtmpl': out,
                    'format': 'bestaudio/best',
                    'quiet': True,
                    'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}],
                }
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([url])
                for f in os.listdir(tmp):
                    if f.endswith('.mp3'):
                        return os.path.join(tmp, f)
                for f in os.listdir(tmp):
                    fp = os.path.join(tmp, f)
                    if os.path.isfile(fp):
                        return fp
                return None

            await msg.edit_text("⬇️ Audio yuklanmoqda...")
            audio = await loop.run_in_executor(None, dl)

            if not audio:
                await msg.edit_text("❌ Audio yuklab bo'lmadi.")
                return

            if os.path.getsize(audio) > 50 * 1024 * 1024:
                await msg.edit_text("❌ Audio 50MB dan katta.")
                return

            await msg.edit_text("📤 Yuborilmoqda...")
            with open(audio, 'rb') as f:
                await q.message.reply_audio(
                    audio=f,
                    title=title,
                    performer=artist,
                    caption="@NyuklaBot orqali istagan musiqangizni tez va oson toping!"
                )
            await msg.delete()
            db.inc_download(user.id)

    except Exception as e:
        logger.error(f"Music dl error: {e}")
        await msg.edit_text(f"❌ Xatolik: {str(e)[:150]}")
