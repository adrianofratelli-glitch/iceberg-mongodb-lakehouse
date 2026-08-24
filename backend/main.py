"""API da PoV Iceberg + MongoDB.

Duas metades: o cluster operacional (MongoDB) e a tabela derivada (Iceberg no
S3, lida por Athena). A interface mostra as duas lado a lado -- a tese da PoV é
justamente que elas convergem sozinhas.
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import athena_side
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
        checks.append({"item": "Conexão com o Atlas", "estado": "falha", "detalhe": str(exc)[:200]})
        return {"ok": False, "checks": checks}

    images = mongo_side.post_images_enabled()
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

    dlq = mongo_side.dlq().count_documents({})
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
            "detalhe": aws.get("arn") or aws.get("erro"),
        }
    )

    return {"ok": ok, "checks": checks}


@app.get("/api/visao-geral")
def visao_geral():
    try:
        mongo = mongo_side.overview()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"MongoDB indisponível: {exc}") from exc

    iceberg: dict = {"disponivel": False}
    try:
        iceberg = {"disponivel": True, **athena_side.counts()}
    except athena_side.AwsUnavailable as exc:
        iceberg["erro"] = str(exc)
    except Exception as exc:  # noqa: BLE001
        iceberg["erro"] = str(exc)[:300]

    convergiu = (
        iceberg.get("disponivel")
        and iceberg.get("total") == mongo["total"]
        and iceberg.get("distintos") == mongo["total"]
    )
    return {"mongo": mongo, "iceberg": iceberg, "convergiu": bool(convergiu)}


@app.get("/api/schema")
def schema():
    try:
        return {"disponivel": True, "colunas": athena_side.table_columns()}
    except athena_side.AwsUnavailable as exc:
        return {"disponivel": False, "erro": str(exc)}


@app.get("/api/pedido/{order_id}")
def pedido(order_id: str):
    doc = mongo_side.find_order(order_id)
    if doc and isinstance(doc.get("orderDate"), object):
        doc = {**doc, "orderDate": str(doc.get("orderDate"))}
    resposta = {"mongo": doc}
    try:
        resposta["iceberg"] = athena_side.find_order(order_id)
    except athena_side.AwsUnavailable as exc:
        resposta["iceberg"] = {"erro": str(exc)}
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
        raise HTTPException(status_code=503, detail=str(exc)[:300]) from exc

    if isinstance(resultado, dict) and "orderDate" in resultado:
        resultado = {**resultado, "orderDate": str(resultado["orderDate"])}
    mensagens = {
        "insert": "Pedido inserido no MongoDB. O change stream já levou o evento adiante.",
        "update": "Pedido atualizado. Data lake append-only não faria isso sem reescrever partição.",
        "delete": "Pedido removido. Acompanhe a linha sumir do Iceberg.",
        "schema": "Pedido com campo novo. O Iceberg evolui o schema sozinho.",
        "reset": "Documentos da demo removidos.",
    }
    return {"operacao": operacao, "documento": resultado, "mensagem": mensagens[operacao]}


@app.post("/api/corrigir/post-images")
def corrigir_post_images():
    try:
        mongo_side.enable_post_images()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=str(exc)[:300]) from exc
    return {
        "ok": True,
        "mensagem": "Post-images habilitado. Reinicie o processor sem checkpoint: "
        'load("stream-processing/restart_processor.js")',
    }


@app.get("/api/snapshots")
def snapshots():
    try:
        return {"disponivel": True, **athena_side.snapshots()}
    except athena_side.AwsUnavailable as exc:
        return {"disponivel": False, "erro": str(exc)}


@app.get("/api/snapshots/{snapshot_id}/pedido/{order_id}")
def pedido_no_snapshot(snapshot_id: str, order_id: str):
    try:
        return {"disponivel": True, **athena_side.order_at_snapshot(order_id, snapshot_id)}
    except athena_side.AwsUnavailable as exc:
        return {"disponivel": False, "erro": str(exc)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
def rodar_consulta(consulta_id: str):
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
        return {"disponivel": True, "sql": sql, **athena_side.run_query(sql)}
    except athena_side.AwsUnavailable as exc:
        return {"disponivel": False, "sql": sql, "erro": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=502, content={"disponivel": True, "erro": str(exc)[:300]})
