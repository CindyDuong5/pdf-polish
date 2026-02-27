# app/storage/s3_storage.py
from __future__ import annotations

import os
from datetime import datetime, timezone
from urllib.parse import quote

import boto3
from botocore.client import Config
from dotenv import load_dotenv


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _safe_filename(name: str) -> str:
    # Keep it simple for Content-Disposition; browsers are picky.
    name = (name or "document.pdf").strip().replace("\n", " ").replace("\r", " ")
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    return name


class S3Storage:
    def __init__(self):
        load_dotenv(".env")

        self.bucket = os.getenv("S3_BUCKET")
        if not self.bucket:
            raise RuntimeError("S3_BUCKET not set in .env")

        region = os.getenv("AWS_REGION") or "us-east-1"
        profile = os.getenv("AWS_PROFILE")

        session = boto3.Session(profile_name=profile) if profile else boto3.Session()

        # signature_version helps with some environments, safe default
        self.s3 = session.client(
            "s3",
            region_name=region,
            config=Config(signature_version="s3v4"),
        )

    def upload_pdf_bytes(self, key: str, data: bytes) -> None:
        self.s3.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType="application/pdf",
        )

    def copy_object(self, src_key: str, dst_key: str) -> None:
        """
        Server-side copy (no download/re-upload).
        """
        self.s3.copy_object(
            Bucket=self.bucket,
            Key=dst_key,
            CopySource={"Bucket": self.bucket, "Key": src_key},
            ContentType="application/pdf",
            MetadataDirective="REPLACE",
        )
    def download_bytes(self, key: str) -> bytes:
        resp = self.s3.get_object(Bucket=self.bucket, Key=key)
        return resp["Body"].read()
    
    def presign_get_url(
        self,
        key: str,
        expires_seconds: int = 3600,
        download_filename: str | None = None,
        inline: bool = True,
    ) -> str:
        """
        inline=True opens in browser tab; inline=False forces download.
        """
        params = {"Bucket": self.bucket, "Key": key}

        if download_filename:
            fname = _safe_filename(download_filename)
            disp = "inline" if inline else "attachment"
            # filename*= for utf-8 safety
            params["ResponseContentDisposition"] = f"{disp}; filename*=UTF-8''{quote(fname)}"
            params["ResponseContentType"] = "application/pdf"

        return self.s3.generate_presigned_url(
            ClientMethod="get_object",
            Params=params,
            ExpiresIn=int(expires_seconds),
        )


# convenience functions (matches your api_main import style)
_storage_singleton: S3Storage | None = None


def get_storage() -> S3Storage:
    global _storage_singleton
    if _storage_singleton is None:
        _storage_singleton = S3Storage()
    return _storage_singleton


def presign_get_url(key: str, expires_seconds: int = 3600) -> str:
    return get_storage().presign_get_url(key=key, expires_seconds=expires_seconds)