import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes
from telegram.error import TelegramError
from database import db
from config import OWNER_ID

logger = logging.getLogger(__name__)


def get_admin_keyboard():
    keyboard = [
        [KeyboardButton("👥 Foydalanuvchilar"), KeyboardButton("📊 Statistika")],
        [KeyboardButton("📢 Xabar yuborish"), KeyboardButton("🔔 Majburiy obuna")],
        [KeyboardButton("👨‍💼 Adminlar"), KeyboardButton("🤖 Bot holati")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


async def admin_panel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, section: str = "main"):
    user_id = update.effective_user.id
    admins = db.get_admins()

    if user_id not in admins and user_id != OWNER_ID:
        await update.message.reply_text("❌ Siz admin emassiz!")
        return

    if section == "main":
        text = "🛠 <b>Admin Panel</b>\n\nQuyidagi menyudan tanlang:"
        await update.message.reply_text(
            text,
            parse_mode='HTML',
            reply_markup=get_admin_keyboard()
        )

    elif section == "users":
        users = db.get_all_users()
        if not users:
            await update.message.reply_text("👥 Hozircha foydalanuvchilar yo'q.")
            return

        # Show last 20 users
        text = f"👥 <b>Foydalanuvchilar</b> (jami: {len(users)})\n\n"
        for u in users[-20:]:
            username = f"@{u['username']}" if u.get('username') else "Yo'q"
            name = u.get('full_name', 'Noma\'lum')
            uid = u.get('id', '?')
            text += f"👤 <b>{name}</b>\n"
            text += f"   📎 Username: {username}\n"
            text += f"   🆔 ID: <code>{uid}</code>\n\n"

        if len(users) > 20:
            text += f"... va yana {len(users) - 20} ta foydalanuvchi"

        await update.message.reply_text(text, parse_mode='HTML')

    elif section == "stats":
        stats = db.get_stats()
        channels = db.get_required_channels()
        text = (
            "📊 <b>Bot Statistikasi</b>\n\n"
            f"👥 Jami foydalanuvchilar: <b>{stats['users']}</b>\n"
            f"👨‍💼 Adminlar soni: <b>{stats['admins']}</b>\n"
            f"📥 Jami yuklashlar: <b>{stats['total_downloads']}</b>\n"
            f"🔍 Musiqa qidiruvlar: <b>{stats['total_music_searches']}</b>\n"
            f"🔔 Majburiy kanallar: <b>{len(channels)}</b>\n"
            f"🤖 Bot holati: <b>{'✅ Faol' if stats['bot_active'] else '❌ Nofarol'}</b>"
        )
        await update.message.reply_text(text, parse_mode='HTML')

    elif section == "subscription":
        channels = db.get_required_channels()
        text = "🔔 <b>Majburiy Obuna Kanallari</b>\n\n"
        if channels:
            for i, ch in enumerate(channels, 1):
                text += f"{i}. {ch}\n"
        else:
            text += "Hozircha majburiy kanal yo'q.\n"

        text += "\n➕ Kanal qo'shish uchun: /addchannel @kanal_username\n"
        text += "➖ Kanal o'chirish uchun: /removechannel @kanal_username"

        buttons = [[InlineKeyboardButton("➕ Kanal qo'shish", callback_data="admin_add_channel")]]
        if channels:
            for ch in channels:
                buttons.append([InlineKeyboardButton(f"❌ {ch}", callback_data=f"admin_rm_channel:{ch}")])

        await update.message.reply_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(buttons))

    elif section == "admins":
        admins_list = db.get_admins()
        text = "👨‍💼 <b>Adminlar ro'yxati</b>\n\n"
        for i, aid in enumerate(admins_list, 1):
            owner_tag = " 👑 (Egasi)" if aid == OWNER_ID else ""
            text += f"{i}. <code>{aid}</code>{owner_tag}\n"

        text += "\n➕ Admin qo'shish: /addadmin USER_ID\n"
        text += "➖ Admin o'chirish: /removeadmin USER_ID"

        buttons = [[InlineKeyboardButton("➕ Admin qo'shish", callback_data="admin_add_admin")]]
        for aid in admins_list:
            if aid != OWNER_ID:
                buttons.append([InlineKeyboardButton(f"❌ {aid}", callback_data=f"admin_rm_admin:{aid}")])

        await update.message.reply_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(buttons))

    elif section == "status":
        status = db.get_bot_status()
        text = f"🤖 <b>Bot holati:</b> {'✅ Faol' if status else '❌ Nofarol'}\n\n"
        text += "Bot holatini o'zgartirish uchun tugmani bosing:"

        btn_text = "❌ Botni o'chirish" if status else "✅ Botni yoqish"
        btn_data = "admin_bot_off" if status else "admin_bot_on"
        buttons = [[InlineKeyboardButton(btn_text, callback_data=btn_data)]]

        await update.message.reply_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(buttons))


