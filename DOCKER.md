# Guía de Docker para Scrapper Facturas XML

## Requisitos Previos

- Docker Engine 20.10 o superior
- Docker Compose 2.0 o superior
- Archivo `.env` configurado (ver sección de configuración)

## Configuración

### 1. Crear archivo `.env`

Crea un archivo `.env` en la raíz del proyecto con las siguientes variables:

```env
# Base de Datos
DB_NAME=scrapper
DB_USER=scrapper
DB_PASSWORD=tu_contraseña_segura
DB_HOST=postgres
DB_PORT=5432

# OCR (Opcional - para uso local)
USE_REMOTE_OCR=false
OCR_SERVER_URL=
TESSERACT_CMD=

# O para usar OCR remoto:
# USE_REMOTE_OCR=true
# OCR_SERVER_URL=http://servidor-ocr:5000

# Gunicorn
GUNICORN_TIMEOUT=300

# IMAP (Opcional - para leer facturas desde correo)
# IMAP_SERVER=imap.gmail.com
# IMAP_USER=tu_email@gmail.com
# IMAP_PASS=tu_contraseña

# PgAdmin (Opcional)
# PGADMIN_DEFAULT_EMAIL=admin@example.com
# PGADMIN_DEFAULT_PASSWORD=admin
```

## Construcción y Ejecución

### Construir la imagen

```bash
docker-compose build
```

O construir solo el servicio web:

```bash
docker-compose build web
```

### Iniciar los servicios

```bash
docker-compose up -d
```

Esto iniciará:
- **Web**: Aplicación Flask en `http://localhost:5000`
- **PostgreSQL**: Base de datos en `localhost:5432`
- **PgAdmin**: Interfaz de administración en `http://localhost:5050`

### Ver logs

```bash
# Todos los servicios
docker-compose logs -f

# Solo el servicio web
docker-compose logs -f web

# Solo la base de datos
docker-compose logs -f postgres
```

### Detener los servicios

```bash
docker-compose down
```

### Detener y eliminar volúmenes (⚠️ Elimina los datos)

```bash
docker-compose down -v
```

## Comandos Útiles

### Reconstruir sin cache

```bash
docker-compose build --no-cache
```

### Ejecutar comandos dentro del contenedor

```bash
# Acceder al shell del contenedor web
docker-compose exec web bash

# Ejecutar un script Python
docker-compose exec web python ejecutar_esquema.py
```

### Verificar estado de los servicios

```bash
docker-compose ps
```

### Reiniciar un servicio específico

```bash
docker-compose restart web
```

## Estructura de Volúmenes

- `pgdata`: Datos persistentes de PostgreSQL
- `pgadmin_data`: Configuración de PgAdmin
- `./uploads`: Directorio de uploads (montado desde el host)

## Solución de Problemas

### El contenedor no inicia

1. Verifica los logs: `docker-compose logs web`
2. Verifica que el puerto 5000 no esté en uso
3. Verifica que el archivo `.env` esté configurado correctamente

### Error de conexión a la base de datos

1. Verifica que el servicio `postgres` esté corriendo: `docker-compose ps`
2. Verifica las credenciales en `.env`
3. Espera unos segundos después de iniciar para que PostgreSQL esté listo

### Error con Tesseract OCR

Si usas OCR local, Tesseract está incluido en la imagen Docker. Si necesitas OCR remoto:

1. Configura `USE_REMOTE_OCR=true` en `.env`
2. Configura `OCR_SERVER_URL` con la URL del servidor OCR remoto

### Limpiar todo y empezar de nuevo

```bash
# Detener y eliminar contenedores, redes y volúmenes
docker-compose down -v

# Eliminar imágenes
docker-compose rm -f

# Reconstruir desde cero
docker-compose build --no-cache
docker-compose up -d
```

## Desarrollo

### Modo desarrollo con recarga automática

Para desarrollo, puedes montar el código como volumen para ver cambios sin reconstruir:

```yaml
# En docker-compose.yml, agregar a volumes del servicio web:
volumes:
  - ./uploads:/app/uploads
  - .:/app  # Solo para desarrollo, comentar en producción
```

⚠️ **Nota**: Montar el código completo en desarrollo puede afectar el rendimiento. En producción, usa la imagen construida.

## Producción

### Optimizaciones recomendadas

1. Usa variables de entorno específicas para producción
2. Configura límites de recursos en `docker-compose.yml`:
   ```yaml
   deploy:
     resources:
       limits:
         cpus: '2'
         memory: 2G
   ```
3. Usa un proxy reverso (nginx) delante de la aplicación
4. Configura SSL/TLS
5. Implementa backups regulares de la base de datos

### Backup de base de datos

```bash
# Crear backup
docker-compose exec postgres pg_dump -U scrapper scrapper > backup.sql

# Restaurar backup
docker-compose exec -T postgres psql -U scrapper scrapper < backup.sql
```

