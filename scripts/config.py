"""Local demo configuration.

Reads MongoDB connection info from environment variables (.env) instead of
hardcoding credentials in this file. For a public GitHub repository, do not
commit real credentials or a filled-in .env file.
"""

import os
from dotenv import load_dotenv

load_dotenv()

MONGODB_URI = os.environ["MONGODB_URI"]
DATABASE_NAME = os.getenv("DATABASE_NAME", "iceberg_demo")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "orders")
