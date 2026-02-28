import os
import sys
import asyncio
import logging
import uuid
import re
import shutil
import time
from datetime import datetime
from typing import List, Dict, Any, Optional, Union

# Tashqi kutubxonalar
import yt_dlp
from dotenv import load_dotenv
from fastapi import FastAPI, Request
import uvicorn

from aiogram import Bot, Dispatcher, Router, F, types, BaseMiddleware
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardButton, 
    ReplyKeyboardMarkup, KeyboardButton, FSInputFile,
    InputMediaPhoto, InputMediaVideo, InputMediaAudio,
    ReplyKeyboardRemove
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters import Command, CommandObject, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from sqlalchemy import (
    Column, Integer, String, BigInteger, 
    Boolean, DateTime, Text, select, func, 
    update, delete, desc
)
from sqlalchemy.ext.asyncio import (
    AsyncSession, create_async_engine, 
    async_sessionmaker, AsyncAttrs
)
from sqlalchemy.orm import declarative_base

# ------------------------------------------------------------------
# 1. LOGGING SOZLAMALARI
# ------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot_production.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("NyuklaBot")

# ------------------------------------------------------------------
# 2. ENVIRONMENT VALIDATION & CONFIG
# ------------------------------------------------------------------
load_dotenv()

class Config:
    """Production darajasidagi konfiguratsiya va validatsiya klasi"""
    try:
        BOT_TOKEN = os.getenv("8679344041:AAGVo6gwxoyjWOPCSb3ezdtfgwJ7PkhhQaM")
        if not BOT_TOKEN:
            raise ValueError("BOT_TOKEN topilmadi!")

        ADMIN_IDS_RAW = os.getenv("ADMIN_IDS", "8553997595")
        if not ADMIN_IDS_RAW:
            raise ValueError("ADMIN_IDS topilmadi!")
        ADMIN_IDS = [int(i.strip()) for i in ADMIN_IDS_RAW.split(",") if i.strip()]

        DATABASE_URL = os.getenv("postgresql://nyukla_user:aWXI7hFmjhVVW6F2oqGUHUmasyJL4Qan@dpg-d6hh06k50q8c73aj7340-a/nyukla_db")
        if not DATABASE_URL:
            raise ValueError("DATABASE_URL topilmadi!")

        WEBHOOK_HOST = os.getenv("https://nyukla.onrender.com")
        if not WEBHOOK_HOST:
            raise ValueError("WEBHOOK_HOST topilmadi!")
        WEBHOOK_HOST = WEBHOOK_HOST.rstrip("/")

        CHANNEL_ID = os.getenv("-1002980992642")
        if not CHANNEL_ID:
            raise ValueError("CHANNEL_ID topilmadi!")
        # Agar channel id -100 bilan boshlanmasa, uni integerga o'girishda xato bo'lmasligi kerak
        try:
            CHANNEL_ID = int(CHANNEL_ID)
        except ValueError:
            pass # Username holatida qoldiramiz

        CHANNEL_URL = os.getenv("https://t.me/aclubnc")
        if not CHANNEL_URL:
            raise ValueError("CHANNEL_URL topilmadi!")

    except Exception as e:
        logger.critical(f"CONFIG ERROR: {str(e)}")
        sys.exit(1)

    WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
    WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
    DOWNLOAD_DIR = "downloads"
    TEMP_CACHE_TTL = 3600  # Kesh yashash vaqti (1 soat)

# Papkani yaratish
if not os.path.exists(Config.DOWNLOAD_DIR):
    os.makedirs(Config.DOWNLOAD_DIR)

# ------------------------------------------------------------------
# 3. DATABASE SETUP (SQLAlchemy Async)
# ------------------------------------------------------------------
Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, unique=True, index=True, nullable=False)
    username = Column(String(255), nullable=True)
    full_name = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    joined_at = Column(DateTime, default=datetime.utcnow)

class BotSettings(Base):
    __tablename__ = 'bot_settings'
    id = Column(Integer, primary_key=True)
    sub_required = Column(Boolean, default=True)
    bot_enabled = Column(Boolean, default=True)
    broadcast_running = Column(Boolean, default=False)

class AdminUser(Base):
    __tablename__ = 'admins'
    user_id = Column(BigInteger, primary_key=True)
    added_at = Column(DateTime, default=datetime.utcnow)

