# Guía de Docker para ApoloSys (Scrapper Facturas XML)

## Requisitos Previos

- Docker Engine 20.10 o superior
- Docker Compose 2.0 o superior
- Archivo `.env` configurado (ver sección de configuración)

## ⚠️ IMPORTANTE: Construcción Modular

Este proyecto ahora incluye archivos Docker Compose modulares para construir cada bloque de forma independiente y evitar sobrescribir datos importantes:

### Archivos Disponibles

1. **`docker-compose.yml`** (MODO SEGURO - por defecto)
   - Todos los servicios (web + postgres + pgadmin)
   - **NO inicializa la base de datos automáticamente** para proteger datos existentes
   - Uso: `docker-compose up -d`

2. **`docker-compose.web.yml`** (Solo aplicación web)
   - Construye únicamente el servicio web
   - Requiere base de datos externa o usar junto con `docker-compose.db.yml`
   - Uso: `docker-compose -f docker-compose.web.yml up -d`

3. **`docker-compose.db.yml`** (Solo base de datos)
   - Construye únicamente PostgreSQL
   - **NO inicializa la base de datos** automáticamente
   - Uso: `docker-compose -f docker-compose.db.yml up -d`

4. **`docker-compose.pgadmin.yml`** (Solo PgAdmin)
   - Construye únicamente la interfaz de administración
   - Uso: `docker-compose -f docker-compose.pgadmin.yml up -d`

5. **`docker-compose.full.yml`** (COMPLETO con inicialización)
   - Todos los servicios con inicialización automática de DB
   - ⚠️ **SOLO usar en entornos nuevos o cuando quieras reinicializar todo**
   - Uso: `docker-compose -f docker-compose.full.yml up -d`

### Ejemplos de Uso

#### Construir solo la aplicación web (sin tocar la base de datos)
```bash
# Si ya tienes la DB corriendo
docker-compose -f docker-compose.web.yml build
docker-compose -f docker-compose.web.yml up -d
```

#### Construir solo la base de datos
```bash
docker-compose -f docker-compose.db.yml up -d
```

#### Construir web + base de datos por separado
```bash
# Primero la base de datos
docker-compose -f docker-compose.db.yml up -d

# Luego la aplicación web (conectada a la DB)
docker-compose -f docker-compose.web.yml up -d
```

#### Construir todo desde cero (solo para entornos nuevos)
```bash
docker-compose -f docker-compose.full.yml up -d
```

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

**Modo seguro (recomendado - no inicializa DB automáticamente):**
```bash
docker-compose build
docker-compose up -d
```

**Construir solo el servicio web:**
```bash
docker-compose -f docker-compose.web.yml build
docker-compose -f docker-compose.web.yml up -d
```

**Construir solo la base de datos:**
```bash
docker-compose -f docker-compose.db.yml up -d
```

### Iniciar los servicios

**Modo seguro (por defecto):**
```bash
docker-compose up -d
```

Esto iniciará:
- **Web**: Aplicación Flask en `http://localhost:5000`
- **PostgreSQL**: Base de datos en `localhost:5432`
- **PgAdmin**: Interfaz de administración en `http://localhost:5050`

⚠️ **Nota**: En modo seguro, la base de datos NO se inicializa automáticamente. Para inicializarla manualmente:
```bash
docker-compose exec web python /app/init_db.py
```

### Inicialización de Base de Datos

**Modo seguro (por defecto):**
- La base de datos NO se inicializa automáticamente
- Protege datos existentes de ser sobrescritos
- Inicialización manual: `docker-compose exec web python /app/init_db.py`

**Modo completo (solo para entornos nuevos):**
```bash
docker-compose -f docker-compose.full.yml up -d
```
- Inicializa la base de datos automáticamente
- ⚠️ Solo usar cuando quieras empezar desde cero

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

⚠️ **ADVERTENCIA**: Esto eliminará TODOS los datos, incluyendo la base de datos.

```bash
# Detener y eliminar contenedores, redes y volúmenes
docker-compose down -v

# Eliminar imágenes
docker-compose rm -f

# Reconstruir desde cero (con inicialización automática)
docker-compose -f docker-compose.full.yml build --no-cache
docker-compose -f docker-compose.full.yml up -d
```

### Reconstruir solo un servicio específico

**Solo la aplicación web (sin afectar la base de datos):**
```bash
docker-compose -f docker-compose.web.yml build --no-cache
docker-compose -f docker-compose.web.yml up -d
```

**Solo la base de datos:**
```bash
docker-compose -f docker-compose.db.yml down
docker-compose -f docker-compose.db.yml up -d
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

## Resumen de Archivos Docker Compose

| Archivo | Servicios | Inicializa DB | Uso Recomendado |
|---------|-----------|---------------|-----------------|
| `docker-compose.yml` | Web + DB + PgAdmin | ❌ No (seguro) | Producción, desarrollo con datos existentes |
| `docker-compose.web.yml` | Solo Web | ❌ No | Actualizar solo la aplicación |
| `docker-compose.db.yml` | Solo DB | ❌ No | Actualizar solo la base de datos |
| `docker-compose.pgadmin.yml` | Solo PgAdmin | ❌ No | Solo interfaz de administración |
| `docker-compose.full.yml` | Web + DB + PgAdmin | ✅ Sí | Entornos nuevos, pruebas, desarrollo inicial |

## Mejores Prácticas

1. **En producción**: Usa `docker-compose.yml` (modo seguro) para proteger datos
2. **Para actualizar la app**: Usa `docker-compose.web.yml` para no tocar la DB
3. **Para desarrollo nuevo**: Usa `docker-compose.full.yml` solo la primera vez
4. **Siempre haz backup**: Antes de cualquier cambio importante
5. **Inicialización manual**: Usa `docker-compose exec web python /app/init_db.py` cuando sea necesario

