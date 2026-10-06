"""API da PoV Iceberg + MongoDB.

Duas metades: o cluster operacional (MongoDB) e a tabela derivada (Iceberg no
S3, lida por Athena). A interface mostra as duas lado a lado -- a tese da PoV é
justamente que elas convergem sozinhas.
"""

import re
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Path as ApiPath
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import athena_side
import lag_side
import mongo_side
import settings

app = FastAPI(title="Iceberg + MongoDB", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5250", "http://localhost:5250"],
    allow_methods=["*"],
    allow_headers=["*"],
)

SQL_DIR = Path(__file__).resolve().parents[1] / "sql"
OrderId = Annotated[
    str,
    ApiPath(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$"),
]
SnapshotId = Annotated[int, ApiPath(ge=1, le=9_223_372_036_854_775_807)]
QueryId = Annotated[
    str,
    ApiPath(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$"),
]


_URI_RE = re.compile(r"mongodb(?:\+srv)?://[^\s'\"]+")
_HOST_RE = re.compile(r"\b[\w.-]+\.mongodb(?:-dev)?\.net(?::\d+)?\b")
_AWS_ID_RE = re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b|\b\d{12}\b")


def safe_error(exc: BaseException | str, limit: int = 300) -> str:
    """Error text that can reach the browser: no URI, cluster host or AWS id.

    pymongo's ServerSelectionTimeoutError lists every replica-set host, and
    botocore messages can carry the account id; the UI only needs the cause.
    """
    text = str(exc)
    text = _URI_RE.sub("mongodb://<redacted>", text)
    text = _HOST_RE.sub("<cluster-host>", text)
    text = _AWS_ID_RE.sub("<aws-id>", text)
    return text[:limit]


@app.get("/health/live")
def health_live():
    return {"status": "ok"}


@app.get("/preflight")
def preflight():
    """O mesmo diagnóstico do scripts/preflight.py, servido para a interface."""
    checks = []
    ok = True

    try:
        mongo_side.ping()
        checks.append({"item": "Conexão com o Atlas", "estado": "ok"})
    except Exception as exc:  # noqa: BLE001
        ok = False
        checks.append({"item": "Conexão com o Atlas", "estado": "falha", "detalhe": safe_error(exc, 200)})
        return {"ok": False, "checks": checks}

    try:
        images = mongo_side.post_images_enabled()
        dlq = mongo_side.dlq().count_documents({})
    except Exception as exc:  # noqa: BLE001 -- connection dropped after the ping
        checks.append({"item": "Coleção de origem", "estado": "falha", "detalhe": safe_error(exc, 200)})
        return {"ok": False, "checks": checks}

    if images is True:
        checks.append({"item": "changeStreamPreAndPostImages", "estado": "ok"})
    elif images is False:
        ok = False
        checks.append(
            {
                "item": "changeStreamPreAndPostImages",
                "estado": "falha",
                "detalhe": "Sem post-image o processor morre no primeiro UPDATE. Use POST /api/corrigir/post-images.",
            }
        )
    else:
        ok = False
        checks.append({"item": "Coleção de origem", "estado": "falha", "detalhe": "A coleção não existe. Rode o seed."})

    checks.append(
        {
            "item": "Dead-letter queue",
            "estado": "ok" if dlq == 0 else "alerta",
            "detalhe": None if dlq == 0 else f"{dlq} documento(s) rejeitado(s)",
        }
    )

    aws = athena_side.identity()
    checks.append(
        {
            "item": "Credencial AWS",
            "estado": "ok" if aws["disponivel"] else "alerta",
            "detalhe": safe_error(aws.get("arn") or aws.get("erro") or ""),
        }
    )

    return {"ok": ok, "checks": checks}


@app.get("/api/visao-geral")
async def visao_geral():
    try:
        mongo = await run_in_threadpool(mongo_side.overview)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"MongoDB indisponível: {safe_error(exc)}") from exc

    iceberg: dict = {"disponivel": False}
    try:
        # athena_side.counts() polls Athena synchronously (sleep loop); runs
        # in a worker thread so it doesn't block the event loop.
        iceberg = {"disponivel": True, **(await run_in_threadpool(athena_side.counts))}
    except Exception as exc:  # noqa: BLE001 -- AwsUnavailable included
        iceberg["erro"] = safe_error(exc)

    convergiu = (
        iceberg.get("disponivel")
        and iceberg.get("total") == mongo["total"]
        and iceberg.get("distintos") == mongo["total"]
    )
    return {"mongo": mongo, "iceberg": iceberg, "convergiu": bool(convergiu)}


@app.get("/api/schema")
async def schema():
    try:
        colunas = await run_in_threadpool(athena_side.table_columns)
        return {"disponivel": True, "colunas": colunas}
    except Exception as exc:  # noqa: BLE001
        return {"disponivel": False, "erro": safe_error(exc)}


@app.get("/api/pedido/{order_id}")
async def pedido(order_id: OrderId):
    try:
        doc = await run_in_threadpool(mongo_side.find_order, order_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"MongoDB indisponível: {safe_error(exc)}") from exc
    if doc and doc.get("orderDate") is not None:
        doc = {**doc, "orderDate": str(doc["orderDate"])}
    resposta = {"mongo": doc}
    try:
        resposta["iceberg"] = await run_in_threadpool(athena_side.find_order, order_id)
    except Exception as exc:  # noqa: BLE001 -- AwsUnavailable or Athena FAILED
        resposta["iceberg"] = {"erro": safe_error(exc)}
    return resposta


class OperacaoResposta(BaseModel):
    operacao: str
    documento: dict | None = None
    mensagem: str


@app.post("/api/demo/{operacao}")
def demo(operacao: str):
    acoes = {
        "insert": mongo_side.demo_insert,
        "update": mongo_side.demo_update,
        "delete": mongo_side.demo_delete,
        "schema": mongo_side.demo_schema_field,
        "reset": mongo_side.demo_reset,
    }
    if operacao not in acoes:
        raise HTTPException(status_code=404, detail="Operação desconhecida.")
    try:
        resultado = acoes[operacao]()
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=safe_error(exc)) from exc

    if isinstance(resultado, dict) and "orderDate" in resultado:
        resultado = {**resultado, "orderDate": str(resultado["orderDate"])}
    mensagens = {
        "insert": "Pedido inserido no MongoDB. O change stream já levou o evento adiante.",
        "update": "Pedido atualizado. Data lake append-only não faria isso sem reescrever partição.",
        "delete": "Pedido removido. Acompanhe a linha sumir do Iceberg.",
        "schema": "Pedido com campo novo. O Iceberg evolui o schema sozinho.",
        "reset": "Documentos da demo removidos.",
    }
    ids = {
        "insert": settings.LIVE_ORDER_ID,
        "update": settings.LIVE_ORDER_ID,
        "delete": settings.LIVE_ORDER_ID,
        "schema": settings.SCHEMA_ORDER_ID,
    }
    calls = {
        "insert": [
            {"replaceOne": {"filter": {"_id": settings.LIVE_ORDER_ID}, "replacement": resultado, "upsert": True}},
        ],
        "update": [
            {
                "updateOne": {
                    "filter": {"_id": settings.LIVE_ORDER_ID},
                    "update": {"$set": {"status": "EM_TRANSPORTE", "amount": 2159.10}},
                }
            },
            {"findOne": {"filter": {"_id": settings.LIVE_ORDER_ID}}},
        ],
        "delete": [{"deleteOne": {"filter": {"_id": settings.LIVE_ORDER_ID}}}],
        "schema": [
            {"replaceOne": {"filter": {"_id": settings.SCHEMA_ORDER_ID}, "replacement": resultado, "upsert": True}},
        ],
        "reset": [
            {
                "deleteMany": {
                    "filter": {
                        "_id": {"$in": [settings.LIVE_ORDER_ID, settings.SCHEMA_ORDER_ID]}
                    }
                }
            }
        ],
    }
    return {
        "operacao": operacao,
        "documento": resultado,
        "mensagem": mensagens[operacao],
        "query_details": {
            "operation": operacao,
            "namespace": f"{settings.DATABASE_NAME}.{settings.COLLECTION_NAME}",
            "query": calls[operacao],
            "explain": (
                "Busca pela chave _id; o índice único nativo cobre as operações de demonstração."
                if operacao in ids
                else "Remoção por conjunto de chaves _id; o índice único nativo é suficiente."
            ),
        },
    }


