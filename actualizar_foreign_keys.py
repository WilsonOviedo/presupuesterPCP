"""Script para actualizar foreign keys después de renombrar la tabla"""
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

def actualizar_foreign_keys():
    conn = psycopg2.connect(**PG_CONN)
    cur = conn.cursor()
    
    try:
        # Verificar si existe la constraint antigua
        cur.execute("""
            SELECT constraint_name 
            FROM information_schema.table_constraints 
            WHERE table_name = 'presupuesto_items' 
            AND constraint_name LIKE '%item_id%'
            AND constraint_type = 'FOREIGN KEY'
        """)
        constraints = cur.fetchall()
        
        if constraints:
            # Eliminar constraint antigua
            for constraint in constraints:
                constraint_name = constraint[0]
                print(f"Eliminando constraint: {constraint_name}")
                cur.execute(f"ALTER TABLE presupuesto_items DROP CONSTRAINT IF EXISTS {constraint_name}")
            
            # Crear nueva constraint apuntando a items_mano_de_obra
            print("Creando nueva foreign key hacia items_mano_de_obra...")
            cur.execute("""
                ALTER TABLE presupuesto_items 
                ADD CONSTRAINT presupuesto_items_item_id_fkey 
                FOREIGN KEY (item_id) 
                REFERENCES items_mano_de_obra(id) 
                ON DELETE SET NULL
            """)
            
            conn.commit()
            print("Foreign keys actualizadas exitosamente!")
        else:
            print("No se encontraron foreign keys para actualizar.")
            
    except Exception as e:
        conn.rollback()
        print(f"Error: {e}")
        # Si la constraint ya existe, está bien
        if "already exists" in str(e).lower():
            print("La foreign key ya existe correctamente.")
        else:
            raise
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    actualizar_foreign_keys()

