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
    "path_prefix": "raw/exports",
    "source_name": "business_central"
  }
}
```

Los valores `tables_file` y `output_dir` pueden ser rutas relativas; se resolverán respecto al directorio que contiene `config.json`. Para más detalles consulta `config.example.json`.

## Variables de Entorno (solo secretos)

Crea tu `.env` con los secretos y opcionalmente el nombre del archivo de configuración:

```bash
BC_CLIENT_SECRET=tu_client_secret_aqui
FABRIC_CLIENT_SECRET=tu_fabric_secret_aqui
CONFIG_FILE=./config.json
FABRIC_UPLOAD_ENABLED=true  # opcional, override del campo 'enabled'
```

## Configuración de Tablas

### Archivo YAML Básico

Crea `tables.yaml`:

```yaml
tables:
  - name: Customers
    url: https://api.businesscentral.dynamics.com/v2.0/{tenant}/{environment}/api/data/companies({company})/customers
  - name: Vendors
    url: https://api.businesscentral.dynamics.com/v2.0/{tenant}/{environment}/api/data/companies({company})/vendors
```

### Descubrir URLs de Tablas

Puedes explorar las APIs disponibles en:

- **Empresas**: `/api/data/companies`
- **Metadatos**: `/api/data/$metadata`
- **Entidades**: Consultar la documentación de Business Central API

### Ejemplos de Tablas Comunes

```yaml
tables:
  # Maestros
  - name: Customers
    url: https://api.businesscentral.dynamics.com/v2.0/{tenant}/{environment}/api/data/companies({company})/customers
  - name: Vendors
    url: https://api.businesscentral.dynamics.com/v2.0/{tenant}/{environment}/api/data/companies({company})/vendors
  - name: Items
    url: https://api.businesscentral.dynamics.com/v2.0/{tenant}/{environment}/api/data/companies({company})/items

  # Transacciones
  - name: SalesOrders
    url: https://api.businesscentral.dynamics.com/v2.0/{tenant}/{environment}/api/data/companies({company})/salesOrders
  - name: PurchaseOrders
    url: https://api.businesscentral.dynamics.com/v2.0/{tenant}/{environment}/api/data/companies({company})/purchaseOrders

  # Contabilidad
  - name: GeneralLedgerEntries
    url: https://api.businesscentral.dynamics.com/v2.0/{tenant}/{environment}/api/data/companies({company})/generalLedgerEntries
```

## Validación de Configuración

### Verificar Configuración

```bash
# Ejecución en seco para validar todo
task ingest -- --dry-run --verbose
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
BC_TABLES_FILE=tables-empresa1.yaml BC_COMPANY_ID=guid1 task ingest

# tables-empresa2.yaml  
BC_TABLES_FILE=tables-empresa2.yaml BC_COMPANY_ID=guid2 task ingest
```

### Entornos Diferentes

```bash
# Sandbox
BC_ENVIRONMENT=Sandbox task ingest

# Production
BC_ENVIRONMENT=Production task ingest
```

### Exportación Programada

```bash
# Crear directorio con timestamp
export OUTPUT_DIR="exports_$(date +%Y%m%d_%H%M%S)"
task ingest -- --output-dir "$OUTPUT_DIR" --verbose
```

---

[← Volver al README principal](../README.md) | [Ver Guía de Desarrollo →](desarrollo.md)
