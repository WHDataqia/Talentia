// Sistema de Keep-Alive para mantener sesión activa
(function() {
    const DEFAULT_FETCH_TIMEOUT_MS = 10000;
    const WRITE_FETCH_TIMEOUT_MS = 25000;
    const DEFAULT_FETCH_RETRIES = 0;
    const LOADING_STUCK_MS = 15000;
    const BUTTON_STUCK_MS = 20000;

    function sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    // Parche global de fetch con timeout y reintento para evitar requests colgadas en localhost.
    if (!window.__talentiaFetchPatched) {
        const originalFetch = window.fetch.bind(window);

        window.fetch = async function(url, options = {}) {
            if (options && options.signal) {
                return originalFetch(url, options);
            }

            const method = String(options.method || 'GET').toUpperCase();
            const isIdempotent = method === 'GET' || method === 'HEAD';
            const retries = Number.isInteger(options.retries)
                ? options.retries
                : (isIdempotent ? DEFAULT_FETCH_RETRIES : 0);
            const timeoutMs = Number(options.timeoutMs) > 0
                ? Number(options.timeoutMs)
                : (isIdempotent ? DEFAULT_FETCH_TIMEOUT_MS : WRITE_FETCH_TIMEOUT_MS);

            let attempt = 0;
            let lastError = null;

            while (attempt <= retries) {
                const controller = new AbortController();
                const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

                const mergedOptions = {
                    ...options,
                    signal: controller.signal
                };
                delete mergedOptions.timeoutMs;
                delete mergedOptions.retries;

                try {
                    const response = await originalFetch(url, mergedOptions);
                    clearTimeout(timeoutId);

                    const retryableStatus = [408, 429, 500, 502, 503, 504].includes(response.status);
                    if (isIdempotent && retryableStatus && attempt < retries) {
                        attempt += 1;
                        await sleep(300 * attempt);
                        continue;
                    }
                    return response;
                } catch (error) {
                    clearTimeout(timeoutId);
                    lastError = error;
                    const retryableError = error && (error.name === 'AbortError' || error.name === 'TypeError');
                    if (!isIdempotent || !retryableError || attempt >= retries) {
                        throw error;
                    }
                    attempt += 1;
                    await sleep(300 * attempt);
                }
            }

            throw lastError || new Error('Error de red desconocido');
        };

        window.__talentiaFetchPatched = true;
        console.log(`✓ Fetch global protegido (timeout ${DEFAULT_FETCH_TIMEOUT_MS} ms, reintentos ${DEFAULT_FETCH_RETRIES})`);
    }

    function marcarPrimeraVez(el, key) {
        if (!el.dataset[key]) {
            el.dataset[key] = String(Date.now());
        }
        return Number(el.dataset[key]);
    }

    function limpiarEstadosPegados() {
        const now = Date.now();

        // Limpia textos de carga que se quedan indefinidamente.
        const textSelectors = 'span, p, div, td, option';
        document.querySelectorAll(textSelectors).forEach(el => {
            const text = (el.textContent || '').trim();
            if (!text) return;

            const lower = text.toLowerCase();
            const isLoadingText = lower === 'cargando...' || lower === 'cargando' || lower.includes('cargando evaluaciones');
            if (!isLoadingText) {
                delete el.dataset.loadingSince;
                return;
            }

            const since = marcarPrimeraVez(el, 'loadingSince');
            if (now - since < LOADING_STUCK_MS) return;

            if (el.id === 'nombre-evaluador') {
                resolverTextoCargandoUsuario();
                return;
            }

            if (el.tagName === 'OPTION') {
                el.textContent = '-- No disponible (reintente) --';
            } else {
                el.textContent = 'No disponible, reintente';
            }
        });

        // Reactiva botones que quedaron bloqueados en estado de carga.
        document.querySelectorAll('button[disabled]').forEach(btn => {
            const label = (btn.textContent || '').trim();
            const lower = label.toLowerCase();
            const isBusyLabel = lower.includes('cargando') || lower.includes('guardando') || lower.includes('procesando') || lower.includes('iniciando');
            if (!isBusyLabel) {
                delete btn.dataset.busySince;
                return;
            }

            const since = marcarPrimeraVez(btn, 'busySince');
            if (now - since < BUTTON_STUCK_MS) return;

            btn.disabled = false;
            if (!btn.dataset.originalLabel) {
                btn.dataset.originalLabel = label;
            }
            btn.textContent = 'Reintentar';
        });
    }

    function iniciarWatchdogUI() {
        setInterval(limpiarEstadosPegados, 5000);
    }

    function resolverTextoCargandoUsuario() {
        const spanUsuario = document.getElementById('nombre-evaluador');
        if (!spanUsuario) return;

        setTimeout(() => {
            const actual = (spanUsuario.textContent || '').trim().toLowerCase();
            if (actual === 'cargando...' || actual === 'cargando') {
                try {
                    const usuarioRaw = sessionStorage.getItem('usuario');
                    if (usuarioRaw) {
                        const usuario = JSON.parse(usuarioRaw);
                        const nombre = usuario?.nombres_completos || usuario?.nombre || 'Usuario';
                        spanUsuario.textContent = nombre;
                    } else {
                        spanUsuario.textContent = 'Sin información';
                    }
                } catch (error) {
                    console.warn('⚠️ No se pudo resolver nombre de usuario:', error);
                    spanUsuario.textContent = 'Sin información';
                }
            }
        }, 4000);
    }

    // Enviar ping cada 30 minutos para mantener la sesión viva
    const KEEP_ALIVE_INTERVAL = 30 * 60 * 1000; // 30 minutos
    
    function keepAlive() {
        const token = sessionStorage.getItem('token');
        if (!token) return; // No hay sesión
        
        fetch('/api/health', {
            method: 'GET',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            }
        })
        .then(resp => {
            if (!resp.ok && resp.status === 401) {
                // Token expiró, redirigir a login
                console.warn('⚠️ Sesión expirada. Redirigiendo a login...');
                sessionStorage.clear();
                window.location.href = 'login.html';
            }
        })
        .catch(err => {
            console.warn('⚠️ Error en keep-alive:', err.message);
            // No redirigir por error de red, solo logging
        });
    }
    
    // Iniciar keep-alive cuando el documento esté listo
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            resolverTextoCargandoUsuario();
            iniciarWatchdogUI();
            setInterval(keepAlive, KEEP_ALIVE_INTERVAL);
            console.log('✓ Keep-alive iniciado (cada 30 minutos)');
        });
    } else {
        resolverTextoCargandoUsuario();
        iniciarWatchdogUI();
        setInterval(keepAlive, KEEP_ALIVE_INTERVAL);
        console.log('✓ Keep-alive iniciado (cada 30 minutos)');
    }

    window.addEventListener('unhandledrejection', function(event) {
        console.warn('⚠️ Promesa no controlada en UI:', event.reason);
        limpiarEstadosPegados();
    });

    window.addEventListener('error', function(event) {
        console.warn('⚠️ Error de runtime en UI:', event.message);
        limpiarEstadosPegados();
    });
    
    // También ejecutar keep-alive cuando el navegador vuelve del background
    document.addEventListener('visibilitychange', function() {
        if (document.visibilityState === 'visible') {
            console.log('✓ Navegador activo de nuevo, ejecutando keep-alive...');
            keepAlive();
        }
    });
    
    // NUEVO: Cuando se cierra la pestaña, intentar hacer logout automático
    // Esto limpia la sesión en el servidor
    window.addEventListener('beforeunload', function() {
        const token = sessionStorage.getItem('token');
        if (token) {
            // Intentar logout asincrónico
            try {
                // Usar sendBeacon para asegurar que se envíe incluso si la pestaña se cierra
                const payload = JSON.stringify({
                    token: token
                });
                
                // Intentar POST con sendBeacon
                navigator.sendBeacon('/api/logout', payload);
                console.log('✓ Logout automático al cerrar pestaña');
            } catch (e) {
                console.warn('⚠️ No se pudo hacer logout automático:', e);
            }
        }
    });
    
})();
