from common import get_collection

LIVE_IDS = ["PED-AOVIVO-001", "PED-AOVIVO-002"]


def main():
    client, coll = get_collection()
    try:
        result = coll.delete_many({"_id": {"$in": LIVE_IDS}})
        print(f"Removed {result.deleted_count} live demo document(s).")
        print(f"{coll.count_documents({})} seeded orders remain.")
    finally:
        client.close()


if __name__ == "__main__":
    main()
