"""Convergência real MongoDB -> processor -> Iceberg -> Athena (uma amostra).

Pulado por padrão. Exige credencial AWS válida, o processor rodando e um banco
que ele leia (o da demo, com ALLOW_DEMO_DB_WRITE=1, ou um *_test com processor
próprio):

    LIVE_LAKE=1 ALLOW_DEMO_DB_WRITE=1 DATABASE_NAME=iceberg_demo \\
        backend/venv/bin/pytest -q backend/tests/test_live_lake_convergence.py

A sonda usa um id PED-PROBE-* e o apaga no fim, mesmo em falha.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(os.getenv("LIVE_LAKE") != "1", reason="LIVE_LAKE=1 não definido (exige AWS + processor)")

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))


def test_insert_update_delete_reach_athena():
    import athena_side
    import lake_probe
    import mongo_side
    import settings

    lake_probe.assert_safe_target(settings.DATABASE_NAME)
    aws = athena_side.identity()
    if not aws["disponivel"]:
        pytest.skip(f"AWS indisponível: {aws.get('erro')}")
    timeout = float(os.getenv("LIVE_LAKE_TIMEOUT", "120"))
    res = lake_probe.run_sample(
        mongo_side.collection(),
        "PED-PROBE-pytest-000",
        athena_side.find_order,
        timeout_s=timeout,
        interval_s=3,
    )
    for op in ("insert", "update", "delete"):
        assert res.get(op, {}).get("ok"), f"{op} não convergiu em {timeout}s: {res}"
