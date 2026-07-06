# Guía de Ampliación — Business Central (para contexto de IA)

Este documento describe exactamente cómo añadir una nueva tabla a la integración de Business Central existente en TAIDY. Está optimizado para ser leído por un asistente de IA como contexto previo a realizar una ampliación, sin necesidad de reanálizar el código.

---

## 1. Arquitectura de la integración BC

### Ficheros clave

| Fichero | Rol |
|---------|-----|
| `tables.yaml` | **Único fichero a tocar** para añadir una nueva tabla |
| `config.json` → sección `business_central` | Configuración global (tenant, company, page_size, ruta al YAML) |
| `src/bc_client/config.py` | Carga y valida `tables.yaml` → produce lista de `TableConfig` |
| `src/bc_client/api.py` | `BusinessCentralClient` — paginación OData, reintentos |
| `src/bc_client/auth.py` | Token OAuth con caché en memoria (hilo-seguro) |
| `src/bc_client/exporter.py` | Exportación atómica a CSV (temp → rename) |
| `src/ingest/executor.py` | Orquestación de la extracción por tabla |
| `src/ingest/jobs.py` | Preparación de jobs (carga checkpoints, filtra tablas) |
| `src/fabric_upload/checkpoints.py` | Checkpoints incrementales almacenados en Fabric OneLake |
| `src/main.py` | CLI de extracción BC |
| `src/cli/sync.py` | CLI combinado extracción + subida a Fabric |

### Variables de entorno requeridas (`.env`)

```
BC_CLIENT_SECRET=<oauth-secret>         # Obligatorio
FABRIC_CLIENT_SECRET=<azure-secret>     # Obligatorio para subida a Fabric
CONFIG_FILE=./config.json               # Opcional, por defecto ./config.json
```

### Flujo de datos

```
CLI (main.py) → load_settings() → TableConfig list
    → BusinessCentralClient.fetch_table()
        → OData GET con paginación (@odata.nextLink)
        → Retries exponenciales (tenacity, 5 intentos)
    → exporter.export_table() → CSV atómico en exports/full/ o exports/incremental/
    → Checkpoint guardado en Fabric OneLake (solo incremental)
    → FabricUploader.upload() → raw/business_central/
```

---

## 2. Caso A — Añadir una nueva tabla OData (caso más común)

**Único fichero a modificar:** `tables.yaml`

### Estructura de una entrada

```yaml
- name: bc_nombre_tabla          # snake_case, prefijo bc_, único en el fichero
  description: Descripción API   # texto libre, solo informativo
  url: https://api.businesscentral.dynamics.com/v2.0/{tenant_id}/{ENVIRONMENT}/ODataV4/Company('{Company_Encoded}')/NombrePaginaBC
  incremental: true              # true si la tabla tiene SystemModifiedAt; false si no
```

### Reglas de validación (aplicadas por `src/bc_client/config.py:_parse_table_entry`)

- `name` → string no vacío. Obligatorio.
- `url` → string no vacío, URL OData completa. Obligatorio. **No usar `api_path`** (campo retirado — lanzará error).
- `incremental` → bool. Por defecto `false` si se omite.
- **No poner `base_api_url`** en el nivel raíz del YAML (lanzará error).
- El campo `description` es ignorado por el parser (solo documental).

### Patrón de URL

```
https://api.businesscentral.dynamics.com/v2.0/{tenant_id}/{ENVIRONMENT}/ODataV4/Company('{Company_Name_URL_Encoded}')/{NombrePaginaBC}
```

Valores actuales del proyecto (de `config.json`):
- `tenant_id`: `2d6ec162-8eb4-42d3-93e2-7ee771e85da5`
- `ENVIRONMENT`: `PRODUCTION`
- `Company`: `CADE%20Soluciones` (URL-encoded)

### Ejemplo completo

```yaml
- name: bc_nueva_tabla
  description: Nueva Tabla BC
  url: https://api.businesscentral.dynamics.com/v2.0/2d6ec162-8eb4-42d3-93e2-7ee771e85da5/PRODUCTION/ODataV4/Company('CADE%20Soluciones')/APInuevapagina
  incremental: true
```

### Verificación tras añadir

```bash
# Dry-run: valida config sin llamar a la API
task extract:bc -- --dry-run --verbose

# Extracción solo de la nueva tabla
task extract:bc -- --mode full --tables bc_nueva_tabla --verbose

# Subida a Fabric
task push:fabric -- --output-dir ./exports/full
```

---

## 3. Comportamiento incremental

Cuando `incremental: true`:

