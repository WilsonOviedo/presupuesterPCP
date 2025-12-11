-- Esquema SQL para sistema de presupuestos
-- PostgreSQL compatible

-- ============================================
-- TABLAS DE PRECIOS Y FACTURAS
-- ============================================

-- Tabla de precios (procesados desde facturas XML)
CREATE TABLE IF NOT EXISTS precios (
    id SERIAL PRIMARY KEY,
    proveedor TEXT,
    fecha TIMESTAMP,
    producto TEXT,
    precio NUMERIC,
    UNIQUE(proveedor, fecha, producto, precio)
);

-- Índices para la tabla de precios
CREATE INDEX IF NOT EXISTS idx_precios_proveedor ON precios(proveedor);
CREATE INDEX IF NOT EXISTS idx_precios_producto ON precios(producto);
CREATE INDEX IF NOT EXISTS idx_precios_fecha ON precios(fecha);
CREATE INDEX IF NOT EXISTS idx_precios_proveedor_producto ON precios(proveedor, producto);

-- Tabla para facturas ya procesadas (evita duplicados)
CREATE TABLE IF NOT EXISTS facturas_procesadas (
    id SERIAL PRIMARY KEY,
    nombre_archivo TEXT,
    hash_md5 TEXT UNIQUE,
    fecha_procesado TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Índices para la tabla de facturas procesadas
CREATE INDEX IF NOT EXISTS idx_facturas_procesadas_hash ON facturas_procesadas(hash_md5);
CREATE INDEX IF NOT EXISTS idx_facturas_procesadas_fecha ON facturas_procesadas(fecha_procesado);

-- ============================================
-- TABLAS DE PRESUPUESTOS Y MATERIALES
-- ============================================

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
    iva_porcentaje NUMERIC(5, 2) DEFAULT 10.0,
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

-- ============================================
-- SISTEMA DE AUTENTICACIÓN Y PERMISOS
-- ============================================

-- Tabla de usuarios
CREATE TABLE IF NOT EXISTS usuarios (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) UNIQUE,
    password_hash VARCHAR(255),
    nombre_completo VARCHAR(255),
    email VARCHAR(255),
    es_admin BOOLEAN DEFAULT FALSE,
    activo BOOLEAN DEFAULT TRUE,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ultimo_acceso TIMESTAMP
);

-- Agregar columna registro_completo si no existe (debe ser antes de usarla)
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS registro_completo BOOLEAN DEFAULT FALSE;

-- Modificar constraint de username para permitir NULL
DO $$
BEGIN
    -- Permitir NULL en username si tiene NOT NULL
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'usuarios' 
        AND column_name = 'username' 
        AND is_nullable = 'NO'
    ) THEN
        ALTER TABLE usuarios ALTER COLUMN username DROP NOT NULL;
    END IF;
    
    -- Permitir NULL en password_hash si tiene NOT NULL
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'usuarios' 
        AND column_name = 'password_hash' 
        AND is_nullable = 'NO'
    ) THEN
        ALTER TABLE usuarios ALTER COLUMN password_hash DROP NOT NULL;
    END IF;
    
    -- Asegurar que email sea UNIQUE y NOT NULL
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE table_name = 'usuarios' 
        AND constraint_name = 'usuarios_email_key'
    ) THEN
        -- Primero hacer email NOT NULL si no lo es
        IF EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'usuarios' 
            AND column_name = 'email' 
            AND is_nullable = 'YES'
        ) THEN
            ALTER TABLE usuarios ALTER COLUMN email SET NOT NULL;
        END IF;
        
        -- Luego agregar constraint UNIQUE
        ALTER TABLE usuarios ADD CONSTRAINT usuarios_email_key UNIQUE (email);
    END IF;
END $$;

