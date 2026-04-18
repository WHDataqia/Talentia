import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

from competencias_modelo import COMPETENCIAS

load_dotenv()

PG_URL = os.getenv('DATABASE_URL')


def main():
    if not PG_URL:
        raise RuntimeError('DATABASE_URL no configurada')

    pg_conn = psycopg2.connect(PG_URL)
    pg_conn.cursor_factory = RealDictCursor
    p_cur = pg_conn.cursor()

    try:
        # 1) Validar catálogo de cargos en PostgreSQL
        p_cur.execute('SELECT COUNT(*) AS n FROM cargos')
        cargos_pg = p_cur.fetchone()['n']
        print(f'cargos PG antes: {cargos_pg}')
        if cargos_pg == 0:
            print('ADVERTENCIA: catálogo de cargos vacío en PostgreSQL. Cargue maestras antes de continuar.')

        # 2) Reparar catálogo de competencias completo (descriptores/comportamientos)
        # Mantiene competencias (upsert) y reconstruye tablas hijas para estado consistente.
        p_cur.execute('TRUNCATE TABLE comportamientos RESTART IDENTITY CASCADE')
        p_cur.execute('TRUNCATE TABLE descriptores_competencia RESTART IDENTITY CASCADE')

        for codigo, comp in COMPETENCIAS.items():
            p_cur.execute(
                '''
                INSERT INTO competencias (id, nombre, descripcion, categoria, nivel_ocupacional)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE
                SET nombre = EXCLUDED.nombre,
                    descripcion = EXCLUDED.descripcion,
                    categoria = EXCLUDED.categoria,
                    nivel_ocupacional = EXCLUDED.nivel_ocupacional
                ''',
                (comp['id'], comp['nombre'], comp['descripcion'], codigo, comp['nivel_aplicacion'])
            )

            for desc in comp.get('descriptores', []):
                p_cur.execute(
                    '''
                    INSERT INTO descriptores_competencia (competencia_id, descriptor_numero, rol)
                    VALUES (%s, %s, %s)
                    RETURNING id
                    ''',
                    (comp['id'], str(desc['id']), desc['rol'])
                )
                descriptor_id = p_cur.fetchone()['id']

                for orden, comportamiento in enumerate(desc.get('comportamientos', []), 1):
                    p_cur.execute(
                        '''
                        INSERT INTO comportamientos (descriptor_id, comportamiento, orden)
                        VALUES (%s, %s, %s)
                        ''',
                        (descriptor_id, comportamiento, str(orden))
                    )

        pg_conn.commit()

        # Verificación rápida
        p_cur.execute('SELECT COUNT(*) AS n FROM cargos')
        cargos_fin = p_cur.fetchone()['n']
        p_cur.execute('SELECT COUNT(*) AS n FROM competencias')
        comps_fin = p_cur.fetchone()['n']
        p_cur.execute('SELECT COUNT(*) AS n FROM descriptores_competencia')
        desc_fin = p_cur.fetchone()['n']
        p_cur.execute('SELECT COUNT(*) AS n FROM comportamientos')
        compor_fin = p_cur.fetchone()['n']

        print(f'OK cargos: {cargos_fin}')
        print(f'OK competencias: {comps_fin}')
        print(f'OK descriptores: {desc_fin}')
        print(f'OK comportamientos: {compor_fin}')

    except Exception:
        pg_conn.rollback()
        raise
    finally:
        p_cur.close()
        pg_conn.close()


if __name__ == '__main__':
    main()
