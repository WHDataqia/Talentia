# Talentia - Sistema de EvaluaciÃ³n de DesempeÃ±o

## DescripciÃ³n
AplicaciÃ³n web completa para la evaluaciÃ³n y gestiÃ³n del desempeÃ±o de empleados con backend en Python, base de datos PostgreSQL y visualizaciÃ³n mediante grÃ¡ficos de araÃ±a (radar chart).

## ðŸŽ¯ CaracterÃ­sticas Principales

### âœ¨ Funcionalidades Completas
- **GestiÃ³n de Empleados**: CRUD completo de empleados con bÃºsqueda
- **Evaluaciones DinÃ¡micas**: Formularios interactivos para crear evaluaciones
- **GrÃ¡fico de AraÃ±a Interactivo**: VisualizaciÃ³n de 6 competencias clave
- **Historial Completo**: Seguimiento de evaluaciones por empleado y perÃ­odo
- **GrÃ¡ficos de Tendencia**: AnÃ¡lisis temporal del desempeÃ±o
- **Base de Datos**: Persistencia de datos con PostgreSQL
- **API REST**: Backend completo en Python/Flask
- **DiseÃ±o Responsive**: Adaptable a mÃ³viles, tablets y desktop
- **ExportaciÃ³n**: ImpresiÃ³n de reportes

### ðŸ“Š Competencias Evaluadas
1. Trabajo en Equipo
2. Liderazgo
3. ComunicaciÃ³n
4. ResoluciÃ³n de Problemas
5. Creatividad
6. OrientaciÃ³n a Resultados

### ðŸŽ¨ Niveles de DesempeÃ±o
- **Excelente**: 90-100 puntos (Verde)
- **Bueno**: 80-89 puntos (Azul)
- **Satisfactorio**: 70-79 puntos (Amarillo)
- **Necesita Mejora**: < 70 puntos (Rojo)

## ðŸš€ InstalaciÃ³n y ConfiguraciÃ³n

### Requisitos Previos
- **Python 3.8+**
- **pip** (gestor de paquetes de Python)
- Navegador web moderno

### Paso 1: Configurar el Backend

1. **Abrir PowerShell en la carpeta del proyecto**
   ```powershell
   cd c:\dataQIA\SoftRRHH\backend
   ```

2. **Crear entorno virtual**
   ```powershell
   python -m venv venv
   ```

3. **Activar entorno virtual**
   ```powershell
   .\venv\Scripts\Activate.ps1
   ```

4. **Instalar dependencias**
   ```powershell
   pip install -r requirements.txt
   ```

5. **Ejecutar el servidor**
   ```powershell
   python app.py
   ```

   El servidor estarÃ¡ en: `http://localhost:5000` ðŸŸ¢

### Paso 2: Abrir el Frontend

1. Abrir cualquiera de estos archivos en el navegador:
   - `index.html` - Ver evaluaciones (demo)
   - `empleados.html` - Gestionar empleados â­ **EMPEZAR AQUÃ**
   - `crear-evaluacion.html` - Nueva evaluaciÃ³n
   - `historial.html` - Ver historial completo

2. **O usar un servidor local (opcional):**
   ```powershell
   # Desde la carpeta raÃ­z (SoftRRHH)
   python -m http.server 8080
   ```
   Luego abrir: `http://localhost:8080`

## ðŸ“– CÃ³mo Usar la AplicaciÃ³n

### Flujo de Trabajo Recomendado

1. **Gestionar Empleados** (`empleados.html`)
   - Crear nuevos empleados
   - Editar informaciÃ³n existente
   - Buscar empleados

2. **Crear Evaluaciones** (`crear-evaluacion.html`)
   - Seleccionar empleado
   - Evaluar 6 competencias (0-100)
   - Agregar observaciones
   - El promedio se calcula automÃ¡ticamente

3. **Ver Historial** (`historial.html`)
   - Filtrar por empleado, departamento o perÃ­odo
   - Ver grÃ¡ficos de tendencia
   - Consultar evaluaciones anteriores

