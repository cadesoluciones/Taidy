# 🔧 Configuración Detallada

[← Volver al README principal](../README.md)

## Configuración de Azure AD

### 1. Crear Aplicación en Azure AD

1. Ve al [Portal de Azure](https://portal.azure.com)
2. Navega a **Azure Active Directory** > **App registrations**
3. Clic en **New registration**
4. Configura:
   - **Name**: `BC Data Extractor` (o el nombre que prefieras)
   - **Supported account types**: `Accounts in this organizational directory only`
   - **Redirect URI**: Dejar vacío
5. Clic en **Register**

### 2. Configurar Permisos

1. En tu aplicación, ve a **API permissions**
2. Clic en **Add a permission**
3. Selecciona **Dynamics 365 Business Central**
4. Selecciona **Application permissions**
5. Marca **API.ReadWrite.All**
6. Clic en **Add permissions**
7. **Importante**: Clic en **Grant admin consent** y confirma

### 3. Crear Client Secret

1. Ve a **Certificates & secrets**
2. Clic en **New client secret**
3. Descripción: `BC Extractor Secret`
4. Expires: `24 months` (recomendado)
5. Clic en **Add**
6. **Copia el valor inmediatamente** (no se mostrará de nuevo)

### 4. Obtener IDs Necesarios

- **Tenant ID**: En **Overview** de tu aplicación
- **Client ID**: En **Overview** de tu aplicación (Application ID)
- **Client Secret**: El valor copiado en el paso anterior

## Configuración de archivos [/config.json]

El resto de la configuración (tenant, endpoints, tablas, Lakehouse, prefijos, etc.) vive ahora en `config.json`. Copia el ejemplo y adapta los valores no secretos:

```bash
cp config.example.json config.json
```

Dentro de `config.json` debes rellenar al menos las secciones `business_central` y `fabric_upload` con los campos que usas en tu entorno. Las claves deben incluir lo siguiente:

```json
{
  "business_central": {
    "tenant_id": "...",
    "environment": "Sandbox",
    "client_id": "...",
    "scope": "https://api.businesscentral.dynamics.com/.default",
    "token_url": "https://login.microsoftonline.com/<tenant>/oauth2/v2.0/token",
    "company_name": "Company",
    "tables_file": "tables.yaml",
    "output_dir": "./exports"
  },
  "fabric_upload": {
    "tenant_id": "...",
    "client_id": "13457bce-b857-4544-8d36-73ab06ca8e92",
    "workspace_name": "Sandbox",
    "lakehouse_name": "Lakehouse",
    "workspace_id": "...",
    "lakehouse_id": "...",
    "path_prefix": "raw",
    "source_name": "business_central"
  }
}
```

Los valores `tables_file` y `output_dir` pueden ser rutas relativas; se resolverán respecto al directorio que contiene `config.json`. El `output_dir` actúa como raíz y el sistema creará automáticamente subcarpetas `full/` para snapshots completos o `incremental/<timestamp>/` para corridas incrementales. Para más detalles consulta `config.example.json`.

> 📁 **OneLake:** con esta configuración los snapshots completos subirán a `raw/business_central/full/<tabla>.csv` y las corridas incrementales a `raw/business_central/incremental/<tabla>/<run_timestamp>/<tabla>.csv`. Los checkpoints permanecen en `raw/checkpoints/business_central/<tabla>.json`.

## Variables de Entorno (solo secretos)

Crea tu `.env` con los secretos y opcionalmente el nombre del archivo de configuración:

```bash
BC_CLIENT_SECRET=tu_client_secret_aqui
FABRIC_CLIENT_SECRET=tu_fabric_secret_aqui
CONFIG_FILE=./config.json
FABRIC_UPLOAD_ENABLED=true  # opcional, override del campo 'enabled'
```

## Configuración de Tablas

El archivo `tables.yaml` contiene la configuración de las tablas a extraer. Personalízalo según tus necesidades:

```yaml
base_api_url: https://api.businesscentral.dynamics.com/v2.0/{tenant}/{environment}/api/data/companies({company})
tables:
  - name: Customers
    api_path: customers
  - name: Vendors
    api_path: vendors
```

### Estructura de URLs

**Patrón estándar de Business Central (base + path):**

```text
base_api_url: https://api.businesscentral.dynamics.com/v2.0/{tenant}/{environment}/api/data/companies({company})
api_path: {tabla}
```

**Patrón OData personalizado (base + path):**

```text
base_api_url: https://api.businesscentral.dynamics.com/v2.0/{tenant}/{environment}/ODataV4/Company('{company_name}')
api_path: {api_endpoint}
```

> 📝 **Nota**: Las variables `{tenant}`, `{environment}`, `{company}` se reemplazan automáticamente con los valores de tu `config.json`.

### Descubrir URLs de Tablas

Puedes explorar las APIs disponibles en:

- **Empresas**: `/api/data/companies`
- **Metadatos**: `/api/data/$metadata`
- **Entidades**: Consultar la documentación de Business Central API

### Ejemplos de Tablas Comunes

```yaml
base_api_url: https://api.businesscentral.dynamics.com/v2.0/{tenant}/{environment}/api/data/companies({company})
tables:
  # Maestros
  - name: Customers
    api_path: customers
  - name: Vendors
    api_path: vendors
  - name: Items
    api_path: items

  # Transacciones
  - name: SalesOrders
    api_path: salesOrders
  - name: PurchaseOrders
    api_path: purchaseOrders

  # Contabilidad
  - name: GeneralLedgerEntries
    api_path: generalLedgerEntries
```

### Campos Opcionales para Ingesta Incremental

Cada tabla puede activar la sincronización incremental declarando `incremental: true`. Esto asume que el endpoint expone la columna `SystemModifiedAt`. Si la columna no existe, simplemente omite la clave para que la tabla se procese como snapshot completo.

```yaml
base_api_url: https://.../Company('nombre')
tables:
  - name: bc_job_headers
    api_path: jobs
    incremental: true   # Usa SystemModifiedAt automáticamente

  - name: bc_customer_list  # sin SystemModifiedAt
    api_path: customers
    # incremental ausente => snapshot completo
```

> ⚠️ No hay soporte para otras columnas: si `SystemModifiedAt` no está disponible, la tabla se queda como carga completa.

## Validación de Configuración

### Verificar Configuración

```bash
# Ejecución en seco para validar todo
task extract:bc -- --dry-run --verbose
```

Este comando verifica:

- ✅ Variables de entorno
- ✅ Autenticación OAuth
- ✅ URLs de tablas
- ✅ Permisos de escritura

## Casos de Uso Específicos

### Múltiples Empresas

Si tienes múltiples empresas, crea archivos YAML separados:

```bash
# tables-empresa1.yaml
BC_TABLES_FILE=tables-empresa1.yaml BC_COMPANY_ID=guid1 task extract:bc

# tables-empresa2.yaml  
BC_TABLES_FILE=tables-empresa2.yaml BC_COMPANY_ID=guid2 task extract:bc
```

### Entornos Diferentes

```bash
# Sandbox
BC_ENVIRONMENT=Sandbox task extract:bc

# Production
BC_ENVIRONMENT=Production task extract:bc
```

### Exportación Programada

```bash
# Crear directorio con timestamp
export OUTPUT_DIR="exports_$(date +%Y%m%d_%H%M%S)"
task extract:bc -- --output-dir "$OUTPUT_DIR" --verbose
```

---

[← Volver al README principal](../README.md) | [Ver Guía de Desarrollo →](desarrollo.md)
