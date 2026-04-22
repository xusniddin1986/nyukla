from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.error import TelegramError
from database import db
from config import OWNER_ID


async def check_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check if user is subscribed to all required channels. Returns True if ok."""
    user = update.effective_user
    if not user:
        return False

    # Owner always passes
    if user.id == OWNER_ID:
        db.add_user(user.id, user.username, user.full_name)
        return True

    channels = db.get_required_channels()
    if not channels:
        db.add_user(user.id, user.username, user.full_name)
        return True

    not_subscribed = []
    for channel in channels:
        try:
            member = await context.bot.get_chat_member(channel, user.id)
            if member.status in ("left", "kicked", "banned"):
                not_subscribed.append(channel)
        except TelegramError:
            not_subscribed.append(channel)

    if not_subscribed:
        buttons = []
        for ch in not_subscribed:
            try:
                chat = await context.bot.get_chat(ch)
                invite = chat.invite_link or f"https://t.me/{ch.lstrip('@')}"
                buttons.append([InlineKeyboardButton(f"📢 {chat.title}", url=invite)])
            except:
                buttons.append([InlineKeyboardButton(f"📢 {ch}", url=f"https://t.me/{ch.lstrip('@')}")])

        buttons.append([InlineKeyboardButton("✅ Obuna bo'ldim", callback_data="check_sub")])
        markup = InlineKeyboardMarkup(buttons)

        text = (
            "⚠️ <b>Botdan foydalanish uchun kanalga obuna bo'ling!</b>\n\n"
            "Quyidagi kanalga obuna bo'ling va ✅ <b>Obuna bo'ldim</b> tugmasini bosing:"
        )
        msg = update.message or (update.callback_query.message if update.callback_query else None)
        if msg:
            await msg.reply_text(text, reply_markup=markup, parse_mode='HTML')
        return False

    db.add_user(user.id, user.username, user.full_name)
    return True


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.add_user(user.id, user.username, user.full_name)

    if not await check_subscription(update, context):
        return

    text = (
        f"👋 Salom, <b>{user.first_name}</b>!\n\n"
        "🤖 <b>NyuklaBot</b>ga xush kelibsiz!\n\n"
        "📥 <b>Men nima qila olaman?</b>\n"
        "• Instagram, YouTube, TikTok videolarini yuklash\n"
        "• Musiqa qidirish va yuklab olish\n\n"
        "🔗 Video linkini yuboring yoki 🎵 musiqa nomini yozing!"
    )
    await update.message.reply_text(text, parse_mode='HTML')