- **Columna de watermark**: `SystemModifiedAt` (campo estándar BC — no configurable).
- **Checkpoint almacenado en Fabric OneLake**: `raw/checkpoints/business_central/{table_name}.json`
- **En cada ejecución incremental**: filtra `?$filter=SystemModifiedAt gt {last_checkpoint}`.
- **Primera ejecución** (sin checkpoint): extracción completa.
- **Salida**: `exports/incremental/{timestamp}/{table_name}.csv`

Cuando `incremental: false`:

- Siempre extrae todos los registros.
- **Salida**: `exports/full/{table_name}.csv` (sobreescribe).

---

## 4. Comandos CLI de referencia

```bash
# Extracción completa de todas las tablas
task extract:bc -- --mode full

# Extracción incremental (usa checkpoints)
task extract:bc -- --mode incremental

# Tablas específicas
task extract:bc -- --mode full --tables bc_customer bc_nueva_tabla

# Paralelismo (N tablas simultáneas)
task extract:bc -- --mode full --parallel 4

# Dry-run (valida sin llamar API)
task extract:bc -- --dry-run --verbose

# Subir CSVs a Fabric
task push:fabric -- --output-dir ./exports/full

# Extracción + subida combinadas
task sync -- --mode incremental

# Extracción BC + Factorial combinadas
task sync:all MODE=incremental START_ON=2025-01-01
```

---

## 5. Caso B — Nueva empresa o entorno BC (mismo patrón de API)

Si la nueva tabla pertenece a una **empresa distinta** (company) o **entorno distinto** (PRODUCTION vs SANDBOX):

1. Las URLs ya llevan la company/entorno embebidos → basta con poner la URL correcta en `tables.yaml`.
2. Si se necesita autenticación con un tenant distinto, se requiere un nuevo bloque en `config.json` (por ejemplo `business_central_sandbox`) y duplicar la lógica de `load_settings()` en un nuevo módulo cliente.

---

## 6. Caso C — Nueva fuente con arquitectura BC completa (desde cero)

Solo aplica si se añade una fuente completamente nueva que siga el mismo patrón OData + OAuth. El patrón seguido fue el mismo que se usó para construir BC originalmente:

| Fichero a crear | Modelo en el que basarse |
|----------------|--------------------------|
| `src/{source}_client/config.py` | `src/bc_client/config.py` |
| `src/{source}_client/auth.py` | `src/bc_client/auth.py` |
| `src/{source}_client/api.py` | `src/bc_client/api.py` |
| `src/{source}_client/exporter.py` | `src/bc_client/exporter.py` |
| `{source}_tables.yaml` | `tables.yaml` |
| `src/{source}_main.py` | `src/main.py` |

Pasos adicionales:
- Añadir sección `{source}` en `config.json`
- Añadir variable de secreto en `.env`
- Añadir tareas en `Taskfile.yml` (extracción, subida, sync combinado)
- Reutilizar `src/fabric_upload/uploader.py` para la subida (sin modificar)
- Reutilizar `src/config_loader.py` para cargar `config.json`

Ver `README_ampliacion_factorial.md` para un ejemplo real de cómo se aplicó este patrón.

---

## 7. Qué NO tocar

- `src/bc_client/api.py` — no modificar para añadir tablas; la paginación es genérica.
- `src/bc_client/auth.py` — el token OAuth se reutiliza automáticamente.
- `src/fabric_upload/` — infraestructura compartida; no modificar salvo cambio de destino.
- `src/config_loader.py` — cargador compartido entre BC y Factorial.
- `config.json` — no tocar para añadir tablas (solo para cambiar tenant, company, page_size, etc.).

---

## 8. Posibles errores al añadir una tabla

| Error | Causa | Solución |
|-------|-------|----------|
| `'api_path' is not supported; use full 'url'` | Entrada usa `api_path` (campo retirado) | Usar `url` con URL completa |
| `top-level 'base_api_url' is not supported` | YAML tiene `base_api_url` en raíz | Eliminar ese campo |
| `missing 'url'` | Entrada sin campo `url` | Añadir `url` |
| `missing 'name'` | Entrada sin campo `name` | Añadir `name` |
| `Tables file not found` | `tables_file` en `config.json` apunta a ruta incorrecta | Verificar ruta en `config.json` |
| HTTP 401 | Secret expirado o incorrecto | Renovar `BC_CLIENT_SECRET` en `.env` |
| HTTP 404 | URL de la tabla incorrecta | Verificar nombre de página en BC |
| Sin datos en incremental | Checkpoint apunta a fecha futura | Borrar checkpoint en Fabric OneLake |
