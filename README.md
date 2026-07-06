
# 📊 TAIDY — Extracción y Carga de Datos al Datalake

Herramienta para extraer datos de **Microsoft Dynamics 365 Business Central** y **Factorial HR** a archivos CSV y subirlos a Microsoft Fabric OneLake. Incluye autenticación OAuth / API Key, paginación automática, procesamiento paralelo, exportación atómica e ingesta incremental con checkpoints.

[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![Pytest](https://img.shields.io/badge/Pytest-✔e06?style=flat-square&logo=pytest&logoColor=white)](https://pytest.org)
[![Taskfile](https://img.shields.io/badge/Taskfile-4d2a85?style=flat-square)](https://taskfile.dev)
![coverage](./docs/coverage.svg)

## 🚀 Inicio Rápido

### Business Central

```bash
# 1. Configurar entorno
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt

# 2. Configurar credenciales
cp .env.example .env
# Editar .env con BC_CLIENT_SECRET y FABRIC_CLIENT_SECRET; actualizar config.json y tables.yaml

# 3. Probar configuración
task extract:bc -- --dry-run --verbose

# 4. Extraer datos
task extract:bc -- --verbose
```

### Factorial HR

```bash
# 1. Añadir credenciales al .env
FACTORIAL_API_KEY=tu-api-key-aqui
VERSION_API_FACTORIAL=2026-07-01
FABRIC_CLIENT_SECRET=tu-fabric-secret-aqui

# 2. Probar configuración (sin llamar la API ni subir nada)
task extract:factorial -- --start-on 2025-01-01 --end-on 2025-01-07 --dry-run

# 3. Extraer y subir al datalake en un paso
task sync:factorial -- --start-on 2025-01-01 --end-on 2026-01-01 --mode incremental --parallel 5
```

## 📚 Documentación Adicional

- **[🔧 Configuración Detallada](docs/configuracion.md)** - Azure AD, variables de entorno, configuración de tablas
- **[🛠️ Guía de Desarrollo](docs/desarrollo.md)** - Arquitectura, pruebas, troubleshooting, extensión
- **[🐳 Guía de Docker](docs/docker.md)** - Cómo construir y ejecutar la aplicación con Docker

## ⚡ Características

### Business Central
- **Autenticación OAuth** con caché automático de tokens
- **Paginación completa** vía `@odata.nextLink`
- **Procesamiento paralelo** de múltiples tablas
- **Exportación atómica** para evitar archivos parciales
- **Pruebas comprehensivas** (unit/integration/acceptance)
- **Ingesta incremental** usando columnas watermark y checkpoints en Fabric OneLake

### Factorial HR
- **Autenticación por API Key** vía cabecera `x-api-key`
- **Paginación por cursor** automática (`meta.has_next_page` / `end_cursor`)
- **Campos configurables por tabla** en `factorial_tables.yaml` — sin tocar código para añadir endpoints
- **Exportación atómica** (escribe a fichero temporal, luego renombra)
- **Procesamiento paralelo** de múltiples tablas con `--parallel N`
- **Reintentos automáticos** con backoff exponencial (5 intentos, retryable en 5xx)
- **Versión de API parametrizada** vía `VERSION_API_FACTORIAL`
- **Modo incremental** con checkpoints locales y solapamiento configurable por tabla (`overlap_days`)
- **División de rangos** en ventanas de `chunk_days` días para evitar timeouts en la API
- **Subida a Fabric OneLake** bajo `raw/factorial/`, independiente del pipeline de BC

## 📋 Requisitos

- Python 3.12+
- Aplicación Azure AD con permisos de Business Central y/o Fabric OneLake
- API Key de Factorial HR (para el pipeline de Factorial)

## ⚙️ Configuración Básica

### Secretos en `.env`

Solo guarda los secretos. El resto de la configuración vive en `config.json`.

```bash
# Business Central
BC_CLIENT_SECRET=tu-client-secret-aqui

# Factorial HR
FACTORIAL_API_KEY=tu-api-key-aqui
VERSION_API_FACTORIAL=2026-07-01
FACTORIAL_OVERLAP_DAYS=2      # opcional, días de solapamiento incremental global (default: 2)

# Fabric OneLake (compartido por BC y Factorial)
FABRIC_CLIENT_SECRET=tu-fabric-secret-aqui
CONFIG_FILE=./config.json
```

### Configuración en `config.json`

```json
"bc_upload": {
  "tenant_id": "...",
  "client_id": "...",
  "workspace_name": "Sandbox",
  "lakehouse_name": "Lakehouse",
  "path_prefix": "raw",
  "source_name": "business_central"
},
"factorial_upload": {
  "tenant_id": "...",
  "client_id": "...",
  "workspace_name": "Sandbox",
  "lakehouse_name": "Lakehouse",
  "workspace_id": "...",
  "lakehouse_id": "...",
  "path_prefix": "raw",
  "source_name": "factorial",
  "overwrite": true,
  "max_retries": 3
}
```

### Configuración de Tablas BC

```yaml
# En tables.yaml
base_api_url: https://api.businesscentral.dynamics.com/v2.0/{tenant}/{environment}/api/data/companies({company})
tables:
  - name: Customers
    api_path: customers
  - name: Vendors
    api_path: vendors
```

### Configuración de Tablas Factorial

Cada endpoint se declara en `factorial_tables.yaml`. Campos opcionales por tabla:

| Campo | Default | Descripción |
|---|---|---|
| `date_range` | `true` | Envía `start_on`/`end_on` a la API |
| `employee_filter` | `true` | Envía `employee_ids[]` a la API |
| `incremental` | `false` | Activa extracción incremental con checkpoint |
| `overlap_days` | *(global)* | Solapamiento propio de la tabla (sobreescribe `FACTORIAL_OVERLAP_DAYS`) |
| `chunk_days` | *(ninguno)* | Divide el rango en ventanas de N días (evita timeouts) |
| `extra_params` | *(ninguno)* | Parámetros estáticos añadidos a cada llamada a la API |

```yaml
tables:
  - name: factorial_worked_times
    path: resources/attendance/worked_times
    incremental: true
    overlap_days: 15
    chunk_days: 1
    employee_filter: false
    extra_params:
      - [include_non_attendable_employees, "true"]
    fields: [employee_id, minutes, date]
```

Para añadir un nuevo endpoint basta con añadir una entrada al YAML — sin modificar código.

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

### Business Central

```bash
# Validar configuración (sin llamar API)
task extract:bc -- --dry-run --verbose

# Extraer tablas específicas
task extract:bc -- --tables Customers Vendors

# Procesamiento paralelo
task extract:bc -- --parallel 4

# Snapshot completo (CSV en exports/full/)
task extract:bc -- --mode full

# Incremental → CSV en exports/incremental/<timestamp>/
task extract:bc -- --mode incremental

# Subir a Fabric una carpeta exportada
task push:fabric -- --output-dir ./exports/incremental/20240512T101500Z

# Saltar archivos que ya existen en Fabric
task push:fabric -- --output-dir ./exports/full --skip-existing

# Pipeline completo (extrae y sube)
task sync -- --mode incremental
```

### Factorial HR

```bash
# Extracción full de todas las tablas
task extract:factorial -- --start-on 2025-01-01 --end-on 2026-01-01

# Extraer solo una tabla
task extract:factorial -- --start-on 2025-01-01 --end-on 2026-01-01 --tables factorial_worked_times

# Extracción en paralelo (5 tablas a la vez)
task extract:factorial -- --start-on 2025-01-01 --end-on 2026-01-01 --parallel 5

# Modo incremental (retoma desde último checkpoint)
task extract:factorial -- --start-on 2025-01-01 --end-on 2026-06-10 --mode incremental

# Incremental, solo una tabla, 5 workers
task extract:factorial -- --start-on 2025-01-01 --end-on 2026-06-10 --mode incremental --tables factorial_worked_times --parallel 5

# Extraer + subir en un único comando
task sync:factorial -- --start-on 2025-01-01 --end-on 2026-06-10 --mode incremental --parallel 5

# Solo subir los CSVs ya generados
task push:fabric:factorial

# Subir sin sobreescribir ficheros existentes
task push:fabric:factorial -- --skip-existing

# Ver qué se subiría sin ejecutar nada
task push:fabric:factorial -- --dry-run
```

#### Parámetros CLI de extracción Factorial

| Parámetro | Obligatorio | Descripción |
|---|---|---|
| `--start-on` | Sí | Fecha de inicio `YYYY-MM-DD` (fallback si no hay checkpoint en modo incremental) |
| `--end-on` | Sí | Fecha de fin `YYYY-MM-DD` |
| `--mode` | No | `full` (defecto) o `incremental` |
| `--reset-checkpoints` | No | Sin valor: resetea todos. Con nombres: resetea solo esas tablas |
| `--employees` | No | IDs manuales (si se omite, se auto-descubren de `factorial_employees`) |
| `--employee-status` | No | `active` (defecto), `inactive` o `all` |
| `--tables` | No | Filtrar tablas por nombre |
| `--parallel` | No | Tablas a extraer en paralelo (default: 1) |
| `--dry-run` | No | Simula sin llamar la API |
| `--verbose` | No | Logging a nivel DEBUG |

### Ingesta incremental con checkpoints

Cada tabla puede activar incremental marcando `incremental: true` en su YAML correspondiente.

**Business Central** — usa `SystemModifiedAt` como watermark. Los checkpoints se guardan en `Files/raw/checkpoints/.../` dentro del Lakehouse.

> 📁 Las ejecuciones `--mode full` suben los CSV a `raw/business_central/full/<tabla>.csv`, mientras que las incrementales crean `raw/business_central/incremental/<tabla>/<run_timestamp>/<tabla>.csv`.

```bash
task extract:bc -- --mode incremental
task extract:bc -- --mode full
task extract:bc -- --reset-watermarks
```

**Factorial HR** — los checkpoints se guardan localmente en `exports_factorial/.checkpoints/<tabla>.json`. En cada run incremental la tabla retoma desde `último_checkpoint - overlap_days`.

> 📁 Los CSV master viven en `exports_factorial/full/<tabla>.csv`; cada run incremental archiva también en `exports_factorial/incremental/<run_ts>/<tabla>.csv` y hace merge+dedup en el master (las filas nuevas ganan).

```bash
# Primera vez: extrae desde --start-on (no hay checkpoint aún)
task extract:factorial -- --start-on 2025-01-01 --end-on 2025-01-31 --mode incremental

# Segunda vez: retoma desde checkpoint - overlap_days
task extract:factorial -- --start-on 2025-01-01 --end-on 2026-06-10 --mode incremental

# Reiniciar checkpoint de una tabla
task extract:factorial -- --start-on 2025-01-01 --end-on 2026-06-10 --reset-checkpoints factorial_worked_times

# Reiniciar todos los checkpoints
task extract:factorial -- --start-on 2025-01-01 --end-on 2026-06-10 --reset-checkpoints
```

> 💡 Usa `task sync:factorial` o `task sync` para ejecutar extracción + subida en un solo comando.

## ☁️ Subir CSV directamente a Microsoft Fabric OneLake

Las cargas a Fabric se ejecutan en un paso independiente para poder validar primero los CSV exportados.

### Business Central

1. Completa en `.env`: `BC_CLIENT_SECRET` y `FABRIC_CLIENT_SECRET`
2. Ejecuta `task extract:bc -- --verbose` y revisa los CSV generados
3. Ejecuta `task push:fabric -- --output-dir <carpeta_exportada>`

### Factorial HR

1. Completa en `.env`: `FACTORIAL_API_KEY`, `VERSION_API_FACTORIAL` y `FABRIC_CLIENT_SECRET`
2. Completa la sección `factorial_upload` en `config.json` con `tenant_id`, `client_id`, `workspace_id`, `lakehouse_id`
3. Ejecuta `task extract:factorial -- ...` y revisa los CSV en `exports_factorial/full/`
4. Ejecuta `task push:fabric:factorial` para subir (o usa `task sync:factorial` para todo en uno)

Los CSV de Factorial se suben a `raw/factorial/full/<tabla>.csv` y `raw/factorial/incremental/<run_ts>/<tabla>.csv`, separados del espacio de BC.

Para evitar errores `ArtifactNotFound`, especifica `workspace_id` y `lakehouse_id` en `config.json` con los GUIDs del portal (`.../groups/<workspaceId>/lakehouses/<lakehouseId>`). El uploader crea las carpetas intermedias automáticamente y los reintentos manejan errores transitorios de red.

## 🔧 Solución de Problemas Básicos

### Error de autenticación (BC / Fabric)

- Verificar `BC_CLIENT_SECRET` y `FABRIC_CLIENT_SECRET` en `.env`
- Confirmar permisos en Azure AD y que admin consent fue otorgado

### Error de autenticación en Factorial (401)

- Verificar `FACTORIAL_API_KEY` en `.env`
- Confirmar que la clave tiene permisos sobre el recurso solicitado

### Error de versión de API Factorial (404)

- Verificar `VERSION_API_FACTORIAL` en `.env`
- Consultar la documentación de Factorial para la versión activa del endpoint

### Timeout en la API de Factorial

- Añadir `chunk_days: 1` (o el valor adecuado) a la tabla en `factorial_tables.yaml`
- Esto divide el rango en ventanas diarias y acumula en memoria antes de escribir el CSV

### Factorial devuelve 0 empleados

- Si la tabla tiene `employee_filter: true`, verificar que `factorial_employees` está en el YAML
- Usar `--employee-status all` o añadir `only_active: "false"` en `extra_params` del YAML

### La subida no encuentra ficheros

- Ejecutar primero la extracción: `task extract:factorial -- ...`
- Verificar que `exports_factorial/full/` contiene los CSVs

### Error de configuración general

```bash
# Verificar variables BC
env | grep BC_

# Verificar variables Factorial
env | grep FACTORIAL_

# Probar configuración sin llamar APIs
task extract:bc -- --dry-run --verbose
task extract:factorial -- --start-on 2025-01-01 --end-on 2025-01-07 --dry-run
```

### Problemas de red

- El sistema reintenta automáticamente (5 intentos con backoff exponencial)
- Verificar conectividad a `api.businesscentral.dynamics.com` y `api.factorialhr.com`

> 🔍 **Para troubleshooting avanzado**: Ver [Guía de Desarrollo](docs/desarrollo.md)

## 📁 Estructura del Proyecto

```text
src/
├── main.py                        # CLI y orquestación de Business Central
├── factorial_main.py              # CLI y orquestación de Factorial HR
├── bc_client/
│   ├── config.py                  # Configuración y validación BC
│   ├── auth.py                    # OAuth con caché de tokens
│   ├── api.py                     # Cliente OData con paginación
│   └── exporter.py                # Exportación CSV atómica
├── factorial_client/
│   ├── config.py                  # Settings, TableConfig, carga de YAML
│   ├── api.py                     # Cliente HTTP con paginación por cursor y chunking
│   ├── exporter.py                # Exportación atómica + merge incremental en master
│   ├── checkpoints.py             # Gestión de checkpoints para modo incremental
│   └── push.py                    # CLI de subida a Fabric OneLake
└── fabric_upload/
    ├── config.py                  # FabricUploadSettings (compartido BC + Factorial)
    └── uploader.py                # FabricUploader — autenticación Azure y carga a OneLake

tables.yaml                        # Endpoints de Business Central
factorial_tables.yaml              # Endpoints de Factorial HR
config.json                        # Configuración no secreta (IDs, rutas, opciones)

exports/                           # Salida de Business Central
├── full/                          # Snapshot completo
└── incremental/                   # Runs incrementales por timestamp

exports_factorial/                 # Salida de Factorial HR
├── full/                          # Master CSV (último estado)
├── incremental/                   # Runs incrementales por timestamp
└── .checkpoints/                  # JSON con el último end_on por tabla

tests/
├── unit/                          # Pruebas unitarias rápidas
├── integration/                   # Pruebas de integración
└── acceptance/                    # Pruebas con API real

docs/
├── configuracion.md               # Configuración detallada
└── desarrollo.md                  # Guía técnica
```
