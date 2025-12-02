"""Script para migrar la tabla items a items_mano_de_obra"""
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

def migrar_tabla():
    conn = psycopg2.connect(**PG_CONN)
    cur = conn.cursor()
    
    try:
        # Verificar si existe la tabla items
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'items'
            )
        """)
        existe_items = cur.fetchone()[0]
        
        # Verificar si existe la tabla items_mano_de_obra
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'items_mano_de_obra'
            )
        """)
        existe_items_mano_de_obra = cur.fetchone()[0]
        
        if existe_items and not existe_items_mano_de_obra:
            print("Renombrando tabla 'items' a 'items_mano_de_obra'...")
            cur.execute("ALTER TABLE items RENAME TO items_mano_de_obra")
            
            # Renombrar indices si existen
            try:
                cur.execute("ALTER INDEX IF EXISTS idx_items_tipo RENAME TO idx_items_mano_de_obra_tipo")
            except:
                pass
            
            try:
                cur.execute("ALTER INDEX IF EXISTS idx_items_activo RENAME TO idx_items_mano_de_obra_activo")
            except:
                pass
            
            # Eliminar trigger antiguo si existe
            try:
                cur.execute("DROP TRIGGER IF EXISTS trigger_items_actualizado ON items_mano_de_obra")
            except:
                pass
            
            # Crear nuevo trigger
            cur.execute("""
                CREATE TRIGGER trigger_items_mano_de_obra_actualizado
                    BEFORE UPDATE ON items_mano_de_obra
                    FOR EACH ROW
                    EXECUTE FUNCTION actualizar_timestamp()
            """)
            
            conn.commit()
            print("Migracion completada exitosamente!")
            
        elif existe_items_mano_de_obra:
            print("La tabla 'items_mano_de_obra' ya existe. No se requiere migracion.")
            
        elif not existe_items and not existe_items_mano_de_obra:
            print("No existe ninguna de las tablas. Ejecuta el esquema SQL completo para crearlas.")
            
    except Exception as e:
        conn.rollback()
        print(f"Error durante la migracion: {e}")
        raise
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    migrar_tabla()

