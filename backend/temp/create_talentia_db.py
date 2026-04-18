#!/usr/bin/env python3
"""
Script para crear la base de datos Talentia_db en PostgreSQL
"""
import psycopg
import os
from dotenv import load_dotenv

load_dotenv()

conf_url = os.getenv('DATABASE_URL', '')

# Extraer conexión a postgres (sin especificar BD)
base_url = conf_url.rsplit('/', 1)[0] + '/postgres'

try:
    print("[*] Conectando a PostgreSQL (base de datos default)...")
    conn = psycopg.connect(base_url)
    conn.autocommit = True
    cursor = conn.cursor()
    
    print("[*] Creando base de datos talentia_db...")
    cursor.execute("CREATE DATABASE talentia_db;")
    
    print("[✓] Base de datos talentia_db creada exitosamente")
    
    cursor.close()
    conn.close()
    
except psycopg.Error as e:
    if "already exists" in str(e):
        print("[!] La base de datos talentia_db ya existe")
    else:
        print(f"[✗] Error: {e}")
        exit(1)
except Exception as e:
    print(f"[✗] Error: {e}")
    exit(1)
