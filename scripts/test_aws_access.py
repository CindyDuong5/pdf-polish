import os
from dotenv import load_dotenv
import boto3

load_dotenv()

REGION = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "ca-central-1"
BUCKET = os.getenv("S3_BUCKET") or "mainline-doc-styler"

print("Using REGION:", REGION)
print("Using BUCKET:", BUCKET)

s3 = boto3.client("s3", region_name=REGION)
ses = boto3.client("ses", region_name=REGION)

# ---- S3 test: can we access our bucket? ----
print("\nS3: HeadBucket...")
s3.head_bucket(Bucket=BUCKET)
print("✅ HeadBucket OK")

print("\nS3: ListObjectsV2 (max 5)...")
resp = s3.list_objects_v2(Bucket=BUCKET, MaxKeys=5)
for item in resp.get("Contents", []):
    print("-", item["Key"])
print("✅ ListObjectsV2 OK")

# ---- SES test ----
print("\nSES: GetSendQuota...")
print(ses.get_send_quota())
print("✅ SES API access OK")

