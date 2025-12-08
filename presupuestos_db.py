from dotenv import load_dotenv
import psycopg2
import psycopg2.extras
import os

load_dotenv()

PG_CONN = {
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT"),
}

UNIDADES_SIMPLIFICADAS = {
    'UNIDAD': 'UND',
    'UNIDADES': 'UND',
    'UND': 'UND',
    'U': 'UND',
    'METRO': 'M',
    'METROS': 'M',
    'M': 'M',
    'METRO LINEAL': 'ML',
    'METROS LINEALES': 'ML',
    'ML': 'ML',
    'METRO CUADRADO': 'M2',
    'METROS CUADRADOS': 'M2',
    'M2': 'M2',
    'METRO CÚBICO': 'M3',
    'METROS CÚBICOS': 'M3',
    'M3': 'M3',
    'HORA': 'H',
    'HORAS': 'H',
    'H': 'H',
    'KILOGRAMO': 'KG',
    'KILOGRAMOS': 'KG',
    'KG': 'KG',
    'LITRO': 'L',
    'LITROS': 'L',
    'L': 'L',
    'PAR': 'PAR',
    'PARES': 'PAR',
    'JUEGO': 'JGO',
    'JUEGOS': 'JGO',
}


def simplificar_unidad(unidad):
    if unidad is None:
        return 'UND'
    clave = str(unidad).strip().upper()
    if not clave:
        return 'UND'
    return UNIDADES_SIMPLIFICADAS.get(clave, clave[:6])


def _texto_mayusculas(valor):
    if valor is None:
        return None
    texto = str(valor).strip()
    if texto == "":
        return ""
    return texto.upper()


def _calcular_precio_venta(precio_base, margen_porcentaje):
    try:
        base = float(precio_base or 0)
        margen = float(margen_porcentaje or 0)
        denominador = 1 - (margen / 100.0)
        if denominador <= 0:
            return None
        return round(base / denominador, 2)
    except (TypeError, ValueError, ZeroDivisionError):
        return None

def conectar():
    conn = psycopg2.connect(**PG_CONN)
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    return conn, cur

def obtener_items_activos(tipo=None):
    """Obtiene todos los items activos, opcionalmente filtrados por tipo"""
    conn, cur = conectar()
    try:
        if tipo:
            cur.execute(
                "SELECT * FROM items_mano_de_obra WHERE activo = TRUE AND tipo = %s ORDER BY tipo, descripcion",
                (tipo,)
            )
        else:
            cur.execute(
                "SELECT * FROM items_mano_de_obra WHERE activo = TRUE ORDER BY tipo, descripcion"
            )
        rows = cur.fetchall()
        resultado = []
        for row in rows:
            item = dict(row)
            precio_calculado = _calcular_precio_venta(item.get('precio_base'), item.get('margen_porcentaje'))
            if precio_calculado is not None:
                item['precio_venta'] = precio_calculado
            elif item.get('precio_venta') is None:
                try:
                    item['precio_venta'] = float(item.get('precio_base') or 0)
                except (TypeError, ValueError):
                    item['precio_venta'] = 0
            resultado.append(item)
        return resultado
    finally:
        cur.close()
        conn.close()

def obtener_item_por_id(item_id):
    """Obtiene un item por su ID"""
    conn, cur = conectar()
    try:
        cur.execute("SELECT * FROM items_mano_de_obra WHERE id = %s", (item_id,))
        row = cur.fetchone()
        if not row:
            return None
        item = dict(row)
        precio_calculado = _calcular_precio_venta(item.get('precio_base'), item.get('margen_porcentaje'))
        if precio_calculado is not None:
            item['precio_venta'] = precio_calculado
        elif item.get('precio_venta') is None:
            try:
                item['precio_venta'] = float(item.get('precio_base') or 0)
            except (TypeError, ValueError):
                item['precio_venta'] = 0
        return item
    finally:
        cur.close()
        conn.close()

