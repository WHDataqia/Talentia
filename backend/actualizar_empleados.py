"""
Módulo para actualizar empleados desde archivo Excel.
Permite validar y cargar empleados masivamente, útil para sincronización periódica con RRHH.
"""

import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
from auth import hashear_contrasena
import os
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://postgres@localhost:5432/talentia_db')


def get_db_connection():
    """Conexión a PostgreSQL con cursor dict."""
    conn = psycopg2.connect(DATABASE_URL)
    conn.cursor_factory = RealDictCursor
    return conn


def normalizar_texto(texto):
    """Normaliza texto para comparaciones (mayúsculas, sin espacios extras)."""
    if pd.isna(texto) or texto is None:
        return None
    return str(texto).strip().upper()


def buscar_id_por_nombre(conn, tabla, nombre_col, valor):
    """
    Busca ID en tabla maestra por nombre.
    
    Args:
        conn: Conexión a BD
        tabla: Nombre de tabla (cargos, centros_costo, empresas)
        nombre_col: Columna donde buscar (nombre, razon_social, nit)
        valor: Valor a buscar
    
    Returns:
        ID encontrado o None
    """
    if not valor:
        return None
    
    valor_norm = normalizar_texto(valor)
    cursor = conn.cursor()
    
    # Buscar por coincidencia exacta
    query = f"SELECT id FROM {tabla} WHERE UPPER({nombre_col}) = %s AND activo = true"
    cursor.execute(query, (valor_norm,))
    result = cursor.fetchone()
    
    if result:
        return result['id']
    
    # Si no encuentra, buscar por LIKE (contiene)
    query = f"SELECT id FROM {tabla} WHERE UPPER({nombre_col}) LIKE %s AND activo = true"
    cursor.execute(query, (f'%{valor_norm}%',))
    result = cursor.fetchone()
    
    return result['id'] if result else None


def buscar_empleado_por_cedula(conn, cedula):
    """Busca empleado existente por cédula."""
    if not cedula:
        return None
    
    cursor = conn.cursor()
    cursor.execute(
        'SELECT * FROM empleados WHERE cedula = %s OR identificacion = %s',
        (str(cedula), str(cedula))
    )
    result = cursor.fetchone()
    
    return dict(result) if result else None


