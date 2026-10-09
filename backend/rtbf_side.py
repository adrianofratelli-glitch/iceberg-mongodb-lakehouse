"""Direito ao esquecimento no lake: o que o DELETE faz e o que ainda falta.

O DELETE no MongoDB chega ao Iceberg como um commit novo: a linha some da
visão corrente, mas os snapshots anteriores continuam referenciando o arquivo
de dados que a contém -- é isso que faz o time travel funcionar. Pela
documentação do Iceberg (Maintenance, "Expire Snapshots"): "Data files are not
deleted until they are no longer referenced by a snapshot that may be used for
time travel or rollback."

Apagamento definitivo, portanto, são três passos depois do DELETE propagado:

1. OPTIMIZE ... REWRITE DATA USING BIN_PACK -- reescreve os arquivos de dados
   aplicando os delete files; o snapshot novo não referencia mais o arquivo
   antigo. Os limiares ``optimize_rewrite_*_threshold`` (padrão 5 arquivos e 2
   delete files) são baixados para 1, senão um único delete não dispara a
   reescrita.
2. VACUUM com ``vacuum_max_snapshot_age_seconds`` = retenção -- expira os
   snapshots mais velhos que a retenção e remove os arquivos que ficaram
   inalcançáveis e os órfãos.
3. Verificação: nenhum snapshot retido devolve o pedido.

Referências (Athena engine v3):
- https://iceberg.apache.org/docs/latest/maintenance/
- https://docs.aws.amazon.com/athena/latest/ug/vacuum-statement.html
- https://docs.aws.amazon.com/athena/latest/ug/optimize-statement.html
- https://docs.aws.amazon.com/athena/latest/ug/querying-iceberg-creating-tables.html

O expurgo é destrutivo para o time travel da tabela inteira, por isso só roda
com ``ALLOW_LAKE_PURGE=1``. A verificação é só leitura.
"""

from __future__ import annotations

import os
import re

import athena_side
import settings

# Padrão do Athena para vacuum_max_snapshot_age_seconds (5 dias).
RETENCAO_PADRAO_S = 432_000
MAX_SNAPSHOTS_VERIFICADOS = 50


def tabela() -> str:
    return f"{settings.GLUE_DATABASE}.{settings.ICEBERG_TABLE}"


def expurgo_habilitado() -> bool:
    return os.getenv("ALLOW_LAKE_PURGE") == "1"


def passos(retencao_s: int = 1) -> list[dict]:
    """Os comandos do expurgo, na ordem, para a UI e o README mostrarem."""
    t = tabela()
    return [
        {
            "passo": "1. DELETE no MongoDB",
            "descricao": "O processor propaga o delete: a linha some da visão atual do Iceberg. "
            "Os snapshots anteriores ainda a contêm (é o time travel).",
            "sql": None,
        },
        {
            "passo": "2. Reescrever os arquivos com o delete aplicado",
            "descricao": "Limiar 1 para que um único delete já dispare a reescrita; o snapshot "
            "novo deixa de referenciar o arquivo antigo.",
            "sql": [
                f"ALTER TABLE {t} SET TBLPROPERTIES ("
                "'optimize_rewrite_delete_file_threshold'='1', "
                "'optimize_rewrite_data_file_threshold'='1')",
                f"OPTIMIZE {t} REWRITE DATA USING BIN_PACK",
            ],
        },
        {
            "passo": "3. Expirar snapshots e remover arquivos",
            "descricao": "VACUUM expira snapshots mais velhos que a retenção e apaga os arquivos "
            "inalcançáveis e órfãos. Depois a retenção volta ao padrão. O time travel "
            "anterior a este ponto deixa de existir.",
            "sql": [
                f"ALTER TABLE {t} SET TBLPROPERTIES "
                f"('vacuum_max_snapshot_age_seconds'='{int(retencao_s)}')",
                f"VACUUM {t}",
                f"ALTER TABLE {t} SET TBLPROPERTIES "
                f"('vacuum_max_snapshot_age_seconds'='{RETENCAO_PADRAO_S}')",
            ],
        },
        {
            "passo": "4. Verificar",
            "descricao": "Nenhum snapshot retido pode devolver o pedido (FOR VERSION AS OF em cada um).",
            "sql": None,
        },
    ]


