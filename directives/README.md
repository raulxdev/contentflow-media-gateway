# Media Gateway

Guia operativa del almacenamiento interno del proyecto para n8n y microservicios en la red privada de Coolify.

## Arquitectura

- `media-gateway` recibe uploads, valida el archivo y registra metadata.
- `MinIO` almacena el binario real en buckets privados.
- Las descargas se hacen con URLs firmadas temporales.

## Endpoints

- `GET /health`
- `POST /v1/media/upload`
- `GET /v1/media/{media_id}/download-url`
- `GET /public/media/{token}`
- `POST /v1/media/{media_id}/revoke-public`
- `DELETE /v1/media/{media_id}`

## Buckets

### `user-videos`

- Es el bucket principal y persistente del sistema.
- Se usa para archivos de negocio que deben conservarse.
- Aunque el nombre es `user-videos`, tambien guarda imagenes.
- No tiene expiracion automatica.

Usalo para:

- imagenes de usuarios
- videos de usuarios
- archivos que deban seguir disponibles despues del flujo inmediato

### `tmp-uploads`

- Es el bucket temporal del sistema.
- Se usa para material efimero o de staging.
- Tiene expiracion automatica de `3 dias`.

Usalo para:

- archivos intermedios
- material temporal para procesos
- archivos que pueden borrarse solos sin afectar el negocio

## `userId`

- `userId` no crea un bucket separado por usuario.
- Todos los usuarios comparten el mismo bucket.
- `userId` se usa como prefijo logico del `objectKey`, por ejemplo `user-123/archivo.ext`.

Sirve para:

- trazabilidad
- organizacion logica
- auditoria
- futuras cuotas o reglas por usuario

Recomendaciones:

- usa un ID interno estable
- evita datos sensibles en texto plano si no son necesarios
- no uses valores ambiguos o cambiantes

## Seguridad

- `X-API-Key` es obligatorio para `POST` y `DELETE`.
- Se validan MIME, extension y tamano.
- Hay rate limit basico por API key o IP.
- Los buckets son privados.

## URLs de descarga

- Las `downloadUrl` actuales son para uso interno entre servicios.
- Hoy apuntan a `http://minio:9000/...`.
- Solo funcionan dentro de la red interna de Coolify.
- No deben compartirse con usuarios externos o clientes fuera de esa red.

Si envias una de esas URLs a un usuario final:

- normalmente no va a resolver el host
- o no podra descargar el archivo fuera del entorno interno

## URLs publicas temporales

Cuando un upload se hace con publicacion activa:

- la respuesta incluye `publicUrl`
- esa URL si es compartible externamente
- usa el dominio publico configurado en `PUBLIC_BASE_URL`, por ejemplo `media-share.example.com`
- el gateway valida el token y sirve el archivo desde el endpoint publico

Reglas:

- solo aplica para `user-videos`
- `tmp-uploads` no admite publicacion
- la publicacion es temporal
- puede revocarse con `POST /v1/media/{media_id}/revoke-public`

## Limites operativos

- Buckets soportados: `user-videos`, `tmp-uploads`
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
- Tamano maximo por archivo:
  - `MAX_FILE_SIZE_MB` en `.env`

## Variables

Ver `.env.example`.

## Operacion desde n8n

Ver [N8N_CURL_EXAMPLES.md](/c:/Users/kevin/Documents/minio%20coolify/directives/N8N_CURL_EXAMPLES.md) para el flujo completo con `curl` importable en nodos `HTTP Request`.

## Distribucion

Si otra persona quiere instalar esta solucion en su propio Coolify, comparte tambien [COMMUNITY_INSTALL.md](/c:/Users/kevin/Documents/minio%20coolify/directives/COMMUNITY_INSTALL.md).

## Advertencia

El sistema esta funcionando para pruebas internas, pero la persistencia robusta en Coolify sigue siendo un punto pendiente antes de tratarlo como almacenamiento de produccion.