def analizar_archivo_empleados(ruta_excel):
    """
    Analiza archivo Excel de empleados y genera reporte de validación.
    
    Args:
        ruta_excel: Ruta al archivo Excel
    
    Returns:
        Dict con estructura:
        {
            'success': bool,
            'total_filas': int,
            'empleados_nuevos': int,
            'empleados_existentes': int,
            'errores': [str],
            'advertencias': [str],
            'preview': [dict] - Primeras 5 filas procesadas
        }
    """
    try:
        # Leer Excel
        df = pd.read_excel(ruta_excel)
        
        # Normalizar nombres de columnas
        df.columns = [col.strip().upper().replace(' ', '_') for col in df.columns]
        
        # Columnas esperadas (flexibles)
        columnas_posibles = {
            'cedula': ['CEDULA', 'IDENTIFICACION', 'CC', 'DOCUMENTO'],
            'nombres': ['NOMBRES_COMPLETOS', 'NOMBRES', 'NOMBRE_COMPLETO', 'NOMBRE'],
            'correo_personal': ['CORREO_PERSONAL', 'EMAIL_PERSONAL', 'CORREO'],
            'correo_corporativo': ['CORREO_CORPORATIVO', 'EMAIL_CORPORATIVO', 'EMAIL'],
            'celular': ['CELULAR', 'TELEFONO', 'MOVIL'],
            'cargo': ['CARGO', 'PUESTO'],
            'centro_costo': ['CENTRO_DE_COSTO', 'CENTRO_COSTO', 'ÁREA', 'AREA'],
            'empresa': ['EMPRESA', 'RAZON_SOCIAL', 'NIT'],
            'jefe': ['JEFE', 'CEDULA_JEFE', 'SUPERVISOR'],
            'fecha_ingreso': ['FECHA_INGRESO', 'FECHA_INICIO'],
            'aplica_kpi': ['APLICA_KPI', 'KPI']
        }
        
        # Mapear columnas encontradas
        columnas_mapeadas = {}
        for campo, posibles in columnas_posibles.items():
            for col in posibles:
                if col in df.columns:
                    columnas_mapeadas[campo] = col
                    break
        
        # Validar columnas obligatorias
        obligatorias = ['cedula', 'nombres', 'cargo', 'centro_costo']
        faltantes = [campo for campo in obligatorias if campo not in columnas_mapeadas]
        
        if faltantes:
            return {
                'success': False,
                'error': f'Faltan columnas obligatorias: {", ".join(faltantes)}',
                'columnas_encontradas': list(df.columns),
                'columnas_esperadas': [col for cols in columnas_posibles.values() for col in cols]
            }
        
        # Conectar a BD para validaciones
        conn = get_db_connection()
        
        errores = []
        advertencias = []
        nuevos = 0
        existentes = 0
        preview = []
        
        for idx, row in df.iterrows():
            fila = idx + 2  # Excel empieza en 1, más header
            
            try:
                # Datos básicos
                cedula = str(row[columnas_mapeadas['cedula']]).strip() if not pd.isna(row[columnas_mapeadas['cedula']]) else None
                nombres = str(row[columnas_mapeadas['nombres']]).strip() if not pd.isna(row[columnas_mapeadas['nombres']]) else None
                
                if not cedula or cedula == 'nan':
                    errores.append(f'Fila {fila}: Cédula vacía')
                    continue
                
                if not nombres or nombres == 'nan':
                    errores.append(f'Fila {fila}: Nombre vacío')
                    continue
                
                # Buscar si existe
                empleado_actual = buscar_empleado_por_cedula(conn, cedula)
                es_nuevo = empleado_actual is None
                
                if es_nuevo:
                    nuevos += 1
                else:
                    existentes += 1
                
                # Validar cargo
                cargo_texto = row[columnas_mapeadas['cargo']] if not pd.isna(row[columnas_mapeadas['cargo']]) else None
                cargo_id = buscar_id_por_nombre(conn, 'cargos', 'nombre', cargo_texto)
                if cargo_texto and not cargo_id:
                    advertencias.append(f'Fila {fila}: Cargo "{cargo_texto}" no encontrado (se creará o asignará manualmente)')
                
                # Validar centro de costo
                cc_texto = row[columnas_mapeadas['centro_costo']] if not pd.isna(row[columnas_mapeadas['centro_costo']]) else None
                cc_id = buscar_id_por_nombre(conn, 'centros_costo', 'nombre', cc_texto)
                if cc_texto and not cc_id:
                    advertencias.append(f'Fila {fila}: Centro de costo "{cc_texto}" no encontrado (se creará o asignará manualmente)')
                
                # Preview de primeras 5 filas
                if len(preview) < 5:
                    preview.append({
                        'fila': fila,
                        'cedula': cedula,
                        'nombres': nombres,
                        'cargo': cargo_texto,
                        'centro_costo': cc_texto,
                        'accion': 'NUEVO' if es_nuevo else 'ACTUALIZAR',
                        'cargo_encontrado': cargo_id is not None,
                        'cc_encontrado': cc_id is not None
                    })
            
            except Exception as e:
                errores.append(f'Fila {fila}: Error procesando - {str(e)}')
        
        conn.close()
        
        return {
            'success': len(errores) == 0,
            'total_filas': len(df),
            'empleados_nuevos': nuevos,
            'empleados_existentes': existentes,
            'errores': errores[:10],  # Limitar a 10 primeros errores
            'advertencias': advertencias[:10],
            'preview': preview,
            'columnas_mapeadas': columnas_mapeadas
        }
    
    except Exception as e:
        return {
            'success': False,
            'error': f'Error leyendo archivo: {str(e)}'
        }


