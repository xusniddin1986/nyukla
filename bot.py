import os
import logging
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    CallbackQuery, Message
)
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from config import (
    BOT_TOKEN, ADMIN_IDS, CHANNEL_ID, CHANNEL_LINK,
    WEBHOOK_URL, WEBHOOK_PATH, PORT
)
from database import Database
from downloader import VideoDownloader
from music_search import MusicSearcher

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
db = Database()
downloader = VideoDownloader()
music_searcher = MusicSearcher()


# ─── FSM States ───────────────────────────────────────────────
class AdminStates(StatesGroup):
    broadcast_message = State()
    broadcast_photo = State()
    broadcast_video = State()
    broadcast_audio = State()
    add_admin = State()
    remove_admin = State()
    add_channel = State()
    remove_channel = State()


# ─── Helpers ──────────────────────────────────────────────────
async def check_subscription(user_id: int) -> bool:
    channels = db.get_required_channels()
    if not channels:
        return True
    for channel in channels:
        try:
            member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status in ['left', 'kicked', 'banned']:
                return False
        except Exception:
            return False
    return True


async def send_subscription_message(message: Message):
    channels = db.get_required_channels()
    buttons = []
    for ch in channels:
        try:
            chat = await bot.get_chat(ch)
            invite = await bot.export_chat_invite_link(ch)
            buttons.append([InlineKeyboardButton(
                text="📢 " + chat.title,
                url=invite
            )])
        except Exception:
            buttons.append([InlineKeyboardButton(
                text="📢 Kanal",
                url=CHANNEL_LINK
            )])
    buttons.append([InlineKeyboardButton(
        text="✅ Obuna bo'ldim",
        callback_data="check_subscription"
    )])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(
        "⚠️ <b>Bot ishlashi uchun kanalga obuna bo'ling!</b>\n\n"
        "Quyidagi kanallarga obuna bo'lib, so'ng '✅ Obuna bo'ldim' tugmasini bosing:",
        reply_markup=kb,
        parse_mode="HTML"
    )


def is_admin(user_id: int) -> bool:
    admins = db.get_admins()
    return user_id in ADMIN_IDS or user_id in admins


def admin_keyboard():
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📢 Xabar yuborish"), KeyboardButton(text="👥 Foydalanuvchilar")],
        [KeyboardButton(text="📊 Statistika"), KeyboardButton(text="🔔 Majburiy obuna")],
        [KeyboardButton(text="👑 Adminlar"), KeyboardButton(text="🤖 Bot holati")],
        [KeyboardButton(text="🏠 Asosiy menyu")]
    ], resize_keyboard=True)
    return kb


def is_video_link(text: str) -> bool:
    domains = [
        'youtube.com', 'youtu.be', 'instagram.com', 'facebook.com',
        'fb.watch', 'tiktok.com', 'pinterest.com', 'pin.it',
        'vimeo.com', 'twitter.com', 'x.com', 't.me'
    ]
    return any(d in text.lower() for d in domains)


# ─── /start ───────────────────────────────────────────────────
@dp.message(CommandStart())
async def cmd_start(message: Message):
    user = message.from_user
    db.add_user(user.id, user.username, user.full_name)

    if not await check_subscription(user.id):
        await send_subscription_message(message)
        return

    text = (
        "👋 Salom, <b>" + user.full_name + "</b>!\n\n"
        "🎵 <b>NyuklaBot</b> — video va musiqa yuklovchi bot\n\n"
        "📌 <b>Nima qila olaman:</b>\n"
        "• Video havolasini yuboring → videoni yuklab beraman\n"
        "• Musiqa nomi/ijrochi ismini yuboring → ro'yhat chiqaraman\n\n"
        "⚡ Tez, bepul va qulay!"
    )
    await message.answer(text, parse_mode="HTML")


