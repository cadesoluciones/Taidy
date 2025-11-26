# 🛠️ Guía de Desarrollo

[← Volver al README principal](../README.md)

## Arquitectura del Sistema

### Componentes Principales

- **main.py** - CLI y orquestación
- **config.py** - Configuración y validación
- **auth.py** - OAuth con caché de tokens
- **api.py** - Cliente OData con paginación
- **exporter.py** - Exportación CSV atómica

### Flujo de Datos

1. **Configuración** → Carga variables de entorno y YAML
2. **Autenticación** → Obtiene token OAuth con caché thread-safe
3. **Descubrimiento** → Valida URLs de tablas
4. **Extracción** → Paginación automática vía `@odata.nextLink`
5. **Exportación** → Escritura atómica de archivos CSV

### Patrones de Diseño

- **Dependency Injection** - Componentes testeable
- **Protocol-based** - Interfaces flexibles
- **Immutable Data** - Estructuras seguras
- **Thread Safety** - Caché compartido seguro

## Configuración del Entorno

### Instalación

```bash
# Clonar y configurar
git clone <repo>
cd cade-ingesta-bc

# Crear entorno virtual
uv venv
source .venv/bin/activate

# Instalar dependencias
uv pip install -r requirements.txt

# Configurar pre-commit hooks
pre-commit install
```

### Herramientas de Desarrollo

```bash
# Formatear código
task lint:format

# Verificar calidad
task lint:check

# Ejecutar todas las pruebas
task test:run

# Ejecutar con cobertura
task test:run COVERAGE=true
```

## Estrategia de Pruebas

### Tipos de Pruebas

**Unit Tests** (`tests/unit/`) - Rápidas, aisladas

```bash
pytest tests/unit/ -v
```

**Integration Tests** (`tests/integration/`) - Componentes integrados

```bash
pytest tests/integration/ -v
```

**Acceptance Tests** (`tests/acceptance/`) - API real (requiere `.env`)

```bash
pytest -m acceptance -v
```

### Ejecutar Pruebas

```bash
# Por defecto: unit + integration
pytest

# Solo pruebas rápidas
pytest tests/unit/

# Con cobertura
pytest --cov=src --cov-report=html

# Paralelo (más rápido)
pytest -n auto
```

### Estructura de Pruebas

- **Arrange** - Configurar mocks y datos
- **Act** - Ejecutar función bajo prueba
- **Assert** - Verificar resultado esperado

## Estándares de Código

### Requisitos

- **Type Hints** - 100% cobertura de tipos
- **Docstrings** - Documentación de funciones públicas
- **Error Handling** - Excepciones específicas con contexto
- **Testing** - Pruebas para toda funcionalidad nueva

## Resilencia de Red

### Configuración de Reintentos

- **5 intentos** con backoff exponencial
- **Errores de red** - ConnectionError, Timeout
- **NO reintenta** - Errores de autenticación (4xx, 5xx)

### Errores que NO se reintentan

- Errores de autenticación (401, 403)
- Errores de cliente (4xx)
- Errores de servidor (5xx)

## Troubleshooting Avanzado

### Debug y Logs

```bash
# Logs detallados
task ingest -- --verbose --dry-run

# Verificar configuración
cat config.json
```

### Problemas Comunes

**Error: `Missing required configuration`**

```bash
# Verificar configuración
cat config.json
```

**Error: `Token request failed`**

- Verificar Client ID/Secret
- Confirmar permisos en Azure AD
- Verificar que el admin consent fue otorgado

**Error: `Failed to fetch data`**

- Verificar URLs en `tables.yaml`
- Confirmar que el Company ID existe
- Probar endpoint manualmente con curl

**Error: `Permission denied`**

- Verificar permisos de escritura en `BC_OUTPUT_DIR`
- Confirmar que el directorio existe

## Extensión del Proyecto

### Ideas de Extensión

- **Nuevos Exportadores** - JSON, Parquet, bases de datos
- **Filtros OData** - Sincronización incremental
- **Cloud Storage** - S3, Azure Blob, Google Cloud
- **Monitoreo** - Métricas y alertas

## Contribuir al Proyecto

### Flujo de Desarrollo

1. **Fork** del repositorio
2. **Crear branch** para feature: `git checkout -b feature/nueva-funcionalidad`
3. **Escribir pruebas** primero (TDD)
4. **Implementar** funcionalidad
5. **Verificar** que todas las pruebas pasan
6. **Commit** con mensaje descriptivo
7. **Push** y crear **Pull Request**

### Checklist Pre-Commit

- [ ] Todas las pruebas pasan: `pytest`
- [ ] Código formateado: `task lint:format`
- [ ] Sin errores de lint: `task lint:check`
- [ ] Type hints completos
- [ ] Docstrings actualizados
- [ ] Tests para nueva funcionalidad

---

[← Volver al README principal](../README.md) | [Ver Configuración →](configuracion.md)
