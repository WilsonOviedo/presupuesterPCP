from flask import Flask, request, render_template, redirect, url_for, jsonify
import io
from contextlib import redirect_stdout
from threading import Thread, Lock
import time
from urllib.parse import parse_qsl

# Reutilizamos la lógica existente sin levantar su servidor
import buscar_precios_web as precios
import leer_factura as facturas
import presupuestos_db as presupuestos
from flask import make_response
from datetime import datetime


app = Flask(__name__)


@app.route("/")
def menu():
    return render_template('menu.html')
_job_state = {"running": False, "output": "", "finished": False, "started_at": None}
_job_lock = Lock()

def _run_leer_facturas_job():
    buf = io.StringIO()
    with redirect_stdout(buf):
        try:
            facturas.procesar_correos()
        except Exception as e:
            print(f"❌ Error: {e}")
    # Guardar salida y marcar fin
    with _job_lock:
        _job_state["output"] = buf.getvalue()
        _job_state["running"] = False
        _job_state["finished"] = True


@app.route("/precios", methods=["GET"])
def precios_index():
    proveedor = request.args.get("proveedor") or None
    producto = request.args.get("producto") or None
    fecha_inicio_raw = request.args.get("fecha_inicio") or None
    fecha_fin_raw = request.args.get("fecha_fin") or None
    limite = request.args.get("limite") or "200"
    filtro = request.args.get("filtro") or "sin"
    margen_str = request.args.get("margen") or "0"
    try:
        limite = int(limite)
    except ValueError:
        limite = 200
    try:
        margen_val = float(margen_str)
    except ValueError:
        margen_val = 0.0

    rows = None
    if any((proveedor, producto, fecha_inicio_raw, fecha_fin_raw)) or request.args.get("limite") or request.args.get("filtro"):
        fi = precios.parse_fecha(fecha_inicio_raw, inicio=True)
        ff = precios.parse_fecha(fecha_fin_raw, inicio=False)
        conn, cur = precios.conectar()
        try:
            fetched = precios.buscar_precios_db(cur, proveedor=proveedor, producto=producto, fecha_inicio=fi, fecha_fin=ff, limite=limite, filtro=filtro)
        finally:
            cur.close()
            conn.close()
        # Enriquecer filas con precio_venta calculado
        rows = []
        for r in fetched or []:
            precio = r["precio"]
            proveedor_val = r["proveedor"]
            fecha_val = r["fecha"]
            producto_val = r["producto"]
            precio_venta = None
            try:
                if precio is not None and (100.0 - margen_val) != 0.0:
                    precio_venta = float(precio) * 100.0 / (100.0 - margen_val)
            except Exception:
                precio_venta = None
            rows.append({
                "proveedor": proveedor_val,
                "fecha": fecha_val,
                "producto": producto_val,
                "precio": precio,
                "precio_venta": precio_venta,
            })

    current_query = request.query_string.decode('utf-8') if request.query_string else ''

    return render_template('precios.html', rows=rows, request=request, current_query=current_query)


@app.route("/precios/materiales", methods=["POST"])
def precios_agregar_material():
    descripcion = (request.form.get("descripcion") or "").strip()
    proveedor = (request.form.get("proveedor") or "").strip()
    precio_str = request.form.get("precio") or "0"
    tiempo_str = request.form.get("tiempo_instalacion") or "0"
    return_query = request.form.get("return_query") or ""

    try:
        precio = float(precio_str)
    except ValueError:
        precio = 0.0
    try:
        tiempo_instalacion = float(tiempo_str)
    except ValueError:
        tiempo_instalacion = 0.0

    status = "error"
    if descripcion:
        try:
            _, updated = presupuestos.crear_o_actualizar_material(
                descripcion=descripcion,
                precio=precio,
                tiempo_instalacion=tiempo_instalacion,
                proveedor=proveedor or None,
            )
            status = "updated" if updated else "created"
        except Exception:
            status = "error"

    params = dict(parse_qsl(return_query)) if return_query else {}
    params["material_msg"] = status
    params["material_desc"] = descripcion
    return redirect(url_for('precios_index', **params))


