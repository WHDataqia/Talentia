from flask import Flask, request, jsonify, send_from_directory, redirect, g
from flask_cors import CORS
from flask_compress import Compress
from flask_jwt_extended import JWTManager, jwt_required, get_jwt_identity, get_jwt, verify_jwt_in_request
from datetime import datetime, timedelta
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
import json
import os
import sys
import tempfile
import time
import threading
from functools import wraps
from dotenv import load_dotenv
import jwt as _jwt
import secrets
import string
import decimal as _decimal
from flask.json.provider import DefaultJSONProvider as _DefaultJSONProvider
from competencias_db import upgrade_db_with_acceso_codes, get_subordinados_directos, upgrade_evaluaciones_expandir_campos, upgrade_evaluaciones_fecha_hora
from rutas_competencias import registrar_rutas_competencias
from migrations import upgrade_empleados_agregar_cargo, upgrade_empleados_agregar_identificacion, upgrade_empleados_agregar_nivel_ocupacional, upgrade_empleados_agregar_items_kpi, upgrade_competencia_kpi
from actualizar_empleados import analizar_archivo_empleados, recargar_empleados_desde_excel, asignar_contrasenas_cedula_existentes
from auth import (
    hashear_contrasena, verificar_contrasena, autenticar_usuario,
    autenticar_empleado_por_cedula, generar_token_acceso,
    puede_ver_empleado, puede_evaluar_empleado, get_toda_jerarquia_subordinados,
    limpiar_sesion, registrar_sesion_atomico,
    validar_token_contra_bd
)

# Resolver directorio base de la app para modo desarrollo y binario compilado.
def _resolve_app_base_dir():
    override_dir = os.getenv('TALENTIA_STATIC_DIR', '').strip()
    if override_dir:
        return os.path.abspath(override_dir)

    # Cuando se ejecuta binario compilado (Nuitka/PyInstaller)
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)

    # Modo desarrollo: backend/app.py -> base en carpeta raíz del proyecto
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


APP_BASE_DIR = _resolve_app_base_dir()

# Cargar variables de entorno desde la raíz del proyecto o bundle compilado.
load_dotenv(dotenv_path=os.path.join(APP_BASE_DIR, '.env'))
load_dotenv()

class _TalentiaJSONProvider(_DefaultJSONProvider):
    """JSON provider que convierte tipos no serializables de PostgreSQL (Decimal, date, etc.)"""
    def default(self, o):
        if isinstance(o, _decimal.Decimal):
            return float(o)
        return super().default(o)

app = Flask(__name__, static_folder=APP_BASE_DIR, static_url_path='')
app.json_provider_class = _TalentiaJSONProvider
app.json = _TalentiaJSONProvider(app)
CORS(app)

# Comprimir respuestas gzip para mejor rendimiento con ngrok
Compress(app)

# Cache para recursos estáticos (mejora la velocidad entre navegación de páginas)
STATIC_CACHE_SECONDS = int(os.getenv('STATIC_CACHE_SECONDS', '3600'))
STATIC_CACHE_EXTENSIONS = {
    '.css', '.js', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico',
    '.webp', '.woff', '.woff2', '.ttf', '.eot', '.jfif', '.json'
}

# Configuración JWT
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'tu-clave-super-segura-cambiar-en-produccion-2024')
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=1)  # Sesión expira después de 1 hora de inactividad
jwt = JWTManager(app)

# Modo estricto de logout:
# - Producción: respuestas estrictas (401/500) para observabilidad y seguridad.
# - Pruebas/desarrollo: respuestas tolerantes para evitar ruido en test manual.
APP_ENV = os.getenv('APP_ENV', os.getenv('FLASK_ENV', 'development')).strip().lower()
LOGOUT_STRICT_MODE = os.getenv(
    'LOGOUT_STRICT_MODE',
    '1' if APP_ENV == 'production' else '0'
).strip().lower() in ('1', 'true', 'yes', 'on')

# Fase 1 de hardening: proteger endpoints sensibles sin forzar corte inmediato.
# En Linux/produccion activar: SECURITY_HARDENING=1
SECURITY_HARDENING = os.getenv('SECURITY_HARDENING', '0').strip().lower() in ('1', 'true', 'yes', 'on')