engine = create_async_engine(
    Config.DATABASE_URL, 
    pool_pre_ping=True, 
    echo=False
)
async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

# ------------------------------------------------------------------
# 4. MEMORY CACHE (FOR CALLBACK DATA BYPASS)
# ------------------------------------------------------------------
# UUID : URL mapping
url_storage: Dict[str, str] = {}
# Tozalash mantiqi keyinroq qo'shiladi

# ------------------------------------------------------------------
# 5. FSM STATES
# ------------------------------------------------------------------
class AdminStates(StatesGroup):
    waiting_for_broadcast_content = State()
    waiting_for_new_admin_id = State()
    waiting_for_del_admin_id = State()

class SearchStates(StatesGroup):
    waiting_for_query = State()

# ------------------------------------------------------------------
# 6. MEDIA SERVICE (YT-DLP INTEGRATION)
# ------------------------------------------------------------------
class MediaDownloader:
    """Universal downloader for various platforms"""
    
    @staticmethod
    async def get_info(url: str) -> Optional[dict]:
        """URL haqida ma'lumot olish (yuklamasdan)"""
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'allowed_extractors': [
                '.*instagram.*', '.*tiktok.*', '.*youtube.*', 
                '.*facebook.*', '.*pinterest.*', '.*shorts.*'
            ]
        }
        loop = asyncio.get_event_loop()
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=False))
        except Exception as e:
            logger.error(f"Info extraction error: {e}")
            return None

    @staticmethod
    async def download_video(url: str, file_id: str) -> Optional[str]:
        """Videoni 50MB limit bilan yuklash"""
        output_path = os.path.join(Config.DOWNLOAD_DIR, f"{file_id}.mp4")
        ydl_opts = {
            'format': 'bestvideo[ext=mp4][filesize<50M]+bestaudio[ext=m4a]/best[ext=mp4][filesize<50M]/best[filesize<50M]',
            'outtmpl': output_path,
            'quiet': True,
            'no_warnings': True,
            'max_filesize': 50 * 1024 * 1024, # 50MB
        }
        loop = asyncio.get_event_loop()
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=True))
                if os.path.exists(output_path):
                    return output_path
                return None
        except Exception as e:
            logger.error(f"Video download error: {e}")
            return None

    @staticmethod
    async def extract_mp3(url: str, file_id: str) -> Optional[str]:
        """Videodan yuqori sifatli MP3 ajratib olish"""
        output_base = os.path.join(Config.DOWNLOAD_DIR, file_id)
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': output_base,
            'quiet': True,
            'no_warnings': True,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        }
        loop = asyncio.get_event_loop()
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=True))
                final_path = f"{output_base}.mp3"
                if os.path.exists(final_path):
                    return final_path
                return None
        except Exception as e:
            logger.error(f"MP3 extraction error: {e}")
            return None

# ------------------------------------------------------------------
# 7. UTILS & HELPERS
# ------------------------------------------------------------------
async def safe_remove(file_path: Optional[str]):
    """Faylni xavfsiz o'chirish"""
    try:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"File deleted: {file_path}")
    except Exception as e:
        logger.error(f"File delete error: {e}")

