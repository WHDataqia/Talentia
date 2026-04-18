# 🔐 Test Fase 1 & 2 - SECURITY_HARDENING

## Activar Hardening en Windows (test local)

```powershell
# En PowerShell, desde raíz de proyecto:
$env:SECURITY_HARDENING=1
$env:FLASK_DEBUG=0
python .\backend\app.py
```

Servidor debe iniciar en `http://localhost:5000`

---

## Matriz de Pruebas

### ✅ Debe permitir (público)
- [ ] **Login**: Acceso a `http://localhost:5000/login.html` SIN token → OK, carga pantalla
- [ ] **Autoevaluación**: Acceso a `http://localhost:5000/autoevaluacion.html` SIN token → OK, carga pantalla
- [ ] **Health API**: `GET /api/health` SIN token → 200 OK
- [ ] **Login API**: `POST /api/login` SIN token → Acepta POST (validará credenciales)
- [ ] **Auth Empleado**: `POST /api/auth/empleado` SIN token → Acepta POST

### ❌ Debe RECHAZAR (protegido - requiere JWT)
- [ ] **Index**: Acceso a `http://localhost:5000/index.html` SIN token → Redirige a `/login.html`
- [ ] **Empleados**: Acceso a `http://localhost:5000/empleados.html` SIN token → Redirige a `/login.html`
- [ ] **Evaluación Competencias**: Acceso a `http://localhost:5000/evaluacion-competencias.html` SIN token → Redirige a `/login.html`
- [ ] **API Empleados**: `GET /api/empleados` SIN token → 401 Unauthorized

### ✅ Flujos de Usuario (CON login exitoso)
1. **Admin Panel**
   - [ ] Login exitoso (email corporativo + contraseña)
   - [ ] Token recibido y almacenado
   - [ ] Acceso a `/admin.html` funciona
   - [ ] Ver tabla de empleados, crear evaluación

2. **Jefe Evalúa Subordinados**
   - [ ] Login (usuario jefe)
   - [ ] Navegar a `/evaluacion-competencias.html`
   - [ ] Seleccionar subordinado
   - [ ] Completar evaluación y guardar
   - [ ] Ver historial de evaluaciones

3. **Empleado Autoevalúa**
   - [ ] Acceso público a `/autoevaluacion.html`
   - [ ] Ingresar cédula + contraseña (o código de acceso si aplica)
   - [ ] Completar autoevaluación
   - [ ] Guardar exitosamente

4. **Admin Genera Código de Acceso**
   - [ ] Login admin
   - [ ] Ir a `/admin-maestras.html` (o sección de códigos)
   - [ ] Generar código para empleado
   - [ ] Usar código en `/autoevaluacion.html` (flujo público)

---

## Resultados Esperados

- **Sin errores 404/500**: Todos los flujos funcionan sin crashes
- **Redirecciones funcionales**: URLs protegidas redirigen a login cuando no hay token
- **Tokens válidos**: Usuarios autenticados acceden a todo sin problemas
- **API JSON vigente**: Las respuestas de API siguen siendo iguales

---

## Rollback (si algo se rompe)

```powershell
# Apagar hardening
$env:SECURITY_HARDENING=0
$env:FLASK_DEBUG=0
python .\backend\app.py
```

Todo vuelve al estado anterior (sin protección de HTML).

---

## Notas Técnicas

- `SECURITY_HARDENING=1` activa:
  - Decorator `@jwt_required_if_hardening_enabled()` en 10 rutas API sensibles
  - Protección de HTML internos en `serve_file()` (excepto login y autoevaluación)
  
- Cookie de sesión + JWT:
  - Frontend almacena token en `localStorage` o cookie
  - Cada request a API incluye `Authorization: Bearer <token>`
  - HTML internos validan token al cargar (redirigen si no hay)

- **Base de datos sin cambios**: Estructura BD sigue igual, solo control de acceso

---

## ¿Todo OK? Siguiente Paso

Una vez validado en Windows:
1. Copiar proyecto a Ubuntu/Linux
2. Crear `.env` con `SECURITY_HARDENING=1`
3. Ejecutar en systemd con Nginx como reverse proxy
