# Estructura de Archivos de ProducciÃ³n

**Limpieza realizada:** 61 archivos de desarrollo/testing eliminados (10-Mar-2026)

## Backend (12 archivos esenciales)

### Core del sistema
- `app.py` - Servidor Flask principal con todas las rutas API
- `auth.py` - AutenticaciÃ³n JWT y control de permisos
- `db_helpers.py` - Funciones auxiliares para base de datos

### MÃ³dulo de competencias
- `competencias_db.py` - CRUD de competencias
- `competencias_modelo.py` - Modelo de datos de competencias
- `rutas_competencias.py` - Endpoints especÃ­ficos de competencias
- `rutas_competencias.py` - Endpoints especÃ­ficos de competencias
- `actualizar_empleados.py` - Carga masiva desde Excel (migraciones periÃ³dicas)

### Migraciones y configuraciÃ³n
- `migrations.py` - Sistema de migraciones de esquema
- `migrate_to_postgres.py` - Script para migrar a PostgreSQL
- `requirements.txt` - Dependencias Python
- `.env` - Variables de entorno (SECRET_KEY, DB_PATH, etc.)

### Base de datos
- `talentia_db` - PostgreSQL con todos los datos (evaluaciones, empleados, etc.)

## Frontend (17 archivos)

### PÃ¡ginas HTML (11)
- `login.html` - PÃ¡gina de inicio de sesiÃ³n
- `index.html` - Dashboard principal con selector de evaluaciones
- `historial.html` - Listado de evaluaciones con filtros
- `detalle-evaluacion.html` - Vista detallada de una evaluaciÃ³n
- `informe-comparativo.html` - ComparaciÃ³n evaluaciÃ³n vs autoevaluaciÃ³n
- `evaluacion-competencias.html` - Formulario crear evaluaciÃ³n (jefe)
- `autoevaluacion.html` - Formulario autoevaluaciÃ³n (empleado)
- `crear-evaluacion.html` - PÃ¡gina de creaciÃ³n de evaluaciÃ³n
- `empleados.html` - GestiÃ³n de empleados
- `admin.html` - Panel de administraciÃ³n
- `admin-maestras.html` - GestiÃ³n de tablas maestras

### JavaScript (5)
- `keep-alive.js` - Sistema de timeouts y reintentos (60s reads, 120s writes)
- `competencia-evaluador.js` - GestiÃ³n de formularios de evaluaciÃ³n
- `config-loader.js` - Carga de configuraciÃ³n desde config.json

### CSS (2)
- `styles.css` - Estilos globales
- `competencia-estilos.css` - Estilos especÃ­ficos del mÃ³dulo de competencias

### ConfiguraciÃ³n
- `config.json` - URLs de API y configuraciÃ³n frontend

## Otros archivos productivos

### DocumentaciÃ³n
- [README.md](README.md) - GuÃ­a principal del proyecto
- [START_HERE.md](START_HERE.md) - GuÃ­a de inicio rÃ¡pido
- [backend/GUIA_CARGA_EMPLEADOS.md](backend/GUIA_CARGA_EMPLEADOS.md) - CÃ³mo cargar empleados desde Excel

### Scripts de utilidad
- `probar_servidor.sh` - Script para probar el servidor en Linux
- `verificar_migracion.sh` - Validar migraciÃ³n exitosa
- `backup_bd.sh` - Backup de base de datos

### Plantillas de configuraciÃ³n
- `.env.ejemplo` - Plantilla para variables de entorno
- `.env.example.postgres` - Plantilla para configuraciÃ³n PostgreSQL

## Carpetas
- `Logo/` - Assets de imÃ¡genes/logos
- `ETL/` - Scripts de extracciÃ³n, transformaciÃ³n y carga de datos
- `backend/` - Todo el cÃ³digo del servidor
- `.venv/` o `venv/` - Entorno virtual Python (no subir a producciÃ³n)

---

## Archivos eliminados (61 total)

### Scripts de diagnÃ³stico/testing (8)
- diagnosticar_ngrok.py, diagnostico_sesiones_multiples.py, medir_latencia.py
- test-historial-debug.html, test_token_invalidation.py, trace_login.py
- LIMPIAR_CACHE.bat, INICIAR_SERVIDOR.bat

### DocumentaciÃ³n de desarrollo (13)
- ANALISIS_VIABILIDAD_PRODUCCION.md, CREDENCIALES_PRUEBA.md
- INSTRUCCIONES_PRUEBA_5_USUARIOS.md, OPTIMIZACION_NGROK.md
- SESIONES_CONTROL_MEJORADO.md, SOLUCION_CONTROL_SESIONES.md
- SOLICITUD_AUTORIZACION_*.html/md, CHECKLIST_MIGRACION.md
- DIA_1_MIGRACION_UBUNTU.md, GUIA_RAPIDA_UBUNTU.md
- INDICE_MIGRACION.md, README_MIGRACION_UBUNTU.md

### Scripts de mantenimiento backend (38)
- actualizar_*.py (datos, empleados, jefes, maestras, descripciones)
- agregar_control_sesiones.py, asignar_contrasenas*.py
- buscar_o_crear_admin.py, cargar_datos_excel.py, check_contraseÃ±as.py
- crear_*.py (admin, bd_completa, indices)
- debug_ariza_observaciones.py, diagnostico_*.py (historial, velocidad)
- limpiar_sesiones.py, listar_*.py (admins, credenciales, empleados, tablas)
- optimizar_bd.py, recrear_*.py (bd, tablas_sin_huecos)
- recuperar_relaciones.py, resetear_ids.py, reset_admin_password.py
- test_*.py (historial_endpoint, karen_historial)
- validar_postgres.py, ver_datos.py
- verificar_*.py (admin, admin_columnas, bd_completa, sesiones, todas_bd, usuarios_prueba)

### Backups de BD daÃ±adas (2)
- backend/talentia_db.backup
- backend/talentia_db.BAD

---

## PreparaciÃ³n para producciÃ³n

Para desplegar:
1. Copiar solo archivos listados arriba (sin .venv, __pycache__, etc.)
2. Configurar `.env` con variables de producciÃ³n
3. Ejecutar `pip install -r backend/requirements.txt`
4. Iniciar con Gunicorn/Waitress: `gunicorn -w 4 -b 0.0.0.0:5000 backend.app:app`

