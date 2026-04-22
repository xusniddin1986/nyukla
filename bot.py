import os
import logging
import asyncio
from aiohttp import web
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes
)
from config import BOT_TOKEN, OWNER_ID
from database import db
from handlers.start import start_handler, check_subscription
from handlers.video import video_handler
from handlers.music import music_search_handler, music_callback_handler
from handlers.admin import admin_panel_handler, admin_callback_handler, admin_message_handler

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

PORT = int(os.environ.get("PORT", 8443))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")


# ── Health check ──────────────────────────────────────────────────────────────

async def health_handler(request):
    stats = db.get_stats()
    return web.Response(text=f"NyuklaBot OK | Users: {stats['users']}", status=200)


async def telegram_webhook(request):
    tg_app = request.app['tg_app']
    data = await request.json()
    update = Update.de_json(data, tg_app.bot)
    await tg_app.process_update(update)
    return web.Response(text="OK")


# ── Commands ──────────────────────────────────────────────────────────────────

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_subscription(update, context):
        return
    await update.message.reply_text(
        "🤖 <b>NyuklaBot - Yordam</b>\n\n"
        "📥 <b>Video:</b> Instagram, YouTube, TikTok linkini yuboring\n"
        "🎵 <b>Musiqa:</b> Musiqa nomi yoki ijrochi ismini yozing\n\n"
        "/start — Boshlash\n/help — Yordam\n/about — Bot haqida\n/admin — Admin panel",
        parse_mode='HTML'
    )


async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_subscription(update, context):
        return
    await update.message.reply_text(
        "ℹ️ <b>NyuklaBot haqida</b>\n\n"
        "🚀 Kuchli media yuklab olish boti!\n\n"
        "✅ Instagram, YouTube, TikTok videolari\n"
        "🎵 Musiqa qidirish va yuklab olish\n"
        "⚡️ Tez va qulay\n\n"
        "📬 @NyuklaBot",
        parse_mode='HTML'
    )


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in db.get_admins() and user_id != OWNER_ID:
        await update.message.reply_text("❌ Siz admin emassiz!")
        return
    await admin_panel_handler(update, context)


async def addchannel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in db.get_admins() and update.effective_user.id != OWNER_ID:
        return
    if not context.args:
        await update.message.reply_text("Foydalanish: /addchannel @kanal"); return
    channel = context.args[0]
    try:
        chat = await context.bot.get_chat(channel)
        db.add_channel(channel)
        await update.message.reply_text(f"✅ {chat.title} qo'shildi!")
    except Exception as e:
        await update.message.reply_text(f"❌ Xatolik: {e}")


async def removechannel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in db.get_admins() and update.effective_user.id != OWNER_ID:
        return
    if not context.args:
        await update.message.reply_text("Foydalanish: /removechannel @kanal"); return
    if db.remove_channel(context.args[0]):
        await update.message.reply_text(f"✅ {context.args[0]} o'chirildi.")
    else:
        await update.message.reply_text("❌ Topilmadi.")


async def addadmin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Faqat egasi uchun!"); return
    if not context.args:
        await update.message.reply_text("Foydalanish: /addadmin USER_ID"); return
    try:
        db.add_admin(int(context.args[0]))
        await update.message.reply_text(f"✅ {context.args[0]} admin qilindi!")
    except ValueError:
        await update.message.reply_text("❌ Noto'g'ri ID")


async def removeadmin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if not context.args:
        await update.message.reply_text("Foydalanish: /removeadmin USER_ID"); return
    try:
        if db.remove_admin(int(context.args[0])):
            await update.message.reply_text(f"✅ O'chirildi.")
        else:
            await update.message.reply_text("❌ O'chirib bo'lmadi.")
    except ValueError:
        await update.message.reply_text("❌ Noto'g'ri ID")


# ── Subscription callback ─────────────────────────────────────────────────────

async def check_sub_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not await check_subscription(update, context):
        await query.answer("❌ Hali obuna bo'lmadingiz!", show_alert=True)
        return
    await query.message.delete()
    await update.effective_chat.send_message(
        "✅ Obuna tasdiqlandi! Botdan foydalanishingiz mumkin. 🎉\n"
        "Yordam uchun /help"
    )


