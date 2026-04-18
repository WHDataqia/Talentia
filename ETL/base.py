import pandas as pd
from sqlalchemy import create_engine

# 1. Cargar el archivo original
file_path = 'BASE BLUEDOORS.xlsx'
df = pd.read_excel(file_path)
if df.empty:
    print("El archivo está vacío. Por favor, verifica el contenido.")
    exit()  
# 2. Separar los datos en DataFrames independientes

# Nombre de las columnas
#print("Las columnas  son:")
#print(df.columns.tolist())

# Eliminamos duplicados para tener tablas maestras limpias
df_cargos = df[['CARGO']].drop_duplicates().reset_index(drop=True)
df_centros = df[['CENTRO DE COSTO']].drop_duplicates().reset_index(drop=True)

df['NIT'] = df['NIT'].astype(str).str.replace('.', '', regex=False).str.strip()
df_entidades = df[['RAZON SOCIAL', 'NIT']].drop_duplicates().reset_index(drop=True)

# 3. Exportar a tres archivos distintos (Excel o CSV)
df_cargos.to_excel('cargos.xlsx', index=False)
df_centros.to_excel('centros_costo.xlsx', index=False)
df_entidades.to_excel('entidades.xlsx', index=False)



print("¡Proceso completado con éxito!")