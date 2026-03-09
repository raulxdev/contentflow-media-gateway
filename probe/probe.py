import hashlib
import json
import os
import sys
import time
import traceback
from pathlib import Path
from shutil import disk_usage

import boto3
import requests
from botocore.config import Config


def run_media_probe() -> int:
    try:
        base = os.getenv("MEDIA_GATEWAY_BASE_URL", "http://media-gateway:8000")
        headers = {
            "X-API-Key": os.environ["MEDIA_GATEWAY_API_KEY"],
            "Content-Type": "application/json",
        }
        payload = b"probe-video-payload"
        init = requests.post(
            f"{base}/v1/media/init-upload",
            headers=headers,
            json={
                "filename": "probe.mp4",
                "mimeType": "video/mp4",
                "size": len(payload),
                "userId": "probe-user",
                "bucket": "user-videos",
            },
            timeout=60,
        )
        init.raise_for_status()
        init_payload = init.json()

        upload = requests.put(
            init_payload["uploadUrl"],
            headers={"Content-Type": "video/mp4"},
            data=payload,
            timeout=120,
        )
        if upload.status_code >= 400:
            raise RuntimeError(
                json.dumps(
                    {
                        "upload_status": upload.status_code,
                        "upload_headers": dict(upload.headers),
                        "upload_body": upload.text[:1000],
                        "upload_url": init_payload["uploadUrl"],
                    }
                )
            )
        upload.raise_for_status()

        complete = requests.post(
            f"{base}/v1/media/complete",
            headers=headers,
            json={
                "objectKey": init_payload["objectKey"],
                "filename": "probe.mp4",
                "mimeType": "video/mp4",
                "size": len(payload),
                "userId": "probe-user",
                "bucket": "user-videos",
            },
            timeout=60,
        )
        complete.raise_for_status()
        media_id = complete.json()["mediaId"]

        download_info = requests.get(f"{base}/v1/media/{media_id}/download-url", timeout=60)
        download_info.raise_for_status()
        download_url = download_info.json()["downloadUrl"]

        download = requests.get(download_url, timeout=120)
        download.raise_for_status()

        result = {
            "health": requests.get(f"{base}/health", timeout=30).json(),
            "init_status": init.status_code,
            "upload_status": upload.status_code,
            "complete_status": complete.status_code,
            "download_url_status": download_info.status_code,
            "download_status": download.status_code,
            "media_id": media_id,
            "object_key": init_payload["objectKey"],
            "sha256": hashlib.sha256(download.content).hexdigest(),
        }
        print(json.dumps(result))
        sys.stdout.flush()
        time.sleep(300)
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                }
            )
        )
        sys.stdout.flush()
        time.sleep(300)
        return 1


def run_single_step_upload_probe() -> int:
    try:
        base = os.getenv("MEDIA_GATEWAY_BASE_URL", "http://media-gateway:8000")
        api_key = os.environ["MEDIA_GATEWAY_API_KEY"]
        payload = b"probe-video-payload"
        upload = requests.post(
            f"{base}/v1/media/upload",
            headers={"X-API-Key": api_key},
            data={"userId": "probe-user", "bucket": "user-videos"},
            files={"file": ("probe.mp4", payload, "video/mp4")},
            timeout=120,
        )
        upload.raise_for_status()
        upload_payload = upload.json()
        download = requests.get(upload_payload["downloadUrl"], timeout=120)
        download.raise_for_status()
        result = {
            "health": requests.get(f"{base}/health", timeout=30).json(),
            "upload_status": upload.status_code,
            "download_status": download.status_code,
            "media_id": upload_payload["mediaId"],
            "download_url": upload_payload["downloadUrl"],
            "sha256": hashlib.sha256(download.content).hexdigest(),
        }
        print(json.dumps(result))
        sys.stdout.flush()
        time.sleep(300)
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                }
            )
        )
        sys.stdout.flush()
        time.sleep(300)
        return 1


