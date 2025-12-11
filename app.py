from flask import Flask, request, render_template, redirect, url_for, jsonify, session
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
import presupuestos_db
from flask import make_response
from datetime import datetime
from collections import OrderedDict
import procesar_presupuesto_ocr as ocr_processor
import auth
import psycopg2
import facturacion
import reportes_clientes
import financiero

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
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'change-this-secret-key-in-production')

# Agregar funciones útiles al contexto global de Jinja2
app.jinja_env.globals['abs'] = abs

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


# ============================================
# RUTAS DE AUTENTICACIÓN
# ============================================

@app.route("/login", methods=["GET", "POST"])
def login():
    """Ruta de login"""
    if request.method == "POST":
        username_or_email = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        next_url = request.form.get('next') or url_for('menu')
        
        # Verificar primero si el usuario tiene registro incompleto (antes de pedir contraseña)
        usuario_incompleto = auth.verificar_usuario_incompleto_por_email(username_or_email)
        if usuario_incompleto:
            # Si es un usuario incompleto, redirigir directamente a completar registro
            session['usuario_incompleto_id'] = usuario_incompleto['id']
            session['usuario_incompleto_email'] = usuario_incompleto['email']
            return redirect(url_for('completar_registro'))
        
        # Si no es usuario incompleto, intentar login normal (requiere contraseña)
        if not password:
            return render_template('login.html', error='Por favor ingresa tu contraseña')
        
        usuario = auth.login_user(username_or_email, password)
        if usuario:
            # Si el usuario tiene registro incompleto, redirigir a completar registro
            if usuario.get('incompleto'):
                session['usuario_incompleto_id'] = usuario['id']
                session['usuario_incompleto_email'] = usuario['email']
                return redirect(url_for('completar_registro'))
            
            session['user_id'] = usuario['id']
            session['username'] = usuario['username']
            session['es_admin'] = usuario['es_admin']
            return redirect(next_url)
        else:
            return render_template('login.html', error='Usuario o contraseña incorrectos')
    
    return render_template('login.html')


@app.route("/logout")
def logout():
    """Ruta de logout"""
    session.clear()
    return redirect(url_for('login', mensaje='Sesión cerrada correctamente'))


@app.route("/completar-registro", methods=["GET", "POST"])
def completar_registro():
    """Ruta para completar el registro de usuarios creados solo con email"""
    # Verificar que hay un usuario incompleto en sesión
    if 'usuario_incompleto_id' not in session:
        return redirect(url_for('login', error='No hay registro pendiente'))
    
    usuario_id = session.get('usuario_incompleto_id')
    email = session.get('usuario_incompleto_email')
    
    if request.method == "POST":
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        password_confirm = request.form.get('password_confirm', '').strip()
        nombre_completo = request.form.get('nombre_completo', '').strip() or None
        
        # Validaciones
        if not username:
            return render_template('completar_registro.html', 
                                 email=email,
                                 error='El nombre de usuario es requerido')
        
        if not password:
            return render_template('completar_registro.html', 
                                 email=email,
                                 error='La contraseña es requerida')
        
        if password != password_confirm:
            return render_template('completar_registro.html', 
                                 email=email,
                                 error='Las contraseñas no coinciden')
        
        if len(password) < 6:
            return render_template('completar_registro.html', 
                                 email=email,
                                 error='La contraseña debe tener al menos 6 caracteres')
        
        # Verificar que el username no esté en uso
        if not auth.verificar_username_disponible(username):
            return render_template('completar_registro.html', 
                                 email=email,
                                 error='El nombre de usuario ya está en uso. Por favor, elige otro.')
        
        # Completar el registro
        if auth.completar_registro(usuario_id, username, password, nombre_completo):
            # Limpiar sesión temporal
            session.pop('usuario_incompleto_id', None)
            session.pop('usuario_incompleto_email', None)
            
            # Iniciar sesión automáticamente
            usuario = auth.login_user(username, password)
            if usuario:
                session['user_id'] = usuario['id']
                session['username'] = usuario['username']
                session['es_admin'] = usuario['es_admin']
                return redirect(url_for('menu', mensaje='Registro completado correctamente. Bienvenido!'))
        
        return render_template('completar_registro.html', 
                             email=email,
                             error='Error al completar el registro. Por favor, intenta nuevamente.')
    
    return render_template('completar_registro.html', email=email)


@app.route("/")
@auth.login_required
def menu():
    usuario = auth.get_current_user()
    error = request.args.get('error')
    return render_template('menu.html', usuario=usuario, error=error)

# ============================================
# RUTAS DE GESTIÓN DE USUARIOS (Solo Admin)
# ============================================

@app.route("/usuarios", methods=["GET"])
@auth.admin_required
def usuarios_index():
    """Lista de usuarios"""
    usuarios = auth.obtener_usuarios()
    error = request.args.get('error')
    mensaje = request.args.get('mensaje')
    return render_template('usuarios/index.html', 
                         usuarios=usuarios, 
                         error=error, 
                         mensaje=mensaje)


@app.route("/usuarios/nuevo", methods=["GET", "POST"])
@auth.admin_required
def usuarios_nuevo():
    """Crear nuevo usuario (solo con email, el usuario completará el registro después)"""
    if request.method == "POST":
        email = request.form.get('email', '').strip()
        es_admin = request.form.get('es_admin') == '1'
        activo = request.form.get('activo') == '1'
        
        if not email:
            return render_template('usuarios/form.html', 
                                 usuario=None,
                                 error='El email es requerido')
        
        try:
            conn, cur = precios.conectar()
            try:
                # Crear usuario solo con email, sin username ni password
                cur.execute("""
                    INSERT INTO usuarios (email, es_admin, activo, registro_completo)
                    VALUES (%s, %s, %s, FALSE)
                    RETURNING id
                """, (email, es_admin, activo))
                
                usuario_id = cur.fetchone()['id']
                conn.commit()
                return redirect(url_for('usuarios_index', mensaje=f'Usuario con email {email} creado. El usuario deberá completar su registro al iniciar sesión.'))
            except psycopg2.IntegrityError as e:
                if 'usuarios_email_key' in str(e) or 'unique' in str(e).lower():
                    return render_template('usuarios/form.html', 
                                         usuario=None,
                                         error='El email ya está registrado')
                raise
            finally:
                cur.close()
                conn.close()
        except Exception as e:
            return render_template('usuarios/form.html', 
                                 usuario=None,
                                 error=f'Error al crear usuario: {str(e)}')
    
    return render_template('usuarios/form.html', usuario=None)


@app.route("/usuarios/<int:id>/editar", methods=["GET", "POST"])
@auth.admin_required
def usuarios_editar(id):
    """Editar usuario"""
    try:
        conn, cur = precios.conectar()
        try:
            if request.method == "POST":
                nombre_completo = request.form.get('nombre_completo', '').strip() or None
                email = request.form.get('email', '').strip() or None
                password = request.form.get('password', '').strip()
                es_admin = request.form.get('es_admin') == '1'
                activo = request.form.get('activo') == '1'
                
                if password:
                    password_hash = auth.hash_password(password)
                    cur.execute("""
                        UPDATE usuarios 
                        SET nombre_completo = %s, email = %s, password_hash = %s, 
                            es_admin = %s, activo = %s
                        WHERE id = %s
                    """, (nombre_completo, email, password_hash, es_admin, activo, id))
                else:
                    cur.execute("""
                        UPDATE usuarios 
                        SET nombre_completo = %s, email = %s, es_admin = %s, activo = %s
                        WHERE id = %s
                    """, (nombre_completo, email, es_admin, activo, id))
                
                conn.commit()
                return redirect(url_for('usuarios_index', mensaje='Usuario actualizado correctamente'))
            
            # GET: mostrar formulario
            cur.execute("""
                SELECT id, username, nombre_completo, email, es_admin, activo
                FROM usuarios
                WHERE id = %s
            """, (id,))
            usuario = cur.fetchone()
            
            if not usuario:
                return redirect(url_for('usuarios_index', error='Usuario no encontrado'))
            
            return render_template('usuarios/form.html', usuario=dict(usuario))
        finally:
            cur.close()
            conn.close()
    except Exception as e:
        return redirect(url_for('usuarios_index', error=f'Error: {str(e)}'))


@app.route("/usuarios/<int:id>/permisos", methods=["GET", "POST"])
@auth.admin_required
def usuarios_permisos(id):
    """Gestionar permisos de usuario"""
    try:
        conn, cur = precios.conectar()
        try:
            # Obtener usuario
            cur.execute("""
                SELECT id, username, es_admin
                FROM usuarios
                WHERE id = %s
            """, (id,))
            usuario = cur.fetchone()
            
            if not usuario:
                return redirect(url_for('usuarios_index', error='Usuario no encontrado'))
            
            usuario_dict = dict(usuario)
            
            if request.method == "POST":
                # Obtener permisos seleccionados
                permisos_seleccionados = request.form.getlist('permisos')
                permisos_seleccionados = [int(p) for p in permisos_seleccionados]
                
                # Obtener permisos actuales
                permisos_actuales = auth.obtener_permisos_usuario(id)
                permisos_actuales_ids = [p['id'] for p in permisos_actuales]
                
                # Agregar nuevos permisos
                for permiso_id in permisos_seleccionados:
                    if permiso_id not in permisos_actuales_ids:
                        auth.asignar_permiso(id, permiso_id)
                
                # Revocar permisos no seleccionados
                for permiso_id in permisos_actuales_ids:
                    if permiso_id not in permisos_seleccionados:
                        auth.revocar_permiso(id, permiso_id)
                
                return redirect(url_for('usuarios_index', mensaje='Permisos actualizados correctamente'))
            
            # GET: mostrar formulario
            permisos_disponibles = auth.obtener_permisos_rutas()
            permisos_usuario = auth.obtener_permisos_usuario(id)
            permisos_usuario_ids = [p['id'] for p in permisos_usuario]
            
            return render_template('usuarios/permisos.html',
                                 usuario=usuario_dict,
                                 permisos_disponibles=permisos_disponibles,
                                 permisos_usuario_ids=permisos_usuario_ids)
        finally:
            cur.close()
            conn.close()
    except Exception as e:
        return redirect(url_for('usuarios_index', error=f'Error: {str(e)}'))

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
@auth.login_required
@auth.permission_required('/precios')
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


@app.route("/precios/cargar-proveedores", methods=["GET", "POST"])
@auth.login_required
@auth.permission_required('/precios/cargar-proveedores')
def precios_cargar_proveedores():
    """Cargar proveedores únicos desde la tabla precios a la tabla proveedores"""
    if request.method == "POST":
        # Procesar carga de proveedores
        try:
            conn, cur = precios.conectar()
            
            # Obtener proveedores seleccionados del formulario
            proveedores_seleccionados = request.form.getlist('proveedores')
            
            if not proveedores_seleccionados:
                return redirect(url_for('precios_cargar_proveedores', 
                                      mensaje='No se seleccionaron proveedores para cargar'))
            
            proveedores_cargados = 0
            proveedores_duplicados = 0
            errores = []
            
            for nombre_proveedor in proveedores_seleccionados:
                if not nombre_proveedor or not nombre_proveedor.strip():
                    continue
                
                nombre_upper = _to_upper(nombre_proveedor.strip())
                
                try:
                    # Verificar si ya existe en la tabla proveedores
                    cur.execute("""
                        SELECT id FROM proveedores 
                        WHERE LOWER(nombre) = LOWER(%s)
                    """, (nombre_upper,))
                    
                    if cur.fetchone():
                        proveedores_duplicados += 1
                        continue
                    
                    # Insertar en la tabla proveedores
                    cur.execute("""
                        INSERT INTO proveedores (nombre, activo, creado_en, actualizado_en)
                        VALUES (%s, TRUE, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """, (nombre_upper,))
                    
                    proveedores_cargados += 1
                    
                except Exception as e:
                    errores.append(f"{nombre_upper}: {str(e)}")
            
            conn.commit()
            cur.close()
            conn.close()
            
            mensaje = f"Se cargaron {proveedores_cargados} proveedores correctamente."
            if proveedores_duplicados > 0:
                mensaje += f" {proveedores_duplicados} ya existían y se omitieron."
            if errores:
                mensaje += f" Errores: {len(errores)}"
            
            return redirect(url_for('precios_cargar_proveedores', mensaje=mensaje))
            
        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            print(f"Error al cargar proveedores: {e}")
            print(error_trace)
            return redirect(url_for('precios_cargar_proveedores', 
                                  error=f"Error al cargar proveedores: {str(e)}"))
    
    # GET: mostrar lista de proveedores únicos
    try:
        conn, cur = precios.conectar()
        
        # Obtener todos los proveedores únicos de la tabla precios
        cur.execute("""
            SELECT DISTINCT proveedor as nombre
            FROM precios
            WHERE proveedor IS NOT NULL 
              AND proveedor != ''
              AND TRIM(proveedor) != ''
            ORDER BY proveedor ASC
        """)
        proveedores_precios = [row['nombre'] for row in cur.fetchall()]
        
        # Obtener proveedores que ya están en la tabla proveedores
        proveedores_existentes = []
        try:
            cur.execute("""
                SELECT LOWER(nombre) as nombre_lower, nombre
                FROM proveedores
                ORDER BY nombre ASC
            """)
            proveedores_existentes = {row['nombre_lower']: row['nombre'] for row in cur.fetchall()}
        except:
            # Si la tabla proveedores no existe, continuar sin error
            pass
        
        cur.close()
        conn.close()
        
        # Filtrar proveedores que ya existen (comparación case-insensitive)
        proveedores_nuevos = []
        proveedores_ya_existen = []
        
        for prov in proveedores_precios:
            prov_lower = prov.lower().strip()
            if prov_lower in proveedores_existentes:
                proveedores_ya_existen.append(prov)
            else:
                proveedores_nuevos.append(prov)
        
        mensaje = request.args.get('mensaje')
        error = request.args.get('error')
        
        return render_template('precios/cargar_proveedores.html',
                             proveedores_nuevos=proveedores_nuevos,
                             proveedores_ya_existen=proveedores_ya_existen,
                             total_nuevos=len(proveedores_nuevos),
                             total_existentes=len(proveedores_ya_existen),
                             mensaje=mensaje,
                             error=error)
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Error al obtener proveedores: {e}")
        print(error_trace)
        return render_template('precios/cargar_proveedores.html',
                             proveedores_nuevos=[],
                             proveedores_ya_existen=[],
                             total_nuevos=0,
                             total_existentes=0,
                             error=f"Error al obtener proveedores: {str(e)}")


@app.route("/precios/cargar-manual", methods=["GET", "POST"])
@auth.login_required
@auth.permission_required('/precios/cargar-manual')
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
@auth.login_required
@auth.permission_required('/leer-facturas')
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
    
    return render_template('leer_facturas.html', 
                         salida=salida, 
                         running=running, 
                         finished=finished)

@app.route("/leer-facturas/status", methods=["GET"])
def leer_facturas_status():
    with _job_lock:
        return jsonify({
            "running": _job_state["running"],
            "finished": _job_state["finished"],
            "output": _job_state["output"],
        })