# ─── /help ────────────────────────────────────────────────────
@dp.message(Command("help"))
async def cmd_help(message: Message):
    if not await check_subscription(message.from_user.id):
        await send_subscription_message(message)
        return
    await message.answer(
        "📖 <b>Yordam</b>\n\n"
        "🔗 <b>Video yuklab olish:</b>\n"
        "YouTube, Instagram, Facebook, TikTok, Pinterest va boshqa platformalardan "
        "video havolasini yuboring\n\n"
        "🎵 <b>Musiqa qidirish:</b>\n"
        "Musiqa nomi yoki ijrochi ismini yuboring, bot 1-5 ta natija ko'rsatadi\n\n"
        "📋 <b>Buyruqlar:</b>\n"
        "/start — Botni ishga tushirish\n"
        "/help — Yordam\n"
        "/about — Bot haqida\n"
        "/admin — Admin panel",
        parse_mode="HTML"
    )


# ─── /about ───────────────────────────────────────────────────
@dp.message(Command("about"))
async def cmd_about(message: Message):
    if not await check_subscription(message.from_user.id):
        await send_subscription_message(message)
        return
    await message.answer(
        "ℹ️ <b>NyuklaBot haqida</b>\n\n"
        "🤖 Bot: @NyuklaBot\n"
        "🎯 Maqsad: Video va musiqa yuklab berish\n"
        "🌐 Platformalar: YouTube, Instagram, Facebook, TikTok, Pinterest va boshqalar\n\n"
        "💡 <i>Istalgan savollar uchun adminga murojaat qiling</i>",
        parse_mode="HTML"
    )


# ─── /admin ───────────────────────────────────────────────────
@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Sizda admin huquqi yo'q!")
        return
    await message.answer(
        "👑 <b>Admin Panel</b>\n\nXohlagan bo'limni tanlang:",
        reply_markup=admin_keyboard(),
        parse_mode="HTML"
    )


# ─── Subscription Check ────────────────────────────────────────
@dp.callback_query(F.data == "check_subscription")
async def check_sub_callback(callback: CallbackQuery):
    if await check_subscription(callback.from_user.id):
        await callback.message.delete()
        name = callback.from_user.full_name
        await callback.message.answer(
            "✅ <b>Rahmat, " + name + "!</b>\n\n"
            "Endi botdan foydalanishingiz mumkin 🎉\n"
            "Video havola yoki musiqa nomini yuboring!",
            parse_mode="HTML"
        )
    else:
        await callback.answer("❌ Siz hali obuna bo'lmadingiz!", show_alert=True)


# ─── Music Download Callback ──────────────────────────────────
@dp.callback_query(F.data.startswith("dl_music_"))
async def download_music_callback(callback: CallbackQuery):
    if not await check_subscription(callback.from_user.id):
        await callback.answer("❌ Avval kanalga obuna bo'ling!", show_alert=True)
        return

    track_id = callback.data.replace("dl_music_", "")
    await callback.answer("⏳ Musiqa yuklanmoqda...")

    msg = await callback.message.answer("⏳ Musiqa yuklanmoqda, iltimos kuting...")

    try:
        result = await music_searcher.download_track(track_id)
        if result and result.get('file'):
            title = result.get('title') or "Noma'lum"
            artist = result.get('artist') or "Noma'lum"
            caption = (
                "🎵 <b>" + title + "</b>\n"
                "👤 " + artist + "\n\n"
                "📥 @NyuklaBot orqali istagan musiqangizni tez va oson toping!"
            )
            audio_file = types.FSInputFile(result['file'])
            await bot.send_audio(
                callback.from_user.id,
                audio=audio_file,
                caption=caption,
                parse_mode="HTML"
            )
            if os.path.exists(result['file']):
                os.remove(result['file'])
        else:
            await callback.message.answer("❌ Musiqa yuklab bo'lmadi. Qayta urinib ko'ring.")
    except Exception as e:
        logger.error("Music download error: %s", e)
        await callback.message.answer("❌ Xatolik yuz berdi. Qayta urinib ko'ring.")
    finally:
        await msg.delete()


