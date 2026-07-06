# Guía de Ampliación — Factorial HR (para contexto de IA)

Este documento describe exactamente cómo añadir un nuevo endpoint a la integración de Factorial HR existente en TAIDY. Está optimizado para ser leído por un asistente de IA como contexto previo a realizar una ampliación, sin necesidad de reanálizar el código.

---

## 1. Arquitectura de la integración Factorial

### Ficheros clave

| Fichero | Rol |
|---------|-----|
| `factorial_tables.yaml` | **Único fichero a tocar** para añadir un nuevo endpoint |
| `config.json` → sección `factorial` | Configuración global (base_url, ruta al YAML, output_dir) |
| `src/factorial_client/config.py` | Carga y valida `factorial_tables.yaml` → produce lista de `TableConfig` |
| `src/factorial_client/api.py` | `FactorialClient` — cursor/OData pagination, chunking por fechas, field filtering |
| `src/factorial_client/exporter.py` | Exportación atómica + merge incremental en master CSV |
| `src/factorial_client/checkpoints.py` | Checkpoints locales en `exports_factorial/.checkpoints/{table}.json` |
| `src/factorial_client/push.py` | CLI de subida a Fabric OneLake |
| `src/factorial_main.py` | CLI de extracción Factorial |

### Variables de entorno requeridas (`.env`)

```
FACTORIAL_API_KEY=<api-key-de-factorial>         # Obligatorio
VERSION_API_FACTORIAL=2026-07-01                 # Obligatorio — debe coincidir con versión activa de la API
FACTORIAL_OVERLAP_DAYS=2                         # Opcional, por defecto 2 días
FABRIC_CLIENT_SECRET=<azure-secret>              # Obligatorio para subida a Fabric
CONFIG_FILE=./config.json                        # Opcional, por defecto ./config.json
```

### Flujo de datos

```
CLI (factorial_main.py) → load_settings() → TableConfig list
    → FactorialClient.fetch_table(table, start_on, end_on)
        → Si chunk_days: divide el rango en ventanas de N días
        → GET {base_url}/{version}/{path} con params
        → Paginación: cursor (meta.has_next_page/after_id) o @odata.nextLink
        → Field filtering: solo columnas declaradas en fields[]
        → Retries exponenciales (tenacity, 5 intentos en 5xx)
    → exporter.export_table()
        → Modo full: exports_factorial/full/{table}.csv (sobreescribe)
        → Modo incremental:
            - exports_factorial/incremental/{timestamp}/{table}.csv
            - Merge en exports_factorial/full/{table}.csv (dedup por todos los campos)
    → Checkpoint guardado: exports_factorial/.checkpoints/{table}.json
    → push.py → FabricUploader → raw/factorial/full/ y raw/factorial/incremental/
```

---

## 2. Añadir un nuevo endpoint (caso más común)

**Único fichero a modificar:** `factorial_tables.yaml`

### Estructura completa de una entrada

```yaml
- name: factorial_nombre_tabla        # snake_case, prefijo factorial_, único en el fichero
  description: Descripción del endpoint  # texto libre, solo informativo
  path: resources/categoria/endpoint  # ruta relativa desde base_url/{version}/
  fields:                             # columnas a extraer (OBLIGATORIO, lista no vacía)
    - id
    - campo1
    - campo2
  # --- Opcionales (ver defaults abajo) ---
  incremental: false                  # true para usar checkpoints por fecha
  date_range: true                    # true → envía start_on/end_on como parámetros
  employee_filter: true               # true → envía employee_ids[] como parámetro
  overlap_days: 2                     # días a re-procesar en modo incremental
  chunk_days: 1                       # divide el rango en ventanas de N días (evita timeouts)
  version: "2026-07-01"              # sobreescribe VERSION_API_FACTORIAL para esta tabla
  extra_params:                       # params estáticos adicionales en la query
    - [nombre_param, "valor"]
```

### Valores por defecto cuando se omiten campos

| Campo | Default |
|-------|---------|
| `incremental` | `false` |
| `date_range` | `true` |
| `employee_filter` | `true` |
| `overlap_days` | Hereda `FACTORIAL_OVERLAP_DAYS` (env var, default 2) |
| `chunk_days` | `null` (sin división) |
| `version` | Hereda `VERSION_API_FACTORIAL` (env var) |
| `extra_params` | `[]` |
| `description` | `""` |

### Reglas de validación (aplicadas por `src/factorial_client/config.py:_parse_table_entry`)

- `name` → string no vacío. **Obligatorio.**
- `path` → string no vacío. **Obligatorio.**
- `fields` → lista no vacía de strings. **Obligatorio.**
- `overlap_days` → entero >= 0 si se especifica.
- `chunk_days` → entero > 0 si se especifica.
- `extra_params` → lista de pares `[key, value]`.

---

## 3. Patrones de uso por tipo de endpoint

### Endpoint sin rango de fechas ni filtro por empleado (catálogos, maestros)

```yaml
- name: factorial_nuevo_catalogo
  description: Catálogo de ejemplo
  path: resources/categoria/catalogo
  date_range: false
  employee_filter: false
  fields:
    - id
    - name
    - code
```

### Endpoint con rango de fechas e incremental (asistencia, fichajes)

