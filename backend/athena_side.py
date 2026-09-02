"""Everything that touches the Iceberg table: Athena and Glue.

Degrades on purpose: AWS credentials expire between demos, and the UI must say
so plainly instead of showing a spinner forever.
"""

import re
import time

import boto3
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError

import settings


class AwsUnavailable(RuntimeError):
    """No usable AWS credentials."""


def _client(service: str):
    return boto3.client(service, region_name=settings.AWS_REGION)


def identity() -> dict:
    try:
        who = _client("sts").get_caller_identity()
        return {"disponivel": True, "arn": who.get("Arn"), "conta": who.get("Account")}
    except (NoCredentialsError, ClientError, BotoCoreError) as exc:
        return {"disponivel": False, "erro": _friendly(exc)}


def _friendly(exc: Exception) -> str:
    text = str(exc)
    if isinstance(exc, NoCredentialsError) or "NoCredentials" in text:
        return "Credencial AWS ausente ou expirada. Cole um bloco novo em ~/.aws/credentials."
    if "ExpiredToken" in text or "InvalidClientTokenId" in text:
        return "Credencial AWS expirada. Cole um bloco novo em ~/.aws/credentials."
    if "AccessDenied" in text:
        return f"Acesso negado pela policy IAM: {text[:200]}"
    return text[:300]


# Errors worth a short retry: transient network/throttling, not "your
# credentials are wrong" or "your SQL is wrong".
_TRANSIENT_ERROR_CODES = {
    "ThrottlingException",
    "TooManyRequestsException",
    "RequestTimeout",
    "RequestTimeoutException",
    "InternalServerException",
    "InternalFailure",
    "ServiceUnavailable",
    "ServiceUnavailableException",
}


def _is_transient(exc: ClientError) -> bool:
    code = exc.response.get("Error", {}).get("Code", "")
    return code in _TRANSIENT_ERROR_CODES


def run_query(sql: str, timeout: int = 60, retries: int = 3) -> dict:
    """Run one Athena query and return columns plus rows.

    Retries a small, fixed number of times (short backoff) on transient
    ClientErrors (throttling, transient service errors) before giving up.
    Credential errors and query failures are not retried.
    """
    started = time.perf_counter()
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return _run_query_once(sql, timeout, started)
        except (NoCredentialsError, BotoCoreError) as exc:
            raise AwsUnavailable(_friendly(exc)) from exc
        except ClientError as exc:
            last_exc = exc
            if not _is_transient(exc) or attempt == retries:
                raise AwsUnavailable(_friendly(exc)) from exc
            time.sleep(0.5 * attempt)  # short linear backoff: 0.5s, 1.0s, ...
    # Unreachable in practice -- the loop above always returns or raises.
    raise AwsUnavailable(_friendly(last_exc)) if last_exc else RuntimeError("run_query failed")


def _run_query_once(sql: str, timeout: int, started: float) -> dict:
    athena = _client("athena")
    execution = athena.start_query_execution(
        QueryString=sql.strip().rstrip(";"),
        QueryExecutionContext={"Database": settings.GLUE_DATABASE},
        ResultConfiguration={"OutputLocation": settings.ATHENA_OUTPUT},
        WorkGroup=settings.ATHENA_WORKGROUP,
    )
    qid = execution["QueryExecutionId"]

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        info = athena.get_query_execution(QueryExecutionId=qid)["QueryExecution"]
        state = info["Status"]["State"]
        if state == "SUCCEEDED":
            break
        if state in ("FAILED", "CANCELLED"):
            raise RuntimeError(info["Status"].get("StateChangeReason", state))
        time.sleep(0.6)
    else:
        raise RuntimeError("A query do Athena estourou o tempo limite.")

    result = athena.get_query_results(QueryExecutionId=qid, MaxResults=200)
    raw = [
        [cell.get("VarCharValue", "") for cell in row["Data"]]
        for row in result["ResultSet"]["Rows"]
    ]
    columns = raw[0] if raw else []
    rows = raw[1:] if len(raw) > 1 else []
    stats = info.get("Statistics", {})
    return {
        "colunas": columns,
        "linhas": rows,
        "query_id": qid,
        "tempo_ms": int(stats.get("EngineExecutionTimeInMillis", 0)),
        "bytes_escaneados": int(stats.get("DataScannedInBytes", 0)),
        "total_ms": int((time.perf_counter() - started) * 1000),
    }


def drop_table() -> dict:
    """DROP the Iceberg table so a checkpoint-less restart's initialSync can
    rebuild it clean instead of appending a duplicate copy on top.

    Used by stream-processing/rebuild_table.py, which is the automated
    counterpart of the manual `DROP TABLE IF EXISTS ...` step documented in
    docs/TROUBLESHOOTING.md.
    """
    return run_query(
        f"DROP TABLE IF EXISTS {settings.GLUE_DATABASE}.{settings.ICEBERG_TABLE}"
    )


def table_columns() -> list[dict]:
    try:
        table = _client("glue").get_table(
            DatabaseName=settings.GLUE_DATABASE, Name=settings.ICEBERG_TABLE
        )["Table"]
        return [
            {"nome": c["Name"], "tipo": c["Type"]}
            for c in table["StorageDescriptor"]["Columns"]
        ]
    except (NoCredentialsError, ClientError, BotoCoreError) as exc:
        raise AwsUnavailable(_friendly(exc)) from exc


def counts() -> dict:
    data = run_query(
        f"SELECT count(*) AS total, count(DISTINCT _id) AS ids "
        f"FROM {settings.GLUE_DATABASE}.{settings.ICEBERG_TABLE}"
    )
    total, ids = (int(v) for v in data["linhas"][0]) if data["linhas"] else (0, 0)
    return {
        "total": total,
        "distintos": ids,
        "tempo_ms": data["tempo_ms"],
        "bytes_escaneados": data["bytes_escaneados"],
    }


def find_order(order_id: str) -> dict:
    return run_query(
        f"SELECT _id, status, amount, channel, paymentmethod "
        f"FROM {settings.GLUE_DATABASE}.{settings.ICEBERG_TABLE} "
        f"WHERE _id = '{_safe(order_id)}'"
    )


def snapshots(limit: int = 12) -> dict:
    return run_query(
        f"SELECT snapshot_id, committed_at, operation, "
        f"summary['added-records'] AS adicionados, "
        f"summary['deleted-records'] AS removidos "
        f'FROM "{settings.GLUE_DATABASE}"."{settings.ICEBERG_TABLE}$snapshots" '
        f"ORDER BY committed_at DESC LIMIT {int(limit)}"
    )


def order_at_snapshot(order_id: str, snapshot_id: str) -> dict:
    return run_query(
        f"SELECT _id, status, amount "
        f"FROM {settings.GLUE_DATABASE}.{settings.ICEBERG_TABLE} "
        f"FOR VERSION AS OF {int(snapshot_id)} "
        f"WHERE _id = '{_safe(order_id)}'"
    )


def _safe(value: str) -> str:
    """Athena has no bind parameters here; reject anything but a boring ID."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", value):
        raise ValueError("Identificador inválido.")
    return value
