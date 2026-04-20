FROM python:3.10-slim

# Node.js olib tashlandi, faqat ffmpeg qoldi
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

CMD ["python", "nyukla.py"]