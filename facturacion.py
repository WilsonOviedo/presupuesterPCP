"""
Módulo de facturación
Maneja la creación de facturas, cálculo de totales y conversión de números a letras
"""
import psycopg2
import psycopg2.extras
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

PG_CONN = {
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT"),
}


def conectar():
    """Conecta a la base de datos"""
    conn = psycopg2.connect(**PG_CONN)
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    return conn, cur


def unidades(num):
    """Convierte unidades (1-9) a letras"""
    unidades_dict = {
        1: "UNO ",
        2: "DOS ",
        3: "TRES ",
        4: "CUATRO ",
        5: "CINCO ",
        6: "SEIS ",
        7: "SIETE ",
        8: "OCHO ",
        9: "NUEVE "
    }
    return unidades_dict.get(num, "")


def decenas(num):
    """Convierte decenas a letras"""
    decena = num // 10
    unidad = num - decena * 10
    
    if decena == 1:
        if unidad == 0:
            return "DIEZ "
        elif unidad == 1:
            return "ONCE "
        elif unidad == 2:
            return "DOCE "
        elif unidad == 3:
            return "TRECE "
        elif unidad == 4:
            return "CATORCE "
        elif unidad == 5:
            return "QUINCE "
        else:
            return "DIECI" + unidades(unidad)
    elif decena == 2:
        if unidad == 0:
            return "VEINTE "
        else:
            return "VEINTI" + unidades(unidad)
    elif decena == 3:
        return decenas_y("TREINTA", unidad)
    elif decena == 4:
        return decenas_y("CUARENTA", unidad)
    elif decena == 5:
        return decenas_y("CINCUENTA", unidad)
    elif decena == 6:
        return decenas_y("SESENTA", unidad)
    elif decena == 7:
        return decenas_y("SETENTA", unidad)
    elif decena == 8:
        return decenas_y("OCHENTA", unidad)
    elif decena == 9:
        return decenas_y("NOVENTA", unidad)
    else:
        return unidades(unidad)


def decenas_y(str_sin, num_unidades):
    """Formatea decenas con unidades"""
    if num_unidades > 0:
        return str_sin + " Y " + unidades(num_unidades)
    return str_sin


def centenas(num):
    """Convierte centenas a letras"""
    centenas_num = num // 100
    decenas_num = num - centenas_num * 100
    
    if centenas_num == 1:
        if decenas_num > 0:
            return "CIENTO " + decenas(decenas_num)
        return "CIEN "
    elif centenas_num == 2:
        return "DOSCIENTOS " + decenas(decenas_num)
    elif centenas_num == 3:
        return "TRESCIENTOS " + decenas(decenas_num)
    elif centenas_num == 4:
        return "CUATROCIENTOS " + decenas(decenas_num)
    elif centenas_num == 5:
        return "QUINIENTOS " + decenas(decenas_num)
    elif centenas_num == 6:
        return "SEISCIENTOS " + decenas(decenas_num)
    elif centenas_num == 7:
        return "SETECIENTOS " + decenas(decenas_num)
    elif centenas_num == 8:
        return "OCHOCIENTOS " + decenas(decenas_num)
    elif centenas_num == 9:
        return "NOVECIENTOS " + decenas(decenas_num)
    else:
        return decenas(decenas_num)


def seccion(num, divisor, str_singular, str_plural):
    """Convierte secciones (miles, millones)"""
    cientos = num // divisor
    resto = num - cientos * divisor
    letras = ""
    
    if cientos > 0:
        if cientos > 1:
            letras = centenas(cientos) + " " + str_plural
        else:
            letras = str_singular
    
    if resto > 0:
        letras += ""
    
    return letras


def miles(num):
    """Convierte miles a letras"""
    divisor = 1000
    cientos = num // divisor
    resto = num - cientos * divisor
    
    str_miles = seccion(num, divisor, "UN MIL", "MIL")
    str_centenas = centenas(resto)
    
    if str_miles == "":
        return str_centenas
    return str_miles + " " + str_centenas


def millones(num):
    """Convierte millones a letras"""
    divisor = 1000000
    cientos = num // divisor
    resto = num - cientos * divisor
    
    str_millones = seccion(num, divisor, "UN MILLÓN", "MILLONES")
    str_miles = miles(resto)
    
    if str_millones == "":
        return str_miles
    return str_millones + " " + str_miles


