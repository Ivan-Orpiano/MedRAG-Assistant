"""Object storage abstraction: local filesystem (default), AWS S3, or
Supabase Storage via its S3-compatible endpoint (set STORAGE_BACKEND=s3 or
supabase and point S3_ENDPOINT_URL at the Supabase S3 gateway)."""
import os
from pathlib import Path

from app.core.config import get_settings


class StorageBackend:
    def put(self, key: str, data: bytes) -> None: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...


class LocalStorage(StorageBackend):
    def __init__(self, root: str):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if not str(p).startswith(str(self.root.resolve())):
            raise ValueError("Invalid storage key")
        return p

    def put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        try:
            os.remove(self._path(key))
        except FileNotFoundError:
            pass


class S3Storage(StorageBackend):
    def __init__(self):
        import boto3  # optional dependency; only imported when configured

        s = get_settings()
        self.bucket = s.s3_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=s.s3_endpoint_url or None,
            region_name=s.aws_region,
            aws_access_key_id=s.aws_access_key_id or None,
            aws_secret_access_key=s.aws_secret_access_key or None,
        )

    def put(self, key: str, data: bytes) -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data)

    def get(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)


_backend: StorageBackend | None = None


def get_storage() -> StorageBackend:
    global _backend
    if _backend is None:
        s = get_settings()
        if s.storage_backend in ("s3", "supabase"):
            _backend = S3Storage()
        else:
            _backend = LocalStorage(s.local_storage_path)
    return _backend
