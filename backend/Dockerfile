# Backend için Dockerfile
FROM python:3.11-slim

# Ortam değişkenleri
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    PORT=10000

# Çalışma klasörü
WORKDIR /app

# Sistem bağımlılıkları (tesseract + poppler) ve apt temizliği tek katmanda
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      tesseract-ocr \
      poppler-utils \
      libgl1 \
 && rm -rf /var/lib/apt/lists/*

# Python gereksinimleri
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Uygulama kodu
COPY . .

# (Opsiyonel) bilgilendirici: portu dışa aç
EXPOSE 10000

# FastAPI backend
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]