@app.route("/leer-facturas", methods=["GET", "POST"])
def leer_facturas_page():
    if request.method == "POST":
        with _job_lock:
            if not _job_state["running"]:
                _job_state["running"] = True
                _job_state["finished"] = False
                _job_state["output"] = ""
                _job_state["started_at"] = time.time()
                t = Thread(target=_run_leer_facturas_job, daemon=True)
                t.start()
    with _job_lock:
        running = _job_state["running"]
        finished = _job_state["finished"]
        salida = _job_state["output"]
    return render_template('leer_facturas.html', salida=salida, running=running, finished=finished)

@app.route("/leer-facturas/status", methods=["GET"])
def leer_facturas_status():
    with _job_lock:
        return jsonify({
            "running": _job_state["running"],
            "finished": _job_state["finished"],
            "output": _job_state["output"],
        })


@app.route("/calculadora", methods=["GET"])
def calculadora():
    precio_str = request.args.get("precio")
    margen_str = request.args.get("margen")
    resultado = None
    try:
        if precio_str is not None and margen_str is not None:
            precio_val = float(precio_str)
            margen_val = float(margen_str)
            if (100.0 - margen_val) != 0.0:
                resultado = precio_val * 100.0 / (100.0 - margen_val)
    except ValueError:
        resultado = None
    return render_template('calculadora.html', request=request, resultado=resultado)

@app.route("/historial", methods=["GET"])
def historial():
    producto = request.args.get('producto')
    items = None
    if producto:
        conn, cur = precios.conectar()
        try:
            cur.execute(
                """
                SELECT DISTINCT producto, proveedor
                FROM precios
                WHERE producto ILIKE %s
                ORDER BY producto ASC, proveedor ASC
                LIMIT 50
                """,
                (f"%{producto}%",)
            )
            rows = cur.fetchall()
            items = [{"producto": r['producto'], "proveedor": r['proveedor']} for r in rows]
        finally:
            cur.close(); conn.close()
    return render_template('historial.html', items=items, producto=producto)

@app.route("/historial/data", methods=["GET"])
def historial_data():
    producto = request.args.get('producto')
    proveedor = request.args.get('proveedor')
    if not producto:
        return jsonify({"labels": [], "data": []})
    conn, cur = precios.conectar()
    try:
        if proveedor:
            cur.execute(
                """
                SELECT fecha, precio
                FROM precios
                WHERE producto = %s AND proveedor = %s
                ORDER BY fecha ASC NULLS LAST
                LIMIT 5000
                """,
                (producto, proveedor)
            )
        else:
            cur.execute(
                """
                SELECT fecha, precio
                FROM precios
                WHERE producto = %s
                ORDER BY fecha ASC NULLS LAST
                LIMIT 5000
                """,
                (producto,)
            )
        rows = cur.fetchall()
    finally:
        cur.close(); conn.close()
    labels = [r['fecha'].strftime('%Y-%m-%d') if r['fecha'] else '' for r in rows]
    data = [float(r['precio']) if r['precio'] is not None else None for r in rows]
    return jsonify({"labels": labels, "data": data, "producto": producto, "proveedor": proveedor})


# ==================== RUTAS DE PRESUPUESTOS ====================

@app.route("/presupuestos", methods=["GET"])
def presupuestos_index():
    """Lista de presupuestos"""
    estado = request.args.get("estado")
    cliente_id = request.args.get("cliente_id")
    try:
        cliente_id = int(cliente_id) if cliente_id else None
    except ValueError:
        cliente_id = None
    
    presupuestos_lista = presupuestos.obtener_presupuestos(estado=estado, cliente_id=cliente_id)
    clientes_lista = presupuestos.obtener_clientes()
    
    return render_template('presupuestos/index.html', 
                         presupuestos=presupuestos_lista, 
                         clientes=clientes_lista,
                         estado_filtro=estado,
                         cliente_filtro=cliente_id,
                         request=request)

