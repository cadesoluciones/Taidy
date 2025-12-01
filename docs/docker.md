# 🐳 Guía de Docker

[← Volver al README principal](../README.md)

Esta guía explica cómo construir y ejecutar el extractor de datos de Business Central usando Docker. Docker le permite ejecutar la aplicación en un entorno contenedorizado, garantizando la coherencia y el aislamiento.

## Requisitos Previos

- [Docker](httpshttps://docs.docker.com/get-docker/) instalado en su sistema.

## Construyendo la Imagen de Docker

Para construir la imagen de Docker, ejecute el siguiente comando desde el directorio raíz del proyecto:

```bash
docker build -t bc-data-extractor .
```

Esto creará una imagen de Docker llamada `bc-data-extractor` basada en el `Dockerfile` proporcionado.

## Ejecutando el Contenedor de Docker

Para ejecutar la aplicación solo debe inyectar las variables de entorno sensibles (descritas en `.env.example`). El contenedor ya incluye `config.json`, `tables.yaml` y el resto de los archivos de la app, por lo que no es necesario montarlos. Opcionalmente puede montar `exports/` para persistir los CSV generados fuera del contenedor.

### Ejemplos de Comandos `docker run`

Aquí hay algunos ejemplos de cómo ejecutar el contenedor:

En todos los ejemplos debe proporcionar los secretos `BC_CLIENT_SECRET` y `FABRIC_CLIENT_SECRET` (por ejemplo con `--env-file .env` usando el formato de `.env.example`), ya que son obligatorios.

**A. Ejecutar con un dry-run para probar la configuración:**

Este comando lee las variables desde `.env` y monta el directorio `exports/` para conservar los resultados en el host (opcional).

```bash
docker run --rm \
  --env-file .env \
  -v $(pwd)/exports:/app/exports \
  bc-data-extractor extract:bc -- --dry-run --verbose
```

**B. Ejecutar una extracción completa:**

Este comando ejecuta una extracción completa y, si monta `exports/`, los CSV quedarán en esa carpeta del host.

```bash
docker run --rm \
  --env-file .env \
  -v $(pwd)/exports:/app/exports \
  bc-data-extractor extract:bc -- --verbose
```

**C. Ejecutar el proceso de sincronización completo (extraer y subir):**

Este comando ejecuta todo el proceso de sincronización, que incluye la extracción de los datos y su carga en Microsoft Fabric OneLake.

```bash
docker run --rm \
  --env-file .env \
  -v $(pwd)/exports:/app/exports \
  bc-data-extractor sync
```

Siguiendo estas instrucciones, puede ejecutar fácilmente el extractor de datos de Business Central en un contenedor de Docker, manteniendo su entorno local limpio y asegurando que la aplicación se ejecute de manera consistente.
