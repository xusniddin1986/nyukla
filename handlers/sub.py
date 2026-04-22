from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.error import TelegramError
from database import db
from config import OWNER_ID


async def check_sub(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    if not user:
        return False
    if user.id == OWNER_ID:
        db.add_user(user.id, user.username, user.full_name)
        return True

    channels = db.get_channels()
    if not channels:
        db.add_user(user.id, user.username, user.full_name)
        return True

    not_subbed = []
    for ch in channels:
        try:
            member = await context.bot.get_chat_member(ch, user.id)
            if member.status in ("left", "kicked"):
                not_subbed.append(ch)
        except TelegramError:
            not_subbed.append(ch)

    if not_subbed:
        buttons = []
        for ch in not_subbed:
            try:
                chat = await context.bot.get_chat(ch)
                link = chat.invite_link or f"https://t.me/{ch.lstrip('@')}"
                buttons.append([InlineKeyboardButton(f"📢 {chat.title}", url=link)])
            except:
                buttons.append([InlineKeyboardButton(f"📢 {ch}", url=f"https://t.me/{ch.lstrip('@')}")])
        buttons.append([InlineKeyboardButton("✅ Tekshirish", callback_data="check_sub")])

        msg = update.message or (update.callback_query.message if update.callback_query else None)
        if msg:
            await msg.reply_text(
                "⚠️ <b>Botdan foydalanish uchun kanalga obuna bo'ling!</b>\n\n"
                "Obuna bo'lib ✅ <b>Tekshirish</b> tugmasini bosing:",
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode='HTML'
            )
        return False

    db.add_user(user.id, user.username, user.full_name)
    return True