@app.route("/presupuestos/nuevo", methods=["GET", "POST"])
def presupuestos_nuevo():
    """Crear nuevo presupuesto"""
    if request.method == "POST":
        cliente_id = request.form.get("cliente_id")
        try:
            cliente_id = int(cliente_id) if cliente_id else None
        except ValueError:
            cliente_id = None
        
        numero = request.form.get("numero_presupuesto") or presupuestos.generar_numero_presupuesto()
        titulo = request.form.get("titulo") or None
        descripcion = request.form.get("descripcion") or None
        estado = request.form.get("estado") or "borrador"
        fecha = request.form.get("fecha_presupuesto") or None
        validez_dias = request.form.get("validez_dias")
        try:
            validez_dias = int(validez_dias) if validez_dias else 30
        except ValueError:
            validez_dias = 30
        iva_porcentaje = request.form.get("iva_porcentaje")
        try:
            iva_porcentaje = float(iva_porcentaje) if iva_porcentaje else 21.0
        except ValueError:
            iva_porcentaje = 21.0
        notas = request.form.get("notas") or None
        
        presupuesto_id = presupuestos.crear_presupuesto(
            cliente_id=cliente_id,
            numero_presupuesto=numero,
            titulo=titulo,
            descripcion=descripcion,
            estado=estado,
            fecha_presupuesto=fecha,
            validez_dias=validez_dias,
            iva_porcentaje=iva_porcentaje,
            notas=notas
        )
        return redirect(url_for('presupuestos_ver', id=presupuesto_id))
    
    clientes_lista = presupuestos.obtener_clientes()
    numero_presupuesto = presupuestos.generar_numero_presupuesto()
    return render_template('presupuestos/form.html', 
                         presupuesto=None, 
                         clientes=clientes_lista,
                         numero_presupuesto=numero_presupuesto,
                         request=request)

@app.route("/presupuestos/<int:id>", methods=["GET"])
def presupuestos_ver(id):
    """Ver presupuesto"""
    presupuesto = presupuestos.obtener_presupuesto_por_id(id)
    if not presupuesto:
        return "Presupuesto no encontrado", 404
    
    items_servicio_raw = presupuestos.obtener_items_activos()
    items_servicio = []
    for item in items_servicio_raw:
        item_dict = dict(item)
        item_dict['precio_venta'] = float(item_dict.get('precio_venta') or item_dict.get('precio_base') or 0)
        item_dict['tiempo_instalacion'] = float(item_dict.get('tiempo_instalacion') or 0)
        item_dict['codigo'] = item_dict.get('codigo') or f"SERV-{item_dict.get('id')}"
        item_dict['unidad'] = item_dict.get('unidad') or 'unidad'
        items_servicio.append(item_dict)

    materiales_raw = presupuestos.obtener_materiales()
    items_materiales = []
    for material in materiales_raw:
        material_dict = dict(material)
        material_dict['precio_venta'] = float(material_dict.get('precio') or 0)
        material_dict['tiempo_instalacion'] = float(material_dict.get('tiempo_instalacion') or 0)
        material_dict['tipo'] = material_dict.get('tipo') or 'Material'
        material_dict['unidad'] = material_dict.get('unidad') or 'unidad'
        material_dict['codigo'] = material_dict.get('codigo') or f"MAT-{material_dict.get('id')}"
        items_materiales.append(material_dict)

    tipos_items = presupuestos.obtener_tipos_items()
    items_disponibles = items_servicio + items_materiales

    return render_template('presupuestos/ver.html', 
                         presupuesto=presupuesto, 
                         items_disponibles=items_disponibles,
                         items_servicio=items_servicio,
                         items_materiales=items_materiales,
                         tipos_items=tipos_items,
                         request=request)

