# Internal Media Storage for Coolify

Solucion lista para desplegar en Coolify para tener almacenamiento interno con:

- `MinIO` como storage S3-compatible privado
- `media-gateway` para uploads, URLs internas y URLs publicas temporales

Esta base esta pensada para n8n y microservicios internos, con opcion de compartir enlaces publicos temporales cuando se configure un dominio.

## Que incluye este repo

- `Dockerfile`
  - imagen del `media-gateway`
- `minio/Dockerfile`
  - imagen wrapper para desplegar `MinIO` en Coolify
- `directives/README.md`
  - guia operativa del sistema
- `directives/N8N_CURL_EXAMPLES.md`
  - ejemplos importables en n8n

## Arquitectura

### 1. MinIO

- recurso privado en Coolify
- alias interno recomendado: `minio`
- volumen persistente en `/data`
- buckets:
  - `user-videos`
  - `tmp-uploads`

### 2. media-gateway

- recurso privado o publico controlado en Coolify
- alias interno recomendado: `media-gateway`
- volumen persistente en `/app/data`
- expone:
  - upload en un paso
  - `downloadUrl` interna
  - `publicUrl` temporal opcional

## Despliegue rapido en Coolify

### MinIO

- crea una app nueva desde este repo
- `Build Pack`: `Dockerfile`
- `Dockerfile Location`: `/minio/Dockerfile`
- puerto: `9000`
- alias interno: `minio`
- volumen persistente:
  - `Volume Mount`
  - `Destination Path`: `/data`
- variables:
  - `MINIO_ROOT_USER`
  - `MINIO_ROOT_PASSWORD`
  - `MINIO_BROWSER=off`

### media-gateway

- crea otra app desde este repo
- `Build Pack`: `Dockerfile`
- `Dockerfile Location`: `/Dockerfile`
- puerto: `8000`
- alias interno: `media-gateway`
- volumen persistente:
  - `Volume Mount`
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

Si quieres enlaces publicos temporales:

```env
PUBLIC_BASE_URL=https://media-share.tudominio.com
PUBLIC_LINK_DEFAULT_TTL_SEC=3600
PUBLIC_LINK_MAX_TTL_SEC=604800
```

## Buckets y retencion

- `user-videos`
  - bucket persistente principal
  - guarda videos e imagenes
  - sin expiracion automatica
- `tmp-uploads`
  - bucket temporal
  - expira automaticamente a `3 dias`

## URLs internas vs publicas

- `downloadUrl`
  - interna
  - pensada para n8n y microservicios dentro de Coolify
- `publicUrl`
  - opcional
  - solo aparece si el upload se hace con `makePublic=true`
  - se puede compartir externamente

## Documentacion

- guia operativa: [directives/README.md](/c:/Users/kevin/Documents/minio%20coolify/directives/README.md)
- guia n8n: [directives/N8N_CURL_EXAMPLES.md](/c:/Users/kevin/Documents/minio%20coolify/directives/N8N_CURL_EXAMPLES.md)
- instalacion compartible: [directives/COMMUNITY_INSTALL.md](/c:/Users/kevin/Documents/minio%20coolify/directives/COMMUNITY_INSTALL.md)

## Nota importante

Si alguien lo instala en su propio Coolify, debe usar los `Volume Mounts` nativos de Coolify y no `custom_docker_run_options` con `-v ...`.
