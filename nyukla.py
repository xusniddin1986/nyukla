import os
import asyncio
import logging
import aiosqlite
import uuid
import shutil
from datetime import datetime
from typing import Union, List, Dict, Optional

import uvicorn
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, F, BaseMiddleware
from aiogram.types import (
    Update, FSInputFile, InlineKeyboardMarkup, 
    InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton,
    ReplyKeyboardRemove, CallbackQuery, Message
)
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramForbiddenError
from yt_dlp import YoutubeDL

# --- INITIAL SETUP ---
try:
    import static_ffmpeg
    static_ffmpeg.add_paths()
except:
    pass

BOT_TOKEN = "8679344041:AAGVo6gwxoyjWOPCSb3ezdtfgwJ7PkhhQaM"
RENDER_URL = "https://nyukla.onrender.com"
DEFAULT_ADMIN = 8553997595 
WEBHOOK_PATH = f"/bot/{BOT_TOKEN}"
WEBHOOK_URL = f"{RENDER_URL}{WEBHOOK_PATH}"

logging.basicConfig(level=logging.INFO, format='%(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("PowerBot")

# --- STATES ---
class AdminStates(StatesGroup):
    waiting_ads = State()
    adding_ch = State()
    removing_ch = State()

class BotStates(StatesGroup):
    search = State()

# --- DATABASE ENGINE ---
class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def _run(self, query: str, params: tuple = (), commit: bool = False, fetch: str = None):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(query, params)
            if commit: await db.commit()
            if fetch == "one": return await cursor.fetchone()
            if fetch == "all": return await cursor.fetchall()
            return cursor

    async def setup(self):
        await self._run("CREATE TABLE IF NOT EXISTS users (uid INTEGER PRIMARY KEY, nick TEXT, date TEXT)", commit=True)
        await self._run("CREATE TABLE IF NOT EXISTS channels (cid TEXT PRIMARY KEY, name TEXT, link TEXT)", commit=True)
        await self._run("CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, fid TEXT, type TEXT, title TEXT)", commit=True)
        await self._run("CREATE TABLE IF NOT EXISTS admins (uid INTEGER PRIMARY KEY)", commit=True)
        await self._run("INSERT OR IGNORE INTO admins VALUES (?)", (DEFAULT_ADMIN,), commit=True)

db = Database("power_v4.db")

# --- MEDIA ENGINE ---
class MediaEngine:
    def __init__(self):
        self.opts = {
            'quiet': True, 'no_warnings': True,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }

    async def search(self, query: str):
        with YoutubeDL({'extract_flat': True, **self.opts}) as ydl:
            info = await asyncio.to_thread(ydl.extract_info, f"ytsearch5:{query}", download=False)
            return info['entries']

    async def fetch(self, url: str, mode: str = "video"):
        folder = "downloads"
        if not os.path.exists(folder): os.makedirs(folder)
        fname = f"{folder}/{uuid.uuid4()}"
        
        y_opts = {
            'outtmpl': fname,
            'max_filesize': 49 * 1024 * 1024, # 49MB Safe limit
            **self.opts
        }
        
        if mode == "audio":
            y_opts.update({'format': 'bestaudio/best', 'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3'}]})
        else:
            y_opts['format'] = 'best[height<=720][ext=mp4]/best'

        with YoutubeDL(y_opts) as ydl:
            info = await asyncio.to_thread(ydl.extract_info, url, download=True)
            path = ydl.prepare_filename(info)
            if mode == "audio": path = path.rsplit('.', 1)[0] + ".mp3"
            return path, info.get('title', 'Media')

engine = MediaEngine()

