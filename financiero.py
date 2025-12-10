"""
Módulo para gestión financiera
Maneja categorías y tipos de ingresos
"""
import psycopg2
import psycopg2.extras
import os
from dotenv import load_dotenv

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


def obtener_categorias_ingresos(activo=None):
    """Obtiene todas las categorías de ingresos"""
    conn, cur = conectar()
    try:
        if activo is not None:
            cur.execute("""
                SELECT * FROM categorias_ingresos
                WHERE activo = %s
                ORDER BY orden, codigo
            """, (activo,))
        else:
            cur.execute("""
                SELECT * FROM categorias_ingresos
                ORDER BY orden, codigo
            """)
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()


def obtener_categoria_por_id(categoria_id):
    """Obtiene una categoría por su ID"""
    conn, cur = conectar()
    try:
        cur.execute("""
            SELECT * FROM categorias_ingresos
            WHERE id = %s
        """, (categoria_id,))
        return cur.fetchone()
    finally:
        cur.close()
        conn.close()


def _to_upper(valor):
    """Convierte un valor a mayúsculas si es un string"""
    if valor is None:
        return None
    texto = str(valor).strip()
    if texto == "":
        return ""
    return texto.upper()


def generar_codigo_categoria():
    """Genera automáticamente el código de la siguiente categoría (números enteros: 1, 2, 3...)"""
    conn, cur = conectar()
    try:
        # Obtener todos los códigos de categorías existentes
        cur.execute("SELECT codigo FROM categorias_ingresos ORDER BY codigo")
        categorias_existentes = cur.fetchall()
        
        # Encontrar el siguiente número entero disponible
        numeros_usados = []
        for categoria in categorias_existentes:
            codigo = categoria['codigo']
            try:
                # Intentar convertir el código a entero (debe ser un número simple: 1, 2, 3...)
                numero = int(codigo)
                numeros_usados.append(numero)
            except ValueError:
                # Si no es un número entero, intentar extraer el primer número
                try:
                    partes = codigo.split('.')
                    if partes[0].isdigit():
                        numeros_usados.append(int(partes[0]))
                except:
                    pass
        
        # Encontrar el siguiente número disponible
        siguiente_numero = 1
        if numeros_usados:
            siguiente_numero = max(numeros_usados) + 1
        
        # Verificar que no exista (doble verificación)
        codigo_generado = str(siguiente_numero)
        cur.execute("SELECT COUNT(*) as count FROM categorias_ingresos WHERE codigo = %s", (codigo_generado,))
        existe = cur.fetchone()['count'] > 0
        
        if existe:
            # Si existe, incrementar hasta encontrar uno disponible
            while existe:
                siguiente_numero += 1
                codigo_generado = str(siguiente_numero)
                cur.execute("SELECT COUNT(*) as count FROM categorias_ingresos WHERE codigo = %s", (codigo_generado,))
                existe = cur.fetchone()['count'] > 0
        
        return codigo_generado
    except Exception as e:
        print(f"Error al generar código de categoría: {e}")
        import traceback
        traceback.print_exc()
        # Fallback: empezar con 1
        return "1"
    finally:
        cur.close()
        conn.close()


def crear_categoria_ingreso(nombre, orden=None):
    """Crea una nueva categoría de ingreso con código automático"""
    conn, cur = conectar()
    try:
        # Generar código automático
        codigo = generar_codigo_categoria()
        
        # Convertir nombre a mayúsculas
        nombre = _to_upper(nombre)
        
        if orden is None:
            # Obtener el siguiente orden
            cur.execute("SELECT COALESCE(MAX(orden), 0) + 1 FROM categorias_ingresos")
            orden = cur.fetchone()[0]
        
        cur.execute("""
            INSERT INTO categorias_ingresos (codigo, nombre, orden)
            VALUES (%s, %s, %s)
            RETURNING id
        """, (codigo, nombre, orden))
        
        categoria_id = cur.fetchone()['id']
        conn.commit()
        return categoria_id
    except Exception as e:
        conn.rollback()
        print(f"Error al crear categoría: {e}")
        raise
    finally:
        cur.close()
        conn.close()


def actualizar_categoria_ingreso(categoria_id, nombre, orden=None, activo=None):
    """Actualiza una categoría de ingreso (el código no se puede cambiar)"""
    conn, cur = conectar()
    try:
        updates = []
        params = []
        
        if nombre is not None:
            updates.append("nombre = %s")
            params.append(_to_upper(nombre))
        
        if orden is not None:
            updates.append("orden = %s")
            params.append(orden)
        
        if activo is not None:
            updates.append("activo = %s")
            params.append(activo)
        
        if updates:
            updates.append("actualizado_en = CURRENT_TIMESTAMP")
            params.append(categoria_id)
            
            cur.execute(f"""
                UPDATE categorias_ingresos
                SET {', '.join(updates)}
                WHERE id = %s
            """, params)
            conn.commit()
            return cur.rowcount > 0
    except Exception as e:
        conn.rollback()
        print(f"Error al actualizar categoría: {e}")
        raise
    finally:
        cur.close()
        conn.close()


def eliminar_categoria_ingreso(categoria_id):
    """Elimina una categoría de ingreso (y sus tipos asociados por CASCADE)"""
    conn, cur = conectar()
    try:
        cur.execute("DELETE FROM categorias_ingresos WHERE id = %s", (categoria_id,))
        conn.commit()
        return cur.rowcount > 0
    except Exception as e:
        conn.rollback()
        print(f"Error al eliminar categoría: {e}")
        raise
    finally:
        cur.close()
        conn.close()


def obtener_tipos_ingresos(categoria_id=None, activo=None):
    """Obtiene todos los tipos de ingresos, opcionalmente filtrados por categoría"""
    conn, cur = conectar()
    try:
        where_clauses = []
        params = []
        
        if categoria_id is not None:
            where_clauses.append("ti.categoria_id = %s")
            params.append(categoria_id)
        
        if activo is not None:
            where_clauses.append("ti.activo = %s")
            params.append(activo)
        
        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)
        
        cur.execute(f"""
            SELECT ti.*, ci.codigo AS categoria_codigo, ci.nombre AS categoria_nombre
            FROM tipos_ingresos ti
            LEFT JOIN categorias_ingresos ci ON ti.categoria_id = ci.id
            {where_sql}
            ORDER BY ci.orden, ci.codigo, ti.orden, ti.codigo
        """, params)
        
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()


def obtener_tipo_ingreso_por_id(tipo_id):
    """Obtiene un tipo de ingreso por su ID"""
    conn, cur = conectar()
    try:
        cur.execute("""
            SELECT ti.*, ci.codigo AS categoria_codigo, ci.nombre AS categoria_nombre
            FROM tipos_ingresos ti
            LEFT JOIN categorias_ingresos ci ON ti.categoria_id = ci.id
            WHERE ti.id = %s
        """, (tipo_id,))
        return cur.fetchone()
    finally:
        cur.close()
        conn.close()


def generar_codigo_tipo_ingreso(categoria_id):
    """Genera automáticamente el código del siguiente tipo de ingreso para una categoría (formato: categoria.tipo)"""
    conn, cur = conectar()
    try:
        # Obtener el código de la categoría (debe ser un número entero: 1, 2, 3...)
        cur.execute("SELECT codigo FROM categorias_ingresos WHERE id = %s", (categoria_id,))
        categoria = cur.fetchone()
        if not categoria:
            return None
        
        codigo_categoria = categoria['codigo']
        
        # Obtener todos los códigos de tipos existentes para esta categoría
        cur.execute("""
            SELECT codigo FROM tipos_ingresos
            WHERE categoria_id = %s
            ORDER BY codigo
        """, (categoria_id,))
        tipos_existentes = cur.fetchall()
        
        # Encontrar el siguiente número disponible
        siguiente_numero = 1
        if tipos_existentes:
            numeros_usados = []
            for tipo in tipos_existentes:
                codigo_tipo = tipo['codigo']
                try:
                    # El código del tipo debe ser formato: "1.1", "1.2", "2.1", "2.2", etc.
                    # El código debe empezar con el código de la categoría seguido de un punto
                    if codigo_tipo.startswith(codigo_categoria + '.'):
                        # Extraer la parte después del código de categoría y el punto
                        parte_restante = codigo_tipo[len(codigo_categoria) + 1:]
                        # Debe ser un número simple (ej: "1" en "1.1")
                        if parte_restante.isdigit():
                            numero = int(parte_restante)
                            numeros_usados.append(numero)
                        else:
                            # Si hay más puntos, tomar el primer número después del punto de la categoría
                            partes_restantes = parte_restante.split('.')
                            if partes_restantes and partes_restantes[0].isdigit():
                                numero = int(partes_restantes[0])
                                numeros_usados.append(numero)
                except (ValueError, IndexError, AttributeError) as e:
                    print(f"Error al parsear código {codigo_tipo}: {e}")
                    continue
            
            if numeros_usados:
                siguiente_numero = max(numeros_usados) + 1
        
        # Generar el código completo: categoría.tipo (ej: "1.1", "1.2", "2.1")
        codigo_generado = f"{codigo_categoria}.{siguiente_numero}"
        
        # Verificar que no exista (doble verificación)
        cur.execute("""
            SELECT COUNT(*) as count FROM tipos_ingresos
            WHERE categoria_id = %s AND codigo = %s
        """, (categoria_id, codigo_generado))
        existe = cur.fetchone()['count'] > 0
        
        if existe:
            # Si existe, incrementar hasta encontrar uno disponible
            while existe:
                siguiente_numero += 1
                codigo_generado = f"{codigo_categoria}.{siguiente_numero}"
                cur.execute("""
                    SELECT COUNT(*) as count FROM tipos_ingresos
                    WHERE categoria_id = %s AND codigo = %s
                """, (categoria_id, codigo_generado))
                existe = cur.fetchone()['count'] > 0
        
        return codigo_generado
    except Exception as e:
        print(f"Error al generar código de tipo de ingreso: {e}")
        import traceback
        traceback.print_exc()
        # Fallback: usar método simple
        try:
            codigo_categoria = categoria['codigo'] if categoria else "1"
            return f"{codigo_categoria}.1"
        except:
            return "1.1"
    finally:
        cur.close()
        conn.close()


