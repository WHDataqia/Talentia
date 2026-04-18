import psycopg2, os
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
load_dotenv()
conn = psycopg2.connect(os.getenv('DATABASE_URL'))
cur = conn.cursor(cursor_factory=RealDictCursor)
cur.execute('SELECT competencia, puntuacion FROM competencias_evaluadas WHERE evaluacion_id=18')
rows = cur.fetchall()
print('competencias para eval 18:', len(rows))
for r in rows:
    print(' ', r['competencia'], ':', r['puntuacion'])
conn.close()
