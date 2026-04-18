# ðŸš€ EMPIEZA AQUÃ - MigraciÃ³n a Ubuntu

## Â¿Primera vez migrando a Linux?

### ðŸ‘‰ PASO 1: Lee esto primero
**[README_MIGRACION_UBUNTU.md](README_MIGRACION_UBUNTU.md)**

Este archivo te da la visiÃ³n general de toda la migraciÃ³n.

---

### ðŸ‘‰ PASO 2: Sigue esta guÃ­a paso a paso
**[DIA_1_MIGRACION_UBUNTU.md](DIA_1_MIGRACION_UBUNTU.md)**

Tutorial completo con todos los comandos que necesitas copiar y pegar.

**Tiempo estimado**: 2-4 horas (incluye instalaciÃ³n de Ubuntu)

---

### ðŸ‘‰ PASO 3: Valida que todo funciona

Ejecuta en Ubuntu:
```bash
cd ~/proyectos/Talentia
./verificar_migracion.sh
```

---

### ðŸ‘‰ PASO 4: Arranca el servidor

```bash
./iniciar_servidor.sh
```

Abre en navegador: `http://localhost:5000`

---

## Â¿Ya terminaste la migraciÃ³n?

### Para uso diario:
**[GUIA_RAPIDA_UBUNTU.md](GUIA_RAPIDA_UBUNTU.md)**

Comandos rÃ¡pidos que vas a usar todos los dÃ­as.

---

## Â¿Necesitas encontrar algo especÃ­fico?

**[INDICE_MIGRACION.md](INDICE_MIGRACION.md)**

Ãndice completo de todos los archivos y contenidos.

---

## ðŸ“ž Â¿Problemas?

1. **Busca tu error en**: DIA_1_MIGRACION_UBUNTU.md Â§ Troubleshooting
2. **Ejecuta**: `./verificar_migracion.sh` para diagnÃ³stico
3. **Compara con**: Sistema Windows original

---

## âš¡ Ruta RÃ¡pida (si tienes experiencia con Linux)

```bash
# 1. Preparar Ubuntu
sudo apt update && sudo apt install -y python3 python3-venv python3-pip git psql

# 2. Copiar proyecto
cp -r /ruta/desde/windows ~/proyectos/Talentia

# 3. Setup Python
cd ~/proyectos/Talentia
python3 -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt

# 4. Permisos scripts
chmod +x *.sh

# 5. Validar
./verificar_migracion.sh

# 6. Arrancar
./iniciar_servidor.sh
```

---

**Â¿Listo?** â†’ Empieza con [README_MIGRACION_UBUNTU.md](README_MIGRACION_UBUNTU.md)

---

*Creado: Marzo 2026 | VersiÃ³n: 1.0 | Sistema: Talentia â†’ Ubuntu*

