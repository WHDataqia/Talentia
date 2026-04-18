// Módulo de Competencias - Frontend
// Gestiona la visualización y evaluación de competencias

class CompetenciaEvaluador {
    constructor() {
        this.competencias = [];
        this.nivelOcupacionalIndex = 0;
        this.evaluacionesAlmacenadas = {};
        this.enviando = false;
        this.autoguardadoInicializado = false;
        this.intervaloAutoguardado = null;
    }

    esAutoevaluacion() {
        return typeof window !== 'undefined' && window.AUTOEVALUACION === true;
    }

    obtenerContextoBorrador() {
        const empleadoId = document.getElementById('empleado-id')?.value;
        const periodo = document.getElementById('periodo-select')?.value;
        if (!empleadoId || !periodo) return null;
        return { empleadoId, periodo };
    }

    obtenerClaveBorrador() {
        if (!this.esAutoevaluacion()) return null;
        const contexto = this.obtenerContextoBorrador();
        if (!contexto) return null;
        return `autoeval_borrador_${contexto.empleadoId}_${contexto.periodo}`;
    }

    construirBorrador() {
        if (!this.esAutoevaluacion()) return null;

        const contexto = this.obtenerContextoBorrador();
        if (!contexto) return null;

        const calificaciones = {};
        const radiosSeleccionados = document.querySelectorAll('input[type="radio"][name^="calif-"]:checked');
        radiosSeleccionados.forEach((radio) => {
            calificaciones[radio.name] = radio.value;
        });

        const observaciones = {};
        const camposObservaciones = document.querySelectorAll('textarea[id^="observaciones-"]');
        camposObservaciones.forEach((textarea) => {
            observaciones[textarea.id] = textarea.value || '';
        });

        const comentariosGenerales = document.getElementById('comentariosGenerales')?.value || '';

        return {
            version: 1,
            empleadoId: contexto.empleadoId,
            periodo: contexto.periodo,
            nivelOcupacionalIndex: this.nivelOcupacionalIndex,
            calificaciones,
            observaciones,
            comentariosGenerales,
            updatedAt: new Date().toISOString()
        };
    }

    guardarBorrador() {
        const key = this.obtenerClaveBorrador();
        if (!key) return;

        const borrador = this.construirBorrador();
        if (!borrador) return;

        try {
            localStorage.setItem(key, JSON.stringify(borrador));
        } catch (error) {
            console.warn('No se pudo guardar borrador en localStorage:', error);
        }
    }

    leerBorrador() {
        const key = this.obtenerClaveBorrador();
        if (!key) return null;
        try {
            const raw = localStorage.getItem(key);
            return raw ? JSON.parse(raw) : null;
        } catch (error) {
            console.warn('No se pudo leer borrador de localStorage:', error);
            return null;
        }
    }

    limpiarBorrador() {
        const key = this.obtenerClaveBorrador();
        if (!key) return;
        try {
            localStorage.removeItem(key);
        } catch (error) {
            console.warn('No se pudo limpiar borrador de localStorage:', error);
        }
    }

    restaurarBorradorSiExiste() {
        const borrador = this.leerBorrador();
        if (!borrador) return;

        if (Number.isInteger(borrador.nivelOcupacionalIndex)) {
            this.setNivelOcupacional(borrador.nivelOcupacionalIndex);
        }

        // Esperar al renderizado final para aplicar valores sobre el DOM vigente.
        setTimeout(() => {
            Object.entries(borrador.calificaciones || {}).forEach(([name, value]) => {
                const radio = document.querySelector(`input[name="${name}"][value="${value}"]`);
                if (radio && !radio.disabled) {
                    radio.checked = true;
                }
            });

            Object.entries(borrador.observaciones || {}).forEach(([id, value]) => {
                const textarea = document.getElementById(id);
                if (textarea && !textarea.disabled) {
                    textarea.value = value;
                }
            });

            const comentarios = document.getElementById('comentariosGenerales');
            if (comentarios && !comentarios.disabled) {
                comentarios.value = borrador.comentariosGenerales || '';
            }

            alert('Se recuperó un borrador de autoevaluación guardado automáticamente.');
        }, 0);
    }

