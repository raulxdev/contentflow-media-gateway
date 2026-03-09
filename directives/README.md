# Media Gateway

Servicio interno para gestionar uploads y descargas firmadas sobre almacenamiento S3-compatible.

## Endpoints

- `GET /health`
- `POST /v1/media/init-upload`
- `POST /v1/media/complete`
- `GET /v1/media/{media_id}/download-url`
- `DELETE /v1/media/{media_id}`

## Seguridad

- `X-API-Key` obligatorio para `POST` y `DELETE`.
- Validacion de MIME, extension y tamano.
- Rate limit basico por API key o IP.

## Variables

Ver `.env.example`.