-- Asegurar que usuarios existentes tengan registro_completo = TRUE si tienen username
-- (Solo después de asegurar que la columna existe)
DO $$
BEGIN
    -- Verificar que la tabla y la columna existen
    IF EXISTS (
        SELECT 1 FROM information_schema.tables 
        WHERE table_name = 'usuarios'
    ) AND EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'usuarios' 
        AND column_name = 'registro_completo'
    ) THEN
        -- Actualizar solo si hay registros que cumplen la condición
        UPDATE usuarios 
        SET registro_completo = TRUE 
        WHERE username IS NOT NULL 
        AND password_hash IS NOT NULL 
        AND (registro_completo IS NULL OR registro_completo = FALSE);
    END IF;
EXCEPTION
    WHEN OTHERS THEN
        -- Si hay algún error, continuar sin actualizar
        NULL;
END $$;

-- Agregar constraint CHECK para validar registro_completo
DO $$
BEGIN
    -- Eliminar constraint anterior si existe
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE table_name = 'usuarios' 
        AND constraint_name = 'usuarios_registro_completo_check'
    ) THEN
        ALTER TABLE usuarios DROP CONSTRAINT usuarios_registro_completo_check;
    END IF;
    
    -- Agregar nuevo constraint
    ALTER TABLE usuarios ADD CONSTRAINT usuarios_registro_completo_check 
    CHECK (
        (username IS NOT NULL AND password_hash IS NOT NULL AND registro_completo = TRUE) 
        OR 
        (username IS NULL AND password_hash IS NULL AND registro_completo = FALSE)
    );
EXCEPTION
    WHEN OTHERS THEN
        -- Si falla, continuar sin el constraint
        NULL;
END $$;

