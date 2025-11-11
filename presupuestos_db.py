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

def conectar():
    conn = psycopg2.connect(**PG_CONN)
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    return conn, cur


def _texto_mayusculas(valor):
    """Convierte un texto a mayúsculas y elimina espacios laterales."""
    if valor is None:
        return None
    texto = str(valor).strip()
    if texto == "":
        return ""
    return texto.upper()


def obtener_items_activos(tipo=None):
    """Obtiene todos los items activos, opcionalmente filtrados por tipo"""
    conn, cur = conectar()
    try:
        if tipo:
            cur.execute(
                "SELECT * FROM items WHERE activo = TRUE AND tipo = %s ORDER BY tipo, descripcion",
                (tipo,)
            )
        else:
            cur.execute(
                "SELECT * FROM items WHERE activo = TRUE ORDER BY tipo, descripcion"
            )
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()

def obtener_item_por_id(item_id):
    """Obtiene un item por su ID"""
    conn, cur = conectar()
    try:
        cur.execute("SELECT * FROM items WHERE id = %s", (item_id,))
        return cur.fetchone()
    finally:
        cur.close()
        conn.close()

def crear_item(codigo, descripcion, tipo, unidad, precio_base, margen_porcentaje, notas=None):
    """Crea un nuevo item"""
    conn, cur = conectar()
    try:
        codigo_normalizado = _texto_mayusculas(codigo)
        descripcion_normalizada = _texto_mayusculas(descripcion)
        tipo_normalizado = _texto_mayusculas(tipo)
        notas_normalizadas = _texto_mayusculas(notas)
        unidad_simplificada = simplificar_unidad(unidad)
        cur.execute(
            """INSERT INTO items (codigo, descripcion, tipo, unidad, precio_base, margen_porcentaje, notas)
               VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (codigo_normalizado, descripcion_normalizada, tipo_normalizado, unidad_simplificada, precio_base, margen_porcentaje, notas_normalizadas)
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
            params.append(_texto_mayusculas(codigo))
        if descripcion is not None:
            updates.append("descripcion = %s")
            params.append(_texto_mayusculas(descripcion))
        if tipo is not None:
            updates.append("tipo = %s")
            params.append(_texto_mayusculas(tipo))
        if unidad is not None:
            updates.append("unidad = %s")
            params.append(simplificar_unidad(unidad))
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
            params.append(_texto_mayusculas(notas))
        
        if updates:
            params.append(item_id)
            query = f"UPDATE items SET {', '.join(updates)} WHERE id = %s"
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

def crear_o_actualizar_material(descripcion, precio, tiempo_instalacion=0, proveedor=None):
    """Crea o actualiza un material eléctrico"""
    conn, cur = conectar()
    try:
        descripcion_normalizada = _texto_mayusculas(descripcion)
        proveedor_normalizado = _texto_mayusculas(proveedor)
        cur.execute(
            "SELECT id FROM materiales WHERE LOWER(descripcion) = LOWER(%s)",
            (descripcion,)
        )
        existente = cur.fetchone()
        if existente:
            material_id = existente['id']
            cur.execute(
                """UPDATE materiales 
                   SET precio = %s, tiempo_instalacion = %s, proveedor = %s, actualizado_en = CURRENT_TIMESTAMP
                   WHERE id = %s""",
                (precio, tiempo_instalacion, proveedor_normalizado, material_id)
            )
            conn.commit()
            return material_id, True
        else:
            cur.execute(
                """INSERT INTO materiales (descripcion, proveedor, precio, tiempo_instalacion)
                   VALUES (%s, %s, %s, %s) RETURNING id""",
                (descripcion_normalizada, proveedor_normalizado, precio, tiempo_instalacion)
            )
            material_id = cur.fetchone()['id']
            conn.commit()
            return material_id, False
    finally:
        cur.close()
        conn.close()

def actualizar_material(material_id, descripcion=None, proveedor=None, precio=None, tiempo_instalacion=None):
    """Actualiza campos del material"""
    conn, cur = conectar()
    try:
        updates = []
        params = []
        if descripcion is not None:
            updates.append("descripcion = %s")
            params.append(_texto_mayusculas(descripcion))
        if proveedor is not None:
            updates.append("proveedor = %s")
            params.append(_texto_mayusculas(proveedor))
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
    """Obtiene un cliente específico por ID"""
    conn, cur = conectar()
    try:
        cur.execute("SELECT * FROM clientes WHERE id = %s", (cliente_id,))
        return cur.fetchone()
    finally:
        cur.close()
        conn.close()

def crear_cliente(nombre, razon_social=None, ruc=None, direccion=None,
                  telefono=None, email=None, notas=None, contacto=None):
    """Crea un nuevo cliente"""
    conn, cur = conectar()
    try:
        nombre = _texto_mayusculas(nombre)
        razon_social = _texto_mayusculas(razon_social)
        ruc = _texto_mayusculas(ruc)
        direccion = _texto_mayusculas(direccion)
        telefono = _texto_mayusculas(telefono)
        email = _texto_mayusculas(email)
        notas = _texto_mayusculas(notas)
        contacto = _texto_mayusculas(contacto)
        cur.execute(
            """INSERT INTO clientes (nombre, razon_social, ruc, direccion, telefono, email, notas, contacto)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (nombre, razon_social, ruc, direccion, telefono, email, notas, contacto)
        )
        cliente_id = cur.fetchone()['id']
        conn.commit()
        return cliente_id
    finally:
        cur.close()
        conn.close()

