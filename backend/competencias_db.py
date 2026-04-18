from competencias_modelo import COMPETENCIAS


def _get_columns(conn, table_name):
    """Obtener columnas de una tabla en PostgreSQL."""
    cursor = conn.cursor()
    cursor.execute(
        '''
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        ''',
        (table_name,)
    )
    return {row['column_name'] for row in cursor.fetchall()}

def upgrade_db_with_competencias(conn):
    """Agregar tablas de competencias a la base de datos existente"""
    try:
        cursor = conn.cursor()
        
        # Tabla de competencias disponibles
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS competencias (
                id INTEGER PRIMARY KEY,
                codigo TEXT UNIQUE NOT NULL,
                nombre TEXT NOT NULL,
                descripcion TEXT,
                nivel_aplicacion TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tabla de descriptores/niveles de competencia
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS descriptores_competencia (
                id SERIAL PRIMARY KEY,
                competencia_id INTEGER NOT NULL,
                descriptor_numero INTEGER,
                rol TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (competencia_id) REFERENCES competencias (id)
            )
        ''')
        
        # Tabla de comportamientos de cada descriptor
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS comportamientos (
                id SERIAL PRIMARY KEY,
                descriptor_id INTEGER NOT NULL,
                comportamiento TEXT NOT NULL,
                orden INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (descriptor_id) REFERENCES descriptores_competencia (id)
            )
        ''')
        
        # Tabla de evaluaciones por competencia (reemplaza competencias_evaluadas)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS evaluaciones_competencia (
                id SERIAL PRIMARY KEY,
                evaluacion_id INTEGER NOT NULL,
                competencia_id INTEGER NOT NULL,
                descriptor_id INTEGER,
                puntuacion_descriptor INTEGER,
                puntuacion_general REAL,
                observaciones TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (evaluacion_id) REFERENCES evaluaciones (id),
                FOREIGN KEY (competencia_id) REFERENCES competencias (id),
                FOREIGN KEY (descriptor_id) REFERENCES descriptores_competencia (id)
            )
        ''')
        
        competencias_cols = _get_columns(conn, 'competencias')

        # Insertar competencias estándar si faltan
        for competencia_key in COMPETENCIAS:
            comp = COMPETENCIAS[competencia_key]
            cursor.execute('SELECT id FROM competencias WHERE id = %s', (comp["id"],))
            existe = cursor.fetchone()
            
            if not existe:
                if 'codigo' in competencias_cols and 'nivel_aplicacion' in competencias_cols:
                    cursor.execute('''
                        INSERT INTO competencias (id, codigo, nombre, descripcion, nivel_aplicacion)
                        VALUES (%s, %s, %s, %s, %s)
                    ''', (comp["id"], competencia_key, comp["nombre"], comp["descripcion"], comp["nivel_aplicacion"]))
                else:
                    cursor.execute('''
                        INSERT INTO competencias (id, nombre, descripcion, categoria, nivel_ocupacional)
                        VALUES (%s, %s, %s, %s, %s)
                    ''', (comp["id"], comp["nombre"], comp["descripcion"], competencia_key, comp["nivel_aplicacion"]))
                
                # Insertar descriptores
                for desc in comp["descriptores"]:
                    cursor.execute('''
                        INSERT INTO descriptores_competencia (competencia_id, descriptor_numero, rol)
                        VALUES (%s, %s, %s) RETURNING id
                    ''', (comp["id"], desc["id"], desc["rol"]))
                    
                    descriptor_id = cursor.fetchone()['id']
                    
                    # Insertar comportamientos
                    for idx, comportamiento in enumerate(desc["comportamientos"], 1):
                        cursor.execute('''
                            INSERT INTO comportamientos (descriptor_id, comportamiento, orden)
                            VALUES (%s, %s, %s)
                        ''', (descriptor_id, comportamiento, idx))
        
        conn.commit()
    except Exception as e:
        print(f"Error en upgrade_db_with_competencias: {e}")
        try:
            conn.rollback()
        except:
            pass

def get_competencias(conn):
    """Obtener todas las competencias"""
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM competencias')
    return [dict(row) for row in cursor.fetchall()]

def get_competencia_completa(conn, competencia_id):
    """Obtener una competencia con todos sus descriptores y comportamientos (un solo JOIN)"""
    cursor = conn.cursor()

    cursor.execute('''
        SELECT
            c.id, c.nombre, c.descripcion, c.categoria, c.nivel_ocupacional, c.created_at,
            d.id        AS desc_id,
            d.descriptor_numero,
            d.rol,
            b.comportamiento,
            b.orden     AS comp_orden
        FROM competencias c
        LEFT JOIN descriptores_competencia d ON d.competencia_id = c.id
        LEFT JOIN comportamientos b ON b.descriptor_id = d.id
        WHERE c.id = %s
        ORDER BY d.descriptor_numero, b.orden
    ''', (competencia_id,))

    rows = cursor.fetchall()
    cursor.close()

    if not rows:
        return None

    first = rows[0]
    competencia = {
        'id': first['id'],
        'nombre': first['nombre'],
        'descripcion': first['descripcion'],
        'categoria': first['categoria'],
        'nivel_ocupacional': first['nivel_ocupacional'],
        'created_at': first['created_at'],
    }

    descriptores_map = {}
    for row in rows:
        did = row['desc_id']
        if did is None:
            continue
        if did not in descriptores_map:
            descriptores_map[did] = {
                'id': did,
                'descriptor_numero': row['descriptor_numero'],
                'rol': row['rol'],
                'comportamientos': []
            }
        if row['comportamiento']:
            descriptores_map[did]['comportamientos'].append(row['comportamiento'])

    competencia['descriptores'] = list(descriptores_map.values())
    return competencia


def get_todas_competencias_completas(conn):
    """Obtener todas las competencias con descriptores y comportamientos en un solo JOIN"""
    cursor = conn.cursor()

    cursor.execute('''
        SELECT
            c.id, c.nombre, c.descripcion, c.categoria, c.nivel_ocupacional, c.created_at,
            d.id        AS desc_id,
            d.descriptor_numero,
            d.rol,
            b.comportamiento,
            b.orden     AS comp_orden
        FROM competencias c
        LEFT JOIN descriptores_competencia d ON d.competencia_id = c.id
        LEFT JOIN comportamientos b ON b.descriptor_id = d.id
        ORDER BY c.id, d.descriptor_numero, b.orden
    ''')

    rows = cursor.fetchall()
    cursor.close()

    competencias_map = {}
    for row in rows:
        cid = row['id']
        if cid not in competencias_map:
            competencias_map[cid] = {
                'id': cid,
                'nombre': row['nombre'],
                'descripcion': row['descripcion'],
                'categoria': row['categoria'],
                'nivel_ocupacional': row['nivel_ocupacional'],
                'created_at': row['created_at'],
                '_descriptores_map': {}
            }
        comp = competencias_map[cid]
        did = row['desc_id']
        if did is None:
            continue
        dm = comp['_descriptores_map']
        if did not in dm:
            dm[did] = {
                'id': did,
                'descriptor_numero': row['descriptor_numero'],
                'rol': row['rol'],
                'comportamientos': []
            }
        if row['comportamiento']:
            dm[did]['comportamientos'].append(row['comportamiento'])

    result = []
    for comp in competencias_map.values():
        comp['descriptores'] = list(comp.pop('_descriptores_map').values())
        result.append(comp)
    return result

def guardar_evaluacion_competencia(conn, evaluacion_id, competencia_id, descriptor_id, puntuacion, observaciones):
    """Guardar la evaluación de una competencia"""
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO evaluaciones_competencia 
        (evaluacion_id, competencia_id, descriptor_id, puntuacion_descriptor, observaciones)
        VALUES (%s, %s, %s, %s, %s) RETURNING id
    ''', (evaluacion_id, competencia_id, descriptor_id, puntuacion, observaciones))
    conn.commit()
    return cursor.fetchone()['id']

