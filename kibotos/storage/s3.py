"""S3 storage integration for video uploads."""

from functools import lru_cache

import boto3
from botocore.config import Config

from kibotos.config import get_settings


class S3Client:
    """S3 client for video storage operations (supports AWS S3 and Cloudflare R2)."""

    def __init__(
        self,
        bucket: str,
        region: str,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        endpoint_url: str | None = None,
    ):
        self.bucket = bucket
        self.region = region
        self.endpoint_url = endpoint_url

        # Configure boto3 client
        config = Config(
            region_name=region,
            signature_version="s3v4",
        )

        client_kwargs = {"config": config}
        if access_key_id and secret_access_key:
            client_kwargs["aws_access_key_id"] = access_key_id
            client_kwargs["aws_secret_access_key"] = secret_access_key
        if endpoint_url:
            client_kwargs["endpoint_url"] = endpoint_url

        self._client = boto3.client("s3", **client_kwargs)

    def generate_presigned_upload(
        self,
        key: str,
        content_type: str = "video/mp4",
        expires_in: int = 3600,
    ) -> tuple[str, int]:
        """
        Generate a presigned URL for uploading a file.

        Returns:
            Tuple of (presigned_url, expires_in_seconds)
        """
        url = self._client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": self.bucket,
                "Key": key,
                "ContentType": content_type,
            },
            ExpiresIn=expires_in,
        )
        return url, expires_in

    def generate_presigned_download(
        self,
        key: str,
        expires_in: int = 3600,
    ) -> str:
        """Generate a presigned URL for downloading a file."""
        return self._client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self.bucket,
                "Key": key,
            },
            ExpiresIn=expires_in,
        )

    def check_object_exists(self, key: str) -> bool:
        """Check if an object exists in the bucket."""
        try:
            self._client.head_object(Bucket=self.bucket, Key=key)
            return True
        except self._client.exceptions.ClientError:
            return False

    def get_object_metadata(self, key: str) -> dict:
        """Get metadata for an object."""
        response = self._client.head_object(Bucket=self.bucket, Key=key)
        return {
            "content_length": response.get("ContentLength"),
            "content_type": response.get("ContentType"),
            "last_modified": response.get("LastModified"),
            "etag": response.get("ETag"),
        }

    def delete_object(self, key: str) -> None:
        """Delete an object from the bucket."""
        self._client.delete_object(Bucket=self.bucket, Key=key)


@lru_cache
def get_s3_client() -> S3Client:
    """Get cached S3 client instance."""
    settings = get_settings()
    return S3Client(
        bucket=settings.s3.s3_bucket,
        region=settings.s3.s3_region,
        access_key_id=settings.s3.aws_access_key_id,
        secret_access_key=settings.s3.aws_secret_access_key,
        endpoint_url=settings.s3.s3_endpoint,
    )
