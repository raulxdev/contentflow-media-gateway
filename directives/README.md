# Media Gateway

Servicio interno para gestionar uploads y descargas firmadas sobre almacenamiento S3-compatible.

## Endpoints

- `GET /health`
- `POST /v1/media/upload`
- `GET /v1/media/{media_id}/download-url`
- `DELETE /v1/media/{media_id}`

## Seguridad

- `X-API-Key` obligatorio para `POST` y `DELETE`.
- Validacion de MIME, extension y tamano.
- Rate limit basico por API key o IP.

## Variables

Ver `.env.example`.

## Operacion desde n8n

Ver [N8N_CURL_EXAMPLES.md](/c:/Users/kevin/Documents/minio%20coolify/directives/N8N_CURL_EXAMPLES.md) para el flujo completo con `curl` importable en nodos `HTTP Request`.
