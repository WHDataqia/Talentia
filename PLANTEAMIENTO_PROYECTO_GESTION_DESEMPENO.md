# Proyecto De Gestion De Desempeno

## Introduccion
Antes de este proyecto, la evaluacion de desempeno se realizaba con documentos de Word. Cada evaluacion se hacia por separado y se guardaba en carpetas o se compartia por correo. Este metodo funcionaba, pero con el tiempo se volvio lento y dificil de controlar.

Para mejorar esta situacion, se desarrollo un software que permite registrar, consultar y dar seguimiento a las evaluaciones en un solo lugar.

Este trabajo se enmarca dentro del ciclo de vida del desarrollo de software (SDLC), siguiendo una secuencia ordenada de fases para asegurar que la solucion fuera util, estable y sostenible.

## Planteamiento Del Problema
El proceso anterior presentaba varias dificultades:
- Los archivos estaban dispersos y no habia una fuente unica de informacion.
- Tomaba mucho tiempo consolidar resultados de varios colaboradores.
- Era facil cometer errores al copiar datos o hacer calculos manuales.
- No habia trazabilidad clara del historial por periodos.
- El proceso se complicaba cuando muchas personas evaluaban al mismo tiempo.

## Objetivo General
Disenar e implementar una solucion digital para gestionar las evaluaciones de desempeno de forma ordenada, rapida y confiable.

## Objetivos Especificos
- Centralizar la informacion de evaluaciones en una sola plataforma.
- Reducir tiempos del proceso que antes era manual.
- Mejorar la consulta del historial y comparacion por periodos.
- Disminuir errores operativos en el registro de informacion.
- Permitir que varios usuarios trabajen sin afectar la estabilidad del sistema.

## Alcance
Este proyecto cubre:
- Registro de evaluaciones por competencias.
- Consulta de historial de evaluaciones.
- Vista de detalle por colaborador y periodo.
- Manejo de perfiles de usuario segun rol.
- Preparacion para uso en entorno servidor.

No incluye, por ahora, modulos de nomina ni integraciones externas con otros sistemas institucionales.

## Enfoque SDLC
El proyecto se organizo segun el SDLC, de la siguiente manera:
- Planificacion: comprender el problema y definir objetivos.
- Diseno: estructurar la solucion y la forma de uso.
- Implementacion: construir el sistema.
- Pruebas: validar funcionamiento y corregir fallas.
- Despliegue: preparar y poner en marcha en servidor.
- Mantenimiento: mejorar, monitorear y sostener la operacion.

## Marco Metodologico (Por Fases)

### 1. Planificacion
En esta fase se identifico el problema del proceso en Word y se definio el alcance del software.

Actividades principales:
- **Recoleccion de necesidades:** Se realizaron conversaciones con los responsables del proceso para entender como se hacian las evaluaciones, cuanto tiempo tomaban y que partes resultaban mas dificiles o propensas a errores.
- **Identificacion de fallas del proceso manual:** Se documentaron los problemas concretos: archivos dispersos en carpetas locales, inconsistencias al consolidar resultados entre evaluadores y ausencia de un historial centralizado por periodos.
- **Definicion de metas del proyecto:** Con base en los problemas identificados, se establecieron los objetivos que el sistema debia cumplir: centralizar la informacion, reducir los tiempos del proceso y garantizar trazabilidad por periodo y colaborador.

Resultado:
Se construyo una ruta clara de trabajo para el desarrollo, con alcance definido y prioridades establecidas.

Evidencia visual sugerida:
- Figura 1. Flujo del proceso manual en Word (diagrama o esquema).
- Figura 2. Mapa de problemas detectados en el proceso anterior.

### 2. Diseno
Se organizo como iba a funcionar el sistema para que fuera facil de usar.

Actividades principales:
- **Diseno de pantallas principales:** Se definieron las vistas esenciales del sistema: inicio de sesion, listado de evaluaciones, formulario de evaluacion por competencias, historial y detalle por colaborador. Cada pantalla se penso en funcion del flujo de trabajo real del evaluador.
- **Definicion de roles de usuario:** Se identificaron dos niveles de acceso: administrador, con capacidad de gestionar empleados, periodos y reportes; y evaluador, que solo accede a las evaluaciones que le corresponden.
- **Estructura de la informacion a manejar:** Se modelo la base de datos para soportar evaluaciones vinculadas a empleados, competencias con puntajes por nivel y planes de formacion. Se eligio PostgreSQL por su capacidad para manejar multiples conexiones simultaneas.

Resultado:
Se obtuvo un modelo funcional y entendible, con las bases tecnicas necesarias para iniciar la implementacion.

Evidencia visual sugerida:
- Figura 3. Mockup o borrador de la pantalla de inicio de sesion.
- Figura 4. Mockup de la pantalla de evaluacion por competencias.
- Figura 5. Propuesta visual del historial de evaluaciones.

### 3. Implementacion
Se construyo el software y se conecto con la base de datos.