def crear_tipo_ingreso(categoria_id, descripcion, orden=None):
    """Crea un nuevo tipo de ingreso con código automático"""
    conn, cur = conectar()
    try:
        # Generar código automático
        codigo = generar_codigo_tipo_ingreso(categoria_id)
        if not codigo:
            raise Exception("No se pudo generar el código. Verifique que la categoría existe.")
        
        # Convertir descripción a mayúsculas
        descripcion = _to_upper(descripcion)
        
        if orden is None:
            # Obtener el siguiente orden para esta categoría
            cur.execute("""
                SELECT COALESCE(MAX(orden), 0) + 1 
                FROM tipos_ingresos 
                WHERE categoria_id = %s
            """, (categoria_id,))
            orden = cur.fetchone()[0]
        
        cur.execute("""
            INSERT INTO tipos_ingresos (categoria_id, codigo, descripcion, orden)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        """, (categoria_id, codigo, descripcion, orden))
        
        tipo_id = cur.fetchone()['id']
        conn.commit()
        return tipo_id
    except Exception as e:
        conn.rollback()
        print(f"Error al crear tipo de ingreso: {e}")
        raise
    finally:
        cur.close()
        conn.close()


def actualizar_tipo_ingreso(tipo_id, descripcion=None, orden=None, activo=None):
    """Actualiza un tipo de ingreso (el código no se puede cambiar)"""
    conn, cur = conectar()
    try:
        updates = []
        params = []
        
        if descripcion is not None:
            updates.append("descripcion = %s")
            params.append(_to_upper(descripcion))
        
        if orden is not None:
            updates.append("orden = %s")
            params.append(orden)
        
        if activo is not None:
            updates.append("activo = %s")
            params.append(activo)
        
        if updates:
            updates.append("actualizado_en = CURRENT_TIMESTAMP")
            params.append(tipo_id)
            
            cur.execute(f"""
                UPDATE tipos_ingresos
                SET {', '.join(updates)}
                WHERE id = %s
            """, params)
            conn.commit()
            return cur.rowcount > 0
    except Exception as e:
        conn.rollback()
        print(f"Error al actualizar tipo de ingreso: {e}")
        raise
    finally:
        cur.close()
        conn.close()


def eliminar_tipo_ingreso(tipo_id):
    """Elimina un tipo de ingreso"""
    conn, cur = conectar()
    try:
        cur.execute("DELETE FROM tipos_ingresos WHERE id = %s", (tipo_id,))
        conn.commit()
        return cur.rowcount > 0
    except Exception as e:
        conn.rollback()
        print(f"Error al eliminar tipo de ingreso: {e}")
        raise
    finally:
        cur.close()
        conn.close()


# ==================== FUNCIONES PARA GASTOS ====================

def obtener_categorias_gastos(activo=None):
    """Obtiene todas las categorías de gastos"""
    conn, cur = conectar()
    try:
        if activo is not None:
            cur.execute("""
                SELECT * FROM categorias_gastos
                WHERE activo = %s
                ORDER BY orden, codigo
            """, (activo,))
        else:
            cur.execute("""
                SELECT * FROM categorias_gastos
                ORDER BY orden, codigo
            """)
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()


def obtener_categoria_gasto_por_id(categoria_id):
    """Obtiene una categoría de gasto por su ID"""
    conn, cur = conectar()
    try:
        cur.execute("""
            SELECT * FROM categorias_gastos
            WHERE id = %s
        """, (categoria_id,))
        return cur.fetchone()
    finally:
        cur.close()
        conn.close()


def generar_codigo_categoria_gasto():
    """Genera automáticamente el código de la siguiente categoría de gasto (números enteros: 1, 2, 3...)"""
    conn, cur = conectar()
    try:
        # Obtener todos los códigos de categorías de gastos existentes
        cur.execute("SELECT codigo FROM categorias_gastos ORDER BY codigo")
        categorias_existentes = cur.fetchall()
        
        # También considerar categorías de ingresos para evitar conflictos
        cur.execute("SELECT codigo FROM categorias_ingresos ORDER BY codigo")
        categorias_ingresos = cur.fetchall()
        
        # Encontrar el siguiente número entero disponible
        numeros_usados = []
        for categoria in categorias_existentes:
            codigo = categoria['codigo']
            try:
                numero = int(codigo)
                numeros_usados.append(numero)
            except ValueError:
                try:
                    partes = codigo.split('.')
                    if partes[0].isdigit():
                        numeros_usados.append(int(partes[0]))
                except:
                    pass
        
        # También considerar números de categorías de ingresos
        for categoria in categorias_ingresos:
            codigo = categoria['codigo']
            try:
                numero = int(codigo)
                numeros_usados.append(numero)
            except ValueError:
                try:
                    partes = codigo.split('.')
                    if partes[0].isdigit():
                        numeros_usados.append(int(partes[0]))
                except:
                    pass
        
        # Encontrar el siguiente número disponible
        siguiente_numero = 1
        if numeros_usados:
            siguiente_numero = max(numeros_usados) + 1
        
        # Verificar que no exista (doble verificación)
        codigo_generado = str(siguiente_numero)
        cur.execute("SELECT COUNT(*) as count FROM categorias_gastos WHERE codigo = %s", (codigo_generado,))
        existe = cur.fetchone()['count'] > 0
        
        if existe:
            while existe:
                siguiente_numero += 1
                codigo_generado = str(siguiente_numero)
                cur.execute("SELECT COUNT(*) as count FROM categorias_gastos WHERE codigo = %s", (codigo_generado,))
                existe = cur.fetchone()['count'] > 0
        
        return codigo_generado
    except Exception as e:
        print(f"Error al generar código de categoría de gasto: {e}")
        import traceback
        traceback.print_exc()
        return "1"
    finally:
        cur.close()
        conn.close()


def crear_categoria_gasto(nombre, orden=None):
    """Crea una nueva categoría de gasto con código automático"""
    conn, cur = conectar()
    try:
        # Generar código automático
        codigo = generar_codigo_categoria_gasto()
        
        # Convertir nombre a mayúsculas
        nombre = _to_upper(nombre)
        
        if orden is None:
            # Obtener el siguiente orden
            cur.execute("SELECT COALESCE(MAX(orden), 0) + 1 FROM categorias_gastos")
            orden = cur.fetchone()[0]
        
        cur.execute("""
            INSERT INTO categorias_gastos (codigo, nombre, orden)
            VALUES (%s, %s, %s)
            RETURNING id
        """, (codigo, nombre, orden))
        
        categoria_id = cur.fetchone()['id']
        conn.commit()
        return categoria_id
    except Exception as e:
        conn.rollback()
        print(f"Error al crear categoría de gasto: {e}")
        raise
    finally:
        cur.close()
        conn.close()


def actualizar_categoria_gasto(categoria_id, nombre, orden=None, activo=None):
    """Actualiza una categoría de gasto (el código no se puede cambiar)"""
    conn, cur = conectar()
    try:
        updates = []
        params = []
        
        if nombre is not None:
            updates.append("nombre = %s")
            params.append(_to_upper(nombre))
        
        if orden is not None:
            updates.append("orden = %s")
            params.append(orden)
        
        if activo is not None:
            updates.append("activo = %s")
            params.append(activo)
        
        if updates:
            updates.append("actualizado_en = CURRENT_TIMESTAMP")
            params.append(categoria_id)
            
            cur.execute(f"""
                UPDATE categorias_gastos
                SET {', '.join(updates)}
                WHERE id = %s
            """, params)
            conn.commit()
            return cur.rowcount > 0
    except Exception as e:
        conn.rollback()
        print(f"Error al actualizar categoría de gasto: {e}")
        raise
    finally:
        cur.close()
        conn.close()


def eliminar_categoria_gasto(categoria_id):
    """Elimina una categoría de gasto (y sus tipos asociados por CASCADE)"""
    conn, cur = conectar()
    try:
        cur.execute("DELETE FROM categorias_gastos WHERE id = %s", (categoria_id,))
        conn.commit()
        return cur.rowcount > 0
    except Exception as e:
        conn.rollback()
        print(f"Error al eliminar categoría de gasto: {e}")
        raise
    finally:
        cur.close()
        conn.close()


def obtener_tipos_gastos(categoria_id=None, activo=None):
    """Obtiene todos los tipos de gastos, opcionalmente filtrados por categoría"""
    conn, cur = conectar()
    try:
        where_clauses = []
        params = []
        
        if categoria_id is not None:
            where_clauses.append("tg.categoria_id = %s")
            params.append(categoria_id)
        
        if activo is not None:
            where_clauses.append("tg.activo = %s")
            params.append(activo)
        
        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)
        
        cur.execute(f"""
            SELECT tg.*, cg.codigo AS categoria_codigo, cg.nombre AS categoria_nombre
            FROM tipos_gastos tg
            LEFT JOIN categorias_gastos cg ON tg.categoria_id = cg.id
            {where_sql}
            ORDER BY cg.orden, cg.codigo, tg.orden, tg.codigo
        """, params)
        
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()


def obtener_tipo_gasto_por_id(tipo_id):
    """Obtiene un tipo de gasto por su ID"""
    conn, cur = conectar()
    try:
        cur.execute("""
            SELECT tg.*, cg.codigo AS categoria_codigo, cg.nombre AS categoria_nombre
            FROM tipos_gastos tg
            LEFT JOIN categorias_gastos cg ON tg.categoria_id = cg.id
            WHERE tg.id = %s
        """, (tipo_id,))
        return cur.fetchone()
    finally:
        cur.close()
        conn.close()