    inicializarAutoguardado() {
        if (!this.esAutoevaluacion() || this.autoguardadoInicializado) return;

        const handler = (event) => {
            const target = event.target;
            if (!target) return;
            const esCampoCalificacion = target.matches('input[type="radio"][name^="calif-"]');
            const esObservacion = target.matches('textarea[id^="observaciones-"]');
            const esComentarioGeneral = target.id === 'comentariosGenerales';
            if (esCampoCalificacion || esObservacion || esComentarioGeneral) {
                this.guardarBorrador();
            }
        };

        document.addEventListener('change', handler, true);
        document.addEventListener('input', handler, true);

        this.intervaloAutoguardado = setInterval(() => {
            this.guardarBorrador();
        }, 15000);

        this.autoguardadoInicializado = true;
    }

    hayEmpleadoSeleccionado() {
        const esAutoevaluacion = typeof window !== 'undefined' && window.AUTOEVALUACION === true;

        if (esAutoevaluacion) {
            const empleadoHidden = document.getElementById('empleado-id');
            return Boolean(empleadoHidden && empleadoHidden.value);
        }

        const empleadoSelect = document.getElementById('empleado-select');
        return Boolean(empleadoSelect && empleadoSelect.value);
    }

    // Inicializar el evaluador con todas las competencias
    inicializarCompetencias(competenciasData) {
        this.competencias = competenciasData || [];
        this.renderizarCompetencias();
        this.inicializarAutoguardado();
        this.restaurarBorradorSiExiste();
    }

    setNivelOcupacional(index) {
        console.log('🔄 CAMBIO DE NIVEL:');
        console.log('  Índice anterior:', this.nivelOcupacionalIndex);
        console.log('  Índice nuevo:', index);
        
        this.nivelOcupacionalIndex = index;
        
        // Verificar descriptor de primera competencia
        if (this.competencias && this.competencias.length > 0) {
            const primeraComp = this.competencias[0];
            const descriptor = primeraComp.descriptores?.[index];
            console.log(`  Competencia: ${primeraComp.nombre}`);
            console.log(`  Descriptor: ${descriptor?.rol || 'NO ENCONTRADO'}`);
            console.log(`  Comportamientos para este nivel:`, descriptor?.comportamientos || []);
        }
        
        this.renderizarCompetencias();
        console.log('✅ Re-renderizado completado');
    }

    // Renderizar la interfaz de evaluación de todas las competencias
    renderizarCompetencias() {
        if (!this.competencias || this.competencias.length === 0) return;

        const container = document.getElementById('competencia-container');
        if (!container) return;

        const html = this.competencias.map((competencia) => {
            const descriptor = competencia.descriptores?.[this.nivelOcupacionalIndex];
            const descriptorIndex = this.nivelOcupacionalIndex;

            if (!descriptor) {
                return `
                    <div class="competencia-evaluacion">
                        <div class="competencia-header">
                            <h2>${competencia.nombre}</h2>
                            <p class="competencia-descripcion">${competencia.descripcion}</p>
                        </div>
                        <div class="error">No hay datos para este nivel ocupacional.</div>
                    </div>
                `;
            }

            return `
                <div class="competencia-evaluacion">
                    <div class="competencia-header">
                        <h2>${competencia.nombre}</h2>
                        <p class="competencia-descripcion">${competencia.descripcion}</p>
                    </div>

                    <div class="descriptores-container">
                        ${this.renderizarDescriptor(descriptor, competencia.id, descriptorIndex)}
                    </div>
                </div>
            `;
        }).join('') + `
            <div class="evaluacion-general">
                <div class="comentarios-generales">
                    <label for="comentariosGenerales">Comentarios generales:</label>
                    <textarea id="comentariosGenerales" rows="3" placeholder="Comentarios"></textarea>
                </div>
                <button id="btnGuardarEvaluacion" class="btn-guardar" onclick="competenciaEvaluador.guardarEvaluacion()">
                    Guardar Evaluación
                </button>
            </div>
        `;

        container.innerHTML = html;

        // Reaplicar el bloqueo si existe una evaluación duplicada
        if (typeof window !== 'undefined' && window.EVALUACION_DUPLICADA && typeof setEstadoValidacion === 'function') {
            // Usar setTimeout para asegurar que el DOM esté actualizado
            setTimeout(() => {
                const aviso = document.getElementById('validacion-periodo');
                const mensaje = aviso ? aviso.textContent : 'Ya existe una evaluación para este período';
                setEstadoValidacion(true, mensaje);
            }, 0);
        }
    }