4. **Detalle de EvaluaciÃ³n** (`detalle-evaluacion.html`)
   - GrÃ¡fico de araÃ±a completo
   - Tabla de competencias
   - Imprimir reporte

## ðŸ“ Estructura del Proyecto

```
SoftRRHH/
â”œâ”€â”€ backend/
â”‚   â”œâ”€â”€ app.py                    # API REST con Flask
â”‚   â”œâ”€â”€ requirements.txt          # Dependencias Python
â”‚   â”œâ”€â”€ README.md                 # DocumentaciÃ³n del backend
â”‚   â””â”€â”€ talentia_db             # base de datos PostgreSQL (se crea automÃ¡ticamente)
â”‚
â”œâ”€â”€ðŸ› ï¸ TecnologÃ­as Utilizadas

### Frontend
- **HTML5**: Estructura semÃ¡ntica
- **CSS3**: Estilos modernos con gradientes y animaciones
- **JavaScript ES6**: LÃ³gica de aplicaciÃ³n y comunicaciÃ³n con API
- **Chart.js**: LibrerÃ­a para grÃ¡ficos (araÃ±a, lÃ­neas)

### Backend
- **Python 3.8+**: Lenguaje del servidor
- **Flask**: Framework web ligero
- **PostgreSQL**: Base de datos relacional
- **Flask-CORS**: Manejo de solicitudes cross-origin

## ðŸ—„ï¸ Base de Datos

### Tablas
âœ… Funcionalidades Implementadas

- [x] base de datos PostgreSQL con 3 tablas relacionales
- [x] API REST completa con Flask
- [x] CRUD de empleados
- [x] CRUD de evaluaciones
- [x] Historial de evaluaciones por empleado
- [x] GrÃ¡fico de araÃ±a interactivo
- [x] GrÃ¡fico de tendencias temporales
- [x] Filtros avanzados (empleado, departamento, perÃ­odo)
- [x] CÃ¡lculo automÃ¡tico de promedios
- [x] DiseÃ±o responsive
- [x] ImpresiÃ³n de reportes

## ðŸš§ PrÃ³ximas Mejoras Sugeridas

### Funcionalidades Pendientes
- [ ] AutenticaciÃ³n de usuarios (login/registro)
- [ ] Roles y permisos (admin, supervisor, empleado)
- [ ] EdiciÃ³n de evaluaciones existentes
- [ ] ExportaciÃ³n real a PDF con jsPDF
- [ ] ExportaciÃ³n a Excel
- [ ] Dashboard con estadÃ­sticas generales
- [ ] Notificaciones por email
- [ ] ComparaciÃ³n entre empleados
- [ðŸŽ¨ PersonalizaciÃ³n

### Cambiar Competencias
Editar en `crear-evaluacion.html` y `detalle-evaluacion.html`:
```javascript
const competencias = [
    'Tu Competencia 1',
    'Tu Competencia 2',
    // ...
];
```

### AÃ±adir Departamentos
Editar el select en `empleados.html`:
```html
<option value="Tu Departamento">Tu Departamento</option>
```

### Modificar Colores
Editar variables CSS en `styles.css`:
```css
/* Cambiar colores principales */
background: linear-gradient(135deg, #TU_COLOR_1 0%, #TU_COLOR_2 100%);
```

## âš ï¸ SoluciÃ³n de Problemas

### Error: "No se pudo conectar con el servidor"
- Verifica que el backend estÃ© ejecutÃ¡ndose en `http://localhost:5000`
## ðŸŽ“ GuÃ­a RÃ¡pida de Uso

### Para empezar desde cero:

1. **Iniciar el backend**
   ```powershell
   cd backend
   .\venv\Scripts\Activate.ps1
   python app.py
   ```

2. **Abrir `empleados.html` en el navegador**

3. **Crear algunos empleados de prueba**

4. **Ir a `crear-evaluacion.html` y crear evaluaciones**

5. **Ver el historial en `historial.html`**

## ðŸ“Š Capturas de Pantalla

- **GestiÃ³n de Empleados**: Lista completa con bÃºsqueda y acciones
- **Nueva EvaluaciÃ³n**: Sliders interactivos para cada competencia
- **Historial**: Cards con filtros y grÃ¡fico de tendencias
- **Detalle**: GrÃ¡fico de araÃ±a completo con tabla de competencias

## ðŸ¤ ContribuciÃ³n

Este es un proyecto interno. Para sugerencias o mejoras, contactar al equipo de desarrollo.

---

**VersiÃ³n**: 2.0.0 (Completa)  
**Fecha**: Enero 2026  
**Estado**: âœ… Funcional con Backend y Base de Datosno se crea
- AsegÃºrate de tener permisos de escritura en la carpeta `backend/`
- Verifica que PostgreSQL estÃ© disponible (incluido en Python)

### CORS errors en el navegador
- Flask-CORS debe estar instalado: `pip install Flask-CORS`
- Verifica que el servidor use el puerto 5000

### Los grÃ¡ficos no se muestran
- Verifica la conexiÃ³n a internet (Chart.js se carga desde CDN)
- Abre la consola del navegador (F12) para ver errores
- [ ] Implementar cachÃ© (Redis)
- [ ] Testing automatizado (pytest, Jest)
- [ ] CI/CD pipeline
- [ ] DockerizaciÃ³n
- [ ] Deploy en cloud (Azure, AWS)
- [ ] Logs y monitoreoEADME.md) para mÃ¡s detalles.bales
â”œâ”€â”€ app.js                        # LÃ³gica del demo inicial
â””â”€â”€ README.md                     # Este archivo
```

## TecnologÃ­as Utilizadas

- **HTML5**: Estructura semÃ¡ntica
- **CSS3**: Estilos modernos con gradientes y animaciones
- **JavaScript ES6**: LÃ³gica de aplicaciÃ³n
- **Chart.js**: LibrerÃ­a para grÃ¡ficos de araÃ±a

## PrÃ³ximas Mejoras Sugeridas

### Funcionalidades
- [ ] ConexiÃ³n a base de datos (backend)
- [ ] AutenticaciÃ³n de usuarios
- [ ] EdiciÃ³n de evaluaciones en lÃ­nea
- [ ] ComparaciÃ³n de perÃ­odos (histÃ³rico)
- [ ] ExportaciÃ³n real a PDF con jsPDF
- [ ] GrÃ¡ficos adicionales (barras, lÃ­neas)
- [ ] Notificaciones y alertas
- [ ] Sistema de comentarios

### Competencias Adicionales
- [ ] Adaptabilidad
- [ ] GestiÃ³n del Tiempo
- [ ] Conocimientos TÃ©cnicos
- [ ] AtenciÃ³n al Cliente
- [ ] PlanificaciÃ³n EstratÃ©gica

### Integraciones
- [ ] API REST para datos
- [ ] IntegraciÃ³n con sistemas de RRHH existentes
- [ ] ExportaciÃ³n a Excel
- [ ] EnvÃ­o de reportes por email

## PersonalizaciÃ³n

### Cambiar Competencias
Editar en `app.js` el array de competencias:
```javascript
labels: ['Nueva Competencia 1', 'Competencia 2', ...]
```

### AÃ±adir MÃ¡s Empleados
Agregar objetos al array `employeesData` en `app.js`

### Modificar Colores
Editar las variables de color en `styles.css` y los colores del grÃ¡fico en `app.js`

## Soporte de Navegadores

- âœ… Chrome/Edge (versiÃ³n 90+)
- âœ… Firefox (versiÃ³n 88+)
- âœ… Safari (versiÃ³n 14+)
- âœ… Opera (versiÃ³n 76+)

## Licencia

Proyecto piloto para evaluaciÃ³n interna.

## Contacto

Para consultas sobre funcionalidades adicionales o personalizaciones, contactar al equipo de desarrollo.

---

**VersiÃ³n**: 1.0.0 (Piloto)  
**Fecha**: Enero 2026