def generar_codigo_tipo_gasto(categoria_id):
    """Genera automáticamente el código del siguiente tipo de gasto para una categoría (formato: categoria.tipo)"""
    conn, cur = conectar()
    try:
        # Obtener el código de la categoría (debe ser un número entero: 1, 2, 3...)
        cur.execute("SELECT codigo FROM categorias_gastos WHERE id = %s", (categoria_id,))
        categoria = cur.fetchone()
        if not categoria:
            return None
        
        codigo_categoria = categoria['codigo']
        
        # Obtener todos los códigos de tipos existentes para esta categoría
        cur.execute("""
            SELECT codigo FROM tipos_gastos
            WHERE categoria_id = %s
            ORDER BY codigo
        """, (categoria_id,))
        tipos_existentes = cur.fetchall()
        
        # Encontrar el siguiente número disponible
        siguiente_numero = 1
        if tipos_existentes:
            numeros_usados = []
            for tipo in tipos_existentes:
                codigo_tipo = tipo['codigo']
                try:
                    if codigo_tipo.startswith(codigo_categoria + '.'):
                        parte_restante = codigo_tipo[len(codigo_categoria) + 1:]
                        if parte_restante.isdigit():
                            numero = int(parte_restante)
                            numeros_usados.append(numero)
                        else:
                            partes_restantes = parte_restante.split('.')
                            if partes_restantes and partes_restantes[0].isdigit():
                                numero = int(partes_restantes[0])
                                numeros_usados.append(numero)
                except (ValueError, IndexError, AttributeError) as e:
                    print(f"Error al parsear código {codigo_tipo}: {e}")
                    continue
            
            if numeros_usados:
                siguiente_numero = max(numeros_usados) + 1
        
        # Generar el código completo: categoría.tipo (ej: "1.1", "1.2", "2.1")
        codigo_generado = f"{codigo_categoria}.{siguiente_numero}"
        
        # Verificar que no exista (doble verificación)
        cur.execute("""
            SELECT COUNT(*) as count FROM tipos_gastos
            WHERE categoria_id = %s AND codigo = %s
        """, (categoria_id, codigo_generado))
        existe = cur.fetchone()['count'] > 0
        
        if existe:
            while existe:
                siguiente_numero += 1
                codigo_generado = f"{codigo_categoria}.{siguiente_numero}"
                cur.execute("""
                    SELECT COUNT(*) as count FROM tipos_gastos
                    WHERE categoria_id = %s AND codigo = %s
                """, (categoria_id, codigo_generado))
                existe = cur.fetchone()['count'] > 0
        
        return codigo_generado
    except Exception as e:
        print(f"Error al generar código de tipo de gasto: {e}")
        import traceback
        traceback.print_exc()
        try:
            codigo_categoria = categoria['codigo'] if categoria else "1"
            return f"{codigo_categoria}.1"
        except:
            return "1.1"
    finally:
        cur.close()
        conn.close()


def crear_tipo_gasto(categoria_id, descripcion, orden=None):
    """Crea un nuevo tipo de gasto con código automático"""
    conn, cur = conectar()
    try:
        # Generar código automático
        codigo = generar_codigo_tipo_gasto(categoria_id)
        if not codigo:
            raise Exception("No se pudo generar el código. Verifique que la categoría existe.")
        
        # Convertir descripción a mayúsculas
        descripcion = _to_upper(descripcion)
        
        if orden is None:
            # Obtener el siguiente orden para esta categoría
            cur.execute("""
                SELECT COALESCE(MAX(orden), 0) + 1 
                FROM tipos_gastos 
                WHERE categoria_id = %s
            """, (categoria_id,))
            orden = cur.fetchone()[0]
        
        cur.execute("""
            INSERT INTO tipos_gastos (categoria_id, codigo, descripcion, orden)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        """, (categoria_id, codigo, descripcion, orden))
        
        tipo_id = cur.fetchone()['id']
        conn.commit()
        return tipo_id
    except Exception as e:
        conn.rollback()
        print(f"Error al crear tipo de gasto: {e}")
        raise
    finally:
        cur.close()
        conn.close()


def actualizar_tipo_gasto(tipo_id, descripcion=None, orden=None, activo=None):
    """Actualiza un tipo de gasto (el código no se puede cambiar)"""
    conn, cur = conectar()
    try:
        updates = []
        params = []
        
        if descripcion is not None:
            updates.append("descripcion = %s")
            params.append(_to_upper(descripcion))
        
        if orden is not None:
            updates.append("orden = %s")
            params.append(orden)
        
        if activo is not None:
            updates.append("activo = %s")
            params.append(activo)
        
        if updates:
            updates.append("actualizado_en = CURRENT_TIMESTAMP")
            params.append(tipo_id)
            
            cur.execute(f"""
                UPDATE tipos_gastos
                SET {', '.join(updates)}
                WHERE id = %s
            """, params)
            conn.commit()
            return cur.rowcount > 0
    except Exception as e:
        conn.rollback()
        print(f"Error al actualizar tipo de gasto: {e}")
        raise
    finally:
        cur.close()
        conn.close()


def eliminar_tipo_gasto(tipo_id):
    """Elimina un tipo de gasto"""
    conn, cur = conectar()
    try:
        cur.execute("DELETE FROM tipos_gastos WHERE id = %s", (tipo_id,))
        conn.commit()
        return cur.rowcount > 0
    except Exception as e:
        conn.rollback()
        print(f"Error al eliminar tipo de gasto: {e}")
        raise
    finally:
        cur.close()
        conn.close()


# ==================== FUNCIONES PARA PROYECTOS ====================

def obtener_proyectos(activo=None):
    """Obtiene todos los proyectos"""
    conn, cur = conectar()
    try:
        if activo is not None:
            cur.execute("""
                SELECT * FROM proyectos
                WHERE activo = %s
                ORDER BY codigo
            """, (activo,))
        else:
            cur.execute("""
                SELECT * FROM proyectos
                ORDER BY codigo
            """)
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()


def obtener_proyecto_por_id(proyecto_id):
    """Obtiene un proyecto por su ID"""
    conn, cur = conectar()
    try:
        cur.execute("""
            SELECT * FROM proyectos
            WHERE id = %s
        """, (proyecto_id,))
        return cur.fetchone()
    finally:
        cur.close()
        conn.close()


def generar_codigo_proyecto():
    """Genera automáticamente el código del siguiente proyecto (números enteros: 1, 2, 3...)"""
    conn, cur = conectar()
    try:
        cur.execute("SELECT COALESCE(MAX(codigo), 0) + 1 FROM proyectos")
        siguiente_codigo = cur.fetchone()[0]
        
        # Verificar que no exista (doble verificación)
        cur.execute("SELECT COUNT(*) as count FROM proyectos WHERE codigo = %s", (siguiente_codigo,))
        existe = cur.fetchone()['count'] > 0
        
        if existe:
            while existe:
                siguiente_codigo += 1
                cur.execute("SELECT COUNT(*) as count FROM proyectos WHERE codigo = %s", (siguiente_codigo,))
                existe = cur.fetchone()['count'] > 0
        
        return siguiente_codigo
    except Exception as e:
        print(f"Error al generar código de proyecto: {e}")
        return 1
    finally:
        cur.close()
        conn.close()


def crear_proyecto(nombre, codigo=None):
    """Crea un nuevo proyecto con código automático"""
    conn, cur = conectar()
    try:
        if codigo is None:
            codigo = generar_codigo_proyecto()
        
        nombre = _to_upper(nombre)
        
        cur.execute("""
            INSERT INTO proyectos (codigo, nombre)
            VALUES (%s, %s)
            RETURNING id
        """, (codigo, nombre))
        
        proyecto_id = cur.fetchone()['id']
        conn.commit()
        return proyecto_id
    except Exception as e:
        conn.rollback()
        print(f"Error al crear proyecto: {e}")
        raise
    finally:
        cur.close()
        conn.close()


def actualizar_proyecto(proyecto_id, nombre=None, activo=None):
    """Actualiza un proyecto (el código no se puede cambiar)"""
    conn, cur = conectar()
    try:
        updates = []
        params = []
        
        if nombre is not None:
            updates.append("nombre = %s")
            params.append(_to_upper(nombre))
        
        if activo is not None:
            updates.append("activo = %s")
            params.append(activo)
        
        if updates:
            updates.append("actualizado_en = CURRENT_TIMESTAMP")
            params.append(proyecto_id)
            
            cur.execute(f"""
                UPDATE proyectos
                SET {', '.join(updates)}
                WHERE id = %s
            """, params)
            conn.commit()
            return cur.rowcount > 0
    except Exception as e:
        conn.rollback()
        print(f"Error al actualizar proyecto: {e}")
        raise
    finally:
        cur.close()
        conn.close()


def eliminar_proyecto(proyecto_id):
    """Elimina un proyecto"""
    conn, cur = conectar()
    try:
        cur.execute("DELETE FROM proyectos WHERE id = %s", (proyecto_id,))
        conn.commit()
        return cur.rowcount > 0
    except Exception as e:
        conn.rollback()
        print(f"Error al eliminar proyecto: {e}")
        raise
    finally:
        cur.close()
        conn.close()


# ==================== FUNCIONES PARA TIPOS DE DOCUMENTOS ====================

def obtener_tipos_documentos(activo=None):
    """Obtiene todos los tipos de documentos"""
    conn, cur = conectar()
    try:
        if activo is not None:
            cur.execute("""
                SELECT * FROM tipos_documentos
                WHERE activo = %s
                ORDER BY codigo
            """, (activo,))
        else:
            cur.execute("""
                SELECT * FROM tipos_documentos
                ORDER BY codigo
            """)
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()


def obtener_tipo_documento_por_id(tipo_id):
    """Obtiene un tipo de documento por su ID"""
    conn, cur = conectar()
    try:
        cur.execute("""
            SELECT * FROM tipos_documentos
            WHERE id = %s
        """, (tipo_id,))
        return cur.fetchone()
    finally:
        cur.close()
        conn.close()


def generar_codigo_tipo_documento():
    """Genera automáticamente el código del siguiente tipo de documento (números enteros: 1, 2, 3...)"""
    conn, cur = conectar()
    try:
        cur.execute("SELECT COALESCE(MAX(codigo), 0) + 1 FROM tipos_documentos")
        siguiente_codigo = cur.fetchone()[0]
        
        # Verificar que no exista (doble verificación)
        cur.execute("SELECT COUNT(*) as count FROM tipos_documentos WHERE codigo = %s", (siguiente_codigo,))
        existe = cur.fetchone()['count'] > 0
        
        if existe:
            while existe:
                siguiente_codigo += 1
                cur.execute("SELECT COUNT(*) as count FROM tipos_documentos WHERE codigo = %s", (siguiente_codigo,))
                existe = cur.fetchone()['count'] > 0
        
        return siguiente_codigo
    except Exception as e:
        print(f"Error al generar código de tipo de documento: {e}")
        return 1
    finally:
        cur.close()
        conn.close()


def crear_tipo_documento(nombre, codigo=None):
    """Crea un nuevo tipo de documento con código automático"""
    conn, cur = conectar()
    try:
        if codigo is None:
            codigo = generar_codigo_tipo_documento()
        
        nombre = _to_upper(nombre)
        
        cur.execute("""
            INSERT INTO tipos_documentos (codigo, nombre)
            VALUES (%s, %s)
            RETURNING id
        """, (codigo, nombre))
        
        tipo_id = cur.fetchone()['id']
        conn.commit()
        return tipo_id
    except Exception as e:
        conn.rollback()
        print(f"Error al crear tipo de documento: {e}")
        raise
    finally:
        cur.close()
        conn.close()