    // Renderizar un descriptor con sus comportamientos
    renderizarDescriptor(descriptor, competenciaId, descriptorIndex) {
        const puedeCalificar = this.hayEmpleadoSeleccionado();
        return `
            <div class="descriptor-card">
                <div class="descriptor-header">
                    <h3>${descriptor.rol}</h3>
                </div>

                <div class="comportamientos">
                    ${descriptor.comportamientos.map((comportamiento, idx) => `
                        <div class="comportamiento-item">
                            <div class="comportamiento-texto">
                                <span class="comportamiento-numero">${idx + 1}.</span>
                                <span class="checkbox-label">${comportamiento}</span>
                            </div>
                            <div class="comportamiento-calificacion">
                                <label>Calificación:</label>
                                <div class="puntuacion-inline">
                                    ${[1, 2, 3, 4, 5].map(valor => `
                                        <label class="radio-opcion">
                                            <input type="radio" 
                                                   name="calif-${competenciaId}-${descriptorIndex}-${idx}" 
                                                   value="${valor}"
                                                   ${puedeCalificar ? '' : 'disabled'}>
                                            <span>${valor}</span>
                                        </label>
                                    `).join('')}
                                </div>
                            </div>
                        </div>
                    `).join('')}
                </div>

                <div class="evaluacion-descriptor">
                    <label for="observaciones-${competenciaId}-${descriptorIndex}">Compromisos u observaciones generales de la competencia:</label>
                    <textarea id="observaciones-${competenciaId}-${descriptorIndex}" 
                              class="observaciones-descriptor" 
                              placeholder="Comentarios"
                              ${puedeCalificar ? '' : 'disabled'}
                              rows="3"></textarea>
                </div>
            </div>
        `;
    }

    // Renderizar escala de puntuación (1-5)
    renderizarEscala(descriptorIndex) {
        const escalas = {
            1: "No cumple",
            2: "Cumple parcialmente",
            3: "Cumple adecuadamente",
            4: "Cumple muy bien",
            5: "Cumple de manera excepcional"
        };

        return Object.entries(escalas).map(([valor, texto]) => `
            <label class="escala-opcion">
                <input type="radio" 
                       name="puntuacion-${descriptorIndex}" 
                       value="${valor}" 
                       class="puntuacion-radio">
                <span class="valor">${valor}</span>
                <span class="descripcion">${texto}</span>
            </label>
        `).join('');
    }

    // Obtener datos de evaluación del formulario
    validarCalificacionesCompletas() {
        if (!this.competencias || this.competencias.length === 0) {
            return { valido: false, mensaje: 'No hay competencias para evaluar' };
        }

        const faltantes = [];

        for (const competencia of this.competencias) {
            const descriptor = competencia.descriptores?.[this.nivelOcupacionalIndex];
            if (!descriptor) continue;

            for (let j = 0; j < descriptor.comportamientos.length; j++) {
                const calificacion = document.querySelector(
                    `input[name="calif-${competencia.id}-${this.nivelOcupacionalIndex}-${j}"]:checked`
                );

                if (!calificacion) {
                    faltantes.push({
                        competencia: competencia.nombre,
                        comportamiento: descriptor.comportamientos[j]
                    });
                }
            }
        }

        if (faltantes.length > 0) {
            let mensaje = 'Por favor complete todas las calificaciones. Faltan:\n\n';
            faltantes.forEach((item, index) => {
                if (index < 5) { // Mostrar máximo 5 ejemplos
                    mensaje += `• ${item.competencia}: ${item.comportamiento.substring(0, 60)}${item.comportamiento.length > 60 ? '...' : ''}\n`;
                }
            });
            if (faltantes.length > 5) {
                mensaje += `\n... y ${faltantes.length - 5} más.`;
            }
            return { valido: false, mensaje: mensaje };
        }

        return { valido: true };
    }

