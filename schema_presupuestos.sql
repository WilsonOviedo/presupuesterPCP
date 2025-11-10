-- Esquema SQL para sistema de presupuestos
-- PostgreSQL compatible

-- Tabla de clientes
CREATE TABLE IF NOT EXISTS clientes (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(255) NOT NULL,
    razon_social VARCHAR(255),
    cuit VARCHAR(20),
    direccion TEXT,
    telefono VARCHAR(50),
    email VARCHAR(255),
    notas TEXT,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabla de items (servicios o materiales)
CREATE TABLE IF NOT EXISTS items (
    id SERIAL PRIMARY KEY,
    codigo VARCHAR(50) UNIQUE,
    descripcion VARCHAR(500) NOT NULL,
    tipo VARCHAR(50) NOT NULL, -- 'Montaje', 'Programación', 'Materiales', 'Diseño', 'Otros'
    unidad VARCHAR(20) DEFAULT 'unidad', -- 'unidad', 'hora', 'metro', 'kg', etc.
    precio_base NUMERIC(15, 2) NOT NULL DEFAULT 0,
    margen_porcentaje NUMERIC(5, 2) DEFAULT 0, -- Margen de ganancia en porcentaje
    precio_venta NUMERIC(15, 2) GENERATED ALWAYS AS (
        CASE 
            WHEN margen_porcentaje = 0 THEN precio_base
            ELSE precio_base * (100 + margen_porcentaje) / 100
        END
    ) STORED,
    activo BOOLEAN DEFAULT TRUE,
    notas TEXT,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabla de materiales eléctricos
CREATE TABLE IF NOT EXISTS materiales (
    id SERIAL PRIMARY KEY,
    descripcion VARCHAR(500) NOT NULL,
    proveedor VARCHAR(255),
    precio NUMERIC(15, 2) NOT NULL DEFAULT 0,
    tiempo_instalacion NUMERIC(10, 2) DEFAULT 0,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabla de presupuestos
CREATE TABLE IF NOT EXISTS presupuestos (
    id SERIAL PRIMARY KEY,
    cliente_id INTEGER REFERENCES clientes(id) ON DELETE SET NULL,
    numero_presupuesto VARCHAR(50) UNIQUE NOT NULL,
    titulo VARCHAR(255),
    descripcion TEXT,
    estado VARCHAR(50) DEFAULT 'borrador', -- 'borrador', 'enviado', 'aprobado', 'rechazado', 'facturado'
    fecha_presupuesto DATE DEFAULT CURRENT_DATE,
    validez_dias INTEGER DEFAULT 30,
    iva_porcentaje NUMERIC(5, 2) DEFAULT 21.0,
    notas TEXT,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabla de subgrupos del presupuesto
CREATE TABLE IF NOT EXISTS presupuesto_subgrupos (
    id SERIAL PRIMARY KEY,
    presupuesto_id INTEGER NOT NULL REFERENCES presupuestos(id) ON DELETE CASCADE,
    numero INTEGER NOT NULL, -- Número del subgrupo (1, 2, 3, ...)
    nombre VARCHAR(255) NOT NULL, -- Nombre del subgrupo (ej: "MONTAJE DE BANDEJADO")
    orden INTEGER DEFAULT 0, -- Orden de visualización
    tiempo_ejecucion_horas NUMERIC(10, 2) DEFAULT 0, -- Tiempo total de ejecución en horas (se calcula desde los items)
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(presupuesto_id, numero)
);

-- Tabla de items del presupuesto (snapshot de precios)
CREATE TABLE IF NOT EXISTS presupuesto_items (
    id SERIAL PRIMARY KEY,
    presupuesto_id INTEGER NOT NULL REFERENCES presupuestos(id) ON DELETE CASCADE,
    subgrupo_id INTEGER REFERENCES presupuesto_subgrupos(id) ON DELETE SET NULL,
    item_id INTEGER REFERENCES items(id) ON DELETE SET NULL,
    material_id INTEGER REFERENCES materiales(id) ON DELETE SET NULL,
    codigo_item VARCHAR(50), -- Snapshot del código (por si se elimina el item)
    descripcion VARCHAR(500) NOT NULL, -- Snapshot de la descripción
    proveedor VARCHAR(255),
    tipo VARCHAR(50), -- Snapshot del tipo
    unidad VARCHAR(20),
    cantidad NUMERIC(10, 2) NOT NULL DEFAULT 1,
    precio_unitario NUMERIC(15, 2) NOT NULL, -- Precio al momento del presupuesto
    subtotal NUMERIC(15, 2) GENERATED ALWAYS AS (
        precio_unitario * cantidad
    ) STORED,
    numero_subitem VARCHAR(20), -- Número del subitem (1.1, 1.2, 2.1, etc.)
    tiempo_ejecucion_horas NUMERIC(10, 2) DEFAULT 0, -- Tiempo de ejecución en horas
    orden INTEGER DEFAULT 0, -- Orden de visualización dentro del subgrupo
    notas TEXT,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Índices para mejorar el rendimiento
CREATE INDEX IF NOT EXISTS idx_items_tipo ON items(tipo);
CREATE INDEX IF NOT EXISTS idx_items_activo ON items(activo);
CREATE UNIQUE INDEX IF NOT EXISTS idx_materiales_descripcion_unique ON materiales (LOWER(descripcion));
CREATE INDEX IF NOT EXISTS idx_presupuestos_cliente ON presupuestos(cliente_id);
CREATE INDEX IF NOT EXISTS idx_presupuestos_estado ON presupuestos(estado);
CREATE INDEX IF NOT EXISTS idx_presupuestos_fecha ON presupuestos(fecha_presupuesto);
CREATE INDEX IF NOT EXISTS idx_presupuesto_subgrupos_presupuesto ON presupuesto_subgrupos(presupuesto_id);
CREATE INDEX IF NOT EXISTS idx_presupuesto_items_presupuesto ON presupuesto_items(presupuesto_id);
CREATE INDEX IF NOT EXISTS idx_presupuesto_items_subgrupo ON presupuesto_items(subgrupo_id);
CREATE INDEX IF NOT EXISTS idx_presupuesto_items_item ON presupuesto_items(item_id);

-- Asegurar columnas nuevas cuando ya existen tablas previas
ALTER TABLE presupuesto_items
    ADD COLUMN IF NOT EXISTS material_id INTEGER REFERENCES materiales(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS proveedor VARCHAR(255);

ALTER TABLE materiales
    ADD COLUMN IF NOT EXISTS proveedor VARCHAR(255);

-- Función para actualizar updated_at automáticamente
CREATE OR REPLACE FUNCTION actualizar_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.actualizado_en = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Triggers para actualizar timestamp
CREATE TRIGGER trigger_clientes_actualizado
    BEFORE UPDATE ON clientes
    FOR EACH ROW
    EXECUTE FUNCTION actualizar_timestamp();

CREATE TRIGGER trigger_items_actualizado
    BEFORE UPDATE ON items
    FOR EACH ROW
    EXECUTE FUNCTION actualizar_timestamp();

CREATE TRIGGER trigger_materiales_actualizado
    BEFORE UPDATE ON materiales
    FOR EACH ROW
    EXECUTE FUNCTION actualizar_timestamp();

CREATE TRIGGER trigger_presupuestos_actualizado
    BEFORE UPDATE ON presupuestos
    FOR EACH ROW
    EXECUTE FUNCTION actualizar_timestamp();

-- Vista para presupuestos con totales
DROP VIEW IF EXISTS vista_presupuestos_totales;
CREATE VIEW vista_presupuestos_totales AS
SELECT 
    p.id,
    p.numero_presupuesto,
    p.titulo,
    COALESCE(c.nombre, 'Sin cliente') AS nombre_cliente,
    COALESCE(c.razon_social, c.nombre, 'Sin proveedor') AS nombre_proveedor,
    c.id AS cliente_id,
    COUNT(pi.id) AS cantidad_items,
    COALESCE(SUM(pi.precio_unitario * pi.cantidad), 0) AS subtotal,
    p.iva_porcentaje,
    COALESCE(SUM(pi.precio_unitario * pi.cantidad), 0) * p.iva_porcentaje / 100 AS iva_monto,
    COALESCE(SUM(pi.precio_unitario * pi.cantidad), 0) * (1 + p.iva_porcentaje / 100) AS total,
    p.estado,
    p.fecha_presupuesto,
    p.validez_dias,
    p.creado_en,
    p.actualizado_en
FROM presupuestos p
LEFT JOIN clientes c ON p.cliente_id = c.id
LEFT JOIN presupuesto_items pi ON p.id = pi.presupuesto_id
GROUP BY p.id, c.id, c.nombre, c.razon_social, p.iva_porcentaje;

-- Función para generar número de presupuesto automático
CREATE OR REPLACE FUNCTION generar_numero_presupuesto()
RETURNS TEXT AS $$
DECLARE
    año_actual INTEGER;
    ultimo_numero INTEGER;
    nuevo_numero TEXT;
BEGIN
    año_actual := EXTRACT(YEAR FROM CURRENT_DATE);
    
    -- Buscar el último número del año actual
    SELECT COALESCE(MAX(
        CAST(SUBSTRING(numero_presupuesto FROM '^PR-' || año_actual || '-(\d+)$') AS INTEGER)
    ), 0) INTO ultimo_numero
    FROM presupuestos
    WHERE numero_presupuesto LIKE 'PR-' || año_actual || '-%';
    
    -- Generar nuevo número
    nuevo_numero := 'PR-' || año_actual || '-' || LPAD((ultimo_numero + 1)::TEXT, 4, '0');
    
    RETURN nuevo_numero;
END;
$$ LANGUAGE plpgsql;