@app.route("/calculadora", methods=["GET"])
@auth.login_required
@auth.permission_required('/calculadora')
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
@auth.login_required
@auth.permission_required('/historial')
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
@auth.login_required
@auth.permission_required('/listas-materiales')
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
            iva_porcentaje = float(iva_porcentaje) if iva_porcentaje else 10.0
        except ValueError:
            iva_porcentaje = 10.0
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
@auth.login_required
@auth.permission_required('/listas-materiales/items_mano_de_obra')
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
@auth.login_required
@auth.permission_required('/listas-materiales/clientes')
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

# ==================== RUTAS DE MARCAS DE MATERIALES ====================

@app.route("/listas-materiales/marcas_materiales", methods=["GET"])
@auth.login_required
@auth.permission_required('/listas-materiales/marcas')
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
@auth.login_required
@auth.permission_required('/listas-materiales/materiales_genericos')
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
MAX_PROVEEDORES = 3

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
    proveedor_nombre = _to_upper(request.form.get("proveedor_nombre")) if request.form.get("proveedor_nombre") else None
    proveedor_id_form = request.form.get("proveedor_id") or None
    precio_valor = request.form.get("precio")
    moneda = request.form.get("moneda") or "PYG"
    modelo = _to_upper(request.form.get("modelo")) if request.form.get("modelo") else None
    notas = request.form.get("notas") or ""  # No convertir a mayúsculas todavía, para preservar el formato
    # Si las notas ya tienen MODELO y PRODUCTO (vienen del frontend), usarlas tal cual
    # Si no, construir las notas desde el modelo
    if notas and ("MODELO:" in notas or "PRODUCTO:" in notas):
        # Las notas ya vienen formateadas desde el frontend, solo convertir a mayúsculas
        notas = _to_upper(notas)
    elif modelo:
        # Si no hay notas formateadas pero hay modelo, crear las notas solo con el modelo
        notas = f"MODELO: {_to_upper(modelo)}"
    else:
        notas = _to_upper(notas) if notas else None
    es_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    if not lista_id:
        if es_ajax:
            return jsonify({'success': False, 'error': 'Lista ID es requerido'}), 400
        return "Lista ID es requerido", 400
    try:
        lista_id = int(lista_id)
    except ValueError:
        if es_ajax:
            return jsonify({'success': False, 'error': 'Lista ID inválido'}), 400
        return "Lista ID inválido", 400
    
    # Buscar proveedor por nombre o usar ID si está disponible
    proveedor_id = None
    if proveedor_id_form:
        try:
            proveedor_id = int(proveedor_id_form)
        except ValueError:
            pass
    
    # Si no hay ID, buscar por nombre
    if not proveedor_id and proveedor_nombre:
        proveedores = presupuestos.obtener_proveedores(activo=True)
        for prov in proveedores:
            if prov['nombre'].upper().strip() == proveedor_nombre.strip():
                proveedor_id = prov['id']
                break
        
        # Si no se encontró, crear el proveedor automáticamente
        if not proveedor_id:
            try:
                proveedor_id = presupuestos.crear_proveedor(
                    nombre=proveedor_nombre.strip(),
                    activo=True
                )
            except Exception as e:
                # Si hay un error al crear (por ejemplo, duplicado), intentar buscar de nuevo
                proveedores = presupuestos.obtener_proveedores(activo=True)
                for prov in proveedores:
                    if prov['nombre'].upper().strip() == proveedor_nombre.strip():
                        proveedor_id = prov['id']
                        break
                if not proveedor_id:
                    error_msg = f"Error al crear o encontrar proveedor: {str(e)}"
                    if es_ajax:
                        return jsonify({'success': False, 'error': error_msg}), 400
                    return error_msg, 400
    
    if not proveedor_id:
        error_msg = "Proveedor es requerido. Ingrese un nombre de proveedor válido."
        if es_ajax:
            return jsonify({'success': False, 'error': error_msg}), 400
        return error_msg, 400
    
    try:
        precio_float = float(precio_valor)
    except (TypeError, ValueError):
        if es_ajax:
            return jsonify({'success': False, 'error': 'Precio inválido'}), 400
        return "Precio inválido", 400
    
    try:
        if precio_id:
            precio_id_int = int(precio_id)
            resultado = presupuestos.actualizar_precio_item(
                precio_id=precio_id_int,
                proveedor_id=proveedor_id,
                precio=precio_float,
                moneda=moneda,
                notas=notas
            )
            if not resultado:
                raise ValueError("No se pudo actualizar el precio")
        else:
            precio_id_int = presupuestos.agregar_precio_item(
                lista_material_item_id=item_id,
                proveedor_id=proveedor_id,
                precio=precio_float,
                moneda=moneda,
                notas=notas,
                seleccionado=False
            )
            if not precio_id_int:
                raise ValueError("No se pudo crear el precio")
    except ValueError as e:
        if es_ajax:
            return jsonify({'success': False, 'error': str(e)}), 400
        return str(e), 400
    except Exception as e:
        # Capturar cualquier otro error (base de datos, etc.)
        import traceback
        error_trace = traceback.format_exc()
        print(f"ERROR al guardar precio: {str(e)}")
        print(error_trace)
        error_msg = f"Error al guardar el precio: {str(e)}"
        if es_ajax:
            return jsonify({'success': False, 'error': error_msg}), 500
        return error_msg, 500
    
    try:
        presupuestos.seleccionar_precio_item(precio_id_int)
        precio_final = presupuestos.obtener_precio_por_id(precio_id_int)
    except Exception as e:
        # Si falla la selección, continuar de todas formas
        precio_final = None
    
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
    es_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    try:
        presupuestos.seleccionar_precio_por_criterio(item_id, criterio)
        
        # Obtener el precio final seleccionado
        precios = presupuestos.obtener_precios_por_item(item_id)
        precio_seleccionado = None
        for precio in precios:
            if precio.get('seleccionado'):
                precio_seleccionado = precio
                break
        
        if es_ajax:
            if precio_seleccionado:
                return jsonify({
                    'success': True,
                    'precio_final': {
                        'proveedor_nombre': precio_seleccionado.get('proveedor_nombre'),
                        'moneda': precio_seleccionado.get('moneda') or 'PYG',
                        'precio': float(precio_seleccionado.get('precio') or 0)
                    }
                })
            else:
                return jsonify({'success': True, 'precio_final': None})
        
        return redirect(url_for('listas_materiales_precios', id=lista_id))
    except Exception as e:
        if es_ajax:
            return jsonify({'success': False, 'error': str(e)}), 500
        return redirect(url_for('listas_materiales_precios', id=lista_id) + f'?error={str(e)}')


@app.route("/api/listas-materiales/buscar-precio", methods=["POST"])
def api_buscar_precio():
    """API para buscar precio por producto y devolver proveedor y costo"""
    try:
        data = request.get_json()
        producto = data.get('producto', '').strip()
        
        if not producto:
            return jsonify({'success': False, 'error': 'Producto es requerido'}), 400
        
        # Buscar en la tabla de precios
        conn, cur = precios.conectar()
        try:
            resultados = precios.buscar_precios_db(
                cur, 
                producto=producto, 
                limite=10, 
                filtro="actual"
            )
            
            if not resultados:
                return jsonify({
                    'success': False, 
                    'message': 'No se encontraron precios para este producto'
                }), 404
            
            # Obtener lista de proveedores para mapear nombres a IDs
            proveedores = presupuestos.obtener_proveedores(activo=True)
            proveedores_map = {p['nombre'].upper(): p['id'] for p in proveedores}
            
            # Procesar todos los resultados
            precios_lista = []
            for resultado in resultados:
                proveedor_nombre = resultado.get('proveedor', '').strip().upper()
                proveedor_id = None
                if proveedor_nombre in proveedores_map:
                    proveedor_id = proveedores_map[proveedor_nombre]
                
                precios_lista.append({
                    'proveedor_id': proveedor_id,
                    'proveedor_nombre': resultado.get('proveedor', ''),
                    'precio': float(resultado.get('precio', 0)),
                    'producto': resultado.get('producto', ''),
                    'fecha': resultado.get('fecha', '').strftime('%Y-%m-%d') if resultado.get('fecha') else ''
                })
            
            return jsonify({
                'success': True,
                'precios': precios_lista
            })
        finally:
            cur.close()
            conn.close()
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

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
@auth.login_required
@auth.permission_required('/listas-materiales/prefijos_codigos')
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

# ============================================
# RUTAS DE FACTURACIÓN
# ============================================

@app.route("/facturacion", methods=["GET"])
@auth.login_required
@auth.permission_required('/facturacion')
def facturacion_index():
    """Página principal de facturación - formulario para crear factura"""
    error = request.args.get('error')
    # Obtener lista de clientes para autocompletado
    clientes = presupuestos.obtener_clientes()
    return render_template('facturacion/form.html', error=error, clientes=clientes)


@app.route("/api/facturacion/buscar-cliente", methods=["GET"])
@auth.login_required
@auth.permission_required('/facturacion')
def api_buscar_cliente():
    """API para buscar cliente por nombre y retornar sus datos"""
    nombre = request.args.get('nombre', '').strip()
    if not nombre:
        return jsonify({'error': 'Nombre requerido'}), 400
    
    try:
        conn, cur = presupuestos.conectar()
        try:
            cur.execute("""
                SELECT id, nombre, ruc, direccion, telefono, email, razon_social
                FROM clientes
                WHERE UPPER(nombre) = UPPER(%s) OR UPPER(COALESCE(razon_social, '')) = UPPER(%s)
                LIMIT 1
            """, (nombre, nombre))
            
            cliente = cur.fetchone()
            if cliente:
                return jsonify({
                    'id': cliente['id'],
                    'nombre': cliente['nombre'],
                    'ruc': cliente['ruc'] or '',
                    'direccion': cliente['direccion'] or '',
                    'telefono': cliente['telefono'] or '',
                    'email': cliente['email'] or ''
                })
            else:
                return jsonify({'error': 'Cliente no encontrado'}), 404
        finally:
            cur.close()
            conn.close()
    except Exception as e:
        import traceback
        print(f"Error al buscar cliente: {e}")
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


@app.route("/api/facturacion/crear-cliente", methods=["POST"])
@auth.login_required
@auth.permission_required('/facturacion')
def api_crear_cliente():
    """API para crear un nuevo cliente desde el formulario de facturación"""
    try:
        data = request.get_json()
        nombre = _to_upper(data.get('nombre', '').strip())
        
        if not nombre:
            return jsonify({'error': 'Nombre es requerido'}), 400
        
        def _campo(valor):
            if not valor or not valor.strip():
                return None
            return _to_upper(valor.strip())
        
        razon_social = _campo(data.get('razon_social'))
        ruc = _campo(data.get('ruc'))
        direccion = _campo(data.get('direccion'))
        telefono = _campo(data.get('telefono'))
        email = data.get('email', '').strip() or None
        notas = _campo(data.get('notas'))
        
        cliente_id = presupuestos.crear_cliente(
            nombre=nombre,
            razon_social=razon_social,
            ruc=ruc,
            direccion=direccion,
            telefono=telefono,
            email=email,
            notas=notas
        )
        
        # Obtener el cliente creado
        cliente = presupuestos.obtener_cliente_por_id(cliente_id)
        
        return jsonify({
            'success': True,
            'cliente': {
                'id': cliente['id'],
                'nombre': cliente['nombre'],
                'ruc': cliente['ruc'] or '',
                'direccion': cliente['direccion'] or '',
                'telefono': cliente['telefono'] or '',
                'email': cliente['email'] or ''
            }
        })
    except Exception as e:
        import traceback
        print(f"Error al crear cliente: {e}")
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


@app.route("/facturacion/generar", methods=["POST"])
@auth.login_required
@auth.permission_required('/facturacion')
def facturacion_generar():
    """Genera una nueva factura"""
    try:
        # Obtener datos del formulario
        fecha_str = request.form.get('fecha', '').strip()
        cliente = _to_upper(request.form.get('cliente', '').strip())
        ruc = request.form.get('ruc', '').strip() or None
        direccion = request.form.get('direccion', '').strip() or None
        nota_remision = request.form.get('remision', '').strip() or None
        moneda = 'USD' if request.form.get('moneda') == '1' else 'Gs'
        tipo_venta = 'Crédito' if request.form.get('tipoVenta') == '1' else 'Contado'
        plazo_dias = None
        if tipo_venta == 'Crédito':
            plazo_dias_str = request.form.get('plazo_dias', '').strip()
            if plazo_dias_str:
                try:
                    plazo_dias = int(plazo_dias_str)
                    if plazo_dias < 1:
                        return render_template('facturacion/form.html', 
                                             error='El plazo debe ser mayor a 0 días')
                except ValueError:
                    return render_template('facturacion/form.html', 
                                         error='El plazo debe ser un número válido')
            else:
                return render_template('facturacion/form.html', 
                                     error='El plazo de crédito es obligatorio para ventas a crédito')
        
        if not fecha_str or not cliente:
            return render_template('facturacion/form.html', 
                                 error='Fecha y Cliente son requeridos')
        
        # Parsear fecha
        try:
            fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        except ValueError:
            return render_template('facturacion/form.html', 
                                 error='Fecha inválida')
        
        # Obtener items del formulario
        items = []
        item_count = 0
        while True:
            cantidad_key = f'item_cantidad_{item_count}'
            descripcion_key = f'item_descripcion_{item_count}'
            precio_key = f'item_precio_{item_count}'
            impuesto_key = f'item_impuesto_{item_count}'
            
            if cantidad_key not in request.form:
                break
            
            cantidad = request.form.get(cantidad_key, '').strip()
            descripcion = request.form.get(descripcion_key, '').strip()
            precio = request.form.get(precio_key, '').strip()
            impuesto = request.form.get(impuesto_key, 'exc')
            
            if cantidad and descripcion and precio:
                try:
                    items.append({
                        'cantidad': float(cantidad),
                        'descripcion': _to_upper(descripcion),
                        'precio_unitario': float(precio),
                        'impuesto': impuesto
                    })
                except ValueError:
                    pass  # Ignorar items con valores inválidos
            
            item_count += 1
        
        if not items:
            return render_template('facturacion/form.html', 
                                 error='Debe ingresar al menos un item válido')
        
        # Crear factura
        factura_id = facturacion.crear_factura(
            fecha=fecha,
            cliente=cliente,
            ruc=ruc,
            direccion=direccion,
            nota_remision=nota_remision,
            moneda=moneda,
            tipo_venta=tipo_venta,
            plazo_dias=plazo_dias,
            items=items
        )
        
        return redirect(url_for('facturacion_pdf', id=factura_id))
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Error al generar factura: {e}")
        print(error_trace)
        return render_template('facturacion/form.html', 
                             error=f'Error al generar factura: {str(e)}')


