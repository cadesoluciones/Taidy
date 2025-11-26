# ☁️ Configuración de Microsoft Fabric OneLake

[← Volver al README principal](../README.md)

Guía completa para configurar la subida automática de archivos CSV a Microsoft Fabric OneLake. Esta funcionalidad permite almacenar los datos extraídos de Business Central directamente en un Lakehouse de Fabric para análisis posterior.

## 📋 Requisitos Previos

- **Licencia de Microsoft Fabric** o trial activo
- **Permisos de administrador** en el tenant de Fabric (para configuración inicial)
- **Workspace compartido** en Fabric (no funciona con "Mi área de trabajo")
- **Aplicación registrada** en Entra ID con permisos apropiados

## 🏗️ Arquitectura de la Solución

```text
Business Central API → CSV Exports → Fabric OneLake
                                        ↓
                                   Lakehouse Files
                                        ↓
                              raw/exports/business_central/
                                   ├── tabla1/2025/11/26/
                                   ├── tabla2/2025/11/26/
                                   └── tabla3/2025/11/26/
```

## 🚀 Configuración Paso a Paso

### 1. Configurar Workspace de Fabric

#### 1.1 Crear o Seleccionar Workspace

1. Abre **Microsoft Fabric** ([app.fabric.microsoft.com](https://app.fabric.microsoft.com))
2. Ve a **Workspaces** en el panel izquierdo
3. Selecciona un workspace existente **O** crea uno nuevo:
   - Clic en **Nuevo workspace**
   - Nombre: `CADE-DataLake` (o el que prefieras)
   - Descripción: `Workspace para ingesta de datos de Business Central`
   - Clic en **Crear**

> ⚠️ **Importante**: No uses "Mi área de trabajo" ya que no permite asignar permisos a aplicaciones.

#### 1.2 Obtener IDs del Workspace

1. Una vez en el workspace, copia la URL del navegador
2. Extrae el **Workspace ID** de la URL:

   ```text
   https://app.fabric.microsoft.com/groups/44b1286f-484d-41b1-9259-6904105d8d09/...
                                          ↑ Este es tu Workspace ID
   ```

3. Guarda este ID para la configuración posterior

### 2. Crear Lakehouse

#### 2.1 Crear el Lakehouse

1. Dentro del workspace, clic en **Nuevo**
2. Selecciona **Lakehouse**
3. Nombre: `BusinessCentralLakehouse` (o el que prefieras)
4. Clic en **Crear**

#### 2.2 Configurar Estructura de Carpetas

1. Abre el Lakehouse recién creado
2. Ve a la sección **Files** (no Tables)
3. Crea la estructura de carpetas:

   ```text
   Files/
   └── raw/
       └── exports/
           └── business_central/
   ```

4. Para crear carpetas: clic derecho en Files → **Nueva carpeta**

#### 2.3 Obtener IDs del Lakehouse

1. Copia la URL del Lakehouse:

   ```text
   https://app.fabric.microsoft.com/groups/.../lakehouses/1287f84f-d048-4967-a27f-b3f3019345d9/...
                                                        ↑ Este es tu Lakehouse ID
   ```

2. Guarda este ID para la configuración

### 3. Configurar Tenant de Fabric

#### 3.1 Habilitar Configuraciones del Tenant

**Si eres administrador de Fabric:**

1. Ve al **Portal de administración de Fabric**
2. Navega a **Configuración del tenant**
3. Habilita las siguientes opciones:
   - **"Las entidades de servicio pueden llamar a las API públicas de Fabric"**
   - **"Los usuarios pueden acceder a los datos almacenados en OneLake con aplicaciones externas a Fabric"**
4. Guarda los cambios

**Si NO eres administrador:**

Solicita al administrador de Fabric que habilite estas dos configuraciones específicas.

### 4. Registrar Aplicación en Entra ID

#### 4.1 Crear la Aplicación

1. Ve al [Centro de administración de Entra ID](https://entra.microsoft.com)
2. Navega a **Registros de aplicaciones**
3. Clic en **Nuevo registro**
4. Configura:
   - **Nombre**: `CADE-Fabric-Uploader`
   - **Tipos de cuenta admitidos**: `Solo las cuentas de este directorio organizativo`
   - **URI de redirección**: Dejar vacío
5. Clic en **Registrar**

#### 4.2 Obtener Credenciales

1. En la página **Información general** de la aplicación, anota:
   - **Id. de aplicación (cliente)**: `13457bce-b857-4544-8d36-73ab06ca8e92`
   - **Id. de directorio (inquilino)**: `2d6ec162-8eb4-42d3-93e2-7ee771e85da5`

#### 4.3 Crear Client Secret

1. Ve a **Certificados y secretos**
2. Clic en **Nuevo secreto de cliente**
3. Configura:
   - **Descripción**: `FabricUploaderSecret`
   - **Expira**: `24 meses` (recomendado)
4. Clic en **Agregar**
5. **Copia el valor del secreto inmediatamente** (no se mostrará de nuevo)

### 5. Asignar Permisos en Fabric

#### 5.1 Agregar la Aplicación al Workspace

1. En el workspace de Fabric, clic en **Administrar acceso**
2. Clic en **Agregar personas o grupos**
3. Busca el nombre de tu aplicación: `CADE-Fabric-Uploader`
4. Selecciona el rol **Colaborador**
5. Clic en **Agregar**

#### 5.2 Verificar Permisos

1. Confirma que la aplicación aparece en la lista de acceso
2. Verifica que tiene el rol **Colaborador** asignado

## ⚙️ Configuración del Proyecto

### 6.1 Actualizar config.json

Edita tu archivo `config.json` y agrega/actualiza la sección `fabric_upload`:

```json
{
  "business_central": {
    // ... configuración existente
  },
  "fabric_upload": {
    "tenant_id": "2d6ec162-8eb4-42d3-93e2-7ee771e85da5",
    "client_id": "13457bce-b857-4544-8d36-73ab06ca8e92",
    "workspace_name": "CADE-DataLake",
    "lakehouse_name": "BusinessCentralLakehouse",
    "workspace_id": "44b1286f-484d-41b1-9259-6904105d8d09",
    "lakehouse_id": "1287f84f-d048-4967-a27f-b3f3019345d9",
    "path_prefix": "raw/exports",
    "source_name": "business_central",
    "overwrite": true,
    "max_retries": 3,
    "enabled": true
  }
}
```

### 6.2 Actualizar .env

Agrega el secreto de Fabric a tu archivo `.env`:

```bash
# Secretos existentes
BC_CLIENT_SECRET=tu_bc_secret_aqui

# Nuevo secreto de Fabric
FABRIC_CLIENT_SECRET=2~k8Q~jumnNuzAiByh55p9LHuNgh0bMUHK1oobhc

# Configuración opcional
CONFIG_FILE=./config.json
```

## 🧪 Probar la Configuración

### 7.1 Validar Configuración

```bash
# Verificar que la configuración es correcta
task fabric:upload -- --output-dir ./exports --dry-run --verbose
```

### 7.2 Subida de Prueba

```bash
# 1. Extraer datos de Business Central
task ingest -- --verbose

# 2. Subir a Fabric OneLake
task fabric:upload -- --output-dir ./exports --verbose

# Opciones adicionales:
# --skip-existing: Saltar archivos que ya existen (por defecto sobrescribe)
# --dry-run: Ver qué archivos se subirían sin subirlos
task fabric:upload -- --output-dir ./exports --skip-existing
```

### 7.3 Verificar en Fabric

1. Ve a tu workspace en Fabric
2. Abre el Lakehouse
3. Navega a **Files** → **raw** → **exports** → **business_central**
4. Verifica que aparecen las carpetas por tabla y fecha:

   ```text
   business_central/
   ├── customers/2025/11/26/customers.csv
   ├── vendors/2025/11/26/vendors.csv
   └── items/2025/11/26/items.csv
   ```

## 🔧 Configuración Avanzada

### Parámetros Opcionales

| Parámetro | Descripción | Valor por Defecto |
|-----------|-------------|-------------------|
| `path_prefix` | Prefijo de ruta en OneLake | `raw/exports` |
| `source_name` | Nombre del sistema fuente | `business_central` |
| `overwrite` | Sobrescribir archivos existentes | `true` |
| `max_retries` | Reintentos en caso de error | `3` |
| `enabled` | Habilitar subidas automáticas | `true` |

### Estructura de Rutas

Los archivos se organizan automáticamente con esta estructura:

```text
Files/
└── {path_prefix}/           # raw/exports
    └── {source_name}/       # business_central
        └── {tabla}/         # customers, vendors, etc.
            └── {año}/       # 2025
                └── {mes}/   # 11
                    └── {día}/ # 26
                        └── {tabla}.csv
```

## 🔒 Seguridad y Mejores Prácticas

### Rotación de Secretos

1. **Crear nuevo secreto** en Entra ID antes de que expire el actual
2. **Actualizar .env** con el nuevo valor
3. **Probar** que funciona correctamente
4. **Eliminar** el secreto anterior

### Permisos Mínimos

- **Workspace**: Rol **Colaborador** (no Admin)
- **Entra ID**: Solo permisos de aplicación, no delegados
- **Tenant**: Solo las dos configuraciones mencionadas

### Monitoreo

```bash
# Logs detallados para troubleshooting
task fabric:upload -- --output-dir ./exports --verbose

# Verificar archivos sin subirlos
task fabric:upload -- --output-dir ./exports --dry-run
```

## 🚨 Troubleshooting

### Errores Comunes

**Error: `FriendlyNameSupportDisabled`**

- **Causa**: Configuración incorrecta de workspace/lakehouse IDs
- **Solución**: Verificar que `workspace_name` y `lakehouse_name` son correctos

**Error: `Missing required Fabric upload configuration`**

- **Causa**: Falta `FABRIC_CLIENT_SECRET` en `.env`
- **Solución**: Agregar el secreto al archivo `.env`

**Error: `403 Forbidden`**

- **Causa**: La aplicación no tiene permisos en el workspace
- **Solución**: Verificar que está agregada como Colaborador

**Error: `Tenant settings not enabled`**

- **Causa**: Configuraciones del tenant no habilitadas
- **Solución**: Contactar al administrador de Fabric

### Verificación de Configuración

```bash
# Verificar variables de entorno
env | grep FABRIC_

# Probar conectividad
task fabric:upload -- --dry-run --verbose

# Verificar estructura de archivos
ls -la exports/
```

## 📊 Uso en Producción

### Automatización

```bash
#!/bin/bash
# Script de ejemplo para automatización

# 1. Extraer datos
task ingest -- --verbose --output-dir "./exports_$(date +%Y%m%d)"

# 2. Subir a Fabric
task fabric:upload -- --output-dir "./exports_$(date +%Y%m%d)" --verbose

# 3. Limpiar archivos locales antiguos (opcional)
find ./exports_* -type d -mtime +7 -exec rm -rf {} \;
```

### Monitoreo y Alertas

- Configurar logs centralizados
- Monitorear el tamaño de archivos subidos
- Alertas en caso de fallos de subida
- Verificación periódica de permisos

---

[← Volver al README principal](../README.md) | [Ver Configuración →](configuracion.md) | [Ver Desarrollo →](desarrollo.md)
