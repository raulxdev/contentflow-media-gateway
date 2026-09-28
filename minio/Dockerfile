# MinIO compilado desde el código fuente oficial.
# MinIO ya no publica imágenes (Docker Hub borrado, Quay pide login).
# Última versión comunitaria: RELEASE.2025-10-15T17-29-55Z (incluye los parches de oct-2025).
# El proyecto está archivado: no habrá más parches. Solución temporal; planear migración.

# ---------- Etapa 1: compilar minio y mc ----------
FROM golang:1.26-alpine AS build

ARG MINIO_TAG=RELEASE.2025-10-15T17-29-55Z
ARG MC_TAG=RELEASE.2025-08-13T08-35-41Z

ENV CGO_ENABLED=0 \
    GOTOOLCHAIN=local \
    GOFLAGS=-trimpath

RUN apk add --no-cache git

WORKDIR /src

RUN git clone --depth 1 --branch "$MINIO_TAG" https://github.com/minio/minio.git minio \
 && cd minio \
 && go build -ldflags "$(MINIO_RELEASE=RELEASE go run buildscripts/gen-ldflags.go)" -o /out/minio .

RUN git clone --depth 1 --branch "$MC_TAG" https://github.com/minio/mc.git mc \
 && cd mc \
 && go build -ldflags "-s -w" -o /out/mc .

# ---------- Etapa 2: imagen final mínima ----------
FROM alpine:3.23

RUN apk add --no-cache ca-certificates \
 && addgroup -S minio \
 && adduser -S -G minio -h /home/minio minio \
 && mkdir -p /data \
 && chown minio:minio /data

COPY --from=build /out/minio /out/mc /usr/local/bin/

USER minio

EXPOSE 9000

ENTRYPOINT ["minio"]
CMD ["server", "/data", "--address", ":9000"]