# --- MIDDLEWARE ---
class ProtectionMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: Union[Message, CallbackQuery], data: dict):
        user = event.from_user
        if not user: return await handler(event, data)

        await db._run("INSERT OR IGNORE INTO users VALUES (?, ?, ?)", (user.id, user.username, datetime.now().isoformat()), commit=True)
        
        is_admin = await db._run("SELECT uid FROM admins WHERE uid=?", (user.id,), fetch="one")
        data['is_admin'] = bool(is_admin)

        if is_admin or (isinstance(event, Message) and event.text == "/start"):
            return await handler(event, data)

        chans = await db._run("SELECT * FROM channels", fetch="all")
        not_joined = []
        for ch in chans:
            try:
                m = await data['bot'].get_chat_member(ch['cid'], user.id)
                if m.status in ['left', 'kicked']: not_joined.append(ch)
            except: continue

        if not_joined:
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"➕ {c['name']}", url=c['link'])] for c in not_joined])
            kb.inline_keyboard.append([InlineKeyboardButton(text="🔄 Tekshirish", callback_data="check")])
            if isinstance(event, Message): await event.answer("⚠️ Botni ishlatish uchun kanallarga a'zo bo'ling:", reply_markup=kb)
            else: await event.answer("Obuna bo'lmagansiz!", show_alert=True)
            return
        return await handler(event, data)

# --- BOT CORE ---
bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher(storage=MemoryStorage())
dp.update.outer_middleware(ProtectionMiddleware())
app = FastAPI()

# Keyboards
def main_kb(adm=False):
    btn = [[KeyboardButton(text="🎵 Musiqa qidirish"), KeyboardButton(text="🎬 Video yuklash")]]
    if adm: btn.append([KeyboardButton(text="🛠 Admin Menu")])
    return ReplyKeyboardMarkup(keyboard=btn, resize_keyboard=True)

def adm_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📊 Statistika"), KeyboardButton(text="📢 Kanallar")],
        [KeyboardButton(text="✉️ Reklama"), KeyboardButton(text="🔙 Chiqish")]
    ], resize_keyboard=True)

# Handlers
@dp.message(Command("start"))
async def cmd_start(m: Message, is_admin: bool):
    await m.answer(f"Assalomu alaykum {m.from_user.full_name}!\nLink yuboring yoki quyidagi tugmani bosing:", reply_markup=main_kb(is_admin))

@dp.callback_query(F.data == "check")
async def cb_check(call: CallbackQuery):
    await call.message.delete()
    await call.message.answer("✅ Rahmat! Endi link yuborsangiz bo'ladi.")

# Musiqa qidirish
@dp.message(F.text == "🎵 Musiqa qidirish")
async def music_start(m: Message, state: FSMContext):
    await m.answer("🔍 Musiqa nomini yozing:")
    await state.set_state(BotStates.search)

@dp.message(BotStates.search)
async def music_process(m: Message, state: FSMContext):
    wait = await m.answer("🔎 Qidirilmoqda...")
    res = await engine.search(m.text)
    if not res: return await wait.edit_text("❌ Topilmadi.")
    
    kb = []
    text = "🎵 <b>Qidiruv natijalari:</b>\n\n"
    for i, item in enumerate(res, 1):
        text += f"{i}. {item['title'][:45]}...\n"
        kb.append([InlineKeyboardButton(text=f"{i}-ni yuklash", callback_data=f"dl_au_{item['id']}")])
    await wait.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await state.clear()

@dp.callback_query(F.data.startswith("dl_au_"))
async def dl_audio_cb(call: CallbackQuery):
    v_id = call.data.split("_")[2]
    url = f"https://www.youtube.com/watch?v={v_id}"
    
    # Cache check
    cache = await db._run("SELECT fid FROM cache WHERE key=?", (f"au_{v_id}",), fetch="one")
    if cache: return await call.message.answer_audio(cache['fid'])

    wait = await call.message.answer("🎵 Musiqa tayyorlanmoqda...")
    try:
        path, title = await engine.fetch(url, "audio")
        sent = await call.message.answer_audio(FSInputFile(path), caption=f"🎵 {title}\n@NYuklaBot")
        await db._run("INSERT INTO cache VALUES (?, ?, ?, ?)", (f"au_{v_id}", sent.audio.file_id, "audio", title), commit=True)
        if os.path.exists(path): os.remove(path)
        await wait.delete()
    except: await wait.edit_text("❌ Xato! Hajm juda katta.")

