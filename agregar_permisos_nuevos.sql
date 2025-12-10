-- Script para agregar nuevos permisos a bases de datos existentes
-- Ejecutar este script si ya tienes una base de datos en uso

-- Agregar permiso para Transferencias entre Cuentas
INSERT INTO permisos_rutas (ruta, nombre, descripcion) 
VALUES ('/financiero/transferencias', 'Transferencias entre Cuentas', 'Gestión de transferencias entre cuentas bancarias')
ON CONFLICT (ruta) DO NOTHING;

-- Agregar permiso para Conciliación Bancaria
INSERT INTO permisos_rutas (ruta, nombre, descripcion) 
VALUES ('/reportes/conciliacion-bancaria', 'Conciliación Bancaria', 'Acceso a la conciliación bancaria diaria')
ON CONFLICT (ruta) DO NOTHING;

-- Agregar permiso para Análisis Históricos (si no existe)
INSERT INTO permisos_rutas (ruta, nombre, descripcion) 
VALUES ('/reportes/analisis', 'Análisis Históricos', 'Acceso al análisis histórico y dashboard financiero')
ON CONFLICT (ruta) DO NOTHING;

-- Verificar que se insertaron correctamente
SELECT id, ruta, nombre, descripcion 
FROM permisos_rutas 
WHERE ruta IN ('/financiero/transferencias', '/reportes/conciliacion-bancaria', '/reportes/analisis')
ORDER BY ruta;