def actualizar_tipo_documento(tipo_id, nombre=None, activo=None):
    """Actualiza un tipo de documento (el código no se puede cambiar)"""
    conn, cur = conectar()
    try:
        updates = []
        params = []
        
        if nombre is not None:
            updates.append("nombre = %s")
            params.append(_to_upper(nombre))
        
        if activo is not None:
            updates.append("activo = %s")
            params.append(activo)
        
        if updates:
            updates.append("actualizado_en = CURRENT_TIMESTAMP")
            params.append(tipo_id)
            
            cur.execute(f"""
                UPDATE tipos_documentos
                SET {', '.join(updates)}
                WHERE id = %s
            """, params)
            conn.commit()
            return cur.rowcount > 0
    except Exception as e:
        conn.rollback()
        print(f"Error al actualizar tipo de documento: {e}")
        raise
    finally:
        cur.close()
        conn.close()


def eliminar_tipo_documento(tipo_id):
    """Elimina un tipo de documento"""
    conn, cur = conectar()
    try:
        cur.execute("DELETE FROM tipos_documentos WHERE id = %s", (tipo_id,))
        conn.commit()
        return cur.rowcount > 0
    except Exception as e:
        conn.rollback()
        print(f"Error al eliminar tipo de documento: {e}")
        raise
    finally:
        cur.close()
        conn.close()


# ==================== FUNCIONES PARA BANCOS ====================

def obtener_fecha_saldo_inicial():
    """Obtiene la fecha global de saldos iniciales"""
    conn, cur = conectar()
    try:
        cur.execute("""
            SELECT fecha_saldo_inicial 
            FROM configuracion_saldos_iniciales 
            WHERE id = 1
        """)
        result = cur.fetchone()
        return result['fecha_saldo_inicial'] if result and result['fecha_saldo_inicial'] else None
    finally:
        cur.close()
        conn.close()


def actualizar_fecha_saldo_inicial(fecha):
    """Actualiza la fecha global de saldos iniciales"""
    conn, cur = conectar()
    try:
        cur.execute("""
            INSERT INTO configuracion_saldos_iniciales (id, fecha_saldo_inicial, actualizado_en)
            VALUES (1, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (id) 
            DO UPDATE SET fecha_saldo_inicial = %s, actualizado_en = CURRENT_TIMESTAMP
        """, (fecha, fecha))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"Error al actualizar fecha de saldo inicial: {e}")
        raise
    finally:
        cur.close()
        conn.close()


def obtener_bancos(activo=None):
    """Obtiene todos los bancos"""
    conn, cur = conectar()
    try:
        if activo is not None:
            cur.execute("""
                SELECT * FROM bancos
                WHERE activo = %s
                ORDER BY nombre
            """, (activo,))
        else:
            cur.execute("""
                SELECT * FROM bancos
                ORDER BY nombre
            """)
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()


def obtener_banco_por_id(banco_id):
    """Obtiene un banco por su ID"""
    conn, cur = conectar()
    try:
        cur.execute("""
            SELECT * FROM bancos
            WHERE id = %s
        """, (banco_id,))
        return cur.fetchone()
    finally:
        cur.close()
        conn.close()


def crear_banco(nombre, saldo_inicial=0):
    """Crea un nuevo banco"""
    conn, cur = conectar()
    try:
        nombre = _to_upper(nombre)
        
        cur.execute("""
            INSERT INTO bancos (nombre, saldo_inicial)
            VALUES (%s, %s)
            RETURNING id
        """, (nombre, saldo_inicial))
        
        banco_id = cur.fetchone()['id']
        conn.commit()
        return banco_id
    except Exception as e:
        conn.rollback()
        print(f"Error al crear banco: {e}")
        raise
    finally:
        cur.close()
        conn.close()


def actualizar_banco(banco_id, nombre=None, saldo_inicial=None, activo=None):
    """Actualiza un banco"""
    conn, cur = conectar()
    try:
        updates = []
        params = []
        
        if nombre is not None:
            updates.append("nombre = %s")
            params.append(_to_upper(nombre))
        
        if saldo_inicial is not None:
            updates.append("saldo_inicial = %s")
            params.append(saldo_inicial)
        
        if activo is not None:
            updates.append("activo = %s")
            params.append(activo)
        
        if updates:
            updates.append("actualizado_en = CURRENT_TIMESTAMP")
            params.append(banco_id)
            
            cur.execute(f"""
                UPDATE bancos
                SET {', '.join(updates)}
                WHERE id = %s
            """, params)
            conn.commit()
            return cur.rowcount > 0
    except Exception as e:
        conn.rollback()
        print(f"Error al actualizar banco: {e}")
        raise
    finally:
        cur.close()
        conn.close()


def eliminar_banco(banco_id):
    """Elimina un banco"""
    conn, cur = conectar()
    try:
        cur.execute("DELETE FROM bancos WHERE id = %s", (banco_id,))
        conn.commit()
        return cur.rowcount > 0
    except Exception as e:
        conn.rollback()
        print(f"Error al eliminar banco: {e}")
        raise
    finally:
        cur.close()
        conn.close()


# ==================== FUNCIONES PARA CUENTAS A RECIBIR ====================

def obtener_cuentas_a_recibir(filtros=None, limite=None, offset=None):
    """Obtiene todas las cuentas a recibir con filtros opcionales y paginación"""
    conn, cur = conectar()
    try:
        where_clauses = []
        params = []
        
        if filtros:
            if filtros.get('fecha_desde'):
                where_clauses.append("car.fecha_emision >= %s")
                params.append(filtros['fecha_desde'])
            
            if filtros.get('fecha_hasta'):
                where_clauses.append("car.fecha_emision <= %s")
                params.append(filtros['fecha_hasta'])
            
            if filtros.get('cliente'):
                where_clauses.append("UPPER(car.cliente) LIKE UPPER(%s)")
                params.append(f"%{filtros['cliente']}%")
            
            if filtros.get('estado'):
                where_clauses.append("car.estado = %s")
                params.append(filtros['estado'])
            
            if filtros.get('banco_id'):
                where_clauses.append("car.banco_id = %s")
                params.append(filtros['banco_id'])
        
        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)
        
        # Agregar LIMIT y OFFSET si se proporcionan
        limit_sql = ""
        if limite is not None:
            limit_sql = f" LIMIT {limite}"
            if offset is not None:
                limit_sql += f" OFFSET {offset}"
        
        cur.execute(f"""
            SELECT 
                car.*,
                td.nombre AS documento_nombre,
                b.nombre AS banco_nombre,
                ci.nombre AS cuenta_nombre,
                p.nombre AS proyecto_nombre,
                COALESCE(car.monto_abonado, 0) AS monto_abonado,
                (COALESCE(car.valor_cuota, car.valor, 0) - COALESCE(car.monto_abonado, 0)) AS saldo
            FROM cuentas_a_recibir car
            LEFT JOIN tipos_documentos td ON car.documento_id = td.id
            LEFT JOIN bancos b ON car.banco_id = b.id
            LEFT JOIN categorias_ingresos ci ON car.cuenta_id = ci.id
            LEFT JOIN proyectos p ON car.proyecto_id = p.id
            {where_sql}
            ORDER BY car.fecha_emision DESC, car.id DESC
            {limit_sql}
        """, params)
        
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()


def contar_cuentas_a_recibir(filtros=None):
    """Cuenta el total de cuentas a recibir con filtros opcionales"""
    conn, cur = conectar()
    try:
        where_clauses = []
        params = []
        
        if filtros:
            if filtros.get('fecha_desde'):
                where_clauses.append("car.fecha_emision >= %s")
                params.append(filtros['fecha_desde'])
            
            if filtros.get('fecha_hasta'):
                where_clauses.append("car.fecha_emision <= %s")
                params.append(filtros['fecha_hasta'])
            
            if filtros.get('cliente'):
                where_clauses.append("UPPER(car.cliente) LIKE UPPER(%s)")
                params.append(f"%{filtros['cliente']}%")
            
            if filtros.get('estado'):
                where_clauses.append("car.estado = %s")
                params.append(filtros['estado'])
            
            if filtros.get('banco_id'):
                where_clauses.append("car.banco_id = %s")
                params.append(filtros['banco_id'])
        
        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)
        
        cur.execute(f"""
            SELECT COUNT(*) 
            FROM cuentas_a_recibir car
            {where_sql}
        """, params)
        
        return cur.fetchone()[0]
    finally:
        cur.close()
        conn.close()


def obtener_cuenta_a_recibir_por_id(cuenta_id):
    """Obtiene una cuenta a recibir por su ID"""
    conn, cur = conectar()
    try:
        cur.execute("""
            SELECT 
                car.*,
                td.nombre AS documento_nombre,
                b.nombre AS banco_nombre,
                ci.nombre AS cuenta_nombre,
                p.nombre AS proyecto_nombre
            FROM cuentas_a_recibir car
            LEFT JOIN tipos_documentos td ON car.documento_id = td.id
            LEFT JOIN bancos b ON car.banco_id = b.id
            LEFT JOIN categorias_ingresos ci ON car.cuenta_id = ci.id
            LEFT JOIN proyectos p ON car.proyecto_id = p.id
            WHERE car.id = %s
        """, (cuenta_id,))
        return cur.fetchone()
    finally:
        cur.close()
        conn.close()


def calcular_status_recibo(fecha_vencimiento, fecha_recibo):
    """Calcula el status del recibo: ADELANTADO, ATRASADO, EN DIA"""
    if not fecha_vencimiento or not fecha_recibo:
        return None
    
    from datetime import date as date_type
    if isinstance(fecha_vencimiento, str):
        fecha_vencimiento = datetime.strptime(fecha_vencimiento, "%Y-%m-%d").date()
    elif hasattr(fecha_vencimiento, 'date'):
        fecha_vencimiento = fecha_vencimiento.date() if hasattr(fecha_vencimiento, 'date') else fecha_vencimiento
    
    if isinstance(fecha_recibo, str):
        fecha_recibo = datetime.strptime(fecha_recibo, "%Y-%m-%d").date()
    elif hasattr(fecha_recibo, 'date'):
        fecha_recibo = fecha_recibo.date() if hasattr(fecha_recibo, 'date') else fecha_recibo
    
    if fecha_recibo < fecha_vencimiento:
        return 'ADELANTADO'
    elif fecha_recibo > fecha_vencimiento:
        return 'ATRASADO'
    else:
        return 'EN DIA'


