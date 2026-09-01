from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import athena_side  # noqa: E402
import main  # noqa: E402


client = TestClient(main.app)


@pytest.mark.parametrize(
    "order_id",
    ["!!!", "pedido com espaços", "abc' OR '1'='1", '{"$ne":null}', "x" * 129],
)
def test_order_id_is_rejected_before_any_backend_call(monkeypatch, order_id: str):
    monkeypatch.setattr(main.mongo_side, "find_order", lambda _: pytest.fail("Mongo não deveria ser chamado"))
    monkeypatch.setattr(main.athena_side, "find_order", lambda _: pytest.fail("Athena não deveria ser chamado"))
    response = client.get(f"/api/pedido/{order_id}")
    assert response.status_code == 422, response.text


@pytest.mark.parametrize("snapshot_id", ["zero", "0", "-1", "9" * 80])
def test_snapshot_id_must_be_a_positive_bounded_integer(monkeypatch, snapshot_id: str):
    monkeypatch.setattr(
        main.athena_side,
        "order_at_snapshot",
        lambda *_: pytest.fail("Athena não deveria ser chamado"),
    )
    response = client.get(f"/api/snapshots/{snapshot_id}/pedido/ORDER-1")
    assert response.status_code == 422, response.text


@pytest.mark.parametrize("value", ["", "!!!", "abc def", "abc' OR '1'='1", "x" * 129])
def test_athena_identifier_guard_rejects_instead_of_silently_rewriting(value: str):
    with pytest.raises(ValueError):
        athena_side._safe(value)


def test_unknown_or_traversal_query_never_reads_outside_sql_directory():
    for query_id in ("../README", "%2e%2e%2fREADME", "x" * 200):
        response = client.post(f"/api/consultas/{query_id}")
        assert response.status_code in {404, 422}, response.text
