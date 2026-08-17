# Plan: Sincronización real BC ↔ HubSpot ("Sincronizar")

Estado: **propuesta de arquitectura, sin implementar todavía.** Retomar cuando se decida avanzar de la Fase 1 (solo lectura: mapeos + Comparar, ya construida) a la escritura real.

## Contexto

Ya existe y funciona:
- Modelo de mapeo (`sync_mappings.yaml`): tabla origen/destino, clave de coincidencia, campo de fecha maestro, pares de campos.
- Motor de comparación de solo lectura (`src/sync_engine/compare.py`): live-read de ambos lados, clasifica en crear-en-destino / crear-en-origen / actualizar-destino / actualizar-origen / sin-cambios / saltado-por-clave.
- UI: Sincronización → Comparar (Operator+Admin) y Sincronización → Mapeos (Admin).
- `BC_ENVIRONMENT` (PRODUCTION/SANDBOX_CADE/...) selecciona el entorno de Business Central; Fabric/Factorial/HubSpot no tienen concepto de entorno.

Falta: el botón **"Sincronizar"** que aplique de verdad los cambios, con escritura real en BC y HubSpot.

## Problemas de fondo detectados (por qué no basta con "escribir lo que diga Comparar")

### 1. El email como clave es frágil
Si el email cambia en cualquiera de los dos sistemas, el emparejamiento por email se rompe y un contacto ya sincronizado se interpretaría como nuevo → duplicado.

**Propuesta**: mapeo de identidad persistente, propio de la app (no requiere tocar BC ni HubSpot): una tabla ligera (SQLite o JSON, por mapeo) que guarda, una vez emparejados o creados, el par `(SystemId de BC, id de HubSpot)`. Las ejecuciones futuras emparejan primero por ese par de IDs (robusto a cambios de email) y solo caen al email como respaldo para registros que aún no están en la tabla. Esta misma tabla es donde vive el checkpoint anti-bucle (fecha de cada lado en el último sync) — es la misma pieza de estado, ampliada.

### 2. Usar el upsert nativo de HubSpot en vez de decidir nosotros
`POST /crm/v3/objects/contacts/batch/upsert` con `idProperty: email`: una sola llamada hace "si existe por este email, actualiza; si no, créalo", hasta 100 registros por llamada.
- Elimina la ventana de carrera entre comparar y escribir.
- Con 578 altas pendientes (dato real de la primera comparación BC→HubSpot), son 6 llamadas en vez de 578.
- BC no tiene un upsert equivalente — ahí la decisión (crear vs. `PATCH`) la hacemos nosotros.

### 3. Escribir en BC exige manejar el ETag (concurrencia optimista)
La página de contactos de BC (50403) tiene `ModifyAllowed = true`, pero cada `PATCH` requiere cabecera `If-Match: <etag>`. Si el registro cambió desde que lo leímos, BC devuelve `412 Precondition Failed`.

**Propuesta**: releer el ETag justo antes de escribir (no confiar en el capturado durante "Comparar"); si da 412, reintentar una vez con lectura fresca antes de darlo por fallido.

### 4. Orden de ejecución: primero altas, luego actualizaciones
Las altas no arriesgan perder datos existentes — ejecutarlas primero. Las actualizaciones sí "pisan" algo — ejecutarlas después, y actualizar el checkpoint de identidad solo tras confirmar que la escritura tuvo éxito (nunca de forma optimista).

### 5. Cortafuegos de cantidad
Si por un error de configuración de la clave "Sincronizar" fuera a tocar miles de registros de golpe, debe pedir confirmación explícita en vez de ejecutarlo sin más.

**Propuesta**: umbral configurable (a decidir, ej. 50 acciones) por encima del cual se exige un "sí, estoy seguro" adicional.

### 6. Auditoría
Cada "Sincronizar" debe quedar registrado en Historial igual que un extract/upload, con desglose por registro (creado/actualizado/omitido/fallido) — mismo patrón que ya usa `FabricUploader` (un fallo en un registro no aborta el resto del lote).

### 7. Polling vs. Webhooks
HubSpot soporta webhooks (tiempo real), pero exige un endpoint público receptor y más infraestructura. Recomendación: seguir con el patrón actual de la app (bajo demanda o programado vía Schedules) — webhooks quedaría como evolución futura si la latencia llega a importar.

## Dudas pendientes de responder antes de implementar

1. ¿El mapeo de identidad (BC SystemId ↔ HubSpot id) vive solo en nuestro lado (tabla propia), sin pedir un campo personalizado nuevo en BC/HubSpot?
2. ¿Umbral razonable para el cortafuegos de cantidad, o prefieres confirmación manual siempre la primera vez que se usa un mapeo nuevo?
3. Para BC, con volumen bajo hoy (2 altas pendientes en la primera comparación), ¿asumimos secuencial y dejamos el `$batch` de OData para si el volumen crece?

## Fases de implementación propuestas (pendientes de aprobar)

1. Mapeo de identidad persistente (tabla propia) + checkpoint anti-bucle integrado ahí.
2. Escritura mínima en BC (POST crear, PATCH actualizar con manejo de ETag/412).
3. Escritura en HubSpot vía batch upsert (crear + actualizar en una llamada, por lotes de 100).
4. Orquestación de "Sincronizar": recalcula el estado (no confía en un informe de Comparar antiguo), aplica altas → actualizaciones, cortafuegos de cantidad, registro en Historial, selector de dirección (BC→HubSpot / HubSpot→BC / bidireccional).