def crear_cuenta_a_recibir(fecha_emision, documento_id=None, cuenta_id=None, plano_cuenta=None, tipo='RECURRENTE',
                           cliente=None, factura=None, descripcion=None, banco_id=None, valor=0,
                           cuotas=None, valor_cuota=None, vencimiento=None, fecha_recibo=None,
                           estado='ABIERTO', proyecto_id=None):
    """Crea una nueva cuenta a recibir"""
    conn, cur = conectar()
    try:
        # Convertir a mayúsculas
        plano_cuenta = _to_upper(plano_cuenta) if plano_cuenta else None
        tipo = _to_upper(tipo) if tipo else 'RECURRENTE'
        cliente = _to_upper(cliente) if cliente else None
        factura = _to_upper(factura) if factura else None
        descripcion = _to_upper(descripcion) if descripcion else None
        
        # Determinar estado automáticamente si no se proporciona
        if estado is None or estado == '':
            estado = 'RECIBIDO' if fecha_recibo else 'ABIERTO'
        estado = _to_upper(estado) if estado else 'ABIERTO'
        
        # Calcular status_recibo automáticamente si hay fecha_recibo y vencimiento
        status_recibo = None
        if fecha_recibo and vencimiento:
            status_recibo = calcular_status_recibo(vencimiento, fecha_recibo)
        
        cur.execute("""
            INSERT INTO cuentas_a_recibir (
                fecha_emision, documento_id, cuenta_id, plano_cuenta, tipo, cliente, factura, descripcion,
                banco_id, valor, cuotas, valor_cuota, vencimiento, fecha_recibo,
                estado, status_recibo, proyecto_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            fecha_emision, documento_id, cuenta_id, plano_cuenta, tipo, cliente, factura, descripcion,
            banco_id, valor, cuotas, valor_cuota, vencimiento, fecha_recibo,
            estado, status_recibo, proyecto_id
        ))
        
        cuenta_id = cur.fetchone()['id']
        conn.commit()
        return cuenta_id
    except Exception as e:
        conn.rollback()
        print(f"Error al crear cuenta a recibir: {e}")
        raise
    finally:
        cur.close()
        conn.close()


def actualizar_cuenta_a_recibir(cuenta_id, fecha_emision=None, documento_id=None, cuenta_categoria_id=None, plano_cuenta=None,
                                tipo=None, cliente=None, factura=None, descripcion=None, banco_id=None,
                                valor=None, cuotas=None, valor_cuota=None, vencimiento=None,
                                fecha_recibo=None, estado=None, proyecto_id=None, actualizar_fecha_recibo=False):
    """Actualiza una cuenta a recibir"""
    conn, cur = conectar()
    try:
        updates = []
        params = []
        
        if fecha_emision is not None:
            updates.append("fecha_emision = %s")
            params.append(fecha_emision)
        
        if documento_id is not None:
            updates.append("documento_id = %s")
            params.append(documento_id)
        
        if cuenta_categoria_id is not None:
            updates.append("cuenta_id = %s")
            params.append(cuenta_categoria_id)
        
        if plano_cuenta is not None:
            updates.append("plano_cuenta = %s")
            params.append(_to_upper(plano_cuenta))
        
        if tipo is not None:
            updates.append("tipo = %s")
            params.append(_to_upper(tipo))
        
        if cliente is not None:
            updates.append("cliente = %s")
            params.append(_to_upper(cliente))
        
        if factura is not None:
            updates.append("factura = %s")
            params.append(_to_upper(factura))
        
        if descripcion is not None:
            updates.append("descripcion = %s")
            params.append(_to_upper(descripcion))
        
        if banco_id is not None:
            updates.append("banco_id = %s")
            params.append(banco_id)
        
        if valor is not None:
            updates.append("valor = %s")
            params.append(valor)
        
        if cuotas is not None:
            updates.append("cuotas = %s")
            params.append(cuotas)
        
        if valor_cuota is not None:
            updates.append("valor_cuota = %s")
            params.append(valor_cuota)
        
        if vencimiento is not None:
            updates.append("vencimiento = %s")
            params.append(vencimiento)
        
        # Actualizar fecha_recibo si se pasa explícitamente (incluso si es None para borrarlo)
        if actualizar_fecha_recibo or fecha_recibo is not None:
            updates.append("fecha_recibo = %s")
            params.append(fecha_recibo)
        
        if proyecto_id is not None:
            updates.append("proyecto_id = %s")
            params.append(proyecto_id)
        
        # Calcular estado automáticamente si se actualiza fecha_recibo
        if actualizar_fecha_recibo or fecha_recibo is not None:
            # Si hay fecha_recibo, estado es RECIBIDO, si no, ABIERTO
            nuevo_estado = 'RECIBIDO' if fecha_recibo else 'ABIERTO'
            updates.append("estado = %s")
            params.append(nuevo_estado)
        elif estado is not None:
            updates.append("estado = %s")
            params.append(_to_upper(estado))
        
        # Recalcular status_recibo si se actualizó vencimiento o fecha_recibo
        if vencimiento is not None or actualizar_fecha_recibo or fecha_recibo is not None:
            # Obtener valores actuales
            cur.execute("SELECT vencimiento, fecha_recibo FROM cuentas_a_recibir WHERE id = %s", (cuenta_id,))
            actual = cur.fetchone()
            ven = vencimiento if vencimiento is not None else actual['vencimiento']
            rec = fecha_recibo if (actualizar_fecha_recibo or fecha_recibo is not None) else actual['fecha_recibo']
            
            if ven and rec:
                status_recibo = calcular_status_recibo(ven, rec)
                updates.append("status_recibo = %s")
                params.append(status_recibo)
            elif (actualizar_fecha_recibo or fecha_recibo is not None) and not fecha_recibo:
                # Si se borró fecha_recibo, también borrar status_recibo
                updates.append("status_recibo = NULL")
        
        if updates:
            updates.append("actualizado_en = CURRENT_TIMESTAMP")
            params.append(cuenta_id)
            
            cur.execute(f"""
                UPDATE cuentas_a_recibir
                SET {', '.join(updates)}
                WHERE id = %s
            """, params)
            conn.commit()
            return cur.rowcount > 0
    except Exception as e:
        conn.rollback()
        print(f"Error al actualizar cuenta a recibir: {e}")
        raise
    finally:
        cur.close()
        conn.close()


def eliminar_cuenta_a_recibir(cuenta_id):
    """Elimina una cuenta a recibir"""
    conn, cur = conectar()
    try:
        cur.execute("DELETE FROM cuentas_a_recibir WHERE id = %s", (cuenta_id,))
        conn.commit()
        return cur.rowcount > 0
    except Exception as e:
        conn.rollback()
        print(f"Error al eliminar cuenta a recibir: {e}")
        raise
    finally:
        cur.close()
        conn.close()


def agregar_pago_cuenta_a_recibir(cuenta_id, monto_pago, fecha_pago):
    """Agrega un pago a una cuenta a recibir (suma al monto_abonado existente y actualiza fecha_recibo)"""
    conn, cur = conectar()
    try:
        # Obtener datos actuales de la cuenta
        cur.execute("SELECT monto_abonado, vencimiento, valor_cuota, valor FROM cuentas_a_recibir WHERE id = %s", (cuenta_id,))
        cuenta = cur.fetchone()
        if not cuenta:
            raise ValueError("Cuenta a recibir no encontrada")
        
        # Convertir monto_abonado_actual a float (puede venir como Decimal de PostgreSQL)
        monto_abonado_actual = float(cuenta['monto_abonado'] or 0)
        vencimiento = cuenta['vencimiento']
        valor_cuota = cuenta['valor_cuota']
        valor = cuenta['valor']
        
        # Convertir monto_pago a float
        monto_pago_float = float(monto_pago)
        
        # Sumar el nuevo pago al monto abonado existente
        nuevo_monto_abonado = monto_abonado_actual + monto_pago_float
        
        # Calcular status_recibo si hay vencimiento
        status_recibo = None
        if vencimiento and fecha_pago:
            status_recibo = calcular_status_recibo(vencimiento, fecha_pago)
        
        # Determinar si el estado debe cambiar a RECIBIDO
        # Calcular el saldo: saldo = (valor_cuota o valor) - monto_abonado
        # Solo cambiar a RECIBIDO si el saldo <= 0 (no hay saldo pendiente)
        monto_comparar = valor_cuota if valor_cuota is not None else valor
        nuevo_estado = None
        if monto_comparar:
            monto_comparar_float = float(monto_comparar) if monto_comparar else 0
            saldo = abs(monto_comparar_float) - nuevo_monto_abonado
            # Solo cambiar a RECIBIDO si no hay saldo pendiente (saldo <= 0)
            if saldo <= 0:
                nuevo_estado = 'RECIBIDO'
            else:
                # Si hay saldo pendiente, asegurar que esté en ABIERTO
                nuevo_estado = 'ABIERTO'
        
        # Actualizar monto_abonado, fecha_recibo, status_recibo y posiblemente estado
        updates = ["monto_abonado = %s", "fecha_recibo = %s", "status_recibo = %s", "actualizado_en = CURRENT_TIMESTAMP"]
        params = [nuevo_monto_abonado, fecha_pago, status_recibo]
        
        if nuevo_estado:
            updates.append("estado = %s")
            params.append(nuevo_estado)
        
        params.append(cuenta_id)
        
        cur.execute(f"""
            UPDATE cuentas_a_recibir 
            SET {', '.join(updates)}
            WHERE id = %s
        """, params)
        
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"Error al agregar pago a cuenta a recibir: {e}")
        raise
    finally:
        cur.close()
        conn.close()


# ==================== FUNCIONES PARA CUENTAS A PAGAR ====================

def obtener_cuentas_a_pagar(filtros=None, limite=None, offset=None):
    """Obtiene todas las cuentas a pagar con filtros opcionales y paginación"""
    conn, cur = conectar()
    try:
        where_clauses = []
        params = []
        
        if filtros:
            if filtros.get('fecha_desde'):
                where_clauses.append("cap.fecha_emision >= %s")
                params.append(filtros['fecha_desde'])
            
            if filtros.get('fecha_hasta'):
                where_clauses.append("cap.fecha_emision <= %s")
                params.append(filtros['fecha_hasta'])
            
            if filtros.get('proveedor'):
                where_clauses.append("UPPER(cap.proveedor) LIKE UPPER(%s)")
                params.append(f"%{filtros['proveedor']}%")
            
            if filtros.get('estado'):
                where_clauses.append("cap.estado = %s")
                params.append(filtros['estado'])
            
            if filtros.get('banco_id'):
                where_clauses.append("cap.banco_id = %s")
                params.append(filtros['banco_id'])
        
        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)
        
        # Agregar LIMIT y OFFSET si se proporcionan
        limit_sql = ""
        if limite is not None:
            limit_sql = f" LIMIT {limite}"
            if offset is not None:
                limit_sql += f" OFFSET {offset}"
        
        cur.execute(f"""
            SELECT 
                cap.*,
                td.nombre AS documento_nombre,
                b.nombre AS banco_nombre,
                cg.nombre AS cuenta_nombre,
                p.nombre AS proyecto_nombre,
                COALESCE(cap.monto_abonado, 0) AS monto_abonado,
                (COALESCE(cap.valor_cuota, cap.valor, 0) - COALESCE(cap.monto_abonado, 0)) AS saldo
            FROM cuentas_a_pagar cap
            LEFT JOIN tipos_documentos td ON cap.documento_id = td.id
            LEFT JOIN bancos b ON cap.banco_id = b.id
            LEFT JOIN categorias_gastos cg ON cap.cuenta_id = cg.id
            LEFT JOIN proyectos p ON cap.proyecto_id = p.id
            {where_sql}
            ORDER BY cap.fecha_emision DESC, cap.id DESC
            {limit_sql}
        """, params)
        
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()


def contar_cuentas_a_pagar(filtros=None):
    """Cuenta el total de cuentas a pagar con filtros opcionales"""
    conn, cur = conectar()
    try:
        where_clauses = []
        params = []
        
        if filtros:
            if filtros.get('fecha_desde'):
                where_clauses.append("cap.fecha_emision >= %s")
                params.append(filtros['fecha_desde'])
            
            if filtros.get('fecha_hasta'):
                where_clauses.append("cap.fecha_emision <= %s")
                params.append(filtros['fecha_hasta'])
            
            if filtros.get('proveedor'):
                where_clauses.append("UPPER(cap.proveedor) LIKE UPPER(%s)")
                params.append(f"%{filtros['proveedor']}%")
            
            if filtros.get('estado'):
                where_clauses.append("cap.estado = %s")
                params.append(filtros['estado'])
            
            if filtros.get('banco_id'):
                where_clauses.append("cap.banco_id = %s")
                params.append(filtros['banco_id'])
        
        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)
        
        cur.execute(f"""
            SELECT COUNT(*) 
            FROM cuentas_a_pagar cap
            {where_sql}
        """, params)
        
        return cur.fetchone()[0]
    finally:
        cur.close()
        conn.close()


def obtener_cuenta_a_pagar_por_id(cuenta_id):
    """Obtiene una cuenta a pagar por su ID"""
    conn, cur = conectar()
    try:
        cur.execute("""
            SELECT 
                cap.*,
                td.nombre AS documento_nombre,
                b.nombre AS banco_nombre,
                cg.nombre AS cuenta_nombre,
                p.nombre AS proyecto_nombre
            FROM cuentas_a_pagar cap
            LEFT JOIN tipos_documentos td ON cap.documento_id = td.id
            LEFT JOIN bancos b ON cap.banco_id = b.id
            LEFT JOIN categorias_gastos cg ON cap.cuenta_id = cg.id
            LEFT JOIN proyectos p ON cap.proyecto_id = p.id
            WHERE cap.id = %s
        """, (cuenta_id,))
        
        return cur.fetchone()
    finally:
        cur.close()
        conn.close()


def crear_cuenta_a_pagar(fecha_emision, documento_id=None, cuenta_id=None, plano_cuenta=None, tipo='RECURRENTE',
                           proveedor=None, factura=None, descripcion=None, banco_id=None, valor=0,
                           cuotas=None, valor_cuota=None, vencimiento=None, fecha_pago=None,
                           estado='ABIERTO', proyecto_id=None):
    """Crea una nueva cuenta a pagar"""
    conn, cur = conectar()
    try:
        # Convertir a mayúsculas
        plano_cuenta = _to_upper(plano_cuenta) if plano_cuenta else None
        tipo = _to_upper(tipo) if tipo else 'RECURRENTE'
        proveedor = _to_upper(proveedor) if proveedor else None
        factura = _to_upper(factura) if factura else None
        descripcion = _to_upper(descripcion) if descripcion else None
        
        # Determinar estado automáticamente si no se proporciona
        if estado is None or estado == '':
            estado = 'PAGADO' if fecha_pago else 'ABIERTO'
        estado = _to_upper(estado) if estado else 'ABIERTO'
        
        # Calcular status_pago automáticamente si hay fecha_pago y vencimiento
        status_pago = None
        if fecha_pago and vencimiento:
            status_pago = calcular_status_recibo(vencimiento, fecha_pago)  # Reutilizamos la misma función
        
        # Si es FCON (al contado), establecer monto_abonado igual al valor_cuota (o valor si no hay valor_cuota)
        monto_abonado = None
        if tipo == 'FCON':
            # Si hay valor_cuota, usar ese valor; si no, usar el valor total
            monto_abonado = valor_cuota if valor_cuota is not None else valor
            # Asegurar que sea positivo (absoluto)
            if monto_abonado is not None:
                monto_abonado = abs(monto_abonado)
        
        cur.execute("""
            INSERT INTO cuentas_a_pagar (
                fecha_emision, documento_id, cuenta_id, plano_cuenta, tipo, proveedor, factura, descripcion,
                banco_id, valor, cuotas, valor_cuota, vencimiento, fecha_pago,
                estado, status_pago, proyecto_id, monto_abonado
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            fecha_emision, documento_id, cuenta_id, plano_cuenta, tipo, proveedor, factura, descripcion,
            banco_id, valor, cuotas, valor_cuota, vencimiento, fecha_pago,
            estado, status_pago, proyecto_id, monto_abonado
        ))
        
        cuenta_id = cur.fetchone()['id']
        conn.commit()
        return cuenta_id
    except Exception as e:
        conn.rollback()
        print(f"Error al crear cuenta a pagar: {e}")
        raise
    finally:
        cur.close()
        conn.close()


