from common import get_collection

ORDER_ID = "PED-AOVIVO-001"


def main():
    client, coll = get_collection()
    try:
        result = coll.delete_one({"_id": ORDER_ID})
        print(f"DELETE {ORDER_ID}: {result.deleted_count} document(s)")
    finally:
        client.close()


if __name__ == "__main__":
    main()
