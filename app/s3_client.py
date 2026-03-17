# app/s3_client.py
from __future__ import annotations

import os
import boto3
from botocore.client import Config
from dotenv import load_dotenv


class S3Client:
    def __init__(self):
        load_dotenv(".env")
        region = os.getenv("AWS_REGION")
        profile = os.getenv("AWS_PROFILE")
        session = boto3.Session(profile_name=profile) if profile else boto3.Session()

        self.s3 = session.client(
            "s3",
            region_name=region,
            config=Config(signature_version="s3v4"),
        )

        self.bucket = os.getenv("S3_BUCKET")
        if not self.bucket:
            raise RuntimeError("S3_BUCKET not set in .env")

    def upload_bytes(
        self,
        key: str,
        data: bytes,
        content_type: str | None = None,
        content_disposition: str | None = None,
    ) -> None:
        extra: dict = {}
        if content_type:
            extra["ContentType"] = content_type
        if content_disposition:
            extra["ContentDisposition"] = content_disposition

        self.s3.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=data,
            **extra,
        )

    def upload_pdf_bytes(self, key: str, data: bytes) -> None:
        self.upload_bytes(key=key, data=data, content_type="application/pdf")

    def copy_pdf(self, src_key: str, dst_key: str) -> None:
        self.s3.copy_object(
            Bucket=self.bucket,
            Key=dst_key,
            CopySource={"Bucket": self.bucket, "Key": src_key},
            ContentType="application/pdf",
            MetadataDirective="REPLACE",
        )

    def presign_get_url(self, key: str, expires_seconds: int = 3600) -> str:
        return self.s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=int(expires_seconds),
        )

    def download_bytes(self, key: str) -> bytes:
        obj = self.s3.get_object(Bucket=self.bucket, Key=key)
        return obj["Body"].read()

    def download_pdf_bytes(self, key: str) -> bytes:
        return self.download_bytes(key)

    def delete_object(self, key: str) -> None:
        self.s3.delete_object(Bucket=self.bucket, Key=key)

    def head_object(self, key: str) -> dict:
        return self.s3.head_object(Bucket=self.bucket, Key=key)