def crear_item(codigo, descripcion, tipo, unidad, precio_base, margen_porcentaje, notas=None):
    """Crea un nuevo item"""
    conn, cur = conectar()
    try:
        cur.execute(
            """INSERT INTO items_mano_de_obra (codigo, descripcion, tipo, unidad, precio_base, margen_porcentaje, notas)
               VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (codigo, descripcion, tipo, unidad, precio_base, margen_porcentaje, notas)
        )
        item_id = cur.fetchone()['id']
        conn.commit()
        return item_id
    finally:
        cur.close()
        conn.close()

def actualizar_item(item_id, codigo=None, descripcion=None, tipo=None, unidad=None, 
                   precio_base=None, margen_porcentaje=None, activo=None, notas=None):
    """Actualiza un item"""
    conn, cur = conectar()
    try:
        updates = []
        params = []
        
        if codigo is not None:
            updates.append("codigo = %s")
            params.append(codigo)
        if descripcion is not None:
            updates.append("descripcion = %s")
            params.append(descripcion)
        if tipo is not None:
            updates.append("tipo = %s")
            params.append(tipo)
        if unidad is not None:
            updates.append("unidad = %s")
            params.append(unidad)
        if precio_base is not None:
            updates.append("precio_base = %s")
            params.append(precio_base)
        if margen_porcentaje is not None:
            updates.append("margen_porcentaje = %s")
            params.append(margen_porcentaje)
        if activo is not None:
            updates.append("activo = %s")
            params.append(activo)
        if notas is not None:
            updates.append("notas = %s")
            params.append(notas)
        
        if updates:
            params.append(item_id)
            query = f"UPDATE items_mano_de_obra SET {', '.join(updates)} WHERE id = %s"
            cur.execute(query, tuple(params))
            conn.commit()
            return cur.rowcount > 0
        return False
    finally:
        cur.close()
        conn.close()

def obtener_materiales():
    """Obtiene todos los materiales eléctricos"""
    conn, cur = conectar()
    try:
        cur.execute(
            "SELECT * FROM materiales ORDER BY descripcion ASC"
        )
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()

def obtener_material_por_id(material_id):
    """Obtiene un material por su ID"""
    conn, cur = conectar()
    try:
        cur.execute("SELECT * FROM materiales WHERE id = %s", (material_id,))
        return cur.fetchone()
    finally:
        cur.close()
        conn.close()

def crear_o_actualizar_material(descripcion, precio, tiempo_instalacion=0, marca=None, marca_id=None):
    """Crea o actualiza un material eléctrico"""
    conn, cur = conectar()
    try:
        marca_nombre = _texto_mayusculas(marca)
        marca_fk = marca_id
        if marca_fk:
            registro_marca = obtener_marca_material_por_id(marca_fk)
            if not registro_marca:
                raise ValueError("Marca no encontrada")
            marca_nombre = _texto_mayusculas(registro_marca['nombre'])

        cur.execute(
            "SELECT id FROM materiales WHERE LOWER(descripcion) = LOWER(%s)",
            (descripcion,)
        )
        existente = cur.fetchone()
        if existente:
            material_id = existente['id']
            cur.execute(
                """UPDATE materiales 
                   SET precio = %s, tiempo_instalacion = %s, marca = %s, marca_id = %s, actualizado_en = CURRENT_TIMESTAMP
                   WHERE id = %s""",
                (precio, tiempo_instalacion, marca_nombre, marca_fk, material_id)
            )
            conn.commit()
            return material_id, True
        else:
            cur.execute(
                """INSERT INTO materiales (descripcion, marca, marca_id, precio, tiempo_instalacion)
                   VALUES (%s, %s, %s, %s, %s) RETURNING id""",
                (descripcion, marca_nombre, marca_fk, precio, tiempo_instalacion)
            )
            material_id = cur.fetchone()['id']
            conn.commit()
            return material_id, False
    finally:
        cur.close()
        conn.close()

def actualizar_material(material_id, descripcion=None, marca=None, marca_id=None, precio=None, tiempo_instalacion=None):
    """Actualiza campos del material"""
    conn, cur = conectar()
    try:
        updates = []
        params = []
        if descripcion is not None:
            updates.append("descripcion = %s")
            params.append(descripcion)
        if marca is not None or marca_id is not None:
            marca_nombre = marca
            marca_fk = marca_id
            if marca_fk:
                registro_marca = obtener_marca_material_por_id(marca_fk)
                if not registro_marca:
                    raise ValueError("Marca no encontrada")
                marca_nombre = registro_marca['nombre']
            updates.append("marca = %s")
            params.append(_texto_mayusculas(marca_nombre))
            updates.append("marca_id = %s")
            params.append(marca_fk)
        if precio is not None:
            updates.append("precio = %s")
            params.append(precio)
        if tiempo_instalacion is not None:
            updates.append("tiempo_instalacion = %s")
            params.append(tiempo_instalacion)
        if updates:
            updates.append("actualizado_en = CURRENT_TIMESTAMP")
            query = f"UPDATE materiales SET {', '.join(updates)} WHERE id = %s"
            params.append(material_id)
            cur.execute(query, tuple(params))
            conn.commit()
            return cur.rowcount > 0
        return False
    finally:
        cur.close()
        conn.close()

def eliminar_material(material_id):
    """Elimina un material"""
    conn, cur = conectar()
    try:
        cur.execute("DELETE FROM materiales WHERE id = %s", (material_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        cur.close()
        conn.close()

# ==================== MARCAS DE MATERIALES ====================

def obtener_marcas_materiales(activo=None, busqueda=None):
    """Obtiene las marcas registradas"""
    conn, cur = conectar()
    try:
        query = "SELECT * FROM materiales_marcas WHERE 1=1"
        params = []
        if activo is not None:
            query += " AND activo = %s"
            params.append(activo)
        if busqueda:
            query += " AND LOWER(nombre) LIKE LOWER(%s)"
            params.append(f"%{busqueda}%")
        query += " ORDER BY nombre ASC"
        cur.execute(query, tuple(params))
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()


def obtener_marca_material_por_id(marca_id):
    """Devuelve una marca específica"""
    if not marca_id:
        return None
    conn, cur = conectar()
    try:
        cur.execute("SELECT * FROM materiales_marcas WHERE id = %s", (marca_id,))
        return cur.fetchone()
    finally:
        cur.close()
        conn.close()


def crear_marca_material(nombre, descripcion=None, fabricante=None, pais_origen=None,
                         sitio_web=None, contacto=None, notas=None, activo=True):
    """Crea una nueva marca de material"""
    conn, cur = conectar()
    try:
        nombre = _texto_mayusculas(nombre)
        descripcion = _texto_mayusculas(descripcion)
        fabricante = _texto_mayusculas(fabricante)
        pais_origen = _texto_mayusculas(pais_origen)
        sitio_web = _texto_mayusculas(sitio_web)
        contacto = _texto_mayusculas(contacto)
        notas = _texto_mayusculas(notas)
        cur.execute(
            """INSERT INTO materiales_marcas 
               (nombre, descripcion, fabricante, pais_origen, sitio_web, contacto, notas, activo)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (nombre) DO UPDATE SET
                   descripcion = EXCLUDED.descripcion,
                   fabricante = EXCLUDED.fabricante,
                   pais_origen = EXCLUDED.pais_origen,
                   sitio_web = EXCLUDED.sitio_web,
                   contacto = EXCLUDED.contacto,
                   notas = EXCLUDED.notas,
                   activo = EXCLUDED.activo,
                   actualizado_en = CURRENT_TIMESTAMP
               RETURNING id""",
            (nombre, descripcion, fabricante, pais_origen, sitio_web, contacto, notas, activo)
        )
        marca_id = cur.fetchone()['id']
        conn.commit()
        return marca_id
    finally:
        cur.close()
        conn.close()


def actualizar_marca_material(marca_id, nombre=None, descripcion=None, fabricante=None,
                              pais_origen=None, sitio_web=None, contacto=None, notas=None,
                              activo=None):
    """Actualiza los datos de una marca"""
    conn, cur = conectar()
    try:
        updates = []
        params = []
        if nombre is not None:
            updates.append("nombre = %s")
            params.append(_texto_mayusculas(nombre))
        if descripcion is not None:
            updates.append("descripcion = %s")
            params.append(_texto_mayusculas(descripcion))
        if fabricante is not None:
            updates.append("fabricante = %s")
            params.append(_texto_mayusculas(fabricante))
        if pais_origen is not None:
            updates.append("pais_origen = %s")
            params.append(_texto_mayusculas(pais_origen))
        if sitio_web is not None:
            updates.append("sitio_web = %s")
            params.append(_texto_mayusculas(sitio_web))
        if contacto is not None:
            updates.append("contacto = %s")
            params.append(_texto_mayusculas(contacto))
        if notas is not None:
            updates.append("notas = %s")
            params.append(_texto_mayusculas(notas))
        if activo is not None:
            updates.append("activo = %s")
            params.append(activo)
        if not updates:
            return False
        updates.append("actualizado_en = CURRENT_TIMESTAMP")
        params.append(marca_id)
        query = f"UPDATE materiales_marcas SET {', '.join(updates)} WHERE id = %s"
        cur.execute(query, tuple(params))
        conn.commit()
        return cur.rowcount > 0
    finally:
        cur.close()
        conn.close()


def eliminar_marca_material(marca_id):
    """Elimina una marca (si no está referenciada)"""
    conn, cur = conectar()
    try:
        cur.execute("DELETE FROM materiales_marcas WHERE id = %s", (marca_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        cur.close()
        conn.close()


# ==================== PROVEEDORES ====================

def obtener_proveedores(activo=None, busqueda=None):
    conn, cur = conectar()
    try:
        query = "SELECT * FROM proveedores WHERE 1=1"
        params = []
        if activo is not None:
            query += " AND activo = %s"
            params.append(activo)
        if busqueda:
            query += " AND (LOWER(nombre) LIKE LOWER(%s) OR LOWER(razon_social) LIKE LOWER(%s))"
            params.extend([f"%{busqueda}%", f"%{busqueda}%"])
        query += " ORDER BY nombre ASC"
        cur.execute(query, tuple(params))
        return [dict(row) for row in cur.fetchall()]
    finally:
        cur.close()
        conn.close()


def obtener_proveedor_por_id(proveedor_id):
    conn, cur = conectar()
    try:
        cur.execute("SELECT * FROM proveedores WHERE id = %s", (proveedor_id,))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        cur.close()
        conn.close()


def crear_proveedor(nombre, razon_social=None, ruc=None, direccion=None,
                    telefono=None, email=None, contacto=None, notas=None, activo=True):
    conn, cur = conectar()
    try:
        nombre = _texto_mayusculas(nombre)
        razon_social = _texto_mayusculas(razon_social)
        ruc = _texto_mayusculas(ruc)
        direccion = _texto_mayusculas(direccion)
        telefono = _texto_mayusculas(telefono)
        email = _texto_mayusculas(email)
        contacto = _texto_mayusculas(contacto)
        notas = _texto_mayusculas(notas)
        cur.execute(
            """INSERT INTO proveedores
               (nombre, razon_social, ruc, direccion, telefono, email, contacto, notas, activo)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (nombre, razon_social, ruc, direccion, telefono, email, contacto, notas, activo)
        )
        proveedor_id = cur.fetchone()['id']
        conn.commit()
        return proveedor_id
    finally:
        cur.close()
        conn.close()


