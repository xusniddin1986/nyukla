import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes
from telegram.error import TelegramError
from database import db
from config import OWNER_ID

logger = logging.getLogger(__name__)


def admin_kb():
    return ReplyKeyboardMarkup([
        [KeyboardButton("👥 Foydalanuvchilar"), KeyboardButton("📊 Statistika")],
        [KeyboardButton("📢 Xabar yuborish"), KeyboardButton("🔔 Majburiy obuna")],
        [KeyboardButton("👨‍💼 Adminlar"), KeyboardButton("🤖 Bot holati")],
    ], resize_keyboard=True)


async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE, section="main"):
    uid = update.effective_user.id
    if uid not in db.get_admins() and uid != OWNER_ID:
        await update.message.reply_text("❌ Siz admin emassiz!")
        return

    if section == "main":
        await update.message.reply_text("🛠 <b>Admin Panel</b>", parse_mode='HTML', reply_markup=admin_kb())

    elif section == "users":
        users = db.get_users()
        text = f"👥 <b>Foydalanuvchilar</b> (jami: {len(users)})\n\n"
        for u in users[-20:]:
            un = f"@{u['username']}" if u.get('username') else "—"
            text += f"👤 <b>{u.get('full_name','?')}</b> | {un} | <code>{u['id']}</code>\n"
        if len(users) > 20:
            text += f"\n... va yana {len(users)-20} ta"
        await update.message.reply_text(text, parse_mode='HTML')

    elif section == "stats":
        s = db.get_stats()
        await update.message.reply_text(
            f"📊 <b>Statistika</b>\n\n"
            f"👥 Foydalanuvchilar: <b>{s['users']}</b>\n"
            f"👨‍💼 Adminlar: <b>{s['admins']}</b>\n"
            f"📥 Yuklashlar: <b>{s['downloads']}</b>\n"
            f"🔍 Qidiruvlar: <b>{s['searches']}</b>\n"
            f"🔔 Kanallar: <b>{s['channels']}</b>\n"
            f"🤖 Bot: <b>{'✅ Faol' if s['bot_on'] else '❌ Off'}</b>",
            parse_mode='HTML'
        )

    elif section == "subscription":
        channels = db.get_channels()
        text = "🔔 <b>Majburiy kanallar:</b>\n\n"
        text += "\n".join(f"• {c}" for c in channels) if channels else "Hozircha yo'q"
        btns = [[InlineKeyboardButton("➕ Kanal qo'shish", callback_data="admin_add_channel")]]
        for c in channels:
            btns.append([InlineKeyboardButton(f"❌ O'chirish: {c}", callback_data=f"admin_rm_ch:{c}")])
        await update.message.reply_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(btns))

    elif section == "admins":
        admins = db.get_admins()
        text = "👨‍💼 <b>Adminlar:</b>\n\n"
        for a in admins:
            tag = " 👑" if a == OWNER_ID else ""
            text += f"• <code>{a}</code>{tag}\n"
        btns = [[InlineKeyboardButton("➕ Admin qo'shish", callback_data="admin_add_admin")]]
        for a in admins:
            if a != OWNER_ID:
                btns.append([InlineKeyboardButton(f"❌ {a}", callback_data=f"admin_rm_adm:{a}")])
        await update.message.reply_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(btns))

    elif section == "status":
        on = db.is_active()
        btn = "❌ O'chirish" if on else "✅ Yoqish"
        cb = "admin_bot_off" if on else "admin_bot_on"
        await update.message.reply_text(
            f"🤖 Bot holati: <b>{'✅ Faol' if on else '❌ Off'}</b>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(btn, callback_data=cb)]])
        )


async def admin_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    if uid not in db.get_admins() and uid != OWNER_ID:
        await q.answer("❌ Siz admin emassiz!", show_alert=True)
        return

    data = q.data

    if data == "admin_add_channel":
        context.user_data['admin_action'] = 'add_channel'
        await q.message.reply_text("📢 Kanal username yuboring (masalan: @mychannel)")

    elif data.startswith("admin_rm_ch:"):
        ch = data.split(":", 1)[1]
        db.remove_channel(ch)
        await q.message.edit_text(f"✅ {ch} o'chirildi.")

    elif data == "admin_add_admin":
        context.user_data['admin_action'] = 'add_admin'
        await q.message.reply_text("👤 Yangi admin Telegram ID sini yuboring:")

    elif data.startswith("admin_rm_adm:"):
        aid = int(data.split(":", 1)[1])
        db.remove_admin(aid)
        await q.message.edit_text(f"✅ {aid} o'chirildi.")

    elif data == "admin_bot_on":
        db.set_active(True)
        await q.message.edit_text("✅ Bot yoqildi!")

    elif data == "admin_bot_off":
        db.set_active(False)
        await q.message.edit_text("❌ Bot o'chirildi.")


async def admin_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in db.get_admins() and uid != OWNER_ID:
        return

    action = context.user_data.get('admin_action')

    if action == 'add_channel':
        ch = update.message.text.strip()
        try:
            chat = await context.bot.get_chat(ch)
            db.add_channel(ch)
            await update.message.reply_text(f"✅ {chat.title} qo'shildi!")
        except TelegramError as e:
            await update.message.reply_text(f"❌ {e}")
        context.user_data.pop('admin_action', None)

    elif action == 'add_admin':
        try:
            new_id = int(update.message.text.strip())
            db.add_admin(new_id)
            await update.message.reply_text(f"✅ {new_id} admin qilindi!")
        except ValueError:
            await update.message.reply_text("❌ Noto'g'ri ID")
        context.user_data.pop('admin_action', None)

    elif action == 'broadcast':
        users = db.get_users()
        ok = fail = 0
        status = await update.message.reply_text(f"📢 Yuborilmoqda... 0/{len(users)}")
        for i, u in enumerate(users):
            try:
                if update.message.text:
                    await context.bot.send_message(u['id'], update.message.text)
                elif update.message.photo:
                    await context.bot.send_photo(u['id'], update.message.photo[-1].file_id,
                                                  caption=update.message.caption or "")
                elif update.message.video:
                    await context.bot.send_video(u['id'], update.message.video.file_id,
                                                  caption=update.message.caption or "")
                elif update.message.audio:
                    await context.bot.send_audio(u['id'], update.message.audio.file_id,
                                                  caption=update.message.caption or "")
                ok += 1
            except:
                fail += 1
            if (i + 1) % 30 == 0:
                try:
                    await status.edit_text(f"📢 Yuborilmoqda... {i+1}/{len(users)}")
                except:
                    pass
        await status.edit_text(f"✅ Tugadi!\n✅ {ok} ta yuborildi\n❌ {fail} ta xato")
        context.user_data.pop('admin_action', None)