def numero_a_letras(num, centavos=True, moneda="Gs"):
    """Convierte un número a letras en español"""
    enteros = int(num)
    centavos_num = round((num - enteros) * 100)
    
    if moneda == "Gs":
        letras_moneda = "SON GUARANIES"
        letras_moneda_plural = "GUARANIES"
        letras_moneda_singular = "GUARANI"
    elif moneda == "USD":
        letras_moneda = "SON DOLARES AMERICANOS"
        letras_moneda_plural = "DOLARES AMERICANOS"
        letras_moneda_singular = "DOLAR AMERICANO"
    else:
        letras_moneda = ""
        letras_moneda_plural = ""
        letras_moneda_singular = ""
    
    letras_centavos = ""
    if centavos and centavos_num > 0:
        if moneda == "Gs":
            letras_centavos = "CON " + numero_a_letras(centavos_num, False, "")
        elif moneda == "USD":
            letras_centavos = f"CON {centavos_num}/100"
    
    if enteros == 0:
        resultado = "CERO " + letras_moneda_plural
        if letras_centavos:
            resultado += " " + letras_centavos
        return resultado
    elif enteros == 1:
        resultado = millones(enteros) + letras_moneda_singular
        if letras_centavos:
            resultado += " " + letras_centavos
        return resultado
    else:
        resultado = letras_moneda + " " + millones(enteros) + letras_moneda_plural
        if letras_centavos:
            resultado += " " + letras_centavos
        return resultado + " ---"


def calcular_totales(items):
    """Calcula los totales de una factura basado en los items"""
    excentas = 0
    iva5 = 0
    iva10 = 0
    
    if not items or not isinstance(items, list):
        return {
            'excentas': 0,
            'iva5': 0,
            'iva10': 0,
            'ivaTotal': 0,
            'total': 0,
            'iva5Total': 0,
            'iva10Total': 0,
            'enLetras': ''
        }
    
    for item in items:
        cantidad = float(item.get('cantidad', 0) or 0)
        precio_unitario = float(item.get('precio_unitario', 0) or 0)
        total_item = cantidad * precio_unitario
        impuesto = item.get('impuesto', 'exc')
        
        if impuesto == 'exc':
            excentas += total_item
        elif impuesto == '5':
            iva5 += total_item
        elif impuesto == '10':
            iva10 += total_item
    
    # Calcular IVA
    iva5_total = iva5 / 21  # IVA 5%: el total incluye IVA, entonces IVA = total / 21
    iva10_total = iva10 / 11  # IVA 10%: el total incluye IVA, entonces IVA = total / 11
    iva_total = iva5_total + iva10_total
    
    total = excentas + iva5 + iva10
    
    return {
        'excentas': round(excentas, 2),
        'iva5': round(iva5, 2),
        'iva10': round(iva10, 2),
        'ivaTotal': round(iva_total, 2),
        'total': round(total, 2),
        'iva5Total': round(iva5_total, 2),
        'iva10Total': round(iva10_total, 2),
        'enLetras': numero_a_letras(total, True, 'Gs')  # Se actualizará con la moneda correcta
    }


