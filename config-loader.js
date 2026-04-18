// Cargar configuración de API desde archivo central
let API_URL = '/api'; // Por defecto (compatible con red/LAN)

async function loadConfig() {
    try {
        const response = await fetch('./config.json');
        const config = await response.json();
        API_URL = config.apiUrl;
        console.log('✅ API URL cargada desde config.json:', API_URL);
    } catch (error) {
        console.warn('⚠️ No se pudo cargar config.json, usando URL por defecto:', API_URL);
    }
}

// Cargar configuración al iniciar
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', loadConfig);
} else {
    loadConfig();
}