    obtenerDatosEvaluacion() {
        if (!this.competencias || this.competencias.length === 0) return null;

        const evaluacion = {
            nivel_ocupacional: this.nivelOcupacionalIndex,
            competencias: []
        };

        for (const competencia of this.competencias) {
            const descriptor = competencia.descriptores?.[this.nivelOcupacionalIndex];
            if (!descriptor) continue;

            const observaciones = document.getElementById(`observaciones-${competencia.id}-${this.nivelOcupacionalIndex}`)?.value || '';
            const comportamientos = [];

            for (let j = 0; j < descriptor.comportamientos.length; j++) {
                const calificacion = document.querySelector(
                    `input[name="calif-${competencia.id}-${this.nivelOcupacionalIndex}-${j}"]:checked`
                );

                if (calificacion) {
                    comportamientos.push({
                        texto: descriptor.comportamientos[j],
                        calificacion: parseInt(calificacion.value)
                    });
                }
            }

            if (comportamientos.length > 0) {
                const promedio = comportamientos.reduce((sum, c) => sum + c.calificacion, 0) / comportamientos.length;

                evaluacion.competencias.push({
                    competencia_id: competencia.id,
                    competencia_nombre: competencia.nombre,
                    descriptor_id: this.nivelOcupacionalIndex,
                    descriptor_nombre: descriptor.rol,
                    comportamientos: comportamientos,
                    puntuacion_promedio: promedio.toFixed(2),
                    observaciones: observaciones
                });
            }
        }

        return evaluacion;
    }

    // Guardar evaluación
    guardarEvaluacion() {
        if (this.enviando) {
            alert('La evaluación ya se está enviando. Espere un momento.');
            return;
        }

        if (!this.hayEmpleadoSeleccionado()) {
            alert('Debe seleccionar un empleado antes de calificar.');
            return;
        }

        if (typeof window !== 'undefined' && window.EVALUACION_DUPLICADA) {
            alert('Ya existe una evaluación para este período. Seleccione otro período.');
            return;
        }

        // Validar que todas las calificaciones estén completas
        const validacion = this.validarCalificacionesCompletas();
        if (!validacion.valido) {
            alert(validacion.mensaje);
            return;
        }

        const datos = this.obtenerDatosEvaluacion();
        
        if (!datos || datos.competencias.length === 0) {
            alert('Por favor, complete la evaluación');
            return;
        }

        const confirmar = confirm('Una vez guardada, la evaluación no se puede editar. ¿Desea continuar?');
        if (!confirmar) {
            return;
        }

        const empleadoSelect = document.getElementById('empleado-select');
        const empleadoHidden = document.getElementById('empleado-id');
        const empleadoId = empleadoSelect?.value || empleadoHidden?.value;
        const periodo = document.getElementById('periodo-select')?.value;

        if (!empleadoId || !periodo) {
            alert('Seleccione empleado y período');
            return;
        }

        // Detectar frecuencia automáticamente según el período
        let frecuencia = 'anual';
        if (periodo.toLowerCase().includes('semestral')) {
            frecuencia = 'semestral';
        } else if (periodo.toLowerCase().includes('anual')) {
            frecuencia = 'anual';
        } else if (periodo.match(/Q[1-4]/i)) {
            frecuencia = 'trimestral';
        } else {
            frecuencia = 'mensual';
        }

        // Obtener evaluador (jefe directo o autoevaluacion)
        const jefeDirecto = document.getElementById('jefe-directo')?.value || 'Sistema';
        const esAutoevaluacion = typeof window !== 'undefined' && window.AUTOEVALUACION === true;
        const evaluadorFinal = esAutoevaluacion ? 'Autoevaluación' : jefeDirecto;
        
        const payload = {
            empleado_id: parseInt(empleadoId, 10),
            periodo: periodo,
            evaluador: evaluadorFinal,
            frecuencia: frecuencia,
            nivel_ocupacional: this.nivelOcupacionalIndex,
            competencias: datos.competencias,
            comentarios_generales: document.getElementById('comentariosGenerales')?.value || '',
            fecha_evaluacion: new Date().toISOString().split('T')[0],
            autoevaluacion: esAutoevaluacion
        };

        // Almacenar localmente
        this.evaluacionesAlmacenadas[`nivel-${this.nivelOcupacionalIndex}`] = payload;

        // Enviar al servidor
        this.enviarAlServidor(payload);
    }

