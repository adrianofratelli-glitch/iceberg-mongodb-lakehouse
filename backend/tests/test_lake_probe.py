"""Sonda ponta a ponta (backend/lake_probe.py) e honestidade das respostas da demo.

Tudo offline: relógio, Athena e coleção são falsos. O caminho real roda com
LIVE_LAKE=1 em test_live_lake_convergence.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import athena_side  # noqa: E402
import lake_probe  # noqa: E402
import main  # noqa: E402
import mongo_side  # noqa: E402


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


class FakeLake:
    """Mongo + processor + Athena: a mudança aparece `lag` consultas depois."""

    def __init__(self, clock, lag_polls=2, query_s=1.0, never=()):
        self.clock = clock
        self.lag = lag_polls
        self.query_s = query_s
        self.never = set(never)
        self.mongo: dict[str, dict] = {}
        self.lake: dict[str, dict] = {}
        self.pending: list[list] = []  # [polls_left, op, id, doc]
        self.deleted: list[str] = []

    # coleção
    def insert_one(self, doc):
        self.mongo[doc["_id"]] = dict(doc)
        self._queue("insert", doc["_id"])

    def update_one(self, flt, upd):
        doc = self.mongo.get(flt["_id"])
        if doc:
            doc.update(upd["$set"])
            self._queue("update", flt["_id"])

    def delete_one(self, flt):
        self.deleted.append(flt["_id"])
        if self.mongo.pop(flt["_id"], None) is not None:
            self._queue("delete", flt["_id"])

    def _queue(self, op, oid):
        if op not in self.never:
            self.pending.append([self.lag, op, oid, dict(self.mongo.get(oid, {}))])

    # Athena
    def find_order(self, oid):
        self.clock.t += self.query_s
        for item in self.pending:
            item[0] -= 1
        for item in [p for p in self.pending if p[0] <= 0]:
            self.pending.remove(item)
            _, op, i, doc = item
            if op == "delete":
                self.lake.pop(i, None)
            else:
                self.lake[i] = doc
        row = self.lake.get(oid)
        linhas = [[row["_id"], row["status"], row["amount"], "APP", "PIX"]] if row else []
        return {"linhas": linhas, "bytes_escaneados": 1000}


def _sample(lake, clock, **kw):
    return lake_probe.run_sample(
        lake, "PED-PROBE-x-000", lake.find_order,
        timeout_s=kw.get("timeout_s", 30), interval_s=2, clock=clock, sleep=clock.sleep,
    )


def test_cycle_converges_and_reports_upper_bound():
    clock = FakeClock()
    lake = FakeLake(clock, lag_polls=2)
    res = _sample(lake, clock)
    assert [res[op]["ok"] for op in ("insert", "update", "delete")] == [True, True, True]
    # 2 consultas de 1 s + 1 espera de 2 s: o limite superior é 4 s, janela 4 s
    assert res["insert"]["visivel_s"] == 4.0
    assert res["insert"]["consultas"] == 2
    assert res["insert"]["bytes_escaneados"] == 2000
    assert 0 < res["insert"]["janela_s"] <= res["insert"]["visivel_s"]


def test_timeout_stops_cycle_and_still_cleans_up():
    clock = FakeClock()
    lake = FakeLake(clock, never={"update"})  # processor não aplica o UPDATE
    res = _sample(lake, clock, timeout_s=10)
    assert res["insert"]["ok"] is True
    assert res["update"]["ok"] is False and res["update"]["visivel_s"] is None
    assert "delete" not in res  # parou no primeiro timeout
    assert "PED-PROBE-x-000" not in lake.mongo  # limpeza no finally
    assert lake.deleted == ["PED-PROBE-x-000"]


def test_cleanup_runs_when_athena_raises():
    clock = FakeClock()
    lake = FakeLake(clock)

    def boom(_):
        raise athena_side.AwsUnavailable("expirou")

    with pytest.raises(athena_side.AwsUnavailable):
        lake_probe.run_sample(lake, "PED-PROBE-y", boom, timeout_s=5, interval_s=1,
                              clock=clock, sleep=clock.sleep)
    assert "PED-PROBE-y" not in lake.mongo


def test_summary_percentiles_and_timeouts():
    ok = lambda s: {"ok": True, "visivel_s": s, "bytes_escaneados": 10}  # noqa: E731
    bad = {"ok": False, "visivel_s": None, "bytes_escaneados": 10}
    samples = [{"insert": ok(5), "update": ok(20), "delete": ok(30)},
               {"insert": ok(7), "update": bad},
               {"insert": ok(9), "update": ok(22), "delete": ok(40)}]
    out = lake_probe.summarize(samples)
    assert out["insert"] == {"amostras": 3, "convergiu": 3, "timeouts": 0, "p50_s": 7,
                             "p95_s": 9, "max_s": 9, "media_s": 7.0, "bytes_escaneados": 30}
    assert out["update"]["timeouts"] == 1 and out["update"]["convergiu"] == 2
    assert out["delete"]["amostras"] == 2


@pytest.mark.parametrize("db", ["iceberg_demo", "iceberg_demo_prod"])
def test_refuses_demo_db_without_flag(monkeypatch, db):
    monkeypatch.delenv("ALLOW_DEMO_DB_WRITE", raising=False)
    with pytest.raises(lake_probe.ProbeRefused):
        lake_probe.assert_safe_target(db)
    monkeypatch.setenv("ALLOW_DEMO_DB_WRITE", "1")
    lake_probe.assert_safe_target(db)


def test_main_without_aws_exits_2_and_writes_nothing(monkeypatch):
    monkeypatch.setattr(lake_probe.settings, "DATABASE_NAME", "iceberg_demo_test")
    monkeypatch.setattr(athena_side, "identity", lambda: {"disponivel": False, "erro": "expirada"})

    def no_mongo():
        raise AssertionError("não pode tocar o MongoDB sem AWS")

    monkeypatch.setattr(mongo_side, "collection", no_mongo)
    assert lake_probe.main(["--samples", "1"]) == 2


def test_main_demo_db_refused_before_aws(monkeypatch):
    monkeypatch.delenv("ALLOW_DEMO_DB_WRITE", raising=False)
    monkeypatch.setattr(lake_probe.settings, "DATABASE_NAME", "iceberg_demo")
    monkeypatch.setattr(athena_side, "identity", lambda: pytest.fail("não deveria chamar AWS"))
    assert lake_probe.main([]) == 2


# --- respostas da API só afirmam o que foi verificado ------------------------

@pytest.mark.parametrize("op", ["insert", "update", "delete", "schema"])
def test_demo_response_does_not_claim_propagation(monkeypatch, op):
    fakes = {
        "insert": lambda: {"_id": "PED-AOVIVO-001", "status": "PROCESSANDO"},
        "update": lambda: {"_id": "PED-AOVIVO-001", "status": "EM_TRANSPORTE"},
        "delete": lambda: {"removidos": 1},
        "schema": lambda: {"_id": "PED-AOVIVO-002", "fraudScore": 0.9},
    }
    monkeypatch.setattr(mongo_side, f"demo_{'schema_field' if op == 'schema' else op}", fakes[op])
    body = TestClient(main.app).post(f"/api/demo/{op}").json()
    assert body["propagacao"] == "aguardando_confirmacao"
    assert "MongoDB" in body["mensagem"]
    assert "já levou" not in body["mensagem"]
    assert "sozinho" not in body["mensagem"]


def _preflight(monkeypatch, aws_ok: bool):
    monkeypatch.setattr(mongo_side, "ping", lambda: None)
    monkeypatch.setattr(mongo_side, "post_images_enabled", lambda: True)

    class Dlq:
        def count_documents(self, _):
            return 0

    monkeypatch.setattr(mongo_side, "dlq", lambda: Dlq())
    monkeypatch.setattr(
        athena_side, "identity",
        lambda: {"disponivel": True, "arn": "arn:x"} if aws_ok else {"disponivel": False, "erro": "Credencial AWS expirada."},
    )
    return TestClient(main.app).get("/preflight").json()


def test_preflight_says_mongo_only_mode_without_aws(monkeypatch):
    body = _preflight(monkeypatch, aws_ok=False)
    assert body["ok"] is True
    assert body["modo"] == "somente_mongodb"
    assert "nenhuma propagação é confirmada" in body["resumo"]


def test_preflight_full_mode_with_aws(monkeypatch):
    body = _preflight(monkeypatch, aws_ok=True)
    assert body["modo"] == "completo"
