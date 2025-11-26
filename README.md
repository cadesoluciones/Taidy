# Extracción de Datos de Business Central - PoC

Esta prueba de concepto demuestra cómo autenticarse contra Microsoft Dynamics 365 Business Central, recuperar datos de tablas a través de la API OData, y exportar el conjunto completo de resultados a archivos CSV. La paginación se basa en `@odata.nextLink` de Business Central junto con el encabezado `Prefer: odata.maxpagesize=<N>` para que las tablas con más de 100 filas se transmitan completamente. El código sigue un enfoque dirigido por pruebas para que los comportamientos principales (carga de configuración, autenticación, paginación, exportación, orquestación) estén cubiertos por pruebas unitarias.

## Estructura del Proyecto

- `api_test.py` – Punto de entrada CLI que conecta configuración, autenticación, cliente API y exportador CSV
- `bc_client/` – Módulos de soporte:
  - `config.py` – Cargador de configuración basado en variables de entorno
  - `auth.py` – Flujo OAuth client credentials con caché de tokens
  - `api.py` – Wrapper OData de Business Central con paginación
  - `exporter.py` – Utilidades de exportación CSV con nombres de archivo seguros
- `tests/` – Pruebas unitarias que cubren los módulos anteriores; herméticas mediante mocks

## Requisitos Previos

- Python 3.12+
- Acceso a Business Central con una aplicación Azure AD configurada para client-credentials

## Instrucciones de Configuración

1. **Crear entorno virtual e instalar dependencias (vía `uv`)**

   ```bash
   uv venv
   source .venv/bin/activate
   uv pip install -r requirements.txt
   ```

2. **Proporcionar configuración**

   Copia `.env.example` a `.env` para credenciales y configuración general, luego copia `tables.example.yaml` a `tables.yaml` (o otra ruta de tu elección) para declarar las tablas que quieres exportar.

   ```bash
   cp .env.example .env
   cp tables.example.yaml tables.yaml
   $EDITOR .env
   $EDITOR tables.yaml
   ```

   Variables clave:

   - `BC_TENANT_ID` – ID del tenant de Azure AD (GUID)
   - `BC_ENVIRONMENT` – Nombre del entorno de Business Central (ej., `Sandbox`, `Production`)
   - `BC_CLIENT_ID` / `BC_CLIENT_SECRET` – Credenciales del registro de aplicación
   - `BC_SCOPE` – Usualmente `https://api.businesscentral.dynamics.com/.default`
   - `BC_COMPANY_ID` – *Opcional* GUID de la empresa objetivo (descubrir vía `.../api/data/companies`; dejar en blanco si es desconocido)
   - `BC_TABLES_FILE` – Ruta al archivo YAML que describe nombres y URLs de tablas (por defecto `tables.yaml` si se omite)
   - `BC_PAGE_SIZE` – *Opcional* Anulación del tamaño de chunk de paginación; por defecto 1000 filas por solicitud y controla el encabezado `Prefer: odata.maxpagesize`
   - `BC_OUTPUT_DIR` – Directorio donde se escribirán los archivos CSV

   El archivo YAML debe verse así:

   ```yaml
   tables:
     - name: Customers
       url: https://api.businesscentral.dynamics.com/v2.0/<TENANT>/<ENV>/api/data/companies(<COMPANY_ID>)/customers
     - name: Vendors
       url: https://api.businesscentral.dynamics.com/v2.0/<TENANT>/<ENV>/api/data/companies(<COMPANY_ID>)/vendors
   ```

   Elige valores `name` compactos—se usarán para anulaciones CLI (ej., `--tables Customers`).

## Ejecutar las Pruebas Automatizadas

Las pruebas unitarias validan el análisis de configuración, ciclo de vida de tokens, lógica de paginación, exportación CSV y comportamiento CLI. Ejécutalas después de cada cambio.

```bash
uv run pytest -q
```

La suite es hermética y no requiere acceso en vivo a Business Central. Cuando agregues pruebas de integración más tarde, márcalas con `@pytest.mark.integration` para que puedan omitirse por defecto.

## Flujo de Verificación Manual

1. **Ejecución en seco** – Confirma configuración y selección de tablas sin llamar a la API:

   ```bash
   uv run python api_test.py --dry-run --verbose
   ```

2. **Obtener datos** – Remueve `--dry-run` una vez que las credenciales estén confirmadas:

   ```bash
   uv run python api_test.py --verbose
   ```

   Anulaciones opcionales:

   - `--tables Customers Vendors` – Obtiene solo los nombres de tabla listados definidos en tu configuración YAML
   - `--page-size 1000` – Ajusta la sugerencia `Prefer: odata.maxpagesize` para conjuntos de datos grandes (por defecto 1000 cuando no se establece)
   - `--output-dir ./exports_run_$(date +%Y%m%d)` – Personaliza la ubicación de salida

3. Inspecciona los archivos CSV generados bajo `BC_OUTPUT_DIR`. Los archivos se nombran según la tabla (minúsculas con guiones bajos) y se escriben atómicamente para evitar resultados parciales.

## Extendiendo el PoC

- Agregar pruebas de integración que llamen a la API en vivo usando credenciales cargadas desde `.env`, protegidas detrás de una bandera opt-in (ej., `pytest -m integration`)
- Introducir políticas de reintento/backoff (ej., vía `tenacity`) alrededor de llamadas API si la limitación de velocidad se convierte en un problema
- Transmitir filas directamente al almacenamiento en la nube (S3, Azure Blob) una vez que la exportación CSV esté validada localmente
- Implementar estrategias de sincronización incremental rastreando timestamps de última modificación o usando filtros OData

## Solución de Problemas

- **Fallas de autenticación** – Verifica que el registro de aplicación Azure AD tenga los permisos delegados/de aplicación de `Dynamics 365 Business Central` y que el secreto esté vigente
- **Errores de `Missing required configuration`** – Asegúrate de que tu `.env` coincida con `.env.example` y que ninguna clave esté en blanco
- **Problemas de esquema inesperados** – Confirma que los nombres de tabla referencien entidades de la API de Business Central (ver `https://api.businesscentral.dynamics.com/v2.0/<tenant>/<environment>/api/data/$metadata`)

Para depuración adicional, vuelve a ejecutar con `--verbose` para emitir logging de nivel debug e inspeccionar respuestas HTTP.