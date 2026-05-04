"""AWS S3 integration tools — bucket and object operations via boto3."""

from __future__ import annotations

import os
from typing import Any, Dict, List

from agentspan.agents import tool


def _get_s3_client() -> Any:
    """Create and return a boto3 S3 client, raising if credentials are missing."""
    access_key = os.environ.get("AWS_ACCESS_KEY_ID", "")
    secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
    if not access_key:
        raise RuntimeError("AWS_ACCESS_KEY_ID environment variable is not set")
    if not secret_key:
        raise RuntimeError("AWS_SECRET_ACCESS_KEY environment variable is not set")

    import boto3

    return boto3.client(
        "s3",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=os.environ.get("AWS_REGION", "us-east-1"),
    )


@tool(credentials=["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"])
def s3_list_objects(bucket: str, prefix: str = "") -> List[Dict[str, Any]]:
    """List objects in an S3 bucket.

    Args:
        bucket: S3 bucket name.
        prefix: Optional key prefix to filter results.

    Returns:
        List of dicts with ``key``, ``size``, ``last_modified``,
        and ``storage_class`` keys.
    """
    client = _get_s3_client()

    params: Dict[str, Any] = {"Bucket": bucket, "MaxKeys": 100}
    if prefix:
        params["Prefix"] = prefix

    resp = client.list_objects_v2(**params)

    results: List[Dict[str, Any]] = []
    for obj in resp.get("Contents", []):
        results.append({
            "key": obj.get("Key", ""),
            "size": obj.get("Size", 0),
            "last_modified": obj.get("LastModified", "").isoformat()
            if hasattr(obj.get("LastModified", ""), "isoformat")
            else str(obj.get("LastModified", "")),
            "storage_class": obj.get("StorageClass", ""),
        })
    return results


@tool(credentials=["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"])
def s3_read_object(bucket: str, key: str) -> str:
    """Read the text content of an S3 object.

    Args:
        bucket: S3 bucket name.
        key: Object key (path within the bucket).

    Returns:
        The object content decoded as UTF-8 text.
    """
    client = _get_s3_client()
    resp = client.get_object(Bucket=bucket, Key=key)
    return resp["Body"].read().decode("utf-8")


@tool(credentials=["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"])
def s3_write_object(bucket: str, key: str, content: str) -> str:
    """Write text content to an S3 object.

    Args:
        bucket: S3 bucket name.
        key: Object key (path within the bucket).
        content: Text content to write.

    Returns:
        Confirmation message with bucket and key.
    """
    client = _get_s3_client()
    client.put_object(Bucket=bucket, Key=key, Body=content.encode("utf-8"))
    return f"Wrote {len(content)} bytes to s3://{bucket}/{key}"


@tool(credentials=["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"])
def s3_list_buckets() -> List[Dict[str, str]]:
    """List all S3 buckets accessible with the configured credentials.

    Returns:
        List of dicts with ``name`` and ``creation_date`` keys.
    """
    client = _get_s3_client()
    resp = client.list_buckets()

    results: List[Dict[str, str]] = []
    for bucket in resp.get("Buckets", []):
        results.append({
            "name": bucket.get("Name", ""),
            "creation_date": bucket.get("CreationDate", "").isoformat()
            if hasattr(bucket.get("CreationDate", ""), "isoformat")
            else str(bucket.get("CreationDate", "")),
        })
    return results


def get_tools() -> List[Any]:
    """Return all S3 tools."""
    return [s3_list_objects, s3_read_object, s3_write_object, s3_list_buckets]
