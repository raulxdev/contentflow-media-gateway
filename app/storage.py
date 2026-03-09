from pathlib import Path
from urllib.parse import urlparse, urlunparse
from uuid import uuid4

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.config import Settings, get_settings


class StorageClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint,
            region_name=settings.s3_region,
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path" if settings.s3_use_path_style else "auto"}),
        )

    def build_object_key(self, user_id: str, filename: str) -> str:
        suffix = Path(filename).suffix.lower()
        return f"{user_id}/{uuid4().hex}{suffix}"

    def generate_upload_url(self, bucket: str, object_key: str, mime_type: str) -> str:
        url = self._client.generate_presigned_url(
            "put_object",
            Params={"Bucket": bucket, "Key": object_key, "ContentType": mime_type},
            ExpiresIn=self.settings.presigned_upload_ttl_sec,
        )
        return self._rewrite_endpoint(url)

    def generate_download_url(self, bucket: str, object_key: str) -> str:
        url = self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": object_key},
            ExpiresIn=self.settings.presigned_download_ttl_sec,
        )
        return self._rewrite_endpoint(url)

    def object_exists(self, bucket: str, object_key: str) -> bool:
        try:
            self._client.head_object(Bucket=bucket, Key=object_key)
            return True
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise
        except Exception:
            return False

    def delete_object(self, bucket: str, object_key: str) -> None:
        self._client.delete_object(Bucket=bucket, Key=object_key)

    def _rewrite_endpoint(self, url: str) -> str:
        if not self.settings.s3_public_endpoint:
            return url
        parsed = urlparse(url)
        public = urlparse(self.settings.s3_public_endpoint)
        return urlunparse(parsed._replace(scheme=public.scheme or parsed.scheme, netloc=public.netloc or parsed.netloc))


def get_storage_client() -> StorageClient:
    return StorageClient(get_settings())
