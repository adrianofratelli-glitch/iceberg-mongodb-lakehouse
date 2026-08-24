from common import get_collection, utcnow

ORDER_ID = "PED-AOVIVO-001"


def main():
    client, coll = get_collection()
    try:
        if coll.find_one({"_id": ORDER_ID}):
            coll.delete_one({"_id": ORDER_ID})
            print(f"Removed existing {ORDER_ID} so the next operation is a clean INSERT.")

        doc = {
            "_id": ORDER_ID,
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
        coll.insert_one(doc)
        print(f"INSERT {ORDER_ID}: R$ {doc['amount']:.2f} status={doc['status']}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