def actualizar_cliente(cliente_id, nombre=None, razon_social=None, ruc=None,
                       direccion=None, telefono=None, email=None, contacto=None):
    """Actualiza la información básica del cliente"""
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

        if not updates:
            return False
        params.append(cliente_id)
        query = f"UPDATE clientes SET {', '.join(updates)}, actualizado_en = CURRENT_TIMESTAMP WHERE id = %s"
        cur.execute(query, tuple(params))
        conn.commit()
        return cur.rowcount > 0
    finally:
        cur.close()
        conn.close()

def generar_numero_presupuesto():
    """Genera un número de presupuesto automático"""
    conn, cur = conectar()
    try:
        cur.execute("SELECT generar_numero_presupuesto()")
        return cur.fetchone()[0]
    finally:
        cur.close()
        conn.close()

def crear_presupuesto(cliente_id, numero_presupuesto, titulo=None, descripcion=None, 
                     estado='borrador', fecha_presupuesto=None, validez_dias=30, 
                     iva_porcentaje=21.0, notas=None):
    """Crea un nuevo presupuesto"""
    conn, cur = conectar()
    try:
        numero_presupuesto = _texto_mayusculas(numero_presupuesto)
        titulo = _texto_mayusculas(titulo)
        descripcion = _texto_mayusculas(descripcion)
        notas = _texto_mayusculas(notas)
        cur.execute(
            """INSERT INTO presupuestos 
               (cliente_id, numero_presupuesto, titulo, descripcion, estado, fecha_presupuesto, validez_dias, iva_porcentaje, notas)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (cliente_id, numero_presupuesto, titulo, descripcion, estado, fecha_presupuesto, validez_dias, iva_porcentaje, notas)
        )
        presupuesto_id = cur.fetchone()['id']
        conn.commit()
        return presupuesto_id
    finally:
        cur.close()
        conn.close()

def obtener_presupuestos(estado=None, cliente_id=None, limit=100):
    """Obtiene presupuestos con totales"""
    conn, cur = conectar()
    try:
        query = "SELECT * FROM vista_presupuestos_totales WHERE 1=1"
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

def obtener_presupuesto_por_id(presupuesto_id):
    """Obtiene un presupuesto por su ID con todos sus datos, organizados por subgrupos"""
    conn, cur = conectar()
    try:
        # Obtener el presupuesto desde la vista que incluye los totales calculados
        cur.execute(
            "SELECT * FROM vista_presupuestos_totales WHERE id = %s",
            (presupuesto_id,)
        )
        presupuesto_row = cur.fetchone()
        if not presupuesto_row:
            return None
        
        # Convertir el DictRow a un diccionario normal
        presupuesto = {}
        for key in presupuesto_row.keys():
            presupuesto[key] = presupuesto_row[key]
        
        # Obtener subgrupos del presupuesto
        cur.execute(
            "SELECT * FROM presupuesto_subgrupos WHERE presupuesto_id = %s ORDER BY orden, numero",
            (presupuesto_id,)
        )
        subgrupos_rows = cur.fetchall()
        
        # Convertir subgrupos a diccionarios
        subgrupos_list = []
        for sg in subgrupos_rows:
            sg_dict = {}
            for key in sg.keys():
                sg_dict[key] = sg[key]
            subgrupos_list.append(sg_dict)
        
        # Obtener items del presupuesto
        cur.execute(
            """SELECT * FROM presupuesto_items 
               WHERE presupuesto_id = %s 
               ORDER BY subgrupo_id NULLS LAST, orden, id""",
            (presupuesto_id,)
        )
        items = cur.fetchall()
        
        # Convertir items a diccionarios y organizarlos por subgrupo
        items_por_subgrupo = {}
        items_sin_subgrupo = []
        
        for item in items:
            item_dict = {}
            for key in item.keys():
                item_dict[key] = item[key]
            item_dict['unidad'] = simplificar_unidad(item_dict.get('unidad'))
            
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
        
        presupuesto['subgrupos'] = subgrupos_list
        presupuesto['items_sin_subgrupo'] = items_sin_subgrupo
        
        # Calcular totales del presupuesto
        iva_porcentaje = float(presupuesto.get('iva_porcentaje', 21.0) or 21.0)
        iva_monto = subtotal_total * iva_porcentaje / 100
        total = subtotal_total + iva_monto
        
        presupuesto['subtotal'] = subtotal_total
        presupuesto['iva_monto'] = iva_monto
        presupuesto['total'] = total
        presupuesto['tiempo_ejecucion_total'] = tiempo_total
        presupuesto['cantidad_items'] = len(items)
        
        return presupuesto
    finally:
        cur.close()
        conn.close()

UNIDADES_SIMPLIFICADAS = {
    'unidad': 'UND',
    'unidades': 'UND',
    'und': 'UND',
    'u': 'UND',
    'metro': 'M',
    'metros': 'M',
    'm': 'M',
    'metro lineal': 'ML',
    'metros lineales': 'ML',
    'ml': 'ML',
    'metro cuadrado': 'M2',
    'metros cuadrados': 'M2',
    'm2': 'M2',
    'metro cúbico': 'M3',
    'metros cúbicos': 'M3',
    'm3': 'M3',
    'hora': 'H',
    'horas': 'H',
    'h': 'H',
    'kilogramo': 'KG',
    'kilogramos': 'KG',
    'kg': 'KG',
    'litro': 'L',
    'litros': 'L',
    'l': 'L',
    'par': 'PAR',
    'pares': 'PAR',
    'juego': 'JGO',
    'juegos': 'JGO',
}


def simplificar_unidad(valor):
    """Devuelve la abreviatura estándar para una unidad de medida."""
    if valor is None:
        return 'UND'
    valor_str = str(valor).strip()
    if not valor_str:
        return 'UND'
    clave = valor_str.lower()
    if clave in UNIDADES_SIMPLIFICADAS:
        return UNIDADES_SIMPLIFICADAS[clave]
    return valor_str.upper()[:6]


def agregar_item_a_presupuesto(presupuesto_id, item_id=None, cantidad=1, precio_unitario=None,
                               subgrupo_id=None, numero_subitem=None, tiempo_ejecucion_horas=None,
                               material_id=None, unidad=None,
                               orden=0, notas=None):
    """Agrega un item a un presupuesto"""
    conn, cur = conectar()
    try:
        numero_subitem = _texto_mayusculas(numero_subitem)
        notas = _texto_mayusculas(notas)
        codigo_item = None
        descripcion = None
        tipo = None
        unidad_final = simplificar_unidad(unidad) if unidad else None
        unidad_insercion = 'UND'
        item_fk = None
        material_fk = None
        tiempo_defecto = 0.0
        proveedor = None

        if material_id:
            material = obtener_material_por_id(material_id)
            if not material:
                raise ValueError("Material no encontrado")
            material_fk = material['id']
            descripcion = _texto_mayusculas(material['descripcion'])
            proveedor = _texto_mayusculas(material.get('proveedor'))
            tipo = _texto_mayusculas('Material')
            unidad_material = simplificar_unidad(material.get('unidad')) if isinstance(material, dict) else None
            unidad_insercion = unidad_final or unidad_material or 'UND'
            tiempo_defecto = float(material.get('tiempo_instalacion') or 0) if material.get('tiempo_instalacion') is not None else 0.0
            if precio_unitario is None:
                precio_unitario = float(material.get('precio') or 0)
            codigo_item = f"MAT-{material_fk}"
        else:
            if not item_id:
                raise ValueError("Item o material requerido")
            item = obtener_item_por_id(item_id)
            if not item:
                raise ValueError("Item no encontrado")
            item_fk = item['id']
            codigo_item = _texto_mayusculas(item['codigo'])
            descripcion = _texto_mayusculas(item['descripcion'])
            tipo = _texto_mayusculas(item['tipo'])
            unidad_item = simplificar_unidad(item.get('unidad')) if isinstance(item, dict) else None
            unidad_insercion = unidad_final or unidad_item or 'UND'
            proveedor = _texto_mayusculas(item.get('proveedor'))
            if precio_unitario is None:
                precio_unitario = item['precio_venta'] or item['precio_base'] or 0
            tiempo_defecto = 0.0
        
        if tiempo_ejecucion_horas is None:
            tiempo_ejecucion_horas = tiempo_defecto
        
        tiempo_ejecucion_horas = float(tiempo_ejecucion_horas or 0)
        cantidad = float(cantidad or 0)
        precio_unitario = float(precio_unitario or 0)
        
        cur.execute(
            """INSERT INTO presupuesto_items 
               (presupuesto_id, subgrupo_id, item_id, material_id, codigo_item, descripcion, proveedor, tipo, unidad, 
                cantidad, precio_unitario, numero_subitem, tiempo_ejecucion_horas, orden, notas)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (presupuesto_id, subgrupo_id, item_fk, material_fk, codigo_item, descripcion, proveedor, tipo, unidad_insercion,
             cantidad, precio_unitario, numero_subitem, tiempo_ejecucion_horas, orden, notas)
        )
        item_presupuesto_id = cur.fetchone()['id']
        conn.commit()
        return item_presupuesto_id
    finally:
        cur.close()
        conn.close()

