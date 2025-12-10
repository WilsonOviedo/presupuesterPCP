#!/bin/bash
set -e

echo "=========================================="
echo "Iniciando contenedor..."
echo "=========================================="

# Verificar si se debe saltar la inicialización de la base de datos
if [ "${SKIP_DB_INIT}" = "true" ]; then
    echo "⚠️  MODO SEGURO: Saltando inicialización automática de base de datos"
    echo "Para inicializar la DB manualmente, ejecuta:"
    echo "  docker-compose exec web python /app/init_db.py"
else
    # Ejecutar inicialización de base de datos
    echo "Ejecutando inicialización de base de datos..."
    python3 /app/init_db.py
fi

# Ejecutar el comando pasado como argumento (gunicorn)
echo "=========================================="
echo "Iniciando aplicación..."
echo "=========================================="

# Si el primer argumento es "gunicorn", usar la variable de entorno GUNICORN_TIMEOUT
if [ "$1" = "gunicorn" ]; then
    TIMEOUT="${GUNICORN_TIMEOUT:-300}"
    echo "Usando timeout de Gunicorn: ${TIMEOUT} segundos"
    exec gunicorn -b 0.0.0.0:5000 --workers 2 --threads 4 --timeout "${TIMEOUT}" app:app
else
    # Para otros comandos, ejecutar normalmente
    exec "$@"
fi

