from pydantic import BaseModel, Field, field_validator


class InitUploadRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    mimeType: str = Field(min_length=3, max_length=255)
    size: int = Field(gt=0)
    userId: str = Field(min_length=1, max_length=128)
    bucket: str = Field(min_length=1, max_length=64)

    @field_validator("filename", "mimeType", "userId", "bucket")
    @classmethod
    def strip_values(cls, value: str) -> str:
        return value.strip()


class InitUploadResponse(BaseModel):
    uploadUrl: str
    objectKey: str


class CompleteUploadRequest(BaseModel):
    objectKey: str = Field(min_length=1)
    userId: str = Field(min_length=1, max_length=128)
    bucket: str = Field(min_length=1, max_length=64)
    filename: str = Field(min_length=1, max_length=255)
    mimeType: str = Field(min_length=3, max_length=255)
    size: int = Field(gt=0)


class CompleteUploadResponse(BaseModel):
    mediaId: str


class DownloadUrlResponse(BaseModel):
    downloadUrl: str
    expiresIn: int


class UploadResponse(BaseModel):
    mediaId: str
    downloadUrl: str
    expiresIn: int
    publicUrl: str | None = None
    publicExpiresAt: str | None = None


class ActionResponse(BaseModel):
    ok: bool


class DeleteResponse(BaseModel):
    ok: bool
