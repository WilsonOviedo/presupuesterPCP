from flask import Flask, request, render_template, redirect, url_for, jsonify
import io
from contextlib import redirect_stdout
from threading import Thread, Lock
import time
from urllib.parse import parse_qsl
import csv
import os
import uuid
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Reutilizamos la lógica existente sin levantar su servidor
import buscar_precios_web as precios
import leer_factura as facturas
import presupuestos_db as presupuestos
from flask import make_response
from datetime import datetime
from collections import OrderedDict
import procesar_presupuesto_ocr as ocr_processor

# Importación opcional de OCR con OpenCV (solo si está disponible)
try:
    import procesar_ocr_opencv as ocr_opencv
    OCR_OPENCV_AVAILABLE = True
except ImportError:
    ocr_opencv = None
    OCR_OPENCV_AVAILABLE = False


app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max

# Crear carpeta de uploads si no existe
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _to_upper(valor):
    """Convierte un valor a mayúsculas si es un string, mantiene None si es None"""
    if valor is None:
        return None
    if not isinstance(valor, str):
        return valor
    texto = valor.strip()
    if texto == "":
        return ""
    return texto.upper()


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
                if precio is not None:
                    denominador = 1 - (margen_val / 100.0)
                    if denominador != 0:
                        precio_venta = float(precio) / denominador
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


@app.route("/precios/cargar-manual", methods=["GET", "POST"])
def precios_cargar_manual():
    """Cargar precios manualmente con el mismo formato que IMAP"""
    if request.method == "GET":
        return render_template('precios/cargar_manual.html')
    
    # POST: procesar formulario
    try:
        conn, cur = precios.conectar()
        
        # Obtener datos del formulario (todo en mayúsculas)
        proveedor_raw = (request.form.get('proveedor') or '').strip()
        proveedor = _to_upper(proveedor_raw) if proveedor_raw else "MANUAL"
        fecha_str = request.form.get('fecha', '').strip()
        hora_str = request.form.get('hora', '').strip()
        
        # Parsear fecha
        fecha = None
        if fecha_str:
            try:
                # Parsear fecha (formato YYYY-MM-DD)
                fecha = datetime.strptime(fecha_str, "%Y-%m-%d")
            except:
                # Intentar con parse_fecha como fallback
                fecha = precios.parse_fecha(fecha_str, inicio=True)
        
        if not fecha:
            fecha = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Procesar hora
        if hora_str:
            try:
                hora_int = int(hora_str)
                if 0 <= hora_int <= 23:
                    # Completar hora a HH:00:00
                    fecha = fecha.replace(hour=hora_int, minute=0, second=0, microsecond=0)
            except ValueError:
                pass  # Si la hora no es válida, usar solo la fecha
        
        # Obtener items (producto, precio)
        items_guardados = 0
        items_errores = []
        
        # Procesar items del formulario
        item_count = 0
        while True:
            producto_key = f'producto_{item_count}'
            precio_key = f'precio_{item_count}'
            
            if producto_key not in request.form:
                break
            
            producto = _to_upper((request.form.get(producto_key) or '').strip())
            precio_str = (request.form.get(precio_key) or '').strip()
            
            if producto and precio_str:
                try:
                    precio = float(precio_str.replace(',', '.'))
                    
                    # Insertar en la base de datos (mismo formato que IMAP)
                    # Asegurar que todo esté en mayúsculas
                    proveedor_final = proveedor if proveedor else "MANUAL"
                    producto_final = producto  # Ya está en mayúsculas por _to_upper()
                    
                    cur.execute("""
                        INSERT INTO precios (proveedor, fecha, producto, precio)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT DO NOTHING;
                    """, (proveedor_final, fecha, producto_final, precio))
                    
                    if cur.rowcount > 0:
                        items_guardados += 1
                    else:
                        items_errores.append(f"{producto} (duplicado)")
                        
                except ValueError:
                    items_errores.append(f"{producto} (precio inválido: {precio_str})")
                except Exception as e:
                    items_errores.append(f"{producto} (error: {str(e)})")
            
            item_count += 1
        
        conn.commit()
        cur.close()
        conn.close()
        
        mensaje = f"Se guardaron {items_guardados} precios correctamente."
        if items_errores:
            mensaje += f" Errores: {len(items_errores)} items no se guardaron."
        
        return redirect(url_for('precios_index', 
                              mensaje=mensaje,
                              items_guardados=items_guardados,
                              items_errores=','.join(items_errores[:5])))  # Limitar errores mostrados
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Error al cargar precios manualmente: {e}")
        print(error_trace)
        return render_template('precios/cargar_manual.html', 
                             error=f"Error al guardar precios: {str(e)}")


@app.route("/precios/materiales", methods=["POST"])
def precios_agregar_material():
    descripcion = _to_upper((request.form.get("descripcion") or "").strip())
    marca = _to_upper((request.form.get("proveedor") or "").strip())
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
                marca=marca or None,
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
            denominador = 1 - (margen_val / 100.0)
            if denominador != 0.0:
                resultado = precio_val / denominador
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


@app.route("/api/ocr/process", methods=["POST"])
def api_ocr_process():
    """API endpoint para procesar OCR con OpenCV y Tesseract"""
    try:
        if 'imagen' not in request.files:
            return jsonify({'error': 'No se proporcionó imagen'}), 400
        
        file = request.files['imagen']
        if file.filename == '':
            return jsonify({'error': 'No se seleccionó archivo'}), 400
        
        # Leer imagen
        image_bytes = file.read()
        
        # Obtener configuración de preprocesamiento
        config = {
            'enable_preprocessing': request.form.get('enable_preprocessing', 'true').lower() == 'true',
            'threshold': int(request.form.get('threshold', 128)),
            'contrast': int(request.form.get('contrast', 0)),
            'brightness': int(request.form.get('brightness', 0)),
            'enable_smoothing': request.form.get('enable_smoothing', 'true').lower() == 'true',
            'enable_grayscale': request.form.get('enable_grayscale', 'true').lower() == 'true',
            'psm_mode': request.form.get('psm_mode', '6'),
            'lang': request.form.get('lang', 'spa+por+eng')
        }
        
        # Obtener región de recorte si existe
        crop_region_str = request.form.get('crop_region')
        if crop_region_str:
            try:
                import json
                config['crop_region'] = json.loads(crop_region_str)
            except:
                pass
        
        # Procesar OCR (local o remoto según configuración)
        if not OCR_OPENCV_AVAILABLE:
            return jsonify({
                'error': 'OCR con OpenCV no está disponible. Por favor, instala las dependencias necesarias o configura un servidor OCR remoto.'
            }), 503
        
        result = ocr_opencv.process_ocr(image_bytes, config)
        
        # Convertir palabras al formato esperado
        palabras_formato = []
        for word in result['words']:
            bbox = word['bbox']
            palabras_formato.append([
                [[bbox['x0'], bbox['y0']], [bbox['x1'], bbox['y0']], 
                 [bbox['x1'], bbox['y1']], [bbox['x0'], bbox['y1']]],
                word['text'],
                word['confidence'] / 100.0
            ])
        
        return jsonify({
            'text': result['text'],
            'words': palabras_formato,
            'word_count': len(palabras_formato)
        })
    
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Error en API OCR: {e}")
        print(error_trace)
        return jsonify({'error': str(e)}), 500

@app.route("/precios/cargar-presupuesto", methods=["GET", "POST"])
def precios_cargar_presupuesto():
    """Cargar presupuesto desde imagen usando OCR"""
    if request.method == "GET":
        return render_template('precios/cargar_presupuesto.html')
    
    # POST: procesar imagen
    # Verificar si viene texto OCR desde el frontend (compatibilidad con Tesseract.js)
    ocr_text = request.form.get('ocr_text', '')
    ocr_data_str = request.form.get('ocr_data', '')
    
    if not ocr_text:
        return render_template('precios/cargar_presupuesto.html', 
                             error="No se recibió texto OCR. Por favor, asegúrate de que la imagen se procese correctamente.")
    
    try:
        # Parsear datos OCR estructurados
        resultados_ocr = []
        if ocr_data_str:
            try:
                import json
                resultados_ocr = json.loads(ocr_data_str)
            except:
                resultados_ocr = []
        
        # Procesar texto OCR
        datos = ocr_processor.procesar_texto_presupuesto(ocr_text, resultados_ocr)
        
        # Guardar datos en sesión para confirmación
        import json
        
        # Asegurar que items sea una lista
        items = datos.get('items', [])
        if not isinstance(items, list):
            if items is None:
                items = []
            else:
                try:
                    items = list(items)
                except:
                    items = []
        
        datos_serializables = {
            'proveedor': datos.get('proveedor'),
            'fecha': datos.get('fecha').isoformat() if datos.get('fecha') else None,
            'numero_presupuesto': datos.get('numero_presupuesto'),
            'items': items,
            'total': datos.get('total')
        }
        
        return render_template('precios/confirmar_presupuesto.html', 
                             datos=datos_serializables,
                             datos_json=json.dumps(datos_serializables))
    
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Error al procesar OCR: {e}")
        print(error_trace)
        return render_template('precios/cargar_presupuesto.html', 
                             error=f"Error al procesar imagen: {str(e)}")

