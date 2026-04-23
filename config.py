import os

# ─── Bot token (BotFather dan oling) ──────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN", "8679344041:AAFPAOq1vlF7EXUNvN-3KdiAbA8z0LORINc")

# ─── Admin ID lar (Telegram user ID) ──────────────────────────
_admin_ids = os.getenv("ADMIN_IDS", "8553997595")
ADMIN_IDS = [int(x) for x in _admin_ids.split(",") if x.strip().isdigit()]

# ─── Kanal sozlamalari ─────────────────────────────────────────
CHANNEL_ID = os.getenv("CHANNEL_ID", "@xamidovsx")   # @username yoki -100xxxxxxx
CHANNEL_LINK = os.getenv("CHANNEL_LINK", "https://t.me/xamidovsx")

# ─── Webhook (Render.com uchun) ───────────────────────────────
# Render.com da: https://yourapp.onrender.com
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://nyukla.onrender.com")   # bo'sh bo'lsa polling ishlatiladi
WEBHOOK_PATH = "/webhook"
PORT = int(os.getenv("PORT", 8080))

# ─── Fayl sozlamalari ─────────────────────────────────────────
DOWNLOADS_DIR = os.getenv("DOWNLOADS_DIR", "/tmp/nyuklabot_downloads")
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", 50))

# ─── Musiqa API (Deezer - bepul) ─────────────────────────────
DEEZER_API = "https://api.deezer.com"

os.makedirs(DOWNLOADS_DIR, exist_ok=True)
