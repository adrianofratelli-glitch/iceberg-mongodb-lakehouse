"""Resume-token lag monitoring.

Nothing today measures the distance between the processor's checkpoint and
the end of the source oplog. The failure is discovered only after the
processor is already FAILED and the resume token has rolled off the oplog --
at that point recovery without a table rebuild is no longer possible (see
docs/TROUBLESHOOTING.md, "Resume of change stream was not possible").

This module gives an earlier signal: it reads the processor's checkpoint
timestamp (via `mongosh --eval 'sp.<name>.stats()'` against the Stream
Processing workspace -- pymongo cannot talk to ASP workspaces directly) and
compares it against the source cluster's current oplog window (read directly
via pymongo, same connection as the rest of the app).

Best-effort by construction:
  - STREAM_PROCESSING_URI must be configured (it is not required for the rest
    of the app, so this degrades to "não configurado" if unset).
  - Reading local.oplog.rs requires a role with access to it, which some
    Atlas tiers/users restrict. That failure is reported, not raised.
  - The exact shape of sp.<name>.stats() output has not been validated
    against a live Atlas Stream Processing workspace as part of this change;
    the parser below is defensive (falls back to "desconhecido" instead of
    raising) but the field names it looks for should be re-checked against a
    real workspace before this is relied on for a demo.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone

import settings
from mongo_side import client


class LagUnavailable(RuntimeError):
    """Lag can't be computed right now (config, permissions, or mongosh)."""


def _run_mongosh_stats() -> dict:
    if not settings.STREAM_PROCESSING_URI:
        raise LagUnavailable(
            "STREAM_PROCESSING_URI não configurado. Defina no .env para habilitar "
            "o monitoramento de lag do checkpoint."
        )
    expr = f"JSON.stringify(sp.{settings.PROCESSOR_NAME}.stats())"
    try:
        proc = subprocess.run(
            [settings.MONGOSH_PATH, settings.STREAM_PROCESSING_URI, "--quiet", "--eval", expr],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except FileNotFoundError as exc:
        raise LagUnavailable(f"mongosh não encontrado (MONGOSH_PATH={settings.MONGOSH_PATH}).") from exc
    except subprocess.TimeoutExpired as exc:
        raise LagUnavailable("mongosh não respondeu a tempo.") from exc

    if proc.returncode != 0:
        raise LagUnavailable(f"mongosh falhou: {proc.stderr.strip()[:300]}")

    # mongosh --quiet still prefixes some output; take the last line that
    # looks like JSON.
    for line in reversed(proc.stdout.strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    raise LagUnavailable("Não foi possível interpretar a saída do mongosh.")


def _extract_checkpoint_ts(stats: dict) -> datetime | None:
    """sp.<name>.stats() shape is not fully documented here -- try the
    field names known to appear and fall back to None (reported upstream as
    'desconhecido') rather than guessing.
    """
    candidates = [
        ("stats", "checkpoint", "timestamp"),
        ("checkpoint", "timestamp"),
        ("stats", "checkpointTimestamp"),
        ("checkpointTimestamp",),
    ]
    for path in candidates:
        node = stats
        for key in path:
            if isinstance(node, dict) and key in node:
                node = node[key]
            else:
                node = None
                break
        if node:
            return _to_datetime(node)
    return None


def _to_datetime(value) -> datetime | None:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if isinstance(value, dict) and "$date" in value:
        return _to_datetime(value["$date"])
    return None


def _oplog_window() -> tuple[datetime, datetime]:
    """First and last entry timestamps in the source cluster's oplog.

    Requires read access to local.oplog.rs, which is often restricted on
    Atlas. Raises LagUnavailable if it can't be read.
    """
    try:
        oplog = client()["local"]["oplog.rs"]
        first = oplog.find_one(sort=[("$natural", 1)], projection={"ts": 1})
        last = oplog.find_one(sort=[("$natural", -1)], projection={"ts": 1})
    except Exception as exc:  # noqa: BLE001
        raise LagUnavailable(
            f"Sem acesso a local.oplog.rs para medir a janela do oplog: {exc}"
        ) from exc
    if not first or not last:
        raise LagUnavailable("Oplog vazio ou inacessível.")
    return (_bson_ts_to_datetime(first["ts"]), _bson_ts_to_datetime(last["ts"]))


def _bson_ts_to_datetime(ts) -> datetime:
    # pymongo Timestamp exposes .time (seconds since epoch) and .inc.
    return datetime.fromtimestamp(ts.time, tz=timezone.utc)


def processor_lag() -> dict:
    """Return the checkpoint-vs-oplog-window picture, or an explanation of
    why it can't be computed right now.
    """
    stats = _run_mongosh_stats()  # raises LagUnavailable on its own
    checkpoint_ts = _extract_checkpoint_ts(stats)
    oplog_start, oplog_end = _oplog_window()  # raises LagUnavailable on its own

    if checkpoint_ts is None:
        return {
            "disponivel": True,
            "estado": "desconhecido",
            "mensagem": "Checkpoint não encontrado na saída de stats() -- "
            "verifique o formato retornado pela versão do Atlas Stream Processing em uso.",
            "oplog_inicio": oplog_start.isoformat(),
            "oplog_fim": oplog_end.isoformat(),
        }

    window_seconds = (oplog_end - oplog_start).total_seconds()
    margin_seconds = (checkpoint_ts - oplog_start).total_seconds()

    if checkpoint_ts < oplog_start:
        estado = "critico"
        mensagem = (
            "O checkpoint já rolou para fora da janela do oplog. Um restart "
            "sem checkpoint vai duplicar a tabela -- rode "
            "stream-processing/rebuild_table.py --auto-rebuild antes de reiniciar."
        )
    elif window_seconds <= 0 or margin_seconds / window_seconds < 0.2:
        estado = "alerta"
        mensagem = (
            "O checkpoint está perto do início da janela do oplog. Um restart "
            "próximo pode duplicar a tabela -- monitore com mais frequência."
        )
    else:
        estado = "ok"
        mensagem = "Checkpoint dentro de uma margem segura da janela do oplog."

    return {
        "disponivel": True,
        "estado": estado,
        "mensagem": mensagem,
        "checkpoint": checkpoint_ts.isoformat(),
        "oplog_inicio": oplog_start.isoformat(),
        "oplog_fim": oplog_end.isoformat(),
        "margem_segundos": round(margin_seconds, 1),
        "janela_segundos": round(window_seconds, 1),
    }
