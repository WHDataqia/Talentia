#!/usr/bin/env python3
"""
Script para limpiar la base de datos Talentia_db
"""
import psycopg
import os
from dotenv import load_dotenv

load_dotenv()

try:
    print("[*] Conectando a PostgreSQL...")
    # Conectar a postgres DB para poder eliminar talentia_db
    conn = psycopg.connect("postgresql://postgres@localhost:5432/postgres")
    conn.autocommit = True
    cursor = conn.cursor()
    
    print("[*] Terminando conexiones a talentia_db...")
    cursor.execute("""
        SELECT pg_terminate_backend(pg_stat_activity.pid)
        FROM pg_stat_activity
        WHERE pg_stat_activity.datname = 'talentia_db'
        AND pid <> pg_backend_pid();
    """)
    
    print("[*] Eliminando base de datos talentia_db...")
    cursor.execute("DROP DATABASE IF EXISTS talentia_db;")
    
    print("[*] Creando base de datos talentia_db...")
    cursor.execute("CREATE DATABASE talentia_db;")
    
    print("[✓] Base de datos limpiada y recreada exitosamente")
    
    cursor.close()
    conn.close()
    
except Exception as e:
    print(f"[✗] Error: {e}")
    exit(1)