def crear_factura(fecha, cliente, ruc=None, direccion=None, nota_remision=None,
                  moneda='Gs', tipo_venta='Contado', plazo_dias=None, items=None):
    """Crea una nueva factura en la base de datos"""
    conn, cur = conectar()
    try:
        # Calcular totales
        totales = calcular_totales(items)
        totales['enLetras'] = numero_a_letras(totales['total'], True, moneda)
        
        # Generar número de factura
        año_actual = datetime.now().year
        año_str = str(año_actual)
        cur.execute("""
            SELECT COALESCE(MAX(
                CAST(SUBSTRING(numero_factura FROM '^FAC-' || %s || '-(\d+)$') AS INTEGER)
            ), 0) + 1 AS siguiente_numero
            FROM facturas
            WHERE numero_factura LIKE %s
        """, (año_str, f'FAC-{año_str}-%'))
        
        resultado = cur.fetchone()
        siguiente_numero = resultado['siguiente_numero'] if resultado else 1
        numero_factura = f"FAC-{año_actual}-{str(siguiente_numero).zfill(4)}"
        
        # Calcular fecha de vencimiento y fecha de pago
        fecha_vencimiento = None
        fecha_pago = None
        estado_pago = 'pendiente'
        
        if tipo_venta == 'Crédito' and plazo_dias:
            from datetime import timedelta
            fecha_vencimiento = fecha + timedelta(days=plazo_dias)
        elif tipo_venta == 'Contado':
            # Para contado, fecha de pago = fecha de emisión
            fecha_pago = fecha
            estado_pago = 'pagado'
        
        # Insertar factura
        cur.execute("""
            INSERT INTO facturas (
                numero_factura, fecha, cliente, ruc, direccion, nota_remision,
                moneda, tipo_venta, plazo_dias, fecha_vencimiento, fecha_pago, estado_pago,
                total_excentas, total_iva5, total_iva10,
                iva_total, total_general, total_en_letras
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            numero_factura, fecha, cliente, ruc, direccion, nota_remision,
            moneda, tipo_venta, plazo_dias, fecha_vencimiento, fecha_pago, estado_pago,
            totales['excentas'], totales['iva5'],
            totales['iva10'], totales['ivaTotal'], totales['total'],
            totales['enLetras']
        ))
        
        factura_id = cur.fetchone()['id']
        
        # Insertar items
        if items:
            for orden, item in enumerate(items):
                cur.execute("""
                    INSERT INTO facturas_items (
                        factura_id, cantidad, descripcion, precio_unitario,
                        impuesto, orden
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    factura_id,
                    float(item.get('cantidad', 0) or 0),
                    item.get('descripcion', ''),
                    float(item.get('precio_unitario', 0) or 0),
                    item.get('impuesto', 'exc'),
                    orden
                ))
        
        conn.commit()
        return factura_id
    finally:
        cur.close()
        conn.close()


def obtener_factura_por_id(factura_id):
    """Obtiene una factura con sus items"""
    conn, cur = conectar()
    try:
        cur.execute("""
            SELECT * FROM facturas WHERE id = %s
        """, (factura_id,))
        
        factura = cur.fetchone()
        if not factura:
            return None
        
        cur.execute("""
            SELECT * FROM facturas_items
            WHERE factura_id = %s
            ORDER BY orden
        """, (factura_id,))
        
        items = cur.fetchall()
        
        return {
            'factura': dict(factura),
            'items': [dict(item) for item in items]
        }
    finally:
        cur.close()
        conn.close()


def obtener_facturas(limite=50):
    """Obtiene la lista de facturas"""
    conn, cur = conectar()
    try:
        cur.execute("""
            SELECT * FROM facturas
            ORDER BY fecha DESC, id DESC
            LIMIT %s
        """, (limite,))
        
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()


def actualizar_factura(factura_id, fecha_pago=None, estado_pago=None):
    """Actualiza la fecha de pago y estado de una factura"""
    conn, cur = conectar()
    try:
        updates = []
        params = []
        
        if fecha_pago is not None:
            updates.append("fecha_pago = %s")
            params.append(fecha_pago)
        
        if estado_pago is not None:
            updates.append("estado_pago = %s")
            params.append(estado_pago)
        
        if not updates:
            return False
        
        params.append(factura_id)
        
        query = f"""
            UPDATE facturas
            SET {', '.join(updates)}, actualizado_en = CURRENT_TIMESTAMP
            WHERE id = %s
        """
        
        cur.execute(query, params)
        conn.commit()
        
        return cur.rowcount > 0
    except Exception as e:
        conn.rollback()
        print(f"Error al actualizar factura: {e}")
        raise
    finally:
        cur.close()
        conn.close()


def eliminar_factura(factura_id):
    """Elimina una factura y sus items asociados (CASCADE)"""
    conn, cur = conectar()
    try:
        # Verificar que la factura existe
        cur.execute("SELECT id, numero_factura FROM facturas WHERE id = %s", (factura_id,))
        factura = cur.fetchone()
        
        if not factura:
            return False
        
        # Eliminar la factura (los items se eliminan automáticamente por CASCADE)
        cur.execute("DELETE FROM facturas WHERE id = %s", (factura_id,))
        conn.commit()
        
        return cur.rowcount > 0
    except Exception as e:
        conn.rollback()
        print(f"Error al eliminar factura: {e}")
        raise
    finally:
        cur.close()
        conn.close()