@app.route("/precios/confirmar-presupuesto", methods=["POST"])
def precios_confirmar_presupuesto():
    """Confirmar y guardar presupuesto en la base de datos"""
    import json
    
    datos_json = request.form.get('datos_json')
    if not datos_json:
        return redirect(url_for('precios_cargar_presupuesto'))
    
    try:
        datos = json.loads(datos_json)
        proveedor = datos.get('proveedor') or 'PROVEEDOR_DESCONOCIDO'
        fecha_str = datos.get('fecha')
        
        if fecha_str:
            fecha = datetime.fromisoformat(fecha_str)
        else:
            fecha = datetime.now()
        
        items = datos.get('items', [])
        
        # Conectar a la base de datos
        conn, cur = precios.conectar()
        
        items_guardados = 0
        items_duplicados = 0
        errores = []
        
        try:
            for item in items:
                descripcion = item.get('descripcion')
                precio = item.get('precio_unitario')
                
                if not descripcion or not precio:
                    continue
                
                # Normalizar descripción
                descripcion = _to_upper(descripcion)
                
                # Intentar guardar
                try:
                    cur.execute("""
                        INSERT INTO precios (proveedor, fecha, producto, precio)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT DO NOTHING;
                    """, (proveedor, fecha, descripcion, precio))
                    
                    if cur.rowcount > 0:
                        items_guardados += 1
                    else:
                        items_duplicados += 1
                
                except Exception as e:
                    errores.append(f"{descripcion}: {str(e)}")
            
            conn.commit()
            
            # Limpiar archivo temporal
            imagen_path = datos.get('imagen_path')
            if imagen_path:
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], imagen_path)
                if os.path.exists(filepath):
                    os.remove(filepath)
        
        finally:
            cur.close()
            conn.close()
        
        mensaje = f"Se guardaron {items_guardados} items"
        if items_duplicados > 0:
            mensaje += f", {items_duplicados} duplicados omitidos"
        if errores:
            mensaje += f", {len(errores)} errores"
        
        return redirect(url_for('precios_index', 
                               mensaje=mensaje,
                               items_guardados=items_guardados))
    
    except Exception as e:
        return render_template('precios/cargar_presupuesto.html', 
                             error=f"Error al guardar: {str(e)}")


# ==================== RUTAS DE PRESUPUESTOS ====================

@app.route("/listas-materiales", methods=["GET"], endpoint="listas_materiales_index")
@app.route("/presupuestos", methods=["GET"], endpoint="presupuestos_index")
def listas_materiales_index():
    """Lista de presupuestos"""
    estado = request.args.get("estado")
    cliente_id = request.args.get("cliente_id")
    try:
        cliente_id = int(cliente_id) if cliente_id else None
    except ValueError:
        cliente_id = None
    
    presupuestos_lista = presupuestos.obtener_listas_materiales(estado=estado, cliente_id=cliente_id)
    clientes_lista = presupuestos.obtener_clientes()
    
    return render_template('listas_materiales/index.html', 
                         presupuestos=presupuestos_lista, 
                         clientes=clientes_lista,
                         estado_filtro=estado,
                         cliente_filtro=cliente_id,
                         request=request)

@app.route("/listas-materiales/nuevo", methods=["GET", "POST"], endpoint="listas_materiales_nuevo")
def listas_materiales_nuevo():
    """Flujo guiado: proyecto → lista de materiales → precios → resumen"""
    lista_id_param = request.args.get("lista_id")
    paso_param = request.args.get("paso")
    lista_seleccionada = None
    tabla_items = []
    precios_asignados = False

    if request.method == "POST":
        cliente_id = request.form.get("cliente_id")
        try:
            cliente_id = int(cliente_id) if cliente_id else None
        except ValueError:
            cliente_id = None
        
        numero = request.form.get("numero_presupuesto") or request.form.get("numero_lista") or presupuestos.generar_numero_lista()
        titulo = _to_upper(request.form.get("titulo")) if request.form.get("titulo") else None
        descripcion = _to_upper(request.form.get("descripcion")) if request.form.get("descripcion") else None
        estado = request.form.get("estado") or "borrador"
        fecha = request.form.get("fecha_lista") or request.form.get("fecha_presupuesto") or None
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
        notas = _to_upper(request.form.get("notas")) if request.form.get("notas") else None
        
        lista_id_nueva = presupuestos.crear_lista_material(
            cliente_id=cliente_id,
            numero_lista=numero,
            titulo=titulo,
            descripcion=descripcion,
            estado=estado,
            fecha_lista=fecha,
            validez_dias=validez_dias,
            iva_porcentaje=iva_porcentaje,
            notas=notas
        )
        return redirect(url_for('listas_materiales_nuevo', lista_id=lista_id_nueva, paso=2))

    if lista_id_param:
        try:
            lista_id = int(lista_id_param)
            lista_seleccionada = presupuestos.obtener_lista_material_por_id(lista_id)
        except (ValueError, TypeError):
            lista_seleccionada = None
        if not lista_seleccionada:
            lista_id_param = None
        else:
            items_tabla = []
            for subgrupo in lista_seleccionada.get('subgrupos', []):
                for item in subgrupo.get('items', []):
                    item_copy = dict(item)
                    item_copy['subgrupo_label'] = f"{subgrupo.get('numero')} - {subgrupo.get('nombre')}"
                    items_tabla.append(item_copy)
            for item in lista_seleccionada.get('items_sin_subgrupo', []):
                item_copy = dict(item)
                item_copy['subgrupo_label'] = "Sin subgrupo"
                items_tabla.append(item_copy)

            for item in items_tabla:
                precios_item = presupuestos.obtener_precios_por_item(item['id'])
                precio_seleccionado = next((p for p in precios_item if p.get('seleccionado')), None)
                if precio_seleccionado:
                    precios_asignados = True
                tabla_items.append({
                    'id': item['id'],
                    'numero': item.get('numero_subitem'),
                    'descripcion': item.get('descripcion'),
                    'unidad': (item.get('unidad') or 'UND'),
                    'cantidad': item.get('cantidad') or 0,
                    'marca': item.get('marca'),
                    'subgrupo': item.get('subgrupo_label'),
                    'tiempo_ejecucion_horas': item.get('tiempo_ejecucion_horas') or 0,
                    'tiempo_total': (item.get('cantidad') or 0) * (item.get('tiempo_ejecucion_horas') or 0),
                    'precios': precios_item,
                    'precio_seleccionado': precio_seleccionado
                })

    clientes_lista = presupuestos.obtener_clientes()
    numero_generado = presupuestos.generar_numero_lista()

    paso1_completado = lista_seleccionada is not None
    cantidad_items = int(lista_seleccionada.get('cantidad_items') or 0) if lista_seleccionada else 0
    paso2_completado = paso1_completado and cantidad_items > 0
    paso3_completado = paso2_completado and precios_asignados
    paso4_completado = paso3_completado and cantidad_items > 0

    def _proximo_paso():
        if not paso1_completado:
            return 1
        if not paso2_completado:
            return 2
        if not paso3_completado:
            return 3
        return 4

    try:
        paso_activo = int(paso_param) if paso_param else _proximo_paso()
    except (TypeError, ValueError):
        paso_activo = _proximo_paso()
    if not paso1_completado:
        paso_activo = 1

    return render_template(
        'listas_materiales/wizard.html',
        clientes=clientes_lista,
        numero_presupuesto=numero_generado,
        lista=lista_seleccionada,
        tabla_items=tabla_items,
        paso_activo=paso_activo,
        paso1_completado=paso1_completado,
        paso2_completado=paso2_completado,
        paso3_completado=paso3_completado,
        paso4_completado=paso4_completado,
        precios_asignados=precios_asignados,
        cantidad_items=cantidad_items,
        request=request
    )

@app.route("/listas-materiales/<int:id>", methods=["GET"], endpoint="listas_materiales_ver")
def listas_materiales_ver(id):
    """Ver presupuesto"""
    presupuesto = presupuestos.obtener_lista_material_por_id(id)
    if not presupuesto:
        return "Presupuesto no encontrado", 404
    
    # Solo items de mano de obra
    items_servicio_raw = presupuestos.obtener_items_activos()
    items_servicio = []
    for item in items_servicio_raw:
        item_dict = dict(item)
        item_dict['precio_venta'] = float(item_dict.get('precio_venta') or item_dict.get('precio_base') or 0)
        item_dict['tiempo_instalacion'] = float(item_dict.get('tiempo_instalacion') or 0)
        item_dict['codigo'] = item_dict.get('codigo') or f"SERV-{item_dict.get('id')}"
        item_dict['unidad'] = item_dict.get('unidad') or 'unidad'
        items_servicio.append(item_dict)

    # Solo materiales genéricos (no materiales eléctricos)
    materiales_genericos_raw = presupuestos.obtener_materiales_genericos()
    items_materiales_genericos = []
    for material in materiales_genericos_raw:
        material_dict = dict(material)
        material_dict['precio_venta'] = 0  # Los materiales genéricos no tienen precio
        material_dict['tiempo_instalacion'] = float(material_dict.get('tiempo_instalacion') or 0)
        material_dict['tipo'] = 'Material Genérico'
        material_dict['unidad'] = 'unidad'
        material_dict['codigo'] = f"GEN-{material_dict.get('id')}"
        items_materiales_genericos.append(material_dict)

    tipos_items = presupuestos.obtener_tipos_items()
    items_disponibles = items_servicio + items_materiales_genericos
    
    # Obtener templates disponibles
    templates_raw = presupuestos.obtener_templates_listas_materiales()
    templates_disponibles = [dict(t) for t in templates_raw]

    marcas_materiales = [dict(m) for m in presupuestos.obtener_marcas_materiales(activo=True)]

    return render_template('listas_materiales/ver.html', 
                         presupuesto=presupuesto, 
                         items_disponibles=items_disponibles,
                         items_servicio=items_servicio,
                         items_materiales=items_materiales_genericos,
                         tipos_items=tipos_items,
                         templates_disponibles=templates_disponibles,
                         marcas_materiales=marcas_materiales,
                         request=request)

