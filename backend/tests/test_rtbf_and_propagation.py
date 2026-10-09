"""Regressões da rodada 2026-10-08: RTBF honesto, propagação não presumida,
preflight explícito sem AWS e alerta de documento grande. Sem rede."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import athena_side  # noqa: E402
import main  # noqa: E402
import rtbf_side  # noqa: E402

client = TestClient(main.app)


@pytest.fixture
def mongo_fake(monkeypatch):
    estado = {"doc": None}
    doc = {"_id": "PED-AOVIVO-001", "status": "PROCESSANDO", "amount": 2399.0, "orderDate": "x"}
    monkeypatch.setattr(main.mongo_side, "demo_insert", lambda: dict(doc))
    monkeypatch.setattr(main.mongo_side, "demo_update", lambda: dict(doc, status="EM_TRANSPORTE"))
    monkeypatch.setattr(main.mongo_side, "demo_delete", lambda: {"removidos": 1})
    monkeypatch.setattr(main.mongo_side, "demo_schema_field", lambda: dict(doc, _id="PED-AOVIVO-002"))
    monkeypatch.setattr(main.mongo_side, "find_order", lambda _id: estado["doc"])
    return estado


# --- C6: a resposta não afirma entrega que não foi confirmada ----------------

@pytest.mark.parametrize("op", ["insert", "update", "delete", "schema"])
def test_demo_message_never_claims_lake_delivery(mongo_fake, op):
    body = client.post(f"/api/demo/{op}").json()
    texto = body["mensagem"].lower()
    assert "já levou" not in texto
    assert "evolui o schema sozinho" not in texto
    assert "aguardando" in texto
    assert body["propagacao"] == {
        "mongo": "confirmado",
        "iceberg": "aguardando_confirmacao",
        "confirmar_em": f"/api/pedido/{'PED-AOVIVO-002' if op == 'schema' else 'PED-AOVIVO-001'}",
    }


# --- C5: RTBF -----------------------------------------------------------------

def test_rtbf_plan_has_optimize_vacuum_and_thresholds():
    sqls = [sql for passo in rtbf_side.passos(1) for sql in (passo["sql"] or [])]
    joined = "\n".join(sqls)
    assert "optimize_rewrite_delete_file_threshold'='1'" in joined
    assert "optimize_rewrite_data_file_threshold'='1'" in joined
    assert "REWRITE DATA USING BIN_PACK" in joined
    assert "vacuum_max_snapshot_age_seconds'='1'" in joined
    # a retenção volta ao padrão depois do VACUUM
    assert sqls[-1].endswith(f"'vacuum_max_snapshot_age_seconds'='{rtbf_side.RETENCAO_PADRAO_S}')")
    assert sqls.index(next(s for s in sqls if s.startswith("VACUUM"))) > sqls.index(
        next(s for s in sqls if s.startswith("OPTIMIZE"))
    )


def test_snapshot_union_query_rejects_hostile_id_and_casts_ids():
    q = rtbf_side.query_snapshots_com_pedido("PED-1", [11, 22])
    assert q.count("FOR VERSION AS OF") == 2 and "UNION ALL" in q
    with pytest.raises(ValueError):
        rtbf_side.query_snapshots_com_pedido("x' OR '1'='1", [1])


def test_verificar_reports_order_still_in_old_snapshot(monkeypatch):
    def fake_query(sql, **_):
        if "$snapshots" in sql:
            return {"linhas": [["300"], ["200"], ["100"]]}
        if "UNION ALL" in sql:
            return {"linhas": [["100"]]}
        raise AssertionError(sql)

    monkeypatch.setattr(athena_side, "find_order", lambda _id: {"linhas": []})
    monkeypatch.setattr(athena_side, "run_query", fake_query)
    monkeypatch.setattr(rtbf_side, "versionamento_s3", lambda: "Enabled")
    r = rtbf_side.verificar("PED-AOVIVO-001")
    assert r["linhas_na_visao_atual"] == 0
    assert r["snapshots_com_pedido"] == ["100"]
    assert r["apagado_do_lake"] is False
    assert any("versionamento" in x for x in r["ressalvas"])


def test_esquecimento_get_degrades_without_aws(mongo_fake, monkeypatch):
    def sem_aws(_id):
        raise athena_side.AwsUnavailable("Credencial AWS expirada. Cole um bloco novo em ~/.aws/credentials.")

    monkeypatch.setattr(rtbf_side, "verificar", sem_aws)
    r = client.get("/api/esquecimento/PED-AOVIVO-001")
    assert r.status_code == 200
    body = r.json()
    assert body["disponivel"] is False and "expirada" in body["erro"]
    assert len(body["passos"]) == 4 and body["no_mongo"] is False


def test_esquecimento_rejects_hostile_id():
    assert client.get("/api/esquecimento/%7B%22$ne%22:null%7D").status_code == 422
    assert client.post("/api/esquecimento/a'b").status_code == 422


def test_purge_is_refused_without_flag(monkeypatch):
    monkeypatch.delenv("ALLOW_LAKE_PURGE", raising=False)
    called = []
    monkeypatch.setattr(athena_side, "run_query", lambda *a, **k: called.append(a))
    r = client.post("/api/esquecimento/PED-AOVIVO-001")
    assert r.status_code == 403
    assert not called


def test_purge_refuses_while_order_still_in_mongo(mongo_fake, monkeypatch):
    monkeypatch.setenv("ALLOW_LAKE_PURGE", "1")
    mongo_fake["doc"] = {"_id": "PED-AOVIVO-001"}
    called = []
    monkeypatch.setattr(athena_side, "run_query", lambda *a, **k: called.append(a))
    r = client.post("/api/esquecimento/PED-AOVIVO-001")
    assert r.status_code == 409 and "MongoDB" in r.json()["detail"]
    assert not called


def test_purge_refuses_while_delete_not_in_current_view(mongo_fake, monkeypatch):
    monkeypatch.setenv("ALLOW_LAKE_PURGE", "1")
    monkeypatch.setattr(athena_side, "find_order", lambda _id: {"linhas": [["PED-AOVIVO-001"]]})
    called = []
    monkeypatch.setattr(athena_side, "run_query", lambda *a, **k: called.append(a))
    r = client.post("/api/esquecimento/PED-AOVIVO-001")
    assert r.status_code == 409 and "processor" in r.json()["detail"]
    assert not called


def test_purge_runs_steps_in_order_then_verifies(mongo_fake, monkeypatch):
    monkeypatch.setenv("ALLOW_LAKE_PURGE", "1")
    monkeypatch.setattr(athena_side, "find_order", lambda _id: {"linhas": []})
    executados = []

    def fake_query(sql, **_):
        executados.append(sql)
        if "$snapshots" in sql:
            return {"linhas": [["999"]]}
        if "UNION ALL" in sql:
            return {"linhas": []}
        return {"linhas": [], "query_id": "q"}

    monkeypatch.setattr(athena_side, "run_query", fake_query)
    monkeypatch.setattr(rtbf_side, "versionamento_s3", lambda: "Desligado")
    r = client.post("/api/esquecimento/PED-AOVIVO-001")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["apagado_do_lake"] is True
    kinds = [s.split()[0] for s in executados[:5]]
    assert kinds == ["ALTER", "OPTIMIZE", "ALTER", "VACUUM", "ALTER"]


# --- preflight sem AWS e documento grande ------------------------------------

def _preflight_base(monkeypatch, maior=1000):
    monkeypatch.setattr(main.mongo_side, "ping", lambda: None)
    monkeypatch.setattr(main.mongo_side, "post_images_enabled", lambda: True)
    monkeypatch.setattr(main.mongo_side, "largest_document_bytes", lambda: maior)

    class Dlq:
        def count_documents(self, _f):
            return 0

    monkeypatch.setattr(main.mongo_side, "dlq", lambda: Dlq())


def test_preflight_says_mongodb_only_mode_when_aws_expired(monkeypatch):
    _preflight_base(monkeypatch)
    monkeypatch.setattr(
        athena_side,
        "identity",
        lambda: {"disponivel": False, "erro": "Credencial AWS expirada. Cole um bloco novo em ~/.aws/credentials."},
    )
    body = client.get("/preflight").json()
    assert body["ok"] is True
    assert body["demo_completa"] is False
    assert body["modo"] == "somente_mongodb"
    assert "Credencial AWS expirada" in body["resumo"]
    assert "nenhuma propagação é confirmada" in body["resumo"]


def test_preflight_full_mode_when_aws_ok(monkeypatch):
    _preflight_base(monkeypatch)
    monkeypatch.setattr(athena_side, "identity", lambda: {"disponivel": True, "arn": "arn:aws:sts::123456789012:x"})
    body = client.get("/preflight").json()
    assert body["modo"] == "completa" and body["demo_completa"] is True
    assert "123456789012" not in str(body)


def test_preflight_flags_document_near_event_limit(monkeypatch):
    _preflight_base(monkeypatch, maior=9 * 1024 * 1024)
    monkeypatch.setattr(athena_side, "identity", lambda: {"disponivel": True, "arn": "x"})
    item = next(c for c in client.get("/preflight").json()["checks"] if c["item"] == "Maior documento")
    assert item["estado"] == "alerta" and "16 MB" in item["detalhe"]