@app.route("/presupuestos/<int:id>/editar", methods=["GET", "POST"])
def presupuestos_editar(id):
    """Editar presupuesto"""
    presupuesto = presupuestos.obtener_presupuesto_por_id(id)
    if not presupuesto:
        return "Presupuesto no encontrado", 404
    
    if request.method == "POST":
        cliente_id = request.form.get("cliente_id")
        try:
            cliente_id = int(cliente_id) if cliente_id else None
        except ValueError:
            cliente_id = None
        
        titulo = request.form.get("titulo") or None
        descripcion = request.form.get("descripcion") or None
        estado = request.form.get("estado") or "borrador"
        fecha = request.form.get("fecha_presupuesto") or None
        validez_dias = request.form.get("validez_dias")
        try:
            validez_dias = int(validez_dias) if validez_dias else None
        except ValueError:
            validez_dias = None
        iva_porcentaje = request.form.get("iva_porcentaje")
        try:
            iva_porcentaje = float(iva_porcentaje) if iva_porcentaje else None
        except ValueError:
            iva_porcentaje = None
        notas = request.form.get("notas") or None
        
        presupuestos.actualizar_presupuesto(
            presupuesto_id=id,
            cliente_id=cliente_id,
            titulo=titulo,
            descripcion=descripcion,
            estado=estado,
            fecha_presupuesto=fecha,
            validez_dias=validez_dias,
            iva_porcentaje=iva_porcentaje,
            notas=notas
        )
        return redirect(url_for('presupuestos_ver', id=id))
    
    clientes_lista = presupuestos.obtener_clientes()
    return render_template('presupuestos/form.html', 
                         presupuesto=presupuesto, 
                         clientes=clientes_lista,
                         request=request)

@app.route("/presupuestos/<int:id>/items/agregar", methods=["POST"])
def presupuestos_agregar_item(id):
    """Agregar item a presupuesto"""
    item_id = request.form.get("item_id")
    try:
        item_id = int(item_id) if item_id else None
    except ValueError:
        item_id = None

    material_id = request.form.get("material_id")
    try:
        material_id = int(material_id) if material_id else None
    except ValueError:
        material_id = None
    
    if not item_id and not material_id:
        return "Debe seleccionar un servicio o material", 400
    
    cantidad = request.form.get("cantidad")
    try:
        cantidad = float(cantidad) if cantidad else 1
    except ValueError:
        cantidad = 1
    
    precio_unitario = request.form.get("precio_unitario")
    try:
        precio_unitario = float(precio_unitario) if precio_unitario else None
    except ValueError:
        precio_unitario = None
    
    subgrupo_id = request.form.get("subgrupo_id")
    try:
        subgrupo_id = int(subgrupo_id) if subgrupo_id else None
    except ValueError:
        subgrupo_id = None
    
    numero_subitem = request.form.get("numero_subitem") or None
    tiempo_ejecucion_horas = request.form.get("tiempo_ejecucion_horas")
    try:
        tiempo_ejecucion_horas = float(tiempo_ejecucion_horas) if tiempo_ejecucion_horas not in (None, "") else None
    except ValueError:
        tiempo_ejecucion_horas = None
    
    orden = request.form.get("orden")
    try:
        orden = int(orden) if orden else 0
    except ValueError:
        orden = 0
    
    notas = request.form.get("notas") or None
    
    try:
        presupuestos.agregar_item_a_presupuesto(
            presupuesto_id=id,
            item_id=item_id,
            material_id=material_id,
            cantidad=cantidad,
            precio_unitario=precio_unitario,
            subgrupo_id=subgrupo_id,
            numero_subitem=numero_subitem,
            tiempo_ejecucion_horas=tiempo_ejecucion_horas,
            orden=orden,
            notas=notas
        )
    except Exception as e:
        return f"Error al agregar item: {str(e)}", 400
    
    return redirect(url_for('presupuestos_ver', id=id))

@app.route("/presupuestos/items/<int:item_id>/eliminar", methods=["POST"])
def presupuestos_eliminar_item(item_id):
    """Eliminar item de presupuesto"""
    presupuesto_id = request.form.get("presupuesto_id")
    try:
        presupuesto_id = int(presupuesto_id) if presupuesto_id else None
    except ValueError:
        return "Presupuesto ID inválido", 400
    
    if presupuestos.eliminar_item_de_presupuesto(item_id):
        return redirect(url_for('presupuestos_ver', id=presupuesto_id))
    return "Error al eliminar item", 400