@app.route("/listas-materiales/<int:id>/editar", methods=["GET", "POST"], endpoint="listas_materiales_editar")
def listas_materiales_editar(id):
    """Editar presupuesto"""
    presupuesto = presupuestos.obtener_lista_material_por_id(id)
    if not presupuesto:
        return "Presupuesto no encontrado", 404
    
    if request.method == "POST":
        cliente_id = request.form.get("cliente_id")
        try:
            cliente_id = int(cliente_id) if cliente_id else None
        except ValueError:
            cliente_id = None
        
        titulo = _to_upper(request.form.get("titulo")) if request.form.get("titulo") else None
        descripcion = _to_upper(request.form.get("descripcion")) if request.form.get("descripcion") else None
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
        notas = _to_upper(request.form.get("notas")) if request.form.get("notas") else None
        
        presupuestos.actualizar_lista_material(
            lista_material_id=id,
            cliente_id=cliente_id,
            titulo=titulo,
            descripcion=descripcion,
            estado=estado,
            fecha_lista=fecha,
            validez_dias=validez_dias,
            iva_porcentaje=iva_porcentaje,
            notas=notas
        )
        return redirect(url_for('listas_materiales_ver', id=id))
    
    clientes_lista = presupuestos.obtener_clientes()
    return render_template('listas_materiales/form.html', 
                         presupuesto=presupuesto, 
                         clientes=clientes_lista,
                         request=request)

@app.route("/listas-materiales/<int:id>/items/agregar", methods=["POST"], endpoint="listas_materiales_agregar_item")
@app.route("/listas-materiales/<int:id>/items/agregar", methods=["POST"], endpoint="listas_materiales_agregar_item")
def listas_materiales_agregar_item(id):
    """Agregar item a presupuesto"""
    item_id = request.form.get("item_id")
    try:
        item_id = int(item_id) if item_id else None
    except ValueError:
        item_id = None

    material_generico_id = request.form.get("material_generico_id")
    try:
        material_generico_id = int(material_generico_id) if material_generico_id else None
    except ValueError:
        material_generico_id = None
    
    if not item_id and not material_generico_id:
        return "Debe seleccionar un servicio o material genérico", 400
    
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
    
    notas = _to_upper(request.form.get("notas")) if request.form.get("notas") else None

    marca_id = request.form.get("marca_id")
    try:
        marca_id = int(marca_id) if marca_id else None
    except ValueError:
        marca_id = None
    marca = _to_upper(request.form.get("marca")) if request.form.get("marca") else None
    
    try:
        item_presupuesto_id = presupuestos.agregar_item_a_lista_material(
            lista_material_id=id,
            item_id=item_id,
            material_generico_id=material_generico_id,
            cantidad=cantidad,
            precio_unitario=precio_unitario,
            subgrupo_id=subgrupo_id,
            numero_subitem=numero_subitem,
            tiempo_ejecucion_horas=tiempo_ejecucion_horas,
            orden=orden,
            notas=notas,
            marca=marca,
            marca_id=marca_id
        )
        
        # Si es una petición AJAX, devolver JSON
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            # Obtener el item recién creado
            item = presupuestos.obtener_item_presupuesto_por_id(item_presupuesto_id)
            if item:
                return jsonify({
                    'success': True,
                    'item': {
                        'id': item['id'],
                        'descripcion': item['descripcion'],
                            'marca': item.get('marca') or '-',
                        'cantidad': float(item['cantidad']),
                        'precio_unitario': float(item['precio_unitario']),
                        'subtotal': float(item.get('subtotal', item['cantidad'] * item['precio_unitario'])),
                        'tiempo_ejecucion_horas': float(item.get('tiempo_ejecucion_horas', 0)),
                        'numero_subitem': item.get('numero_subitem') or '',
                        'material_id': item.get('material_id')
                    }
                })
            return jsonify({'success': True, 'item_id': item_presupuesto_id})
    except Exception as e:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': str(e)}), 400
        return f"Error al agregar item: {str(e)}", 400
    
    return redirect(url_for('listas_materiales_ver', id=id))

@app.route("/listas-materiales/items/<int:item_id>/eliminar", methods=["POST"], endpoint="listas_materiales_eliminar_item")
@app.route("/listas-materiales/items/<int:item_id>/eliminar", methods=["POST"], endpoint="listas_materiales_eliminar_item")
def listas_materiales_eliminar_item(item_id):
    """Eliminar item de presupuesto"""
    lista_id = request.form.get("lista_id") or request.form.get("presupuesto_id")
    try:
        lista_id = int(lista_id) if lista_id else None
    except ValueError:
        return "Lista ID inválida", 400
    
    if presupuestos.eliminar_item_de_lista_material(item_id):
        return redirect(url_for('listas_materiales_ver', id=lista_id))
    return "Error al eliminar item", 400

@app.route("/listas-materiales/items/<int:item_id>/actualizar", methods=["POST"], endpoint="listas_materiales_actualizar_item")
@app.route("/listas-materiales/items/<int:item_id>/actualizar", methods=["POST"], endpoint="listas_materiales_actualizar_item")
def listas_materiales_actualizar_item(item_id):
    """Actualizar item de presupuesto"""
    lista_id = request.form.get("lista_id") or request.form.get("presupuesto_id")
    try:
        lista_id = int(lista_id) if lista_id else None
    except ValueError:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': 'Lista ID inválida'}), 400
        return "Lista ID inválida", 400
    
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
    
    descripcion = _to_upper(request.form.get("descripcion")) if request.form.get("descripcion") else None
    notas = _to_upper(request.form.get("notas")) if request.form.get("notas") else None
    material_id = request.form.get("material_id")
    try:
        material_id = int(material_id) if material_id else None
    except ValueError:
        material_id = None

    marca_id = request.form.get("marca_id")
    try:
        marca_id = int(marca_id) if marca_id else None
    except ValueError:
        marca_id = None
    marca = _to_upper(request.form.get("marca")) if request.form.get("marca") else None
    
    es_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if presupuestos.actualizar_item_lista_material(
        lista_material_item_id=item_id,
        cantidad=cantidad,
        precio_unitario=precio_unitario,
        subgrupo_id=subgrupo_id,
        numero_subitem=numero_subitem,
        tiempo_ejecucion_horas=tiempo_ejecucion_horas,
        orden=orden,
        descripcion=descripcion,
        notas=notas,
        material_id=material_id,
        marca=marca,
        marca_id=marca_id
    ):
        if es_ajax:
            item = presupuestos.obtener_item_presupuesto_por_id(item_id)
            if item:
                return jsonify({
                    'success': True,
                    'item': {
                        'id': item['id'],
                        'marca': item.get('marca'),
                        'marca_id': item.get('marca_id')
                    }
                })
            return jsonify({'success': False, 'error': 'Item no encontrado'}), 404
        return redirect(url_for('listas_materiales_ver', id=lista_id))
    if es_ajax:
        return jsonify({'success': False, 'error': 'Error al actualizar item'}), 400
    return "Error al actualizar item", 400

# ==================== RUTAS DE SUBGRUPOS ====================

@app.route("/listas-materiales/<int:id>/subgrupos/agregar", methods=["POST"], endpoint="listas_materiales_agregar_subgrupo")
@app.route("/listas-materiales/<int:id>/subgrupos/agregar", methods=["POST"], endpoint="listas_materiales_agregar_subgrupo")
def listas_materiales_agregar_subgrupo(id):
    """Agregar subgrupo a presupuesto"""
    nombre = _to_upper(request.form.get("nombre"))
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
            lista_material_id=id,
            numero=numero,
            nombre=nombre,
            orden=orden
        )
    except Exception as e:
        return f"Error al agregar subgrupo: {str(e)}", 400
    
    return redirect(url_for('listas_materiales_ver', id=id))