@app.route("/facturacion/<int:id>/pdf", methods=["GET"])
@auth.login_required
@auth.permission_required('/facturacion')
def facturacion_pdf(id):
    """Genera el PDF de una factura"""
    try:
        datos = facturacion.obtener_factura_por_id(id)
        if not datos:
            return "Factura no encontrada", 404
        
        factura = datos['factura']
        items = datos['items']
        
        # Calcular totales
        items_dict = [{
            'cantidad': item['cantidad'],
            'descripcion': item['descripcion'],
            'precio_unitario': float(item['precio_unitario']),
            'impuesto': item['impuesto']
        } for item in items]
        
        totales = facturacion.calcular_totales(items_dict)
        totales['enLetras'] = facturacion.numero_a_letras(totales['total'], True, factura['moneda'])
        
        # Formatear fecha
        fecha_obj = factura['fecha']
        if isinstance(fecha_obj, str):
            fecha_obj = datetime.strptime(fecha_obj, "%Y-%m-%d").date()
        
        dia = fecha_obj.day
        mes = fecha_obj.month
        año = fecha_obj.year
        fecha_formateada = f"{dia:02d}-{mes:02d}-{año}"
        
        factura['fecha_formateada'] = fecha_formateada
        
        # Renderizar HTML
        html = render_template('facturacion/pdf.html',
                             factura=factura,
                             items=items,
                             totales=totales)
        
        # Generar PDF - intentar WeasyPrint primero, luego xhtml2pdf como alternativa
        try:
            from weasyprint import HTML
            pdf = HTML(string=html, base_url=request.host_url).write_pdf()
            response = make_response(pdf)
            response.headers['Content-Type'] = 'application/pdf'
            response.headers['Content-Disposition'] = f'inline; filename=factura_{factura["numero_factura"]}.pdf'
            return response
        except (ImportError, OSError, Exception) as e:
            # Si WeasyPrint falla, intentar con xhtml2pdf
            try:
                from xhtml2pdf import pisa
                from io import BytesIO
                
                pdf_buffer = BytesIO()
                pisa_status = pisa.CreatePDF(html, dest=pdf_buffer)
                
                if pisa_status.err:
                    # Si xhtml2pdf falla, mostrar HTML
                    return html
                
                pdf_buffer.seek(0)
                response = make_response(pdf_buffer.getvalue())
                response.headers['Content-Type'] = 'application/pdf'
                response.headers['Content-Disposition'] = f'inline; filename=factura_{factura["numero_factura"]}.pdf'
                return response
            except ImportError:
                # Si ninguna librería está disponible, mostrar HTML
                return html
            except Exception as e2:
                # Si hay otro error, mostrar HTML con mensaje
                return html + f"<br><br><p style='color:red;'>Nota: No se pudo generar PDF automáticamente. Error: {str(e2)}</p>"
            
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Error al generar PDF de factura: {e}")
        print(error_trace)
        return f"Error: {str(e)}", 500


@app.route("/reportes/clientes", methods=["GET"], endpoint="reportes_clientes_index")
@auth.login_required
@auth.permission_required('/reportes/clientes')
def reportes_clientes_index():
    """Página de reportes de clientes"""
    cliente_nombre = request.args.get('cliente', '').strip() or None
    fecha_desde = request.args.get('fecha_desde', '').strip() or None
    fecha_hasta = request.args.get('fecha_hasta', '').strip() or None
    estado_filtro = request.args.get('estado', '').strip() or None
    
    # Obtener lista de clientes para el filtro
    clientes = reportes_clientes.obtener_clientes_con_facturas()
    
    # Obtener reportes
    reportes = reportes_clientes.obtener_reportes_cliente(
        cliente_nombre=cliente_nombre,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        estado_pago_filtro=estado_filtro
    )
    
    # Filtrar por estado si se especifica
    if estado_filtro:
        reportes = [r for r in reportes if r['estado_pago'].lower() == estado_filtro.lower()]
    
    return render_template('reportes/clientes.html',
                         reportes=reportes,
                         clientes=clientes,
                         cliente_seleccionado=cliente_nombre or '',
                         fecha_desde=fecha_desde or '',
                         fecha_hasta=fecha_hasta or '',
                         estado_seleccionado=estado_filtro or '')


@app.route("/reportes/cuentas-a-pagar", methods=["GET"], endpoint="reportes_cuentas_a_pagar_index")
@auth.login_required
@auth.permission_required('/reportes/cuentas-a-pagar')
def reportes_cuentas_a_pagar_index():
    """Página de reportes de cuentas a pagar"""
    proveedor_nombre = request.args.get('proveedor', '').strip() or None
    fecha_desde = request.args.get('fecha_desde', '').strip() or None
    fecha_hasta = request.args.get('fecha_hasta', '').strip() or None
    estado_filtro = request.args.get('estado', '').strip() or None
    tipo_filtro = request.args.get('tipo', '').strip() or None
    
    # Paginación
    pagina = request.args.get('pagina', type=int, default=1)
    limite = request.args.get('limite', type=int, default=50)
    
    # Validar límite (mínimo 10, máximo 500)
    if limite < 10:
        limite = 10
    elif limite > 500:
        limite = 500
    
    # Obtener lista de proveedores para el filtro
    proveedores = reportes_clientes.obtener_proveedores_con_cuentas()
    
    # Obtener total de registros
    total_registros = reportes_clientes.contar_reportes_cuentas_a_pagar(
        proveedor_nombre=proveedor_nombre,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        estado_pago_filtro=estado_filtro,
        tipo_filtro=tipo_filtro
    )
    
    # Calcular total de páginas
    total_paginas = (total_registros + limite - 1) // limite if total_registros > 0 else 1
    
    # Asegurar que la página esté en rango válido
    if pagina < 1:
        pagina = 1
    elif pagina > total_paginas and total_paginas > 0:
        pagina = total_paginas
    
    # Calcular offset
    offset = (pagina - 1) * limite
    
    # Obtener reportes con paginación
    reportes = reportes_clientes.obtener_reportes_cuentas_a_pagar(
        proveedor_nombre=proveedor_nombre,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        estado_pago_filtro=estado_filtro,
        tipo_filtro=tipo_filtro,
        limite=limite,
        offset=offset
    )
    
    return render_template('reportes/cuentas_a_pagar.html',
                         reportes=reportes,
                         proveedores=proveedores,
                         proveedor_seleccionado=proveedor_nombre or '',
                         fecha_desde=fecha_desde or '',
                         fecha_hasta=fecha_hasta or '',
                         estado_seleccionado=estado_filtro or '',
                         tipo_seleccionado=tipo_filtro or '',
                         pagina=pagina,
                         limite=limite,
                         total_registros=total_registros,
                         total_paginas=total_paginas)


@app.route("/reportes/analisis", methods=["GET"], endpoint="reportes_analisis_index")
@auth.login_required
@auth.permission_required('/reportes/analisis')
def reportes_analisis_index():
    """Dashboard de análisis históricos y financieros"""
    from datetime import datetime, date
    
    # Filtros
    fecha_desde = request.args.get('fecha_desde', '').strip() or None
    fecha_hasta = request.args.get('fecha_hasta', '').strip() or None
    ano = request.args.get('ano', type=int)
    proyecto_id = request.args.get('proyecto_id', type=int)
    banco_id = request.args.get('banco_id', type=int)
    tipo_reporte = request.args.get('tipo_reporte', 'realizado')  # 'realizado' o 'proyectado'
    
    # Obtener datos para filtros
    proyectos = financiero.obtener_proyectos(activo=True)
    bancos = financiero.obtener_bancos(activo=True)
    
    # Obtener datos del dashboard
    saldos_bancos = reportes_clientes.obtener_saldos_bancos()
    receita_mensual_raw = reportes_clientes.obtener_receita_bruta_mensual(
        ano=ano, proyecto_id=proyecto_id, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta,
        tipo_reporte=tipo_reporte
    )
    custos_mensual_raw = reportes_clientes.obtener_custos_despesas_mensual(
        ano=ano, proyecto_id=proyecto_id, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta,
        tipo_reporte=tipo_reporte
    )
    flujo_caja = reportes_clientes.obtener_flujo_caja_mensual(
        ano=ano, proyecto_id=proyecto_id, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta
    )
    evolucion_saldo = reportes_clientes.obtener_evolucion_saldo_mensual(
        banco_id=banco_id, ano=ano, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta
    )
    
    # Convertir datos a formato JSON-friendly (convertir Decimal a int/float)
    receita_mensual = []
    for r in receita_mensual_raw:
        receita_mensual.append({
            'mes': int(float(r['mes'])),
            'ano': int(float(r['ano'])),
            'receita_bruta': float(r['receita_bruta'] or 0)
        })
    
    custos_mensual = []
    for c in custos_mensual_raw:
        custos_mensual.append({
            'mes': int(float(c['mes'])),
            'ano': int(float(c['ano'])),
            'custos_despesas': float(c['custos_despesas'] or 0)
        })
    
    # Calcular totales
    total_receita = sum(float(r['receita_bruta'] or 0) for r in receita_mensual)
    total_custos = sum(float(c['custos_despesas'] or 0) for c in custos_mensual)
    total_lucro = total_receita - total_custos
    total_saldo_bancos = sum(float(s['saldo_actual'] or 0) for s in saldos_bancos)
    
    return render_template('reportes/analisis.html',
                         saldos_bancos=saldos_bancos,
                         receita_mensual=receita_mensual,
                         custos_mensual=custos_mensual,
                         flujo_caja=flujo_caja,
                         evolucion_saldo=evolucion_saldo,
                         total_receita=total_receita,
                         total_custos=total_custos,
                         total_lucro=total_lucro,
                         total_saldo_bancos=total_saldo_bancos,
                         proyectos=proyectos,
                         bancos=bancos,
                         fecha_desde=fecha_desde or '',
                         fecha_hasta=fecha_hasta or '',
                         ano=ano or date.today().year,
                         proyecto_id=proyecto_id,
                         banco_id=banco_id,
                         tipo_reporte=tipo_reporte)


@app.route("/reportes/cuentas-a-recibir", methods=["GET"], endpoint="reportes_cuentas_a_recibir_index")
@auth.login_required
@auth.permission_required('/reportes/cuentas-a-recibir')
def reportes_cuentas_a_recibir_index():
    """Página de reportes de cuentas a recibir"""
    cliente_nombre = request.args.get('cliente', '').strip() or None
    fecha_desde = request.args.get('fecha_desde', '').strip() or None
    fecha_hasta = request.args.get('fecha_hasta', '').strip() or None
    estado_filtro = request.args.get('estado', '').strip() or None
    tipo_filtro = request.args.get('tipo', '').strip() or None
    
    # Paginación
    pagina = request.args.get('pagina', type=int, default=1)
    limite = request.args.get('limite', type=int, default=50)
    
    # Validar límite (mínimo 10, máximo 500)
    if limite < 10:
        limite = 10
    elif limite > 500:
        limite = 500
    
    # Obtener lista de clientes para el filtro
    clientes = reportes_clientes.obtener_clientes_con_cuentas_a_recibir()
    
    # Obtener total de registros
    total_registros = reportes_clientes.contar_reportes_cuentas_a_recibir(
        cliente_nombre=cliente_nombre,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        estado_pago_filtro=estado_filtro,
        tipo_filtro=tipo_filtro
    )
    
    # Calcular total de páginas
    total_paginas = (total_registros + limite - 1) // limite if total_registros > 0 else 1
    
    # Asegurar que la página esté en rango válido
    if pagina < 1:
        pagina = 1
    elif pagina > total_paginas and total_paginas > 0:
        pagina = total_paginas
    
    # Calcular offset
    offset = (pagina - 1) * limite
    
    # Obtener reportes con paginación
    reportes = reportes_clientes.obtener_reportes_cuentas_a_recibir(
        cliente_nombre=cliente_nombre,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        estado_pago_filtro=estado_filtro,
        tipo_filtro=tipo_filtro,
        limite=limite,
        offset=offset
    )
    
    return render_template('reportes/cuentas_a_recibir.html',
                         reportes=reportes,
                         clientes=clientes,
                         cliente_seleccionado=cliente_nombre or '',
                         fecha_desde=fecha_desde or '',
                         fecha_hasta=fecha_hasta or '',
                         estado_seleccionado=estado_filtro or '',
                         tipo_seleccionado=tipo_filtro or '',
                         pagina=pagina,
                         limite=limite,
                         total_registros=total_registros,
                         total_paginas=total_paginas)


@app.route("/reportes/conciliacion-bancaria", methods=["GET"], endpoint="reportes_conciliacion_bancaria_index")
@auth.login_required
@auth.permission_required('/reportes/conciliacion-bancaria')
def reportes_conciliacion_bancaria_index():
    """Página de conciliación bancaria"""
    banco_id = request.args.get('banco_id', type=int)
    anio = request.args.get('anio', type=int, default=datetime.now().year)
    mes = request.args.get('mes', type=int, default=datetime.now().month)
    
    # Obtener lista de bancos
    bancos = financiero.obtener_bancos(activo=True)
    
    # Si no hay banco seleccionado y hay bancos disponibles, usar el primero
    if not banco_id and bancos:
        banco_id = bancos[0]['id']
    
    conciliacion = None
    error = request.args.get('error')
    
    if banco_id:
        try:
            conciliacion = reportes_clientes.obtener_conciliacion_bancaria(banco_id, anio, mes)
            if not conciliacion:
                error = 'Banco no encontrado'
        except Exception as e:
            error = f'Error al obtener conciliación: {str(e)}'
    
    return render_template('reportes/conciliacion_bancaria.html',
                         bancos=bancos,
                         banco_id=banco_id,
                         anio=anio,
                         mes=mes,
                         conciliacion=conciliacion,
                         error=error)


@app.route("/api/facturacion/eliminar-factura/<int:factura_id>", methods=["DELETE"])
@auth.login_required
@auth.permission_required('/facturacion')
def api_eliminar_factura(factura_id):
    """API para eliminar una factura"""
    try:
        resultado = facturacion.eliminar_factura(factura_id)
        if resultado:
            return jsonify({'success': True, 'message': 'Factura eliminada correctamente'}), 200
        else:
            return jsonify({'success': False, 'message': 'Factura no encontrada'}), 404
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error al eliminar factura: {str(e)}'}), 500


@app.route("/api/facturacion/actualizar-factura/<int:factura_id>", methods=["POST"])
@auth.login_required
@auth.permission_required('/facturacion')
def api_actualizar_factura(factura_id):
    """API para actualizar fecha de pago y estado de una factura"""
    try:
        data = request.get_json()
        fecha_pago = data.get('fecha_pago')
        estado_pago = data.get('estado_pago')
        
        # Convertir fecha_pago vacía a None
        if fecha_pago == '' or fecha_pago is None:
            fecha_pago = None
        else:
            # Validar formato de fecha
            try:
                fecha_pago = datetime.strptime(fecha_pago, "%Y-%m-%d").date()
            except ValueError:
                return jsonify({'error': 'Formato de fecha inválido'}), 400
        
        # Validar estado_pago
        estados_validos = ['Pagado', 'Pendiente', 'En día', 'Atrasado', 'Adelantado']
        if estado_pago and estado_pago not in estados_validos:
            return jsonify({'error': 'Estado de pago inválido'}), 400
        
        # Actualizar factura
        resultado = facturacion.actualizar_factura(
            factura_id=factura_id,
            fecha_pago=fecha_pago,
            estado_pago=estado_pago
        )
        
        if resultado:
            return jsonify({'success': True, 'message': 'Factura actualizada correctamente'})
        else:
            return jsonify({'error': 'No se pudo actualizar la factura'}), 400
            
    except Exception as e:
        import traceback
        print(f"Error al actualizar factura: {e}")
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


# ==================== RUTAS FINANCIERAS ====================

@app.route("/financiero", methods=["GET"], endpoint="financiero_index")
@auth.login_required
@auth.permission_required('/financiero')
def financiero_index():
    """Menú principal del módulo financiero"""
    return render_template('financiero/index.html')