-- Tabla de permisos (rutas protegidas)
CREATE TABLE IF NOT EXISTS permisos_rutas (
    id SERIAL PRIMARY KEY,
    ruta VARCHAR(255) NOT NULL UNIQUE,
    nombre VARCHAR(255) NOT NULL,
    descripcion TEXT,
    activo BOOLEAN DEFAULT TRUE,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabla de asignación de permisos a usuarios
CREATE TABLE IF NOT EXISTS usuarios_permisos (
    id SERIAL PRIMARY KEY,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    permiso_ruta_id INTEGER NOT NULL REFERENCES permisos_rutas(id) ON DELETE CASCADE,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(usuario_id, permiso_ruta_id)
);

-- Índices para usuarios y permisos
CREATE INDEX IF NOT EXISTS idx_usuarios_username ON usuarios(username);
CREATE INDEX IF NOT EXISTS idx_usuarios_activo ON usuarios(activo);
CREATE INDEX IF NOT EXISTS idx_permisos_rutas_ruta ON permisos_rutas(ruta);
CREATE INDEX IF NOT EXISTS idx_usuarios_permisos_usuario ON usuarios_permisos(usuario_id);
CREATE INDEX IF NOT EXISTS idx_usuarios_permisos_permiso ON usuarios_permisos(permiso_ruta_id);

-- Trigger para actualizar timestamp de usuarios
CREATE TRIGGER trigger_usuarios_actualizado
    BEFORE UPDATE ON usuarios
    FOR EACH ROW
    EXECUTE FUNCTION actualizar_timestamp();

-- Insertar permisos básicos para rutas principales
INSERT INTO permisos_rutas (ruta, nombre, descripcion) VALUES
    ('/precios', 'Ver precios', 'Acceso a la búsqueda y visualización de precios'),
    ('/precios/cargar-manual', 'Cargar precios manualmente', 'Permite cargar precios manualmente'),
    ('/precios/cargar-proveedores', 'Cargar proveedores', 'Permite cargar proveedores desde la tabla de precios'),
    ('/leer-facturas', 'Leer facturas', 'Acceso al procesamiento de facturas desde correo'),
    ('/calculadora', 'Calculadora de precio', 'Acceso a la calculadora de precios'),
    ('/historial', 'Historial de precios', 'Acceso al historial y gráficos de precios'),
    ('/listas-materiales', 'Listas de materiales', 'Acceso a la gestión de listas de materiales'),
    ('/listas-materiales/clientes', 'Gestión de clientes', 'Acceso a la gestión de clientes'),
    ('/listas-materiales/items_mano_de_obra', 'Gestión de items', 'Acceso a la gestión de items de mano de obra'),
    ('/listas-materiales/materiales', 'Gestión de materiales', 'Acceso a la gestión de materiales'),
    ('/listas-materiales/materiales_genericos', 'Gestión de materiales genéricos', 'Acceso a la gestión de materiales genéricos'),
    ('/listas-materiales/marcas', 'Gestión de marcas', 'Acceso a la gestión de marcas'),
    ('/listas-materiales/prefijos_codigos', 'Gestión de prefijos', 'Acceso a la gestión de prefijos de códigos'),
    ('/usuarios', 'Gestión de usuarios', 'Acceso a la gestión de usuarios y permisos'),
    ('/facturacion', 'Facturación', 'Acceso al módulo de facturación'),
    ('/reportes/clientes', 'Reportes de Clientes', 'Acceso a reportes de clientes'),
    ('/reportes/cuentas-a-recibir', 'Reportes de Cuentas a Recibir', 'Acceso a reportes de cuentas a recibir'),
    ('/reportes/cuentas-a-pagar', 'Reportes de Cuentas a Pagar', 'Acceso a reportes de cuentas a pagar'),
    ('/reportes/analisis', 'Análisis Históricos', 'Acceso al análisis histórico y dashboard financiero')
ON CONFLICT (ruta) DO NOTHING;

-- ============================================
-- TABLAS DE FACTURACIÓN
-- ============================================

-- Tabla de facturas
CREATE TABLE IF NOT EXISTS facturas (
    id SERIAL PRIMARY KEY,
    numero_factura VARCHAR(50) UNIQUE,
    fecha DATE NOT NULL,
    cliente VARCHAR(255) NOT NULL,
    ruc VARCHAR(50),
    direccion TEXT,
    nota_remision VARCHAR(100),
    moneda VARCHAR(10) DEFAULT 'Gs', -- 'Gs' o 'USD'
    tipo_venta VARCHAR(20) DEFAULT 'Contado', -- 'Contado' o 'Crédito'
    plazo_dias INTEGER, -- Plazo en días para ventas a crédito
    total_excentas NUMERIC(15, 2) DEFAULT 0,
    total_iva5 NUMERIC(15, 2) DEFAULT 0,
    total_iva10 NUMERIC(15, 2) DEFAULT 0,
    iva_total NUMERIC(15, 2) DEFAULT 0,
    total_general NUMERIC(15, 2) NOT NULL,
    total_en_letras TEXT,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabla de items de facturas
CREATE TABLE IF NOT EXISTS facturas_items (
    id SERIAL PRIMARY KEY,
    factura_id INTEGER NOT NULL REFERENCES facturas(id) ON DELETE CASCADE,
    cantidad NUMERIC(10, 2) NOT NULL,
    descripcion VARCHAR(500) NOT NULL,
    precio_unitario NUMERIC(15, 2) NOT NULL,
    impuesto VARCHAR(10) DEFAULT 'exc', -- 'exc', '5', '10'
    subtotal NUMERIC(15, 2) GENERATED ALWAYS AS (
        cantidad * precio_unitario
    ) STORED,
    orden INTEGER DEFAULT 0,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Índices para facturas
CREATE INDEX IF NOT EXISTS idx_facturas_fecha ON facturas(fecha);
CREATE INDEX IF NOT EXISTS idx_facturas_cliente ON facturas(cliente);
CREATE INDEX IF NOT EXISTS idx_facturas_numero ON facturas(numero_factura);
CREATE INDEX IF NOT EXISTS idx_facturas_items_factura ON facturas_items(factura_id);

-- Agregar columnas si no existen (para migraciones)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'facturas' AND column_name = 'plazo_dias'
    ) THEN
        ALTER TABLE facturas ADD COLUMN plazo_dias INTEGER;
    END IF;
    
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'facturas' AND column_name = 'fecha_vencimiento'
    ) THEN
        ALTER TABLE facturas ADD COLUMN fecha_vencimiento DATE;
    END IF;
    
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'facturas' AND column_name = 'fecha_pago'
    ) THEN
        ALTER TABLE facturas ADD COLUMN fecha_pago DATE;
    END IF;
    
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'facturas' AND column_name = 'estado_pago'
    ) THEN
        ALTER TABLE facturas ADD COLUMN estado_pago VARCHAR(20) DEFAULT 'pendiente';
    END IF;
