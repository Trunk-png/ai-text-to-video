import asyncio
import mimetypes
import os
from pathlib import Path

from minio import Minio


class MinioHandler:
    def __init__(self):
        self.endpoint = os.environ["MINIO_ENDPOINT"]
        self.bucket = os.getenv("MINIO_BUCKET_NAME", "ai-inhouse")
        self.folder = os.getenv("MINIO_OUTPUT_FOLDER", "text_to_video_results").strip("/")
        self.public_base = os.getenv("OUTPUT_URL_BASE", "").rstrip("/")
        self.secure = os.getenv("MINIO_SECURE", "true").lower() == "true"
        self.client = Minio(self.endpoint, os.environ["MINIO_ACCESS_KEY"], os.environ["MINIO_SECRET_KEY"], secure=self.secure)

    def _upload(self, path: Path, request_id: str) -> str:
        name = f"{self.folder}/{request_id}{path.suffix}"
        self.client.fput_object(self.bucket, name, str(path), content_type=mimetypes.guess_type(path.name)[0] or "video/mp4")
        if self.public_base:
            return f"{self.public_base}/{request_id}{path.suffix}"
        scheme = "https" if self.secure else "http"
        return f"{scheme}://{self.endpoint}/{self.bucket}/{name}"

    async def upload(self, path: Path, request_id: str) -> str:
        return await asyncio.to_thread(self._upload, path, request_id)

