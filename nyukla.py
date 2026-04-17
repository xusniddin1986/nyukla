import os
import asyncio
import logging
import sqlite3
import aiosqlite
from aiogram import Bot, Dispatcher, F, types, BaseMiddleware
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.types import FSInputFile, CallbackQuery, Message, ReplyKeyboardRemove
from aiohttp import web
import yt_dlp

# --- SOZLAMALAR ---
BOT_TOKEN = os.getenv("8679344041:AAGS9_ugLxpyW2tFlPju5d7ZmEdiQ3qDIBM")
ADMIN_ID = int(os.getenv("8553997595", 0)) # SIZNING TELEGRAM ID RAQAMINGIZ
PORT = int(os.getenv("PORT", 8080))
COOKIES_FILE = "cookies.txt"
DB_FILE = "nyukla.db"

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# --- MA'LUMOTLAR BAZASI (SQLite) ---
async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT, full_name TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS channels (channel_id TEXT PRIMARY KEY, url TEXT, title TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        # Bot holatini standart yoqilgan qilish
        await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('bot_active', '1')")
        await db.commit()

async def add_user(user_id, username, full_name):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("INSERT OR IGNORE INTO users (id, username, full_name) VALUES (?, ?, ?)", 
                         (user_id, username, full_name))
        await db.commit()

async def get_bot_status():
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT value FROM settings WHERE key='bot_active'") as cursor:
            row = await cursor.fetchone()
            return row[0] == '1' if row else True

async def toggle_bot_status():
    current = await get_bot_status()
    new_status = '0' if current else '1'
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE settings SET value=? WHERE key='bot_active'", (new_status,))
        await db.commit()
    return new_status == '1'

async def get_channels():
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT channel_id, url, title FROM channels") as cursor:
            return await cursor.fetchall()

# --- HOLATLAR MASHINASI (FSM) ---
class AdminStates(StatesGroup):
    broadcasting = State()
    add_channel_id = State()
    add_channel_url = State()
    add_channel_title = State()
    delete_channel = State()

# --- YORDAMCHI FUNKSIYALAR (yt-dlp) ---
# (Oldingi koddan o'zgarishsiz olingan)
def get_ydl_opts(is_audio=False):
    opts = {'outtmpl': 'downloads/%(id)s.%(ext)s', 'quiet': True, 'no_warnings': True}
    if os.path.exists(COOKIES_FILE): opts['cookiefile'] = COOKIES_FILE
    if is_audio:
        opts['format'] = 'bestaudio/best'
        opts['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}]
    else:
        opts['format'] = 'best[filesize<50M]/bestvideo[filesize<40M]+bestaudio/best'
    return opts

def download_media_sync(url, is_audio=False):
    with yt_dlp.YoutubeDL(get_ydl_opts(is_audio)) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        if is_audio: filename = filename.rsplit('.', 1)[0] + '.mp3'
        return filename, info.get('title', 'Media')

def search_music_sync(query):
    opts = {'extract_flat': True, 'quiet': True}
    if os.path.exists(COOKIES_FILE): opts['cookiefile'] = COOKIES_FILE
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"ytsearch5:{query}", download=False)
        return info.get('entries', [])[:5]

async def download_media(url, is_audio=False): return await asyncio.to_thread(download_media_sync, url, is_audio)
async def search_music(query): return await asyncio.to_thread(search_music_sync, query)

# --- MAJBURIY OBUNA VA HOLAT TEKSHIRUVI (MIDDLEWARE) ---
class CheckMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = event.from_user
        if not user: return await handler(event, data)
        
        # Foydalanuvchini bazaga qo'shish
        await add_user(user.id, user.username, user.full_name)

        if user.id == ADMIN_ID:
            return await handler(event, data) # Adminga hamma narsa mumkin

        # 1. Bot holatini tekshirish
        is_active = await get_bot_status()
        if not is_active:
            text = "🔴 Uzr, bot hozircha o'chirilgan. Texnik ishlar olib borilmoqda."
            if isinstance(event, Message): await event.answer(text)
            elif isinstance(event, CallbackQuery): await event.message.answer(text)
            return

        # 2. Majburiy obunani tekshirish
        channels = await get_channels()
        unsubbed = []
        for ch_id, url, title in channels:
            try:
                member = await bot.get_chat_member(chat_id=ch_id, user_id=user.id)
                if member.status in ['left', 'kicked']:
                    unsubbed.append((url, title))
            except Exception as e:
                logging.error(f"Kanal tekshirishda xato ({ch_id}): {e}")
                pass # Bot kanalda admin bo'lmasa o'tkazib yuboradi

        if unsubbed:
            builder = InlineKeyboardBuilder()
            for url, title in unsubbed:
                builder.button(text=f"📢 {title}", url=url)
            builder.button(text="✅ Tekshirish", callback_data="check_sub")
            builder.adjust(1)
            
            text = "Botdan foydalanish uchun quyidagi kanallarga obuna bo'lishingiz shart! 👇"
            if isinstance(event, Message):
                await event.answer(text, reply_markup=builder.as_markup())
            elif isinstance(event, CallbackQuery) and event.data != "check_sub":
                await event.message.answer(text, reply_markup=builder.as_markup())
            return # Obuna bo'lmaguncha o'tkazmaydi

        return await handler(event, data)

dp.message.middleware(CheckMiddleware())
dp.callback_query.middleware(CheckMiddleware())


# --- KEYBOARDLAR ---
def get_admin_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.button(text="👥 Foydalanuvchilar statistikasi")
    builder.button(text="📢 Xabar yuborish")
    builder.button(text="⚙️ Kanallarni sozlash")
    builder.button(text="🔴/🟢 Botni Yoqish/O'chirish")
    builder.button(text="🏠 Asosiy menyu")
    builder.adjust(2, 2, 1)
    return builder.as_markup(resize_keyboard=True)

def get_channels_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Kanal qo'shish", callback_data="admin_add_channel")
    builder.button(text="➖ Kanalni o'chirish", callback_data="admin_del_channel")
    builder.button(text="📋 Kanallar ro'yxati", callback_data="admin_list_channels")
    builder.adjust(1)
    return builder.as_markup()

# --- ADMIN PANEL HANDLERLARI ---
@dp.message(Command("admin"), F.from_user.id == ADMIN_ID)
async def admin_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("👑 Admin panelga xush kelibsiz!", reply_markup=get_admin_keyboard())

@dp.message(F.text == "🏠 Asosiy menyu", F.from_user.id == ADMIN_ID)
async def admin_home(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Asosiy menyudasiz.", reply_markup=ReplyKeyboardRemove())
    await start_cmd(message)

@dp.message(F.text == "🔴/🟢 Botni Yoqish/O'chirish", F.from_user.id == ADMIN_ID)
async def admin_toggle_bot(message: Message):
    new_status = await toggle_bot_status()
    status_text = "🟢 YOQILGAN" if new_status else "🔴 O'CHIRILGAN"
    await message.answer(f"Bot holati o'zgardi. Hozirgi holat: {status_text}")

@dp.message(F.text == "👥 Foydalanuvchilar statistikasi", F.from_user.id == ADMIN_ID)
async def admin_stats(message: Message):
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT id, username, full_name FROM users") as cursor:
            users = await cursor.fetchall()
            
    if not users:
        return await message.answer("Hozircha foydalanuvchilar yo'q.")
    
    # Ro'yxat uzun bo'lsa .txt qilib yuboramiz
    text_content = f"Jami foydalanuvchilar: {len(users)}\n\n"
    for i, user in enumerate(users, 1):
        un = f"@{user[1]}" if user[1] else "Yo'q"
        text_content += f"{i}. {user[2]} | {un} | ID: {user[0]}\n"
        
    file_path = "users_stat.txt"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(text_content)
        
    await message.answer_document(FSInputFile(file_path), caption=f"📊 Jami foydalanuvchilar: {len(users)}")
    os.remove(file_path)

# --- XABAR YUBORISH (BROADCAST) ---
@dp.message(F.text == "📢 Xabar yuborish", F.from_user.id == ADMIN_ID)
async def admin_broadcast_start(message: Message, state: FSMContext):
    await message.answer("Yuboriladigan xabarni (matn, rasm, video, audio) yuboring.\nBekor qilish uchun /cancel bosing.")
    await state.set_state(AdminStates.broadcasting)

@dp.message(Command("cancel"), F.from_user.id == ADMIN_ID)
async def cancel_state(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Jarayon bekor qilindi.", reply_markup=get_admin_keyboard())

@dp.message(AdminStates.broadcasting, F.from_user.id == ADMIN_ID)
async def admin_broadcast_send(message: Message, state: FSMContext):
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT id FROM users") as cursor:
            users = await cursor.fetchall()
    
    await message.answer(f"⏳ Xabar {len(users)} ta foydalanuvchiga yuborilmoqda...")
    success, fail = 0, 0
    
    for user in users:
        try:
            await message.send_copy(chat_id=user[0])
            success += 1
            await asyncio.sleep(0.05) # Telegram limitiga tushmaslik uchun
        except Exception:
            fail += 1
            
    await message.answer(f"✅ Xabar yuborish tugadi.\nMuvaqqiyatli: {success}\nXatolik: {fail}", reply_markup=get_admin_keyboard())
    await state.clear()

# --- KANALLARNI BOSHQARISH ---
@dp.message(F.text == "⚙️ Kanallarni sozlash", F.from_user.id == ADMIN_ID)
async def admin_channels_menu(message: Message):
    await message.answer("Kanallarni boshqarish bo'limi:", reply_markup=get_channels_keyboard())

@dp.callback_query(F.data == "admin_list_channels", F.from_user.id == ADMIN_ID)
async def admin_list_channels(call: CallbackQuery):
    channels = await get_channels()
    if not channels:
        return await call.message.edit_text("Kanallar yo'q.", reply_markup=get_channels_keyboard())
    
    text = "Hozirgi kanallar:\n\n"
    for ch_id, url, title in channels:
        text += f"Nom: {title}\nID: {ch_id}\nURL: {url}\n\n"
    await call.message.edit_text(text, reply_markup=get_channels_keyboard(), disable_web_page_preview=True)

@dp.callback_query(F.data == "admin_add_channel", F.from_user.id == ADMIN_ID)
async def admin_add_ch_start(call: CallbackQuery, state: FSMContext):
    await call.message.answer("Kanal ID sini yuboring (masalan: -1001234567890).\nEslatma: Bot kanalda admin bo'lishi shart!")
    await state.set_state(AdminStates.add_channel_id)

@dp.message(AdminStates.add_channel_id, F.from_user.id == ADMIN_ID)
async def admin_add_ch_id(message: Message, state: FSMContext):
    await state.update_data(ch_id=message.text)
    await message.answer("Endi kanal URLsini (linkini) yuboring:")
    await state.set_state(AdminStates.add_channel_url)

@dp.message(AdminStates.add_channel_url, F.from_user.id == ADMIN_ID)
async def admin_add_ch_url(message: Message, state: FSMContext):
    await state.update_data(ch_url=message.text)
    await message.answer("Kanalning ko'rinadigan nomini yuboring (masalan: Nyukla Rasmiy):")
    await state.set_state(AdminStates.add_channel_title)

@dp.message(AdminStates.add_channel_title, F.from_user.id == ADMIN_ID)
async def admin_add_ch_title(message: Message, state: FSMContext):
    data = await state.get_data()
    ch_id, ch_url, ch_title = data['ch_id'], data['ch_url'], message.text
    
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("INSERT OR REPLACE INTO channels (channel_id, url, title) VALUES (?, ?, ?)", 
                         (ch_id, ch_url, ch_title))
        await db.commit()
        
    await message.answer("✅ Kanal muvaffaqiyatli qo'shildi!", reply_markup=get_admin_keyboard())
    await state.clear()

@dp.callback_query(F.data == "admin_del_channel", F.from_user.id == ADMIN_ID)
async def admin_del_ch_start(call: CallbackQuery, state: FSMContext):
    await call.message.answer("O'chirmoqchi bo'lgan kanal ID sini yuboring:")
    await state.set_state(AdminStates.delete_channel)

@dp.message(AdminStates.delete_channel, F.from_user.id == ADMIN_ID)
async def admin_del_ch_exec(message: Message, state: FSMContext):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("DELETE FROM channels WHERE channel_id=?", (message.text,))
        await db.commit()
    await message.answer("✅ Kanal o'chirildi.", reply_markup=get_admin_keyboard())
    await state.clear()

# --- ASOSIY BOT HANDLERLARI (Foydalanuvchilar uchun) ---
@dp.callback_query(F.data == "check_sub")
async def check_subscription_callback(call: CallbackQuery):
    # Bu callback ushlanganda, yuqoridagi CheckMiddleware ishga tushib, yana tekshiradi.
    # Agar bu qatorga o'tsa, demak obuna bo'lgan.
    await call.message.delete()
    await call.message.answer("✅ Obuna tasdiqlandi. Botdan foydalanishingiz mumkin!\n/start ni bosing yoki link/matn yuboring.")

@dp.message(CommandStart())
async def start_cmd(message: Message):
    await message.answer(
        "👋 Salom! Men Nyukla botman.\n\n"
        "📹 Menga Instagram yoki YouTube linkini yuboring - videoni yuklab beraman.\n"
        "🎵 Yoki qo'shiq/qo'shiqchi nomini yozing - musiqani topib beraman."
    )

@dp.message(F.text.regexp(r'(https?://(?:www\.)?(?:instagram\.com|youtube\.com|youtu\.be)/.+)'))
async def handle_video_link(message: Message):
    url = message.text
    wait_msg = await message.answer("⏳ Video yuklanmoqda, kuting...")
    try:
        os.makedirs("downloads", exist_ok=True)
        filepath, title = await download_media(url, is_audio=False)
        video = FSInputFile(filepath)
        await message.answer_video(video, caption="📥 @NyuklaBot orqali yuklab olindi")
        os.remove(filepath)
    except Exception as e:
        logging.error(f"Video yuklashda xato: {e}")
        await message.answer("❌ Videoni yuklashda xatolik yuz berdi. Hajmi juda katta bo'lishi mumkin.")
    finally:
        await wait_msg.delete()

@dp.message(F.text & ~F.text.startswith('/')) # Slesh bilan boshlanmagan matnlar (qidiruv)
async def handle_music_search(message: Message):
    # Agar admin menularida bo'lsa qidirmasligi uchun
    if message.text in ["👥 Foydalanuvchilar statistikasi", "📢 Xabar yuborish", "⚙️ Kanallarni sozlash", "🔴/🟢 Botni Yoqish/O'chirish", "🏠 Asosiy menyu"]:
        return

    query = message.text
    wait_msg = await message.answer("🔍 Musiqalar qidirilmoqda...")
    try:
        results = await search_music(query)
        if not results:
            return await wait_msg.edit_text("❌ Hech narsa topilmadi.")

        builder = InlineKeyboardBuilder()
        for idx, entry in enumerate(results, start=1):
            title = entry.get('title', 'Nomaʼlum')
            video_id = entry.get('id')
            builder.button(text=f"{idx}. {title}", callback_data=f"dl_mus_{video_id}")
        builder.adjust(1)
        await wait_msg.edit_text(f"🎵 **{query}** natijalari:\n👇", reply_markup=builder.as_markup())
    except Exception as e:
        logging.error(f"Qidiruvda xato: {e}")
        await wait_msg.edit_text("❌ Qidirishda xatolik yuz berdi.")

@dp.callback_query(F.data.startswith("dl_mus_"))
async def handle_music_download(callback: CallbackQuery):
    video_id = callback.data.split("dl_mus_")[1]
    url = f"https://www.youtube.com/watch?v={video_id}"
    await callback.message.edit_text("⏳ Musiqa yuklab olinmoqda...")
    try:
        os.makedirs("downloads", exist_ok=True)
        filepath, title = await download_media(url, is_audio=True)
        audio = FSInputFile(filepath)
        await callback.message.answer_audio(audio, caption="@NyuklaBot orqali istagan musiqangizni tez va oson toping!")
        os.remove(filepath)
        await callback.message.delete()
    except Exception as e:
        logging.error(f"Musiqa yuklashda xato: {e}")
        await callback.message.edit_text("❌ Musiqani yuklashda xatolik yuz berdi.")

# --- RENDER.COM UCHUN WEB-SERVER VA ISHGA TUSHIRISH ---
async def health_check(request):
    return web.Response(text="Nyukla Bot ishlab turibdi!")

async def main():
    if not BOT_TOKEN:
        logging.error("BOT_TOKEN muhit o'zgaruvchisi topilmadi!")
        return

    await init_db()

    app = web.Application()
    app.router.add_get('/', health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logging.info(f"Veb server {PORT} portda ishga tushdi.")

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot to'xtatildi.")