# Video yuklash
@dp.message(F.text.contains("http"))
async def video_dl(m: Message):
    url = m.text
    cache = await db._run("SELECT fid, title FROM cache WHERE key=?", (url,), fetch="one")
    if cache: return await m.answer_video(cache['fid'], caption=f"🎬 {cache['title']}")

    wait = await m.answer("🚀 Yuklanmoqda...")
    try:
        path, title = await engine.fetch(url, "video")
        sent = await m.answer_video(FSInputFile(path), caption=f"🎬 {title}\n@NYuklaBot")
        await db._run("INSERT INTO cache VALUES (?, ?, ?, ?)", (url, sent.video.file_id, "video", title), commit=True)
        if os.path.exists(path): os.remove(path)
        await wait.delete()
    except: await wait.edit_text("❌ Video 50MB dan katta yoki link xato.")

# --- ADMIN PANEL ---
@dp.message(F.text == "🛠 Admin Menu")
async def adm_panel(m: Message, is_admin: bool):
    if is_admin: await m.answer("Boshqaruv paneli:", reply_markup=adm_kb())

@dp.message(F.text == "📊 Statistika")
async def adm_stats(m: Message, is_admin: bool):
    if not is_admin: return
    u = await db._run("SELECT COUNT(*) as c FROM users", fetch="one")
    c = await db._run("SELECT COUNT(*) as c FROM cache", fetch="one")
    await m.answer(f"📈 <b>Statistika:</b>\n\n👤 Userlar: {u['c']}\n💾 Fayllar keshda: {c['c']}")

@dp.message(F.text == "📢 Kanallar")
async def adm_chans(m: Message, is_admin: bool):
    if not is_admin: return
    ch = await db._run("SELECT * FROM channels", fetch="all")
    text = "📢 <b>Majburiy kanallar:</b>\n\n"
    kb = []
    for c in ch:
        text += f"🔹 {c['name']} ({c['cid']})\n"
        kb.append([InlineKeyboardButton(text=f"❌ {c['name']}", callback_data=f"del_{c['cid']}")])
    kb.append([InlineKeyboardButton(text="➕ Qo'shish", callback_data="add_ch")])
    await m.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data == "add_ch")
async def add_ch_cb(call: CallbackQuery, state: FSMContext):
    await call.message.answer("Format: <code>ID | Nomi | Link</code>\n\nMisol: <code>-100123 | Kanalim | t.me/link</code>")
    await state.set_state(AdminStates.adding_ch)

@dp.message(AdminStates.adding_ch)
async def add_ch_final(m: Message, state: FSMContext):
    try:
        cid, name, link = m.text.split("|")
        await db._run("INSERT INTO channels VALUES (?, ?, ?)", (cid.strip(), name.strip(), link.strip()), commit=True)
        await m.answer("✅ Qo'shildi.")
    except: await m.answer("❌ Xato format.")
    await state.clear()

@dp.callback_query(F.data.startswith("del_"))
async def del_ch_cb(call: CallbackQuery):
    cid = call.data.split("_")[1]
    await db._run("DELETE FROM channels WHERE cid=?", (cid,), commit=True)
    await call.message.delete()
    await call.answer("O'chirildi.")

@dp.message(F.text == "✉️ Reklama")
async def ads_start(m: Message, state: FSMContext, is_admin: bool):
    if not is_admin: return
    await m.answer("Xabarni yuboring (Copy-post):")
    await state.set_state(AdminStates.waiting_ads)

@dp.message(AdminStates.waiting_ads)
async def ads_process(m: Message, state: FSMContext):
    users = await db._run("SELECT uid FROM users", fetch="all")
    await m.answer(f"Yuborish boshlandi: {len(users)} ta")
    c = 0
    for u in users:
        try:
            await m.copy_to(u['uid'])
            c += 1
            await asyncio.sleep(0.05)
        except: continue
    await m.answer(f"✅ Tugadi. {c} ta userga yetdi.")
    await state.clear()

@dp.message(F.text == "🔙 Chiqish")
async def adm_exit(m: Message, is_admin: bool):
    await m.answer("Asosiy menu", reply_markup=main_kb(is_admin))

# --- SERVER ---
@app.on_event("startup")
async def on_startup():
    await db.setup()
    await bot.set_webhook(url=WEBHOOK_URL, drop_pending_updates=True)

@app.post(WEBHOOK_PATH)
async def hook(request: Request):
    update = Update.model_validate(await request.json(), context={"bot": bot})
    await dp.feed_update(bot, update)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))