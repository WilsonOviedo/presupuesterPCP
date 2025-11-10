#!/usr/bin/env python3
"""
Script para ejecutar el esquema SQL de presupuestos en PostgreSQL.
Uso: python ejecutar_esquema.py
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
        print(f"❌ Error al conectar a la base de datos: {e}")
        sys.exit(1)

def leer_archivo_sql(archivo="schema_presupuestos.sql"):
    """Lee el archivo SQL y lo divide en comandos"""
    try:
        with open(archivo, 'r', encoding='utf-8') as f:
            contenido = f.read()
        return contenido
    except FileNotFoundError:
        print(f"❌ Error: No se encontró el archivo {archivo}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error al leer el archivo SQL: {e}")
        sys.exit(1)

def dividir_comandos_sql(sql_content):
    """Divide el SQL en comandos individuales, manejando funciones con bloques $$"""
    comandos = []
    comando_actual = []
    en_bloque_dollar = False
    
    lineas = sql_content.split('\n')
    
    for linea in lineas:
        linea_strip = linea.strip()
        linea_upper = linea_strip.upper()
        
        # Agregar línea al comando actual
        comando_actual.append(linea)
        
        # Detectar inicio de bloque $$ (AS $$)
        if not en_bloque_dollar and 'AS $$' in linea_upper:
            en_bloque_dollar = True
        
        # Detectar fin de bloque $$ ($$ LANGUAGE)
        elif en_bloque_dollar and '$$' in linea and 'LANGUAGE' in linea_upper:
            # Es el cierre del bloque
            comando = '\n'.join(comando_actual).strip()
            if comando:
                comandos.append(comando)
            comando_actual = []
            en_bloque_dollar = False
        
        # Si no estamos en bloque $$, buscar punto y coma al final
        elif not en_bloque_dollar and linea_strip.endswith(';'):
            # Verificar que no estemos dentro de paréntesis anidados
            texto_actual = '\n'.join(comando_actual)
            nivel_parentesis = texto_actual.count('(') - texto_actual.count(')')
            
            if nivel_parentesis == 0:
                # Estamos en nivel 0, es el fin del comando
                comando = '\n'.join(comando_actual).strip()
                if comando and comando != ';':
                    comandos.append(comando)
                comando_actual = []
    
    # Agregar último comando si queda
    if comando_actual:
        comando = '\n'.join(comando_actual).strip()
        if comando and comando != ';':
            comandos.append(comando)
    
    # Filtrar comandos vacíos
    return [c for c in comandos if c.strip() and c.strip() != ';']

def ejecutar_esquema(archivo_sql="schema_presupuestos.sql"):
    """Ejecuta el esquema SQL en la base de datos"""
    print("=" * 60)
    print("EJECUTANDO ESQUEMA SQL DE PRESUPUESTOS")
    print("=" * 60)
    
    # Leer archivo SQL
    print(f"\n📖 Leyendo archivo: {archivo_sql}")
    sql_content = leer_archivo_sql(archivo_sql)
    
    # Conectar a la base de datos
    print("🔌 Conectando a la base de datos...")
    conn = obtener_conexion()
    conn.autocommit = True  # Usar autocommit para permitir DDL
    
    try:
        cur = conn.cursor()
        
        print("\n🔍 Dividiendo comandos SQL...")
        comandos = dividir_comandos_sql(sql_content)
        print(f"   Se encontraron {len(comandos)} comandos SQL")
        
        print("\n🚀 Ejecutando comandos SQL...\n")
        
        comandos_exitosos = 0
        comandos_fallidos = 0
        errores = []
        
        for i, comando in enumerate(comandos, 1):
            comando_limpio = comando.strip()
            if not comando_limpio:
                continue
            
            # Identificar tipo de comando
            tipo = "Comando"
            nombre = ""
            if 'CREATE TABLE' in comando_limpio.upper():
                tipo = "Tabla"
                # Extraer nombre de tabla
                partes = comando_limpio.split()
                try:
                    if 'IF NOT EXISTS' in comando_limpio.upper():
                        idx = [p.upper() for p in partes].index('EXISTS') + 1
                    else:
                        idx = [p.upper() for p in partes].index('TABLE') + 1
                    if idx < len(partes):
                        nombre = partes[idx].split('(')[0]
                except:
                    pass
            elif 'CREATE INDEX' in comando_limpio.upper():
                tipo = "Índice"
            elif 'CREATE VIEW' in comando_limpio.upper() or 'CREATE OR REPLACE VIEW' in comando_limpio.upper():
                tipo = "Vista"
                try:
                    partes = comando_limpio.split()
                    if 'OR REPLACE' in comando_limpio.upper():
                        idx = [p.upper() for p in partes].index('VIEW') + 1
                    else:
                        idx = [p.upper() for p in partes].index('VIEW') + 1
                    if idx < len(partes):
                        nombre = partes[idx].split('AS')[0].strip()
                except:
                    pass
            elif 'CREATE FUNCTION' in comando_limpio.upper() or 'CREATE OR REPLACE FUNCTION' in comando_limpio.upper():
                tipo = "Función"
                try:
                    partes = comando_limpio.split()
                    if 'OR REPLACE' in comando_limpio.upper():
                        idx = [p.upper() for p in partes].index('FUNCTION') + 1
                    else:
                        idx = [p.upper() for p in partes].index('FUNCTION') + 1
                    if idx < len(partes):
                        nombre = partes[idx].split('(')[0]
                except:
                    pass
            elif 'CREATE TRIGGER' in comando_limpio.upper():
                tipo = "Trigger"
            
            try:
                cur.execute(comando_limpio)
                comandos_exitosos += 1
                mensaje = f"✅ [{i}/{len(comandos)}] {tipo}"
                if nombre:
                    mensaje += f": {nombre}"
                print(mensaje)
            except psycopg2.errors.DuplicateTable:
                comandos_exitosos += 1
                mensaje = f"⚠️  [{i}/{len(comandos)}] {tipo}"
                if nombre:
                    mensaje += f": {nombre}"
                mensaje += " - Ya existe (se omite)"
                print(mensaje)
            except psycopg2.errors.DuplicateObject:
                comandos_exitosos += 1
                mensaje = f"⚠️  [{i}/{len(comandos)}] {tipo}"
                if nombre:
                    mensaje += f": {nombre}"
                mensaje += " - Ya existe (se omite)"
                print(mensaje)
            except Exception as e:
                comandos_fallidos += 1
                mensaje = f"❌ [{i}/{len(comandos)}] {tipo}"
                if nombre:
                    mensaje += f": {nombre}"
                mensaje += f" - ERROR: {str(e)}"
                print(mensaje)
                errores.append((i, tipo, nombre, str(e)))
                # Mostrar primeras líneas del comando problemático
                lineas_comando = comando_limpio.split('\n')[:2]
                for linea in lineas_comando:
                    if linea.strip():
                        print(f"   → {linea[:100]}")
        
        print("\n" + "=" * 60)
        print("RESUMEN")
        print("=" * 60)
        print(f"✅ Comandos exitosos: {comandos_exitosos}")
        if comandos_fallidos > 0:
            print(f"❌ Comandos fallidos: {comandos_fallidos}")
        print("=" * 60)
        
        # Verificar objetos creados
        if comandos_fallidos == 0 or comandos_exitosos > 0:
            print("\n📊 Verificando objetos creados...")
            
            # Verificar tablas
            cur.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name IN ('clientes', 'items', 'materiales', 'presupuestos', 'presupuesto_subgrupos', 'presupuesto_items')
                ORDER BY table_name
            """)
            tablas = cur.fetchall()
            
            if tablas:
                print("\n✅ Tablas encontradas:")
                for tabla in tablas:
                    print(f"   - {tabla[0]}")
            
            # Verificar vistas
            cur.execute("""
                SELECT table_name 
                FROM information_schema.views 
                WHERE table_schema = 'public' 
                AND table_name = 'vista_presupuestos_totales'
            """)
            vistas = cur.fetchall()
            
            if vistas:
                print("\n✅ Vistas encontradas:")
                for vista in vistas:
                    print(f"   - {vista[0]}")
            
            # Verificar funciones
            cur.execute("""
                SELECT routine_name 
                FROM information_schema.routines 
                WHERE routine_schema = 'public' 
                AND routine_type = 'FUNCTION'
                AND routine_name IN ('generar_numero_presupuesto', 'actualizar_timestamp')
            """)
            funciones = cur.fetchall()
            
            if funciones:
                print("\n✅ Funciones encontradas:")
                for funcion in funciones:
                    print(f"   - {funcion[0]}")
        
        if comandos_fallidos == 0:
            print("\n🎉 ¡ESQUEMA SQL EJECUTADO CORRECTAMENTE!")
        elif comandos_exitosos > 0:
            print(f"\n⚠️  Se ejecutaron {comandos_exitosos} comandos pero {comandos_fallidos} fallaron.")
            print("   Algunos objetos pueden haberse creado correctamente.")
        else:
            print(f"\n❌ Todos los comandos fallaron. Revisa los errores arriba.")
            sys.exit(1)
        
    except Exception as e:
        print(f"\n❌ Error durante la ejecución: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        cur.close()
        conn.close()
        print("\n🔌 Conexión cerrada.")

if __name__ == "__main__":
    # Verificar que el archivo SQL existe
    archivo_sql = "schema_presupuestos.sql"
    if len(sys.argv) > 1:
        archivo_sql = sys.argv[1]
    
    if not os.path.exists(archivo_sql):
        print(f"❌ Error: No se encontró el archivo {archivo_sql}")
        print("   Uso: python ejecutar_esquema.py [archivo.sql]")
        sys.exit(1)
    
    ejecutar_esquema(archivo_sql)