def actualizar_cuenta_a_pagar(cuenta_id, fecha_emision=None, documento_id=None, cuenta_categoria_id=None, plano_cuenta=None,
                                tipo=None, proveedor=None, factura=None, descripcion=None, banco_id=None,
                                valor=None, cuotas=None, valor_cuota=None, vencimiento=None,
                                fecha_pago=None, estado=None, proyecto_id=None, actualizar_fecha_pago=False):
    """Actualiza una cuenta a pagar"""
    conn, cur = conectar()
    try:
        updates = []
        params = []
        
        if fecha_emision is not None:
            updates.append("fecha_emision = %s")
            params.append(fecha_emision)
        
        if documento_id is not None:
            updates.append("documento_id = %s")
            params.append(documento_id)
        
        if cuenta_categoria_id is not None:
            updates.append("cuenta_id = %s")
            params.append(cuenta_categoria_id)
        
        if plano_cuenta is not None:
            updates.append("plano_cuenta = %s")
            params.append(_to_upper(plano_cuenta))
        
        if tipo is not None:
            updates.append("tipo = %s")
            params.append(_to_upper(tipo))
        
        if proveedor is not None:
            updates.append("proveedor = %s")
            params.append(_to_upper(proveedor))
        
        if factura is not None:
            updates.append("factura = %s")
            params.append(_to_upper(factura))
        
        if descripcion is not None:
            updates.append("descripcion = %s")
            params.append(_to_upper(descripcion))
        
        if banco_id is not None:
            updates.append("banco_id = %s")
            params.append(banco_id)
        
        if valor is not None:
            updates.append("valor = %s")
            params.append(valor)
        
        if cuotas is not None:
            updates.append("cuotas = %s")
            params.append(cuotas)
        
        if valor_cuota is not None:
            updates.append("valor_cuota = %s")
            params.append(valor_cuota)
        
        if vencimiento is not None:
            updates.append("vencimiento = %s")
            params.append(vencimiento)
        
        # Actualizar fecha_pago si se pasa explícitamente (incluso si es None para borrarlo)
        if actualizar_fecha_pago or fecha_pago is not None:
            updates.append("fecha_pago = %s")
            params.append(fecha_pago)
        
        if proyecto_id is not None:
            updates.append("proyecto_id = %s")
            params.append(proyecto_id)
        
        # Calcular estado automáticamente si se actualiza fecha_pago
        if actualizar_fecha_pago or fecha_pago is not None:
            # Si hay fecha_pago, estado es PAGADO, si no, ABIERTO
            nuevo_estado = 'PAGADO' if fecha_pago else 'ABIERTO'
            updates.append("estado = %s")
            params.append(nuevo_estado)
        elif estado is not None:
            updates.append("estado = %s")
            params.append(_to_upper(estado))
        
        # Recalcular status_pago si se actualizó vencimiento o fecha_pago
        if vencimiento is not None or actualizar_fecha_pago or fecha_pago is not None:
            # Obtener valores actuales
            cur.execute("SELECT vencimiento, fecha_pago FROM cuentas_a_pagar WHERE id = %s", (cuenta_id,))
            actual = cur.fetchone()
            ven = vencimiento if vencimiento is not None else actual['vencimiento']
            pag = fecha_pago if (actualizar_fecha_pago or fecha_pago is not None) else actual['fecha_pago']
            
            if ven and pag:
                status_pago = calcular_status_recibo(ven, pag)  # Reutilizamos la misma función
                updates.append("status_pago = %s")
                params.append(status_pago)
            elif (actualizar_fecha_pago or fecha_pago is not None) and not fecha_pago:
                # Si se borró fecha_pago, también borrar status_pago
                updates.append("status_pago = NULL")
        
        if updates:
            updates.append("actualizado_en = CURRENT_TIMESTAMP")
            params.append(cuenta_id)
            
            cur.execute(f"""
                UPDATE cuentas_a_pagar
                SET {', '.join(updates)}
                WHERE id = %s
            """, params)
            
            conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Error al actualizar cuenta a pagar: {e}")
        raise
    finally:
        cur.close()
        conn.close()


