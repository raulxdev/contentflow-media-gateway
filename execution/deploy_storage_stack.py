import json
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path

import boto3
import requests
from botocore.client import Config as BotoConfig
from dotenv import load_dotenv

from execution.github_manager import create_private_repo, grant_github_app_access, initialize_and_push

load_dotenv()


@dataclass
class ResourceSummary:
    name: str
    uuid: str
    fqdn: str | None
    alias: str | None
    status: str | None


class CoolifyClient:
    def __init__(self):
        self.base_url = os.environ["COOLIFY_URL"].rstrip("/")
        self.project_uuid = os.environ["COOLIFY_PROJECT_UUID"]
        self.headers = {
            "Authorization": f"Bearer {os.environ['COOLIFY_TOKEN']}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        servers = self.get("/servers")
        if isinstance(servers, list):
            self.server_uuid = servers[0]["uuid"]
        else:
            self.server_uuid = servers["uuid"]

    def get(self, path: str):
        response = requests.get(f"{self.base_url}/api/v1{path}", headers=self.headers, timeout=60)
        response.raise_for_status()
        return response.json()

    def post(self, path: str, payload: dict):
        response = requests.post(f"{self.base_url}/api/v1{path}", headers=self.headers, json=payload, timeout=60)
        response.raise_for_status()
        return response.json()

    def patch(self, path: str, payload: dict):
        response = requests.patch(f"{self.base_url}/api/v1{path}", headers=self.headers, json=payload, timeout=60)
        response.raise_for_status()
        return response.json() if response.text else {}

    def delete(self, path: str):
        response = requests.delete(f"{self.base_url}/api/v1{path}", headers=self.headers, timeout=60)
        response.raise_for_status()
        return response.json() if response.text else {}

    def list_applications(self) -> list[dict]:
        return self.get("/applications")

    def find_application(self, name: str) -> dict | None:
        for app in self.list_applications():
            if app["name"] == name:
                return app
        return None

    def create_private_github_app(self, name: str, repo: str, port: str) -> dict:
        apps = self.get("/github-apps")
        github_app_uuid = next(app["uuid"] for app in apps if not app["is_public"])
        return self.post(
            "/applications/private-github-app",
            {
                "name": name,
                "project_uuid": self.project_uuid,
                "environment_name": "production",
                "server_uuid": self.server_uuid,
                "github_app_uuid": github_app_uuid,
                "git_repository": repo,
                "git_branch": "main",
                "build_pack": "dockerfile",
                "ports_exposes": port,
            },
        )

    def create_docker_image_app(self, name: str, image: str, tag: str, port: str, health_path: str) -> dict:
        return self.post(
            "/applications/dockerimage",
            {
                "name": name,
                "project_uuid": self.project_uuid,
                "environment_name": "production",
                "server_uuid": self.server_uuid,
                "docker_registry_image_name": image,
                "docker_registry_image_tag": tag,
                "ports_exposes": port,
                "health_check_enabled": True,
                "health_check_path": health_path,
                "health_check_port": port,
                "health_check_host": "localhost",
                "health_check_method": "GET",
                "health_check_return_code": 200,
                "health_check_scheme": "http",
                "health_check_interval": 5,
                "health_check_retries": 10,
                "health_check_timeout": 5,
                "health_check_start_period": 10,
            },
        )

    def set_env(self, app_uuid: str, key: str, value: str) -> None:
        existing = self.get(f"/applications/{app_uuid}/envs")
        for env in existing:
            if env["key"] == key:
                self.delete(f"/applications/{app_uuid}/envs/{env['uuid']}")
        self.post(f"/applications/{app_uuid}/envs", {"key": key, "value": value, "is_preview": False})

    def configure_app(self, app_uuid: str, **payload) -> dict:
        result = {}
        for key, value in payload.items():
            result[key] = self.patch(f"/applications/{app_uuid}", {key: value})
        return result

    def deploy(self, app_uuid: str) -> str:
        response = requests.get(
            f"{self.base_url}/api/v1/deploy?uuid={app_uuid}&force=true",
            headers=self.headers,
            timeout=60,
        )
        response.raise_for_status()
        return response.json()["deployments"][0]["deployment_uuid"]

    def wait_for_deployment(self, deployment_uuid: str, timeout_seconds: int = 900) -> dict:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            deployment = self.get(f"/deployments/{deployment_uuid}")
            if deployment.get("status") in {"finished", "failed", "canceled"}:
                return deployment
            time.sleep(10)
        raise TimeoutError(f"Deployment {deployment_uuid} timed out")

    def wait_for_health(self, app_uuid: str, timeout_seconds: int = 600) -> dict:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            app = self.get(f"/applications/{app_uuid}")
            if app.get("status") == "running:healthy":
                return app
            time.sleep(10)
        raise TimeoutError(f"Application {app_uuid} did not become healthy")

    def get_logs(self, app_uuid: str) -> str:
        return self.get(f"/applications/{app_uuid}/logs")["logs"]


def create_s3_client(endpoint: str, access_key: str, secret_key: str):
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name="us-east-1",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=BotoConfig(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def estimate_storage(free_gb: float) -> dict:
    daily_gb = (120 * 80) / 1024
    monthly_gb = daily_gb * 30
    tmp_steady_gb = daily_gb * 7
    total_30d_gb = monthly_gb + tmp_steady_gb
    used_pct = (total_30d_gb / free_gb) * 100 if free_gb else 0
    return {
        "daily_gb": round(daily_gb, 2),
        "monthly_gb": round(monthly_gb, 2),
        "tmp_steady_gb": round(tmp_steady_gb, 2),
        "total_30d_gb": round(total_30d_gb, 2),
        "used_pct": round(used_pct, 2),
    }


def main() -> None:
    coolify = CoolifyClient()
    repo_name = "contentflow-media-gateway"
    description = "Media gateway for internal uploads and signed downloads"

    owner, repo_name, repo_id = create_private_repo(repo_name, description)
    installation_id = next(app["installation_id"] for app in coolify.get("/github-apps") if not app["is_public"])
    grant_github_app_access(repo_id, installation_id)
    initialize_and_push(repo_name, owner)

    minio_access_key = secrets.token_urlsafe(16)[:20]
    minio_secret_key = secrets.token_urlsafe(36)[:40]
    gateway_api_key = secrets.token_hex(32)

    summary: dict[str, object] = {}

    minio = coolify.find_application("minio")
    if not minio:
        minio = coolify.create_docker_image_app("minio", "minio/minio", "latest", "9000", "/minio/health/live")
    minio_uuid = minio["uuid"]
    coolify.configure_app(
        minio_uuid,
        custom_network_aliases="minio",
        start_command='server /data --console-address ":9001"',
        custom_docker_run_options="-v minio-data:/data",
    )
    coolify.set_env(minio_uuid, "MINIO_ROOT_USER", minio_access_key)
    coolify.set_env(minio_uuid, "MINIO_ROOT_PASSWORD", minio_secret_key)
    coolify.set_env(minio_uuid, "MINIO_BROWSER", "off")
    minio_deployment = coolify.deploy(minio_uuid)
    coolify.wait_for_deployment(minio_deployment)
    minio_app = coolify.wait_for_health(minio_uuid)

    minio_public_url = minio_app.get("fqdn")
    minio_client = create_s3_client(minio_public_url, minio_access_key, minio_secret_key)

    for bucket in ("user-videos", "tmp-uploads"):
        existing = [item["Name"] for item in minio_client.list_buckets()["Buckets"]]
        if bucket not in existing:
            minio_client.create_bucket(Bucket=bucket)
    lifecycle = {
        "Rules": [
            {
                "ID": "expire-tmp-uploads-7d",
                "Status": "Enabled",
                "Filter": {"Prefix": ""},
                "Expiration": {"Days": 7},
            }
        ]
    }
    minio_client.put_bucket_lifecycle_configuration(Bucket="tmp-uploads", LifecycleConfiguration=lifecycle)

    gateway = coolify.find_application("media-gateway")
    if not gateway:
        gateway = coolify.create_private_github_app("media-gateway", f"{owner}/{repo_name}", "8000")
    gateway_uuid = gateway["uuid"]
    coolify.configure_app(
        gateway_uuid,
        custom_network_aliases="media-gateway",
        dockerfile_location="/Dockerfile",
        health_check_enabled=True,
        health_check_path="/health",
        health_check_port="8000",
        health_check_host="localhost",
        health_check_method="GET",
        health_check_return_code=200,
        health_check_scheme="http",
        health_check_interval=5,
        health_check_retries=10,
        health_check_timeout=5,
        health_check_start_period=10,
        custom_docker_run_options="-v media-gateway-data:/app/data",
    )
    gateway_envs = {
        "SERVICE_API_KEY": gateway_api_key,
        "S3_ENDPOINT": "http://minio:9000",
        "S3_PUBLIC_ENDPOINT": minio_public_url,
        "S3_REGION": "us-east-1",
        "S3_ACCESS_KEY_ID": minio_access_key,
        "S3_SECRET_ACCESS_KEY": minio_secret_key,
        "S3_BUCKET_USER_VIDEOS": "user-videos",
        "S3_BUCKET_TMP_UPLOADS": "tmp-uploads",
        "S3_USE_PATH_STYLE": "true",
        "PRESIGNED_UPLOAD_TTL_SEC": "900",
        "PRESIGNED_DOWNLOAD_TTL_SEC": "900",
        "WRITE_RATE_LIMIT_PER_MINUTE": "30",
        "MAX_FILE_SIZE_MB": "512",
        "DATABASE_URL": "sqlite:////app/data/media.db",
    }
    for key, value in gateway_envs.items():
        coolify.set_env(gateway_uuid, key, value)

    gateway_deployment = coolify.deploy(gateway_uuid)
    coolify.wait_for_deployment(gateway_deployment)
    gateway_app = coolify.wait_for_health(gateway_uuid)

    gateway_url = gateway_app["fqdn"].rstrip("/")
    sample_path = Path(".tmp/test_data")
    sample_path.mkdir(parents=True, exist_ok=True)
    sample_file = sample_path / "sample-video.mp4"
    sample_file.write_bytes(b"0" * 1024)

    headers = {"X-API-Key": gateway_api_key, "Content-Type": "application/json"}
    init_response = requests.post(
        f"{gateway_url}/v1/media/init-upload",
        headers=headers,
        json={
            "filename": sample_file.name,
            "mimeType": "video/mp4",
            "size": sample_file.stat().st_size,
            "userId": "telegram-user-1",
            "bucket": "user-videos",
        },
        timeout=60,
    )
    init_response.raise_for_status()
    init_payload = init_response.json()

    upload_response = requests.put(
        init_payload["uploadUrl"],
        headers={"Content-Type": "video/mp4"},
        data=sample_file.read_bytes(),
        timeout=120,
    )
    upload_response.raise_for_status()

    complete_response = requests.post(
        f"{gateway_url}/v1/media/complete",
        headers=headers,
        json={
            "objectKey": init_payload["objectKey"],
            "filename": sample_file.name,
            "mimeType": "video/mp4",
            "size": sample_file.stat().st_size,
            "userId": "telegram-user-1",
            "bucket": "user-videos",
        },
        timeout=60,
    )
    complete_response.raise_for_status()
    media_id = complete_response.json()["mediaId"]

    download_response = requests.get(f"{gateway_url}/v1/media/{media_id}/download-url", timeout=60)
    download_response.raise_for_status()
    download_url = download_response.json()["downloadUrl"]
    downloaded = requests.get(download_url, timeout=120)
    downloaded.raise_for_status()
    sample_hash = downloaded.content.hex()

    gateway_public_before_internal = gateway_url
    minio_public_before_internal = minio_public_url

    coolify.set_env(gateway_uuid, "S3_PUBLIC_ENDPOINT", "")
    coolify.configure_app(gateway_uuid, domains="")
    coolify.configure_app(minio_uuid, domains="")
    redeploy_gateway = coolify.deploy(gateway_uuid)
    redeploy_minio = coolify.deploy(minio_uuid)
    coolify.wait_for_deployment(redeploy_gateway)
    coolify.wait_for_deployment(redeploy_minio)
    coolify.wait_for_health(gateway_uuid)
    coolify.wait_for_health(minio_uuid)

    internal_probe = coolify.find_application("media-probe")
    if not internal_probe:
        internal_probe = coolify.create_docker_image_app("media-probe", "curlimages/curl", "8.12.1", "8080", "/")
    probe_uuid = internal_probe["uuid"]
    probe_script = (
        "sh -lc \""
        f"echo health=$(curl -s http://media-gateway:8000/health); "
        f"URL=$(curl -s http://media-gateway:8000/v1/media/{media_id}/download-url | sed 's/.*\\\"downloadUrl\\\":\\\"//;s/\\\",\\\"expiresIn.*//'); "
        "echo internal_download_code=$(curl -s -o /dev/null -w '%{http_code}' $URL); "
        "sleep 30\""
    )
    coolify.configure_app(
        probe_uuid,
        custom_network_aliases="media-probe",
        start_command=probe_script,
        domains="",
        health_check_enabled=False,
    )
    probe_deployment = coolify.deploy(probe_uuid)
    coolify.wait_for_deployment(probe_deployment, timeout_seconds=180)
    probe_logs = coolify.get_logs(probe_uuid)

    redeploy_gateway_2 = coolify.deploy(gateway_uuid)
    redeploy_minio_2 = coolify.deploy(minio_uuid)
    coolify.wait_for_deployment(redeploy_gateway_2)
    coolify.wait_for_deployment(redeploy_minio_2)
    coolify.wait_for_health(gateway_uuid)
    coolify.wait_for_health(minio_uuid)

    minio_internal = coolify.get(f"/applications/{minio_uuid}")
    gateway_internal = coolify.get(f"/applications/{gateway_uuid}")
    probe_deployment_2 = coolify.deploy(probe_uuid)
    coolify.wait_for_deployment(probe_deployment_2, timeout_seconds=180)
    probe_logs_after_redeploy = coolify.get_logs(probe_uuid)

    disk_probe = coolify.find_application("disk-check")
    if not disk_probe:
        disk_probe = coolify.create_docker_image_app("disk-check", "alpine", "3.20", "8081", "/")
    disk_uuid = disk_probe["uuid"]
    coolify.configure_app(
        disk_uuid,
        start_command='sh -lc "df -BG / | tail -1; sleep 120"',
        domains="",
        health_check_enabled=False,
    )
    disk_deployment = coolify.deploy(disk_uuid)
    coolify.wait_for_deployment(disk_deployment, timeout_seconds=180)
    disk_logs = coolify.get_logs(disk_uuid)
    free_gb = 0.0
    for line in disk_logs.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[3].endswith("G"):
            free_gb = float(parts[3].replace("G", ""))
            break

    estimate = estimate_storage(free_gb)
    summary["space"] = {"free_gb": free_gb, **estimate}
    summary["resources"] = [
        ResourceSummary("minio", minio_internal["uuid"], minio_public_before_internal, minio_internal.get("custom_network_aliases"), minio_internal["status"]).__dict__,
        ResourceSummary("media-gateway", gateway_internal["uuid"], gateway_public_before_internal, gateway_internal.get("custom_network_aliases"), gateway_internal["status"]).__dict__,
    ]
    summary["tests"] = {
        "init_upload_status": init_response.status_code,
        "upload_status": upload_response.status_code,
        "complete_status": complete_response.status_code,
        "download_status": downloaded.status_code,
        "download_hash": sample_hash,
        "probe_logs": probe_logs,
        "probe_logs_after_redeploy": probe_logs_after_redeploy,
    }
    summary["env"] = {
        "S3_ENDPOINT": "http://minio:9000",
        "S3_REGION": "us-east-1",
        "S3_ACCESS_KEY_ID": minio_access_key,
        "S3_SECRET_ACCESS_KEY": minio_secret_key,
        "S3_BUCKET_USER_VIDEOS": "user-videos",
        "S3_BUCKET_TMP_UPLOADS": "tmp-uploads",
        "S3_USE_PATH_STYLE": "true",
        "MEDIA_GATEWAY_BASE_URL": "http://media-gateway:8000",
        "MEDIA_GATEWAY_API_KEY": gateway_api_key,
        "PRESIGNED_UPLOAD_TTL_SEC": "900",
        "PRESIGNED_DOWNLOAD_TTL_SEC": "900",
    }
    Path("deployment-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