def recargar_empleados_desde_excel(ruta_excel):
    """
    Carga/actualiza empleados desde archivo Excel.
    
    Args:
        ruta_excel: Ruta al archivo Excel validado
    
    Returns:
        Dict con resultado de la operación
    """
    try:
        # Primero analizar
        reporte = analizar_archivo_empleados(ruta_excel)
        
        if not reporte['success']:
            return reporte
        
        # Leer Excel
        df = pd.read_excel(ruta_excel)
        df.columns = [col.strip().upper().replace(' ', '_') for col in df.columns]
        
        columnas = reporte['columnas_mapeadas']
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        insertados = 0
        actualizados = 0
        errores = []
        
        for idx, row in df.iterrows():
            try:
                # Extraer datos
                cedula = str(row[columnas['cedula']]).strip() if not pd.isna(row[columnas['cedula']]) else None
                if not cedula or cedula == 'nan':
                    continue
                
                nombres = str(row[columnas['nombres']]).strip() if not pd.isna(row[columnas['nombres']]) else ''
                correo_personal = str(row[columnas['correo_personal']]).strip() if 'correo_personal' in columnas and not pd.isna(row[columnas['correo_personal']]) else ''
                correo_corporativo = str(row[columnas['correo_corporativo']]).strip() if 'correo_corporativo' in columnas and not pd.isna(row[columnas['correo_corporativo']]) else ''
                celular = str(row[columnas['celular']]).strip() if 'celular' in columnas and not pd.isna(row[columnas['celular']]) else ''
                
                # Buscar IDs de maestras
                cargo_texto = row[columnas['cargo']] if not pd.isna(row[columnas['cargo']]) else None
                cargo_id = buscar_id_por_nombre(conn, 'cargos', 'nombre', cargo_texto)
                
                cc_texto = row[columnas['centro_costo']] if not pd.isna(row[columnas['centro_costo']]) else None
                cc_id = buscar_id_por_nombre(conn, 'centros_costo', 'nombre', cc_texto)
                
                empresa_texto = row[columnas['empresa']] if 'empresa' in columnas and not pd.isna(row[columnas['empresa']]) else None
                empresa_id = buscar_id_por_nombre(conn, 'empresas', 'razon_social', empresa_texto)
                if not empresa_id and empresa_texto:
                    empresa_id = buscar_id_por_nombre(conn, 'empresas', 'nit', empresa_texto)
                
                # Buscar jefe
                jefe_cedula = str(row[columnas['jefe']]).strip() if 'jefe' in columnas and not pd.isna(row[columnas['jefe']]) else None
                jefe_id = None
                if jefe_cedula and jefe_cedula != 'nan':
                    jefe = buscar_empleado_por_cedula(conn, jefe_cedula)
                    jefe_id = jefe['id'] if jefe else None
                
                # Fecha ingreso
                fecha_ingreso = None
                if 'fecha_ingreso' in columnas and not pd.isna(row[columnas['fecha_ingreso']]):
                    try:
                        fecha_ingreso = pd.to_datetime(row[columnas['fecha_ingreso']]).strftime('%Y-%m-%d')
                    except:
                        fecha_ingreso = None
                
                # Aplica KPI
                aplica_kpi = 0
                if 'aplica_kpi' in columnas and not pd.isna(row[columnas['aplica_kpi']]):
                    valor = str(row[columnas['aplica_kpi']]).upper()
                    aplica_kpi = 1 if valor in ['SI', 'SÍ', '1', 'TRUE', 'YES'] else 0
                
                # Verificar si existe
                empleado_actual = buscar_empleado_por_cedula(conn, cedula)
                
                if empleado_actual:
                    # Actualizar
                    cursor.execute('''
                        UPDATE empleados SET
                            nombres_completos = %s,
                            correo_personal = %s,
                            correo_corporativo = %s,
                            celular = %s,
                            cargo_id = %s,
                            centro_costo_id = %s,
                            empresa_id = %s,
                            jefe_id = %s,
                            fecha_ingreso = %s,
                            aplica_kpi = %s,
                            cargo = %s,
                            identificacion = %s,
                            activo = true
                        WHERE id = %s
                    ''', (
                        nombres,
                        correo_personal,
                        correo_corporativo,
                        celular,
                        cargo_id,
                        cc_id,
                        empresa_id,
                        jefe_id,
                        fecha_ingreso,
                        aplica_kpi,
                        cargo_texto,  # campo texto legacy
                        cedula,
                        empleado_actual['id']
                    ))
                    actualizados += 1
                else:
                    # Insertar nuevo
                    contrasena_hash = hashear_contrasena(cedula)  # Contraseña inicial = cédula
                    
                    cursor.execute('''
                        INSERT INTO empleados (
                            cedula, identificacion, nombres_completos,
                            correo_personal, correo_corporativo, celular,
                            cargo_id, centro_costo_id, empresa_id, jefe_id,
                            fecha_ingreso, aplica_kpi, cargo,
                            contrasena_hash, rol, activo, created_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ''', (
                        cedula,
                        cedula,
                        nombres,
                        correo_personal,
                        correo_corporativo,
                        celular,
                        cargo_id,
                        cc_id,
                        empresa_id,
                        jefe_id,
                        fecha_ingreso,
                        aplica_kpi,
                        cargo_texto,
                        contrasena_hash,
                        'empleado',
                        True,
                        datetime.now()
                    ))
                    insertados += 1
            
            except Exception as e:
                errores.append(f'Fila {idx+2}: {str(e)}')
        
        conn.commit()
        conn.close()
        
        return {
            'success': True,
            'insertados': insertados,
            'actualizados': actualizados,
            'total_procesados': insertados + actualizados,
            'errores': errores[:10]
        }
    
    except Exception as e:
        return {
            'success': False,
            'error': f'Error cargando empleados: {str(e)}'
        }