@app.route("/listas-materiales/subgrupos/<int:subgrupo_id>/actualizar", methods=["POST"], endpoint="listas_materiales_actualizar_subgrupo")
@app.route("/listas-materiales/subgrupos/<int:subgrupo_id>/actualizar", methods=["POST"], endpoint="listas_materiales_actualizar_subgrupo")
def listas_materiales_actualizar_subgrupo(subgrupo_id):
    """Actualizar subgrupo"""
    lista_id = request.form.get("lista_id") or request.form.get("presupuesto_id")
    try:
        lista_id = int(lista_id) if lista_id else None
    except ValueError:
        return "Lista ID inválido", 400
    
    numero = request.form.get("numero")
    try:
        numero = int(numero) if numero else None
    except ValueError:
        numero = None
    
    nombre = _to_upper(request.form.get("nombre"))
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
        return redirect(url_for('listas_materiales_ver', id=lista_id))
    return "Error al actualizar subgrupo", 400

@app.route("/listas-materiales/subgrupos/<int:subgrupo_id>/eliminar", methods=["POST"], endpoint="listas_materiales_eliminar_subgrupo")
@app.route("/listas-materiales/subgrupos/<int:subgrupo_id>/eliminar", methods=["POST"], endpoint="listas_materiales_eliminar_subgrupo")
def listas_materiales_eliminar_subgrupo(subgrupo_id):
    """Eliminar subgrupo"""
    lista_id = request.form.get("lista_id") or request.form.get("presupuesto_id")
    try:
        lista_id = int(lista_id) if lista_id else None
    except ValueError:
        return "Lista ID inválido", 400
    
    if presupuestos.eliminar_subgrupo(subgrupo_id):
        return redirect(url_for('listas_materiales_ver', id=lista_id))
    return "Error al eliminar subgrupo", 400