def obtener_evaluaciones_competencia(conn, evaluacion_id, competencia_id):
    """Obtener todas las evaluaciones de una competencia en una evaluación"""
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM evaluaciones_competencia
        WHERE evaluacion_id = %s AND competencia_id = %s
        ORDER BY descriptor_id
    ''', (evaluacion_id, competencia_id))
    return [dict(row) for row in cursor.fetchall()]

# ==================== FUNCIONES PARA GESTIÓN DE JERARQUÍA ====================

def upgrade_empleados_con_jerarquia(conn):
    """Agregar campo jefe_id a la tabla empleados para jerarquía"""
    try:
        cursor = conn.cursor()
        
        # Verificar si la columna jefe_id ya existe
        columnas = _get_columns(conn, 'empleados')
        
        if 'jefe_id' not in columnas:
            # Agregar columna jefe_id
            cursor.execute('''
                ALTER TABLE empleados ADD COLUMN jefe_id INTEGER
                REFERENCES empleados(id)
            ''')
            print("[OK] Campo jefe_id agregado a tabla empleados")
        
        # Agregar campo evaluador_id a evaluaciones
        columnas_eval = _get_columns(conn, 'evaluaciones')
        
        if 'evaluador_id' not in columnas_eval:
            cursor.execute('''
                ALTER TABLE evaluaciones ADD COLUMN evaluador_id INTEGER
                REFERENCES empleados(id)
            ''')
            print("[OK] Campo evaluador_id agregado a tabla evaluaciones")
        
        conn.commit()
    except Exception as e:
        print(f"Error en upgrade_empleados_con_jerarquia: {e}")
        conn.rollback()

def upgrade_evaluaciones_con_nivel(conn):
    """Agregar campos nivel_ocupacional y evaluador a la tabla evaluaciones"""
    try:
        cursor = conn.cursor()
        
        # Verificar columnas existentes
        columnas = _get_columns(conn, 'evaluaciones')
        
        if 'nivel_ocupacional' not in columnas:
            cursor.execute('''
                ALTER TABLE evaluaciones ADD COLUMN nivel_ocupacional INTEGER
            ''')
            print("[OK] Campo nivel_ocupacional agregado a tabla evaluaciones")
        
        if 'evaluador' not in columnas:
            cursor.execute('''
                ALTER TABLE evaluaciones ADD COLUMN evaluador TEXT
            ''')
            print("[OK] Campo evaluador agregado a tabla evaluaciones")
        
        conn.commit()
    except Exception as e:
        print(f"Error en upgrade_evaluaciones_con_nivel: {e}")
        conn.rollback()

def upgrade_evaluaciones_expandir_campos(conn):
    """Expandir campos varchar(255) a TEXT para evitar limite de caracteres"""
    try:
        cursor = conn.cursor()
        
        # Cambiar evaluador de varchar(255) a TEXT si está limitado
        cursor.execute('''
            SELECT column_name, data_type, character_maximum_length
            FROM information_schema.columns
            WHERE table_name = 'evaluaciones' AND column_name = 'evaluador'
        ''')
        result = cursor.fetchone()
        
        if result:
            col_type = result.get('data_type', '').upper()
            max_length = result.get('character_maximum_length')
            
            # Si es varchar con límite de 255, cambiar a TEXT
            if col_type == 'CHARACTER VARYING' and max_length == 255:
                try:
                    cursor.execute('''
                        ALTER TABLE evaluaciones 
                        ALTER COLUMN evaluador TYPE TEXT
                    ''')
                    print("[OK] Campo evaluador expandido de varchar(255) a TEXT")
                except Exception as e:
                    if 'already' not in str(e):
                        print(f"[WARN] No se pudo expandir evaluador: {e}")
        
        # Cambiar comentarios_generales si existe y está limitado
        cursor.execute('''
            SELECT column_name, data_type, character_maximum_length
            FROM information_schema.columns
            WHERE table_name = 'evaluaciones' AND column_name = 'comentarios_generales'
        ''')
        result = cursor.fetchone()
        
        if result:
            col_type = result.get('data_type', '').upper()
            max_length = result.get('character_maximum_length')
            
            # Si es varchar con límite, cambiar a TEXT
            if col_type == 'CHARACTER VARYING' and max_length and max_length < 1000:
                try:
                    cursor.execute('''
                        ALTER TABLE evaluaciones 
                        ALTER COLUMN comentarios_generales TYPE TEXT
                    ''')
                    print("[OK] Campo comentarios_generales expandido a TEXT")
                except Exception as e:
                    if 'already' not in str(e):
                        print(f"[WARN] No se pudo expandir comentarios_generales: {e}")
        
        # Expandir observaciones en competencias_evaluadas
        cursor.execute('''
            SELECT column_name, data_type, character_maximum_length
            FROM information_schema.columns
            WHERE table_name = 'competencias_evaluadas' AND column_name = 'observaciones'
        ''')
        result = cursor.fetchone()
        
        if result:
            col_type = result.get('data_type', '').upper()
            max_length = result.get('character_maximum_length')
            
            # Si es varchar con límite, cambiar a TEXT
            if col_type == 'CHARACTER VARYING' and max_length and max_length < 1000:
                try:
                    cursor.execute('''
                        ALTER TABLE competencias_evaluadas 
                        ALTER COLUMN observaciones TYPE TEXT
                    ''')
                    print("[OK] Campo observaciones en competencias_evaluadas expandido a TEXT")
                except Exception as e:
                    if 'already' not in str(e):
                        print(f"[WARN] No se pudo expandir observaciones: {e}")
        
        conn.commit()
    except Exception as e:
        print(f"Error en upgrade_evaluaciones_expandir_campos: {e}")
        conn.rollback()

def upgrade_evaluaciones_fecha_hora(conn):
    """Asegurar que evaluaciones.fecha_evaluacion almacene fecha y hora."""
    try:
        cursor = conn.cursor()

        cursor.execute('''
            SELECT data_type
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'evaluaciones'
              AND column_name = 'fecha_evaluacion'
        ''')
        result = cursor.fetchone()

        if not result:
            return

        current_type = (result.get('data_type') or '').lower()
        if current_type == 'timestamp without time zone':
            return

        cursor.execute('''
            ALTER TABLE evaluaciones
            ALTER COLUMN fecha_evaluacion
            TYPE TIMESTAMP WITHOUT TIME ZONE
            USING (
                CASE
                    WHEN fecha_evaluacion IS NULL THEN NULL
                    WHEN fecha_evaluacion::text ~ '^\\d{4}-\\d{2}-\\d{2}$'
                        THEN (fecha_evaluacion::text || ' 00:00:00')::timestamp
                    WHEN fecha_evaluacion::text ~ '^\\d{4}-\\d{2}-\\d{2}[ T]\\d{2}:\\d{2}(:\\d{2})?$'
                        THEN REPLACE(fecha_evaluacion::text, 'T', ' ')::timestamp
                    ELSE NULL
                END
            )
        ''')
        print('[OK] Campo fecha_evaluacion convertido a TIMESTAMP')
        conn.commit()
    except Exception as e:
        print(f"Error en upgrade_evaluaciones_fecha_hora: {e}")
        conn.rollback()

def upgrade_evaluaciones_autoevaluacion(conn):
    """Agregar campo autoevaluacion a la tabla evaluaciones"""
    try:
        cursor = conn.cursor()

        columnas = _get_columns(conn, 'evaluaciones')

        if 'autoevaluacion' not in columnas:
            cursor.execute('''
                ALTER TABLE evaluaciones ADD COLUMN autoevaluacion BOOLEAN DEFAULT 0
            ''')
            print("[OK] Campo autoevaluacion agregado a tabla evaluaciones")

        conn.commit()
    except Exception as e:
        print(f"Error en upgrade_evaluaciones_autoevaluacion: {e}")
        conn.rollback()

def upgrade_plan_formacion(conn):
    """Crear tabla para plan de formación con metodología 70-20-10"""
    try:
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS plan_formacion (
                id SERIAL PRIMARY KEY,
                evaluacion_id INTEGER NOT NULL,
                tipo_formacion TEXT NOT NULL,
                porcentaje INTEGER NOT NULL,
                oportunidad_desarrollo TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (evaluacion_id) REFERENCES evaluaciones (id) ON DELETE CASCADE,
                UNIQUE(evaluacion_id, tipo_formacion)
            )
        ''')
        print("[OK] Tabla plan_formacion creada/verificada")
        conn.commit()
    except Exception as e:
        print(f"Error en upgrade_plan_formacion: {e}")
        conn.rollback()

