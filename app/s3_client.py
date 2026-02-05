# app/s3_client.py
from __future__ import annotations

import os
import boto3
from dotenv import load_dotenv


class S3Client:
    def __init__(self):
        load_dotenv(".env")
        region = os.getenv("AWS_REGION")
        profile = os.getenv("AWS_PROFILE")
        session = boto3.Session(profile_name=profile) if profile else boto3.Session()
        self.s3 = session.client("s3", region_name=region)
        self.bucket = os.getenv("S3_BUCKET")
        if not self.bucket:
            raise RuntimeError("S3_BUCKET not set in .env")

    def upload_pdf_bytes(self, key: str, data: bytes) -> None:
        self.s3.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType="application/pdf",
        )