def actualizar_proveedor(proveedor_id, nombre=None, razon_social=None, ruc=None,
                         direccion=None, telefono=None, email=None, contacto=None,
                         notas=None, activo=None):
    conn, cur = conectar()
    try:
        updates = []
        params = []
        if nombre is not None:
            updates.append("nombre = %s")
            params.append(_texto_mayusculas(nombre))
        if razon_social is not None:
            updates.append("razon_social = %s")
            params.append(_texto_mayusculas(razon_social))
        if ruc is not None:
            updates.append("ruc = %s")
            params.append(_texto_mayusculas(ruc))
        if direccion is not None:
            updates.append("direccion = %s")
            params.append(_texto_mayusculas(direccion))
        if telefono is not None:
            updates.append("telefono = %s")
            params.append(_texto_mayusculas(telefono))
        if email is not None:
            updates.append("email = %s")
            params.append(_texto_mayusculas(email))
        if contacto is not None:
            updates.append("contacto = %s")
            params.append(_texto_mayusculas(contacto))
        if notas is not None:
            updates.append("notas = %s")
            params.append(_texto_mayusculas(notas))
        if activo is not None:
            updates.append("activo = %s")
            params.append(activo)
        if not updates:
            return False
        updates.append("actualizado_en = CURRENT_TIMESTAMP")
        params.append(proveedor_id)
        cur.execute(f"UPDATE proveedores SET {', '.join(updates)} WHERE id = %s", tuple(params))
        conn.commit()
        return cur.rowcount > 0
    finally:
        cur.close()
        conn.close()


