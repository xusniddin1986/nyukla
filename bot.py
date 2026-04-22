import os
import asyncio
import logging
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)
from config import BOT_TOKEN, OWNER_ID, WEBHOOK_URL, PORT
from database import db
from handlers.sub import check_sub
from handlers.video import handle_video
from handlers.music import handle_music_search, handle_music_cb
from handlers.admin import admin_panel, admin_cb, admin_input

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

VIDEO_DOMAINS = [
    'instagram.com', 'youtube.com', 'youtu.be', 'tiktok.com',
    'twitter.com', 'x.com', 'facebook.com', 'vimeo.com',
    'vm.tiktok.com', 'dailymotion.com', 't.me', 'pinterest.com'
]

# ── Health check ──────────────────────────────────────────────────────────────
async def health(request):
    s = db.get_stats()
    return web.Response(text=f"NyuklaBot OK | users={s['users']}", status=200)

async def tg_webhook(request):
    app = request.app['tg']
    data = await request.json()
    update = Update.de_json(data, app.bot)
    await app.process_update(update)
    return web.Response(text="OK")

# ── Commands ──────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.add_user(user.id, user.username, user.full_name)
    if not await check_sub(update, context):
        return
    await update.message.reply_text(
        f"👋 Salom, <b>{user.first_name}</b>!\n\n"
        "🤖 <b>NyuklaBot</b>ga xush kelibsiz!\n\n"
        "📥 Video linkini yuboring yoki\n"
        "🎵 Musiqa nomini yozing!",
        parse_mode='HTML'
    )

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_sub(update, context):
        return
    await update.message.reply_text(
        "🤖 <b>Yordam</b>\n\n"
        "📥 Instagram/YouTube/TikTok linkini yuboring\n"
        "🎵 Musiqa nomini yozing\n\n"
        "/start /help /about /admin",
        parse_mode='HTML'
    )

async def cmd_about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_sub(update, context):
        return
    await update.message.reply_text(
        "ℹ️ <b>NyuklaBot</b>\n\n"
        "✅ Video yuklab olish\n"
        "🎵 Musiqa qidirish\n"
        "⚡️ Tez va qulay\n\n"
        "@NyuklaBot",
        parse_mode='HTML'
    )

async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in db.get_admins() and uid != OWNER_ID:
        await update.message.reply_text("❌ Siz admin emassiz!")
        return
    await admin_panel(update, context)

async def cmd_addchannel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in db.get_admins() and uid != OWNER_ID:
        return
    if not context.args:
        await update.message.reply_text("Foydalanish: /addchannel @kanal")
        return
    ch = context.args[0]
    try:
        chat = await context.bot.get_chat(ch)
        db.add_channel(ch)
        await update.message.reply_text(f"✅ {chat.title} qo'shildi!")
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")

async def cmd_removechannel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in db.get_admins() and uid != OWNER_ID:
        return
    if not context.args:
        await update.message.reply_text("Foydalanish: /removechannel @kanal")
        return
    if db.remove_channel(context.args[0]):
        await update.message.reply_text(f"✅ O'chirildi.")
    else:
        await update.message.reply_text("❌ Topilmadi.")

async def cmd_addadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if not context.args:
        await update.message.reply_text("Foydalanish: /addadmin USER_ID")
        return
    try:
        db.add_admin(int(context.args[0]))
        await update.message.reply_text("✅ Admin qilindi!")
    except:
        await update.message.reply_text("❌ Xatolik")

async def cmd_removeadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if not context.args:
        await update.message.reply_text("Foydalanish: /removeadmin USER_ID")
        return
    try:
        if db.remove_admin(int(context.args[0])):
            await update.message.reply_text("✅ O'chirildi.")
        else:
            await update.message.reply_text("❌ O'chirib bo'lmadi.")
    except:
        await update.message.reply_text("❌ Xatolik")

# ── Callbacks ─────────────────────────────────────────────────────────────────
async def cb_check_sub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not await check_sub(update, context):
        await q.answer("❌ Hali obuna bo'lmadingiz!", show_alert=True)
        return
    try:
        await q.message.delete()
    except:
        pass
    await update.effective_chat.send_message("✅ Obuna tasdiqlandi! /help")

# ── Text handler ──────────────────────────────────────────────────────────────
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_sub(update, context):
        return
    if not db.is_active():
        await update.message.reply_text("🔧 Bot hozircha texnik ishlar uchun to'xtatilgan.")
        return

    uid = update.effective_user.id
    admins = db.get_admins()
    text = update.message.text.strip()

    # Admin keyboard
    if uid in admins or uid == OWNER_ID:
        sections = {
            "👥 Foydalanuvchilar": "users",
            "📊 Statistika": "stats",
            "🔔 Majburiy obuna": "subscription",
            "👨‍💼 Adminlar": "admins",
            "🤖 Bot holati": "status",
            "🏠 Bosh menu": "main",
        }
        if text in sections:
            await admin_panel(update, context, section=sections[text])
            return
        if text == "📢 Xabar yuborish":
            context.user_data['admin_action'] = 'broadcast'
            await update.message.reply_text("📢 Xabar yuboring (matn/rasm/video/audio):")
            return
        if context.user_data.get('admin_action'):
            await admin_input(update, context)
            return

    # URL → video
    if any(d in text.lower() for d in VIDEO_DOMAINS) or (text.startswith('http') and len(text) > 10):
        await handle_video(update, context)
        return

    # Else → music
    await handle_music_search(update, context)

async def media_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if (uid in db.get_admins() or uid == OWNER_ID) and context.user_data.get('admin_action') == 'broadcast':
        await admin_input(update, context)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Error: {context.error}")

# ── Build app ─────────────────────────────────────────────────────────────────
def build():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("about", cmd_about))
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(CommandHandler("addchannel", cmd_addchannel))
    app.add_handler(CommandHandler("removechannel", cmd_removechannel))
    app.add_handler(CommandHandler("addadmin", cmd_addadmin))
    app.add_handler(CommandHandler("removeadmin", cmd_removeadmin))

    app.add_handler(CallbackQueryHandler(handle_music_cb, pattern=r"^(music_|page_)"))
    app.add_handler(CallbackQueryHandler(admin_cb, pattern=r"^admin_"))
    app.add_handler(CallbackQueryHandler(cb_check_sub, pattern=r"^check_sub$"))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_handler(MessageHandler(filters.VIDEO | filters.AUDIO | filters.PHOTO, media_handler))

    app.add_error_handler(error_handler)
    return app

# ── Webhook runner ────────────────────────────────────────────────────────────
async def run_webhook():
    tg = build()
    await tg.initialize()
    await tg.start()
    await tg.bot.set_webhook(f"{WEBHOOK_URL}/{BOT_TOKEN}")
    logger.info(f"Webhook: {WEBHOOK_URL}/{BOT_TOKEN}")

    wa = web.Application()
    wa['tg'] = tg
    wa.router.add_get('/', health)
    wa.router.add_get('/health', health)
    wa.router.add_post(f'/{BOT_TOKEN}', tg_webhook)

    runner = web.AppRunner(wa)
    await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', PORT).start()
    logger.info(f"Listening on port {PORT}")

    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()
        await tg.stop()
        await tg.shutdown()

# ── Entry ─────────────────────────────────────────────────────────────────────
def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN topilmadi! .env faylini tekshiring.")
    if WEBHOOK_URL:
        logger.info("WEBHOOK mode")
        asyncio.run(run_webhook())
    else:
        logger.info("POLLING mode")
        build().run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
