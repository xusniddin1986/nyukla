# 🤖 NyuklaBot — To'liq O'rnatish Qo'llanmasi

## 📁 Fayl Tuzilishi
```
nyuklabot/
├── bot.py              # Asosiy bot fayli
├── config.py           # Sozlamalar
├── database.py         # Ma'lumotlar bazasi (SQLite)
├── downloader.py       # Video yuklovchi (yt-dlp)
├── music_search.py     # Musiqa qidiruvchi (Deezer API)
├── requirements.txt    # Python kutubxonalari
├── Dockerfile          # Docker konfiguratsiyasi
├── render.yaml         # Render.com konfiguratsiyasi
├── cookies.txt         # Cookie fayli (ixtiyoriy)
└── README.md           # Ushbu fayl
```

---

## 🚀 1-QADAM: Telegram Bot Yaratish

1. [@BotFather](https://t.me/BotFather) ga boring
2. `/newbot` yuboring
3. Bot nomini kiriting: `NyuklaBot`
4. Bot username: `NyuklaBot` (yoki boshqa)
5. **BOT TOKEN** ni nusxalab oling
6. `/setcommands` → botni tanlang → quyidagi buyruqlarni qo'shing:
```
start - Botni ishga tushirish
help - Yordam
about - Bot haqida
admin - Admin panel
```

---

## 📢 2-QADAM: Kanal Sozlash

1. Telegram kanalingizga boring
2. **Bot**ni kanal adminiga qo'shing (to'liq huquqlar)
3. Kanal ID sini bilib oling:
   - [@userinfobot](https://t.me/userinfobot) ga kanalingizni forward qiling
   - Yoki `@username` formatida ishlating

---

## 💻 3-QADAM: GitHub ga Yuklash

```bash
git init
git add .
git commit -m "NyuklaBot initial commit"
git branch -M main
git remote add origin https://github.com/SIZNING_USERNAME/nyuklabot.git
git push -u origin main
```

---

## 🌐 4-QADAM: Render.com ga Deploy

1. [render.com](https://render.com) ga kiring → **New Web Service**
2. GitHub repo'ni ulang
3. **Environment: Docker** tanlang
4. **Environment Variables** qo'shing:

| Kalit | Qiymat | Misol |
|-------|--------|-------|
| `BOT_TOKEN` | BotFather dan | `7123456789:AAF...` |
| `ADMIN_IDS` | Sizning Telegram ID | `123456789` |
| `CHANNEL_ID` | Kanalingiz | `@mychannel` |
| `CHANNEL_LINK` | Kanal havolasi | `https://t.me/mychannel` |
| `WEBHOOK_URL` | Render URL | `https://nyuklabot.onrender.com` |
| `PORT` | Port | `8080` |

5. **Deploy** tugmasini bosing
6. 5-10 daqiqa kuting — bot ishlaydi!

> **WEBHOOK_URL** ni Render.com sizga bergan URL: `https://YOUR_APP_NAME.onrender.com`

---

## ⏰ 5-QADAM: UptimeRobot (24/7 ishlashi uchun)

Render.com bepul rejimda 15 daqiqada bir uxlab qoladi.
UptimeRobot uni 5 daqiqada bir "uyg'otadi".

1. [uptimerobot.com](https://uptimerobot.com) ga kiring (bepul)
2. **Add New Monitor** bosing
3. Monitor type: **HTTP(s)**
4. URL: `https://YOUR_APP_NAME.onrender.com/health`
5. Monitoring interval: **5 minutes**
6. **Create Monitor** bosing

✅ Endi bot 24/7 ishlaydi!

---

## 👑 Admin Panel Buyruqlari

Bot ishlayotganda `/admin` yuboring:

| Tugma | Vazifa |
|-------|--------|
| 📢 Xabar yuborish | Matn/Rasm/Video/Audio broadcast |
| 👥 Foydalanuvchilar | Oxirgi 20 foydalanuvchi ro'yxati |
| 📊 Statistika | Umumiy statistika |
| 🔔 Majburiy obuna | Kanal qo'shish/o'chirish |
| 👑 Adminlar | Admin qo'shish/o'chirish |
| 🤖 Bot holati | Bot ishlayotganligi |

---

## 🎵 Musiqa Qidirish

Bot **Deezer API** ishlatadi (bepul, API kalit kerak emas).
Musiqa yuklab olish uchun **YouTube Music** ishlatiladi.

---

## 📹 Video Yuklab Olish

Qo'llab-quvvatlanadigan platformalar:
- ✅ YouTube
- ✅ Instagram (Reels, Stories, Posts)
- ✅ Facebook
- ✅ TikTok
- ✅ Pinterest
- ✅ Twitter/X
- ✅ Vimeo
- ✅ Va boshqa 1000+ sayt

**Cheklov:** 50MB gacha (Telegram limiti)

---

## 🍪 Cookies (Ixtiyoriy)

Agar ba'zi videolar yuklanmasa:
1. Chrome → "Get cookies.txt LOCALLY" extension
2. YouTube/Instagram ga kiring
3. Cookies eksport qiling
4. `cookies.txt` faylini almashtiring
5. GitHub ga push qiling → Render qayta deploy qiladi

---

## 🔧 Mahalliy Ishga Tushirish (Test uchun)

```bash
pip install -r requirements.txt
# .env fayl yarating:
BOT_TOKEN=your_token
ADMIN_IDS=your_id
CHANNEL_ID=@yourchannel
CHANNEL_LINK=https://t.me/yourchannel
# WEBHOOK_URL ni bo'sh qoldiring (polling ishlatiladi)

python bot.py
```

---

## ❓ Muammolar

**Bot javob bermayapti:**
- WEBHOOK_URL to'g'riligini tekshiring
- Render loglarini ko'ring

**Video yuklanmaydi:**
- Video ommaviy (public) ekanligini tekshiring
- 50MB dan kichik ekanligini tekshiring
- cookies.txt qo'shib ko'ring

**Musiqa topilmaydi:**
- Inglizcha yoziing
- Ijrochi nomi + qo'shiq nomi birga yozing
