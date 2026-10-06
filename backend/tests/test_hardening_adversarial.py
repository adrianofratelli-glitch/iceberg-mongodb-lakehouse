"""Adversarial regressions found in the 2026-10 hardening pass. No network."""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parents[1]
SCRIPTS = BACKEND.parent / "scripts"
sys.path.insert(0, str(BACKEND))

import main  # noqa: E402

client = TestClient(main.app)

FAKE_HOST = "ac-abc123-shard-00-01.zzzz9.mongodb.net:27017"
# montado por partes para não disparar o secret scanning (credencial fictícia)
FAKE_SCHEME = "mongodb" + "+srv://"
FAKE_CRED = "user" + ":" + "s3cr3t"


# --- error text never leaks connection details ------------------------------

def test_safe_error_redacts_uri_hosts_and_aws_ids():
    raw = (
        f"{FAKE_SCHEME}{FAKE_CRED}@cluster0.zzzz9.mongodb.net/?x=1 timed out; "
        f"{FAKE_HOST}: [Errno 61] arn:aws:iam::123456789012:role/x AKIAIOSFODNN7EXAMPLE"
    )
    text = main.safe_error(raw)
    assert "s3cr3t" not in text and "zzzz9" not in text
    assert "123456789012" not in text and "AKIAIOSFODNN7EXAMPLE" not in text
    assert "<cluster-host>" in text or "<redacted>" in text


def test_visao_geral_503_does_not_echo_cluster_hosts(monkeypatch):
    def boom():
        raise RuntimeError(f"No servers found yet, Topology: {FAKE_HOST}")

    monkeypatch.setattr(main.mongo_side, "overview", boom)
    response = client.get("/api/visao-geral")
    assert response.status_code == 503
    assert "zzzz9" not in response.text


def test_preflight_survives_connection_drop_after_ping(monkeypatch):
    monkeypatch.setattr(main.mongo_side, "ping", lambda: None)

    def dropped():
        raise ConnectionError(f"connection closed {FAKE_HOST}")

    monkeypatch.setattr(main.mongo_side, "post_images_enabled", dropped)
    response = client.get("/preflight")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert "zzzz9" not in response.text


def test_pedido_mongo_down_is_503_not_500(monkeypatch):
    def boom(_):
        raise TimeoutError("server selection timeout")

    monkeypatch.setattr(main.mongo_side, "find_order", boom)
    assert client.get("/api/pedido/PED-1").status_code == 503


def test_pedido_without_order_date_is_not_the_string_none(monkeypatch):
    monkeypatch.setattr(main.mongo_side, "find_order", lambda _: {"_id": "PED-1"})
    monkeypatch.setattr(main.athena_side, "find_order", lambda _: {"linhas": []})
    body = client.get("/api/pedido/PED-1").json()
    assert "orderDate" not in body["mongo"]


def test_athena_failure_in_order_lookup_degrades_instead_of_500(monkeypatch):
    monkeypatch.setattr(main.mongo_side, "find_order", lambda _: None)

    def failed(_):
        raise RuntimeError("TABLE_NOT_FOUND")

    monkeypatch.setattr(main.athena_side, "find_order", failed)
    response = client.get("/api/pedido/PED-1")
    assert response.status_code == 200
    assert "TABLE_NOT_FOUND" in response.json()["iceberg"]["erro"]


def test_time_travel_athena_failure_is_502_with_message(monkeypatch):
    def failed(*_):
        raise RuntimeError("snapshot expired")

    monkeypatch.setattr(main.athena_side, "order_at_snapshot", failed)
    response = client.get("/api/snapshots/123/pedido/PED-1")
    assert response.status_code == 502
    assert "snapshot expired" in response.json()["erro"]


# --- hostile identifiers -----------------------------------------------------

@pytest.mark.parametrize(
    "order_id",
    [
        "PED-​001",          # zero-width space
        "PED-‮100",          # RTL override
        "PED-\U0001f9ca",         # emoji
        "PEDÍDO",                 # accented
        "$where",
        "x" * 60_000,             # near the HTTP client URL cap (64 KB)
    ],
)
def test_unusual_order_ids_are_rejected(monkeypatch, order_id):
    monkeypatch.setattr(main.mongo_side, "find_order", lambda _: pytest.fail("Mongo não deveria ser chamado"))
    response = client.get(f"/api/pedido/{order_id}")
    assert response.status_code in {404, 414, 422}