def upgrade_empleados_campos_adicionales(conn):
    """Agregar campos identificacion, empresa y aplica_kpi a la tabla empleados"""
    try:
        cursor = conn.cursor()
        
        # Verificar columnas existentes
        columnas = _get_columns(conn, 'empleados')
        
        if 'identificacion' not in columnas:
            cursor.execute('''
                ALTER TABLE empleados ADD COLUMN identificacion TEXT
            ''')
            print("[OK] Campo identificacion agregado a tabla empleados")
        
        if 'empresa' not in columnas:
            cursor.execute('''
                ALTER TABLE empleados ADD COLUMN empresa TEXT
            ''')
            print("[OK] Campo empresa agregado a tabla empleados")
        
        if 'aplica_kpi' not in columnas:
            cursor.execute('''
                ALTER TABLE empleados ADD COLUMN aplica_kpi BOOLEAN DEFAULT 0
            ''')
            print("[OK] Campo aplica_kpi agregado a tabla empleados")
        
        conn.commit()
    except Exception as e:
        print(f"Error en upgrade_empleados_campos_adicionales: {e}")
        conn.rollback()

def get_empleado_por_id(conn, empleado_id):
    """Obtener un empleado por su ID"""
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM empleados WHERE id = %s', (empleado_id,))
    row = cursor.fetchone()
    return dict(row) if row else None