Actividades principales:
- **Desarrollo de formularios y vistas:** Se implementaron en HTML, CSS y JavaScript las pantallas definidas en la fase de diseno. Se aplicaron estilos visuales consistentes y se garantizo la navegacion entre vistas sin recargas innecesarias.
- **Programacion de funciones para crear, consultar y eliminar evaluaciones:** Se desarrollo la API REST con Python y Flask, incluyendo endpoints para el ciclo completo de una evaluacion: creacion, consulta por filtros, visualizacion de detalle y eliminacion. Se implemento autenticacion por token JWT para proteger cada operacion.
- **Ajustes para mejorar velocidad y estabilidad:** Se migraron las consultas de PostgreSQL a PostgreSQL, se corrigieron errores de compatibilidad en las instrucciones SQL y se implemento un pool de conexiones (entre 5 y 30 conexiones simultaneas) para soportar multiples usuarios sin degradar el rendimiento.

Resultado:
Sistema operativo y estable para gestionar el proceso de desempeno de forma digital.

Evidencia visual sugerida:
- Figura 6. Pantalla real de inicio de sesion.
- Figura 7. Pantalla real de registro/edicion de evaluacion.
- Figura 8. Pantalla real de historial y detalle de evaluacion.

### 4. Pruebas
Se verifico que el sistema funcionara correctamente bajo distintos escenarios de uso.

Actividades principales:
- **Pruebas de ingreso y flujo de evaluacion:** Se valido que el inicio de sesion, la creacion de una evaluacion y el guardado de competencias y plan de formacion funcionaran de forma correcta y sin perdida de datos.
- **Pruebas de historial y detalle:** Se verifico que el historial mostrara las evaluaciones filtradas por empleado y periodo, y que el detalle cargara la informacion completa sin errores ni datos mezclados entre registros.
- **Validacion de tiempos de respuesta:** Se ejecutaron pruebas de carga con hasta 180 solicitudes simultaneas usando 30 hilos concurrentes, obteniendo tiempos promedio de respuesta por debajo de los 75 milisegundos, lo que confirma la estabilidad del sistema bajo uso intensivo.
- **Correccion de errores detectados:** Durante las pruebas se identificaron errores en consultas SQL que usaban sintaxis de PostgreSQL incompatible con PostgreSQL. Cada error fue corregido y re-probado hasta obtener un comportamiento correcto y consistente.

Resultado:
Mayor estabilidad, tiempos de respuesta aceptables y mejor experiencia de uso para el usuario final.

Evidencia visual sugerida:
- Figura 9. Captura de prueba funcional exitosa (creacion y consulta de evaluacion).
- Figura 10. Evidencia de pruebas de carga/concurrencia (resumen de tiempos).
- Figura 11. Captura de validaciones o correcciones aplicadas tras pruebas.

### 5. Despliegue
Se preparo el paso del entorno de desarrollo al entorno de servidor para uso en produccion.

Actividades principales:
- **Configuracion del ambiente en Linux:** Se definieron los pasos para instalar Python, las dependencias del sistema y el servidor de aplicaciones (Waitress) en un entorno Ubuntu/Debian, incluyendo la configuracion de un servicio systemd para que la aplicacion se inicie automaticamente con el servidor.
- **Preparacion de variables de entorno:** Se establecieron las variables de configuracion necesarias para produccion, como la cadena de conexion a PostgreSQL, el numero de hilos del servidor y los parametros del pool de conexiones, separadas del codigo fuente para mayor seguridad.
- **Conexion de la aplicacion con base de datos en servidor:** Se verifico que la aplicacion pudiera conectarse correctamente a PostgreSQL en el entorno de servidor, ejecutando consultas de validacion y confirmando que los datos migrados desde el entorno de desarrollo estuvieran integros.

Resultado:
Base tecnica lista para operar en ambiente productivo con disponibilidad continua.

Evidencia visual sugerida:
- Figura 12. Servicio de aplicacion activo en servidor (systemd en estado running).
- Figura 13. Aplicacion accesible desde navegador en entorno de servidor.
- Figura 14. Verificacion de conexion a PostgreSQL en ambiente productivo.

### 6. Mantenimiento
Se definieron actividades para sostener la calidad y disponibilidad del sistema a lo largo del tiempo.

Actividades principales:
- **Seguimiento de rendimiento:** Se habilitaron mecanismos de monitoreo del estado del servidor y de los tiempos de respuesta de la API, permitiendo detectar degradaciones antes de que afecten a los usuarios.
- **Respaldo de datos:** Se establecio una rutina de copias de seguridad de la base de datos PostgreSQL, asegurando que la informacion historica de evaluaciones pueda recuperarse ante cualquier fallo.
- **Correccion de incidencias:** Se definio un proceso para registrar y atender errores reportados por usuarios, priorizando los que afecten la operacion critica del sistema.
- **Mejoras continuas segun necesidades:** Se identificaron posibles ampliaciones futuras como modulos de reportes descargables, integraciones con otros sistemas institucionales y ajustes al modelo de competencias segun la evolucion de los procesos de la organizacion.

Resultado:
Sistema mas confiable, sostenible y preparado para crecer con las necesidades de la organizacion.

Evidencia visual sugerida:
- Figura 15. Registro de monitoreo de estado o tiempos de respuesta.
- Figura 16. Evidencia de respaldo de base de datos.
- Figura 17. Ejemplo de incidencia atendida y mejora aplicada.

## Conclusiones
El cambio de un proceso manual en Word a una plataforma digital soluciono problemas de orden, tiempo y control. Ahora la gestion de desempeno es mas clara, mas rapida y con mejor seguimiento para la toma de decisiones.

En terminos academicos y practicos, el proyecto demuestra que una solucion sencilla, bien planificada y bien probada puede mejorar significativamente un proceso institucional.