# ── Text & media handlers ─────────────────────────────────────────────────────

VIDEO_DOMAINS = [
    'instagram.com', 'youtube.com', 'youtu.be', 'tiktok.com',
    'twitter.com', 'x.com', 'facebook.com', 'vimeo.com',
    'dailymotion.com', 't.me', 'vm.tiktok.com', 'pinterest.com'
]


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_subscription(update, context):
        return
    if not db.get_bot_status():
        await update.message.reply_text("🔧 Bot hozircha texnik ishlar uchun to'xtatilgan.")
        return

    user_id = update.effective_user.id
    admins = db.get_admins()
    text = update.message.text.strip()

    # Admin keyboard buttons
    if user_id in admins or user_id == OWNER_ID:
        admin_buttons = {
            "👥 Foydalanuvchilar": "users",
            "📊 Statistika": "stats",
            "🔔 Majburiy obuna": "subscription",
            "👨‍💼 Adminlar": "admins",
            "🤖 Bot holati": "status",
            "🏠 Bosh menu": "main",
        }
        if text in admin_buttons:
            await admin_panel_handler(update, context, section=admin_buttons[text])
            return
        if text == "📢 Xabar yuborish":
            context.user_data['admin_action'] = 'broadcast'
            await update.message.reply_text(
                "📢 Barcha foydalanuvchilarga yubormoqchi bo'lgan xabaringizni yuboring\n"
                "(matn, rasm, video yoki audio):"
            )
            return
        if context.user_data.get('admin_action'):
            await admin_message_handler(update, context)
            return

    # URL → video download
    if any(d in text.lower() for d in VIDEO_DOMAINS) or (
        text.startswith('http') and len(text) > 10
    ):
        await video_handler(update, context)
        return

    # Else → music search
    await music_search_handler(update, context)


async def media_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    admins = db.get_admins()
    if (user_id in admins or user_id == OWNER_ID) and context.user_data.get('admin_action') == 'broadcast':
        await admin_message_handler(update, context)


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Error: {context.error}")


# ── Build Telegram app ────────────────────────────────────────────────────────

def build_app():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("about", about_command))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("addchannel", addchannel_command))
    app.add_handler(CommandHandler("removechannel", removechannel_command))
    app.add_handler(CommandHandler("addadmin", addadmin_command))
    app.add_handler(CommandHandler("removeadmin", removeadmin_command))

    app.add_handler(CallbackQueryHandler(music_callback_handler, pattern=r"^(music_|page_)"))
    app.add_handler(CallbackQueryHandler(admin_callback_handler, pattern=r"^admin_"))
    app.add_handler(CallbackQueryHandler(check_sub_callback, pattern=r"^check_sub$"))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_handler(MessageHandler(filters.VIDEO | filters.AUDIO | filters.PHOTO, media_handler))

    app.add_error_handler(error_handler)
    return app


# ── Entry point ───────────────────────────────────────────────────────────────

async def run_webhook():
    tg_app = build_app()
    await tg_app.initialize()
    await tg_app.start()

    wh_url = f"{WEBHOOK_URL}/{BOT_TOKEN}"
    await tg_app.bot.set_webhook(wh_url)
    logger.info(f"Webhook set → {wh_url}")

    web_app = web.Application()
    web_app['tg_app'] = tg_app
    web_app.router.add_get('/', health_handler)
    web_app.router.add_get('/health', health_handler)
    web_app.router.add_post(f'/{BOT_TOKEN}', telegram_webhook)

    runner = web.AppRunner(web_app)
    await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', PORT).start()
    logger.info(f"Server listening on 0.0.0.0:{PORT}")

    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()
        await tg_app.stop()
        await tg_app.shutdown()


def main():
    if WEBHOOK_URL:
        logger.info("▶ WEBHOOK mode (Render.com)")
        asyncio.run(run_webhook())
    else:
        logger.info("▶ POLLING mode (local)")
        build_app().run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