def eliminar_cuenta_a_pagar(cuenta_id):
    """Elimina una cuenta a pagar"""
    conn, cur = conectar()
    try:
        cur.execute("DELETE FROM cuentas_a_pagar WHERE id = %s", (cuenta_id,))
        conn.commit()
        return cur.rowcount > 0
    except Exception as e:
        conn.rollback()
        print(f"Error al eliminar cuenta a pagar: {e}")
        raise
    finally:
        cur.close()
        conn.close()


def agregar_pago_cuenta_a_pagar(cuenta_id, monto_pago, fecha_pago):
    """Agrega un pago a una cuenta a pagar (suma al monto_abonado existente y actualiza fecha_pago)"""
    conn, cur = conectar()
    try:
        # Obtener datos actuales de la cuenta
        cur.execute("SELECT monto_abonado, vencimiento, valor_cuota, valor FROM cuentas_a_pagar WHERE id = %s", (cuenta_id,))
        cuenta = cur.fetchone()
        if not cuenta:
            raise ValueError("Cuenta a pagar no encontrada")
        
        # Convertir monto_abonado_actual a float (puede venir como Decimal de PostgreSQL)
        monto_abonado_actual = float(cuenta['monto_abonado'] or 0)
        vencimiento = cuenta['vencimiento']
        valor_cuota = cuenta['valor_cuota']
        valor = cuenta['valor']
        
        # Convertir monto_pago a float
        monto_pago_float = float(monto_pago)
        
        # Sumar el nuevo pago al monto abonado existente
        nuevo_monto_abonado = monto_abonado_actual + monto_pago_float
        
        # Calcular status_pago si hay vencimiento
        status_pago = None
        if vencimiento and fecha_pago:
            status_pago = calcular_status_recibo(vencimiento, fecha_pago)
        
        # Determinar si el estado debe cambiar a PAGADO
        # Calcular el saldo: saldo = (valor_cuota o valor) - monto_abonado
        # Solo cambiar a PAGADO si el saldo <= 0 (no hay saldo pendiente)
        monto_comparar = valor_cuota if valor_cuota is not None else valor
        nuevo_estado = None
        if monto_comparar:
            monto_comparar_float = float(monto_comparar) if monto_comparar else 0
            saldo = abs(monto_comparar_float) - nuevo_monto_abonado
            # Solo cambiar a PAGADO si no hay saldo pendiente (saldo <= 0)
            if saldo <= 0:
                nuevo_estado = 'PAGADO'
            else:
                # Si hay saldo pendiente, asegurar que esté en ABIERTO
                nuevo_estado = 'ABIERTO'
        
        # Actualizar monto_abonado, fecha_pago, status_pago y posiblemente estado
        updates = ["monto_abonado = %s", "fecha_pago = %s", "status_pago = %s", "actualizado_en = CURRENT_TIMESTAMP"]
        params = [nuevo_monto_abonado, fecha_pago, status_pago]
        
        if nuevo_estado:
            updates.append("estado = %s")
            params.append(nuevo_estado)
        
        params.append(cuenta_id)
        
        cur.execute(f"""
            UPDATE cuentas_a_pagar 
            SET {', '.join(updates)}
            WHERE id = %s
        """, params)
        
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"Error al agregar pago a cuenta a pagar: {e}")
        raise
    finally:
        cur.close()
        conn.close()


# ==================== FUNCIONES DE EXPORTACIÓN/IMPORTACIÓN CSV ====================

def exportar_cuentas_a_recibir_csv(filtros=None):
    """Exporta cuentas a recibir a formato CSV"""
    import csv
    import io
    from datetime import datetime
    
    cuentas = obtener_cuentas_a_recibir(filtros)
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Encabezados
    writer.writerow([
        'ID', 'Fecha Emisión', 'Documento', 'Cuenta', 'Plano de Cuenta', 'Proyecto',
        'Tipo', 'Cliente', 'Factura', 'Descripción', 'Banco', 'Valor', 'Cuotas', 'Valor Cuota',
        'Vencimiento', 'Fecha Recibo', 'Estado', 'Status Recibo'
    ])
    
    # Datos
    for cuenta in cuentas:
        writer.writerow([
            cuenta.get('id', ''),
            cuenta.get('fecha_emision').strftime('%d-%m-%Y') if cuenta.get('fecha_emision') else '',
            cuenta.get('documento_nombre', ''),
            cuenta.get('cuenta_nombre', ''),
            cuenta.get('plano_cuenta', ''),
            cuenta.get('proyecto_nombre', ''),
            cuenta.get('tipo', ''),
            cuenta.get('cliente', ''),
            cuenta.get('factura', ''),
            cuenta.get('descripcion', ''),
            cuenta.get('banco_nombre', ''),
            str(cuenta.get('valor', 0)) if cuenta.get('valor') else '0',
            cuenta.get('cuotas', ''),
            str(cuenta.get('valor_cuota', 0)) if cuenta.get('valor_cuota') else '',
            cuenta.get('vencimiento').strftime('%d-%m-%Y') if cuenta.get('vencimiento') else '',
            cuenta.get('fecha_recibo').strftime('%d-%m-%Y') if cuenta.get('fecha_recibo') else '',
            cuenta.get('estado', ''),
            cuenta.get('status_recibo', '')
        ])
    
    output.seek(0)
    return output.getvalue()


def exportar_cuentas_a_pagar_csv(filtros=None):
    """Exporta cuentas a pagar a formato CSV"""
    import csv
    import io
    from datetime import datetime
    
    cuentas = obtener_cuentas_a_pagar(filtros)
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Encabezados
    writer.writerow([
        'ID', 'Fecha Emisión', 'Documento', 'Cuenta', 'Plano de Cuenta', 'Proyecto',
        'Tipo', 'Proveedor', 'Factura', 'Descripción', 'Banco', 'Valor', 'Cuotas', 'Valor Cuota',
        'Vencimiento', 'Fecha Pago', 'Estado', 'Status Pago'
    ])
    
    # Datos
    for cuenta in cuentas:
        writer.writerow([
            cuenta.get('id', ''),
            cuenta.get('fecha_emision').strftime('%d-%m-%Y') if cuenta.get('fecha_emision') else '',
            cuenta.get('documento_nombre', ''),
            cuenta.get('cuenta_nombre', ''),
            cuenta.get('plano_cuenta', ''),
            cuenta.get('proyecto_nombre', ''),
            cuenta.get('tipo', ''),
            cuenta.get('proveedor', ''),
            cuenta.get('factura', ''),
            cuenta.get('descripcion', ''),
            cuenta.get('banco_nombre', ''),
            str(cuenta.get('valor', 0)) if cuenta.get('valor') else '0',
            cuenta.get('cuotas', ''),
            str(cuenta.get('valor_cuota', 0)) if cuenta.get('valor_cuota') else '',
            cuenta.get('vencimiento').strftime('%d-%m-%Y') if cuenta.get('vencimiento') else '',
            cuenta.get('fecha_pago').strftime('%d-%m-%Y') if cuenta.get('fecha_pago') else '',
            cuenta.get('estado', ''),
            cuenta.get('status_pago', '')
        ])
    
    output.seek(0)
    return output.getvalue()


def importar_cuentas_a_recibir_csv(csv_content):
    """Importa cuentas a recibir desde CSV"""
    import csv
    import io
    from datetime import datetime
    
    cuentas_importadas = []
    errores = []
    
    reader = csv.DictReader(io.StringIO(csv_content))
    
    for idx, row in enumerate(reader, start=2):  # start=2 porque la fila 1 es el encabezado
        try:
            # Ignorar el campo ID si existe (siempre creamos nuevos registros)
            if 'ID' in row:
                del row['ID']
            if 'id' in row:
                del row['id']
            
            # Validar campos requeridos
            if not row.get('Fecha Emisión'):
                errores.append(f"Fila {idx}: Fecha Emisión es obligatoria")
                continue
            
            fecha_emision = datetime.strptime(row['Fecha Emisión'], '%d-%m-%Y').date()
            
            # Obtener IDs de relaciones
            documento_id = None
            if row.get('Documento'):
                documento = financiero.obtener_tipos_documentos(activo=True)
                doc = next((d for d in documento if d['nombre'].upper() == row['Documento'].upper()), None)
                if doc:
                    documento_id = doc['id']
            
            cuenta_id = None
            if row.get('Cuenta'):
                categorias = financiero.obtener_categorias_ingresos(activo=True)
                cat = next((c for c in categorias if c['nombre'].upper() == row['Cuenta'].upper()), None)
                if cat:
                    cuenta_id = cat['id']
            
            banco_id = None
            if row.get('Banco'):
                bancos = financiero.obtener_bancos(activo=True)
                banco = next((b for b in bancos if b['nombre'].upper() == row['Banco'].upper()), None)
                if banco:
                    banco_id = banco['id']
            
            proyecto_id = None
            if row.get('Proyecto'):
                proyectos = financiero.obtener_proyectos(activo=True)
                proyecto = next((p for p in proyectos if p['nombre'].upper() == row['Proyecto'].upper()), None)
                if proyecto:
                    proyecto_id = proyecto['id']
            
            valor = float(row.get('Valor', 0).replace(',', '.')) if row.get('Valor') else 0
            valor_cuota = float(row.get('Valor Cuota', 0).replace(',', '.')) if row.get('Valor Cuota') else None
            
            tipo = _to_upper(row.get('Tipo', 'RECURRENTE').strip() or 'RECURRENTE')
            
            # Si es NCRE, hacer el valor y valor_cuota negativos
            if tipo == 'NCRE':
                valor = -abs(valor)
                if valor_cuota is not None:
                    valor_cuota = -abs(valor_cuota)
            
            vencimiento = None
            if row.get('Vencimiento'):
                vencimiento = datetime.strptime(row['Vencimiento'], '%d-%m-%Y').date()
            
            fecha_recibo = None
            if row.get('Fecha Recibo'):
                fecha_recibo = datetime.strptime(row['Fecha Recibo'], '%d-%m-%Y').date()
            
            cuenta_id_creado = crear_cuenta_a_recibir(
                fecha_emision=fecha_emision,
                documento_id=documento_id,
                cuenta_id=cuenta_id,
                plano_cuenta=_to_upper(row.get('Plano de Cuenta', '').strip() or None),
                tipo=tipo,
                cliente=_to_upper(row.get('Cliente', '').strip() or None),
                factura=_to_upper(row.get('Factura', '').strip() or None),
                descripcion=_to_upper(row.get('Descripción', '').strip() or None),
                banco_id=banco_id,
                valor=valor,
                cuotas=_to_upper(row.get('Cuotas', '').strip() or None),
                valor_cuota=valor_cuota,
                vencimiento=vencimiento,
                fecha_recibo=fecha_recibo,
                estado=_to_upper(row.get('Estado', 'ABIERTO').strip() or 'ABIERTO'),
                proyecto_id=proyecto_id
            )
            
            cuentas_importadas.append(cuenta_id_creado)
            
        except Exception as e:
            errores.append(f"Fila {idx}: {str(e)}")
    
    return cuentas_importadas, errores


