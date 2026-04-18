"""
Módulo de autenticación y autorización
"""
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from datetime import timedelta, datetime
from functools import wraps
from flask import jsonify

# ==================== GESTIÓN DE CONTRASEÑAS ====================

def hashear_contrasena(contrasena):
    """Hashear una contraseña con seguridad"""
    return generate_password_hash(contrasena, method='pbkdf2:sha256')

def verificar_contrasena(contrasena, hash_contrasena):
    """Verificar si una contraseña coincide con su hash"""
    return check_password_hash(hash_contrasena, contrasena)

# ==================== AUTENTICACIÓN ====================

def autenticar_usuario(conn, email, contrasena):
    """
    Autenticar un usuario por email corporativo y contraseña
    Retorna: (usuario_dict, error_message)
    """
    try:
        cursor = conn.cursor()
        cursor.execute(
            'SELECT * FROM empleados WHERE correo_corporativo = %s AND activo = true',
            (email,)
        )
        usuario = cursor.fetchone()
        cursor.close()
        
        if not usuario:
            return None, 'Usuario o contraseña incorrectos'
        
        # Verificar contraseña
        if not verificar_contrasena(contrasena, usuario['contrasena_hash']):
            return None, 'Usuario o contraseña incorrectos'
        
        return dict(usuario), None
    
    except Exception as e:
        return None, f'Error en autenticación: {str(e)}'

def autenticar_empleado_por_cedula(conn, cedula, contrasena):
    """
    Autenticar un empleado por cédula y contraseña
    Para usar en autoevaluaciones
    Busca primero por cedula; si no encuentra, intenta por identificacion
    (cubre el caso donde la cedula fue modificada por error desde admin).
    Retorna: (usuario_dict, error_message)
    """
    try:
        cursor = conn.cursor()
        cursor.execute(
            'SELECT * FROM empleados WHERE cedula = %s AND activo = true',
            (cedula,)
        )
        usuario = cursor.fetchone()
        
        # Fallback: buscar por identificacion (útil cuando la cedula fue cambiada por error)
        if not usuario:
            cursor.execute(
                'SELECT * FROM empleados WHERE identificacion = %s AND activo = true',
                (cedula,)
            )
            usuario = cursor.fetchone()
        
        cursor.close()
        
        if not usuario:
            return None, 'Cédula o contraseña incorrectos'
        
        # Verificar que tenga contraseña configurada
        if not usuario['contrasena_hash']:
            return None, 'Usuario no tiene contraseña configurada. Contacte al administrador.'
        
        # Verificar contraseña
        if not verificar_contrasena(contrasena, usuario['contrasena_hash']):
            return None, 'Cédula o contraseña incorrectos'
        
        return dict(usuario), None
    
    except Exception as e:
        return None, f'Error en autenticación: {str(e)}'

def generar_token_acceso(usuario_id, email, rol='empleado'):
    """
    Generar un token JWT para un usuario
    """
    access_token = create_access_token(
        identity=str(usuario_id),  # Convertir a string - Flask-JWT-Extended requiere string
        additional_claims={
            'email': email,
            'rol': rol
        },
        expires_delta=timedelta(hours=1)  # Token válido por 1 hora
    )
    return access_token

# ==================== CONTROL DE SESIONES ÚNICAS ====================

def validar_token_contra_bd(conn, usuario_id, token_del_request):
    """
    Validar que el token del request coincida con el token registrado en BD
    Esta validación REVOCA tokens anteriores cuando se hace login desde otro lado
    
    Retorna: (es_valido: bool, mensaje: str)
    """
    try:
        cursor = conn.cursor()
        cursor.execute(
            'SELECT sesion_token, sesion_activa FROM empleados WHERE id = %s',
            (usuario_id,)
        )
        usuario = cursor.fetchone()
        cursor.close()
        
        if not usuario:
            return False, "Usuario no encontrado"
        
        # Si no hay sesión activa, rechazar
        if usuario['sesion_activa'] != True:
            return False, "No hay sesión activa registrada"
        
        # Si el token NO coincide con el registrado, rechazar
        # Esto invalida tokens de navegadores anteriores
        if usuario['sesion_token'] != token_del_request:
            return False, "Token inválido para esta sesión. Sesión desde otro dispositivo detectada."
        
        return True, "Token válido"
    
    except Exception as e:
        return False, f"Error validando token: {str(e)}"

