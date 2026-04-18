import pandas as pd
from sqlalchemy import create_engine

# 1. Cargar el archivo original
file_path = 'BASE BLUEDOORS.xlsx'
df = pd.read_excel(file_path)

# Lista de columnas que ya separaste en otros archivos/tablas
columnas_a_eliminar = ['CARGO', 'CENTRO DE COSTO', 'RAZON SOCIAL', 'NIT']

# Creamos la base principal "limpia"
# axis=1 indica que queremos borrar COLUMNAS (no filas)
df_principal = df.drop(columns=columnas_a_eliminar)

print("Columnas restantes en la base principal:")
print(df_principal.columns.tolist())
#imprimir todos los datos para verificar que se han eliminado correctamente las columnas
print(df_principal)


df_principal.to_excel('base_principal.xlsx', index=False)
print("Base principal exportada a 'base_principal.xlsx'")