# ─── Video Music Search Callback ─────────────────────────────
@dp.callback_query(F.data.startswith("video_music_"))
async def video_music_callback(callback: CallbackQuery):
    if not await check_subscription(callback.from_user.id):
        await callback.answer("❌ Avval kanalga obuna bo'ling!", show_alert=True)
        return

    video_title = callback.data.replace("video_music_", "")
    await callback.answer("🔍 Musiqa qidirilmoqda...")

    msg = await callback.message.answer("🔍 Videodagi musiqa qidirilmoqda...")

    try:
        results = await music_searcher.search(video_title, limit=5)
        if results:
            text = "🎵 <b>Mos musiqalar:</b>\n\n"
            buttons = []
            for i, track in enumerate(results[:5], 1):
                text += str(i) + ". <b>" + track['title'] + "</b> — " + track['artist'] + "\n"
                btn_text = str(i) + ". " + track['title'][:30]
                buttons.append([InlineKeyboardButton(
                    text=btn_text,
                    callback_data="dl_music_" + track['id']
                )])
            text += "\n📥 @NyuklaBot orqali istagan musiqangizni tez va oson toping!"
            kb = InlineKeyboardMarkup(inline_keyboard=buttons)
            await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
        else:
            await callback.message.answer("❌ Musiqa topilmadi.")
    except Exception as e:
        logger.error("Video music search error: %s", e)
        await callback.message.answer("❌ Xatolik yuz berdi.")
    finally:
        await msg.delete()


# ─── Admin: Statistika ────────────────────────────────────────
@dp.message(F.text == "📊 Statistika")
async def admin_stats(message: Message):
    if not is_admin(message.from_user.id):
        return
    stats = db.get_stats()
    await message.answer(
        "📊 <b>Bot Statistikasi</b>\n\n"
        "👥 Jami foydalanuvchilar: <b>" + str(stats['total']) + "</b>\n"
        "📅 Bugun qo'shilganlar: <b>" + str(stats['today']) + "</b>\n"
        "📆 Shu hafta: <b>" + str(stats['week']) + "</b>\n"
        "📆 Shu oy: <b>" + str(stats['month']) + "</b>",
        parse_mode="HTML",
        reply_markup=admin_keyboard()
    )


# ─── Admin: Foydalanuvchilar ──────────────────────────────────
@dp.message(F.text == "👥 Foydalanuvchilar")
async def admin_users(message: Message):
    if not is_admin(message.from_user.id):
        return
    users = db.get_all_users(limit=20)
    text = "👥 <b>Oxirgi 20 foydalanuvchi:</b>\n\n"
    for u in users:
        name = u[2] if u[2] else "Nomsiz"
        username = "@" + u[1] if u[1] else "username yo'q"
        text += "• " + name + " | " + username + " | <code>" + str(u[0]) + "</code>\n"
    await message.answer(text, parse_mode="HTML", reply_markup=admin_keyboard())


# ─── Admin: Bot holati ────────────────────────────────────────
@dp.message(F.text == "🤖 Bot holati")
async def admin_bot_status(message: Message):
    if not is_admin(message.from_user.id):
        return
    stats = db.get_stats()
    channels = db.get_required_channels()
    admins = db.get_admins()
    text = (
        "🤖 <b>Bot Holati</b>\n\n"
        "✅ Bot ishlayapti\n"
        "👥 Foydalanuvchilar: " + str(stats['total']) + "\n"
        "📢 Majburiy kanallar: " + str(len(channels)) + "\n"
        "👑 Adminlar: " + str(len(admins) + len(ADMIN_IDS)) + "\n"
        "🌐 Webhook: Faol"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=admin_keyboard())


# ─── Admin: Majburiy obuna ────────────────────────────────────
@dp.message(F.text == "🔔 Majburiy obuna")
async def admin_channels_menu(message: Message):
    if not is_admin(message.from_user.id):
        return
    channels = db.get_required_channels()
    text = "🔔 <b>Majburiy kanallar:</b>\n\n"
    if channels:
        for ch in channels:
            text += "• <code>" + ch + "</code>\n"
    else:
        text += "Hech qanday kanal yo'q\n"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Kanal qo'shish", callback_data="add_channel")],
        [InlineKeyboardButton(text="➖ Kanal o'chirish", callback_data="remove_channel")]
    ])
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


# ─── Admin: Adminlar ──────────────────────────────────────────
@dp.message(F.text == "👑 Adminlar")
async def admin_admins_menu(message: Message):
    if not is_admin(message.from_user.id):
        return
    admins = db.get_admins()
    all_admins = list(set(ADMIN_IDS + admins))
    text = "👑 <b>Adminlar ro'yxati:</b>\n\n"
    for a in all_admins:
        text += "• <code>" + str(a) + "</code>\n"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Admin qo'shish", callback_data="add_admin")],
        [InlineKeyboardButton(text="➖ Admin o'chirish", callback_data="del_admin")]
    ])
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


