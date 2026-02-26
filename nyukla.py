import os
import logging
import asyncio
from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
import yt_dlp
from youtube_search import YoutubeSearch
from database import Database

# --- KONFIGURATSIYA ---
API_TOKEN = '8679344041:AAGVo6gwxoyjWOPCSb3ezdtfgwJ7PkhhQaM'
ADMIN_ID = 8553997595 # O'zingizning ID
CHANNELS = ["@aclubnc"] # Majburiy obuna

db = Database('bot_database.db')
bot = Bot(token=API_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot, storage=MemoryStorage())

class AdminStates(StatesGroup):
    waiting_for_ad = State()

# --- MAJBURIY OBUNA TEKSHIRUV ---
async def check_sub(user_id):
    for channel in CHANNELS:
        try:
            chat_member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
            if chat_member.status == 'left': return False
        except: return False
    return True

# --- TUGMALAR ---
def sub_kb():
    kb = InlineKeyboardMarkup(row_width=1)
    for ch in CHANNELS:
        kb.add(InlineKeyboardButton("Kanalga a'zo bo'lish ➕", url=f"https://t.me/{ch[1:]}"))
    kb.add(InlineKeyboardButton("Tekshirish ✅", callback_data="check_status"))
    return kb

def admin_kb():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("Statistika 📊", "Xabar yuborish 📢")
    kb.add("Foydalanuvchilar ro'yxati 📋", "Bot holati ✅")
    return kb

# --- START ---
@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    db.add_user(message.from_user.id, message.from_user.username)
    if await check_sub(message.from_user.id):
        await message.answer(f"Xush kelibsiz, {message.from_user.first_name}!\nLink yuboring yoki musiqa nomini yozing.", reply_markup=types.ReplyKeyboardRemove())
    else:
        await message.answer("<b>Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:</b>", reply_markup=sub_kb())

# --- ADMIN PANEL ---
@dp.message_handler(commands=['admin'])
async def admin_panel(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("Admin panelga xush kelibsiz!", reply_markup=admin_keyboard())

@dp.message_handler(lambda m: m.text == "Statistika 📊")
async def stats(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        count = db.count_users()
        await message.answer(f"Botdagi jami foydalanuvchilar: <b>{count} ta</b>")

@dp.message_handler(lambda m: m.text == "Xabar yuborish 📢")
async def start_ad(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("Reklama xabarini yuboring (Rasm, Video yoki Matn):")
        await AdminStates.waiting_for_ad.set()

@dp.message_handler(state=AdminStates.waiting_for_ad, content_types=types.ContentTypes.ANY)
async def send_ad(message: types.Message, state: FSMContext):
    users = db.get_users()
    count = 0
    for user in users:
        try:
            await message.copy_to(user[0])
            count += 1
            await asyncio.sleep(0.05)
        except: pass
    await message.answer(f"Xabar {count} ta foydalanuvchiga yetkazildi.")
    await state.finish()

# --- MUSIQA QIDIRISH (1-10) ---
@dp.message_handler(lambda m: not m.text.startswith("http") and not m.text.startswith("/"))
async def music_search(message: types.Message):
    if not await check_sub(message.from_user.id):
        return await message.answer("Obuna bo'lmagansiz!", reply_markup=sub_kb())
    
    query = message.text
    results = YoutubeSearch(query, max_results=10).to_dict()
    
    if not results:
        return await message.answer("Hech narsa topilmadi.")

    text = "🔍 <b>Natijalar:</b>\n\n"
    kb = InlineKeyboardMarkup(row_width=5)
    nums = []
    for i, res in enumerate(results, 1):
        text += f"{i}. <b>{res['title']}</b> | {res['duration']}\n"
        nums.append(InlineKeyboardButton(text=str(i), callback_data=f"mp3_{res['id']}"))
    
    kb.add(*nums)
    await message.answer(text, reply_markup=kb)

# --- VIDEO YUKLASH ---
@dp.message_handler(regexp=r'http')
async def downloader(message: types.Message):
    if not await check_sub(message.from_user.id):
        return await message.answer("Obuna bo'lmagansiz!", reply_markup=sub_kb())

    wait = await message.answer("Yuklanmoqda... ⏳")
    url = message.text
    file_id = f"downloads/{message.from_user.id}"

    ydl_opts = {'format': 'best', 'outtmpl': f'{file_id}.%(ext)s', 'noplaylist': True}
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            with open(filename, 'rb') as video:
                kb = InlineKeyboardMarkup().add(InlineKeyboardButton("Musiqasini yuklash 🎵", callback_data=f"mp3_{info['id']}"))
                await message.answer_video(video, caption="Bajarildi ✅", reply_markup=kb)
            os.remove(filename)
            await wait.delete()
    except Exception as e:
        await wait.edit_text("Xatolik! Link noto'g'ri yoki video juda katta.")

# --- CALLBACKS ---
@dp.callback_query_handler(lambda c: c.data.startswith('mp3_'))
async def get_audio(call: types.CallbackQuery):
    vid_id = call.data.split("_")[1]
    url = f"https://www.youtube.com/watch?v={vid_id}"
    await call.message.answer("Musiqa tayyorlanmoqda... 🎧")
    
    opts = {
        'format': 'bestaudio/best',
        'outtmpl': f'downloads/{vid_id}.mp3',
        'postprocessors': [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3','preferredquality': '192'}],
    }
    
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])
        with open(f"downloads/{vid_id}.mp3", 'rb') as audio:
            await bot.send_audio(call.from_user.id, audio)
        os.remove(f"downloads/{vid_id}.mp3")

@dp.callback_query_handler(text="check_status")
async def check_status(call: types.CallbackQuery):
    if await check_sub(call.from_user.id):
        await call.message.delete()
        await bot.send_message(call.from_user.id, "Tabriklaymiz, obuna tasdiqlandi!")
    else:
        await call.answer("Hali obuna bo'lmagansiz!", show_alert=True)

# --- RENDER SERVER ---
from flask import Flask
from threading import Thread
app = Flask('')
@app.route('/')
def home(): return "Bot is Alive"
def run(): app.run(host='0.0.0.0', port=8080)

if __name__ == '__main__':
    if not os.path.exists('downloads'): os.makedirs('downloads')
    Thread(target=run).start()
    executor.start_polling(dp, skip_updates=True)