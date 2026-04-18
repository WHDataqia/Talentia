import pandas as pd
from sqlalchemy import create_engine
import os
from dotenv import load_dotenv

# Migrar datos desde Excel a PostgreSQL usando pandas y SQLAlchemy
# Tablas objetivo: empleados, cargos, centros_costo, empresas

load_dotenv()
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://postgres@localhost:5432/talentia_db')

# Crear conexión a PostgreSQL
engine = create_engine(DATABASE_URL)

def cargar_archivo(archivo_excel, tabla_destino, nombre_tabla_label):
    """
    Carga un archivo Excel específico a una tabla en la base de datos
    """
    try:
        # Verificar que el archivo existe
        if not os.path.exists(archivo_excel):
            print(f"❌ Error: Archivo '{archivo_excel}' no encontrado")
            return False
            
        # Leer el archivo Excel
        print(f"📖 Leyendo: {archivo_excel}")
        df = pd.read_excel(archivo_excel)
        
        print(f"   - Filas: {len(df)}")
        print(f"   - Columnas: {list(df.columns)}")
        
        # Limpiar espacios en blanco en nombres de columnas
        df.columns = df.columns.str.strip()
        
        # Exportar a la tabla en la base de datos
        df.to_sql(tabla_destino, con=engine, if_exists='replace', index=False)
        print(f"✅ {nombre_tabla_label} exportado exitosamente a tabla '{tabla_destino}'")
        return True
        
    except Exception as e:
        print(f"❌ Error al cargar {nombre_tabla_label}: {str(e)}")
        return False

# Mapeo de archivos a tablas
cargas = [
    ('base_principal.xlsx', 'empleados', 'Empleados'),
    ('cargos.xlsx', 'cargos', 'Cargos'),
    ('centros_costo.xlsx', 'centros_costo', 'Centros de Costo'),
    ('entidades.xlsx', 'empresas', 'Empresas'),
]

print("=" * 60)
print("INICIANDO CARGA DE DATOS A POSTGRESQL")
print("=" * 60)

resultados = []
for archivo, tabla, label in cargas:
    resultado = cargar_archivo(archivo, tabla, label)
    resultados.append((label, resultado))

print("\n" + "=" * 60)
print("RESUMEN DE CARGA")
print("=" * 60)
for label, resultado in resultados:
    estado = "✅ ÉXITO" if resultado else "❌ FALLÓ"
    print(f"{estado}: {label}")

todos_exitosos = all(r[1] for r in resultados)
if todos_exitosos:
    print("\n🎉 ¡Todos los datos han sido cargados exitosamente!")
else:
    print("\n⚠️  Algunos archivos no se cargaron correctamente")