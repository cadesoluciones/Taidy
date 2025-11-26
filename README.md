
# 📊 Extracción de Datos de Business Central - PoC

Herramienta para extraer datos completos de Microsoft Dynamics 365 Business Central a archivos CSV. Incluye autenticación OAuth, paginación automática, procesamiento paralelo y exportación atómica.

[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![Pytest](https://img.shields.io/badge/Pytest-✔e06?style=flat-square&logo=pytest&logoColor=white)](https://pytest.org)
[![Taskfile](https://img.shields.io/badge/Taskfile-4d2a85?style=flat-square)](https://taskfile.dev)
![coverage](./docs/coverage.svg)

## 🚀 Inicio Rápido

```bash
# 1. Configurar entorno
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt

# 2. Configurar credenciales y configuración
cp .env.example .env
# Editar .env con tus secretos de Azure AD y actualizar config.json y tables.yaml

# 3. Probar configuración
task ingest -- --dry-run --verbose

# 4. Extraer datos
task ingest -- --verbose
```

## 📚 Documentación Adicional

- **[🔧 Configuración Detallada](docs/configuracion.md)** - Azure AD, variables de entorno, configuración de tablas
- **[🛠️ Guía de Desarrollo](docs/desarrollo.md)** - Arquitectura, pruebas, troubleshooting, extensión

## ⚡ Características

- **Autenticación OAuth** con caché automático de tokens
- **Paginación completa** vía `@odata.nextLink`
- **Procesamiento paralelo** de múltiples tablas
- **Exportación atómica** para evitar archivos parciales
- **Pruebas comprehensivas** (unit/integration/acceptance)

## 📋 Requisitos

- Python 3.12+
- Aplicación Azure AD con permisos de Business Central

## ⚙️ Configuración Básica

### Secretos en `.env`

Solo guarda los secretos: `BC_CLIENT_SECRET` y `FABRIC_CLIENT_SECRET`. El resto de la configuración vive en `config.json` (consulta `config.example.json`).

```bash
# En tu archivo .env
BC_CLIENT_SECRET=tu-client-secret-aqui
FABRIC_CLIENT_SECRET=tu-fabric-secret-aqui
CONFIG_FILE=./config.json
```

### Configuración de Tablas

```yaml
# En tables.yaml
tables:
  - name: Customers
    url: https://api.businesscentral.dynamics.com/v2.0/{tenant}/{environment}/api/data/companies({company})/customers
  - name: Vendors
    url: https://api.businesscentral.dynamics.com/v2.0/{tenant}/{environment}/api/data/companies({company})/vendors
```

> 📖 **Para configuración detallada**: Ver [Guía de Configuración](docs/configuracion.md)

## 🧪 Pruebas

```bash
# Pruebas rápidas (unit + integration)
pytest

# Con cobertura
task test:run

# Pruebas con API real (requiere .env configurado)
pytest -m acceptance -v
```

## 🔄 Comandos de Uso

```bash
# Validar configuración (sin llamar API)
task ingest -- --dry-run --verbose

# Extraer todas las tablas
task ingest -- --verbose

# Extraer tablas específicas
task ingest -- --tables Customers Vendors

# Procesamiento paralelo
task ingest -- --parallel 4

# Directorio personalizado
task ingest -- --output-dir ./exports_$(date +%Y%m%d)

# Subir a Fabric (sobrescribe archivos existentes por defecto)
task fabric:upload -- --output-dir ./exports

# Saltar archivos que ya existen en Fabric
task fabric:upload -- --output-dir ./exports --skip-existing
```

## ☁️ Subir CSV directamente a Microsoft Fabric OneLake

Ahora las cargas a Fabric se ejecutan en un paso independiente para poder validar primero los CSV exportados.

1. Completa en `.env` las variables `FABRIC_*`:
   - `FABRIC_TENANT_ID`, `FABRIC_CLIENT_ID`, `FABRIC_CLIENT_SECRET`
   - `FABRIC_WORKSPACE_NAME`, `FABRIC_LAKEHOUSE_NAME`
   - Opcional: `FABRIC_WORKSPACE_ID`, `FABRIC_LAKEHOUSE_ID` (recomendado: usa los GUID del portal para garantizar nombres compatibles con OneLake)
   - Opcional: `FABRIC_PATH_PREFIX`, `FABRIC_SOURCE_NAME`, `FABRIC_OVERWRITE`, `FABRIC_MAX_RETRIES`
2. Ejecuta `task ingest -- --verbose` para descargar las tablas a `exports/`.
3. Revisa/valida los CSV generados.
4. Ejecuta `task fabric:upload -- --output-dir ./exports` para subir todos los CSV encontrados a `Files/<prefijo>/<source>/<tabla>/<yyyy>/<mm>/<dd>/<archivo>.csv` usando tu aplicación de Entra ID.

El comando de subida admite `--dry-run` (lista los archivos sin subirlos) y respeta `FABRIC_OVERWRITE`/`FABRIC_MAX_RETRIES`. Para evitar errores `ArtifactNotFound`, especifica `FABRIC_WORKSPACE_ID`/`FABRIC_LAKEHOUSE_ID` con los GUID que aparecen en las URLs del portal (`.../groups/<workspaceId>/lakehouses/<lakehouseId>`) y recuerda que OneLake usa la ruta `https://onelake.dfs.fabric.microsoft.com/<workspace>/<lakehouse>.Lakehouse/Files/...`. El uploader crea las carpetas intermedias automáticamente y los reintentos manejan errores transitorios de red.

## 🔧 Solución de Problemas Básicos

### Error de autenticación

- Verificar credenciales en `.env`
- Confirmar permisos en Azure AD
- Verificar que admin consent fue otorgado

### Error de configuración

```bash
# Verificar variables
env | grep BC_

# Probar configuración
task ingest -- --dry-run --verbose
```

### Problemas de red

- El sistema reintenta automáticamente (5 intentos)
- Verificar conectividad a `api.businesscentral.dynamics.com`

> 🔍 **Para troubleshooting avanzado**: Ver [Guía de Desarrollo](docs/desarrollo.md)

## 📁 Estructura del Proyecto

```text
src/
├── main.py              # CLI y orquestación
└── bc_client/
    ├── config.py        # Configuración y validación
    ├── auth.py          # OAuth con caché de tokens
    ├── api.py           # Cliente OData con paginación
    └── exporter.py      # Exportación CSV atómica

tests/
├── unit/               # Pruebas unitarias rápidas
├── integration/        # Pruebas de integración
└── acceptance/         # Pruebas con API real

docs/
├── configuracion.md    # Configuración detallada
└── desarrollo.md       # Guía técnica
```
