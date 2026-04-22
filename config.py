import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "8679344041:AAFPAOq1vlF7EXUNvN-3KdiAbA8z0LORINc")
OWNER_ID = int(os.getenv("OWNER_ID", "8553997595"))

# Required subscription channel (e.g., "@mychannel" or "-100xxxxxxxxx")
REQUIRED_CHANNEL = os.getenv("REQUIRED_CHANNEL", "@xamidovsx")

# Spotify API (optional, for music search)
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "")

# Webhook settings for Render.com
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://nyukla.onrender.com")  # e.g. https://nyuklabot.onrender.com
PORT = int(os.getenv("PORT", 8443))
