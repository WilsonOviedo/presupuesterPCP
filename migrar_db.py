#!/usr/bin/env python3
"""
Script para migrar datos de la base de datos local a la base de datos del servidor.
Usa las mismas credenciales del .env, solo cambia el host:
- Local: localhost
- Servidor: pcp-server.local
"""

import os
import sys
from dotenv import load_dotenv
import psycopg2
import psycopg2.extras
from datetime import datetime

# Cargar variables de entorno
load_dotenv()

# Configuración de conexiones
DB_CONFIG = {
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "port": os.getenv("DB_PORT", "5432"),
}

DB_LOCAL = {**DB_CONFIG, "host": "localhost"}
DB_SERVER = {**DB_CONFIG, "host": "pcp-server.local"}

def conectar_local():
    """Conecta a la base de datos local"""
    try:
        conn = psycopg2.connect(**DB_LOCAL)
        return conn
    except Exception as e:
        print(f"[ERROR] No se pudo conectar a la base de datos local: {e}")
        sys.exit(1)

def conectar_server():
    """Conecta a la base de datos del servidor"""
    try:
        conn = psycopg2.connect(**DB_SERVER)
        return conn
    except Exception as e:
        print(f"[ERROR] No se pudo conectar a la base de datos del servidor: {e}")
        sys.exit(1)

