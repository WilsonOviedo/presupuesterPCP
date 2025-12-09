# 🐳 Guía Rápida de Docker - ApoloSys

## ⚠️ Construcción Modular - Protege tus Datos

Este proyecto ahora permite construir cada bloque de forma independiente para evitar sobrescribir datos importantes.

## 📋 Archivos Disponibles

| Archivo | Qué Construye | Inicializa DB | Cuándo Usar |
|---------|---------------|---------------|-------------|
| `docker-compose.yml` | Web + DB + PgAdmin | ❌ No | **Por defecto** - Producción |
| `docker-compose.web.yml` | Solo Web | ❌ No | Actualizar solo la app |
| `docker-compose.db.yml` | Solo DB | ❌ No | Actualizar solo la DB |
| `docker-compose.pgadmin.yml` | Solo PgAdmin | ❌ No | Solo interfaz admin |
| `docker-compose.full.yml` | Web + DB + PgAdmin | ✅ Sí | **Solo entornos nuevos** |

## 🚀 Comandos Rápidos

### Modo Seguro (Recomendado)
```bash
# Construir y ejecutar todo (NO inicializa DB automáticamente)
docker-compose up -d

# Inicializar DB manualmente si es necesario
docker-compose exec web python /app/init_db.py
```

### Solo Aplicación Web
```bash
# Construir solo la app (sin tocar la DB)
docker-compose -f docker-compose.web.yml build
docker-compose -f docker-compose.web.yml up -d
```

### Solo Base de Datos
```bash
# Construir solo la DB
docker-compose -f docker-compose.db.yml up -d
```

### Entorno Nuevo (Inicializa Todo)
```bash
# ⚠️ SOLO para entornos nuevos - inicializa la DB automáticamente
docker-compose -f docker-compose.full.yml up -d
```

## 🔧 Comandos Útiles

```bash
# Ver logs
docker-compose logs -f web

# Detener servicios
docker-compose down

# Reconstruir sin cache
docker-compose build --no-cache

# Acceder al contenedor
docker-compose exec web bash
```

## 📚 Documentación Completa

Para más detalles, consulta `DOCKER.md`