END $$;

-- Trigger para actualizar timestamp de facturas
CREATE TRIGGER trigger_facturas_actualizado
    BEFORE UPDATE ON facturas
    FOR EACH ROW
    EXECUTE FUNCTION actualizar_timestamp();

-- ============================================
-- TABLAS FINANCIERAS
-- ============================================

-- Tabla de categorías de ingresos (categorías principales)
CREATE TABLE IF NOT EXISTS categorias_ingresos (
    id SERIAL PRIMARY KEY,
    codigo VARCHAR(20) UNIQUE NOT NULL, -- Ej: "1.1", "1.2", "1.3"
    nombre VARCHAR(255) NOT NULL, -- Ej: "Ingresos con Producto", "Ingresos con Servicios"
    orden INTEGER DEFAULT 0,
    activo BOOLEAN DEFAULT TRUE,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabla de tipos de ingresos (subcategorías)
CREATE TABLE IF NOT EXISTS tipos_ingresos (
    id SERIAL PRIMARY KEY,
    categoria_id INTEGER NOT NULL REFERENCES categorias_ingresos(id) ON DELETE CASCADE,
    codigo VARCHAR(20) NOT NULL, -- Ej: "1.1.1", "1.2.1"
    descripcion VARCHAR(255) NOT NULL, -- Ej: "Venta de Materiales", "Retrofit de maquinas"
    orden INTEGER DEFAULT 0,
    activo BOOLEAN DEFAULT TRUE,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(categoria_id, codigo)
);

-- Índices para tablas financieras
CREATE INDEX IF NOT EXISTS idx_categorias_ingresos_orden ON categorias_ingresos(orden);
CREATE INDEX IF NOT EXISTS idx_tipos_ingresos_categoria ON tipos_ingresos(categoria_id);
CREATE INDEX IF NOT EXISTS idx_tipos_ingresos_orden ON tipos_ingresos(orden);

-- Tabla de categorías de gastos (categorías principales)
CREATE TABLE IF NOT EXISTS categorias_gastos (
    id SERIAL PRIMARY KEY,
    codigo VARCHAR(20) UNIQUE NOT NULL, -- Ej: "1", "2", "3"
    nombre VARCHAR(255) NOT NULL, -- Ej: "GASTOS OPERATIVOS", "GASTOS ADMINISTRATIVOS"
    orden INTEGER DEFAULT 0,
    activo BOOLEAN DEFAULT TRUE,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabla de tipos de gastos (subcategorías)
CREATE TABLE IF NOT EXISTS tipos_gastos (
    id SERIAL PRIMARY KEY,
    categoria_id INTEGER NOT NULL REFERENCES categorias_gastos(id) ON DELETE CASCADE,
    codigo VARCHAR(20) NOT NULL, -- Ej: "1.1", "1.2", "2.1"
    descripcion VARCHAR(255) NOT NULL, -- Ej: "ALQUILER", "SERVICIOS PUBLICOS"
    orden INTEGER DEFAULT 0,
    activo BOOLEAN DEFAULT TRUE,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(categoria_id, codigo)
);

-- Índices para tablas de gastos
CREATE INDEX IF NOT EXISTS idx_categorias_gastos_orden ON categorias_gastos(orden);
CREATE INDEX IF NOT EXISTS idx_tipos_gastos_categoria ON tipos_gastos(categoria_id);
CREATE INDEX IF NOT EXISTS idx_tipos_gastos_orden ON tipos_gastos(orden);

-- Agregar permisos para módulo financiero
INSERT INTO permisos_rutas (ruta, nombre, descripcion) 
VALUES ('/financiero', 'Módulo Financiero', 'Acceso al módulo financiero')
ON CONFLICT (ruta) DO NOTHING;

INSERT INTO permisos_rutas (ruta, nombre, descripcion) 
VALUES ('/financiero/tipos-ingresos', 'Tipos de Ingresos', 'Gestión de tipos de ingresos')
ON CONFLICT (ruta) DO NOTHING;

INSERT INTO permisos_rutas (ruta, nombre, descripcion) 
VALUES ('/financiero/tipos-gastos', 'Tipos de Gastos', 'Gestión de tipos de gastos')
ON CONFLICT (ruta) DO NOTHING;

-- Tabla de proyectos
CREATE TABLE IF NOT EXISTS proyectos (
    id SERIAL PRIMARY KEY,
    codigo INTEGER UNIQUE NOT NULL, -- Ej: 1, 2, 3...
    nombre VARCHAR(255) NOT NULL, -- Ej: "CONSOLIDADO", "PCP", "KF S.A"
    activo BOOLEAN DEFAULT TRUE,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabla de tipos de documentos
CREATE TABLE IF NOT EXISTS tipos_documentos (
    id SERIAL PRIMARY KEY,
    codigo INTEGER UNIQUE NOT NULL, -- Ej: 1, 2, 3...
    nombre VARCHAR(255) NOT NULL, -- Ej: "EFECTIVO", "CONTRAFACTURA", "TRANSFERENCIA"
    activo BOOLEAN DEFAULT TRUE,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Índices para proyectos y tipos de documentos
CREATE INDEX IF NOT EXISTS idx_proyectos_codigo ON proyectos(codigo);
CREATE INDEX IF NOT EXISTS idx_tipos_documentos_codigo ON tipos_documentos(codigo);

-- Agregar permisos para proyectos y tipos de documentos
INSERT INTO permisos_rutas (ruta, nombre, descripcion) 
VALUES ('/financiero/proyectos', 'Proyectos', 'Gestión de proyectos')
ON CONFLICT (ruta) DO NOTHING;

INSERT INTO permisos_rutas (ruta, nombre, descripcion) 
VALUES ('/financiero/tipos-documentos', 'Tipos de Documentos', 'Gestión de tipos de documentos')
ON CONFLICT (ruta) DO NOTHING;

-- Tabla de bancos
CREATE TABLE IF NOT EXISTS bancos (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(255) NOT NULL UNIQUE,
    saldo_inicial NUMERIC(15, 2) DEFAULT 0,
    activo BOOLEAN DEFAULT TRUE,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabla de configuración para saldos iniciales
CREATE TABLE IF NOT EXISTS configuracion_saldos_iniciales (
    id INTEGER PRIMARY KEY DEFAULT 1,
    fecha_saldo_inicial DATE,
    actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT configuracion_saldos_iniciales_single_row CHECK (id = 1)
);

-- Insertar registro inicial si no existe
INSERT INTO configuracion_saldos_iniciales (id, fecha_saldo_inicial)
VALUES (1, NULL)
ON CONFLICT (id) DO NOTHING;

-- Tabla de cuentas a recibir
CREATE TABLE IF NOT EXISTS cuentas_a_recibir (
    id SERIAL PRIMARY KEY,
    fecha_emision DATE NOT NULL,
    documento_id INTEGER REFERENCES tipos_documentos(id),
    cuenta_id INTEGER REFERENCES categorias_ingresos(id), -- ID de la categoría (Cuenta)
    plano_cuenta VARCHAR(255), -- Nombre del tipo de ingreso (Plano de Conta)
    proyecto_id INTEGER REFERENCES proyectos(id), -- ID del proyecto
    tipo VARCHAR(20) DEFAULT 'RECURRENTE', -- 'RECURRENTE' o 'PARCELADO'
    cliente VARCHAR(255), -- Nombre del cliente (de tabla clientes)
    factura VARCHAR(100), -- Número de factura
    descripcion TEXT,
    banco_id INTEGER REFERENCES bancos(id), -- Recibido por la cuenta (banco)
    valor NUMERIC(15, 2) NOT NULL,
    cuotas VARCHAR(20), -- Ej: "1 de 1", "1 de 2", "2 de 2"
    valor_cuota NUMERIC(15, 2),
    vencimiento DATE,
    fecha_recibo DATE,
    estado VARCHAR(20) DEFAULT 'ABIERTO', -- 'RECIBIDO' o 'ABIERTO'
    status_recibo VARCHAR(20), -- 'ADELANTADO', 'ATRASADO', 'EN DIA'
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Agregar columnas si no existen (para migraciones)
DO $$ 
BEGIN
    -- Agregar cuenta_id
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'cuentas_a_recibir' AND column_name = 'cuenta_id'
    ) THEN
        ALTER TABLE cuentas_a_recibir 
        ADD COLUMN cuenta_id INTEGER REFERENCES categorias_ingresos(id);
    END IF;
    
    -- Agregar proyecto_id
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'cuentas_a_recibir' AND column_name = 'proyecto_id'
    ) THEN
        ALTER TABLE cuentas_a_recibir 
        ADD COLUMN proyecto_id INTEGER REFERENCES proyectos(id);
    END IF;
    
    -- Cambiar estado por defecto a ABIERTO si existe la columna
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'cuentas_a_recibir' AND column_name = 'estado'
    ) THEN
        ALTER TABLE cuentas_a_recibir 
        ALTER COLUMN estado SET DEFAULT 'ABIERTO';
    END IF;
    
    -- Agregar columna factura
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'cuentas_a_recibir' AND column_name = 'factura'
    ) THEN
        ALTER TABLE cuentas_a_recibir 
        ADD COLUMN factura VARCHAR(100);
    END IF;
    
    -- Agregar columna monto_abonado
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'cuentas_a_recibir' AND column_name = 'monto_abonado'
    ) THEN
        ALTER TABLE cuentas_a_recibir 
        ADD COLUMN monto_abonado NUMERIC(15, 2) DEFAULT 0;
    END IF;
END $$;

-- Índices para cuentas a recibir
CREATE INDEX IF NOT EXISTS idx_cuentas_a_recibir_fecha_emision ON cuentas_a_recibir(fecha_emision);
CREATE INDEX IF NOT EXISTS idx_cuentas_a_recibir_cliente ON cuentas_a_recibir(cliente);
CREATE INDEX IF NOT EXISTS idx_cuentas_a_recibir_estado ON cuentas_a_recibir(estado);
CREATE INDEX IF NOT EXISTS idx_cuentas_a_recibir_vencimiento ON cuentas_a_recibir(vencimiento);

-- Tabla de cuentas a pagar
CREATE TABLE IF NOT EXISTS cuentas_a_pagar (
    id SERIAL PRIMARY KEY,
    fecha_emision DATE NOT NULL,
    documento_id INTEGER REFERENCES tipos_documentos(id),
    cuenta_id INTEGER REFERENCES categorias_gastos(id), -- ID de la categoría (Cuenta)
    plano_cuenta VARCHAR(255), -- Nombre del tipo de gasto (Plano de Conta)
    proyecto_id INTEGER REFERENCES proyectos(id), -- ID del proyecto
    tipo VARCHAR(20) DEFAULT 'RECURRENTE', -- 'RECURRENTE' o 'PARCELADO'
    proveedor VARCHAR(255), -- Nombre del proveedor (de tabla proveedores)
    factura VARCHAR(100), -- Número de factura
    descripcion TEXT,
    banco_id INTEGER REFERENCES bancos(id), -- Pagado por la cuenta (banco)
    valor NUMERIC(15, 2) NOT NULL,
    cuotas VARCHAR(20), -- Ej: "1 de 1", "1 de 2", "2 de 2"
    valor_cuota NUMERIC(15, 2),
    vencimiento DATE,
    fecha_pago DATE,
    estado VARCHAR(20) DEFAULT 'ABIERTO', -- 'PAGADO' o 'ABIERTO'
    status_pago VARCHAR(20), -- 'ADELANTADO', 'ATRASADO', 'EN DIA'
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Agregar columnas si no existen (para migraciones) - cuentas a pagar
DO $$ 
BEGIN
    -- Agregar columna factura
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'cuentas_a_pagar' AND column_name = 'factura'
    ) THEN
        ALTER TABLE cuentas_a_pagar 
        ADD COLUMN factura VARCHAR(100);
    END IF;
    
    -- Agregar columna monto_abonado
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'cuentas_a_pagar' AND column_name = 'monto_abonado'
    ) THEN
        ALTER TABLE cuentas_a_pagar 
        ADD COLUMN monto_abonado NUMERIC(15, 2) DEFAULT 0;
    END IF;
