from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    service_api_key: str = Field(alias="SERVICE_API_KEY")
    s3_endpoint: str = Field(alias="S3_ENDPOINT")
    s3_public_endpoint: str | None = Field(default=None, alias="S3_PUBLIC_ENDPOINT")
    s3_region: str = Field(default="us-east-1", alias="S3_REGION")
    s3_access_key_id: str = Field(alias="S3_ACCESS_KEY_ID")
    s3_secret_access_key: str = Field(alias="S3_SECRET_ACCESS_KEY")
    s3_bucket_user_videos: str = Field(default="user-videos", alias="S3_BUCKET_USER_VIDEOS")
    s3_bucket_tmp_uploads: str = Field(default="tmp-uploads", alias="S3_BUCKET_TMP_UPLOADS")
    s3_use_path_style: bool = Field(default=True, alias="S3_USE_PATH_STYLE")
    presigned_upload_ttl_sec: int = Field(default=900, alias="PRESIGNED_UPLOAD_TTL_SEC")
    presigned_download_ttl_sec: int = Field(default=900, alias="PRESIGNED_DOWNLOAD_TTL_SEC")
    max_file_size_mb: int = Field(default=512, alias="MAX_FILE_SIZE_MB")
    allowed_mime_types: str = Field(
        default="image/jpeg,image/png,image/webp,video/mp4,video/quicktime,video/webm",
        alias="ALLOWED_MIME_TYPES",
    )
    allowed_extensions: str = Field(default=".jpg,.jpeg,.png,.webp,.mp4,.mov,.webm", alias="ALLOWED_EXTENSIONS")
    write_rate_limit_per_minute: int = Field(default=30, alias="WRITE_RATE_LIMIT_PER_MINUTE")
    database_url: str = Field(default="sqlite:////app/data/media.db", alias="DATABASE_URL")
    public_base_url: str | None = Field(default=None, alias="PUBLIC_BASE_URL")
    public_link_default_ttl_sec: int = Field(default=3600, alias="PUBLIC_LINK_DEFAULT_TTL_SEC")
    public_link_max_ttl_sec: int = Field(default=604800, alias="PUBLIC_LINK_MAX_TTL_SEC")

    @property
    def allowed_mime_type_set(self) -> set[str]:
        return {item.strip().lower() for item in self.allowed_mime_types.split(",") if item.strip()}

    @property
    def allowed_extension_set(self) -> set[str]:
        return {item.strip().lower() for item in self.allowed_extensions.split(",") if item.strip()}

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
