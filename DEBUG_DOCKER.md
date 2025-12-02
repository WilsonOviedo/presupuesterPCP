# Debug: Variables de Entorno en Docker

## Problema: Variables de entorno no se cargan

Si ves el error:
```
[ERROR] Variables de entorno faltantes: DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT
```

## Solución

### 1. Verificar que el archivo `.env` existe en la raíz del proyecto

El archivo `.env` debe estar en la misma carpeta que `docker-compose.yml`:

```
proyecto/
├── .env              ← Debe estar aquí
├── docker-compose.yml
├── Dockerfile
└── ...
```

### 2. Verificar el contenido del `.env`

El archivo `.env` debe contener:

```env
DB_NAME=scrapper
DB_USER=scrapper
DB_PASSWORD=tu_contraseña
DB_HOST=postgres
DB_PORT=5432
```

**Nota**: `DB_HOST` debe ser `postgres` (nombre del servicio en docker-compose.yml), no `localhost`.

### 3. Activar modo debug

Para ver qué variables están disponibles en el contenedor:

```bash
# Agregar DEBUG_DB_INIT=true al .env
echo "DEBUG_DB_INIT=true" >> .env

# Reconstruir y ejecutar
docker-compose build
docker-compose up
```

### 4. Verificar variables dentro del contenedor

```bash
# Entrar al contenedor
docker-compose exec web bash

# Ver todas las variables de entorno
env | grep DB

# O ejecutar el script manualmente
python3 /app/init_db.py
```

### 5. Verificar que docker-compose lee el .env

```bash
# Ver qué variables lee docker-compose
docker-compose config
```

Esto mostrará la configuración completa con las variables expandidas.

### 6. Solución alternativa: Variables directas en docker-compose.yml

Si el `.env` no funciona, puedes definir las variables directamente en `docker-compose.yml`:

```yaml
services:
  web:
    environment:
      DB_NAME: scrapper
      DB_USER: scrapper
      DB_PASSWORD: tu_contraseña
      DB_HOST: postgres
      DB_PORT: 5432
```

### 7. Verificar que el .env no está en .dockerignore

El `.env` NO debe estar en `.dockerignore` (está bien que esté, porque Docker Compose lo lee del host, no del contenedor).

## Cómo funciona

1. Docker Compose lee el `.env` del **host** (no del contenedor)
2. Inyecta las variables como variables de entorno del sistema en el contenedor
3. El script `init_db.py` lee las variables usando `os.getenv()`
4. No necesita el archivo `.env` dentro del contenedor

## Verificar que funciona

```bash
# Reconstruir
docker-compose build

# Ver logs de inicialización
docker-compose up web

# Deberías ver:
# [OK] Variables de entorno verificadas
# [OK] PostgreSQL está listo
# [OK] Esquema SQL ejecutado correctamente
```