@app.get("/api/lag")
async def lag():
    """Distância entre o checkpoint do processor e a janela do oplog.

    Dá visibilidade ANTES do processor falhar por checkpoint fora da janela
    (ver docs/TROUBLESHOOTING.md, "Resume of change stream was not
    possible") -- hoje isso só é descoberto quando o processor já está
    FAILED e a recuperação sem duplicar a tabela já não é mais possível.
    """
    try:
        return await run_in_threadpool(lag_side.processor_lag)
    except lag_side.LagUnavailable as exc:
        return {"disponivel": False, "erro": safe_error(exc)}


@app.post("/api/corrigir/post-images")
def corrigir_post_images():
    try:
        mongo_side.enable_post_images()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=safe_error(exc)) from exc
    return {
        "ok": True,
        "mensagem": "Post-images habilitado. Reinicie o processor sem checkpoint: "
        'load("stream-processing/restart_processor.js")',
    }


@app.get("/api/snapshots")
async def snapshots():
    try:
        return {"disponivel": True, **(await run_in_threadpool(athena_side.snapshots))}
    except Exception as exc:  # noqa: BLE001
        return {"disponivel": False, "erro": safe_error(exc)}


@app.get("/api/snapshots/{snapshot_id}/pedido/{order_id}")
async def pedido_no_snapshot(snapshot_id: SnapshotId, order_id: OrderId):
    try:
        dados = await run_in_threadpool(athena_side.order_at_snapshot, order_id, snapshot_id)
        return {"disponivel": True, **dados}
    except athena_side.AwsUnavailable as exc:
        return {"disponivel": False, "erro": safe_error(exc)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 -- Athena FAILED (expired snapshot, etc.)
        return JSONResponse(status_code=502, content={"disponivel": True, "erro": safe_error(exc)})


@app.get("/api/consultas")
def consultas():
    arquivos = sorted(SQL_DIR.glob("*.sql"))
    return {
        "consultas": [
            {"id": f.stem, "arquivo": f.name, "titulo": _titulo(f)} for f in arquivos
        ]
    }


def _titulo(path: Path) -> str:
    for linha in path.read_text().splitlines():
        if linha.startswith("--") and linha.strip("- ").strip():
            return linha.strip("- ").strip()
    return path.stem


@app.post("/api/consultas/{consulta_id}")
async def rodar_consulta(consulta_id: QueryId):
    caminho = SQL_DIR / f"{consulta_id}.sql"
    if not caminho.exists() or caminho.parent != SQL_DIR:
        raise HTTPException(status_code=404, detail="Consulta desconhecida.")
    sql = "\n".join(
        linha for linha in caminho.read_text().splitlines() if not linha.strip().startswith("--")
    ).strip()
    # arquivos com vários statements: roda o primeiro
    sql = sql.split(";")[0].strip()
    if not sql:
        raise HTTPException(status_code=400, detail="A consulta está vazia.")
    try:
        resultado = await run_in_threadpool(athena_side.run_query, sql)
        return {"disponivel": True, "sql": sql, **resultado}
    except athena_side.AwsUnavailable as exc:
        return {"disponivel": False, "sql": sql, "erro": safe_error(exc)}
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=502, content={"disponivel": True, "erro": safe_error(exc)})
