from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine

from app.config import get_settings


settings = get_settings()
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    ensure_mediarecord_columns()


def ensure_mediarecord_columns() -> None:
    inspector = inspect(engine)
    if "mediarecord" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("mediarecord")}
    alterations = {
        "is_public": "ALTER TABLE mediarecord ADD COLUMN is_public BOOLEAN NOT NULL DEFAULT 0",
        "public_token": "ALTER TABLE mediarecord ADD COLUMN public_token VARCHAR",
        "public_expires_at": "ALTER TABLE mediarecord ADD COLUMN public_expires_at DATETIME",
        "public_revoked_at": "ALTER TABLE mediarecord ADD COLUMN public_revoked_at DATETIME",
    }
    with engine.begin() as connection:
        for column_name, statement in alterations.items():
            if column_name not in columns:
                connection.execute(text(statement))


def get_session():
    with Session(engine) as session:
        yield session
