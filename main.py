import logging
import mimetypes
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, status
from sqlmodel import Session, select

from app.config import get_settings
from app.db import get_session, init_db
from app.models import MediaRecord
from app.rate_limit import enforce_write_rate_limit
from app.schemas import (
    CompleteUploadRequest,
    CompleteUploadResponse,
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
    body = await file.read()
    size = len(body)
    validate_upload_metadata(file.filename, mime_type, size, bucket)

    object_key = storage.build_object_key(userId, file.filename)
    try:
        storage.upload_object(bucket, object_key, body, mime_type)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Upload to storage failed") from exc

    record = MediaRecord(
        user_id=userId,
        bucket=bucket,
        object_key=object_key,
        filename=file.filename,
        mime_type=mime_type,
        size=size,
        status="ready",
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