@app.route("/presupuestos/items/<int:item_id>/actualizar", methods=["POST"])
def presupuestos_actualizar_item(item_id):
    """Actualizar item de presupuesto"""
    presupuesto_id = request.form.get("presupuesto_id")
    try:
        presupuesto_id = int(presupuesto_id) if presupuesto_id else None
    except ValueError:
        return "Presupuesto ID inválido", 400
    
    cantidad = request.form.get("cantidad")
    try:
        cantidad = float(cantidad) if cantidad else None
    except ValueError:
        cantidad = None
    
    precio_unitario = request.form.get("precio_unitario")
    try:
        precio_unitario = float(precio_unitario) if precio_unitario else None
    except ValueError:
        precio_unitario = None
    
    subgrupo_id = request.form.get("subgrupo_id")
    try:
        subgrupo_id = int(subgrupo_id) if subgrupo_id else None
    except ValueError:
        subgrupo_id = None
    
    numero_subitem = request.form.get("numero_subitem")
    tiempo_ejecucion_horas = request.form.get("tiempo_ejecucion_horas")
    try:
        tiempo_ejecucion_horas = float(tiempo_ejecucion_horas) if tiempo_ejecucion_horas else None
    except ValueError:
        tiempo_ejecucion_horas = None
    
    orden = request.form.get("orden")
    try:
        orden = int(orden) if orden else None
    except ValueError:
        orden = None
    
    descripcion = request.form.get("descripcion")
    notas = request.form.get("notas")
    material_id = request.form.get("material_id")
    try:
        material_id = int(material_id) if material_id else None
    except ValueError:
        material_id = None
    
    if presupuestos.actualizar_item_presupuesto(
        presupuesto_item_id=item_id,
        cantidad=cantidad,
        precio_unitario=precio_unitario,
        subgrupo_id=subgrupo_id,
        numero_subitem=numero_subitem,
        tiempo_ejecucion_horas=tiempo_ejecucion_horas,
        orden=orden,
        descripcion=descripcion,
        notas=notas,
        material_id=material_id
    ):
        return redirect(url_for('presupuestos_ver', id=presupuesto_id))
    return "Error al actualizar item", 400

# ==================== RUTAS DE SUBGRUPOS ====================

@app.route("/presupuestos/<int:id>/subgrupos/agregar", methods=["POST"])
def presupuestos_agregar_subgrupo(id):
    """Agregar subgrupo a presupuesto"""
    nombre = request.form.get("nombre")
    if not nombre:
        return "Nombre del subgrupo es requerido", 400
    
    numero = request.form.get("numero")
    try:
        numero = int(numero) if numero else presupuestos.obtener_siguiente_numero_subgrupo(id)
    except ValueError:
        numero = presupuestos.obtener_siguiente_numero_subgrupo(id)
    
    orden = request.form.get("orden")
    try:
        orden = int(orden) if orden else 0
    except ValueError:
        orden = 0
    
    try:
        presupuestos.crear_subgrupo(
            presupuesto_id=id,
            numero=numero,
            nombre=nombre,
            orden=orden
        )
    except Exception as e:
        return f"Error al agregar subgrupo: {str(e)}", 400
    
    return redirect(url_for('presupuestos_ver', id=id))

@app.route("/presupuestos/subgrupos/<int:subgrupo_id>/actualizar", methods=["POST"])
def presupuestos_actualizar_subgrupo(subgrupo_id):
    """Actualizar subgrupo"""
    presupuesto_id = request.form.get("presupuesto_id")
    try:
        presupuesto_id = int(presupuesto_id) if presupuesto_id else None
    except ValueError:
        return "Presupuesto ID inválido", 400
    
    numero = request.form.get("numero")
    try:
        numero = int(numero) if numero else None
    except ValueError:
        numero = None
    
    nombre = request.form.get("nombre")
    orden = request.form.get("orden")
    try:
        orden = int(orden) if orden else None
    except ValueError:
        orden = None
    
    if presupuestos.actualizar_subgrupo(
        subgrupo_id=subgrupo_id,
        numero=numero,
        nombre=nombre,
        orden=orden
    ):
        return redirect(url_for('presupuestos_ver', id=presupuesto_id))
    return "Error al actualizar subgrupo", 400

@app.route("/presupuestos/subgrupos/<int:subgrupo_id>/eliminar", methods=["POST"])
def presupuestos_eliminar_subgrupo(subgrupo_id):
    """Eliminar subgrupo"""
    presupuesto_id = request.form.get("presupuesto_id")
    try:
        presupuesto_id = int(presupuesto_id) if presupuesto_id else None
    except ValueError:
        return "Presupuesto ID inválido", 400
    
    if presupuestos.eliminar_subgrupo(subgrupo_id):
        return redirect(url_for('presupuestos_ver', id=presupuesto_id))
    return "Error al eliminar subgrupo", 400


