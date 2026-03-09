# n8n Importable cURL

Estos ejemplos estan pensados para pegarse directamente en `Import from cURL` de un nodo `HTTP Request` de n8n.

El flujo principal para n8n ahora es de un solo paso:

1. `POST /v1/media/upload`
2. La respuesta ya devuelve `mediaId + downloadUrl`

## 1. Healthcheck

```bash
curl --request GET 'http://media-gateway:8000/health'
```

## 2. Upload de foto JPG en un solo paso

```bash
curl --request POST 'http://media-gateway:8000/v1/media/upload' \
  --header 'X-API-Key: REPLACE_ME_API_KEY' \
  --form 'userId="user-123"' \
  --form 'bucket="user-videos"' \
  --form 'file=@"/data/photo.jpg";type=image/jpeg'
```

## 3. Upload de video MP4 en un solo paso

```bash
curl --request POST 'http://media-gateway:8000/v1/media/upload' \
  --header 'X-API-Key: REPLACE_ME_API_KEY' \
  --form 'userId="user-123"' \
  --form 'bucket="user-videos"' \
  --form 'file=@"/data/video.mp4";type=video/mp4'
```

Respuesta esperada:

```json
{
  "mediaId": "REPLACE_WITH_MEDIA_ID",
  "downloadUrl": "http://minio:9000/...",
  "expiresIn": 900
}
```

## 4. Get Download URL

```bash
curl --request GET 'http://media-gateway:8000/v1/media/REPLACE_WITH_MEDIA_ID/download-url'
```

## 5. Descargar archivo desde la URL firmada

```bash
curl --request GET 'REPLACE_WITH_DOWNLOAD_URL'
```

## 6. Delete media

```bash
curl --request DELETE 'http://media-gateway:8000/v1/media/REPLACE_WITH_MEDIA_ID' \
  --header 'X-API-Key: REPLACE_ME_API_KEY'
```

## Como usarlo en n8n

- Crea un nodo `HTTP Request`
- Usa `Import from cURL`
- Pega el cURL de upload de foto o video
- Reemplaza `REPLACE_ME_API_KEY`
- Ajusta la ruta del archivo si el importador la conserva literal

## Configuracion esperada del nodo en n8n

- Metodo: `POST`
- URL: `http://media-gateway:8000/v1/media/upload`
- Header: `X-API-Key`
- Body Content Type: `Form-Data` o `n8n Binary File`
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

## Notas

- `bucket` debe ser `user-videos` o `tmp-uploads`
- `POST /v1/media/upload` y `DELETE` requieren `X-API-Key`
- `GET /download-url` no requiere API key actualmente
- El gateway valida MIME, extension y tamano antes de guardar en MinIO
- La respuesta del upload ya sirve para continuar el flujo sin llamada extra inmediata
