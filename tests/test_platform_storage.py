from __future__ import annotations

from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest

from aix_platform.config import Settings
from aix_platform.storage import (
    LocalObjectStore,
    S3ObjectStore,
    evidence_object_key,
    safe_filename,
    scan_file,
    store_upload,
)


def test_local_object_store_round_trip_and_tenant_key(tmp_path):
    store = LocalObjectStore(tmp_path / "objects")
    source = tmp_path / "upload.tmp"
    source.write_bytes(b"evidence")
    key = evidence_object_key("org-1", "assessment-1", "../../audit report.txt")

    assert key.startswith("organizations/org-1/assessments/assessment-1/")
    assert key.endswith("-audit-report.txt")
    store.put_file(source, key, "text/plain")
    with store.open(key) as handle:
        assert handle.read() == b"evidence"
    store.delete(key)
    with pytest.raises(FileNotFoundError):
        store.open(key)


def test_local_object_store_rejects_path_escape(tmp_path):
    store = LocalObjectStore(tmp_path / "objects")
    with pytest.raises(ValueError, match="Invalid object key"):
        store.open("../outside")
    assert safe_filename("..") == "evidence.bin"


def test_store_upload_hashes_and_enforces_limit(tmp_path):
    store = LocalObjectStore(tmp_path / "objects")
    stored = store_upload(
        source=BytesIO(b"abc"),
        store=store,
        object_key="organizations/o/assessments/a/evidence.txt",
        content_type="text/plain",
        max_bytes=3,
    )
    assert stored.size_bytes == 3
    assert stored.content_sha256 == (
        "ba7816bf8f01cfea414140de5dae2223"
        "b00361a396177a9cb410ff61f20015ad"
    )

    with pytest.raises(ValueError, match="exceeds"):
        store_upload(
            source=BytesIO(b"abcd"),
            store=store,
            object_key="organizations/o/assessments/a/too-large.txt",
            content_type="text/plain",
            max_bytes=3,
        )
    assert not Path(tmp_path / "objects/organizations/o/assessments/a/too-large.txt").exists()


def test_store_upload_rejects_malware_before_storage(tmp_path, monkeypatch):
    store = LocalObjectStore(tmp_path / "objects")
    monkeypatch.setattr(
        "aix_platform.storage.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1),
    )
    settings = Settings(
        token_pepper="test-token-pepper-value",
        malware_scan_enabled=True,
    )
    with pytest.raises(ValueError, match="malware"):
        store_upload(
            source=BytesIO(b"unsafe"),
            store=store,
            object_key="organizations/o/assessments/a/unsafe.txt",
            content_type="text/plain",
            max_bytes=100,
            settings=settings,
        )
    assert not (tmp_path / "objects/organizations/o/assessments/a/unsafe.txt").exists()


def test_clamd_stream_scan_protocol(tmp_path, monkeypatch):
    class FakeConnection:
        def __init__(self):
            self.sent = bytearray()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def sendall(self, value):
            self.sent.extend(value)

        def recv(self, size):
            return b"stream: OK\0"

    connection = FakeConnection()
    monkeypatch.setattr(
        "aix_platform.storage.socket.create_connection",
        lambda *args, **kwargs: connection,
    )
    path = tmp_path / "evidence.bin"
    path.write_bytes(b"clean")
    settings = Settings(
        token_pepper="test-token-pepper-value",
        malware_scan_enabled=True,
        malware_scan_backend="clamd",
    )
    scan_file(path, settings)
    assert connection.sent.startswith(b"zINSTREAM\0")
    assert connection.sent.endswith(b"\0\0\0\0")


def test_s3_object_store_passes_customer_managed_kms_key(tmp_path, monkeypatch):
    class FakeClient:
        def __init__(self):
            self.extra_args = None

        def upload_fileobj(self, handle, bucket, object_key, ExtraArgs):
            assert handle.read() == b"evidence"
            assert bucket == "evidence"
            assert object_key == "org/file"
            self.extra_args = ExtraArgs

    client = FakeClient()
    monkeypatch.setattr(
        "aix_platform.storage.boto3.client",
        lambda *args, **kwargs: client,
    )
    settings = Settings(
        token_pepper="test-token-pepper-value",
        storage_backend="s3",
        s3_bucket="evidence",
        s3_server_side_encryption="aws:kms",
        s3_kms_key_id="alias/aix-evidence",
    )
    store = S3ObjectStore(settings)
    source = tmp_path / "upload.tmp"
    source.write_bytes(b"evidence")

    store.put_file(source, "org/file", "application/octet-stream")

    assert client.extra_args == {
        "ContentType": "application/octet-stream",
        "ServerSideEncryption": "aws:kms",
        "SSEKMSKeyId": "alias/aix-evidence",
    }
    assert not source.exists()
