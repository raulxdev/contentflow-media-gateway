import logging
import mimetypes
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import Response, StreamingResponse
from sqlmodel import Session, select

from app.config import get_settings
from app.db import get_session, init_db
from app.models import MediaRecord
from app.rate_limit import enforce_write_rate_limit
from app.schemas import (
    CompleteUploadRequest,
    CompleteUploadResponse,
    ActionResponse,
    DeleteResponse,
    DownloadUrlResponse,
    InitUploadRequest,
    InitUploadResponse,
    UploadResponse,
)
from app.security import require_api_key
from app.storage import StorageClient, get_storage_client


settings = get_settings()
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("media-gateway")

app = FastAPI(title="media-gateway")


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


def normalize_bucket(bucket: str) -> str:
    allowed = {settings.s3_bucket_user_videos, settings.s3_bucket_tmp_uploads}
    if bucket not in allowed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid bucket")
    return bucket


def validate_upload_request(payload: InitUploadRequest | CompleteUploadRequest) -> None:
    mime_type = payload.mimeType.lower()
    extension = Path(payload.filename).suffix.lower()
    if mime_type not in settings.allowed_mime_type_set:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported mime type")
    if extension not in settings.allowed_extension_set:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported file extension")
    if payload.size > settings.max_file_size_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File too large")
    normalize_bucket(payload.bucket)


def validate_upload_metadata(filename: str, mime_type: str, size: int, bucket: str) -> None:
    payload = InitUploadRequest(
        filename=filename,
        mimeType=mime_type,
        size=size,
        userId="validation-only",
        bucket=bucket,
    )
    validate_upload_request(payload)


def audit(event: str, **fields: str | int | None) -> None:
    payload = {"event": event, **fields, "timestamp": datetime.now(timezone.utc).isoformat()}
    logger.info(payload)


def infer_mime_type(upload: UploadFile) -> str:
    if upload.content_type:
        return upload.content_type.strip().lower()
    guessed, _ = mimetypes.guess_type(upload.filename or "")
    if guessed:
        return guessed.lower()
    return "application/octet-stream"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def build_public_url(token: str) -> str:
    if not settings.public_base_url:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Public base URL is not configured")
    return f"{settings.public_base_url.rstrip('/')}/public/media/{token}"


def normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def parse_range_header(range_header: str, total_size: int) -> tuple[int, int]:
    if not range_header.startswith("bytes="):
        raise HTTPException(status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE, detail="Invalid range unit")
    raw = range_header[6:].strip()
    if "," in raw:
        raise HTTPException(status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE, detail="Multiple ranges are not supported")
    if "-" not in raw:
        raise HTTPException(status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE, detail="Invalid range format")

    start_raw, end_raw = raw.split("-", 1)
    if start_raw == "":
        try:
            suffix_length = int(end_raw)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE, detail="Invalid range format") from exc
        if suffix_length <= 0:
            raise HTTPException(status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE, detail="Invalid range format")
        start = max(total_size - suffix_length, 0)
        end = total_size - 1
        return start, end

    try:
        start = int(start_raw)
        end = int(end_raw) if end_raw else total_size - 1
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE, detail="Invalid range format") from exc

    if start < 0 or end < start or start >= total_size:
        raise HTTPException(status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE, detail="Range not satisfiable")
    end = min(end, total_size - 1)
    return start, end


def public_media_headers(filename: str, media_type: str, size: int) -> dict[str, str]:
    return {
        "Content-Disposition": f'inline; filename="{filename}"',
        "Cache-Control": "private, max-age=60",
        "Accept-Ranges": "bytes",
        "Content-Type": media_type,
        "Content-Length": str(size),
    }


def public_media_metadata(record: MediaRecord, storage: StorageClient) -> dict[str, Any]:
    metadata = storage.head_object(record.bucket, record.object_key)
    content_type = metadata.get("ContentType") or record.mime_type
    content_length = int(metadata["ContentLength"])
    return {"content_type": content_type, "content_length": content_length}


def parse_public_ttl(public_ttl_sec: int | None) -> int:
    ttl = public_ttl_sec or settings.public_link_default_ttl_sec
    if ttl <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid public TTL")
    if ttl > settings.public_link_max_ttl_sec:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Public TTL exceeds maximum")
    return ttl