@app.route("/financiero/tipos-ingresos", methods=["GET"], endpoint="tipos_ingresos_index")
@auth.login_required
@auth.permission_required('/financiero/tipos-ingresos')
def tipos_ingresos_index():
    """Página principal de gestión de tipos de ingresos"""
    categorias = financiero.obtener_categorias_ingresos()
    tipos = financiero.obtener_tipos_ingresos()
    
    # Organizar tipos por categoría
    tipos_por_categoria = {}
    for tipo in tipos:
        cat_id = tipo['categoria_id']
        if cat_id not in tipos_por_categoria:
            tipos_por_categoria[cat_id] = []
        tipos_por_categoria[cat_id].append(tipo)
    
    error = request.args.get('error')
    mensaje = request.args.get('mensaje')
    
    return render_template('financiero/tipos_ingresos/index.html',
                         categorias=categorias,
                         tipos_por_categoria=tipos_por_categoria,
                         error=error,
                         mensaje=mensaje)


@app.route("/financiero/tipos-ingresos/categoria/nuevo", methods=["GET", "POST"], endpoint="categoria_ingreso_nuevo")
@auth.login_required
@auth.permission_required('/financiero/tipos-ingresos')
def categoria_ingreso_nuevo():
    """Crear nueva categoría de ingreso"""
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        orden_str = request.form.get('orden', '').strip()
        
        if not nombre:
            return redirect(url_for('tipos_ingresos_index', error='El nombre es obligatorio'))
        
        try:
            orden = int(orden_str) if orden_str else None
            financiero.crear_categoria_ingreso(nombre, orden)
            return redirect(url_for('tipos_ingresos_index', mensaje='Categoría creada correctamente'))
        except Exception as e:
            return redirect(url_for('tipos_ingresos_index', error=f'Error al crear categoría: {str(e)}'))
    
    return render_template('financiero/tipos_ingresos/categoria_form.html', categoria=None)


@app.route("/financiero/tipos-ingresos/categoria/<int:id>/editar", methods=["GET", "POST"], endpoint="categoria_ingreso_editar")
@auth.login_required
@auth.permission_required('/financiero/tipos-ingresos')
def categoria_ingreso_editar(id):
    """Editar categoría de ingreso"""
    categoria = financiero.obtener_categoria_por_id(id)
    if not categoria:
        return redirect(url_for('tipos_ingresos_index', error='Categoría no encontrada'))
    
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        orden_str = request.form.get('orden', '').strip()
        activo = request.form.get('activo') == 'on'
        
        if not nombre:
            return redirect(url_for('tipos_ingresos_index', error='El nombre es obligatorio'))
        
        try:
            orden = int(orden_str) if orden_str else None
            financiero.actualizar_categoria_ingreso(id, nombre, orden, activo)
            return redirect(url_for('tipos_ingresos_index', mensaje='Categoría actualizada correctamente'))
        except Exception as e:
            return redirect(url_for('tipos_ingresos_index', error=f'Error al actualizar categoría: {str(e)}'))
    
    return render_template('financiero/tipos_ingresos/categoria_form.html', categoria=dict(categoria))


@app.route("/financiero/tipos-ingresos/categoria/<int:id>/eliminar", methods=["POST"], endpoint="categoria_ingreso_eliminar")
@auth.login_required
@auth.permission_required('/financiero/tipos-ingresos')
def categoria_ingreso_eliminar(id):
    """Eliminar categoría de ingreso"""
    try:
        financiero.eliminar_categoria_ingreso(id)
        return redirect(url_for('tipos_ingresos_index', mensaje='Categoría eliminada correctamente'))
    except Exception as e:
        return redirect(url_for('tipos_ingresos_index', error=f'Error al eliminar categoría: {str(e)}'))


@app.route("/financiero/tipos-ingresos/tipo/nuevo", methods=["GET", "POST"], endpoint="tipo_ingreso_nuevo")
@auth.login_required
@auth.permission_required('/financiero/tipos-ingresos')
def tipo_ingreso_nuevo():
    """Crear nuevo tipo de ingreso"""
    categoria_id = request.args.get('categoria_id', type=int)
    
    if request.method == 'POST':
        categoria_id = request.form.get('categoria_id', type=int)
        descripcion = request.form.get('descripcion', '').strip()
        orden_str = request.form.get('orden', '').strip()
        
        if not categoria_id or not descripcion:
            return redirect(url_for('tipos_ingresos_index', error='Categoría y descripción son obligatorios'))
        
        try:
            orden = int(orden_str) if orden_str else None
            financiero.crear_tipo_ingreso(categoria_id, descripcion, orden)
            return redirect(url_for('tipos_ingresos_index', mensaje='Tipo de ingreso creado correctamente'))
        except Exception as e:
            return redirect(url_for('tipos_ingresos_index', error=f'Error al crear tipo de ingreso: {str(e)}'))
    
    categorias = financiero.obtener_categorias_ingresos(activo=True)
    categoria_seleccionada = None
    if categoria_id:
        categoria_seleccionada = financiero.obtener_categoria_por_id(categoria_id)
    
    return render_template('financiero/tipos_ingresos/tipo_form.html',
                         tipo=None,
                         categorias=categorias,
                         categoria_seleccionada=dict(categoria_seleccionada) if categoria_seleccionada else None)


@app.route("/financiero/tipos-ingresos/tipo/<int:id>/editar", methods=["GET", "POST"], endpoint="tipo_ingreso_editar")
@auth.login_required
@auth.permission_required('/financiero/tipos-ingresos')
def tipo_ingreso_editar(id):
    """Editar tipo de ingreso"""
    tipo = financiero.obtener_tipo_ingreso_por_id(id)
    if not tipo:
        return redirect(url_for('tipos_ingresos_index', error='Tipo de ingreso no encontrado'))
    
    if request.method == 'POST':
        descripcion = request.form.get('descripcion', '').strip()
        orden_str = request.form.get('orden', '').strip()
        activo = request.form.get('activo') == 'on'
        
        if not descripcion:
            return redirect(url_for('tipos_ingresos_index', error='La descripción es obligatoria'))
        
        try:
            orden = int(orden_str) if orden_str else None
            financiero.actualizar_tipo_ingreso(id, descripcion, orden, activo)
            return redirect(url_for('tipos_ingresos_index', mensaje='Tipo de ingreso actualizado correctamente'))
        except Exception as e:
            return redirect(url_for('tipos_ingresos_index', error=f'Error al actualizar tipo de ingreso: {str(e)}'))
    
    categorias = financiero.obtener_categorias_ingresos(activo=True)
    return render_template('financiero/tipos_ingresos/tipo_form.html',
                         tipo=dict(tipo),
                         categorias=categorias,
                         categoria_seleccionada=None)


@app.route("/financiero/tipos-ingresos/tipo/<int:id>/eliminar", methods=["POST"], endpoint="tipo_ingreso_eliminar")
@auth.login_required
@auth.permission_required('/financiero/tipos-ingresos')
def tipo_ingreso_eliminar(id):
    """Eliminar tipo de ingreso"""
    try:
        financiero.eliminar_tipo_ingreso(id)
        return redirect(url_for('tipos_ingresos_index', mensaje='Tipo de ingreso eliminado correctamente'))
    except Exception as e:
        return redirect(url_for('tipos_ingresos_index', error=f'Error al eliminar tipo de ingreso: {str(e)}'))


# ==================== RUTAS PARA TIPOS DE GASTOS ====================

@app.route("/financiero/tipos-gastos", methods=["GET"], endpoint="tipos_gastos_index")
@auth.login_required
@auth.permission_required('/financiero/tipos-gastos')
def tipos_gastos_index():
    """Página principal de gestión de tipos de gastos"""
    categorias = financiero.obtener_categorias_gastos()
    tipos = financiero.obtener_tipos_gastos()
    
    # Organizar tipos por categoría
    tipos_por_categoria = {}
    for tipo in tipos:
        cat_id = tipo['categoria_id']
        if cat_id not in tipos_por_categoria:
            tipos_por_categoria[cat_id] = []
        tipos_por_categoria[cat_id].append(tipo)
    
    error = request.args.get('error')
    mensaje = request.args.get('mensaje')
    
    return render_template('financiero/tipos_gastos/index.html',
                         categorias=categorias,
                         tipos_por_categoria=tipos_por_categoria,
                         error=error,
                         mensaje=mensaje)


@app.route("/financiero/tipos-gastos/categoria/nuevo", methods=["GET", "POST"], endpoint="categoria_gasto_nuevo")
@auth.login_required
@auth.permission_required('/financiero/tipos-gastos')
def categoria_gasto_nuevo():
    """Crear nueva categoría de gasto"""
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        orden_str = request.form.get('orden', '').strip()
        
        if not nombre:
            return redirect(url_for('tipos_gastos_index', error='El nombre es obligatorio'))
        
        try:
            orden = int(orden_str) if orden_str else None
            financiero.crear_categoria_gasto(nombre, orden)
            return redirect(url_for('tipos_gastos_index', mensaje='Categoría creada correctamente'))
        except Exception as e:
            return redirect(url_for('tipos_gastos_index', error=f'Error al crear categoría: {str(e)}'))
    
    return render_template('financiero/tipos_gastos/categoria_form.html', categoria=None)


@app.route("/financiero/tipos-gastos/categoria/<int:id>/editar", methods=["GET", "POST"], endpoint="categoria_gasto_editar")
@auth.login_required
@auth.permission_required('/financiero/tipos-gastos')
def categoria_gasto_editar(id):
    """Editar categoría de gasto"""
    categoria = financiero.obtener_categoria_gasto_por_id(id)
    if not categoria:
        return redirect(url_for('tipos_gastos_index', error='Categoría no encontrada'))
    
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        orden_str = request.form.get('orden', '').strip()
        activo = request.form.get('activo') == 'on'
        
        if not nombre:
            return redirect(url_for('tipos_gastos_index', error='El nombre es obligatorio'))
        
        try:
            orden = int(orden_str) if orden_str else None
            financiero.actualizar_categoria_gasto(id, nombre, orden, activo)
            return redirect(url_for('tipos_gastos_index', mensaje='Categoría actualizada correctamente'))
        except Exception as e:
            return redirect(url_for('tipos_gastos_index', error=f'Error al actualizar categoría: {str(e)}'))
    
    return render_template('financiero/tipos_gastos/categoria_form.html', categoria=dict(categoria))


@app.route("/financiero/tipos-gastos/categoria/<int:id>/eliminar", methods=["POST"], endpoint="categoria_gasto_eliminar")
@auth.login_required
@auth.permission_required('/financiero/tipos-gastos')
def categoria_gasto_eliminar(id):
    """Eliminar categoría de gasto"""
    try:
        financiero.eliminar_categoria_gasto(id)
        return redirect(url_for('tipos_gastos_index', mensaje='Categoría eliminada correctamente'))
    except Exception as e:
        return redirect(url_for('tipos_gastos_index', error=f'Error al eliminar categoría: {str(e)}'))


@app.route("/financiero/tipos-gastos/tipo/nuevo", methods=["GET", "POST"], endpoint="tipo_gasto_nuevo")
@auth.login_required
@auth.permission_required('/financiero/tipos-gastos')
def tipo_gasto_nuevo():
    """Crear nuevo tipo de gasto"""
    categoria_id = request.args.get('categoria_id', type=int)
    
    if request.method == 'POST':
        categoria_id = request.form.get('categoria_id', type=int)
        descripcion = request.form.get('descripcion', '').strip()
        orden_str = request.form.get('orden', '').strip()
        
        if not categoria_id or not descripcion:
            return redirect(url_for('tipos_gastos_index', error='Categoría y descripción son obligatorios'))
        
        try:
            orden = int(orden_str) if orden_str else None
            financiero.crear_tipo_gasto(categoria_id, descripcion, orden)
            return redirect(url_for('tipos_gastos_index', mensaje='Tipo de gasto creado correctamente'))
        except Exception as e:
            return redirect(url_for('tipos_gastos_index', error=f'Error al crear tipo de gasto: {str(e)}'))
    
    categorias = financiero.obtener_categorias_gastos(activo=True)
    categoria_seleccionada = None
    if categoria_id:
        categoria_seleccionada = financiero.obtener_categoria_gasto_por_id(categoria_id)
    
    return render_template('financiero/tipos_gastos/tipo_form.html',
                         tipo=None,
                         categorias=categorias,
                         categoria_seleccionada=dict(categoria_seleccionada) if categoria_seleccionada else None)


@app.route("/financiero/tipos-gastos/tipo/<int:id>/editar", methods=["GET", "POST"], endpoint="tipo_gasto_editar")
@auth.login_required
@auth.permission_required('/financiero/tipos-gastos')
def tipo_gasto_editar(id):
    """Editar tipo de gasto"""
    tipo = financiero.obtener_tipo_gasto_por_id(id)
    if not tipo:
        return redirect(url_for('tipos_gastos_index', error='Tipo de gasto no encontrado'))
    
    if request.method == 'POST':
        descripcion = request.form.get('descripcion', '').strip()
        orden_str = request.form.get('orden', '').strip()
        activo = request.form.get('activo') == 'on'
        
        if not descripcion:
            return redirect(url_for('tipos_gastos_index', error='La descripción es obligatoria'))
        
        try:
            orden = int(orden_str) if orden_str else None
            financiero.actualizar_tipo_gasto(id, descripcion, orden, activo)
            return redirect(url_for('tipos_gastos_index', mensaje='Tipo de gasto actualizado correctamente'))
        except Exception as e:
            return redirect(url_for('tipos_gastos_index', error=f'Error al actualizar tipo de gasto: {str(e)}'))
    
    categorias = financiero.obtener_categorias_gastos(activo=True)
    return render_template('financiero/tipos_gastos/tipo_form.html',
                         tipo=dict(tipo),
                         categorias=categorias,
                         categoria_seleccionada=None)


@app.route("/financiero/tipos-gastos/tipo/<int:id>/eliminar", methods=["POST"], endpoint="tipo_gasto_eliminar")
@auth.login_required
@auth.permission_required('/financiero/tipos-gastos')
def tipo_gasto_eliminar(id):
    """Eliminar tipo de gasto"""
    try:
        financiero.eliminar_tipo_gasto(id)
        return redirect(url_for('tipos_gastos_index', mensaje='Tipo de gasto eliminado correctamente'))
    except Exception as e:
        return redirect(url_for('tipos_gastos_index', error=f'Error al eliminar tipo de gasto: {str(e)}'))


# ==================== RUTAS PARA PROYECTOS ====================

@app.route("/financiero/proyectos", methods=["GET"], endpoint="proyectos_index")
@auth.login_required
@auth.permission_required('/financiero/proyectos')
def proyectos_index():
    """Página principal de gestión de proyectos"""
    proyectos = financiero.obtener_proyectos()
    error = request.args.get('error')
    mensaje = request.args.get('mensaje')
    
    return render_template('financiero/proyectos/index.html',
                         proyectos=proyectos,
                         error=error,
                         mensaje=mensaje)


