"""
Módulo de autenticación y autorización
Maneja login, sesiones, y control de acceso basado en permisos
"""
from functools import wraps
from flask import session, redirect, url_for, request
import psycopg2
import psycopg2.extras
import hashlib
import os
from dotenv import load_dotenv

load_dotenv()

# Configuración de base de datos
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


def hash_password(password):
    """Genera un hash SHA-256 de la contraseña con salt"""
    salt = os.getenv("PASSWORD_SALT", "default_salt_change_in_production")
    return hashlib.sha256((password + salt).encode()).hexdigest()


def verificar_password(password, password_hash):
    """Verifica si la contraseña coincide con el hash"""
    return hash_password(password) == password_hash


def verificar_usuario_incompleto_por_email(username_or_email):
    """
    Verifica si existe un usuario con el username o email dado que no tiene registro completo
    Retorna el usuario si existe y está incompleto, None si no
    """
    try:
        conn, cur = conectar()
        try:
            # Buscar por username o email
            cur.execute("""
                SELECT id, email, registro_completo, username, password_hash
                FROM usuarios
                WHERE (username = %s OR email = %s) AND activo = TRUE 
                AND (registro_completo = FALSE OR username IS NULL OR password_hash IS NULL)
            """, (username_or_email, username_or_email))
            
            usuario = cur.fetchone()
            if usuario:
                return {
                    'id': usuario['id'],
                    'email': usuario['email']
                }
        finally:
            cur.close()
            conn.close()
    except Exception as e:
        print(f"Error en verificar_usuario_incompleto_por_email: {e}")
    
    return None


def login_user(username_or_email, password):
    """
    Intenta autenticar un usuario por username o email
    Retorna el usuario si es exitoso, None si falla
    Si el usuario existe pero no tiene registro completo, retorna {'incompleto': True, 'email': email}
    """
    try:
        conn, cur = conectar()
        try:
            # Buscar por username o email
            cur.execute("""
                SELECT id, username, password_hash, nombre_completo, email, es_admin, activo, registro_completo
                FROM usuarios
                WHERE (username = %s OR email = %s) AND activo = TRUE
            """, (username_or_email, username_or_email))
            
            usuario = cur.fetchone()
            
            if not usuario:
                return None
            
            # Si el usuario no tiene registro completo, retornar indicador
            if not usuario.get('registro_completo') or not usuario.get('username') or not usuario.get('password_hash'):
                return {
                    'incompleto': True,
                    'id': usuario['id'],
                    'email': usuario['email']
                }
            
            if verificar_password(password, usuario['password_hash']):
                # Actualizar último acceso
                cur.execute("""
                    UPDATE usuarios 
                    SET ultimo_acceso = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (usuario['id'],))
                conn.commit()
                
                return {
                    'id': usuario['id'],
                    'username': usuario['username'],
                    'nombre_completo': usuario['nombre_completo'],
                    'email': usuario['email'],
                    'es_admin': usuario['es_admin']
                }
        finally:
            cur.close()
            conn.close()
    except Exception as e:
        print(f"Error en login_user: {e}")
    
    return None


def verificar_username_disponible(username):
    """Verifica si un username está disponible"""
    try:
        conn, cur = conectar()
        try:
            cur.execute("""
                SELECT COUNT(*) as count
                FROM usuarios
                WHERE username = %s
            """, (username,))
            
            resultado = cur.fetchone()
            return resultado['count'] == 0
        finally:
            cur.close()
            conn.close()
    except Exception as e:
        print(f"Error en verificar_username_disponible: {e}")
        return False


def completar_registro(usuario_id, username, password, nombre_completo=None):
    """
    Completa el registro de un usuario que fue creado solo con email
    Retorna True si es exitoso, False si falla
    """
    try:
        conn, cur = conectar()
        try:
            # Verificar que el username no esté en uso
            if not verificar_username_disponible(username):
                return False
            
            password_hash = hash_password(password)
            
            cur.execute("""
                UPDATE usuarios 
                SET username = %s, 
                    password_hash = %s,
                    nombre_completo = %s,
                    registro_completo = TRUE
                WHERE id = %s AND registro_completo = FALSE
            """, (username, password_hash, nombre_completo, usuario_id))
            
            conn.commit()
            return cur.rowcount > 0
        finally:
            cur.close()
            conn.close()
    except Exception as e:
        print(f"Error en completar_registro: {e}")
        return False


def get_current_user():
    """Obtiene el usuario actual desde la sesión"""
    if 'user_id' in session:
        try:
            conn, cur = conectar()
            try:
                cur.execute("""
                    SELECT id, username, nombre_completo, email, es_admin, activo
                    FROM usuarios
                    WHERE id = %s AND activo = TRUE
                """, (session['user_id'],))
                
                usuario = cur.fetchone()
                if usuario:
                    return {
                        'id': usuario['id'],
                        'username': usuario['username'],
                        'nombre_completo': usuario['nombre_completo'],
                        'email': usuario['email'],
                        'es_admin': usuario['es_admin']
                    }
            finally:
                cur.close()
                conn.close()
        except Exception as e:
            print(f"Error en get_current_user: {e}")
    
    return None


def usuario_tiene_permiso(usuario_id, ruta):
    """
    Verifica si un usuario tiene permiso para acceder a una ruta
    Los administradores tienen acceso a todas las rutas
    """
    try:
        conn, cur = conectar()
        try:
            # Verificar si es admin
            cur.execute("SELECT es_admin FROM usuarios WHERE id = %s", (usuario_id,))
            usuario = cur.fetchone()
            if usuario and usuario['es_admin']:
                return True
            
            # Verificar permisos específicos
            cur.execute("""
                SELECT COUNT(*) as tiene_permiso
                FROM usuarios_permisos up
                INNER JOIN permisos_rutas pr ON up.permiso_ruta_id = pr.id
                WHERE up.usuario_id = %s 
                AND pr.ruta = %s 
                AND pr.activo = TRUE
            """, (usuario_id, ruta))
            
            resultado = cur.fetchone()
            return resultado and resultado['tiene_permiso'] > 0
        finally:
            cur.close()
            conn.close()
    except Exception as e:
        print(f"Error en usuario_tiene_permiso: {e}")
        return False


def login_required(f):
    """Decorador para requerir autenticación"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """Decorador para requerir que el usuario sea administrador"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login', next=request.url))
        
        usuario = get_current_user()
        if not usuario or not usuario.get('es_admin'):
            return redirect(url_for('menu', error='Acceso denegado. Se requieren permisos de administrador.'))
        
        return f(*args, **kwargs)
    return decorated_function


def permission_required(ruta):
    """
    Decorador para requerir un permiso específico
    Los administradores siempre tienen acceso
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('login', next=request.url))
            
            usuario = get_current_user()
            if not usuario:
                return redirect(url_for('login', next=request.url))
            
            # Los admins tienen acceso a todo
            if usuario.get('es_admin'):
                return f(*args, **kwargs)
            
            # Verificar permiso específico
            if not usuario_tiene_permiso(usuario['id'], ruta):
                return redirect(url_for('menu', error=f'No tienes permiso para acceder a esta ruta: {ruta}'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def crear_usuario(username, password, nombre_completo=None, email=None, es_admin=False):
    """
    Crea un nuevo usuario
    Retorna el ID del usuario creado o None si falla
    """
    try:
        conn, cur = conectar()
        try:
            password_hash = hash_password(password)
            # Si username y password están presentes, registro_completo debe ser TRUE
            registro_completo = True if username and password_hash else False
            
            cur.execute("""
                INSERT INTO usuarios (username, password_hash, nombre_completo, email, es_admin, registro_completo)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (username, password_hash, nombre_completo, email, es_admin, registro_completo))
            
            usuario_id = cur.fetchone()['id']
            conn.commit()
            return usuario_id
        finally:
            cur.close()
            conn.close()
    except Exception as e:
        print(f"Error al crear usuario: {e}")
        return None


