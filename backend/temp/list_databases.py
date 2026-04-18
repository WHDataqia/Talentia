#!/usr/bin/env python3
"""
Script para listar bases de datos en PostgreSQL
"""
import psycopg
import os
from dotenv import load_dotenv

load_dotenv()

try:
    # Conectar a postgres (BD default)
    conn = psycopg.connect("postgresql://postgres@localhost:5432/postgres")
    cursor = conn.cursor()
    
    cursor.execute("SELECT datname FROM pg_database WHERE datistemplate = false;")
    databases = cursor.fetchall()
    
    print("[*] Bases de datos disponibles:")
    for db in databases:
        print(f"  - {db[0]}")
    
    cursor.close()
    conn.close()
    
except Exception as e:
    print(f"[✗] Error: {e}")
    exit(1)
