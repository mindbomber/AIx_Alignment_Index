from __future__ import annotations

import argparse
from base64 import b64decode, b64encode
from hashlib import sha256
import os
from uuid import uuid4

import boto3
from botocore.exceptions import ClientError
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def main() -> int:
    parser = argparse.ArgumentParser(description="Exercise S3 evidence backup and restore.")
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--endpoint-url")
    parser.add_argument("--region", default="us-east-1")
    args = parser.parse_args()
    client = boto3.client("s3", endpoint_url=args.endpoint_url, region_name=args.region)
    try:
        client.create_bucket(Bucket=args.bucket)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") not in {
            "BucketAlreadyOwnedByYou",
            "BucketAlreadyExists",
        }:
            raise
    drill_id = str(uuid4())
    source_key = f"drills/{drill_id}/evidence.bin"
    backup_key = f"drills/{drill_id}/backup/evidence.bin"
    payload = b"AIx object-store disaster recovery drill"
    expected = sha256(payload).hexdigest()
    key_value = os.environ.get("AIX_DR_ENCRYPTION_KEY")
    key = b64decode(key_value) if key_value else AESGCM.generate_key(bit_length=256)
    nonce = os.urandom(12)
    encrypted = AESGCM(key).encrypt(nonce, payload, expected.encode())
    try:
        client.put_object(
            Bucket=args.bucket,
            Key=source_key,
            Body=encrypted,
            Metadata={
                "aix-encryption": "aes-256-gcm",
                "aix-nonce": b64encode(nonce).decode(),
                "aix-plaintext-sha256": expected,
            },
        )
        client.copy_object(
            Bucket=args.bucket,
            Key=backup_key,
            CopySource={"Bucket": args.bucket, "Key": source_key},
        )
        client.delete_object(Bucket=args.bucket, Key=source_key)
        client.copy_object(
            Bucket=args.bucket,
            Key=source_key,
            CopySource={"Bucket": args.bucket, "Key": backup_key},
        )
        response = client.get_object(Bucket=args.bucket, Key=source_key)
        restored_ciphertext = response["Body"].read()
        metadata = response["Metadata"]
        restored = AESGCM(key).decrypt(
            b64decode(metadata["aix-nonce"]),
            restored_ciphertext,
            metadata["aix-plaintext-sha256"].encode(),
        )
        if sha256(restored).hexdigest() != expected:
            raise RuntimeError("Restored object hash does not match the source")
        if metadata.get("aix-encryption") != "aes-256-gcm":
            raise RuntimeError("Restored object encryption metadata is missing")
        print(f"S3 restore drill passed: sha256={expected}")
        return 0
    finally:
        for key in (source_key, backup_key):
            client.delete_object(Bucket=args.bucket, Key=key)


if __name__ == "__main__":
    raise SystemExit(main())
