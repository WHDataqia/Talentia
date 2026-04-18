"""
Helpers para manejo seguro de base de datos en entorno multi-usuario
Convertido a PostgreSQL
"""
import psycopg2
from psycopg2.extras import RealDictCursor
import time
from contextlib import contextmanager
import os
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://postgres@localhost:5432/talentia_db')

@contextmanager
def get_db_transaction(max_retries=5, retry_delay=0.1):
    """
    Context manager para transacciones seguras con reintentos
    Uso:
        with get_db_transaction() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE ...")
            cursor.execute("INSERT ...")
            # commit automático al salir del bloque (si no hay error)
            # rollback automático si hay error
    """
    conn = None
    retries = 0
    
    while retries < max_retries:
        try:
            # Crear conexión con PostgreSQL
            conn = psycopg2.connect(DATABASE_URL)
            conn.cursor_factory = RealDictCursor
            
            # PostgreSQL maneja transacciones automáticamente
            
            yield conn
            
            # Si todo salió bien, commit
            conn.commit()
            break
            
        except psycopg2.OperationalError as e:
            # Si hay error de conexión, reintentar
            if 'could not connect' in str(e).lower() or 'connection' in str(e).lower():
                retries += 1
                if retries >= max_retries:
                    raise Exception(f"No se pudo conectar a la BD después de {max_retries} intentos")
                time.sleep(retry_delay * retries)  # Backoff exponencial
                if conn:
                    try:
                        conn.rollback()
                        conn.close()
                    except:
                        pass
                conn = None
                continue
            else:
                raise
                
        except Exception as e:
            # Cualquier otro error: rollback
            if conn:
                try:
                    conn.rollback()
                except:
                    pass
            raise
            
        finally:
            # Siempre cerrar conexión
            if conn:
                try:
                    conn.close()
                except:
                    pass

@contextmanager
def get_db_readonly():
    """
    Context manager para consultas de solo lectura (más rápido)
    Uso:
        with get_db_readonly() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT ...")
            result = cursor.fetchall()
    """
    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL)
        conn.cursor_factory = RealDictCursor
        # Read-only transaction
        conn.set_session(readonly=True)
        yield conn
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass

def ejecutar_con_reintentos(query, params=(), max_retries=3):
    """
    Ejecutar una query con reintentos automáticos
    Útil para operaciones críticas
    """
    retries = 0
    
    while retries < max_retries:
        try:
            with get_db_transaction() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                result = cursor.fetchall()
                cursor.close()
                conn.commit()
                return result
        except Exception as e:
            retries += 1
            if retries >= max_retries:
                raise
            time.sleep(0.2 * retries)
    
    return None