@app.route("/financiero/proyectos/nuevo", methods=["GET", "POST"], endpoint="proyecto_nuevo")
@auth.login_required
@auth.permission_required('/financiero/proyectos')
def proyecto_nuevo():
    """Crear nuevo proyecto"""
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        
        if not nombre:
            return redirect(url_for('proyectos_index', error='El nombre es obligatorio'))
        
        try:
            financiero.crear_proyecto(nombre)
            return redirect(url_for('proyectos_index', mensaje='Proyecto creado correctamente'))
        except Exception as e:
            return redirect(url_for('proyectos_index', error=f'Error al crear proyecto: {str(e)}'))
    
    return render_template('financiero/proyectos/form.html', proyecto=None)


@app.route("/financiero/proyectos/<int:id>/editar", methods=["GET", "POST"], endpoint="proyecto_editar")
@auth.login_required
@auth.permission_required('/financiero/proyectos')
def proyecto_editar(id):
    """Editar proyecto"""
    proyecto = financiero.obtener_proyecto_por_id(id)
    if not proyecto:
        return redirect(url_for('proyectos_index', error='Proyecto no encontrado'))
    
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        activo = request.form.get('activo') == 'on'
        
        if not nombre:
            return redirect(url_for('proyectos_index', error='El nombre es obligatorio'))
        
        try:
            financiero.actualizar_proyecto(id, nombre, activo)
            return redirect(url_for('proyectos_index', mensaje='Proyecto actualizado correctamente'))
        except Exception as e:
            return redirect(url_for('proyectos_index', error=f'Error al actualizar proyecto: {str(e)}'))
    
    return render_template('financiero/proyectos/form.html', proyecto=dict(proyecto))


@app.route("/financiero/proyectos/<int:id>/eliminar", methods=["POST"], endpoint="proyecto_eliminar")
@auth.login_required
@auth.permission_required('/financiero/proyectos')
def proyecto_eliminar(id):
    """Eliminar proyecto"""
    try:
        financiero.eliminar_proyecto(id)
        return redirect(url_for('proyectos_index', mensaje='Proyecto eliminado correctamente'))
    except Exception as e:
        return redirect(url_for('proyectos_index', error=f'Error al eliminar proyecto: {str(e)}'))


# ==================== RUTAS PARA TIPOS DE DOCUMENTOS ====================

@app.route("/financiero/tipos-documentos", methods=["GET"], endpoint="tipos_documentos_index")
@auth.login_required
@auth.permission_required('/financiero/tipos-documentos')
def tipos_documentos_index():
    """Página principal de gestión de tipos de documentos"""
    tipos = financiero.obtener_tipos_documentos()
    error = request.args.get('error')
    mensaje = request.args.get('mensaje')
    
    return render_template('financiero/tipos_documentos/index.html',
                         tipos=tipos,
                         error=error,
                         mensaje=mensaje)


@app.route("/financiero/tipos-documentos/nuevo", methods=["GET", "POST"], endpoint="tipo_documento_nuevo")
@auth.login_required
@auth.permission_required('/financiero/tipos-documentos')
def tipo_documento_nuevo():
    """Crear nuevo tipo de documento"""
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        
        if not nombre:
            return redirect(url_for('tipos_documentos_index', error='El nombre es obligatorio'))
        
        try:
            financiero.crear_tipo_documento(nombre)
            return redirect(url_for('tipos_documentos_index', mensaje='Tipo de documento creado correctamente'))
        except Exception as e:
            return redirect(url_for('tipos_documentos_index', error=f'Error al crear tipo de documento: {str(e)}'))
    
    return render_template('financiero/tipos_documentos/form.html', tipo=None)


@app.route("/financiero/tipos-documentos/<int:id>/editar", methods=["GET", "POST"], endpoint="tipo_documento_editar")
@auth.login_required
@auth.permission_required('/financiero/tipos-documentos')
def tipo_documento_editar(id):
    """Editar tipo de documento"""
    tipo = financiero.obtener_tipo_documento_por_id(id)
    if not tipo:
        return redirect(url_for('tipos_documentos_index', error='Tipo de documento no encontrado'))
    
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        activo = request.form.get('activo') == 'on'
        
        if not nombre:
            return redirect(url_for('tipos_documentos_index', error='El nombre es obligatorio'))
        
        try:
            financiero.actualizar_tipo_documento(id, nombre, activo)
            return redirect(url_for('tipos_documentos_index', mensaje='Tipo de documento actualizado correctamente'))
        except Exception as e:
            return redirect(url_for('tipos_documentos_index', error=f'Error al actualizar tipo de documento: {str(e)}'))
    
    return render_template('financiero/tipos_documentos/form.html', tipo=dict(tipo))


@app.route("/financiero/tipos-documentos/<int:id>/eliminar", methods=["POST"], endpoint="tipo_documento_eliminar")
@auth.login_required
@auth.permission_required('/financiero/tipos-documentos')
def tipo_documento_eliminar(id):
    """Eliminar tipo de documento"""
    try:
        financiero.eliminar_tipo_documento(id)
        return redirect(url_for('tipos_documentos_index', mensaje='Tipo de documento eliminado correctamente'))
    except Exception as e:
        return redirect(url_for('tipos_documentos_index', error=f'Error al eliminar tipo de documento: {str(e)}'))


# ==================== RUTAS PARA SALDOS INICIALES (BANCOS) ====================

@app.route("/financiero/saldos-iniciales", methods=["GET"], endpoint="saldos_iniciales_index")
@auth.login_required
@auth.permission_required('/financiero/saldos-iniciales')
def saldos_iniciales_index():
    """Página principal de gestión de bancos y saldos iniciales"""
    bancos = financiero.obtener_bancos()
    fecha_saldo_inicial = financiero.obtener_fecha_saldo_inicial()
    error = request.args.get('error')
    mensaje = request.args.get('mensaje')
    
    return render_template('financiero/saldos_iniciales/index.html',
                         bancos=bancos,
                         fecha_saldo_inicial=fecha_saldo_inicial,
                         error=error,
                         mensaje=mensaje)


@app.route("/api/financiero/actualizar-fecha-saldo-inicial", methods=["POST"], endpoint="actualizar_fecha_saldo_inicial")
@auth.login_required
@auth.permission_required('/financiero/saldos-iniciales')
def actualizar_fecha_saldo_inicial():
    """API para actualizar la fecha global de saldos iniciales"""
    try:
        data = request.get_json()
        fecha_str = data.get('fecha', '').strip()
        
        if not fecha_str:
            return jsonify({'success': False, 'message': 'La fecha es obligatoria'}), 400
        
        from datetime import datetime
        fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        
        financiero.actualizar_fecha_saldo_inicial(fecha)
        return jsonify({'success': True, 'message': 'Fecha de saldo inicial actualizada correctamente'}), 200
    except ValueError:
        return jsonify({'success': False, 'message': 'Formato de fecha inválido'}), 400
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error al actualizar fecha: {str(e)}'}), 500


@app.route("/financiero/saldos-iniciales/nuevo", methods=["GET", "POST"], endpoint="banco_nuevo")
@auth.login_required
@auth.permission_required('/financiero/saldos-iniciales')
def banco_nuevo():
    """Crear nuevo banco"""
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        saldo_inicial_str = request.form.get('saldo_inicial', '0').strip()
        
        if not nombre:
            return redirect(url_for('saldos_iniciales_index', error='El nombre es obligatorio'))
        
        try:
            saldo_inicial = float(saldo_inicial_str) if saldo_inicial_str else 0
            financiero.crear_banco(nombre, saldo_inicial)
            return redirect(url_for('saldos_iniciales_index', mensaje='Banco creado correctamente'))
        except ValueError:
            return redirect(url_for('saldos_iniciales_index', error='El saldo inicial debe ser un número válido'))
        except Exception as e:
            return redirect(url_for('saldos_iniciales_index', error=f'Error al crear banco: {str(e)}'))
    
    return render_template('financiero/saldos_iniciales/form.html', banco=None)


@app.route("/financiero/saldos-iniciales/<int:id>/editar", methods=["GET", "POST"], endpoint="banco_editar")
@auth.login_required
@auth.permission_required('/financiero/saldos-iniciales')
def banco_editar(id):
    """Editar banco"""
    banco = financiero.obtener_banco_por_id(id)
    if not banco:
        return redirect(url_for('saldos_iniciales_index', error='Banco no encontrado'))
    
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        saldo_inicial_str = request.form.get('saldo_inicial', '0').strip()
        activo = request.form.get('activo') == 'on'
        
        if not nombre:
            return redirect(url_for('saldos_iniciales_index', error='El nombre es obligatorio'))
        
        try:
            saldo_inicial = float(saldo_inicial_str) if saldo_inicial_str else 0
            financiero.actualizar_banco(id, nombre, saldo_inicial, activo)
            return redirect(url_for('saldos_iniciales_index', mensaje='Banco actualizado correctamente'))
        except ValueError:
            return redirect(url_for('saldos_iniciales_index', error='El saldo inicial debe ser un número válido'))
        except Exception as e:
            return redirect(url_for('saldos_iniciales_index', error=f'Error al actualizar banco: {str(e)}'))
    
    return render_template('financiero/saldos_iniciales/form.html', banco=dict(banco))


@app.route("/financiero/saldos-iniciales/<int:id>/eliminar", methods=["POST"], endpoint="banco_eliminar")
@auth.login_required
@auth.permission_required('/financiero/saldos-iniciales')
def banco_eliminar(id):
    """Eliminar banco"""
    try:
        financiero.eliminar_banco(id)
        return redirect(url_for('saldos_iniciales_index', mensaje='Banco eliminado correctamente'))
    except Exception as e:
        return redirect(url_for('saldos_iniciales_index', error=f'Error al eliminar banco: {str(e)}'))


# ==================== RUTAS PARA CUENTAS A RECIBIR ====================

@app.route("/financiero/cuentas-a-recibir", methods=["GET"], endpoint="cuentas_a_recibir_index")
@auth.login_required
@auth.permission_required('/financiero/cuentas-a-recibir')
def cuentas_a_recibir_index():
    """Página principal de gestión de cuentas a recibir"""
    # Obtener datos para los dropdowns
    documentos = financiero.obtener_tipos_documentos(activo=True)
    bancos = financiero.obtener_bancos(activo=True)
    categorias_ingresos = financiero.obtener_categorias_ingresos(activo=True)
    proyectos = financiero.obtener_proyectos(activo=True)
    
    # Obtener todos los tipos de ingresos para el JavaScript
    tipos_ingresos_raw = financiero.obtener_tipos_ingresos(activo=True)
    # Convertir DictRow a diccionarios normales para JSON
    tipos_ingresos = [dict(tipo) for tipo in tipos_ingresos_raw]
    
    # Obtener clientes
    try:
        clientes_lista = presupuestos.obtener_clientes()
        clientes = [c['nombre'] for c in clientes_lista]
    except:
        clientes = []
    
    # Filtros
    filtros = {}
    fecha_desde = request.args.get('fecha_desde', '').strip()
    fecha_hasta = request.args.get('fecha_hasta', '').strip()
    cliente_filtro = request.args.get('cliente', '').strip()
    estado_filtro = request.args.get('estado', '').strip()
    banco_filtro = request.args.get('banco_id', type=int)
    
    if fecha_desde:
        filtros['fecha_desde'] = fecha_desde
    if fecha_hasta:
        filtros['fecha_hasta'] = fecha_hasta
    if cliente_filtro:
        filtros['cliente'] = cliente_filtro
    if estado_filtro:
        filtros['estado'] = estado_filtro
    if banco_filtro:
        filtros['banco_id'] = banco_filtro
    
    # Paginación
    pagina = request.args.get('pagina', type=int, default=1)
    limite = request.args.get('limite', type=int, default=50)
    
    # Validar límite (mínimo 10, máximo 500)
    if limite < 10:
        limite = 10
    elif limite > 500:
        limite = 500
    
    # Calcular offset
    offset = (pagina - 1) * limite
    
    # Obtener total de registros
    total_registros = financiero.contar_cuentas_a_recibir(filtros if filtros else None)
    
    # Calcular total de páginas
    total_paginas = (total_registros + limite - 1) // limite if total_registros > 0 else 1
    
    # Asegurar que la página esté en rango válido
    if pagina < 1:
        pagina = 1
    elif pagina > total_paginas and total_paginas > 0:
        pagina = total_paginas
    
    # Recalcular offset con la página corregida
    offset = (pagina - 1) * limite
    
    # Obtener cuentas con paginación
    cuentas = financiero.obtener_cuentas_a_recibir(
        filtros if filtros else None,
        limite=limite,
        offset=offset
    )
    
    error = request.args.get('error')
    mensaje = request.args.get('mensaje')
    
    return render_template('financiero/cuentas_a_recibir/index.html',
                         cuentas=cuentas,
                         documentos=documentos,
                         bancos=bancos,
                         pagina=pagina,
                         limite=limite,
                         total_registros=total_registros,
                         total_paginas=total_paginas,
                         categorias_ingresos=categorias_ingresos,
                         tipos_ingresos=tipos_ingresos,
                         proyectos=proyectos,
                         clientes=clientes,
                         fecha_desde=fecha_desde,
                         fecha_hasta=fecha_hasta,
                         cliente_filtro=cliente_filtro,
                         estado_filtro=estado_filtro,
                         banco_filtro=banco_filtro,
                         error=error,
                         mensaje=mensaje)