@app.route("/presupuestos/<int:id>/pdf", methods=["GET"])
def presupuestos_pdf(id):
    """Generar/visualizar PDF del presupuesto"""
    presupuesto = presupuestos.obtener_presupuesto_por_id(id)
    if not presupuesto:
        return "Presupuesto no encontrado", 404

    items_disponibles = presupuestos.obtener_items_activos()
    tipos_items = presupuestos.obtener_tipos_items()

    html = render_template(
        'presupuestos/pdf.html',
        presupuesto=presupuesto,
        items_disponibles=items_disponibles,
        tipos_items=tipos_items,
        request=request,
        datetime=datetime,
    )

    try:
        from weasyprint import HTML

        pdf = HTML(string=html, base_url=request.host_url).write_pdf()
        response = make_response(pdf)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'inline; filename=presupuesto_{id}.pdf'
        return response
    except Exception as e:
        mensaje = (
            "<p style='padding:10px; background:#fff3cd;'>"
            "⚠️ No se pudo generar el PDF automáticamente."
            "<br>• Si deseas exportar a PDF desde la aplicación instala la dependencia opcional "
            "<code>weasyprint</code> y sus librerías del sistema (GTK/GObject)."
            "<br>• Error reportado: <code>{error}</code>"
            "<br>Mostrando vista previa imprimible."
            "</p>"
        ).format(error=str(e))
        return mensaje + html

# ==================== RUTAS DE ITEMS ====================

@app.route("/presupuestos/items", methods=["GET"])
def items_index():
    """Lista de items"""
    tipo = request.args.get("tipo")
    items_lista = presupuestos.obtener_items_activos(tipo=tipo)
    tipos_lista = presupuestos.obtener_tipos_items()
    return render_template('presupuestos/items/index.html', 
                         items=items_lista, 
                         tipos=tipos_lista,
                         tipo_filtro=tipo,
                         request=request)

@app.route("/presupuestos/items/nuevo", methods=["GET", "POST"])
def items_nuevo():
    """Crear nuevo item"""
    if request.method == "POST":
        codigo = request.form.get("codigo") or None
        descripcion = request.form.get("descripcion")
        if not descripcion:
            return "Descripción es requerida", 400
        tipo = request.form.get("tipo") or "Otros"
        unidad = request.form.get("unidad") or "unidad"
        precio_base = request.form.get("precio_base")
        try:
            precio_base = float(precio_base) if precio_base else 0
        except ValueError:
            precio_base = 0
        margen_porcentaje = request.form.get("margen_porcentaje")
        try:
            margen_porcentaje = float(margen_porcentaje) if margen_porcentaje else 0
        except ValueError:
            margen_porcentaje = 0
        notas = request.form.get("notas") or None
        
        try:
            presupuestos.crear_item(
                codigo=codigo,
                descripcion=descripcion,
                tipo=tipo,
                unidad=unidad,
                precio_base=precio_base,
                margen_porcentaje=margen_porcentaje,
                notas=notas
            )
            return redirect(url_for('items_index'))
        except Exception as e:
            return f"Error al crear item: {str(e)}", 400
    
    tipos_lista = presupuestos.obtener_tipos_items()
    return render_template('presupuestos/items/form.html', 
                         item=None, 
                         tipos=tipos_lista,
                         request=request)

