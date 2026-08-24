from common import get_collection, utcnow

LIVE_1 = "PED-AOVIVO-001"
LIVE_2 = "PED-AOVIVO-002"


def wait(message):
    input(f"\n{message}\nPress ENTER when ready... ")


def main():
    client, coll = get_collection()
    try:
        coll.delete_many({"_id": {"$in": [LIVE_1, LIVE_2]}})
        print("Live demo records reset.")

        wait("STEP 1 - INSERT. Have Athena ready with sql/02_find_live_order.sql.")
        coll.insert_one(
            {
                "_id": LIVE_1,
                "customerId": "CLI-00042",
                "region": "SP",
                "product": "Smart TV 50\"",
                "quantity": 1,
                "amount": 2399.00,
                "status": "PROCESSANDO",
                "channel": "APP",
                "paymentMethod": "PIX",
                "orderDate": utcnow(),
            }
        )
        print(f"INSERTED {LIVE_1} status=PROCESSANDO amount=2399.00")

        wait("Refresh Athena. Confirm ORD-LIVE-001 exists. Next: UPDATE.")
        coll.update_one(
            {"_id": LIVE_1},
            {"$set": {"status": "EM_TRANSPORTE", "amount": 2159.10}},
        )
        print(f"UPDATED {LIVE_1} status=EM_TRANSPORTE amount=2159.10")

        wait("Run sql/03_validate_update.sql. Next: DELETE.")
        coll.delete_one({"_id": LIVE_1})
        print(f"DELETED {LIVE_1}")

        wait("Run sql/04_validate_delete.sql and confirm zero rows. Next: SCHEMA CHANGE.")
        coll.insert_one(
            {
                "_id": LIVE_2,
                "customerId": "CLI-00999",
                "region": "RJ",
                "product": "Notebook 15\"",
                "quantity": 1,
                "amount": 4299.00,
                "status": "EM_ANALISE",
                "channel": "SITE",
                "paymentMethod": "CREDITO",
                "fraudScore": 0.92,
                "orderDate": utcnow(),
            }
        )
        print(f"INSERTED {LIVE_2} with NEW FIELD fraudScore=0.92")

        print("\nFinal step: run sql/05_validate_schema.sql in Athena.")
        print("Demo complete.")
    finally:
        client.close()


if __name__ == "__main__":
    main()
