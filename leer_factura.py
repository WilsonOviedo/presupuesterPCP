import imaplib
import email
import xml.etree.ElementTree as ET
import psycopg2
from io import BytesIO
from dotenv import load_dotenv
import os
import hashlib
from datetime import datetime

# Cargar variables del .env
load_dotenv()

# Configuración IMAP
IMAP_SERVER = os.getenv("IMAP_SERVER")
IMAP_USER = os.getenv("IMAP_USER")
IMAP_PASS = os.getenv("IMAP_PASS")

# Configuración PostgreSQL
PG_CONN = {
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT"),
}

def conectar_postgres():
    conn = psycopg2.connect(**PG_CONN)
    cur = conn.cursor()

    # Tabla de precios
    cur.execute("""
        CREATE TABLE IF NOT EXISTS precios (
            id SERIAL PRIMARY KEY,
            proveedor TEXT,
            fecha TIMESTAMP,
            producto TEXT,
            precio NUMERIC,
            UNIQUE(proveedor, fecha, producto, precio)
        );
    """)

    # Tabla para facturas ya procesadas
    cur.execute("""
        CREATE TABLE IF NOT EXISTS facturas_procesadas (
            id SERIAL PRIMARY KEY,
            nombre_archivo TEXT,
            hash_md5 TEXT UNIQUE,
            fecha_procesado TIMESTAMP DEFAULT NOW()
        );
    """)

    conn.commit()
    return conn, cur


def calcular_hash(xml_bytes):
    """Devuelve un hash MD5 del contenido XML"""
    return hashlib.md5(xml_bytes).hexdigest()


def ya_procesado(cur, hash_md5):
    """Verifica si ya se procesó una factura con ese hash"""
    cur.execute("SELECT 1 FROM facturas_procesadas WHERE hash_md5 = %s;", (hash_md5,))
    return cur.fetchone() is not None


def registrar_factura(cur, filename, hash_md5):
    """Guarda registro de factura procesada"""
    cur.execute("""
        INSERT INTO facturas_procesadas (nombre_archivo, hash_md5, fecha_procesado)
        VALUES (%s, %s, %s)
        ON CONFLICT DO NOTHING;
    """, (filename, hash_md5, datetime.now()))


def extraer_datos_xml(xml_bytes):
    """Devuelve lista de tuplas (proveedor, fecha, producto, precio)"""
    datos = []
    tree = ET.parse(BytesIO(xml_bytes))
    root = tree.getroot()

    proveedor = root.findtext(".//{*}dNomEmi") or "Desconocido"
    fecha = root.findtext(".//{*}dFecFirma")

    for item in root.findall(".//{*}gCamItem"):
        producto = item.findtext(".//{*}dDesProSer")
        precio = item.findtext(".//{*}dPUniProSer")
        if producto and precio:
            try:
                datos.append((proveedor.strip(), fecha.strip(), producto.strip(), float(precio)))
            except ValueError:
                pass
    return datos


def obtener_ultima_fecha(cur):
    """Obtiene la última fecha procesada de una factura"""
    cur.execute("SELECT MAX(fecha_procesado) FROM facturas_procesadas;")
    res = cur.fetchone()
    return res[0] if res and res[0] else None


def procesar_correos():
    print("📬 Conectando al servidor IMAP...")
    mail = imaplib.IMAP4_SSL(IMAP_SERVER)
    mail.login(IMAP_USER, IMAP_PASS)
    mail.select("INBOX")

    conn, cur = conectar_postgres()
    ultima_fecha = obtener_ultima_fecha(cur)
    print(f"🕒 Última fecha procesada: {ultima_fecha}")

    # Buscar solo correos desde la última fecha procesada
    if ultima_fecha:
        # Formato IMAP: DD-MMM-YYYY (ejemplo: 12-Oct-2025)
        fecha_busqueda = ultima_fecha.strftime("%d-%b-%Y")
        result, data = mail.search(None, f'SINCE {fecha_busqueda}')
    else:
        result, data = mail.search(None, 'ALL')

    correos = data[0].split()

    for num in correos:
        result, data = mail.fetch(num, "(RFC822)")
        raw_email = data[0][1]
        msg = email.message_from_bytes(raw_email)

        # Obtener fecha del correo
        fecha_email = msg.get("Date")
        fecha_email_dt = None
        try:
            fecha_email_dt = datetime.strptime(fecha_email[:31], "%a, %d %b %Y %H:%M:%S %z")
        except Exception:
            pass

        # Si hay última fecha, saltar correos anteriores
        if ultima_fecha and fecha_email_dt and fecha_email_dt.replace(tzinfo=None) <= ultima_fecha:
            continue

        for part in msg.walk():
            filename = part.get_filename()
            content_type = part.get_content_type()

            if not filename:
                continue

            if filename.lower().endswith(".xml") or content_type == "application/xml":
                xml_bytes = part.get_payload(decode=True)
                if not xml_bytes or len(xml_bytes) < 50:
                    print(f"⚠️  Archivo vacío o no válido: {filename}")
                    continue

                hash_md5 = calcular_hash(xml_bytes)

                # 🔒 Verificamos si ya se procesó
                if ya_procesado(cur, hash_md5):
                    print(f"⏩ Ya procesado anteriormente: {filename}")
                    continue

                try:
                    datos = extraer_datos_xml(xml_bytes)
                    if not datos:
                        print(f"⚠️  No se encontraron productos en: {filename}")
                        continue

                    for fila in datos:
                        cur.execute("""
                            INSERT INTO precios (proveedor, fecha, producto, precio)
                            VALUES (%s, %s, %s, %s)
                            ON CONFLICT DO NOTHING;
                        """, fila)

                    registrar_factura(cur, filename, hash_md5)
                    conn.commit()
                    print(f"✅ Factura procesada y registrada: {filename}")

                except ET.ParseError:
                    print(f"❌ Error al parsear {filename}: no es un XML válido.")
                except Exception as e:
                    print(f"❌ Error procesando {filename}: {e}")

    cur.close()
    conn.close()
    print("✅ Proceso finalizado. Todas las facturas nuevas fueron cargadas correctamente.")


if __name__ == "__main__":
    procesar_correos()