@app.route("/presupuestos/items/<int:id>/editar", methods=["GET", "POST"])
def items_editar(id):
    """Editar item"""
    item = presupuestos.obtener_item_por_id(id)
    if not item:
        return "Item no encontrado", 404
    
    if request.method == "POST":
        codigo = request.form.get("codigo") or None
        descripcion = request.form.get("descripcion")
        if not descripcion:
            return "Descripción es requerida", 400
        tipo = request.form.get("tipo") or "Otros"
        unidad = request.form.get("unidad") or "unidad"
        precio_base = request.form.get("precio_base")
        try:
            precio_base = float(precio_base) if precio_base else 0
        except ValueError:
            precio_base = 0
        margen_porcentaje = request.form.get("margen_porcentaje")
        try:
            margen_porcentaje = float(margen_porcentaje) if margen_porcentaje else 0
        except ValueError:
            margen_porcentaje = 0
        activo = request.form.get("activo")
        activo = activo == "on" or activo == "1" or activo == "true"
        notas = request.form.get("notas") or None
        
        try:
            if presupuestos.actualizar_item(
                item_id=id,
                codigo=codigo,
                descripcion=descripcion,
                tipo=tipo,
                unidad=unidad,
                precio_base=precio_base,
                margen_porcentaje=margen_porcentaje,
                activo=activo,
                notas=notas
            ):
                return redirect(url_for('items_index'))
            else:
                return "Error al actualizar item", 400
        except Exception as e:
            return f"Error al actualizar item: {str(e)}", 400
    
    # Convertir DictRow a diccionario
    item_dict = dict(item) if item else None
    tipos_lista = presupuestos.obtener_tipos_items()
    return render_template('presupuestos/items/form.html', 
                         item=item_dict, 
                         tipos=tipos_lista,
                         request=request)

# ==================== RUTAS DE CLIENTES ====================

@app.route("/presupuestos/clientes", methods=["GET"])
def clientes_index():
    """Lista de clientes"""
    clientes_lista = presupuestos.obtener_clientes()
    return render_template('presupuestos/clientes/index.html', 
                         clientes=clientes_lista,
                         request=request)

@app.route("/presupuestos/clientes/nuevo", methods=["GET", "POST"])
def clientes_nuevo():
    """Crear nuevo cliente"""
    if request.method == "POST":
        nombre = request.form.get("nombre")
        if not nombre:
            return "Nombre es requerido", 400
        razon_social = request.form.get("razon_social") or None
        cuit = request.form.get("cuit") or None
        direccion = request.form.get("direccion") or None
        telefono = request.form.get("telefono") or None
        email = request.form.get("email") or None
        notas = request.form.get("notas") or None
        
        try:
            presupuestos.crear_cliente(
                nombre=nombre,
                razon_social=razon_social,
                cuit=cuit,
                direccion=direccion,
                telefono=telefono,
                email=email,
                notas=notas
            )
            return redirect(url_for('clientes_index'))
        except Exception as e:
            return f"Error al crear cliente: {str(e)}", 400
    
    return render_template('presupuestos/clientes/form.html', 
                         cliente=None,
                         request=request)

@app.route("/presupuestos/materiales", methods=["GET"])
def materiales_index():
    descripcion = request.args.get("descripcion") or None
    proveedor = request.args.get("proveedor") or None
    materiales = presupuestos.buscar_materiales(descripcion=descripcion, proveedor=proveedor)
    materiales_list = [dict(m) for m in materiales]
    return render_template(
        'presupuestos/materiales/index.html',
        materiales=materiales_list,
        descripcion_filtro=descripcion or "",
        proveedor_filtro=proveedor or "",
        request=request
    )

@app.route("/presupuestos/materiales/<int:id>/editar", methods=["GET", "POST"])
def materiales_editar(id):
    material = presupuestos.obtener_material_por_id(id)
    if not material:
        return "Material no encontrado", 404
    if request.method == "POST":
        descripcion = request.form.get("descripcion") or None
        proveedor = request.form.get("proveedor") or None
        precio = request.form.get("precio")
        tiempo = request.form.get("tiempo_instalacion")
        try:
            precio = float(precio) if precio else None
        except ValueError:
            precio = None
        try:
            tiempo = float(tiempo) if tiempo else None
        except ValueError:
            tiempo = None
        presupuestos.actualizar_material(
            material_id=id,
            descripcion=descripcion,
            proveedor=proveedor,
            precio=precio,
            tiempo_instalacion=tiempo
        )
        return redirect(url_for('materiales_index'))
    return render_template('presupuestos/materiales/form.html', material=dict(material), request=request)


@app.route("/presupuestos/materiales/<int:id>/eliminar", methods=["POST"])
def materiales_eliminar(id):
    if presupuestos.eliminar_material(id):
        return redirect(url_for('materiales_index'))
    return "Error al eliminar material", 400


if __name__ == "__main__":
    # App unificada
    app.run(host="127.0.0.1", port=5000, debug=True)