def importar_cuentas_a_pagar_csv(csv_content):
    """Importa cuentas a pagar desde CSV"""
    import csv
    import io
    from datetime import datetime
    
    cuentas_importadas = []
    errores = []
    
    reader = csv.DictReader(io.StringIO(csv_content))
    
    for idx, row in enumerate(reader, start=2):  # start=2 porque la fila 1 es el encabezado
        try:
            # Ignorar el campo ID si existe (siempre creamos nuevos registros)
            if 'ID' in row:
                del row['ID']
            if 'id' in row:
                del row['id']
            
            # Validar campos requeridos
            if not row.get('Fecha Emisión'):
                errores.append(f"Fila {idx}: Fecha Emisión es obligatoria")
                continue
            
            fecha_emision = datetime.strptime(row['Fecha Emisión'], '%d-%m-%Y').date()
            
            # Obtener IDs de relaciones
            documento_id = None
            if row.get('Documento'):
                documentos = obtener_tipos_documentos(activo=True)
                doc = next((d for d in documentos if d['nombre'].upper() == row['Documento'].upper()), None)
                if doc:
                    documento_id = doc['id']
            
            cuenta_id = None
            if row.get('Cuenta'):
                categorias = obtener_categorias_gastos(activo=True)
                cat = next((c for c in categorias if c['nombre'].upper() == row['Cuenta'].upper()), None)
                if cat:
                    cuenta_id = cat['id']
            
            banco_id = None
            if row.get('Banco'):
                bancos = obtener_bancos(activo=True)
                banco = next((b for b in bancos if b['nombre'].upper() == row['Banco'].upper()), None)
                if banco:
                    banco_id = banco['id']
            
            proyecto_id = None
            if row.get('Proyecto'):
                proyectos = obtener_proyectos(activo=True)
                proyecto = next((p for p in proyectos if p['nombre'].upper() == row['Proyecto'].upper()), None)
                if proyecto:
                    proyecto_id = proyecto['id']
            
            valor = float(row.get('Valor', 0).replace(',', '.')) if row.get('Valor') else 0
            valor_cuota = float(row.get('Valor Cuota', 0).replace(',', '.')) if row.get('Valor Cuota') else None
            
            tipo = _to_upper(row.get('Tipo', 'RECURRENTE').strip() or 'RECURRENTE')
            
            # Si es NCRE, hacer el valor y valor_cuota negativos
            if tipo == 'NCRE':
                valor = -abs(valor)
                if valor_cuota is not None:
                    valor_cuota = -abs(valor_cuota)
            
            vencimiento = None
            if row.get('Vencimiento'):
                vencimiento = datetime.strptime(row['Vencimiento'], '%d-%m-%Y').date()
            
            fecha_pago = None
            if row.get('Fecha Pago'):
                fecha_pago = datetime.strptime(row['Fecha Pago'], '%d-%m-%Y').date()
            
            cuenta_id_creado = crear_cuenta_a_pagar(
                fecha_emision=fecha_emision,
                documento_id=documento_id,
                cuenta_id=cuenta_id,
                plano_cuenta=_to_upper(row.get('Plano de Cuenta', '').strip() or None),
                tipo=tipo,
                proveedor=_to_upper(row.get('Proveedor', '').strip() or None),
                factura=_to_upper(row.get('Factura', '').strip() or None),
                descripcion=_to_upper(row.get('Descripción', '').strip() or None),
                banco_id=banco_id,
                valor=valor,
                cuotas=_to_upper(row.get('Cuotas', '').strip() or None),
                valor_cuota=valor_cuota,
                vencimiento=vencimiento,
                fecha_pago=fecha_pago,
                estado=_to_upper(row.get('Estado', 'ABIERTO').strip() or 'ABIERTO'),
                proyecto_id=proyecto_id
            )
            
            cuentas_importadas.append(cuenta_id_creado)
            
        except Exception as e:
            errores.append(f"Fila {idx}: {str(e)}")
    
    return cuentas_importadas, errores


def previsualizar_cuentas_a_pagar_csv(csv_content):
    """Previsualiza cuentas a pagar desde CSV sin guardarlas"""
    import csv
    import io
    from datetime import datetime
    
    datos_previsualizacion = []
    errores = []
    
    reader = csv.DictReader(io.StringIO(csv_content))
    
    for idx, row in enumerate(reader, start=2):
        fila_data = {
            'fila': idx,
            'valida': True,
            'errores': [],
            'datos': {}
        }
        
        try:
            if 'ID' in row:
                del row['ID']
            if 'id' in row:
                del row['id']
            
            if not row.get('Fecha Emisión'):
                fila_data['valida'] = False
                fila_data['errores'].append('Fecha Emisión es obligatoria')
                errores.append(f"Fila {idx}: Fecha Emisión es obligatoria")
            
            fecha_emision = None
            if row.get('Fecha Emisión'):
                try:
                    fecha_emision = datetime.strptime(row['Fecha Emisión'], '%d-%m-%Y').date()
                except ValueError:
                    fila_data['valida'] = False
                    fila_data['errores'].append(f'Fecha Emisión inválida: {row.get("Fecha Emisión")}')
            
            documento_nombre = row.get('Documento', '')
            documento_id = None
            if documento_nombre:
                documentos = obtener_tipos_documentos(activo=True)
                doc = next((d for d in documentos if d['nombre'].upper() == documento_nombre.upper()), None)
                if not doc:
                    fila_data['valida'] = False
                    fila_data['errores'].append(f'Documento no encontrado: {documento_nombre}')
                else:
                    documento_id = doc['id']
            
            cuenta_nombre = row.get('Cuenta', '')
            cuenta_id = None
            if cuenta_nombre:
                categorias = obtener_categorias_gastos(activo=True)
                cat = next((c for c in categorias if c['nombre'].upper() == cuenta_nombre.upper()), None)
                if not cat:
                    fila_data['valida'] = False
                    fila_data['errores'].append(f'Cuenta no encontrada: {cuenta_nombre}')
                else:
                    cuenta_id = cat['id']
            
            banco_nombre = row.get('Banco', '')
            banco_id = None
            if banco_nombre:
                bancos = obtener_bancos(activo=True)
                banco = next((b for b in bancos if b['nombre'].upper() == banco_nombre.upper()), None)
                if not banco:
                    fila_data['valida'] = False
                    fila_data['errores'].append(f'Banco no encontrado: {banco_nombre}')
                else:
                    banco_id = banco['id']
            
            proyecto_nombre = row.get('Proyecto', '')
            proyecto_id = None
            if proyecto_nombre:
                proyectos = obtener_proyectos(activo=True)
                proyecto = next((p for p in proyectos if p['nombre'].upper() == proyecto_nombre.upper()), None)
                if not proyecto:
                    fila_data['valida'] = False
                    fila_data['errores'].append(f'Proyecto no encontrado: {proyecto_nombre}')
                else:
                    proyecto_id = proyecto['id']
            
            valor = None
            if row.get('Valor'):
                try:
                    valor = float(row.get('Valor', 0).replace(',', '.'))
                except ValueError:
                    fila_data['valida'] = False
                    fila_data['errores'].append(f'Valor inválido: {row.get("Valor")}')
            
            valor_cuota = None
            if row.get('Valor Cuota'):
                try:
                    valor_cuota = float(row.get('Valor Cuota', 0).replace(',', '.'))
                except ValueError:
                    fila_data['valida'] = False
                    fila_data['errores'].append(f'Valor Cuota inválido: {row.get("Valor Cuota")}')
            
            vencimiento = None
            if row.get('Vencimiento'):
                try:
                    vencimiento = datetime.strptime(row['Vencimiento'], '%d-%m-%Y').date()
                except ValueError:
                    fila_data['valida'] = False
                    fila_data['errores'].append(f'Vencimiento inválido: {row.get("Vencimiento")}')
            
            fecha_pago = None
            if row.get('Fecha Pago'):
                try:
                    fecha_pago = datetime.strptime(row['Fecha Pago'], '%d-%m-%Y').date()
                except ValueError:
                    fila_data['valida'] = False
                    fila_data['errores'].append(f'Fecha Pago inválida: {row.get("Fecha Pago")}')
            
            fila_data['datos'] = {
                'fecha_emision': row.get('Fecha Emisión', ''),
                'documento': documento_nombre,
                'cuenta': cuenta_nombre,
                'plano_cuenta': _to_upper(row.get('Plano de Cuenta', '')),
                'proyecto': proyecto_nombre,
                'tipo': _to_upper(row.get('Tipo', 'RECURRENTE')),
                'proveedor': _to_upper(row.get('Proveedor', '')),
                'factura': _to_upper(row.get('Factura', '')),
                'descripcion': _to_upper(row.get('Descripción', '')),
                'banco': banco_nombre,
                'valor': row.get('Valor', ''),
                'cuotas': _to_upper(row.get('Cuotas', '')),
                'valor_cuota': row.get('Valor Cuota', ''),
                'vencimiento': row.get('Vencimiento', ''),
                'fecha_pago': row.get('Fecha Pago', ''),
                'estado': _to_upper(row.get('Estado', 'ABIERTO'))
            }
            
            if not fila_data['valida']:
                errores.append(f"Fila {idx}: {'; '.join(fila_data['errores'])}")
            
        except Exception as e:
            fila_data['valida'] = False
            fila_data['errores'].append(str(e))
            errores.append(f"Fila {idx}: {str(e)}")
        
        datos_previsualizacion.append(fila_data)
    
    return datos_previsualizacion, errores

