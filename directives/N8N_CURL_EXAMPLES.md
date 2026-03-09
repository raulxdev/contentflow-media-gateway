# n8n Importable cURL

Guia practica para el equipo que trabaja con `media-gateway` desde n8n.

Estos ejemplos se pueden pegar en `Import from cURL` de un nodo `HTTP Request`, pero la parte del archivo binario puede requerir ajuste manual en n8n para apuntar a la propiedad binaria correcta.

## Resumen rapido

- Endpoint principal: `POST /v1/media/upload`
- Uso principal: subir imagenes y videos en un solo paso
- Bucket persistente: `user-videos`
- Bucket temporal: `tmp-uploads`
- Las URLs devueltas son internas, no para compartir con usuarios externos

## Cuando usar cada bucket

### `user-videos`

Usa este bucket para:

- videos de usuarios
- imagenes de usuarios
- cualquier archivo que deba seguir disponible despues del flujo actual

Importante:

- tambien se usa para imagenes, no solo para videos
- el nombre del bucket es historico
- no tiene expiracion automatica

### `tmp-uploads`

Usa este bucket para:

- archivos temporales
- staging
- material intermedio que luego se transforma, procesa o descarta

Importante:

- expira automaticamente a los `3 dias`
- no debes usarlo para archivos que quieras conservar de forma permanente

## Que hace `userId`

- `userId` no crea un bucket por usuario
- todos los usuarios comparten el mismo bucket
- `userId` se usa para construir el `objectKey`, por ejemplo:

```text
user-123/14f6909135e542ff870cb5d5c492fb01.mp4
```

Para que sirve:

- organizar archivos por usuario
- hacer trazabilidad
- facilitar auditoria y futuras cuotas

Buenas practicas:

- usa IDs internos estables
- evita correos, telefonos o datos sensibles si no son necesarios

## Seguridad de las URLs

La respuesta del upload incluye una `downloadUrl`, pero:

- es una URL interna
- hoy apunta a `http://minio:9000/...`
- sirve para uso interno entre n8n y otros microservicios en Coolify
- no debes compartirla con usuarios externos

Si la compartes fuera de la red interna:

- el host `minio` no va a resolver
- el usuario final no podra descargar el archivo

## Flujo principal

1. `POST /v1/media/upload`
2. recibes `mediaId + downloadUrl + expiresIn`
3. si otro microservicio interno necesita el archivo, puede usar esa URL o pedir otra con `GET /v1/media/{mediaId}/download-url`

## 1. Healthcheck

```bash
curl --request GET 'http://media-gateway:8000/health'
```

## 2. Upload de imagen en un solo paso

```bash
curl --request POST 'http://media-gateway:8000/v1/media/upload' \
  --header 'X-API-Key: REPLACE_ME_API_KEY' \
  --form 'userId="user-123"' \
  --form 'bucket="user-videos"' \
  --form 'file=@"/data/photo.jpg";type=image/jpeg'
```

## 3. Upload de video en un solo paso

```bash
curl --request POST 'http://media-gateway:8000/v1/media/upload' \
  --header 'X-API-Key: REPLACE_ME_API_KEY' \
  --form 'userId="user-123"' \
  --form 'bucket="user-videos"' \
  --form 'file=@"/data/video.mp4";type=video/mp4'
```

## 4. Upload temporal

```bash
curl --request POST 'http://media-gateway:8000/v1/media/upload' \
  --header 'X-API-Key: REPLACE_ME_API_KEY' \
  --form 'userId="user-123"' \
  --form 'bucket="tmp-uploads"' \
  --form 'file=@"/data/temp-video.mp4";type=video/mp4'
```

## Respuesta esperada

```json
{
  "mediaId": "REPLACE_WITH_MEDIA_ID",
  "downloadUrl": "http://minio:9000/...",
  "expiresIn": 900
}
```

## 5. Pedir una nueva URL de descarga

```bash
curl --request GET 'http://media-gateway:8000/v1/media/REPLACE_WITH_MEDIA_ID/download-url'
```

## 6. Descargar desde una URL interna firmada

```bash
curl --request GET 'REPLACE_WITH_DOWNLOAD_URL'
```

## 7. Borrar media

```bash
curl --request DELETE 'http://media-gateway:8000/v1/media/REPLACE_WITH_MEDIA_ID' \
  --header 'X-API-Key: REPLACE_ME_API_KEY'
```

## Configuracion esperada en n8n

- Metodo: `POST`
- URL: `http://media-gateway:8000/v1/media/upload`
- Header: `X-API-Key`
- Body Content Type: `Form-Data`
- Campos de texto:
  - `userId`
  - `bucket`
- Campo archivo:
  - `file`

## Valores que debes sustituir

- `REPLACE_ME_API_KEY`
- `REPLACE_WITH_MEDIA_ID`
- `REPLACE_WITH_DOWNLOAD_URL`
- `userId`
- `bucket`

## Restricciones actuales

- Buckets permitidos: `user-videos`, `tmp-uploads`
- Tipos MIME permitidos:
  - `image/jpeg`
  - `image/png`
  - `image/webp`
  - `video/mp4`
  - `video/quicktime`
  - `video/webm`
- Extensiones permitidas:
  - `.jpg`
  - `.jpeg`
  - `.png`
  - `.webp`
  - `.mp4`
  - `.mov`
  - `.webm`
- Tamano maximo:
  - `MAX_FILE_SIZE_MB`

## Nota importante para el equipo

- `user-videos` es el bucket persistente comun para media de negocio
- `tmp-uploads` es temporal y caduca a los `3 dias`
- `userId` organiza archivos dentro del bucket compartido, no crea un bucket por usuario
- las URLs de descarga actuales son internas, no son enlaces para compartir con clientes o usuarios finales
