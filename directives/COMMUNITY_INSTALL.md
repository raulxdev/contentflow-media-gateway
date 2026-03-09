# Community Install Guide

Guia pensada para compartir esta solucion en una comunidad como Skool.

## Que se despliega

Esta solucion usa un solo repo, pero se crean dos apps separadas en Coolify:

1. `minio`
2. `media-gateway`

No hace falta separar el codigo en dos repos distintos mientras el usuario sepa que:

- `minio` usa `/minio/Dockerfile`
- `media-gateway` usa `/Dockerfile`

## Requisitos previos

- una instancia de Coolify funcional
- acceso para crear 2 aplicaciones
- un volumen persistente para cada app
- un dominio opcional si quiere enlaces publicos temporales

## Orden recomendado

1. desplegar `minio`
2. anadir volumen persistente a `/data`
3. configurar credenciales de MinIO
4. desplegar `media-gateway`
5. anadir volumen persistente a `/app/data`
6. configurar variables `S3_*`
7. probar upload privado
8. opcionalmente configurar dominio publico y `PUBLIC_BASE_URL`

## Paso 1: desplegar MinIO

En Coolify:

- nueva app desde este repo
- `Dockerfile Location`: `/minio/Dockerfile`
- puerto: `9000`
- alias interno: `minio`
- `Volume Mount`:
  - nombre sugerido: `minio-data`
  - `Destination Path`: `/data`

Variables:

```env
MINIO_ROOT_USER=replace-me
MINIO_ROOT_PASSWORD=replace-me
MINIO_BROWSER=off
```

## Paso 2: desplegar media-gateway

En Coolify:

- nueva app desde este repo
- `Dockerfile Location`: `/Dockerfile`
- puerto: `8000`
- alias interno: `media-gateway`
- `Volume Mount`:
  - nombre sugerido: `media-gateway-data`
  - `Destination Path`: `/app/data`

Variables minimas:

```env
SERVICE_API_KEY=replace-me
S3_ENDPOINT=http://minio:9000
S3_REGION=us-east-1
S3_ACCESS_KEY_ID=replace-me
S3_SECRET_ACCESS_KEY=replace-me
S3_BUCKET_USER_VIDEOS=user-videos
S3_BUCKET_TMP_UPLOADS=tmp-uploads
S3_USE_PATH_STYLE=true
PRESIGNED_DOWNLOAD_TTL_SEC=900
MAX_FILE_SIZE_MB=512
WRITE_RATE_LIMIT_PER_MINUTE=30
DATABASE_URL=sqlite:////app/data/media.db
```

Opcionales para links publicos:

```env
PUBLIC_BASE_URL=https://media-share.tudominio.com
PUBLIC_LINK_DEFAULT_TTL_SEC=3600
PUBLIC_LINK_MAX_TTL_SEC=604800
```

## Buckets

El sistema espera estos buckets:

- `user-videos`
- `tmp-uploads`

Politica esperada:

- `user-videos`
  - persistente
  - sirve para imagenes y videos
- `tmp-uploads`
  - temporal
  - expira a `3 dias`

## Como usarlo desde n8n

Usa la guia:

- [N8N_CURL_EXAMPLES.md](/c:/Users/kevin/Documents/minio%20coolify/directives/N8N_CURL_EXAMPLES.md)

Flujo principal:

- `POST /v1/media/upload`
- si quieres publico:
  - `makePublic=true`
  - `publicTtlSec=3600`

## Validacion minima despues de instalar

### Privado

- `GET /health` responde `200`
- un upload a `user-videos` responde `200`
- `downloadUrl` funciona dentro de la red interna

### Publico opcional

Si configura un dominio publico:

- `publicUrl` aparece en la respuesta del upload
- abrir `publicUrl` entrega el archivo

## Errores comunes

### Los buckets desaparecen tras redeploy

Probable causa:

- no hay volumen persistente nativo en Coolify
- o se esta usando `custom_docker_run_options` con `-v ...`

Correccion:

- usar solo `Volume Mount`
- no mezclarlo con mounts manuales

### `Upload to storage failed`

Probable causa:

- bucket inexistente
- credenciales S3 incorrectas
- `S3_ENDPOINT` mal configurado

### El link publico no funciona

Probable causa:

- el dominio no apunta al VPS
- `PUBLIC_BASE_URL` no coincide con el dominio real
- el token ya expiro o fue revocado

## Recomendacion para distribuirlo

Si lo vas a compartir en Skool:

- comparte el repo
- comparte esta guia
- comparte una checklist corta de instalacion
- recomienda probar primero uploads privados y luego publicos