def eliminar_proveedor(proveedor_id):
    conn, cur = conectar()
    try:
        cur.execute("DELETE FROM proveedores WHERE id = %s", (proveedor_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        cur.close()
        conn.close()


# ==================== PRECIOS POR ITEM ====================

def obtener_precios_por_item(lista_material_item_id):
    conn, cur = conectar()
    try:
        cur.execute(
            """SELECT p.*, prov.nombre AS proveedor_nombre, prov.contacto
               FROM lista_materiales_precios p
               JOIN proveedores prov ON prov.id = p.proveedor_id
               WHERE lista_material_item_id = %s
               ORDER BY p.seleccionado DESC, p.precio ASC, p.creado_en ASC""",
            (lista_material_item_id,)
        )
        return [dict(row) for row in cur.fetchall()]
    finally:
        cur.close()
        conn.close()


def obtener_precio_por_id(precio_id):
    conn, cur = conectar()
    try:
        cur.execute(
            """SELECT p.*, prov.nombre AS proveedor_nombre, prov.contacto
               FROM lista_materiales_precios p
               LEFT JOIN proveedores prov ON prov.id = p.proveedor_id
               WHERE p.id = %s""",
            (precio_id,)
        )
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        cur.close()
        conn.close()


def _validar_max_proveedores(lista_material_item_id, cur):
    cur.execute(
        "SELECT COUNT(*) FROM lista_materiales_precios WHERE lista_material_item_id = %s",
        (lista_material_item_id,)
    )
    count = cur.fetchone()[0]
    if count >= 5:
        raise ValueError("Solo se permiten hasta 5 proveedores por item")


def agregar_precio_item(lista_material_item_id, proveedor_id, precio,
                        moneda='PYG', fecha_cotizacion=None, notas=None, seleccionado=False):
    conn, cur = conectar()
    try:
        _validar_max_proveedores(lista_material_item_id, cur)
        cur.execute(
            """INSERT INTO lista_materiales_precios
               (lista_material_item_id, proveedor_id, precio, moneda, fecha_cotizacion, notas, seleccionado)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               RETURNING id""",
            (lista_material_item_id, proveedor_id, precio, moneda, fecha_cotizacion, notas, seleccionado)
        )
        precio_id = cur.fetchone()['id']
        if seleccionado:
            _marcar_precio_seleccionado(cur, precio_id, lista_material_item_id)
        conn.commit()
        return precio_id
    finally:
        cur.close()
        conn.close()


def _marcar_precio_seleccionado(cur, precio_id, lista_material_item_id=None):
    if lista_material_item_id is None:
        cur.execute(
            "SELECT lista_material_item_id FROM lista_materiales_precios WHERE id = %s",
            (precio_id,)
        )
        row = cur.fetchone()
        if not row:
            return
        lista_material_item_id = row['lista_material_item_id']

    cur.execute(
        "UPDATE lista_materiales_precios SET seleccionado = FALSE WHERE lista_material_item_id = %s",
        (lista_material_item_id,)
    )
    cur.execute(
        "UPDATE lista_materiales_precios SET seleccionado = TRUE WHERE id = %s",
        (precio_id,)
    )


def actualizar_precio_item(precio_id, proveedor_id=None, precio=None, moneda=None,
                           fecha_cotizacion=None, notas=None, seleccionado=None):
    conn, cur = conectar()
    try:
        updates = []
        params = []
        if proveedor_id is not None:
            updates.append("proveedor_id = %s")
            params.append(proveedor_id)
        if precio is not None:
            updates.append("precio = %s")
            params.append(precio)
        if moneda is not None:
            updates.append("moneda = %s")
            params.append(moneda)
        if fecha_cotizacion is not None:
            updates.append("fecha_cotizacion = %s")
            params.append(fecha_cotizacion)
        if notas is not None:
            updates.append("notas = %s")
            params.append(notas)
        if seleccionado is not None:
            updates.append("seleccionado = %s")
            params.append(seleccionado)
        if not updates:
            return False
        updates.append("actualizado_en = CURRENT_TIMESTAMP")
        params.append(precio_id)
        cur.execute(
            f"UPDATE lista_materiales_precios SET {', '.join(updates)} WHERE id = %s",
            tuple(params)
        )
        if seleccionado:
            _marcar_precio_seleccionado(cur, precio_id)
        conn.commit()
        return cur.rowcount > 0
    finally:
        cur.close()
        conn.close()


def eliminar_precio_item(precio_id):
    conn, cur = conectar()
    try:
        cur.execute("DELETE FROM lista_materiales_precios WHERE id = %s", (precio_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        cur.close()
        conn.close()


def seleccionar_precio_item(precio_id):
    conn, cur = conectar()
    try:
        _marcar_precio_seleccionado(cur, precio_id)
        conn.commit()
        return True
    finally:
        cur.close()
        conn.close()


def seleccionar_precio_por_criterio(lista_material_item_id, criterio="menor"):
    conn, cur = conectar()
    try:
        if criterio == "mayor":
            orden = "precio DESC"
        else:
            orden = "precio ASC"
        cur.execute(
            f"""SELECT id FROM lista_materiales_precios
                WHERE lista_material_item_id = %s
                ORDER BY {orden}, creado_en ASC
                LIMIT 1""",
            (lista_material_item_id,)
        )
        row = cur.fetchone()
        if not row:
            return False
        _marcar_precio_seleccionado(cur, row['id'], lista_material_item_id)
        conn.commit()
        return True
    finally:
        cur.close()
        conn.close()


def eliminar_marca_material(marca_id):
    """Elimina una marca (si no está referenciada)"""
    conn, cur = conectar()
    try:
        cur.execute("DELETE FROM materiales_marcas WHERE id = %s", (marca_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        cur.close()
        conn.close()

def obtener_clientes():
    """Obtiene todos los clientes"""
    conn, cur = conectar()
    try:
        cur.execute("SELECT * FROM clientes ORDER BY nombre")
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()
def obtener_cliente_por_id(cliente_id):
    """Obtiene un cliente específico por su ID"""
    conn, cur = conectar()
    try:
        cur.execute("SELECT * FROM clientes WHERE id = %s", (cliente_id,))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        cur.close()
        conn.close()


def crear_cliente(nombre, razon_social=None, ruc=None, direccion=None, telefono=None, email=None, notas=None):
    """Crea un nuevo cliente"""
    conn, cur = conectar()
    try:
        cur.execute(
            """INSERT INTO clientes (nombre, razon_social, ruc, direccion, telefono, email, notas)
               VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (nombre, razon_social, ruc, direccion, telefono, email, notas)
        )
        cliente_id = cur.fetchone()['id']
        conn.commit()
        return cliente_id
    finally:
        cur.close()
        conn.close()


def actualizar_cliente(cliente_id, nombre=None, razon_social=None, ruc=None,
                       direccion=None, telefono=None, email=None, notas=None):
    """Actualiza los datos de un cliente existente"""
    conn, cur = conectar()
    try:
        updates = []
        params = []
        if nombre is not None:
            updates.append("nombre = %s")
            params.append(nombre)
        if razon_social is not None:
            updates.append("razon_social = %s")
            params.append(razon_social)
        if ruc is not None:
            updates.append("ruc = %s")
            params.append(ruc)
        if direccion is not None:
            updates.append("direccion = %s")
            params.append(direccion)
        if telefono is not None:
            updates.append("telefono = %s")
            params.append(telefono)
        if email is not None:
            updates.append("email = %s")
            params.append(email)
        if notas is not None:
            updates.append("notas = %s")
            params.append(notas)
        if not updates:
            return False
        updates.append("actualizado_en = CURRENT_TIMESTAMP")
        params.append(cliente_id)
        cur.execute(
            f"UPDATE clientes SET {', '.join(updates)} WHERE id = %s",
            tuple(params)
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        cur.close()
        conn.close()


def eliminar_cliente(cliente_id):
    """Elimina un cliente por su ID"""
    conn, cur = conectar()
    try:
        cur.execute("DELETE FROM clientes WHERE id = %s", (cliente_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        cur.close()
        conn.close()


def generar_numero_lista():
    """Genera un número automático para la lista de materiales"""
    conn, cur = conectar()
    try:
        cur.execute("SELECT generar_numero_lista()")
        return cur.fetchone()[0]
    finally:
        cur.close()
        conn.close()


def generar_numero_presupuesto():
    """Compatibilidad retro: alias de generar_numero_lista"""
    return generar_numero_lista()


def crear_lista_material(cliente_id, numero_lista, titulo=None, descripcion=None,
                         estado='borrador', fecha_lista=None, validez_dias=30,
                         iva_porcentaje=10.0, notas=None):
    """Crea una nueva lista de materiales"""
    conn, cur = conectar()
    try:
        cur.execute(
            """INSERT INTO listas_materiales 
               (cliente_id, numero_lista, titulo, descripcion, estado, fecha_lista, validez_dias, iva_porcentaje, notas)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (cliente_id, numero_lista, titulo, descripcion, estado, fecha_lista, validez_dias, iva_porcentaje, notas)
        )
        lista_id = cur.fetchone()['id']
        conn.commit()
        return lista_id
    finally:
        cur.close()
        conn.close()


def crear_presupuesto(*args, **kwargs):
    """Alias retro-compatible"""
    return crear_lista_material(*args, **kwargs)

def obtener_listas_materiales(estado=None, cliente_id=None, limit=100):
    """Obtiene listas_materiales con totales"""
    conn, cur = conectar()
    try:
        query = "SELECT * FROM vista_listas_materiales_totales WHERE 1=1"
        params = []
        
        if estado:
            query += " AND estado = %s"
            params.append(estado)
        if cliente_id:
            query += " AND cliente_id = %s"
            params.append(cliente_id)
        
        query += " ORDER BY creado_en DESC LIMIT %s"
        params.append(limit)
        
        cur.execute(query, tuple(params))
        rows = cur.fetchall()
        # Convertir DictRow a diccionarios normales
        return [dict(row) for row in rows]
    finally:
        cur.close()
        conn.close()

def obtener_lista_material_por_id(lista_material_id):
    """Obtiene una lista de materiales por su ID con todos sus datos, organizados por subgrupos"""
    conn, cur = conectar()
    try:
        # Obtener la lista desde la vista que incluye los totales calculados
        cur.execute(
            "SELECT * FROM vista_listas_materiales_totales WHERE id = %s",
            (lista_material_id,)
        )
        lista_row = cur.fetchone()
        if not lista_row:
            return None
        
        # Convertir el DictRow a un diccionario normal
        lista = {}
        for key in lista_row.keys():
            lista[key] = lista_row[key]
        
        # Obtener subgrupos de la lista
        cur.execute(
            "SELECT * FROM lista_materiales_subgrupos WHERE lista_material_id = %s ORDER BY orden, numero",
            (lista_material_id,)
        )
        subgrupos_rows = cur.fetchall()
        
        # Convertir subgrupos a diccionarios
        subgrupos_list = []
        for sg in subgrupos_rows:
            sg_dict = {}
            for key in sg.keys():
                sg_dict[key] = sg[key]
            subgrupos_list.append(sg_dict)
        
        # Obtener items de la lista
        cur.execute(
            """SELECT * FROM lista_materiales_items 
               WHERE lista_material_id = %s 
               ORDER BY subgrupo_id NULLS LAST, orden, id""",
            (lista_material_id,)
        )
        items = cur.fetchall()
        
        # Convertir items a diccionarios y organizarlos por subgrupo
        items_por_subgrupo = {}
        items_sin_subgrupo = []
        
        for item in items:
            item_dict = {}
            for key in item.keys():
                item_dict[key] = item[key]
            
            subgrupo_id = item_dict.get('subgrupo_id')
            if subgrupo_id:
                if subgrupo_id not in items_por_subgrupo:
                    items_por_subgrupo[subgrupo_id] = []
                items_por_subgrupo[subgrupo_id].append(item_dict)
            else:
                items_sin_subgrupo.append(item_dict)
        
        # Calcular totales y tiempo de ejecución por subgrupo
        subtotal_total = 0
        tiempo_total = 0
        
        for sg in subgrupos_list:
            sg_id = sg['id']
            sg_items = items_por_subgrupo.get(sg_id, [])
            
            # Calcular subtotal del subgrupo
            sg_subtotal = 0
            sg_tiempo = 0
            for item in sg_items:
                if 'subtotal' in item and item['subtotal'] is not None:
                    sg_subtotal += float(item['subtotal'])
                else:
                    precio = float(item.get('precio_unitario', 0) or 0)
                    cantidad = float(item.get('cantidad', 0) or 0)
                    sg_subtotal += precio * cantidad
                
                # Sumar tiempo de ejecución
                sg_tiempo += float(item.get('tiempo_ejecucion_horas', 0) or 0)
            
            sg['subtotal'] = sg_subtotal
            sg['tiempo_ejecucion_horas'] = sg_tiempo
            sg['items'] = sg_items
            subtotal_total += sg_subtotal
            tiempo_total += sg_tiempo
        
        # Calcular subtotal de items sin subgrupo
        for item in items_sin_subgrupo:
            if 'subtotal' in item and item['subtotal'] is not None:
                subtotal_total += float(item['subtotal'])
            else:
                precio = float(item.get('precio_unitario', 0) or 0)
                cantidad = float(item.get('cantidad', 0) or 0)
                subtotal_total += precio * cantidad
            
            tiempo_total += float(item.get('tiempo_ejecucion_horas', 0) or 0)
        
        # Calcular totales de la lista
        iva_porcentaje = float(lista.get('iva_porcentaje', 10.0) or 10.0)
        iva_monto = subtotal_total * iva_porcentaje / 100
        total = subtotal_total + iva_monto
        
        lista['subgrupos'] = subgrupos_list
        lista['items_sin_subgrupo'] = items_sin_subgrupo
        lista['subtotal'] = subtotal_total
        lista['iva_monto'] = iva_monto
        lista['total'] = total
        lista['tiempo_ejecucion_total'] = tiempo_total
        lista['cantidad_items'] = len(items)
        
        return lista
    finally:
        cur.close()
        conn.close()


def obtener_presupuesto_por_id(presupuesto_id):
    """Alias retro-compatible"""
    return obtener_lista_material_por_id(presupuesto_id)

def agregar_item_a_lista_material(lista_material_id, item_id=None, cantidad=1, precio_unitario=None,
                                  subgrupo_id=None, numero_subitem=None, tiempo_ejecucion_horas=None,
                                  material_id=None, material_generico_id=None,
                                  orden=0, notas=None, marca=None, marca_id=None):
    """Agrega un item a una lista de materiales"""
    conn, cur = conectar()
    try:
        codigo_item = None
        descripcion = None
        tipo = None
        unidad = 'UND'
        item_fk = None
        material_fk = None
        tiempo_defecto = 0.0
        marca_texto = _texto_mayusculas(marca)
        marca_fk = marca_id

        if material_generico_id:
            # Material genérico
            material = obtener_material_generico_por_id(material_generico_id)
            if not material:
                raise ValueError("Material genérico no encontrado")
            descripcion = material['descripcion']
            tipo = 'Material Genérico'
            unidad_generico = simplificar_unidad(material.get('unidad')) if material.get('unidad') else None
            unidad = unidad_generico or 'UND'
            tiempo_defecto = float(material.get('tiempo_instalacion') or 0) if material.get('tiempo_instalacion') is not None else 0.0
            if precio_unitario is None:
                precio_unitario = 0  # Los materiales genéricos no tienen precio por defecto
            codigo_item = f"GEN-{material_generico_id}"
            material_fk = None  # No se guarda FK porque no hay relación en la tabla
            if marca_texto is None:
                marca_texto = None
        elif material_id:
            # Material eléctrico (legacy, por si acaso)
            material = obtener_material_por_id(material_id)
            if not material:
                raise ValueError("Material no encontrado")
            material_fk = material['id']
            descripcion = material['descripcion']
            marca_texto = _texto_mayusculas(material.get('marca'))
            marca_fk = material.get('marca_id')
            tipo = 'Material'
            unidad = 'unidad'
            tiempo_defecto = float(material.get('tiempo_instalacion') or 0) if material.get('tiempo_instalacion') is not None else 0.0
            if precio_unitario is None:
                precio_unitario = float(material.get('precio') or 0)
            codigo_item = f"MAT-{material_fk}"
        else:
            # Item de mano de obra
            if not item_id:
                raise ValueError("Item, material o material genérico requerido")
            item = obtener_item_por_id(item_id)
            if not item:
                raise ValueError("Item no encontrado")
            item_fk = item['id']
            codigo_item = item['codigo']
            descripcion = item['descripcion']
            tipo = item['tipo']
            unidad = item['unidad'] or 'unidad'
            if marca_texto is None:
                marca_texto = _texto_mayusculas(item.get('marca'))
            if precio_unitario is None:
                precio_unitario = item['precio_venta'] or item['precio_base'] or 0
            tiempo_defecto = 0.0
        
        if tiempo_ejecucion_horas is None:
            tiempo_ejecucion_horas = tiempo_defecto
        
        tiempo_ejecucion_horas = float(tiempo_ejecucion_horas or 0)
        cantidad = float(cantidad or 0)
        precio_unitario = float(precio_unitario or 0)
        
        # Si no se proporciona numero_subitem y hay subgrupo_id, generar uno automáticamente
        if not numero_subitem and subgrupo_id:
            # Obtener el número del subgrupo
            cur.execute("SELECT numero FROM lista_materiales_subgrupos WHERE id = %s", (subgrupo_id,))
            subgrupo_row = cur.fetchone()
            if subgrupo_row:
                subgrupo_numero = subgrupo_row['numero']
                # Contar los items existentes en este subgrupo
                cur.execute(
                    "SELECT COUNT(*) as count FROM lista_materiales_items WHERE subgrupo_id = %s",
                    (subgrupo_id,)
                )
                count_row = cur.fetchone()
                item_count = count_row['count'] if count_row else 0
                # Generar el número de subitem: subgrupo_numero.item_count+1
                numero_subitem = f"{subgrupo_numero}.{item_count + 1}"
        
        cur.execute(
            """INSERT INTO lista_materiales_items 
               (lista_material_id, subgrupo_id, item_id, material_id, marca_id, codigo_item, descripcion, marca, tipo, unidad, 
                cantidad, precio_unitario, numero_subitem, tiempo_ejecucion_horas, orden, notas)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (lista_material_id, subgrupo_id, item_fk, material_fk, marca_fk, codigo_item, descripcion, marca_texto, tipo, unidad, 
             cantidad, precio_unitario, numero_subitem, tiempo_ejecucion_horas, orden, notas)
        )
        item_presupuesto_id = cur.fetchone()['id']
        conn.commit()
        return item_presupuesto_id
    finally:
        cur.close()
        conn.close()


def agregar_item_a_presupuesto(*args, **kwargs):
    """Alias retro-compatible"""
    return agregar_item_a_lista_material(*args, **kwargs)

def obtener_item_presupuesto_por_id(item_presupuesto_id):
    """Obtiene un item de presupuesto por su ID"""
    conn, cur = conectar()
    try:
        cur.execute("SELECT * FROM lista_materiales_items WHERE id = %s", (item_presupuesto_id,))
        row = cur.fetchone()
        if not row:
            return None
        item = {}
        for key in row.keys():
            item[key] = row[key]
        # Calcular subtotal si no existe
        if 'subtotal' not in item or item['subtotal'] is None:
            cantidad = float(item.get('cantidad', 0) or 0)
            precio = float(item.get('precio_unitario', 0) or 0)
            item['subtotal'] = cantidad * precio
        return item
    finally:
        cur.close()
        conn.close()

def eliminar_item_de_lista_material(lista_material_item_id):
    """Elimina un item de una lista de materiales"""
    conn, cur = conectar()
    try:
        cur.execute("DELETE FROM lista_materiales_items WHERE id = %s", (lista_material_item_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        cur.close()
        conn.close()


def eliminar_item_de_presupuesto(presupuesto_item_id):
    """Alias retro-compatible"""
    return eliminar_item_de_lista_material(presupuesto_item_id)


def actualizar_lista_material(lista_material_id, cliente_id=None, titulo=None, descripcion=None,
                              estado=None, fecha_lista=None, validez_dias=None,
                              iva_porcentaje=None, notas=None):
    """Actualiza una lista de materiales"""
    conn, cur = conectar()
    try:
        updates = []
        params = []
        
        if cliente_id is not None:
            updates.append("cliente_id = %s")
            params.append(cliente_id)
        if titulo is not None:
            updates.append("titulo = %s")
            params.append(titulo)
        if descripcion is not None:
            updates.append("descripcion = %s")
            params.append(descripcion)
        if estado is not None:
            updates.append("estado = %s")
            params.append(estado)
        if fecha_lista is not None:
            updates.append("fecha_lista = %s")
            params.append(fecha_lista)
        if validez_dias is not None:
            updates.append("validez_dias = %s")
            params.append(validez_dias)
        if iva_porcentaje is not None:
            updates.append("iva_porcentaje = %s")
            params.append(iva_porcentaje)
        if notas is not None:
            updates.append("notas = %s")
            params.append(notas)
        
        if updates:
            params.append(lista_material_id)
            query = f"UPDATE listas_materiales SET {', '.join(updates)} WHERE id = %s"
            cur.execute(query, tuple(params))
            conn.commit()
            return cur.rowcount > 0
        return False
    finally:
        cur.close()
        conn.close()


def actualizar_presupuesto(presupuesto_id, **kwargs):
    """Alias retro-compatible"""
    return actualizar_lista_material(presupuesto_id, **kwargs)


def actualizar_item_lista_material(lista_material_item_id, cantidad=None, precio_unitario=None,
                                subgrupo_id=None, numero_subitem=None, tiempo_ejecucion_horas=None,
                                orden=None, descripcion=None, notas=None, material_id=None,
                                marca=None, marca_id=None):
    """Actualiza un item de una lista de materiales"""
    conn, cur = conectar()
    try:
        updates = []
        params = []
        
        if cantidad is not None:
            updates.append("cantidad = %s")
            params.append(cantidad)
        if precio_unitario is not None:
            updates.append("precio_unitario = %s")
            params.append(precio_unitario)
        if subgrupo_id is not None:
            updates.append("subgrupo_id = %s")
            params.append(subgrupo_id)
        if numero_subitem is not None:
            updates.append("numero_subitem = %s")
            params.append(numero_subitem)
        if tiempo_ejecucion_horas is not None:
            updates.append("tiempo_ejecucion_horas = %s")
            params.append(tiempo_ejecucion_horas)
        if orden is not None:
            updates.append("orden = %s")
            params.append(orden)
        if descripcion is not None:
            updates.append("descripcion = %s")
            params.append(descripcion)
        if notas is not None:
            updates.append("notas = %s")
            params.append(notas)
        if material_id is not None:
            updates.append("material_id = %s")
            params.append(material_id)
        if marca is not None:
            updates.append("marca = %s")
            params.append(_texto_mayusculas(marca))
        if marca_id is not None:
            updates.append("marca_id = %s")
            params.append(marca_id)
        
        if updates:
            params.append(lista_material_item_id)
            query = f"UPDATE lista_materiales_items SET {', '.join(updates)} WHERE id = %s"
            cur.execute(query, tuple(params))
            conn.commit()
            return cur.rowcount > 0
        return False
    finally:
        cur.close()
        conn.close()


def actualizar_item_presupuesto(presupuesto_item_id, **kwargs):
    """Alias retro-compatible"""
    return actualizar_item_lista_material(presupuesto_item_id, **kwargs)

def obtener_tipos_items():
    """Obtiene los tipos únicos de items"""
    conn, cur = conectar()
    try:
        cur.execute("SELECT DISTINCT tipo FROM items_mano_de_obra WHERE activo = TRUE ORDER BY tipo")
        tipos = [row['tipo'] for row in cur.fetchall()]
        # Si no hay tipos, devolver los tipos por defecto
        if not tipos:
            tipos = ['Montaje', 'Programación', 'Materiales', 'Diseño', 'Otros']
        return tipos
    finally:
        cur.close()
        conn.close()

# ==================== FUNCIONES PARA PREFIJOS DE CÓDIGOS ====================

def obtener_prefijos_codigos(activo=None):
    """Obtiene todos los prefijos de códigos"""
    conn, cur = conectar()
    try:
        if activo is not None:
            cur.execute("SELECT * FROM prefijos_codigos WHERE activo = %s ORDER BY tipo_servicio", (activo,))
        else:
            cur.execute("SELECT * FROM prefijos_codigos ORDER BY tipo_servicio")
        return [dict(row) for row in cur.fetchall()]
    finally:
        cur.close()
        conn.close()

def obtener_prefijo_por_id(prefijo_id):
    """Obtiene un prefijo por su ID"""
    conn, cur = conectar()
    try:
        cur.execute("SELECT * FROM prefijos_codigos WHERE id = %s", (prefijo_id,))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        cur.close()
        conn.close()

def obtener_prefijo_por_tipo(tipo_servicio):
    """Obtiene el prefijo para un tipo de servicio"""
    conn, cur = conectar()
    try:
        cur.execute("SELECT * FROM prefijos_codigos WHERE tipo_servicio = %s AND activo = TRUE", (tipo_servicio,))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        cur.close()
        conn.close()

def crear_prefijo_codigo(tipo_servicio, prefijo, activo=True):
    """Crea un nuevo prefijo de código"""
    conn, cur = conectar()
    try:
        cur.execute(
            """INSERT INTO prefijos_codigos (tipo_servicio, prefijo, activo)
               VALUES (%s, %s, %s) RETURNING id""",
            (tipo_servicio, prefijo, activo)
        )
        prefijo_id = cur.fetchone()['id']
        conn.commit()
        return prefijo_id
    finally:
        cur.close()
        conn.close()

def actualizar_prefijo_codigo(prefijo_id, tipo_servicio=None, prefijo=None, activo=None):
    """Actualiza un prefijo de código"""
    conn, cur = conectar()
    try:
        updates = []
        params = []
        
        if tipo_servicio is not None:
            updates.append("tipo_servicio = %s")
            params.append(tipo_servicio)
        if prefijo is not None:
            updates.append("prefijo = %s")
            params.append(prefijo)
        if activo is not None:
            updates.append("activo = %s")
            params.append(activo)
        
        if updates:
            updates.append("actualizado_en = CURRENT_TIMESTAMP")
            params.append(prefijo_id)
            cur.execute(
                f"UPDATE prefijos_codigos SET {', '.join(updates)} WHERE id = %s",
                params
            )
            conn.commit()
            return True
        return False
    finally:
        cur.close()
        conn.close()

def eliminar_prefijo_codigo(prefijo_id):
    """Elimina un prefijo de código"""
    conn, cur = conectar()
    try:
        cur.execute("DELETE FROM prefijos_codigos WHERE id = %s", (prefijo_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        cur.close()
        conn.close()

def obtener_siguiente_numero_codigo(tipo_servicio):
    """Obtiene el siguiente número de código para un tipo de servicio"""
    conn, cur = conectar()
    try:
        prefijo_obj = obtener_prefijo_por_tipo(tipo_servicio)
        if not prefijo_obj:
            return None
        
        prefijo = prefijo_obj['prefijo']
        return obtener_siguiente_codigo_por_prefijo(prefijo)
    finally:
        cur.close()
        conn.close()

def obtener_siguiente_codigo_por_prefijo(prefijo):
    """Obtiene el siguiente código disponible para un prefijo dado"""
    conn, cur = conectar()
    try:
        # Normalizar prefijo (mayúsculas, sin espacios)
        prefijo = str(prefijo).strip().upper()
        if not prefijo:
            return None
        
        # Buscar el último código con este prefijo
        cur.execute(
            """SELECT codigo FROM items_mano_de_obra 
               WHERE codigo LIKE %s 
               ORDER BY codigo DESC 
               LIMIT 1""",
            (f"{prefijo}-%",)
        )
        row = cur.fetchone()
        
        if row and row['codigo']:
            # Extraer el número del código (ej: "mon-001" -> 1)
            try:
                ultimo_numero = int(row['codigo'].split('-')[-1])
                siguiente = ultimo_numero + 1
            except (ValueError, IndexError):
                siguiente = 1
        else:
            siguiente = 1
        
        # Formatear con 3 dígitos (001, 002, etc.)
        return f"{prefijo}-{siguiente:03d}"
    finally:
        cur.close()
        conn.close()

# ==================== FUNCIONES DE SUBGRUPOS ====================

def crear_subgrupo(lista_material_id, numero, nombre, orden=0):
    """Crea un nuevo subgrupo en una lista de materiales"""
    conn, cur = conectar()
    try:
        cur.execute(
            """INSERT INTO lista_materiales_subgrupos (lista_material_id, numero, nombre, orden)
               VALUES (%s, %s, %s, %s) RETURNING id""",
            (lista_material_id, numero, nombre, orden)
        )
        subgrupo_id = cur.fetchone()['id']
        conn.commit()
        return subgrupo_id
    finally:
        cur.close()
        conn.close()

def actualizar_subgrupo(subgrupo_id, numero=None, nombre=None, orden=None, tiempo_ejecucion_horas=None):
    """Actualiza un subgrupo"""
    conn, cur = conectar()
    try:
        updates = []
        params = []
        
        if numero is not None:
            updates.append("numero = %s")
            params.append(numero)
        if nombre is not None:
            updates.append("nombre = %s")
            params.append(nombre)
        if orden is not None:
            updates.append("orden = %s")
            params.append(orden)
        if tiempo_ejecucion_horas is not None:
            updates.append("tiempo_ejecucion_horas = %s")
            params.append(tiempo_ejecucion_horas)
        
        if updates:
            params.append(subgrupo_id)
            query = f"UPDATE lista_materiales_subgrupos SET {', '.join(updates)} WHERE id = %s"
            cur.execute(query, tuple(params))
            conn.commit()
            return cur.rowcount > 0
        return False
    finally:
        cur.close()
        conn.close()

def eliminar_subgrupo(subgrupo_id):
    """Elimina un subgrupo (los items quedan sin subgrupo)"""
    conn, cur = conectar()
    try:
        cur.execute("DELETE FROM lista_materiales_subgrupos WHERE id = %s", (subgrupo_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        cur.close()
        conn.close()

def obtener_siguiente_numero_subgrupo(lista_material_id):
    """Obtiene el siguiente número disponible para un subgrupo"""
    conn, cur = conectar()
    try:
        cur.execute(
            "SELECT COALESCE(MAX(numero), 0) + 1 FROM lista_materiales_subgrupos WHERE lista_material_id = %s",
            (lista_material_id,)
        )
        return cur.fetchone()[0]
    finally:
        cur.close()
        conn.close()

def buscar_materiales(descripcion=None, marca=None, marca_id=None):
    """Busca materiales con filtros opcionales"""
    conn, cur = conectar()
    try:
        query = "SELECT * FROM materiales WHERE 1=1"
        params = []
        if descripcion:
            query += " AND LOWER(descripcion) LIKE LOWER(%s)"
            params.append(f"%{descripcion}%")
        if marca:
            query += " AND LOWER(marca) LIKE LOWER(%s)"
            params.append(f"%{marca}%")
        if marca_id:
            query += " AND marca_id = %s"
            params.append(marca_id)
        query += " ORDER BY descripcion ASC"
        cur.execute(query, tuple(params))
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()

# ==================== FUNCIONES DE LISTAS DE MATERIALES ====================

def obtener_materiales_genericos():
    """Obtiene todos los materiales genéricos"""
    conn, cur = conectar()
    try:
        cur.execute("SELECT * FROM materiales_genericos ORDER BY descripcion")
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()

def obtener_material_generico_por_id(material_id):
    """Obtiene un material genérico por su ID"""
    conn, cur = conectar()
    try:
        cur.execute("SELECT * FROM materiales_genericos WHERE id = %s", (material_id,))
        return cur.fetchone()
    finally:
        cur.close()
        conn.close()

def crear_material_generico(descripcion, tiempo_instalacion=0, unidad='UND'):
    """Crea un nuevo material genérico (descripción se guarda en mayúsculas)"""
    conn, cur = conectar()
    try:
        # Convertir descripción a mayúsculas
        descripcion_upper = descripcion.upper().strip() if descripcion else ""
        unidad_normalizada = simplificar_unidad(unidad)
        cur.execute(
            """INSERT INTO materiales_genericos (descripcion, tiempo_instalacion, unidad)
               VALUES (%s, %s, %s) RETURNING id""",
            (descripcion_upper, tiempo_instalacion, unidad_normalizada)
        )
        material_id = cur.fetchone()['id']
        conn.commit()
        return material_id
    finally:
        cur.close()
        conn.close()

def actualizar_material_generico(material_id, descripcion=None, tiempo_instalacion=None, unidad=None):
    """Actualiza un material genérico (descripción se guarda en mayúsculas)"""
    conn, cur = conectar()
    try:
        updates = []
        params = []
        if descripcion is not None:
            # Convertir descripción a mayúsculas
            descripcion_upper = descripcion.upper().strip() if descripcion else ""
            updates.append("descripcion = %s")
            params.append(descripcion_upper)
        if tiempo_instalacion is not None:
            updates.append("tiempo_instalacion = %s")
            params.append(tiempo_instalacion)
        if unidad is not None:
            updates.append("unidad = %s")
            params.append(simplificar_unidad(unidad))
        if updates:
            updates.append("actualizado_en = CURRENT_TIMESTAMP")
            query = f"UPDATE materiales_genericos SET {', '.join(updates)} WHERE id = %s"
            params.append(material_id)
            cur.execute(query, tuple(params))
            conn.commit()
            return cur.rowcount > 0
        return False
    finally:
        cur.close()
        conn.close()

def eliminar_material_generico(material_id):
    """Elimina un material genérico"""
    conn, cur = conectar()
    try:
        cur.execute("DELETE FROM materiales_genericos WHERE id = %s", (material_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        cur.close()
        conn.close()

def buscar_materiales_genericos(descripcion=None):
    """Busca materiales genéricos por descripción"""
    conn, cur = conectar()
    try:
        query = "SELECT * FROM materiales_genericos WHERE 1=1"
        params = []
        if descripcion:
            query += " AND LOWER(descripcion) LIKE LOWER(%s)"
            params.append(f"%{descripcion}%")
        query += " ORDER BY descripcion ASC"
        cur.execute(query, tuple(params))
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()

# ==================== FUNCIONES DE TEMPLATES DE PRESUPUESTOS ====================

def obtener_templates_listas_materiales():
    """Obtiene todos los templates de listas_materiales"""
    conn, cur = conectar()
    try:
        cur.execute("SELECT * FROM templates_listas_materiales ORDER BY nombre")
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()

def obtener_template_por_id(template_id):
    """Obtiene un template por su ID con sus items"""
    conn, cur = conectar()
    try:
        # Obtener el template
        cur.execute("SELECT * FROM templates_listas_materiales WHERE id = %s", (template_id,))
        template = cur.fetchone()
        if not template:
            return None
        
        template_dict = dict(template)
        
        # Obtener items del template
        cur.execute("""
            SELECT ti.*, 
                   i.codigo, i.descripcion as descripcion_item, i.tipo, i.unidad, 
                   i.precio_base, i.margen_porcentaje, i.precio_venta,
                   mg.descripcion as descripcion_material, mg.tiempo_instalacion
            FROM template_items ti
            LEFT JOIN items_mano_de_obra i ON ti.item_mano_de_obra_id = i.id
            LEFT JOIN materiales_genericos mg ON ti.material_generico_id = mg.id
            WHERE ti.template_id = %s
            ORDER BY ti.orden, ti.id
        """, (template_id,))
        items = cur.fetchall()
        
        template_dict['items'] = [dict(item) for item in items]
        return template_dict
    finally:
        cur.close()
        conn.close()

def crear_template(nombre, descripcion=None):
    """Crea un nuevo template"""
    conn, cur = conectar()
    try:
        cur.execute(
            """INSERT INTO templates_listas_materiales (nombre, descripcion)
               VALUES (%s, %s) RETURNING id""",
            (nombre, descripcion)
        )
        template_id = cur.fetchone()['id']
        conn.commit()
        return template_id
    finally:
        cur.close()
        conn.close()

def actualizar_template(template_id, nombre=None, descripcion=None):
    """Actualiza un template"""
    conn, cur = conectar()
    try:
        updates = []
        params = []
        if nombre is not None:
            updates.append("nombre = %s")
            params.append(nombre)
        if descripcion is not None:
            updates.append("descripcion = %s")
            params.append(descripcion)
        if updates:
            updates.append("actualizado_en = CURRENT_TIMESTAMP")
            query = f"UPDATE templates_listas_materiales SET {', '.join(updates)} WHERE id = %s"
            params.append(template_id)
            cur.execute(query, tuple(params))
            conn.commit()
            return cur.rowcount > 0
        return False
    finally:
        cur.close()
        conn.close()

def eliminar_template(template_id):
    """Elimina un template (y sus items por CASCADE)"""
    conn, cur = conectar()
    try:
        cur.execute("DELETE FROM templates_listas_materiales WHERE id = %s", (template_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        cur.close()
        conn.close()

def agregar_item_a_template(template_id, item_mano_de_obra_id=None, material_generico_id=None, cantidad=1, orden=0):
    """Agrega un item (mano de obra o material genérico) a un template"""
    conn, cur = conectar()
    try:
        if not item_mano_de_obra_id and not material_generico_id:
            raise ValueError("Debe especificar item_mano_de_obra_id o material_generico_id")
        
        cur.execute(
            """INSERT INTO template_items (template_id, item_mano_de_obra_id, material_generico_id, cantidad, orden)
               VALUES (%s, %s, %s, %s, %s) RETURNING id""",
            (template_id, item_mano_de_obra_id, material_generico_id, cantidad, orden)
        )
        item_id = cur.fetchone()['id']
        conn.commit()
        return item_id
    finally:
        cur.close()
        conn.close()

def eliminar_item_de_template(template_item_id):
    """Elimina un item de un template"""
    conn, cur = conectar()
    try:
        cur.execute("DELETE FROM template_items WHERE id = %s", (template_item_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        cur.close()
        conn.close()

def aplicar_template_a_lista_material(lista_material_id, template_id, subgrupo_id=None):
    """Aplica un template a una lista de materiales, agregando todos sus items"""
    conn, cur = conectar()
    try:
        template = obtener_template_por_id(template_id)
        if not template:
            raise ValueError("Template no encontrado")
        
        items_agregados = []
        for item_template in template.get('items', []):
            item_mano_de_obra_id = item_template.get('item_mano_de_obra_id')
            material_generico_id = item_template.get('material_generico_id')
            cantidad = float(item_template.get('cantidad', 1))
            
            if item_mano_de_obra_id:
                # Es un item de mano de obra
                item = obtener_item_por_id(item_mano_de_obra_id)
                if item:
                    precio_unitario = item.get('precio_venta') or item.get('precio_base') or 0
                    tiempo_ejecucion = 0.0
                    agregar_item_a_lista_material(
                        lista_material_id=lista_material_id,
                        item_id=item_mano_de_obra_id,
                        cantidad=cantidad,
                        precio_unitario=precio_unitario,
                        subgrupo_id=subgrupo_id,
                        tiempo_ejecucion_horas=tiempo_ejecucion,
                        orden=item_template.get('orden', 0)
                    )
                    items_agregados.append(f"Item: {item.get('descripcion')}")
            
            elif material_generico_id:
                # Es un material genérico - insertar directamente en lista_materiales_items
                material = obtener_material_generico_por_id(material_generico_id)
                if material:
                    descripcion = material.get('descripcion')
                    tiempo_ejecucion = float(material.get('tiempo_instalacion', 0) or 0)
                    unidad_material = simplificar_unidad(material.get('unidad')) if material.get('unidad') else 'UND'
                    
                    # Insertar directamente como item de presupuesto sin precio (se debe ingresar manualmente)
                    cur.execute(
                        """INSERT INTO lista_materiales_items 
                           (lista_material_id, subgrupo_id, codigo_item, descripcion, tipo, unidad, 
                            cantidad, precio_unitario, tiempo_ejecucion_horas, orden, notas)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                        (lista_material_id, subgrupo_id, f"GEN-{material_generico_id}", descripcion, 
                         'Material Genérico', unidad_material, cantidad, 0, tiempo_ejecucion, 
                         item_template.get('orden', 0), f"Material genérico")
                    )
                    cur.fetchone()
                    conn.commit()
                    items_agregados.append(f"Material genérico: {descripcion}")
        
        return items_agregados
    finally:
        cur.close()
        conn.close()


def aplicar_template_a_presupuesto(presupuesto_id, *args, **kwargs):
    """Alias retro-compatible"""
    return aplicar_template_a_lista_material(presupuesto_id, *args, **kwargs)

