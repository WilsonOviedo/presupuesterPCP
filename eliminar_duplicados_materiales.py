#!/usr/bin/env python3
"""
Script para eliminar duplicados de materiales_genéricos.
Uso: python eliminar_duplicados_materiales.py
"""

import os
import sys
from dotenv import load_dotenv
import psycopg2

# Cargar variables de entorno
load_dotenv()

def obtener_conexion():
    """Obtiene una conexión a la base de datos"""
    try:
        conn = psycopg2.connect(
            dbname=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            host=os.getenv("DB_HOST"),
            port=os.getenv("DB_PORT"),
        )
        return conn
    except Exception as e:
        print(f"[ERROR] Error al conectar a la base de datos: {e}")
        sys.exit(1)

def verificar_funcion_existe(conn):
    """Verifica si la función existe, si no existe, la crea desde el schema"""
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT EXISTS (
                SELECT 1 
                FROM pg_proc 
                WHERE proname = 'eliminar_duplicados_materiales_genericos'
            )
        """)
        existe = cur.fetchone()[0]
        
        if not existe:
            print("[INFO] La función no existe. Creándola desde el schema...")
            # Leer y ejecutar solo la función del schema
            try:
                with open('schema_presupuestos.sql', 'r', encoding='utf-8') as f:
                    contenido = f.read()
                
                # Buscar la función en el contenido
                inicio_funcion = contenido.find('CREATE OR REPLACE FUNCTION eliminar_duplicados_materiales_genericos()')
                if inicio_funcion != -1:
                    # Buscar el final de la función (buscar el último $$ LANGUAGE plpgsql; después del inicio)
                    fin_funcion = contenido.find('$$ LANGUAGE plpgsql;', inicio_funcion)
                    if fin_funcion != -1:
                        fin_funcion = fin_funcion + len('$$ LANGUAGE plpgsql;')
                        funcion_sql = contenido[inicio_funcion:fin_funcion]
                        cur.execute(funcion_sql)
                        conn.commit()
                        print("[OK] Función creada exitosamente")
                    else:
                        print("[ERROR] No se pudo encontrar el final de la función en el schema")
                        sys.exit(1)
                else:
                    print("[ERROR] No se encontró la función en schema_presupuestos.sql")
                    print("       Ejecuta primero: python ejecutar_esquema.py")
                    sys.exit(1)
            except FileNotFoundError:
                print("[ERROR] No se encontró el archivo schema_presupuestos.sql")
                print("       Ejecuta primero: python ejecutar_esquema.py")
                sys.exit(1)
            except Exception as e:
                print(f"[ERROR] Error al crear la función: {e}")
                conn.rollback()
                sys.exit(1)
        else:
            print("[OK] La función existe en la base de datos")
        
        cur.close()
        return True
    except Exception as e:
        print(f"[ERROR] Error al verificar la función: {e}")
        cur.close()
        return False

def eliminar_duplicados():
    """Ejecuta la función para eliminar duplicados"""
    print("=" * 60)
    print("ELIMINAR DUPLICADOS DE MATERIALES GENÉRICOS")
    print("=" * 60)
    
    # Conectar a la base de datos
    print("\nConectando a la base de datos...")
    conn = obtener_conexion()
    conn.autocommit = False
    
    try:
        cur = conn.cursor()
        
        # Verificar que la función existe
        print("\nVerificando función...")
        if not verificar_funcion_existe(conn):
            sys.exit(1)
        
        # Contar materiales antes
        cur.execute("SELECT COUNT(*) FROM materiales_genericos")
        total_antes = cur.fetchone()[0]
        print(f"\n[INFO] Total de materiales antes: {total_antes}")
        
        # Contar duplicados
        cur.execute("""
            SELECT COUNT(*) - COUNT(DISTINCT UPPER(TRIM(descripcion)))
            FROM materiales_genericos
        """)
        duplicados_estimados = cur.fetchone()[0]
        print(f"[INFO] Materiales duplicados estimados: {duplicados_estimados}")
        
        if duplicados_estimados == 0:
            print("\n[OK] No hay duplicados en la base de datos.")
            conn.commit()
            return
        
        # Pedir confirmación
        print("\n¿Deseas continuar con la eliminación de duplicados?")
        respuesta = input("Escribe 'SI' para confirmar: ").strip().upper()
        
        if respuesta != 'SI':
            print("\n[INFO] Operación cancelada por el usuario.")
            conn.rollback()
            return
        
        # Ejecutar la función
        print("\nEjecutando función de eliminación...")
        cur.execute("SELECT * FROM eliminar_duplicados_materiales_genericos()")
        resultado = cur.fetchone()
        
        eliminados = resultado[0]
        mensaje = resultado[1]
        
        # Confirmar transacción
        conn.commit()
        
        # Contar materiales después
        cur.execute("SELECT COUNT(*) FROM materiales_genericos")
        total_despues = cur.fetchone()[0]
        
        print("\n" + "=" * 60)
        print("RESULTADO")
        print("=" * 60)
        print(mensaje)
        print(f"[INFO] Total de materiales antes: {total_antes}")
        print(f"[INFO] Total de materiales después: {total_despues}")
        print(f"[INFO] Materiales eliminados: {eliminados}")
        print("=" * 60)
        
        print("\n[OK] ¡DUPLICADOS ELIMINADOS EXITOSAMENTE!")
        
        cur.close()
        
    except Exception as e:
        print(f"\n[ERROR] Error durante la ejecución: {e}")
        import traceback
        traceback.print_exc()
        conn.rollback()
        sys.exit(1)
    finally:
        conn.close()
        print("\nConexión cerrada.")

if __name__ == "__main__":
    eliminar_duplicados()

