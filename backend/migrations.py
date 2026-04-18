"""
Migraciones de base de datos para el sistema de gestión de desempeño
"""


def _column_exists(conn, table_name, column_name):
        cursor = conn.cursor()
        cursor.execute(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                    AND table_name = %s
                    AND column_name = %s
                """,
                (table_name, column_name)
        )
        exists = cursor.fetchone() is not None
        cursor.close()
        return exists

def upgrade_empleados_agregar_cargo(conn):
    """Agregar columna cargo a la tabla empleados si no existe"""
    try:
        cursor = conn.cursor()

        if not _column_exists(conn, 'empleados', 'cargo'):
            cursor.execute('ALTER TABLE empleados ADD COLUMN cargo TEXT')
            cursor.close()
            print("  [OK] Campo cargo agregado a tabla empleados")

            if _column_exists(conn, 'empleados', 'cargo_id'):
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE empleados e
                    SET cargo = COALESCE(
                        (SELECT nombre FROM cargos c WHERE c.id = e.cargo_id),
                        'Sin especificar'
                    )
                    WHERE cargo IS NULL
                ''')
                cursor.close()
                print("  [OK] Campo cargo poblado desde cargos")
            
            conn.commit()
        
    except Exception as e:
        print(f"Error en upgrade_empleados_agregar_cargo: {e}")
        try:
            conn.rollback()
        except:
            pass

def upgrade_empleados_agregar_identificacion(conn):
    """Agregar columna identificacion a la tabla empleados si no existe"""
    try:
        cursor = conn.cursor()

        if not _column_exists(conn, 'empleados', 'identificacion'):
            cursor.execute('ALTER TABLE empleados ADD COLUMN identificacion TEXT')
            print("  [OK] Campo identificacion agregado a tabla empleados")

            if _column_exists(conn, 'empleados', 'cedula'):
                cursor.execute('''
                    UPDATE empleados
                    SET identificacion = cedula
                    WHERE identificacion IS NULL AND cedula IS NOT NULL
                ''')
                print("  [OK] Campo identificacion poblado desde cedula")
            
            conn.commit()
        
    except Exception as e:
        print(f"Error en upgrade_empleados_agregar_identificacion: {e}")
        try:
            conn.rollback()
        except:
            pass

def upgrade_empleados_agregar_nivel_ocupacional(conn):
    """Agregar columna nivel_ocupacional a la tabla empleados si no existe"""
    try:
        cursor = conn.cursor()

        if not _column_exists(conn, 'empleados', 'nivel_ocupacional'):
            cursor.execute('ALTER TABLE empleados ADD COLUMN nivel_ocupacional TEXT')
            print("  [OK] Campo nivel_ocupacional agregado a tabla empleados")
            conn.commit()

    except Exception as e:
        print(f"Error en upgrade_empleados_agregar_nivel_ocupacional: {e}")
        try:
            conn.rollback()
        except:
            pass

def upgrade_empleados_agregar_items_kpi(conn):
    """Agregar columnas de ítems KPI a la tabla empleados si no existen"""
    try:
        cursor = conn.cursor()

        if not _column_exists(conn, 'empleados', 'kpi_item_1'):
            cursor.execute('ALTER TABLE empleados ADD COLUMN kpi_item_1 TEXT')
            print("  [OK] Campo kpi_item_1 agregado a tabla empleados")

        if not _column_exists(conn, 'empleados', 'kpi_item_2'):
            cursor.execute('ALTER TABLE empleados ADD COLUMN kpi_item_2 TEXT')
            print("  [OK] Campo kpi_item_2 agregado a tabla empleados")

        if not _column_exists(conn, 'empleados', 'kpi_item_3'):
            cursor.execute('ALTER TABLE empleados ADD COLUMN kpi_item_3 TEXT')
            print("  [OK] Campo kpi_item_3 agregado a tabla empleados")

        conn.commit()

    except Exception as e:
        print(f"Error en upgrade_empleados_agregar_items_kpi: {e}")
        try:
            conn.rollback()
        except:
            pass

def upgrade_competencia_kpi(conn):
    """Asegurar existencia de la competencia 7 (Metas del Cargo KPIs)"""
    try:
        cursor = conn.cursor()

        has_codigo = _column_exists(conn, 'competencias', 'codigo')
        has_nivel = _column_exists(conn, 'competencias', 'nivel_aplicacion')

        if has_codigo:
            cursor.execute('SELECT id FROM competencias WHERE codigo = %s', ('METAS_DEL_CARGO_KPIS',))
            competencia = cursor.fetchone()
        else:
            cursor.execute('SELECT id FROM competencias WHERE nombre = %s', ('7. METAS DEL CARGO (KPIs) (si aplica)',))
            competencia = cursor.fetchone()

        if not competencia:
            if has_codigo and has_nivel:
                cursor.execute('''
                    INSERT INTO competencias (codigo, nombre, descripcion, nivel_aplicacion)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                ''', (
                    'METAS_DEL_CARGO_KPIS',
                    '7. METAS DEL CARGO (KPIs) (si aplica)',
                    'Metas del cargo definidas para el colaborador.',
                    'KPIs'
                ))
            elif has_codigo:
                cursor.execute('''
                    INSERT INTO competencias (codigo, nombre, descripcion)
                    VALUES (%s, %s, %s)
                    RETURNING id
                ''', (
                    'METAS_DEL_CARGO_KPIS',
                    '7. METAS DEL CARGO (KPIs) (si aplica)',
                    'Metas del cargo definidas para el colaborador.'
                ))
            else:
                cursor.execute('''
                    INSERT INTO competencias (nombre, descripcion)
                    VALUES (%s, %s)
                    RETURNING id
                ''', (
                    '7. METAS DEL CARGO (KPIs) (si aplica)',
                    'Metas del cargo definidas para el colaborador.'
                ))
            print("  [OK] Competencia 7 KPI agregada")
            competencia = cursor.fetchone()

        competencia_id = competencia['id'] if isinstance(competencia, dict) else competencia[0]
        competencia_id_param = str(competencia_id)

        niveles = [
            'HACEMOS QUE LAS COSAS PASEN (Ejecutando)',
            'GESTORES DE EXPERIENCIAS (Gestionando)',
            'POTENCIANDO EQUIPOS (Potenciando)',
            'EMPODERANDO Y FOMENTANDO (Dando forma)',
            'LIDERAZGO ESTRATÉGICO (Liderando)'
        ]

        for idx, rol in enumerate(niveles, start=1):
            descriptor_numero_param = str(idx)
            cursor.execute('''
                SELECT id FROM descriptores_competencia
                WHERE competencia_id = %s AND descriptor_numero = %s
            ''', (competencia_id_param, descriptor_numero_param))
            row = cursor.fetchone()

            if row:
                descriptor_id = row['id'] if isinstance(row, dict) else row[0]
            else:
                cursor.execute('''
                    INSERT INTO descriptores_competencia (competencia_id, descriptor_numero, rol)
                    VALUES (%s, %s, %s)
                    RETURNING id
                ''', (competencia_id_param, descriptor_numero_param, rol))
                new_row = cursor.fetchone()
                descriptor_id = new_row['id'] if isinstance(new_row, dict) else new_row[0]

            cursor.execute('SELECT COUNT(*) FROM comportamientos WHERE descriptor_id = %s', (descriptor_id,))
            total_row = cursor.fetchone()
            total = total_row['count'] if isinstance(total_row, dict) else total_row[0]
            if total == 0:
                for orden, comportamiento in enumerate(['KPI 1', 'KPI 2', 'KPI 3'], start=1):
                    cursor.execute('''
                        INSERT INTO comportamientos (descriptor_id, comportamiento, orden)
                        VALUES (%s, %s, %s)
                    ''', (descriptor_id, comportamiento, orden))

        conn.commit()

    except Exception as e:
        print(f"Error en upgrade_competencia_kpi: {e}")
        try:
            conn.rollback()
        except:
            pass
