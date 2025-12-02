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
import psycopg2

# En Docker, las variables de entorno vienen de docker-compose.yml/env_file
# Docker Compose lee el .env del host y lo inyecta como variables de entorno
# Intentar cargar .env si existe (para desarrollo local), pero las variables
# de entorno del sistema (de Docker) tienen prioridad
try:
    from dotenv import load_dotenv
    # Cargar .env solo si existe, pero no sobrescribir variables ya existentes
    # (override=False significa que las variables de entorno del sistema tienen prioridad)
    if os.path.exists('/app/.env'):
        load_dotenv('/app/.env', override=False)
    elif os.path.exists('.env'):
        load_dotenv('.env', override=False)
except ImportError:
    pass  # dotenv no es crítico si las variables vienen del sistema
except Exception:
    pass  # Si hay error cargando .env, continuar con variables del sistema

# Debug: mostrar qué variables están disponibles (sin mostrar valores sensibles)
if os.getenv('DEBUG_DB_INIT'):
    print("[DEBUG] Variables de entorno detectadas:")
    for var in ['DB_NAME', 'DB_USER', 'DB_HOST', 'DB_PORT']:
        val = os.getenv(var)
        print(f"   {var}: {val if val else 'NO CONFIGURADA'}")
    db_pass = os.getenv('DB_PASSWORD')
    print(f"   DB_PASSWORD: {'*' * len(db_pass) if db_pass else 'NO CONFIGURADA'}")

def verificar_variables_env():
    """Verifica que las variables de entorno necesarias estén configuradas"""
    variables_requeridas = ['DB_NAME', 'DB_USER', 'DB_PASSWORD', 'DB_HOST', 'DB_PORT']
    faltantes = []
    valores = {}
    
    # Debug: mostrar todas las variables de entorno relacionadas con DB
    debug_mode = os.getenv('DEBUG_DB_INIT', '').lower() in ('1', 'true', 'yes')
    if debug_mode:
        print("[DEBUG] Variables de entorno detectadas:")
        for key, value in os.environ.items():
            if 'DB' in key or 'POSTGRES' in key:
                if 'PASSWORD' in key:
                    print(f"   {key}: {'*' * len(value) if value else 'NO CONFIGURADA'}")
                else:
                    print(f"   {key}: {value if value else 'NO CONFIGURADA'}")
        print("")
    
    for var in variables_requeridas:
        valor = os.getenv(var)
        valores[var] = valor
        if not valor:
            faltantes.append(var)
    
    if faltantes:
        print(f"[ERROR] Variables de entorno faltantes: {', '.join(faltantes)}")
        print("[ERROR] Por favor, configura estas variables en:")
        print("   1. El archivo .env en la raíz del proyecto (Docker Compose lo leerá)")
        print("   2. O directamente en docker-compose.yml en la sección 'environment'")
        print("\nVariables encontradas:")
        for var in variables_requeridas:
            if var not in faltantes:
                # Ocultar valores sensibles
                if 'PASSWORD' in var:
                    print(f"   {var}: {'*' * len(valores[var])}")
                else:
                    print(f"   {var}: {valores[var]}")
        print("\n[INFO] En Docker, el archivo .env del host se lee automáticamente")
        print("       por docker-compose.yml mediante 'env_file: - .env'")
        sys.exit(1)
    
    print("[OK] Variables de entorno verificadas")
    # Mostrar valores (ocultando contraseña)
    print("   Configuración de base de datos:")
    print(f"   - DB_NAME: {valores['DB_NAME']}")
    print(f"   - DB_USER: {valores['DB_USER']}")
    print(f"   - DB_HOST: {valores['DB_HOST']}")
    print(f"   - DB_PORT: {valores['DB_PORT']}")
    print(f"   - DB_PASSWORD: {'*' * len(valores['DB_PASSWORD']) if valores['DB_PASSWORD'] else 'NO CONFIGURADA'}")

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

