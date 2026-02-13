import logging
import os
import sqlite3
import asyncio
from aiogram import Bot, Dispatcher, types, executor
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
import yt_dlp
from aiohttp import web

# --- SOZLAMALAR (O'ZGARTIRING) ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "8510711803:AAE1sApRn8lL0MFjUhOd5uxYQwQZpDa14w8") # Renderda Environment Variable qilib kiritasiz
CHANNEL_ID = os.getenv("CHANNEL_ID", "-1002980992642") # Kanal IDsi
CHANNEL_LINK = os.getenv("CHANNEL_LINK", "https://t.me/aclubnc") # Kanal linki
ADMIN_ID = int(os.getenv("ADMIN_ID", "8553997595")) # Admin IDsi

# --- LOGGING ---
logging.basicConfig(level=logging.INFO)

# --- BOT & DB INIT ---
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# --- DATABASE (SQLite) ---
def db_start():
    con = sqlite3.connect("bot_db.db")
    cur = con.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT)")
    cur.execute("CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT)")
    # Boshlang'ich sozlama: Majburiy obuna yoqilgan (1)
    cur.execute("INSERT OR IGNORE INTO settings VALUES ('force_sub', '1')")
    con.commit()
    con.close()

def add_user(user_id, username):
    con = sqlite3.connect("bot_db.db")
    cur = con.cursor()
    cur.execute("INSERT OR IGNORE INTO users VALUES (?, ?)", (user_id, username))
    con.commit()
    con.close()

def get_users_count():
    con = sqlite3.connect("bot_db.db")
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    count = cur.fetchone()[0]
    con.close()
    return count

def get_all_users():
    con = sqlite3.connect("bot_db.db")
    cur = con.cursor()
    cur.execute("SELECT id FROM users")
    users = cur.fetchall()
    con.close()
    return [x[0] for x in users]

def set_force_sub(status): # 1 = On, 0 = Off
    con = sqlite3.connect("bot_db.db")
    cur = con.cursor()
    cur.execute("UPDATE settings SET value = ? WHERE key = 'force_sub'", (str(status),))
    con.commit()
    con.close()

def get_force_sub_status():
    con = sqlite3.connect("bot_db.db")
    cur = con.cursor()
    cur.execute("SELECT value FROM settings WHERE key = 'force_sub'")
    status = cur.fetchone()
    con.close()
    return status[0] if status else '1'

# --- STATES ---
class AdminState(StatesGroup):
    broadcast = State()

# --- YORDAMCHI FUNKSIYALAR ---
async def check_sub(user_id):
    force_sub = get_force_sub_status()
    if force_sub == '0':
        return True
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        if member.status in ['creator', 'administrator', 'member']:
            return True
    except Exception as e:
        logging.error(f"Kanal tekshirishda xato: {e}")
        # Agar bot kanalga admin bo'lmasa yoki xato bo'lsa, foydalanuvchini o'tkazib yuboramiz (xalaqit bermaslik uchun)
        return True 
    return False

def get_yt_opts(is_audio=False):
    if is_audio:
        return {
            'format': 'bestaudio/best',
            'postprocessors': [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3','preferredquality': '192'}],
            'outtmpl': 'downloads/%(title)s.%(ext)s',
            'quiet': True,
            'noplaylist': True
        }
    else:
        return {
            'format': 'best[ext=mp4][filesize<50M]', # 50MB dan kichik videolarni olish
            'outtmpl': 'downloads/%(title)s.%(ext)s',
            'quiet': True,
            'noplaylist': True
        }

# --- KEYBOARDS ---
def sub_keyboard():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(text="📢 Kanalga obuna bo'lish", url=CHANNEL_LINK))
    markup.add(InlineKeyboardButton(text="✅ Obunani tekshirish", callback_data="check_sub"))
    return markup

def admin_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(KeyboardButton("📊 Statistika"), KeyboardButton("✉️ Xabar yuborish"))
    markup.add(KeyboardButton("🔒 Majburiy obuna: ON/OFF"), KeyboardButton("🔙 Chiqish"))
    return markup

# --- HANDLERS ---

@dp.message_handler(commands=['start'])
async def send_welcome(message: types.Message):
    add_user(message.from_user.id, message.from_user.username)
    if await check_sub(message.from_user.id):
        await message.answer(f"Assalomu alaykum, {message.from_user.first_name}!\n\n"
                             "Men Instagram, TikTok, YouTube va boshqa tarmoqlardan video yuklovchi va musiqa topuvchi botman.\n\n"
                             "🚀 **Ishlatish uchun:**\n"
                             "1. Video linkini yuboring.\n"
                             "2. Musiqa nomini yozing.", parse_mode="Markdown")
    else:
        await message.answer("⚠️ **Botdan foydalanish uchun kanalimizga obuna bo'ling!**", reply_markup=sub_keyboard(), parse_mode="Markdown")

