import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "8679344041:AAFPAOq1vlF7EXUNvN-3KdiAbA8z0LORINc")
OWNER_ID = int(os.getenv("OWNER_ID", "8553997595"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://nyukla.onrender.com")
PORT = int(os.getenv("PORT", "8443"))
