from common import get_collection

ORDER_ID = "PED-AOVIVO-001"


def main():
    client, coll = get_collection()
    try:
        result = coll.update_one(
            {"_id": ORDER_ID},
            {"$set": {"status": "EM_TRANSPORTE", "amount": 2159.10}},
        )
        if result.matched_count == 0:
            raise SystemExit(
                f"{ORDER_ID} does not exist. Run scripts/insert_order.py first."
            )
        print(f"UPDATE {ORDER_ID}: status=EM_TRANSPORTE amount=R$ 2159.10")
    finally:
        client.close()


if __name__ == "__main__":
    main()
