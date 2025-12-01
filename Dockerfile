# 1. Python 3.9'u temel al
FROM python:3.9-slim

# 2. Çalışma klasörünü ayarla
WORKDIR /app

# 3. İşletim sistemi seviyesinde gerekli kütüphaneleri yükle (Postgres için gerekli)
RUN apt-get update \
    && apt-get install -y libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

# 4. requirements.txt dosyasını içeri kopyala
COPY requirements.txt .

# 5. Python kütüphanelerini yükle (Otomatik pip install)
RUN pip install --no-cache-dir -r requirements.txt

# 6. Kodları kopyala
COPY . .

# 7. Portu aç
EXPOSE 5000

# 8. Başlat
CMD ["python", "app.py"]