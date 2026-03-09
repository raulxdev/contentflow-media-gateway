import hashlib
import json
import os
import sys
import time
import traceback

import requests


def main() -> int:
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


if __name__ == "__main__":
    raise SystemExit(main())