def eliminar_item_de_presupuesto(presupuesto_item_id):
    """Elimina un item de un presupuesto"""
    conn, cur = conectar()
    try:
        cur.execute("DELETE FROM presupuesto_items WHERE id = %s", (presupuesto_item_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        cur.close()
        conn.close()


def eliminar_item_catalogo(item_id):
    """Elimina un servicio del catálogo principal"""
    conn, cur = conectar()
    try:
        cur.execute("DELETE FROM items WHERE id = %s", (item_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        cur.close()
        conn.close()


def duplicar_item_catalogo(item_id):
    """Duplica un servicio del catálogo y devuelve el nuevo ID"""
    conn, cur = conectar()
    try:
        cur.execute("SELECT * FROM items WHERE id = %s", (item_id,))
        item = cur.fetchone()
        if not item:
            return None

        nuevo_codigo = None
        if item['codigo']:
            cur.execute("SELECT COUNT(*) FROM items WHERE codigo = %s", (item['codigo'],))
            existe = cur.fetchone()[0] > 0
            if not existe:
                nuevo_codigo = item['codigo']
            else:
                base_codigo = item['codigo']
                sufijo = 1
                while True:
                    candidato = f"{base_codigo}-{sufijo}"
                    cur.execute("SELECT COUNT(*) FROM items WHERE codigo = %s", (candidato,))
                    if cur.fetchone()[0] == 0:
                        nuevo_codigo = candidato
                        break
                    sufijo += 1
        descripcion = f"{item['descripcion']} (COPIA)"

        cur.execute(
            """INSERT INTO items (codigo, descripcion, tipo, unidad, precio_base, margen_porcentaje, notas, activo)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (
                nuevo_codigo,
                descripcion,
                item['tipo'],
                item['unidad'],
                item['precio_base'],
                item['margen_porcentaje'],
                item['notas'],
                item['activo'],
            )
        )
        nuevo_id = cur.fetchone()['id']
        conn.commit()
        return nuevo_id
    finally:
        cur.close()
        conn.close()

def actualizar_presupuesto(presupuesto_id, cliente_id=None, titulo=None, descripcion=None,
                          estado=None, fecha_presupuesto=None, validez_dias=None,
                          iva_porcentaje=None, notas=None):
    """Actualiza un presupuesto"""
    conn, cur = conectar()
    try:
        updates = []
        params = []
        
        if cliente_id is not None:
            updates.append("cliente_id = %s")
            params.append(cliente_id)
        if titulo is not None:
            updates.append("titulo = %s")
            params.append(_texto_mayusculas(titulo))
        if descripcion is not None:
            updates.append("descripcion = %s")
            params.append(_texto_mayusculas(descripcion))
        if estado is not None:
            updates.append("estado = %s")
            params.append(estado)
        if fecha_presupuesto is not None:
            updates.append("fecha_presupuesto = %s")
            params.append(fecha_presupuesto)
        if validez_dias is not None:
            updates.append("validez_dias = %s")
            params.append(validez_dias)
        if iva_porcentaje is not None:
            updates.append("iva_porcentaje = %s")
            params.append(iva_porcentaje)
        if notas is not None:
            updates.append("notas = %s")
            params.append(_texto_mayusculas(notas))
        
        if updates:
            params.append(presupuesto_id)
            query = f"UPDATE presupuestos SET {', '.join(updates)} WHERE id = %s"
            cur.execute(query, tuple(params))
            conn.commit()
            return cur.rowcount > 0
        return False
    finally:
        cur.close()
        conn.close()

def actualizar_item_presupuesto(presupuesto_item_id, cantidad=None, precio_unitario=None,
                                subgrupo_id=None, numero_subitem=None, tiempo_ejecucion_horas=None,
                                orden=None, descripcion=None, notas=None, material_id=None, proveedor=None,
                                unidad=None):
    """Actualiza un item de un presupuesto"""
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
            params.append(_texto_mayusculas(numero_subitem))
        if tiempo_ejecucion_horas is not None:
            updates.append("tiempo_ejecucion_horas = %s")
            params.append(tiempo_ejecucion_horas)
        if orden is not None:
            updates.append("orden = %s")
            params.append(orden)
        if descripcion is not None:
            updates.append("descripcion = %s")
            params.append(_texto_mayusculas(descripcion))
        if notas is not None:
            updates.append("notas = %s")
            params.append(_texto_mayusculas(notas))
        if material_id is not None:
            updates.append("material_id = %s")
            params.append(material_id)
        if proveedor is not None:
            updates.append("proveedor = %s")
            params.append(_texto_mayusculas(proveedor))
        if unidad is not None:
            updates.append("unidad = %s")
            params.append(simplificar_unidad(unidad))
        
        if updates:
            params.append(presupuesto_item_id)
            query = f"UPDATE presupuesto_items SET {', '.join(updates)} WHERE id = %s"
            cur.execute(query, tuple(params))
            conn.commit()
            return cur.rowcount > 0
        return False
    finally:
        cur.close()
        conn.close()

def obtener_tipos_items():
    """Obtiene los tipos únicos de items"""
    conn, cur = conectar()
    try:
        cur.execute("SELECT DISTINCT tipo FROM items WHERE activo = TRUE ORDER BY tipo")
        tipos = [row['tipo'] for row in cur.fetchall()]
        # Si no hay tipos, devolver los tipos por defecto
        if not tipos:
            tipos = ['Montaje', 'Programación', 'Materiales', 'Diseño', 'Otros']
        return tipos
    finally:
        cur.close()
        conn.close()

# ==================== FUNCIONES DE SUBGRUPOS ====================

def crear_subgrupo(presupuesto_id, numero, nombre, orden=0):
    """Crea un nuevo subgrupo en un presupuesto"""
    conn, cur = conectar()
    try:
        nombre = _texto_mayusculas(nombre)
        cur.execute(
            """INSERT INTO presupuesto_subgrupos (presupuesto_id, numero, nombre, orden)
               VALUES (%s, %s, %s, %s) RETURNING id""",
            (presupuesto_id, numero, nombre, orden)
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
            params.append(_texto_mayusculas(nombre))
        if orden is not None:
            updates.append("orden = %s")
            params.append(orden)
        if tiempo_ejecucion_horas is not None:
            updates.append("tiempo_ejecucion_horas = %s")
            params.append(tiempo_ejecucion_horas)
        
        if updates:
            params.append(subgrupo_id)
            query = f"UPDATE presupuesto_subgrupos SET {', '.join(updates)} WHERE id = %s"
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
        cur.execute("DELETE FROM presupuesto_subgrupos WHERE id = %s", (subgrupo_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        cur.close()
        conn.close()

def obtener_siguiente_numero_subgrupo(presupuesto_id):
    """Obtiene el siguiente número disponible para un subgrupo"""
    conn, cur = conectar()
    try:
        cur.execute(
            "SELECT COALESCE(MAX(numero), 0) + 1 FROM presupuesto_subgrupos WHERE presupuesto_id = %s",
            (presupuesto_id,)
        )
        return cur.fetchone()[0]
    finally:
        cur.close()
        conn.close()

def buscar_materiales(descripcion=None, proveedor=None):
    """Busca materiales con filtros opcionales"""
    conn, cur = conectar()
    try:
        query = "SELECT * FROM materiales WHERE 1=1"
        params = []
        if descripcion:
            query += " AND LOWER(descripcion) LIKE LOWER(%s)"
            params.append(f"%{descripcion}%")
        if proveedor:
            query += " AND LOWER(proveedor) LIKE LOWER(%s)"
            params.append(f"%{proveedor}%")
        query += " ORDER BY descripcion ASC"
        cur.execute(query, tuple(params))
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()


def _procesar_mayusculas_para_columnas(row, columnas):
    cambios = {}
    for columna in columnas:
        valor = row.get(columna)
        if valor is None:
            continue
        if columna == "unidad":
            nuevo = simplificar_unidad(valor)
        else:
            nuevo = _texto_mayusculas(valor)
        if nuevo != valor:
            cambios[columna] = nuevo
    return cambios


def convertir_datos_a_mayusculas():
    """
    Normaliza a mayúsculas los campos de texto principales en todas las tablas relevantes.
    Devuelve un diccionario con la cantidad de filas modificadas por tabla.
    """
    tablas = {
        "clientes": ["nombre", "razon_social", "ruc", "direccion", "telefono", "email", "notas", "contacto"],
        "items": ["codigo", "descripcion", "tipo", "unidad", "notas"],
        "materiales": ["descripcion", "proveedor"],
        "presupuestos": ["numero_presupuesto", "titulo", "descripcion", "notas"],
        "presupuesto_subgrupos": ["nombre"],
        "presupuesto_items": ["descripcion", "proveedor", "notas", "numero_subitem", "unidad"],
        "precios": ["proveedor", "producto"],
    }

    conn, cur = conectar()
    try:
        resumen = {}
        for tabla, columnas in tablas.items():
            cur.execute(f"SELECT id, {', '.join(columnas)} FROM {tabla}")
            filas = cur.fetchall()
            modificadas = 0
            for fila in filas:
                fila_dict = dict(fila)
                cambios = _procesar_mayusculas_para_columnas(fila_dict, columnas)
                if cambios:
                    sets = ", ".join(f"{col} = %s" for col in cambios.keys())
                    params = list(cambios.values())
                    params.append(fila_dict["id"])
                    cur.execute(f"UPDATE {tabla} SET {sets} WHERE id = %s", params)
                    modificadas += 1
            resumen[tabla] = modificadas
        conn.commit()
        return resumen
    finally:
        cur.close()
        conn.close()