END $$;

-- Índices para cuentas a pagar
CREATE INDEX IF NOT EXISTS idx_cuentas_a_pagar_fecha_emision ON cuentas_a_pagar(fecha_emision);
CREATE INDEX IF NOT EXISTS idx_cuentas_a_pagar_proveedor ON cuentas_a_pagar(proveedor);
CREATE INDEX IF NOT EXISTS idx_cuentas_a_pagar_estado ON cuentas_a_pagar(estado);
CREATE INDEX IF NOT EXISTS idx_cuentas_a_pagar_vencimiento ON cuentas_a_pagar(vencimiento);

-- Agregar permisos para nuevos módulos
INSERT INTO permisos_rutas (ruta, nombre, descripcion) 
VALUES ('/financiero/saldos-iniciales', 'Saldos Iniciales', 'Gestión de bancos y saldos iniciales')
ON CONFLICT (ruta) DO NOTHING;

INSERT INTO permisos_rutas (ruta, nombre, descripcion) 
VALUES 
    ('/financiero/cuentas-a-recibir', 'Cuentas a Recibir', 'Gestión de cuentas a recibir'),
    ('/financiero/cuentas-a-pagar', 'Cuentas a Pagar', 'Gestión de cuentas a pagar'),
    ('/financiero/transferencias', 'Transferencias entre Cuentas', 'Gestión de transferencias entre cuentas bancarias')
ON CONFLICT (ruta) DO NOTHING;

-- Agregar permisos para conciliación bancaria
INSERT INTO permisos_rutas (ruta, nombre, descripcion) 
VALUES ('/reportes/conciliacion-bancaria', 'Conciliación Bancaria', 'Acceso a la conciliación bancaria diaria')
ON CONFLICT (ruta) DO NOTHING;

INSERT INTO permisos_rutas (ruta, nombre, descripcion) 
VALUES ('/reportes/flujo-caja-mensual', 'Flujo de Caja Mensual', 'Acceso al reporte de flujo de caja mensual detallado')
ON CONFLICT (ruta) DO NOTHING;

INSERT INTO permisos_rutas (ruta, nombre, descripcion) 
VALUES ('/reportes/dre', 'DRE - Demonstrativo de Resultado', 'Acceso al reporte DRE (Demonstrativo de Resultado)')
ON CONFLICT (ruta) DO NOTHING;

