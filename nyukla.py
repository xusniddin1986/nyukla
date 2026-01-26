from aiogram import types
import asyncio
import logging
import os
import sqlite3
import tempfile
import time
from typing import Dict, List

import yt_dlp
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup
)

# =========================
# CONFIG
# =========================
BOT_TOKEN = "8510711803:AAE3klDsgCCgQTaB0oY8IDL4u-GmK9D2yAc"
CHANNEL = "@aclubnc"
ADMINS = {8553997595}
DB_NAME = "bot.db"
COOKIES_FILE = "cookies.txt"
PORT = 10000
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = "https://nyukla.onrender.com/webhook"


# =========================
# LOGGING
# =========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
log = logging.getLogger("nyukla")

# =========================
# DATABASE
# =========================
db = sqlite3.connect(DB_NAME, check_same_thread=False)
cur = db.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT,
    joined_at INTEGER
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
)
""")

db.commit()

def db_get(key: str, default="0"):
    cur.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = cur.fetchone()
    return row[0] if row else default

def db_set(key: str, value: str):
    cur.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (key, value))
    db.commit()

# default settings
if db_get("force_sub") is None:
    db_set("force_sub", "1")

# =========================
# BOT
# =========================
bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# =========================
# USER SESSIONS
# =========================
class UserSession:
    def __init__(self):
        self.tracks: List[dict] = []
        self.last_activity = time.time()

sessions: Dict[int, UserSession] = {}

def get_session(uid: int) -> UserSession:
    if uid not in sessions:
        sessions[uid] = UserSession()
    sessions[uid].last_activity = time.time()
    return sessions[uid]

async def cleanup_sessions():
    while True:
        now = time.time()
        for uid in list(sessions.keys()):
            if now - sessions[uid].last_activity > 600:
                del sessions[uid]
        await asyncio.sleep(60)

# =========================
# UTILS
# =========================
async def check_subscription(uid: int) -> bool:
    if db_get("force_sub", "1") == "0":
        return True
    try:
        m = await bot.get_chat_member(CHANNEL, uid)
        return m.status in ("member", "administrator", "creator")
    except:
        return False

def save_user(user):
    cur.execute(
        "INSERT OR IGNORE INTO users VALUES (?,?,?)",
        (user.id, user.username, int(time.time()))
    )
    db.commit()

YDL_BASE = {
    "quiet": True,
    "cookiefile": COOKIES_FILE,
    "nocheckcertificate": True,
}

def yt_search(query: str) -> List[dict]:
    opts = YDL_BASE | {"extract_flat": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        res = ydl.extract_info(f"ytsearch10:{query}", download=False)
        return res.get("entries", [])

def yt_download_audio(url: str, out_path: str):
    opts = YDL_BASE | {
        "format": "bestaudio",
        "outtmpl": out_path,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192"
        }]
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])

# =========================
# KEYBOARDS
# =========================
def sub_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Kanalga obuna", url=f"https://t.me/{CHANNEL[1:]}")],
        [InlineKeyboardButton(text="✅ Tekshirish", callback_data="check_sub")]
    ])

def admin_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            ["📊 Statistika", "📢 Broadcast"],
            ["🔒 Obuna ON/OFF"]
        ],
        resize_keyboard=True
    )

# =========================
# COMMANDS
# =========================
@dp.message(Command("start"))
async def cmd_start(msg: Message):
    save_user(msg.from_user)

    if not await check_subscription(msg.from_user.id):
        await msg.answer(
            "❗ Botdan foydalanish uchun kanalga obuna bo‘ling.",
            reply_markup=sub_keyboard()
        )
        return

    await msg.answer(
        "🎵 Musiqa nomi yoki 🎥 video link yuboring.\n"
        "YouTube / Instagram / TikTok / Facebook qo‘llab-quvvatlanadi."
    )

@dp.message(Command("help"))
async def cmd_help(msg: Message):
    await msg.answer(
        "/start - botni ishga tushirish\n"
        "/help - yordam\n"
        "/about - bot haqida\n"
        "/admin - admin panel"
    )

@dp.message(Command("about"))
async def cmd_about(msg: Message):
    await msg.answer("Nyukla Media Bot • Professional downloader")

@dp.message(Command("admin"))
async def cmd_admin(msg: Message):
    if msg.from_user.id not in ADMINS:
        return
    await msg.answer("👑 Admin panel", reply_markup=admin_keyboard())

# =========================
# CALLBACKS
# =========================
@dp.callback_query(F.data == "check_sub")
async def cb_check_sub(cb: CallbackQuery):
    if await check_subscription(cb.from_user.id):
        await cb.message.edit_text("✅ Obuna tasdiqlandi. /start")
    else:
        await cb.answer("❌ Hali obuna bo‘lmadingiz", show_alert=True)

@dp.callback_query(F.data.startswith("play_"))
async def cb_play(cb: CallbackQuery):
    uid = cb.from_user.id
    session = sessions.get(uid)
    if not session:
        await cb.answer("Sessiya topilmadi", show_alert=True)
        return

    idx = int(cb.data.split("_")[1])
    track = session.tracks[idx]

    await cb.answer("⏳ Yuklanmoqda...")

    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "audio.%(ext)s")
        yt_download_audio(track["url"], out)
        mp3 = os.path.join(tmp, "audio.mp3")
        await cb.message.answer_audio(open(mp3, "rb"))

# =========================
# TEXT HANDLER
# =========================
@dp.message(F.text)
async def handle_text(msg: Message):
    if not await check_subscription(msg.from_user.id):
        await cmd_start(msg)
        return

    session = get_session(msg.from_user.id)
    tracks = yt_search(msg.text)
    if not tracks:
        await msg.answer("❌ Hech narsa topilmadi")
        return

    session.tracks = tracks

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"{i+1}. {t['title'][:40]}",
            callback_data=f"play_{i}"
        )]
        for i, t in enumerate(tracks)
    ])

    await msg.answer("🎶 Top 10 natija:", reply_markup=kb)

# =========================
# ADMIN ACTIONS
# =========================
@dp.message(F.text == "📊 Statistika")
async def admin_stats(msg: Message):
    if msg.from_user.id not in ADMINS:
        return
    cur.execute("SELECT COUNT(*) FROM users")
    count = cur.fetchone()[0]
    await msg.answer(f"👥 Foydalanuvchilar: {count}")

@dp.message(F.text == "🔒 Obuna ON/OFF")
async def admin_toggle_sub(msg: Message):
    if msg.from_user.id not in ADMINS:
        return
    current = db_get("force_sub", "1")
    new = "0" if current == "1" else "1"
    db_set("force_sub", new)
    await msg.answer(f"Majburiy obuna: {'ON' if new=='1' else 'OFF'}")

async def web_server():
    app = web.Application()

    async def handle_webhook(request):
        data = await request.json()
        update = types.Update(**data)
        await dp.feed_update(bot, update)
        return web.Response(text="ok")

    app.router.add_post(WEBHOOK_PATH, handle_webhook)
    app.router.add_get("/", lambda r: web.Response(text="OK"))

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

    await bot.set_webhook(WEBHOOK_URL)

async def main():
    await web_server()
    asyncio.create_task(cleanup_sessions())
    await asyncio.Event().wait()  # botni tirik ushlab turadi