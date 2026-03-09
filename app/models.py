from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MediaRecord(SQLModel, table=True):
    media_id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True, index=True)
    user_id: str = Field(index=True)
    bucket: str = Field(index=True)
    object_key: str = Field(unique=True, index=True)
    filename: str
    mime_type: str
    size: int
    status: str = Field(default="pending", index=True)
    is_public: bool = Field(default=False, nullable=False, index=True)
    public_token: Optional[str] = Field(default=None, index=True)
    public_expires_at: Optional[datetime] = Field(default=None, nullable=True)
    public_revoked_at: Optional[datetime] = Field(default=None, nullable=True)
    deleted_at: Optional[datetime] = Field(default=None, nullable=True)
    created_at: datetime = Field(default_factory=utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=utcnow, nullable=False)