# ─── Admin: Asosiy menyu ──────────────────────────────────────
@dp.message(F.text == "🏠 Asosiy menyu")
async def main_menu(message: Message):
    await message.answer("🏠 Asosiy menyuga qaytdingiz", reply_markup=ReplyKeyboardRemove())


# ─── Admin Callbacks: Channel ─────────────────────────────────
@dp.callback_query(F.data == "add_channel")
async def cb_add_channel(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "📢 Kanal username yuboring (masalan: @mychannel yoki -100xxxxxxxxx):"
    )
    await state.set_state(AdminStates.add_channel)
    await callback.answer()


@dp.message(AdminStates.add_channel)
async def process_add_channel(message: Message, state: FSMContext):
    ch = message.text.strip()
    db.add_required_channel(ch)
    await message.answer(
        "✅ <code>" + ch + "</code> kanal qo'shildi!",
        parse_mode="HTML",
        reply_markup=admin_keyboard()
    )
    await state.clear()


@dp.callback_query(F.data == "remove_channel")
async def cb_remove_channel(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("📢 O'chirmoqchi bo'lgan kanal username'ini yuboring:")
    await state.set_state(AdminStates.remove_channel)
    await callback.answer()


@dp.message(AdminStates.remove_channel)
async def process_remove_channel(message: Message, state: FSMContext):
    ch = message.text.strip()
    db.remove_required_channel(ch)
    await message.answer(
        "✅ <code>" + ch + "</code> kanal o'chirildi!",
        parse_mode="HTML",
        reply_markup=admin_keyboard()
    )
    await state.clear()


# ─── Admin Callbacks: Admin ───────────────────────────────────
@dp.callback_query(F.data == "add_admin")
async def cb_add_admin(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("👤 Yangi admin user ID'sini yuboring:")
    await state.set_state(AdminStates.add_admin)
    await callback.answer()


@dp.message(AdminStates.add_admin)
async def process_add_admin(message: Message, state: FSMContext):
    try:
        admin_id = int(message.text.strip())
        db.add_admin(admin_id)
        await message.answer(
            "✅ Admin qo'shildi: <code>" + str(admin_id) + "</code>",
            parse_mode="HTML",
            reply_markup=admin_keyboard()
        )
    except ValueError:
        await message.answer("❌ Noto'g'ri ID formati! Faqat raqam kiriting.")
    await state.clear()


@dp.callback_query(F.data == "del_admin")
async def cb_del_admin(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("👤 O'chirmoqchi bo'lgan admin ID'sini yuboring:")
    await state.set_state(AdminStates.remove_admin)
    await callback.answer()


@dp.message(AdminStates.remove_admin)
async def process_del_admin(message: Message, state: FSMContext):
    try:
        admin_id = int(message.text.strip())
        db.remove_admin(admin_id)
        await message.answer(
            "✅ Admin o'chirildi: <code>" + str(admin_id) + "</code>",
            parse_mode="HTML",
            reply_markup=admin_keyboard()
        )
    except ValueError:
        await message.answer("❌ Noto'g'ri ID formati! Faqat raqam kiriting.")
    await state.clear()


# ─── Admin: Broadcast Menu ────────────────────────────────────
@dp.message(F.text == "📢 Xabar yuborish")
async def admin_broadcast_menu(message: Message):
    if not is_admin(message.from_user.id):
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✉️ Matn", callback_data="bc_text")],
        [InlineKeyboardButton(text="🖼 Rasm", callback_data="bc_photo")],
        [InlineKeyboardButton(text="🎬 Video", callback_data="bc_video")],
        [InlineKeyboardButton(text="🎵 Audio", callback_data="bc_audio")]
    ])
    await message.answer("📢 <b>Xabar turini tanlang:</b>", reply_markup=kb, parse_mode="HTML")


@dp.callback_query(F.data == "bc_text")
async def bc_text(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("✉️ Yubormoqchi bo'lgan matnni kiriting:")
    await state.set_state(AdminStates.broadcast_message)
    await callback.answer()


@dp.message(AdminStates.broadcast_message)
async def do_broadcast_text(message: Message, state: FSMContext):
    users = db.get_all_users()
    sent, failed = 0, 0
    total = len(users)
    msg = await message.answer("⏳ Xabar yuborilmoqda... 0/" + str(total))
    for i, user in enumerate(users):
        try:
            await bot.send_message(user[0], message.text)
            sent += 1
        except Exception:
            failed += 1
        if i % 20 == 0:
            await msg.edit_text("⏳ Xabar yuborilmoqda... " + str(i) + "/" + str(total))
        await asyncio.sleep(0.05)
    await msg.edit_text(
        "✅ Xabar yuborildi!\n"
        "✅ Muvaffaqiyatli: " + str(sent) + "\n"
        "❌ Xato: " + str(failed)
    )
    await state.clear()


@dp.callback_query(F.data == "bc_photo")
async def bc_photo(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("🖼 Rasm va caption yuboring:")
    await state.set_state(AdminStates.broadcast_photo)
    await callback.answer()


@dp.message(AdminStates.broadcast_photo, F.photo)
async def do_broadcast_photo(message: Message, state: FSMContext):
    users = db.get_all_users()
    sent, failed = 0, 0
    total = len(users)
    photo = message.photo[-1].file_id
    caption = message.caption or ""
    msg = await message.answer("⏳ Rasm yuborilmoqda... 0/" + str(total))
    for i, user in enumerate(users):
        try:
            await bot.send_photo(user[0], photo, caption=caption)
            sent += 1
        except Exception:
            failed += 1
        if i % 20 == 0:
            await msg.edit_text("⏳ Rasm yuborilmoqda... " + str(i) + "/" + str(total))
        await asyncio.sleep(0.05)
    await msg.edit_text(
        "✅ Rasm yuborildi!\n"
        "✅ Muvaffaqiyatli: " + str(sent) + "\n"
        "❌ Xato: " + str(failed)
    )
    await state.clear()


@dp.callback_query(F.data == "bc_video")
async def bc_video(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("🎬 Video yuboring:")
    await state.set_state(AdminStates.broadcast_video)
    await callback.answer()


@dp.message(AdminStates.broadcast_video, F.video)
async def do_broadcast_video(message: Message, state: FSMContext):
    users = db.get_all_users()
    sent, failed = 0, 0
    total = len(users)
    video = message.video.file_id
    caption = message.caption or ""
    msg = await message.answer("⏳ Video yuborilmoqda... 0/" + str(total))
    for i, user in enumerate(users):
        try:
            await bot.send_video(user[0], video, caption=caption)
            sent += 1
        except Exception:
            failed += 1
        if i % 20 == 0:
            await msg.edit_text("⏳ Video yuborilmoqda... " + str(i) + "/" + str(total))
        await asyncio.sleep(0.05)
    await msg.edit_text(
        "✅ Video yuborildi!\n"
        "✅ Muvaffaqiyatli: " + str(sent) + "\n"
        "❌ Xato: " + str(failed)
    )
    await state.clear()


@dp.callback_query(F.data == "bc_audio")
async def bc_audio(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("🎵 Audio yuboring:")
    await state.set_state(AdminStates.broadcast_audio)
    await callback.answer()


@dp.message(AdminStates.broadcast_audio, F.audio)
async def do_broadcast_audio(message: Message, state: FSMContext):
    users = db.get_all_users()
    sent, failed = 0, 0
    total = len(users)
    audio = message.audio.file_id
    caption = message.caption or ""
    msg = await message.answer("⏳ Audio yuborilmoqda... 0/" + str(total))
    for i, user in enumerate(users):
        try:
            await bot.send_audio(user[0], audio, caption=caption)
            sent += 1
        except Exception:
            failed += 1
        if i % 20 == 0:
            await msg.edit_text("⏳ Audio yuborilmoqda... " + str(i) + "/" + str(total))
        await asyncio.sleep(0.05)
    await msg.edit_text(
        "✅ Audio yuborildi!\n"
        "✅ Muvaffaqiyatli: " + str(sent) + "\n"
        "❌ Xato: " + str(failed)
    )
    await state.clear()


# ─── Main Message Handler ─────────────────────────────────────
@dp.message(F.text)
async def handle_text(message: Message):
    user = message.from_user
    db.add_user(user.id, user.username, user.full_name)

    if not await check_subscription(user.id):
        await send_subscription_message(message)
        return

    text = message.text.strip()

    # Admin tugmalar — yuqoridagi handlerlarda ishlanadi
    admin_buttons = [
        "📢 Xabar yuborish", "👥 Foydalanuvchilar", "📊 Statistika",
        "🔔 Majburiy obuna", "👑 Adminlar", "🤖 Bot holati", "🏠 Asosiy menyu"
    ]
    if is_admin(user.id) and text in admin_buttons:
        return

    # Video havola tekshiruvi
    if is_video_link(text):
        wait_msg = await message.answer("⏳ Video yuklanmoqda, iltimos kuting...")
        try:
            result = await downloader.download(text)
            if result and result.get('file'):
                video_title = result.get('title') or 'video'
                safe_title = video_title[:30].replace(" ", "_")

                kb = InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(
                        text="🎵 Musiqani yuklab olish",
                        callback_data="video_music_" + safe_title
                    )
                ]])

                caption = "📥 @NyuklaBot orqali yuklab olindi"
                video_file = types.FSInputFile(result['file'])
                await bot.send_video(
                    message.chat.id,
                    video=video_file,
                    caption=caption,
                    reply_markup=kb
                )
                if os.path.exists(result['file']):
                    os.remove(result['file'])
            else:
                await message.answer(
                    "❌ Video yuklab bo'lmadi.\n\n"
                    "Sabablari:\n"
                    "• Havola noto'g'ri\n"
                    "• Video yopiq/private\n"
                    "• Fayl juda katta (50MB+)"
                )
        except Exception as e:
            logger.error("Download error: %s", e)
            await message.answer("❌ Xatolik yuz berdi. Qayta urinib ko'ring.")
        finally:
            await wait_msg.delete()
        return

    # Musiqa qidirish
    wait_msg = await message.answer("🔍 Musiqa qidirilmoqda...")
    try:
        results = await music_searcher.search(text, limit=5)
        if results:
            resp = "🎵 <b>Qidiruv natijalari:</b>\n\n"
            buttons = []
            for i, track in enumerate(results[:5], 1):
                duration = track.get('duration', '')
                dur_str = " [" + duration + "]" if duration else ""
                resp += str(i) + ". <b>" + track['title'] + "</b> — " + track['artist'] + dur_str + "\n"
                btn_text = str(i) + ". " + track['title'][:35]
                buttons.append([InlineKeyboardButton(
                    text=btn_text,
                    callback_data="dl_music_" + track['id']
                )])

            resp += "\n📥 @NyuklaBot orqali istagan musiqangizni tez va oson toping!"
            kb = InlineKeyboardMarkup(inline_keyboard=buttons)
            await message.answer(resp, reply_markup=kb, parse_mode="HTML")
        else:
            await message.answer(
                "❌ Hech narsa topilmadi.\n"
                "Musiqa nomini to'liqroq yoki inglizcha yozing."
            )
    except Exception as e:
        logger.error("Search error: %s", e)
        await message.answer("❌ Qidirishda xatolik yuz berdi.")
    finally:
        await wait_msg.delete()


# ─── Health Check ─────────────────────────────────────────────
async def health_check(request):
    return web.Response(text="OK", status=200)


# ─── Startup / Shutdown ───────────────────────────────────────
async def on_startup(app):
    await bot.set_webhook(WEBHOOK_URL + WEBHOOK_PATH)
    logger.info("Webhook set: %s%s", WEBHOOK_URL, WEBHOOK_PATH)


async def on_shutdown(app):
    await bot.delete_webhook()
    await bot.session.close()


# ─── Entry Point ──────────────────────────────────────────────
def main():
    if WEBHOOK_URL:
        app = web.Application()
        app.on_startup.append(on_startup)
        app.on_shutdown.append(on_shutdown)
        app.router.add_get('/health', health_check)
        app.router.add_get('/', health_check)

        SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
        setup_application(app, dp, bot=bot)

        web.run_app(app, host="0.0.0.0", port=PORT)
    else:
        asyncio.run(dp.start_polling(bot))


if __name__ == "__main__":
    main()