@app.route("/financiero/cuentas-a-recibir/nuevo", methods=["GET", "POST"], endpoint="cuenta_a_recibir_nuevo")
@auth.login_required
@auth.permission_required('/financiero/cuentas-a-recibir')
def cuenta_a_recibir_nuevo():
    """Crear nueva cuenta a recibir"""
    if request.method == 'POST':
        fecha_emision_str = request.form.get('fecha_emision', '').strip()
        documento_id_str = request.form.get('documento_id', '').strip()
        cuenta_id_str = request.form.get('cuenta', '').strip()
        plano_cuenta = request.form.get('plano_cuenta', '').strip()
        proyecto_id_str = request.form.get('proyecto', '').strip()
        tipo = request.form.get('tipo', 'FCON').strip()
        cliente = request.form.get('cliente', '').strip()
        factura = request.form.get('factura', '').strip()
        descripcion = request.form.get('descripcion', '').strip()
        banco_id_str = request.form.get('banco_id', '').strip()
        valor_str = request.form.get('valor', '0').strip()
        num_cuotas_str = request.form.get('num_cuotas', '1').strip()
        valor_cuota_str = request.form.get('valor_cuota', '').strip()
        vencimiento_str = request.form.get('vencimiento', '').strip()
        fecha_recibo_str = request.form.get('fecha_recibo', '').strip()
        
        # Validar campos obligatorios
        if not fecha_emision_str:
            return redirect(url_for('cuentas_a_recibir_index', error='La fecha de emisión es obligatoria'))
        if not documento_id_str:
            return redirect(url_for('cuentas_a_recibir_index', error='El documento es obligatorio'))
        if not cuenta_id_str:
            return redirect(url_for('cuentas_a_recibir_index', error='La cuenta es obligatoria'))
        if not plano_cuenta:
            return redirect(url_for('cuentas_a_recibir_index', error='El plano de cuenta es obligatorio'))
        if not proyecto_id_str:
            return redirect(url_for('cuentas_a_recibir_index', error='El proyecto es obligatorio'))
        if not cliente:
            return redirect(url_for('cuentas_a_recibir_index', error='El cliente es obligatorio'))
        if not descripcion:
            return redirect(url_for('cuentas_a_recibir_index', error='La descripción es obligatoria'))
        if not banco_id_str:
            return redirect(url_for('cuentas_a_recibir_index', error='El banco es obligatorio'))
        if not valor_str:
            return redirect(url_for('cuentas_a_recibir_index', error='El valor total es obligatorio'))
        if not vencimiento_str:
            return redirect(url_for('cuentas_a_recibir_index', error='El vencimiento es obligatorio'))
        
        try:
            fecha_emision = datetime.strptime(fecha_emision_str, "%Y-%m-%d").date()
            documento_id = int(documento_id_str)
            cuenta_categoria_id = int(cuenta_id_str)
            proyecto_id = int(proyecto_id_str) if proyecto_id_str else None
            banco_id = int(banco_id_str)
            valor_total = float(valor_str.replace('.', '').replace(',', '.'))
            num_cuotas = int(num_cuotas_str) if num_cuotas_str else 1
            vencimiento_base = datetime.strptime(vencimiento_str, "%Y-%m-%d").date()
            fecha_recibo = datetime.strptime(fecha_recibo_str, "%Y-%m-%d").date() if fecha_recibo_str else None
            
            # Si es NCRE, hacer el valor negativo
            if tipo == 'NCRE':
                valor_total = -abs(valor_total)
            
            # Calcular valor de cuota
            # Si es NCRE, el valor_cuota también debe ser negativo
            if tipo == 'NCRE':
                valor_cuota = valor_total / num_cuotas if num_cuotas > 0 else valor_total
            else:
                valor_cuota = abs(valor_total) / num_cuotas if num_cuotas > 0 else abs(valor_total)
            
            # Calcular estado automáticamente
            estado = 'RECIBIDO' if fecha_recibo else 'ABIERTO'
            
            # Si hay múltiples cuotas, crear un registro por cada cuota
            from datetime import timedelta
            cuentas_creadas = []
            
            for i in range(1, num_cuotas + 1):
                # Calcular vencimiento de esta cuota (30 días de diferencia)
                vencimiento_cuota = vencimiento_base + timedelta(days=(i - 1) * 30)
                
                # Calcular status_recibo si hay fecha_recibo
                status_recibo = None
                if fecha_recibo:
                    if fecha_recibo < vencimiento_cuota:
                        status_recibo = 'ADELANTADO'
                    elif fecha_recibo > vencimiento_cuota:
                        status_recibo = 'ATRASADO'
                    else:
                        status_recibo = 'EN DIA'
                
                cuenta_id = financiero.crear_cuenta_a_recibir(
                    fecha_emision=fecha_emision,
                    documento_id=documento_id,
                    cuenta_id=cuenta_categoria_id,
                    plano_cuenta=plano_cuenta,
                    tipo=tipo,
                    cliente=cliente,
                    factura=factura if factura else None,
                    descripcion=descripcion,
                    banco_id=banco_id,
                    valor=valor_total,  # Puede ser negativo si es NCRE
                    cuotas=f"{i} de {num_cuotas}",
                    valor_cuota=valor_cuota,  # Puede ser negativo si es NCRE
                    vencimiento=vencimiento_cuota,
                    fecha_recibo=fecha_recibo,
                    estado=estado,
                    proyecto_id=proyecto_id
                )
                cuentas_creadas.append(cuenta_id)
            
            mensaje = f'{"Cuenta" if num_cuotas == 1 else f"{num_cuotas} cuotas"} creada{"s" if num_cuotas > 1 else ""} correctamente'
            return redirect(url_for('cuentas_a_recibir_index', mensaje=mensaje))
        except ValueError as e:
            return redirect(url_for('cuentas_a_recibir_index', error=f'Error en los datos: {str(e)}'))
        except Exception as e:
            return redirect(url_for('cuentas_a_recibir_index', error=f'Error al crear cuenta a recibir: {str(e)}'))
    
    # GET: mostrar formulario
    documentos = financiero.obtener_tipos_documentos(activo=True)
    bancos = financiero.obtener_bancos(activo=True)
    categorias_ingresos = financiero.obtener_categorias_ingresos(activo=True)
    tipos_ingresos_raw = financiero.obtener_tipos_ingresos(activo=True)
    proyectos = financiero.obtener_proyectos(activo=True)
    
    # Convertir DictRow a diccionarios normales para JSON
    tipos_ingresos = [dict(tipo) for tipo in tipos_ingresos_raw]
    
    # Obtener clientes
    try:
        clientes_lista = presupuestos.obtener_clientes()
        clientes = [c['nombre'] for c in clientes_lista]
    except:
        clientes = []
    
    return render_template('financiero/cuentas_a_recibir/form.html',
                         cuenta=None,
                         documentos=documentos,
                         bancos=bancos,
                         categorias_ingresos=categorias_ingresos,
                         tipos_ingresos=tipos_ingresos,
                         proyectos=proyectos,
                         clientes=clientes)


@app.route("/financiero/cuentas-a-recibir/<int:id>/editar", methods=["GET", "POST"], endpoint="cuenta_a_recibir_editar")
@auth.login_required
@auth.permission_required('/financiero/cuentas-a-recibir')
def cuenta_a_recibir_editar(id):
    """Editar cuenta a recibir"""
    cuenta = financiero.obtener_cuenta_a_recibir_por_id(id)
    if not cuenta:
        return redirect(url_for('cuentas_a_recibir_index', error='Cuenta a recibir no encontrada'))
    
    if request.method == 'POST':
        fecha_emision_str = request.form.get('fecha_emision', '').strip()
        documento_id_str = request.form.get('documento_id', '').strip()
        cuenta_id_str = request.form.get('cuenta', '').strip()
        plano_cuenta = request.form.get('plano_cuenta', '').strip()
        proyecto_id_str = request.form.get('proyecto', '').strip()
        tipo = request.form.get('tipo', 'FCON').strip()
        cliente = request.form.get('cliente', '').strip()
        factura = request.form.get('factura', '').strip()
        descripcion = request.form.get('descripcion', '').strip()
        banco_id_str = request.form.get('banco_id', '').strip()
        valor_str = request.form.get('valor', '0').strip()
        num_cuotas_str = request.form.get('num_cuotas', '1').strip()
        valor_cuota_str = request.form.get('valor_cuota', '').strip()
        vencimiento_str = request.form.get('vencimiento', '').strip()
        fecha_recibo_str = request.form.get('fecha_recibo', '').strip()
        
        if not fecha_emision_str:
            return redirect(url_for('cuentas_a_recibir_index', error='La fecha de emisión es obligatoria'))
        
        try:
            fecha_emision = datetime.strptime(fecha_emision_str, "%Y-%m-%d").date()
            documento_id = int(documento_id_str) if documento_id_str else None
            cuenta_categoria_id = int(cuenta_id_str) if cuenta_id_str else None
            proyecto_id = int(proyecto_id_str) if proyecto_id_str else None
            banco_id = int(banco_id_str) if banco_id_str else None
            valor = float(valor_str.replace('.', '').replace(',', '.')) if valor_str else 0
            valor_cuota = float(valor_cuota_str.replace('.', '').replace(',', '.')) if valor_cuota_str else None
            vencimiento = datetime.strptime(vencimiento_str, "%Y-%m-%d").date() if vencimiento_str else None
            fecha_recibo = datetime.strptime(fecha_recibo_str, "%Y-%m-%d").date() if fecha_recibo_str else None
            
            # Si es NCRE, hacer el valor negativo
            if tipo == 'NCRE':
                valor = -abs(valor)
                if valor_cuota is not None:
                    valor_cuota = -abs(valor_cuota)
            
            # Calcular estado automáticamente
            estado = 'RECIBIDO' if fecha_recibo else 'ABIERTO'
            
            financiero.actualizar_cuenta_a_recibir(
                cuenta_id=id,
                fecha_emision=fecha_emision,
                documento_id=documento_id,
                cuenta_categoria_id=cuenta_categoria_id,
                plano_cuenta=plano_cuenta if plano_cuenta else None,
                tipo=tipo,
                cliente=cliente if cliente else None,
                factura=factura if factura else None,
                descripcion=descripcion if descripcion else None,
                banco_id=banco_id,
                valor=valor,
                cuotas=request.form.get('cuotas', '').strip() if request.form.get('cuotas') else None,
                valor_cuota=valor_cuota,
                vencimiento=vencimiento,
                fecha_recibo=fecha_recibo,
                estado=estado,
                proyecto_id=proyecto_id,
                actualizar_fecha_recibo=True  # Siempre actualizar fecha_recibo cuando se edita desde el formulario
            )
            return redirect(url_for('cuentas_a_recibir_index', mensaje='Cuenta a recibir actualizada correctamente'))
        except ValueError as e:
            return redirect(url_for('cuentas_a_recibir_index', error=f'Error en los datos: {str(e)}'))
        except Exception as e:
            return redirect(url_for('cuentas_a_recibir_index', error=f'Error al actualizar cuenta a recibir: {str(e)}'))
    
    # GET: mostrar formulario
    documentos = financiero.obtener_tipos_documentos(activo=True)
    bancos = financiero.obtener_bancos(activo=True)
    categorias_ingresos = financiero.obtener_categorias_ingresos(activo=True)
    tipos_ingresos_raw = financiero.obtener_tipos_ingresos(activo=True)
    proyectos = financiero.obtener_proyectos(activo=True)
    
    # Convertir DictRow a diccionarios normales para JSON
    tipos_ingresos = [dict(tipo) for tipo in tipos_ingresos_raw]
    
    # Obtener clientes
    try:
        clientes_lista = presupuestos.obtener_clientes()
        clientes = [c['nombre'] for c in clientes_lista]
    except:
        clientes = []
    
    return render_template('financiero/cuentas_a_recibir/form.html',
                         cuenta=dict(cuenta),
                         documentos=documentos,
                         bancos=bancos,
                         categorias_ingresos=categorias_ingresos,
                         tipos_ingresos=tipos_ingresos,
                         proyectos=proyectos,
                         clientes=clientes)


@app.route("/financiero/cuentas-a-recibir/<int:id>/eliminar", methods=["POST"], endpoint="cuenta_a_recibir_eliminar")
@auth.login_required
@auth.permission_required('/financiero/cuentas-a-recibir')
def cuenta_a_recibir_eliminar(id):
    """Eliminar cuenta a recibir"""
    try:
        financiero.eliminar_cuenta_a_recibir(id)
        return redirect(url_for('cuentas_a_recibir_index', mensaje='Cuenta a recibir eliminada correctamente'))
    except Exception as e:
        return redirect(url_for('cuentas_a_recibir_index', error=f'Error al eliminar cuenta a recibir: {str(e)}'))


