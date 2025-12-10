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

# Copiar el resto de la aplicación (docker-entrypoint.sh se copia aquí también)
COPY . /app

# Crear directorio de uploads si no existe
RUN mkdir -p /app/uploads

# Hacer ejecutables los scripts
RUN chmod +x /app/init_db.py /app/docker-entrypoint.sh

# Exponer puerto
EXPOSE 5000

# Ejecutar con gunicorn en 0.0.0.0:5000 (timeout configurable desde variable de entorno)
ENV GUNICORN_TIMEOUT=300
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["gunicorn"]


