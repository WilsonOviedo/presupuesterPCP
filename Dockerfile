FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencias del sistema para psycopg2, OpenCV y Tesseract OCR
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    tesseract-ocr \
    tesseract-ocr-spa \
    tesseract-ocr-por \
    tesseract-ocr-eng \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    curl \
 && rm -rf /var/lib/apt/lists/*

# Copiar requirements primero para aprovechar cache de Docker
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /app/requirements.txt

# Copiar el resto de la aplicación
COPY . /app

# Crear directorio de uploads si no existe
RUN mkdir -p /app/uploads

# Exponer puerto
EXPOSE 5000

# Ejecutar con gunicorn en 0.0.0.0:5000 (timeout configurable)
ENV GUNICORN_TIMEOUT=300
# Usamos sh -c para que se expanda la variable de entorno
CMD ["sh", "-c", "gunicorn -b 0.0.0.0:5000 --workers 2 --threads 4 --timeout ${GUNICORN_TIMEOUT:-300} app:app"]