def jwt_required_if_hardening_enabled():
    """Exige JWT solo cuando SECURITY_HARDENING está activo."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if SECURITY_HARDENING:
                verify_jwt_in_request()
            return fn(*args, **kwargs)
        return wrapper
    return decorator

# Cache corto para evitar consultar BD en cada request autenticado.
# Se limpia por usuario durante login/logout para mantener coherencia de sesiones.
TOKEN_VALIDATION_CACHE_SECONDS = max(0, int(os.getenv('TOKEN_VALIDATION_CACHE_SECONDS', '8')))
_token_validation_cache = {}
_token_validation_cache_lock = threading.Lock()

def _get_cached_token_validation(token_string):
    if TOKEN_VALIDATION_CACHE_SECONDS <= 0:
        return None

    now = time.monotonic()
    with _token_validation_cache_lock:
        entry = _token_validation_cache.get(token_string)
        if not entry:
            return None

        if entry['expires_at'] <= now:
            _token_validation_cache.pop(token_string, None)
            return None

        return entry

def _set_cached_token_validation(token_string, usuario_id):
    if TOKEN_VALIDATION_CACHE_SECONDS <= 0:
        return

    with _token_validation_cache_lock:
        _token_validation_cache[token_string] = {
            'usuario_id': int(usuario_id),
            'expires_at': time.monotonic() + TOKEN_VALIDATION_CACHE_SECONDS
        }

def _evict_user_cached_tokens(usuario_id):
    if TOKEN_VALIDATION_CACHE_SECONDS <= 0:
        return

    usuario_id_int = int(usuario_id)
    with _token_validation_cache_lock:
        tokens_a_borrar = [
            token for token, entry in _token_validation_cache.items()
            if entry.get('usuario_id') == usuario_id_int
        ]
        for token in tokens_a_borrar:
            _token_validation_cache.pop(token, None)

# MIDDLEWARE: Validar que tokens revocados sean rechazados
@app.before_request
def validar_sesion_activa():
    """
    Middleware que valida la sesión para TODOS los endpoints protegidos
    Rechaza tokens que ya fueron revocados por un nuevo login desde otro dispositivo
    """
    # Solo validar endpoints de API
    if not request.path.startswith('/api/'):
        return
    
    # Excluir endpoints públicos
    endpoints_publicos = {
        '/api/login', '/api/auth/empleado', '/api/test', '/api/logout', '/api/health'
    }
    
    if request.path in endpoints_publicos:
        return
    
    # Si hay token, validar que sea válido
    token_header = request.headers.get('Authorization', '')
    if not token_header or not token_header.startswith('Bearer '):
        return  # @jwt_required() se encargará de validar la presencia
    
    try:
        token_string = token_header.split(' ')[1]

        cached = _get_cached_token_validation(token_string)
        if cached:
            return

        from flask_jwt_extended import decode_token
        
        # Intentar decodificar el token (esto validará firma, expiry, etc)
        payload = decode_token(token_string)
        usuario_id = int(payload['sub'])
        
        # Validar que el token corresponda a la sesión actualmente registrada en BD
        conn = get_db_connection()
        try:
            es_valido, mensaje = validar_token_contra_bd(conn, usuario_id, token_string)
        finally:
            conn.close()
        
        if not es_valido:
            # Token revocado por un nuevo login desde otro dispositivo
            from flask import abort
            abort(401)

        _set_cached_token_validation(token_string, usuario_id)
    
    except Exception:
        # Si hay error decodificando o validando, dejar que @jwt_required() lo maneje
        # Solo rechazamos si es un caso de "token revocado"
        pass

# Configuración de la base de datos
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://postgres@localhost:5432/talentia_db')
DB_POOL_MINCONN = max(1, int(os.getenv('DB_POOL_MINCONN', '5')))
DB_POOL_MAXCONN = max(DB_POOL_MINCONN, int(os.getenv('DB_POOL_MAXCONN', '30')))
DB_CONNECT_TIMEOUT = max(2, int(os.getenv('DB_CONNECT_TIMEOUT', '10')))

_db_pool = None
_db_pool_lock = threading.Lock()


def _init_db_pool():
    global _db_pool
    with _db_pool_lock:
        if _db_pool is None:
            _db_pool = pool.ThreadedConnectionPool(
                minconn=DB_POOL_MINCONN,
                maxconn=DB_POOL_MAXCONN,
                dsn=DATABASE_URL,
                connect_timeout=DB_CONNECT_TIMEOUT
            )
            print(f"[DB] Pool PostgreSQL inicializado ({DB_POOL_MINCONN}-{DB_POOL_MAXCONN})")
    return _db_pool

class PostgreSQLConnectionWrapper:
    """Wrapper para estandarizar operaciones sobre conexión psycopg2."""
    def __init__(self, raw_conn, source_pool=None):
        self._conn = raw_conn
        self._pool = source_pool
        self._closed = False
    
    def execute(self, sql, params=()):
        """Ejecutar una query y devolver un cursor compatible"""
        try:
            cursor = self._conn.cursor()
            # Convertir ? a %s si es necesario
            sql = sql.replace('?', '%s')
            cursor.execute(sql, params if params else ())
            return cursor
        except Exception as e:
            print(f"[ERROR] SQL error: {sql} - {str(e)}")
            raise
    
    def cursor(self):
        """Devolver un cursor de la conexión interna"""
        return self._conn.cursor()
    
    def commit(self):
        """Commit de la transacción"""
        return self._conn.commit()
    
    def rollback(self):
        """Rollback de la transacción"""
        return self._conn.rollback()
    
    def close(self):
        """Cerrar la conexión o devolverla al pool"""
        if self._closed:
            return
        if self._pool:
            self._pool.putconn(self._conn)
        else:
            self._conn.close()
        self._closed = True
    
    def set_session(self, **kwargs):
        """Pasar configuración de sesión a la conexión interna"""
        return self._conn.set_session(**kwargs)

def get_db_connection():
    """Crear conexión a la base de datos PostgreSQL"""
    try:
        current_pool = _init_db_pool()
        raw_conn = current_pool.getconn()
        # Garantizar estado limpio entre requests
        raw_conn.rollback()
        # Usar RealDictCursor para obtener resultados como diccionarios
        raw_conn.cursor_factory = RealDictCursor
        conn = PostgreSQLConnectionWrapper(raw_conn, source_pool=current_pool)
        # Registrar en g para devolución automática al pool al terminar el request
        try:
            if not hasattr(g, '_db_connections'):
                g._db_connections = []
            g._db_connections.append(conn)
        except RuntimeError:
            pass  # Fuera del contexto de request (ej: init_db al arrancar)
        return conn
    except psycopg2.Error as e:
        print(f"[ERROR] No se pudo conectar a PostgreSQL: {str(e)}")
        raise


@app.teardown_request
def _devolver_conexiones_al_pool(exception=None):
    """Garantizar que TODAS las conexiones abiertas se devuelvan al pool al terminar cada request,
    incluso si hubo una excepción no manejada o un conn.close() olvidado."""
    for conn in getattr(g, '_db_connections', []):
        if not conn._closed:
            try:
                conn.close()
            except Exception:
                pass

def obtener_usuario_id_del_token(request_obj):
    """Decodificar el token JWT manualmente desde el header"""
    auth_header = request_obj.headers.get('Authorization', '')
    
    if not auth_header.startswith('Bearer '):
        return None
    
    token = auth_header.split(' ')[1]
    
    try:
        # Decodificar usando jwt.decode() con la llave secreta
        secret_key = os.getenv('JWT_SECRET_KEY', 'tu-clave-super-segura-cambiar-en-produccion-2024')
        payload = _jwt.decode(token, secret_key, algorithms=['HS256'])
        usuario_id = payload.get('sub')
        return usuario_id
    except Exception:
        return None

def init_db():
    """Inicializar la base de datos con las tablas necesarias"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Verificar si las tablas existen
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_name = 'empleados'
        """)
        tabla_existe = cursor.fetchone()
        
        if not tabla_existe:
            print("[WARN] Tabla empleados no encontrada. Ejecutar: python backend/temp/create_talentia_db.py")
            conn.close()
            return
        
        # Ejecutar migraciones necesarias
        upgrade_empleados_agregar_identificacion(conn)
        upgrade_empleados_agregar_cargo(conn)
        upgrade_empleados_agregar_nivel_ocupacional(conn)
        upgrade_empleados_agregar_items_kpi(conn)
        upgrade_competencia_kpi(conn)
        upgrade_evaluaciones_expandir_campos(conn)  # Expandir campos varchar(255) a TEXT
        upgrade_evaluaciones_fecha_hora(conn)  # Guardar timestamp para auditoría
        
        # Crear índices para optimizar performance
        crear_indices_optimizacion(conn)
        
        conn.close()
        print("[OK] Base de datos verificada")
    except Exception as e:
        print(f"[ERROR] Error inicializando BD: {str(e)}")

def crear_indices_optimizacion(conn):
    """Crear índices para optimizar queries de performance"""
    try:
        cursor = conn.cursor()
        
        # Índices para jerarquía de empleados
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_empleados_jefe_id ON empleados(jefe_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_empleados_activo ON empleados(activo)')
        
        # Índices para evaluaciones
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_evaluaciones_empleado_id ON evaluaciones(empleado_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_evaluaciones_periodo ON evaluaciones(periodo)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_evaluaciones_empleado_periodo ON evaluaciones(empleado_id, periodo)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_evaluaciones_autoevaluacion ON evaluaciones(autoevaluacion)')
        
        # Índices para competencias (si la tabla existe)
        cursor.execute("""
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'evaluaciones_competencia'
        """)
        if cursor.fetchone():
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_evaluaciones_competencia_eval_id ON evaluaciones_competencia(evaluacion_id)')
        
        conn.commit()
        print("[OK] Índices de optimización creados/verificados")
    except Exception as e:
        print(f"[WARN] Error creando índices: {str(e)}")
        conn.rollback()

def upgrade_db_campos_autenticacion(conn):
    """Agregar campos de contraseña y rol si no existen"""
    try:
        cursor = conn.cursor()
        
        # Verificar si la columna contrasena_hash existe
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'empleados' AND column_name = 'contrasena_hash'
        """)
        has_contrasena = cursor.fetchone()
        
        if not has_contrasena:
            # Agregar columna de contraseña con valor por defecto
            cursor.execute('ALTER TABLE empleados ADD COLUMN contrasena_hash TEXT')
            # Hashear una contraseña por defecto (cambiar después en el login)
            contrasena_default = hashear_contrasena('Temporal123!')
            cursor.execute('UPDATE empleados SET contrasena_hash = %s', (contrasena_default,))
            conn.commit()
            print("[OK] Campo contrasena_hash agregado a empleados")
        
        # Verificar si la columna rol existe
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'empleados' AND column_name = 'rol'
        """)
        has_rol = cursor.fetchone()
        
        if not has_rol:
            cursor.execute('ALTER TABLE empleados ADD COLUMN rol TEXT DEFAULT \'empleado\'')
            conn.commit()
            print("[OK] Campo rol agregado a empleados")
        
    except Exception as e:
        print(f"Nota: BD podría ya tener los campos de autenticación: {str(e)}")

def _insert_sample_data(cursor, conn):
    """Insertar datos de ejemplo (solo se ejecuta la primera vez)"""
    # Los datos de ejemplo se manejan desde init_db_script.py
    # Esta función se mantiene para compatibilidad pero no inserta nada
    pass

# Inicializar BD al arrancar
init_db()

# ==================== RUTAS DE AUTENTICACIÓN ====================

@app.route('/api/test', methods=['GET'])
def test():
    """Endpoint de test simple"""
    return jsonify({'message': 'Test OK'}), 200

@app.route('/api/test-jwt', methods=['GET'])
@jwt_required()
def test_jwt():
    """Endpoint de test con JWT - ahora valida token contra BD"""
    usuario_id = get_jwt_identity()
    
    # Validar token contra BD para rechazar sesiones anteriores
    token_header = request.headers.get('Authorization', '')
    token_string = token_header.split(' ')[1] if ' ' in token_header else None
    
    if token_string:
        conn = get_db_connection()
        es_valido, mensaje = validar_token_contra_bd(conn, int(usuario_id), token_string)
        conn.close()
        
        if not es_valido:
            return jsonify({'error': mensaje}), 401
    
    return jsonify({'message': f'JWT OK, user={usuario_id}'}), 200

@app.route('/api/login', methods=['POST'])
def login():
    """
    Endpoint de login
    Espera: { "email": "usuario@example.com", "contrasena": "password" }
    """
    try:
        data = request.json
        email = data.get('email')
        contrasena = data.get('contrasena')
        
        if not email or not contrasena:
            return jsonify({'error': 'Email y contraseña requeridos'}), 400
        
        conn = get_db_connection()
        usuario, error = autenticar_usuario(conn, email, contrasena)
        
        if error:
            conn.close()
            return jsonify({'error': error}), 401
        
        # Validar que solo admin y jefe puedan ingresar
        rol_usuario = usuario.get('rol', 'empleado')
        if rol_usuario not in ['admin', 'jefe']:
            conn.close()
            return jsonify({'error': 'Acceso denegado. Solo administradores y jefes pueden ingresar al sistema.'}), 403
        
        # Generar token
        token = generar_token_acceso(usuario['id'], usuario.get('correo_corporativo', ''), rol_usuario)
        
        # REGISTRAR LA NUEVA SESIÓN (registrar_sesion_atomico previene race conditions)
        # Esta función automáticamente limpia sesiones anteriores y registra la nueva de forma atómica
        exito_registro, msg_registro = registrar_sesion_atomico(conn, usuario['id'], token)
        if not exito_registro:
            conn.close()
            return jsonify({'error': f'Error al registrar sesión: {msg_registro}'}), 500

        _evict_user_cached_tokens(usuario['id'])
        
        conn.close()
        
        return jsonify({
            'token': token,
            'usuario': {
                'id': usuario['id'],
                'nombres_completos': usuario.get('nombres_completos', ''),
                'correo_corporativo': usuario.get('correo_corporativo', ''),
                'cargo_id': usuario.get('cargo_id'),
                'centro_costo_id': usuario.get('centro_costo_id'),
                'rol': usuario.get('rol', 'empleado')
            }
        }), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/auth/empleado', methods=['POST'])
def login_empleado():
    """
    Endpoint de login PARA EMPLEADOS (autoevaluación)
    Acepta cédula + contraseña (no requiere rol admin/jefe)
    Espera: { "cedula": "123456789", "contrasena": "password" }
    """
    try:
        data = request.json
        cedula = data.get('cedula', '').strip()
        contrasena = data.get('contrasena', '').strip()
        
        if not cedula or not contrasena:
            return jsonify({'error': 'Cédula y contraseña requeridos'}), 400
        
        conn = get_db_connection()
        usuario, error = autenticar_empleado_por_cedula(conn, cedula, contrasena)
        
        if error:
            conn.close()
            return jsonify({'error': error}), 401
        
        # Generar token (cualquier empleado puede acceder)
        rol_usuario = usuario.get('rol', 'empleado')
        token = generar_token_acceso(usuario['id'], usuario.get('correo_corporativo', ''), rol_usuario)
        
        # REGISTRAR LA NUEVA SESIÓN (registrar_sesion_atomico previene race conditions)
        exito_registro, msg_registro = registrar_sesion_atomico(conn, usuario['id'], token)
        if not exito_registro:
            conn.close()
            return jsonify({'error': f'Error al registrar sesión: {msg_registro}'}), 500

        _evict_user_cached_tokens(usuario['id'])
        
        conn.close()
        
        return jsonify({
            'token': token,
            'usuario': {
                'id': usuario['id'],
                'cedula': usuario.get('cedula', ''),
                'nombres_completos': usuario.get('nombres_completos', ''),
                'correo_corporativo': usuario.get('correo_corporativo', ''),
                'correo_personal': usuario.get('correo_personal', ''),
                'cargo_id': usuario.get('cargo_id'),
                'rol': rol_usuario
            }
        }), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/logout', methods=['POST'])
def logout():
    """
    Endpoint de logout - Cierra la sesión activa del usuario
    Limpia los campos de sesión en la BD
    Funciona con o sin JWT (para logout automático al cerrar pestaña)
    """
    conn = None
    try:
        # Intentar obtener usuario_id del JWT si está disponible.
        usuario_id = None
        try:
            identity = get_jwt_identity()
            if identity is not None:
                usuario_id = int(identity)
        except Exception:
            # Si no hay JWT/contexto válido, continuar con body/header.
            pass

        # Si no hay usuario_id por JWT, intentar del body (tolerante a JSON inválido/vacío).
        if not usuario_id:
            data = request.get_json(silent=True) or {}
            body_usuario_id = data.get('usuario_id')
            if body_usuario_id not in (None, ''):
                try:
                    usuario_id = int(body_usuario_id)
                except (TypeError, ValueError):
                    usuario_id = None

        # Si aún no hay usuario_id, intentar del auth header.
        if not usuario_id:
            auth_header = request.headers.get('Authorization', '')
            if auth_header.startswith('Bearer '):
                try:
                    token = auth_header.split('Bearer ', 1)[1].strip()
                    from flask_jwt_extended import decode_token
                    decoded = decode_token(token)
                    sub = decoded.get('sub')
                    if sub is not None:
                        usuario_id = int(sub)
                except Exception:
                    usuario_id = None

        # Si no hay identidad: estricto en producción, tolerante en pruebas.
        if not usuario_id:
            if LOGOUT_STRICT_MODE:
                return jsonify({
                    'error': 'No se pudo identificar al usuario para logout',
                    'success': False
                }), 401
            return jsonify({
                'message': 'Logout recibido sin sesión activa identificable',
                'success': True
            }), 200

        conn = get_db_connection()
        exito, mensaje = limpiar_sesion(conn, usuario_id)
        _evict_user_cached_tokens(usuario_id)

        if not exito:
            if LOGOUT_STRICT_MODE:
                return jsonify({
                    'error': f'Error al cerrar sesión: {mensaje}',
                    'success': False
                }), 500
            # En pruebas, evitar 500 por doble logout o estado inconsistente.
            return jsonify({
                'message': f'Logout procesado con advertencia: {mensaje}',
                'success': True
            }), 200

        return jsonify({
            'message': 'Sesión cerrada correctamente',
            'success': True
        }), 200

    except Exception as e:
        print(f"[WARN] Error controlado en /api/logout: {e}")
        if LOGOUT_STRICT_MODE:
            return jsonify({
                'error': f'Error al procesar logout: {str(e)}',
                'success': False
            }), 500
        return jsonify({
            'message': 'Logout procesado con advertencia',
            'success': True
        }), 200
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass

@app.route('/api/cambiar-contrasena', methods=['POST'])
@jwt_required()
def cambiar_contrasena():
    """
    Cambiar la contraseña del usuario autenticado
    Espera: { "contrasena_actual": "old", "contrasena_nueva": "new" }
    """
    try:
        usuario_id = int(get_jwt_identity())  # Convertir a int
        data = request.json
        contrasena_actual = data.get('contrasena_actual')
        contrasena_nueva = data.get('contrasena_nueva')
        
        if not contrasena_actual or not contrasena_nueva:
            return jsonify({'error': 'Se requieren ambas contraseñas'}), 400
        
        conn = get_db_connection()
        usuario = conn.execute('SELECT * FROM empleados WHERE id = %s', (usuario_id,)).fetchone()
        
        if not usuario:
            return jsonify({'error': 'Usuario no encontrado'}), 404
        
        # Verificar contraseña actual
        if not verificar_contrasena(contrasena_actual, usuario['contrasena_hash']):
            return jsonify({'error': 'Contraseña actual incorrecta'}), 401
        
        # Hashear y guardar nueva contraseña
        nueva_hash = hashear_contrasena(contrasena_nueva)
        conn.execute('UPDATE empleados SET contrasena_hash = %s WHERE id = %s', (nueva_hash, usuario_id))
        conn.commit()
        conn.close()
        
        return jsonify({'message': 'Contraseña actualizada exitosamente'}), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/usuarios/<int:usuario_id>/cambiar-contrasena', methods=['PUT'])
@jwt_required()
def cambiar_contrasena_usuario(usuario_id):
    """
    Cambiar la contraseña de un usuario (SOLO ADMIN)
    Espera: { "contrasena_nueva": "new_password" }
    """
    try:
        admin_id = int(get_jwt_identity())  # Convertir a int
        data = request.json
        contrasena_nueva = data.get('contrasena_nueva')
        
        if not contrasena_nueva:
            return jsonify({'error': 'Se requiere la nueva contraseña'}), 400
        
        conn = get_db_connection()
        
        # Verificar que el usuario autenticado es admin
        admin = conn.execute('SELECT rol FROM empleados WHERE id = %s', (admin_id,)).fetchone()
        if not admin or admin['rol'] != 'admin':
            conn.close()
            return jsonify({'error': 'No tienes permisos para cambiar la contraseña de otros usuarios'}), 403
        
        # Verificar que el usuario a cambiar existe
        usuario = conn.execute('SELECT * FROM empleados WHERE id = %s', (usuario_id,)).fetchone()
        if not usuario:
            conn.close()
            return jsonify({'error': 'Usuario no encontrado'}), 404
        
        # Hashear y guardar nueva contraseña
        nueva_hash = hashear_contrasena(contrasena_nueva)
        conn.execute('UPDATE empleados SET contrasena_hash = %s WHERE id = %s', (nueva_hash, usuario_id))
        conn.commit()
        conn.close()
        
        nombre_usuario = usuario['nombres_completos'] if usuario['nombres_completos'] else 'usuario'
        
        return jsonify({
            'message': f'Contraseña actualizada para {nombre_usuario}',
            'usuario_id': usuario_id,
            'usuario_nombre': usuario['nombres_completos'] or ''
        }), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/mi-perfil', methods=['GET'])
@jwt_required()
def mi_perfil():
    """Obtener el perfil del usuario autenticado"""
    try:
        usuario_id = int(get_jwt_identity())
        conn = get_db_connection()
        usuario = conn.execute('SELECT * FROM empleados WHERE id = %s', (usuario_id,)).fetchone()
        conn.close()
        
        if usuario:
            resultado = dict(usuario)
            # No enviar el hash de la contraseña
            if 'contrasena_hash' in resultado:
                del resultado['contrasena_hash']
            return jsonify(resultado)
        
        return jsonify({'error': 'Usuario no encontrado'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/cambiar-rol/<int:empleado_id>', methods=['PUT'])
@jwt_required()
def cambiar_rol_empleado(empleado_id):
    """
    Cambiar el rol de un empleado (solo administrador)
    Espera: { "rol": "admin" | "jefe" | "empleado" }
    """
    try:
        usuario_id = int(get_jwt_identity())
        claims = get_jwt()
        rol_usuario = claims.get('rol', 'empleado')
        
        # Solo admin puede cambiar roles
        if rol_usuario != 'admin':
            return jsonify({'error': 'Solo administradores pueden cambiar roles'}), 403
        
        data = request.json
        nuevo_rol = data.get('rol', 'empleado')
        
        # Validar que sea un rol válido
        if nuevo_rol not in ['admin', 'jefe', 'empleado']:
            return jsonify({'error': 'Rol inválido. Debe ser: admin, jefe o empleado'}), 400
        
        # No permitir que el último admin pierda sus privilegios
        if empleado_id == usuario_id and nuevo_rol != 'admin':
            return jsonify({'error': 'No puedes quitarte a ti mismo los privilegios de admin'}), 400
        
        conn = get_db_connection()
        
        # Verificar que el empleado existe
        empleado = conn.execute(
            'SELECT id, nombres_completos, correo_corporativo, rol FROM empleados WHERE id = %s',
            (empleado_id,)
        ).fetchone()
        
        if not empleado:
            conn.close()
            return jsonify({'error': 'Empleado no encontrado'}), 404
        
        # Actualizar rol
        conn.execute(
            'UPDATE empleados SET rol = %s WHERE id = %s',
            (nuevo_rol, empleado_id)
        )
        conn.commit()
        conn.close()
        
        return jsonify({
            'message': 'Rol actualizado exitosamente',
            'empleado': {
                'id': empleado['id'],
                'nombres_completos': empleado.get('nombres_completos', ''),
                'correo_corporativo': empleado.get('correo_corporativo', ''),
                'rol_anterior': empleado['rol'],
                'rol_nuevo': nuevo_rol
            }
        }), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== RUTAS DE TABLAS MAESTRAS ====================

# EMPRESAS
@app.route('/api/empresas', methods=['GET'])
@jwt_required()
def get_empresas():
    """Obtener todas las empresas"""
    try:
        conn = get_db_connection()
        empresas = conn.execute('SELECT * FROM empresas WHERE activo = true ORDER BY razon_social').fetchall()
        conn.close()
        return jsonify([dict(empresa) for empresa in empresas])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/empresas/<int:id>', methods=['GET'])
@jwt_required()
def get_empresa(id):
    """Obtener una empresa por ID"""
    try:
        conn = get_db_connection()
        empresa = conn.execute('SELECT * FROM empresas WHERE id = %s', (id,)).fetchone()
        conn.close()
        if empresa:
            return jsonify(dict(empresa))
        return jsonify({'error': 'Empresa no encontrada'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/empresas', methods=['POST'])
@jwt_required()
def crear_empresa():
    """Crear una nueva empresa (solo admin)"""
    try:
        claims = get_jwt()
        rol_usuario = claims.get('rol', 'empleado')
        
        if rol_usuario != 'admin':
            return jsonify({'error': 'Solo administradores pueden crear empresas'}), 403
        
        data = request.json
        razon_social = data.get('razon_social', '').strip()
        nit = data.get('nit', '').strip()
        ciudad = data.get('ciudad', '').strip()
        
        if not razon_social or not nit:
            return jsonify({'error': 'Razón social y NIT son requeridos'}), 400
        
        conn = get_db_connection()
        
        # Verificar si el NIT ya existe
        existe = conn.execute('SELECT id FROM empresas WHERE nit = %s', (nit,)).fetchone()
        if existe:
            conn.close()
            return jsonify({'error': 'Ya existe una empresa con ese NIT'}), 400
        
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO empresas (razon_social, nit, ciudad) VALUES (%s, %s, %s) RETURNING id',
            (razon_social, nit, ciudad)
        )
        empresa_id = cursor.fetchone()['id']
        conn.commit()
        conn.close()
        
        return jsonify({'id': empresa_id, 'message': 'Empresa creada exitosamente'}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/empresas/<int:id>', methods=['PUT'])
@jwt_required()
def actualizar_empresa(id):
    """Actualizar una empresa (solo admin)"""
    try:
        claims = get_jwt()
        rol_usuario = claims.get('rol', 'empleado')
        
        if rol_usuario != 'admin':
            return jsonify({'error': 'Solo administradores pueden actualizar empresas'}), 403
        
        data = request.json
        razon_social = data.get('razon_social', '').strip()
        nit = data.get('nit', '').strip()
        ciudad = data.get('ciudad', '').strip()
        
        if not razon_social or not nit:
            return jsonify({'error': 'Razón social y NIT son requeridos'}), 400
        
        conn = get_db_connection()
        
        # Verificar si la empresa existe
        empresa = conn.execute('SELECT * FROM empresas WHERE id = %s', (id,)).fetchone()
        if not empresa:
            conn.close()
            return jsonify({'error': 'Empresa no encontrada'}), 404
        
        # Verificar si el NIT ya existe en otra empresa
        existe = conn.execute('SELECT id FROM empresas WHERE nit = %s AND id != %s', (nit, id)).fetchone()
        if existe:
            conn.close()
            return jsonify({'error': 'Ya existe otra empresa con ese NIT'}), 400
        
        conn.execute(
            'UPDATE empresas SET razon_social = %s, nit = %s, ciudad = %s WHERE id = %s',
            (razon_social, nit, ciudad, id)
        )
        conn.commit()
        conn.close()
        
        return jsonify({'message': 'Empresa actualizada exitosamente'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/empresas/<int:id>', methods=['DELETE'])
@jwt_required()
def eliminar_empresa(id):
    """Eliminar (desactivar) una empresa (solo admin)"""
    try:
        claims = get_jwt()
        rol_usuario = claims.get('rol', 'empleado')
        
        if rol_usuario != 'admin':
            return jsonify({'error': 'Solo administradores pueden eliminar empresas'}), 403
        
        conn = get_db_connection()
        empresa = conn.execute('SELECT * FROM empresas WHERE id = %s', (id,)).fetchone()
        
        if not empresa:
            conn.close()
            return jsonify({'error': 'Empresa no encontrada'}), 404
        
        # Desactivar en lugar de eliminar
        conn.execute('UPDATE empresas SET activo = false WHERE id = %s', (id,))
        conn.commit()
        conn.close()
        
        return jsonify({'message': 'Empresa desactivada exitosamente'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# CARGOS
@app.route('/api/cargos', methods=['GET'])
@jwt_required()
def get_cargos():
    """Obtener todos los cargos"""
    try:
        conn = get_db_connection()
        cargos = conn.execute('SELECT * FROM cargos WHERE activo = true ORDER BY nombre').fetchall()
        conn.close()
        return jsonify([dict(cargo) for cargo in cargos])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/cargos', methods=['POST'])
@jwt_required()
def crear_cargo():
    """Crear un nuevo cargo (solo admin)"""
    try:
        claims = get_jwt()
        rol_usuario = claims.get('rol', 'empleado')
        
        if rol_usuario != 'admin':
            return jsonify({'error': 'Solo administradores pueden crear cargos'}), 403
        
        data = request.json
        nombre = data.get('nombre', '').strip()
        descripcion = data.get('descripcion', '').strip()
        
        if not nombre:
            return jsonify({'error': 'El nombre del cargo es requerido'}), 400
        
        conn = get_db_connection()
        
        # Verificar si el cargo ya existe
        existe = conn.execute('SELECT id FROM cargos WHERE nombre = %s', (nombre,)).fetchone()
        if existe:
            conn.close()
            return jsonify({'error': 'Ya existe un cargo con ese nombre'}), 400
        
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO cargos (nombre, descripcion) VALUES (%s, %s) RETURNING id',
            (nombre, descripcion)
        )
        cargo_id = cursor.fetchone()['id']
        conn.commit()
        conn.close()
        
        return jsonify({'id': cargo_id, 'message': 'Cargo creado exitosamente'}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/cargos/<int:id>', methods=['GET'])
@jwt_required()
def get_cargo(id):
    """Obtener un cargo por ID"""
    try:
        conn = get_db_connection()
        cargo = conn.execute('SELECT * FROM cargos WHERE id = %s', (id,)).fetchone()
        conn.close()
        if cargo:
            return jsonify(dict(cargo))
        return jsonify({'error': 'Cargo no encontrado'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/cargos/<int:id>', methods=['PUT'])
@jwt_required()
def actualizar_cargo(id):
    """Actualizar un cargo (solo admin)"""
    try:
        claims = get_jwt()
        rol_usuario = claims.get('rol', 'empleado')
        
        if rol_usuario != 'admin':
            return jsonify({'error': 'Solo administradores pueden actualizar cargos'}), 403
        
        data = request.json
        nombre = data.get('nombre', '').strip()
        descripcion = data.get('descripcion', '').strip()
        
        if not nombre:
            return jsonify({'error': 'El nombre del cargo es requerido'}), 400
        
        conn = get_db_connection()
        
        # Verificar si el cargo existe
        cargo = conn.execute('SELECT * FROM cargos WHERE id = %s', (id,)).fetchone()
        if not cargo:
            conn.close()
            return jsonify({'error': 'Cargo no encontrado'}), 404
        
        # Verificar si el nombre ya existe en otro cargo
        existe = conn.execute('SELECT id FROM cargos WHERE nombre = %s AND id != %s', (nombre, id)).fetchone()
        if existe:
            conn.close()
            return jsonify({'error': 'Ya existe otro cargo con ese nombre'}), 400
        
        conn.execute(
            'UPDATE cargos SET nombre = %s, descripcion = %s WHERE id = %s',
            (nombre, descripcion, id)
        )
        conn.commit()
        conn.close()
        
        return jsonify({'message': 'Cargo actualizado exitosamente'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/cargos/<int:id>', methods=['DELETE'])
@jwt_required()
def eliminar_cargo(id):
    """Eliminar (desactivar) un cargo (solo admin)"""
    try:
        claims = get_jwt()
        rol_usuario = claims.get('rol', 'empleado')
        
        if rol_usuario != 'admin':
            return jsonify({'error': 'Solo administradores pueden eliminar cargos'}), 403
        
        conn = get_db_connection()
        cargo = conn.execute('SELECT * FROM cargos WHERE id = %s', (id,)).fetchone()
        
        if not cargo:
            conn.close()
            return jsonify({'error': 'Cargo no encontrado'}), 404
        
        conn.execute('UPDATE cargos SET activo = false WHERE id = %s', (id,))
        conn.commit()
        conn.close()
        
        return jsonify({'message': 'Cargo desactivado exitosamente'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# CENTROS DE COSTO
@app.route('/api/centros-costo', methods=['GET'])
@jwt_required()
def get_centros_costo():
    """Obtener todos los centros de costo"""
    try:
        conn = get_db_connection()
        centros = conn.execute('SELECT * FROM centros_costo WHERE activo = true ORDER BY nombre').fetchall()
        conn.close()
        return jsonify([dict(centro) for centro in centros])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/centros-costo', methods=['POST'])
@jwt_required()
def crear_centro_costo():
    """Crear un nuevo centro de costo (solo admin)"""
    try:
        claims = get_jwt()
        rol_usuario = claims.get('rol', 'empleado')
        
        if rol_usuario != 'admin':
            return jsonify({'error': 'Solo administradores pueden crear centros de costo'}), 403
        
        data = request.json
        nombre = data.get('nombre', '').strip()
        descripcion = data.get('descripcion', '').strip()
        
        if not nombre:
            return jsonify({'error': 'El nombre del centro de costo es requerido'}), 400
        
        conn = get_db_connection()
        
        # Verificar si el centro de costo ya existe
        existe = conn.execute('SELECT id FROM centros_costo WHERE nombre = %s', (nombre,)).fetchone()
        if existe:
            conn.close()
            return jsonify({'error': 'Ya existe un centro de costo con ese nombre'}), 400
        
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO centros_costo (nombre, descripcion) VALUES (%s, %s) RETURNING id',
            (nombre, descripcion)
        )
        centro_id = cursor.fetchone()['id']
        conn.commit()
        conn.close()
        
        return jsonify({'id': centro_id, 'message': 'Centro de costo creado exitosamente'}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/centros-costo/<int:id>', methods=['GET'])
@jwt_required()
def get_centro_costo(id):
    """Obtener un centro de costo por ID"""
    try:
        conn = get_db_connection()
        centro = conn.execute('SELECT * FROM centros_costo WHERE id = %s', (id,)).fetchone()
        conn.close()
        if centro:
            return jsonify(dict(centro))
        return jsonify({'error': 'Centro de costo no encontrado'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/centros-costo/<int:id>', methods=['PUT'])
@jwt_required()
def actualizar_centro_costo(id):
    """Actualizar un centro de costo (solo admin)"""
    try:
        claims = get_jwt()
        rol_usuario = claims.get('rol', 'empleado')
        
        if rol_usuario != 'admin':
            return jsonify({'error': 'Solo administradores pueden actualizar centros de costo'}), 403
        
        data = request.json
        nombre = data.get('nombre', '').strip()
        descripcion = data.get('descripcion', '').strip()
        
        if not nombre:
            return jsonify({'error': 'El nombre del centro de costo es requerido'}), 400
        
        conn = get_db_connection()
        
        # Verificar si el centro de costo existe
        centro = conn.execute('SELECT * FROM centros_costo WHERE id = %s', (id,)).fetchone()
        if not centro:
            conn.close()
            return jsonify({'error': 'Centro de costo no encontrado'}), 404
        
        # Verificar si el nombre ya existe en otro centro
        existe = conn.execute('SELECT id FROM centros_costo WHERE nombre = %s AND id != %s', (nombre, id)).fetchone()
        if existe:
            conn.close()
            return jsonify({'error': 'Ya existe otro centro de costo con ese nombre'}), 400
        
        conn.execute(
            'UPDATE centros_costo SET nombre = %s, descripcion = %s WHERE id = %s',
            (nombre, descripcion, id)
        )
        conn.commit()
        conn.close()
        
        return jsonify({'message': 'Centro de costo actualizado exitosamente'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/centros-costo/<int:id>', methods=['DELETE'])
@jwt_required()
def eliminar_centro_costo(id):
    """Eliminar (desactivar) un centro de costo (solo admin)"""
    try:
        claims = get_jwt()
        rol_usuario = claims.get('rol', 'empleado')
        
        if rol_usuario != 'admin':
            return jsonify({'error': 'Solo administradores pueden eliminar centros de costo'}), 403
        
        conn = get_db_connection()
        centro = conn.execute('SELECT * FROM centros_costo WHERE id = %s', (id,)).fetchone()
        
        if not centro:
            conn.close()
            return jsonify({'error': 'Centro de costo no encontrado'}), 404
        
        conn.execute('UPDATE centros_costo SET activo = false WHERE id = %s', (id,))
        conn.commit()
        conn.close()
        
        return jsonify({'message': 'Centro de costo desactivado exitosamente'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== RUTAS DE EMPLEADOS ====================

@app.route('/api/empleados', methods=['GET'])
@jwt_required()
def get_empleados():
    """Obtener empleados (solo subordinados del usuario actual)
    
    Parámetro opcional:
    - directo=true: obtiene solo subordinados directos (para evaluación)
    - directo=false o no especificado: obtiene toda la jerarquía (para reportes)
    """
    try:
        usuario_id = int(get_jwt_identity())
        # Obtener parámetro directo
        solo_directos = request.args.get('directo', 'false').lower() == 'true'
        
        conn = get_db_connection()
        
        # Obtener usuario actual
        usuario_actual = conn.execute('SELECT * FROM empleados WHERE id = %s', (usuario_id,)).fetchone()
        
        if not usuario_actual:
            conn.close()
            return jsonify({'error': 'Usuario no encontrado'}), 404
        
        # Si es admin, obtener todos
        if usuario_actual['rol'] == 'admin':
            empleados = conn.execute('''
                SELECT e.*, 
                       e.nombres_completos,
                       j.nombres_completos as jefe_nombre,
                       j.id as jefe_id_real,
                       emp.razon_social as empresa_nombre,
                       emp.nit as empresa_nit,
                       c.nombre as cargo_nombre,
                       cc.nombre as centro_costo_nombre
                FROM empleados e
                LEFT JOIN empleados j ON e.jefe_id = j.id
                LEFT JOIN empresas emp ON e.empresa_id = emp.id
                LEFT JOIN cargos c ON e.cargo_id = c.id
                LEFT JOIN centros_costo cc ON e.centro_costo_id = cc.id
                WHERE e.activo = true 
                ORDER BY e.nombres_completos
            ''').fetchall()
        else:
            # Si es jefe, obtener subordinados
            if solo_directos:
                # SOLO subordinados DIRECTOS (para evaluación)
                subordinados = get_subordinados_directos(conn, usuario_id)
            else:
                # Toda la jerarquía (para reportes)
                subordinados = get_toda_jerarquia_subordinados(conn, usuario_id)
            
            subordinados_ids = [s['id'] for s in subordinados]
            
            # Si no tiene subordinados, devolver lista vacía
            if not subordinados_ids:
                conn.close()
                return jsonify([])
            
            placeholders = ','.join('?' * len(subordinados_ids))
            empleados = conn.execute(f'''
                SELECT e.*, 
                       e.nombres_completos,
                       j.nombres_completos as jefe_nombre,
                       j.id as jefe_id_real,
                       emp.razon_social as empresa_nombre,
                       emp.nit as empresa_nit,
                       c.nombre as cargo_nombre,
                       cc.nombre as centro_costo_nombre
                FROM empleados e
                LEFT JOIN empleados j ON e.jefe_id = j.id
                LEFT JOIN empresas emp ON e.empresa_id = emp.id
                LEFT JOIN cargos c ON e.cargo_id = c.id
                LEFT JOIN centros_costo cc ON e.centro_costo_id = cc.id
                WHERE e.activo = true AND e.id IN ({placeholders})
                ORDER BY e.nombres_completos
            ''', subordinados_ids).fetchall()
        
        conn.close()
        
        # No incluir contraseñas
        resultado = []
        for emp in empleados:
            emp_dict = dict(emp)
            if 'contrasena_hash' in emp_dict:
                del emp_dict['contrasena_hash']
            cargo_nombre = emp_dict.get('cargo_nombre') or emp_dict.get('cargo')
            centro_nombre = emp_dict.get('centro_costo_nombre') or emp_dict.get('centro_costo')
            if cargo_nombre:
                emp_dict['cargo'] = cargo_nombre
            if centro_nombre:
                emp_dict['centro_costo'] = centro_nombre
            resultado.append(emp_dict)
        
        return jsonify(resultado)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/empleados/<int:id>', methods=['GET'])
@jwt_required()
def get_empleado(id):
    """Obtener un empleado específico (con verificación de permisos)"""
    try:
        usuario_id = int(get_jwt_identity())
        
        conn = get_db_connection()
        
        # Verificar permisos
        puede_ver, mensaje = puede_ver_empleado(conn, usuario_id, id)
        
        if not puede_ver:
            conn.close()
            return jsonify({'error': mensaje}), 403
        
        # Obtener empleado con información de cargo y centro de costo
        empleado = conn.execute('''
            SELECT e.*,
                   c.nombre as cargo_nombre,
                   cc.nombre as centro_costo_nombre,
                   emp.razon_social as empresa_nombre,
                   j.nombres_completos as jefe_nombre
            FROM empleados e
            LEFT JOIN cargos c ON e.cargo_id = c.id
            LEFT JOIN centros_costo cc ON e.centro_costo_id = cc.id
            LEFT JOIN empresas emp ON e.empresa_id = emp.id
            LEFT JOIN empleados j ON e.jefe_id = j.id
            WHERE e.id = ?
        ''', (id,)).fetchone()
        conn.close()
        
        if empleado:
            emp_dict = dict(empleado)
            # No incluir contraseña
            if 'contrasena_hash' in emp_dict:
                del emp_dict['contrasena_hash']
            cargo_nombre = emp_dict.get('cargo_nombre') or emp_dict.get('cargo')
            centro_nombre = emp_dict.get('centro_costo_nombre') or emp_dict.get('centro_costo')
            if cargo_nombre:
                emp_dict['cargo'] = cargo_nombre
            if centro_nombre:
                emp_dict['centro_costo'] = centro_nombre
            return jsonify(emp_dict)
        
        return jsonify({'error': 'Empleado no encontrado'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/empleados/identificacion/<identificacion>', methods=['GET'])
@jwt_required_if_hardening_enabled()
def get_empleado_por_identificacion(identificacion):
    """Obtener un empleado por identificacion"""
    try:
        identificacion = (identificacion or '').strip()
        identificacion_limpia = (
            identificacion.replace(' ', '')
            .replace('.', '')
            .replace('-', '')
        )
        conn = get_db_connection()
        empleado = conn.execute(
            '''
                SELECT * FROM empleados
                WHERE activo = true
                AND (
                    identificacion = ?
                    OR REPLACE(REPLACE(REPLACE(identificacion, ' ', ''), '.', ''), '-', '') = ?
                )
            ''',
            (identificacion, identificacion_limpia)
        ).fetchone()
        conn.close()

        if empleado:
            return jsonify(dict(empleado))
        return jsonify({'error': 'Empleado no encontrado'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/empleados/excel/analizar', methods=['POST'])
@jwt_required()
def analizar_excel_empleados():
    """Analizar archivo Excel de empleados antes de recargar datos (solo admin)."""
    temp_path = None
    try:
        usuario_id = int(get_jwt_identity())
        conn = get_db_connection()
        usuario_actual = conn.execute('SELECT rol FROM empleados WHERE id = %s', (usuario_id,)).fetchone()
        conn.close()

        if not usuario_actual or usuario_actual['rol'] != 'admin':
            return jsonify({'error': 'Solo administradores pueden analizar archivos Excel'}), 403

        archivo = request.files.get('archivo')
        if not archivo:
            return jsonify({'error': 'Debes seleccionar un archivo Excel'}), 400

        nombre = (archivo.filename or '').lower()
        if not nombre.endswith(('.xlsx', '.xls')):
            return jsonify({'error': 'Formato inválido. Solo se permiten archivos .xlsx o .xls'}), 400

        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(nombre)[1] or '.xlsx') as temp_file:
            archivo.save(temp_file.name)
            temp_path = temp_file.name

        reporte = analizar_archivo_empleados(temp_path)
        return jsonify(reporte), 200
    except Exception as e:
        return jsonify({'error': f'No se pudo analizar el archivo: {str(e)}'}), 500
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)


@app.route('/api/empleados/excel/recargar', methods=['POST'])
@jwt_required()
def recargar_excel_empleados():
    """Recargar empleados desde archivo Excel (solo admin)."""
    temp_path = None
    try:
        usuario_id = int(get_jwt_identity())
        conn = get_db_connection()
        usuario_actual = conn.execute('SELECT rol FROM empleados WHERE id = %s', (usuario_id,)).fetchone()
        conn.close()

        if not usuario_actual or usuario_actual['rol'] != 'admin':
            return jsonify({'error': 'Solo administradores pueden recargar empleados desde Excel'}), 403

        archivo = request.files.get('archivo')
        if not archivo:
            return jsonify({'error': 'Debes seleccionar un archivo Excel'}), 400

        nombre = (archivo.filename or '').lower()
        if not nombre.endswith(('.xlsx', '.xls')):
            return jsonify({'error': 'Formato inválido. Solo se permiten archivos .xlsx o .xls'}), 400

        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(nombre)[1] or '.xlsx') as temp_file:
            archivo.save(temp_file.name)
            temp_path = temp_file.name

        resultado = recargar_empleados_desde_excel(temp_path)
        status = 200 if resultado.get('success') else 400
        return jsonify(resultado), status
    except Exception as e:
        return jsonify({'error': f'No se pudo recargar desde Excel: {str(e)}'}), 500
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)


@app.route('/api/empleados/asignar-contrasenas', methods=['POST'])
@jwt_required()
def asignar_contrasenas_empleados():
    """Asignar contraseña (cédula) a todos los empleados sin contraseña (solo admin)."""
    try:
        usuario_id = int(get_jwt_identity())
        conn = get_db_connection()
        usuario_actual = conn.execute('SELECT rol FROM empleados WHERE id = %s', (usuario_id,)).fetchone()
        conn.close()

        if not usuario_actual or usuario_actual['rol'] != 'admin':
            return jsonify({'error': 'Solo administradores pueden asignar contraseñas'}), 403

        resultado = asignar_contrasenas_cedula_existentes()
        status = 200 if resultado.get('success') else 400
        return jsonify(resultado), status
    except Exception as e:
        return jsonify({'error': f'Error al asignar contraseñas: {str(e)}'}), 500


# ==================== RUTAS DE PLAN DE FORMACIÓN ====================

@app.route('/api/evaluaciones/<int:evaluacion_id>/plan-formacion', methods=['GET'])
@jwt_required_if_hardening_enabled()
def get_plan_formacion(evaluacion_id):
    """Obtener plan de formación de una evaluación"""
    try:
        conn = get_db_connection()
        planes = conn.execute(
            'SELECT * FROM plan_formacion WHERE evaluacion_id = %s ORDER BY porcentaje DESC',
            (evaluacion_id,)
        ).fetchall()
        conn.close()
        
        return jsonify([dict(plan) for plan in planes])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/evaluaciones/<int:evaluacion_id>/plan-formacion', methods=['POST'])
@jwt_required_if_hardening_enabled()
def save_plan_formacion(evaluacion_id):
    """Guardar o actualizar plan de formación"""
    conn = None
    try:
        data = request.json
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Validar que la evaluación existe y obtener empleado_id
        cursor.execute('SELECT id, empleado_id FROM evaluaciones WHERE id = %s', (evaluacion_id,))
        evaluacion = cursor.fetchone()
        if not evaluacion:
            if conn:
                conn.close()
            return jsonify({'error': 'Evaluación no encontrada'}), 404
        
        empleado_id = evaluacion['empleado_id']
        
        # Actualizar o insertar cada plan de formación individualmente
        for plan in data:
            oportunidad = plan.get('oportunidad_desarrollo', '')
            tipo_formacion = plan.get('tipo_formacion')
            
            if oportunidad.strip():  # Solo guardar si hay contenido
                # Verificar si ya existe un registro para este tipo de formación
                cursor.execute('''
                    SELECT id FROM plan_formacion 
                    WHERE evaluacion_id = %s AND tipo_formacion = %s
                ''', (evaluacion_id, tipo_formacion))
                existing = cursor.fetchone()
                
                if existing:
                    # Actualizar existente
                    cursor.execute('''
                        UPDATE plan_formacion 
                        SET oportunidad_desarrollo = %s,
                            brecha_competencia = %s,
                            accion_formacion = %s,
                            porcentaje = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                    ''', (oportunidad, oportunidad, oportunidad, plan.get('porcentaje'), existing['id']))
                else:
                    # Insertar nuevo
                    cursor.execute('''
                        INSERT INTO plan_formacion 
                        (evaluacion_id, empleado_id, tipo_formacion, porcentaje, oportunidad_desarrollo, 
                         brecha_competencia, accion_formacion, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ''', (
                        evaluacion_id,
                        empleado_id,
                        tipo_formacion,
                        plan.get('porcentaje'),
                        oportunidad,
                        oportunidad,
                        oportunidad
                    ))
            else:
                # Si el campo está vacío, eliminar el registro si existe
                cursor.execute('''
                    DELETE FROM plan_formacion 
                    WHERE evaluacion_id = %s AND tipo_formacion = %s
                ''', (evaluacion_id, tipo_formacion))
        
        conn.commit()
        conn.close()
        
        return jsonify({'message': 'Plan de formación guardado exitosamente'}), 201
    except Exception as e:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
        return jsonify({'error': str(e)}), 500

@app.route('/api/empleados', methods=['POST'])
@jwt_required()
def create_empleado():
    """Crear un nuevo empleado (solo administrador)"""
    try:
        usuario_id = int(get_jwt_identity())
        conn = get_db_connection()
        
        # Obtener usuario actual
        usuario_actual = conn.execute('SELECT * FROM empleados WHERE id = %s', (usuario_id,)).fetchone()
        
        # Solo admin puede crear empleados
        if usuario_actual['rol'] != 'admin':
            conn.close()
            return jsonify({'error': 'Solo administradores pueden crear empleados'}), 403
        
        data = request.json
        cursor = conn.cursor()

        cedula = (data.get('cedula') or '').strip()
        if not cedula:
            conn.close()
            return jsonify({'error': 'La cédula es requerida'}), 400
        
        # Validar que el jefe existe si se proporciona
        jefe_id = data.get('jefe_id')
        if jefe_id:
            cursor.execute('SELECT id FROM empleados WHERE id = %s', (jefe_id,))
            jefe = cursor.fetchone()
            if not jefe:
                conn.close()
                return jsonify({'error': 'El jefe especificado no existe'}), 400
        
        # Hashear contraseña inicial:
        # - si llega contraseña explícita, usarla
        # - si no llega, usar la cédula para no requerir procesos adicionales
        contrasena_temporal = (data.get('contrasena') or '').strip() or cedula
        contrasena_hash = hashear_contrasena(contrasena_temporal)
        
        aplica_kpi = 1 if data.get('aplica_kpi') else 0
        kpi_item_1 = (data.get('kpi_item_1') or '').strip()
        kpi_item_2 = (data.get('kpi_item_2') or '').strip()
        kpi_item_3 = (data.get('kpi_item_3') or '').strip()

        if aplica_kpi and (not kpi_item_1 or not kpi_item_2 or not kpi_item_3):
            conn.close()
            return jsonify({'error': 'Debe diligenciar los 3 ítems KPI cuando aplica KPI'}), 400

        cursor.execute('''
            INSERT INTO empleados (
                cedula, nombres_completos, correo_personal, correo_corporativo, celular,
                empresa_id, cargo_id, centro_costo_id, fecha_ingreso, jefe_id,
                contrasena_hash, rol, activo, aplica_kpi, nivel_ocupacional,
                kpi_item_1, kpi_item_2, kpi_item_3
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, true, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (
            cedula,
            data.get('nombres_completos'),
            data.get('correo_personal'),
            data.get('correo_corporativo'),
            data.get('celular'),
            data.get('empresa_id'),
            data.get('cargo_id'),
            data.get('centro_costo_id'),
            data.get('fecha_ingreso'),
            jefe_id,
            contrasena_hash,
            data.get('rol', 'empleado'),
            aplica_kpi,
            data.get('nivel_ocupacional', ''),
            kpi_item_1 if aplica_kpi else '',
            kpi_item_2 if aplica_kpi else '',
            kpi_item_3 if aplica_kpi else ''
        ))

        row = cursor.fetchone()
        empleado_id = row['id'] if isinstance(row, dict) else row[0]
        conn.commit()
        conn.close()
        
        return jsonify({'id': empleado_id, 'message': 'Empleado creado exitosamente'}), 201
    except psycopg2.IntegrityError:
        return jsonify({'error': 'El email ya existe'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/empleados/<int:id>', methods=['PUT'])
@jwt_required()
def update_empleado(id):
    """Actualizar un empleado (solo administrador)"""
    try:
        usuario_id = int(get_jwt_identity())
        conn = get_db_connection()
        
        # Obtener usuario actual
        usuario_actual = conn.execute('SELECT * FROM empleados WHERE id = %s', (usuario_id,)).fetchone()
        
        # Solo admin puede actualizar
        if usuario_actual['rol'] != 'admin':
            conn.close()
            return jsonify({'error': 'Solo administradores pueden actualizar empleados'}), 403
        
        data = request.json
        
        # Validar que el jefe existe si se proporciona
        jefe_id = data.get('jefe_id')
        if jefe_id:
            jefe = conn.execute('SELECT id FROM empleados WHERE id = %s', (jefe_id,)).fetchone()
            if not jefe:
                conn.close()
                return jsonify({'error': 'El jefe especificado no existe'}), 400
        
        aplica_kpi = 1 if data.get('aplica_kpi') else 0
        kpi_item_1 = (data.get('kpi_item_1') or '').strip()
        kpi_item_2 = (data.get('kpi_item_2') or '').strip()
        kpi_item_3 = (data.get('kpi_item_3') or '').strip()

        if aplica_kpi and (not kpi_item_1 or not kpi_item_2 or not kpi_item_3):
            conn.close()
            return jsonify({'error': 'Debe diligenciar los 3 ítems KPI cuando aplica KPI'}), 400

        nueva_cedula = data.get('cedula')

        # Si la cédula cambió, sincronizar identificacion y resetear contraseña
        empleado_previo = conn.execute('SELECT cedula FROM empleados WHERE id = %s', (id,)).fetchone()
        cedula_cambio = empleado_previo and nueva_cedula and empleado_previo['cedula'] != nueva_cedula

        conn.execute('''
            UPDATE empleados 
            SET cedula = %s, nombres_completos = %s, correo_personal = %s, correo_corporativo = %s,
                celular = %s, empresa_id = %s, cargo_id = %s, centro_costo_id = %s,
                jefe_id = %s, fecha_ingreso = %s, rol = %s, aplica_kpi = %s, nivel_ocupacional = %s,
                kpi_item_1 = %s, kpi_item_2 = %s, kpi_item_3 = %s,
                identificacion = %s
            WHERE id = %s
        ''', (
            nueva_cedula,
            data.get('nombres_completos'),
            data.get('correo_personal'),
            data.get('correo_corporativo'),
            data.get('celular'),
            data.get('empresa_id'),
            data.get('cargo_id'),
            data.get('centro_costo_id'),
            jefe_id,
            data.get('fecha_ingreso'),
            data.get('rol', 'empleado'),
            aplica_kpi,
            data.get('nivel_ocupacional', ''),
            kpi_item_1 if aplica_kpi else '',
            kpi_item_2 if aplica_kpi else '',
            kpi_item_3 if aplica_kpi else '',
            nueva_cedula,
            id
        ))

        # Si la cédula cambió, resetear contraseña a la nueva cédula para que pueda ingresar
        if cedula_cambio:
            conn.execute(
                'UPDATE empleados SET contrasena_hash = %s WHERE id = %s',
                (hashear_contrasena(nueva_cedula), id)
            )
        
        conn.commit()
        conn.close()
        
        msg = 'Empleado actualizado exitosamente'
        if cedula_cambio:
            msg += '. La cédula cambió: la contraseña fue reseteada a la nueva cédula.'
        return jsonify({'message': msg})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/empleados/<int:id>/reset-password', methods=['POST'])
@jwt_required()
def reset_password_empleado(id):
    """Resetear la contraseña de un empleado a su cédula (solo administrador)"""
    try:
        usuario_id = int(get_jwt_identity())
        conn = get_db_connection()

        usuario_actual = conn.execute('SELECT * FROM empleados WHERE id = %s', (usuario_id,)).fetchone()
        if usuario_actual['rol'] != 'admin':
            conn.close()
            return jsonify({'error': 'Solo administradores pueden resetear contraseñas'}), 403

        empleado = conn.execute('SELECT id, cedula, nombres_completos FROM empleados WHERE id = %s', (id,)).fetchone()
        if not empleado:
            conn.close()
            return jsonify({'error': 'Empleado no encontrado'}), 404

        cedula = empleado['cedula']
        if not cedula:
            conn.close()
            return jsonify({'error': 'El empleado no tiene cédula asignada'}), 400

        nuevo_hash = hashear_contrasena(cedula)
        conn.execute('UPDATE empleados SET contrasena_hash = %s WHERE id = %s', (nuevo_hash, id))
        conn.commit()
        conn.close()

        return jsonify({'message': f'Contraseña reseteada a la cédula para {empleado["nombres_completos"]}'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/empleados/<int:id>', methods=['DELETE'])
@jwt_required()
def delete_empleado(id):
    """Desactivar un empleado (solo administrador)"""
    try:
        usuario_id = int(get_jwt_identity())
        conn = get_db_connection()
        
        # Obtener usuario actual
        usuario_actual = conn.execute('SELECT * FROM empleados WHERE id = %s', (usuario_id,)).fetchone()
        
        # Solo admin puede eliminar
        if usuario_actual['rol'] != 'admin':
            conn.close()
            return jsonify({'error': 'Solo administradores pueden eliminar empleados'}), 403
        
        conn.execute('UPDATE empleados SET activo = false WHERE id = %s', (id,))
        conn.commit()
        conn.close()
        
        return jsonify({'message': 'Empleado desactivado exitosamente'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== RUTAS DE EVALUACIONES ====================

@app.route('/api/evaluaciones', methods=['GET'])
@jwt_required()
def get_evaluaciones():
    """Obtener evaluaciones (solo del usuario y sus subordinados)"""
    try:
        usuario_id = int(get_jwt_identity())
        conn = get_db_connection()
        
        # Obtener usuario actual
        usuario_actual = conn.execute('SELECT * FROM empleados WHERE id = %s', (usuario_id,)).fetchone()
        
        if not usuario_actual:
            conn.close()
            return jsonify({'error': 'Usuario no encontrado'}), 404
        
        # Si es admin, obtener todas
        if usuario_actual['rol'] == 'admin':
            evaluaciones = conn.execute('''
                SELECT e.*, emp.nombres_completos, 
                       c.nombre as cargo, cc.nombre as centro_costo,
                       evaluador.nombres_completos as nombre_evaluador
                FROM evaluaciones e
                JOIN empleados emp ON e.empleado_id = emp.id
                LEFT JOIN cargos c ON emp.cargo_id = c.id
                LEFT JOIN centros_costo cc ON emp.centro_costo_id = cc.id
                LEFT JOIN empleados evaluador ON e.evaluador_id = evaluador.id
                ORDER BY e.fecha_evaluacion DESC
            ''').fetchall()
        elif usuario_actual['rol'] == 'empleado':
            # Empleados solo ven SUS PROPIAS evaluaciones y autoevaluaciones
            evaluaciones = conn.execute('''
                SELECT e.*, emp.nombres_completos,
                       c.nombre as cargo, cc.nombre as centro_costo,
                       evaluador.nombres_completos as nombre_evaluador
                FROM evaluaciones e
                JOIN empleados emp ON e.empleado_id = emp.id
                LEFT JOIN cargos c ON emp.cargo_id = c.id
                LEFT JOIN centros_costo cc ON emp.centro_costo_id = cc.id
                LEFT JOIN empleados evaluador ON e.evaluador_id = evaluador.id
                WHERE e.empleado_id = ?
                ORDER BY e.fecha_evaluacion DESC
            ''', (usuario_id,)).fetchall()
        else:
            # Jefes: Obtener evaluaciones del usuario y sus subordinados
            subordinados = get_toda_jerarquia_subordinados(conn, usuario_id)
            subordinados_ids = [s['id'] for s in subordinados]
            subordinados_ids.append(usuario_id)
            
            placeholders = ','.join('?' * len(subordinados_ids))
            evaluaciones = conn.execute(f'''
                SELECT e.*, emp.nombres_completos,
                       c.nombre as cargo, cc.nombre as centro_costo,
                       evaluador.nombres_completos as nombre_evaluador
                FROM evaluaciones e
                JOIN empleados emp ON e.empleado_id = emp.id
                LEFT JOIN cargos c ON emp.cargo_id = c.id
                LEFT JOIN centros_costo cc ON emp.centro_costo_id = cc.id
                LEFT JOIN empleados evaluador ON e.evaluador_id = evaluador.id
                WHERE e.empleado_id IN ({placeholders})
                ORDER BY e.fecha_evaluacion DESC
            ''', subordinados_ids).fetchall()
        
        conn.close()
        return jsonify([dict(ev) for ev in evaluaciones])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/evaluaciones/empleado/<int:empleado_id>', methods=['GET'])
@jwt_required()
def get_evaluaciones_empleado(empleado_id):
    """Obtener evaluaciones de un empleado específico"""
    try:
        usuario_id = int(get_jwt_identity())
        conn = get_db_connection()
        
        # Verificar permisos
        puede_ver, mensaje = puede_ver_empleado(conn, usuario_id, empleado_id)
        
        if not puede_ver:
            conn.close()
            return jsonify({'error': mensaje}), 403
        
        evaluaciones = conn.execute('''
            SELECT e.*, evaluador.nombres_completos as nombre_evaluador
            FROM evaluaciones e
            LEFT JOIN empleados evaluador ON e.evaluador_id = evaluador.id
            WHERE e.empleado_id = ?
            ORDER BY e.fecha_evaluacion DESC
        ''', (empleado_id,)).fetchall()
        conn.close()
        
        return jsonify([dict(ev) for ev in evaluaciones])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/evaluaciones/<int:id>', methods=['GET'])
@jwt_required()
def get_evaluacion(id):
    """Obtener una evaluación completa"""
    try:
        usuario_id = int(get_jwt_identity())
        conn = get_db_connection()
        
        # Obtener evaluación
        evaluacion = conn.execute('''
            SELECT e.*, emp.nombres_completos, emp.cedula,
                   emp.aplica_kpi, emp.kpi_item_1, emp.kpi_item_2, emp.kpi_item_3,
                   c.nombre as cargo, cc.nombre as centro_costo,
                   evaluador.nombres_completos as nombre_evaluador,
                   evaluador.cedula as cedula_evaluador
            FROM evaluaciones e
            JOIN empleados emp ON e.empleado_id = emp.id
            LEFT JOIN cargos c ON emp.cargo_id = c.id
            LEFT JOIN centros_costo cc ON emp.centro_costo_id = cc.id
            LEFT JOIN empleados evaluador ON e.evaluador_id = evaluador.id
            WHERE e.id = ?
        ''', (id,)).fetchone()
        
        if not evaluacion:
            conn.close()
            return jsonify({'error': 'Evaluación no encontrada'}), 404
        
        # Verificar permisos
        puede_ver, mensaje = puede_ver_empleado(conn, usuario_id, evaluacion['empleado_id'])
        
        if not puede_ver:
            conn.close()
            return jsonify({'error': mensaje}), 403
        
        # Obtener competencias (nuevo modelo) - deduplicar por nombre canónico
        competencias = conn.execute('''
            SELECT DISTINCT ON (UPPER(REGEXP_REPLACE(c.nombre, '^\\s*\\d+\\.\\s*', ''))) c.id as competencia_id, c.nombre as competencia, ec.puntuacion_descriptor as puntuacion, ec.observaciones
            FROM evaluaciones_competencia ec
            JOIN competencias c ON ec.competencia_id = c.id
            WHERE ec.evaluacion_id = %s
            ORDER BY UPPER(REGEXP_REPLACE(c.nombre, '^\\s*\\d+\\.\\s*', '')), ec.id DESC
        ''', (id,)).fetchall()

        # Si no hay datos en el nuevo modelo, usar el modelo anterior
        if not competencias:
            competencias = conn.execute('''
                SELECT DISTINCT ON (UPPER(REGEXP_REPLACE(competencia, '^\\s*\\d+\\.\\s*', '')))
                       NULL as competencia_id, competencia, puntuacion, observaciones
                FROM competencias_evaluadas
                WHERE evaluacion_id = ?
                ORDER BY UPPER(REGEXP_REPLACE(competencia, '^\\s*\\d+\\.\\s*', '')), id DESC
            ''', (id,)).fetchall()
        
        conn.close()
        
        result = dict(evaluacion)
        comps_list = []
        for comp in competencias:
            d = dict(comp)
            # Asegurar que puntuacion sea siempre numérico (puede venir como string de PG)
            try:
                d['puntuacion'] = float(d['puntuacion']) if d['puntuacion'] is not None else 0.0
            except (TypeError, ValueError):
                d['puntuacion'] = 0.0
            comps_list.append(d)
        result['competencias'] = comps_list
        
        # NUEVO: Detectar si hay KPI evaluado en competencia 7
        # Buscar competencia 7 (METAS DEL CARGO / KPIs)
        tiene_kpi_evaluado = False
        kpi_detalle = []
        for comp in result['competencias']:
            if comp.get('competencia_id') == 7 or 'METAS DEL CARGO' in (comp.get('competencia') or '').upper():
                tiene_kpi_evaluado = True

                # Si observaciones viene como JSON, extraer detalle KPI individual.
                observaciones_raw = comp.get('observaciones')
                if isinstance(observaciones_raw, str) and observaciones_raw.strip().startswith('{'):
                    try:
                        obs_json = json.loads(observaciones_raw)
                        if isinstance(obs_json, dict):
                            detalle = obs_json.get('kpi_detalle')
                            if isinstance(detalle, list):
                                kpi_detalle = detalle
                            comp['observaciones'] = obs_json.get('comentario', '')
                    except Exception:
                        pass
                break
        
        # Retornar si tiene KPI evaluado (ya sea desde tabla empleados o desde evaluacion)
        result['aplica_kpi'] = tiene_kpi_evaluado or (result.get('aplica_kpi') in [1, True])
        
        # Si se encuentran en empleados, mantenerlos; sino poner None
        if 'kpi_item_1' not in result or result['kpi_item_1'] is None:
            result['kpi_item_1'] = None
        if 'kpi_item_2' not in result or result['kpi_item_2'] is None:
            result['kpi_item_2'] = None
        if 'kpi_item_3' not in result or result['kpi_item_3'] is None:
            result['kpi_item_3'] = None

        result['kpi_detalle'] = kpi_detalle
        
        return jsonify(result)
    except Exception as e:
        import traceback
        print(f"Error en get_evaluacion: {str(e)}")
        print(traceback.format_exc())
        return jsonify({'error': f'Error al cargar evaluación: {str(e)}'}), 500

@app.route('/api/evaluaciones/comparativo/<int:empleado_id>/<periodo>', methods=['GET'])
@jwt_required()
def get_evaluaciones_comparativo(empleado_id, periodo):
    """Obtener evaluación y autoevaluación juntas para un período (informe consolidado)"""
    try:
        usuario_id = int(get_jwt_identity())
        conn = get_db_connection()
        
        # Verificar permisos
        puede_ver, mensaje = puede_ver_empleado(conn, usuario_id, empleado_id)
        if not puede_ver:
            conn.close()
            return jsonify({'error': mensaje}), 403
        
        # Obtener datos del empleado
        empleado = conn.execute('''
            SELECT emp.*, c.nombre as cargo_nombre
            FROM empleados emp
            LEFT JOIN cargos c ON emp.cargo_id = c.id
            WHERE emp.id = ?
        ''', (empleado_id,)).fetchone()
        if not empleado:
            conn.close()
            return jsonify({'error': 'Empleado no encontrado'}), 404

        evaluacion_id_param = request.args.get('evaluacion_id', type=int)
        autoevaluacion_id_param = request.args.get('autoevaluacion_id', type=int)
        
        # Obtener EVALUACIÓN (hecha por jefe/admin)
        if evaluacion_id_param:
            evaluacion = conn.execute('''
                SELECT e.*, evaluador.nombres_completos as nombre_evaluador
                FROM evaluaciones e
                LEFT JOIN empleados evaluador ON e.evaluador_id = evaluador.id
                WHERE e.id = ? AND e.empleado_id = ? AND e.periodo = ? AND e.autoevaluacion = false
                LIMIT 1
            ''', (evaluacion_id_param, empleado_id, periodo)).fetchone()
        else:
            evaluacion = conn.execute('''
                SELECT e.*, evaluador.nombres_completos as nombre_evaluador
                FROM evaluaciones e
                LEFT JOIN empleados evaluador ON e.evaluador_id = evaluador.id
                WHERE e.empleado_id = ? AND e.periodo = ? AND e.autoevaluacion = false
                ORDER BY e.fecha_evaluacion DESC NULLS LAST, e.id DESC
                LIMIT 1
            ''', (empleado_id, periodo)).fetchone()
        
        # Obtener AUTOEVALUACIÓN
        if autoevaluacion_id_param:
            autoevaluacion = conn.execute('''
                SELECT * FROM evaluaciones
                WHERE id = ? AND empleado_id = ? AND periodo = ? AND autoevaluacion = true
                LIMIT 1
            ''', (autoevaluacion_id_param, empleado_id, periodo)).fetchone()
        elif evaluacion and evaluacion.get('fecha_evaluacion') is not None:
            # Si hay varias en el mismo período, usar la autoevaluación más cercana en fecha.
            autoevaluacion = conn.execute('''
                SELECT * FROM evaluaciones
                WHERE empleado_id = ? AND periodo = ? AND autoevaluacion = true
                ORDER BY ABS(EXTRACT(EPOCH FROM (fecha_evaluacion - ?::timestamp))) ASC, id DESC
                LIMIT 1
            ''', (empleado_id, periodo, evaluacion['fecha_evaluacion'])).fetchone()
        else:
            autoevaluacion = conn.execute('''
                SELECT * FROM evaluaciones 
                WHERE empleado_id = ? AND periodo = ? AND autoevaluacion = true
                ORDER BY fecha_evaluacion DESC NULLS LAST, id DESC
                LIMIT 1
            ''', (empleado_id, periodo)).fetchone()

        # Si no llegó evaluacion_id y sí tenemos autoevaluación, emparejar evaluación por cercanía de fecha.
        if not evaluacion and autoevaluacion and autoevaluacion.get('fecha_evaluacion') is not None:
            evaluacion = conn.execute('''
                SELECT e.*, evaluador.nombres_completos as nombre_evaluador
                FROM evaluaciones e
                LEFT JOIN empleados evaluador ON e.evaluador_id = evaluador.id
                WHERE e.empleado_id = ? AND e.periodo = ? AND e.autoevaluacion = false
                ORDER BY ABS(EXTRACT(EPOCH FROM (e.fecha_evaluacion - ?::timestamp))) ASC, e.id DESC
                LIMIT 1
            ''', (empleado_id, periodo, autoevaluacion['fecha_evaluacion'])).fetchone()
        
        # Función helper para obtener competencias
        def obtener_competencias_evaluacion(eval_id):
            if not eval_id:
                return []
            comps = conn.execute('''
                SELECT DISTINCT ON (UPPER(REGEXP_REPLACE(c.nombre, '^\\s*\\d+\\.\\s*', ''))) c.nombre as competencia, ec.puntuacion_descriptor as puntuacion, 
                       ec.observaciones, c.id as competencia_id
                FROM evaluaciones_competencia ec
                JOIN competencias c ON ec.competencia_id = c.id
                WHERE ec.evaluacion_id = %s
                ORDER BY UPPER(REGEXP_REPLACE(c.nombre, '^\\s*\\d+\\.\\s*', '')), ec.id DESC
            ''', (eval_id,)).fetchall()

            if comps:
                return [dict(c) for c in comps]

            # Fallback al modelo anterior
            comps_legacy = conn.execute('''
                SELECT DISTINCT ON (UPPER(REGEXP_REPLACE(competencia, '^\\s*\\d+\\.\\s*', '')))
                       NULL as competencia_id, competencia, puntuacion, observaciones
                FROM competencias_evaluadas
                WHERE evaluacion_id = ?
                ORDER BY UPPER(REGEXP_REPLACE(competencia, '^\\s*\\d+\\.\\s*', '')), id DESC
            ''', (eval_id,)).fetchall()
            return [dict(c) for c in comps_legacy]

        def _normalizar_observaciones_kpi(comps_list):
            """Extraer comentario legible del JSON de KPI en observaciones."""
            for comp in comps_list:
                obs_raw = comp.get('observaciones')
                if isinstance(obs_raw, str) and obs_raw.strip().startswith('{'):
                    try:
                        obs_json = json.loads(obs_raw)
                        if isinstance(obs_json, dict):
                            comp['observaciones'] = obs_json.get('comentario', '')
                            if 'kpi_detalle' in obs_json:
                                comp['kpi_detalle'] = obs_json['kpi_detalle']
                    except Exception:
                        pass
            return comps_list
        
        # Preparar respuesta
        resultado = {
            'empleado': dict(empleado),
            'periodo': periodo,
            'evaluacion': dict(evaluacion) if evaluacion else None,
            'autoevaluacion': dict(autoevaluacion) if autoevaluacion else None
        }
        
        # Agregar competencias si existen evaluaciones
        if evaluacion:
            resultado['evaluacion']['competencias'] = _normalizar_observaciones_kpi(
                obtener_competencias_evaluacion(evaluacion['id'])
            )
        if autoevaluacion:
            resultado['autoevaluacion']['competencias'] = _normalizar_observaciones_kpi(
                obtener_competencias_evaluacion(autoevaluacion['id'])
            )
        
        conn.close()
        return jsonify(resultado)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/evaluaciones', methods=['POST'])
@jwt_required()
def create_evaluacion():
    """
    [DEPRECATED] Esta ruta está DESHABILITADA. Use /api/evaluaciones/nivel en su lugar.
    Redirecciona a la ruta correcta.
    """
    return jsonify({
        'error': 'Use POST /api/evaluaciones/nivel para crear evaluaciones',
        'deprecated': True
    }), 400

# ==================== RUTAS DE CÓDIGOS DE ACCESO ====================

def generar_codigo_aleatorio(longitud=8):
    """Generar código aleatorio único de 8 caracteres (mayúsculas y números)"""
    caracteres = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(caracteres) for _ in range(longitud))

@app.route('/api/codigos-acceso/generar', methods=['POST'])
@jwt_required()
def generar_codigo_acceso():
    """
    Generar un código de acceso para autoevaluación
    Requerido: identificacion_empleado
    Solo admin/jefe pueden generar códigos
    """
    try:
        usuario_id = int(get_jwt_identity())
        data = request.json
        identificacion = data.get('identificacion')
        empleado_id = data.get('empleado_id')
        
        if not (identificacion or empleado_id):
            return jsonify({'error': 'Se requiere identificación o empleado_id'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()

        # Solo administradores y jefes pueden generar códigos de acceso.
        cursor.execute('SELECT rol FROM empleados WHERE id = %s', (usuario_id,))
        usuario_actual = cursor.fetchone()
        if not usuario_actual or usuario_actual.get('rol') not in ['admin', 'jefe']:
            conn.close()
            return jsonify({'error': 'Solo administradores o jefes pueden generar códigos de acceso'}), 403
        
        # Asegurar que la tabla existe
        upgrade_db_with_acceso_codes(conn)
        
        # Buscar empleado
        if empleado_id:
            cursor.execute('SELECT id FROM empleados WHERE id = %s', (empleado_id,))
        else:
            cursor.execute('SELECT id FROM empleados WHERE identificacion = %s', (identificacion,))
        
        resultado = cursor.fetchone()
        if not resultado:
            return jsonify({'error': 'Empleado no encontrado'}), 404
        
        emp_id = resultado['id']
        
        # Generar código único
        codigo = generar_codigo_aleatorio()
        
        # Verificar que no exista ya un código activo para este empleado
        cursor.execute('''
            SELECT codigo FROM codigos_acceso 
            WHERE empleado_id = %s AND estado = 'activo'
            LIMIT 1
        ''', (emp_id,))
        
        codigo_existente = cursor.fetchone()
        if codigo_existente:
            # Marcar como usado el código anterior
            cursor.execute('''
                UPDATE codigos_acceso 
                SET estado = 'inactivo'
                WHERE empleado_id = %s AND estado = 'activo'
            ''', (emp_id,))
        
        # Insertar nuevo código
        cursor.execute('''
            INSERT INTO codigos_acceso 
            (codigo, empleado_id, generado_por, estado, fecha_generacion)
            VALUES (%s, %s, %s, 'activo', CURRENT_TIMESTAMP)
        ''', (codigo, emp_id, usuario_id))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'codigo': codigo,
            'empleado_id': emp_id,
            'message': 'Código generado exitosamente'
        }), 201
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/codigos-acceso/validar', methods=['POST'])
def validar_codigo_acceso():
    """
    Validar código de acceso para autoevaluación
    Requerido: identificacion, codigo
    Retorna: token temporal para acceso a competencias
    """
    try:
        data = request.json
        identificacion = data.get('identificacion')
        codigo = data.get('codigo', '').upper().strip()
        
        if not identificacion or not codigo:
            return jsonify({'error': 'Se requieren identificación y código'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Verificar que la tabla existe (PostgreSQL)
        cursor.execute("""
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'codigos_acceso'
        """)
        tabla_existe = cursor.fetchone()
        
        if not tabla_existe:
            upgrade_db_with_acceso_codes(conn)
            cursor = conn.cursor()  # Crear nuevo cursor después de actualizar
        
        # Buscar empleado por identificación
        cursor.execute('''
            SELECT id, nombres_completos, COALESCE(cargo, 'Sin especificar') as cargo
            FROM empleados 
            WHERE COALESCE(identificacion, '') = %s
        ''', (identificacion,))
        
        empleado = cursor.fetchone()
        if not empleado:
            conn.close()
            return jsonify({'error': 'Identificación no encontrada'}), 404
        
        emp_id = empleado['id']
        
        # Validar código
        cursor.execute('''
            SELECT id, codigo, estado FROM codigos_acceso 
            WHERE empleado_id = %s AND codigo = %s
        ''', (emp_id, codigo))
        
        codigo_record = cursor.fetchone()
        if not codigo_record:
            conn.close()
            return jsonify({'error': 'Código inválido'}), 401
        
        codigo_id = codigo_record['id']
        estado = codigo_record['estado']
        
        if estado != 'activo':
            conn.close()
            return jsonify({'error': 'Código expirado o ya utilizado'}), 401
        
        # Marcar código como usado
        cursor.execute('''
            UPDATE codigos_acceso 
            SET estado = 'usado', fecha_uso = CURRENT_TIMESTAMP, ip_uso = %s
            WHERE id = %s
        ''', (request.remote_addr, codigo_id))
        
        conn.commit()
        
        # Generar token temporal para autoevaluación
        token = generar_token_acceso(emp_id, emp_id, 'empleado')
        
        conn.close()
        
        return jsonify({
            'valido': True,
            'token': token,
            'empleado_id': emp_id,
            'nombres_completos': empleado['nombres_completos'],
            'cargo': empleado['cargo'],
            'message': 'Código válido'
        }), 200
    
    except Exception as e:
        print(f"[ERROR] Error en validar_codigo_acceso: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Error: {str(e)}'}), 500

@app.route('/api/evaluaciones/nivel', methods=['POST'])
@jwt_required()
def create_evaluacion_nivel():
    """Crear evaluación con niveles ocupacionales (jefe, admin, o empleado para autoevaluación)"""
    try:
        usuario_id = int(get_jwt_identity())
        data = request.json
        conn = get_db_connection()
        
        # Obtener usuario actual
        usuario_actual = conn.execute('SELECT * FROM empleados WHERE id = %s', (usuario_id,)).fetchone()
        
        # Determinar si es autoevaluación ANTES de validar rol
        es_autoevaluacion = data.get('autoevaluacion', False)
        empleado_id = data['empleado_id']
        periodo = data['periodo']
        
        # Si es empleado: solo permitir autoevaluación propia
        if usuario_actual['rol'] == 'empleado':
            if not es_autoevaluacion or empleado_id != usuario_id:
                conn.close()
                return jsonify({'error': 'Los empleados solo pueden hacer su propia autoevaluación'}), 403
            # Para autoevaluación propia está permitido, continuar
        else:
            # Para jefe/admin: verificar permisos de evaluación
            puede_evaluar, mensaje = puede_evaluar_empleado(conn, usuario_id, empleado_id)
            
            if not puede_evaluar:
                conn.close()
                return jsonify({'error': mensaje}), 403
        
        # Verificar si ya existe evaluación para este empleado en este período
        if es_autoevaluacion:
            # Para autoevaluación: solo una autoevaluación por período
            evaluacion_existente = conn.execute(
                'SELECT id FROM evaluaciones WHERE empleado_id = %s AND periodo = %s AND autoevaluacion = true',
                (empleado_id, periodo)
            ).fetchone()
            if evaluacion_existente:
                conn.close()
                return jsonify({'error': f'Ya existe una autoevaluación para este período {periodo}. No se pueden crear autoevaluaciones duplicadas.'}), 409
        else:
            # Para evaluación de jefe/admin: solo una evaluación de jefe/admin por período
            evaluacion_existente = conn.execute(
                'SELECT id FROM evaluaciones WHERE empleado_id = %s AND periodo = %s AND autoevaluacion = false',
                (empleado_id, periodo)
            ).fetchone()
            if evaluacion_existente:
                conn.close()
                return jsonify({'error': f'Ya existe una evaluación para este empleado en el período {periodo}. No se pueden crear evaluaciones duplicadas.'}), 409
        
        cursor = conn.cursor()
        
        # Calcular promedio desde las competencias con ponderación:
        # Competencias 1-6: 80% del peso
        # Competencia 7 (METAS/KPI): 20% del peso
        competencias = data['competencias']
        if not competencias:
            return jsonify({'error': 'No se proporcionaron competencias'}), 400

        def _competencia_id(comp):
            try:
                return int(comp.get('competencia_id', comp.get('id', 0)))
            except (TypeError, ValueError):
                return 0

        competencias_regulares = [c for c in competencias if _competencia_id(c) != 7]
        kpi_competencia = [c for c in competencias if _competencia_id(c) == 7]
        
        if competencias_regulares and kpi_competencia:
            # Tanto competencias regulares como KPI presentes
            promedio_competencias = sum(float(c.get('puntuacion_promedio', 0)) for c in competencias_regulares) / len(competencias_regulares)
            promedio_kpi = float(kpi_competencia[0].get('puntuacion_promedio', 0))
            promedio = (promedio_competencias * 0.8) + (promedio_kpi * 0.2)
        elif competencias_regulares:
            # Solo competencias regulares (sin KPI)
            promedio = sum(float(c.get('puntuacion_promedio', 0)) for c in competencias_regulares) / len(competencias_regulares)
        elif kpi_competencia:
            # Solo KPI
            promedio = float(kpi_competencia[0].get('puntuacion_promedio', 0))
        else:
            # Ninguna competencia (caso extremo)
            promedio = 0
        
        # Determinar evaluador real desde el usuario autenticado
        if es_autoevaluacion:
            evaluador_registrado = 'Autoevaluación'
        else:
            evaluador_registrado = (
                (usuario_actual['nombres_completos'] if usuario_actual and usuario_actual['nombres_completos'] else None)
                or data.get('evaluador')
                or 'Sistema'
            )

        # Auditoría: persistir fecha y hora de evaluación.
        fecha_evaluacion_input = (data.get('fecha_evaluacion') or '').strip()
        now_ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        if fecha_evaluacion_input:
            fecha_norm = fecha_evaluacion_input.replace('T', ' ')
            if len(fecha_norm) == 10:
                fecha_evaluacion_valor = f"{fecha_norm} {datetime.now().strftime('%H:%M:%S')}"
            elif len(fecha_norm) == 16:
                fecha_evaluacion_valor = f"{fecha_norm}:00"
            else:
                fecha_evaluacion_valor = fecha_norm
        else:
            fecha_evaluacion_valor = now_ts

        # Insertar evaluación
        cursor.execute('''
            INSERT INTO evaluaciones 
            (empleado_id, evaluador_id, periodo, fecha_evaluacion, evaluador, promedio_general, comentarios_generales, frecuencia, nivel_ocupacional, autoevaluacion)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (
            empleado_id,
            usuario_id,
            data['periodo'],
            fecha_evaluacion_valor,
            evaluador_registrado,
            round(promedio, 2),
            data.get('comentarios_generales', ''),
            data.get('frecuencia', 'anual'),
            data.get('nivel_ocupacional', 0),
            True if data.get('autoevaluacion') else False
        ))
        
        evaluacion_id = cursor.fetchone()['id']
        
        # Insertar competencias
        for comp in competencias:
            comp_id = _competencia_id(comp)
            observaciones = comp.get('observaciones', '')

            # Guardar detalle individual de KPI (ej: 3, 4, 5) para mostrarlo en resultados.
            if comp_id == 7:
                comportamientos = comp.get('comportamientos') or []
                if comportamientos:
                    detalle_kpi = []
                    for item in comportamientos:
                        detalle_kpi.append({
                            'texto': item.get('texto', ''),
                            'calificacion': item.get('calificacion')
                        })
                    observaciones = json.dumps({
                        'comentario': observaciones,
                        'kpi_detalle': detalle_kpi
                    }, ensure_ascii=False)
            
            cursor.execute('''
                INSERT INTO competencias_evaluadas 
                (evaluacion_id, competencia, puntuacion, observaciones)
                VALUES (%s, %s, %s, %s)
            ''', (
                evaluacion_id,
                comp.get('competencia_nombre', 'Competencia'),
                round(float(comp.get('puntuacion_promedio', 0)), 2),
                observaciones
            ))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'id': evaluacion_id,
            'message': 'Evaluación creada exitosamente',
            'promedio_general': round(promedio, 2)
        }), 201
    except Exception as e:
        print(f"Error creando evaluación: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/evaluaciones/<int:id>', methods=['DELETE'])
@jwt_required()
def delete_evaluacion(id):
    """Eliminar una evaluación (solo admin o quien la creó)"""
    try:
        usuario_id = int(get_jwt_identity())
        
        conn = get_db_connection()
        
        # Obtener usuario actual
        usuario_actual = conn.execute('SELECT * FROM empleados WHERE id = %s', (usuario_id,)).fetchone()
        
        # Rechazar acceso a empleados
        if usuario_actual['rol'] == 'empleado':
            conn.close()
            return jsonify({'error': 'Los empleados no pueden eliminar evaluaciones'}), 403
        
        # Obtener evaluación
        evaluacion = conn.execute('SELECT * FROM evaluaciones WHERE id = %s', (id,)).fetchone()
        
        if not evaluacion:
            conn.close()
            return jsonify({'error': 'Evaluación no encontrada'}), 404
        
        # Verificar permisos: admin o quien la creó
        if usuario_actual['rol'] != 'admin' and evaluacion['evaluador_id'] != usuario_id:
            conn.close()
            return jsonify({'error': 'No tienes permiso para eliminar esta evaluación'}), 403
        
        # Eliminar competencias
        conn.execute('DELETE FROM competencias_evaluadas WHERE evaluacion_id = %s', (id,))
        
        # Eliminar evaluación
        conn.execute('DELETE FROM evaluaciones WHERE id = %s', (id,))
        
        conn.commit()
        conn.close()
        
        return jsonify({'message': 'Evaluación eliminada exitosamente'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== RUTAS DE ESTADÍSTICAS ====================

@app.route('/api/estadisticas/empleado/<int:empleado_id>', methods=['GET'])
@jwt_required_if_hardening_enabled()
def get_estadisticas_empleado(empleado_id):
    """Obtener estadísticas históricas de un empleado"""
    try:
        conn = get_db_connection()
        
        # Promedio histórico
        stats = conn.execute('''
            SELECT 
                AVG(promedio_general) as promedio_historico,
                COUNT(*) as total_evaluaciones,
                MIN(CAST(fecha_evaluacion AS DATE)) as primera_evaluacion,
                MAX(CAST(fecha_evaluacion AS DATE)) as ultima_evaluacion
            FROM evaluaciones
            WHERE empleado_id = ?
        ''', (empleado_id,)).fetchone()
        
        # Tendencia por competencia
        tendencias = conn.execute('''
            SELECT 
                ce.competencia,
                AVG(ce.puntuacion) as promedio,
                COUNT(*) as veces_evaluada
            FROM competencias_evaluadas ce
            JOIN evaluaciones e ON ce.evaluacion_id = e.id
            WHERE e.empleado_id = ?
            GROUP BY ce.competencia
            ORDER BY promedio DESC
        ''', (empleado_id,)).fetchall()
        
        conn.close()
        
        return jsonify({
            'estadisticas': dict(stats),
            'tendencias': [dict(t) for t in tendencias]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/estadisticas/departamento/<departamento>', methods=['GET'])
@jwt_required_if_hardening_enabled()
def get_estadisticas_departamento(departamento):
    """Obtener estadísticas por departamento"""
    try:
        conn = get_db_connection()
        
        stats = conn.execute('''
            SELECT 
                emp.departamento,
                AVG(e.promedio_general) as promedio_departamento,
                COUNT(DISTINCT emp.id) as total_empleados,
                COUNT(e.id) as total_evaluaciones
            FROM empleados emp
            LEFT JOIN evaluaciones e ON emp.id = e.empleado_id
            WHERE emp.departamento = ? AND emp.activo = true
            GROUP BY emp.departamento
        ''', (departamento,)).fetchone()
        
        conn.close()
        
        return jsonify(dict(stats) if stats else {})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== RUTAS DE JERARQUÍA DE EMPLEADOS ====================

@app.route('/api/empleados/<int:empleado_id>/subordinados', methods=['GET'])
@jwt_required_if_hardening_enabled()
def get_subordinados(empleado_id):
    """Obtener empleados que reportan directamente a un jefe"""
    try:
        from competencias_db import get_subordinados_directos
        conn = get_db_connection()
        subordinados = get_subordinados_directos(conn, empleado_id)
        conn.close()
        
        return jsonify(subordinados)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/empleados/<int:empleado_id>/subordinados/todos', methods=['GET'])
@jwt_required_if_hardening_enabled()
def get_todos_subordinados(empleado_id):
    """Obtener todos los subordinados en la jerarquía (recursivo)"""
    try:
        from competencias_db import get_toda_jerarquia_subordinados
        conn = get_db_connection()
        subordinados = get_toda_jerarquia_subordinados(conn, empleado_id)
        conn.close()
        
        return jsonify(subordinados)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/empleados/<int:empleado_id>/jefes', methods=['GET'])
@jwt_required_if_hardening_enabled()
def get_jefes_cadena(empleado_id):
    """Obtener la cadena de jefes de un empleado"""
    try:
        from competencias_db import get_cadena_jefes
        conn = get_db_connection()
        jefes = get_cadena_jefes(conn, empleado_id)
        conn.close()
        
        return jsonify(jefes)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/empleados/<int:empleado_id>/jefe', methods=['PUT'])
@jwt_required_if_hardening_enabled()
def actualizar_jefe(empleado_id):
    """Actualizar el jefe de un empleado"""
    try:
        from competencias_db import actualizar_jefe_empleado
        data = request.json
        nuevo_jefe_id = data.get('jefe_id')
        
        conn = get_db_connection()
        actualizado = actualizar_jefe_empleado(conn, empleado_id, nuevo_jefe_id)
        conn.close()
        
        if actualizado:
            return jsonify({'message': 'Jefe actualizado exitosamente'})
        return jsonify({'error': 'No se pudo actualizar el jefe'}), 400
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/jerarquia', methods=['GET'])
@jwt_required_if_hardening_enabled()
def get_jerarquia():
    """Obtener la estructura jerárquica completa de la empresa"""
    try:
        from competencias_db import obtener_estructura_jerarquica
        empleado_id = request.args.get('empleado_id', type=int)
        
        conn = get_db_connection()
        estructura = obtener_estructura_jerarquica(conn, empleado_id)
        conn.close()
        
        return jsonify(estructura)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/validar-evaluador', methods=['POST'])
@jwt_required_if_hardening_enabled()
def validar_evaluador():
    """Validar si un evaluador puede evaluar a un empleado"""
    try:
        from competencias_db import validar_puede_evaluar
        data = request.json
        evaluador_id = data.get('evaluador_id')
        evaluado_id = data.get('evaluado_id')
        
        if not evaluador_id or not evaluado_id:
            return jsonify({'error': 'Se requieren evaluador_id y evaluado_id'}), 400
        
        conn = get_db_connection()
        puede_evaluar, mensaje = validar_puede_evaluar(conn, evaluador_id, evaluado_id)
        conn.close()
        
        return jsonify({
            'puede_evaluar': puede_evaluar,
            'mensaje': mensaje
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== RUTA DE SALUD ====================

@app.route('/api/health', methods=['GET'])
def health_check():
    """Verificar que el servidor esté funcionando"""
    return jsonify({
        'status': 'ok',
        'message': 'API de Talentia funcionando correctamente',
        'timestamp': datetime.now().isoformat()
    })

# ==================== RUTAS DE ARCHIVOS ESTÁTICOS ====================

@app.route('/', methods=['GET'])
def index():
    """Redirigir a login"""
    return redirect('/login.html')

@app.route('/<path:filename>', methods=['GET'])
def serve_file(filename):
    """Servir archivos estáticos (HTML, CSS, JS, JSON)
    
    Fase 2 hardening: Protege HTML internos si SECURITY_HARDENING=1
    - login.html: público (sin JWT)
    - Otros .html: requieren JWT si hardening activo
    - CSS, JS, imágenes: siempre público
    """
    try:
        extension = os.path.splitext(filename)[1].lower()
        
        # Fase 2: Si es HTML interno y hardening está activo, exigir JWT
        if extension == '.html' and SECURITY_HARDENING:
            # login.html y autoevaluacion.html son públicos (flujos sin sesión anterior)
            whitelist_public_html = {'login.html', 'autoevaluacion.html'}
            
            if filename not in whitelist_public_html:
                # Exigir JWT para otros HTML
                try:
                    verify_jwt_in_request()
                except Exception:
                    # Si no hay token válido, redirigir a login
                    return redirect('/login.html')
        
        cache_seconds = STATIC_CACHE_SECONDS if extension in STATIC_CACHE_EXTENSIONS else 0
        response = send_from_directory(APP_BASE_DIR, filename, conditional=True, max_age=cache_seconds)

        # HTML sin cache para evitar que usuarios vean pantallas antiguas tras cambios
        if extension == '.html':
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'

        return response
    except Exception as e:
        # Excepción de JWT ya redirige; otras excepciones son 404
        if 'redirect' in str(type(e)):
            raise
        return jsonify({'error': 'Archivo no encontrado'}), 404

# ==================== REGISTRAR RUTAS DE COMPETENCIAS ====================
registrar_rutas_competencias(app, get_db_connection)

# ==================== EJECUTAR SERVIDOR ====================

if __name__ == '__main__':
    debug_mode = os.getenv('FLASK_DEBUG', '0') == '1'
    host = os.getenv('HOST', '0.0.0.0')
    port = int(os.getenv('PORT', '5000'))

    # En modo debug, el reloader ejecuta el proceso dos veces.
    # Inicializar solo en el proceso principal para evitar duplicados.
    debe_inicializar = (not debug_mode) or (os.environ.get('WERKZEUG_RUN_MAIN') == 'true')

    if debe_inicializar:
        init_db()
        print("[INICIO] Iniciando servidor de Gestion de Desempeno...")
        print("[INFO] Base de datos inicializada")
        print(f"[SERVIDOR] Corriendo en http://{host}:{port}")

    if debug_mode:
        app.run(debug=True, host=host, port=port, threaded=True)
    else:
        try:
            from waitress import serve
            waitress_threads = int(os.getenv('WAITRESS_THREADS', '8'))
            print(f"[MODO] Producción (Waitress, threads={waitress_threads})")
            serve(app, host=host, port=port, threads=waitress_threads)
        except ImportError:
            print("[WARN] Waitress no instalado. Usando servidor Flask con threaded=True")
            app.run(debug=False, host=host, port=port, threaded=True)