def get_todos_empleados(conn):
    """Obtener todos los empleados activos"""
    cursor = conn.cursor()
    cursor.execute('''
        SELECT e.*, 
               j.nombre || ' ' || j.apellidos as jefe_nombre
        FROM empleados e
        LEFT JOIN empleados j ON e.jefe_id = j.id
        WHERE e.activo = true
        ORDER BY e.departamento, e.nombre
    ''')
    return [dict(row) for row in cursor.fetchall()]

def get_subordinados_directos(conn, jefe_id):
    """Obtener empleados que reportan directamente a un jefe"""
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM empleados
        WHERE jefe_id = %s AND activo = true
        ORDER BY nombres_completos
    ''', (jefe_id,))
    return [dict(row) for row in cursor.fetchall()]

def get_toda_jerarquia_subordinados(conn, jefe_id):
    """Obtener todos los subordinados en la jerarquía usando CTE recursivo (una sola query)"""
    cursor = conn.cursor()
    cursor.execute('''
        WITH RECURSIVE subordinados_cte AS (
            SELECT *
            FROM empleados
            WHERE jefe_id = %s AND activo = true
            UNION ALL
            SELECT e.*
            FROM empleados e
            INNER JOIN subordinados_cte s ON e.jefe_id = s.id
            WHERE e.activo = true
        )
        SELECT * FROM subordinados_cte
        ORDER BY nombres_completos
    ''', (jefe_id,))
    return [dict(row) for row in cursor.fetchall()]

def get_cadena_jefes(conn, empleado_id):
    """Obtener la cadena de jefes de un empleado (hasta el CEO)"""
    cadena = []
    empleado_actual = get_empleado_por_id(conn, empleado_id)
    
    while empleado_actual and empleado_actual.get('jefe_id'):
        jefe = get_empleado_por_id(conn, empleado_actual['jefe_id'])
        if jefe:
            cadena.append(jefe)
            empleado_actual = jefe
        else:
            break
    
    return cadena

def validar_puede_evaluar(conn, evaluador_id, evaluado_id):
    """Validar si un evaluador puede evaluar a un empleado (debe ser su jefe directo)"""
    evaluado = get_empleado_por_id(conn, evaluado_id)
    
    if not evaluado:
        return False, "Empleado evaluado no encontrado"
    
    if evaluado.get('jefe_id') == evaluador_id:
        return True, "Evaluador autorizado"
    
    return False, "Solo el jefe directo puede realizar la evaluación"

def crear_empleado(conn, nombre, apellidos, email, puesto, departamento, fecha_ingreso, jefe_id=None):
    """Crear un nuevo empleado"""
    cursor = conn.cursor()
    
    # Validar que el jefe existe si se proporciona
    if jefe_id:
        jefe = get_empleado_por_id(conn, jefe_id)
        if not jefe:
            raise ValueError("El jefe especificado no existe")
    
    cursor.execute('''
        INSERT INTO empleados (nombre, apellidos, email, puesto, departamento, fecha_ingreso, jefe_id, activo)
        VALUES (%s, %s, %s, %s, %s, %s, %s, true) RETURNING id
    ''', (nombre, apellidos, email, puesto, departamento, fecha_ingreso, jefe_id))
    
    conn.commit()
    return cursor.fetchone()['id']

def actualizar_jefe_empleado(conn, empleado_id, nuevo_jefe_id):
    """Actualizar el jefe de un empleado"""
    cursor = conn.cursor()
    
    # Validar que no se cree un ciclo
    if nuevo_jefe_id:
        # Verificar que el nuevo jefe no sea subordinado del empleado
        subordinados = get_toda_jerarquia_subordinados(conn, empleado_id)
        subordinados_ids = [s['id'] for s in subordinados]
        
        if nuevo_jefe_id in subordinados_ids:
            raise ValueError("No se puede crear un ciclo jerárquico: el nuevo jefe es subordinado del empleado")
        
        # Validar que el nuevo jefe existe
        jefe = get_empleado_por_id(conn, nuevo_jefe_id)
        if not jefe:
            raise ValueError("El jefe especificado no existe")
    
    cursor.execute('''
        UPDATE empleados
        SET jefe_id = %s
        WHERE id = %s
    ''', (nuevo_jefe_id, empleado_id))
    
    conn.commit()
    return cursor.rowcount > 0

def obtener_estructura_jerarquica(conn, empleado_id=None):
    """Obtener la estructura jerárquica completa o desde un empleado específico"""
    if empleado_id:
        empleado = get_empleado_por_id(conn, empleado_id)
        if not empleado:
            return None
        
        # Obtener subordinados
        subordinados = get_subordinados_directos(conn, empleado_id)
        
        # Recursivamente obtener la estructura de cada subordinado
        empleado['subordinados'] = [
            obtener_estructura_jerarquica(conn, sub['id'])
            for sub in subordinados
        ]
        
        return empleado
    else:
        # Obtener todos los empleados sin jefe (CEO y top-level)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM empleados WHERE jefe_id IS NULL AND activo = true')
        top_level = [dict(row) for row in cursor.fetchall()]
        
        # Obtener estructura de cada uno
        return [obtener_estructura_jerarquica(conn, emp['id']) for emp in top_level]


def upgrade_nombres_competencias_con_numeros(conn):
    """Actualizar nombres de competencias para incluir numeración"""
    try:
        cursor = conn.cursor()
        print("[INFO] Actualizando nombres de competencias con numeración...")
        
        # Mapeo de nombres de competencias con numeración
        actualizaciones = {
            '1. GESTION_OPERATIVA': '1. GESTIÓN OPERATIVA',
            'GESTION_OPERATIVA': '1. GESTIÓN OPERATIVA',
            '2. INNOVACION_MEJORA_CONTINUA': '2. INNOVACIÓN Y MEJORA CONTINUA',
            'INNOVACION_MEJORA_CONTINUA': '2. INNOVACIÓN Y MEJORA CONTINUA',
            '3. FOCO_EN_EL_CLIENTE': '3. FOCO EN EL CLIENTE',
            'FOCO_EN_EL_CLIENTE': '3. FOCO EN EL CLIENTE',
            '4. ORIENTACION_AL_RESULTADO': '4. ORIENTACIÓN AL RESULTADO',
            'ORIENTACION_AL_RESULTADO': '4. ORIENTACIÓN AL RESULTADO',
            '5. CONSTRUYENDO_RELACIONES_SOLIDAS': '5. CONSTRUYENDO RELACIONES SÓLIDAS',
            'CONSTRUYENDO_RELACIONES_SOLIDAS': '5. CONSTRUYENDO RELACIONES SÓLIDAS',
            '6. EQUIPOS_GANADORES': '6. EQUIPOS GANADORES',
            'EQUIPOS_GANADORES': '6. EQUIPOS GANADORES',
        }
        
        # Actualizar cada competencia por su código
        for codigo, nuevo_nombre in actualizaciones.items():
            cursor.execute('''
                UPDATE competencias 
                SET nombre = %s 
                WHERE codigo = %s
            ''', (nuevo_nombre, codigo))
            
            if cursor.rowcount > 0:
                print(f"  [OK] Actualizada competencia '{codigo}' → '{nuevo_nombre}'")
        
        conn.commit()
        print("[OK] Nombres de competencias actualizados con numeración")
        
    except Exception as e:
        print(f"[ERROR] Error actualizando nombres de competencias: {e}")
        try:
            conn.rollback()
        except:
            pass

def upgrade_tablas_maestras(conn):
    """Crear tablas maestras para empresas, cargos y centros de costo"""
    try:
        cursor = conn.cursor()
        
        # Tabla de empresas
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS empresas (
                id SERIAL PRIMARY KEY,
                razon_social TEXT NOT NULL,
                nit TEXT UNIQUE NOT NULL,
                ciudad TEXT,
                activo BOOLEAN DEFAULT true,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        print("[OK] Tabla empresas creada")
        
        # Tabla de cargos
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cargos (
                id SERIAL PRIMARY KEY,
                nombre TEXT UNIQUE NOT NULL,
                descripcion TEXT,
                activo BOOLEAN DEFAULT true,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        print("[OK] Tabla cargos creada")
        
        # Tabla de centros de costo
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS centros_costo (
                id SERIAL PRIMARY KEY,
                nombre TEXT UNIQUE NOT NULL,
                descripcion TEXT,
                activo BOOLEAN DEFAULT true,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        print("[OK] Tabla centros_costo creada")
        
        conn.commit()
        print("[OK] Tablas maestras creadas exitosamente")
        
    except Exception as e:
        print(f"[ERROR] Error creando tablas maestras: {e}")
        try:
            conn.rollback()
        except:
            pass

def upgrade_empleados_nuevos_campos(conn):
    """Actualizar tabla empleados con los nuevos campos requeridos"""
    try:
        cursor = conn.cursor()
        
        # Verificar columnas existentes
        columnas = _get_columns(conn, 'empleados')
        
        # Agregar campo cedula
        if 'cedula' not in columnas:
            cursor.execute('ALTER TABLE empleados ADD COLUMN cedula TEXT')
            print("  [OK] Campo cedula agregado")
        
        # Agregar campo nombres_completos
        if 'nombres_completos' not in columnas:
            cursor.execute('ALTER TABLE empleados ADD COLUMN nombres_completos TEXT')
            # Migrar datos existentes de nombre + apellidos
            cursor.execute('''
                UPDATE empleados 
                SET nombres_completos = nombre || ' ' || apellidos 
                WHERE nombres_completos IS NULL
            ''')
            print("  [OK] Campo nombres_completos agregado y migrado")
        
        # Agregar campo correo_personal
        if 'correo_personal' not in columnas:
            cursor.execute('ALTER TABLE empleados ADD COLUMN correo_personal TEXT')
            print("  [OK] Campo correo_personal agregado")
        
        # Agregar campo correo_corporativo
        if 'correo_corporativo' not in columnas:
            cursor.execute('ALTER TABLE empleados ADD COLUMN correo_corporativo TEXT')
            # Migrar email existente a correo_corporativo
            cursor.execute('''
                UPDATE empleados 
                SET correo_corporativo = email 
                WHERE correo_corporativo IS NULL
            ''')
            print("  [OK] Campo correo_corporativo agregado y migrado")
        
        # Agregar campo celular
        if 'celular' not in columnas:
            cursor.execute('ALTER TABLE empleados ADD COLUMN celular TEXT')
            print("  [OK] Campo celular agregado")
        
        # Agregar campo cargo_id (reemplaza puesto)
        if 'cargo_id' not in columnas:
            cursor.execute('ALTER TABLE empleados ADD COLUMN cargo_id INTEGER REFERENCES cargos(id)')
            print("  [OK] Campo cargo_id agregado")
        
        # Agregar campo centro_costo_id (reemplaza departamento)
        if 'centro_costo_id' not in columnas:
            cursor.execute('ALTER TABLE empleados ADD COLUMN centro_costo_id INTEGER REFERENCES centros_costo(id)')
            print("  [OK] Campo centro_costo_id agregado")
        
        # Agregar campo empresa_id
        if 'empresa_id' not in columnas:
            cursor.execute('ALTER TABLE empleados ADD COLUMN empresa_id INTEGER REFERENCES empresas(id)')
            print("  [OK] Campo empresa_id agregado")
        
        conn.commit()
        print("[OK] Tabla empleados actualizada con nuevos campos")
        
    except Exception as e:
        print(f"[ERROR] Error actualizando empleados: {e}")
        try:
            conn.rollback()
        except:
            pass
def upgrade_db_with_acceso_codes(conn):
    """Crear tabla de códigos de acceso para autoevaluación"""
    try:
        cursor = conn.cursor()
        
        # Crear tabla de códigos de acceso
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS codigos_acceso (
                id SERIAL PRIMARY KEY,
                codigo TEXT UNIQUE NOT NULL,
                empleado_id INTEGER NOT NULL,
                generado_por INTEGER,
                estado TEXT DEFAULT 'activo',
                fecha_generacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                fecha_uso TIMESTAMP,
                ip_uso TEXT,
                FOREIGN KEY (empleado_id) REFERENCES empleados (id),
                FOREIGN KEY (generado_por) REFERENCES empleados (id)
            )
        ''')
        
        conn.commit()
        print("[OK] Tabla codigos_acceso creada")
        
    except Exception as e:
        print(f"Error en upgrade_db_with_acceso_codes: {e}")
        try:
            conn.rollback()
        except:
            pass