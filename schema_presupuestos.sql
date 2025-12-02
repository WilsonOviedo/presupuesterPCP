-- Esquema SQL para sistema de presupuestos
-- PostgreSQL compatible

-- Tabla de clientes
CREATE TABLE IF NOT EXISTS clientes (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(255) NOT NULL,
    razon_social VARCHAR(255),
    ruc VARCHAR(20),
    direccion TEXT,
    telefono VARCHAR(50),
    email VARCHAR(255),
    notas TEXT,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Renombrar columna CUIT a RUC si aún existe
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'clientes' AND column_name = 'cuit'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'clientes' AND column_name = 'ruc'
    ) THEN
        EXECUTE 'ALTER TABLE clientes RENAME COLUMN cuit TO ruc';
    END IF;
END;
$$;


-- Tabla de prefijos de códigos para tipos de servicios
CREATE TABLE IF NOT EXISTS prefijos_codigos (
    id SERIAL PRIMARY KEY,
    tipo_servicio VARCHAR(50) NOT NULL UNIQUE,
    prefijo VARCHAR(20) NOT NULL,
    activo BOOLEAN DEFAULT TRUE,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabla de items_mano_de_obra (servicios o materiales)
CREATE TABLE IF NOT EXISTS items_mano_de_obra (
    id SERIAL PRIMARY KEY,
    codigo VARCHAR(50) UNIQUE,
    descripcion VARCHAR(500) NOT NULL,
    tipo VARCHAR(50) NOT NULL, -- 'Montaje', 'Programación', 'Materiales', 'Diseño', 'Otros'
    unidad VARCHAR(20) DEFAULT 'unidad', -- 'unidad', 'hora', 'metro', 'kg', etc.
    precio_base NUMERIC(15, 2) NOT NULL DEFAULT 0,
    margen_porcentaje NUMERIC(5, 2) DEFAULT 0, -- Margen de ganancia en porcentaje
    precio_venta NUMERIC(15, 2) GENERATED ALWAYS AS (
        CASE 
            WHEN margen_porcentaje IS NULL OR margen_porcentaje = 0 THEN precio_base
            WHEN margen_porcentaje >= 100 THEN NULL
            ELSE precio_base / (1 - (margen_porcentaje / 100.0))
        END
    ) STORED,
    activo BOOLEAN DEFAULT TRUE,
    notas TEXT,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'items_mano_de_obra' AND column_name = 'precio_venta'
    ) THEN
        BEGIN
            EXECUTE 'ALTER TABLE items_mano_de_obra DROP COLUMN precio_venta';
        EXCEPTION
            WHEN undefined_column THEN NULL;
        END;
    END IF;
    EXECUTE $ddl$
        ALTER TABLE items_mano_de_obra
        ADD COLUMN IF NOT EXISTS precio_venta NUMERIC(15, 2) GENERATED ALWAYS AS (
            CASE 
                WHEN margen_porcentaje IS NULL OR margen_porcentaje = 0 THEN precio_base
                WHEN margen_porcentaje >= 100 THEN NULL
                ELSE precio_base / (1 - (margen_porcentaje / 100.0))
            END
        ) STORED
    $ddl$;
END;
$$;

-- Tabla de marcas de materiales
CREATE TABLE IF NOT EXISTS materiales_marcas (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(255) UNIQUE NOT NULL,
    descripcion TEXT,
    fabricante VARCHAR(255),
    pais_origen VARCHAR(120),
    sitio_web VARCHAR(255),
    contacto VARCHAR(255),
    notas TEXT,
    activo BOOLEAN DEFAULT TRUE,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabla de proveedores (nuevo módulo)
CREATE TABLE IF NOT EXISTS proveedores (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(255) NOT NULL,
    razon_social VARCHAR(255),
    ruc VARCHAR(30),
    direccion TEXT,
    telefono VARCHAR(50),
    email VARCHAR(255),
    contacto VARCHAR(255),
    notas TEXT,
    activo BOOLEAN DEFAULT TRUE,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabla de materiales eléctricos
CREATE TABLE IF NOT EXISTS materiales (
    id SERIAL PRIMARY KEY,
    descripcion VARCHAR(500) NOT NULL,
    marca VARCHAR(255),
    marca_id INTEGER REFERENCES materiales_marcas(id) ON DELETE SET NULL,
    precio NUMERIC(15, 2) NOT NULL DEFAULT 0,
    tiempo_instalacion NUMERIC(10, 2) DEFAULT 0,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabla de materiales genéricos
CREATE TABLE IF NOT EXISTS materiales_genericos (
    id SERIAL PRIMARY KEY,
    descripcion VARCHAR(500) NOT NULL,
    unidad VARCHAR(20) DEFAULT 'UND',
    tiempo_instalacion NUMERIC(10, 2) DEFAULT 0,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Renombrar tabla de templates si aún tiene el nombre antiguo
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_name = 'templates_presupuestos'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_name = 'templates_listas_materiales'
    ) THEN
        EXECUTE 'ALTER TABLE templates_presupuestos RENAME TO templates_listas_materiales';
        IF EXISTS (
            SELECT 1 FROM information_schema.sequences
            WHERE sequence_name = 'templates_presupuestos_id_seq'
        ) THEN
            EXECUTE 'ALTER SEQUENCE templates_presupuestos_id_seq RENAME TO templates_listas_materiales_id_seq';
        END IF;
    END IF;
END;
$$;

-- Tabla de templates de listas de materiales
CREATE TABLE IF NOT EXISTS templates_listas_materiales (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(255) NOT NULL,
    descripcion TEXT,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabla de items de templates (relación muchos a muchos)
CREATE TABLE IF NOT EXISTS template_items (
    id SERIAL PRIMARY KEY,
    template_id INTEGER NOT NULL REFERENCES templates_listas_materiales(id) ON DELETE CASCADE,
    item_mano_de_obra_id INTEGER REFERENCES items_mano_de_obra(id) ON DELETE CASCADE,
    material_generico_id INTEGER REFERENCES materiales_genericos(id) ON DELETE CASCADE,
    cantidad NUMERIC(10, 2) DEFAULT 1,
    orden INTEGER DEFAULT 0,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        (item_mano_de_obra_id IS NOT NULL AND material_generico_id IS NULL) OR
        (item_mano_de_obra_id IS NULL AND material_generico_id IS NOT NULL)
    )
);

-- Tabla de listas de materiales (antes presupuestos)
CREATE TABLE IF NOT EXISTS listas_materiales (
    id SERIAL PRIMARY KEY,
    cliente_id INTEGER REFERENCES clientes(id) ON DELETE SET NULL,
    numero_lista VARCHAR(50) UNIQUE NOT NULL,
    titulo VARCHAR(255),
    descripcion TEXT,
    estado VARCHAR(50) DEFAULT 'borrador', -- 'borrador', 'en construcción', 'asignando precios', etc.
    fecha_lista DATE DEFAULT CURRENT_DATE,
    validez_dias INTEGER DEFAULT 30,
    iva_porcentaje NUMERIC(5, 2) DEFAULT 21.0,
    notas TEXT,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabla de subgrupos de la lista de materiales
CREATE TABLE IF NOT EXISTS lista_materiales_subgrupos (
    id SERIAL PRIMARY KEY,
    lista_material_id INTEGER NOT NULL REFERENCES listas_materiales(id) ON DELETE CASCADE,
    numero INTEGER NOT NULL, -- Número del subgrupo (1, 2, 3, ...)
    nombre VARCHAR(255) NOT NULL, -- Nombre del subgrupo (ej: "MONTAJE DE BANDEJADO")
    orden INTEGER DEFAULT 0, -- Orden de visualización
    tiempo_ejecucion_horas NUMERIC(10, 2) DEFAULT 0, -- Tiempo total de ejecución en horas (se calcula desde los items)
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(lista_material_id, numero)
);

-- Tabla de items de la lista de materiales (snapshot de precios)
CREATE TABLE IF NOT EXISTS lista_materiales_items (
    id SERIAL PRIMARY KEY,
    lista_material_id INTEGER NOT NULL REFERENCES listas_materiales(id) ON DELETE CASCADE,
    subgrupo_id INTEGER REFERENCES lista_materiales_subgrupos(id) ON DELETE SET NULL,
    item_id INTEGER REFERENCES items_mano_de_obra(id) ON DELETE SET NULL,
    material_id INTEGER REFERENCES materiales(id) ON DELETE SET NULL,
    marca_id INTEGER REFERENCES materiales_marcas(id) ON DELETE SET NULL,
    codigo_item VARCHAR(50), -- Snapshot del código (por si se elimina el item)
    descripcion VARCHAR(500) NOT NULL, -- Snapshot de la descripción
    marca VARCHAR(255),
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

-- Tabla de precios por item (hasta 5 proveedores)
CREATE TABLE IF NOT EXISTS lista_materiales_precios (
    id SERIAL PRIMARY KEY,
    lista_material_item_id INTEGER NOT NULL REFERENCES lista_materiales_items(id) ON DELETE CASCADE,
    proveedor_id INTEGER NOT NULL REFERENCES proveedores(id) ON DELETE CASCADE,
    precio NUMERIC(15, 2) NOT NULL,
    moneda VARCHAR(10) DEFAULT 'PYG',
    fecha_cotizacion DATE DEFAULT CURRENT_DATE,
    notas TEXT,
    seleccionado BOOLEAN DEFAULT FALSE,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(lista_material_item_id, proveedor_id)
);

-- Índices para mejorar el rendimiento
CREATE INDEX IF NOT EXISTS idx_items_mano_de_obra_tipo ON items_mano_de_obra(tipo);
CREATE INDEX IF NOT EXISTS idx_items_mano_de_obra_activo ON items_mano_de_obra(activo);
CREATE INDEX IF NOT EXISTS idx_prefijos_codigos_tipo ON prefijos_codigos(tipo_servicio);
CREATE INDEX IF NOT EXISTS idx_prefijos_codigos_activo ON prefijos_codigos(activo);
CREATE UNIQUE INDEX IF NOT EXISTS idx_materiales_descripcion_unique ON materiales (LOWER(descripcion));
CREATE UNIQUE INDEX IF NOT EXISTS idx_materiales_marcas_nombre_unique ON materiales_marcas (LOWER(nombre));
CREATE INDEX IF NOT EXISTS idx_materiales_marca_id ON materiales(marca_id);
CREATE INDEX IF NOT EXISTS idx_proveedores_nombre ON proveedores (LOWER(nombre));
CREATE INDEX IF NOT EXISTS idx_listas_materiales_cliente ON listas_materiales(cliente_id);
CREATE INDEX IF NOT EXISTS idx_listas_materiales_estado ON listas_materiales(estado);
CREATE INDEX IF NOT EXISTS idx_listas_materiales_fecha ON listas_materiales(fecha_lista);
CREATE INDEX IF NOT EXISTS idx_lista_materiales_subgrupos_lista ON lista_materiales_subgrupos(lista_material_id);
CREATE INDEX IF NOT EXISTS idx_lista_materiales_items_lista ON lista_materiales_items(lista_material_id);
CREATE INDEX IF NOT EXISTS idx_lista_materiales_items_subgrupo ON lista_materiales_items(subgrupo_id);
CREATE INDEX IF NOT EXISTS idx_lista_materiales_items_item ON lista_materiales_items(item_id);
CREATE INDEX IF NOT EXISTS idx_lista_materiales_items_marca_id ON lista_materiales_items(marca_id);
CREATE INDEX IF NOT EXISTS idx_lista_materiales_precios_item ON lista_materiales_precios(lista_material_item_id);
CREATE INDEX IF NOT EXISTS idx_lista_materiales_precios_proveedor ON lista_materiales_precios(proveedor_id);
CREATE INDEX IF NOT EXISTS idx_materiales_genericos_descripcion ON materiales_genericos(descripcion);
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_class WHERE relname = 'idx_templates_presupuestos_nombre'
    ) THEN
        EXECUTE 'ALTER INDEX idx_templates_presupuestos_nombre RENAME TO idx_templates_listas_materiales_nombre';
    END IF;
END;
$$;

CREATE INDEX IF NOT EXISTS idx_templates_listas_materiales_nombre ON templates_listas_materiales(nombre);
CREATE INDEX IF NOT EXISTS idx_template_items_template ON template_items(template_id);
CREATE INDEX IF NOT EXISTS idx_template_items_item_mano_de_obra ON template_items(item_mano_de_obra_id);
CREATE INDEX IF NOT EXISTS idx_template_items_material_generico ON template_items(material_generico_id);

-- Asegurar columnas nuevas cuando ya existen tablas previas
ALTER TABLE lista_materiales_items
    ADD COLUMN IF NOT EXISTS material_id INTEGER REFERENCES materiales(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS marca VARCHAR(255),
    ADD COLUMN IF NOT EXISTS marca_id INTEGER REFERENCES materiales_marcas(id) ON DELETE SET NULL;

ALTER TABLE materiales
    ADD COLUMN IF NOT EXISTS marca VARCHAR(255),
    ADD COLUMN IF NOT EXISTS marca_id INTEGER REFERENCES materiales_marcas(id) ON DELETE SET NULL;

ALTER TABLE materiales_genericos
    ADD COLUMN IF NOT EXISTS unidad VARCHAR(20) DEFAULT 'UND';

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'materiales' AND column_name = 'proveedor'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'materiales' AND column_name = 'marca'
    ) THEN
        ALTER TABLE materiales RENAME COLUMN proveedor TO marca;
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'presupuesto_items' AND column_name = 'proveedor'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'presupuesto_items' AND column_name = 'marca'
    ) THEN
        ALTER TABLE presupuesto_items RENAME COLUMN proveedor TO marca;
    END IF;
END $$;

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

CREATE TRIGGER trigger_items_mano_de_obra_actualizado
    BEFORE UPDATE ON items_mano_de_obra
    FOR EACH ROW
    EXECUTE FUNCTION actualizar_timestamp();

CREATE TRIGGER trigger_materiales_actualizado
    BEFORE UPDATE ON materiales
    FOR EACH ROW
    EXECUTE FUNCTION actualizar_timestamp();

CREATE TRIGGER trigger_materiales_genericos_actualizado
    BEFORE UPDATE ON materiales_genericos
    FOR EACH ROW
    EXECUTE FUNCTION actualizar_timestamp();

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.triggers
        WHERE trigger_name = 'trigger_templates_presupuestos_actualizado'
    ) THEN
        EXECUTE 'DROP TRIGGER trigger_templates_presupuestos_actualizado ON templates_listas_materiales';
    END IF;
END;
$$;

CREATE TRIGGER trigger_templates_listas_materiales_actualizado
    BEFORE UPDATE ON templates_listas_materiales
    FOR EACH ROW
    EXECUTE FUNCTION actualizar_timestamp();

CREATE TRIGGER trigger_listas_materiales_actualizado
    BEFORE UPDATE ON listas_materiales
    FOR EACH ROW
    EXECUTE FUNCTION actualizar_timestamp();

-- Vista para listas de materiales con totales
DROP VIEW IF EXISTS vista_presupuestos_totales;
DROP VIEW IF EXISTS vista_listas_materiales_totales;
CREATE VIEW vista_listas_materiales_totales AS
SELECT 
    lm.id,
    lm.numero_lista AS numero_presupuesto,
    lm.titulo,
    COALESCE(c.nombre, 'Sin cliente') AS nombre_cliente,
    COALESCE(c.razon_social, c.nombre, 'Sin proveedor') AS nombre_proveedor,
    c.id AS cliente_id,
    COUNT(lmi.id) AS cantidad_items,
    COALESCE(SUM(lmi.precio_unitario * lmi.cantidad), 0) AS subtotal,
    lm.iva_porcentaje,
    COALESCE(SUM(lmi.precio_unitario * lmi.cantidad), 0) * lm.iva_porcentaje / 100 AS iva_monto,
    COALESCE(SUM(lmi.precio_unitario * lmi.cantidad), 0) * (1 + lm.iva_porcentaje / 100) AS total,
    lm.estado,
    lm.fecha_lista AS fecha_presupuesto,
    lm.validez_dias,
    lm.creado_en,
    lm.actualizado_en
FROM listas_materiales lm
LEFT JOIN clientes c ON lm.cliente_id = c.id
LEFT JOIN lista_materiales_items lmi ON lm.id = lmi.lista_material_id
GROUP BY lm.id, c.id, c.nombre, c.razon_social, lm.iva_porcentaje;

CREATE VIEW vista_presupuestos_totales AS
SELECT * FROM vista_listas_materiales_totales;

-- Función para generar número automático de lista de materiales
CREATE OR REPLACE FUNCTION generar_numero_lista()
RETURNS TEXT AS $$
DECLARE
    año_actual INTEGER;
    ultimo_numero INTEGER;
    nuevo_numero TEXT;
BEGIN
    año_actual := EXTRACT(YEAR FROM CURRENT_DATE);
    
    -- Buscar el último número del año actual
    SELECT COALESCE(MAX(
        CAST(SUBSTRING(numero_lista FROM '^LM-' || año_actual || '-(\d+)$') AS INTEGER)
    ), 0) INTO ultimo_numero
    FROM listas_materiales
    WHERE numero_lista LIKE 'LM-' || año_actual || '-%';
    
    -- Generar nuevo número
    nuevo_numero := 'LM-' || año_actual || '-' || LPAD((ultimo_numero + 1)::TEXT, 4, '0');
    
    RETURN nuevo_numero;
END;
$$ LANGUAGE plpgsql;

-- Compatibilidad con el nombre anterior
CREATE OR REPLACE FUNCTION generar_numero_presupuesto()
RETURNS TEXT AS $$
BEGIN
    RETURN generar_numero_lista();
END;
$$ LANGUAGE plpgsql;

-- Función para eliminar duplicados de materiales_genéricos
-- Mantiene solo el registro con el menor ID (más antiguo) para cada descripción única
CREATE OR REPLACE FUNCTION eliminar_duplicados_materiales_genericos()
RETURNS TABLE(eliminados INTEGER, mensaje TEXT) AS $$
DECLARE
    total_eliminados INTEGER := 0;
    materiales_unicos INTEGER;
    total_materiales INTEGER;
BEGIN
    -- Contar total de materiales antes
    SELECT COUNT(*) INTO total_materiales FROM materiales_genericos;
    
    -- Eliminar duplicados manteniendo solo el registro con menor ID
    WITH materiales_a_mantener AS (
        SELECT MIN(id) as id_mantener
        FROM materiales_genericos
        GROUP BY UPPER(TRIM(descripcion))
    )
    DELETE FROM materiales_genericos
    WHERE id NOT IN (SELECT id_mantener FROM materiales_a_mantener);
    
    GET DIAGNOSTICS total_eliminados = ROW_COUNT;
    
    -- Contar materiales únicos después
    SELECT COUNT(*) INTO materiales_unicos FROM materiales_genericos;
    
    -- Retornar resultado
    RETURN QUERY SELECT 
        total_eliminados,
        format('Se eliminaron %s material(es) duplicado(s). Quedaron %s material(es) único(s) de un total inicial de %s.', 
               total_eliminados, materiales_unicos, total_materiales)::TEXT;
END;
$$ LANGUAGE plpgsql;