def obtener_y_validar_token_usuario(conn, token_header):
    """
    Obtener usuario_id del token JWT del header Authorization
    Y validar que el token sea válido en la BD
    
    Retorna: (usuario_id: int o None, es_valido: bool, mensaje: str)
    """
    try:
        if not token_header or not token_header.startswith('Bearer '):
            return None, False, "Token no encontrado en request"
        
        token_string = token_header.split(' ')[1]
        
        # Intentar decodificar el token JWT
        from flask_jwt_extended import decode_token
        payload = decode_token(token_string)
        usuario_id = int(payload['sub'])
        
        # Validar contra BD
        es_valido, mensaje = validar_token_contra_bd(conn, usuario_id, token_string)
        
        return usuario_id, es_valido, mensaje
    
    except Exception as e:
        return None, False, f"Error decodificando token: {str(e)}"

def verificar_sesion_activa(conn, usuario_id):
    """
    Verificar si el usuario ya tiene una sesión activa y VÁLIDA
    - Si la sesión tiene > 1 hora, se limpia automáticamente
    Retorna: (tiene_sesion_activa: bool, mensaje: str)
    """
    try:
        from datetime import datetime, timedelta
        
        cursor = conn.cursor()
        cursor.execute(
            'SELECT sesion_activa, sesion_inicio FROM empleados WHERE id = %s',
            (usuario_id,)
        )
        usuario = cursor.fetchone()
        cursor.close()
        
        if not usuario:
            return False, "Usuario no encontrado"
        
        if usuario['sesion_activa'] == True:
            sesion_inicio = usuario.get('sesion_inicio')
            
            # Verificar si la sesión es válida (menos de 1 hora)
            if sesion_inicio:
                try:
                    fecha_inicio = datetime.strptime(sesion_inicio, '%Y-%m-%d %H:%M:%S')
                    tiempo_transcurrido = datetime.now() - fecha_inicio
                    
                    # Si pasó más de 1 hora, limpiar la sesión "fantasma"
                    if tiempo_transcurrido > timedelta(hours=1):
                        print(f"[INFO] Sesión expirada limpiada automáticamente para usuario {usuario_id}")
                        limpiar_sesion(conn, usuario_id)
                        return False, "Sesión anterior expirada (limpiada automáticamente)"
                    else:
                        # Sesión sigue válida
                        minutos_restantes = int((timedelta(hours=1) - tiempo_transcurrido).total_seconds() / 60)
                        return True, f"Ya existe una sesión activa desde: {sesion_inicio} (expira en {minutos_restantes} minutos)"
                except Exception as e:
                    print(f"[WARN] Error calculando tiempo de sesión: {e}")
                    return True, f"Ya existe una sesión activa desde: {sesion_inicio}"
            else:
                return True, "Ya existe una sesión activa (sin timestamp)"
        
        return False, "No hay sesión activa"
    
    except Exception as e:
        return False, f"Error al verificar sesión: {str(e)}"

def registrar_sesion_atomico(conn, usuario_id, token):
    """
    Registrar una nueva sesión de forma ATÓMICA
    - Primero limpia cualquier sesión anterior
    - Luego registra la nueva
    - Todo dentro de una transacción IMMEDIATE para evitar race conditions
    Retorna: (exito: bool, mensaje: str)
    """
    try:
        ahora = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        cursor = conn.cursor()
        
        # Uso de PostgreSQL: el manejo de transacciones es automático
        # Paso 1: Limpiar cualquier sesión anterior
        cursor.execute(
            '''UPDATE empleados 
               SET sesion_activa = false, 
                   sesion_token = NULL, 
                   sesion_inicio = NULL 
               WHERE id = %s''',
            (usuario_id,)
        )
        
        # Paso 2: Registrar la nueva sesión
        cursor.execute(
            '''UPDATE empleados 
               SET sesion_activa = true, 
                   sesion_token = %s, 
                   sesion_inicio = %s 
               WHERE id = %s''',
            (token, ahora, usuario_id)
        )
        cursor.close()
        
        # Paso 3: Commit - esto libera el lock
        conn.commit()
        return True, "Sesión registrada correctamente"
    
    except Exception as e:
        try:
            conn.rollback()
        except:
            pass
        return False, f"Error al registrar sesión: {str(e)}"

def registrar_sesion(conn, usuario_id, token):
    """
    Registrar una nueva sesión activa para el usuario
    DEPRECATED: usar registrar_sesion_atomico() en su lugar
    Se mantiene por compatibilidad, pero redirige a la función atómica
    """
    return registrar_sesion_atomico(conn, usuario_id, token)

def limpiar_sesion(conn, usuario_id):
    """
    Limpiar la sesión activa de un usuario (logout)
    """
    try:
        cursor = conn.cursor()
        cursor.execute(
            '''UPDATE empleados 
               SET sesion_activa = false, 
                   sesion_token = NULL, 
                   sesion_inicio = NULL 
               WHERE id = %s''',
            (usuario_id,)
        )
        cursor.close()
        conn.commit()
        return True, "Sesión cerrada correctamente"
    
    except Exception as e:
        return False, f"Error al cerrar sesión: {str(e)}"

