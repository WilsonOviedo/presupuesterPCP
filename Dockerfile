FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencias del sistema para psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
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

# Hacer ejecutable el script de inicialización
RUN chmod +x /app/init_db.py

# Exponer puerto
EXPOSE 5000

# Script de inicio que inicializa la DB y luego ejecuta gunicorn
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

# Ejecutar con gunicorn en 0.0.0.0:5000 (timeout configurable)
ENV GUNICORN_TIMEOUT=300
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["gunicorn", "-b", "0.0.0.0:5000", "--workers", "2", "--threads", "4", "--timeout", "300", "app:app"]


