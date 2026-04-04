import os
from typing import Optional

import boto3


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def get_r2_client():
    endpoint_url = _require_env("R2_ENDPOINT_URL")
    access_key_id = _require_env("R2_ACCESS_KEY_ID")
    secret_access_key = _require_env("R2_SECRET_ACCESS_KEY")

    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        region_name=os.getenv("R2_REGION", "auto"),
    )


def upload_bytes(
    *,
    bucket: str,
    key: str,
    content: bytes,
    content_type: str,
):
    client = get_r2_client()
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=content,
        ContentType=content_type,
    )


def get_download_url(
    *,
    bucket: str,
    key: str,
    expires_seconds: int = 3600,
) -> str:
    public_base = os.getenv("R2_PUBLIC_BASE_URL")
    if public_base:
        return f"{public_base.rstrip('/')}/{key}"

    client = get_r2_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expires_seconds,
    )


def get_bucket_name() -> str:
    return _require_env("R2_BUCKET_NAME")


def get_key_prefix() -> str:
    return os.getenv("R2_KEY_PREFIX", "shorts").strip("/") or "shorts"


def build_object_key(*parts: str, extension: Optional[str] = None) -> str:
    cleaned = [p.strip("/").strip() for p in parts if p and p.strip("/").strip()]
    key = "/".join(cleaned)
    if extension:
        ext = extension if extension.startswith(".") else f".{extension}"
        if not key.endswith(ext):
            key = f"{key}{ext}"
    return key