@app.post("/v1/media/init-upload", response_model=InitUploadResponse, dependencies=[Depends(require_api_key)])
def init_upload(
    payload: InitUploadRequest,
    request: Request,
    storage: StorageClient = Depends(get_storage_client),
) -> InitUploadResponse:
    enforce_write_rate_limit(request)
    validate_upload_request(payload)
    object_key = storage.build_object_key(payload.userId, payload.filename)
    upload_url = storage.generate_upload_url(payload.bucket, object_key, payload.mimeType)
    audit(
        "init-upload",
        userId=payload.userId,
        mediaId=None,
        bucket=payload.bucket,
        size=payload.size,
        status="issued",
    )
    return InitUploadResponse(uploadUrl=upload_url, objectKey=object_key)


@app.post("/v1/media/complete", response_model=CompleteUploadResponse, dependencies=[Depends(require_api_key)])
def complete_upload(
    payload: CompleteUploadRequest,
    request: Request,
    session: Session = Depends(get_session),
    storage: StorageClient = Depends(get_storage_client),
) -> CompleteUploadResponse:
    enforce_write_rate_limit(request)
    validate_upload_request(payload)
    if not storage.object_exists(payload.bucket, payload.objectKey):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Uploaded object not found")

    existing = session.exec(select(MediaRecord).where(MediaRecord.object_key == payload.objectKey)).first()
    if existing:
        if existing.deleted_at is not None:
            existing.deleted_at = None
        existing.status = "ready"
        existing.updated_at = datetime.now(timezone.utc)
        session.add(existing)
        session.commit()
        session.refresh(existing)
        audit(
            "complete-upload",
            userId=existing.user_id,
            mediaId=existing.media_id,
            bucket=existing.bucket,
            size=existing.size,
            status=existing.status,
        )
        return CompleteUploadResponse(mediaId=existing.media_id)

    record = MediaRecord(
        user_id=payload.userId,
        bucket=payload.bucket,
        object_key=payload.objectKey,
        filename=payload.filename,
        mime_type=payload.mimeType,
        size=payload.size,
        status="ready",
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    audit(
        "complete-upload",
        userId=record.user_id,
        mediaId=record.media_id,
        bucket=record.bucket,
        size=record.size,
        status=record.status,
    )
    return CompleteUploadResponse(mediaId=record.media_id)


@app.post("/v1/media/upload", response_model=UploadResponse, dependencies=[Depends(require_api_key)])
async def upload_media(
    request: Request,
    userId: str = Form(..., min_length=1, max_length=128),
    bucket: str = Form(..., min_length=1, max_length=64),
    makePublic: bool = Form(default=False),
    publicTtlSec: int | None = Form(default=None),
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    storage: StorageClient = Depends(get_storage_client),
) -> UploadResponse:
    enforce_write_rate_limit(request)
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Filename is required")

    mime_type = infer_mime_type(file)
    bucket = normalize_bucket(bucket.strip())
    userId = userId.strip()
    public_ttl_sec: int | None = None
    public_token: str | None = None
    public_expires_at: datetime | None = None
    if makePublic:
        if bucket != settings.s3_bucket_user_videos:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Public links are only allowed for user-videos")
        public_ttl_sec = parse_public_ttl(publicTtlSec)
        public_token = secrets.token_urlsafe(24)
        public_expires_at = (utcnow() + timedelta(seconds=public_ttl_sec)).replace(microsecond=0)
    body = await file.read()
    size = len(body)
    validate_upload_metadata(file.filename, mime_type, size, bucket)

    object_key = storage.build_object_key(userId, file.filename)
    try:
        storage.upload_object(bucket, object_key, body, mime_type)
    except Exception as exc:
        logger.exception(
            {
                "event": "upload-media-storage-error",
                "userId": userId,
                "bucket": bucket,
                "objectKey": object_key,
                "size": size,
                "errorType": type(exc).__name__,
                "errorMessage": str(exc),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Upload to storage failed") from exc

    record = MediaRecord(
        user_id=userId,
        bucket=bucket,
        object_key=object_key,
        filename=file.filename,
        mime_type=mime_type,
        size=size,
        status="ready",
        is_public=makePublic,
        public_token=public_token,
        public_expires_at=public_expires_at,
    )
    session.add(record)
    session.commit()
    session.refresh(record)

    download_url = storage.generate_download_url(record.bucket, record.object_key)
    audit(
        "upload-media",
        userId=record.user_id,
        mediaId=record.media_id,
        bucket=record.bucket,
        size=record.size,
        status=record.status,
    )
    return UploadResponse(
        mediaId=record.media_id,
        downloadUrl=download_url,
        expiresIn=settings.presigned_download_ttl_sec,
        publicUrl=build_public_url(record.public_token) if record.is_public and record.public_token else None,
        publicExpiresAt=record.public_expires_at.isoformat() if record.public_expires_at else None,
    )


@app.get("/v1/media/{media_id}/download-url", response_model=DownloadUrlResponse)
def get_download_url(
    media_id: str,
    session: Session = Depends(get_session),
    storage: StorageClient = Depends(get_storage_client),
) -> DownloadUrlResponse:
    record = session.get(MediaRecord, media_id)
    if not record or record.deleted_at is not None or record.status != "ready":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media not found")
    download_url = storage.generate_download_url(record.bucket, record.object_key)
    audit(
        "download-url",
        userId=record.user_id,
        mediaId=record.media_id,
        bucket=record.bucket,
        size=record.size,
        status="issued",
    )
    return DownloadUrlResponse(downloadUrl=download_url, expiresIn=settings.presigned_download_ttl_sec)


@app.api_route("/public/media/{token}", methods=["GET", "HEAD"])
def get_public_media(
    token: str,
    request: Request,
    session: Session = Depends(get_session),
    storage: StorageClient = Depends(get_storage_client),
):
    record = session.exec(select(MediaRecord).where(MediaRecord.public_token == token)).first()
    if not record or record.deleted_at is not None or record.status != "ready":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media not found")
    now = utcnow()
    public_expires_at = normalize_datetime(record.public_expires_at)
    if not record.is_public or record.public_revoked_at is not None or not public_expires_at or public_expires_at <= now:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media not found")
    metadata = public_media_metadata(record, storage)
    audit(
        "public-download",
        userId=record.user_id,
        mediaId=record.media_id,
        bucket=record.bucket,
        size=record.size,
        status="issued",
    )
    headers = public_media_headers(record.filename, metadata["content_type"], metadata["content_length"])
    if request.method == "HEAD":
        return Response(status_code=status.HTTP_200_OK, headers=headers, media_type=metadata["content_type"])

    range_header = request.headers.get("range")
    status_code = status.HTTP_200_OK
    byte_range = None
    if range_header:
        start, end = parse_range_header(range_header, metadata["content_length"])
        byte_range = f"bytes={start}-{end}"
        headers["Content-Range"] = f"bytes {start}-{end}/{metadata['content_length']}"
        headers["Content-Length"] = str(end - start + 1)
        status_code = status.HTTP_206_PARTIAL_CONTENT

    obj = storage.get_object(record.bucket, record.object_key, byte_range=byte_range)
    return StreamingResponse(
        obj["Body"].iter_chunks(),
        status_code=status_code,
        media_type=metadata["content_type"],
        headers=headers,
    )


@app.post("/v1/media/{media_id}/revoke-public", response_model=ActionResponse, dependencies=[Depends(require_api_key)])
def revoke_public_media(
    media_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> ActionResponse:
    enforce_write_rate_limit(request)
    record = session.get(MediaRecord, media_id)
    if not record or record.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media not found")
    record.is_public = False
    record.public_token = None
    record.public_revoked_at = utcnow()
    record.updated_at = utcnow()
    session.add(record)
    session.commit()
    audit(
        "revoke-public-media",
        userId=record.user_id,
        mediaId=record.media_id,
        bucket=record.bucket,
        size=record.size,
        status=record.status,
    )
    return ActionResponse(ok=True)


@app.delete("/v1/media/{media_id}", response_model=DeleteResponse, dependencies=[Depends(require_api_key)])
def delete_media(
    media_id: str,
    request: Request,
    session: Session = Depends(get_session),
    storage: StorageClient = Depends(get_storage_client),
) -> DeleteResponse:
    enforce_write_rate_limit(request)
    record = session.get(MediaRecord, media_id)
    if not record or record.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media not found")
    storage.delete_object(record.bucket, record.object_key)
    record.status = "deleted"
    record.deleted_at = datetime.now(timezone.utc)
    record.updated_at = datetime.now(timezone.utc)
    record.is_public = False
    record.public_token = None
    record.public_revoked_at = datetime.now(timezone.utc)
    session.add(record)
    session.commit()
    audit(
        "delete-media",
        userId=record.user_id,
        mediaId=record.media_id,
        bucket=record.bucket,
        size=record.size,
        status=record.status,
    )
    return DeleteResponse(ok=True)
