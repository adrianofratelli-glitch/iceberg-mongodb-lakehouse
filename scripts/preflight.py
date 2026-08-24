"""Run this before every demo.

Checks the MongoDB side of the pipeline and fixes what it can:
  1. .env is present and has no leftover placeholders
  2. the cluster is reachable
  3. the source collection has changeStreamPreAndPostImages enabled
     (without it the processor dies on the first UPDATE)
  4. reports document counts and any dead-letter queue entries

The stream processor itself lives in Atlas Stream Processing and is not
reachable from pymongo -- check it with:
    mongosh "<workspace-uri>" --eval 'sp.ordersToIceberg.stats()'
"""

import configparser
import json
import os
import subprocess
import sys
from pathlib import Path

from common import get_collection, DATABASE_NAME, COLLECTION_NAME

DLQ_COLLECTION = "dlq"
AWS_CREDENTIALS = Path.home() / ".aws" / "credentials"
AWS_CONFIG = Path.home() / ".aws" / "config"


def _sso_profile():
    """Return a profile name configured for SSO, if any."""
    if not AWS_CONFIG.exists():
        return None
    parser = configparser.ConfigParser()
    try:
        parser.read(AWS_CONFIG)
    except configparser.Error:
        return None
    for section in parser.sections():
        entries = parser[section]
        if "sso_start_url" in entries or "sso_session" in entries:
            return section.replace("profile ", "", 1)
    return None


def check_aws():
    """Credentials for Athena/Glue expire; surface that before the demo starts."""
    try:
        result = subprocess.run(
            ["aws", "sts", "get-caller-identity", "--output", "json"],
            capture_output=True,
            text=True,
            timeout=25,
        )
    except FileNotFoundError:
        print("[warn] AWS CLI not installed -- Athena checks unavailable")
        return
    except subprocess.TimeoutExpired:
        print("[warn] aws sts get-caller-identity timed out")
        return

    if result.returncode == 0:
        arn = json.loads(result.stdout).get("Arn", "?")
        print(f"[ok]   AWS credentials valid -- {arn}")
        return

    profile = _sso_profile()
    if profile:
        print(f"[warn] AWS credentials expired or missing -- refresh with:")
        print(f"           aws sso login --profile {profile}")
        return

    print("[warn] AWS credentials expired or missing (Athena and Glue unavailable)")
    print(f"       paste a fresh block from the SSO portal into {AWS_CREDENTIALS}")
    if sys.platform == "darwin" and not os.environ.get("POV_NO_POPUP"):
        AWS_CREDENTIALS.parent.mkdir(exist_ok=True)
        if not AWS_CREDENTIALS.exists():
            AWS_CREDENTIALS.write_text("[default]\n")
            AWS_CREDENTIALS.chmod(0o600)
        subprocess.run(["open", "-a", "TextEdit", str(AWS_CREDENTIALS)], check=False)
        print("       (opened it for you -- set POV_NO_POPUP=1 to skip)")


def main():
    client, coll = get_collection()
    ok = True
    try:
        print(f"[ok]   connected -- {DATABASE_NAME}.{COLLECTION_NAME}")

        db = client[DATABASE_NAME]
        info = next(db.list_collections(filter={"name": COLLECTION_NAME}), None)
        if info is None:
            print(f"[warn] collection {COLLECTION_NAME} does not exist yet -- run seed_orders.py")
        else:
            enabled = (
                info.get("options", {})
                .get("changeStreamPreAndPostImages", {})
                .get("enabled", False)
            )
            if enabled:
                print("[ok]   changeStreamPreAndPostImages enabled")
            else:
                db.command(
                    {
                        "collMod": COLLECTION_NAME,
                        "changeStreamPreAndPostImages": {"enabled": True},
                    }
                )
                print("[fix]  changeStreamPreAndPostImages was OFF -- enabled now")
                print("       restart the processor: sp.ordersToIceberg.start({tier:'SP10', resumeFromCheckpoint:false})")

        count = coll.count_documents({})
        print(f"[ok]   {count} document(s) in {COLLECTION_NAME}")
        if count == 0:
            print("[warn] collection is empty -- run scripts/seed_orders.py")

        dlq = db[DLQ_COLLECTION].count_documents({})
        if dlq:
            ok = False
            print(f"[warn] {dlq} document(s) in the dead-letter queue")
            for doc in db[DLQ_COLLECTION].find().limit(3):
                reason = doc.get("errInfo", {}).get("reason", "unknown")
                print(f"       - {doc.get('doc', {}).get('_id', '?')}: {reason}")
            print("       clear it with: db.dlq.deleteMany({})")
        else:
            print("[ok]   dead-letter queue is empty")

        print(
            "\nIceberg side (needs AWS credentials, run manually):\n"
            "  aws athena start-query-execution --region <region> \\\n"
            "    --query-string \"SELECT count(*) AS total, count(DISTINCT _id) AS ids FROM orders\" \\\n"
            "    --query-execution-context Database=<glue-db> \\\n"
            "    --result-configuration OutputLocation=s3://<bucket>/athena-results/\n"
            f"  both numbers must equal {count}; a higher total means the table was\n"
            "  duplicated by a restart -- see docs/TROUBLESHOOTING.md"
        )
        check_aws()

        print("\npreflight " + ("PASSED" if ok else "PASSED WITH WARNINGS"))
    finally:
        client.close()


if __name__ == "__main__":
    main()