async def is_subscribed(bot: Bot, user_id: int) -> bool:
    """Obunani tekshirish"""
    try:
        member = await bot.get_chat_member(Config.CHANNEL_ID, user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception as e:
        logger.error(f"Sub check error: {e}")
        return False

# ------------------------------------------------------------------
# 8. MIDDLEWARES
# ------------------------------------------------------------------
class GlobalMiddleware(BaseMiddleware):
    """Obuna va Bot holatini tekshiruvchi asosiy middleware"""
    
    async def __call__(self, handler, event: Union[Message, CallbackQuery], data):
        user = data.get("event_from_user")
        if not user or user.is_bot:
            return await handler(event, data)

        async with async_session() as session:
            # Bot sozlamalarini olish
            settings_res = await session.execute(select(BotSettings).limit(1))
            settings = settings_res.scalar()
            
            # Adminlarni tekshirish (Config va DB)
            admin_res = await session.execute(select(AdminUser).where(AdminUser.user_id == user.id))
            is_admin = user.id in Config.ADMIN_IDS or admin_res.scalar() is not None
            data["is_admin"] = is_admin

            # Bot o'chirilgan bo'lsa (Adminlar mustasno)
            if settings and not settings.bot_enabled and not is_admin:
                if isinstance(event, Message):
                    await event.answer("💤 Bot hozircha texnik ishlar tufayli o'chirilgan.")
                return

            # Majburiy obuna (Adminlar mustasno)
            if settings and settings.sub_required and not is_admin:
                # Start va check_sub callbacklariga ruxsat berish
                is_start = isinstance(event, Message) and event.text and event.text.startswith("/start")
                is_check_cb = isinstance(event, CallbackQuery) and event.data == "check_sub"
                
                if not is_start and not is_check_cb:
                    subscribed = await is_subscribed(data["bot"], user.id)
                    if not subscribed:
                        kb = InlineKeyboardBuilder()
                        kb.row(InlineKeyboardButton(text="Kanalga o'tish ↗️", url=Config.CHANNEL_URL))
                        kb.row(InlineKeyboardButton(text="Tekshirish ✅", callback_data="check_sub"))
                        
                        msg_text = "⚠️ Botdan foydalanish uchun kanalimizga obuna bo'lishingiz shart!"
                        if isinstance(event, Message):
                            await event.answer(msg_text, reply_markup=kb.as_markup())
                        else:
                            await event.answer(msg_text, show_alert=True)
                        return

        return await handler(event, data)

# ------------------------------------------------------------------
# 9. KEYBOARDS
# ------------------------------------------------------------------
def get_admin_main_kb():
    kb = [
        [KeyboardButton(text="📢 Broadcast"), KeyboardButton(text="📊 Statistika")],
        [KeyboardButton(text="➕ Admin qo'shish"), KeyboardButton(text="➖ Admin o'chirish")],
        [KeyboardButton(text="⚙️ Majburiy obuna"), KeyboardButton(text="🛑 Bot ON/OFF")],
        [KeyboardButton(text="👥 Foydalanuvchilar ro'yxati")],
        [KeyboardButton(text="🏠 Asosiy menyu")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_main_kb():
    kb = [[KeyboardButton(text="🔍 Musiqa qidirish"), KeyboardButton(text="ℹ️ Ma'lumot")]]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# ------------------------------------------------------------------
# 10. FOYDALANUVCHI HANDLERLARI
# ------------------------------------------------------------------
user_router = Router()

@user_router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        # Foydalanuvchini bazaga qo'shish yoki yangilash
        stmt = select(User).where(User.user_id == message.from_user.id)
        res = await session.execute(stmt)
        user = res.scalar()
        
        if not user:
            new_user = User(
                user_id=message.from_user.id,
                username=message.from_user.username,
                full_name=message.from_user.full_name
            )
            session.add(new_user)
        else:
            user.username = message.from_user.username
            user.full_name = message.from_user.full_name
            user.is_active = True
        await session.commit()

    welcome_text = (
        f"👋 Salom, <b>{message.from_user.full_name}</b>!\n\n"
        "Men orqali quyidagi platformalardan video yuklashingiz mumkin:\n"
        "🎬 <b>YouTube, TikTok, Instagram, Facebook, Pinterest</b>\n\n"
        "Shunchaki video havolasini (link) yuboring yoki musiqa nomini yozing!"
    )
    await message.answer(welcome_text, reply_markup=get_main_kb(), parse_mode="HTML")

@user_router.message(Command("help"))
async def cmd_help(message: Message):
    help_text = (
        "📖 <b>Botdan foydalanish qo'llanmasi:</b>\n\n"
        "1️⃣ <b>Video yuklash:</b> Instagram, TikTok yoki YouTube linkini botga yuboring.\n"
        "2️⃣ <b>Musiqa yuklash:</b> Video yuklangach, '🎵 MP3' tugmasini bosing.\n"
        "3️⃣ <b>Qidiruv:</b> '🔍 Musiqa qidirish' tugmasini bosing va qo'shiq nomini yozing.\n\n"
        "⚠️ <b>Limit:</b> Fayl hajmi 50MB dan oshmasligi kerak."
    )
    await message.answer(help_text, parse_mode="HTML")

@user_router.message(Command("about"))
async def cmd_about(message: Message):
    await message.answer(
        "🤖 <b>Nyukla Downloader v2.0</b>\n"
        "Ushbu bot ijtimoiy tarmoqlardan media yuklab olish uchun yaratilgan.\n\n"
        "👨‍💻 Dasturchi: @developer_user\n"
        "📚 Texnologiyalar: Aiogram 3, SQLAlchemy, FastAPI, Yt-dlp",
        parse_mode="HTML"
    )

# ------------------------------------------------------------------
# 11. DOWNLOADER MANTIQI (LINKLARNI TUTISH)
# ------------------------------------------------------------------

@user_router.message(F.text.regexp(r'(https?://[^\s]+)'))
async def link_handler(message: Message):
    url = message.text.strip()
    status_msg = await message.answer("🔍 Havola tahlil qilinmoqda...")
    
    try:
        # Media ma'lumotlarini olish
        info = await MediaDownloader.get_info(url)
        if not info:
            return await status_msg.edit_text("❌ Media topilmadi yoki havola noto'g'ri.")

        # Sarlavha va davomiylikni olish
        title = info.get('title', 'Video')
        duration = info.get('duration', 0)
        
        # 64 byte limitini aylanib o'tish uchun UUID yaratish
        media_uuid = str(uuid.uuid4())[:8]
        url_storage[media_uuid] = url # Keshga URL saqlash

        await status_msg.edit_text("⏳ Video yuklanmoqda...")
        
        # Videoni yuklab olish
        file_path = await MediaDownloader.download_video(url, media_uuid)
        
        if not file_path:
            return await status_msg.edit_text("❌ Xatolik: Video hajmi 50MB dan katta yoki yuklab bo'lmadi.")

        # Inline tugma yaratish
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="🎵 MP3 formatda yuklash", callback_data=f"mp3_{media_uuid}"))
        
        video = FSInputFile(file_path)
        await message.answer_video(
            video, 
            caption=f"🎬 <b>{title}</b>", 
            reply_markup=kb.as_markup(),
            parse_mode="HTML"
        )
        
        await status_msg.delete()
        await safe_remove(file_path) # Yuborgandan keyin o'chirish

    except Exception as e:
        logger.error(f"Handler error: {e}")
        await status_msg.edit_text("❌ Kutilmagan xatolik yuz berdi.")

# ------------------------------------------------------------------
# 12. MUSIQA QIDIRISH MANTIQI
# ------------------------------------------------------------------

@user_router.message(F.text == "🔍 Musiqa qidirish")
async def music_search_start(message: Message, state: FSMContext):
    await message.answer("🎵 Musiqa nomini yoki ijrochini yozing:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(SearchStates.waiting_for_query)

@user_router.message(SearchStates.waiting_for_query)
async def process_music_search(message: Message, state: FSMContext):
    query = message.text
    status_msg = await message.answer(f"🔎 <b>'{query}'</b> bo'yicha qidirilmoqda...")
    
    try:
        entries = await MediaDownloader.get_info(f"ytsearch10:{query}")
        if not entries or 'entries' not in entries:
            return await status_msg.edit_text("❌ Hech narsa topilmadi.")

        kb = InlineKeyboardBuilder()
        results_text = "<b>🔍 Topilgan natijalar:</b>\n\n"
        
        for i, entry in enumerate(entries['entries'], 1):
            if not entry: continue
            
            e_id = entry.get('id')
            e_title = entry.get('title', 'Noma\'lum')[:50]
            e_url = f"https://www.youtube.com/watch?v={e_id}"
            
            # Keshga saqlash
            m_uuid = str(uuid.uuid4())[:8]
            url_storage[m_uuid] = e_url
            
            results_text += f"{i}. {e_title}\n"
            kb.row(InlineKeyboardButton(text=f"{i}", callback_data=f"yt_{m_uuid}"))
            
        kb.adjust(5) # Tugmalarni 5 qatordan taxlash
        await status_msg.edit_text(results_text, reply_markup=kb.as_markup(), parse_mode="HTML")
        await state.clear()

    except Exception as e:
        logger.error(f"Search error: {e}")
        await status_msg.edit_text("❌ Qidiruvda xatolik yuz berdi.")

# ------------------------------------------------------------------
# 13. CALLBACK HANDLERLAR (mp3, yt, check_sub)
# ------------------------------------------------------------------

@user_router.callback_query(F.data.startswith("mp3_"))
async def cb_mp3_extract(call: CallbackQuery):
    media_uuid = call.data.split("_")[1]
    url = url_storage.get(media_uuid)
    
    if not url:
        return await call.answer("❌ Havola eskirgan yoki topilmadi.", show_alert=True)

    await call.answer("🎵 Audio ajratib olinmoqda...")
    status_msg = await call.message.answer("⏳ MP3 tayyorlanmoqda, kuting...")
    
    try:
        file_path = await MediaDownloader.extract_mp3(url, media_uuid)
        if file_path:
            audio = FSInputFile(file_path)
            await call.message.answer_audio(audio)
            await status_msg.delete()
            await safe_remove(file_path)
        else:
            await status_msg.edit_text("❌ Audioni yuklab bo'lmadi.")
    except Exception as e:
        logger.error(f"Callback MP3 error: {e}")
        await status_msg.edit_text("❌ Xatolik yuz berdi.")

@user_router.callback_query(F.data.startswith("yt_"))
async def cb_yt_download(call: CallbackQuery):
    media_uuid = call.data.split("_")[1]
    url = url_storage.get(media_uuid)
    
    if not url:
        return await call.answer("❌ Ma'lumot topilmadi.", show_alert=True)

    await call.answer("📥 Yuklanmoqda...")
    status_msg = await call.message.answer("⏳ Musiqa yuklab olinmoqda...")
    
    try:
        file_path = await MediaDownloader.extract_mp3(url, media_uuid)
        if file_path:
            await call.message.answer_audio(FSInputFile(file_path))
            await status_msg.delete()
            await safe_remove(file_path)
        else:
            await status_msg.edit_text("❌ Faylni yuklab bo'lmadi.")
    except Exception as e:
        logger.error(f"Callback YT error: {e}")

@user_router.callback_query(F.data == "check_sub")
async def cb_check_sub(call: CallbackQuery, bot: Bot):
    subscribed = await is_subscribed(bot, call.from_user.id)
    if subscribed:
        await call.answer("✅ Rahmat! Endi botdan foydalanishingiz mumkin.", show_alert=True)
        await call.message.delete()
        # Foydalanuvchiga start xabarini qayta yuborish
        await cmd_start(call.message, None) 
    else:
        await call.answer("❌ Siz hali ham kanalga obuna bo'lmagansiz!", show_alert=True)
        
# ------------------------------------------------------------------
# 14. ADMIN HANDLERLARI (FULL PANEL)
# ------------------------------------------------------------------
admin_router = Router()

@admin_router.message(Command("admin"))
async def cmd_admin(message: Message, is_admin: bool):
    if not is_admin:
        return
    await message.answer("👑 <b>Admin boshqaruv paneliga xush kelibsiz!</b>", 
                         reply_markup=get_admin_main_kb(), parse_mode="HTML")

@admin_router.message(F.text == "🏠 Asosiy menyu")
async def back_to_main(message: Message):
    await message.answer("Bosh menyuga qaytdingiz.", reply_markup=get_main_kb())

@admin_router.message(F.text == "📊 Statistika")
async def admin_stats(message: Message, is_admin: bool):
    if not is_admin: return
    async with async_session() as session:
        # Jami foydalanuvchilar
        total_users = await session.execute(select(func.count(User.id)))
        # Faol foydalanuvchilar (Oxirgi 24 soatda qo'shilganlar misolida)
        active_users = await session.execute(select(func.count(User.id)).where(User.is_active == True))
        
        text = (
            "📊 <b>Bot Statistikasi:</b>\n\n"
            f"👤 Jami foydalanuvchilar: <b>{total_users.scalar()}</b>\n"
            f"✅ Faol foydalanuvchilar: <b>{active_users.scalar()}</b>\n"
            f"🕒 Hozirgi vaqt: <code>{datetime.now().strftime('%Y-%m-%d %H:%M')}</code>"
        )
        await message.answer(text, parse_mode="HTML")

# --- BROADCAST LOGIC ---
@admin_router.message(F.text == "📢 Broadcast")
async def broadcast_start(message: Message, is_admin: bool, state: FSMContext):
    if not is_admin: return
    await message.answer("📢 Reklama xabarini yuboring.\nBu xabar, rasm, video yoki audio bo'lishi mumkin.")
    await state.set_state(AdminStates.waiting_for_broadcast_content)

@admin_router.message(AdminStates.waiting_for_broadcast_content)
async def process_broadcast(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    async with async_session() as session:
        users_res = await session.execute(select(User.user_id))
        user_ids = users_res.scalars().all()

    count, blocked = 0, 0
    status_msg = await message.answer(f"🚀 Xabar yuborish boshlandi: 0/{len(user_ids)}")

    for idx, u_id in enumerate(user_ids):
        try:
            await message.copy_to(chat_id=u_id)
            count += 1
        except (TelegramForbiddenError, TelegramBadRequest):
            blocked += 1
            # Bazada foydalanuvchini nofaol qilish
            async with async_session() as session:
                await session.execute(update(User).where(User.user_id == u_id).values(is_active=False))
                await session.commit()
        except Exception as e:
            logger.error(f"Broadcast error for {u_id}: {e}")
        
        # Har 50 ta xabarda statusni yangilash
        if idx % 50 == 0:
            try: await status_msg.edit_text(f"🚀 Yuborilmoqda: {idx}/{len(user_ids)}")
            except: pass
        
        await asyncio.sleep(0.05) # Flood limit oldini olish

    await message.answer(
        f"✅ <b>Broadcast yakunlandi!</b>\n\n"
        f"👤 Qabul qildi: <b>{count}</b>\n"
        f"🚫 Bloklaganlar: <b>{blocked}</b>", 
        parse_mode="HTML"
    )

# --- BOT SETTINGS ---
@admin_router.message(F.text == "🛑 Bot ON/OFF")
async def toggle_bot(message: Message, is_admin: bool):
    if not is_admin: return
    async with async_session() as session:
        res = await session.execute(select(BotSettings).limit(1))
        settings = res.scalar()
        settings.bot_enabled = not settings.bot_enabled
        status = "YOQILDI ✅" if settings.bot_enabled else "O'CHIRILDI 🛑"
        await session.commit()
        await message.answer(f"Bot holati: <b>{status}</b>", parse_mode="HTML")

@admin_router.message(F.text == "⚙️ Majburiy obuna")
async def toggle_sub(message: Message, is_admin: bool):
    if not is_admin: return
    async with async_session() as session:
        res = await session.execute(select(BotSettings).limit(1))
        settings = res.scalar()
        settings.sub_required = not settings.sub_required
        status = "YOQILDI (Majburiy) ✅" if settings.sub_required else "O'CHIRILDI (Ixtiyoriy) 🔓"
        await session.commit()
        await message.answer(f"Majburiy obuna: <b>{status}</b>", parse_mode="HTML")

# --- ADMIN MANAGEMENT ---
@admin_router.message(F.text == "➕ Admin qo'shish")
async def add_admin_start(message: Message, is_admin: bool, state: FSMContext):
    if not is_admin: return
    await message.answer("Yangi adminning <b>User ID</b> sini yuboring:")
    await state.set_state(AdminStates.waiting_for_new_admin_id)

@admin_router.message(AdminStates.waiting_for_new_admin_id)
async def process_add_admin(message: Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("ID faqat raqamlardan iborat bo'lishi kerak!")
    
    new_admin_id = int(message.text)
    async with async_session() as session:
        check = await session.execute(select(AdminUser).where(AdminUser.user_id == new_admin_id))
        if check.scalar():
            await message.answer("Ushbu foydalanuvchi allaqachon admin!")
        else:
            session.add(AdminUser(user_id=new_admin_id))
            await session.commit()
            await message.answer(f"✅ {new_admin_id} muvaffaqiyatli admin qilib tayinlandi.")
    await state.clear()

@admin_router.message(F.text == "➖ Admin o'chirish")
async def del_admin_start(message: Message, is_admin: bool, state: FSMContext):
    if not is_admin: return
    async with async_session() as session:
        admins = await session.execute(select(AdminUser))
        admin_list = admins.scalars().all()
        text = "<b>Adminlar ro'yxati:</b>\n\n"
        for a in admin_list:
            text += f"ID: <code>{a.user_id}</code> (Qo'shilgan: {a.added_at.strftime('%Y-%m-%d')})\n"
        
        await message.answer(f"{text}\nO'chirish uchun ID yuboring:", parse_mode="HTML")
        await state.set_state(AdminStates.waiting_for_del_admin_id)

@admin_router.message(AdminStates.waiting_for_del_admin_id)
async def process_del_admin(message: Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("ID faqat raqamlardan iborat bo'lishi kerak!")
    
    target_id = int(message.text)
    if target_id in Config.ADMIN_IDS:
        return await message.answer("Asosiy (Owner) adminlarni o'chirib bo'lmaydi!")

    async with async_session() as session:
        await session.execute(delete(AdminUser).where(AdminUser.user_id == target_id))
        await session.commit()
    await message.answer(f"✅ Admin {target_id} muvaffaqiyatli o'chirildi.")
    await state.clear()

@admin_router.message(F.text == "👥 Foydalanuvchilar ro'yxati")
async def list_users_admin(message: Message, is_admin: bool):
    if not is_admin: return
    async with async_session() as session:
        res = await session.execute(select(User).order_by(desc(User.joined_at)).limit(50))
        users = res.scalars().all()
        
        text = "👥 <b>Oxirgi 50 foydalanuvchi:</b>\n\n"
        for u in users:
            text += f"• <code>{u.user_id}</code> | @{u.username or "yo'q"} | {u.full_name[:15]}\n"
        
        await message.answer(text, parse_mode="HTML")
        
# ------------------------------------------------------------------
# 15. ERROR HANDLING & CLEANUP TASK
# ------------------------------------------------------------------
@router.errors()
async def global_error_handler(event: types.ErrorEvent):
    """Barcha kutilmagan xatolarni ushlash"""
    logger.error(f"Kutilmagan xato: {event.exception}", exc_info=True)
    try:
        if event.update.message:
            await event.update.message.answer("❌ Tizimda xatolik yuz berdi. Dasturchilar xabardor qilindi.")
    except:
        pass

async def periodic_cleanup():
    """Eskirgan kesh va yuklangan fayllarni har soatda tozalash"""
    while True:
        try:
            # 1. Keshni tozalash
            url_storage.clear()
            
            # 2. Downloads papkasini tozalash
            now = time.time()
            for f in os.listdir(Config.DOWNLOAD_DIR):
                f_path = os.path.join(Config.DOWNLOAD_DIR, f)
                if os.stat(f_path).st_mtime < (now - Config.TEMP_CACHE_TTL):
                    if os.path.isfile(f_path):
                        os.remove(f_path)
            logger.info("Cleanup task completed successfully.")
        except Exception as e:
            logger.error(f"Cleanup error: {e}")
        
        await asyncio.sleep(3600) # Har soatda bir marta

# ------------------------------------------------------------------
# 16. WEBHOOK & FASTAPI INTEGRATION
# ------------------------------------------------------------------
app = FastAPI()
bot = Bot(token=Config.BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher(storage=MemoryStorage())

@app.on_event("startup")
async def on_startup():
    """Bot ishga tushganda bajariladigan amallar"""
    # 1. Database yaratish
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all())
    
    # 2. Bot sozlamalarini tekshirish/yaratish
    async with async_session() as session:
        res = await session.execute(select(BotSettings).limit(1))
        if not res.scalar():
            session.add(BotSettings(sub_required=True, bot_enabled=True))
            await session.commit()

    # 3. Router va Middlewarelarni ulash
    dp.include_router(admin_router)
    dp.include_router(user_router)
    dp.message.outer_middleware(GlobalMiddleware())
    dp.callback_query.outer_middleware(GlobalMiddleware())

    # 4. Webhook o'rnatish
    webhook_info = await bot.get_webhook_info()
    if webhook_info.url != Config.WEBHOOK_URL:
        await bot.set_webhook(url=Config.WEBHOOK_URL, drop_pending_updates=True)
    
    # 5. Fon vazifasini ishga tushirish (Cleanup)
    asyncio.create_task(periodic_cleanup())
    
    logger.info("Bot successfully started on Webhook!")

@app.on_event("shutdown")
async def on_shutdown():
    """Bot to'xtaganda sessiyalarni yopish"""
    await bot.session.close()
    await engine.dispose()

@app.post(Config.WEBHOOK_PATH)
async def bot_webhook(request: Request):
    """Telegramdan kelgan update'larni qabul qilish"""
    update = await request.json()
    tg_update = types.Update(**update)
    await dp.feed_update(bot=bot, update=tg_update)

@app.get("/health")
async def health_check():
    """Server holatini tekshirish uchun endpoint"""
    return {
        "status": "alive", 
        "time": str(datetime.now()),
        "cache_entries": len(url_storage)
    }

# ------------------------------------------------------------------
# 17. MAIN ENTRY POINT
# ------------------------------------------------------------------
if __name__ == "__main__":
    # Render.com yoki boshqa PaaS platformalar uchun port
    PORT = int(os.getenv("PORT", 8000))
    
    # Uvicorn orqali FastAPI serverini ishga tushirish
    uvicorn.run(app, host="0.0.0.0", port=PORT)