def obtener_tablas(conn):
    """Obtiene la lista de todas las tablas en la base de datos"""
    cur = conn.cursor()
    cur.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_type = 'BASE TABLE'
        ORDER BY table_name
    """)
    tablas = [row[0] for row in cur.fetchall()]
    cur.close()
    return tablas

def obtener_columnas(conn, tabla):
    """Obtiene las columnas de una tabla"""
    cur = conn.cursor()
    cur.execute("""
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'public' 
        AND table_name = %s
        ORDER BY ordinal_position
    """, (tabla,))
    columnas = cur.fetchall()
    cur.close()
    return columnas

def obtener_primary_key(conn, tabla):
    """Obtiene la columna de clave primaria de una tabla"""
    cur = conn.cursor()
    cur.execute("""
        SELECT a.attname
        FROM pg_index i
        JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
        WHERE i.indrelid = %s::regclass
        AND i.indisprimary
    """, (tabla,))
    result = cur.fetchone()
    cur.close()
    if result:
        return result[0]
    return None

def contar_registros(conn, tabla):
    """Cuenta los registros en una tabla"""
    cur = conn.cursor()
    cur.execute(f"SELECT COUNT(*) FROM {tabla}")
    count = cur.fetchone()[0]
    cur.close()
    return count

def migrar_tabla(conn_local, conn_server, tabla, modo='insert'):
    """
    Migra los datos de una tabla de local a servidor
    
    Args:
        conn_local: Conexión a la base de datos local
        conn_server: Conexión a la base de datos del servidor
        tabla: Nombre de la tabla
        modo: 'insert' (INSERT con ON CONFLICT) o 'truncate' (TRUNCATE e INSERT)
    """
    print(f"\n{'='*60}")
    print(f"Migrando tabla: {tabla}")
    print(f"{'='*60}")
    
    # Verificar que la tabla existe en ambas bases de datos
    cur_local = conn_local.cursor()
    cur_server = conn_server.cursor()
    
    # Contar registros en local
    try:
        count_local = contar_registros(conn_local, tabla)
        print(f"   Registros en local: {count_local}")
    except Exception as e:
        print(f"   [ERROR] No se pudo contar registros en local: {e}")
        cur_local.close()
        cur_server.close()
        return False
    
    if count_local == 0:
        print(f"   [INFO] La tabla está vacía, se omite")
        cur_local.close()
        cur_server.close()
        return True
    
    # Contar registros en servidor antes de migrar
    try:
        count_server_antes = contar_registros(conn_server, tabla)
        print(f"   Registros en servidor (antes): {count_server_antes}")
    except Exception as e:
        print(f"   [WARN] No se pudo contar registros en servidor: {e}")
        count_server_antes = 0
    
    # Obtener columnas
    try:
        columnas = obtener_columnas(conn_local, tabla)
        nombres_columnas = [col[0] for col in columnas]
        print(f"   Columnas: {', '.join(nombres_columnas)}")
    except Exception as e:
        print(f"   [ERROR] No se pudo obtener columnas: {e}")
        cur_local.close()
        cur_server.close()
        return False
    
    # Obtener clave primaria
    pk = obtener_primary_key(conn_local, tabla)
    if pk:
        print(f"   Clave primaria: {pk}")
    
    # Leer datos de local
    try:
        cur_local.execute(f"SELECT * FROM {tabla} ORDER BY {pk if pk else nombres_columnas[0]}")
        datos = cur_local.fetchall()
        print(f"   Datos leídos: {len(datos)} registros")
    except Exception as e:
        print(f"   [ERROR] No se pudo leer datos de local: {e}")
        cur_local.close()
        cur_server.close()
        return False
    
    # Preparar query de inserción
    columnas_str = ', '.join(nombres_columnas)
    placeholders = ', '.join(['%s'] * len(nombres_columnas))
    
    # Si hay clave primaria, usar ON CONFLICT
    if pk and modo == 'insert':
        conflict_clause = f"ON CONFLICT ({pk}) DO NOTHING"
    else:
        conflict_clause = ""
    
    insert_query = f"""
        INSERT INTO {tabla} ({columnas_str})
        VALUES ({placeholders})
        {conflict_clause}
    """
    
    # Si modo es truncate, limpiar primero
    if modo == 'truncate':
        try:
            cur_server.execute(f"TRUNCATE TABLE {tabla} CASCADE")
            conn_server.commit()
            print(f"   [INFO] Tabla truncada en servidor")
        except Exception as e:
            print(f"   [WARN] No se pudo truncar tabla: {e}")
    
    # Insertar datos
    registros_insertados = 0
    registros_omitidos = 0
    errores = []
    
    try:
        for i, fila in enumerate(datos, 1):
            try:
                cur_server.execute(insert_query, fila)
                if cur_server.rowcount > 0:
                    registros_insertados += 1
                else:
                    registros_omitidos += 1
                
                # Mostrar progreso cada 100 registros
                if i % 100 == 0:
                    print(f"   Progreso: {i}/{len(datos)} registros procesados...")
                    
            except psycopg2.IntegrityError as e:
                registros_omitidos += 1
                if len(errores) < 5:  # Guardar solo los primeros 5 errores
                    errores.append(str(e))
            except Exception as e:
                errores.append(f"Registro {i}: {str(e)}")
                if len(errores) >= 10:  # Limitar errores mostrados
                    break
        
        conn_server.commit()
        
        # Contar registros en servidor después de migrar
        count_server_despues = contar_registros(conn_server, tabla)
        
        print(f"\n   [OK] Migración completada:")
        print(f"      - Registros insertados: {registros_insertados}")
        print(f"      - Registros omitidos (duplicados): {registros_omitidos}")
        print(f"      - Registros en servidor (después): {count_server_despues}")
        
        if errores:
            print(f"\n   [WARN] Errores encontrados ({len(errores)}):")
            for error in errores[:5]:
                print(f"      - {error}")
        
        cur_local.close()
        cur_server.close()
        return True
        
    except Exception as e:
        conn_server.rollback()
        print(f"   [ERROR] Error durante la migración: {e}")
        import traceback
        traceback.print_exc()
        cur_local.close()
        cur_server.close()
        return False

def main():
    """Función principal"""
    print("="*60)
    print("MIGRACIÓN DE BASE DE DATOS")
    print("Local -> Servidor")
    print("="*60)
    print(f"\nConfiguración:")
    print(f"   Base de datos: {DB_CONFIG['dbname']}")
    print(f"   Usuario: {DB_CONFIG['user']}")
    print(f"   Puerto: {DB_CONFIG['port']}")
    print(f"   Local: localhost")
    print(f"   Servidor: pcp-server.local")
    
    # Conectar a ambas bases de datos
    print("\n" + "="*60)
    print("Conectando a las bases de datos...")
    print("="*60)
    
    conn_local = conectar_local()
    print("[OK] Conectado a base de datos local")
    
    conn_server = conectar_server()
    print("[OK] Conectado a base de datos del servidor")
    
    # Obtener lista de tablas
    print("\n" + "="*60)
    print("Obteniendo lista de tablas...")
    print("="*60)
    
    tablas = obtener_tablas(conn_local)
    print(f"[OK] Se encontraron {len(tablas)} tablas:")
    for tabla in tablas:
        count = contar_registros(conn_local, tabla)
        print(f"   - {tabla}: {count} registros")
    
    # Preguntar qué tablas migrar
    print("\n" + "="*60)
    print("Opciones de migración:")
    print("="*60)
    print("1. Migrar todas las tablas (con ON CONFLICT)")
    print("2. Migrar todas las tablas (TRUNCATE primero)")
    print("3. Seleccionar tablas específicas")
    print("4. Cancelar")
    
    opcion = input("\nSelecciona una opción (1-4): ").strip()
    
    tablas_a_migrar = []
    modo = 'insert'
    
    if opcion == '1':
        tablas_a_migrar = tablas
        modo = 'insert'
    elif opcion == '2':
        tablas_a_migrar = tablas
        modo = 'truncate'
        confirmar = input("\n⚠️  ADVERTENCIA: Esto eliminará todos los datos en el servidor. ¿Continuar? (s/N): ").strip().lower()
        if confirmar != 's':
            print("Migración cancelada.")
            conn_local.close()
            conn_server.close()
            return
    elif opcion == '3':
        print("\nTablas disponibles:")
        for i, tabla in enumerate(tablas, 1):
            count = contar_registros(conn_local, tabla)
            print(f"   {i}. {tabla} ({count} registros)")
        
        seleccion = input("\nIngresa los números de las tablas separados por comas (ej: 1,3,5): ").strip()
        try:
            indices = [int(x.strip()) - 1 for x in seleccion.split(',')]
            tablas_a_migrar = [tablas[i] for i in indices if 0 <= i < len(tablas)]
        except:
            print("[ERROR] Selección inválida")
            conn_local.close()
            conn_server.close()
            return
    else:
        print("Migración cancelada.")
        conn_local.close()
        conn_server.close()
        return
    
    if not tablas_a_migrar:
        print("[ERROR] No se seleccionaron tablas para migrar")
        conn_local.close()
        conn_server.close()
        return
    
    # Confirmar migración
    print("\n" + "="*60)
    print("RESUMEN DE MIGRACIÓN")
    print("="*60)
    print(f"Modo: {modo}")
    print(f"Tablas a migrar: {len(tablas_a_migrar)}")
    for tabla in tablas_a_migrar:
        count = contar_registros(conn_local, tabla)
        print(f"   - {tabla}: {count} registros")
    
    confirmar = input("\n¿Continuar con la migración? (s/N): ").strip().lower()
    if confirmar != 's':
        print("Migración cancelada.")
        conn_local.close()
        conn_server.close()
        return
    
    # Migrar tablas
    print("\n" + "="*60)
    print("INICIANDO MIGRACIÓN")
    print("="*60)
    
    inicio = datetime.now()
    tablas_exitosas = 0
    tablas_fallidas = 0
    
    for tabla in tablas_a_migrar:
        if migrar_tabla(conn_local, conn_server, tabla, modo):
            tablas_exitosas += 1
        else:
            tablas_fallidas += 1
    
    fin = datetime.now()
    duracion = (fin - inicio).total_seconds()
    
    # Resumen final
    print("\n" + "="*60)
    print("RESUMEN FINAL")
    print("="*60)
    print(f"Tablas migradas exitosamente: {tablas_exitosas}")
    print(f"Tablas con errores: {tablas_fallidas}")
    print(f"Tiempo total: {duracion:.2f} segundos")
    print("="*60)
    
    # Cerrar conexiones
    conn_local.close()
    conn_server.close()
    print("\n[OK] Conexiones cerradas.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[INFO] Migración cancelada por el usuario.")
        sys.exit(0)
    except Exception as e:
        print(f"\n[ERROR] Error fatal: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

