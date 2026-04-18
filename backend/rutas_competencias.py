"""
API Endpoints para Competencias
Define las rutas para gestionar competencias y sus evaluaciones
"""

from flask import request, jsonify
from competencias_db import (
    get_competencias,
    get_competencia_completa,
    get_todas_competencias_completas,
    guardar_evaluacion_competencia,
    obtener_evaluaciones_competencia,
    upgrade_db_with_competencias
)

def registrar_rutas_competencias(app, get_db_connection):
    """Registrar todas las rutas relacionadas con competencias"""
    
    # ==================== RUTAS DE COMPETENCIAS ====================
    
    @app.route('/api/competencias', methods=['GET'])
    def obtener_competencias():
        """Obtener lista de todas las competencias"""
        try:
            conn = get_db_connection()
            competencias = get_competencias(conn)
            conn.close()
            return jsonify(competencias), 200
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/competencias/completas', methods=['GET'])
    def obtener_todas_competencias_completas():
        """Obtener todas las competencias con descriptores en una sola consulta"""
        try:
            conn = get_db_connection()
            competencias = get_todas_competencias_completas(conn)
            conn.close()
            return jsonify(competencias), 200
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/competencias/<int:competencia_id>', methods=['GET'])
    def obtener_competencia(competencia_id):
        """Obtener una competencia específica con todos sus descriptores"""
        try:
            conn = get_db_connection()
            competencia = get_competencia_completa(conn, competencia_id)
            conn.close()
            
            if not competencia:
                return jsonify({'error': 'Competencia no encontrada'}), 404
            
            return jsonify(competencia), 200
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    # ==================== RUTAS DE EVALUACIÓN DE COMPETENCIAS ====================
    
    @app.route('/api/evaluaciones/<int:evaluacion_id>/competencias', methods=['GET'])
    def obtener_evaluaciones_competencias(evaluacion_id):
        """Obtener todas las competencias evaluadas en una evaluación"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT ec.id, c.nombre, ec.competencia_id, ec.descriptor_id, 
                       ec.puntuacion_descriptor, ec.observaciones,
                       d.rol as descriptor_rol
                FROM evaluaciones_competencia ec
                JOIN competencias c ON ec.competencia_id = c.id
                LEFT JOIN descriptores_competencia d ON ec.descriptor_id = d.id
                WHERE ec.evaluacion_id = ?
                ORDER BY c.id, ec.descriptor_id
            ''', (evaluacion_id,))
            
            resultados = [dict(row) for row in cursor.fetchall()]
            conn.close()
            
            return jsonify(resultados), 200
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/evaluaciones/<int:evaluacion_id>/competencias/<int:competencia_id>', methods=['GET'])
    def obtener_evaluacion_competencia(evaluacion_id, competencia_id):
        """Obtener la evaluación de una competencia específica"""
        try:
            conn = get_db_connection()
            evaluaciones = obtener_evaluaciones_competencia(conn, evaluacion_id, competencia_id)
            conn.close()
            
            return jsonify(evaluaciones), 200
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/evaluaciones/<int:evaluacion_id>/competencias', methods=['POST'])
    def crear_evaluacion_competencia(evaluacion_id):
        """Guardar evaluación de una competencia"""
        try:
            datos = request.get_json()
            
            if not datos or 'competencia_id' not in datos:
                return jsonify({'error': 'Datos incompletos'}), 400
            
            conn = get_db_connection()
            
            # Guardar evaluación del descriptor principal
            competencia_id = datos['competencia_id']
            descriptor_id = datos.get('descriptor_id')
            puntuacion = datos.get('puntuacion_descriptor')
            observaciones = datos.get('observaciones', '')
            
            # Si hay múltiples descriptores evaluados
            if 'descriptores' in datos:
                for desc in datos['descriptores']:
                    guardar_evaluacion_competencia(
                        conn,
                        evaluacion_id,
                        competencia_id,
                        desc.get('descriptor_id'),
                        desc.get('puntuacion'),
                        desc.get('observaciones', '')
                    )
            else:
                # Guardar evaluación única
                id_evaluacion = guardar_evaluacion_competencia(
                    conn,
                    evaluacion_id,
                    competencia_id,
                    descriptor_id,
                    puntuacion,
                    observaciones
                )
            
            conn.close()
            return jsonify({
                'mensaje': 'Evaluación guardada correctamente',
                'evaluacion_id': evaluacion_id,
                'competencia_id': competencia_id
            }), 201
            
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/evaluaciones/nivel/legacy', methods=['POST'])
    def crear_evaluacion_por_nivel():
        """
        [DEPRECATED] RUTA LEGACY - NO USAR.
        Esta ruta ha sido reemplazada por /api/evaluaciones/nivel en app.py.
        Se desactiva para evitar duplicación de datos.
        Usa la ruta correcta: POST /api/evaluaciones/nivel
        """
        return jsonify({
            'error': 'Esta ruta está deprecated. Use POST /api/evaluaciones/nivel en su lugar',
            'deprecated': True
        }), 400
    
    @app.route('/api/evaluaciones/<int:evaluacion_id>/competencias/<int:competencia_id>', methods=['PUT'])
    def actualizar_evaluacion_competencia(evaluacion_id, competencia_id):
        """Actualizar evaluación de una competencia"""
        try:
            datos = request.get_json()
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Actualizar observaciones y puntuaciones
            for desc in datos.get('descriptores', []):
                cursor.execute('''
                    UPDATE evaluaciones_competencia
                    SET puntuacion_descriptor = %s, observaciones = %s
                    WHERE evaluacion_id = %s AND competencia_id = %s AND descriptor_id = %s
                ''', (
                    desc.get('puntuacion'),
                    desc.get('observaciones'),
                    evaluacion_id,
                    competencia_id,
                    desc.get('descriptor_id')
                ))
            
            conn.commit()
            conn.close()
            
            return jsonify({'mensaje': 'Evaluación actualizada correctamente'}), 200
            
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/evaluaciones/<int:evaluacion_id>/competencias/<int:competencia_id>', methods=['DELETE'])
    def eliminar_evaluacion_competencia(evaluacion_id, competencia_id):
        """Eliminar evaluación de una competencia"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                DELETE FROM evaluaciones_competencia
                WHERE evaluacion_id = %s AND competencia_id = %s
            ''', (evaluacion_id, competencia_id))
            
            conn.commit()
            conn.close()
            
            return jsonify({'mensaje': 'Evaluación eliminada correctamente'}), 200
            
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    # ==================== RUTAS DE REPORTES ====================
    
    @app.route('/api/reportes/competencias/<int:evaluacion_id>', methods=['GET'])
    def reporte_competencias(evaluacion_id):
        """Generar reporte de evaluación de competencias"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Obtener datos de la evaluación
            cursor.execute('SELECT * FROM evaluaciones WHERE id = %s', (evaluacion_id,))
            evaluacion = dict(cursor.fetchone()) if cursor.fetchone() else None
            
            if not evaluacion:
                return jsonify({'error': 'Evaluación no encontrada'}), 404
            
            # Obtener resumen de competencias evaluadas
            cursor.execute('''
                SELECT 
                    c.id as competencia_id,
                    c.nombre as competencia,
                    COUNT(ec.id) as total_descriptores,
                    AVG(ec.puntuacion_descriptor) as puntuacion_promedio
                FROM evaluaciones_competencia ec
                JOIN competencias c ON ec.competencia_id = c.id
                WHERE ec.evaluacion_id = ?
                GROUP BY c.id, c.nombre
            ''', (evaluacion_id,))
            
            competencias_evaluadas = [dict(row) for row in cursor.fetchall()]
            conn.close()
            
            # Calcular puntuacion_general con ponderación:
            # Competencias 1-6: 80% del peso
            # Competencia 7 (METAS/KPI): 20% del peso
            competencias_regulares = [c for c in competencias_evaluadas if c.get('competencia_id') != 7]
            kpi_competencia = [c for c in competencias_evaluadas if c.get('competencia_id') == 7]
            
            if competencias_regulares and kpi_competencia:
                # Tanto competencias regulares como KPI presentes
                promedio_competencias = sum(c['puntuacion_promedio'] for c in competencias_regulares) / len(competencias_regulares)
                promedio_kpi = kpi_competencia[0]['puntuacion_promedio']
                puntuacion_general = (promedio_competencias * 0.8) + (promedio_kpi * 0.2)
            elif competencias_regulares:
                # Solo competencias regulares (sin KPI)
                puntuacion_general = sum(c['puntuacion_promedio'] for c in competencias_regulares) / len(competencias_regulares)
            elif kpi_competencia:
                # Solo KPI
                puntuacion_general = kpi_competencia[0]['puntuacion_promedio']
            else:
                # Ninguna competencia (caso extremo)
                puntuacion_general = 0
            
            reporte = {
                'evaluacion': evaluacion,
                'competencias': competencias_evaluadas,
                'total_competencias': len(competencias_evaluadas),
                'puntuacion_general': puntuacion_general
            }
            
            return jsonify(reporte), 200
            
        except Exception as e:
            return jsonify({'error': str(e)}), 500