# ==================== AUTORIZACIÓN ====================

def obtener_usuario_actual(conn):
    """
    Obtener el usuario actual desde el token JWT
    """
    try:
        usuario_id = get_jwt_identity()
        cursor = conn.cursor()
        cursor.execute(
            'SELECT * FROM empleados WHERE id = %s',
            (usuario_id,)
        )
        usuario = cursor.fetchone()
        cursor.close()
        return dict(usuario) if usuario else None
    except:
        return None

def puede_ver_empleado(conn, usuario_id, empleado_id):
    """
    Verificar si un usuario puede ver a un empleado
    Reglas:
    - Un empleado puede verse a sí mismo
    - Un jefe puede ver a sus subordinados directos e indirectos
    - Un admin puede ver a todos
    """
    if usuario_id == empleado_id:
        return True, "Puede ver su propio perfil"
    
    # Verificar si es administrador
    cursor = conn.cursor()
    cursor.execute(
        'SELECT rol FROM empleados WHERE id = %s',
        (usuario_id,)
    )
    usuario = cursor.fetchone()
    cursor.close()
    
    if usuario and usuario['rol'] == 'admin':
        return True, "Administrador puede ver a todos"
    
    # Verificar si es jefe
    subordinados = get_toda_jerarquia_subordinados(conn, usuario_id)
    subordinados_ids = [s['id'] for s in subordinados]
    
    if empleado_id in subordinados_ids:
        return True, "Es jefe de este empleado"
    
    return False, "No tienes permiso para ver este empleado"

def puede_evaluar_empleado(conn, evaluador_id, evaluado_id):
    """
    Verificar si un usuario puede evaluar a otro empleado
    Reglas:
    - Un empleado PUEDE autoevaluarse
    - Un jefe PUEDE evaluar a sus subordinados
    - Un admin PUEDE evaluar a todos
    """
    if evaluador_id == evaluado_id:
        return True, "Puede autoevaluarse"
    
    # Verificar si es administrador
    cursor = conn.cursor()
    cursor.execute(
        'SELECT rol FROM empleados WHERE id = %s',
        (evaluador_id,)
    )
    usuario = cursor.fetchone()
    cursor.close()
    
    if usuario and usuario['rol'] == 'admin':
        return True, "Administrador puede evaluar a todos"
    
    # Verificar si es jefe
    subordinados = get_toda_jerarquia_subordinados(conn, evaluador_id)
    subordinados_ids = [s['id'] for s in subordinados]
    
    if evaluado_id in subordinados_ids:
        return True, "Es jefe de este empleado"
    
    return False, "No tienes permiso para evaluar a este empleado"

def requerir_autenticacion(f):
    """Decorador para requerir autenticación"""
    @wraps(f)
    @jwt_required()
    def decorated_function(*args, **kwargs):
        return f(*args, **kwargs)
    return decorated_function

def requerir_rol(rol_requerido):
    """
    Decorador para requerir un rol específico
    Uso: @requerir_rol('admin')
    """
    def decorator(f):
        @wraps(f)
        @jwt_required()
        def decorated_function(*args, **kwargs):
            from flask_jwt_extended import get_jwt
            claims = get_jwt()
            rol_usuario = claims.get('rol', 'empleado')
            
            if rol_usuario != rol_requerido and rol_usuario != 'admin':
                return jsonify({'error': 'Permiso denegado'}), 403
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# ==================== FUNCIONES DE JERARQUÍA ====================
# (Importadas de competencias_db para autorización)

def get_toda_jerarquia_subordinados(conn, empleado_id):
    """Obtener todos los subordinados usando CTE SQL (optimizado)"""
    try:
        cursor = conn.cursor()
        query = '''
        WITH RECURSIVE subordinados_tree AS (
            -- Caso base: subordinados directos
            SELECT id FROM empleados WHERE jefe_id = %s AND activo = true
            UNION ALL
            -- Caso recursivo: subordinados de subordinados
            SELECT e.id FROM empleados e
            INNER JOIN subordinados_tree st ON e.jefe_id = st.id
            WHERE e.activo = true
        )
        SELECT id FROM subordinados_tree
        '''
        cursor.execute(query, (empleado_id,))
        resultado = cursor.fetchall()
        cursor.close()
        return resultado
    except Exception as e:
        print(f"Error en get_toda_jerarquia_subordinados: {str(e)}")
        return []
