"""Seed the demo collection with a realistic order history.

Volume matters for the demo: aggregations over a dozen rows prove nothing.
This writes SEED_COUNT orders spread over the last 18 months, so the Athena
queries in sql/ return something worth looking at.

Field names stay in English to match the Iceberg schema already in the
catalog -- only the values are Brazilian. Amounts are BRL, stored as double:
Decimal128 is rejected by $iceberg and lands in the DLQ.
"""

import random
from datetime import timedelta

from pymongo import ReplaceOne, UpdateOne
from common import get_collection, utcnow

SEED_COUNT = 5000
BATCH = 1000
RANDOM_SEED = 42

# (produto, preço unitário em BRL)
PRODUCTS = [
    ("Cafeteira Expressa", 389.90),
    ("Fone Bluetooth", 249.00),
    ("Air Fryer 5L", 549.90),
    ("Smart TV 50\"", 2399.00),
    ("Notebook 15\"", 4299.00),
    ("Cadeira Gamer", 1189.00),
    ("Ventilador de Coluna", 219.90),
    ("Liquidificador", 179.90),
    ("Monitor 27\"", 1549.00),
    ("Teclado Mecanico", 429.00),
    ("Tenis de Corrida", 399.90),
    ("Mochila Executiva", 289.90),
    ("Panela de Pressao Eletrica", 459.00),
    ("Aspirador Robo", 1899.00),
    ("Smartphone 128GB", 2199.00),
]

# UF com peso aproximado de participação no varejo nacional
REGIONS = [
    ("SP", 32), ("RJ", 13), ("MG", 11), ("RS", 8), ("PR", 7),
    ("BA", 6), ("SC", 6), ("PE", 5), ("CE", 4), ("GO", 3),
    ("DF", 3), ("ES", 2),
]

CHANNELS = ["APP", "SITE", "MARKETPLACE", "LOJA"]
PAYMENTS = ["PIX", "CREDITO", "BOLETO", "DEBITO"]
STATUSES = [
    ("ENTREGUE", 62), ("EM_TRANSPORTE", 14), ("SEPARACAO", 10),
    ("PROCESSANDO", 8), ("CANCELADO", 4), ("EM_ANALISE", 2),
]


def weighted(pairs, rng):
    population = [value for value, _ in pairs]
    weights = [weight for _, weight in pairs]
    return rng.choices(population, weights=weights, k=1)[0]


def build_orders(rng):
    now = utcnow()
    for i in range(1, SEED_COUNT + 1):
        product, unit_price = rng.choice(PRODUCTS)
        quantity = rng.choices([1, 2, 3, 4], weights=[70, 20, 7, 3], k=1)[0]
        # pedidos mais recentes são mais frequentes
        days_ago = int(abs(rng.gauss(0, 190))) % 540
        order_date = now - timedelta(
            days=days_ago, hours=rng.randrange(24), minutes=rng.randrange(60)
        )
        yield {
            "_id": f"PED-{order_date:%Y%m}-{i:06d}",
            "customerId": f"CLI-{rng.randrange(1, 1200):05d}",
            "region": weighted(REGIONS, rng),
            "product": product,
            "quantity": quantity,
            "amount": round(unit_price * quantity, 2),
            "status": weighted(STATUSES, rng),
            "channel": rng.choice(CHANNELS),
            "paymentMethod": weighted(
                [(p, w) for p, w in zip(PAYMENTS, [46, 34, 12, 8])], rng
            ),
            "orderDate": order_date,
        }


def main():
    rng = random.Random(RANDOM_SEED)
    client, coll = get_collection()
    try:
        ops, written = [], 0
        for doc in build_orders(rng):
            ops.append(ReplaceOne({"_id": doc["_id"]}, doc, upsert=True))
            if len(ops) == BATCH:
                coll.bulk_write(ops, ordered=False)
                written += len(ops)
                print(f"  {written}/{SEED_COUNT}")
                ops = []
        if ops:
            coll.bulk_write(ops, ordered=False)
            written += len(ops)
            print(f"  {written}/{SEED_COUNT}")

        total = coll.count_documents({})
        print(f"\nSeed complete: {written} orders written, {total} in {coll.full_name}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