    // Enviar evaluación al servidor
    enviarAlServidor(datos) {
        console.log('📤 ENVIANDO EVALUACIÓN AL SERVIDOR...');

        if (this.enviando) {
            return;
        }
        this.enviando = true;

        const btnGuardarPrincipal = document.getElementById('btnGuardarEvaluacion');
        const btnGuardarAlternativo = document.querySelector('button[onclick="guardarEvaluacionCompleta()"]');
        [btnGuardarPrincipal, btnGuardarAlternativo].forEach(btn => {
            if (!btn) return;
            btn.disabled = true;
            btn.style.opacity = '0.6';
            btn.style.cursor = 'not-allowed';
            btn.dataset.originalText = btn.dataset.originalText || btn.textContent;
            btn.textContent = 'Guardando...';
        });
        
        const token = sessionStorage.getItem('token');
        
        fetch('/api/evaluaciones/nivel', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            timeoutMs: 120000,
            body: JSON.stringify(datos)
        })
        .then(response => {
            // Primero validar el código de estado
            if (!response.ok) {
                if (response.status === 401) {
                    const err = new Error('401_UNAUTHORIZED');
                    err.code = 401;
                    throw err;
                }
                // Si hay error, intentar obtener el mensaje de error del servidor
                return response.json().then(errorData => {
                    const mensajeError = errorData?.error || `Error ${response.status}: ${response.statusText}`;
                    throw new Error(mensajeError);
                });
            }
            return response.json();
        })
        .then(data => {
            console.log('✅ EVALUACIÓN RECIBIDA DEL SERVIDOR:', data);

            // Mostrar resumen solo cuando el backend confirma guardado
            this.mostrarResumen(datos);

            if (data?.promedio_general !== undefined) {
                alert(`Evaluación guardada correctamente. Promedio general: ${data.promedio_general}`);
            } else if (data?.message) {
                alert(data.message);
            } else {
                alert('Evaluación guardada correctamente');
            }

            if (data?.id) {
                console.log('🔓 Mostrando botón detalle...');
                this.mostrarBotonDetalle(data.id);
                console.log('🔒 INICIANDO BLOQUEO DEL FORMULARIO...');
                // Bloquear el formulario después de guardar
                this.bloquearFormularioEvaluacion();
                this.limpiarBorrador();
                console.log('✅ BLOQUEO COMPLETADO');

                // Mantener la sesión activa. El usuario decide si quiere ir al detalle
                // con el botón que se muestra después de guardar.
                return;
            }

            // Si no llegó id, permitir un nuevo intento manual
            this.enviando = false;
            [btnGuardarPrincipal, btnGuardarAlternativo].forEach(btn => {
                if (!btn) return;
                btn.disabled = false;
                btn.style.opacity = '1';
                btn.style.cursor = 'pointer';
                if (btn.dataset.originalText) {
                    btn.textContent = btn.dataset.originalText;
                }
            });
        })
        .catch(error => {
            console.error('❌ Error al enviar evaluación:', error);

            this.enviando = false;
            [btnGuardarPrincipal, btnGuardarAlternativo].forEach(btn => {
                if (!btn) return;
                btn.disabled = false;
                btn.style.opacity = '1';
                btn.style.cursor = 'pointer';
                if (btn.dataset.originalText) {
                    btn.textContent = btn.dataset.originalText;
                }
            });

            if (error && (error.name === 'AbortError' || String(error.message || '').toLowerCase().includes('aborted'))) {
                alert('❌ El guardado tardó demasiado y se canceló automáticamente. Vuelve a intentar en unos segundos.');
                return;
            }

            if (error && error.message === 'Failed to fetch') {
                alert('❌ No se pudo conectar con el servidor. Verifique la conexión/ngrok y vuelva a intentar.');
                return;
            }

            if (error && (error.code === 401 || String(error.message || '').includes('401_UNAUTHORIZED'))) {
                this.guardarBorrador();
                alert('⚠️ Su sesión expiró (401). Se guardó un borrador local automáticamente. Inicie sesión de nuevo para continuar.');
                window.location.href = 'autoevaluacion.html';
                return;
            }

            alert(`❌ Error: ${error.message}`);
        });
    }

    // Bloquear formulario después de guardar
    bloquearFormularioEvaluacion() {
        console.log('🔒 BLOQUEANDO FORMULARIO COMPLETO...');
        
        // 1. Deshabilitar campos principales
        const empleadoSelect = document.getElementById('empleado-select');
        const periodoSelect = document.getElementById('periodo-select');
        const nivelOcupacional = document.getElementById('nivel-ocupacional');
        const btnGuardar = document.querySelector('button[onclick="guardarEvaluacionCompleta()"]');

        if (empleadoSelect) {
            empleadoSelect.disabled = true;
            empleadoSelect.style.pointerEvents = 'none';
            empleadoSelect.style.opacity = '0.6';
        }
        if (periodoSelect) {
            periodoSelect.disabled = true;
            periodoSelect.style.pointerEvents = 'none';
            periodoSelect.style.opacity = '0.6';
        }
        if (nivelOcupacional) {
            nivelOcupacional.disabled = true;
            nivelOcupacional.style.pointerEvents = 'none';
            nivelOcupacional.style.opacity = '0.6';
        }
        if (btnGuardar) btnGuardar.style.display = 'none';

        // 2. Bloquear todos los inputs radio (botones de calificación 1-5)
        const radioInputs = document.querySelectorAll('input[type="radio"]');
        console.log(`📻 Encontrados ${radioInputs.length} inputs radio para deshabilitar`);
        
        radioInputs.forEach(radio => {
            // Deshabilitar el elemento
            radio.disabled = true;
            radio.style.pointerEvents = 'none';
            radio.style.cursor = 'not-allowed';
            
            // Agregar listener para evitar cambios
            radio.addEventListener('change', (e) => {
                e.preventDefault();
                e.stopPropagation();
                return false;
            }, true);
            
            radio.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                return false;
            }, true);

            radio.addEventListener('mousedown', (e) => {
                e.preventDefault();
                e.stopPropagation();
                return false;
            }, true);
            
            // Aplicar estilos al label contenedor
            const radioOpcion = radio.closest('.radio-opcion');
            if (radioOpcion) {
                radioOpcion.style.opacity = '0.5';
                radioOpcion.style.pointerEvents = 'none';
                radioOpcion.style.cursor = 'not-allowed';
                radioOpcion.addEventListener('click', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    return false;
                }, true);
            }
        });

        // BLOQUEO GLOBAL: Agregar listener global a todo el documento
        document.addEventListener('change', (e) => {
            if (e.target.closest('#competencia-container') && e.target.type === 'radio') {
                console.warn('⚠️ Intento de cambio detectado - BLOQUEADO');
                e.preventDefault();
                e.stopPropagation();
                e.stopImmediatePropagation();
                return false;
            }
        }, true);

        document.addEventListener('click', (e) => {
            if (e.target.closest('#competencia-container') && e.target.type === 'radio') {
                console.warn('⚠️ Intento de clic detectado - BLOQUEADO');
                e.preventDefault();
                e.stopPropagation();
                e.stopImmediatePropagation();
                return false;
            }
        }, true);

        // 3. Bloquear todos los textareas
        const textareas = document.querySelectorAll('textarea');
        console.log(`📝 Encontrados ${textareas.length} textareas para deshabilitar`);
        
        textareas.forEach(textarea => {
            textarea.disabled = true;
            textarea.readOnly = true;
            textarea.style.pointerEvents = 'none';
            textarea.style.opacity = '0.6';
            textarea.style.cursor = 'not-allowed';
        });

        // 4. Agregar overlay de bloqueo completo sobre el contenedor
        const competenciaContainer = document.getElementById('competencia-container');
        if (competenciaContainer) {
            competenciaContainer.style.pointerEvents = 'none';
            competenciaContainer.style.opacity = '0.7';
        }

        // 5. Agregar mensaje visual prominente
        const resumenContainer = document.getElementById('resumen-container');
        if (resumenContainer && !document.querySelector('.mensaje-bloqueado')) {
            const mensajeBloqueado = document.createElement('div');
            mensajeBloqueado.className = 'mensaje-bloqueado';
            mensajeBloqueado.style.cssText = `
                background: linear-gradient(135deg, #fff3cd 0%, #fffbea 100%);
                border: 3px solid #ffc107;
                border-radius: 10px;
                padding: 20px 25px;
                margin: 20px 0;
                color: #856404;
                font-weight: 700;
                font-size: 1.1em;
                display: flex;
                align-items: center;
                gap: 12px;
                z-index: 100;
                box-shadow: 0 4px 12px rgba(255, 193, 7, 0.3);
            `;
            mensajeBloqueado.innerHTML = `
                <span style="font-size: 2em; animation: spin 2s linear infinite;">🔒</span>
                <div>
                    <strong>EVALUACIÓN GUARDADA</strong><br>
                    <small>El formulario está bloqueado. No se pueden realizar cambios.</small>
                </div>
            `;
            resumenContainer.insertBefore(mensajeBloqueado, resumenContainer.firstChild);
            console.log('✅ Mensaje de bloqueo agregado');
        }

        console.log('✅ FORMULARIO BLOQUEADO COMPLETAMENTE');
    }

    mostrarResumen(payload) {
        const totalCalificaciones = payload.competencias.reduce(
            (sum, comp) => sum + (comp.comportamientos?.length || 0),
            0
        );
        const promedioGeneral = payload.competencias.length > 0
            ? (payload.competencias.reduce((sum, comp) => sum + parseFloat(comp.puntuacion_promedio), 0) / payload.competencias.length)
            : 0;

        const resumen = document.getElementById('resumen-container');
        const totalEl = document.getElementById('totalCalificaciones');
        const promedioEl = document.getElementById('promedioGeneralNivel');
        const resumenContenido = document.getElementById('resumen-contenido');
        
        if (resumen && totalEl && promedioEl) {
            totalEl.textContent = totalCalificaciones;
            promedioEl.textContent = promedioGeneral.toFixed(2);
            resumen.style.display = 'block';
        }
        
        // Agregar información del empleado si está disponible
        if (resumenContenido && typeof window !== 'undefined' && window.empleadoActual) {
            const emp = window.empleadoActual;
            const periodoSelect = document.getElementById('periodo-select');
            const periodo = periodoSelect ? periodoSelect.value : 'Sin período';
            
            const infoHTML = `
                <div style="margin-top: 15px; padding: 15px; background: #f9f9f9; border: 1px solid #ddd; border-radius: 8px;">
                    <h4 style="margin: 0 0 12px 0; color: #333;">Información del Empleado</h4>
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 12px;">
                        <div>
                            <label style="font-weight: bold; color: #555; font-size: 0.9em;">Nombre:</label>
                            <p style="margin: 3px 0 0 0; color: #333;">${emp.nombres_completos || 'Sin información'}</p>
                        </div>
                        <div>
                            <label style="font-weight: bold; color: #555; font-size: 0.9em;">Identificación:</label>
                            <p style="margin: 3px 0 0 0; color: #333;">${emp.identificacion || emp.cedula || 'Sin información'}</p>
                        </div>
                        <div>
                            <label style="font-weight: bold; color: #555; font-size: 0.9em;">Cargo:</label>
                            <p style="margin: 3px 0 0 0; color: #333;">${emp.cargo || 'Sin asignar'}</p>
                        </div>
                        <div>
                            <label style="font-weight: bold; color: #555; font-size: 0.9em;">Período:</label>
                            <p style="margin: 3px 0 0 0; color: #333;">${periodo}</p>
                        </div>
                    </div>
                </div>
            `;
            resumenContenido.innerHTML = infoHTML;
        }
    }

    mostrarBotonDetalle(evaluacionId) {
        const botonDetalle = document.getElementById('verDetalleEvaluacion');
        if (!botonDetalle) return;

        botonDetalle.style.display = 'inline-block';
        botonDetalle.style.cssText = `
            display: inline-block;
            padding: 15px 30px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 1.1em;
            font-weight: bold;
            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
            transition: all 0.3s ease;
            margin-top: 15px;
        `;
        
        botonDetalle.onmouseover = function() {
            this.style.transform = 'translateY(-2px)';
            this.style.boxShadow = '0 6px 16px rgba(102, 126, 234, 0.6)';
        };
        
        botonDetalle.onmouseout = function() {
            this.style.transform = 'translateY(0)';
            this.style.boxShadow = '0 4px 12px rgba(102, 126, 234, 0.4)';
        };
        
        botonDetalle.onclick = () => {
            window.location.href = `detalle-evaluacion.html?id=${evaluacionId}&tipo=autoevaluacion`;
        };

        const botonGuardar = document.getElementById('btnGuardarEvaluacion');
        if (botonGuardar) {
            botonGuardar.disabled = true;
            botonGuardar.style.opacity = '0.6';
            botonGuardar.style.cursor = 'not-allowed';
            botonGuardar.textContent = 'Evaluación guardada';
        }
    }

    // Obtener evaluación guardada
    obtenerEvaluacion(competencia_id) {
        return this.evaluacionesAlmacenadas[competencia_id] || null;
    }
}

// Instancia global
const competenciaEvaluador = new CompetenciaEvaluador();