@app.route("/listas-materiales/<int:id>/pdf", methods=["GET"], endpoint="listas_materiales_pdf")
@app.route("/listas-materiales/<int:id>/pdf", methods=["GET"], endpoint="listas_materiales_pdf")
def listas_materiales_pdf(id):
    """Generar/visualizar PDF del presupuesto"""
    presupuesto = presupuestos.obtener_lista_material_por_id(id)
    if not presupuesto:
        return "Presupuesto no encontrado", 404

    items_disponibles = presupuestos.obtener_items_activos()
    tipos_items = presupuestos.obtener_tipos_items()

    html = render_template(
        'listas_materiales/pdf.html',
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

# ==================== RUTAS DE ITEMS MANO DE OBRA ====================

@app.route("/listas-materiales/items_mano_de_obra", methods=["GET"])
def items_index():
    """Lista de items"""
    tipo = request.args.get("tipo")
    items_lista = presupuestos.obtener_items_activos(tipo=tipo)
    tipos_lista = presupuestos.obtener_tipos_items()
    return render_template('listas_materiales/items_mano_de_obra/index.html', 
                         items=items_lista, 
                         tipos=tipos_lista,
                         tipo_filtro=tipo,
                         request=request)

@app.route("/listas-materiales/items_mano_de_obra/nuevo", methods=["GET", "POST"])
def items_nuevo():
    """Crear nuevo item"""
    if request.method == "POST":
        codigo = _to_upper(request.form.get("codigo")) if request.form.get("codigo") else None
        descripcion = _to_upper(request.form.get("descripcion"))
        if not descripcion:
            return "Descripción es requerida", 400
        tipo = _to_upper(request.form.get("tipo") or "Otros")
        unidad = _to_upper(request.form.get("unidad") or "unidad")
        precio_base = request.form.get("precio_base")
        try:
            precio_base = float(precio_base) if precio_base else 0
        except ValueError:
            precio_base = 0
        notas = _to_upper(request.form.get("notas")) if request.form.get("notas") else None
        
        # Auto-asignar código si no se proporcionó uno
        if not codigo:
            codigo = presupuestos.obtener_siguiente_numero_codigo(tipo)
        
        try:
            presupuestos.crear_item(
                codigo=codigo,
                descripcion=descripcion,
                tipo=tipo,
                unidad=unidad,
                precio_base=precio_base,
                margen_porcentaje=0,
                notas=notas
            )
            return redirect(url_for('items_index'))
        except Exception as e:
            return f"Error al crear item: {str(e)}", 400
    
    tipos_lista = presupuestos.obtener_tipos_items()
    return render_template('listas_materiales/items_mano_de_obra/form.html', 
                         item=None, 
                         tipos=tipos_lista,
                         request=request)

@app.route("/listas-materiales/items_mano_de_obra/<int:id>/editar", methods=["GET", "POST"])
def items_editar(id):
    """Editar item"""
    item = presupuestos.obtener_item_por_id(id)
    if not item:
        return "Item no encontrado", 404
    
    if request.method == "POST":
        codigo = _to_upper(request.form.get("codigo")) if request.form.get("codigo") else None
        descripcion = _to_upper(request.form.get("descripcion"))
        if not descripcion:
            return "Descripción es requerida", 400
        tipo = _to_upper(request.form.get("tipo") or "Otros")
        unidad = _to_upper(request.form.get("unidad") or "unidad")
        precio_base = request.form.get("precio_base")
        try:
            precio_base = float(precio_base) if precio_base else 0
        except ValueError:
            precio_base = 0
        activo = request.form.get("activo")
        activo = activo == "on" or activo == "1" or activo == "true"
        notas = _to_upper(request.form.get("notas")) if request.form.get("notas") else None
        
        try:
            if presupuestos.actualizar_item(
                item_id=id,
                codigo=codigo,
                descripcion=descripcion,
                tipo=tipo,
                unidad=unidad,
                precio_base=precio_base,
                margen_porcentaje=0,
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
    return render_template('listas_materiales/items_mano_de_obra/form.html', 
                         item=item_dict, 
                         tipos=tipos_lista,
                         request=request)

# ==================== RUTAS DE CLIENTES ====================

@app.route("/listas-materiales/clientes", methods=["GET"])
def clientes_index():
    """Lista de clientes"""
    clientes_lista = presupuestos.obtener_clientes()
    return render_template('listas_materiales/clientes/index.html', 
                         clientes=clientes_lista,
                         request=request)

@app.route("/listas-materiales/clientes/nuevo", methods=["GET", "POST"])
def clientes_nuevo():
    """Crear nuevo cliente"""
    if request.method == "POST":
        nombre = _to_upper(request.form.get("nombre"))
        if not nombre:
            return "Nombre es requerido", 400
        def _campo(valor):
            if not valor or not valor.strip():
                return "-"
            return _to_upper(valor.strip())
        razon_social = _campo(request.form.get("razon_social"))
        ruc = _campo(request.form.get("ruc"))
        direccion = _campo(request.form.get("direccion"))
        telefono = _campo(request.form.get("telefono"))
        email = request.form.get("email")
        email = email.strip() if email and email.strip() else "-"
        notas = _campo(request.form.get("notas"))
        
        try:
            presupuestos.crear_cliente(
                nombre=nombre,
                razon_social=razon_social,
                ruc=ruc,
                direccion=direccion,
                telefono=telefono,
                email=email,
                notas=notas
            )
            return redirect(url_for('clientes_index'))
        except Exception as e:
            return f"Error al crear cliente: {str(e)}", 400
    
    return render_template('listas_materiales/clientes/form.html', 
                         cliente=None,
                         request=request)


@app.route("/listas-materiales/clientes/<int:id>/editar", methods=["GET", "POST"])
def clientes_editar(id):
    """Editar un cliente existente"""
    cliente = presupuestos.obtener_cliente_por_id(id)
    if not cliente:
        return "Cliente no encontrado", 404
    if request.method == "POST":
        nombre = _to_upper(request.form.get("nombre"))
        if not nombre:
            return "Nombre es requerido", 400
        def _campo(valor):
            if not valor or not valor.strip():
                return "-"
            return _to_upper(valor.strip())
        razon_social = _campo(request.form.get("razon_social"))
        ruc = _campo(request.form.get("ruc"))
        direccion = _campo(request.form.get("direccion"))
        telefono = _campo(request.form.get("telefono"))
        email = request.form.get("email")
        email = email.strip() if email and email.strip() else "-"
        notas = _campo(request.form.get("notas"))
        try:
            presupuestos.actualizar_cliente(
                cliente_id=id,
                nombre=nombre,
                razon_social=razon_social,
                ruc=ruc,
                direccion=direccion,
                telefono=telefono,
                email=email,
                notas=notas
            )
            return redirect(url_for('clientes_index'))
        except Exception as e:
            return f"Error al actualizar cliente: {str(e)}", 400
    return render_template('listas_materiales/clientes/form.html',
                         cliente=cliente,
                         request=request)


@app.route("/listas-materiales/clientes/<int:id>/eliminar", methods=["POST"])
def clientes_eliminar(id):
    """Eliminar un cliente"""
    if presupuestos.eliminar_cliente(id):
        return redirect(url_for('clientes_index'))
    return "Error al eliminar cliente", 400

@app.route("/listas-materiales/materiales", methods=["GET"])
def materiales_index():
    descripcion = request.args.get("descripcion") or None
    marca = request.args.get("marca") or None
    materiales = presupuestos.buscar_materiales(descripcion=descripcion, marca=marca)
    materiales_list = [dict(m) for m in materiales]
    marcas = [dict(m) for m in presupuestos.obtener_marcas_materiales(activo=True)]
    return render_template(
        'listas_materiales/materiales/index.html',
        materiales=materiales_list,
        descripcion_filtro=descripcion or "",
        marca_filtro=marca or "",
        marcas=marcas,
        request=request
    )

@app.route("/listas-materiales/materiales/<int:id>/editar", methods=["GET", "POST"])
def materiales_editar(id):
    material = presupuestos.obtener_material_por_id(id)
    if not material:
        return "Material no encontrado", 404
    if request.method == "POST":
        descripcion = _to_upper(request.form.get("descripcion")) if request.form.get("descripcion") else None
        marca = _to_upper(request.form.get("marca")) if request.form.get("marca") else None
        marca_id = request.form.get("marca_id")
        try:
            marca_id = int(marca_id) if marca_id else None
        except ValueError:
            marca_id = None
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
            marca=marca,
            marca_id=marca_id,
            precio=precio,
            tiempo_instalacion=tiempo
        )
        return redirect(url_for('materiales_index'))
    marcas = [dict(m) for m in presupuestos.obtener_marcas_materiales()]
    return render_template('listas_materiales/materiales/form.html', material=dict(material), marcas=marcas, request=request)


@app.route("/listas-materiales/materiales/<int:id>/eliminar", methods=["POST"])
def materiales_eliminar(id):
    if presupuestos.eliminar_material(id):
        return redirect(url_for('materiales_index'))
    return "Error al eliminar material", 400

# ==================== RUTAS DE MARCAS DE MATERIALES ====================

@app.route("/listas-materiales/marcas_materiales", methods=["GET"])
def marcas_materiales_index():
    """Listado de marcas para materiales"""
    busqueda = request.args.get("q") or None
    activo = request.args.get("activo")
    if activo not in ("true", "false"):
        activo_filtro = None
    else:
        activo_filtro = activo == "true"
    marcas = presupuestos.obtener_marcas_materiales(activo=activo_filtro, busqueda=busqueda)
    return render_template(
        'listas_materiales/marcas/index.html',
        marcas=[dict(m) for m in marcas],
        busqueda=busqueda or "",
        activo_filtro=activo,
        request=request
    )


@app.route("/listas-materiales/marcas_materiales/nuevo", methods=["GET", "POST"])
def marcas_materiales_nuevo():
    """Crear nueva marca"""
    if request.method == "POST":
        nombre = _to_upper(request.form.get("nombre"))
        if not nombre:
            return "Nombre requerido", 400
        descripcion = _to_upper(request.form.get("descripcion")) if request.form.get("descripcion") else None
        fabricante = _to_upper(request.form.get("fabricante")) if request.form.get("fabricante") else None
        pais_origen = _to_upper(request.form.get("pais_origen")) if request.form.get("pais_origen") else None
        sitio_web = request.form.get("sitio_web") or None
        contacto = _to_upper(request.form.get("contacto")) if request.form.get("contacto") else None
        notas = _to_upper(request.form.get("notas")) if request.form.get("notas") else None
        activo = request.form.get("activo") != "false"
        presupuestos.crear_marca_material(
            nombre=nombre,
            descripcion=descripcion,
            fabricante=fabricante,
            pais_origen=pais_origen,
            sitio_web=sitio_web,
            contacto=contacto,
            notas=notas,
            activo=activo
        )
        return redirect(url_for('marcas_materiales_index'))
    return render_template('listas_materiales/marcas/form.html', marca=None, request=request)


@app.route("/listas-materiales/marcas_materiales/<int:id>/editar", methods=["GET", "POST"])
def marcas_materiales_editar(id):
    """Editar marca existente"""
    marca = presupuestos.obtener_marca_material_por_id(id)
    if not marca:
        return "Marca no encontrada", 404
    if request.method == "POST":
        nombre = _to_upper(request.form.get("nombre")) if request.form.get("nombre") else None
        descripcion = _to_upper(request.form.get("descripcion")) if request.form.get("descripcion") else None
        fabricante = _to_upper(request.form.get("fabricante")) if request.form.get("fabricante") else None
        pais_origen = _to_upper(request.form.get("pais_origen")) if request.form.get("pais_origen") else None
        sitio_web = request.form.get("sitio_web") or None
        contacto = _to_upper(request.form.get("contacto")) if request.form.get("contacto") else None
        notas = _to_upper(request.form.get("notas")) if request.form.get("notas") else None
        activo = request.form.get("activo")
        if activo is not None:
            activo = activo == "true"
        presupuestos.actualizar_marca_material(
            marca_id=id,
            nombre=nombre,
            descripcion=descripcion,
            fabricante=fabricante,
            pais_origen=pais_origen,
            sitio_web=sitio_web,
            contacto=contacto,
            notas=notas,
            activo=activo
        )
        return redirect(url_for('marcas_materiales_index'))
    return render_template('listas_materiales/marcas/form.html', marca=dict(marca), request=request)


@app.route("/listas-materiales/marcas_materiales/<int:id>/eliminar", methods=["POST"])
def marcas_materiales_eliminar(id):
    """Eliminar una marca"""
    if presupuestos.eliminar_marca_material(id):
        return redirect(url_for('marcas_materiales_index'))
    return "Error al eliminar marca", 400

# ==================== RUTAS DE PROVEEDORES ====================

@app.route("/proveedores", methods=["GET"])
def proveedores_index():
    busqueda = request.args.get("q") or None
    activo = request.args.get("activo")
    if activo not in ("true", "false"):
        activo_filtro = None
    else:
        activo_filtro = activo == "true"
    proveedores = presupuestos.obtener_proveedores(activo=activo_filtro, busqueda=busqueda)
    return render_template(
        'proveedores/index.html',
        proveedores=proveedores,
        busqueda=busqueda or "",
        activo_filtro=activo,
        request=request
    )


@app.route("/proveedores/nuevo", methods=["GET", "POST"])
def proveedores_nuevo():
    if request.method == "POST":
        nombre = _to_upper(request.form.get("nombre"))
        if not nombre:
            return "Nombre es requerido", 400
        def _campo(valor):
            if not valor or not valor.strip():
                return "-"
            return _to_upper(valor.strip())
        razon_social = _campo(request.form.get("razon_social"))
        ruc = _campo(request.form.get("ruc"))
        direccion = _campo(request.form.get("direccion"))
        telefono = _campo(request.form.get("telefono"))
        email = request.form.get("email")
        email = email.strip() if email and email.strip() else "-"
        contacto = _campo(request.form.get("contacto"))
        notas = _campo(request.form.get("notas"))
        activo = request.form.get("activo") != "false"
        try:
            presupuestos.crear_proveedor(
                nombre=nombre,
                razon_social=razon_social,
                ruc=ruc,
                direccion=direccion,
                telefono=telefono,
                email=email,
                contacto=contacto,
                notas=notas,
                activo=activo
            )
            return redirect(url_for('proveedores_index'))
        except Exception as e:
            return f"Error al crear proveedor: {str(e)}", 400
    return render_template('proveedores/form.html', proveedor=None, request=request)


@app.route("/proveedores/<int:id>/editar", methods=["GET", "POST"])
def proveedores_editar(id):
    proveedor = presupuestos.obtener_proveedor_por_id(id)
    if not proveedor:
        return "Proveedor no encontrado", 404
    if request.method == "POST":
        nombre = _to_upper(request.form.get("nombre")) if request.form.get("nombre") else None
        if not nombre:
            return "Nombre es requerido", 400
        def _campo(valor):
            if not valor or not valor.strip():
                return "-"
            return _to_upper(valor.strip())
        razon_social = _campo(request.form.get("razon_social"))
        ruc = _campo(request.form.get("ruc"))
        direccion = _campo(request.form.get("direccion"))
        telefono = _campo(request.form.get("telefono"))
        email = request.form.get("email")
        email = email.strip() if email and email.strip() else "-"
        contacto = _campo(request.form.get("contacto"))
        notas = _campo(request.form.get("notas"))
        activo = request.form.get("activo")
        if activo is not None:
            activo = activo == "true"
        try:
            presupuestos.actualizar_proveedor(
                proveedor_id=id,
                nombre=nombre,
                razon_social=razon_social,
                ruc=ruc,
                direccion=direccion,
                telefono=telefono,
                email=email,
                contacto=contacto,
                notas=notas,
                activo=activo
            )
            return redirect(url_for('proveedores_index'))
        except Exception as e:
            return f"Error al actualizar proveedor: {str(e)}", 400
    return render_template('proveedores/form.html', proveedor=proveedor, request=request)


@app.route("/proveedores/<int:id>/eliminar", methods=["POST"])
def proveedores_eliminar(id):
    if presupuestos.eliminar_proveedor(id):
        return redirect(url_for('proveedores_index'))
    return "Error al eliminar proveedor", 400

# ==================== RUTAS DE MATERIALES GENÉRICOS ====================

@app.route("/listas-materiales/materiales_genericos", methods=["GET"])
def materiales_genericos_index():
    """Lista de materiales genéricos"""
    descripcion_filtro = request.args.get("descripcion") or None
    materiales_lista = presupuestos.buscar_materiales_genericos(descripcion=descripcion_filtro)
    materiales_list = [dict(m) for m in materiales_lista]
    
    # Manejar mensajes de importación
    mensaje_importacion = None
    error = request.args.get("error")
    importacion_exito = request.args.get("importacion_exito")
    duplicados = request.args.get("duplicados")
    duplicados_archivo = request.args.get("duplicados_archivo")
    errores = request.args.get("errores")
    
    if error:
        mensaje_importacion = {
            'tipo': 'error',
            'mensaje': error,
            'detalles': []
        }
    elif importacion_exito:
        mensaje_importacion = {
            'tipo': 'exito' if int(importacion_exito) > 0 else 'error',
            'mensaje': f'Se importaron {importacion_exito} material(es) correctamente.' if int(importacion_exito) > 0 else 'No se importó ningún material.',
            'detalles': []
        }
        if duplicados_archivo and int(duplicados_archivo) > 0:
            mensaje_importacion['detalles'].append(f'{duplicados_archivo} material(es) duplicado(s) dentro del archivo fueron omitidos (solo se procesó uno por nombre).')
        if duplicados and int(duplicados) > 0:
            mensaje_importacion['detalles'].append(f'{duplicados} material(es) ya existían en la base de datos y fueron omitidos.')
        if errores and int(errores) > 0:
            mensaje_importacion['detalles'].append(f'{errores} fila(s) tuvieron errores y no se importaron.')
    
    return render_template(
        'listas_materiales/materiales_genericos/index.html',
        materiales=materiales_list,
        descripcion_filtro=descripcion_filtro or "",
        mensaje_importacion=mensaje_importacion,
        request=request
    )

@app.route("/listas-materiales/materiales_genericos/nuevo", methods=["GET", "POST"])
def materiales_genericos_nuevo():
    """Crear nuevo material genérico"""
    if request.method == "POST":
        descripcion = _to_upper(request.form.get("descripcion"))
        tiempo_str = request.form.get("tiempo_instalacion") or "0"
        unidad = _to_upper(request.form.get("unidad") or "UND")
        if not descripcion:
            return render_template('listas_materiales/materiales_genericos/form.html', 
                                 material=None, request=request, 
                                 error="Descripción es requerida", mostrar_salir=False)
        try:
            tiempo_instalacion = float(tiempo_str)
        except ValueError:
            tiempo_instalacion = 0.0
        try:
            presupuestos.crear_material_generico(
                descripcion=descripcion,
                tiempo_instalacion=tiempo_instalacion,
                unidad=unidad
            )
            # Mostrar formulario vacío con mensaje de éxito
            return render_template('listas_materiales/materiales_genericos/form.html', 
                                 material=None, request=request, 
                                 mensaje_exito=f"Material '{descripcion}' guardado correctamente", 
                                 mostrar_salir=True)
        except Exception as e:
            return render_template('listas_materiales/materiales_genericos/form.html', 
                                 material=None, request=request, 
                                 error=f"Error al crear material: {str(e)}", mostrar_salir=False)
    return render_template('listas_materiales/materiales_genericos/form.html', 
                         material=None, request=request, mostrar_salir=False)

@app.route("/listas-materiales/materiales_genericos/<int:id>/editar", methods=["GET", "POST"])
def materiales_genericos_editar(id):
    """Editar material genérico"""
    material = presupuestos.obtener_material_generico_por_id(id)
    if not material:
        return "Material no encontrado", 404
    if request.method == "POST":
        descripcion = _to_upper(request.form.get("descripcion")) if request.form.get("descripcion") else None
        tiempo_str = request.form.get("tiempo_instalacion")
        unidad = _to_upper(request.form.get("unidad")) if request.form.get("unidad") else None
        try:
            tiempo_instalacion = float(tiempo_str) if tiempo_str else None
        except ValueError:
            tiempo_instalacion = None
        presupuestos.actualizar_material_generico(
            material_id=id,
            descripcion=descripcion,
            tiempo_instalacion=tiempo_instalacion,
            unidad=unidad
        )
        return redirect(url_for('materiales_genericos_index'))
    return render_template('listas_materiales/materiales_genericos/form.html', material=dict(material), request=request)

@app.route("/listas-materiales/materiales_genericos/<int:id>/eliminar", methods=["POST"])
def materiales_genericos_eliminar(id):
    """Eliminar material genérico"""
    if presupuestos.eliminar_material_generico(id):
        return redirect(url_for('materiales_genericos_index'))
    return "Error al eliminar material", 400

@app.route("/listas-materiales/materiales_genericos/exportar_csv", methods=["GET"])
def materiales_genericos_exportar_csv():
    """Exportar materiales genéricos a un archivo CSV"""
    try:
        # Obtener todos los materiales genéricos
        materiales_lista = presupuestos.obtener_materiales_genericos()
        materiales_list = [dict(m) for m in materiales_lista]
        
        # Crear el contenido CSV en memoria
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Escribir encabezados
        writer.writerow(['descripcion', 'unidad', 'tiempo_instalacion'])
        
        # Escribir datos
        for material in materiales_list:
            descripcion = material.get('descripcion', '')
            unidad = material.get('unidad', 'UND') or 'UND'
            tiempo_instalacion = material.get('tiempo_instalacion', 0) or 0
            writer.writerow([descripcion, unidad, tiempo_instalacion])
        
        # Crear la respuesta
        output.seek(0)
        response = make_response(output.getvalue())
        
        # Configurar headers para descarga
        fecha_actual = datetime.now().strftime('%Y%m%d_%H%M%S')
        nombre_archivo = f'materiales_genericos_{fecha_actual}.csv'
        response.headers['Content-Disposition'] = f'attachment; filename={nombre_archivo}'
        response.headers['Content-Type'] = 'text/csv; charset=utf-8'
        
        return response
    
    except Exception as e:
        return f"Error al exportar: {str(e)}", 500

@app.route("/listas-materiales/materiales_genericos/importar_csv", methods=["POST"])
def materiales_genericos_importar_csv():
    """Importar materiales genéricos desde un archivo CSV"""
    if 'archivo_csv' not in request.files:
        return redirect(url_for('materiales_genericos_index') + '?error=No se seleccionó ningún archivo')
    
    archivo = request.files['archivo_csv']
    if archivo.filename == '':
        return redirect(url_for('materiales_genericos_index') + '?error=No se seleccionó ningún archivo')
    
    if not archivo.filename.endswith('.csv'):
        return redirect(url_for('materiales_genericos_index') + '?error=El archivo debe ser un CSV')
    
    materiales_creados = 0
    materiales_duplicados = 0
    materiales_error = []
    errores_generales = []
    
    try:
        # Leer el archivo CSV
        contenido = archivo.stream.read().decode('utf-8-sig')  # utf-8-sig maneja BOM
        archivo.stream.seek(0)  # Resetear el stream
        
        # Parsear CSV
        try:
            csv_reader = csv.DictReader(io.StringIO(contenido))
        except Exception as e:
            return redirect(url_for('materiales_genericos_index') + f'?error=Error al leer el CSV: {str(e)}')
        
        # Validar que tenga la columna descripcion
        if 'descripcion' not in csv_reader.fieldnames:
            return redirect(url_for('materiales_genericos_index') + '?error=El CSV debe tener una columna llamada "descripcion"')
        
        # Primero, agrupar materiales únicos por descripción (normalizada a mayúsculas)
        materiales_unicos = {}  # clave: descripcion_upper, valor: {descripcion, unidad, tiempo, primera_fila}
        duplicados_en_archivo = 0
        
        for num_fila, fila in enumerate(csv_reader, start=2):  # start=2 porque la fila 1 es el header
            try:
                descripcion = fila.get('descripcion', '').strip()
                if not descripcion:
                    materiales_error.append(f"Fila {num_fila}: Descripción vacía")
                    continue
                
                descripcion_upper = _to_upper(descripcion)
                
                # Si ya existe esta descripción en el diccionario, contar como duplicado en archivo
                if descripcion_upper in materiales_unicos:
                    duplicados_en_archivo += 1
                    continue  # Omitir duplicados dentro del mismo archivo
                
                unidad = fila.get('unidad', 'UND').strip() or 'UND'
                tiempo_str = fila.get('tiempo_instalacion', '0').strip() or '0'
                
                try:
                    tiempo_instalacion = float(tiempo_str)
                except (ValueError, TypeError):
                    tiempo_instalacion = 0.0
                
                # Guardar este material único
                materiales_unicos[descripcion_upper] = {
                    'descripcion': descripcion,
                    'unidad': unidad,
                    'tiempo_instalacion': tiempo_instalacion,
                    'primera_fila': num_fila
                }
            
            except Exception as e:
                materiales_error.append(f"Fila {num_fila}: Error inesperado - {str(e)}")
        
        # Ahora procesar solo los materiales únicos
        for descripcion_upper, material_data in materiales_unicos.items():
            try:
                # Intentar crear el material
                presupuestos.crear_material_generico(
                    descripcion=material_data['descripcion'],
                    tiempo_instalacion=material_data['tiempo_instalacion'],
                    unidad=material_data['unidad']
                )
                materiales_creados += 1
            except Exception as e:
                error_msg = str(e).lower()
                # Verificar si es un error de duplicado/unique constraint (ya existe en BD)
                if any(keyword in error_msg for keyword in ['unique', 'duplicate', 'ya existe', 'duplicate key', 'violates unique constraint']):
                    materiales_duplicados += 1
                else:
                    materiales_error.append(f"Fila {material_data['primera_fila']} ({material_data['descripcion']}): {str(e)}")
        
        # Preparar mensaje de resultado
        mensaje_importacion = {
            'tipo': 'exito' if materiales_creados > 0 else 'error',
            'mensaje': '',
            'detalles': []
        }
        
        if materiales_creados > 0:
            mensaje_importacion['mensaje'] = f'Se importaron {materiales_creados} material(es) correctamente.'
        else:
            mensaje_importacion['mensaje'] = 'No se importó ningún material.'
        
        if duplicados_en_archivo > 0:
            mensaje_importacion['detalles'].append(f'{duplicados_en_archivo} material(es) duplicado(s) dentro del archivo fueron omitidos (solo se procesó uno por nombre).')
        
        if materiales_duplicados > 0:
            mensaje_importacion['detalles'].append(f'{materiales_duplicados} material(es) ya existían en la base de datos y fueron omitidos.')
        
        if materiales_error:
            mensaje_importacion['tipo'] = 'error' if materiales_creados == 0 else 'exito'
            mensaje_importacion['detalles'].extend(materiales_error[:10])  # Limitar a 10 errores
            if len(materiales_error) > 10:
                mensaje_importacion['detalles'].append(f'... y {len(materiales_error) - 10} error(es) más.')
        
        # Redirigir con mensaje
        return redirect(url_for('materiales_genericos_index') + f'?importacion_exito={materiales_creados}&duplicados={materiales_duplicados}&duplicados_archivo={duplicados_en_archivo}&errores={len(materiales_error)}')
    
    except Exception as e:
        return redirect(url_for('materiales_genericos_index') + f'?error=Error al procesar el archivo: {str(e)}')

# ==================== ASIGNACIÓN DE PRECIOS POR LISTA ====================
MAX_PROVEEDORES = 5

def _obtener_items_lista(lista):
    items = []
    for subgrupo in lista.get('subgrupos', []) or []:
        for item in subgrupo.get('items', []) or []:
            item_dict = dict(item)
            item_dict['subgrupo'] = {'id': subgrupo['id'], 'nombre': subgrupo['nombre'], 'numero': subgrupo['numero']}
            items.append(item_dict)
    for item in lista.get('items_sin_subgrupo', []) or []:
        items.append(dict(item))
    return items


def _agrupar_items_para_precios(items, precios_por_item, max_slots):
    grupos = OrderedDict()
    for item in items:
        key = (
            (item.get('descripcion') or '').strip().upper(),
            (item.get('marca') or '').strip().upper()
        )
        entry = grupos.setdefault(key, {
            'descripcion': item.get('descripcion'),
            'marca': item.get('marca'),
            'unidad': item.get('unidad') or 'UND',
            'items': []
        })
        entry['items'].append(item)
    
    grupos_lista = []
    for entry in grupos.values():
        items_grupo = entry['items']
        representante = items_grupo[0]
        precios_item = precios_por_item.get(representante['id'], [])
        slots = []
        for idx in range(max_slots):
            slots.append(precios_item[idx] if idx < len(precios_item) else None)
        precio_final = next((p for p in precios_item if p.get('seleccionado')), None)
        grupos_lista.append({
            'representante_id': representante['id'],
            'descripcion': entry['descripcion'],
            'marca': entry['marca'],
            'unidad': entry['unidad'],
            'items_agrupados': items_grupo,
            'cantidad_total': sum(float(i.get('cantidad') or 0) for i in items_grupo),
            'slots': slots,
            'precio_final': precio_final
        })
    return grupos_lista


@app.route("/listas-materiales/<int:id>/precios", methods=["GET"])
def listas_materiales_precios(id):
    lista = presupuestos.obtener_lista_material_por_id(id)
    if not lista:
        return "Lista no encontrada", 404
    items = _obtener_items_lista(lista)
    proveedores = presupuestos.obtener_proveedores(activo=True)
    precios_por_item = {item['id']: presupuestos.obtener_precios_por_item(item['id']) for item in items}
    grupos_precios = _agrupar_items_para_precios(items, precios_por_item, MAX_PROVEEDORES)
    return render_template(
        'listas_materiales/precios.html',
        lista=lista,
        grupos_precios=grupos_precios,
        proveedores=proveedores,
        max_proveedores=MAX_PROVEEDORES,
        request=request
    )


@app.route("/listas-materiales/items/<int:item_id>/precios/agregar", methods=["POST"])
def listas_agregar_precio_item(item_id):
    lista_id = request.form.get("lista_id")
    proveedor_id = request.form.get("proveedor_id")
    precio = request.form.get("precio")
    moneda = request.form.get("moneda") or "PYG"
    fecha = request.form.get("fecha_cotizacion") or None
    notas = _to_upper(request.form.get("notas")) if request.form.get("notas") else None
    seleccionado = request.form.get("seleccionado") == "on"
    try:
        proveedor_id = int(proveedor_id)
    except (TypeError, ValueError):
        return "Proveedor inválido", 400
    try:
        precio_val = float(precio)
    except (TypeError, ValueError):
        return "Precio inválido", 400
    try:
        presupuestos.agregar_precio_item(
            lista_material_item_id=item_id,
            proveedor_id=proveedor_id,
            precio=precio_val,
            moneda=moneda,
            fecha_cotizacion=fecha,
            notas=notas,
            seleccionado=seleccionado
        )
    except Exception as e:
        return f"Error al agregar precio: {str(e)}", 400
    return redirect(url_for('listas_materiales_precios', id=lista_id))


@app.route("/listas-materiales/items/<int:item_id>/precios/slot", methods=["POST"])
def listas_guardar_precio_slot(item_id):
    """Crear o actualizar una cotización en una de las columnas de proveedores"""
    lista_id = request.form.get("lista_id")
    precio_id = request.form.get("precio_id") or None
    proveedor_id = request.form.get("proveedor_id")
    precio_valor = request.form.get("precio")
    moneda = request.form.get("moneda") or "PYG"
    notas = _to_upper(request.form.get("notas")) if request.form.get("notas") else None
    es_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    if not lista_id:
        return "Lista ID es requerido", 400
    try:
        lista_id = int(lista_id)
    except ValueError:
        return "Lista ID inválido", 400
    
    if not proveedor_id:
        return "Proveedor es requerido", 400
    try:
        proveedor_id = int(proveedor_id)
    except ValueError:
        return "Proveedor inválido", 400
    
    try:
        precio_float = float(precio_valor)
    except (TypeError, ValueError):
        return "Precio inválido", 400
    
    try:
        if precio_id:
            precio_id_int = int(precio_id)
            presupuestos.actualizar_precio_item(
                precio_id=precio_id_int,
                proveedor_id=proveedor_id,
                precio=precio_float,
                moneda=moneda,
                notas=notas
            )
        else:
            precio_id_int = presupuestos.agregar_precio_item(
                lista_material_item_id=item_id,
                proveedor_id=proveedor_id,
                precio=precio_float,
                moneda=moneda,
                notas=notas,
                seleccionado=False
            )
    except ValueError as e:
        if es_ajax:
            return jsonify({'success': False, 'error': str(e)}), 400
        return str(e), 400
    
    presupuestos.seleccionar_precio_item(precio_id_int)
    precio_final = presupuestos.obtener_precio_por_id(precio_id_int)
    
    if es_ajax:
        if precio_final:
            respuesta = {
                'success': True,
                'precio_id': precio_id_int,
                'precio_final': {
                    'proveedor': precio_final.get('proveedor_nombre'),
                    'moneda': precio_final.get('moneda') or 'PYG',
                    'precio': float(precio_final.get('precio') or 0),
                }
            }
        else:
            respuesta = {'success': True, 'precio_id': precio_id_int, 'precio_final': None}
        return jsonify(respuesta)
    
    return redirect(url_for('listas_materiales_precios', id=lista_id))


@app.route("/listas-materiales/precios/<int:precio_id>/seleccionar", methods=["POST"])
def listas_seleccionar_precio(precio_id):
    lista_id = request.form.get("lista_id")
    presupuestos.seleccionar_precio_item(precio_id)
    return redirect(url_for('listas_materiales_precios', id=lista_id))


@app.route("/listas-materiales/precios/<int:precio_id>/eliminar", methods=["POST"])
def listas_eliminar_precio(precio_id):
    lista_id = request.form.get("lista_id")
    presupuestos.eliminar_precio_item(precio_id)
    return redirect(url_for('listas_materiales_precios', id=lista_id))


@app.route("/listas-materiales/items/<int:item_id>/precios/criterio", methods=["POST"])
def listas_seleccionar_precio_criterio(item_id):
    lista_id = request.form.get("lista_id")
    criterio = request.form.get("criterio") or "menor"
    presupuestos.seleccionar_precio_por_criterio(item_id, criterio)
    return redirect(url_for('listas_materiales_precios', id=lista_id))

# ==================== RUTAS DE TEMPLATES DE PRESUPUESTOS ====================

@app.route("/listas-materiales/templates", methods=["GET"])
def templates_index():
    """Lista de templates de presupuestos"""
    templates_lista = presupuestos.obtener_templates_listas_materiales()
    templates_list = [dict(t) for t in templates_lista]
    return render_template(
        'listas_materiales/templates/index.html',
        templates=templates_list,
        request=request
    )

@app.route("/listas-materiales/templates/nuevo", methods=["GET", "POST"])
def templates_nuevo():
    """Crear nuevo template"""
    if request.method == "POST":
        nombre = _to_upper(request.form.get("nombre"))
        descripcion = _to_upper(request.form.get("descripcion")) if request.form.get("descripcion") else None
        if not nombre:
            return "Nombre es requerido", 400
        try:
            template_id = presupuestos.crear_template(nombre=nombre, descripcion=descripcion)
            return redirect(url_for('templates_ver', id=template_id))
        except Exception as e:
            return f"Error al crear template: {str(e)}", 400
    
    items_mano_de_obra = presupuestos.obtener_items_activos()
    materiales_genericos = presupuestos.obtener_materiales_genericos()
    return render_template(
        'listas_materiales/templates/form.html',
        template=None,
        items_mano_de_obra=[dict(i) for i in items_mano_de_obra],
        materiales_genericos=[dict(m) for m in materiales_genericos],
        request=request
    )

@app.route("/listas-materiales/templates/<int:id>", methods=["GET"])
def templates_ver(id):
    """Ver template con sus items"""
    template = presupuestos.obtener_template_por_id(id)
    if not template:
        return "Template no encontrado", 404
    
    items_mano_de_obra = presupuestos.obtener_items_activos()
    materiales_genericos = presupuestos.obtener_materiales_genericos()
    
    return render_template(
        'listas_materiales/templates/ver.html',
        template=template,
        items_mano_de_obra=[dict(i) for i in items_mano_de_obra],
        materiales_genericos=[dict(m) for m in materiales_genericos],
        request=request
    )

@app.route("/listas-materiales/templates/<int:id>/editar", methods=["GET", "POST"])
def templates_editar(id):
    """Editar template"""
    template = presupuestos.obtener_template_por_id(id)
    if not template:
        return "Template no encontrado", 404
    
    if request.method == "POST":
        nombre = _to_upper(request.form.get("nombre")) if request.form.get("nombre") else None
        descripcion = _to_upper(request.form.get("descripcion")) if request.form.get("descripcion") else None
        presupuestos.actualizar_template(
            template_id=id,
            nombre=nombre,
            descripcion=descripcion
        )
        return redirect(url_for('templates_ver', id=id))
    
    items_mano_de_obra = presupuestos.obtener_items_activos()
    materiales_genericos = presupuestos.obtener_materiales_genericos()
    return render_template(
        'listas_materiales/templates/form.html',
        template=template,
        items_mano_de_obra=[dict(i) for i in items_mano_de_obra],
        materiales_genericos=[dict(m) for m in materiales_genericos],
        request=request
    )

@app.route("/listas-materiales/templates/<int:id>/eliminar", methods=["POST"])
def templates_eliminar(id):
    """Eliminar template"""
    if presupuestos.eliminar_template(id):
        return redirect(url_for('templates_index'))
    return "Error al eliminar template", 400

@app.route("/listas-materiales/templates/<int:template_id>/items/agregar", methods=["POST"])
def templates_agregar_item(template_id):
    """Agregar item a template"""
    item_mano_de_obra_id = request.form.get("item_mano_de_obra_id")
    material_generico_id = request.form.get("material_generico_id")
    cantidad = request.form.get("cantidad") or "1"
    orden = request.form.get("orden") or "0"
    
    try:
        item_mano_de_obra_id = int(item_mano_de_obra_id) if item_mano_de_obra_id else None
        material_generico_id = int(material_generico_id) if material_generico_id else None
        cantidad = float(cantidad)
        orden = int(orden)
    except ValueError:
        return "Valores inválidos", 400
    
    if not item_mano_de_obra_id and not material_generico_id:
        return "Debe seleccionar un item o material genérico", 400
    
    try:
        presupuestos.agregar_item_a_template(
            template_id=template_id,
            item_mano_de_obra_id=item_mano_de_obra_id,
            material_generico_id=material_generico_id,
            cantidad=cantidad,
            orden=orden
        )
        return redirect(url_for('templates_ver', id=template_id))
    except Exception as e:
        return f"Error al agregar item: {str(e)}", 400

@app.route("/listas-materiales/templates/items/<int:item_id>/eliminar", methods=["POST"])
def templates_eliminar_item(item_id):
    """Eliminar item de template"""
    template_id = request.form.get("template_id")
    try:
        template_id = int(template_id) if template_id else None
    except ValueError:
        return "Template ID inválido", 400
    
    if presupuestos.eliminar_item_de_template(item_id):
        return redirect(url_for('templates_ver', id=template_id))
    return "Error al eliminar item", 400

@app.route("/listas-materiales/<int:lista_id>/aplicar_template", methods=["POST"])
def listas_materiales_aplicar_template(lista_id):
    """Aplicar template a una lista de materiales"""
    template_id = request.form.get("template_id")
    subgrupo_id = request.form.get("subgrupo_id")
    
    try:
        template_id = int(template_id) if template_id else None
        subgrupo_id = int(subgrupo_id) if subgrupo_id else None
    except ValueError:
        return "Valores inválidos", 400
    
    if not template_id:
        return "Template ID es requerido", 400
    
    try:
        items_agregados = presupuestos.aplicar_template_a_lista_material(
            lista_material_id=lista_id,
            template_id=template_id,
            subgrupo_id=subgrupo_id
        )
        return redirect(url_for('listas_materiales_ver', id=lista_id))
    except Exception as e:
        return f"Error al aplicar template: {str(e)}", 400


# ==================== RUTAS DE PREFIJOS DE CÓDIGOS ====================

@app.route("/listas-materiales/prefijos_codigos", methods=["GET"])
def prefijos_codigos_index():
    """Lista de prefijos de códigos"""
    prefijos = presupuestos.obtener_prefijos_codigos()
    return render_template('listas_materiales/prefijos_codigos/index.html', 
                         prefijos=prefijos,
                         request=request)

@app.route("/listas-materiales/prefijos_codigos/nuevo", methods=["GET", "POST"])
def prefijos_codigos_nuevo():
    """Crear nuevo prefijo"""
    if request.method == "POST":
        tipo_servicio = _to_upper(request.form.get("tipo_servicio"))
        if not tipo_servicio:
            return "Tipo de servicio es requerido", 400
        prefijo = _to_upper(request.form.get("prefijo"))
        if not prefijo:
            return "Prefijo es requerido", 400
        activo = request.form.get("activo") != "false"
        
        try:
            presupuestos.crear_prefijo_codigo(
                tipo_servicio=tipo_servicio,
                prefijo=prefijo,
                activo=activo
            )
            return redirect(url_for('prefijos_codigos_index'))
        except Exception as e:
            return f"Error al crear prefijo: {str(e)}", 400
    
    return render_template('listas_materiales/prefijos_codigos/form.html', 
                         prefijo=None,
                         request=request)

@app.route("/listas-materiales/prefijos_codigos/<int:id>/editar", methods=["GET", "POST"])
def prefijos_codigos_editar(id):
    """Editar prefijo"""
    prefijo = presupuestos.obtener_prefijo_por_id(id)
    if not prefijo:
        return "Prefijo no encontrado", 404
    
    if request.method == "POST":
        tipo_servicio = _to_upper(request.form.get("tipo_servicio"))
        if not tipo_servicio:
            return "Tipo de servicio es requerido", 400
        prefijo_val = _to_upper(request.form.get("prefijo"))
        if not prefijo_val:
            return "Prefijo es requerido", 400
        activo = request.form.get("activo") != "false"
        
        try:
            presupuestos.actualizar_prefijo_codigo(
                prefijo_id=id,
                tipo_servicio=tipo_servicio,
                prefijo=prefijo_val,
                activo=activo
            )
            return redirect(url_for('prefijos_codigos_index'))
        except Exception as e:
            return f"Error al actualizar prefijo: {str(e)}", 400
    
    return render_template('listas_materiales/prefijos_codigos/form.html', 
                         prefijo=prefijo,
                         request=request)

@app.route("/listas-materiales/prefijos_codigos/<int:id>/eliminar", methods=["POST"])
def prefijos_codigos_eliminar(id):
    """Eliminar prefijo"""
    if presupuestos.eliminar_prefijo_codigo(id):
        return redirect(url_for('prefijos_codigos_index'))
    return "Error al eliminar prefijo", 400

@app.route("/api/obtener_codigo_por_prefijo", methods=["GET"])
def api_obtener_codigo_por_prefijo():
    """API endpoint para obtener el siguiente código disponible por prefijo"""
    prefijo = request.args.get("prefijo", "").strip().upper()
    if not prefijo:
        return jsonify({"error": "Prefijo requerido"}), 400
    
    codigo = presupuestos.obtener_siguiente_codigo_por_prefijo(prefijo)
    if codigo:
        return jsonify({"codigo": codigo})
    else:
        return jsonify({"error": "No se pudo generar el código"}), 400

if __name__ == "__main__":
    # App unificada
    app.run(host="127.0.0.1", port=5000, debug=True)


