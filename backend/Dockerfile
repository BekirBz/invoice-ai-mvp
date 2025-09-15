# Backend için Dockerfile
FROM python:3.11-slim

# Çalışma klasörü
WORKDIR /app

# Gereksiz cache'leri kapatalım
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Sisteme bağımlılıkları kur
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    poppler-utils \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

# Gereksinimler
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Kodları kopyala
COPY . .

# FastAPI backend başlat
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]