def _snapshot_ids(limit: int = MAX_SNAPSHOTS_VERIFICADOS) -> list[int]:
    dados = athena_side.run_query(
        f'SELECT snapshot_id FROM "{settings.GLUE_DATABASE}"."{settings.ICEBERG_TABLE}$snapshots" '
        f"ORDER BY committed_at DESC LIMIT {int(limit)}"
    )
    return [int(linha[0]) for linha in dados["linhas"] if linha and re.fullmatch(r"\d+", linha[0] or "")]


def query_snapshots_com_pedido(order_id: str, snapshot_ids: list[int]) -> str:
    """Uma query só: em quais snapshots retidos o pedido ainda aparece."""
    oid = athena_side._safe(order_id)  # noqa: SLF001 -- allowlist compartilhada
    partes = [
        f"SELECT CAST({int(sid)} AS bigint) AS snapshot_id FROM {tabela()} "
        f"FOR VERSION AS OF {int(sid)} WHERE _id = '{oid}'"
        for sid in snapshot_ids
    ]
    return " UNION ALL ".join(partes)


def versionamento_s3() -> str | None:
    """Com versionamento ligado, o objeto apagado vira versão não corrente."""
    if not settings.S3_BUCKET:
        return None
    try:
        resposta = athena_side._client("s3").get_bucket_versioning(Bucket=settings.S3_BUCKET)  # noqa: SLF001
    except Exception:  # noqa: BLE001 -- informação acessória; sem permissão, não sabemos
        return "desconhecido"
    return resposta.get("Status") or "Desligado"


def verificar(order_id: str) -> dict:
    """Só leitura. Levanta AwsUnavailable sem credencial."""
    atual = athena_side.find_order(order_id)
    ids = _snapshot_ids()
    com_pedido: list[int] = []
    if ids:
        dados = athena_side.run_query(query_snapshots_com_pedido(order_id, ids))
        com_pedido = sorted({int(l[0]) for l in dados["linhas"] if l and l[0]})
    versionamento = versionamento_s3()
    linhas_atuais = len(atual.get("linhas") or [])
    return {
        "linhas_na_visao_atual": linhas_atuais,
        "snapshots_verificados": len(ids),
        "snapshots_com_pedido": [str(s) for s in com_pedido],
        "versionamento_s3": versionamento,
        "apagado_do_lake": linhas_atuais == 0 and not com_pedido,
        "ressalvas": _ressalvas(versionamento, len(ids)),
    }


def _ressalvas(versionamento: str | None, verificados: int) -> list[str]:
    itens = [
        "VACUUM só apaga arquivos se o papel da query tiver s3:DeleteObject no bucket; "
        "sem a permissão a query termina com sucesso e os arquivos ficam.",
        "Backups do Atlas e a DLQ (iceberg_demo.dlq) têm retenção própria e ficam fora deste fluxo.",
    ]
    if versionamento == "Enabled":
        itens.insert(0, "O bucket tem versionamento ligado: os objetos removidos viram versões não "
                     "correntes até uma regra de lifecycle expirá-las.")
    elif versionamento == "desconhecido":
        itens.insert(0, "Não foi possível ler o versionamento do bucket; confirme se há versões não correntes.")
    if verificados >= MAX_SNAPSHOTS_VERIFICADOS:
        itens.append(f"Só os {MAX_SNAPSHOTS_VERIFICADOS} snapshots mais recentes foram verificados.")
    return itens


class PreCondicao(RuntimeError):
    """O pedido ainda existe em algum lugar que o expurgo não resolve."""


def expurgar(order_id: str, retencao_s: int = 1) -> dict:
    """Destrutivo: reescreve a tabela e expira o histórico. Exige ALLOW_LAKE_PURGE=1."""
    import mongo_side  # import tardio: o CLI pode rodar sem pymongo configurado

    if not expurgo_habilitado():
        raise PermissionError(
            "Expurgo desligado. Ele apaga o time travel da tabela inteira; "
            "habilite com ALLOW_LAKE_PURGE=1 no ambiente do backend."
        )
    if retencao_s < 1:
        raise ValueError("A retenção precisa ser um número positivo de segundos.")
    if mongo_side.find_order(order_id) is not None:
        raise PreCondicao("O pedido ainda existe no MongoDB. Rode o DELETE primeiro.")
    if athena_side.find_order(order_id).get("linhas"):
        raise PreCondicao("O delete ainda não chegou à visão atual do Iceberg. Aguarde o processor.")

    executados = []
    for passo in passos(retencao_s):
        for sql in passo["sql"] or []:
            resultado = athena_side.run_query(sql, timeout=300)
            executados.append({"sql": sql, "query_id": resultado.get("query_id")})
    return {"executados": executados, **verificar(order_id)}