async def admin_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    admins = db.get_admins()

    if user_id not in admins and user_id != OWNER_ID:
        await query.answer("❌ Siz admin emassiz!", show_alert=True)
        return

    data = query.data

    if data == "admin_add_channel":
        context.user_data['admin_action'] = 'add_channel'
        await query.message.reply_text(
            "📢 Kanal username yuboring (masalan: @mychannel)\n"
            "Bot kanal administratori bo'lishi kerak!"
        )

    elif data.startswith("admin_rm_channel:"):
        channel = data.split(":", 1)[1]
        db.remove_channel(channel)
        await query.message.reply_text(f"✅ {channel} kanali o'chirildi.")
        await query.message.delete()

    elif data == "admin_add_admin":
        context.user_data['admin_action'] = 'add_admin'
        await query.message.reply_text("👤 Admin qilmoqchi bo'lgan foydalanuvchining ID sini yuboring:")

    elif data.startswith("admin_rm_admin:"):
        admin_id = int(data.split(":", 1)[1])
        if admin_id == OWNER_ID:
            await query.answer("❌ Egani admin dan o'chirib bo'lmaydi!", show_alert=True)
            return
        db.remove_admin(admin_id)
        await query.message.reply_text(f"✅ {admin_id} admin ro'yxatidan o'chirildi.")

    elif data == "admin_bot_on":
        db.set_bot_status(True)
        await query.message.edit_text("✅ Bot yoqildi!")

    elif data == "admin_bot_off":
        db.set_bot_status(False)
        await query.message.edit_text("❌ Bot o'chirildi!")


async def admin_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin actions that require text input."""
    user_id = update.effective_user.id
    admins = db.get_admins()

    if user_id not in admins and user_id != OWNER_ID:
        return

    action = context.user_data.get('admin_action')

    if action == 'add_channel':
        channel = update.message.text.strip()
        if not channel.startswith('@') and not channel.startswith('-'):
            await update.message.reply_text("❌ Noto'g'ri format. @kanal_username yuboring.")
            return
        # Test if bot can access the channel
        try:
            chat = await context.bot.get_chat(channel)
            db.add_channel(channel)
            await update.message.reply_text(f"✅ {chat.title} ({channel}) kanali qo'shildi!")
        except TelegramError as e:
            await update.message.reply_text(
                f"❌ Kanal topilmadi: {e}\n"
                "Bot kanal administratori bo'lishi kerak!"
            )
        context.user_data.pop('admin_action', None)

    elif action == 'add_admin':
        try:
            new_admin_id = int(update.message.text.strip())
            db.add_admin(new_admin_id)
            await update.message.reply_text(f"✅ {new_admin_id} admin qilindi!")
        except ValueError:
            await update.message.reply_text("❌ Noto'g'ri ID. Raqam kiriting.")
        context.user_data.pop('admin_action', None)

    elif action == 'broadcast':
        # Broadcast to all users
        users = db.get_all_users()
        success = 0
        failed = 0

        status_msg = await update.message.reply_text(f"📢 Xabar yuborilmoqda... (0/{len(users)})")

        for i, user in enumerate(users):
            try:
                uid = user['id']
                if update.message.text:
                    await context.bot.send_message(uid, update.message.text)
                elif update.message.photo:
                    photo = update.message.photo[-1].file_id
                    await context.bot.send_photo(uid, photo, caption=update.message.caption or "")
                elif update.message.video:
                    await context.bot.send_video(uid, update.message.video.file_id,
                                                  caption=update.message.caption or "")
                elif update.message.audio:
                    await context.bot.send_audio(uid, update.message.audio.file_id,
                                                  caption=update.message.caption or "")
                success += 1
            except TelegramError:
                failed += 1

            if (i + 1) % 20 == 0:
                try:
                    await status_msg.edit_text(f"📢 Xabar yuborilmoqda... ({i+1}/{len(users)})")
                except:
                    pass

        await status_msg.edit_text(
            f"✅ Xabar yuborildi!\n\n"
            f"✅ Muvaffaqiyatli: {success}\n"
            f"❌ Xato: {failed}"
        )
        context.user_data.pop('admin_action', None)