@dp.callback_query_handler(text="check_sub")
async def callback_check_sub(call: types.CallbackQuery):
    if await check_sub(call.from_user.id):
        await call.message.delete()
        await call.message.answer("✅ Obuna tasdiqlandi! Endi bemalol foydalanishingiz mumkin.")
    else:
        await call.answer("❌ Siz hali obuna bo'lmadingiz!", show_alert=True)

# --- ADMIN PANEL ---
@dp.message_handler(commands=['admin'])
async def admin_panel(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("👨‍💻 Admin panelga xush kelibsiz!", reply_markup=admin_keyboard())
    else:
        pass # Admin bo'lmasa jim turadi

@dp.message_handler(lambda message: message.text == "📊 Statistika", user_id=ADMIN_ID)
async def admin_stats(message: types.Message):
    count = get_users_count()
    await message.answer(f"📊 **Bot statistikasi:**\n\n👤 Foydalanuvchilar soni: {count} ta\n🤖 Bot holati: Aktiv", parse_mode="Markdown")

@dp.message_handler(lambda message: message.text == "🔒 Majburiy obuna: ON/OFF", user_id=ADMIN_ID)
async def toggle_sub(message: types.Message):
    current = get_force_sub_status()
    new_status = '0' if current == '1' else '1'
    set_force_sub(new_status)
    status_text = "Yoqildi ✅" if new_status == '1' else "O'chirildi ❌"
    await message.answer(f"Majburiy obuna holati: {status_text}")

@dp.message_handler(lambda message: message.text == "✉️ Xabar yuborish", user_id=ADMIN_ID)
async def broadcast_start(message: types.Message):
    await AdminState.broadcast.set()
    await message.answer("Foydalanuvchilarga yuboriladigan xabarni (matn, rasm, video) yuboring. Bekor qilish uchun /cancel")

@dp.message_handler(state=AdminState.broadcast, content_types=types.ContentTypes.ANY)
async def broadcast_send(message: types.Message, state: FSMContext):
    if message.text == "/cancel":
        await state.finish()
        await message.answer("Bekor qilindi.", reply_markup=admin_keyboard())
        return

    users = get_all_users()
    count = 0
    await message.answer(f"Xabar tarqatish boshlandi... ({len(users)} ta odamga)")
    
    for user_id in users:
        try:
            await message.copy_to(user_id)
            count += 1
            await asyncio.sleep(0.05) # Spamdan himoya
        except:
            pass
    
    await state.finish()
    await message.answer(f"✅ Xabar {count} ta foydalanuvchiga yetib bordi.", reply_markup=admin_keyboard())

@dp.message_handler(lambda message: message.text == "🔙 Chiqish", user_id=ADMIN_ID)
async def admin_exit(message: types.Message):
    await message.answer("Admin paneldan chiqildi.", reply_markup=types.ReplyKeyboardRemove())

# --- MAIN LOGIC (DOWNLOAD & SEARCH) ---

@dp.message_handler(content_types=['text'])
async def handle_text(message: types.Message):
    # 1. Obunani tekshirish
    if not await check_sub(message.from_user.id):
        await message.answer("⚠️ **Botdan foydalanish uchun kanalimizga obuna bo'ling!**", reply_markup=sub_keyboard(), parse_mode="Markdown")
        return

    text = message.text
    msg = await message.answer("🔎 So'rovingiz ishlanmoqda...")

    # 2. Agar LINK bo'lsa (Video yuklash)
    if text.startswith("http"):
        try:
            ydl_opts = get_yt_opts(is_audio=False)
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(text, download=True)
                filename = ydl.prepare_filename(info)
                title = info.get('title', 'Video')
                
            # Videoni yuborish
            with open(filename, 'rb') as video:
                # Inline tugma: Audio yuklab olish
                audio_kb = InlineKeyboardMarkup().add(
                    InlineKeyboardButton("🎵 Musiqasini yuklab olish", callback_data=f"getaudio|{title[:15]}")
                ) # Title qisqartirildi, callback limit bor
                await message.reply_video(video, caption=f"📹 {title}\n🤖 @{bot.get_me().username} orqali yuklandi", reply_markup=audio_kb)
            
            os.remove(filename)
            await msg.delete()
            
        except Exception as e:
            await msg.edit_text(f"❌ Kechirasiz, bu linkni yuklab bo'lmadi yoki fayl juda katta.\nXato: {str(e)[:50]}")
            if os.path.exists('downloads'):
                for f in os.listdir('downloads'):
                    os.remove(os.path.join('downloads', f))

    # 3. Agar ODDIY SO'Z bo'lsa (Musiqa qidirish)
    else:
        try:
            # yt-dlp search
            ydl_opts = {'quiet': True, 'default_search': 'ytsearch5', 'noplaylist': True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(text, download=False)
            
            if 'entries' in info and info['entries']:
                markup = InlineKeyboardMarkup(row_width=1)
                results_text = "🎵 **Topilgan musiqalar:**\n\n"
                
                for i, entry in enumerate(info['entries']):
                    title = entry.get('title', 'Noma\'lum')
                    vid_id = entry.get('id')
                    duration = entry.get('duration_string', '')
                    results_text += f"{i+1}. {title} ({duration})\n"
                    markup.add(InlineKeyboardButton(text=f"{i+1}. {title}", callback_data=f"dl_music|{vid_id}"))
                
                await msg.edit_text(results_text, reply_markup=markup, parse_mode="Markdown")
            else:
                await msg.edit_text("❌ Hech narsa topilmadi.")
        except Exception as e:
            await msg.edit_text("❌ Qidiruvda xatolik yuz berdi.")

# --- CALLBACKS FOR MUSIC DOWNLOAD ---

@dp.callback_query_handler(lambda c: c.data and c.data.startswith('dl_music|'))
async def download_music_callback(call: types.CallbackQuery):
    vid_id = call.data.split('|')[1]
    link = f"https://www.youtube.com/watch?v={vid_id}"
    await call.message.edit_text("🎵 Musiqa yuklanmoqda... Biroz kuting.")
    
    try:
        ydl_opts = get_yt_opts(is_audio=True)
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(link, download=True)
            filename = ydl.prepare_filename(info)
            # Extension mp3 ga o'zgarishi mumkin postprocessor tufayli
            filename = filename.rsplit('.', 1)[0] + '.mp3'
            
        with open(filename, 'rb') as audio:
            await call.message.answer_audio(audio, caption=f"🎧 @{ (await bot.get_me()).username}")
        
        os.remove(filename)
        await call.message.delete()
        
    except Exception as e:
        await call.message.answer("❌ Musiqani yuklab bo'lmadi.")

@dp.callback_query_handler(lambda c: c.data and c.data.startswith('getaudio|'))
async def extract_audio_from_video_callback(call: types.CallbackQuery):
    # Bu yerda biz videoni qayta yuklab o'tirmaymiz, chunki biz linkni saqlamadik.
    # Lekin professional yechimda "context" saqlash kerak. 
    # Oddiylik uchun: Foydalanuvchiga "Musiqa nomini yozib qidiring" deymiz, 
    # chunki videodan audio ajratish uchun fayl serverda turishi kerak (Renderda esa u o'chib ketadi).
    # Yoki: Video linki xabarda bor. Uni reply qilib olsak bo'ladi.
    
    await call.answer("🎵 Musiqani qidirish uchun nomini botga yozing yoki linkni qayta tashlang.", show_alert=True)
    # Eslatma: Render free tierda fayllarni uzoq saqlab bo'lmaydi, shuning uchun bu eng barqaror yo'l.

# --- RENDER UCHUN WEB SERVER (Keep-Alive) ---
async def health_check(request):
    return web.Response(text="Bot is running!")

async def on_startup(dp):
    db_start()
    if not os.path.exists('downloads'):
        os.makedirs('downloads')
    await bot.set_webhook(url=f"{os.getenv('RENDER_EXTERNAL_URL')}/webhook") # Webhook ishlatilsa

# --- RENDER ENTRY POINT ---
if __name__ == '__main__':
    # Web serverni alohida thread yoki loopda ishlatish kerak,
    # lekin Renderda eng osoni webhook yoki oddiy polling + dummy server.
    # Polling ishlatamiz (osonroq), lekin Render talabi uchun port ochamiz.
    
    # 1. Background server
    app = web.Application()
    app.router.add_get('/', health_check)
    
    runner = web.AppRunner(app)
    
    async def start_server():
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', int(os.getenv('PORT', 8080)))
        await site.start()

    # 2. Bot loop
    loop = asyncio.get_event_loop()
    loop.run_until_complete(start_server())
    executor.start_polling(dp, on_startup=on_startup, skip_updates=True)