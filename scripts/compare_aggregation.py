"""Run the demo's business aggregation against MongoDB and time it.

The point is not that MongoDB is slow -- it is not. The point is that this
query has nothing to do with serving orders, and every second it spends on
the operational cluster is a second of cache, CPU and IO taken from the
checkout path. The same aggregation over Iceberg on S3 costs the cluster
nothing.

Pair the number printed here with the Athena figures in
docs/prompts/03-interface-fluxos.md.
"""

import time

from common import get_collection

PIPELINE = [
    {
        "$group": {
            "_id": {
                "region": "$region",
                "mes": {"$dateToString": {"format": "%Y-%m", "date": "$orderDate"}},
            },
            "pedidos": {"$sum": 1},
            "receita": {"$sum": "$amount"},
            "ticket_medio": {"$avg": "$amount"},
            "cancelados": {
                "$sum": {"$cond": [{"$eq": ["$status", "CANCELADO"]}, 1, 0]}
            },
            "via_app": {"$sum": {"$cond": [{"$eq": ["$channel", "APP"]}, 1, 0]}},
        }
    },
    {"$sort": {"receita": -1}},
    {"$limit": 25},
]


def main():
    client, coll = get_collection()
    try:
        total = coll.count_documents({})

        started = time.perf_counter()
        rows = list(coll.aggregate(PIPELINE))
        elapsed = time.perf_counter() - started

        explain = client[coll.database.name].command(
            {
                "explain": {"aggregate": coll.name, "pipeline": PIPELINE, "cursor": {}},
                "verbosity": "executionStats",
            }
        )
        stats = explain.get("executionStats", {})
        examined = stats.get("totalDocsExamined")

        print(f"MongoDB (cluster operacional)")
        print(f"  documentos na colecao : {total}")
        if examined is not None:
            print(f"  documentos examinados : {examined}  (COLLSCAN -- sem indice que ajude)")
        print(f"  tempo                 : {elapsed * 1000:.0f} ms")
        print(f"  linhas retornadas     : {len(rows)}")
        print()
        print("Athena (Iceberg no S3, mesma agregacao -- sql/06)")
        print("  tempo                 : ~2.6 s")
        print("  dados escaneados      : ~450 KB")
        print("  impacto no cluster    : nenhum")
        print()
        print("Nesta escala o MongoDB ganha em tempo -- 5 mil documentos cabem na RAM.")
        print("O argumento nao e velocidade: e que a varredura analitica nao disputa")
        print("recursos com a carga transacional, e que o historico pode crescer no S3")
        print("sem crescer o cluster.")

        print("\nTop 5:")
        for row in rows[:5]:
            key = row["_id"]
            print(
                f"  {key['region']} {key['mes']}  "
                f"{row['pedidos']:>4} pedidos  R$ {row['receita']:>12,.2f}"
            )
    finally:
        client.close()


if __name__ == "__main__":
    main()
