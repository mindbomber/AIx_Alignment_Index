from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re
import socket
import struct
import tempfile
from typing import BinaryIO, Protocol
from uuid import uuid4

import boto3

from .config import Settings


CHUNK_SIZE = 1024 * 1024
SAFE_NAME = re.compile(r"[^a-zA-Z0-9._-]+")


@dataclass(frozen=True)
class StoredObject:
    object_key: str
    content_sha256: str
    size_bytes: int
    content_type: str


class ObjectStore(Protocol):
    def put_file(self, source: Path, object_key: str, content_type: str) -> None: ...
    def open(self, object_key: str) -> BinaryIO: ...
    def delete(self, object_key: str) -> None: ...


class LocalObjectStore:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, object_key: str) -> Path:
        candidate = (self.root / object_key).resolve()
        if not candidate.is_relative_to(self.root):
            raise ValueError("Invalid object key")
        return candidate

    def put_file(self, source: Path, object_key: str, content_type: str) -> None:
        destination = self._path(object_key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        source.replace(destination)

    def open(self, object_key: str) -> BinaryIO:
        return self._path(object_key).open("rb")

    def delete(self, object_key: str) -> None:
        path = self._path(object_key)
        if path.exists():
            path.unlink()


class S3ObjectStore:
    def __init__(self, settings: Settings):
        self.bucket = settings.s3_bucket or ""
        credentials = {}
        if settings.s3_access_key_id:
            credentials["aws_access_key_id"] = (
                settings.s3_access_key_id.get_secret_value()
            )
        if settings.s3_secret_access_key:
            credentials["aws_secret_access_key"] = (
                settings.s3_secret_access_key.get_secret_value()
            )
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            region_name=settings.s3_region,
            **credentials,
        )
        self.encryption = settings.s3_server_side_encryption
        self.kms_key_id = settings.s3_kms_key_id

    def put_file(self, source: Path, object_key: str, content_type: str) -> None:
        extra = {"ContentType": content_type}
        if self.encryption:
            extra["ServerSideEncryption"] = self.encryption
        if self.kms_key_id:
            extra["SSEKMSKeyId"] = self.kms_key_id
        with source.open("rb") as handle:
            self.client.upload_fileobj(handle, self.bucket, object_key, ExtraArgs=extra)
        source.unlink(missing_ok=True)

    def open(self, object_key: str) -> BinaryIO:
        response = self.client.get_object(Bucket=self.bucket, Key=object_key)
        return response["Body"]

    def delete(self, object_key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=object_key)


def object_store(settings: Settings) -> ObjectStore:
    if settings.storage_backend == "s3":
        return S3ObjectStore(settings)
    return LocalObjectStore(settings.storage_path)


def safe_filename(filename: str | None) -> str:
    cleaned = SAFE_NAME.sub("-", Path(filename or "evidence.bin").name).strip(".-")
    return cleaned[:160] or "evidence.bin"


def evidence_object_key(
    organization_id: str,
    assessment_id: str,
    filename: str | None,
) -> str:
    return (
        f"organizations/{organization_id}/assessments/{assessment_id}/"
        f"{uuid4()}-{safe_filename(filename)}"
    )


def store_upload(
    *,
    source: BinaryIO,
    store: ObjectStore,
    object_key: str,
    content_type: str,
    max_bytes: int,
    settings: Settings | None = None,
) -> StoredObject:
    digest = sha256()
    size = 0
    temporary = tempfile.NamedTemporaryFile(delete=False)
    temporary_path = Path(temporary.name)
    try:
        with temporary:
            while chunk := source.read(CHUNK_SIZE):
                size += len(chunk)
                if size > max_bytes:
                    raise ValueError(f"Evidence file exceeds {max_bytes} bytes")
                digest.update(chunk)
                temporary.write(chunk)
        if settings and settings.malware_scan_enabled:
            scan_file(temporary_path, settings)
        store.put_file(temporary_path, object_key, content_type)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
    return StoredObject(
        object_key=object_key,
        content_sha256=digest.hexdigest(),
        size_bytes=size,
        content_type=content_type,
    )


def scan_file(path: Path, settings: Settings) -> None:
    try:
        with socket.create_connection(
            (settings.malware_scan_host, settings.malware_scan_port),
            timeout=settings.malware_scan_timeout_seconds,
        ) as connection:
            connection.sendall(b"zINSTREAM\0")
            with path.open("rb") as source:
                while chunk := source.read(CHUNK_SIZE):
                    connection.sendall(struct.pack(">I", len(chunk)) + chunk)
            connection.sendall(struct.pack(">I", 0))
            response = connection.recv(4096).decode(errors="replace")
    except OSError as exc:
        raise RuntimeError("Malware scanner connection failed") from exc
    if " FOUND" in response:
        raise ValueError("Evidence file failed malware scanning")
    if " OK" not in response:
        raise RuntimeError(f"Malware scanner returned: {response.strip()}")


def iter_file(handle: BinaryIO) -> Iterator[bytes]:
    try:
        while chunk := handle.read(CHUNK_SIZE):
            yield chunk
    finally:
        handle.close()