```yaml
- name: factorial_nuevo_fichaje
  description: Datos de fichaje
  path: resources/attendance/nuevo_endpoint
  incremental: true
  overlap_days: 7
  chunk_days: 1
  employee_filter: false
  extra_params:
    - [include_non_attendable_employees, "true"]
  fields:
    - employee_id
    - date
    - minutes
```

### Endpoint con filtro por empleado y parámetros extra

```yaml
- name: factorial_nuevo_por_empleado
  description: Datos por empleado
  path: resources/rrhh/nuevo_endpoint
  date_range: true
  employee_filter: true
  extra_params:
    - [only_active, "true"]
  fields:
    - id
    - employee_id
    - value
```

---

## 4. Comportamiento incremental en Factorial

Cuando `incremental: true`:

- **Checkpoint almacenado localmente**: `exports_factorial/.checkpoints/{table_name}.json`
- Formato del checkpoint: `{ "end_on": "2026-06-10" }`
- **En cada ejecución incremental**: empieza desde `checkpoint.end_on - overlap_days`.
- **Primera ejecución** (sin checkpoint): usa el `--start-on` pasado por CLI.
- **Merge en master**: las filas nuevas se combinan con `exports_factorial/full/{table}.csv` deduplicando por todos los campos; las filas nuevas ganan sobre las existentes si todos los campos coinciden.
- Reset de checkpoints: `task extract:factorial -- --start-on ... --end-on ... --reset-checkpoints` (opcionalmente con nombres de tabla).

---

## 5. Comandos CLI de referencia

```bash
# Extracción completa de todas las tablas
task extract:factorial -- --start-on 2025-01-01 --end-on 2026-06-26 --mode full

# Extracción incremental (usa checkpoints)
task extract:factorial -- --start-on 2025-01-01 --end-on 2026-06-26 --mode incremental

# Tabla específica
task extract:factorial -- --start-on 2025-01-01 --end-on 2026-06-26 --tables factorial_nueva_tabla

# Paralelismo (N tablas simultáneas)
task extract:factorial -- --start-on 2025-01-01 --end-on 2026-06-26 --parallel 5

# Dry-run (valida sin llamar API)
task extract:factorial -- --start-on 2025-01-01 --end-on 2026-06-26 --dry-run

# Subir CSVs a Fabric
task push:fabric:factorial

# Extracción + subida combinadas
task sync:factorial -- --start-on 2025-01-01 --end-on 2026-06-26 --mode incremental

# Reset de checkpoints
task extract:factorial -- --start-on 2025-01-01 --end-on 2026-06-26 --reset-checkpoints

# Reset de checkpoints solo para una tabla
task extract:factorial -- --start-on 2025-01-01 --end-on 2026-06-26 --reset-checkpoints factorial_nueva_tabla
```

---

## 6. Estructura de salida en disco

```
exports_factorial/
├── full/
│   └── {table_name}.csv          # Master actualizado (modo full) o merged (modo incremental)
├── incremental/
│   └── {YYYY-MM-DDTHH-MM-SS}/
│       └── {table_name}.csv      # Snapshot de la ejecución incremental
└── .checkpoints/
    └── {table_name}.json         # {"end_on": "YYYY-MM-DD"}
```

---

## 7. Estructura de salida en Fabric OneLake

```
raw/factorial/
├── full/
│   └── {table_name}.csv
└── incremental/
    └── {YYYY-MM-DDTHH-MM-SS}/
        └── {table_name}.csv
```

---

## 8. Qué NO tocar

- `src/factorial_client/api.py` — la lógica de paginación, chunking y field filtering es genérica.
- `src/factorial_client/exporter.py` — el merge incremental es automático.
- `src/factorial_client/checkpoints.py` — la gestión de checkpoints es automática.
- `src/fabric_upload/` — infraestructura compartida con BC; no modificar.
- `config.json` — no tocar para añadir endpoints (solo para cambiar base_url, output_dir, etc.).

---

## 9. Posibles errores al añadir un endpoint

| Error | Causa | Solución |
|-------|-------|----------|
| `'fields' must be a non-empty list` | Entrada sin `fields` | Añadir lista de campos |
| `'name' must be a non-empty string` | Entrada sin `name` | Añadir `name` |
| `'path' must be a non-empty string` | Entrada sin `path` | Añadir `path` |
| `'overlap_days' must be >= 0` | Valor negativo | Usar 0 o positivo |
| `'chunk_days' must be > 0` | Valor cero o negativo | Usar entero positivo |
| HTTP 401 | API Key incorrecta o expirada | Renovar `FACTORIAL_API_KEY` en `.env` |
| HTTP 404 | `path` incorrecto | Verificar ruta en la documentación de Factorial |
| HTTP 422 | Parámetro no reconocido por la API | Revisar `extra_params` o `employee_filter`/`date_range` |
| Sin datos en incremental | Checkpoint muy reciente | Borrar `exports_factorial/.checkpoints/{table}.json` o usar `--reset-checkpoints` |
| Columnas faltantes en CSV | Campo en `fields` no existe en la respuesta de la API | Verificar nombres de campos con un `--dry-run` y revisar la respuesta real |
| Timeout en rangos grandes | Rango de fechas demasiado amplio | Añadir `chunk_days: 1` o reducir el rango |
