from common import get_collection, utcnow

ORDER_ID = "PED-AOVIVO-002"


def main():
    client, coll = get_collection()
    try:
        coll.delete_one({"_id": ORDER_ID})
        doc = {
            "_id": ORDER_ID,
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
        coll.insert_one(doc)
        print(f"INSERT {ORDER_ID} with NEW FIELD fraudScore=0.92")
        print("Validate with sql/05_validate_schema.sql")
    finally:
        client.close()


if __name__ == "__main__":
    main()
