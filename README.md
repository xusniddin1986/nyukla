# 🤖 NyuklaBot — O'rnatish Qo'llanmasi

## 📁 Fayl tuzilmasi
```
nyuklabot/
├── bot.py              # Asosiy bot fayli
├── config.py           # Sozlamalar
├── database.py         # Ma'lumotlar bazasi (JSON)
├── requirements.txt    # Python kutubxonalari
├── render.yaml         # Render.com konfiguratsiyasi
├── .env.example        # Muhit o'zgaruvchilari namunasi
└── handlers/
    ├── start.py        # /start va obuna tekshiruvi
    ├── video.py        # Video yuklab olish
    ├── music.py        # Musiqa qidirish va yuklab olish
    └── admin.py        # Admin panel
```

---

## ⚙️ Sozlash

### 1. Bot token olish
1. Telegramda [@BotFather](https://t.me/BotFather) ga boring
2. `/newbot` yuboring
3. Bot nomini kiriting (masalan: `NyuklaBot`)
4. Username kiriting (masalan: `NyuklaBot_bot`)
5. Olingan **token** ni saqlang

### 2. Owner ID ni aniqlash
[@userinfobot](https://t.me/userinfobot) ga `/start` yuboring — sizning ID raqamingiz chiqadi.

### 3. Kanal tayyorlash
1. Telegram kanalini yarating yoki mavjudini tanlang
2. **Botni kanal administratori qiling** (Post Post Post + other ruxsatlar)

---

## 🚀 Render.com ga Deploy qilish

### 1-qadam: GitHub ga yuklash
```bash
git init
git add .
git commit -m "NyuklaBot initial commit"
git remote add origin https://github.com/SIZNING_USERNAME/nyuklabot.git
git push -u origin main
```

### 2-qadam: Render.com da loyiha yaratish
1. [render.com](https://render.com) ga kiring (bepul hisob)
2. **New → Web Service** tugmasini bosing
3. GitHub repozitoriyangizni ulang
4. Quyidagi sozlamalarni kiriting:
   - **Name:** `nyuklabot`
   - **Environment:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python bot.py`

### 3-qadam: Muhit o'zgaruvchilarini qo'shish
Render.com → loyiha → **Environment** bo'limiga:

| Key | Value |
|-----|-------|
| `BOT_TOKEN` | BotFather dan olingan token |
| `OWNER_ID` | Sizning Telegram ID |
| `REQUIRED_CHANNEL` | `@kanal_username` |
| `WEBHOOK_URL` | `https://nyuklabot.onrender.com` (deploy qilgandan keyin) |
| `PORT` | `8443` |

> ⚠️ `WEBHOOK_URL` ni deploy qilgandan keyin Render bergan URL bilan to'ldiring!

### 4-qadam: Deploy qilish
**Manual Deploy → Deploy latest commit** tugmasini bosing.

---

## ⏰ UptimeRobot sozlash (24/7 ishlashi uchun)

Render.com bepul plani 15 daqiqa faoliyatsizlikdan keyin "uxlatadi".

1. [uptimerobot.com](https://uptimerobot.com) ga ro'yxatdan o'ting (bepul)
2. **+ Add New Monitor** tugmasini bosing
3. Quyidagilarni to'ldiring:
   - **Monitor Type:** `HTTP(s)`
   - **Friendly Name:** `NyuklaBot`
   - **URL:** `https://nyuklabot.onrender.com/health`
   - **Monitoring Interval:** `5 minutes`
4. **Create Monitor** tugmasini bosing ✅

---

## 📋 Bot buyruqlari

| Buyruq | Tavsif |
|--------|--------|
| `/start` | Botni boshlash |
| `/help` | Yordam |
| `/about` | Bot haqida |
| `/admin` | Admin panel |
| `/addchannel @kanal` | Majburiy kanal qo'shish (admin) |
| `/removechannel @kanal` | Kanal o'chirish (admin) |
| `/addadmin ID` | Admin qo'shish (faqat egasi) |
| `/removeadmin ID` | Admin o'chirish (faqat egasi) |

---

## 🛠 Admin Panel imkoniyatlari

- 👥 **Foydalanuvchilar** — ID, username, ism ko'rish
- 📊 **Statistika** — Jami foydalanuvchilar, yuklashlar, qidiruvlar
- 📢 **Xabar yuborish** — Matn/Rasm/Video/Audio broadcast
- 🔔 **Majburiy obuna** — Kanal qo'shish/o'chirish
- 👨‍💼 **Adminlar** — Admin qo'shish/o'chirish
- 🤖 **Bot holati** — Botni yoqish/o'chirish

---

## 🎵 Musiqa qidirish
Musiqa nomini yoki ijrochi ismini yuboring → 1-10 natija chiqadi → Birini tanlang → MP3 yuklanadi.

## 📥 Video yuklab olish
Instagram / YouTube / TikTok / Twitter linkini yuboring → Video yuboriladi → **"Musiqani yuklab olish"** tugmasi paydo bo'ladi.

---

## ⚠️ Muhim eslatmalar

1. Bot kanal administratori bo'lishi shart!
2. Render bepul planida 512MB RAM mavjud — katta videolar muammo bo'lishi mumkin
3. Kanaldan chiqib ketgan foydalanuvchi botdan foydalana olmaydi
4. `data/` papkasi avtomatik yaratiladi (JSON bazasi)