def test_operators_in_query_string_and_body_are_ignored(monkeypatch):
    seen = []
    monkeypatch.setattr(main.mongo_side, "find_order", lambda oid: seen.append(oid) or None)
    monkeypatch.setattr(main.athena_side, "find_order", lambda _: {"linhas": []})
    response = client.get("/api/pedido/PED-1?_id[$ne]=x&$where=1")
    assert response.status_code == 200
    assert seen == ["PED-1"]


def test_demo_endpoint_ignores_malformed_body_and_unknown_operations(monkeypatch):
    monkeypatch.setattr(main.mongo_side, "demo_delete", lambda: {"removidos": 0})
    ok = client.post("/api/demo/delete", content=b'{"_id": {"$gt": ""', headers={"content-type": "application/json"})
    assert ok.status_code == 200
    for op in ("drop", "%24where", "../reset", "insert;delete"):
        assert client.post(f"/api/demo/{op}").status_code in {404, 405}


def test_demo_query_details_show_the_idempotent_write(monkeypatch):
    monkeypatch.setattr(main.mongo_side, "demo_insert", lambda: {"_id": "PED-AOVIVO-001"})
    body = client.post("/api/demo/insert").json()
    assert "replaceOne" in body["query_details"]["query"][0]
    assert body["query_details"]["query"][0]["replaceOne"]["upsert"] is True


# --- seed / reset safety -----------------------------------------------------

@pytest.fixture
def scripts_env(monkeypatch):
    monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")
    monkeypatch.syspath_prepend(str(SCRIPTS))
    monkeypatch.syspath_prepend(str(BACKEND.parent))
    for name in ("common", "config", "seed_orders"):
        sys.modules.pop(name, None)
    yield
    for name in ("common", "config", "seed_orders"):
        sys.modules.pop(name, None)


def test_reset_refuses_demo_database_without_explicit_flag(scripts_env, monkeypatch):
    monkeypatch.delenv("ALLOW_DEMO_DB_WRITE", raising=False)
    common = importlib.import_module("common")
    with pytest.raises(SystemExit, match="Refusing"):
        common.assert_safe_target("iceberg_demo")
    common.assert_safe_target("iceberg_demo_test")  # always allowed
    monkeypatch.setenv("ALLOW_DEMO_DB_WRITE", "1")
    common.assert_safe_target("iceberg_demo")


def test_seed_ids_do_not_depend_on_the_current_month(scripts_env, monkeypatch):
    monkeypatch.delenv("SEED_ANCHOR", raising=False)
    seed = importlib.import_module("seed_orders")
    first = seed.seed_ids()
    assert len(first) == seed.SEED_COUNT
    assert seed.seed_ids() == first
    # the anchor is fixed, so a run next month writes the same ids
    assert all(i.startswith("PED-20") for i in first)
    assert max(i[4:10] for i in first) == "202608"
    monkeypatch.setenv("SEED_ANCHOR", "2027-01-15T00:00:00Z")
    assert seed.seed_ids() != first


def test_reset_removes_strays_and_live_docs_then_reseeds(scripts_env):
    reset_demo = importlib.import_module("reset_demo")
    coll = MagicMock()
    coll.database.name = "iceberg_demo_test"
    coll.name = "orders"
    coll.delete_many.return_value.deleted_count = 2
    coll.count_documents.return_value = 5000
    mongo = MagicMock()
    mongo.__getitem__.return_value.list_collections.return_value = iter(
        [{"options": {"changeStreamPreAndPostImages": {"enabled": True}}}]
    )
    mongo.__getitem__.return_value.__getitem__.return_value.delete_many.return_value.deleted_count = 3
    result = reset_demo.reset(mongo, coll)
    assert result["ok"] is True
    filters = [c.args[0] for c in coll.delete_many.call_args_list]
    assert {"_id": {"$in": reset_demo.LIVE_IDS}} in filters
    assert any("$nin" in f["_id"] for f in filters)
    assert coll.bulk_write.call_count == 5  # 5,000 upserts in batches of 1,000



def test_invalid_session_token_reads_as_expired_credential():
    from botocore.exceptions import ClientError

    exc = ClientError(
        {"Error": {"Code": "UnrecognizedClientException",
                   "Message": "The security token included in the request is invalid"}},
        "StartQueryExecution",
    )
    assert "expirada" in main.athena_side._friendly(exc)
