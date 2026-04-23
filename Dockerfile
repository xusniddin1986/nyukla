# ─── Python bazaviy image ─────────────────────────────────────
FROM python:3.11-slim

# ─── Tizim paketlari ──────────────────────────────────────────
# ffmpeg: audio/video konversiya uchun (yt-dlp talab qiladi)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ─── Ishchi papka ─────────────────────────────────────────────
WORKDIR /app

# ─── Python kutubxonalarini o'rnatish ─────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ─── Kod nusxalash ────────────────────────────────────────────
COPY . .

# ─── Vaqtinchalik papka ───────────────────────────────────────
RUN mkdir -p /tmp/nyuklabot_downloads

# ─── Port ─────────────────────────────────────────────────────
EXPOSE 8080

# ─── Bot ishga tushirish ──────────────────────────────────────
CMD ["python", "bot.py"]
