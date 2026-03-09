import os
import sys
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

TEST_DB_PATH = Path("test-media.db").resolve()


def setup_module() -> None:
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()
    os.environ["SERVICE_API_KEY"] = "test-key"
    os.environ["S3_ENDPOINT"] = "http://minio:9000"
    os.environ["S3_ACCESS_KEY_ID"] = "access"
    os.environ["S3_SECRET_ACCESS_KEY"] = "secret"
    os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH.as_posix()}"


class FakeStorage:
    def __init__(self):
        self.deleted = []
        self.uploaded = []

    def build_object_key(self, user_id: str, filename: str) -> str:
        return f"{user_id}/{uuid4().hex}{Path(filename).suffix}"

    def generate_upload_url(self, bucket: str, object_key: str, mime_type: str) -> str:
        return f"http://example/upload/{bucket}/{object_key}"

    def generate_download_url(self, bucket: str, object_key: str) -> str:
        return f"http://example/download/{bucket}/{object_key}"

    def object_exists(self, bucket: str, object_key: str) -> bool:
        return True

    def delete_object(self, bucket: str, object_key: str) -> None:
        self.deleted.append((bucket, object_key))

    def upload_object(self, bucket: str, object_key: str, body: bytes, mime_type: str) -> None:
        self.uploaded.append((bucket, object_key, body, mime_type))


def test_single_step_upload_flow():
    from main import app
    from app.storage import get_storage_client

    fake = FakeStorage()
    app.dependency_overrides[get_storage_client] = lambda: fake
    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json() == {"ok": True}

        headers = {"X-API-Key": "test-key"}
        upload_response = client.post(
            "/v1/media/upload",
            headers=headers,
            data={"userId": "user-1", "bucket": "user-videos"},
            files={"file": ("video.mp4", b"video-bytes", "video/mp4")},
        )
        assert upload_response.status_code == 200
        media_id = upload_response.json()["mediaId"]
        object_key = fake.uploaded[0][1]
        assert upload_response.json()["downloadUrl"].startswith("http://example/download")
        assert fake.uploaded == [("user-videos", object_key, b"video-bytes", "video/mp4")]

        download_response = client.get(f"/v1/media/{media_id}/download-url")
        assert download_response.status_code == 200
        assert download_response.json()["downloadUrl"].startswith("http://example/download")

        delete_response = client.delete(f"/v1/media/{media_id}", headers=headers)
        assert delete_response.status_code == 200
        assert fake.deleted == [("user-videos", object_key)]


def test_upload_rejects_invalid_bucket():
    from main import app
    from app.storage import get_storage_client

    fake = FakeStorage()
    app.dependency_overrides[get_storage_client] = lambda: fake
    with TestClient(app) as client:
        response = client.post(
            "/v1/media/upload",
            headers={"X-API-Key": "test-key"},
            data={"userId": "user-1", "bucket": "invalid-bucket"},
            files={"file": ("video.mp4", b"video-bytes", "video/mp4")},
        )
        assert response.status_code == 400


def test_upload_requires_api_key():
    from main import app
    from app.storage import get_storage_client

    fake = FakeStorage()
    app.dependency_overrides[get_storage_client] = lambda: fake
    with TestClient(app) as client:
        response = client.post(
            "/v1/media/upload",
            data={"userId": "user-1", "bucket": "user-videos"},
            files={"file": ("video.mp4", b"video-bytes", "video/mp4")},
        )
        assert response.status_code == 403