@app.route("/financiero/cuentas-a-recibir/<int:id>/agregar-pago", methods=["POST"], endpoint="cuenta_a_recibir_agregar_pago")
@auth.login_required
@auth.permission_required('/financiero/cuentas-a-recibir')
def cuenta_a_recibir_agregar_pago(id):
    """Agregar pago a una cuenta a recibir"""
    try:
        monto_pago_str = request.form.get('monto_pago', '').strip()
        fecha_pago_str = request.form.get('fecha_pago', '').strip()
        
        if not monto_pago_str:
            return jsonify({'success': False, 'error': 'El monto del pago es obligatorio'}), 400
        
        if not fecha_pago_str:
            return jsonify({'success': False, 'error': 'La fecha de pago es obligatoria'}), 400
        
        # Convertir monto (aceptar formato con punto o coma)
        monto_pago = float(monto_pago_str.replace('.', '').replace(',', '.'))
        
        # Convertir fecha
        fecha_pago = datetime.strptime(fecha_pago_str, "%Y-%m-%d").date()
        
        financiero.agregar_pago_cuenta_a_recibir(id, monto_pago, fecha_pago)
        
        return jsonify({'success': True, 'mensaje': 'Pago agregado correctamente'})
    except ValueError as e:
        return jsonify({'success': False, 'error': f'Error en los datos: {str(e)}'}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': f'Error al agregar pago: {str(e)}'}), 500


@app.route("/financiero/cuentas-a-recibir/exportar-csv", methods=["GET"], endpoint="cuentas_a_recibir_exportar_csv")
@auth.login_required
@auth.permission_required('/financiero/cuentas-a-recibir')
def cuentas_a_recibir_exportar_csv():
    """Exportar cuentas a recibir a CSV"""
    try:
        # Aplicar los mismos filtros que en el index
        filtros = {}
        fecha_desde = request.args.get('fecha_desde', '')
        fecha_hasta = request.args.get('fecha_hasta', '')
        cliente_filtro = request.args.get('cliente', '')
        estado_filtro = request.args.get('estado', '')
        banco_filtro = request.args.get('banco_id', '')
        
        if fecha_desde:
            filtros['fecha_desde'] = fecha_desde
        if fecha_hasta:
            filtros['fecha_hasta'] = fecha_hasta
        if cliente_filtro:
            filtros['cliente'] = cliente_filtro
        if estado_filtro:
            filtros['estado'] = estado_filtro
        if banco_filtro:
            filtros['banco_id'] = banco_filtro
        
        csv_content = financiero.exportar_cuentas_a_recibir_csv(filtros if filtros else None)
        
        response = make_response(csv_content)
        response.headers['Content-Type'] = 'text/csv; charset=utf-8'
        response.headers['Content-Disposition'] = f'attachment; filename=cuentas_a_recibir_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        return response
    except Exception as e:
        return redirect(url_for('cuentas_a_recibir_index', error=f'Error al exportar CSV: {str(e)}'))


@app.route("/financiero/cuentas-a-recibir/importar-csv", methods=["POST"], endpoint="cuentas_a_recibir_importar_csv")
@auth.login_required
@auth.permission_required('/financiero/cuentas-a-recibir')
def cuentas_a_recibir_importar_csv():
    """Importar cuentas a recibir desde CSV"""
    try:
        if 'archivo_csv' not in request.files:
            return redirect(url_for('cuentas_a_recibir_index', error='No se seleccionó ningún archivo'))
        
        archivo = request.files['archivo_csv']
        if archivo.filename == '':
            return redirect(url_for('cuentas_a_recibir_index', error='No se seleccionó ningún archivo'))
        
        if not archivo.filename.endswith('.csv'):
            return redirect(url_for('cuentas_a_recibir_index', error='El archivo debe ser CSV'))
        
        csv_content = archivo.read().decode('utf-8')
        cuentas_importadas, errores = financiero.importar_cuentas_a_recibir_csv(csv_content)
        
        mensaje = f'Se importaron {len(cuentas_importadas)} cuenta(s) correctamente'
        if errores:
            mensaje += f'. Errores: {len(errores)}'
            # Guardar errores en sesión para mostrarlos
            session['errores_importacion'] = errores
        
        return redirect(url_for('cuentas_a_recibir_index', mensaje=mensaje))
    except Exception as e:
        return redirect(url_for('cuentas_a_recibir_index', error=f'Error al importar CSV: {str(e)}'))


# ==================== RUTAS PARA CUENTAS A PAGAR ====================

@app.route("/financiero/cuentas-a-pagar", methods=["GET"], endpoint="cuentas_a_pagar_index")
@auth.login_required
@auth.permission_required('/financiero/cuentas-a-pagar')
def cuentas_a_pagar_index():
    """Listar cuentas a pagar"""
    documentos = financiero.obtener_tipos_documentos(activo=True)
    bancos = financiero.obtener_bancos(activo=True)
    categorias_gastos = financiero.obtener_categorias_gastos(activo=True)
    tipos_gastos_raw = financiero.obtener_tipos_gastos(activo=True)
    tipos_gastos = [dict(tipo) for tipo in tipos_gastos_raw]  # Convertir DictRow a dict
    proyectos = financiero.obtener_proyectos(activo=True)
    
    # Obtener lista de proveedores
    proveedores_raw = presupuestos.obtener_proveedores(activo=True)
    proveedores = [p['nombre'] for p in proveedores_raw if p.get('nombre')]
    
    # Filtros
    filtros = {}
    fecha_desde = request.args.get('fecha_desde', '')
    fecha_hasta = request.args.get('fecha_hasta', '')
    proveedor_filtro = request.args.get('proveedor', '')
    estado_filtro = request.args.get('estado', '')
    banco_filtro = request.args.get('banco_id', '')
    
    if fecha_desde:
        filtros['fecha_desde'] = fecha_desde
    if fecha_hasta:
        filtros['fecha_hasta'] = fecha_hasta
    if proveedor_filtro:
        filtros['proveedor'] = proveedor_filtro
    if estado_filtro:
        filtros['estado'] = estado_filtro
    if banco_filtro:
        filtros['banco_id'] = banco_filtro
    
    # Paginación
    pagina = request.args.get('pagina', type=int, default=1)
    limite = request.args.get('limite', type=int, default=50)
    
    # Validar límite (mínimo 10, máximo 500)
    if limite < 10:
        limite = 10
    elif limite > 500:
        limite = 500
    
    # Calcular offset
    offset = (pagina - 1) * limite
    
    # Obtener total de registros
    total_registros = financiero.contar_cuentas_a_pagar(filtros if filtros else None)
    
    # Calcular total de páginas
    total_paginas = (total_registros + limite - 1) // limite if total_registros > 0 else 1
    
    # Asegurar que la página esté en rango válido
    if pagina < 1:
        pagina = 1
    elif pagina > total_paginas and total_paginas > 0:
        pagina = total_paginas
    
    # Recalcular offset con la página corregida
    offset = (pagina - 1) * limite
    
    # Obtener cuentas con paginación
    cuentas = financiero.obtener_cuentas_a_pagar(
        filtros if filtros else None,
        limite=limite,
        offset=offset
    )
    
    error = request.args.get('error')
    mensaje = request.args.get('mensaje')
    
    return render_template('financiero/cuentas_a_pagar/index.html',
                         cuentas=cuentas,
                         documentos=documentos,
                         bancos=bancos,
                         pagina=pagina,
                         limite=limite,
                         total_registros=total_registros,
                         total_paginas=total_paginas,
                         categorias_gastos=categorias_gastos,
                         tipos_gastos=tipos_gastos,
                         proyectos=proyectos,
                         proveedores=proveedores,
                         fecha_desde=fecha_desde,
                         fecha_hasta=fecha_hasta,
                         proveedor_filtro=proveedor_filtro,
                         estado_filtro=estado_filtro,
                         banco_filtro=banco_filtro,
                         error=error,
                         mensaje=mensaje)


@app.route("/financiero/cuentas-a-pagar/nuevo", methods=["GET", "POST"], endpoint="cuenta_a_pagar_nuevo")
@auth.login_required
@auth.permission_required('/financiero/cuentas-a-pagar')
def cuenta_a_pagar_nuevo():
    """Crear nueva cuenta a pagar"""
    if request.method == 'POST':
        fecha_emision_str = request.form.get('fecha_emision', '').strip()
        documento_id_str = request.form.get('documento_id', '').strip()
        cuenta_id_str = request.form.get('cuenta', '').strip()
        plano_cuenta = request.form.get('plano_cuenta', '').strip()
        proyecto_id_str = request.form.get('proyecto', '').strip()
        tipo = request.form.get('tipo', 'FCON').strip()
        proveedor = request.form.get('proveedor', '').strip()
        factura = request.form.get('factura', '').strip()
        descripcion = request.form.get('descripcion', '').strip()
        banco_id_str = request.form.get('banco_id', '').strip()
        valor_str = request.form.get('valor', '0').strip()
        num_cuotas_str = request.form.get('num_cuotas', '1').strip()
        valor_cuota_str = request.form.get('valor_cuota', '').strip()
        vencimiento_str = request.form.get('vencimiento', '').strip()
        fecha_pago_str = request.form.get('fecha_pago', '').strip()
        
        # Validar campos obligatorios
        if not fecha_emision_str:
            return redirect(url_for('cuentas_a_pagar_index', error='La fecha de emisión es obligatoria'))
        if not documento_id_str:
            return redirect(url_for('cuentas_a_pagar_index', error='El documento es obligatorio'))
        if not cuenta_id_str:
            return redirect(url_for('cuentas_a_pagar_index', error='La cuenta es obligatoria'))
        if not plano_cuenta:
            return redirect(url_for('cuentas_a_pagar_index', error='El plano de cuenta es obligatorio'))
        if not proyecto_id_str:
            return redirect(url_for('cuentas_a_pagar_index', error='El proyecto es obligatorio'))
        if not proveedor:
            return redirect(url_for('cuentas_a_pagar_index', error='El proveedor es obligatorio'))
        if not descripcion:
            return redirect(url_for('cuentas_a_pagar_index', error='La descripción es obligatoria'))
        if not banco_id_str:
            return redirect(url_for('cuentas_a_pagar_index', error='El banco es obligatorio'))
        if not valor_str:
            return redirect(url_for('cuentas_a_pagar_index', error='El valor total es obligatorio'))
        if not vencimiento_str:
            return redirect(url_for('cuentas_a_pagar_index', error='El vencimiento es obligatorio'))
        
        try:
            fecha_emision = datetime.strptime(fecha_emision_str, "%Y-%m-%d").date()
            documento_id = int(documento_id_str)
            cuenta_categoria_id = int(cuenta_id_str)
            proyecto_id = int(proyecto_id_str) if proyecto_id_str else None
            banco_id = int(banco_id_str)
            valor_total = float(valor_str.replace('.', '').replace(',', '.'))
            num_cuotas = int(num_cuotas_str) if num_cuotas_str else 1
            vencimiento_base = datetime.strptime(vencimiento_str, "%Y-%m-%d").date()
            fecha_pago = datetime.strptime(fecha_pago_str, "%Y-%m-%d").date() if fecha_pago_str else None
            
            # Si es NCRE, hacer el valor negativo
            if tipo == 'NCRE':
                valor_total = -abs(valor_total)
            
            # Calcular valor de cuota
            # Si es NCRE, el valor_cuota también debe ser negativo
            if tipo == 'NCRE':
                valor_cuota = valor_total / num_cuotas if num_cuotas > 0 else valor_total
            else:
                valor_cuota = abs(valor_total) / num_cuotas if num_cuotas > 0 else abs(valor_total)
            
            # Calcular estado automáticamente
            estado = 'PAGADO' if fecha_pago else 'ABIERTO'
            
            # Si hay múltiples cuotas, crear un registro por cada cuota
            from datetime import timedelta
            cuentas_creadas = []
            
            for i in range(1, num_cuotas + 1):
                # Calcular vencimiento de esta cuota (30 días de diferencia)
                vencimiento_cuota = vencimiento_base + timedelta(days=(i - 1) * 30)
                
                # Calcular status_pago si hay fecha_pago
                status_pago = None
                if fecha_pago:
                    if fecha_pago < vencimiento_cuota:
                        status_pago = 'ADELANTADO'
                    elif fecha_pago > vencimiento_cuota:
                        status_pago = 'ATRASADO'
                    else:
                        status_pago = 'EN DIA'
                
                cuenta_id = financiero.crear_cuenta_a_pagar(
                    fecha_emision=fecha_emision,
                    documento_id=documento_id,
                    cuenta_id=cuenta_categoria_id,
                    plano_cuenta=plano_cuenta,
                    tipo=tipo,
                    proveedor=proveedor,
                    factura=factura if factura else None,
                    descripcion=descripcion,
                    banco_id=banco_id,
                    valor=valor_total,  # Puede ser negativo si es NCRE
                    cuotas=f"{i} de {num_cuotas}",
                    valor_cuota=valor_cuota,  # Puede ser negativo si es NCRE
                    vencimiento=vencimiento_cuota,
                    fecha_pago=fecha_pago,
                    estado=estado,
                    proyecto_id=proyecto_id
                )
                cuentas_creadas.append(cuenta_id)
            
            mensaje = f'{"Cuenta" if num_cuotas == 1 else f"{num_cuotas} cuotas"} creada{"s" if num_cuotas > 1 else ""} correctamente'
            return redirect(url_for('cuentas_a_pagar_index', mensaje=mensaje))
        except ValueError as e:
            return redirect(url_for('cuentas_a_pagar_index', error=f'Error en los datos: {str(e)}'))
        except Exception as e:
            return redirect(url_for('cuentas_a_pagar_index', error=f'Error al crear cuenta a pagar: {str(e)}'))
    
    # GET: mostrar formulario
    documentos = financiero.obtener_tipos_documentos(activo=True)
    bancos = financiero.obtener_bancos(activo=True)
    categorias_gastos = financiero.obtener_categorias_gastos(activo=True)
    tipos_gastos_raw = financiero.obtener_tipos_gastos(activo=True)
    tipos_gastos = [dict(tipo) for tipo in tipos_gastos_raw]  # Convertir DictRow a dict
    proyectos = financiero.obtener_proyectos(activo=True)
    
    # Obtener lista de proveedores
    proveedores_raw = presupuestos.obtener_proveedores(activo=True)
    proveedores = [p['nombre'] for p in proveedores_raw if p.get('nombre')]
    
    return render_template('financiero/cuentas_a_pagar/form.html',
                         cuenta=None,
                         documentos=documentos,
                         bancos=bancos,
                         categorias_gastos=categorias_gastos,
                         tipos_gastos=tipos_gastos,
                         proyectos=proyectos,
                         proveedores=proveedores)


@app.route("/financiero/cuentas-a-pagar/<int:id>/editar", methods=["GET", "POST"], endpoint="cuenta_a_pagar_editar")
@auth.login_required
@auth.permission_required('/financiero/cuentas-a-pagar')
def cuenta_a_pagar_editar(id):
    """Editar cuenta a pagar"""
    cuenta = financiero.obtener_cuenta_a_pagar_por_id(id)
    if not cuenta:
        return redirect(url_for('cuentas_a_pagar_index', error='Cuenta a pagar no encontrada'))
    
    if request.method == 'POST':
        fecha_emision_str = request.form.get('fecha_emision', '').strip()
        documento_id_str = request.form.get('documento_id', '').strip()
        cuenta_id_str = request.form.get('cuenta', '').strip()
        plano_cuenta = request.form.get('plano_cuenta', '').strip()
        proyecto_id_str = request.form.get('proyecto', '').strip()
        tipo = request.form.get('tipo', 'FCON').strip()
        proveedor = request.form.get('proveedor', '').strip()
        factura = request.form.get('factura', '').strip()
        descripcion = request.form.get('descripcion', '').strip()
        banco_id_str = request.form.get('banco_id', '').strip()
        valor_str = request.form.get('valor', '0').strip()
        num_cuotas_str = request.form.get('num_cuotas', '1').strip()
        valor_cuota_str = request.form.get('valor_cuota', '').strip()
        vencimiento_str = request.form.get('vencimiento', '').strip()
        fecha_pago_str = request.form.get('fecha_pago', '').strip()
        
        if not fecha_emision_str:
            return redirect(url_for('cuentas_a_pagar_index', error='La fecha de emisión es obligatoria'))
        
        try:
            fecha_emision = datetime.strptime(fecha_emision_str, "%Y-%m-%d").date()
            documento_id = int(documento_id_str) if documento_id_str else None
            cuenta_categoria_id = int(cuenta_id_str) if cuenta_id_str else None
            proyecto_id = int(proyecto_id_str) if proyecto_id_str else None
            banco_id = int(banco_id_str) if banco_id_str else None
            valor = float(valor_str.replace('.', '').replace(',', '.')) if valor_str else 0
            valor_cuota = float(valor_cuota_str.replace('.', '').replace(',', '.')) if valor_cuota_str else None
            vencimiento = datetime.strptime(vencimiento_str, "%Y-%m-%d").date() if vencimiento_str else None
            fecha_pago = datetime.strptime(fecha_pago_str, "%Y-%m-%d").date() if fecha_pago_str else None
            
            # Si es NCRE, hacer el valor negativo
            if tipo == 'NCRE':
                valor = -abs(valor)
                if valor_cuota is not None:
                    valor_cuota = -abs(valor_cuota)
            
            # Calcular estado automáticamente
            estado = 'PAGADO' if fecha_pago else 'ABIERTO'
            
            financiero.actualizar_cuenta_a_pagar(
                cuenta_id=id,
                fecha_emision=fecha_emision,
                documento_id=documento_id,
                cuenta_categoria_id=cuenta_categoria_id,
                plano_cuenta=plano_cuenta if plano_cuenta else None,
                tipo=tipo,
                proveedor=proveedor if proveedor else None,
                factura=factura if factura else None,
                descripcion=descripcion if descripcion else None,
                banco_id=banco_id,
                valor=valor,
                cuotas=request.form.get('cuotas', '').strip() if request.form.get('cuotas') else None,
                valor_cuota=valor_cuota,
                vencimiento=vencimiento,
                fecha_pago=fecha_pago,
                estado=estado,
                proyecto_id=proyecto_id,
                actualizar_fecha_pago=True  # Siempre actualizar fecha_pago cuando se edita desde el formulario
            )
            return redirect(url_for('cuentas_a_pagar_index', mensaje='Cuenta a pagar actualizada correctamente'))
        except ValueError as e:
            return redirect(url_for('cuentas_a_pagar_index', error=f'Error en los datos: {str(e)}'))
        except Exception as e:
            return redirect(url_for('cuentas_a_pagar_index', error=f'Error al actualizar cuenta a pagar: {str(e)}'))
    
    # GET: mostrar formulario
    documentos = financiero.obtener_tipos_documentos(activo=True)
    bancos = financiero.obtener_bancos(activo=True)
    categorias_gastos = financiero.obtener_categorias_gastos(activo=True)
    tipos_gastos_raw = financiero.obtener_tipos_gastos(activo=True)
    tipos_gastos = [dict(tipo) for tipo in tipos_gastos_raw]  # Convertir DictRow a dict
    proyectos = financiero.obtener_proyectos(activo=True)
    
    # Obtener lista de proveedores
    proveedores_raw = presupuestos.obtener_proveedores(activo=True)
    proveedores = [p['nombre'] for p in proveedores_raw if p.get('nombre')]
    
    return render_template('financiero/cuentas_a_pagar/form.html',
                         cuenta=cuenta,
                         documentos=documentos,
                         bancos=bancos,
                         categorias_gastos=categorias_gastos,
                         tipos_gastos=tipos_gastos,
                         proyectos=proyectos,
                         proveedores=proveedores)


@app.route("/financiero/cuentas-a-pagar/<int:id>/eliminar", methods=["POST"], endpoint="cuenta_a_pagar_eliminar")
@auth.login_required
@auth.permission_required('/financiero/cuentas-a-pagar')
def cuenta_a_pagar_eliminar(id):
    """Eliminar cuenta a pagar"""
    try:
        financiero.eliminar_cuenta_a_pagar(id)
        return redirect(url_for('cuentas_a_pagar_index', mensaje='Cuenta a pagar eliminada correctamente'))
    except Exception as e:
        return redirect(url_for('cuentas_a_pagar_index', error=f'Error al eliminar cuenta a pagar: {str(e)}'))


@app.route("/financiero/cuentas-a-pagar/<int:id>/agregar-pago", methods=["POST"], endpoint="cuenta_a_pagar_agregar_pago")
@auth.login_required
@auth.permission_required('/financiero/cuentas-a-pagar')
def cuenta_a_pagar_agregar_pago(id):
    """Agregar pago a una cuenta a pagar"""
    try:
        monto_pago_str = request.form.get('monto_pago', '').strip()
        fecha_pago_str = request.form.get('fecha_pago', '').strip()
        
        if not monto_pago_str:
            return jsonify({'success': False, 'error': 'El monto del pago es obligatorio'}), 400
        
        if not fecha_pago_str:
            return jsonify({'success': False, 'error': 'La fecha de pago es obligatoria'}), 400
        
        # Convertir monto (aceptar formato con punto o coma)
        monto_pago = float(monto_pago_str.replace('.', '').replace(',', '.'))
        
        # Convertir fecha
        fecha_pago = datetime.strptime(fecha_pago_str, "%Y-%m-%d").date()
        
        financiero.agregar_pago_cuenta_a_pagar(id, monto_pago, fecha_pago)
        
        return jsonify({'success': True, 'mensaje': 'Pago agregado correctamente'})
    except ValueError as e:
        return jsonify({'success': False, 'error': f'Error en los datos: {str(e)}'}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': f'Error al agregar pago: {str(e)}'}), 500


@app.route("/financiero/cuentas-a-pagar/exportar-csv", methods=["GET"], endpoint="cuentas_a_pagar_exportar_csv")
@auth.login_required
@auth.permission_required('/financiero/cuentas-a-pagar')
def cuentas_a_pagar_exportar_csv():
    """Exportar cuentas a pagar a CSV"""
    try:
        # Aplicar los mismos filtros que en el index
        filtros = {}
        fecha_desde = request.args.get('fecha_desde', '')
        fecha_hasta = request.args.get('fecha_hasta', '')
        proveedor_filtro = request.args.get('proveedor', '')
        estado_filtro = request.args.get('estado', '')
        banco_filtro = request.args.get('banco_id', '')
        
        if fecha_desde:
            filtros['fecha_desde'] = fecha_desde
        if fecha_hasta:
            filtros['fecha_hasta'] = fecha_hasta
        if proveedor_filtro:
            filtros['proveedor'] = proveedor_filtro
        if estado_filtro:
            filtros['estado'] = estado_filtro
        if banco_filtro:
            filtros['banco_id'] = banco_filtro
        
        csv_content = financiero.exportar_cuentas_a_pagar_csv(filtros if filtros else None)
        
        response = make_response(csv_content)
        response.headers['Content-Type'] = 'text/csv; charset=utf-8'
        response.headers['Content-Disposition'] = f'attachment; filename=cuentas_a_pagar_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        return response
    except Exception as e:
        return redirect(url_for('cuentas_a_pagar_index', error=f'Error al exportar CSV: {str(e)}'))


@app.route("/financiero/cuentas-a-pagar/previsualizar-csv", methods=["POST"], endpoint="cuentas_a_pagar_previsualizar_csv")
@auth.login_required
@auth.permission_required('/financiero/cuentas-a-pagar')
def cuentas_a_pagar_previsualizar_csv():
    """Previsualizar cuentas a pagar desde CSV sin guardarlas"""
    try:
        if 'archivo_csv' not in request.files:
            return jsonify({'error': 'No se seleccionó ningún archivo'}), 400
        
        archivo = request.files['archivo_csv']
        if archivo.filename == '':
            return jsonify({'error': 'No se seleccionó ningún archivo'}), 400
        
        if not archivo.filename.endswith('.csv'):
            return jsonify({'error': 'El archivo debe ser CSV'}), 400
        
        csv_content = archivo.read().decode('utf-8')
        datos_previsualizacion, errores = financiero.previsualizar_cuentas_a_pagar_csv(csv_content)
        
        # Guardar el contenido CSV en sesión para importarlo después
        session['csv_content_para_importar'] = csv_content
        
        return jsonify({
            'datos': datos_previsualizacion,
            'errores': errores,
            'total_filas': len(datos_previsualizacion),
            'filas_validas': sum(1 for d in datos_previsualizacion if d['valida']),
            'filas_invalidas': sum(1 for d in datos_previsualizacion if not d['valida'])
        })
    except Exception as e:
        return jsonify({'error': f'Error al previsualizar CSV: {str(e)}'}), 500


@app.route("/financiero/cuentas-a-pagar/importar-csv", methods=["POST"], endpoint="cuentas_a_pagar_importar_csv")


# ==================== RUTAS DE TRANSFERENCIAS ENTRE CUENTAS ====================

@app.route("/financiero/transferencias", methods=["GET"], endpoint="transferencias_index")
@auth.login_required
@auth.permission_required('/financiero/transferencias')
def transferencias_index():
    """Página principal de gestión de transferencias entre cuentas"""
    # Filtros
    filtros = {}
    fecha_desde = request.args.get('fecha_desde', '').strip()
    fecha_hasta = request.args.get('fecha_hasta', '').strip()
    banco_origen_id = request.args.get('banco_origen_id', type=int)
    banco_destino_id = request.args.get('banco_destino_id', type=int)
    
    if fecha_desde:
        filtros['fecha_desde'] = fecha_desde
    if fecha_hasta:
        filtros['fecha_hasta'] = fecha_hasta
    if banco_origen_id:
        filtros['banco_origen_id'] = banco_origen_id
    if banco_destino_id:
        filtros['banco_destino_id'] = banco_destino_id
    
    # Paginación
    pagina = request.args.get('pagina', type=int, default=1)
    limite = request.args.get('limite', type=int, default=50)
    
    if limite < 10:
        limite = 10
    elif limite > 500:
        limite = 500
    
    # Obtener bancos para filtros
    bancos = financiero.obtener_bancos(activo=True)
    
    # Obtener total de registros
    total_registros = financiero.contar_transferencias(filtros if filtros else None)
    
    # Calcular total de páginas
    total_paginas = (total_registros + limite - 1) // limite if total_registros > 0 else 1
    
    if pagina < 1:
        pagina = 1
    elif pagina > total_paginas and total_paginas > 0:
        pagina = total_paginas
    
    offset = (pagina - 1) * limite
    
    # Obtener transferencias
    transferencias = financiero.obtener_transferencias(
        filtros if filtros else None,
        limite=limite,
        offset=offset
    )
    
    error = request.args.get('error')
    mensaje = request.args.get('mensaje')
    
    return render_template('financiero/transferencias/index.html',
                         transferencias=transferencias,
                         bancos=bancos,
                         fecha_desde=fecha_desde or '',
                         fecha_hasta=fecha_hasta or '',
                         banco_origen_id=banco_origen_id,
                         banco_destino_id=banco_destino_id,
                         pagina=pagina,
                         limite=limite,
                         total_registros=total_registros,
                         total_paginas=total_paginas,
                         error=error,
                         mensaje=mensaje)


@app.route("/financiero/transferencias/nuevo", methods=["GET", "POST"], endpoint="transferencia_nuevo")
@auth.login_required
@auth.permission_required('/financiero/transferencias')
def transferencia_nuevo():
    """Crear nueva transferencia entre cuentas"""
    if request.method == "POST":
        try:
            fecha_str = request.form.get('fecha', '').strip()
            banco_origen_id = request.form.get('banco_origen_id', type=int)
            banco_destino_id = request.form.get('banco_destino_id', type=int)
            monto_str = request.form.get('monto', '').strip()
            descripcion = request.form.get('descripcion', '').strip() or None
            
            if not fecha_str:
                return redirect(url_for('transferencias_index', error='La fecha es obligatoria'))
            
            if not banco_origen_id:
                return redirect(url_for('transferencias_index', error='El banco de origen es obligatorio'))
            
            if not banco_destino_id:
                return redirect(url_for('transferencias_index', error='El banco de destino es obligatorio'))
            
            if banco_origen_id == banco_destino_id:
                return redirect(url_for('transferencias_index', error='El banco de origen y destino no pueden ser el mismo'))
            
            if not monto_str:
                return redirect(url_for('transferencias_index', error='El monto es obligatorio'))
            
            # Convertir monto (aceptar formato con punto o coma)
            # Si tiene coma, es formato español: eliminar puntos de miles y usar coma como decimal
            # Si tiene punto pero no coma, puede ser formato inglés (punto decimal) o español (punto de miles)
            if ',' in monto_str:
                # Formato español: eliminar puntos (miles) y reemplazar coma por punto
                monto = float(monto_str.replace('.', '').replace(',', '.'))
            elif '.' in monto_str:
                # Tiene punto pero no coma: verificar si es decimal o miles
                # Si tiene más de un punto o el punto está cerca del final, es separador de miles
                partes = monto_str.split('.')
                if len(partes) == 2 and len(partes[1]) <= 2:
                    # Un solo punto y máximo 2 dígitos después: es punto decimal (formato inglés)
                    monto = float(monto_str)
                else:
                    # Múltiples puntos o muchos dígitos después: son separadores de miles
                    monto = float(monto_str.replace('.', ''))
            else:
                # Solo números, sin separadores
                monto = float(monto_str)
            
            if monto <= 0:
                return redirect(url_for('transferencias_index', error='El monto debe ser mayor a 0'))
            
            # Convertir fecha
            fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
            
            financiero.crear_transferencia(fecha, banco_origen_id, banco_destino_id, monto, descripcion)
            
            return redirect(url_for('transferencias_index', mensaje='Transferencia creada correctamente'))
        except ValueError as e:
            return redirect(url_for('transferencias_index', error=f'Error en los datos: {str(e)}'))
        except Exception as e:
            return redirect(url_for('transferencias_index', error=f'Error al crear transferencia: {str(e)}'))
    
    # GET: mostrar formulario
    bancos = financiero.obtener_bancos(activo=True)
    return render_template('financiero/transferencias/form.html',
                         transferencia=None,
                         bancos=bancos,
                         request=request)


@app.route("/financiero/transferencias/<int:id>/editar", methods=["GET", "POST"], endpoint="transferencia_editar")
@auth.login_required
@auth.permission_required('/financiero/transferencias')
def transferencia_editar(id):
    """Editar transferencia existente"""
    transferencia = financiero.obtener_transferencia_por_id(id)
    if not transferencia:
        return redirect(url_for('transferencias_index', error='Transferencia no encontrada'))
    
    if request.method == "POST":
        try:
            fecha_str = request.form.get('fecha', '').strip()
            banco_origen_id = request.form.get('banco_origen_id', type=int)
            banco_destino_id = request.form.get('banco_destino_id', type=int)
            monto_str = request.form.get('monto', '').strip()
            descripcion = request.form.get('descripcion', '').strip() or None
            
            if not fecha_str:
                return redirect(url_for('transferencias_index', error='La fecha es obligatoria'))
            
            if not banco_origen_id:
                return redirect(url_for('transferencias_index', error='El banco de origen es obligatorio'))
            
            if not banco_destino_id:
                return redirect(url_for('transferencias_index', error='El banco de destino es obligatorio'))
            
            if banco_origen_id == banco_destino_id:
                return redirect(url_for('transferencias_index', error='El banco de origen y destino no pueden ser el mismo'))
            
            if not monto_str:
                return redirect(url_for('transferencias_index', error='El monto es obligatorio'))
            
            # Convertir monto (aceptar formato con punto o coma)
            # Si tiene coma, es formato español: eliminar puntos de miles y usar coma como decimal
            # Si tiene punto pero no coma, puede ser formato inglés (punto decimal) o español (punto de miles)
            if ',' in monto_str:
                # Formato español: eliminar puntos (miles) y reemplazar coma por punto
                monto = float(monto_str.replace('.', '').replace(',', '.'))
            elif '.' in monto_str:
                # Tiene punto pero no coma: verificar si es decimal o miles
                # Si tiene más de un punto o el punto está cerca del final, es separador de miles
                partes = monto_str.split('.')
                if len(partes) == 2 and len(partes[1]) <= 2:
                    # Un solo punto y máximo 2 dígitos después: es punto decimal (formato inglés)
                    monto = float(monto_str)
                else:
                    # Múltiples puntos o muchos dígitos después: son separadores de miles
                    monto = float(monto_str.replace('.', ''))
            else:
                # Solo números, sin separadores
                monto = float(monto_str)
            
            if monto <= 0:
                return redirect(url_for('transferencias_index', error='El monto debe ser mayor a 0'))
            
            # Convertir fecha
            fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
            
            financiero.actualizar_transferencia(id, fecha, banco_origen_id, banco_destino_id, monto, descripcion)
            
            return redirect(url_for('transferencias_index', mensaje='Transferencia actualizada correctamente'))
        except ValueError as e:
            return redirect(url_for('transferencias_index', error=f'Error en los datos: {str(e)}'))
        except Exception as e:
            return redirect(url_for('transferencias_index', error=f'Error al actualizar transferencia: {str(e)}'))
    
    # GET: mostrar formulario
    bancos = financiero.obtener_bancos(activo=True)
    return render_template('financiero/transferencias/form.html',
                         transferencia=transferencia,
                         bancos=bancos,
                         request=request)


@app.route("/financiero/transferencias/<int:id>/eliminar", methods=["POST"], endpoint="transferencia_eliminar")
@auth.login_required
@auth.permission_required('/financiero/transferencias')
def transferencia_eliminar(id):
    """Eliminar transferencia"""
    try:
        financiero.eliminar_transferencia(id)
        return redirect(url_for('transferencias_index', mensaje='Transferencia eliminada correctamente'))
    except Exception as e:
        return redirect(url_for('transferencias_index', error=f'Error al eliminar transferencia: {str(e)}'))
@auth.login_required
@auth.permission_required('/financiero/cuentas-a-pagar')
def cuentas_a_pagar_importar_csv():
    """Importar cuentas a pagar desde CSV (después de previsualización)"""
    try:
        # Obtener el contenido CSV de la sesión
        csv_content = session.get('csv_content_para_importar')
        if not csv_content:
            return redirect(url_for('cuentas_a_pagar_index', error='No hay datos para importar. Por favor, previsualice el archivo primero.'))
        
        cuentas_importadas, errores = financiero.importar_cuentas_a_pagar_csv(csv_content)
        
        # Limpiar la sesión
        session.pop('csv_content_para_importar', None)
        
        mensaje = f'Se importaron {len(cuentas_importadas)} cuenta(s) correctamente'
        if errores:
            mensaje += f'. Errores: {len(errores)}'
            # Guardar errores en sesión para mostrarlos
            session['errores_importacion'] = errores
        
        return redirect(url_for('cuentas_a_pagar_index', mensaje=mensaje))
    except Exception as e:
        return redirect(url_for('cuentas_a_pagar_index', error=f'Error al importar CSV: {str(e)}'))


if __name__ == "__main__":
    # App unificada
    app.run(host="127.0.0.1", port=5000, debug=True)


