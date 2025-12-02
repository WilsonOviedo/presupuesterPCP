#!/usr/bin/env python3
"""
Script de inicialización de base de datos para Docker.
Se ejecuta automáticamente al iniciar el contenedor.
Ejecuta ejecutar_esquema.py para aplicar el esquema SQL.
"""

import os
import sys
import time
import subprocess
from dotenv import load_dotenv
import psycopg2

# Cargar variables de entorno
load_dotenv()

def verificar_variables_env():
    """Verifica que las variables de entorno necesarias estén configuradas"""
    variables_requeridas = ['DB_NAME', 'DB_USER', 'DB_PASSWORD', 'DB_HOST', 'DB_PORT']
    faltantes = []
    
    for var in variables_requeridas:
        valor = os.getenv(var)
        if not valor:
            faltantes.append(var)
    
    if faltantes:
        print(f"[ERROR] Variables de entorno faltantes: {', '.join(faltantes)}")
        print("[ERROR] Por favor, configura estas variables en el archivo .env")
        sys.exit(1)
    
    print("[OK] Variables de entorno verificadas")

def esperar_postgresql(max_retries=30, retry_delay=2):
    """Espera a que PostgreSQL esté listo para aceptar conexiones"""
    db_name = os.getenv("DB_NAME")
    db_user = os.getenv("DB_USER")
    db_password = os.getenv("DB_PASSWORD")
    db_host = os.getenv("DB_HOST")
    db_port = os.getenv("DB_PORT")
    
    for intento in range(max_retries):
        try:
            conn = psycopg2.connect(
                dbname=db_name,
                user=db_user,
                password=db_password,
                host=db_host,
                port=db_port,
            )
            conn.close()
            print(f"[OK] PostgreSQL está listo (intento {intento + 1})")
            return True
        except psycopg2.OperationalError as e:
            if intento < max_retries - 1:
                print(f"[INFO] Esperando a que PostgreSQL esté listo... (intento {intento + 1}/{max_retries})")
                time.sleep(retry_delay)
            else:
                print(f"[ERROR] No se pudo conectar a PostgreSQL después de {max_retries} intentos: {e}")
                return False
        except Exception as e:
            print(f"[ERROR] Error inesperado al conectar: {e}")
            return False
    
    return False

def ejecutar_esquema():
    """Ejecuta el script ejecutar_esquema.py"""
    print("=" * 60)
    print("Ejecutando esquema SQL...")
    print("=" * 60)
    
    # Verificar que el archivo existe
    script_path = "/app/ejecutar_esquema.py"
    if not os.path.exists(script_path):
        print(f"[WARNING] Archivo {script_path} no encontrado, omitiendo ejecución de esquema")
        return True
    
    try:
        # Ejecutar el script ejecutar_esquema.py
        # Pasar el archivo SQL como argumento si existe
        archivo_sql = "/app/schema_presupuestos.sql"
        if os.path.exists(archivo_sql):
            resultado = subprocess.run(
                [sys.executable, script_path, archivo_sql],
                cwd="/app",
                capture_output=False,
                text=True
            )
        else:
            # Si no existe el archivo SQL, ejecutar sin argumentos
            resultado = subprocess.run(
                [sys.executable, script_path],
                cwd="/app",
                capture_output=False,
                text=True
            )
        
        if resultado.returncode == 0:
            print("[OK] Esquema SQL ejecutado correctamente")
            return True
        else:
            print(f"[WARNING] El script ejecutar_esquema.py terminó con código {resultado.returncode}")
            return False
            
    except FileNotFoundError:
        print(f"[WARNING] No se encontró el script ejecutar_esquema.py")
        return True  # No es crítico, continuar
    except Exception as e:
        print(f"[ERROR] Error al ejecutar esquema SQL: {e}")
        return False

def main():
    """Función principal de inicialización"""
    print("=" * 60)
    print("Inicializando base de datos...")
    print("=" * 60)
    
    # Verificar variables de entorno
    verificar_variables_env()
    
    # Esperar a que PostgreSQL esté listo
    if not esperar_postgresql():
        print("[ERROR] No se pudo conectar a PostgreSQL. Abortando inicialización.")
        sys.exit(1)
    
    # Ejecutar el esquema SQL usando ejecutar_esquema.py
    if not ejecutar_esquema():
        print("[WARNING] Hubo problemas al ejecutar el esquema SQL, pero continuando...")
    
    print("=" * 60)
    print("[OK] Inicialización de base de datos completada")
    print("=" * 60)

if __name__ == "__main__":
    main()