def run_disk_probe() -> int:
    try:
        target = Path(os.getenv("DISK_CHECK_PATH", "/hostroot"))
        usage = disk_usage(target)
        result = {
            "path": str(target),
            "total_gb": round(usage.total / (1024**3), 2),
            "used_gb": round(usage.used / (1024**3), 2),
            "free_gb": round(usage.free / (1024**3), 2),
        }
        print(json.dumps(result))
        sys.stdout.flush()
        time.sleep(300)
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                }
            )
        )
        sys.stdout.flush()
        time.sleep(300)
        return 1


def run_download_check_probe() -> int:
    try:
        base = os.getenv("MEDIA_GATEWAY_BASE_URL", "http://media-gateway:8000")
        media_id = os.environ["MEDIA_ID"]
        expected_sha256 = os.environ["EXPECTED_SHA256"]
        download_info = requests.get(f"{base}/v1/media/{media_id}/download-url", timeout=60)
        download_info.raise_for_status()
        download_url = download_info.json()["downloadUrl"]
        download = requests.get(download_url, timeout=120)
        download.raise_for_status()
        actual_sha256 = hashlib.sha256(download.content).hexdigest()
        result = {
            "media_id": media_id,
            "download_url_status": download_info.status_code,
            "download_status": download.status_code,
            "sha256": actual_sha256,
            "matches_expected": actual_sha256 == expected_sha256,
        }
        print(json.dumps(result))
        sys.stdout.flush()
        time.sleep(300)
        return 0 if result["matches_expected"] else 1
    except Exception as exc:
        print(
            json.dumps(
                {
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                }
            )
        )
        sys.stdout.flush()
        time.sleep(300)
        return 1


def run_bucket_bootstrap_probe() -> int:
    try:
        client = boto3.client(
            "s3",
            endpoint_url=os.getenv("S3_ENDPOINT", "http://minio:9000"),
            region_name=os.getenv("S3_REGION", "us-east-1"),
            aws_access_key_id=os.environ["S3_ACCESS_KEY_ID"],
            aws_secret_access_key=os.environ["S3_SECRET_ACCESS_KEY"],
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )
        buckets = [
            os.getenv("S3_BUCKET_USER_VIDEOS", "user-videos"),
            os.getenv("S3_BUCKET_TMP_UPLOADS", "tmp-uploads"),
        ]
        existing = {bucket["Name"] for bucket in client.list_buckets().get("Buckets", [])}
        for bucket in buckets:
            if bucket not in existing:
                client.create_bucket(Bucket=bucket)
        client.put_bucket_lifecycle_configuration(
            Bucket=os.getenv("S3_BUCKET_TMP_UPLOADS", "tmp-uploads"),
            LifecycleConfiguration={
                "Rules": [
                    {
                        "ID": "expire-tmp-uploads-7d",
                        "Status": "Enabled",
                        "Filter": {"Prefix": ""},
                        "Expiration": {"Days": 7},
                    }
                ]
            },
        )
        anonymous_check = requests.get(
            f"{os.getenv('S3_ENDPOINT', 'http://minio:9000').rstrip('/')}/{os.getenv('S3_BUCKET_USER_VIDEOS', 'user-videos')}?list-type=2",
            timeout=30,
        )
        result = {
            "buckets": [bucket["Name"] for bucket in client.list_buckets()["Buckets"]],
            "lifecycle_applied_to": os.getenv("S3_BUCKET_TMP_UPLOADS", "tmp-uploads"),
            "anonymous_status": anonymous_check.status_code,
            "anonymous_body": anonymous_check.text[:300],
        }
        print(json.dumps(result))
        sys.stdout.flush()
        time.sleep(300)
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                }
            )
        )
        sys.stdout.flush()
        time.sleep(300)
        return 1


def main() -> int:
    mode = os.getenv("PROBE_MODE")
    if mode == "disk-check":
        return run_disk_probe()
    if mode == "bucket-bootstrap":
        return run_bucket_bootstrap_probe()
    if mode == "single-step-upload":
        return run_single_step_upload_probe()
    if mode == "download-check":
        return run_download_check_probe()
    return run_media_probe()


if __name__ == "__main__":
    raise SystemExit(main())