def obtener_usuarios():
    """Obtiene la lista de todos los usuarios"""
    try:
        conn, cur = conectar()
        try:
            cur.execute("""
                SELECT id, username, nombre_completo, email, es_admin, activo, 
                       registro_completo, creado_en, ultimo_acceso
                FROM usuarios
                ORDER BY registro_completo DESC, username NULLS LAST, email
            """)
            return cur.fetchall()
        finally:
            cur.close()
            conn.close()
    except Exception as e:
        print(f"Error al obtener usuarios: {e}")
        return []


def obtener_permisos_rutas():
    """Obtiene la lista de todas las rutas con permisos"""
    try:
        conn, cur = conectar()
        try:
            cur.execute("""
                SELECT id, ruta, nombre, descripcion, activo
                FROM permisos_rutas
                ORDER BY nombre
            """)
            return cur.fetchall()
        finally:
            cur.close()
            conn.close()
    except Exception as e:
        print(f"Error al obtener permisos: {e}")
        return []


def obtener_permisos_usuario(usuario_id):
    """Obtiene los permisos asignados a un usuario"""
    try:
        conn, cur = conectar()
        try:
            cur.execute("""
                SELECT pr.id, pr.ruta, pr.nombre, pr.descripcion
                FROM permisos_rutas pr
                INNER JOIN usuarios_permisos up ON pr.id = up.permiso_ruta_id
                WHERE up.usuario_id = %s AND pr.activo = TRUE
                ORDER BY pr.nombre
            """, (usuario_id,))
            return cur.fetchall()
        finally:
            cur.close()
            conn.close()
    except Exception as e:
        print(f"Error al obtener permisos de usuario: {e}")
        return []


def asignar_permiso(usuario_id, permiso_ruta_id):
    """Asigna un permiso a un usuario"""
    try:
        conn, cur = conectar()
        try:
            cur.execute("""
                INSERT INTO usuarios_permisos (usuario_id, permiso_ruta_id)
                VALUES (%s, %s)
                ON CONFLICT (usuario_id, permiso_ruta_id) DO NOTHING
            """, (usuario_id, permiso_ruta_id))
            conn.commit()
            return True
        finally:
            cur.close()
            conn.close()
    except Exception as e:
        print(f"Error al asignar permiso: {e}")
        return False


def revocar_permiso(usuario_id, permiso_ruta_id):
    """Revoca un permiso de un usuario"""
    try:
        conn, cur = conectar()
        try:
            cur.execute("""
                DELETE FROM usuarios_permisos
                WHERE usuario_id = %s AND permiso_ruta_id = %s
            """, (usuario_id, permiso_ruta_id))
            conn.commit()
            return True
        finally:
            cur.close()
            conn.close()
    except Exception as e:
        print(f"Error al revocar permiso: {e}")
        return False

