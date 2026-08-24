"""Everything that touches the operational cluster."""

from datetime import datetime, timezone

from pymongo import MongoClient

import settings

_client: MongoClient | None = None


def client() -> MongoClient:
    global _client
    if _client is None:
        if not settings.MONGODB_URI:
            raise RuntimeError("MONGODB_URI ausente. Preencha o .env na raiz do repositório.")
        _client = MongoClient(settings.MONGODB_URI, serverSelectionTimeoutMS=8000)
    return _client


def collection():
    return client()[settings.DATABASE_NAME][settings.COLLECTION_NAME]


def dlq():
    return client()[settings.DATABASE_NAME][settings.DLQ_COLLECTION]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ping() -> None:
    client().admin.command("ping")


def post_images_enabled() -> bool | None:
    db = client()[settings.DATABASE_NAME]
    info = next(db.list_collections(filter={"name": settings.COLLECTION_NAME}), None)
    if info is None:
        return None
    return (
        info.get("options", {})
        .get("changeStreamPreAndPostImages", {})
        .get("enabled", False)
    )


def enable_post_images() -> None:
    client()[settings.DATABASE_NAME].command(
        {
            "collMod": settings.COLLECTION_NAME,
            "changeStreamPreAndPostImages": {"enabled": True},
        }
    )


def overview() -> dict:
    coll = collection()
    total = coll.count_documents({})
    by_status = list(
        coll.aggregate(
            [{"$group": {"_id": "$status", "n": {"$sum": 1}}}, {"$sort": {"n": -1}}]
        )
    )
    totals = next(
        iter(
            coll.aggregate(
                [
                    {
                        "$group": {
                            "_id": None,
                            "receita": {"$sum": "$amount"},
                            "primeiro": {"$min": "$orderDate"},
                            "ultimo": {"$max": "$orderDate"},
                        }
                    }
                ]
            )
        ),
        {},
    )
    return {
        "total": total,
        "receita": round(totals.get("receita", 0), 2),
        "primeiro_pedido": totals.get("primeiro"),
        "ultimo_pedido": totals.get("ultimo"),
        "por_status": [{"status": r["_id"], "pedidos": r["n"]} for r in by_status],
        "dlq": dlq().count_documents({}),
    }


def find_order(order_id: str) -> dict | None:
    return collection().find_one({"_id": order_id})


# --- as quatro operações da demo -------------------------------------------

def demo_insert() -> dict:
    coll = collection()
    coll.delete_one({"_id": settings.LIVE_ORDER_ID})
    doc = {
        "_id": settings.LIVE_ORDER_ID,
        "customerId": "CLI-00042",
        "region": "SP",
        "product": 'Smart TV 50"',
        "quantity": 1,
        "amount": 2399.00,
        "status": "PROCESSANDO",
        "channel": "APP",
        "paymentMethod": "PIX",
        "orderDate": utcnow(),
    }
    coll.insert_one(doc)
    return doc


def demo_update() -> dict:
    result = collection().update_one(
        {"_id": settings.LIVE_ORDER_ID},
        {"$set": {"status": "EM_TRANSPORTE", "amount": 2159.10}},
    )
    if result.matched_count == 0:
        raise ValueError("O pedido não existe. Rode o INSERT primeiro.")
    return find_order(settings.LIVE_ORDER_ID)


def demo_delete() -> dict:
    deleted = collection().delete_one({"_id": settings.LIVE_ORDER_ID}).deleted_count
    return {"removidos": deleted}


def demo_schema_field() -> dict:
    coll = collection()
    coll.delete_one({"_id": settings.SCHEMA_ORDER_ID})
    doc = {
        "_id": settings.SCHEMA_ORDER_ID,
        "customerId": "CLI-00999",
        "region": "RJ",
        "product": 'Notebook 15"',
        "quantity": 1,
        "amount": 4299.00,
        "status": "EM_ANALISE",
        "channel": "SITE",
        "paymentMethod": "CREDITO",
        "fraudScore": 0.92,
        "orderDate": utcnow(),
    }
    coll.insert_one(doc)
    return doc


def demo_reset() -> dict:
    removed = collection().delete_many(
        {"_id": {"$in": [settings.LIVE_ORDER_ID, settings.SCHEMA_ORDER_ID]}}
    ).deleted_count
    return {"removidos": removed, "restantes": collection().count_documents({})}
