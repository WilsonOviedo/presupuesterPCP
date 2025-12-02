#!/bin/bash
set -e

echo "=========================================="
echo "Iniciando contenedor..."
echo "=========================================="

# Ejecutar inicialización de base de datos
echo "Ejecutando inicialización de base de datos..."
python3 /app/init_db.py

# Ejecutar el comando pasado como argumento (gunicorn)
echo "=========================================="
echo "Iniciando aplicación..."
echo "=========================================="
exec "$@"

