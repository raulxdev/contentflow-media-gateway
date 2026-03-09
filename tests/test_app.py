import os
from pathlib import Path

from fastapi.testclient import TestClient


def setup_module() -> None:
    os.environ["SERVICE_API_KEY"] = "test-key"
    os.environ["S3_ENDPOINT"] = "http://minio:9000"
    os.environ["S3_ACCESS_KEY_ID"] = "access"
    os.environ["S3_SECRET_ACCESS_KEY"] = "secret"
    os.environ["DATABASE_URL"] = f"sqlite:///{Path('test-media.db').resolve().as_posix()}"


class FakeStorage:
    def __init__(self):
        self.deleted = []

    def build_object_key(self, user_id: str, filename: str) -> str:
        return f"{user_id}/object{Path(filename).suffix}"

    def generate_upload_url(self, bucket: str, object_key: str, mime_type: str) -> str:
        return f"http://example/upload/{bucket}/{object_key}"

    def generate_download_url(self, bucket: str, object_key: str) -> str:
        return f"http://example/download/{bucket}/{object_key}"

    def object_exists(self, bucket: str, object_key: str) -> bool:
        return True

    def delete_object(self, bucket: str, object_key: str) -> None:
        self.deleted.append((bucket, object_key))


def test_media_flow():
    from main import app
    from app.storage import get_storage_client

    fake = FakeStorage()
    app.dependency_overrides[get_storage_client] = lambda: fake
    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json() == {"ok": True}

        headers = {"X-API-Key": "test-key"}
        init_response = client.post(
            "/v1/media/init-upload",
            headers=headers,
            json={
                "filename": "video.mp4",
                "mimeType": "video/mp4",
                "size": 1024,
                "userId": "user-1",
                "bucket": "user-videos",
            },
        )
        assert init_response.status_code == 200
        object_key = init_response.json()["objectKey"]

        complete_response = client.post(
            "/v1/media/complete",
            headers=headers,
            json={
                "objectKey": object_key,
                "filename": "video.mp4",
                "mimeType": "video/mp4",
                "size": 1024,
                "userId": "user-1",
                "bucket": "user-videos",
            },
        )
        assert complete_response.status_code == 200
        media_id = complete_response.json()["mediaId"]

        download_response = client.get(f"/v1/media/{media_id}/download-url")
        assert download_response.status_code == 200
        assert download_response.json()["downloadUrl"].startswith("http://example/download")

        delete_response = client.delete(f"/v1/media/{media_id}", headers=headers)
        assert delete_response.status_code == 200
        assert fake.deleted == [("user-videos", object_key)]
