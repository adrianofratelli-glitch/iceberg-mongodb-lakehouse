"""Backend configuration, read from the repository .env."""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

MONGODB_URI = os.getenv("MONGODB_URI", "")
DATABASE_NAME = os.getenv("DATABASE_NAME", "iceberg_demo")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "orders")
DLQ_COLLECTION = "dlq"

AWS_REGION = os.getenv("AWS_REGION", "sa-east-1")
S3_BUCKET = os.getenv("S3_BUCKET", "")
GLUE_DATABASE = os.getenv("GLUE_DATABASE", "mongodb_iceberg_demo")
ICEBERG_TABLE = os.getenv("ICEBERG_TABLE", "orders")
ATHENA_WORKGROUP = os.getenv("ATHENA_WORKGROUP", "primary")
ATHENA_OUTPUT = os.getenv(
    "ATHENA_OUTPUT", f"s3://{S3_BUCKET}/athena-results/" if S3_BUCKET else ""
)

LIVE_ORDER_ID = "PED-AOVIVO-001"
SCHEMA_ORDER_ID = "PED-AOVIVO-002"
