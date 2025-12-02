"""Script para crear las nuevas tablas de materiales_genericos y templates"""
from dotenv import load_dotenv
import psycopg2
import os

load_dotenv()

PG_CONN = {
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT"),
}

def crear_nuevas_tablas():
    conn = psycopg2.connect(**PG_CONN)
    cur = conn.cursor()
    
    try:
        print("Creando tabla materiales_genericos...")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS materiales_genericos (
                id SERIAL PRIMARY KEY,
                descripcion VARCHAR(500) NOT NULL,
                tiempo_instalacion NUMERIC(10, 2) DEFAULT 0,
                creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        print("Creando tabla templates_presupuestos...")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS templates_presupuestos (
                id SERIAL PRIMARY KEY,
                nombre VARCHAR(255) NOT NULL,
                descripcion TEXT,
                creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        print("Creando tabla template_items...")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS template_items (
                id SERIAL PRIMARY KEY,
                template_id INTEGER NOT NULL REFERENCES templates_presupuestos(id) ON DELETE CASCADE,
                item_mano_de_obra_id INTEGER REFERENCES items_mano_de_obra(id) ON DELETE CASCADE,
                material_generico_id INTEGER REFERENCES materiales_genericos(id) ON DELETE CASCADE,
                cantidad NUMERIC(10, 2) DEFAULT 1,
                orden INTEGER DEFAULT 0,
                creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CHECK (
                    (item_mano_de_obra_id IS NOT NULL AND material_generico_id IS NULL) OR
                    (item_mano_de_obra_id IS NULL AND material_generico_id IS NOT NULL)
                )
            )
        """)
        
        print("Creando indices...")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_materiales_genericos_descripcion ON materiales_genericos(descripcion)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_templates_presupuestos_nombre ON templates_presupuestos(nombre)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_template_items_template ON template_items(template_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_template_items_item_mano_de_obra ON template_items(item_mano_de_obra_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_template_items_material_generico ON template_items(material_generico_id)")
        
        print("Creando triggers...")
        cur.execute("DROP TRIGGER IF EXISTS trigger_materiales_genericos_actualizado ON materiales_genericos")
        cur.execute("""
            CREATE TRIGGER trigger_materiales_genericos_actualizado
                BEFORE UPDATE ON materiales_genericos
                FOR EACH ROW
                EXECUTE FUNCTION actualizar_timestamp()
        """)
        
        cur.execute("DROP TRIGGER IF EXISTS trigger_templates_presupuestos_actualizado ON templates_presupuestos")
        cur.execute("""
            CREATE TRIGGER trigger_templates_presupuestos_actualizado
                BEFORE UPDATE ON templates_presupuestos
                FOR EACH ROW
                EXECUTE FUNCTION actualizar_timestamp()
        """)
        
        conn.commit()
        print("\nTodas las tablas, indices y triggers fueron creados exitosamente!")
        
    except Exception as e:
        conn.rollback()
        print(f"Error: {e}")
        raise
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    crear_nuevas_tablas()