def asignar_contrasenas_cedula_existentes():
    """
    Asigna contraseña (cédula) a todos los empleados que no tienen contraseña.
    Útil para reseteos masivos o empleados importados sin contraseña.
    
    Returns:
        Dict con resultado de la operación
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Buscar empleados sin contraseña
        cursor.execute('''
            SELECT id, cedula, identificacion, nombres_completos
            FROM empleados
            WHERE contrasena_hash IS NULL OR contrasena_hash = ''
            AND activo = true
        ''')
        empleados = cursor.fetchall()
        
        asignados = 0
        errores = []
        
        for emp in empleados:
            try:
                cedula = emp['cedula'] or emp['identificacion']
                if not cedula:
                    errores.append(f"Empleado {emp['id']} ({emp['nombres_completos']}): sin cédula")
                    continue
                
                contrasena_hash = hashear_contrasena(cedula)
                cursor.execute(
                    'UPDATE empleados SET contrasena_hash = %s WHERE id = %s',
                    (contrasena_hash, emp['id'])
                )
                asignados += 1
            
            except Exception as e:
                errores.append(f"Empleado {emp['id']}: {str(e)}")
        
        conn.commit()
        conn.close()
        
        return {
            'success': True,
            'total_empleados_sin_contrasena': len(empleados),
            'asignados': asignados,
            'errores': errores[:10]
        }
    
    except Exception as e:
        return {
            'success': False,
            'error': f'Error asignando contraseñas: {str(e)}'
        }


if __name__ == '__main__':
    """
    Uso desde línea de comandos:
    
    # Analizar archivo antes de cargar
    python backend/actualizar_empleados.py analizar ruta/archivo.xlsx
    
    # Cargar empleados desde archivo
    python backend/actualizar_empleados.py cargar ruta/archivo.xlsx
    
    # Asignar contraseñas a empleados sin contraseña
    python backend/actualizar_empleados.py asignar-contrasenas
    """
    import sys
    import json
    
    if len(sys.argv) < 2:
        print("Uso: python actualizar_empleados.py [analizar|cargar|asignar-contrasenas] [archivo.xlsx]")
        sys.exit(1)
    
    comando = sys.argv[1]
    
    if comando == 'analizar':
        if len(sys.argv) < 3:
            print("Error: Debes especificar la ruta del archivo Excel")
            sys.exit(1)
        
        resultado = analizar_archivo_empleados(sys.argv[2])
        print(json.dumps(resultado, indent=2, ensure_ascii=False))
    
    elif comando == 'cargar':
        if len(sys.argv) < 3:
            print("Error: Debes especificar la ruta del archivo Excel")
            sys.exit(1)
        
        resultado = recargar_empleados_desde_excel(sys.argv[2])
        print(json.dumps(resultado, indent=2, ensure_ascii=False))
    
    elif comando == 'asignar-contrasenas':
        resultado = asignar_contrasenas_cedula_existentes()
        print(json.dumps(resultado, indent=2, ensure_ascii=False))
    
    else:
        print(f"Comando desconocido: {comando}")
        print("Comandos válidos: analizar, cargar, asignar-contrasenas")
        sys.exit(1)
